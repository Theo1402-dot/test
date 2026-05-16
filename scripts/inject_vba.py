"""Inject VBA source code into an existing xlsm's vbaProject.bin.

Strategy:
  1. Read vbaProject.bin from the xlsm zip.
  2. Decompress the dir stream, find MODULEOFFSET for each target module.
  3. For each target module, read its existing stream:
       header_bytes = stream[:offset]      (PerformanceCache; keep verbatim)
       existing_src = decompress(stream[offset:])  (just the Attribute lines)
       new_full_src = existing_src + b"\\r\\n" + new_user_code
       new_stream  = header_bytes + compress(new_full_src)
  4. Rewrite vbaProject.bin as a fresh CFB with the new stream contents.
  5. Repack the xlsm with the updated vbaProject.bin.

This preserves attribute headers (which Excel needs) and only appends the
user-provided source code below them.

Usage:
    python3 inject_vba.py <in.xlsm> <out.xlsm> \\
        --module Module1=path/to/Module1.bas \\
        --module ThisWorkbook=path/to/ThisWorkbook.cls
"""

from __future__ import annotations
import argparse
import io
import struct
import sys
import re
import zipfile
import shutil
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olefile  # type: ignore
from msovba import compress, decompress
import cfb


VBA_DIR_PATH = "VBA/dir"


# ---------- dir-stream MODULEOFFSET helpers ----------

def find_module_offsets(dir_decompressed: bytes) -> dict[str, int]:
    """Return {module_name: source_offset_within_its_stream} by scanning
    the decompressed dir stream for MODULESTREAMNAME (0x001A) records
    followed by MODULEOFFSET (0x0031) records."""
    result: dict[str, int] = {}
    pending_name: str | None = None
    # Scan for record-pair patterns.
    # MODULESTREAMNAME: id=0x001A, size=N, payload=N bytes (MBCS string)
    # MODULEOFFSET   : id=0x0031, size=4,  payload=uint32
    i = 0
    while i + 6 <= len(dir_decompressed):
        rid = struct.unpack_from("<H", dir_decompressed, i)[0]
        rsize = struct.unpack_from("<I", dir_decompressed, i + 2)[0]
        if rsize > len(dir_decompressed) - (i + 6):
            i += 1
            continue
        payload = dir_decompressed[i + 6:i + 6 + rsize]
        if rid == 0x001A and 1 <= rsize <= 64 and all(0x20 <= b < 0x7F or b in (0, 9, 10, 13) for b in payload):
            pending_name = payload.decode("cp1252", errors="replace").rstrip("\x00")
        elif rid == 0x0031 and rsize == 4 and pending_name is not None:
            off = struct.unpack_from("<I", payload)[0]
            result[pending_name] = off
            pending_name = None
        i += 6 + rsize
    return result


# ---------- vbaProject.bin patcher ----------

def patch_vba_project_bin(vba_bin: bytes, new_sources: dict[str, str]) -> bytes:
    """Return a new vbaProject.bin where the given module sources have
    been replaced (appended after the existing Attribute header lines).

    `new_sources` maps module name (e.g. "Module1") to the new VBA code
    that should appear AFTER the Attribute header lines.
    """
    # Open the existing bin to read every stream.
    src_buf = io.BytesIO(vba_bin)
    ole = olefile.OleFileIO(src_buf)
    dir_raw = ole.openstream("VBA/dir").read()
    dir_decomp = decompress(dir_raw)
    module_offsets = find_module_offsets(dir_decomp)

    replacements: dict[str, bytes] = {}
    for module_name, new_code in new_sources.items():
        stream_path = f"VBA/{module_name}"
        if not ole.exists(stream_path):
            raise KeyError(f"No such VBA module stream: {stream_path}")
        if module_name not in module_offsets:
            raise KeyError(f"MODULEOFFSET not found for {module_name}")
        offset = module_offsets[module_name]
        stream = ole.openstream(stream_path).read()
        header_bytes = stream[:offset]
        existing_src_bytes = decompress(stream[offset:])
        # Make sure to use CRLF line endings and ensure the existing
        # Attribute lines end with a newline before we append.
        existing = existing_src_bytes
        if existing and not existing.endswith(b"\r\n"):
            existing += b"\r\n"
        new_code_bytes = new_code.replace("\r\n", "\n").replace("\n", "\r\n").encode("cp1252", errors="replace")
        if not new_code_bytes.endswith(b"\r\n"):
            new_code_bytes += b"\r\n"
        full_src = existing + new_code_bytes
        compressed = compress(full_src)
        replacements[stream_path] = header_bytes + compressed
    ole.close()

    # Now rewrite the CFB using our writer.
    # Provide the patched streams as overrides.
    src_buf2 = io.BytesIO(vba_bin)
    # cfb.rebuild_vba_project expects a path; we'll write to a temp file.
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
        tf.write(vba_bin)
        tmp_path = tf.name
    try:
        rebuilt = cfb.rebuild_vba_project(tmp_path, replacements)
    finally:
        try: os.unlink(tmp_path)
        except OSError: pass
    return rebuilt


# ---------- xlsm in-place updater ----------

def update_xlsm(src_xlsm: str, dst_xlsm: str, new_sources: dict[str, str]) -> None:
    """Read src_xlsm, patch its vbaProject.bin with new_sources, write to dst_xlsm."""
    with zipfile.ZipFile(src_xlsm, "r") as zin:
        names = zin.namelist()
        if "xl/vbaProject.bin" not in names:
            raise RuntimeError("xlsm has no xl/vbaProject.bin")
        vba_bin = zin.read("xl/vbaProject.bin")

    patched = patch_vba_project_bin(vba_bin, new_sources)

    # Write a fresh zip preserving everything else.
    with zipfile.ZipFile(src_xlsm, "r") as zin, \
         zipfile.ZipFile(dst_xlsm, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in zin.namelist():
            if name == "xl/vbaProject.bin":
                zout.writestr(name, patched)
            else:
                zout.writestr(name, zin.read(name))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("src", help="input xlsm")
    p.add_argument("dst", help="output xlsm")
    p.add_argument("--module", action="append", default=[],
                   help="Module_Name=path/to/source.bas (can be given multiple times)")
    args = p.parse_args(argv)

    new_sources: dict[str, str] = {}
    for spec in args.module:
        if "=" not in spec:
            print(f"bad --module spec: {spec}", file=sys.stderr)
            return 2
        name, path = spec.split("=", 1)
        with open(path, "r", encoding="utf-8") as f:
            new_sources[name] = f.read()

    update_xlsm(args.src, args.dst, new_sources)
    print(f"wrote {args.dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
