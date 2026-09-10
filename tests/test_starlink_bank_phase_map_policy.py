"""Bank-to-map admission and receipt checks; actual-core logs prove arithmetic."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
RUNNER = ACQ / "simulate_iq_to_phase_map_xfft.tcl"
VECTORS = (
    "samples_ci16", "forward_q17", "product_q17", "inverse_q17",
    "forward_exponents", "inverse_exponents", "scores_u8",
)


def tcl(script):
    return subprocess.run(
        ["tclsh"], input=script, text=True, capture_output=True, timeout=10, check=False
    )


def probe(arguments):
    script = 'proc version {args} {return "2022.2"}\n'
    script += 'proc create_project {args} {error "ADMITTED"}\n'
    script += "set argv [list " + " ".join(f"{{{arg}}}" for arg in arguments) + "]\n"
    script += "set argc [llength $argv]\n"
    script += f"if {{[catch {{source {{{RUNNER}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return tcl(script)


@pytest.mark.parametrize("clock", [175, 200])
def test_bank_admission_freezes_real_composition_before_project(tmp_path, clock):
    output, vectors = tmp_path / "new evidence", tmp_path / "vectors"
    vectors.mkdir()
    for name in VECTORS:
        (vectors / f"{name}.mem").write_text("00\n")
    result = probe([output, vectors, 1, 1, 1, clock])
    assert result.returncode == 2 and "ADMITTED" in result.stderr
    for name in (
        "starlink_pss_iq_to_score_bank_owned.v", "starlink_pss_fft_bank_owned_slice.v",
        "starlink_pss_iq_to_phase_map.v", "starlink_pss_phase_map.v",
        "starlink_pss_acquisition_health.v", "starlink_pss_realtime_result_guard.v",
    ):
        assert (output / "frozen_sources" / name).read_bytes() == (ACQ / name).read_bytes()
    assert (output / "frozen_sources/probe_runner.tcl").read_bytes() == RUNNER.read_bytes()


@pytest.mark.parametrize("selectors", [
    [0, 0, 1, 175], [1, 0, 1, 175], [0, 1, 1, 175], [1, 1, 0, 175],
    [1, 1, 1, 150], [1, 1, 1, "175.0"], [1, 1, 2, 200], [1, 1, 1, 200, 0],
])
def test_invalid_bank_or_clock_never_allocates(tmp_path, selectors):
    output = tmp_path / "new evidence"
    result = probe([output, tmp_path / "missing", *selectors])
    assert result.returncode == 2 and "ADMITTED" not in result.stderr
    assert not output.exists()


def test_bank_does_not_overwrite_existing_evidence(tmp_path):
    retained = tmp_path / "keep"
    retained.write_text("untouched")
    result = probe([tmp_path, tmp_path / "missing", 1, 1, 1, 175])
    assert "refusing to overwrite" in result.stderr
    assert retained.read_text() == "untouched"


@pytest.mark.parametrize("mutation", ["none", "missing_bank", "wrong_clock", "fail", "fatal"])
def test_exact_postprocessor_requires_bank_receipt_and_rejects_late_failure(tmp_path, mutation):
    # Execute the real runner's post-simulation contract, not a mirrored parser.
    source = RUNNER.read_text()
    contract = source.split("close_sim\n", 1)[1].split("close_project", 1)[0]
    log = tmp_path / "test.sim/sim_1/behav/xsim/simulate.log"
    log.parent.mkdir(parents=True)
    lines = [
        "IQ_TO_PHASE_MAP_XFFT_PASS samples=1406 scores=1341",
        "SHARED_PHASE_MAP_FAULT_PASS partial_tile_aborted=1 no_partial_publication=1 service_health_bit=14 detector_episodes=1",
        "REALTIME_PHASE_MAP_PASS exact_scores=1341 exact_map_reads=447 reduced_geometry_only=1 CAPACITY_AND_PHYSICAL_UNQUALIFIED",
        "REALTIME_PHASE_MAP_FAULT_PASS partial_tile_aborted=1 service_health_bit=14",
        "BANK_PHASE_MAP_PASS exact_scores=1341 exact_map_reads=447 partial_fault_abort=1 service_health_bit=14 fast_mhz=175 REDUCED_GEOMETRY_NOT_RECEIVER",
    ]
    if mutation == "missing_bank":
        lines.pop()
    if mutation == "wrong_clock":
        lines[-1] = lines[-1].replace("fast_mhz=175", "fast_mhz=200")
    if mutation == "fail":
        lines.append("IQ_TO_PHASE_MAP_XFFT_FAIL late assertion")
    if mutation == "fatal":
        lines.append("Fatal: simulator failure")
    log.write_text("\n".join(lines) + "\n")
    script = f"source {{{ACQ / 'verify_realtime_probe_result.tcl'}}}\n"
    script += f"set project_dir {{{tmp_path}}}\nset project_name test\n"
    script += "set use_shared_xfft 1\nset use_realtime_xfft 1\nset use_bank_owned_xfft 1\nset fast_mhz 175\n"
    script += f"if {{[catch {{{contract}}} message]}} {{puts stderr $message; exit 2}}\n"
    result = tcl(script)
    assert (result.returncode == 0) == (mutation == "none"), result.stderr


def test_receiver_defaults_and_map_arithmetic_unchanged():
    phase = (ACQ / "starlink_pss_iq_to_phase_map.v").read_text()
    assert "parameter integer USE_BANK_OWNED_XFFT = 0" in phase
    assert "end else if (USE_SHARED_XFFT) begin : shared_transform" in phase
    # The new selector is deliberately not forwarded by the receiver wrapper.
    wrapper = (ROOT / "hdl/library/axi_starlink_pss_acquisition/axi_starlink_pss_acquisition.v").read_text()
    assert "USE_BANK_OWNED_XFFT" not in wrapper
