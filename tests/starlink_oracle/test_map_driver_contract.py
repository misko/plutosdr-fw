"""Execute the real kernel contract/health functions with a modeled MMIO bank.

This tests extracted C logic, not kernel IRQ/IIO execution or radio hardware.
The separately cross-compiled module establishes target compilation only.
"""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def _function(source, name):
    match = re.search(r"static (?:int|bool) " + name + r"\(", source)
    assert match, f"missing actual driver function {name}"
    start = source.index("{", match.start())
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


def test_actual_map_driver_contract_and_health_functions(tmp_path):
    driver = (ROOT / "linux/drivers/iio/adc/adi_starlink_pss_map.c").read_text()
    defines = "\n".join(line for line in driver.splitlines()
                        if re.match(r"#define MAP_[A-Z0-9_]+\s", line))
    preamble = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
struct adi_starlink_pss_map { u32 version, input_rate_msps, mmio[64]; };
struct map_snapshot { u32 fault_signature[14]; };
static u32 map_read(struct adi_starlink_pss_map *st, unsigned int address)
{ assert(address % 4 == 0 && address < sizeof(st->mmio)); return st->mmio[address / 4]; }
"""
    functions = "\n".join(_function(driver, name) for name in
                            ("map_require_contract", "map_snapshot_fault_free"))
    harness = (Path(__file__).parent / "map_contract_harness.c").read_text()
    source = tmp_path / "contract.c"
    source.write_text(preamble + defines + "\n" + functions + "\n" + harness)
    executable = tmp_path / "contract"
    subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
                    str(source), "-o", str(executable)], check=True,
                   capture_output=True, text=True, timeout=30)
    result = subprocess.run([str(executable)], check=True,
                            capture_output=True, text=True, timeout=30)
    assert "MAP_DRIVER_CONTRACT_HEALTH_PASS versions=5 " in result.stdout
