"""Execute real PSMA receipt/snapshot code, plus the real RTL register mapping.

The C harness models MMIO, poll progress, IRQ/IIO dependencies and a mutex; it
does not execute a kernel or transfer RF/maps. The RTL test exercises the
actual frozen/live register sources independently of that MMIO model.
"""
from pathlib import Path
import re
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _function(source, name):
    match = re.search(r"static (?:int|bool|u32|void|ssize_t|irqreturn_t|unsigned int) "
                      + name + r"\(", source)
    assert match, f"missing actual driver function {name}"
    start = source.index("{", match.start())
    depth, end = 1, start + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


def test_actual_map_health_receipt_and_late_fault(tmp_path):
    driver = (ROOT / "linux/drivers/iio/adc/adi_starlink_pss_map.c").read_text()
    defines = "\n".join(line for line in driver.splitlines()
                        if re.match(r"#define MAP_[A-Z0-9_]+\s", line))
    structures = []
    for name in ("map_snapshot", "adi_starlink_pss_map"):
        match = re.search(r"struct " + name + r" \{.*?\n\};", driver, re.DOTALL)
        assert match, f"missing actual driver structure {name}"
        structures.append(match.group(0))
    functions = "\n".join(_function(driver, name) for name in (
        "map_read", "map_write", "map_take_snapshot", "map_read_live_ddc64",
        "map_take_health", "map_acquisition_health_show", "map_snapshot_fault_free",
        "map_choose_bank", "map_irq_thread",
    ))
    (tmp_path / "map_health_actual.inc").write_text(
        defines + "\n" + "\n".join(structures) + "\n" + functions + "\n")
    executable = tmp_path / "health"
    subprocess.run([
        "gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
        "-Wno-unused-parameter", "-O2", "-fsanitize=undefined",
        "-fno-sanitize-recover=all", "-I", str(tmp_path),
        str(Path(__file__).with_name("map_health_harness.c")),
        "-o", str(executable),
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run([str(executable)], check=True,
                            capture_output=True, text=True, timeout=30)
    assert "MAP_HEALTH_RECEIPT_PASS versions=5 fault_receipts=70 " in result.stdout
    assert "mock_only=1 no_kernel_or_radio_claim=1" in result.stdout
    receipt = next(line for line in result.stdout.splitlines()
                   if line.startswith("PSMH "))
    assert re.fullmatch(r"PSMH 1 46(?: [0-9a-f]{8}){46}", receipt)
    # A stable fixture emitted by actual C, suitable for an independent parser.
    assert receipt.split()[3:6] == ["00010005", "0000000f", "00000008"]


@pytest.mark.parametrize("rate,shared", [(15, 0), (15, 1), (30, 0), (60, 0)])
def test_actual_rtl_health_snapshot_vs_live_ddc(tmp_path, rate, shared):
    executable = tmp_path / "mapping.vvp"
    subprocess.run([
        "iverilog", "-g2012", "-s", "map_health_mapping_harness",
        f"-Pmap_health_mapping_harness.INPUT_RATE_MSPS={rate}",
        f"-Pmap_health_mapping_harness.USE_SHARED_XFFT={shared}",
        "-o", str(executable),
        str(Path(__file__).with_name("map_health_mapping_harness.sv")),
        str(ROOT / "hdl/library/axi_starlink_pss_acquisition/axi_starlink_pss_phase_map_sync.v"),
        str(ROOT / "hdl/library/axi_starlink_pss_phase_map/starlink_pss_axi_lite.v"),
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run(["vvp", str(executable)], check=True,
                            capture_output=True, text=True, timeout=30)
    assert f"MAP_HEALTH_MAPPING_PASS rate={rate} shared={shared}" in result.stdout


def test_acquisition_health_is_additive_read_only_iio_attribute():
    driver = (ROOT / "linux/drivers/iio/adc/adi_starlink_pss_map.c").read_text()
    assert "IIO_DEVICE_ATTR(acquisition_health, 0444, map_acquisition_health_show," in driver
    assert "&iio_dev_attr_acquisition_health.dev_attr.attr," in driver
