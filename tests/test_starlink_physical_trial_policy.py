"""Execute diagnostic-runner admission without pretending to run implementation."""

from pathlib import Path
import subprocess

import pytest


RUNNER = Path(__file__).resolve().parents[1] / "hdl/projects/pluto/explore_shared_receiver_checkpoint.tcl"
FFT_RUNNER = RUNNER.parents[2] / "library/starlink_pss_acquisition/measure_shared_xfft_clock.tcl"


@pytest.mark.parametrize("mode", ["spread-high", "spread-medium", "post-route"])
def test_named_trial_requires_fresh_evidence_directory(tmp_path, mode):
    checkpoint = tmp_path / "saved.dcp"
    checkpoint.touch()
    existing = tmp_path / "existing"
    existing.mkdir()
    result = subprocess.run(["tclsh", str(RUNNER), str(checkpoint), str(existing), mode],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "refusing to overwrite experiment evidence" in result.stderr
    assert not list(existing.iterdir())


@pytest.mark.parametrize("mode", ["default", "spread-low", "spread-medium; exit 0", ""])
def test_unknown_trial_is_rejected_before_creating_output(tmp_path, mode):
    checkpoint = tmp_path / "saved.dcp"
    checkpoint.touch()
    output = tmp_path / "new"
    result = subprocess.run(["tclsh", str(RUNNER), str(checkpoint), str(output), mode],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "unsupported implementation experiment" in result.stderr
    assert not output.exists()


def test_missing_checkpoint_does_not_create_output(tmp_path):
    output = tmp_path / "new"
    result = subprocess.run(["tclsh", str(RUNNER), str(tmp_path / "missing.dcp"),
                             str(output), "spread-medium"],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "missing input checkpoint" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("clock,mode,existing,error", [
    ("200", "actual-synth", True, "requires a fresh output directory"),
    ("150", "actual-synth", False, "restricted to 100/200 MHz"),
    ("200", "unknown", False, "only optional synthesis-clock probe"),
    ("200", "actual-synth; exit 0", False, "only optional synthesis-clock probe"),
])
def test_actual_synthesis_probe_admission(tmp_path, clock, mode, existing, error):
    runner = RUNNER.parents[2] / "library/starlink_pss_acquisition/measure_shared_xfft_clock.tcl"
    output = tmp_path / "evidence"
    if existing:
        output.mkdir()
    # The actual runner exits before any Vivado design command. Only emulate
    # its version query, not synthesis, implementation, clocks or timing.
    script = "proc version {args} {return 2022.2}\nset argc 3\n"
    script += f"set argv [list {{{output}}} {{{clock}}} {{{mode}}}]\n"
    script += f"if {{[catch {{source {{{runner}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    result = subprocess.run(["tclsh"], input=script, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2 and error in result.stderr
    assert output.exists() == existing
    if existing:
        assert not list(output.iterdir())


def _fft_probe(output, arguments, *, vivado_version="2022.2", generated=None):
    """Run the actual Tcl until a mocked Vivado boundary, never synthesize.

    With generated=(architecture, throttle, clock_text), emulate only the IP
    generator's two text files so the real runner's guards/clock rewrite run.
    The stop at create_ip_run prevents every synthesis/implementation command.
    """
    argv = [str(output), *arguments]
    script = f"proc version {{args}} {{return {{{vivado_version}}}}}\n"
    script += f"set argc {len(argv)}\nset argv [list "
    script += " ".join("{" + value + "}" for value in argv) + "]\n"
    if generated is None:
        script += r"""
proc create_project {args} {
    error "ADMITTED actual=$::actual_synthesis_clock realtime=$::shared_realtime_probe clock=$::clock_mhz throttle=$::throttle_scheme"
}
"""
    else:
        architecture, throttle, clock_text = generated
        script += f"set test_arch {architecture}\nset test_throttle {throttle}\n"
        script += "set test_clock {" + clock_text + "}\n"
        script += r"""
proc create_project {args} {}
proc current_project {} {return mock_project}
proc create_ip {args} {}
proc get_ips {args} {return mock_ip}
proc set_property {args} {
    if {[lindex $args 0] eq "-dict"} {set ::test_ip_config [lindex $args 1]}
}
proc generate_target {args} {
    set ip_dir [file join $::output_dir project shared_xfft_clock.gen sources_1 ip starlink_pss_fft512_bfp18]
    file mkdir [file join $ip_dir synth]
    set channel [open [file join $ip_dir synth starlink_pss_fft512_bfp18.vhd] w]
    puts $channel "C_ARCH => $::test_arch,\nC_THROTTLE_SCHEME => $::test_throttle,"
    close $channel
    set channel [open [file join $ip_dir starlink_pss_fft512_bfp18_ooc.xdc] w]
    puts -nonewline $channel $::test_clock
    close $channel
}
proc create_ip_run {args} {
    error "BEFORE_SYNTH throttle=[dict get $::test_ip_config CONFIG.throttle_scheme] clock=[dict get $::test_ip_config CONFIG.target_clock_frequency]"
}
"""
    script += f"if {{[catch {{source {{{FFT_RUNNER}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return subprocess.run(["tclsh"], input=script, capture_output=True, text=True, timeout=10)


@pytest.mark.parametrize("arguments,error", [
    (["100", "actual-synth", "shared-realtime"], "requires actual-synth at 200 MHz"),
    (["200", "shared-realtime"], "only optional synthesis-clock probe"),
    (["200", "wrong", "shared-realtime"], "only optional synthesis-clock probe"),
    (["200", "actual-synth", "realtime"], "requires actual-synth at 200 MHz"),
    (["200", "actual-synth", "shared-realtime; exit 0"], "requires actual-synth at 200 MHz"),
    (["200", "actual-synth", ""], "requires actual-synth at 200 MHz"),
    (["200", "actual-synth", "shared-realtime", "extra"], "expected output directory"),
    (["250", "actual-synth", "shared-realtime"], "restricted to 100/200 MHz"),
])
def test_realtime_probe_invalid_mode_has_no_filesystem_effect(tmp_path, arguments, error):
    output = tmp_path / "new-evidence"
    result = _fft_probe(output, arguments)
    assert result.returncode == 2 and error in result.stderr
    assert "ADMITTED" not in result.stderr and not output.exists()


@pytest.mark.parametrize("existing_kind", ["directory", "file", "symlink"])
def test_realtime_probe_preserves_existing_evidence(tmp_path, existing_kind):
    output = tmp_path / "evidence"
    if existing_kind == "file":
        output.write_text("retained evidence")
        retained = output
    else:
        destination = tmp_path / "destination" if existing_kind == "symlink" else output
        destination.mkdir()
        retained = destination / "receipt.txt"
        retained.write_text("retained evidence")
        if existing_kind == "symlink":
            output.symlink_to(destination, target_is_directory=True)
    result = _fft_probe(output, ["200", "actual-synth", "shared-realtime"])
    assert result.returncode == 2 and "requires a fresh output directory" in result.stderr
    assert "ADMITTED" not in result.stderr and retained.read_text() == "retained evidence"
    if existing_kind != "file":
        assert list(output.iterdir()) == [output / "receipt.txt"]


def test_realtime_probe_rejects_wrong_tool_before_creating_output(tmp_path):
    output = tmp_path / "new-evidence"
    result = _fft_probe(output, ["200", "actual-synth", "shared-realtime"],
                        vivado_version="2023.1")
    assert result.returncode == 2 and "requires Vivado 2022.2" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("arguments,actual,realtime,clock", [
    ([], 0, 0, 200), (["100"], 0, 0, 100), (["200"], 0, 0, 200),
    (["100", "actual-synth"], 1, 0, 100),
    (["200", "actual-synth"], 1, 0, 200),
    (["200", "actual-synth", "shared-realtime"], 1, 1, 200),
])
def test_realtime_is_explicit_and_legacy_defaults_unchanged(tmp_path, arguments, actual, realtime, clock):
    output = tmp_path / "new-evidence"
    result = _fft_probe(output, arguments)
    throttle = "realtime" if realtime else "nonrealtime"
    assert result.returncode == 2
    assert f"ADMITTED actual={actual} realtime={realtime} clock={clock} throttle={throttle}" in result.stderr
    if actual:
        assert (output / "probe_source.tcl").read_bytes() == FFT_RUNNER.read_bytes()
    else:
        assert not list(output.iterdir())


@pytest.mark.parametrize("arguments,generated_throttle,expected_period,throttle", [
    ([], 1, None, "nonrealtime"),
    (["100", "actual-synth"], 1, "10.0", "nonrealtime"),
    (["200", "actual-synth"], 1, "5.0", "nonrealtime"),
    (["200", "actual-synth", "shared-realtime"], 0, "5.0", "realtime"),
])
def test_fresh_generated_clock_only_is_rewritten_before_synthesis(
    tmp_path, arguments, generated_throttle, expected_period, throttle,
):
    original = "# untouched marker\ncreate_clock -period 10 -name aclk [get_ports aclk]\n"
    output = tmp_path / "new-evidence"
    result = _fft_probe(output, arguments, generated=(1, generated_throttle, original))
    assert result.returncode == 2 and f"BEFORE_SYNTH throttle={throttle}" in result.stderr
    generated_file = (output / "project/shared_xfft_clock.gen/sources_1/ip/"
                      "starlink_pss_fft512_bfp18/starlink_pss_fft512_bfp18_ooc.xdc")
    if expected_period is None:
        assert generated_file.read_text() == original
        assert not (output / "actual_synthesis_ooc.xdc").exists()
    else:
        expected = original.replace("-period 10 ", f"-period {expected_period} ")
        assert generated_file.read_text() == expected
        assert (output / "actual_synthesis_ooc.xdc").read_text() == expected
        assert (output / "generated_ooc_original.xdc").read_text() == original


@pytest.mark.parametrize("architecture,throttle,clock,error", [
    (2, 0, "create_clock -period 10 -name aclk [get_ports aclk]\n", "retain the frozen radix-4"),
    (1, 1, "create_clock -period 10 -name aclk [get_ports aclk]\n", "requested throttle scheme"),
    (1, 0, "create_clock -period 5 -name aclk [get_ports aclk]\n", "exactly one generated 10 ns"),
    (1, 0, "create_clock -period 10 -name aclk [get_ports aclk]\n" * 2, "exactly one generated 10 ns"),
])
def test_realtime_generated_contract_mismatch_stops_before_synthesis(
    tmp_path, architecture, throttle, clock, error,
):
    output = tmp_path / "new-evidence"
    result = _fft_probe(output, ["200", "actual-synth", "shared-realtime"],
                        generated=(architecture, throttle, clock))
    assert result.returncode == 2 and error in result.stderr
    assert "BEFORE_SYNTH" not in result.stderr
    assert not (output / "actual_synthesis_ooc.xdc").exists()


def test_realtime_trial_preserves_constraints_and_unqualified_evidence_labels():
    """Source policy guard only; actual timing belongs to retained Vivado reports."""
    source = FFT_RUNNER.read_text()
    assert "-part xc7z010clg400-1" in source
    assert "CONFIG.transform_length {512}" in source
    assert "CONFIG.input_width {18}" in source
    assert "CONFIG.scaling_options {block_floating_point}" in source
    assert "CONFIG.rounding_modes {convergent_rounding}" in source
    assert "set_property HD.CLK_SRC BUFGCTRL_X0Y0 $clock_port" in source
    assert "1000.0 / $clock_mhz" in source
    for direction in ("input", "output"):
        for bound, delay in (("max", "1.000"), ("min", "0.000")):
            assert f"set_{direction}_delay -clock $core_clock -{bound} {delay}" in source
    for prohibited in ("set_false_path", "set_multicycle_path", "set_max_delay", "set_clock_groups"):
        assert prohibited not in source
    for label in ("numerical_equivalence_qualified=false", "service_protocol_qualified=false",
                  "whole_receiver_qualified=false", "protocol_scope=shared_candidate_realtime_feasibility_only"):
        assert label in source
    assert 'if {[llength $synth_ce_registers] != 0}' in source
    assert 'if {[llength $ce_registers] != 0}' in source
