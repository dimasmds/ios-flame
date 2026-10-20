#pragma once
#include <stdint.h>

#define RAM_TEST_PAGE 0x4000U
struct ram_report {
    uint64_t first, last, words_compared;
    uint32_t pattern_errors, restore_errors;
};
/* Caller must establish that these are unused RAM pages and caches are off.
 * Saves/tests/restores the first and last 16 KiB pages, not the entire range.
 * Returns 0 for invalid arguments, 1 after all normal-path restores. */
int ram_test(uintptr_t base, uint64_t size, struct ram_report *report);
