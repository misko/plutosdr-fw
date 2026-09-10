"""Clock IP/runner admission; actual generated-IP logs own clock/reset proof."""

import subprocess
from pathlib import Path

import pytest

ACQ = Path(__file__).resolve().parents[1] / "hdl/library/starlink_pss_acquisition"
HELPER = ACQ / "create_bank_owned_clock_ip.tcl"
RUNNER = ACQ / "simulate_bank_owned_clock_epoch.tcl"
PARAMETERS = {"DIVCLK_DIVIDE": "2", "CLKFBOUT_MULT_F": "20.125",
              "CLKOUT0_DIVIDE_F": "5.750", "CLKIN1_PERIOD": "10.000"}


def tcl(script):
    return subprocess.run(["tclsh"], input=script, text=True, capture_output=True,
                          check=False, timeout=10)


def helper_probe(tmp_path, mutation=None, version="2022.2", existing=False):
    parameters = PARAMETERS | ({mutation: "999"} if mutation in PARAMETERS else {})
    text = "MMCME2_ADV\nBUFG\nBUFG\n" + "\n".join(
        f".{key} ({value})" for key, value in parameters.items()
    )
    text += "\nassign reset_high = ~resetn;\n"
    text += "assign clk_in1_starlink_bank_clock175_candidate = clk_in1;\n"
    if mutation == "duplicate":
        text += ".DIVCLK_DIVIDE (2)\n"
    if mutation == "buffer":
        text += "BUFG\n"
    if mutation == "reset":
        text = text.replace("~resetn", "resetn")
    if mutation == "input":
        text = text.replace("= clk_in1", "= bad_clock")
    (tmp_path / "starlink_bank_clock175_candidate_clk_wiz.v").write_text(text)
    script = f"source {{{HELPER}}}\n"
    script += "proc version {args} {return {" + version + "}}\n"
    script += "set created 0\nproc create_ip {args} {incr ::created}\n"
    script += 'proc set_property {args} {set ::configuration [lindex $args 1]}\n'
    script += "proc generate_target {args} {}\n"
    script += ("proc get_ips {args} {if {[lindex $args 0] eq {-quiet}} "
               "{return {%s}}; return clock}\n") % ("existing" if existing else "")
    script += f"set failed [catch {{pss_create_bank_owned_clock_ip {{{tmp_path}}}}} message]\n"
    script += 'puts "created=$created failed=$failed result=$message"\n'
    script += 'if {!$failed} {puts $::configuration}\n'
    return tcl(script)


def test_actual_candidate_contract_is_explicit(tmp_path):
    result = helper_probe(tmp_path)
    assert "created=1 failed=0" in result.stdout
    assert "CONFIG.PRIM_SOURCE No_buffer" in result.stdout
    assert "CONFIG.RESET_TYPE ACTIVE_LOW" in result.stdout
    assert "CONFIG.CLKOUT1_REQUESTED_OUT_FREQ 175.000" in result.stdout
    assert "CONFIG.PRIM_IN_FREQ 100.000" in result.stdout


@pytest.mark.parametrize("mutation", [*PARAMETERS, "duplicate", "buffer", "reset", "input"])
def test_changed_generated_clock_contract_is_rejected(tmp_path, mutation):
    assert "failed=1" in helper_probe(tmp_path, mutation=mutation).stdout


@pytest.mark.parametrize("version,existing", [("2023.1", False), ("2022.2", True)])
def test_wrong_tool_or_existing_ip_rejected_before_creation(tmp_path, version, existing):
    result = helper_probe(tmp_path, version=version, existing=existing)
    assert "created=0 failed=1" in result.stdout


def runner_probe(arguments):
    script = 'proc version {args} {return "2022.2"}\nproc set_param {args} {}\n'
    script += 'proc create_project {args} {error "ADMITTED"}\n'
    script += "set argv [list " + " ".join(f"{{{arg}}}" for arg in arguments) + "]\n"
    script += "set argc [llength $argv]\n"
    script += f"if {{[catch {{source {{{RUNNER}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return tcl(script)


def test_runner_freezes_actual_bank_and_helpers_before_project(tmp_path):
    output = tmp_path / "new evidence"
    result = runner_probe([output])
    assert result.returncode == 2 and "ADMITTED" in result.stderr
    for path in (RUNNER, HELPER, ACQ / "starlink_pss_fft_bank_owned_slice.v",
                 ACQ / "tb/tb_starlink_pss_bank_clock_epoch.sv"):
        assert (output / "frozen_sources" / path.name).read_bytes() == path.read_bytes()


def test_runner_never_overwrites_existing_evidence(tmp_path):
    retained = tmp_path / "keep"
    retained.write_text("unchanged")
    result = runner_probe([tmp_path])
    assert "refusing to overwrite" in result.stderr
    assert retained.read_text() == "unchanged"


@pytest.mark.parametrize("arguments", [[], ["unused", "extra"]])
def test_invalid_arity_is_rejected(arguments):
    result = runner_probe(arguments)
    assert result.returncode == 2 and "expected NEW_OUTPUT" in result.stderr


@pytest.mark.parametrize("mutation", ["none", "missing_period", "missing_epoch", "fail", "fatal"])
def test_exact_clock_postprocessor_rejects_incomplete_or_failed_epoch(tmp_path, mutation):
    log = tmp_path / "test.sim/sim_1/behav/xsim/simulate.log"
    log.parent.mkdir(parents=True)
    lines = [f"BANK_CLOCK_EPOCH_READY epoch={n}" for n in range(1, 4)]
    lines += [f"BANK_CLOCK_PERIOD_PASS epoch={n} edges=1024 mean_period_ns=5.714286133"
              for n in range(1, 4)]
    lines.append("BANK_CLOCK_EPOCH_PASS epochs=3 measured_edges=3072 mmcm_reset_lock_drop=1 manual_epoch_reset=1 actual_idle_bank=1 NO_PAYLOAD_PHYSICAL_OR_RADIO_CLAIM")
    if mutation == "missing_period":
        lines.pop(3)
    if mutation == "missing_epoch":
        lines.pop(0)
    if mutation == "fail":
        lines.append("BANK_CLOCK_EPOCH_FAIL late assertion")
    if mutation == "fatal":
        lines.append("Fatal: simulation failure")
    log.write_text("\n".join(lines) + "\n")
    contract = RUNNER.read_text().split("close_sim\n", 1)[1].split("close_project", 1)[0]
    script = f"source {{{ACQ / 'verify_realtime_probe_result.tcl'}}}\n"
    script += f"set project_dir {{{tmp_path}}}\nset project_name test\n"
    script += f"if {{[catch {{{contract}}} message]}} {{puts stderr $message; exit 2}}\n"
    result = tcl(script)
    assert (result.returncode == 0) == (mutation == "none"), result.stderr
