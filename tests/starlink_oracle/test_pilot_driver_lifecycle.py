"""Execute actual PIL1 driver functions against bounded MMIO/DMA mocks.

The extraction includes the real state declaration, lifecycle/control code, and
DMAengine submit helper (including cap/alignment truncation); the harness models
kernel locks, poll progress, DMA controller submission and MMIO. This is
not kernel/IRQ execution, DMA hardware completion, or a device-to-host test.
"""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def test_frozen_pilot_dma_geometry_matches_the_local_backend():
    """Fail if the fixed ABI cap/alignment requires a new backend review."""
    design = (ROOT / "hdl/projects/pluto/system_bd.tcl").read_text()
    dma = (ROOT / "linux/drivers/dma/dma-axi-dmac.c").read_text()
    allocation = (ROOT / "linux/drivers/iio/buffer/industrialio-buffer-dma.c").read_text()
    assert "ad_ip_parameter starlink_pilot_dma CONFIG.DMA_DATA_WIDTH_SRC 32" in design
    assert "ad_ip_parameter starlink_pilot_dma CONFIG.DMA_DATA_WIDTH_DEST 64" in design
    assert "ad_ip_parameter starlink_pilot_dma CONFIG.DMA_LENGTH_WIDTH 24" in design
    assert "dma_set_max_seg_size(&pdev->dev, UINT_MAX);" in dma
    assert "dma_dev->src_addr_widths = BIT(dmac->chan.src_width);" in dma
    assert "dma_dev->dst_addr_widths = BIT(dmac->chan.dest_width);" in dma
    assert "if (chan->max_length != UINT_MAX)\n\t\tchan->max_length++;" in dma
    assert "iio_dma_buffer_max_block_size = SZ_16M;" in allocation


def _function(source, name):
    match = re.search(r"(?:static )?(?:int|u32|void) " + name + r"\(", source)
    assert match, f"missing actual pilot driver function {name}"
    start = source.index("{", match.start())
    depth, end = 1, start + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


def test_actual_pilot_driver_geometry_and_lifecycle(tmp_path):
    driver = (ROOT / "linux/drivers/iio/adc/adi_starlink_pilot.c").read_text()
    defines = "\n".join(line for line in driver.splitlines()
                        if re.match(r"#define PIL_[A-Z0-9_]+\s", line))
    state = re.search(r"struct pilot_state \{.*?\n\};", driver, re.DOTALL)
    assert state, "missing actual pilot driver state"
    functions = "\n".join(_function(driver, name) for name in (
        "pilot_read", "pilot_write", "pilot_snapshot", "pilot_buffer_geometry",
        "pilot_submit", "pilot_preenable", "pilot_stop_and_drain",
        "pilot_postenable", "pilot_predisable",
    ))
    (tmp_path / "pilot_driver_actual.inc").write_text(
        defines + "\n" + state.group(0) + "\n" + functions + "\n")
    dmaengine = (ROOT / "linux/drivers/iio/buffer/industrialio-buffer-dmaengine.c").read_text()
    (tmp_path / "pilot_dmaengine_actual.inc").write_text(
        _function(dmaengine, "iio_dmaengine_buffer_submit_block") + "\n")
    executable = tmp_path / "lifecycle"
    subprocess.run([
        "gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-O2",
        "-fsanitize=undefined", "-fno-sanitize-recover=all", "-I", str(tmp_path),
        str(Path(__file__).with_name("pilot_driver_harness.c")),
        "-o", str(executable),
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run([str(executable)], check=True,
                            capture_output=True, text=True, timeout=30)
    assert "PILOT_DRIVER_LIFECYCLE_PASS geometry_cases=33030 " in result.stdout
    assert "helper_cap_alignment=8" in result.stdout
    assert "snapshots=4 mock_only=1 no_dma_completion_claim=1" in result.stdout
