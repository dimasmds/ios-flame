"""Adversarial memory-map fixtures; called by check.py using the real C parser."""
import ctypes as c
import struct

U32 = lambda *v: struct.pack(">" + "I" * len(v), *v)
U64 = lambda *v: struct.pack(">" + "Q" * len(v), *v)


class Report(c.Structure):
    _fields_ = [(n, c.c_uint64) for n in ("candidate", "size", "highest_fixed_end")] + [
        (n, c.c_uint32) for n in ("ram_banks", "fixed_ranges", "reserve_entries", "dynamic_pools",
                                 "conflicts", "unbounded_pools", "errors", "contained")]


def fixture(reserved=(), reservations=(), ram=(0xc0000000, 0x140000000), chosen=(), ranges=True):
    names = bytearray()
    offsets = {}

    def prop(key, value):
        if key not in offsets:
            offsets[key] = len(names)
            names.extend(key.encode() + b"\0")
        return U32(3, len(value), offsets[key]) + value + bytes(-len(value) % 4)

    def node(name, props=(), children=()):
        s = name.encode() + b"\0"
        return U32(1) + s + bytes(-len(s) % 4) + b"".join(prop(k, v) for k, v in props) + b"".join(children) + U32(2)

    cells = [("#address-cells", U32(2)), ("#size-cells", U32(2))]
    children = [node("memory", [("reg", U64(*ram))]), node("reserved-memory", cells + ([("ranges", b"")] if ranges else []),
                [node(f"region{i}", props) for i, props in enumerate(reserved)]), node("chosen", chosen)]
    structure = node("", cells, children) + U32(9)
    reserve = b"".join(U64(*r) for r in reservations) + bytes(16)
    off = 40 + len(reserve)
    header = U32(0xd00dfeed, off + len(structure) + len(names), off, off + len(structure),
                 40, 17, 16, 0, len(names), len(structure))
    return header + reserve + structure + names


def check_memory(lib, DT):
    lib.map_check.argtypes = [c.POINTER(DT), c.c_uint64, c.c_uint64, c.c_uint64, c.c_uint64, c.POINTER(Report)]

    def run(data, base=0x100000000, size=0x40000000, image=(0x80080000, 0x80090000)):
        buf = c.create_string_buffer(data)
        dt, report = DT(), Report()
        assert lib.dt_open(c.byref(dt), buf, len(data))
        lib.map_check(c.byref(dt), base, size, *image, c.byref(report))
        return report

    def clear(r):
        return r.contained and not (r.errors or r.conflicts or r.unbounded_pools)

    static = lambda base, size: [("reg", U64(base, size))]
    dynamic = lambda base, size: [("size", U64(0x100000)), ("alloc-ranges", U64(base, size))]
    assert clear(run(fixture()))
    assert clear(run(fixture([static(0x9c400000, 0x2400000)])))
    assert not clear(run(fixture([static(0x110000000, 0x1000)])))
    assert not clear(run(fixture(reservations=[(0x100000000, 0x1000)])))
    assert not clear(run(fixture([[('size', U64(0x1000))]])))
    assert clear(run(fixture([dynamic(0x80000000, 0x40000000)])))
    assert not clear(run(fixture([dynamic(0x80000000, 0x100000000)])))
    assert clear(run(fixture([static(0x80000000, 0x1000) + [("size", U64(0x1000))]])))
    assert not clear(run(fixture(ranges=False)))
    assert not clear(run(fixture(), base=0x200000000))
    assert not clear(run(fixture(), base=0xfffffffffffff000))
    assert not clear(run(fixture(ram=(0xffffffffffff0000, 0x20000))))
    assert not clear(run(fixture(), image=(0x100000000, 0x100010000)))
    assert not clear(run(fixture(chosen=[("linux,initrd-start", U64(0x100000000)), ("linux,initrd-end", U64(0x100100000))])))
    assert not clear(run(fixture(chosen=[("linux,initrd-start", U32(0x80000000))])))
    assert not clear(run(fixture([[("reg", bytes(15))]])))
    truncated_reserve = bytearray(fixture())
    truncated_reserve[40:56] = U64(0x80000000, 0x1000)  # No terminator before structure.
    assert not clear(run(bytes(truncated_reserve)))
    broken = bytearray(fixture())
    off = struct.unpack_from(">I", broken, 8)[0]
    size = struct.unpack_from(">I", broken, 36)[0]
    broken[off + size - 4:off + size] = U32(4)  # Missing FDT_END.
    assert not clear(run(bytes(broken)))
    print("PASS: memory-map conflicts, dynamic pools, overflow, initrd/image exclusions, malformed reservations")
