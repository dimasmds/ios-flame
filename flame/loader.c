/* Bounded, storage-free loader for the limited Pixel early-console kernel. */
#include "loader.h"

#define PAGE 0x4000ULL
#define LINE 608
struct segment { uint64_t va, size, offset, bytes; };
struct payload {
    char magic[8];
    uint32_t version, count;
    uint64_t virt, entry, adt_offset, adt_size, kernel_end, phys, memory;
    char command[LINE];
    struct segment segments[];
};
struct video { uint64_t base, display, stride, width, height, depth; };
struct boot_args {
    uint16_t revision, version;
    uint64_t virt, phys, memory, top;
    struct video video;
    uint32_t machine;
    uint64_t tree;
    uint32_t tree_size;
    char command[LINE];
    uint64_t flags, actual;
};
_Static_assert(offsetof(struct payload, segments) == 0x2a8, "payload ABI");
_Static_assert(offsetof(struct boot_args, video) == 40, "video ABI");
_Static_assert(offsetof(struct boot_args, command) == 108, "command ABI");
_Static_assert(sizeof(struct boot_args) == 736, "boot_args ABI");

const char *payload_validate(const void *data, size_t length, struct load_plan *plan)
{
    *plan = (struct load_plan){0};
    if (((uintptr_t)data & 7) || length < sizeof(struct payload) || length > FLAME_IMAGE_MAX)
        return "PAYLOAD SIZE OR ALIGNMENT";
    const struct payload *p = data;
    const char magic[] = "SWEETXNU";
    for (unsigned i = 0; i < 8; i++) if (p->magic[i] != magic[i]) return "PAYLOAD MAGIC";
    if (p->version != 1 || !p->count || p->count > 32 ||
        p->count > (length - sizeof(*p)) / sizeof(struct segment)) return "PAYLOAD HEADER";
    uint64_t header = sizeof(*p) + p->count * sizeof(struct segment);
    if (p->phys != FLAME_RAM_BASE || p->memory != FLAME_RAM_SIZE ||
        (p->virt & 0x1ffffff) || p->virt < 0xffff000000000000ULL ||
        p->virt > UINT64_MAX - FLAME_RAM_SIZE) return "PAYLOAD RAM PROFILE";
    uintptr_t source = (uintptr_t)data;
    if (source > UINTPTR_MAX - length ||
        (source < FLAME_RAM_BASE + FLAME_RAM_SIZE && source + length > FLAME_RAM_BASE))
        return "PAYLOAD SOURCE OVERLAP";
    if (p->command[LINE - 1] || p->adt_offset < header || (p->adt_offset & 7) ||
        p->adt_offset > length || p->adt_size < 8 || p->adt_size > 0x100000 ||
        p->adt_size > length - p->adt_offset || p->kernel_end < p->virt ||
        p->kernel_end - p->virt >= FLAME_RAM_SIZE || (p->kernel_end & (PAGE - 1)))
        return "PAYLOAD ADT OR END";
    int entry_found = 0;
    for (unsigned i = 0; i < p->count; i++) {
        const struct segment *s = &p->segments[i];
        if (s->va < p->virt || (s->va & (PAGE - 1)) || !s->size ||
            s->va - p->virt >= FLAME_RAM_SIZE || s->size > FLAME_RAM_SIZE - (s->va - p->virt) ||
            s->bytes > s->size || s->offset < header || (s->offset & 7) ||
            s->offset > p->adt_offset || s->bytes > p->adt_offset - s->offset ||
            s->va + s->size > p->kernel_end) return "PAYLOAD SEGMENT BOUNDS";
        for (unsigned j = 0; j < i; j++) {
            const struct segment *t = &p->segments[j];
            if (s->va < t->va + t->size && s->va + s->size > t->va)
                return "PAYLOAD SEGMENT OVERLAP";
        }
        if (!(p->entry & 3) && s->bytes >= 4 && p->entry >= s->va && p->entry - s->va <= s->bytes - 4)
            entry_found = 1;
    }
    if (!entry_found) return "PAYLOAD ENTRY";
    uint64_t adt = p->kernel_end - p->virt;
    if (p->adt_size > FLAME_RAM_SIZE - adt) return "PAYLOAD ADT RAM BOUNDS";
    uint64_t args = (adt + p->adt_size + PAGE - 1) & ~(PAGE - 1);
    if (args > FLAME_RAM_SIZE - PAGE) return "PAYLOAD BOOT ARGS BOUNDS";
    *plan = (struct load_plan){adt, args, args + PAGE, p->entry - p->virt};
    return 0;
}

static void copy(uintptr_t dst, uintptr_t src, uint64_t size)
{
    if (!((dst | src) & 7)) {
        while (size >= 8) {
            *(volatile uint64_t *)dst = *(const volatile uint64_t *)src;
            dst += 8; src += 8; size -= 8;
        }
    }
    while (size--) *(volatile uint8_t *)dst++ = *(const volatile uint8_t *)src++;
}

static void zero(uintptr_t dst, uint64_t size)
{
    while ((dst & 7) && size) { *(volatile uint8_t *)dst++ = 0; size--; }
    while (size >= 8) { *(volatile uint64_t *)dst = 0; dst += 8; size -= 8; }
    while (size--) *(volatile uint8_t *)dst++ = 0;
}

void payload_materialize(const void *data, const struct load_plan *plan, uintptr_t base)
{
    const struct payload *p = data;
    for (unsigned i = 0; i < p->count; i++) {
        const struct segment *s = &p->segments[i];
        uintptr_t dst = base + (s->va - p->virt);
        copy(dst, (uintptr_t)data + s->offset, s->bytes);
        zero(dst + s->bytes, s->size - s->bytes);
    }
    copy(base + plan->adt, (uintptr_t)data + p->adt_offset, p->adt_size);
    zero(base + plan->args, PAGE);
    volatile struct boot_args *ba = (volatile struct boot_args *)(base + plan->args);
    ba->revision = 2; ba->version = 2;
    ba->virt = p->virt; ba->phys = p->phys; ba->memory = p->memory;
    ba->top = p->phys + plan->top;
    ba->video.base = 0x9c400000; ba->video.display = 1; ba->video.stride = 4320;
    ba->video.width = 1080; ba->video.height = 2280; ba->video.depth = 32;
    ba->tree = p->virt + plan->adt; ba->tree_size = p->adt_size;
    for (unsigned i = 0; i < LINE; i++) ba->command[i] = p->command[i];
    ba->actual = p->memory;
}
