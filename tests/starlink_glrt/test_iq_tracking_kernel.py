"""Compile the actual driver probe's register identity checks against a port."""
import ctypes as C
from pathlib import Path
import re
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    root = tmp_path_factory.mktemp("gli1-kernel")
    source = (ROOT/"linux/drivers/iio/adc/adi_starlink_glrt.c").read_text()
    checks = source[source.index("\tidentity = glrt_read(st, GLR_ID);"):source.index(
        '\tst->source_clk = devm_clk_get(&pdev->dev, "rx_sample");')]
    definitions = "\n".join(re.findall(r"^#define .*", source[:source.index("struct glrt_state")], re.M))
    wrapper = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <errno.h>
#include <string.h>
typedef uint32_t u32; typedef uint64_t u64; typedef int32_t s32; typedef int64_t s64;
#define BIT(n) (1U<<(n))
#include "adi_starlink_glrt_tracking.h"
#include "adi_starlink_glrt_local.h"
struct glrt_state {
    const u32 *regs;
    bool lean_profile, local_profile, iq_tracking_profile, has_extension;
    bool has_native, has_schedule, has_tracking;
    u32 source_rate;
    struct gls_capture schedule;
};
static u32 glrt_read(struct glrt_state *st, unsigned offset) { return st->regs[offset/4]; }
static u32 read_port(void *context, unsigned offset) { return glrt_read(context, offset); }
int probe(const u32 *registers) {
    struct glrt_state state={.regs=registers}, *st=&state;
    struct gln_port native_port={.read=read_port, .context=st};
    u32 identity, delay;
CHECKS
    return 0;
}
'''
    (root/"wrapper.c").write_text(definitions+"\n"+wrapper.replace("CHECKS", checks))
    built = subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                    "-I", str(ROOT/"linux/drivers/iio/adc"), str(root/"wrapper.c"),
                    "-o", str(root/"checks.so")], capture_output=True, text=True)
    assert built.returncode == 0, built.stdout+built.stderr
    lib = C.CDLL(str(root/"checks.so"))
    lib.probe.argtypes = [C.POINTER(C.c_uint32)]
    return lib.probe


def registers(rate):
    w = (C.c_uint32*1024)()
    for address, value in {
        0:0x474c4931, 4:0x10000, 0x14:rate, 0x18:2500000, 0x1c:rate//2500000,
        0x24:1, 0x28:636*(rate//30000000), 0x2c:1272*(rate//30000000),
        0x5c:0x474c4931, 0x60:0x10000, 0x64:16, 0x68:17,
        0x800:0x474c5431, 0x804:0x10000, 0x880:rate*33//25000,
        0x884:rate, 0x888:64, 0x88c:0xb04a2fab, 0x890:1, 0x894:1, 0x898:24,
    }.items(): w[address//4] = value
    return w


@pytest.mark.parametrize("rate", [30000000, 60000000])
@pytest.mark.parametrize("damage", [None, 0, 4, 0x14, 0x18, 0x1c, 0x24, 0x28, 0x2c,
                                     0x5c, 0x60, 0x64, 0x68, 0x800, 0x804, 0x880,
                                     0x884, 0x888, 0x88c, 0x890, 0x894, 0x898, 0xc00])
def test_kernel_accepts_only_exact_iq_tracking_geometry(probe, rate, damage):
    w = registers(rate)
    if damage is not None: w[damage//4] ^= 1
    assert (probe(w) == 0) == (damage is None)


@pytest.mark.parametrize("identity", [0x474c4131, 0x474c4631, 0x474c5231])
def test_new_profile_cannot_masquerade_as_published_acquisition_profiles(probe, identity):
    w = registers(60000000)
    w[0] = w[0x5c//4] = identity
    assert probe(w) != 0
