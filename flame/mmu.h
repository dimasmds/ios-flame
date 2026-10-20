#pragma once
#include <stdint.h>

struct mmu_report {
    uint64_t root, tables, image_lo, image_hi;
    uint64_t saved_sctlr, saved_tcr, saved_mair, saved_ttbr;
};
/* Build precise identity mappings only: image, viewport, two test pages. */
int mmu_prepare(uintptr_t image_lo, uintptr_t image_hi, uintptr_t framebuffer,
                uint64_t framebuffer_size, uintptr_t first, uintptr_t last,
                struct mmu_report *);
int mmu_enable(struct mmu_report *);
void mmu_disable(const struct mmu_report *);
uint64_t mmu_translate(uintptr_t address);
