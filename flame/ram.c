#include "ram.h"

#define WORDS (RAM_TEST_PAGE / sizeof(uint64_t))
static uint64_t saved[2][WORDS];

static void barrier(void)
{
#ifdef __aarch64__
    __asm__ volatile("dsb sy" ::: "memory");
#else
    __sync_synchronize();
#endif
}

int ram_test(uintptr_t base, uint64_t size, struct ram_report *r)
{
    *r = (struct ram_report){0};
    if ((base & (RAM_TEST_PAGE - 1)) || size < 2 * RAM_TEST_PAGE ||
        (size & (RAM_TEST_PAGE - 1)) || base > UINTPTR_MAX - size) return 0;
    r->first = base;
    r->last = base + size - RAM_TEST_PAGE;
    /* Save both pages before modifying either, so aliasing can be detected. */
    for (unsigned page = 0; page < 2; page++) {
        volatile uint64_t *p = (volatile uint64_t *)(page ? r->last : r->first);
        for (unsigned i = 0; i < WORDS; i++) saved[page][i] = p[i];
    }
    for (unsigned pass = 0; pass < 2; pass++) {
        uint64_t pattern = pass ? 0x5a5a5a5affffffffULL : 0xa5a5a5a500000000ULL;
        for (unsigned page = 0; page < 2; page++) {
            volatile uint64_t *p = (volatile uint64_t *)(page ? r->last : r->first);
            for (unsigned i = 0; i < WORDS; i++) p[i] = pattern ^ (uintptr_t)&p[i];
        }
        barrier();
        for (unsigned page = 0; page < 2; page++) {
            volatile uint64_t *p = (volatile uint64_t *)(page ? r->last : r->first);
            for (unsigned i = 0; i < WORDS; i++) {
                if (p[i] != (pattern ^ (uintptr_t)&p[i])) r->pattern_errors++;
                r->words_compared++;
            }
        }
    }
    for (unsigned page = 0; page < 2; page++) {
        volatile uint64_t *p = (volatile uint64_t *)(page ? r->last : r->first);
        for (unsigned i = 0; i < WORDS; i++) p[i] = saved[page][i];
    }
    barrier();
    for (unsigned page = 0; page < 2; page++) {
        volatile uint64_t *p = (volatile uint64_t *)(page ? r->last : r->first);
        for (unsigned i = 0; i < WORDS; i++) if (p[i] != saved[page][i]) r->restore_errors++;
    }
    return 1;
}
