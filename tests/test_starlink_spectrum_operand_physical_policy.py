"""Physical runner admission only: synthesis commands are forbidden stubs."""
import hashlib
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / "hdl/library/starlink_pss_acquisition"
RUNNER = RTL / "measure_spectrum_operand_boundary.tcl"
XDC = RTL / "starlink_pss_spectrum_operand_register_ooc.xdc"
PROBE = RTL / "tb/tb_starlink_spectrum_operand_parameters.sv"
MARKER = "OPERAND_PARAMETERS_VERIFIED width=18 round=1 registered=0 child_width=18 child_round=1 clocks=0"


def invoke(path, option, *, version="2022.2", cwd=None, before="", after="", probe_stdout=None, probe_error=False):
    injection = ""
    if probe_stdout is not None:
        injection = f"""set injected_probe [encoding convertfrom utf-8 [binary format H* {{{probe_stdout.encode().hex()}}}]]
rename exec original_exec
proc exec {{args}} {{
  if {{[lrange $args 0 3] eq {{env -u LD_LIBRARY_PATH vvp}}}} {{
    {'error' if probe_error else 'return'} $::injected_probe
  }}
  return [uplevel 1 [linsert $args 0 original_exec]]
}}
"""
    script = injection + before + f"""\nproc version {{args}} {{return {version}}}
proc set_param {{args}} {{}}
proc read_verilog {{args}} {{}}
proc synth_design {{args}} {{error SYNTHESIS_FENCED_NO_PHYSICAL_RUN}}
set argv [list {{{path}}} {{{option}}}]
set argc 2
set status [catch {{source {{{RUNNER}}}}} message]
puts "RESULT $status $message"
{after}
"""
    return subprocess.run(["tclsh"], input=script, cwd=cwd or ROOT, text=True,
                          capture_output=True, check=False, timeout=30)


@pytest.mark.parametrize("option", [0, 1])
def test_real_preflight_freezes_and_proves_parameters_before_synthesis(tmp_path, option):
    output = tmp_path / "run"
    result = invoke(output, option)
    assert result.returncode == 0 and not result.stderr, result.stderr
    assert "RESULT 1 SYNTHESIS_FENCED_NO_PHYSICAL_RUN" in result.stdout
    assert "OPERAND_BOUNDARY_PHYSICAL_MEASURED" not in result.stdout
    frozen = output / "frozen_sources"
    inventory = {name: digest for digest, name in
                 (line.split() for line in (output / "input_sources.sha256").read_text().splitlines())}
    assert len(inventory) == 6
    assert inventory == {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in frozen.iterdir()}
    assert (frozen / RUNNER.name).read_bytes() == RUNNER.read_bytes()
    assert (frozen / XDC.name).read_bytes() == XDC.read_bytes()
    assert (frozen / Path(__file__).name).read_bytes() == Path(__file__).read_bytes()
    assert (output / "parameter_probe.log").read_text().strip() == (
        f"OPERAND_PARAMETERS_VERIFIED width=18 round=1 registered={option} child_width=18 child_round=1 clocks=0")
    assert "tool_error=1 source_integrity_error=0" in (output / "result.txt").read_text()
    assert not list(output.glob("*.dcp"))


@pytest.mark.parametrize("option", [-1, 2, "1.0", "x", "", "00"])
def test_invalid_selection_never_allocates(tmp_path, option):
    output = tmp_path / "run"
    result = invoke(output, option)
    assert "expected NEW_OUTPUT and literal REGISTER_OPERANDS" in result.stdout
    assert not output.exists()


def test_version_and_nonoverwrite(tmp_path):
    output = tmp_path / "out"
    result = invoke(output, 0, version="2023.1")
    assert "Vivado2022.2 required" in result.stdout and not output.exists()
    output.mkdir(); (output / "sentinel").write_text("preserve")
    result = invoke(output, 1)
    assert "refusing to overwrite evidence" in result.stdout
    assert list(output.iterdir()) == [output / "sentinel"]
    assert (output / "sentinel").read_text() == "preserve"


def test_relative_output_is_resolved_before_cwd_change(tmp_path):
    result = invoke("relative-run", 1, cwd=tmp_path)
    assert "SYNTHESIS_FENCED_NO_PHYSICAL_RUN" in result.stdout
    assert (tmp_path / "relative-run/frozen_sources").is_dir()


@pytest.mark.parametrize("option", [0, 1])
def test_both_icarus_children_remove_library_path_but_parent_preserves_it(tmp_path, option):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for program in ("iverilog", "vvp"):
        executable = shutil.which(program)
        assert executable is not None
        trace = tmp_path / f"{program}.environment.log"
        shim = binaries / program
        shim.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"${{LD_LIBRARY_PATH-UNSET}}\" > {shlex.quote(str(trace))}\n"
            f"exec {shlex.quote(executable)} \"$@\"\n")
        shim.chmod(0o755)
    inherited = "/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/Ubuntu"
    output = tmp_path / "run"
    result = invoke(output, option, before=(
        f"set ::env(LD_LIBRARY_PATH) {{{inherited}}}\n"
        f"set ::env(PATH) [join [list {{{binaries}}} $::env(PATH)] :]\n"
        'puts "PARENT_BEFORE $::env(LD_LIBRARY_PATH)"\n'),
        after='puts "PARENT_AFTER $::env(LD_LIBRARY_PATH)"')
    (tmp_path / "parent.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0 and not result.stderr
    assert f"PARENT_BEFORE {inherited}" in result.stdout
    assert f"PARENT_AFTER {inherited}" in result.stdout
    assert "RESULT 1 SYNTHESIS_FENCED_NO_PHYSICAL_RUN" in result.stdout
    for program in ("iverilog", "vvp"):
        assert (tmp_path / f"{program}.environment.log").read_text() == "UNSET\n"
    assert (output / "parameter_probe.log").read_text().strip() == MARKER.replace(
        "registered=0", f"registered={option}")
    assert "tool_error=1 source_integrity_error=0" in (output / "result.txt").read_text()


def test_runner_diff_is_only_the_two_child_environment_prefixes():
    before = subprocess.run([
        "git", "-C", str(ROOT / "hdl"), "show",
        "7d4efdb36629e45187d992a7b86e94825b021dbd:library/starlink_pss_acquisition/measure_spectrum_operand_boundary.tcl",
    ], text=True, capture_output=True, check=True).stdout
    after = RUNNER.read_text()
    for program in ("iverilog", "vvp"):
        added = f"exec env -u LD_LIBRARY_PATH {program}"
        assert after.count(added) == 1
        after = after.replace(added, f"exec {program}")
    assert after == before


@pytest.mark.parametrize("receipt", [
    "", MARKER + "\n" + MARKER, MARKER.replace("registered=0", "registered=1"),
    MARKER.replace("child_width=18", "child_width=24"),
    MARKER.replace("child_round=1", "child_round=0"),
    MARKER + "\nFAIL late", MARKER + "\nFATAL: late", MARKER + "\nERROR: late",
    MARKER + "\nunknown receipt", MARKER + " malformed",
    MARKER + "\nprobe.sv:15: $finish called at 1000 (1ps)",
])
def test_probe_receipt_is_single_exact_line_without_late_failure(tmp_path, receipt):
    output = tmp_path / "run"
    result = invoke(output, 0, probe_stdout=receipt)
    assert "RESULT 1 parameter probe did not exactly qualify" in result.stdout
    assert "SYNTHESIS_FENCED" not in result.stdout
    assert "OPERAND_BOUNDARY_PHYSICAL_MEASURED" not in result.stdout
    assert (output / "parameter_probe.log").read_text() == receipt + "\n"
    assert "tool_error=1 source_integrity_error=0" in (output / "result.txt").read_text()
    assert not list(output.glob("*.dcp"))


def test_probe_nonzero_exit_rejects_even_a_correct_marker_and_preserves_log(tmp_path):
    output = tmp_path / "run"
    result = invoke(output, 0, probe_stdout=MARKER, probe_error=True)
    assert "RESULT 1 " + MARKER in result.stdout
    assert "SYNTHESIS_FENCED" not in result.stdout
    assert (output / "parameter_probe.log").read_text() == MARKER + "\n"
    assert "tool_error=1 source_integrity_error=0" in (output / "result.txt").read_text()


@pytest.mark.parametrize("mutation", ["invalid_register", "actual_child_width"])
def test_finish_zero_does_not_hide_real_probe_fatal(tmp_path, mutation):
    source = PROBE.read_text()
    option = 2 if mutation == "invalid_register" else 0
    if mutation == "actual_child_width":
        assert source.count(".DATA_WIDTH(18)") == 1
        source = source.replace(".DATA_WIDTH(18)", ".DATA_WIDTH(24)")
    probe = tmp_path / "probe.sv"
    probe.write_text(source)
    executable = tmp_path / "probe.vvp"
    compiled = subprocess.run([
        "iverilog", "-g2012", "-s", "tb_starlink_spectrum_operand_parameters",
        f"-Ptb_starlink_spectrum_operand_parameters.REGISTER={option}", "-o", str(executable),
        str(RTL / "starlink_pss_spectrum_product.v"),
        str(RTL / "starlink_pss_spectrum_product_operand_register.v"), str(probe),
    ], text=True, capture_output=True, check=False, timeout=30)
    (tmp_path / "compile.log").write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0
    result = subprocess.run(["vvp", str(executable)], text=True, capture_output=True, check=False, timeout=30)
    (tmp_path / "probe.log").write_text(result.stdout + result.stderr)
    assert result.returncode != 0
    assert "FATAL:" in result.stdout
    assert "OPERAND_PARAMETERS_VERIFIED" not in result.stdout
    expected = "invalid" if mutation == "invalid_register" else "actual operand parameters differ"
    assert expected in result.stdout


@pytest.mark.parametrize("mutation", ["delete", "extra", "payload"])
def test_source_guard_rejects_full_inventory_change(tmp_path, mutation):
    commands = {
        "delete": "file delete [file join $frozen starlink_pss_spectrum_product.v]",
        "extra": "set h [open [file join $frozen extra] w]; puts $h extra; close $h",
        "payload": "set h [open [file join $frozen starlink_pss_spectrum_product.v] a]; puts $h changed; close $h",
    }
    result = invoke(tmp_path / "run", 0, after=commands[mutation] +
                    '\nputs "INTEGRITY [catch {operand_verify_sources $frozen $inventory} reason] $reason"')
    assert "INTEGRITY 1 frozen source" in result.stdout


def test_fixed_flow_constraints_and_inventory_contract():
    text = RUNNER.read_text(); constraints = XDC.read_text()
    old = (RTL / "measure_spectrum_round_boundary.tcl").read_text()
    start = old.index("create_clock -name product_clk")
    end = old.index("opt_design -directive ExploreArea")
    assert constraints.splitlines()[1:] == old[start:end].strip().splitlines()
    commands = ["-directive AreaOptimized_high", "opt_design -directive ExploreArea",
                "place_design", "phys_opt_design", "route_design"]
    positions = [text.index(command) for command in commands]
    assert positions == sorted(positions)
    for forbidden in ("set_false_path", "set_multicycle_path", "set_max_delay", "set_min_delay", "-force"):
        assert forbidden not in text and forbidden not in constraints
    assert "set_param general.maxThreads 2" in text
    assert "DATA_WIDTH=18 REGISTER_OPERANDS=$option BOUNDARY_ROUND_SAT=1" in text
    assert "-part xc7z010clg400-1" in text
    assert "foreach property {AREG BREG MREG PREG CREG ACASCREG BCASCREG}" in text
    assert "foreach required {CEA1 CEA2 CEB1 CEB2 CEM CEP}" in text
    assert "get_nets -quiet -of_objects $pin" in text
    for stage in ("synth", "route"):
        assert f"operand_dsp_inventory {stage}" in text
        assert f"operand_timing {stage}" in text
        assert f"utilization_{stage}.rpt" in text
    assert "foreach stage {synth opt route}" in text
    assert "-slack_lesser_than 0 -nworst 1 -max_paths 10000" in text
    assert "failed-endpoint inventory cap reached" in text
    assert text.index("set integrity [catch") > text.index("set status [catch")
    assert re.search(r'if \{\$status\} \{ return -options \$options \$message \}', text)
    assert "NOT_BANK_OR_TIMING_QUALIFICATION" in text
