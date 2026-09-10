"""Offline generation/elaboration and checker self-tests, NEVER an actual FFT run."""

import importlib.util
import itertools
import json
import re
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.test_exact_control import STUB

HDL = Path(__file__).resolve().parents[2] / "hdl"
ACQ = HDL / "library/starlink_pss_acquisition"
SPEC = importlib.util.spec_from_file_location(
    "exact_prepare", ACQ / "prepare_exact_control_actual.py"
)
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)
VECTORS = ACQ / "evidence/forward-retirement-v1/actual/frozen_sources"


def restore_candidate(text):
    for kind in ("PARAMETERS", "SHADOW", "RECEIPT"):
        text, count = re.subn(
            rf"^  // BEGIN EXACT_CONTROL_{kind}\n.*?^  // END EXACT_CONTROL_{kind}\n",
            "",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert count == 1
    return PREPARE.once(
        text,
        "#(.REGISTERED_SCHEDULING(REGISTERED_SCHEDULING),\n"
        "    .DISTRIBUTED_FAST_FAULT(DISTRIBUTED_FAST_FAULT),\n"
        "    .PRIVATE_NEXT_START_SCRATCH(PRIVATE_NEXT_START_SCRATCH)) dut (.*);",
        "#(.REGISTERED_SCHEDULING(REGISTERED_SCHEDULING)) dut (.*);",
    )


def restore_reference(text):
    for kind in PREPARE.RTL:
        name = "starlink_pss_" + kind
        text = re.sub(rf"\b{name}_dec20d63_golden\b", name, text)
    text = PREPARE.once(text, f"module {PREPARE.REFERENCE};", f"module {PREPARE.TOP};")
    text = PREPARE.once(
        text,
        "  parameter integer EXACT_EXTRA_EPOCHS = 0;\n"
        + PREPARE.EXTRA_PARAMETER_CHECK
        + "  reg exact_reference_done = 0;\n"
        '  `include "starlink_pss_exact_control_extra_epochs.svh"\n',
        "",
    )
    text = PREPARE.once(
        text, '"exact_control_reference_trace.csv"', '"fft_bank_owned_trace.csv"'
    )
    return PREPARE.once(
        text,
        """    $fclose(trace);
    if (EXACT_EXTRA_EPOCHS) begin
      trace = $fopen("exact_control_reference_extra_trace.csv", "w");
      exact_control_extra_epochs(); $fclose(trace);
    end
    exact_reference_done = 1;
""",
        "    $fclose(trace); $finish;",
    )


def test_generated_candidate_and_independently_driven_reference_restore_entire_old_bench():
    original = PREPARE.git_file(
        HDL, PREPARE.BASE, f"library/starlink_pss_acquisition/tb/{PREPARE.TOP}.sv"
    ).decode()
    assert restore_candidate(PREPARE.candidate_bench(original)) == original
    assert restore_reference(PREPARE.reference_bench(original)) == original
    assert (ACQ / "tb" / f"{PREPARE.TOP}.sv").read_text() == original
    assert len(PREPARE.FIELDS) == len(set(PREPARE.FIELDS))
    for field in (
        "dut.fast_fault",
        "dut.result_guard.faults_now",
        "dut.result_guard.fault_reasons",
        "dut.input_guard.fault_reasons",
        "dut.forward_handoff_ack",
        "dut.product_commit_authorized",
        "dut.product_bank.request_toggle",
        "dut.product_bank.acknowledge_toggle",
        "dut.output_bank.request_toggle",
        "dut.output_bank.acknowledge_toggle",
    ):
        assert field in PREPARE.FIELDS
    assert "dut.joiner.kernel_rom.expected_next_block_start" not in PREPARE.FIELDS


@pytest.mark.parametrize(
    "registered,distributed,scratch", list(itertools.product((0, 1), repeat=3))
)
def test_all_eight_preparations_hashes_independent_sources_and_stub_elaboration_only(
    tmp_path, registered, distributed, scratch
):
    output = tmp_path / "prepared"
    PREPARE.prepare(output, VECTORS, registered, distributed, scratch, 1)
    inventory = json.loads((output / "preparation.json").read_text())
    assert inventory["settings"] == {
        "REGISTERED_SCHEDULING": registered,
        "DISTRIBUTED_FAST_FAULT": distributed,
        "PRIVATE_NEXT_START_SCRATCH": scratch,
        "EXACT_EXTRA_EPOCHS": 1,
        "FAST_MHZ": 175,
        "QUICK_MUTATION": 0,
    }
    subprocess.run(
        ["sha256sum", "-c", "SHA256SUMS", "--quiet"], cwd=output, check=True, timeout=10
    )
    source = output / "frozen_sources"
    for kind in PREPARE.RTL:
        name = "starlink_pss_" + kind
        reference = (source / f"{name}_dec20d63_golden.v").read_text()
        assert reference == PREPARE.renamed(
            PREPARE.git_file(
                HDL, PREPARE.BASE, f"library/starlink_pss_acquisition/{name}.v"
            ).decode()
        )
    # Compile only. This stub cannot produce FFT output and is NEVER executed
    # with either actual stimulus bench; no numerical pass can come from it.
    stub = tmp_path / "compile_only_stub.v"
    stub.write_text(STUB)
    executable = tmp_path / "elaborated_not_run.vvp"
    files = sorted(source.glob("*.v")) + sorted(source.glob("*.sv")) + [stub]
    result = subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-Wall",
            "-I",
            str(source),
            "-s",
            PREPARE.TOP,
            *[
                f"-P{PREPARE.TOP}.{key}={value}"
                for key, value in inventory["settings"].items()
            ],
            "-o",
            str(executable),
            *map(str, files),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    (tmp_path / "elaboration.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    # Inspect the actual compiled expression, not an assumed declared bus
    # width. Hierarchical $bits previously resolved to zero in a localparam
    # even though compilation succeeded. Self-sized equality must observe the
    # full concatenation, and the monitor receives only its exact boolean.
    compiled = executable.read_text()
    driver = re.search(r'\.net "exact_public_equal", 0 0, (\S+);', compiled)
    assert driver is not None
    comparison = re.search(
        rf"^{re.escape(driver.group(1))} \.cmp/eeq (\d+),", compiled, re.MULTILINE
    )
    assert comparison is not None
    assert int(comparison.group(1)) == 2168
    (tmp_path / "observer_width.log").write_text(
        f"ELABORATED_FULL_PUBLIC_EQUALITY_BITS={comparison.group(1)} fields={len(PREPARE.FIELDS)} no_actual_execution=1\n"
    )
    with pytest.raises(FileExistsError):
        PREPARE.prepare(output, VECTORS, registered, distributed, scratch, 1)


@pytest.mark.parametrize("mutation", [0, 1, 2, 3])
def test_observer_self_test_rejects_public_fault_ownership_and_consumed_identity_differences(
    tmp_path, mutation
):
    bench = f"""`timescale 1ns/1fs
module monitor_test;
reg clk=0; always #3 clk=!clk;
reg [63:0] a=0,b=0,sa=0,sb=0;
reg ca=0,cb=0,active_job=0,final_slot=0,current_fault=0,owned=0,stall=0,running=0;
wire [31:0] checks,active_checks,consumed,differences,final_faults,owned_stalls,reset_owned;
integer i;
starlink_pss_exact_control_actual_compare #(.WIDTH(64)) dut(.clk(clk), .actual_public(a),
.reference_public(b), .actual_consume(ca), .reference_consume(cb), .actual_scratch(sa),
.reference_scratch(sb), .active_job(active_job), .final_slot(final_slot), .current_fault(current_fault),
.owned_bank(owned), .stalled_bank(stall), .running(running), .checks(checks), .active_checks(active_checks),
.consumed_identities(consumed), .private_differences(differences), .final_fault_edges(final_faults),
.owned_stall_edges(owned_stalls), .reset_owned_edges(reset_owned));
initial begin
repeat(3) @(negedge clk);
for(i=0;i<64;i=i+1) begin
  #0.1; a=64'b1<<i; b=a; sa=a; sb=~a;
  active_job=i[0]; owned=1; stall=1; running=i[0]; final_slot=1;current_fault=1;
  if({mutation}==1) b=~a;
  @(posedge clk); #0.1;
  @(negedge clk); #0.1; ca=1; cb=1; sb=sa;
  if({mutation}==2) cb=0;
  if({mutation}==3) sb=~sa;
  @(posedge clk); #0.1;
  @(negedge clk); #0.1;ca=0;cb=0;
end
if(!checks || !active_checks || consumed!=64 || !differences || !final_faults || !owned_stalls || !reset_owned)
  $fatal(1,"observer self-test coverage missing");
$display("EXACT_ACTUAL_OBSERVER_SELF_TEST_PASS no_fft=1");$finish;
end
endmodule
"""
    path = tmp_path / "monitor_test.sv"
    path.write_text(bench)
    executable = tmp_path / "monitor.vvp"
    subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-s",
            "monitor_test",
            "-o",
            str(executable),
            str(ACQ / "tb/starlink_pss_exact_control_actual_compare.sv"),
            str(path),
        ],
        check=True,
        timeout=10,
    )
    result = subprocess.run(
        ["vvp", str(executable)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    log = result.stdout + result.stderr
    (tmp_path / "simulate.log").write_text(log)
    if mutation == 0:
        assert (
            result.returncode == 0 and "EXACT_ACTUAL_OBSERVER_SELF_TEST_PASS" in log
        ), log
    else:
        marker = {
            1: "EXACT_ACTUAL_PUBLIC_REASON_OWNERSHIP_MISMATCH",
            2: "EXACT_ACTUAL_CONSUME_MISMATCH",
            3: "EXACT_ACTUAL_SCRATCH_CONSUMED_MISMATCH",
        }[mutation]
        assert result.returncode != 0 and marker in log, log


def test_future_launcher_has_fixed_gates_and_is_never_called_by_preparer():
    source = (ACQ / "prepare_exact_control_actual.py").read_text()
    assert '"vivado"' not in source and "launch_simulation" not in source
    launcher = (ACQ / "simulate_exact_control_prepared.tcl").read_text()
    for marker in (
        "general.maxThreads 2",
        "FAST_MHZ=175",
        "QUICK_MUTATION=0",
        "exec cmp $candidate_csv $reference_csv",
        "25ab9d06ca0e03f280540cda625a7826b3c4cbaa6322ce3266c59e1fbad94122",
        "b0d60e80101b34ff163b85ef7547814e0403561b315f975eb38a98817b7eb84d",
    ):
        assert marker in launcher
    assert "synth_design" not in launcher and "route_design" not in launcher


@pytest.mark.parametrize("reference", [False, True])
@pytest.mark.parametrize("value", ["0", "1", "-1", "2", "1'bx", "1'bz"])
def test_each_generated_extra_parameter_entry_fails_closed_without_fft(
    tmp_path, reference, value
):
    original = PREPARE.git_file(
        HDL, PREPARE.BASE, f"library/starlink_pss_acquisition/tb/{PREPARE.TOP}.sv"
    ).decode()
    generate = PREPARE.reference_bench if reference else PREPARE.candidate_bench
    generated = generate(original)
    assert generated.count(PREPARE.EXTRA_PARAMETER_CHECK) == 1
    # Execute only the literal entry check, never either actual bench/stub.
    entry = tmp_path / "extra_entry.sv"
    entry.write_text(
        "module extra_entry; parameter integer EXACT_EXTRA_EPOCHS=0;\n"
        + PREPARE.EXTRA_PARAMETER_CHECK
        + 'initial begin #1; $display("EXTRA_PARAMETER_VALID_NO_FFT"); $finish; end\nendmodule\n'
        + f"module extra_test; extra_entry #(.EXACT_EXTRA_EPOCHS({value})) dut(); endmodule\n"
    )
    executable = tmp_path / "extra_entry.vvp"
    subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-s",
            "extra_test",
            "-o",
            str(executable),
            str(entry),
        ],
        check=True,
        timeout=10,
    )
    result = subprocess.run(
        ["vvp", str(executable)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    log = result.stdout + result.stderr
    (tmp_path / "simulate.log").write_text(log)
    if value in ("0", "1"):
        assert result.returncode == 0 and "EXTRA_PARAMETER_VALID_NO_FFT" in log
    else:
        assert (
            result.returncode != 0 and "EXACT_EXTRA_EPOCHS_REQUIRES_ZERO_OR_ONE" in log
        ), log


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "disabled_extra",
        "wrong_registered",
        "wrong_distributed",
        "wrong_scratch",
        "wrong_extra",
        "unknown_knob",
        "zero_checks",
        "zero_active",
        "zero_consumed",
        "missing_reference_extra",
        "wrong_final_faults",
        "wrong_stalls",
        "wrong_resets",
        "wrong_recoveries",
        "missing_active_final",
        "missing_owned_stalls",
        "duplicate_terminal",
    ],
)
def test_future_terminal_settings_and_both_extra_receipts_offline(tmp_path, mutation):
    launcher = (ACQ / "simulate_exact_control_prepared.tcl").read_text()
    checker = re.search(
        r"# BEGIN EXACT_CONTROL_RECEIPTS\n(.*?)# END EXACT_CONTROL_RECEIPTS",
        launcher,
        flags=re.DOTALL,
    ).group(1)
    terminal = (
        "EXACT_CONTROL_ACTUAL_PASS registered=1 distributed=1 scratch=1 extra=1 "
        "checks=500 active=300 consumed=2 private_differences=19 final_fault_edges=2 "
        "owned_stalls=9 reset_owned_edges=0 independent_actual_core=1"
    )
    extra = (
        "EXACT_CONTROL_EXTRA_EPOCHS_PASS final_faults=2 held_final_stalls=3 "
        "one_sided_resets=2 healthy_recoveries=4"
    )
    log = f"{extra}\n{extra}\n{terminal}\n"
    settings = "1 1 1 1"
    changes = {
        "wrong_registered": ("registered=1", "registered=0"),
        "wrong_distributed": ("distributed=1", "distributed=0"),
        "wrong_scratch": ("scratch=1", "scratch=0"),
        "wrong_extra": ("extra=1", "extra=0"),
        "unknown_knob": ("scratch=1", "scratch=x"),
        "zero_checks": ("checks=500", "checks=0"),
        "zero_active": ("active=300", "active=0"),
        "zero_consumed": ("consumed=2", "consumed=0"),
        "wrong_final_faults": ("final_faults=2", "final_faults=1"),
        "wrong_stalls": ("held_final_stalls=3", "held_final_stalls=2"),
        "wrong_resets": ("one_sided_resets=2", "one_sided_resets=1"),
        "wrong_recoveries": ("healthy_recoveries=4", "healthy_recoveries=3"),
        "missing_active_final": ("final_fault_edges=2", "final_fault_edges=0"),
        "missing_owned_stalls": ("owned_stalls=9", "owned_stalls=0"),
    }
    if mutation in changes:
        log = log.replace(*changes[mutation], 1)
    elif mutation == "missing_reference_extra":
        log = log.replace(extra + "\n", "", 1)
    elif mutation == "duplicate_terminal":
        log += terminal + "\n"
    elif mutation == "disabled_extra":
        log = terminal.replace("extra=1", "extra=0") + "\n"
        settings = "1 1 1 0"
    invocation = (
        checker
        + f"\nset log {{{log}}}\n"
        + f"if {{[catch {{exact_verify_receipts $log {settings}}} reason]}} {{puts $reason; exit 1}}\n"
        + "puts $reason\n"
    )
    (tmp_path / "receipt_test.tcl").write_text(invocation)
    result = subprocess.run(
        ["tclsh"],
        input=invocation,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    output = result.stdout + result.stderr
    (tmp_path / "receipt_test.log").write_text(output)
    if mutation in ("none", "disabled_extra"):
        assert result.returncode == 0 and "EXACT_CONTROL_RECEIPTS_VERIFIED" in output
    else:
        assert result.returncode != 0, output
