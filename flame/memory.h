#pragma once
#include "fdt.h"

struct map_report {
    uint64_t candidate, size, highest_fixed_end;
    uint32_t ram_banks, fixed_ranges, reserve_entries, dynamic_pools;
    uint32_t conflicts, unbounded_pools, errors, contained;
};
/* Inspects metadata only; never accesses candidate RAM. Excludes the DTB and
 * caller-supplied running image, and checks /chosen initrd when present. */
void map_check(const struct dt *, uint64_t candidate, uint64_t size,
               uint64_t image_start, uint64_t image_end, struct map_report *);
