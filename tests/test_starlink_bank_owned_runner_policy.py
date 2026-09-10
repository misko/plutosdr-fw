"""Root-review tests for bench adaptation/admission, not arithmetic or RF proof."""

import subprocess
from pathlib import Path

import pytest

ACQ = Path(__file__).resolve().parents[1] / "hdl/library/starlink_pss_acquisition"
RUNNER = ACQ / "simulate_iq_to_score_bank_owned.tcl"
PREPARE = ACQ / "prepare_iq_to_score_bank_owned.tcl"
VECTOR_NAMES = (
    "upper_edge_pss_kernel_q17", "samples_ci16", "forward_q17", "product_q17",
    "inverse_q17", "forward_exponents", "inverse_exponents", "scores_u8",
)


def tcl(script):
    return subprocess.run(
        ["tclsh"], input=script, text=True, capture_output=True, timeout=15,
        check=False,
    )


def invoke(arguments, version="2022.2"):
    script = f"proc version {{args}} {{return {{{version}}}}}\n"
    script += 'proc set_param {args} {}\nproc create_project {args} {error "ADMITTED"}\n'
    script += "set argv [list " + " ".join(f"{{{arg}}}" for arg in arguments) + "]\n"
    script += "set argc [llength $argv]\n"
    script += f"if {{[catch {{source {{{RUNNER}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return tcl(script)


def make_vectors(directory, missing=None):
    directory.mkdir()
    for name in VECTOR_NAMES:
        if name != missing:
            (directory / f"{name}.mem").write_text("00\n")


@pytest.mark.parametrize("arguments", [
    [], ["numeric"], ["unknown", "nominal", "175"],
    ["capacity", "unknown", "175"], ["capacity", "nominal", "150"],
    ["capacity", "nominal", "175.0"], ["capacity", "nominal", " 175"],
    ["capacity", "nominal", "200", "extra"],
])
def test_invalid_admission_never_allocates_evidence(tmp_path, arguments):
    output = tmp_path / "new evidence"
    result = invoke([output, *arguments])
    assert result.returncode == 2 and "ADMITTED" not in result.stderr
    assert not output.exists()


def test_wrong_version_is_rejected_before_allocation(tmp_path):
    output = tmp_path / "new evidence"
    result = invoke([output, "capacity", "nominal", "175"], "2023.1")
    assert "requires Vivado 2022.2" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_existing_evidence_is_not_overwritten(tmp_path, kind):
    output = tmp_path / "evidence"
    retained = output
    if kind != "file":
        target = tmp_path / "target" if kind == "symlink" else output
        target.mkdir()
        retained = target / "retained"
        if kind == "symlink":
            output.symlink_to(target, target_is_directory=True)
    retained.write_text("untouched")
    result = invoke([output, "capacity", "nominal", "175"])
    assert "refusing to overwrite" in result.stderr
    assert retained.read_text() == "untouched"


@pytest.mark.parametrize("missing", VECTOR_NAMES)
def test_missing_numeric_inputs_precede_evidence_allocation(tmp_path, missing):
    output, vectors = tmp_path / "evidence", tmp_path / "vectors"
    make_vectors(vectors, missing)
    result = invoke([output, "numeric", vectors, "200"])
    assert "missing source" in result.stderr and missing in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("mode,profile,frequency", [
    ("numeric", None, "175"), ("numeric", None, "200"),
    ("capacity", "nominal", "175"), ("capacity", "bursty-stalled", "175"),
    ("capacity", "nominal", "200"), ("capacity", "bursty-stalled", "200"),
])
def test_exact_snapshots_and_domain_correct_monitors(tmp_path, mode, profile, frequency):
    output, vectors = tmp_path / "evidence", tmp_path / "vectors"
    make_vectors(vectors)
    result = invoke([output, mode, profile or vectors, frequency])
    assert "ADMITTED" in result.stderr, result.stdout + result.stderr
    frozen = output / "frozen_sources"
    assert (frozen / RUNNER.name).read_bytes() == RUNNER.read_bytes()
    assert (frozen / PREPARE.name).read_bytes() == PREPARE.read_bytes()
    for path in frozen.glob("*.v"):
        assert path.read_bytes() == (ACQ / path.name).read_bytes()
    for path in frozen.glob("*.svh"):
        assert path.read_bytes() == (ACQ / "tb" / path.name).read_bytes()
    suffix = "_longrun" if mode == "capacity" else ""
    name = f"tb_starlink_pss_iq_to_score_xfft{suffix}.sv"
    assert (frozen / name).read_bytes() == (ACQ / "tb" / name).read_bytes()
    bench = (output / name).read_text()
    assert "starlink_pss_iq_to_score_bank_owned dut (" in bench
    assert "#(500.0 / FAST_MHZ)" in bench
    before, fast = bench.split("always @(posedge fft_clk)")
    assert "dut.island.joiner.input_valid" not in before
    assert "dut.island.product_valid" not in before
    assert "dut.island.joiner.input_valid" in fast
    assert "dut.island.product_valid && !dut.island.fast_fault" in fast
    assert "dut.inverse_output_valid" in before
    assert "input_valid_UNUSED" not in bench
    if mode == "numeric":
        assert "dut.inverse_forward_exponent !== expected_forward_exponents" in bench
        assert "run_bank_fault_scenarios();" in bench
        assert "dut.forward_adapter.protocol_fault" not in bench
        for vector in VECTOR_NAMES:
            assert (frozen / f"{vector}.mem").read_bytes() == (vectors / f"{vector}.mem").read_bytes()
    else:
        assert "always @(negedge clk) score_ready" in bench
        assert "dut.transform_fifo" not in bench
        assert 'report_and_fail("independent_frame_counter_totals")' in bench
        assert "BANK_IQ_CAPACITY_COMPLETE blocks=64 samples=28673 scores=28608" in bench
        assert '$fatal(1, "bank-owned continuous pipeline fault")' in bench


@pytest.mark.parametrize("value,old", [("absent", "anchor"), ("anchor anchor", "anchor")])
def test_single_anchor_rejects_missing_or_duplicate(value, old):
    result = tcl(
        f"source {{{PREPARE}}}\n"
        f"if {{[catch {{bank_replace_once {{{value}}} {{{old}}} replacement}} message]}} "
        "{puts stderr $message; exit 2}\n"
    )
    assert result.returncode == 2 and "missing or duplicated" in result.stderr


def test_actual_verifier_requires_nonempty_exact_terminal(tmp_path):
    log = tmp_path / "simulate.log"
    log.write_text("BANK_IQ_CAPACITY_COMPLETE blocks=64 samples=28673 scores=28608\nROW result\n")
    verifier = ACQ / "verify_realtime_probe_result.tcl"
    for markers, expected in [("{}", 2), ("{missing}", 2),
                              ("{{BANK_IQ_CAPACITY_COMPLETE blocks=64 samples=28673 scores=28608}}", 0)]:
        result = tcl(
            f"source {{{verifier}}}\n"
            f"if {{[catch {{require_realtime_probe_pass {{{log}}} {markers} ROW 1}} message]}} "
            "{puts stderr $message; exit 2}\n"
        )
        assert result.returncode == expected, result.stderr
    source = RUNNER.read_text()
    assert "require_realtime_probe_pass $logfile {}" not in source
    assert "require_realtime_probe_pass $logfile $terminal_markers" in source


def terminal_transcript(mode):
    if mode == "numeric":
        return (
            "BANK_IQ_FAULT_RESET_GAP_PASS qualifier_mutations=5 descriptor=1 "
            "core_fault=1 fft_reset=1 slow_reset=1 source_gap=1 source_index=1 "
            "exact_epochs=4 exact_scores=5364 autonomous_gap_index_recovery=1\n"
            "IQ_TO_SCORE_XFFT_PASS scores=1341\n"
            + "".join(f"BANK_IQ_EXACT_REPLAY_PASS epoch={epoch} scores=1341\n"
                      for epoch in (2, 3, 4))
        )
    return (
        "BANK_IQ_CAPACITY_COMPLETE blocks=64 samples=28673 scores=28608\n"
        "IQ_TO_SCORE_XFFT_LONGRUN_PASS blocks=64\n"
        "IQ_TO_SCORE_XFFT_BACKLOG_PASS blocks=64\n"
        "BANK_IQ_CAPACITY_METADATA_PASS blocks=64\n"
        + "".join(f"IQ_TO_SCORE_XFFT_LONGRUN_PROGRESS block={block}\n"
                  for block in range(1, 65))
    )


@pytest.mark.parametrize("mode", ["numeric", "capacity"])
@pytest.mark.parametrize("bad_line", [
    "", "IQ_TO_SCORE_XFFT_FAIL reason=assertion\n",
    "IQ_TO_SCORE_XFFT_FAULT reason=assertion\n",
    "IQ_TO_SCORE_XFFT_LONGRUN_FAIL reason=assertion\n",
    "IQ_TO_SCORE_XFFT_LONGRUN_FAULT reason=assertion\n",
    "Fatal: simulator failure\n", "ERROR: simulator failure\n",
])
def test_exact_runner_postprocessor_rejects_failure_even_with_pass(tmp_path, mode, bad_line):
    # Execute the actual Tcl postprocessor, not a Python copy of its regex.
    # Fixture PASS rows test parser admission only; no arithmetic is simulated.
    source = RUNNER.read_text()
    anchor = "set channel [open $logfile r];"
    assert source.count(anchor) == 1
    start = source.index(anchor)
    stop = source.index("\nclose_project", start)
    contract = source[start:stop]
    log = tmp_path / "simulate.log"
    log.write_text(bad_line + terminal_transcript(mode))
    result = tcl(
        f"source {{{ACQ / 'verify_realtime_probe_result.tcl'}}}\n"
        f"set logfile {{{log}}}\nset mode {mode}\nset capacity_blocks 64\n"
        "if {[catch {\n" + contract + "\n} message]} {puts stderr $message; exit 2}\n"
    )
    assert result.returncode == (2 if bad_line else 0), result.stdout + result.stderr
