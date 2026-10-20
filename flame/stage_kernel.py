#!/usr/bin/env python3
"""Stage the deliberately limited Pixel early-console kernel patch set."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent


def selected_inputs():
    # Bootstrap, pthread and portable cryptographic providers only. Filesystem,
    # AMFI replacements, and later Redmi peripheral drivers are excluded.
    numbers = set(range(1, 21)) | {23, 27}
    patches = sorted(p for p in (ROOT / "xnu/patches").glob("*.patch")
                     if int(p.name.split("-")[0]) in numbers)
    if len(patches) != len(numbers):
        raise SystemExit("Expected one patch for every selected core component")
    pixel = sorted((ROOT / "flame/patches").glob("*.patch"))
    if len(pixel) != 1:
        raise SystemExit("Expected exactly one audited Pixel profile patch")
    helpers = [ROOT / "xnu/patches" / name for name in
               ("0019-stage-libpthread.sh", "0020-stage-bearssl.sh")]
    if not all(p.is_file() for p in helpers):
        raise SystemExit("Missing pinned core-provider staging script")
    return sorted(patches + pixel + helpers, key=lambda p: p.name)


def verify(source):
    required = {
        "makedefs/MakeInc.def": "-DARM64_BOARD_CONFIG_SWEET                -mcpu=cortex-a55",
        "osfmk/arm64/start.s": "Lsflame_map_fb_page:",
        "osfmk/arm64/sweet_early.c": "#define EARLY_HEIGHT 2280u",
        "osfmk/arm64/arm_vm_init.c": "kvtophys((vm_offset_t)flame_fb_l3)",
        "iokit/KernelConfigTables.cpp": "'google,flame'",
        "bsd/pthread/sweet_pthread_init.c": "libpthread-514.100.2",
        "libkern/crypto/sweet_aes.c": "br_aes_ct_cbcenc_run",
        "libkern/crypto/corecrypto_sha2.c": "#define SHA256_DI()",
        "libkern/crypto/corecrypto_md5.c": "br_md5_init",
    }
    for path, text in required.items():
        if text not in (source / path).read_text():
            raise SystemExit(f"Pixel kernel check failed: {path}: missing {text}")
    if (source / "bsd/dev/sweet_ufs.c").exists():
        raise SystemExit("Storage driver present: this is not the intended early-console source tree")
    early = (source / "osfmk/arm64/sweet_early.c").read_text()
    if "(uintptr_t)0x9c400000" not in early:
        raise SystemExit("Early console is not aimed at the measured Pixel framebuffer")
    if "FLAME FINAL FB TRANSLATION FAILED" not in early or "at s1e1w" not in early:
        raise SystemExit("Final framebuffer translation preflight diagnostics missing")
    if 'at s1e1w, %1; isb' in early or 'tlbi vaae1is, %0;' in early:
        raise SystemExit("Darwin inline assembly must use newline instruction separators")
    if "SECURITY_READ_ONLY_LATE(tt_entry_t) flame_fb_l3" not in (source / "osfmk/arm64/arm_vm_init.c").read_text():
        raise SystemExit("Final framebuffer table must use the aligned RO-late section")
    print("Pixel source profile verified; storage driver excluded")


def stage(target):
    script = target / "build.sh"
    data = script.read_text()
    # Pinned upstream script: demand exact, single replacements rather than
    # silently carrying a partial compiler/profile change into CI.
    old = 'ARCHS="x86_64 arm64e" VALID_ARCHS="x86_64 arm64e"'
    new = 'ARCHS="arm64" VALID_ARCHS="arm64" OTHER_CFLAGS="-mkernel -nostdinc -Wno-packed -mcpu=cortex-a55"'
    if data.count(old) != 1:
        raise SystemExit("Unexpected libfirehose build command in pinned dxb script")
    data = data.replace(old, new)
    old = 'warning "Skipping patch ${PATCH} (already upstream, previously applied, or malformed): ${APPLY_CHECK}"'
    if data.count(old) != 1:
        raise SystemExit("Unexpected patch loop in pinned dxb script")
    data = data.replace(old, old + '\n                case "${PATCH##*/}" in 0[0-9][0-9][0-9]-*) return 1 ;; esac')
    selected = selected_inputs()
    dest = target / "patches"
    dest.mkdir(exist_ok=True)
    # Do not erase an arbitrary directory or silently retain later Redmi drivers.
    if any(dest.glob("0[0-9][0-9][0-9]-*")):
        raise SystemExit("Numbered port patches already present; use a fresh dxb checkout")
    manifest = []
    for patch in selected:
        shutil.copy2(patch, dest / patch.name)
        manifest.append({"name": patch.name, "sha256": hashlib.sha256(patch.read_bytes()).hexdigest()})
    script.write_text(data)
    (target / "flame-patches.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Staged {len(selected)} source inputs (core providers and Pixel console); peripheral drivers excluded")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["stage", "verify"])
    p.add_argument("path", type=Path)
    args = p.parse_args()
    (stage if args.command == "stage" else verify)(args.path.resolve())
