#!/usr/bin/env bash
# Build only a temporary Pixel diagnostic image. Does not access the phone.
set -euo pipefail
cd "$(dirname "$0")"
mode="${1:-01}"
case "$mode" in 01|02|03|04) ;; *) echo 'Usage: bash flame/build.sh [01|02|03|04]' >&2; exit 1 ;; esac
mkdir -p out
sources=../research/flame-sources
if [[ ! -f "$sources/sm8150.dtb" || ! -f "$sources/sm8150-v2.dtb" || ! -f "$sources/avbtool.py" || ! -f "$sources/mkbootimg.py" || ! -f "$sources/gki/generate_gki_certificate.py" ]]; then
    echo 'Run python3 flame/fetch.py from the repository root first.' >&2
    exit 1
fi
cc="${CROSS_COMPILE:-aarch64-linux-gnu-}gcc"
flags=(-O2 -ffreestanding -nostdlib -fno-pic -fno-pie -fno-jump-tables -mgeneral-regs-only -mstrict-align -fno-stack-protector -Wall -Wextra -Werror)
if [[ "$mode" != 01 ]]; then flags+=(-DPROBE_MAP); fi
if [[ "$mode" == 03 ]]; then flags+=(-DPROBE_RAM); fi
if [[ "$mode" == 04 ]]; then flags+=(-DPROBE_MMU); fi
for source in start.S probe.c fdt.c memory.c ram.c mmu.c; do
    "$cc" "${flags[@]}" -c "$source" -o "out/${source%.*}.o"
done
if "${CROSS_COMPILE:-aarch64-linux-gnu-}readelf" -r out/probe.o out/fdt.o out/memory.o out/ram.o out/mmu.o | rg -q 'ABS64'; then
    echo 'Unexpected absolute relocation in position-independent probe.' >&2
    exit 1
fi
"$cc" "${flags[@]}" -static -no-pie -T probe.ld -Wl,--build-id=none -Wl,--no-warn-rwx-segments -Wl,-N \
    out/start.o out/probe.o out/fdt.o out/memory.o out/ram.o out/mmu.o -o out/probe.elf
"${CROSS_COMPILE:-aarch64-linux-gnu-}objcopy" -O binary out/probe.elf out/Image
size=$("${CROSS_COMPILE:-aarch64-linux-gnu-}nm" out/probe.elf | awk '$3=="_end"{print $1}')
truncate -s "$((16#$size))" out/Image
python3 lz4_image.py out/Image out/Image.lz4
python3 - <<'PY'
import gzip
from pathlib import Path
# Empty, valid newc archive. The diagnostic does not consume the ramdisk.
name = b'TRAILER!!!\0'
fields = [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, len(name), 0]
header = b'070701' + ''.join(f'{v:08x}' for v in fields).encode()
data = header + name
data += b'\0' * (-len(data) % 4)
Path('out/ramdisk.cpio.gz').write_bytes(gzip.compress(data, mtime=0))
PY
# Pixel 4's Google BoardConfig: boot header v2, 4096-byte pages, base 0,
# DTB in the boot image. ABL applies the installed slot's DTBO overlay.
cat "$sources/sm8150-v2.dtb" "$sources/sm8150.dtb" > out/dtb.img
python3 "$sources/mkbootimg.py" \
    --header_version 2 --pagesize 4096 --base 0 \
    --kernel out/Image.lz4 --ramdisk out/ramdisk.cpio.gz --dtb out/dtb.img \
    --os_version 13.0.0 --os_patch_level 2022-10 \
    --cmdline 'console=null' -o "out/flame-probe-$mode.img"
# Stock Pixel boot.img carries an unsigned AVB hash footer and these properties.
# This is metadata for an unlocked-bootloader experiment, not a Google signature.
python3 "$sources/avbtool.py" add_hash_footer \
    --image "out/flame-probe-$mode.img" --partition_name boot --partition_size 67108864 \
    --algorithm NONE --salt 666c616d652d70726f62652d3031 \
    --prop com.android.build.boot.os_version:13 \
    --prop com.android.build.boot.fingerprint:experimental/flame/flame:13/FLAME_PROBE/1:userdebug/test-keys \
    --prop com.android.build.boot.security_patch:2022-10-05
cp out/Image "out/Image-$mode"
sha256sum "out/flame-probe-$mode.img"
