"""Local guard actual preparation only: Icarus guard tests and Tcl mocks, no FFT."""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("local_actual", ROOT / "tests/starlink_oracle/local_admission_actual.py")
STUDY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STUDY)
ACQ = STUDY.ACQ
ACTUAL = ACQ / "build/bank-arithmetic-actual-candidate175-monitor-prepared-v3"


def env():
    return {k: v for k, v in os.environ.items() if k not in {"PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"}}


@pytest.fixture(scope="module", params=[0, 1])
def prepared(request, tmp_path_factory):
    output = tmp_path_factory.mktemp(f"L{request.param}") / "prepared"
    STUDY.freeze(output, ACTUAL, request.param)
    return output


def test_real_freeze_exact_closure_original_history_and_relative_standalone(prepared, tmp_path):
    manifest = STUDY.verify(prepared)
    assert len(manifest["runtime_rtl"]) == 8
    assert manifest["python_runtime_closure"] == ["local_admission_actual.py", "local_admission.py", "bank_arithmetic_actual.py"]
    source = prepared / "frozen_sources"
    assert "automation_FAIL" in manifest["original_history"]
    assert "run_status=1" in (source / "history_run_outcome.txt").read_text()
    assert "after_status=0" in (source / "history_run_outcome.txt").read_text()
    for name, expected in STUDY.HISTORY_FILES.items():
        assert STUDY.digest((source / name).read_bytes()) == expected
    result = subprocess.run([sys.executable, "-B", str(source / "local_admission_actual.py"), "verify",
                             os.path.relpath(prepared, tmp_path), "--expected", STUDY.digest((prepared / "manifest.json").read_bytes())],
                            cwd=tmp_path, env=env(), capture_output=True, text=True, timeout=20, check=False)
    (tmp_path / "standalone.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stderr
    assert not (prepared / "project").exists() and not (prepared / "launch_started.txt").exists()
    assert not list(source.rglob("__pycache__"))
    with pytest.raises(FileExistsError):
        STUDY.freeze(prepared, ACTUAL, manifest["L"])


def test_strict_inverse_preserves_all_stimulus_faults_and_two_119bit_boundaries(prepared):
    source = prepared / "frozen_sources"
    old = (source / (STUDY.OLD_BENCH + ".sv")).read_text()
    derived = (source / (STUDY.BENCH + ".sv")).read_text()
    assert STUDY.adapt(derived, STUDY.edits_bench(), True) == old
    assert derived.count("dut.product.arithmetic.output_overflow") == 2
    assert re.findall(r"force .*?;", derived) == re.findall(r"force .*?;", old)
    assert re.findall(r"\$fatal.*?;", derived) == re.findall(r"\$fatal.*?;", old)
    for name, original, edits in (
        (STUDY.RUNNER, "simulate_bank_arithmetic_actual.tcl", STUDY.edits_runner()),
        (STUDY.DIAGNOSTICS, "simulate_bank_arithmetic_diagnostics.tcl", (("run all\n", STUDY.wave_add(STUDY.verify(prepared)["L"]) + "run all\n"),)),
    ):
        assert STUDY.adapt((source / name).read_text(), edits, True) == (source / original).read_text()


@pytest.mark.parametrize("which", ["bench", "runner"])
def test_missing_and_duplicated_every_exact_adaptation_anchor(which):
    name, edits = (("tb/" + STUDY.OLD_BENCH + ".sv", STUDY.edits_bench()) if which == "bench"
                   else ("simulate_bank_arithmetic_actual.tcl", STUDY.edits_runner()))
    original = (ACQ / name).read_text()
    for before, _ in edits:
        for text in (original.replace(before, "", 1), original + before):
            with pytest.raises(ValueError, match="nonunique"):
                STUDY.adapt(text, edits)


@pytest.mark.parametrize("mutation", ["delete", "extra", "symlink", "runtime", "old_check", "helper", "profile", "bound", "manifest", "synthetic"])
def test_frozen_inventory_or_contract_mutation_rejected(prepared, tmp_path, mutation):
    output = tmp_path / "copy"
    shutil.copytree(prepared, output)
    source = output / "frozen_sources"
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if mutation == "delete":
        (source / STUDY.OBSERVER).unlink()
    elif mutation == "extra":
        (source / "unexpected").write_text("extra")
    elif mutation == "symlink":
        (source / "alias").symlink_to(source / STUDY.OBSERVER)
    elif mutation == "bound":
        manifest["old_bounds"]["fault_observation_fast_cycles"] += 1
    elif mutation == "manifest":
        manifest["O"] = 0
    else:
        name = {"runtime": "starlink_pss_realtime_input_guard_local_admission.v",
                "old_check": STUDY.BENCH + ".sv", "helper": "local_admission.py",
                "profile": "profile.tcl", "synthetic": "unexpected.v"}[mutation]
        target = source / name
        text = target.read_text() if target.exists() else ""
        if mutation == "old_check":
            text = text.replace("inverse final fault missed current veto", "REMOVED_CURRENT_VETO")
        elif mutation == "profile":
            text = text.replace("set R 1", "set R 0")
        elif mutation == "synthetic":
            text = "module starlink_pss_fft512_bfp18_rt_candidate; endmodule\n"
        else:
            text += "\n// changed\n"
        target.write_text(text)
        # Rehash selected mutations to demonstrate semantic/inverse/source gates.
        manifest["source_sha256"][name] = STUDY.digest(target.read_bytes())
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises((ValueError, KeyError, FileNotFoundError)):
        STUDY.verify(output)


def guard_harness(option, mutation):
    checks = (ACQ / "tb" / STUDY.CHECKS).read_text().replace("dut.input_guard", "dut")
    changed = "" if mutation is None else f"force dut.{mutation} = ~dut.{mutation}; #1;"
    return f"""`timescale 1ns/1fs
// OFFLINE_GUARD_ONLY: no FFT or bank transactor is compiled or exercised.
module offline_guard;
  parameter integer L={option}, R=1, B=1, O=1, FAST_MHZ=175, QUICK_MUTATION=0;
  reg clk=0; always #5 clk=~clk;
  reg resetn=0,job_start=0,input_enable=0,input_valid=0,input_last=0,core_input_tready=0;
  reg [69:0] job_descriptor=0,input_metadata=0;
  reg [35:0] input_data=0;
  reg [8:0] input_position=0;
  starlink_pss_realtime_input_guard_local_admission #(.BALANCED_IDENTITY_EQ(1),.LOCAL_FIRST_ADMISSION(L)) dut (
    .clk(clk),.resetn(resetn),.job_start(job_start),.job_descriptor(job_descriptor),
    .input_enable(input_enable),.input_valid(input_valid),.input_data(input_data),
    .input_position(input_position),.input_last(input_last),.input_metadata(input_metadata),.core_input_tready(core_input_tready));
  {checks}
  task tick; begin @(negedge clk); #1; end endtask
  task purge; begin resetn=0;job_start=0;input_valid=0;input_enable=0;core_input_tready=0;tick();resetn=1;tick();end endtask
  integer n,phase;
  initial begin
    #1; purge();
    for(phase=0;phase<2;phase=phase+1) begin
      job_descriptor=70'h123456789abcdef01;job_descriptor[69]=phase;input_metadata=job_descriptor;
      input_position=0;input_last=0;job_start=1;tick();job_start=0;input_enable=1;
      for(n=0;n<512;n=n+1) begin
        input_position=n;input_last=(n==511);input_data={{18'(n),18'(~n)}};
        if(n%7==0) begin input_valid=0;core_input_tready=0;input_data=36'bx;tick();input_data=36'bz;tick();end
        input_valid=1;core_input_tready=1;tick();
      end
      job_descriptor=~job_descriptor;input_metadata=~input_metadata;input_position=0;input_last=0;tick();
      job_start=1;tick();job_start=0;tick();purge();
    end
    job_descriptor=70'h200000000000000013;input_metadata=job_descriptor;job_start=1;tick();job_start=0;input_enable=1;input_valid=1;core_input_tready=0;
    {changed}
    input_metadata=70'bx;tick();input_metadata=70'bz;tick();purge();
    if(local_guard_observer.pre_checks<1024 || local_guard_observer.post_checks<1024 || !local_guard_observer.reset_checks || !local_guard_observer.duplicate_checks)
      $fatal(1,"OFFLINE_GUARD_OBSERVER_COVERAGE_MISSING");
    $display("OFFLINE_GUARD_OBSERVER_PASS L=%0d no_fft=1",L);$finish(0);
  end
  initial begin #100000; $fatal(1,"OFFLINE_GUARD_TIMEOUT"); end
endmodule
"""


@pytest.mark.parametrize("option", [0, 1])
@pytest.mark.parametrize("mutation", [None, "descriptor", "job_started", "input_started", "expected_position", "input_complete", "fault_reasons", "certified_input_beat", "core_input_tdata", "input_ready"])
def test_independent_full_observer_real_guard_state_output_corruption_and_xz_reset(tmp_path, option, mutation):
    recipe = STUDY.load("local_admission")
    original = (ACQ / (recipe.OLD_GUARD + ".v")).read_text().replace("module " + recipe.OLD_GUARD, "module local_admission_original_guard", 1)
    (tmp_path / "original.v").write_text(original)
    shutil.copy(ACQ / (recipe.GUARD + ".v"), tmp_path / "candidate.v")
    shutil.copy(ACQ / "tb" / STUDY.OBSERVER, tmp_path / "observer.sv")
    (tmp_path / "test.sv").write_text(guard_harness(option, mutation))
    compile_result = subprocess.run(["iverilog", "-g2012", "-s", "offline_guard", "-o", "sim", "original.v", "candidate.v", "observer.sv", "test.sv"], cwd=tmp_path, env=env(), capture_output=True, text=True, timeout=15, check=False)
    (tmp_path / "compile.log").write_text(compile_result.stdout + compile_result.stderr)
    assert compile_result.returncode == 0, compile_result.stderr
    result = subprocess.run(["vvp", "sim"], cwd=tmp_path, env=env(), capture_output=True, text=True, timeout=15, check=False)
    log = result.stdout + result.stderr
    (tmp_path / "simulate.log").write_text(log)
    if mutation:
        assert result.returncode != 0 and "LOCAL_GUARD_UNCONDITIONAL_STATE_OUTPUT_MISMATCH" in log, log
    else:
        assert result.returncode == 0 and log.strip() == f"OFFLINE_GUARD_OBSERVER_PASS L={option} no_fft=1", log


def good_guard(option=1):
    return (f"LOCAL_ADMISSION_ACTUAL_PASS L={option} R=1 B=1 O=1 width=155 pre_checks=4096 post_checks=4096 reset_checks=2 "
            "forward_starts=38 inverse_starts=38 current_faults=1 sticky_faults=1 completed_checks=1 closed_prefetch=1 duplicate_checks=1 "
            "full_unconditional_state_outputs=1 original_guard_literal=1 default_omitted=1 added_latency=0\n")


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown", "wrong_L", "reset", "partial", "latency", "mask", "duplicate_key", "late_FAIL", "late_ERROR", "late_FATAL", "early_MISMATCH"])
def test_terminal_contract_is_exact_and_late_failure_always_rejected(mutation):
    log = good_guard()
    assert STUDY.require_guard_terminal(log, 1)["width"] == 155
    if mutation == "missing": log = ""
    elif mutation == "duplicate": log += log
    elif mutation == "unknown": log = log.replace("width=155", "width=x")
    elif mutation == "wrong_L": log = log.replace("L=1", "L=0")
    elif mutation == "reset": log = log.replace("reset_checks=2", "reset_checks=0")
    elif mutation == "partial": log = log.replace("forward_starts=38", "forward_starts=37")
    elif mutation == "latency": log = log.replace("added_latency=0", "added_latency=1")
    elif mutation == "mask": log = log.replace("full_unconditional_state_outputs=1", "full_unconditional_state_outputs=0")
    elif mutation == "duplicate_key": log = log.replace("width=155", "width=155 width=155")
    elif mutation.startswith("late_"): log += mutation + "\n"
    else: log = mutation + "\n" + log
    with pytest.raises(ValueError): STUDY.require_guard_terminal(log, 1)


def test_exact_guard_wave_inventory_and_original_run_all_preserved(prepared):
    option = STUDY.verify(prepared)["L"]
    receipt = "LOCAL_GUARD_WAVE_DIAGNOSTICS_ENABLED objects=14 width=155\n"
    inventory = "".join(f"/{STUDY.BENCH}/local_guard_observer/{name}\n" for name in STUDY.WAVE_FIELDS)
    arithmetic = f"/{STUDY.BENCH}/dut/product_overflow\n"
    assert len(STUDY.require_guard_wave(receipt, inventory, option, arithmetic)) == 14
    for changed in (inventory + inventory, inventory.replace("original_view", "masked_view"), inventory.split("\n", 1)[1]):
        with pytest.raises(ValueError): STUDY.require_guard_wave(receipt, changed, option, arithmetic)
    runner = (prepared / "frozen_sources" / STUDY.DIAGNOSTICS).read_text()
    assert runner.count("run all") == 1
    assert "force " not in runner and "run " not in STUDY.wave_add(option)
    assert runner.count("WRONLY CREAT EXCL") == 4


def mock_runner(tmp_path, option, behavior):
    output = tmp_path / "prepared"
    STUDY.freeze(output, ACTUAL, option)
    source = output / "frozen_sources"
    expected = STUDY.digest((output / "manifest.json").read_bytes())
    wrapper = next((ACTUAL / "project").glob("*.gen/sources_1/ip/*/synth/*.vhd"))
    commands = """proc version {args} {return 2022.2}
proc set_param {args} {}
proc create_project {name directory args} {file mkdir $directory}
proc current_project {args} {return mocked}
proc set_property {args} {}
proc get_ips {args} {return {}}
proc create_ip {args} {}
proc add_files {args} {}
proc get_filesets {args} {return sim_1}
proc get_files {args} {return {}}
proc close_sim {args} {}
proc close_project {args} {}
"""
    commands += f"proc generate_target {{args}} {{file mkdir [file dirname $::wrapper]; file copy {{{wrapper}}} $::wrapper}}\n"
    if behavior == "preproject":
        commands += "proc create_project {args} {error OFFLINE_PREPROJECT_STOP}\n"
    if behavior in ("launch", "mutation", "environment"):
        commands += "proc launch_simulation {args} {\n"
        if behavior == "mutation":
            commands += "set c [open [file join $::source_dir starlink_pss_kernel_rom.v] a]; puts $c MUTATED; close $c\n"
        if behavior == "environment":
            commands += "foreach name {PYTHONHOME PYTHONPATH LD_LIBRARY_PATH} {if {$::env($name) ne {/invalid-vendor}} {error PARENT_ENV_CHANGED}}\n"
        commands += "error OFFLINE_LAUNCH_STOP\n}\n"
    else:
        commands += "proc launch_simulation {args} {}\n"
    if behavior == "postmutation":
        commands += """rename exec real_exec
proc exec {args} {
  if {[lsearch -exact $args results] >= 0} {return MOCK_RESULT_NOT_ACTUAL}
  return [uplevel 1 [linsert $args 0 real_exec]]
}
proc close_project {args} {
  set c [open [file join $::source_dir starlink_pss_kernel_rom.v] a]; puts $c MUTATED; close $c
}
"""
    python = sys.executable
    if behavior == "environment":
        probe = tmp_path / "python-env-probe"
        probe.write_text("#!/usr/bin/python3\nimport os,sys\n"
                         "assert not any(name in os.environ for name in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH'))\n"
                         "assert sys.argv[1] == '-B'\n"
                         f"os.execv({sys.executable!r}, [{sys.executable!r}] + sys.argv[1:])\n")
        probe.chmod(0o700)
        python = str(probe)
    commands += f"set argc 3\nset argv [list {{{output}}} {{{python}}} {expected}]\nsource {{{source / STUDY.RUNNER}}}\n"
    mock = tmp_path / "mock-NOT-Vivado.tcl"
    mock.write_text(commands)
    run_env = env()
    if behavior == "environment":
        run_env.update(dict.fromkeys(("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"), "/invalid-vendor"))
    result = subprocess.run(["tclsh", str(mock)], cwd="/", env=run_env, capture_output=True, text=True, timeout=25, check=False)
    (tmp_path / "mock.log").write_text(result.stdout + result.stderr)
    return output, result, mock


@pytest.mark.parametrize("option", [0, 1])
@pytest.mark.parametrize("behavior", ["preproject", "launch", "mutation", "postcheck", "postmutation", "environment"])
def test_frozen_runner_mock_only_error_options_after_integrity_and_no_success(tmp_path, option, behavior):
    output, result, mock = mock_runner(tmp_path, option, behavior)
    assert result.returncode != 0
    outcome = (output / "run_outcome.txt").read_text()
    assert "after_status=1" in outcome if "mutation" in behavior else "after_status=0" in outcome
    assert "run_status=0" in outcome if behavior == "postmutation" else "run_status=1" in outcome
    assert not (output / "results.json").exists()
    assert "LOCAL_ADMISSION_ACTUAL_CORE_VERIFIED" not in result.stdout
    if behavior == "preproject": assert not (output / "project").exists()
    if behavior == "environment":
        assert "OFFLINE_LAUNCH_STOP" in result.stderr and "PARENT_ENV_CHANGED" not in outcome
        assert not list((output / "frozen_sources").rglob("__pycache__"))
    again = subprocess.run(["tclsh", str(mock)], env=env(), capture_output=True, text=True, timeout=15, check=False)
    (tmp_path / "mock-again.log").write_text(again.stdout + again.stderr)
    assert again.returncode != 0 and "refusing actual launch restart or overwrite" in again.stderr


def test_observer_reads_only_actual_input_ports_and_no_epoch_fault_or_valid_mask():
    checks = (ACQ / "tb" / STUDY.CHECKS).read_text()
    ports = ("clk", "resetn", "job_start", "job_descriptor", "input_enable", "input_valid", "input_data",
             "input_position", "input_last", "input_metadata", "core_input_tready")
    for name in ports:
        assert f".{name}(dut.input_guard.{name})" in checks
    observer = (ACQ / "tb" / STUDY.OBSERVER).read_text()
    assert "actual_view !== original_view || default_view !== original_view" in observer
    assert "expected_fault" not in observer and "epoch" not in observer
    assert "always @(posedge clk or negedge clk)" in observer
    assert "always @(negedge resetn)" in observer
    assert not re.search(r"(?m)^\s*force\s", observer + checks)
    assert "local_admission_original_guard" in observer
    assert ".LOCAL_FIRST_ADMISSION(" not in observer


def test_whole_derived_bench_elaboration_missing_vendor_syntax_only(prepared, tmp_path):
    manifest = STUDY.verify(prepared)
    source = prepared / "frozen_sources"
    command = ["iverilog", "-g2012", "-i", "-s", STUDY.BENCH, "-I", str(source),
               f"-P{STUDY.BENCH}.FAST_MHZ=175", f"-P{STUDY.BENCH}.R=1", f"-P{STUDY.BENCH}.B=1", f"-P{STUDY.BENCH}.O=1",
               f"-P{STUDY.BENCH}.L={manifest['L']}", "-o", str(tmp_path / "SYNTAX_ONLY_DO_NOT_RUN")]
    command += [str(source / name) for name in manifest["compiled"]]
    result = subprocess.run(command, env=env(), capture_output=True, text=True, timeout=20, check=False)
    (tmp_path / "syntax-command.json").write_text(json.dumps(command))
    (tmp_path / "syntax.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stderr
    # No vvp invocation: vendor module is absent and no arithmetic claims follow.


@pytest.mark.parametrize("mutation", ["omit_forwarding", "bad_negative", "bad_two", "bad_x", "bad_z"])
def test_actual_hierarchy_option_readback_invalid_or_omitted_forwarding(tmp_path, mutation):
    recipe = STUDY.load("local_admission")
    (tmp_path / "original.v").write_text((ACQ / (recipe.OLD_GUARD + ".v")).read_text().replace(
        "module " + recipe.OLD_GUARD, "module local_admission_original_guard", 1))
    shutil.copy(ACQ / (recipe.GUARD + ".v"), tmp_path / "candidate.v")
    shutil.copy(ACQ / "tb" / STUDY.OBSERVER, tmp_path / "observer.sv")
    source = guard_harness(1, None)
    if mutation == "omit_forwarding":
        source = source.replace(",.LOCAL_FIRST_ADMISSION(L)", "")
    else:
        value = {"bad_negative": "-1", "bad_two": "2", "bad_x": "1'bx", "bad_z": "1'bz"}[mutation]
        source = source.replace("parameter integer L=1,", "parameter integer L=" + value + ",")
    (tmp_path / "test.sv").write_text(source)
    result = subprocess.run(["iverilog", "-g2012", "-s", "offline_guard", "-o", "sim", "original.v", "candidate.v", "observer.sv", "test.sv"], cwd=tmp_path, env=env(), capture_output=True, text=True, timeout=15, check=False)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(["vvp", "sim"], cwd=tmp_path, env=env(), capture_output=True, text=True, timeout=15, check=False)
    (tmp_path / "simulate.log").write_text(result.stdout + result.stderr)
    assert result.returncode != 0
    assert "LOCAL_ADMISSION_ACTUAL_INSTANCE_BINDING_MISMATCH" in result.stdout if mutation == "omit_forwarding" else "LOCAL_FIRST_ADMISSION must be zero or one" in result.stdout


def policy_result_files(output):
    """Mock result collector only; never label these copied fixtures an actual run."""
    source_sim = ACTUAL / "project/fft_bank_arithmetic_actual.sim/sim_1/behav/xsim"
    sim = output / "project/fft_bank_arithmetic_actual.sim/sim_1/behav/xsim"
    sim.mkdir(parents=True)
    for name in ("simulate.log", "bank_arithmetic_events.csv", "fft_bank_owned_trace.csv", "arithmetic_diagnostic_signals.txt"):
        shutil.copy(source_sim / name, sim / name)
    manifest = STUDY.verify(output)
    shutil.copy(output / "frozen_sources/failed_actual_arithmetic_diagnostic_signals.txt", sim / "arithmetic_diagnostic_signals.txt")
    with (sim / "simulate.log").open("a") as stream:
        stream.write(good_guard(manifest["L"]))
    (sim / "arithmetic_diagnostic_receipt.txt").write_text("ARITHMETIC_WAVE_DIAGNOSTICS_ENABLED objects=115 monitors=4 references=2 wrapper=1 inner=1 transport=1\n")
    (sim / "local_guard_diagnostic_receipt.txt").write_text("LOCAL_GUARD_WAVE_DIAGNOSTICS_ENABLED objects=14 width=155\n")
    root = STUDY.allowed_wave_roots(manifest["L"])[1]
    (sim / "local_guard_diagnostic_signals.txt").write_text("".join(f"{root}/local_guard_observer/{name}\n" for name in STUDY.WAVE_FIELDS))
    wrapper = next((ACTUAL / "project").glob("*.gen/sources_1/ip/*/synth/*.vhd"))
    copied = output / "project/generated-source.vhd"
    shutil.copy(wrapper, copied)
    receipt = STUDY.digest(copied.read_bytes()) + "  " + str(copied) + "\n"
    for stage in ("before", "after"):
        (output / f"generated_ip_{stage}.txt").write_text(receipt)
    (output / "launch_started.txt").write_text(f"actual_fft=true R=1 B=1 O=1 frequency=175 L={manifest['L']} no_restart=true\n")
    return sim


@pytest.mark.parametrize("mutation", [None, "late_error", "old_marker", "guard_marker", "trace", "event", "ip", "wave"])
def test_complete_postprocessor_keeps_original_numeric_fault_cycle_trace_and_new_observer_gates(tmp_path, mutation):
    output = tmp_path / "MOCK_ONLY_NOT_AN_ACTUAL_RUN"
    STUDY.freeze(output, ACTUAL, 1)
    sim = policy_result_files(output)
    if mutation == "late_error":
        with (sim / "simulate.log").open("a") as stream: stream.write("ERROR late fault after PASS\n")
    elif mutation in ("old_marker", "guard_marker"):
        path = sim / "simulate.log"
        path.write_text(path.read_text().replace("HELD_PHASE_INPUT_PASS" if mutation == "old_marker" else "LOCAL_ADMISSION_ACTUAL_PASS", "REMOVED_TERMINAL"))
    elif mutation == "trace":
        with (sim / "fft_bank_owned_trace.csv").open("a") as stream: stream.write("changed\n")
    elif mutation == "event":
        path = sim / "bank_arithmetic_events.csv"
        path.write_text(path.read_text().replace(",forward,0,", ",forward,1,", 1))
    elif mutation == "ip":
        (output / "generated_ip_after.txt").write_text("changed\n")
    elif mutation == "wave":
        (sim / "local_guard_diagnostic_receipt.txt").unlink()
    expected = STUDY.digest((output / "manifest.json").read_bytes())
    if mutation:
        with pytest.raises((ValueError, FileNotFoundError)):
            STUDY.results(output, expected)
    else:
        receipt = STUDY.results(output, expected)
        assert len(receipt["receipts"]) == 11
        assert receipt["events"]["output_derived_exact_sample_scores"] == 16986
        assert receipt["trace_sha256"] == STUDY.HISTORICAL_CANDIDATE_CSV
    assert not (output / "results.json").exists()


@pytest.mark.parametrize("kind", ["output", "dangling_output", "parent", "dangling_parent", "dotdot_parent"])
def test_preparation_rejects_lexical_output_alias_before_normalization(tmp_path, kind):
    target = tmp_path / "target"
    target.mkdir()
    (target / "sentinel").write_text("untouched")
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path / "missing" if "dangling" in kind else target, target_is_directory=True)
    output = alias if "output" in kind else alias / "prepared"
    if kind == "dotdot_parent":
        output = alias / ".." / "prepared"
    with pytest.raises(ValueError, match="symlink"):
        STUDY.freeze(output, ACTUAL, 1)
    assert sorted(p.name for p in target.iterdir()) == ["sentinel"]
    assert (target / "sentinel").read_text() == "untouched"
    assert not (tmp_path / "missing").exists()
    assert not (tmp_path / "prepared").exists()


@pytest.mark.parametrize("kind", ["root", "parent", "frozen_sources", "dangling_source", "manifest", "outcome"])
def test_original_source_root_and_frozen_input_aliases_rejected(tmp_path, kind):
    original = tmp_path / "original"
    if kind == "root":
        original.symlink_to(ACTUAL, target_is_directory=True)
    elif kind == "parent":
        original.symlink_to(ACTUAL.parent, target_is_directory=True)
        original = original / ACTUAL.name
    else:
        original.mkdir()
        for name in ("manifest.json", "run_outcome.txt"):
            shutil.copy(ACTUAL / name, original / name)
        if kind in ("frozen_sources", "dangling_source"):
            (original / "frozen_sources").symlink_to(
                ACTUAL / "frozen_sources" if kind == "frozen_sources" else tmp_path / "missing", target_is_directory=True)
        else:
            (original / "frozen_sources").mkdir()
            name = "manifest.json" if kind == "manifest" else "run_outcome.txt"
            (original / name).unlink()
            (original / name).symlink_to(ACTUAL / name)
    output = tmp_path / "never-created"
    with pytest.raises(ValueError, match="symlink"):
        STUDY.freeze(output, original, 1)
    assert not output.exists()


@pytest.mark.parametrize("kind", ["root", "parent", "dangling_root", "source", "dangling_source", "manifest"])
def test_verifier_rejects_lexical_alias_even_when_target_matches_expected(prepared, tmp_path, kind):
    expected = STUDY.digest((prepared / "manifest.json").read_bytes())
    if kind in ("root", "parent", "dangling_root"):
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path / "missing" if kind == "dangling_root" else prepared.parent if kind == "parent" else prepared, target_is_directory=True)
        output = alias / prepared.name if kind == "parent" else alias
    else:
        output = tmp_path / "copy"
        output.mkdir()
        if kind == "manifest":
            (output / "manifest.json").symlink_to(prepared / "manifest.json")
        else:
            shutil.copy(prepared / "manifest.json", output / "manifest.json")
            (output / "frozen_sources").symlink_to(
                prepared / "frozen_sources" if kind == "source" else tmp_path / "missing", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        STUDY.verify(output, expected)


def test_missing_sources_and_existing_destination_fail_before_any_write(tmp_path):
    output = tmp_path / "never-created"
    with pytest.raises(FileNotFoundError):
        STUDY.freeze(output, tmp_path / "missing", 1)
    assert not output.exists()
    output.mkdir()
    (output / "sentinel").write_text("retained")
    with pytest.raises(FileExistsError):
        STUDY.freeze(output, ACTUAL, 1)
    assert sorted(p.name for p in output.iterdir()) == ["sentinel"]


@pytest.mark.parametrize("kind", ["output", "parent", "runner", "dotdot"])
def test_frozen_tcl_rejects_alias_before_file_normalize(prepared, tmp_path, kind):
    output = prepared
    runner = prepared / "frozen_sources" / STUDY.RUNNER
    alias = tmp_path / "alias"
    if kind == "output":
        alias.symlink_to(prepared, target_is_directory=True)
        output = alias
    elif kind == "parent":
        alias.symlink_to(prepared.parent, target_is_directory=True)
        output = alias / prepared.name
    elif kind == "runner":
        alias.symlink_to(runner)
        runner = alias
    else:
        alias.symlink_to(prepared, target_is_directory=True)
        output = alias / ".." / prepared.name
    expected = STUDY.digest((prepared / "manifest.json").read_bytes())
    mock = tmp_path / "mock-alias.tcl"
    mock.write_text(f"set argc 3\nset argv [list {{{output}}} {{{sys.executable}}} {expected}]\nsource {{{runner}}}\n")
    result = subprocess.run(["tclsh", str(mock)], env=env(), capture_output=True, text=True, timeout=10, check=False)
    (tmp_path / "alias.log").write_text(result.stdout + result.stderr)
    assert result.returncode != 0 and "symlink actual output/runner path forbidden" in result.stderr
    assert not (prepared / "preflight.json").exists() and not (prepared / "launch_started.txt").exists()


def diagnostic_fixture(prepared, escaped=True):
    option = STUDY.verify(prepared)["L"]
    observed = (prepared / "frozen_sources/failed_actual_arithmetic_diagnostic_signals.txt").read_text()
    assert STUDY.digest(observed.encode()) == STUDY.FIXED["failed_actual_arithmetic_diagnostic_signals.txt"]
    real_root = "/" + observed.splitlines()[0].split("/")[1]
    assert real_root == STUDY.allowed_wave_roots(1)[1]
    root = STUDY.allowed_wave_roots(option)[int(escaped)]
    arithmetic = observed.replace(real_root, root).splitlines()
    guards = [f"{root}/local_guard_observer/{name}" for name in STUDY.WAVE_FIELDS]
    return option, root, arithmetic, guards


@pytest.mark.parametrize("escaped", [False, True])
def test_archived_root_fixture_and_mocked_complete_tcl_reaches_original_run_all(prepared, tmp_path, escaped):
    option, _, arithmetic, guards = diagnostic_fixture(prepared, escaped)
    result = execute_diagnostic_mock(prepared, tmp_path, arithmetic + guards)
    assert result.returncode == 1 and "OFFLINE_UNCHANGED_RUN_ALL_TRAP" in result.stdout, result.stdout + result.stderr
    assert "LOCAL_GUARD_WAVE_" not in result.stderr
    receipt = (tmp_path / "local_guard_diagnostic_receipt.txt").read_text()
    inventory = (tmp_path / "local_guard_diagnostic_signals.txt").read_text()
    assert inventory == "\n".join(guards) + "\n"
    assert STUDY.require_guard_wave(receipt, inventory, option, "\n".join(arithmetic) + "\n") == guards
    assert (tmp_path / "arithmetic_diagnostic_signals.txt").read_text() == "\n".join(arithmetic) + "\n"


def execute_diagnostic_mock(prepared, directory, objects):
    # Braced Tcl list preserves exact backslashes/spaces; nothing is eval'd.
    values = " ".join("{" + value + "}" for value in objects)
    program = """proc current_wave_config {args} {return existing_offline_wave}
proc get_objects {args} {
  if {$args ne {-r *}} {error "UNREVIEWED_LITERAL_LOOKUP"}
  return $::offline_objects
}
proc log_wave {args} {}
proc run {args} {
  if {$args ne {all}} {error "ORIGINAL_RUN_ARGUMENT_CHANGED"}
  puts OFFLINE_UNCHANGED_RUN_ALL_TRAP
  error "OFFLINE_STOP_NO_SIMULATION"
}
"""
    program += f"set offline_objects [list {values}]\nsource {{{prepared / 'frozen_sources' / STUDY.DIAGNOSTICS}}}\n"
    script = directory / "diagnostic-mock-NO-Vivado.tcl"
    script.write_text(program)
    result = subprocess.run(["tclsh", str(script)], cwd=directory, env=env(), capture_output=True, text=True, timeout=10, check=False)
    (directory / "diagnostic-mock.log").write_text(result.stdout + result.stderr)
    return result


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "mixed", "wrong_profile", "arithmetic_root", "nested", "injection", "unknown_leaf"])
def test_tcl_and_parser_reject_root_leaf_profile_and_path_injection(prepared, tmp_path, mutation):
    option, root, arithmetic, guards = diagnostic_fixture(prepared)
    if mutation == "duplicate": guards.append(guards[0])
    elif mutation == "missing": guards.pop(0)
    elif mutation == "mixed": guards[0] = guards[0].replace(root, STUDY.allowed_wave_roots(option)[0])
    elif mutation == "wrong_profile":
        guards = [path.replace("O=1", "O=0") for path in guards]
        arithmetic = [path.replace("O=1", "O=0") for path in arithmetic]
    elif mutation == "arithmetic_root": arithmetic = [path.replace(root, STUDY.allowed_wave_roots(option)[0]) for path in arithmetic]
    elif mutation == "nested": guards[0] = guards[0].replace("/local_guard_observer/", "/nested/local_guard_observer/")
    elif mutation == "injection": guards[0] = guards[0].replace("/local_guard_observer/", "/[exec touch UNAUTHORIZED]/local_guard_observer/")
    else: guards[0] = guards[0].replace("/actual_view", "/unknown_view")
    result = execute_diagnostic_mock(prepared, tmp_path, arithmetic + guards)
    assert result.returncode == 1 and "OFFLINE_UNCHANGED_RUN_ALL_TRAP" not in result.stdout
    assert "LOCAL_GUARD_WAVE_" in result.stderr
    assert not (tmp_path / "local_guard_diagnostic_receipt.txt").exists()
    assert not (tmp_path / "UNAUTHORIZED").exists()
    with pytest.raises(ValueError):
        STUDY.require_guard_wave("LOCAL_GUARD_WAVE_DIAGNOSTICS_ENABLED objects=14 width=155\n", "\n".join(guards) + "\n", option, "\n".join(arithmetic) + "\n")


def test_diagnostic_fix_changes_no_compiled_runtime_observer_bench_numeric_or_runner_bytes(prepared):
    # Preserve the original v2->v3 diagnostic-only claim against its immutable
    # sources; the new scheduling revision is checked independently below.
    option = STUDY.verify(prepared)["L"]
    prepared = ACQ / f"build/local-admission-actual-R1B1O1-L{option}-175-prepared-v3"
    manifest = json.loads((prepared / "manifest.json").read_text())
    old = ACQ / f"build/local-admission-actual-R1B1O1-L{manifest['L']}-175-prepared-v2"
    old_manifest = json.loads((old / "manifest.json").read_text())
    changed = {name for name, expected in old_manifest["source_sha256"].items()
               if manifest["source_sha256"].get(name) != expected}
    assert changed == {"local_admission_actual.py", "test_starlink_local_admission_actual_policy.py", STUDY.DIAGNOSTICS}
    assert set(manifest["source_sha256"]) - set(old_manifest["source_sha256"]) == {"failed_actual_arithmetic_diagnostic_signals.txt"}
    for key in old_manifest:
        if key != "source_sha256": assert old_manifest[key] == manifest[key]
    for name in manifest["compiled"] + [STUDY.CHECKS, STUDY.RUNNER, "starlink_pss_bank_arithmetic_actual_checks.svh"]:
        assert (prepared / "frozen_sources" / name).read_bytes() == (old / "frozen_sources" / name).read_bytes()


def test_scheduling_revision_exact_two_waits_and_complete_old_stimulus_runtime_closure(prepared):
    manifest = STUDY.verify(prepared)
    old = ACQ / f"build/local-admission-actual-R1B1O1-L{manifest['L']}-175-prepared-v3"
    old_manifest = json.loads((old / "manifest.json").read_text())
    changed = {name for name, expected in old_manifest["source_sha256"].items()
               if manifest["source_sha256"].get(name) != expected}
    assert changed == {"local_admission_actual.py", "test_starlink_local_admission_actual_policy.py", STUDY.OBSERVER}
    assert set(manifest["source_sha256"]) - set(old_manifest["source_sha256"]) == {
        STUDY.OBSERVER_REFERENCE, STUDY.SCHEDULE_BENCH, STUDY.SCHEDULE_POLICY}
    assert len(manifest["source_sha256"]) == 49
    assert manifest["comparison_schedule"] == STUDY.COMPARISON_SCHEDULE
    assert set(manifest) - set(old_manifest) == {"comparison_schedule"}
    for key in old_manifest:
        if key != "source_sha256": assert old_manifest[key] == manifest[key]
    source = prepared / "frozen_sources"
    reference = (source / STUDY.OBSERVER_REFERENCE).read_text()
    assert reference == (old / "frozen_sources" / STUDY.OBSERVER).read_text()
    assert STUDY.adapt((source / STUDY.OBSERVER).read_text(), STUDY.edits_observer(), True) == reference
    for name in manifest["compiled"] + [STUDY.CHECKS, STUDY.RUNNER, STUDY.DIAGNOSTICS,
                                       "starlink_pss_bank_arithmetic_actual_checks.svh"]:
        if name != STUDY.OBSERVER:
            assert (source / name).read_bytes() == (old / "frozen_sources" / name).read_bytes()


@pytest.mark.parametrize("mutation", ["immediate", "post_only", "after_nba", "post_delay", "width",
                                    "predicate", "counter", "reset_event", "old_reference", "manifest"])
def test_rehashed_observer_scheduling_predicate_state_or_reference_changes_fail_closed(prepared, tmp_path, mutation):
    output = tmp_path / "changed"
    shutil.copytree(prepared, output)
    source = output / "frozen_sources"
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if mutation == "manifest":
        manifest["comparison_schedule"]["pre_region"] = "after_NBA"
    else:
        name = STUDY.OBSERVER_REFERENCE if mutation == "old_reference" else STUDY.OBSERVER
        text = (source / name).read_text()
        before, after = {
            "immediate": ("#0; compare(0);", "compare(0);"),
            "post_only": ("#0; compare(0);", "#0;"),
            "after_nba": ("#0; compare(0);", "#0.001; compare(0);"),
            "post_delay": ("#0.001; compare(1);", "#1; compare(1);"),
            "width": ("[154:0] actual_view", "[153:0] actual_view"),
            "predicate": ("actual_view !== original_view", "1'b0"),
            "counter": ("pre_checks=pre_checks+1", "pre_checks=pre_checks+2"),
            "reset_event": ("always @(negedge resetn)", "always @(posedge resetn)"),
            "old_reference": ("compare(0);", "#0; compare(0);"),
        }[mutation]
        assert text.count(before) == 1
        (source / name).write_text(text.replace(before, after))
        manifest["source_sha256"][name] = STUDY.digest((source / name).read_bytes())
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        STUDY.verify(output)
