from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_experiment_is_marked_do_not_merge_and_ram_only() -> None:
    stop = _read("STARLINK_RX_ONLY_EXPERIMENT_DO_NOT_MERGE.md")
    plan = _read("STARLINK_PSS_15_30_60_PLAN.md")

    assert "DO NOT MERGE" in stop
    assert "codex/starlink-rx-only-do-not-merge" in stop
    assert "persistently flashed" in stop
    assert "DO NOT MERGE INTO FIRMWARE MAIN" in plan
    assert "RAM-only" in plan

    merge_guard = _read(".github/workflows/starlink-rx-only-do-not-merge.yml")
    assert "github.head_ref == 'codex/starlink-rx-only-do-not-merge'" in merge_guard
    assert "exit 1" in merge_guard


def test_source_graph_and_builder_are_locked_to_the_experiment() -> None:
    modules = _read(".gitmodules")
    manifest = _read("manifests/starlink-rx-only-dnm-v1-source.yaml")
    workflow = _read(".github/workflows/firmware-main.yml")
    builder = _read("scripts/ci/build_main_firmware.sh")

    assert "branch = codex/starlink-rx-only-buildroot-do-not-merge" in modules
    assert modules.count("branch = codex/starlink-rx-only-do-not-merge") == 2
    assert "release_state: candidate" in manifest
    assert manifest.count("refs/tags/starlink-rx-only-dnm-v1-source/") == 3
    assert "codex/starlink-rx-only-do-not-merge" in workflow
    assert "v0.49-plutoplus-starlink-rx-only-dnm-v1" in workflow
    assert "starlink-rx-only-dnm-v1-source.yaml" in builder
    assert "for rate in 15 30 60" in builder
    assert "bash hdl-starlink/run_tests.sh" in builder


def test_rx_only_packaging_requires_the_two_remaining_fifo_crossings() -> None:
    packager = _read("scripts/ci/package_main_firmware.sh")

    assert "REQUIRED_BUS_SKEW_CONSTRAINTS=4" in packager
    assert '== "starlink-rx-only-dnm-v1-source.yaml"' in packager
    assert "REQUIRED_BUS_SKEW_CONSTRAINTS=2" in packager
    assert '-ge "$REQUIRED_BUS_SKEW_CONSTRAINTS"' in packager
    assert "Slack (VIOLATED)" in packager


def test_block_design_is_compile_time_single_rx_without_tx_engines() -> None:
    design = _read("hdl/projects/pluto/system_bd.tcl")

    assert "CONFIG.MODE_1R1T 1" in design
    assert "CONFIG.TDD_DISABLE 1" in design
    assert "CONFIG.DAC_DATAPATH_DISABLE 1" in design
    assert "CONFIG.PCW_USE_S_AXI_HP2 0" in design
    assert design.count("CONFIG.SYNC_TRANSFER_START") == 1
    assert "CONFIG.SYNC_TRANSFER_START {true}" in design

    forbidden = (
        "axi_ad9361_dac_dma",
        "tx_fir_interpolator",
        "tx_upack",
        "axi_tdd_0",
        "i_tandem_agc",
    )
    for name in forbidden:
        assert name not in design


def test_top_level_holds_digital_tx_bus_static() -> None:
    top = _read("hdl/projects/pluto/system_top.v")

    assert "assign tx_clk_out = 1'b0;" in top
    assert "assign tx_frame_out = 1'b0;" in top
    assert "assign tx_data_out = 12'b0;" in top
    assert "assign phaser_enable = 1'b0;" in top
    assert "assign phaser_enable = gpio_o[14];" not in top
    assert ".tx_clk_out (tx_clk_out)" not in top
    assert ".tx_frame_out (tx_frame_out)" not in top
    assert ".tx_data_out (tx_data_out)" not in top
    assert "gpio_o[14]" not in top


def test_linux_matches_removed_hardware_and_single_rx_geometry() -> None:
    common = _read("linux/arch/arm/boot/dts/zynq-pluto-sdr.dtsi")
    revc = _read("linux/arch/arm/boot/dts/zynq-pluto-sdr-revc.dts")

    for node in (
        "tandem-agc@7c450000",
        "dma@7c420000",
        "cf-ad9361-dds-core-lpc@79024000",
    ):
        start = common.index(node)
        assert 'status = "disabled";' in common[start : start + 500]

    assert "digital-interface-tune-skip-mode = <1>" in common
    assert "misko,rx-only-fpga;" in common
    assert "adi,source-bus-width = <64>;" in common
    assert "adi,frequency-division-duplex-mode-enable;" not in common
    assert "adi,2rx-2tx-mode-enable;" not in revc

    phaser = revc.index("one-bit-adc-dac@0")
    assert 'status = "disabled";' in revc[phaser : phaser + 500]

    for node in ("axi-tdd-0@7C440000", "iio_axi_tdd_0@0"):
        start = revc.index(node)
        assert 'status = "disabled";' in revc[start : start + 500]


def test_removed_hdl_libraries_are_not_build_dependencies() -> None:
    makefile = _read("hdl/projects/pluto/Makefile")

    assert "LIB_DEPS += axi_tdd" not in makefile
    assert "LIB_DEPS += util_pack/util_upack2" not in makefile
    assert "library/axi_tdd/scripts/axi_tdd.tcl" not in makefile


def test_boot_guard_requires_rx_only_dt_proof_and_powers_down_tx_lo() -> None:
    guard = _read("buildroot/board/pluto/pluto-mute-tx")

    assert "DT_ROOT=${PLUTO_DT_ROOT:-/sys/firmware/devicetree/base}" in guard
    assert '"$DT_ROOT/misko,rx-only-fpga"' in guard
    assert "cf-ad9361-dds-core-lpc@79024000/status" in guard
    assert '"disabled"' in guard
    assert "out_altvoltage*_TX_LO_powerdown" in guard
    assert "printf '1\\n' > \"$control\"" in guard
