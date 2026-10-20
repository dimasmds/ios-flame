#!/usr/bin/env python3
"""Pixel early-console ADT; one CPU, measured 1 GiB candidate, no storage/input."""
import argparse
import os
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import adt

u32 = lambda *v: struct.pack("<" + "I" * len(v), *v)
u64 = lambda *v: struct.pack("<" + "Q" * len(v), *v)
cstr = lambda s: s.encode() + b"\0"


def node(name, props=(), children=()):
    n = adt.Node()
    n.props = [("name", 0, cstr(name))] + [(k, 0, v) for k, v in props]
    n.children = list(children)
    return n


def build():
    phandles = iter(range(1, 100))
    ph = lambda: ("AAPL,phandle", u32(next(phandles)))
    timebase, soc = 19200000, 0x01000000
    cpu = node("cpu0", [ph(), ("device_type", cstr("cpu")),
        ("compatible", cstr("qcom,kryo485") + cstr("ARM,v8")),
        ("reg", u32(0)), ("cpu-id", u32(0)), ("cluster-id", u32(0)),
        ("cluster-type", u32(0)), ("die-cluster-id", u32(0)),
        ("cluster-core-id", u32(0)), ("l2-cache-id", u32(0)), ("l3-cache-id", u32(0)),
        ("state", cstr("running")), ("timebase-frequency", u32(timebase)),
        ("fixed-frequency", u32(timebase)), ("peripheral-frequency", u32(timebase)),
        # Informational placeholder frequencies; no clock programming is performed.
        ("clock-frequency", u32(400000000)), ("bus-frequency", u32(100000000)),
        ("memory-frequency", u32(100000000))])
    chosen = node("chosen", [ph(), ("dram-base", u64(0x100000000)),
        ("dram-size", u64(0x40000000)), ("random-seed", os.urandom(64)),
        ("debug-enabled", u32(1)), ("firmware-version", cstr("flame-early-shim"))],
        [node("memory-map", [ph()])])
    gic = node("gic", [ph(), ("compatible", cstr("arm,gic-v3")),
        ("interrupt-controller", b""), ("virtual-timer-intid", u32(19)),
        ("reg", u64(0x17a00000 - soc, 0x10000, 0x17a60000 - soc, 0x100000))])
    arm_io = node("arm-io", [ph(), ("device_type", cstr("sweet-io")),
        ("compatible", cstr("sweet-io") + cstr("arm-io")),
        ("#address-cells", u32(2)), ("#size-cells", u32(2)),
        ("ranges", u64(0, soc, 0x100000000 - soc))], [gic])
    return node("device-tree", [ph(), ("compatible", cstr("google,flame") + cstr("qcom,sm8150")),
        ("model", cstr("Google Pixel 4")), ("#address-cells", u32(2)), ("#size-cells", u32(2))],
        [chosen, node("defaults", [ph()]),
         node("cpus", [ph(), ("#address-cells", u32(1)), ("#size-cells", u32(0))], [cpu]),
         arm_io, node("sweet-fbcon", [ph(), ("reg", u64(0x9c400000, 0x2400000)),
             ("width", u32(1080)), ("height", u32(2280)), ("stride", u32(4320))])])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(adt.serialize(build()))
    print(f"{args.output}: Pixel early-console ADT; not yet hardware-tested")
