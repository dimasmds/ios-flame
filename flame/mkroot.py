#!/usr/bin/env python3
"""Create a small HFS+ test root using macOS tools; never accesses a phone."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import struct
import subprocess
import sys
import tempfile

ROOT_SIZE = 16 * 1024 * 1024
CHECK_CONTENTS = b'FLAME HFS RAM ROOT OK\n'


def inspect_hfs(data):
    """Validate the exact raw-volume profile used for the bounded RAM root."""
    if len(data) != ROOT_SIZE or data[1024:1028] != b'H+\x00\x04':
        raise ValueError('Expected a raw 16 MiB HFS+ volume')
    attributes = struct.unpack_from('>I', data, 1028)[0]
    block_size, blocks, free = struct.unpack_from('>3I', data, 1064)
    if block_size < 512 or block_size > 65536 or block_size & (block_size - 1):
        raise ValueError('Invalid HFS+ block size')
    if block_size * blocks != len(data) or not 0 < free < blocks:
        raise ValueError('Invalid HFS+ volume bounds')
    if not attributes & 0x100 or attributes & 0x800:
        raise ValueError('HFS+ volume was not cleanly unmounted')
    if data[-1024:-1020] != b'H+\x00\x04':
        raise ValueError('Missing alternate HFS+ volume header')
    return {'filesystem': 'HFS+', 'size': len(data), 'block_size': block_size,
            'blocks': blocks, 'free_blocks': free, 'cleanly_unmounted': True}


def raw_udrw(data):
    """Accept flat UDRW, or strip a trailer around an exact flat data fork."""
    if len(data) == ROOT_SIZE:
        inspect_hfs(data)
        return data
    if len(data) < 512 or data[-512:-508] != b'koly':
        raise ValueError('Missing UDIF trailer')
    trailer = data[-512:]
    version, header_size = struct.unpack_from('>2I', trailer, 4)
    offset, size = struct.unpack_from('>2Q', trailer, 24)
    sectors = struct.unpack_from('>Q', trailer, 492)[0]
    if version != 4 or header_size != 512 or offset != 0 or size != ROOT_SIZE or sectors * 512 != size:
        raise ValueError('UDRW image does not contain the expected flat volume')
    if size > len(data) - 512:
        raise ValueError('Truncated UDRW data fork')
    raw = data[:size]
    inspect_hfs(raw)
    return raw


def run(*args):
    subprocess.run([str(a) for a in args], check=True)


def build(init, output):
    if sys.platform != 'darwin':
        raise ValueError('Root creation requires macOS hdiutil and install')
    init, output = init.resolve(), output.resolve()
    if output.exists() or output.with_suffix('.json').exists():
        raise ValueError('Use a fresh root-image output path')
    executable = init.read_bytes()
    if not 1024 < len(executable) < 128 * 1024 or executable[:4] != b'\xcf\xfa\xed\xfe':
        raise ValueError('Expected the small static arm64 init Mach-O')
    with tempfile.TemporaryDirectory(prefix='flame-hfs-') as temporary:
        work = Path(temporary).resolve()
        image, mount = work / 'root.dmg', work / 'mount'
        mount.mkdir()
        run('hdiutil', 'create', '-size', '16m', '-fs', 'HFS+', '-volname', 'FlameRAM',
            '-layout', 'NONE', '-type', 'UDIF', image)
        attached = False
        try:
            result = subprocess.check_output(['hdiutil', 'attach', '-nobrowse', '-owners', 'on',
                                             '-mountpoint', str(mount), '-plist', str(image)])
            attached = True
            entities = plistlib.loads(result)['system-entities']
            device = next(e['dev-entry'] for e in entities if e.get('mount-point') == str(mount))
            # All privileged paths are within our newly attached temporary image.
            for name in ('sbin', 'dev', 'etc', 'tmp', 'private', 'private/var'):
                run('sudo', 'install', '-d', '-o', '0', '-g', '0', '-m', '0755', mount / name)
            run('sudo', 'chown', '0:0', mount)
            run('sudo', 'chmod', '0755', mount)
            run('sudo', 'install', '-o', '0', '-g', '0', '-m', '0755', init, mount / 'sbin/launchd')
            check = work / 'flame-test'
            check.write_bytes(CHECK_CONTENTS)
            run('sudo', 'install', '-o', '0', '-g', '0', '-m', '0644', check, mount / 'etc/flame-test')
            if (mount / 'sbin/launchd').read_bytes() != executable or (mount / 'etc/flame-test').read_bytes() != CHECK_CONTENTS:
                raise ValueError('Mounted root files do not match their inputs')
            run('hdiutil', 'detach', device)
            attached = False
        finally:
            if attached:
                run('hdiutil', 'detach', mount)
        raw = raw_udrw(image.read_bytes())
    metadata = inspect_hfs(raw)
    metadata.update({'volume_name': 'FlameRAM', 'root_sha256': hashlib.sha256(raw).hexdigest(),
                     'init_sha256': hashlib.sha256(executable).hexdigest(),
                     'check_path': '/etc/flame-test', 'check_contents': CHECK_CONTENTS.decode()})
    output.write_bytes(raw)
    output.with_suffix('.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('init', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build(args.init, args.output)
