#include "mmu.h"

#define PAGE 0x4000ULL
#define ENTRIES 2048U
#define TABLE_MASK 0x0000ffffffffc000ULL
#define UXN (1ULL << 54)
#define PXN (1ULL << 53)
#define FLAGS (3ULL | (1ULL << 10) | (3ULL << 8) | UXN)
/* L2 root plus at most five L3 tables, and one page of runtime alignment slack. */
static uint64_t tables[7 * ENTRIES] __attribute__((aligned(4096)));

static int map(struct mmu_report *r, uint64_t lo, uint64_t hi, int executable)
{
    if (hi <= lo || hi > (1ULL << 36) || hi > UINT64_MAX - PAGE + 1) return 0;
    lo &= ~(PAGE - 1);
    hi = (hi + PAGE - 1) & ~(PAGE - 1);
    uint64_t *l2 = (uint64_t *)(uintptr_t)r->root;
    for (uint64_t pa = lo; pa < hi; pa += PAGE) {
        unsigned index = pa >> 25;
        if (!l2[index]) {
            if (r->tables == 6) return 0;
            l2[index] = (r->root + r->tables++ * PAGE) | 3;
        }
        uint64_t *l3 = (uint64_t *)(uintptr_t)(l2[index] & TABLE_MASK);
        unsigned slot = (pa >> 14) & (ENTRIES - 1);
        if (l3[slot]) return 0; /* Overlapping regions are not accepted. */
        l3[slot] = pa | FLAGS | (executable ? 0 : PXN);
    }
    return 1;
}

int mmu_prepare(uintptr_t image_lo, uintptr_t image_hi, uintptr_t fb, uint64_t fb_size,
                uintptr_t first, uintptr_t last, struct mmu_report *r)
{
    *r = (struct mmu_report){0};
    if (image_hi <= image_lo || image_hi - image_lo > 0x200000 ||
        !fb_size || fb_size > 0x1000000 || fb > UINT64_MAX - fb_size ||
        (first & (PAGE - 1)) || (last & (PAGE - 1)) ||
        first > UINT64_MAX - PAGE || last > UINT64_MAX - PAGE) return 0;
    r->root = ((uintptr_t)tables + PAGE - 1) & ~(PAGE - 1);
    r->tables = 1;
    r->image_lo = image_lo;
    r->image_hi = image_hi;
    uint64_t *pool = (uint64_t *)(uintptr_t)r->root;
    for (unsigned i = 0; i < 6 * ENTRIES; i++) pool[i] = 0;
    return map(r, image_lo, image_hi, 1) && map(r, fb, fb + fb_size, 0) &&
           map(r, first, first + PAGE, 0) && map(r, last, last + PAGE, 0);
}

#ifdef __aarch64__
#define READ(reg) ({ uint64_t value; __asm__ volatile("mrs %0, " reg : "=r"(value)); value; })
#define WRITE(reg, value) __asm__ volatile("msr " reg ", %0" : : "r"((uint64_t)(value)) : "memory")

int mmu_enable(struct mmu_report *r)
{
    r->saved_sctlr = READ("sctlr_el1");
    if (READ("CurrentEL") != 4 || (r->saved_sctlr & 5) ||
        ((READ("id_aa64mmfr0_el1") >> 20) & 15) != 1 ||
        r->root < r->image_lo || r->root + 6 * PAGE > r->image_hi) return 0;
    r->saved_tcr = READ("tcr_el1");
    r->saved_mair = READ("mair_el1");
    r->saved_ttbr = READ("ttbr0_el1");
    /* 36-bit VA, root at L2; 16K granule; TTBR1 disabled; 36-bit PA.
     * Tables and mapped RAM are Normal non-cacheable, so no cache is enabled. */
    uint64_t tcr = 28ULL | (3ULL << 12) | (2ULL << 14) | (28ULL << 16) |
                   (1ULL << 23) | (1ULL << 30) | (1ULL << 32);
    __asm__ volatile("dsb sy" ::: "memory");
    WRITE("mair_el1", 0x44);
    WRITE("tcr_el1", tcr);
    WRITE("ttbr0_el1", r->root);
    __asm__ volatile("isb; tlbi vmalle1; dsb sy; isb" ::: "memory");
    WRITE("sctlr_el1", (r->saved_sctlr & ~(1ULL << 19)) | 1);
    __asm__ volatile("isb" ::: "memory");
    return 1;
}

void mmu_disable(const struct mmu_report *r)
{
    __asm__ volatile("dsb sy" ::: "memory");
    WRITE("sctlr_el1", r->saved_sctlr);
    __asm__ volatile("isb; tlbi vmalle1; dsb sy; isb" ::: "memory");
    WRITE("ttbr0_el1", r->saved_ttbr);
    WRITE("tcr_el1", r->saved_tcr);
    WRITE("mair_el1", r->saved_mair);
    __asm__ volatile("isb" ::: "memory");
}

uint64_t mmu_translate(uintptr_t address)
{
    __asm__ volatile("at s1e1r, %0; isb" : : "r"(address) : "memory");
    return READ("par_el1");
}
#else
int mmu_enable(struct mmu_report *r) { (void)r; return 0; }
void mmu_disable(const struct mmu_report *r) { (void)r; }
uint64_t mmu_translate(uintptr_t address) { (void)address; return 1; }
#endif
