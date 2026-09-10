"""Explicit 4096 admission and inventory tests, not a simulated soak result."""

import pytest

from .test_starlink_bank_owned_runner_policy import ACQ, RUNNER, invoke, tcl


@pytest.mark.parametrize("blocks", ["0", "65", "4095", "4097", "4096.0", " 4096", "-1"])
def test_other_capacity_inventories_rejected_before_allocation(tmp_path, blocks):
    output = tmp_path / "invalid"
    result = invoke([output, "capacity", "bursty-stalled", "175", blocks])
    assert "supports only 64 or 4096" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("blocks", [64, 4096])
def test_explicit_capacity_admission_retains_bounded_bench(tmp_path, blocks):
    output = tmp_path / "admitted"
    result = invoke([output, "capacity", "bursty-stalled", "175", blocks])
    assert "ADMITTED" in result.stderr
    bench = (output / "tb_starlink_pss_iq_to_score_xfft_longrun.sv").read_text()
    assert "localparam integer BLOCK_COUNT = CAPACITY_BLOCKS;" in bench
    assert "CAPACITY_BLOCKS != 64 && CAPACITY_BLOCKS != 4096" in bench
    assert "cycle_count > BLOCK_COUNT * 4000 + 100000" in bench
    assert "BANK_IQ_CAPACITY_COMPLETE blocks=64 samples=28673 scores=28608" in bench
    assert (
        "BANK_IQ_CAPACITY_COMPLETE blocks=4096 samples=1830977 scores=1830912" in bench
    )


def test_numeric_mode_cannot_be_repurposed_as_soak(tmp_path):
    output = tmp_path / "invalid"
    result = invoke([output, "numeric", tmp_path / "vectors", "175", 4096])
    assert "numeric mode has no capacity block override" in result.stderr
    assert not output.exists()


def test_4096_generic_reaches_actual_simulator_configuration():
    source = RUNNER.read_text()
    start = source.index("set generics [list FAST_MHZ=$fast_mhz]")
    stop = source.index("set_property top", start)
    result = tcl(
        "set fast_mhz 175\nset mode capacity\nset profile bursty-stalled\nset capacity_blocks 4096\n"
        + source[start:stop]
        + "\nputs $generics\n"
    )
    assert result.returncode == 0
    assert (
        result.stdout.strip()
        == "FAST_MHZ=175 CAPACITY_BLOCKS=4096 SOURCE_BURST_MODE=1 SCORE_STALL_MODE=1"
    )


@pytest.mark.parametrize(
    "observed,failed", [(4096, False), (64, True), (4095, True), (4097, True)]
)
def test_actual_tcl_postprocessor_demands_requested_progress_inventory(
    tmp_path, observed, failed
):
    source = RUNNER.read_text()
    start = source.index("set channel [open $logfile r];")
    stop = source.index("\nclose_project", start)
    transcript = (
        "BANK_IQ_CAPACITY_COMPLETE blocks=4096 samples=1830977 scores=1830912\n"
        "IQ_TO_SCORE_XFFT_LONGRUN_PASS blocks=4096\n"
        "IQ_TO_SCORE_XFFT_BACKLOG_PASS blocks=4096\n"
        "BANK_IQ_CAPACITY_METADATA_PASS blocks=4096\n"
        + "".join(
            f"IQ_TO_SCORE_XFFT_LONGRUN_PROGRESS block={n}\n"
            for n in range(1, observed + 1)
        )
    )
    logfile = tmp_path / "simulate.log"
    logfile.write_text(transcript)
    result = tcl(
        f"source {{{ACQ / 'verify_realtime_probe_result.tcl'}}}\n"
        f"set logfile {{{logfile}}}\nset mode capacity\nset capacity_blocks 4096\n"
        "if {[catch {\n"
        + source[start:stop]
        + "\n} message]} {puts stderr $message; exit 2}\n"
    )
    assert result.returncode == (2 if failed else 0)
