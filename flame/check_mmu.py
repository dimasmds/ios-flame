"""Inspect real table-builder output; protected neighbours must stay unmapped."""
import ctypes as c


def check_mmu(lib):
    class Report(c.Structure):
        _fields_ = [(n, c.c_uint64) for n in ("root", "tables", "image_lo", "image_hi",
                                              "saved_sctlr", "saved_tcr", "saved_mair", "saved_ttbr")]

    lib.mmu_prepare.argtypes = [c.c_size_t, c.c_size_t, c.c_size_t, c.c_uint64,
                                c.c_size_t, c.c_size_t, c.POINTER(Report)]
    report = Report()
    args = (0x80080000, 0x800c0000, 0x9c400000, 1080 * 2280 * 4, 0x100000000, 0x13fffc000)
    assert lib.mmu_prepare(*args, c.byref(report)) == 1
    assert report.root % 0x4000 == 0 and report.tables == 5

    def entry(address):
        root = (c.c_uint64 * 2048).from_address(report.root)
        table = root[address >> 25]
        if not table:
            return 0
        assert table & 3 == 3
        page = (c.c_uint64 * 2048).from_address(table & 0x0000ffffffffc000)
        return page[(address >> 14) & 2047]

    for address in (0x80080000, 0x800bc000, 0x9c400000, 0x100000000, 0x13fffc000):
        pte = entry(address)
        assert pte & 3 == 3 and pte & (1 << 10)
        assert pte & 0x0000ffffffffc000 == address
    assert not entry(0x80080000) & (1 << 53)  # Probe instructions executable.
    assert entry(0x100000000) & (1 << 53)    # Test data not executable.
    for address in (0x8007c000, 0x800c0000, 0x85e00000, 0x9c000000, 0x9c3fc000,
                    0x100004000, 0x110000000, 0x13fff8000, 0x140000000):
        assert entry(address) == 0, hex(address)
    viewport_end = (0x9c400000 + 1080 * 2280 * 4 + 0x3fff) & ~0x3fff
    assert entry(viewport_end) == 0
    for modified in (args[:4] + (args[4], args[4]),
                     (args[0], args[0]) + args[2:],
                     args[:2] + (0xfffffffffffff000, args[3]) + args[4:]):
        assert lib.mmu_prepare(*modified, c.byref(report)) == 0
    print("PASS: 16K table layout, executable/data permissions, exact viewport and unused-page exclusions")
