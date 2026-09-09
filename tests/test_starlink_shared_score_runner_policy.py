"""Executable admission/snapshot tests; actual-core replays own score evidence."""
from pathlib import Path
import re
import subprocess

import pytest

ACQ = Path(__file__).resolve().parents[1] / "hdl/library/starlink_pss_acquisition"
RUNNER = ACQ / "simulate_iq_to_score_shared.tcl"
VECTORS = ("samples_ci16", "forward_q17", "product_q17", "inverse_q17",
           "forward_exponents", "inverse_exponents", "scores_u8")


def invoke(arguments, version="2022.2"):
    script = "proc version {args} {return {" + version + "}}\n"
    script += 'proc create_project {args} {error "ADMITTED"}\n'
    script += "set argv [list " + " ".join(f"{{{arg}}}" for arg in arguments) + "]\n"
    script += "set argc [llength $argv]\n"
    script += f"if {{[catch {{source {{{RUNNER}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return subprocess.run(["tclsh"], input=script, capture_output=True, text=True, timeout=10)


@pytest.mark.parametrize("arguments", [
    [], ["numeric"], ["numeric", "vectors", "1", "extra"],
    ["capacity", "65"], ["capacity", "4096", "unknown"],
    ["capacity", "64", "nominal", "2"],
    ["capacity", "64", "nominal", "true"],
    ["numeric", "vectors", "1.0"], ["unknown"],
])
def test_invalid_arguments_never_allocate_output(tmp_path, arguments):
    output = tmp_path / "new evidence"
    result = invoke([output, *arguments])
    assert result.returncode == 2 and "ADMITTED" not in result.stderr
    assert not output.exists()


def test_wrong_version_never_allocates(tmp_path):
    output = tmp_path / "evidence"
    result = invoke([output, "capacity"], version="2023.1")
    assert "requires Vivado 2022.2" in result.stderr and not output.exists()


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_old_evidence_is_never_overwritten(tmp_path, kind):
    output = tmp_path / "evidence"
    retained = output
    if kind != "file":
        target = tmp_path / "target" if kind == "symlink" else output
        target.mkdir()
        retained = target / "retained"
        if kind == "symlink":
            output.symlink_to(target, target_is_directory=True)
    retained.write_text("unchanged")
    result = invoke([output, "capacity"])
    assert "refusing to overwrite" in result.stderr
    assert retained.read_text() == "unchanged"


@pytest.mark.parametrize("missing", VECTORS)
def test_missing_vector_is_checked_before_allocation(tmp_path, missing):
    output, vectors = tmp_path / "evidence", tmp_path / "vectors"
    vectors.mkdir()
    for name in VECTORS:
        if name != missing:
            (vectors / f"{name}.mem").write_text("00\n")
    result = invoke([output, "numeric", vectors, "1"])
    assert f"missing vector {missing}" in result.stderr and not output.exists()


@pytest.mark.parametrize("mode,choice", [(mode, choice) for mode in
                         ("numeric", "capacity") for choice in (None, "0", "1")])
def test_exact_snapshots_and_selected_clock_fault_paths(tmp_path, mode, choice):
    output, vectors = tmp_path / "evidence", tmp_path / "vectors"
    vectors.mkdir()
    for name in VECTORS:
        (vectors / f"{name}.mem").write_text("00\n")
    arguments = [output, mode]
    arguments += [vectors] if mode == "numeric" else ["4096", "bursty-stalled"]
    if choice is not None:
        arguments.append(choice)
    result = invoke(arguments)
    assert "ADMITTED" in result.stderr, result.stdout + result.stderr
    frozen = output / "frozen_sources"
    assert (frozen / RUNNER.name).read_bytes() == RUNNER.read_bytes()
    for path in frozen.glob("*.v"):
        assert path.read_bytes() == (ACQ / path.name).read_bytes()
    suffix = "_longrun" if mode == "capacity" else ""
    bench_name = f"tb_starlink_pss_iq_to_score_xfft{suffix}.sv"
    assert (frozen / bench_name).read_bytes() == (ACQ / "tb" / bench_name).read_bytes()
    bench = (output / bench_name).read_text()
    assert f"#(.USE_REALTIME_XFFT({choice or '0'})) dut (" in bench
    assert ".fft_clk(fft_clk), .fft_resetn(fft_resetn)," in bench
    assert "forever #2.5 fft_clk = !fft_clk" in bench
    if mode == "numeric":
        leaf = "realtime_transform.transform_service.input_guard" if choice == "1" else (
            "nonrealtime_transform.transform_service.adapter")
        assert f"force dut.{leaf}.protocol_fault" in bench
        assert "SHARED_PIPELINE_FFT_RESET_PASS" in bench
        assert "SHARED_PIPELINE_NUMERIC_CERTIFIED scores=1341" in bench
        for name in VECTORS:
            assert (frozen / f"{name}.mem").read_bytes() == (vectors / f"{name}.mem").read_bytes()
    else:
        assert "localparam integer BLOCK_COUNT = 4096;" in bench
        assert '$fatal(1, "shared pipeline fault")' in bench
        assert "SHARED_PIPELINE_CAPACITY_CERTIFIED blocks=4096 profile=bursty-stalled" in bench
        assert "COUNTS_ORDER_BACKLOG_NOT_NUMERICS" in bench


def test_pinned_generics_and_terminal_verifier_are_required():
    source = RUNNER.read_text()
    pattern = r"set required_generics \{(.*?)\}"
    pairs = re.search(pattern, source, re.S).group(1).split()
    candidate = re.search(pattern, (ACQ / "simulate_realtime_xfft_protocol_probe.tcl").read_text(), re.S).group(1).split()
    expected = dict(zip(candidate[::2], candidate[1::2]))
    expected.pop("C_THROTTLE_SCHEME")
    assert len(pairs) == 62 and dict(zip(pairs[::2], pairs[1::2])) == expected
    assert "C_THROTTLE_SCHEME [expr {$use_realtime_xfft ? 0 : 1}]" in source
    assert "require_realtime_probe_pass $log_path" in source
    assert "IQ_TO_SCORE_XFFT_LONGRUN_PROGRESS $capacity_blocks" in source
    assert "IQ_TO_SCORE_XFFT_PASS 1" in source
    assert "set use_realtime_xfft 0" in source
    assert "CONFIG.throttle_scheme $throttle" in source
    assert "set module_name starlink_pss_fft512_bfp18_rt_candidate" in source
