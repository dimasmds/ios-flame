#!/usr/bin/env python3
"""Check actual linked Mach-O page-table placement before packaging or booting."""
from pathlib import Path
import struct
import sys


def check_kernel(path):
    data = Path(path).read_bytes()
    magic, cpu, subtype, _, commands, command_bytes, _, _ = struct.unpack_from('<8I', data)
    if (magic, cpu, subtype) != (0xfeedfacf, 0x100000c, 0) or commands > 256 or command_bytes > len(data) - 32:
        raise ValueError('Expected bounded non-PAC arm64 Mach-O')
    sections, symtab = [], None
    offset, end = 32, 32 + command_bytes
    for _ in range(commands):
        if offset + 8 > end:
            raise ValueError('Truncated Mach-O load command')
        command, size = struct.unpack_from('<II', data, offset)
        if size < 8 or size > end - offset:
            raise ValueError('Invalid Mach-O load command')
        if command == 0x19:
            if size < 72:
                raise ValueError('Truncated segment command')
            count = struct.unpack_from('<I', data, offset + 64)[0]
            if count > (size - 72) // 80:
                raise ValueError('Truncated section table')
            for index in range(count):
                start = offset + 72 + index * 80
                section = data[start:start + 16].split(b'\0')[0].decode()
                segment = data[start + 16:start + 32].split(b'\0')[0].decode()
                address, length = struct.unpack_from('<QQ', data, start + 32)
                sections.append((segment, section, address, length))
        elif command == 2:
            if size != 24 or symtab is not None:
                raise ValueError('Unexpected symbol table command')
            symtab = struct.unpack_from('<4I', data, offset + 8)
        offset += size
    if offset != end or symtab is None:
        raise ValueError('Missing symbols or inconsistent command lengths')
    start, count, strings, string_bytes = symtab
    if start > len(data) or count > (len(data) - start) // 16 or strings > len(data) or string_bytes > len(data) - strings:
        raise ValueError('Symbol/string table outside Mach-O')
    required = {'_flame_fb_l3': 0x4000, '_bootstrap_pagetables': 0x4000}
    found = {}
    for index in range(count):
        name, kind, section_index, _, value = struct.unpack_from('<IBBHQ', data, start + index * 16)
        if name >= string_bytes:
            raise ValueError('Invalid symbol string offset')
        finish = data.find(b'\0', strings + name, strings + string_bytes)
        if finish < 0:
            raise ValueError('Unterminated symbol name')
        label = data[strings + name:finish].decode(errors='replace')
        if label not in required or kind & 0xe0 or (kind & 0xe) != 0xe:
            continue
        if label in found or not 1 <= section_index <= len(sections):
            raise ValueError(f'Invalid/duplicate table symbol: {label}')
        segment, section, address, length = sections[section_index - 1]
        if value % 0x4000:
            raise ValueError(f'{label} is not 16K aligned: {value:#x} ({segment},{section})')
        if segment != '__DATA_CONST' or value < address or value + required[label] > address + length:
            raise ValueError(f'{label} is outside the reserved RO-late table section')
        found[label] = value
    if found.keys() != required.keys():
        raise ValueError(f'Missing page-table symbols: {required.keys() - found.keys()}')
    print('PASS: linked Pixel framebuffer and bootstrap tables are 16K aligned in __DATA_CONST')
    return found


if __name__ == '__main__':
    check_kernel(sys.argv[1])
