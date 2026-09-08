"""Compile real device trees; verify opt-in DMA routing and ABI source fences.

These are build/contract checks, not kernel execution or IIO transport tests.
"""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "linux"


@pytest.fixture(scope="module", params=["revc", "paired-pilot"])
def tree(request, tmp_path_factory):
    for tool in ("gcc", "dtc", "fdtget"):
        assert shutil.which(tool), f"{tool} is required for device-tree tests"
    source = KERNEL / "arch/arm/boot/dts" / f"zynq-pluto-sdr-{request.param}.dts"
    preprocessed = subprocess.run([
        "gcc", "-E", "-P", "-x", "assembler-with-cpp", "-nostdinc", "-undef", "-D__DTS__",
        "-I", str(KERNEL / "scripts/dtc/include-prefixes"), str(source),
    ], check=True, capture_output=True, timeout=30)
    path = tmp_path_factory.mktemp("pilot-device-tree") / "tree.dtb"
    subprocess.run(["dtc", "-q", "-@", "-I", "dts", "-O", "dtb", "-o", str(path)],
                   input=preprocessed.stdout, check=True, capture_output=True, timeout=30)
    return request.param, path


def get(tree, node, key, kind="s"):
    return subprocess.run(["fdtget", "-t", kind, str(tree[1]), node, key],
                          check=True, capture_output=True, text=True, timeout=10).stdout.strip()


def symbol(tree, name):
    return get(tree, "/__symbols__", name)


def test_only_paired_tree_enables_the_correct_dma_interface(tree):
    paired = tree[0] == "paired-pilot"
    dma = symbol(tree, "rx_dma")
    assert get(tree, dma, "status") == ("okay" if paired else "disabled")
    channel = dma + "/adi,channels/dma-channel@0"
    assert get(tree, channel, "adi,source-bus-type", "i") == ("1" if paired else "2")
    assert get(tree, channel, "adi,source-bus-width", "i") == ("32" if paired else "64")
    assert get(tree, channel, "adi,destination-bus-width", "i") == "64"


def test_tx_and_raw_adc_capture_remain_disabled(tree):
    assert get(tree, symbol(tree, "tx_dma"), "status") == "disabled"
    assert get(tree, symbol(tree, "cf_ad9364_dac_core_0"), "status") == "disabled"
    result = subprocess.run(["fdtget", str(tree[1]), symbol(tree, "cf_ad9364_adc_core_0"),
                             "dmas"], capture_output=True, text=True, timeout=10)
    assert result.returncode != 0 and "FDT_ERR_NOTFOUND" in result.stderr


def test_pilot_binding_uses_rx_clock_and_its_own_dma(tree):
    if tree[0] == "revc":
        result = subprocess.run(["fdtget", str(tree[1]), "/__symbols__", "starlink_pilot"],
                                capture_output=True, text=True, timeout=10)
        assert result.returncode != 0 and "FDT_ERR_NOTFOUND" in result.stderr
        return
    pilot = symbol(tree, "starlink_pilot")
    assert get(tree, pilot, "compatible") == "adi,starlink-pilot-capture-1.00.a"
    assert get(tree, pilot, "reg", "x") == "79050000 1000"
    assert get(tree, pilot, "interrupts", "i") == "0 55 4"
    dma = get(tree, symbol(tree, "rx_dma"), "phandle", "x")
    phy = get(tree, symbol(tree, "adc0_ad9364"), "phandle", "x")
    assert get(tree, pilot, "dmas", "x") == f"{dma} 0"
    assert get(tree, pilot, "clocks", "x") == f"{phy} 8"


def test_driver_uses_capture_direction_and_refuses_unattested_geometry():
    driver = (KERNEL / "drivers/iio/adc/adi_starlink_pilot.c").read_text()
    assert "iio_dmaengine_buffer_submit_block(queue, block, DMA_DEV_TO_MEM)" in driver
    assert "DMA_MEM_TO_DEV" not in driver
    assert "clk_get_rate(st->source_clk) != st->source_rate" in driver
    assert "*indio->buffer->channel_mask != (BIT(0) | BIT(1))" in driver
    assert "!st->dma_submitted" in driver and "READ_ONCE(st->dma_error)" in driver
    assert "st->recovery_failed = true" in driver
    assert "PIL_ID) != 0x50494c31" in driver and "PIL_VERSION) != 0x00010000" in driver


def test_paired_profile_preserves_pss_and_omits_raw_dma():
    bd = (ROOT / "hdl/projects/pluto/system_bd.tcl").read_text()
    assert "$starlink_pss_profile in {full detector-only paired-pilot}" in bd
    assert "$starlink_pss_profile ni {detector-only paired-pilot}" in bd
    assert "CONFIG.ENABLE_PILOT_TAP $starlink_pilot_enabled" in bd
    assert "starlink_pilot_capture/m_axis starlink_pilot_dma/s_axis" in bd
    assert "CONFIG.DAC_DATAPATH_DISABLE 1" in bd
