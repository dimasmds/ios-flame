#!/usr/bin/env python3
"""Host checks for the boot image and bounded parser before any device test."""
import ctypes
from pathlib import Path
import struct
import subprocess
import tempfile
import argparse
from lz4_image import decompress
from check_memory import check_memory
from check_ram import check_ram
from check_mmu import check_mmu
from check_loader import check_loader

ROOT = Path(__file__).resolve().parent
U32 = lambda *v: struct.pack(">" + "I" * len(v), *v)


def tree(structure, strings=b"reg\0"):
    return U32(0xd00dfeed, 56 + len(structure) + len(strings), 56,
               56 + len(structure), 40, 17, 16, 0, len(strings), len(structure)) + bytes(16) + structure + strings


def node(name):
    s = name.encode() + b"\0"
    return U32(1) + s + bytes(-len(s) % 4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", nargs="?", choices=["01", "02", "03", "04", "05", "06"], default="01")
    mode = parser.parse_args().mode
    with tempfile.TemporaryDirectory() as tmp:
        libpath = Path(tmp) / "fdt.so"
        subprocess.run(["gcc", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "fdt.c"), str(ROOT / "memory.c"), str(ROOT / "ram.c"), str(ROOT / "mmu.c"),
                        str(ROOT / "loader.c"), str(ROOT / "platform.c"), str(ROOT / "ufs.c"), "-o", str(libpath)], check=True)
        lib = ctypes.CDLL(str(libpath))

        class DT(ctypes.Structure):
            _fields_ = [("blob", ctypes.c_void_p)] + [(n, ctypes.c_uint32) for n in
                       ("size", "structure", "end", "strings", "strings_size")]

        lib.dt_open.argtypes = [ctypes.POINTER(DT), ctypes.c_void_p, ctypes.c_size_t]
        lib.dt_prop.argtypes = [ctypes.POINTER(DT), ctypes.c_char_p, ctypes.c_char_p,
                                ctypes.POINTER(ctypes.c_uint32)]
        lib.dt_prop.restype = ctypes.c_void_p
        check_memory(lib, DT)
        check_ram(lib)
        check_mmu(lib)
        check_loader(lib)
        # Exercise the actual capture routine with a mock bus. It may only
        # load these ten documented registers, once each, without writes.
        addresses = [0x1d84000 + off for off in (0, 8, 0x34, 0x30, 0x50, 0x54, 0x60, 0x58, 0x80, 0x78)]
        values = {address: 0xf0000000 + i for i, address in enumerate(addresses)}
        reads = []
        reader_type = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_size_t)
        def read32(address):
            reads.append(address)
            return values.get(address, 0)
        reader = reader_type(read32)
        report = (ctypes.c_uint32 * 10)()
        lib.ufs_capture.argtypes = [reader_type, ctypes.POINTER(ctypes.c_uint32)]
        lib.ufs_capture(reader, report)
        assert reads == addresses and list(report) == list(values.values())

        def lookup(data, path, key=b"reg"):
            buf = ctypes.create_string_buffer(data)
            dt = DT()
            if not lib.dt_open(ctypes.byref(dt), buf, len(data)):
                return None
            n = ctypes.c_uint32()
            p = lib.dt_prop(ctypes.byref(dt), path, key, ctypes.byref(n))
            return ctypes.string_at(p, n.value) if p else None

        # Nested properties must not be mistaken for their parent's property.
        s = node("") + node("memory") + node("child") + U32(3, 4, 0, 123) + U32(2)
        s += U32(3, 4, 0, 456) + U32(2, 2, 9)
        valid = tree(s)
        assert lookup(valid, b"/memory") == U32(456)
        assert lookup(valid, b"/memory/child") == U32(123)
        assert lookup(valid, b"/missing") is None
        assert lookup(valid[:-1], b"/memory") is None
        assert lookup(tree(node("") + node("memory") + U32(3, 0xffffffff, 0)), b"/memory") is None
        assert lookup(tree(node("") + node("memory") + U32(3, 4, 1000, 7)), b"/memory") is None
        assert lookup(tree(node("") + node("memory") + U32(3, 4, 0, 7), b"reg!"), b"/memory") is None
        assert lookup(tree(node("") + b"\0\0\0\1" + b"x" * 300), b"/memory") is None
        assert lookup(tree(node("") + node("a") * 33), b"/memory") is None

        inputs = ROOT.parent / "research/flame-sources"
        dtbs = (inputs / "sm8150-v2.dtb").read_bytes() + (inputs / "sm8150.dtb").read_bytes()
        offset, count = 0, 0
        while offset < len(dtbs):
            assert dtbs[offset:offset + 4] == U32(0xd00dfeed), f"Bad DTB at {offset}"
            size = struct.unpack_from(">I", dtbs, offset + 4)[0]
            assert 40 <= size <= len(dtbs) - offset
            blob = dtbs[offset:offset + size]
            assert lookup(blob, b"", b"compatible")
            assert lookup(blob, b"/psci", b"method") == b"smc\0"
            dt = DT()
            raw = ctypes.create_string_buffer(blob)
            assert lib.dt_open(ctypes.byref(dt), raw, len(blob))
            assert lib.platform_check(ctypes.byref(dt))
            assert lib.platform_ufs_check(ctypes.byref(dt))
            for pattern in (bytes.fromhex('01d8400000002500'), b'qcom,ufshc\0'):
                changed_ufs = bytearray(blob)
                changed_ufs[changed_ufs.index(pattern)] ^= 1
                raw_ufs_bad = ctypes.create_string_buffer(bytes(changed_ufs))
                assert lib.dt_open(ctypes.byref(dt), raw_ufs_bad, len(blob))
                assert not lib.platform_ufs_check(ctypes.byref(dt))
            changed = bytearray(blob)
            position = changed.index(bytes.fromhex('17a000000001000017a6000000100000'))
            changed[position] ^= 1
            raw_bad = ctypes.create_string_buffer(bytes(changed))
            assert lib.dt_open(ctypes.byref(dt), raw_bad, len(blob))
            assert not lib.platform_check(ctypes.byref(dt))
            offset += size
            count += 1
        print("PASS: ten whitelisted UFS register reads; both Google DTBs; wrong controller address/compatibility rejected")

    image_path = ROOT / f"out/flame-probe-{mode}.img"
    image = image_path.read_bytes()
    assert image[:8] == b"ANDROID!"
    kernel_size, kernel_addr, rd_size = struct.unpack_from("<3I", image, 8)
    assert struct.unpack_from("<I", image, 36)[0] == 4096
    assert struct.unpack_from("<I", image, 40)[0] == 2
    assert struct.unpack_from("<I", image, 1644)[0] == 1660
    kernel = decompress(image[4096:4096 + kernel_size])
    assert image[4096:4101] == bytes.fromhex("04224d1864")
    assert kernel == (ROOT / f"out/Image-{mode}").read_bytes()
    assert kernel[56:60] == b"ARM\x64"
    assert struct.unpack_from("<Q", kernel, 8)[0] == 0x80000
    assert struct.unpack_from("<Q", kernel, 16)[0] == len(kernel)
    assert kernel_addr == 0x8000
    if mode == "05":
        from embed import validate
        hits = [i for i in range(0, len(kernel) - 16, 4096) if kernel[i:i + 8] == b"FLAMEPLD"]
        assert len(hits) == 1
        offset = hits[0]
        size = struct.unpack_from('<Q', kernel, offset + 8)[0]
        assert len(kernel) <= 0x4000000 and size == len(kernel) - offset - 16
        validate(kernel[offset + 16:])
    dtb_offset = 4096 + (kernel_size + 4095) // 4096 * 4096 + (rd_size + 4095) // 4096 * 4096
    dtb_size = struct.unpack_from("<I", image, 1648)[0]
    assert image[dtb_offset:dtb_offset + dtb_size] == dtbs
    assert len(image) == 0x04000000
    assert image[-64:-60] == b"AVBf"
    original_size, vbmeta_offset, vbmeta_size = struct.unpack_from(">3Q", image, len(image) - 64 + 12)
    assert original_size <= vbmeta_offset < len(image) - 64
    assert 256 <= vbmeta_size < len(image) - 64 - vbmeta_offset
    assert image[vbmeta_offset:vbmeta_offset + 4] == b"AVB0"
    with tempfile.TemporaryDirectory() as tmp:
        # avbtool resolves the hash descriptor's partition name as boot.img.
        boot = Path(tmp) / "boot.img"
        boot.symlink_to(image_path)
        subprocess.run(["python3", str(inputs / "avbtool.py"), "verify_image", "--image",
                        str(boot)], check=True, stdout=subprocess.DEVNULL)
    print(f"PASS: malformed/nested FDT checks; {count} Google DTBs; arm64 Image and Pixel boot-v2 packaging")


if __name__ == "__main__":
    main()
