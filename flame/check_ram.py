"""Host verification of normal-path page restoration and untouched middle RAM."""
import ctypes as c


def check_ram(lib):
    class Report(c.Structure):
        _fields_ = [(n, c.c_uint64) for n in ("first", "last", "words_compared")] + [
            ("pattern_errors", c.c_uint32), ("restore_errors", c.c_uint32)]

    lib.ram_test.argtypes = [c.c_size_t, c.c_uint64, c.POINTER(Report)]
    page = 0x4000
    raw = c.create_string_buffer(page * 4)
    base = (c.addressof(raw) + page - 1) & ~(page - 1)
    data = bytes((i * 37 + (i >> 8)) & 255 for i in range(page * 3))
    c.memmove(base, data, len(data))
    report = Report()
    assert lib.ram_test(base, page * 3, c.byref(report)) == 1
    assert report.first == base and report.last == base + 2 * page
    assert report.words_compared == 8192
    assert not report.pattern_errors and not report.restore_errors
    assert c.string_at(base, len(data)) == data
    for address, size in [(base + 1, page * 2), (base, page), (base, 2 * page + 1),
                          (0xffffffffffffc000, page * 2)]:
        assert lib.ram_test(address, size, c.byref(report)) == 0
    assert c.string_at(base, len(data)) == data
    print("PASS: two-page pattern test restores original data and leaves middle pages untouched")
