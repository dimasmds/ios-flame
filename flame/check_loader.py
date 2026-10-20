"""Exercise the actual bounded loader, including rejected metadata and exact writes."""
import ctypes as c
import struct


def fixture():
    virt = 0xfffffff000000000
    blob = bytearray(0x330)
    struct.pack_into('<8sII7Q', blob, 0, b'SWEETXNU', 1, 2,
                     virt, virt + 0x4000, 0x320, 13, virt + 0x10000,
                     0x100000000, 0x40000000)
    blob[0x48:0x48 + 8] = b'cpus=1\0\0'
    struct.pack_into('<4Q', blob, 0x2a8, virt + 0x4000, 0x8000, 0x2e8, 33)
    struct.pack_into('<4Q', blob, 0x2c8, virt + 0xc000, 0x4000, 0x310, 16)
    blob[0x2e8:0x309] = bytes(range(33))
    blob[0x310:0x320] = b'Z' * 16
    blob[0x320:0x32d] = b'example tree!'
    return blob


def check_loader(lib):
    class Plan(c.Structure):
        _fields_ = [(n, c.c_uint64) for n in ('adt', 'args', 'top', 'entry')]

    lib.payload_validate.argtypes = [c.c_void_p, c.c_size_t, c.POINTER(Plan)]
    lib.payload_validate.restype = c.c_char_p
    lib.payload_materialize.argtypes = [c.c_void_p, c.POINTER(Plan), c.c_size_t]
    blob = fixture()
    source = c.create_string_buffer(bytes(blob))
    plan = Plan()
    assert lib.payload_validate(source, len(blob), c.byref(plan)) is None
    assert (plan.adt, plan.args, plan.top, plan.entry) == (0x10000, 0x14000, 0x18000, 0x4000)
    arena = c.create_string_buffer(b'\xa5' * 0x1c000)
    lib.payload_materialize(source, c.byref(plan), c.addressof(arena))
    actual = arena.raw
    assert actual[:0x4000] == b'\xa5' * 0x4000
    assert actual[0x4000:0x4021] == bytes(range(33))
    assert actual[0x4021:0xc000] == bytes(0xc000 - 0x4021)
    assert actual[0xc000:0xc010] == b'Z' * 16
    assert actual[0xc010:0x10000] == bytes(0x3ff0)
    assert actual[0x10000:0x1000d] == b'example tree!'
    assert actual[0x1000d:0x14000] == b'\xa5' * (0x14000 - 0x1000d)
    assert actual[0x18000:0x1c000] == b'\xa5' * 0x4000
    ba = actual[0x14000:0x18000]
    assert struct.unpack_from('<2H', ba) == (2, 2)
    assert struct.unpack_from('<4Q', ba, 8) == (0xfffffff000000000, 0x100000000, 0x40000000, 0x100018000)
    assert struct.unpack_from('<6Q', ba, 40) == (0x9c400000, 1, 4320, 1080, 2280, 32)
    assert struct.unpack_from('<Q', ba, 96)[0] == 0xfffffff000010000
    assert struct.unpack_from('<I', ba, 104)[0] == 13
    assert ba[108:116] == b'cpus=1\0\0'
    assert struct.unpack_from('<2Q', ba, 720) == (0, 0x40000000)
    assert ba[736:] == bytes(0x4000 - 736)

    def reject(data, length=None):
        data = c.create_string_buffer(bytes(data))
        assert lib.payload_validate(data, len(data) - 1 if length is None else length, c.byref(Plan()))

    for length in (0, 8, 0x2a7, 0x2e7):
        reject(blob, length)
    for offset, fmt, value in ((0, 'Q', 0), (8, 'I', 2), (12, 'I', 33),
                               (0x38, 'Q', 0x80000000), (0x40, 'Q', 0xffffffffffffffff),
                               (0x20, 'Q', 0xfffffffffffffff8), (0x28, 'Q', 0x100001),
                               (0x18, 'Q', 0xfffffff000008000),
                               (0x2a8, 'Q', 0xfffffff000000001),
                               (0x2b0, 'Q', 0xffffffffffffffff),
                               (0x2b8, 'Q', 0x100), (0x2c0, 'Q', 0x9000),
                               (0x2c8, 'Q', 0xfffffff000008000),
                               (0x30, 'Q', 0xfffffff000004000)):
        changed = bytearray(blob)
        struct.pack_into('<' + fmt, changed, offset, value)
        reject(changed)
    changed = bytearray(blob)
    changed[0x2a7] = 1
    reject(changed)
    print('PASS: payload bounds/overlap/entry rejection, segment copying, BSS, exact ADT and boot_args ABI')
