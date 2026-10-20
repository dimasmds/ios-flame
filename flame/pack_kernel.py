#!/usr/bin/env python3
"""Verify the limited Pixel CI artifact and pack its early-console-only payload."""
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

XNU_COMMIT = '1b191cb58250d0705d8a51287127505aa4bc0789'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    source = args.artifact.resolve()
    if (source / 'xnu-commit.txt').read_text().strip() != XNU_COMMIT:
        raise ValueError('Unexpected XNU source commit')
    expected = sorted(p for p in (ROOT.parent / 'xnu/patches').glob('*.patch')
                      if int(p.name.split('-')[0]) <= 18)
    expected += sorted((ROOT / 'patches').glob('*.patch'))
    assert len(expected) == 19
    manifest = [{'name': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in expected]
    if json.loads((source / 'flame-patches.json').read_text()) != manifest:
        raise ValueError('Artifact does not match the current storage-free Pixel patch profile')
    kernel = source / 'kernel.development.sweet'
    kernel_sha = hashlib.sha256(kernel.read_bytes()).hexdigest()
    checksum = (source / 'SHA256SUMS').read_text().split()
    if len(checksum) != 2 or checksum[0] != kernel_sha or Path(checksum[1]).name != kernel.name:
        raise ValueError('Kernel checksum mismatch')
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
    # No root filesystem, peripheral driver options, or persistent logs.
    command = 'debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress wdt=-1'
    payload, info = mkpayload.build(str(kernel), str(tree), command)
    plan = validate(payload)
    target = out / 'flame-early.payload'
    target.write_bytes(payload)
    record = {'port_commit': (source / 'port-commit.txt').read_text().strip(),
              'xnu_commit': XNU_COMMIT, 'kernel_sha256': kernel_sha,
              'payload_sha256': hashlib.sha256(payload).hexdigest(),
              'loader_offsets': [hex(v) for v in plan], 'kernel': info}
    (out / 'flame-early-manifest.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
    print(f'Next: bash flame/build.sh 05 {target}')


if __name__ == '__main__':
    main()
