#pragma once
#include "fdt.h"
/* Metadata-only check for the fixed addresses in the early Pixel ADT. */
int platform_check(const struct dt *);
int platform_ufs_check(const struct dt *);
