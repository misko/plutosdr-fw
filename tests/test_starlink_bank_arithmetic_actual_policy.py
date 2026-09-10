"""Preparation, independent elastic shadow and strict actual launch/result policy."""
import csv
import itertools
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.starlink_oracle import bank_arithmetic_actual as study

VECTORS = Path("/home/mouse9911/gits/plutosdr-fw-starlink-rx-only/hdl/library/starlink_pss_raw_correlator/build/input-cursor-paired-v1/frozen_sources")
HISTORICAL = Path("/tmp/starlink-completed-input.5EaJuD/forward-retirement-actual-v1/project/fft_bank_owned_slice.sim/sim_1/behav/xsim")


def test_literal_inverse_and_unchanged_runtime_and_full_old_O0_reference():
    study.verify_adaptations()
    for name in ("starlink_pss_fft_bank_owned_slice.v", "starlink_pss_spectrum_product.v"):
        assert (study.ACQ / name).read_text() == study.original(name)
    shadow = (study.ACQ / "tb" / (study.NEW_SHADOW + ".sv")).read_text()
    assert "if (O == 0) begin : unchanged_reference" in shadow
    assert study.OLD_SHADOW + " #(.KERNEL_ROM_FILE(KERNEL_ROM_FILE)) reference (.*);" in shadow
    assert "dut." not in shadow and "operand_register" not in shadow
    assert study.sha(HISTORICAL / "fft_bank_owned_trace.csv") == study.HISTORICAL_R1_CSV


@pytest.mark.parametrize("anchor", ["inverse final fault missed current veto", "private core reset lost exact epoch input reasons",
                                    "late prefix fault lost evidence", "completed-input full shadow control/reasons mismatch"])
def test_original_control_fault_check_removal_cannot_restore(anchor):
    old = study.original("tb/" + study.OLD_BENCH + ".sv")
    new = study.adapt_bench(old)
    assert study.adapt_bench(new, inverse=True) == old
    assert study.adapt_bench(new.replace(anchor, "REMOVED"), inverse=True) != old


@pytest.mark.parametrize("frequency,b,o", [(175, 0, 0), (175, 1, 1), (200, 0, 0), (200, 1, 1)])
def test_real_preparation_full_source_and_import_freeze_without_Vivado(tmp_path, frequency, b, o):
    output = tmp_path / "prepared"
    result = study.freeze(output, VECTORS, frequency, 1, b, o)
    assert result == study.verify_freeze(output)
    assert not (output / "project").exists() and not (output / "launch_started.txt").exists()
    assert result["oracle"]["scores"] == 1341
    assert "tests/starlink_oracle/__init__.py" in result["python_import_sources"]
    assert "tests/starlink_oracle/xfft_bitacc.py" in result["python_import_sources"]
    assert "tests/test_starlink_bank_arithmetic_actual_policy.py" in result["python_import_sources"]
    assert all("offline_xfft" not in name for name in result["source_sha256"])
    with pytest.raises(ValueError, match="overwrite"):
        study.freeze(output, VECTORS, frequency, 1, b, o)


def test_relative_paths_normalized_before_child_cwd_and_frozen_standalone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    relative = os.path.relpath(VECTORS, tmp_path)
    study.freeze("prepared", relative, 175, 1, 0, 0)
    helper = tmp_path / "prepared/frozen_sources/bank_arithmetic_actual.py"
    child = subprocess.run([sys.executable, str(helper), "verify", str(tmp_path / "prepared")],
                           cwd="/", capture_output=True, text=True, timeout=20, check=False)
    (tmp_path / "standalone.log").write_text(child.stdout + child.stderr)
    assert child.returncode == 0, child.stderr


@pytest.mark.parametrize("b,o", [(0, 0), (1, 1)])
def test_actual_Tcl_reaches_only_mocked_create_project_after_real_freeze_checks(tmp_path, b, o):
    output = tmp_path / "p"
    study.freeze(output, VECTORS, 175, 1, b, o)
    runner = output / "frozen_sources/simulate_bank_arithmetic_actual.tcl"
    mock = tmp_path / "mock-Vivado-NOT-Vivado.tcl"
    mock.write_text("proc version {args} {return 2022.2}\nproc set_param {args} {}\n"
        "proc create_project {args} {error \"MOCK_PREPROJECT_STOP R=$::R B=$::B O=$::O\"}\n"
        f"set argc 2\nset argv [list {{{output}}} {{{sys.executable}}}]\nsource {{{runner}}}\n")
    result = subprocess.run(["tclsh", str(mock)], cwd="/", capture_output=True, text=True, timeout=20, check=False)
    (tmp_path / "mock-first.log").write_text(result.stdout + result.stderr)
    assert result.returncode != 0 and f"MOCK_PREPROJECT_STOP R=1 B={b} O={o}" in result.stderr
    assert not (output / "project").exists()
    # A mocked launch has no generated core/results and cannot pass as actual evidence.
    with pytest.raises(FileNotFoundError):
        study.verify_results(output)
    again = subprocess.run(["tclsh", str(mock)], capture_output=True, text=True, timeout=20, check=False)
    (tmp_path / "mock-second.log").write_text(again.stdout + again.stderr)
    assert "refusing actual launch restart" in again.stderr and "MOCK_PREPROJECT_STOP" not in again.stderr.split("while executing")[0]


def test_unfrozen_Tcl_cannot_launch_and_cannot_use_missing_python(tmp_path):
    mock = tmp_path / "unfrozen.tcl"
    mock.write_text(f"set argc 2\nset argv [list {{{tmp_path}}} {{{sys.executable}}}]\n"
                    f"source {{{study.ACQ / 'simulate_bank_arithmetic_actual.tcl'}}}\n")
    result = subprocess.run(["tclsh", str(mock)], capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode != 0 and "launch only the frozen runner" in result.stderr
    assert not (tmp_path / "project").exists()


def mock_full_Tcl(tmp_path, behavior, python=None):
    output = tmp_path / "p"
    study.freeze(output, VECTORS, 175, 1, 0, 0)
    runner = output / "frozen_sources/simulate_bank_arithmetic_actual.tcl"
    historical_wrapper = HISTORICAL.parents[3] / "fft_bank_owned_slice.gen/sources_1/ip/starlink_pss_fft512_bfp18_rt_candidate/synth/starlink_pss_fft512_bfp18_rt_candidate.vhd"
    assert historical_wrapper.is_file()
    source = """proc version {args} {return 2022.2}
proc set_param {args} {}
proc create_project {name directory args} {file mkdir $directory}
proc current_project {args} {return mock_project}
proc set_property {args} {}
proc get_ips {args} {return {}}
proc create_ip {args} {}
proc add_files {args} {}
proc get_filesets {args} {return sim_1}
proc get_files {args} {return {}}
proc close_sim {args} {}
proc close_project {args} {}
"""
    source += f"proc generate_target {{args}} {{file mkdir [file dirname $::wrapper]; file copy {{{historical_wrapper}}} $::wrapper}}\n"
    if behavior == "parent-env":
        source += """proc launch_simulation {args} {
  foreach name {PYTHONHOME PYTHONPATH LD_LIBRARY_PATH} {
    if {$::env($name) ne "/definitely-invalid-vendor-env"} {error "PARENT_ENV_CHANGED $name"}
  }
  return -code error -errorcode {MOCK LAUNCH} "MOCK_LAUNCH_FAILURE_PARENT_ENV_PRESERVED"
}
"""
    elif behavior in ("launch-failure", "launch-mutation"):
        source += "proc launch_simulation {args} {\n"
        if behavior == "launch-mutation":
            source += "set c [open [file join $::source_dir starlink_pss_kernel_rom.v] a]; puts $c { // injected MOCK mutation}; close $c\n"
        source += "return -code error -errorcode {MOCK LAUNCH} MOCK_LAUNCH_FAILURE\n}\n"
    else:
        source += "proc launch_simulation {args} {}\n"
        if behavior == "post-success-mutation":
            # This policy-only mock bypasses results intentionally to test the
            # runner's independent after-integrity path, not to claim a replay.
            source += """rename exec real_exec
proc exec {args} {
  if {[lsearch -exact $args results] >= 0} {
    set redirect [lsearch -exact $args >]
    if {$redirect >= 0} {
      set c [open [lindex $args [expr {$redirect+1}]] w]
      puts $c MOCK_RESULT_POSTPROCESS_ONLY; close $c
    }
    return MOCK_RESULT_POSTPROCESS_ONLY
  }
  return [uplevel 1 [linsert $args 0 real_exec]]
}
proc close_project {args} {
  set c [open [file join $::source_dir starlink_pss_kernel_rom.v] a]
  puts $c { // MOCK after-success mutation}; close $c
}
"""
    mock = tmp_path / "mock-Vivado-NOT-Vivado.tcl"
    mock.write_text(source + f"set argc 2\nset argv [list {{{output}}} {{{python or sys.executable}}}]\nsource {{{runner}}}\n")
    return output, mock


@pytest.mark.parametrize("behavior", ["launch-failure", "launch-mutation", "postcheck-failure", "post-success-mutation"])
def test_runner_always_retains_run_error_and_independent_after_integrity(tmp_path, behavior):
    output, mock = mock_full_Tcl(tmp_path, behavior)
    result = subprocess.run(["tclsh", str(mock)], capture_output=True, text=True, timeout=20, check=False)
    (tmp_path / "mock-run.log").write_text(result.stdout + result.stderr)
    assert result.returncode != 0
    assert "BANK_ARITHMETIC_ACTUAL_CORE_VERIFIED" not in result.stdout
    assert not (output / "results.json").exists()
    receipt = (output / "run_outcome.txt").read_text()
    if behavior.startswith("launch"):
        assert "MOCK_LAUNCH_FAILURE" in result.stderr and "MOCK LAUNCH" in receipt and "run_status=1" in receipt
    if "mutation" in behavior:
        assert "after_status=1" in receipt and "after-run frozen inventory/source/manifest changed" in receipt
    else:
        assert "after_status=0" in receipt and (output / "postflight.json").is_file()
    if behavior == "post-success-mutation":
        assert "run_status=0" in receipt
    if behavior == "postcheck-failure":
        assert "run_status=1" in receipt and "FileNotFoundError" in receipt


def test_python_child_sanitized_B_flag_parent_vendor_environment_preserved(tmp_path):
    probe = tmp_path / "python-child-env-probe"
    probe.write_text("#!/usr/bin/python3\nimport os,sys\n"
        "assert all(name not in os.environ for name in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH'))\n"
        "assert sys.argv[1] == '-B'\n"
        f"os.execv({sys.executable!r}, [{sys.executable!r}] + sys.argv[1:])\n")
    probe.chmod(0o700)
    output, mock = mock_full_Tcl(tmp_path, "parent-env", probe)
    env = dict(os.environ)
    env.update(dict.fromkeys(("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"), "/definitely-invalid-vendor-env"))
    result = subprocess.run(["tclsh", str(mock)], env=env, capture_output=True, text=True, timeout=20, check=False)
    (tmp_path / "mock-env.log").write_text(result.stdout + result.stderr)
    assert result.returncode != 0 and "MOCK_LAUNCH_FAILURE_PARENT_ENV_PRESERVED" in result.stderr
    assert "PARENT_ENV_CHANGED" not in (output / "run_outcome.txt").read_text()
    assert "after_status=0" in (output / "run_outcome.txt").read_text()
    assert not list((output / "frozen_sources").rglob("__pycache__"))


def test_all_actual_python_calls_share_sanitized_frozen_command():
    source = (study.ACQ / "simulate_bank_arithmetic_actual.tcl").read_text()
    assert "set python_command [list env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH $python -B" in source
    assert source.count("exec {*}$python_command") == 3
    assert source.index("} run_result run_options]") < source.index("set after_status [catch")
    assert source.index("} after_result after_options]") < source.index("if {$run_status}")
    assert "return -options $run_options $run_result" in source
    assert "return -options $after_options $after_result" in source
    assert source.index("if {$after_status}") < source.index("set channel [open [file join $output_dir results.json]")


def test_early_success_JSON_publication_mutant_is_detected_offline(tmp_path):
    output, mock = mock_full_Tcl(tmp_path, "post-success-mutation")
    runner = output / "frozen_sources/simulate_bank_arithmetic_actual.tcl"
    runner.write_text(study.once(runner.read_text(), "set result_json [exec {*}$python_command results $output_dir]",
        "exec {*}$python_command results $output_dir > [file join $output_dir results.json]"))
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["source_sha256"][runner.name] = study.sha(runner)
    manifest_path.write_text(json.dumps(manifest))
    result = subprocess.run(["tclsh", str(mock)], capture_output=True, text=True, timeout=20, check=False)
    (tmp_path / "early-JSON-mutant.log").write_text(result.stdout + result.stderr)
    assert result.returncode != 0 and "after_status=1" in (output / "run_outcome.txt").read_text()
    assert "BANK_ARITHMETIC_ACTUAL_CORE_VERIFIED" not in result.stdout
    # This deliberately wrong runner leaves precisely the misleading receipt
    # forbidden by the healthy policy test above. It is NOT accepted evidence.
    assert (output / "results.json").read_text().strip() == "MOCK_RESULT_POSTPROCESS_ONLY"


@pytest.mark.parametrize("name", list(study.VECTOR_HASHES))
def test_each_original_numeric_source_and_golden_is_immutable(tmp_path, name):
    for file in study.VECTOR_HASHES:
        (tmp_path / file).write_bytes((VECTORS / file).read_bytes())
    path = tmp_path / name
    path.write_text(path.read_text() + "00\n")
    with pytest.raises(ValueError, match="cohort"):
        study.verify_vectors(tmp_path)


@pytest.mark.parametrize("field,value", [("R", 0), ("O", 1), ("frequency", 200),
                                        ("baseline_complete_csv_match_required", False),
                                        ("original_r1_complete_csv_sha256", "0"*64),
                                        ("unchanged_bounds", {}), ("normal_R1_core_job", {"commit_delta": 1809})])
def test_manifest_cannot_silently_change_profile_or_historical_contract(tmp_path, field, value):
    study.freeze(tmp_path / "p", VECTORS, 175, 1, 0, 0)
    path = tmp_path / "p/manifest.json"
    manifest = json.loads(path.read_text()); manifest[field] = value
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        study.verify_freeze(tmp_path / "p")


@pytest.mark.parametrize("change", ["missing", "extra", "modified", "directory"])
def test_full_inventory_rejects_changes(tmp_path, change):
    study.freeze(tmp_path / "p", VECTORS, 175, 1, 1, 1)
    root = tmp_path / "p/frozen_sources"
    file = root / "profile.tcl"
    if change == "missing":
        file.unlink()
    elif change == "extra":
        (root / "extra.v").write_text("// extra\n")
    elif change == "modified":
        file.write_text(file.read_text() + "# altered\n")
    else:
        (root / "directory").mkdir()
    with pytest.raises(ValueError, match="inventory"):
        study.verify_freeze(tmp_path / "p")


@pytest.mark.parametrize("source", ["module starlink_pss_fft512_bfp18_rt_candidate(input a); endmodule",
                                    "localparam OFFLINE_NOT_FFT=1;"])
def test_synthetic_transactor_rejected_even_renamed(source):
    with pytest.raises(ValueError, match="synthetic"):
        study.reject_synthetic({"innocent.sv": source.encode()})


@pytest.mark.parametrize("frequency,r,b,o", [(150, 1, 0, 0), (175, 0, 0, 0), (175, 1, 1, 0),
                                           (175, 1, 0, 1), (175, 1, -1, -1), (175, 1, 2, 2)])
def test_undeclared_actual_matrix_has_no_files_or_launch(tmp_path, frequency, r, b, o):
    with pytest.raises(ValueError, match="matrix"):
        study.freeze(tmp_path / "p", VECTORS, frequency, r, b, o)
    assert not (tmp_path / "p").exists()


def actual_stub_compile(tmp_path):
    files = [study.ACQ / (name + ".v") for name in study.RTL]
    files += [study.ACQ / "tb" / name for name in study.TB if not name.endswith(".svh")]
    result = subprocess.run(["env", "-u", "LD_LIBRARY_PATH", "iverilog", "-g2012", "-i", "-Wall",
        "-I", str(study.ACQ / "tb"), "-s", study.NEW_BENCH, "-o", str(tmp_path / "syntax_only.vvp"),
        *map(str, files)], capture_output=True, text=True, check=False, timeout=30)
    (tmp_path / "syntax_only.log").write_text(result.stdout + result.stderr)
    return result


def test_derived_actual_bench_compile_only_missing_vendor_IP_not_simulated(tmp_path):
    result = actual_stub_compile(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not re.search(r"implicit definition|error", result.stderr, re.IGNORECASE)


def shadow_bench():
    source = study.original("tb/tb_starlink_pss_payload_bubbles.sv")
    source = source[:source.index("\nmodule tb_starlink_pss_product_bubbles;")]
    source = study.once(source, "module tb_starlink_pss_payload_bubbles;", "module tb_arithmetic_shadow;\n  parameter integer O=0, B=0;")
    source = source.replace("product.product_", "product.arithmetic.product_").replace("product.sum_valid", "product.arithmetic.sum_valid")
    source = study.once(source,
        "starlink_pss_spectrum_product #(.DATA_WIDTH(18),.PRIVATE_PAYLOAD_BUBBLES(PRODUCT_BUBBLES)) product (",
        "starlink_pss_spectrum_product_operand_register #(.DATA_WIDTH(18),.PRIVATE_PAYLOAD_BUBBLES(PRODUCT_BUBBLES),.REGISTER_OPERANDS(O),.BOUNDARY_ROUND_SAT(B)) product (")
    source = study.once(source, "starlink_pss_payload_bubble_shadow shadow (.*);", "starlink_pss_bank_arithmetic_shadow #(.O(O)) shadow (.*);")
    # Only this separate shadow-unit fixture needs one extra fill token; the
    # actual-core bench's source, waits and original cycle expectations do not.
    assert source.count("n<4;") == 2 and source.count("n=4;") == 1
    return source.replace("n<4;", "n<4+O;").replace("n=4;", "n=4+O;")


def run_shadow(tmp_path, o, b, mutation=None):
    names = ["starlink_pss_forward_kernel_join", "starlink_pss_kernel_rom",
             "starlink_pss_spectrum_product_operand_register", "starlink_pss_spectrum_product_bank_arithmetic"]
    files = [study.ACQ / (name + ".v") for name in names]
    files += [study.ACQ / "tb" / name for name in study.TB if "golden" in name or name in (study.NEW_SHADOW+".sv", study.OLD_SHADOW+".sv")]
    for file in files:
        (tmp_path / file.name).write_bytes(file.read_bytes())
    (tmp_path / "test.sv").write_text(shadow_bench())
    wrapper = tmp_path / "starlink_pss_spectrum_product_operand_register.v"
    if mutation:
        source = wrapper.read_text()
        if mutation == "latency":
            source = study.once(source, "if (REGISTER_OPERANDS == 1)", "if (1'b0)")
        elif mutation == "drop":
            source = study.once(source, "valid <= input_valid;", "valid <= 1'b0;")
        else:
            source = study.once(source, "                           input_block_start_index};",
                                "                           (input_block_start_index ^ 64'b1)};")
        wrapper.write_text(source)
    (tmp_path / "upper_edge_pss_kernel_q17.mem").write_bytes((VECTORS / "upper_edge_pss_kernel_q17.mem").read_bytes())
    before = {p.name: study.sha(p) for p in tmp_path.iterdir()}
    (tmp_path / "sources.json").write_text(json.dumps(before, sort_keys=True, indent=2))
    compiled = subprocess.run(["env", "-u", "LD_LIBRARY_PATH", "iverilog", "-g2012", "-s", "tb_arithmetic_shadow",
        f"-Ptb_arithmetic_shadow.O={o}", f"-Ptb_arithmetic_shadow.B={b}", "-Ptb_arithmetic_shadow.JOIN_BUBBLES=1",
        "-Ptb_arithmetic_shadow.PRODUCT_BUBBLES=1", "-Ptb_arithmetic_shadow.BALANCED_ROM=1",
        "-o", "test.vvp", "test.sv", *[p.name for p in files]], cwd=tmp_path,
        capture_output=True, text=True, check=False, timeout=30)
    (tmp_path / "compile.log").write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run(["env", "-u", "LD_LIBRARY_PATH", "vvp", "test.vvp"], cwd=tmp_path,
                            capture_output=True, text=True, check=False, timeout=30)
    (tmp_path / "simulate.log").write_text(result.stdout + result.stderr)
    assert before == {name: study.sha(tmp_path / name) for name in before}
    return result


@pytest.mark.parametrize("o,b", list(itertools.product((0, 1), repeat=2)))
def test_independent_shadow_all_options_stall_reset_flush_hostile_bubbles(tmp_path, o, b):
    result = run_shadow(tmp_path, o, b)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("PAYLOAD_BUBBLES_PASS") == 1
    assert not re.search(r"FAIL|FATAL|MISMATCH|ERROR", result.stdout, re.IGNORECASE)


@pytest.mark.parametrize("mutation", ["latency", "drop", "metadata"])
def test_shadow_rejects_wrong_latency_dropped_token_and_metadata(tmp_path, mutation):
    result = run_shadow(tmp_path, 1, 1, mutation)
    assert result.returncode != 0 and re.search(r"FATAL:.*PAYLOAD_.*MISMATCH", result.stdout)
    assert "PAYLOAD_BUBBLES_PASS" not in result.stdout


@pytest.mark.parametrize("o", [0, 1])
def test_declared_actual_monitor_accept_to_bank_bound_on_real_arithmetic(tmp_path, o):
    # Distinguish output visibility at +2/+3 from the accepting bank edge +3/+4.
    bench = """module tb;
      parameter integer O=0;
      reg clk=0; always #5 clk=!clk;
      reg resetn=0, flush=0, input_valid=0; wire input_ready;
      reg signed [17:0] input_i=333, input_q=-21, kernel_i=713, kernel_q=529;
      reg [8:0] input_bin_index=0; reg [4:0] input_block_exponent=5;
      reg input_last=0; reg [63:0] input_block_start_index=64'h800000000001;
      wire output_valid,output_last,output_overflow,overflow_pulse;
      wire signed [17:0] output_i,output_q; wire [8:0] output_bin_index;
      wire [4:0] output_block_exponent; wire [63:0] output_block_start_index;
      wire output_ready=1;
      integer cycle=0, admitted=-1, accepted=0;
      starlink_pss_spectrum_product_operand_register #(.DATA_WIDTH(18),.REGISTER_OPERANDS(O),
        .BOUNDARY_ROUND_SAT(O),.PRIVATE_PAYLOAD_BUBBLES(1)) dut(.*);
      always @(posedge clk) begin
        cycle=cycle+1;
        if(resetn && input_valid && input_ready) admitted=cycle;
        if(resetn && output_valid && output_ready) begin
          if(admitted<0 || cycle-admitted != 3+O) $fatal(1,"DECLARED_BANK_EDGE_BOUND_MISMATCH");
          accepted=accepted+1;
        end
      end
      initial begin
        repeat(2) @(negedge clk); resetn=1; input_valid=1;
        @(negedge clk); input_valid=0;
        repeat(8) @(negedge clk);
        if(accepted!=1) $fatal(1,"DECLARED_BANK_EDGE_MISSING_TOKEN");
        $display("DECLARED_BANK_EDGE_PASS O=%0d accept_to_bank_clocks=%0d",O,3+O); $finish;
      end
    endmodule
    """
    (tmp_path / "test.sv").write_text(bench)
    names = ["starlink_pss_spectrum_product_operand_register.v", "starlink_pss_spectrum_product_bank_arithmetic.v"]
    for name in names:
        (tmp_path / name).write_bytes((study.ACQ / name).read_bytes())
    compiled = subprocess.run(["env", "-u", "LD_LIBRARY_PATH", "iverilog", "-g2012", "-s", "tb",
        f"-Ptb.O={o}", "-o", "test.vvp", "test.sv", *names], cwd=tmp_path,
        capture_output=True, text=True, check=False, timeout=20)
    (tmp_path / "compile.log").write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run(["env", "-u", "LD_LIBRARY_PATH", "vvp", "test.vvp"], cwd=tmp_path,
                            capture_output=True, text=True, check=False, timeout=20)
    (tmp_path / "simulate.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0 and f"DECLARED_BANK_EDGE_PASS O={o} accept_to_bank_clocks={3+o}" in result.stdout


def terminal(o):
    return (HISTORICAL / "simulate.log").read_text() + (
        f"\nBANK_ARITHMETIC_ACTUAL_PASS R=1 B={o} O={o} fast_mhz=175 exact_event_words_per_stream=19456 "
        f"nominal_blocks=32 stalled_blocks=6 latency_checks=32 accept_to_bank_clocks={3+o} "
        "old_fault_checks_unchanged=1 score_oracle_only=1\n")


@pytest.mark.parametrize("o", [0, 1])
def test_historical_log_plus_synthetic_new_receipt_parser_only(o):
    assert study.require_terminal(terminal(o), {"R": 1, "B": o, "O": o, "frequency": 175})


@pytest.mark.parametrize("change", ["raw217", "old_only", "duplicate", "lateFAIL", "lateFatal", "lateError", "latency", "prefix"])
def test_rejects_partial_pass_late_failures_and_wrong_contract(change):
    log = terminal(1)
    if change == "raw217":
        log = "RAW217_PASS\n"
    elif change == "old_only":
        log = log[:log.index("BANK_ARITHMETIC_ACTUAL_PASS")]
    elif change == "duplicate":
        log += log[log.index("BANK_ARITHMETIC_ACTUAL_PASS"):]
    elif change in ("lateFAIL", "lateFatal", "lateError"):
        log += change[4:] + ": after early PASS\n"
    elif change == "latency":
        log = log.replace("accept_to_bank_clocks=4", "accept_to_bank_clocks=3")
    else:
        log = log.replace("provisional_prefix_words=130", "provisional_prefix_words=512")
    with pytest.raises(ValueError):
        study.require_terminal(log, {"R": 1, "B": 1, "O": 1, "frequency": 175})


@pytest.fixture(scope="module")
def synthetic_events(tmp_path_factory):
    directory = tmp_path_factory.mktemp("oracle-events-not-actual")
    path = directory / "synthetic_events.csv"
    refs = {k: study.words(VECTORS / (k+"_q17.mem"), 1536) for k in ("forward", "product", "inverse")}
    ef = study.words(VECTORS / "forward_exponents.mem", 3)
    ei = study.words(VECTORS / "inverse_exponents.mem", 3)
    with path.open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(["epoch", "stream", "ordinal", "data", "position", "last", "start", "ef", "ei", "cycle"])
        for epoch, blocks in ((1, 32), (2, 6)):
            for kind, values in refs.items():
                for ordinal in range(blocks*512):
                    block, position = divmod(ordinal, 512)
                    fixture = block % 3
                    writer.writerow([epoch, kind, ordinal, f"{values[fixture*512+position]:09x}", position,
                        int(position == 511), 0x200000000+epoch*65536+block*447, ef[fixture],
                        ei[fixture] if kind == "inverse" else 0, ordinal+1])
    return path


def test_independent_full_sample_score_and_event_oracle_offline(synthetic_events):
    checked = study.verify_vectors(VECTORS)
    assert checked["scores"] == 1341 and checked["independent_spectrum_products"] == 1536
    result = study.verify_events(synthetic_events, VECTORS)
    assert result["output_derived_exact_sample_scores"] == 16986
    assert result["score_scope"] == "oracle_only_no_scorer_RTL"


def test_input_derived_energy_and_69bit_score_saturation_boundaries():
    assert study.score(0, 0, 0, [0x00010001]*66) == 0
    assert study.score(1, 31, 31, [0x00010001]*66) == 255
    with pytest.raises(ValueError, match="aperture"):
        study.score(1, 0, 0, [1]*65)
    with pytest.raises(ValueError, match="energy"):
        study.score(1, 0, 0, [0]*66)


@pytest.mark.parametrize("column", ["data", "position", "start", "ef", "ei", "last", "ordinal", "cycle", "stream", "missing"])
def test_event_numeric_identity_order_exponent_and_count_mutants(tmp_path, synthetic_events, column):
    rows = list(csv.DictReader(synthetic_events.open()))
    if column == "missing":
        rows.pop()
    else:
        rows[512][column] = "x" if column in ("data", "stream") else str(int(rows[512][column])+1)
    path = tmp_path / "mutated_events.csv"
    with path.open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    with pytest.raises(ValueError):
        study.verify_events(path, VECTORS)
