# Pixel 4 (flame) bring-up

This branch starts a new SM8150 port. **XNU runs a static userspace test program
from RAM on the Pixel, confirmed by the owner's heartbeat report. Apple iOS
userland has not booted.**
The inherited README describes the Redmi devices, not Pixel support.

## Observed device

- Pixel 4, `flame`, SM8150 (`msmnile`), 1080 × 2280 display.
- Android 13, `TP1A.221005.002.B2`; bootloader already unlocked.
- Installed kernel: 4.14.276, `6ef255005cea`; Google's Android 13 coral
  source branch resolves to `6ef255005ceaae118d35fba8585de7ba1d4d5efb`.
- The adb shell is unprivileged. Live DT properties, physical memory ranges,
  and boot partitions cannot be read through it. Device-specific observations
  live under ignored `research/flame-device/`.
- The owner confirmed this is a spare device with backed-up data. This is
  not permission to reuse the Redmi author's historical destructive approvals.

## First milestone

`flame/` contains a separate bare-metal arm64 diagnostic, with no XNU,
UFS driver, Android mounts, or persistent log writes. It inspects the CPU
registers and bootloader FDT, validates the live splash reservation against
Google's source, then attempts to display diagnostics in that RAM reservation.
It requests a normal PSCI reset after 120 seconds (the first successful test
used 20 seconds). It does not write the
Redmi's restart register or initialize its interrupt controller.

The Pixel panel uses command mode. Writing splash RAM alone may not update
the screen; a DPU refresh implementation may be needed. A bootloader `OKAY`
does not prove that probe code executed. A normal reset alone also does not
prove that a particular probe stage succeeded.

Build and check, from the repository root:

```sh
python3 flame/fetch.py
bash flame/build.sh
python3 flame/check.py
```

The fetcher uses pinned Google revisions and stores sources plus checksums
under ignored `research/flame-sources/`. Requirements: Python 3, GCC for
`aarch64-linux-gnu`, host GCC, binutils, bash, ripgrep, and system `liblz4`.

Tests cover nested DT properties, malformed lengths, truncated blobs,
unterminated names, traversal limits, both public SM8150 DTBs, LZ4 round trips,
boot-image section sizes and offsets, and verification of the AVB hash descriptor.

## Hardware test results (2026-10-20)

1. Raw arm64 Image with a single DTB, no AVB footer: bootloader rejected it
   with `Unsupported`; diagnostic code did not run.
2. Raw Image with both DTBs and AVB footer: same rejection.
3. Exact stock `TP1A.221005.002.B2` boot image, loaded with `fastboot boot`:
   accepted and returned to Android. This confirms the temporary boot path works.
4. LZ4 Image, default frame settings, zero arm64 text offset: rejected with
   `Invalid Parameter`.
5. LZ4 with a content checksum and stock arm64 text offset `0x80000`:
   bootloader accepted it. **The owner observed the purple `PIXEL 4 / FLAME`
   diagnostic screen.** Android subsequently returned and adb was available.
   The individual effects of checksum and text offset were not isolated.
6. Rebuilt with a 120-second capture window and booted again at the owner's
   request. The owner supplied a photo of the completed diagnostic and then
   confirmed return to the Android home screen. adb independently reported
   `ro.product.device=flame`, `sys.boot_completed=1`, slot `_a`, verified state
   `orange`. Android's `sys.boot.reason` was `watchdog`; the cause of that
   reported reason is unresolved. Do not claim the PSCI reset path is proven.

The accepted 20-second image SHA-256 is
`6ebecb4bec5290f2fd012cb6cebe22801b00ca1e7dcc593f4aa33b8e27007ff3`.
The 120-second image SHA-256 is
`1fe26bae97e7c7492cbe893c1e23f0dd4b7ff177ce83cc9d73f8f76098d759aa`.
Raw host/device transcripts remain in ignored `research/flame-device/`.
There were no flash, erase, bootloader unlock, slot switch, or filesystem
installation commands.

The wrapper uses Pixel boot v2, **LZ4 with a content checksum**, both Google's
`sm8150-v2.dtb` and `sm8150.dtb`, and an unsigned AVB hash footer in a 64 MiB
boot image. The concatenated public DTBs were byte-for-byte identical to
those in the stock boot image. No Apple firmware has been downloaded.

## Hardware differences to port

| Item | Pixel 4 evidence | Remaining work |
| --- | --- | --- |
| Boot wrapper | v2, 4096-byte pages, LZ4 + checksum, DTBs, AVB footer; hardware probe accepted | Adapt for an XNU payload after validating RAM |
| CPU affinity | Probe: EL1, MIDR `0x51df805e`, MPIDR `0x81000000`, TGRAN16 `1`; source affinities `0x000` … `0x700` | Start with boot-core affinity 0; do not reuse topaz's Gold handoff |
| GIC | Google source: distributor `0x17a00000`, redistributors `0x17a60000` | Validate live FDT; port interrupt and SMP initialization |
| Timer | Google source: 19.2 MHz, virtual timer PPI 3 → INTID 19 | Test timer interrupts |
| UFS | Running Android platform device `1d84000.ufshc` | Validate register layout, DMA, IOMMU/firmware state; disable all writes initially |
| Splash | Photo confirms reservation `0x9c400000` / `0x02400000` and visible diagnostic text | Characterize refresh for continuous UI |
| RAM | Photo: `0x80000000` + `0x3cc00000`; `0xc0000000` + `0x140000000` | Validate carve-outs before loading XNU |
| Touch/buttons | Not investigated yet | Identify actual controller and PMIC routing, then port HID |

Source locations at the installed kernel revision:

- [SM8150 CPU, GIC, timer, and reset description](https://android.googlesource.com/kernel/msm/+/6ef255005ceaae118d35fba8585de7ba1d4d5efb/arch/arm64/boot/dts/qcom/sm8150.dtsi)
- [Pixel memory reservations](https://android.googlesource.com/kernel/msm/+/6ef255005ceaae118d35fba8585de7ba1d4d5efb/arch/arm64/boot/dts/google/sm8150-floral-memory.dtsi)
- [Pixel command-mode display](https://android.googlesource.com/kernel/msm/+/6ef255005ceaae118d35fba8585de7ba1d4d5efb/arch/arm64/boot/dts/google/sm8150-floral-display.dtsi)
- [Google boot-image configuration](https://android.googlesource.com/device/google/coral/+/0da6be0c90255271297e19eee1bf6cbd3467406a/BoardConfig-common.mk)

Once the probe has usable output, the next milestones are a validated RAM
map and framebuffer, early XNU console, timer/interrupt support, storage reads,
and finally an iOS filesystem and userland. The inherited kernel patches
contain hard-coded Redmi addresses, including persistent writes to userdata;
they must be audited before running XNU on this phone.

## Memory-map probe 02

```sh
bash flame/build.sh 02
python3 flame/check.py 02
```

This variant inspects candidate range `[0x100000000, 0x140000000)` (1 GiB).
It reads metadata only and never accesses that candidate RAM. It checks:

- Containment in a complete RAM bank and overflow of all inspected intervals.
- Every static `/reserved-memory` range, and every possible allocation window
  for dynamic pools. Unbounded pools prevent a clear result.
- The FDT reservation table, running probe image, FDT blob, and supplied initrd.
- Cell widths, address translation assumptions, traversal completion, and
  reservation-table termination. Incomplete/unsupported metadata blocks a pass.

`NO DT CONFLICTS` is a metadata result, not proof that XPU permissions or DDR
access work. No RAM test or XNU jump is performed. Google source also contains
a memory-offlining policy; `arch/arm64/mm/init.c` treats `offline-sizes` entries
as RAM-size thresholds and amounts to offline, not physical reserved ranges.

Build and host checks passed (including conflict, overflow, dynamic-pool,
initrd/image, and malformed-reservation cases). The bootloader accepted the
02 image on the same verified Pixel. The owner's photo confirms:

- Candidate `0x100000000`, size `0x40000000`, contained in RAM.
- 2 RAM banks, 26 fixed ranges, highest fixed end `0xac800000`.
- 0 reservation-table entries; 8 dynamic pools; 0 unbounded pools.
- 0 conflicts and 0 map errors; `NO DT CONFLICTS - NOT RAM TESTED`.

Android returned and adb reported `sys.boot_completed=1`; the recorded Android
boot reason remains `watchdog` (reset cause not established).

Image SHA-256:
`691b20951f20808f8056e285385df104db9e142a230534c6a7380124b59d8cb3`.

## RAM-access probe 03

```sh
bash flame/build.sh 03
python3 flame/check.py 03
```

This variant repeats the live memory-map checks, requires MMU and data cache
off, then saves/tests/restores exactly two 16 KiB pages:
`0x100000000` and `0x13fffc000`. It compares two address-dependent patterns
across both pages, then restores and verifies the original contents. Other
candidate pages are not accessed. An exception or reset may interrupt
restoration; only a completed test reports its restore verification.

Host tests passed for restoration, untouched middle pages, alignment, range
size, and overflow rejection. The owner's photo confirms SCTLR `0xc00808`,
8,192 word comparisons, zero pattern errors, zero restore errors, and
`TWO PAGE RAM TEST PASSED`. Android returned; adb reported boot_completed=1.
This verifies only the two tested pages. No storage driver is present.
Image SHA-256:
`232f10ef3b68dc426c7653c37e67682304d088cb55dbfa90c18dde257e30a78c`.

## MMU translation probe 04

```sh
bash flame/build.sh 04
python3 flame/check.py 04
```

This variant repeats the live map checks, constructs 16 KiB identity mappings,
enables the EL1 MMU with caches unchanged, and repeats the two-page RAM test.
Only the running probe, visible framebuffer viewport, and two test pages are
mapped. The tables use Normal non-cacheable memory. Host checks inspect the
actual C table builder, including executable/data permissions and exclusions
for neighbouring firmware and untested RAM pages.

The owner's photo confirms five table pages, root `0x80090000`, TCR
`0x1409cb01c`, SCTLR enabled `0xc00809`, and successful translations of
`0x100000000` and `0x13fffc000`. Pattern and restore errors are both zero;
`TRANSLATED TWO PAGE TEST PASSED` is visible. SCTLR was restored to `0xc00808`
and the screen reports `MMU DISABLED AGAIN`. This proves 16K translation and
access for these mappings, not a test of the full 1 GiB or an XNU boot.

Android returned; adb reported boot_completed=1 and boot reason `watchdog`.
The reset cause remains unresolved. No partitions were written.
Image SHA-256:
`fc2773fb93750f97d7dacbf22ca97ebadb35ab4ea6394b3b7ffe762ec94ccfc4`.

## Kernel audit in progress

For read-only source inspection, downloaded the existing upstream
`xnu-buildtree` artifact from run `39419628786`, commit
`2665612a9eabb76b294cbc1b014132c6b89d09db`, into ignored
`research/upstream-2665612/`. This is a later upstream snapshot than this
branch's base and does not represent a Pixel kernel build.

Confirmed obstacles include a hard-coded early framebuffer in `start.s` and
`sweet_early.c`, a 2400-line display assumption, and a boot-CPU affinity check
requiring `0x100`. The UFS initialization can also start Redmi input drivers
and persistent logging. None of that kernel code has been run on the Pixel.

## Pixel early-console kernel build

The owner approved creating the public fork and running GitHub Actions after
clarifying that GitHub supplies the Mac runner. Earlier preference for local
work was superseded for this build; device dumps and firmware remain local.

`.github/workflows/flame-xnu.yml` is manual-dispatch only. It pins the existing
kernel builder and XNU `xnu-8796.141.3` commit
`1b191cb58250d0705d8a51287127505aa4bc0789`, selects bootstrap patches 0001–0018,
and adds `flame/patches/0099-flame-early-console.patch`. Later Redmi drivers are
excluded. `flame/stage_kernel.py` checks the selected source profile.

The Pixel patch selects Cortex-A55 code generation, Pixel platform/CPU matching,
the measured framebuffer base and height, and precise 16K framebuffer-page
mappings in both the bootstrap and final kernel tables. It avoids mapping the
surrounding 32 MiB firmware-containing block as normal memory.

Local validation: all 18 bootstrap patches plus the Pixel patch applied to the
pinned clean Apple source; source-profile checks passed; workflow YAML and build
script syntax passed. The generated early ADT has one CPU at affinity zero,
the candidate 1 GiB RAM range, Pixel GIC addresses from Google source, and no
storage/input nodes. Probe 04 has now passed on hardware. The kernel has not
yet been booted.

Published source branch: `dimasmds/ios-flame`, `pixel4-bringup`.
The first build uses commit `5677199723efe6d6c840e97381da7bf10e0bef18`:
[Actions run 39443010166](https://github.com/dimasmds/ios-flame/actions/runs/39443010166).
The first compilation failed because the Pixel C mapping code used the
assembly-only `PGBYTES` macro. The C code now uses `ARM_PGBYTES`.

Corrected build: [run 39444210854](https://github.com/dimasmds/ios-flame/actions/runs/39444210854),
commit `ef12e803268bb69f8b73eb8360cd1a7e2773aadf`, **succeeded**. Artifact downloaded
to ignored `research/flame-kernel/39444210854/`; source profile and checksum
verified. Kernel SHA-256:
`a97741a8a4135575c2830fdc41e4389525ceeb77ec239fb6810492f33bedd757`.

## Bounded kernel loader (test 05)

`flame/loader.c` validates the payload before writing candidate RAM: exact
physical profile, segment count and bounds, non-overlapping destination segments,
file-backed aligned entry, ADT and boot-argument placement, command termination,
and source/destination separation. Host tests execute the actual copy code and
check BSS clearing, untouched gaps, and the 736-byte boot-argument ABI.
The embedded payload has an explicit length covered by the arm64 Image size;
decompressed images larger than 64 MiB are rejected.

The runtime repeats the live map checks for the full embedded Image and requires
EL1, MMU/data cache off, boot affinity zero, 16K support, and the expected timer
frequency. `platform_check` validates live GIC registers/stride, SoC translation,
and timer metadata against the fixed early ADT before the kernel handoff.

`flame/pack_kernel.py` requires the CI artifact's pinned XNU commit, current
19-patch manifest, checksum, and non-PAC arm64 Mach-O. It makes a fresh early
ADT and resolves chained fixups through the inherited payload packer. No root
filesystem or storage driver is supplied. Build steps, once CI succeeds:

```sh
python3 flame/pack_kernel.py research/flame-kernel/RUN_ID
bash flame/build.sh 05 "$PWD/flame/out/flame-early.payload"
python3 flame/check.py 05
```

The synthetic host-test image was renamed `host-validation-05.img` to keep it
separate from a real kernel image. The real CI kernel was packed successfully;
full host packaging checks passed. Actual ADT inspection confirms Pixel model,
one CPU, correct candidate RAM, and no UFS. Loader entry PA `0x101484488`,
boot arguments `0x102060000`, top of kernel data `0x102064000`.
The first real test-05 image SHA-256 is
`bcece2ab63018661d4f648102e2305f7542d11c9d87ab41bb9debd7d0fe4dca0`.
The verified Pixel accepted this image through temporary `fastboot boot`:
sending 64 MiB OKAY (1.619 s), booting OKAY (4.060 s). No flash or erase command
was issued.

The owner's `flame-ios-5.jpeg` photo confirms XNU execution: stages 1–8 are
visible, including MMU-on `arm_init`, platform initialization, CPU topology,
CPU bootstrap, kernel startup bootstrap, CPU initialization, and entry into
`arm_vm_init`. The last visible line is `SWEET EARLY 8: leaving bootstrap TTBR0`.
The owner reports the screen stayed there. In source, the next operation switches
the early console pointer to its final kernel VA and tries to draw stage 9.
This localizes the next investigation to the final framebuffer alias; it does
not establish the exact fault or exclude a display-only failure. iOS userland
has not run. Android subsequently returned; adb verified `boot_completed=1` and
`ro.product.device=flame`. Its boot reason is `bootloader` after manual restart.

The next kernel profile adds first/last framebuffer write-translation checks,
TCR/TTBR1/PAR output, and bounded L1/L2/L3 table inspection through the outgoing
identity map. It invalidates the newly installed alias's cached translations.
If translation fails or targets the wrong physical address, the console remains
on its working identity address and waits for manual restart. This is a
diagnostic build; the exact cause of the stage-8 stop is still unconfirmed.

Diagnostic build: [run 39446889472](https://github.com/dimasmds/ios-flame/actions/runs/39446889472),
commit `a5b5d635af983f4d2bf91023c31dd99669f1abae`. Run 39446831702 was cancelled
after correcting required patch context; the corrected patch passed a complete
reverse/forward application round trip on the pinned source.

Subsequent inspection of the first kernel's linked symbol table found a concrete
defect: `_flame_fb_l3` is at VA `0xfffffe0007c12000` (PA `0x101c12000`), only
8 KiB aligned. The Mach-O `__DATA,__bss` section has 4 KiB alignment because
`makedefs/MakeInc.def` explicitly forces it with `-sectalign`. The C object's
16 KiB alignment attribute alone therefore did not produce a valid table base.
This is consistent with the stage-8 failure; hardware confirmation of the fix
is still pending.

The table now uses `SECURITY_READ_ONLY_LATE`, like `bootstrap_pagetables`, in
the 16 KiB aligned `__DATA_CONST` section. Its physical alignment is asserted
before installing the descriptor. `flame/check_kernel.py` checks actual linked
symbols and sections in CI and the payload packer; it correctly rejects the
first hardware-test kernel. The translation diagnostics are retained.

The diagnostic-only build 39446889472 succeeded; its artifact independently
has the same misaligned address and was rejected by the new checker. It was
not booted. The fixed-profile [run 39448117298](https://github.com/dimasmds/ios-flame/actions/runs/39448117298)
at commit `d934baacfc21c7f5585492aab3e63fca81efc521` **succeeded**, including
the linked-table check. The new `_flame_fb_l3` is at VA `0xfffffe00071f8000`
(PA `0x1011f8000`), correctly 16 KiB aligned in `__DATA_CONST`.

Test 05b uses this kernel. Artifact profile/checksum, linked alignment, payload
validation, and complete host boot-image checks passed. Kernel SHA-256:
`3237cef33de90789bcf2ff2e7e125977265b706c77a0eacfd1ee43c6c561cecb`.
Boot image SHA-256:
`f03bb748ce52fcf7091e47eca217b2e8a91a625d17657730fa445e95c47b6ac4`.
Loader entry PA `0x10148d488`, boot arguments `0x102064000`.

The same verified Pixel accepted a temporary test-05b boot: sending OKAY
(1.619 s), booting OKAY (4.062 s). Screen evidence arrived below; Android later
returned, independently verified through adb. No flash/erase command was issued. The screen still says test 05;
the new `FLAME` diagnostic lines distinguish this kernel. Preserved images:
`flame/out/flame-xnu-39444210854.img` (first stage-8 test) and
`flame/out/flame-xnu-39448117298.img` (alignment fix); both are ignored.

## Test 05b photo and hands-free investigation

The owner's `flame-ios-6.jpeg` shows stage 8, TTBR1 `0x10206c000`, L2 descriptor
`0x1011f8003`, and L3 descriptor `0x006000009c400607`. The table alignment fix
is present. The screen then reports `FLAME FINAL FB TRANSLATION FAILED`.

The displayed PAR values are invalid diagnostic output, not usable hardware
translation results. Disassembling the exact CI kernel revealed that `;` starts
a comment in the Darwin assembly used here: only the first instruction in each
new multi-instruction asm string was emitted. ISB/MRS PAR and the targeted TLBI
operations were missing. The printed values correspond to stale general
registers, including the L3 PTE and L2 descriptor. This check therefore stopped
the kernel without establishing whether the corrected framebuffer mapping works.

The strings now use newline separators, and the translation helper is explicitly
not inlined. `check_kernel.py` verifies actual compiled AT/ISB/MRS and TLBI
instructions as well as table placement. The known broken 05b kernel is rejected.
The owner reports Android ready after restart and is sleeping; subsequent work
uses source builds and emulation without requesting photos or button presses.

`flame/qemu.py` runs the same console kernel on QEMU's virt machine with the
Pixel framebuffer address and RAM profile, substituting QEMU's GIC/timer ADT
values. `flame/qemu.Dockerfile` provides an isolated, unprivileged runtime.
It dumps and decodes framebuffer RAM into text/PNG and records registers,
exceptions, kernel SHA and QEMU version. This tests generic kernel execution
and mappings, not Pixel hardware or its display controller.

The known-broken 05b kernel was reproduced on QEMU 8.2.2. The decoded framebuffer
matches the owner's stage-8 screen and **every** descriptor/stale-PAR value.
The negative-control run reports `kva_active=0`, zero unknown glyphs, and the
expected failed translation-check message. Results are under ignored
`research/flame-qemu/05b-negative-control/`; no hardware result is inferred.
The runner also reads `kva_active` from simulated RAM, so a later console clear
cannot hide whether the final page-table handoff completed.

Corrected assembly build:
[run 39451069381](https://github.com/dimasmds/ios-flame/actions/runs/39451069381),
commit `12d9abbe1b41c41d0e7b1d45bb8a15dbf4a423c7`, succeeded.

To reproduce the negative control without USB access:

```sh
docker build -t ios-flame-qemu:local - < flame/qemu.Dockerfile
docker run --rm --network none --cpus 2 --memory 6g -v "$PWD:/work" \
  ios-flame-qemu:local python3 flame/qemu.py \
  research/flame-kernel/39448117298/kernel.development.sweet \
  research/flame-qemu/negative-control --reproduce-05b --seconds 10
```

For a corrected kernel, omit `--reproduce-05b` and supply a fresh output
directory. The runner then requires the compiled-instruction and alignment checks.

## Corrected assembly: emulator progress and next core dependencies

The corrected kernel passed source/checksum checks, actual linked alignment and
AT/ISB/PAR/TLBI instruction checks. Kernel SHA-256:
`51e54b18eede98199b6f42164804bc6cee174381dd903e230f0cac738d1c143a`.
Its checked phone image is preserved locally as
`flame/out/flame-xnu-39451069381.img`, SHA-256
`fe29500e2784b03881808a5e2cfcd3a05b1ab59df98528d6174c696045d4d45d`.
It has not been booted on the Pixel.

The QEMU run `research/flame-qemu/fixed-39451069381/` reports `kva_active=1`
and no framebuffer translation-check failure. The final console had advanced
beyond early markers: VM bootstrap completed, the platform expert registered,
and the boot CPU's SGI1 self-test passed. Timer/IRQ entries are present in the
emulator log. The next stop is a real kernel panic:
`pthread kernel extension not loaded (function table is NULL)` at
`pthread_shims.c:318`. Zero glyphs were undecodable. This demonstrates a generic
kernel/emulator milestone; Pixel IRQ/peripheral support remains unverified.

The profile now explicitly selects patches 0001–0020, 0023, 0027, and Pixel0099,
plus staging scripts 0019/0020. These add the matching Apple libpthread provider
and portable AES/SHA256/MD5 providers needed by later generic kernel startup.
The pinned libpthread commit is `a6c70ca0e544347a0377babf748f831577ec24f9`;
the BearSSL commit is `7bea48e5e850ab4cafbe68d3765cdaba13a86d6f`.
No filesystem, storage, AMFI replacement or later peripheral patch is selected.
The manifest now covers all 25 source inputs (23 patches and two staging scripts),
and stage/packer use the same selection function. All extra patches apply cleanly
to the pinned source; the staged builder and helper scripts pass syntax checks.

Expanded-core build:
[run 39452744863](https://github.com/dimasmds/ios-flame/actions/runs/39452744863),
commit `47ee00dc0ba399fe35a799acbea3f0eca13dc002`, succeeded.

## Latest ready image: core startup reaches root discovery in QEMU

Run 39452744863 succeeded. Artifact profile/checksum, actual linked table
alignment, compiled AT/ISB/PAR/TLBI sequences, payload validation, and all host
boot-image checks passed. Kernel SHA-256:
`f6813708e9cb0fd402f2bbcbeee2b3b20247d8fe2c6eaf948952bad61b23d494`.

The 75-second emulator run `research/flame-qemu/core-39452744863/` passes with
zero undecodable glyphs, no panic observed, `kva_active=1`, and no framebuffer
translation failure. The decoded screen confirms libpthread registration, CPU
SGI1 self-test completion, DLIL/Skywalk self-tests, and scheduling of kernel
threads. It reaches IOMedia matching for `Apple_HFS` at root-device discovery.
The wait is expected because no storage driver or root filesystem is supplied.
The final framebuffer console overwrites early stage text, so `kva_active=1`
provides the retained evidence of the successful page-table handoff.

Prepared phone image: `flame/out/flame-xnu-39452744863.img`, SHA-256
`d6563015cd360c31504b70172733bd0321562be3719aeab7a783a3e3e5a6d1e3`.
Entry PA `0x101491488`, boot arguments `0x102074000`.
No phone boot/flash/erase was performed during the overnight investigation.

On 2026-10-21, after the owner returned, **test 05c** temporarily loaded this
exact image on the verified Pixel. Preflight checked flame, Android
boot_completed=1, unlocked bootloader and the image SHA-256. `fastboot boot`
reported sending 65536 KB OKAY (1.602s), booting OKAY (4.053s), total 5.686s.
The transcript is ignored at research/flame-device/probe-05c-fastboot.txt.
The owner's `flame-ios-7.jpeg` confirms **root-device discovery on hardware**:
`Waiting on ... IOMedia ... Apple_HFS` is visible in the circular console above
older startup text. It also shows libpthread registration, platform expert
registration, boot CPU 0 registered / SGI1 verified / initialization complete,
MAC/mbinit, passing DLIL SUM16 and Skywalk self-tests, and kernel threads for
lo0/gif0/stf0 scheduled. This passes the former stage-8 framebuffer blocker and
confirms single-core scheduling and the SGI1 interrupt self-test on the Pixel.
Full timer accuracy and SMP are not established by this photo.

No panic backtrace is visible. The generic `Failed to store the panic-log to
NVRAM.` line is also present in the passing emulator screen and does not alone
establish a panic. No storage driver or root filesystem is supplied, so this
root-device wait is expected; it is not an iOS userland boot. The owner was told
to restart with Power; **Android return is verified** via adb (flame,
boot_completed=1, boot reason bootloader). Transcription
is ignored at research/flame-device/probe-05c-screen.json. No flash or erase
commands were issued.

The simulator's normal acceptance criterion now requires root-device discovery
as well as a completed framebuffer handoff and a fully decoded, panic-free
snapshot. Its default duration is 75 seconds; an arbitrary early blank/stalled
screen does not count as a pass.


## RAM-only userspace probe

The RAM-init source profile selects 0001–0025 plus 0027 and Pixel0099 (27 patches),
the two pinned dependency staging scripts, and tools/sweet-init.S + mkinit.py:
31 checksummed source inputs. Newly enabled mockfs serves a single Mach-O RAM
device as /sbin/launchd and provides /dev for devfs. Patches 0021/0022 fix typed
allocation and allow a RAM root without IOStorageFamily; 0024 routes virtual
RAM devices through normal device I/O rather than treating virtual addresses
as physical pages. The 0025 AMFI interface returns no entitlements and retains
kernel code-signature/page-hash checks. HFS, UFS and later peripheral drivers
remain excluded. All selected patches apply to a fresh pinned XNU checkout.

CI assembles the existing position-independent static syscall program, with
its hardware stack-alignment fix, and builds an ad-hoc SHA256 signed Mach-O.
This is a test program, not Apple launchd or iOS userland. It opens /dev/console,
prints its PID, then prints a heartbeat every five seconds via select timeouts.
No downloaded Apple firmware or SDK files are included in the artifact.

`python3 flame/pack_kernel.py ARTIFACT --ram-init` verifies the artifact/profile
and init checksum, appends the program in bounded kernel-managed RAM, adds the
RAMDisk ADT property, and selects rd=md0. The loader checks the complete payload
and protects its additional segment below topOfKernelData. No device storage
is accessed. Without --ram-init the packer still supplies no root.

The emulator's explicit --ram-init PATH option requires a visible PID 1 banner
and at least two heartbeats, a completed framebuffer handoff and no observed
panic. Use 150 seconds for this profile; root-wait alone is not a pass.
[CI run 39506928628](https://github.com/dimasmds/ios-flame/actions/runs/39506928628)
at commit `14490b8a02a410c15e5e8298390b95070a4cab66` succeeded. Kernel SHA-256:
`95cc1115f84cf9393af6fea29d7424294c31690dffe4e105f8ce92245e6caabe`.
Init SHA-256:
`f5de3714ff95e6a3b9ece30723f677de0f3f74ec5eb985a00c5ae872f0ac9bf1`.
Its machine code matches independently assembled GNU source bytes, including
the real three-instruction stack-alignment prologue. All CodeDirectory SHA256
page hashes independently match the executable.

The 150-second emulator run `research/flame-qemu/ram-init-39506928628/` PASSED:
PID 1 banner and 17 heartbeats, zero unknown glyphs, `kva_active=1`, no
translation failure and no panic observed in the snapshot. This demonstrates
the test program running in the emulator; hardware evidence is recorded below.

Image `flame/out/flame-xnu-39506928628-ram-init.img` SHA-256:
`c7b3e2f4f490d56db956f4aa1ed3323122c935f709ac0d6e7ec7a74bcd64f711`.
Actual linked kernel checks, profile/checksums, loader bounds and all host
boot-image checks pass. Entry PA `0x101491488`; RAM program
`0x102070000+0x8000`; boot arguments `0x10207c000`; top `0x102080000`.

**Hardware test 05d:** after verifying Android ready on the unlocked flame and
matching the exact image hash, temporary `fastboot boot` was accepted: sending
65536 KB OKAY (1.615s), booting OKAY (4.060s), total 5.707s. Ignored transcript:
research/flame-device/probe-05d-fastboot.txt. The owner subsequently reported
**`SWEET init: still alive` on the Pixel**, adding that the PID 1 banner had
probably been replaced. The heartbeat is emitted by the static userspace probe,
so this confirms userspace execution and /dev/console output on hardware. The
program is launched as init via mockfs; no photo independently captures the
numeric PID, heartbeat count or cadence. Evidence is the owner's text report,
not a hardware screenshot. It is saved ignored at
research/flame-device/probe-05d-owner-report.json.

The owner restarted Android; **return is verified** by adb (flame,
boot_completed=1, boot reason bootloader). No flash or erase commands were issued. This milestone is a
source-built userspace probe, not an Apple launchd/iOS UI boot. The next work
is a RAM-only filesystem test before expanding userland.


## Next milestone: HFS+ root in RAM

Profile 0001–0027 plus Pixel0099 adds the audited built-in HFS integration and
its pinned source-staging helper (28 patches / 34 source inputs total).
[Apple OSS hfs-627.100.6](https://github.com/apple-oss-distributions/hfs/tree/31d5ec238dfab485e78a9a30b8b92d13e8914f03)
is staged at its immutable commit; no UFS controller or later Redmi drivers
are selected. mockfs now rejects non-Mach-O root devices, allowing HFS to
mount the RAM filesystem. The raw-program RAM root remains available.

CI builds a 16 MiB HFS+ image containing a second static init variant at
/sbin/launchd, a /dev mount point and /etc/flame-test. The variant reads and
compares the file's 22 bytes, prints `FLAME HFS: file read verified` on success,
then heartbeats. A failed read prints FAILED and does not heartbeat.

flame/mkroot.py creates and populates only a private temporary macOS disk image,
then detaches it cleanly. It accepts flat UDRW output or strips a bounded UDIF
trailer; the trailer offsets follow the
[libmodi format research](https://github.com/libyal/libmodi/blob/main/documentation/Mac%20OS%20disk%20image%20types.asciidoc).
The raw-volume guard checks exact size, HFS+ version, block counts, clean state
and alternate header. It is a profile check, not a filesystem integrity checker;
actual mount/exec/read behavior must pass the kernel emulator test.

The packer's explicit --hfs-root option verifies root/init/metadata hashes,
embeds the image in bounded kernel-managed RAM and selects rd=md0. No rootrw
or UFS arguments are supplied. The simulator's --hfs-root PATH additionally
requires an HFS mount, PID 1 banner, successful file read and >=2 heartbeats.
All 28 patches apply locally; source/profile, Python/script syntax, relocation
and malformed/dirty/out-of-bounds image checks pass. CI/emulator and a new
Pixel hardware test are pending.
