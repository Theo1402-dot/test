"""MS-OVBA compression (Decompression and Compression).

Implements the algorithm specified in [MS-OVBA] section 2.4.1.
Used to write VBA source into vbaProject.bin module streams.

Reference: https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-ovba/

Decompression is also available in oletools.olevba; we reimplement it
here so we can be sure we're symmetric with our compressor.
"""

from __future__ import annotations
import struct

SIG_BYTE = 0x01
MAX_CHUNK_DECOMP_LEN = 4096


def _length_mask_offset_shift(decompressed_chunk_offset: int) -> tuple[int, int]:
    """[MS-OVBA] 2.4.1.3.19 — for a CopyToken at the given offset within the
    decompressed chunk, return (length_mask, offset_shift) where:
       length_mask = 0x000F .. 0x0FFF  (low N bits are the Length field)
       offset_shift = number of bits the Offset field is shifted left
    The split varies with position so that low offsets need fewer bits.
    """
    # Find the smallest n >= 4 such that 1<<n > decompressed_chunk_offset.
    # Actually the spec uses CopyTokenHelp algorithm:
    n = 4
    while (1 << n) < decompressed_chunk_offset:
        n += 1
    if n < 4:
        n = 4
    if n > 12:
        n = 12
    length_bits = 16 - n
    length_mask = (1 << length_bits) - 1
    offset_shift = length_bits
    return length_mask, offset_shift


# ---------- Decompression ----------

def decompress(data: bytes) -> bytes:
    """Decompress MS-OVBA-compressed bytes."""
    if not data or data[0] != SIG_BYTE:
        raise ValueError("Bad MS-OVBA signature byte")
    out = bytearray()
    pos = 1
    n = len(data)
    while pos < n:
        if pos + 2 > n:
            break
        header = struct.unpack_from('<H', data, pos)[0]
        pos += 2
        chunk_size = (header & 0x0FFF) + 3  # total chunk length incl. header (2 bytes)
        chunk_signature = (header >> 12) & 0x07
        chunk_flag = (header >> 15) & 0x01
        if chunk_signature != 0b011:
            raise ValueError("Bad chunk signature")
        chunk_data_len = chunk_size - 2  # excluding the 2-byte header
        chunk_data = data[pos:pos + chunk_data_len]
        pos += chunk_data_len
        if chunk_flag == 0:
            # Uncompressed chunk: 4096 bytes raw (or shorter if at end).
            out += chunk_data
        else:
            decompressed_start = len(out)
            cd_pos = 0
            cd_len = len(chunk_data)
            while cd_pos < cd_len:
                flag_byte = chunk_data[cd_pos]
                cd_pos += 1
                for bit in range(8):
                    if cd_pos >= cd_len:
                        break
                    is_copy = (flag_byte >> bit) & 1
                    if not is_copy:
                        out.append(chunk_data[cd_pos])
                        cd_pos += 1
                    else:
                        if cd_pos + 2 > cd_len:
                            break
                        token = struct.unpack_from('<H', chunk_data, cd_pos)[0]
                        cd_pos += 2
                        decompressed_chunk_off = len(out) - decompressed_start
                        length_mask, offset_shift = _length_mask_offset_shift(
                            decompressed_chunk_off)
                        length = (token & length_mask) + 3
                        offset = (token >> offset_shift) + 1
                        src = len(out) - offset
                        # bytewise copy (handles overlap)
                        for _ in range(length):
                            out.append(out[src])
                            src += 1
    return bytes(out)


# ---------- Compression ----------

def _find_longest_match(buf: memoryview, pos: int, chunk_start: int,
                       max_offset: int, max_length: int) -> tuple[int, int]:
    """Find the longest match ending at buf[pos:] looking back to
    `chunk_start`, with offset <= max_offset and length <= max_length.
    Returns (offset, length) where offset is positive (distance back).
    Returns (0, 0) if no match >= 3 is found.
    """
    n = len(buf)
    best_off = 0
    best_len = 0
    earliest = max(chunk_start, pos - max_offset)
    # Scan backwards.
    for start in range(pos - 1, earliest - 1, -1):
        ml = 0
        while (ml < max_length
               and pos + ml < n
               and buf[start + ml] == buf[pos + ml]):
            ml += 1
        if ml >= 3 and ml > best_len:
            best_off = pos - start
            best_len = ml
            if best_len == max_length:
                break
    return best_off, best_len


def _compress_chunk(chunk: bytes) -> bytes:
    """Compress one MS-OVBA chunk of up to 4096 decompressed bytes."""
    out = bytearray()
    pos = 0
    n = len(chunk)
    while pos < n:
        flag_pos = len(out)
        out.append(0)
        flag = 0
        for bit in range(8):
            if pos >= n:
                break
            length_mask, offset_shift = _length_mask_offset_shift(pos)
            max_length = length_mask + 3
            max_offset = (1 << (16 - offset_shift))
            off, ml = _find_longest_match(memoryview(chunk), pos, 0,
                                          max_offset, max_length)
            if ml >= 3:
                token = ((off - 1) << offset_shift) | (ml - 3)
                out.append(token & 0xFF)
                out.append((token >> 8) & 0xFF)
                flag |= (1 << bit)
                pos += ml
            else:
                out.append(chunk[pos])
                pos += 1
        out[flag_pos] = flag
    return bytes(out)


def compress(data: bytes) -> bytes:
    """MS-OVBA-compress raw bytes."""
    out = bytearray([SIG_BYTE])
    pos = 0
    n = len(data)
    while pos < n:
        chunk = data[pos:pos + MAX_CHUNK_DECOMP_LEN]
        compressed = _compress_chunk(chunk)
        # Decide compressed vs. raw chunk. The spec requires uncompressed
        # chunks to be exactly 4096 bytes data + 2 byte header, so only
        # use uncompressed for full chunks; for the trailing partial chunk
        # we must use the compressed form even if it's larger.
        use_raw = (len(chunk) == MAX_CHUNK_DECOMP_LEN
                   and len(compressed) >= len(chunk))
        if use_raw:
            payload = chunk
            chunk_flag = 0
            chunk_data_len = len(chunk)
        else:
            payload = compressed
            chunk_flag = 1
            chunk_data_len = len(payload)
        chunk_size = chunk_data_len + 2  # incl. 2-byte header
        header = ((0b011 << 12)
                  | (chunk_flag << 15)
                  | ((chunk_size - 3) & 0x0FFF))
        out += struct.pack('<H', header)
        out += payload
        pos += MAX_CHUNK_DECOMP_LEN
    return bytes(out)


# ---------- Self-test ----------

def _selftest() -> None:
    """Round-trip a variety of payloads through compress / decompress."""
    samples = [
        b"",
        b"A",
        b"AAAAAAAAA",
        b"Attribute VB_Name = \"Module1\"\r\nOption Explicit\r\n",
        b"".join(bytes([i % 256]) for i in range(5000)),
        b"abcabcabcabcabcabcabcabcabcabcabc" * 100,
    ]
    for s in samples:
        c = compress(s)
        d = decompress(c)
        assert d == s, f"round-trip failed for {len(s)}-byte sample"
    # Also: oletools' decompressor should agree.
    try:
        from oletools.olevba import decompress_stream as oletools_decompress
        for s in samples:
            c = compress(s)
            d = oletools_decompress(c)
            assert d == s, f"oletools disagrees on {len(s)}-byte sample"
    except ImportError:
        pass
    print("msovba self-test OK")


if __name__ == "__main__":
    _selftest()
