"""Minimal Compound File Binary (MS-CFB) writer.

Just enough to rewrite a vbaProject.bin where some streams need to grow.

Reads via the existing olefile, then rewrites a fresh CFB v3 (512-byte
sectors, 64-byte mini-sectors).  Stream contents may be replaced before
writing.

References:
  [MS-CFB]: Compound File Binary File Format
  https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/
"""

from __future__ import annotations
import struct
from dataclasses import dataclass, field
from typing import Optional

import olefile

# Special FAT entries
FREESECT       = 0xFFFFFFFF
ENDOFCHAIN     = 0xFFFFFFFE
FATSECT        = 0xFFFFFFFD
DIFSECT        = 0xFFFFFFFC
NOSTREAM       = 0xFFFFFFFF

SECTOR_SIZE     = 512
MINI_SECTOR_SIZE = 64
MINI_CUTOFF      = 4096
FAT_ENTRIES_PER_SECTOR     = SECTOR_SIZE // 4              # 128
DIRENTRIES_PER_SECTOR      = SECTOR_SIZE // 128            # 4
DIFAT_ENTRIES_PER_SECTOR   = (SECTOR_SIZE // 4) - 1        # 127
DIFAT_HEADER_SLOTS         = 109

HEADER_MAGIC = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"


@dataclass
class DirEntry:
    name: str
    type: int            # 1=storage, 2=stream, 5=root
    left: int = NOSTREAM
    right: int = NOSTREAM
    child: int = NOSTREAM
    clsid: bytes = b"\x00" * 16
    state: int = 0
    create_time: int = 0
    modify_time: int = 0
    start_sector: int = 0
    size: int = 0
    color: int = 1       # 0=red, 1=black -- black is fine for simple files
    data: bytes = b""    # not serialized; used during build

    def serialize(self) -> bytes:
        name_utf16 = self.name.encode("utf-16-le") + b"\x00\x00"
        if len(name_utf16) > 64:
            raise ValueError(f"Directory entry name too long: {self.name!r}")
        name_padded = name_utf16 + b"\x00" * (64 - len(name_utf16))
        name_len = len(name_utf16)
        out = name_padded
        out += struct.pack("<H", name_len)
        out += struct.pack("<BB", self.type, self.color)
        out += struct.pack("<III", self.left, self.right, self.child)
        out += self.clsid
        out += struct.pack("<I", self.state)
        out += struct.pack("<Q", self.create_time)
        out += struct.pack("<Q", self.modify_time)
        out += struct.pack("<I", self.start_sector)
        out += struct.pack("<Q", self.size)
        return out


def _build_red_black_children(child_indices: list[int],
                              entries: list[DirEntry]) -> int:
    """Return the index that should be the parent's Child pointer for the
    given list of child directory indices.  We assemble them as a sorted
    binary tree using the CFB's case-insensitive name comparison rule
    (shortest name first, otherwise upper-case lexicographic).
    """
    def key(idx: int):
        name = entries[idx].name
        return (len(name), name.upper())
    if not child_indices:
        return NOSTREAM
    sorted_children = sorted(child_indices, key=key)

    def build(lo: int, hi: int) -> int:
        if lo > hi:
            return NOSTREAM
        mid = (lo + hi) // 2
        idx = sorted_children[mid]
        entries[idx].left = build(lo, mid - 1)
        entries[idx].right = build(mid + 1, hi)
        return idx
    return build(0, len(sorted_children) - 1)


class CFBWriter:
    """Builds a CFB compound file from a list of (path, data) streams."""

    def __init__(self) -> None:
        # path -> bytes;  paths look like "/Root/PROJECT" or "/Root/VBA/dir"
        self.streams: dict[str, bytes] = {}
        self.storages: set[str] = set()       # "/Root/VBA" etc
        self.root_clsid: bytes = b"\x00" * 16

    # ---- builder API ----

    def add_storage(self, path: str) -> None:
        self.storages.add(path)

    def add_stream(self, path: str, data: bytes) -> None:
        self.streams[path] = data
        # Ensure parent storages exist
        parts = path.split("/")
        for i in range(1, len(parts)):
            self.storages.add("/".join(parts[:i]))

    # ---- serialize ----

    def build(self) -> bytes:
        # 1) Build dir entries.
        # Paths are like "PROJECT", "VBA/Module1" — no leading slash and no
        # "Root" prefix.  The Root Entry is the implicit root storage.
        path_index: dict[str, int] = {}
        entries: list[DirEntry] = []

        # Root entry is at index 0.
        root = DirEntry(name="Root Entry", type=5)
        root.clsid = self.root_clsid
        entries.append(root)
        path_index[""] = 0   # Empty path key represents the root

        # Add storages (sorted shallowest first so parents exist when we
        # link).  We don't include "" (the root) here.
        def depth(p: str) -> int:
            return 0 if p == "" else p.count("/") + 1
        storages_sorted = sorted(self.storages, key=depth)
        for s in storages_sorted:
            if s == "":
                continue
            name = s.rsplit("/", 1)[-1]
            de = DirEntry(name=name, type=1)
            entries.append(de)
            path_index[s] = len(entries) - 1

        # Add streams.
        for path, _data in self.streams.items():
            name = path.rsplit("/", 1)[-1]
            de = DirEntry(name=name, type=2)
            de.data = self.streams[path]
            de.size = len(de.data)
            entries.append(de)
            path_index[path] = len(entries) - 1

        # 2) Establish Child/Left/Right pointers for every storage entry
        # including the root.
        for storage_path, idx in list(path_index.items()):
            if entries[idx].type not in (1, 5):
                continue
            children: list[int] = []
            for sub_path, sub_idx in path_index.items():
                if sub_path == storage_path:
                    continue
                if storage_path == "":
                    parent = sub_path.rsplit("/", 1)[0] if "/" in sub_path else ""
                else:
                    parent = sub_path.rsplit("/", 1)[0] if "/" in sub_path else ""
                if parent == storage_path:
                    children.append(sub_idx)
            entries[idx].child = _build_red_black_children(children, entries)

        # 3) Layout streams.
        #    Streams >= MINI_CUTOFF go into regular sectors.
        #    Streams <  MINI_CUTOFF go into the mini stream (within Root entry).
        # Mini stream is stored in the Root entry as a regular stream.

        regular_streams: list[tuple[int, bytes]] = []  # (dir_idx, bytes)
        mini_streams:    list[tuple[int, bytes]] = []
        for path, didx in path_index.items():
            de = entries[didx]
            if de.type != 2:
                continue
            if de.size >= MINI_CUTOFF:
                regular_streams.append((didx, de.data))
            else:
                mini_streams.append((didx, de.data))

        # Build mini stream contents and per-stream mini-FAT chain.
        mini_stream_blob = bytearray()
        mini_fat: list[int] = []     # FREESECT or chain entries

        def alloc_mini_sectors(data: bytes) -> int:
            """Append data into the mini stream and return its first
            mini-sector index, while updating mini_fat to chain it."""
            if len(data) == 0:
                return ENDOFCHAIN
            start = len(mini_stream_blob) // MINI_SECTOR_SIZE
            n = (len(data) + MINI_SECTOR_SIZE - 1) // MINI_SECTOR_SIZE
            # Pad data to mini-sector boundary
            padded = data + b"\x00" * (n * MINI_SECTOR_SIZE - len(data))
            mini_stream_blob.extend(padded)
            # Build the chain
            for i in range(n):
                if i == n - 1:
                    mini_fat.append(ENDOFCHAIN)
                else:
                    mini_fat.append(start + i + 1)
            return start

        for didx, data in mini_streams:
            entries[didx].start_sector = alloc_mini_sectors(data)

        # Pad mini-FAT to a multiple of FAT_ENTRIES_PER_SECTOR
        while len(mini_fat) % FAT_ENTRIES_PER_SECTOR != 0:
            mini_fat.append(FREESECT)

        # 4) Compute layout of regular sectors.
        #    Order in sectors: stream data | mini stream | directory | mini-FAT | FAT
        #    The FAT, mini-FAT and directory chains all live in regular sectors.

        # We accumulate sectors as a list of 512-byte blobs.
        sectors: list[bytes] = []
        fat: list[int] = []   # mirrors sectors[]: tells what each sector's chain entry should be

        def pad_to_sector(data: bytes) -> bytes:
            r = len(data) % SECTOR_SIZE
            if r == 0:
                return data
            return data + b"\x00" * (SECTOR_SIZE - r)

        def alloc_chain(data: bytes) -> int:
            """Allocate `data` into the regular FAT chain.  Returns the
            starting sector number.  Pads to a sector boundary.
            """
            if len(data) == 0:
                return ENDOFCHAIN
            padded = pad_to_sector(data)
            n = len(padded) // SECTOR_SIZE
            start = len(sectors)
            for i in range(n):
                sectors.append(padded[i * SECTOR_SIZE:(i + 1) * SECTOR_SIZE])
                if i == n - 1:
                    fat.append(ENDOFCHAIN)
                else:
                    fat.append(start + len(sectors))  # next sector idx (just appended)
                    # Actually we want fat[start+i] = start+i+1
                    # Easier: rewrite after the loop.
            # Fix chain pointers (the appended fat entries above weren't correct).
            for i in range(n):
                if i == n - 1:
                    fat[start + i] = ENDOFCHAIN
                else:
                    fat[start + i] = start + i + 1
            return start

        # 4a) Allocate regular streams.
        for didx, data in regular_streams:
            entries[didx].start_sector = alloc_chain(data)

        # 4b) Allocate the mini stream itself as a regular stream, owned by Root.
        root_mini_start = alloc_chain(bytes(mini_stream_blob))
        entries[0].start_sector = root_mini_start
        entries[0].size = len(mini_stream_blob)

        # 4c) Build directory sectors (serialized entries).
        # Pad entries to a multiple of 4 (DIRENTRIES_PER_SECTOR).
        while len(entries) % DIRENTRIES_PER_SECTOR != 0:
            entries.append(DirEntry(name="", type=0))
        dir_blob = b"".join(e.serialize() for e in entries)
        dir_start = alloc_chain(dir_blob)

        # 4d) Mini-FAT sectors.
        if mini_fat:
            mini_fat_blob = struct.pack("<" + "I" * len(mini_fat), *mini_fat)
            mini_fat_start = alloc_chain(mini_fat_blob)
            num_minifat_sectors = len(mini_fat_blob) // SECTOR_SIZE
        else:
            mini_fat_start = ENDOFCHAIN
            num_minifat_sectors = 0

        # 4e) Allocate FAT sectors.  This is tricky because the FAT
        #     itself occupies sectors that need entries in the FAT marked
        #     as FATSECT.  Solve iteratively.
        # Current size of fat[] before FAT sectors themselves:
        # Compute number of FAT sectors needed considering they take up
        # sectors AND extra entries.
        # FAT entries needed = current len(fat) + num_fat_sectors
        # num_fat_sectors = ceil(FAT entries / 128)
        # Iterate to fixed point.
        num_fat_sectors = 0
        while True:
            est = (len(fat) + num_fat_sectors + FAT_ENTRIES_PER_SECTOR - 1) // FAT_ENTRIES_PER_SECTOR
            if est == num_fat_sectors:
                break
            num_fat_sectors = est

        # Reserve sector slots for FAT.
        fat_sector_indices: list[int] = []
        for _ in range(num_fat_sectors):
            idx = len(sectors)
            sectors.append(b"\x00" * SECTOR_SIZE)  # placeholder
            fat.append(FATSECT)                     # mark this sector as FAT
            fat_sector_indices.append(idx)

        # 4f) DIFAT in header has 109 slots.  If we have <=109 FAT sectors
        # they fit in the header; otherwise we need DIFAT chain sectors.
        # Keep it simple: support up to 109 FAT sectors (suffices for ~7 MB).
        if num_fat_sectors > DIFAT_HEADER_SLOTS:
            raise NotImplementedError(
                f"too many FAT sectors ({num_fat_sectors}); DIFAT chain not implemented")

        # 4g) Pad FAT to whole-sector multiple of entries.
        # The FAT covers ALL sectors -- its length must equal len(sectors).
        # Pad the tail with FREESECT to reach a multiple of 128.
        target = num_fat_sectors * FAT_ENTRIES_PER_SECTOR
        while len(fat) < target:
            fat.append(FREESECT)
        # And ensure len(fat) == len(sectors) (they should match).
        # Actually fat[] only has entries up to len(sectors); the freesect
        # padding above brought it up to target.  But target may be > len(sectors).
        # That's fine — extra entries are FREESECT.

        # 4h) Write FAT into the reserved FAT sectors.
        fat_blob = struct.pack("<" + "I" * len(fat), *fat)
        assert len(fat_blob) == num_fat_sectors * SECTOR_SIZE
        for i, sec_idx in enumerate(fat_sector_indices):
            sectors[sec_idx] = fat_blob[i * SECTOR_SIZE:(i + 1) * SECTOR_SIZE]

        # 5) Build the header.
        header = bytearray()
        header += HEADER_MAGIC
        header += b"\x00" * 16  # CLSID
        header += struct.pack("<H", 0x003E)  # MinorVersion
        header += struct.pack("<H", 0x0003)  # MajorVersion (v3, 512-byte sectors)
        header += struct.pack("<H", 0xFFFE)  # ByteOrder
        header += struct.pack("<H", 0x0009)  # SectorShift (2^9 = 512)
        header += struct.pack("<H", 0x0006)  # MiniSectorShift (2^6 = 64)
        header += b"\x00" * 6                # Reserved
        header += struct.pack("<I", 0)       # NumDirSectors (must be 0 in v3)
        header += struct.pack("<I", num_fat_sectors)
        header += struct.pack("<I", dir_start)
        header += struct.pack("<I", 0)       # TransactionSig
        header += struct.pack("<I", MINI_CUTOFF)
        header += struct.pack("<I", mini_fat_start)
        header += struct.pack("<I", num_minifat_sectors)
        header += struct.pack("<I", ENDOFCHAIN)  # FirstDIFATSectorLocation
        header += struct.pack("<I", 0)            # NumDIFATSectors
        # DIFAT array (109 entries)
        difat = list(fat_sector_indices) + [FREESECT] * (DIFAT_HEADER_SLOTS - len(fat_sector_indices))
        header += struct.pack("<" + "I" * DIFAT_HEADER_SLOTS, *difat)
        assert len(header) == SECTOR_SIZE

        # 6) Assemble.
        out = bytes(header) + b"".join(sectors)
        return out


# ---------- Higher-level helper: rebuild vbaProject.bin ----------

def rebuild_vba_project(src_path: str, replacements: dict[str, bytes]) -> bytes:
    """Read `src_path`, copy every stream verbatim, except those whose path
    appears as a key in `replacements` (where the value is the new bytes).
    Returns the rewritten compound file as bytes.

    Stream path keys are CFB-relative, e.g. "VBA/Module1".
    """
    ole = olefile.OleFileIO(src_path)
    writer = CFBWriter()
    # Preserve root CLSID (some apps care about it).
    try:
        writer.root_clsid = ole.root.clsid_bytes if hasattr(ole.root, "clsid_bytes") else b"\x00" * 16
    except Exception:
        writer.root_clsid = b"\x00" * 16

    for parts in ole.listdir(streams=True, storages=True):
        key = "/".join(parts)
        if ole.get_type(parts) == olefile.STGTY_STREAM:
            data = ole.openstream(parts).read()
            if key in replacements:
                data = replacements[key]
            writer.add_stream(key, data)
        else:
            writer.add_storage(key)
    ole.close()
    return writer.build()
