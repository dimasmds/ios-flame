#!/usr/bin/env python3
"""Use the system liblz4 to match the Pixel stock kernel's LZ4 frame format."""
import ctypes as c
import ctypes.util
from pathlib import Path
import sys


def library():
    name = ctypes.util.find_library("lz4")
    if not name:
        raise SystemExit("System liblz4 is required for the Pixel kernel wrapper")
    lib = c.CDLL(name)
    signatures = {
        "LZ4F_compressFrameBound": (c.c_size_t, [c.c_size_t, c.c_void_p]),
        "LZ4F_compressFrame": (c.c_size_t, [c.c_void_p, c.c_size_t, c.c_void_p, c.c_size_t, c.c_void_p]),
        "LZ4F_isError": (c.c_uint, [c.c_size_t]),
        "LZ4F_createDecompressionContext": (c.c_size_t, [c.POINTER(c.c_void_p), c.c_uint]),
        "LZ4F_freeDecompressionContext": (c.c_size_t, [c.c_void_p]),
        "LZ4F_decompress": (c.c_size_t, [c.c_void_p, c.c_void_p, c.POINTER(c.c_size_t), c.c_void_p, c.POINTER(c.c_size_t), c.c_void_p]),
    }
    for fn, (result, args) in signatures.items():
        getattr(lib, fn).restype = result
        getattr(lib, fn).argtypes = args
    return lib


def compress(data):
    lib = library()
    # Stable public ABI in lz4frame.h. Stock uses independent 4 MiB blocks
    # and a content checksum. liblz4 may reduce the block size for a tiny input.
    class FrameInfo(c.Structure):
        _fields_ = [(n, c.c_int) for n in ("blockSizeID", "blockMode", "contentChecksumFlag", "frameType")] + [
            ("contentSize", c.c_ulonglong), ("dictID", c.c_uint), ("blockChecksumFlag", c.c_int)]

    class Preferences(c.Structure):
        _fields_ = [("frameInfo", FrameInfo), ("compressionLevel", c.c_int),
                    ("autoFlush", c.c_uint), ("favorDecSpeed", c.c_uint), ("reserved", c.c_uint * 3)]

    prefs = Preferences()
    prefs.frameInfo.blockSizeID = 7
    prefs.frameInfo.blockMode = 1
    prefs.frameInfo.contentChecksumFlag = 1
    capacity = lib.LZ4F_compressFrameBound(len(data), c.byref(prefs))
    dst = c.create_string_buffer(capacity)
    size = lib.LZ4F_compressFrame(dst, capacity, data, len(data), c.byref(prefs))
    if lib.LZ4F_isError(size):
        raise ValueError("LZ4 compression failed")
    return dst.raw[:size]


def decompress(data, limit=0x4000000):
    # Match the bounded loader's 64 MiB Image limit, including a RAM root.
    lib = library()
    ctx = c.c_void_p()
    if lib.LZ4F_isError(lib.LZ4F_createDecompressionContext(c.byref(ctx), 100)):
        raise ValueError("LZ4 decoder initialization failed")
    chunks, offset, total = [], 0, 0
    try:
        while True:
            out = c.create_string_buffer(65536)
            ns, nd = c.c_size_t(len(data) - offset), c.c_size_t(len(out))
            result = lib.LZ4F_decompress(ctx, out, c.byref(nd), data[offset:], c.byref(ns), None)
            if lib.LZ4F_isError(result) or total + nd.value > limit:
                raise ValueError("Invalid/oversized LZ4 frame")
            chunks.append(out.raw[:nd.value]); offset += ns.value; total += nd.value
            if result == 0:
                if offset != len(data):
                    raise ValueError("Trailing bytes after LZ4 frame")
                return b"".join(chunks)
            if not ns.value and not nd.value:
                raise ValueError("Truncated LZ4 frame")
    finally:
        lib.LZ4F_freeDecompressionContext(ctx)


if __name__ == "__main__":
    data = Path(sys.argv[1]).read_bytes()
    packed = compress(data)
    assert decompress(packed) == data
    Path(sys.argv[2]).write_bytes(packed)
