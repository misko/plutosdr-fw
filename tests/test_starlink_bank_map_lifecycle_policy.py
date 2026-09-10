"""Executable stop-runner admission checks, not a replacement for real XFFT."""

import hashlib
import subprocess
from pathlib import Path

import pytest

ACQ = Path(__file__).resolve().parents[1] / "hdl/library/starlink_pss_acquisition"
RUNNER = ACQ / "simulate_bank_map_lifecycle.tcl"
BENCH = ACQ / "tb/tb_starlink_pss_bank_map_lifecycle.sv"
GEOMETRY = {
    "samples_ci16": (1406, 8), "forward_q17": (1536, 9),
    "product_q17": (1536, 9), "inverse_q17": (1536, 9),
    "forward_exponents": (3, 2), "inverse_exponents": (3, 2),
    "scores_u8": (1341, 2),
}


def probe(arguments, version="2022.2"):
    script = "proc version {args} {return {" + version + "}}\n"
    script += 'proc set_param {args} {}\n'
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


@pytest.mark.parametrize("count", [0, 1, 4])
def test_wrong_arity_is_nonmutating(tmp_path, count):
    output = tmp_path / "new evidence"
    result = probe([output, tmp_path / "vectors", "extra", "extra"][:count])
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
    assert "compared_scores=every_visible_prefix complete_map_words=447" in scope
    assert "source_bounded_three_blocks_no_canonical_tap_pilot_dma_or_native_fine=true" in scope
    assert "production_geometry_duration_physical_timing_RF_qualified=false" in scope
    assert "frozen_source_hashes=" in scope



@pytest.mark.parametrize("clock", [175, 200])
def test_actual_bank_sources_frozen_for_admitted_clocks(tmp_path, clock):
    output, vectors = tmp_path / "new evidence", tmp_path / "vectors"
    vectors_at(vectors)
    result = probe([output, vectors, clock])
    assert result.returncode == 2 and "ADMITTED" in result.stderr
    for name in ("starlink_pss_iq_to_score_bank_owned.v", "starlink_pss_fft_bank_owned_slice.v"):
        assert (output / "frozen_sources" / name).read_bytes() == (ACQ / name).read_bytes()
    scope = (output / "scope.txt").read_text()
    assert f"fast_clock_MHz={clock}" in scope and "use_bank_owned_xfft=1" in scope
    assert "local_faults_model_current_domain_visibility_separate_from_remote_raw_event=true" in scope


@pytest.mark.parametrize("clock", [0, 150, 250, "175.0", "true"])
def test_bad_clock_nonmutating(tmp_path, clock):
    output = tmp_path / "new evidence"
    result = probe([output, tmp_path / "missing", clock])
    assert result.returncode == 2 and "requires FAST_MHZ" in result.stderr
    assert not output.exists()


def test_scoped_actual_core_no_arithmetic_or_result_substitution():
    runner, bench = RUNNER.read_text(), BENCH.read_text()
    assert "pss_create_shared_realtime_xfft_ip $wrapper_path" in runner
    assert "set_param general.maxThreads 2" in runner
    assert "launch_runs" not in runner and "create_clock" not in runner
    assert "if (score_valid) begin" in bench
    assert "checked_scores >= FIXTURE_SCORES" in bench
    assert "$fatal(1," in bench and "$fatal(1);" not in bench
    forces = [line.strip() for line in bench.splitlines() if line.strip().startswith("force ")]
    assert forces == [
        "force dut.bank_transform.iq_to_score.island.event_last_missing = 1'b1;",
        "force dut.bank_transform.iq_to_score.detector_fault = 1'b1;",
        "force dut.bank_transform.iq_to_score.island_fault = 1'b1;",
        "force dut.bank_transform.iq_to_score.detector_fault = 1'b1;",
        "force dut.bank_transform.iq_to_score.island_fault = 1'b1;",
    ]
    assert "fault_terminal(final_accepted, final_accepted, 1);" in bench
    assert "hardware_resets != saved_resets" in bench
    assert "fft_resetn = 0;" in bench


@pytest.mark.parametrize("mutation", [
    "none", "missing_case", "duplicate_identity", "wrong_boundary_outcome",
    "wrong_clock", "no_terminal", "duplicate_terminal", "fail", "fatal",
])
def test_postprocessor_exact_case_inventory_and_no_false_pass(tmp_path, mutation):
    log = tmp_path / "test.sim/sim_1/behav/xsim/simulate.log"
    log.parent.mkdir(parents=True)
    lines = [
        "BANK_MAP_LIFECYCLE_CASE healthy_reenable=1 external_reset_between=0 tickets=2 exact_scores=1788 exact_map_words=894",
        "BANK_MAP_LIFECYCLE_CASE retained_map_partial_fault=1 exact_map_words=447 exact_prefix=1006",
        "BANK_MAP_LIFECYCLE_CASE independent_fft_reset=1 slow_epoch_preserved=1 exact_prefix=301",
        "BANK_MAP_LIFECYCLE_CASE post_fault_epoch_reset_replay=1 exact_scores=894 exact_map_words=447",
        "BANK_MAP_LIFECYCLE_CASE local_boundary=0 completed=0 exact_scores=894",
        "BANK_MAP_LIFECYCLE_CASE local_boundary=1 completed=1 exact_scores=894",
        "BANK_MAP_LIFECYCLE_CASE local_boundary=2 completed=1 exact_scores=894",
        "BANK_MAP_LIFECYCLE_CASE remote_boundary=1 completed=1 exact_scores=894",
        "BANK_MAP_LIFECYCLE_PASS cases=8 actual_core=1 source_mhz=15 slow_mhz=100 fft_mhz=175 REDUCED_GEOMETRY_NO_PAIRED_FINE_CAPACITY_OR_RF_CLAIM",
    ]
    if mutation == "missing_case":
        lines.pop(1)
    elif mutation == "duplicate_identity":
        lines[2] = lines[1]
    elif mutation == "wrong_boundary_outcome":
        lines[4] = lines[4].replace("completed=0", "completed=1")
    elif mutation == "wrong_clock":
        lines[-1] = lines[-1].replace("fft_mhz=175", "fft_mhz=200")
    elif mutation == "no_terminal":
        lines.pop()
    elif mutation == "duplicate_terminal":
        lines.append(lines[-1])
    elif mutation == "fail":
        lines.append("BANK_MAP_LIFECYCLE_FAIL late assertion")
    elif mutation == "fatal":
        lines.append("Fatal: simulator failure")
    log.write_text("\n".join(lines) + "\n")
    contract = RUNNER.read_text().split("close_sim\n", 1)[1].split("close_project", 1)[0]
    script = f"source {{{ACQ / 'verify_realtime_probe_result.tcl'}}}\n"
    script += f"set project_dir {{{tmp_path}}}\nset project_name test\nset fast_mhz 175\n"
    script += f"if {{[catch {{{contract}}} message]}} {{puts stderr $message; exit 2}}\n"
    result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True,
                            check=False, timeout=10)
    assert (result.returncode == 0) == (mutation == "none"), result.stderr
