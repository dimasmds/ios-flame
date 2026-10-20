#include "platform.h"

static int cells(const struct dt *dt, const char *path, const char *key,
                 const uint32_t *expected, unsigned count)
{
    uint32_t length;
    const uint8_t *p = dt_prop(dt, path, key, &length);
    if (!p || length != count * 4) return 0;
    for (unsigned i = 0; i < count; i++) if (dt_be32(p + i * 4) != expected[i]) return 0;
    return 1;
}

int platform_check(const struct dt *dt)
{
    const uint32_t one[] = {1}, two[] = {2}, ranges[] = {0, 0, 0, 0xffffffff};
    const uint32_t gic[] = {0x17a00000, 0x10000, 0x17a60000, 0x100000};
    const uint32_t stride[] = {0, 0x20000}, frequency[] = {19200000};
    const uint32_t timer[] = {1, 1, 0xf08, 1, 2, 0xf08, 1, 3, 0xf08, 1, 0, 0xf08};
    uint32_t length;
    const uint8_t *compat = dt_prop(dt, "/soc/interrupt-controller@17a00000", "compatible", &length);
    const char want[] = "arm,gic-v3";
    if (!compat || length != sizeof(want)) return 0;
    for (unsigned i = 0; i < sizeof(want); i++) if (compat[i] != (uint8_t)want[i]) return 0;
    return cells(dt, "", "#address-cells", two, 1) &&
           cells(dt, "/soc", "#address-cells", one, 1) &&
           cells(dt, "/soc", "#size-cells", one, 1) &&
           cells(dt, "/soc", "ranges", ranges, 4) &&
           cells(dt, "/soc/interrupt-controller@17a00000", "reg", gic, 4) &&
           cells(dt, "/soc/interrupt-controller@17a00000", "redistributor-stride", stride, 2) &&
           cells(dt, "/soc/timer", "interrupts", timer, 12) &&
           cells(dt, "/soc/timer", "clock-frequency", frequency, 1);
}
