"""Compile board trees and check the dedicated GLRT PHY and DMA contract."""
from pathlib import Path
import shutil
import subprocess

import pytest


KERNEL = Path(__file__).resolve().parents[2] / "linux"


@pytest.fixture(scope="module", params=["revc", "glrt"])
def tree(request, tmp_path_factory):
    for tool in ("gcc", "dtc", "fdtget"):
        assert shutil.which(tool), f"{tool} is required for compiled device-tree checks"
    source = KERNEL / "arch/arm/boot/dts" / f"zynq-pluto-sdr-{request.param}.dts"
    preprocessed = subprocess.run([
        "gcc", "-E", "-P", "-x", "assembler-with-cpp", "-nostdinc", "-undef", "-D__DTS__",
        "-I", str(KERNEL / "scripts/dtc/include-prefixes"), str(source),
    ], check=True, capture_output=True, timeout=30)
    directory = tmp_path_factory.mktemp(f"glrt-device-tree-{request.param}")
    (directory / "preprocessed.dts").write_bytes(preprocessed.stdout)
    path = directory / "tree.dtb"
    subprocess.run(["dtc", "-q", "-@", "-I", "dts", "-O", "dtb", "-o", str(path)],
                   input=preprocessed.stdout, check=True, capture_output=True, timeout=30)
    return request.param, path


def get(tree, node, key, kind="s"):
    return subprocess.run(["fdtget", "-t", kind, str(tree[1]), node, key],
                          check=True, capture_output=True, text=True, timeout=10).stdout.strip()


def symbol(tree, name):
    return get(tree, "/__symbols__", name)


def absent(tree, node, key):
    result = subprocess.run(["fdtget", str(tree[1]), node, key],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0 and "FDT_ERR_NOTFOUND" in result.stderr


def test_phy_capability_is_explicit_only_in_dedicated_image(tree):
    expected = "adi,ad9361" if tree[0] == "glrt" else "adi,ad9363a"
    assert get(tree, symbol(tree, "adc0_ad9364"), "compatible") == expected
    assert get(tree, "/", "model") == "Analog Devices PlutoSDR Rev.C (Z7010/AD9363)"
    absent(tree, symbol(tree, "adc0_ad9364"), "adi,2rx-2tx-mode-enable")
    assert get(tree, symbol(tree, "adc0_ad9364"), "adi,digital-interface-tune-skip-mode", "i") == "1"


def test_no_raw_adc_or_tx_dma_is_enabled_by_phy_capability(tree):
    absent(tree, symbol(tree, "cf_ad9364_adc_core_0"), "dmas")
    assert get(tree, symbol(tree, "tx_dma"), "status") == "disabled"
    assert get(tree, symbol(tree, "cf_ad9364_dac_core_0"), "status") == "disabled"


def test_glrt_image_keeps_its_stream_and_removes_pss(tree):
    if tree[0] == "revc":
        absent(tree, "/__symbols__", "starlink_glrt")
        assert get(tree, symbol(tree, "rx_dma"), "status") == "disabled"
        return
    get(tree, "/", "misko,glrt-fpga")
    for name in ("starlink_pss_track", "starlink_pss_map"):
        absent(tree, "/__symbols__", name)
    glrt = symbol(tree, "starlink_glrt")
    assert get(tree, glrt, "compatible") == "adi,starlink-glrt-1.00.a"
    assert get(tree, glrt, "reg", "x") == "79050000 1000"
    dma = symbol(tree, "rx_dma")
    assert get(tree, dma, "status") == "okay"
    assert get(tree, glrt, "dmas", "x") == f"{get(tree, dma, 'phandle', 'x')} 0"
    phy = symbol(tree, "adc0_ad9364")
    assert get(tree, glrt, "clocks", "x") == f"{get(tree, phy, 'phandle', 'x')} 8"
    channel = dma + "/adi,channels/dma-channel@0"
    assert get(tree, channel, "adi,source-bus-type", "i") == "1"
    assert get(tree, channel, "adi,source-bus-width", "i") == "32"
