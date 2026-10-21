#include "ufs.h"

/* Installed Google kernel ufshci.h register offsets, in reporting order. */
void ufs_capture(uint32_t (*read32)(uintptr_t), struct ufs_report *r)
{
    r->cap = read32(FLAME_UFS_BASE + 0x00);
    r->version = read32(FLAME_UFS_BASE + 0x08);
    r->hce = read32(FLAME_UFS_BASE + 0x34);
    r->hcs = read32(FLAME_UFS_BASE + 0x30);
    r->list_lo = read32(FLAME_UFS_BASE + 0x50);
    r->list_hi = read32(FLAME_UFS_BASE + 0x54);
    r->run = read32(FLAME_UFS_BASE + 0x60);
    r->doorbell = read32(FLAME_UFS_BASE + 0x58);
    r->task_run = read32(FLAME_UFS_BASE + 0x80);
    r->task_doorbell = read32(FLAME_UFS_BASE + 0x78);
}
