#pragma once
#include <stdint.h>

#define FLAME_UFS_BASE 0x01d84000UL
#define UFS_REG_COUNT 10
struct ufs_report { uint32_t cap, version, hce, hcs, list_lo, list_hi, run, doorbell, task_run, task_doorbell; };
/* Only register loads via the supplied reader. No write/DMA/command interface. */
void ufs_capture(uint32_t (*read32)(uintptr_t), struct ufs_report *);
