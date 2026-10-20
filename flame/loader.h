#pragma once
#include <stddef.h>
#include <stdint.h>

#define FLAME_RAM_BASE 0x100000000ULL
#define FLAME_RAM_SIZE 0x40000000ULL
#define FLAME_IMAGE_MAX 0x4000000ULL
struct load_plan { uint64_t adt, args, top, entry; };
/* Validation is read-only. Offsets in the plan are relative to FLAME_RAM_BASE. */
const char *payload_validate(const void *, size_t, struct load_plan *);
/* Only call after successful validation; destination_base permits host checks. */
void payload_materialize(const void *, const struct load_plan *, uintptr_t destination_base);
