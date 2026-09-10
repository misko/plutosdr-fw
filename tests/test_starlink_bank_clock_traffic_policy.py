"""Executable stop-runner admission checks, not a replacement for real XFFT."""

import hashlib
import subprocess
from pathlib import Path

import pytest

ACQ = Path(__file__).resolve().parents[1] / "hdl/library/starlink_pss_acquisition"
RUNNER = ACQ / "simulate_bank_owned_clock_traffic.tcl"
BENCH = ACQ / "tb/tb_starlink_pss_bank_clock_traffic.sv"
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


@pytest.mark.parametrize("count", [0, 1, 3])
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
    protected = [ACQ / "starlink_pss_iq_to_score_bank_owned.v", ACQ / "starlink_pss_fft_bank_owned_slice.v",
                 ACQ / "starlink_pss_candidate_score_path.v"]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
    result = probe([output, vectors])
    assert result.returncode == 2 and "ADMITTED" in result.stderr
    frozen = output / "frozen_sources"
    for path in [*protected, RUNNER, BENCH, ACQ / "create_shared_realtime_xfft_ip.tcl",
                 ACQ / "verify_realtime_probe_result.tcl", ACQ / "starlink_pss_realtime_result_guard.v",
                 ACQ / "create_bank_owned_clock_ip.tcl"]:
        assert (frozen / path.name).read_bytes() == path.read_bytes()
    for name in GEOMETRY:
        assert (frozen / f"{name}.mem").read_bytes() == (vectors / f"{name}.mem").read_bytes()
    assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
    scope = (output / "scope.txt").read_text()
    assert "all_visible_score_and_transform_prefixes_compared=true" in scope
    assert "manual_fft_only_reset=1" in scope
    assert "not_input_clock_loss_detection_not_physical_timing_not_receiver_pilot_fine_RF=true" in scope
    assert "frozen_source_hashes=" in scope




def test_actual_runtime_and_both_ip_helpers_are_frozen(tmp_path):
    output, vectors = tmp_path / "new evidence", tmp_path / "vectors"
    vectors_at(vectors)
    result = probe([output, vectors])
    assert result.returncode == 2 and "ADMITTED" in result.stderr
    for name in ("starlink_pss_iq_to_score_bank_owned.v", "starlink_pss_fft_bank_owned_slice.v",
                 "starlink_pss_overlap_scheduler.v", "starlink_pss_energy_cache.v",
                 "starlink_pss_candidate_score_path.v", "create_bank_owned_clock_ip.tcl"):
        assert (output / "frozen_sources" / name).read_bytes() == (ACQ / name).read_bytes()
    assert (output / "frozen_sources" / Path(__file__).name).read_bytes() == Path(__file__).read_bytes()


def test_no_forced_outputs_or_fault_window_numeric_waiver():
    bench, runner = BENCH.read_text(), RUNNER.read_text()
    assert "force " not in bench
    assert "if (score_valid) begin" in bench
    assert "if (!expected_fault) healthy();" in bench
    assert "if (quarantine && (score_valid" in bench
    assert bench.count("(!monitor_active || !fft_resetn)") == 2
    assert "always @(posedge fft_clk)" in bench
    assert "always @(negedge fft_resetn)" in bench
    assert "wait(locked===1)" in bench
    assert "manual_window" in bench and "score_ready=0" in bench
    assert "pss_create_bank_owned_clock_ip" in runner
    assert "pss_create_shared_realtime_xfft_ip" in runner
    assert "launch_runs" not in runner and "create_clock" not in runner


@pytest.mark.parametrize("name", GEOMETRY)
def test_oversize_vector_is_rejected_before_read_allocation(tmp_path, name):
    output, vectors = tmp_path / "new evidence", tmp_path / "vectors"
    vectors_at(vectors)
    rows, width = GEOMETRY[name]
    (vectors / f"{name}.mem").write_text("0" * (rows * (width + 2) + 1))
    result = probe([output, vectors])
    assert result.returncode == 2 and f"oversize vector {name}" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("mutation", ["none", "missing_exact", "missing_reset", "duplicate_kind",
                                    "duplicate_exact", "wrong_exact", "missing_total",
                                    "duplicate_pass", "wrong_pass", "fail", "fatal"])
def test_exact_postprocessor_rejects_missing_or_failed_traffic(tmp_path, mutation):
    log = tmp_path / "test.sim/sim_1/behav/xsim/simulate.log"
    log.parent.mkdir(parents=True)
    lines = [f"BANK_CLOCK_TRAFFIC_EXACT epoch={n} scores=1341 forward=1536 product=1536 inverse=1536 source_base=1000000"
             for n in (1, 3, 5, 7, 9)]
    lines += [f"BANK_CLOCK_TRAFFIC_RESET kind={n} exact_score_prefix=100" for n in range(4)]
    lines += ["BANK_CLOCK_TRAFFIC_TOTAL exact_scores=7105",
              "BANK_CLOCK_TRAFFIC_PASS exact_epochs=5 exact_full_scores=6705 reset_cases=4 mmcm_active_resets=3 manual_fft_only_resets=1 measured_edges=5120 ACTUAL_IP_NO_INPUT_CLOCK_LOSS_RECEIVER_PHYSICAL_OR_RF_CLAIM"]
    if mutation == "missing_exact":
        lines.pop(0)
    elif mutation == "missing_reset":
        lines.pop(5)
    elif mutation == "duplicate_kind":
        lines[6] = lines[5]
    elif mutation == "duplicate_exact":
        lines[1] = lines[0]
    elif mutation == "wrong_exact":
        lines[0] = lines[0].replace("1341", "1340")
    elif mutation == "missing_total":
        lines.pop(-2)
    elif mutation == "duplicate_pass":
        lines.append(lines[-1])
    elif mutation == "wrong_pass":
        lines[-1] = lines[-1].replace("6705", "6704")
    elif mutation == "fail":
        lines.append("  bank_clock_traffic_fail late assertion")
    elif mutation == "fatal":
        lines.append("Fatal: simulator failure")
    log.write_text("\n".join(lines) + "\n")
    contract = RUNNER.read_text().split("close_sim\n", 1)[1].split("close_project", 1)[0]
    script = f"source {{{ACQ / 'verify_realtime_probe_result.tcl'}}}\n"
    script += f"set project_dir {{{tmp_path}}}\nset project_name test\n"
    script += f"if {{[catch {{{contract}}} message]}} {{puts stderr $message; exit 2}}\n"
    result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True,
                            check=False, timeout=10)
    assert (result.returncode == 0) == (mutation == "none"), result.stderr
