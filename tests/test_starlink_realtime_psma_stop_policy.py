"""Executable stop-runner admission checks, not a replacement for real XFFT."""

import hashlib
import subprocess
from pathlib import Path

import pytest

ACQ = Path(__file__).resolve().parents[1] / "hdl/library/starlink_pss_acquisition"
RUNNER = ACQ / "simulate_realtime_psma_stop.tcl"
BENCH = ACQ / "tb/tb_starlink_pss_realtime_psma_stop.sv"
GEOMETRY = {
    "samples_ci16": (1406, 8), "forward_q17": (1536, 9),
    "product_q17": (1536, 9), "inverse_q17": (1536, 9),
    "forward_exponents": (3, 2), "inverse_exponents": (3, 2),
    "scores_u8": (1341, 2),
}


def probe(arguments, version="2022.2"):
    script = "proc version {args} {return {" + version + "}}\n"
    script += 'proc create_project {args} {error "ADMITTED"}\n'
    script += "set argv [list " + " ".join(f"{{{arg}}}" for arg in arguments) + "]\n"
    script += "set argc [llength $argv]\n"
    script += f"if {{[catch {{source {{{RUNNER}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return subprocess.run(["tclsh"], input=script, capture_output=True,
                          check=False, text=True, timeout=10)


def vectors_at(path, *, omit=None):
    path.mkdir()
    for name, (rows, width) in GEOMETRY.items():
        if name != omit:
            (path / f"{name}.mem").write_text(("0" * width + "\n") * rows)


@pytest.mark.parametrize("count", [0, 1, 3])
def test_wrong_arity_is_nonmutating(tmp_path, count):
    output = tmp_path / "new evidence"
    result = probe([output, tmp_path / "vectors", "extra"][:count])
    assert result.returncode == 2 and "expected NEW_OUTPUT" in result.stderr
    assert not output.exists()


def test_wrong_tool_is_nonmutating(tmp_path):
    output = tmp_path / "new evidence"
    result = probe([output, tmp_path / "vectors"], version="2023.1")
    assert result.returncode == 2 and "requires Vivado 2022.2" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_preserves_existing_evidence(tmp_path, kind):
    output = tmp_path / "evidence"
    if kind == "file":
        retained = output
    else:
        destination = tmp_path / "destination" if kind == "symlink" else output
        destination.mkdir()
        retained = destination / "retained.txt"
        if kind == "symlink":
            output.symlink_to(destination, target_is_directory=True)
    retained.write_text("retained")
    result = probe([output, tmp_path / "vectors"])
    assert result.returncode == 2 and "refusing to overwrite" in result.stderr
    assert retained.read_text() == "retained"


@pytest.mark.parametrize("name", GEOMETRY)
def test_missing_vectors_rejected_before_output(tmp_path, name):
    output, vectors = tmp_path / "new evidence", tmp_path / "vectors"
    vectors_at(vectors, omit=name)
    result = probe([output, vectors])
    assert result.returncode == 2 and f"missing vector {name}" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("name", GEOMETRY)
@pytest.mark.parametrize("bad", ["empty", "short", "long", "nonhex", "wrongwidth"])
def test_vector_geometry_is_bounded_before_allocation(tmp_path, name, bad):
    output, vectors = tmp_path / "new evidence", tmp_path / "vectors"
    vectors_at(vectors)
    rows, width = GEOMETRY[name]
    data = ["0" * width] * rows
    if bad == "empty":
        data = []
    elif bad == "short":
        data.pop()
    elif bad == "long":
        data.append(data[-1])
    elif bad == "nonhex":
        data[rows // 2] = "g" * width
    else:
        data[rows // 2] += "0"
    (vectors / f"{name}.mem").write_text("\n".join(data) + "\n")
    result = probe([output, vectors])
    assert result.returncode == 2 and "vector row" in result.stderr
    assert not output.exists()


def test_exact_sources_and_all_vectors_frozen_before_project_creation(tmp_path):
    output, vectors = tmp_path / "new evidence", tmp_path / "vectors"
    vectors_at(vectors)
    protected = [ACQ / "starlink_pss_iq_to_phase_map.v", ACQ / "starlink_pss_shared_realtime_xfft_service.v",
                 ACQ.parent / "axi_starlink_pss_acquisition/axi_starlink_pss_phase_map_sync.v"]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
    result = probe([output, vectors])
    assert result.returncode == 2 and "ADMITTED" in result.stderr
    frozen = output / "frozen_sources"
    for path in [*protected, RUNNER, BENCH, ACQ / "create_shared_realtime_xfft_ip.tcl",
                 ACQ / "verify_realtime_probe_result.tcl", ACQ / "starlink_pss_realtime_result_guard.v",
                 ACQ.parent / "axi_starlink_pss_phase_map/starlink_pss_axi_lite.v"]:
        assert (frozen / path.name).read_bytes() == path.read_bytes()
    for name in GEOMETRY:
        assert (frozen / f"{name}.mem").read_bytes() == (vectors / f"{name}.mem").read_bytes()
    assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
    scope = (output / "scope.txt").read_text()
    assert "compared_score_prefix=894 exact_map_words=447" in scope
    assert "source_continuation_is_stimulus_not_canonical_tap_or_pilot_dma=true" in scope
    assert "production_geometry_duration_physical_timing_RF_qualified=false" in scope
    assert "frozen_source_hashes=" in scope


def test_terminal_verification_requires_positive_and_both_negative_receipts():
    runner, bench = RUNNER.read_text(), BENCH.read_text()
    assert "pss_create_shared_realtime_xfft_ip $wrapper_path" in runner
    assert "require_realtime_probe_pass" in runner
    assert "] REALTIME_PSMA_STOP_ACK 2" in runner
    for marker in ("REALTIME_PSMA_STOP_HEALTHY_PASS", "REALTIME_PSMA_STOP_LATE_BRIDGE_PASS",
                   "REALTIME_PSMA_STOP_LIVE_FAULT_PASS", "NO_PILOT_DMA_PRODUCTION_CAPACITY_OR_PHYSICAL_CLAIM"):
        assert marker in runner and marker in bench
    assert "third_started && !third_inverse_returned" in bench
    assert "launch_runs" not in runner and "create_clock" not in runner


@pytest.mark.parametrize("clock", [175, 200])
def test_bank_stop_freezes_both_real_bank_modules(tmp_path, clock):
    output, vectors = tmp_path / "new evidence", tmp_path / "vectors"
    vectors_at(vectors)
    result = probe([output, vectors, 1, clock])
    assert result.returncode == 2 and "ADMITTED" in result.stderr
    for name in ("starlink_pss_iq_to_score_bank_owned.v", "starlink_pss_fft_bank_owned_slice.v"):
        assert (output / "frozen_sources" / name).read_bytes() == (ACQ / name).read_bytes()
    scope = (output / "scope.txt").read_text()
    assert f"fast_clock_MHz={clock}" in scope and "use_bank_owned_xfft=1" in scope


@pytest.mark.parametrize("selectors", [[0, 200], [1, 150], [2, 175], ["true", 175],
                                      [1, "175.0"], [1, 175, 0]])
def test_bad_bank_stop_configuration_is_nonmutating(tmp_path, selectors):
    output = tmp_path / "new evidence"
    result = probe([output, tmp_path / "missing", *selectors])
    assert result.returncode == 2 and "ADMITTED" not in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("mutation", ["none", "missing_bank", "wrong_clock", "one_ack", "fail", "fatal"])
def test_bank_stop_exact_postprocessor_rejects_incomplete_or_false_pass(tmp_path, mutation):
    log = tmp_path / "test.sim/sim_1/behav/xsim/simulate.log"
    log.parent.mkdir(parents=True)
    lines = [
        "REALTIME_PSMA_STOP_ACK negative=0",
        "REALTIME_PSMA_STOP_ACK negative=1",
        "REALTIME_PSMA_STOP_HEALTHY_PASS exact_scores=894 exact_map_words=447 actual_third_block_pending=1 source_continues=1 coarse_flush=0 tail_health_clean=1 reduced_geometry_only=1",
        "REALTIME_PSMA_STOP_LATE_BRIDGE_PASS actual_invalid_release=1 stable_terminal_tuple=1 failed_receipt=1",
        "REALTIME_PSMA_STOP_LIVE_FAULT_PASS pending_stop=1 vendor_event_in_live_epoch=1 partial_abort=1 no_partial_publication=1 service_health_bit=14",
        "REALTIME_PSMA_STOP_PASS healthy_maps=1 exact_map_words=447 fault_cases=2 source_mhz=15 slow_mhz=100 fft_mhz=175 NO_PILOT_DMA_PRODUCTION_CAPACITY_OR_PHYSICAL_CLAIM",
        "BANK_PSMA_STOP_PASS actual_core=1 exact_scores=894 exact_map_words=447 fault_cases=2 fast_mhz=175 REDUCED_GEOMETRY_NOT_RECEIVER",
    ]
    if mutation == "missing_bank":
        lines.pop()
    if mutation == "wrong_clock":
        lines[-1] = lines[-1].replace("fast_mhz=175", "fast_mhz=200")
    if mutation == "one_ack":
        lines.pop(1)
    if mutation == "fail":
        lines.append("REALTIME_PSMA_STOP_FAIL late assertion")
    if mutation == "fatal":
        lines.append("Fatal: simulator failure")
    log.write_text("\n".join(lines) + "\n")
    contract = RUNNER.read_text().split("close_sim\n", 1)[1].split("close_project", 1)[0]
    script = f"source {{{ACQ / 'verify_realtime_probe_result.tcl'}}}\n"
    script += f"set project_dir {{{tmp_path}}}\nset project_name test\n"
    script += "set use_bank_owned_xfft 1\nset fast_mhz 175\n"
    script += f"if {{[catch {{{contract}}} message]}} {{puts stderr $message; exit 2}}\n"
    result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True,
                            check=False, timeout=10)
    assert (result.returncode == 0) == (mutation == "none"), result.stderr


def test_bank_third_block_witness_observes_fast_core_not_source_capture():
    bank_observer = BENCH.read_text().split(
        "generate if (USE_BANK_OWNED_XFFT) begin : engine_observer", 1
    )[1].split("end else begin : engine_observer", 1)[0]
    assert "always @(posedge fft_clk)" in bank_observer
    for signal in ("core_input_valid", "core_input_ready", "selected_position", "engine_metadata[68:5]"):
        assert f"island.{signal}" in bank_observer
    assert "source_bank.input_valid" not in bank_observer
