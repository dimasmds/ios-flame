#include "memory.h"

static int equal(const char *a, const char *b)
{
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}
static const char *prefix(const char *s, const char *p)
{
    while (*p && *s == *p) { s++; p++; }
    return *p ? NULL : s;
}
static uint64_t be64(const uint8_t *p) { return (uint64_t)dt_be32(p) << 32 | dt_be32(p + 4); }

static void exclude(struct map_report *r, uint64_t base, uint64_t size)
{
    if (!size) return;
    if (base > UINT64_MAX - size) { r->errors++; return; }
    if (base < r->candidate + r->size && r->candidate < base + size) r->conflicts++;
}

struct context { const struct dt *dt; struct map_report *report; };

static int property(const char *path, const char *key, const uint8_t *value, uint32_t n, void *arg)
{
    struct context *ctx = arg;
    struct map_report *r = ctx->report;
    if (equal(path, "/memory") && equal(key, "reg")) {
        if (!n || n % 16) { r->errors++; return 0; }
        for (uint32_t i = 0; i < n; i += 16) {
            uint64_t b = be64(value + i), s = be64(value + i + 8);
            r->ram_banks++;
            if (!s || b > UINT64_MAX - s) { r->errors++; continue; }
            if (r->candidate >= b && r->candidate + r->size <= b + s) r->contained = 1;
        }
    }
    const char *child = prefix(path, "/reserved-memory/");
    if (!child || !*child) return 0;
    /* Unknown nested buses need address translation; fail closed for them. */
    for (const char *p = child; *p; p++)
        if (*p == '/') { r->errors++; return 0; }
    if (equal(key, "reg")) {
        if (!n || n % 16) { r->errors++; return 0; }
        for (uint32_t i = 0; i < n; i += 16) {
            uint64_t b = be64(value + i), s = be64(value + i + 8);
            r->fixed_ranges++;
            exclude(r, b, s);
            if (b <= UINT64_MAX - s && b + s > r->highest_fixed_end) r->highest_fixed_end = b + s;
        }
    } else if (equal(key, "size")) {
        uint32_t length;
        /* A static reg takes precedence over size in the DT specification. */
        if (dt_prop(ctx->dt, path, "reg", &length)) return 0;
        r->dynamic_pools++;
        if (n != 8 || !be64(value)) { r->errors++; return 0; }
        const uint8_t *ranges = dt_prop(ctx->dt, path, "alloc-ranges", &length);
        if (!ranges) { r->unbounded_pools++; return 0; }
        if (!length || length % 16) { r->errors++; return 0; }
        /* Conservatively exclude every possible allocation window. */
        for (uint32_t i = 0; i < length; i += 16) exclude(r, be64(ranges + i), be64(ranges + i + 8));
    }
    return 0;
}

static int cells_are_two(const struct dt *dt, const char *path, const char *key)
{
    uint32_t n;
    const uint8_t *p = dt_prop(dt, path, key, &n);
    return p && n == 4 && dt_be32(p) == 2;
}

void map_check(const struct dt *dt, uint64_t candidate, uint64_t size,
               uint64_t image_start, uint64_t image_end, struct map_report *r)
{
    *r = (struct map_report){.candidate = candidate, .size = size};
    if (!size || candidate > UINT64_MAX - size) { r->errors++; return; }
    if (!cells_are_two(dt, "", "#address-cells") || !cells_are_two(dt, "", "#size-cells") ||
        !cells_are_two(dt, "/reserved-memory", "#address-cells") ||
        !cells_are_two(dt, "/reserved-memory", "#size-cells")) { r->errors++; return; }
    uint32_t n;
    const uint8_t *ranges = dt_prop(dt, "/reserved-memory", "ranges", &n);
    if (!ranges || n) { r->errors++; return; }
    struct context ctx = {dt, r};
    if (dt_walk(dt, property, &ctx) != 1) r->errors++;

    uint32_t offset = dt_be32(dt->blob + 16), limit = dt->size;
    if (dt->structure > offset && dt->structure < limit) limit = dt->structure;
    if (dt->strings > offset && dt->strings < limit) limit = dt->strings;
    int terminated = 0;
    if (offset < 40 || (offset & 7)) r->errors++;
    else while (offset <= limit && limit - offset >= 16) {
        uint64_t b = be64(dt->blob + offset), s = be64(dt->blob + offset + 8);
        offset += 16;
        if (!b && !s) { terminated = 1; break; }
        r->reserve_entries++; exclude(r, b, s);
    }
    if (!terminated) r->errors++;
    exclude(r, (uintptr_t)dt->blob, dt->size);
    if (image_end <= image_start) r->errors++;
    else exclude(r, image_start, image_end - image_start);

    uint32_t a, b;
    const uint8_t *start = dt_prop(dt, "/chosen", "linux,initrd-start", &a);
    const uint8_t *end = dt_prop(dt, "/chosen", "linux,initrd-end", &b);
    if (start || end) {
        if (!start || !end || (a != 4 && a != 8) || (b != 4 && b != 8)) r->errors++;
        else {
            uint64_t lo = a == 8 ? be64(start) : dt_be32(start);
            uint64_t hi = b == 8 ? be64(end) : dt_be32(end);
            if (hi < lo) r->errors++;
            else exclude(r, lo, hi - lo);
        }
    }
    if (!r->contained) r->errors++;
}
