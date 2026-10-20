#!/usr/bin/env python3
"""Exercise the Pixel kernel console on QEMU virt; no USB/device access.

This substitutes QEMU GIC/timer metadata and treats splash RAM as ordinary
memory. It tests kernel execution and mappings, not Pixel peripherals.
Run inside the container from qemu.Dockerfile or with qemu-system-aarch64.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
from mkadt import build as build_adt
from check_kernel import check_kernel
sys.path.append(str(ROOT.parent / 'tools'))
import adt
import mkpayload

spec = importlib.util.spec_from_file_location('sweet_qemu', ROOT.parent / 'tools/qemu-sweet.py')
qemu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qemu)
qemu.FB_BASE, qemu.FB_H = 0x9c400000, 2280


def symbol_address(kernel, target):
    data = Path(kernel).read_bytes()
    offset, symbols = 32, []
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, size = struct.unpack_from('<II', data, offset)
        if command == 2:
            start, count, strings, string_size = struct.unpack_from('<4I', data, offset + 8)
            for index in range(count):
                name, kind, _, _, value = struct.unpack_from('<IBBHQ', data, start + index * 16)
                finish = data.index(b'\0', strings + name, strings + string_size)
                if data[strings + name:finish].decode(errors='replace') == target and not kind & 0xe0:
                    symbols.append(value)
        offset += size
    if len(symbols) != 1:
        raise ValueError(f'Expected one {target} symbol')
    return symbols[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--seconds', type=float, default=35)
    parser.add_argument('--reproduce-05b', action='store_true', help='Emulate only the exact known-broken 05b kernel')
    args = parser.parse_args()
    kernel, output = args.kernel.resolve(), args.output.resolve()
    kernel_hash = hashlib.sha256(kernel.read_bytes()).hexdigest()
    if args.reproduce_05b:
        if kernel_hash != '3237cef33de90789bcf2ff2e7e125977265b706c77a0eacfd1ee43c6c561cecb':
            raise ValueError('Reproduction option requires the exact 05b kernel')
    else:
        check_kernel(kernel)
    if not 1 <= args.seconds <= 120:
        raise ValueError('Simulation duration must be 1–120 seconds')
    output.mkdir(parents=True, exist_ok=True)
    tree = output / 'qemu-only.adt'
    tree.write_bytes(adt.serialize(build_adt(qemu=True, seed=bytes(range(64)))))
    command = 'debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress wdt=-1'
    payload, info = mkpayload.build(str(kernel), str(tree), command)
    (output / 'qemu-only.payload').write_bytes(payload)
    font = qemu.payload_data(payload, symbol_address(kernel, '_iso_font'), 256 * 16)
    physical, image, boot_args, entry = qemu.build_image(payload)
    (output / 'ram.bin').write_bytes(image)
    (output / 'stub.bin').write_bytes(qemu.stub(boot_args, entry))
    monitor = output / 'monitor.sock'
    if monitor.exists():
        raise ValueError('Existing QMP socket; use a fresh output directory')
    cmd = ['qemu-system-aarch64', '-M', 'virt,gic-version=3', '-cpu', 'cortex-a76',
           '-smp', '1', '-m', '4G', '-nic', 'none', '-nographic', '-serial', f'file:{output}/serial.txt',
           '-qmp', f'unix:{monitor},server,nowait', '-no-reboot',
           '-d', 'int,guest_errors,unimp', '-D', str(output / 'qemu.log'),
           '-device', f'loader,file={output}/ram.bin,addr={physical:#x},force-raw=on',
           '-device', f'loader,file={output}/stub.bin,addr={qemu.STUB_PA:#x},force-raw=on',
           '-device', f'loader,addr={qemu.STUB_PA:#x},cpu-num=0']
    version = subprocess.check_output(['qemu-system-aarch64', '--version'], text=True).splitlines()[0]
    print(version, flush=True)
    print(f'QEMU-only run: kernel SHA {kernel_hash}; entry {entry:#x}', flush=True)
    process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + args.seconds
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.2)
        if process.poll() is not None:
            raise RuntimeError(f'QEMU exited early with status {process.returncode}')
        _, registers = qemu.qmp(str(monitor), 'stop', 'info registers',
                               pmemsave=(qemu.FB_BASE, qemu.FB_STRIDE * qemu.FB_H, str(output / 'fb.raw')))
        (output / 'registers.txt').write_text(registers)
        virtual_base = struct.unpack_from('<Q', payload, 0x10)[0]
        kva_address = physical + symbol_address(kernel, '_kva_active') - virtual_base
        qemu.qmp(str(monitor), pmemsave=(kva_address, 4, str(output / 'kva_active.bin')))
        kva_active = struct.unpack('<I', (output / 'kva_active.bin').read_bytes())[0]
        raw = (output / 'fb.raw').read_bytes()
        qemu.write_png(str(output / 'fb.png'), raw)
        # The bottom band contains coloured stage markers, not text glyphs.
        text_end = ((qemu.FB_H - 32) // 32) * 32 * qemu.FB_STRIDE
        screen, unknown = qemu.decode_screen(raw[:text_end] + bytes(len(raw) - text_end), font)
        (output / 'fb.txt').write_text(screen)
        result = qemu.screen_result(screen, unknown)
        result.update({'simulation_only': True, 'qemu_version': version, 'kernel_sha256': kernel_hash,
                       'stage9_visible': 'kernel framebuffer VA live' in screen,
                       'stage14_visible': 'early I/O page tables ready' in screen,
                       'kva_active': kva_active,
                       'framebuffer_handoff_verified': kva_active == 1,
                       'waiting_for_root': 'Still waiting for root device' in screen,
                       'translation_check_failed': 'FLAME FINAL FB TRANSLATION FAILED' in screen})
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(screen, flush=True)
        print(json.dumps(result, indent=2), flush=True)
        return 0 if args.reproduce_05b and result['translation_check_failed'] else (
            0 if not args.reproduce_05b and result['framebuffer_handoff_verified'] and
                 result['status'] == 'no_panic_observed' and not result['translation_check_failed'] else 2)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        for name in ('ram.bin', 'fb.raw', 'monitor.sock'):
            (output / name).unlink(missing_ok=True)


if __name__ == '__main__':
    sys.exit(main())
