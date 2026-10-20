#pragma once
#include <stddef.h>
#include <stdint.h>

/* Bounded FDT traversal. Only properties of the exact path are returned. */
struct dt { const uint8_t *blob; uint32_t size, structure, end, strings, strings_size; };
static inline uint32_t dt_be32(const uint8_t *p)
{
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}
int dt_open(struct dt *dt, const void *blob, size_t available);
const uint8_t *dt_prop(const struct dt *dt, const char *path, const char *key, uint32_t *length);
