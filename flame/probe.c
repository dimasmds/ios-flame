/* First Pixel 4 experiment: CPU/FDT inspection, no storage or peripheral drivers. */
#include <stdint.h>
#include "fdt.h"
#include "memory.h"
#include "ram.h"
#include "mmu.h"
#include "loader.h"
#include "platform.h"
#include "../shim/font.h"

#define READ(r) ({ uint64_t v; __asm__ volatile("mrs %0, " r : "=r"(v)); v; })
#define WIDTH 1080U
#define HEIGHT 2280U
static volatile uint32_t *screen;
static unsigned row;
static int use_hvc;
extern char _head[], _end[];

static uint64_t firmware(uint64_t fn)
{
    register uint64_t x0 __asm__("x0") = fn;
    register uint64_t x1 __asm__("x1") = 0;
    register uint64_t x2 __asm__("x2") = 0;
    register uint64_t x3 __asm__("x3") = 0;
    if (use_hvc)
        __asm__ volatile("hvc #0" : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3) : :
            "x4", "x5", "x6", "x7", "x8", "x9", "x10", "x11", "x12", "x13", "x14", "x15", "x16", "x17", "memory");
    else
        __asm__ volatile("smc #0" : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3) : :
            "x4", "x5", "x6", "x7", "x8", "x9", "x10", "x11", "x12", "x13", "x14", "x15", "x16", "x17", "memory");
    return x0;
}

static void line(const char *s)
{
    if (!screen) return;
    for (unsigned col = 0; s[col] && col < 42; col++) {
        unsigned c = (unsigned char)s[col];
        if (c < 32 || c > 126) c = '?';
        for (unsigned y = 0; y < 16; y++)
            for (unsigned x = 0; x < 8; x++)
                for (unsigned sy = 0; sy < 3; sy++)
                    for (unsigned sx = 0; sx < 3; sx++) {
                        unsigned px = 24 + col * 24 + x * 3 + sx;
                        unsigned py = 24 + row * 48 + y * 3 + sy;
                        if (py < HEIGHT)
                            screen[py * WIDTH + px] = (font8x16[c - 32][y] & (0x80 >> x)) ? 0xffffffff : 0xff180820;
                    }
    }
    row++;
    __asm__ volatile("dsb sy" ::: "memory");
}

static void hex(const char *label, uint64_t v)
{
    char out[43]; unsigned n = 0;
    while (*label && n < 24) out[n++] = *label++;
    out[n++] = ' ';
    for (int i = 15; i >= 0; i--) {
        unsigned digit = (v >> (i * 4)) & 15;
        out[n++] = digit < 10 ? '0' + digit : 'A' + digit - 10;
    }
    out[n] = 0; line(out);
}

static void wait_seconds(unsigned seconds)
{
    uint64_t freq = READ("cntfrq_el0");
    uint64_t begin = READ("cntpct_el0");
    while (READ("cntpct_el0") - begin < freq * seconds) __asm__ volatile("yield");
}

static void __attribute__((noreturn)) reset(void)
{
    firmware(0x84000009); /* PSCI SYSTEM_RESET: normal Android boot, no IMEM writes. */
    for (;;) __asm__ volatile("wfe");
}

void __attribute__((noreturn)) probe_exception(void)
{
    line("EXCEPTION - RESETTING");
    if (READ("CurrentEL") == 8) { hex("ESR", READ("esr_el2")); hex("ELR", READ("elr_el2")); }
    else { hex("ESR", READ("esr_el1")); hex("ELR", READ("elr_el1")); }
    wait_seconds(5); reset();
}

static uint64_t cells64(const uint8_t *p) { return (uint64_t)dt_be32(p) << 32 | dt_be32(p + 4); }

void probe_main(uintptr_t fdt_address)
{
    struct dt dt; uint32_t n;
    /* The Linux boot protocol supplies a valid FDT in x0; cap traversal at 2 MiB. */
    if (!dt_open(&dt, (const void *)fdt_address, 0x200000)) { wait_seconds(5); reset(); }
    const uint8_t *method = dt_prop(&dt, "/psci", "method", &n);
    use_hvc = method && n == 4 && method[0] == 'h' && method[1] == 'v' && method[2] == 'c' && method[3] == 0;
    const uint8_t *ac = dt_prop(&dt, "/reserved-memory", "#address-cells", &n);
    if (!ac || n != 4 || dt_be32(ac) != 2) { wait_seconds(5); reset(); }
    const uint8_t *sc = dt_prop(&dt, "/reserved-memory", "#size-cells", &n);
    if (!sc || n != 4 || dt_be32(sc) != 2) { wait_seconds(5); reset(); }
    const uint8_t *splash = dt_prop(&dt, "/reserved-memory/cont_splash_region", "reg", &n);
    /* Only write Google's documented splash reservation, after validating the live tree. */
    if (!splash || n != 16 || cells64(splash) != 0x9c400000 ||
        cells64(splash + 8) < WIDTH * HEIGHT * 4 || cells64(splash + 8) > 0x02400000) {
        wait_seconds(5); reset();
    }
    screen = (volatile uint32_t *)(uintptr_t)cells64(splash);
    for (unsigned i = 0; i < WIDTH * HEIGHT; i++) screen[i] = 0xff180820;
#ifdef PROBE_MAP
#ifdef PROBE_KERNEL
    line("PIXEL 4 / FLAME - XNU TEST 05");
    line("EARLY CONSOLE - NO STORAGE DRIVER");
    uint64_t image_size = *(const uint64_t *)(_head + 16);
    uintptr_t image_start = (uintptr_t)_head;
    uintptr_t embedded = ((uintptr_t)_end + 0xfff) & ~0xfffULL;
    if (image_size > FLAME_IMAGE_MAX || image_size < embedded - image_start + 16 ||
        image_start > UINTPTR_MAX - image_size || image_start + image_size > fdt_address) {
        line("EMBEDDED IMAGE BOUNDS REJECTED"); wait_seconds(120); reset();
    }
    const char tag[] = "FLAMEPLD";
    for (unsigned i = 0; i < 8; i++)
        if (((const char *)embedded)[i] != tag[i]) {
            line("EMBEDDED PAYLOAD TAG REJECTED"); wait_seconds(120); reset();
        }
    uint64_t payload_size = *(const uint64_t *)(embedded + 8);
    if (payload_size != image_start + image_size - embedded - 16) {
        line("EMBEDDED PAYLOAD LENGTH REJECTED"); wait_seconds(120); reset();
    }
#elif defined(PROBE_MMU)
    line("PIXEL 4 / FLAME - MMU PROBE 04");
    line("16K IDENTITY TRANSLATION TEST");
#elif defined(PROBE_RAM)
    line("PIXEL 4 / FLAME - RAM PROBE 03");
    line("TEST TWO 16K PAGES, THEN RESTORE");
#else
    line("PIXEL 4 / FLAME - MAP PROBE 02");
    line("READ-ONLY MEMORY MAP CHECK");
#endif
    struct map_report map;
    map_check(&dt, 0x100000000ULL, 0x40000000ULL, (uintptr_t)_head,
#ifdef PROBE_KERNEL
              image_start + image_size,
#else
              (uintptr_t)_end,
#endif
              &map);
    hex("CANDIDATE", map.candidate);
    hex("SIZE", map.size);
    hex("IN RAM", map.contained);
    hex("RAM BANKS", map.ram_banks);
    hex("FIXED RANGES", map.fixed_ranges);
    hex("FIXED END", map.highest_fixed_end);
    hex("RESERVE ENTRIES", map.reserve_entries);
    hex("DYNAMIC POOLS", map.dynamic_pools);
    hex("UNBOUNDED POOLS", map.unbounded_pools);
    hex("CONFLICTS", map.conflicts);
    hex("MAP ERRORS", map.errors);
    if (!map.errors && !map.conflicts && !map.unbounded_pools) {
#if defined(PROBE_RAM) || defined(PROBE_MMU) || defined(PROBE_KERNEL)
        line("NO DT CONFLICTS - TEST PERMITTED");
#else
        line("NO DT CONFLICTS - NOT RAM TESTED");
#endif
    } else
        line("CANDIDATE NOT CLEARED FOR XNU");
#ifdef PROBE_KERNEL
    uint64_t sctlr = READ("sctlr_el1");
    if (map.errors || map.conflicts || map.unbounded_pools || !map.contained ||
        READ("CurrentEL") != 4 || (sctlr & 5) || (READ("mpidr_el1") & 0xff00ffffffULL) ||
        !platform_check(&dt) || READ("cntfrq_el0") != 19200000 ||
        ((READ("id_aa64mmfr0_el1") >> 20) & 15) != 1) line("KERNEL PRECONDITIONS FAILED");
    else {
        struct load_plan plan;
        const void *payload = (const void *)(embedded + 16);
        const char *error = payload_validate(payload, payload_size, &plan);
        if (error) line(error);
        else {
            line("BOUNDED PAYLOAD VERIFIED");
            hex("KERNEL ENTRY", FLAME_RAM_BASE + plan.entry);
            hex("BOOT ARGS", FLAME_RAM_BASE + plan.args);
            hex("KERNEL DATA END", FLAME_RAM_BASE + plan.top);
            line("COPYING KERNEL AND DEVICE TREE");
            payload_materialize(payload, &plan, FLAME_RAM_BASE);
            line("JUMPING TO XNU - CAPTURE SCREEN");
            wait_seconds(2);
            __asm__ volatile("dsb sy; ic iallu; dsb sy; isb" ::: "memory");
            ((void (*)(uint64_t))(uintptr_t)(FLAME_RAM_BASE + plan.entry))(FLAME_RAM_BASE + plan.args);
            line("XNU RETURNED UNEXPECTEDLY");
        }
    }
#elif defined(PROBE_MMU)
    if (!map.errors && !map.conflicts && !map.unbounded_pools && map.contained) {
        struct mmu_report mmu;
        uintptr_t first = map.candidate, last = map.candidate + map.size - RAM_TEST_PAGE;
        if (!mmu_prepare((uintptr_t)_head, (uintptr_t)_end, (uintptr_t)screen,
                         WIDTH * HEIGHT * 4, first, last, &mmu)) line("MMU TABLE PREPARATION FAILED");
        else {
            hex("TABLE ROOT", mmu.root);
            hex("TABLE PAGES", mmu.tables);
            line("ENABLING 16K MMU");
            if (!mmu_enable(&mmu)) line("MMU PRECONDITIONS FAILED");
            else {
                uint64_t a = mmu_translate(first), b = mmu_translate(last);
                hex("TCR", READ("tcr_el1"));
                hex("SCTLR ON", READ("sctlr_el1"));
                hex("PAR FIRST", a); hex("PAR LAST", b);
                if (!(a & 1) && !(b & 1) && (a & 0x0000fffffffff000ULL) == first &&
                    (b & 0x0000fffffffff000ULL) == last) {
                    line("16K TRANSLATIONS VERIFIED");
                    struct ram_report ram;
                    if (!ram_test(map.candidate, map.size, &ram)) line("TRANSLATED RAM TEST REJECTED");
                    else {
                        hex("PATTERN ERRORS", ram.pattern_errors);
                        hex("RESTORE ERRORS", ram.restore_errors);
                        if (!ram.pattern_errors && !ram.restore_errors) line("TRANSLATED TWO PAGE TEST PASSED");
                        else line("TRANSLATED RAM TEST FAILED");
                    }
                } else line("TRANSLATION CHECK FAILED");
                mmu_disable(&mmu);
                hex("SCTLR RESTORED", READ("sctlr_el1"));
                line("MMU DISABLED AGAIN");
            }
        }
    } else line("MMU TEST SKIPPED - MAP CHECK FAILED");
#elif defined(PROBE_RAM)
    uint64_t sctlr = READ("sctlr_el1");
    hex("SCTLR", sctlr);
    if (!map.errors && !map.conflicts && !map.unbounded_pools && map.contained && !(sctlr & 5)) {
        line("RAM ACCESS STARTING");
        struct ram_report ram;
        if (!ram_test(map.candidate, map.size, &ram)) line("RAM TEST ARGUMENTS REJECTED");
        else {
            hex("FIRST PAGE", ram.first);
            hex("LAST PAGE", ram.last);
            hex("WORDS COMPARED", ram.words_compared);
            hex("PATTERN ERRORS", ram.pattern_errors);
            hex("RESTORE ERRORS", ram.restore_errors);
            if (!ram.pattern_errors && !ram.restore_errors)
                line("TWO PAGE RAM TEST PASSED");
            else line("RAM TEST FAILED - STOP HERE");
        }
    } else line("RAM ACCESS SKIPPED - STOP HERE");
    line("REST OF 1 GIB RANGE NOT TESTED");
#else
    line("CANDIDATE RAM WAS NOT ACCESSED");
#endif
#else
    line("PIXEL 4 / FLAME - PROBE 01");
    line("CPU + BOOT DEVICE TREE ONLY");
    hex("EL", READ("CurrentEL") >> 2);
    hex("MIDR", READ("midr_el1"));
    hex("MPIDR", READ("mpidr_el1"));
    uint64_t mmfr0 = READ("id_aa64mmfr0_el1");
    hex("MMFR0", mmfr0);
    hex("TGRAN16", (mmfr0 >> 20) & 15);
    hex("MMFR1", READ("id_aa64mmfr1_el1"));
    hex("ISAR0", READ("id_aa64isar0_el1"));
    hex("ISAR1", READ("id_aa64isar1_el1"));
    hex("CNTFRQ", READ("cntfrq_el0"));
    hex("PSCI", firmware(0x84000000));
    hex("FDT", fdt_address);
    hex("FDT SIZE", dt.size);
    hex("SPLASH", cells64(splash));
    hex("SPLASH SIZE", cells64(splash + 8));
    const uint8_t *memory = dt_prop(&dt, "/memory", "reg", &n);
    if (memory && n % 16 == 0)
        for (uint32_t i = 0; i < n && i < 4 * 16; i += 16) {
            hex("RAM BASE", cells64(memory + i));
            hex("RAM SIZE", cells64(memory + i + 8));
        }
#endif
    line("NO PARTITIONS WRITTEN");
    line("ANDROID RESTART IN 120 SECONDS");
    /* Command-mode display may need a later DPU kickoff driver to show these writes. */
    wait_seconds(120); reset();
}
