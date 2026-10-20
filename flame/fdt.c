#include "fdt.h"

static int equal(const char *a, const char *b)
{
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}

int dt_open(struct dt *dt, const void *blob, size_t available)
{
    const uint8_t *p = blob;
    if (!p || available < 40 || dt_be32(p) != 0xd00dfeed) return 0;
    uint32_t size = dt_be32(p + 4), s = dt_be32(p + 8), strings = dt_be32(p + 12);
    uint32_t ns = dt_be32(p + 32), nt = dt_be32(p + 36);
    if (size < 40 || size > available || dt_be32(p + 20) < 17 || dt_be32(p + 24) > 17 ||
        s < 40 || (s & 3) || s > size || nt > size - s ||
        strings < 40 || strings > size || ns > size - strings) return 0;
    *dt = (struct dt){p, size, s, s + nt, strings, ns};
    return 1;
}

const uint8_t *dt_prop(const struct dt *dt, const char *wanted, const char *key, uint32_t *length)
{
    char path[256];
    uint32_t saved[32], used = 0, depth = 0, pos = dt->structure;
    path[0] = 0;
    while (pos <= dt->end && dt->end - pos >= 4) {
        uint32_t token = dt_be32(dt->blob + pos); pos += 4;
        if (token == 1) {
            if (depth == 32) return NULL;
            saved[depth++] = used;
            if (used >= sizeof(path) - 1) return NULL;
            if (depth > 1) path[used++] = '/';
            while (pos < dt->end && dt->blob[pos]) {
                if (used >= sizeof(path) - 1) return NULL;
                path[used++] = dt->blob[pos++];
            }
            if (pos == dt->end) return NULL;
            path[used] = 0;
            pos = (pos + 4) & ~3U;
        } else if (token == 2) {
            if (!depth) return NULL;
            used = saved[--depth]; path[used] = 0;
        } else if (token == 3) {
            if (!depth || pos > dt->end || dt->end - pos < 8) return NULL;
            uint32_t n = dt_be32(dt->blob + pos), off = dt_be32(dt->blob + pos + 4);
            pos += 8;
            if (n > dt->end - pos || off >= dt->strings_size) return NULL;
            uint32_t end = off;
            while (end < dt->strings_size && dt->blob[dt->strings + end]) end++;
            if (end == dt->strings_size) return NULL;
            if (equal(path, wanted) && equal((const char *)dt->blob + dt->strings + off, key)) {
                *length = n; return dt->blob + pos;
            }
            pos = (pos + n + 3) & ~3U;
        } else if (token != 4) {
            return NULL;
        }
    }
    return NULL;
}
