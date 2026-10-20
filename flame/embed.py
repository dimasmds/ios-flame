#!/usr/bin/env python3
"""Append an exactly bounded payload inside the decompressed Pixel Image."""
import ctypes
from pathlib import Path
import struct
import subprocess
import sys
import tempfile


def validate(data):
    root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory() as tmp:
        shared = Path(tmp) / "loader.so"
        subprocess.run(["gcc", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
                        str(root / "loader.c"), "-o", str(shared)], check=True)
        lib = ctypes.CDLL(str(shared))
        lib.payload_validate.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
        lib.payload_validate.restype = ctypes.c_char_p
        plan = (ctypes.c_uint64 * 4)()
        buf = ctypes.create_string_buffer(data)
        error = lib.payload_validate(buf, len(data), plan)
        if error:
            raise ValueError(error.decode())
        return list(plan)


if __name__ == "__main__":
    payload = Path(sys.argv[1]).read_bytes()
    print("Validated payload offsets:", [hex(v) for v in validate(payload)])
    image_path = Path(__file__).resolve().parent / "out/Image"
    image = bytearray(image_path.read_bytes())
    image += bytes(-len(image) % 4096)
    image += struct.pack("<8sQ", b"FLAMEPLD", len(payload)) + payload
    if len(image) > 0x4000000:
        raise ValueError("Decompressed Image exceeds the 64 MiB Pixel test limit")
    struct.pack_into("<Q", image, 16, len(image))
    image_path.write_bytes(image)
