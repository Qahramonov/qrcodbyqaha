#!/usr/bin/env python3
"""Pure-Python zipalign: rewrites an APK so every STORED entry starts on a 4-byte boundary
(16 KiB for native .so libraries), matching `zipalign -p 4`. Used when the SDK zipalign is unavailable
(e.g. building on a phone in Termux). Compressed entries keep their original deflate data."""
from __future__ import annotations

import struct
import sys
import zipfile


def align(src: str, dst: str, alignment: int = 4) -> None:
    with zipfile.ZipFile(src) as zin, open(dst, "wb") as out:
        central = []
        for info in zin.infolist():
            raw = zin.open(info).read() if info.compress_type == zipfile.ZIP_STORED else _raw_compressed(zin, info)
            name = info.filename.encode("utf-8")
            offset = out.tell()
            header_len = 30 + len(name)
            extra = b""
            if info.compress_type == zipfile.ZIP_STORED:
                a = 16384 if info.filename.endswith(".so") else alignment
                pad = (a - (offset + header_len) % a) % a
                extra = b"\x00" * pad
            flags = info.flag_bits & ~0x08  # no data descriptor
            dostime = _dostime(info.date_time)
            out.write(struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, flags, info.compress_type, dostime[1], dostime[0],
                                  info.CRC, info.compress_size, info.file_size, len(name), len(extra)))
            out.write(name)
            out.write(extra)
            out.write(raw)
            central.append((info, name, offset, flags, dostime))
        cd_start = out.tell()
        for info, name, offset, flags, dostime in central:
            out.write(struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, flags, info.compress_type, dostime[1], dostime[0],
                                  info.CRC, info.compress_size, info.file_size, len(name), 0, 0, 0, 0, info.external_attr, offset))
            out.write(name)
        cd_size = out.tell() - cd_start
        out.write(struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(central), len(central), cd_size, cd_start, 0))


def _raw_compressed(z: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    z.fp.seek(info.header_offset)
    h = z.fp.read(30)
    n, m = struct.unpack("<HH", h[26:30])
    z.fp.seek(info.header_offset + 30 + n + m)
    return z.fp.read(info.compress_size)


def _dostime(dt: tuple) -> tuple[int, int]:
    y, mo, d, h, mi, s = dt
    return ((y - 1980) << 9) | (mo << 5) | d, (h << 11) | (mi << 5) | (s // 2)


def check(path: str, alignment: int = 4) -> bool:
    ok = True
    with zipfile.ZipFile(path) as z, open(path, "rb") as f:
        for info in z.infolist():
            if info.compress_type != zipfile.ZIP_STORED:
                continue
            f.seek(info.header_offset)
            h = f.read(30)
            n, m = struct.unpack("<HH", h[26:30])
            data = info.header_offset + 30 + n + m
            a = 16384 if info.filename.endswith(".so") else alignment
            if data % a:
                print(f"misaligned: {info.filename} @ {data}")
                ok = False
    return ok


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "-c":
        sys.exit(0 if check(sys.argv[2]) else 1)
    if len(sys.argv) != 3:
        print("usage: zipalign.py IN.apk OUT.apk | zipalign.py -c APK")
        sys.exit(2)
    align(sys.argv[1], sys.argv[2])
    sys.exit(0 if check(sys.argv[2]) else 1)
