#!/usr/bin/env python3
"""Verify the storage-free Pixel CI artifact and pack a bounded RAM payload."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.append(str(ROOT.parent / 'tools'))
# Load the Pixel generator before inherited tools adjust sys.path themselves.
from mkadt import build as build_adt
import adt
import mkpayload
from embed import validate
from check_kernel import check_kernel
from stage_kernel import selected_inputs

XNU_COMMIT = '1b191cb58250d0705d8a51287127505aa4bc0789'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--ram-init', action='store_true',
                        help='Embed the artifact\'s source-built static PID 1 probe in RAM')
    args = parser.parse_args()
    source = args.artifact.resolve()
    if (source / 'xnu-commit.txt').read_text().strip() != XNU_COMMIT:
        raise ValueError('Unexpected XNU source commit')
    expected = selected_inputs()
    manifest = [{'name': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in expected]
    if json.loads((source / 'flame-patches.json').read_text()) != manifest:
        raise ValueError('Artifact does not match the current storage-free Pixel patch profile')
    kernel = source / 'kernel.development.sweet'
    kernel_sha = hashlib.sha256(kernel.read_bytes()).hexdigest()
    checksums = {}
    for line in (source / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split()
        name = Path(name).name
        if name in checksums or name not in (kernel.name, 'flame-init'):
            raise ValueError('Unexpected or duplicate artifact checksum')
        checksums[name] = digest
    if checksums.get(kernel.name) != kernel_sha:
        raise ValueError('Kernel checksum mismatch')
    init = source / 'flame-init' if args.ram_init else None
    init_sha = hashlib.sha256(init.read_bytes()).hexdigest() if init else None
    if init and checksums.get(init.name) != init_sha:
        raise ValueError('Init checksum mismatch')
    if init:
        init_header = mkpayload.parse_macho(init.read_bytes())
        if init_header['cputype'] != 0x100000c or init_header['cpusub'] != 0:
            raise ValueError('Expected a non-PAC arm64 init probe')
    check_kernel(kernel)
    m = mkpayload.parse_macho(kernel.read_bytes())
    if m['cputype'] != 0x100000c or m['cpusub'] != 0:
        raise ValueError('Expected non-PAC arm64 kernel')
    out = ROOT / 'out'
    out.mkdir(exist_ok=True)
    tree = out / 'flame-early.adt'
    root = build_adt()
    if root.prop('model') != b'Google Pixel 4\0' or root.prop('compatible').split(b'\0')[0] != b'google,flame':
        raise ValueError('Expected the Pixel ADT generator')
    tree.write_bytes(adt.serialize(root))
    # No persistent storage drivers, device mounts, or persistent logs.
    command = 'debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress wdt=-1'
    if init:
        command += ' rd=md0'
    payload, info = mkpayload.build(str(kernel), str(tree), command, str(init) if init else None)
    plan = validate(payload)
    target = out / 'flame-early.payload'
    target.write_bytes(payload)
    record = {'port_commit': (source / 'port-commit.txt').read_text().strip(),
              'xnu_commit': XNU_COMMIT, 'kernel_sha256': kernel_sha,
              'ram_init_sha256': init_sha,
              'payload_sha256': hashlib.sha256(payload).hexdigest(),
              'loader_offsets': [hex(v) for v in plan], 'kernel': info}
    (out / 'flame-early-manifest.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
    print(f'Next: bash flame/build.sh 05 {target}')


if __name__ == '__main__':
    main()
