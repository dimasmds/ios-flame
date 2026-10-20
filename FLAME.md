# Pixel 4 (flame) bring-up

This branch starts a new SM8150 port. **XNU reaches early VM initialization on
the Pixel; iOS userland has not booted.**
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
