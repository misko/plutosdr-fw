"""Execute actual native stop/IRQ C against MMIO and kfifo mocks, not hardware."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _function(source, name):
    match = re.search(r"static (?:int|bool|u32|void|ssize_t|irqreturn_t|unsigned int) "
                      + name + r"\(", source)
    assert match, name
    start = source.index("{", match.start())
    depth, end = 1, start + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


def test_actual_stop_request_receipt_and_irq_drain(tmp_path):
    driver = (ROOT / "linux/drivers/iio/adc/adi_starlink_pss_map.c").read_text()
    defines = "\n".join(line for line in driver.splitlines()
                        if re.match(r"#define MAP_[A-Z0-9_]+\s", line))
    structures = []
    for name in ("map_snapshot", "map_scan", "adi_starlink_pss_map"):
        match = re.search(r"struct " + name + r" \{.*?\n\};", driver, re.DOTALL)
        assert match, name
        structures.append(match.group(0))
    functions = "\n".join(_function(driver, name) for name in (
        "map_read", "map_write", "map_stop_on_fault", "map_take_snapshot",
        "map_snapshot_fault_free", "map_require_stop", "map_read_stop_word",
        "map_take_stop", "map_acquisition_stop_show", "map_stop_command_error",
        "map_request_stop", "map_acquisition_stop_request_store",
        "map_choose_bank", "map_copy_locked", "map_push_chunks_locked",
        "map_release_locked", "map_irq_thread",
    ))
    (tmp_path / "map_stop_actual.inc").write_text(
        defines + "\n" + "\n".join(structures) + "\n" + functions + "\n")
    executable = tmp_path / "stop"
    subprocess.run([
        "gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
        "-Wno-unused-parameter", "-O2", "-fsanitize=undefined",
        "-fno-sanitize-recover=all", "-I", str(tmp_path),
        str(Path(__file__).with_name("map_stop_harness.c")), "-o", str(executable),
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run([str(executable)], check=False,
                            capture_output=True, text=True, timeout=30)
    (tmp_path / "map-stop-driver.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MAP_STOP_DRIVER_PASS exact_chunks=400 retained_irq=1 " in result.stdout
    assert "mock_only=1 no_kernel_or_radio_claim=1" in result.stdout
    receipt = next(line for line in result.stdout.splitlines() if line.startswith("PSST "))
    assert re.fullmatch(r"PSST 1 12(?: [0-9a-f]{8}){12}", receipt)


def test_stop_attributes_are_separate_typed_operations():
    driver = (ROOT / "linux/drivers/iio/adc/adi_starlink_pss_map.c").read_text()
    assert "IIO_DEVICE_ATTR(acquisition_stop, 0444, map_acquisition_stop_show," in driver
    assert "IIO_DEVICE_ATTR(acquisition_stop_request, 0200, NULL," in driver
    assert "&iio_dev_attr_acquisition_stop.dev_attr.attr," in driver
    assert "&iio_dev_attr_acquisition_stop_request.dev_attr.attr," in driver
    assert "kstrtou32(buf, 0, &ticket)" in _function(driver, "map_acquisition_stop_request_store")
