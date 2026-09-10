"""Paired60 OFFLINE preparation/compile-only coverage; never FFT/service."""

import re
import shutil
import subprocess

import pytest

from tests.starlink_oracle.high_rate60_bundle import (
    ROOT,
    TB,
    TOP,
    base_pins,
    check_bench,
    native_adaptation,
)
from tests.starlink_oracle.high_rate60_harness import (
    check_recipe,
    fixture_payloads,
    prepare_vectors,
    verify_vectors,
)
from tests.starlink_oracle.native60_budget import COHORT, encoded, sha


def test_original69_exact_plus_two_primes_no_tail(tmp_path):
    payloads, result = fixture_payloads(COHORT)
    assert len(result["original69"]) == 69 and len(payloads) == 71
    assert result["tail_added"] is False
    old = (COHORT / "source_ci16.mem").read_text().splitlines()
    assert payloads["paired_source_ci16.mem"].decode().splitlines() == ["00000001", "00000002", *old]
    assert all(sha(payloads[name]) == digest for name, digest in result["original69"].items())
    output = tmp_path / "vectors"
    prepare_vectors(COHORT, output)
    verify_vectors(COHORT, output)
    with pytest.raises(ValueError, match="overwrite"):
        prepare_vectors(COHORT, output)


@pytest.mark.parametrize("name", ["paired_source_ci16.mem", "paired_source_index_u64.mem", "canonical_ci16.mem",
    "ddc60_to30_ci16.mem", "ddc30_to15_ci16.mem", "ddc60_to30_mixed_s17.mem", "ddc30_to15_mixed_s17.mem",
    "conditioned_kernel_q17.mem", "fft_input_q17.mem", "forward_q17.mem", "product_q17.mem", "inverse_q17.mem",
    "energies_u38.mem", "denominators_u69.mem", "map_447x2_u16.mem", "native_capture_ci16.mem", "native_raw_lags_s32.mem",
    "native_expected_packet.mem", "pilot_expected.ci16"])
def test_no_mutable_numerical_halo_phase_packing_kernel(tmp_path, name):
    output = tmp_path / "vectors"
    prepare_vectors(COHORT, output)
    p = output / name
    p.write_bytes(p.read_bytes()+b"\n")
    with pytest.raises(ValueError, match="fixture changed"):
        verify_vectors(COHORT, output)


@pytest.mark.parametrize("field", list(check_recipe()))
def test_each_recipe_field_frozen(field):
    r = check_recipe()
    r[field] = "mutated"
    with pytest.raises(ValueError, match="unadmitted"):
        check_recipe(r)


@pytest.mark.parametrize("field", [key for key, value in check_recipe().items() if type(value) in [int, bool]])
def test_recipe_type_aliases_rejected(field):
    r = check_recipe()
    r[field] = float(r[field])
    with pytest.raises(ValueError, match="unadmitted"):
        check_recipe(r)


def test_destination_parent_symlink_cannot_touch_existing_source(tmp_path):
    actual = tmp_path / "protected"
    actual.mkdir()
    (tmp_path / "alias").symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        prepare_vectors(COHORT, tmp_path / "alias" / "vectors")
    assert not list(actual.iterdir())


def test_native_entire_verifier_strict_projection_and_old_sources():
    native_adaptation(ROOT)
    for name, digest in base_pins(ROOT).items():
        assert sha((ROOT/name).read_bytes()) == digest, name


@pytest.mark.parametrize("before,after", [("<= 84000", "<= 84001"), ("== 257", "== 249"),
    ('== 60, "unrecognized', '== 59, "unrecognized'), ("== 52", "== 26"), ("<= 16", "<= 17")])
def test_native_projection_rejects_inner_check_mutations(tmp_path, before, after):
    names = ["tests/starlink_oracle/native60_budget.py", "tests/starlink_oracle/high_rate60_harness_result.py"]
    for name in names:
        p = tmp_path/name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, p)
    p = tmp_path/names[-1]
    text = p.read_text()
    assert before in text
    p.write_text(text.replace(before, after, 1))
    with pytest.raises(ValueError, match="adaptation"):
        native_adaptation(tmp_path)


INERT_FFT = """module starlink_pss_fft512_bfp18_rt_candidate(
input aclk,aresetn,input [7:0] s_axis_config_tdata,input s_axis_config_tvalid,
output s_axis_config_tready,input [47:0] s_axis_data_tdata,input s_axis_data_tvalid,
output s_axis_data_tready,input s_axis_data_tlast,output [47:0] m_axis_data_tdata,
output [23:0] m_axis_data_tuser,output m_axis_data_tvalid,m_axis_data_tlast,
output [7:0] m_axis_status_tdata,output m_axis_status_tvalid,
output event_frame_started,event_tlast_unexpected,event_tlast_missing,event_data_in_channel_halt);
assign s_axis_config_tready=0; assign s_axis_data_tready=0;
assign m_axis_data_tdata=0; assign m_axis_data_tuser=0; assign m_axis_data_tvalid=0;
assign m_axis_data_tlast=0; assign m_axis_status_tdata=0; assign m_axis_status_tvalid=0;
assign event_frame_started=0; assign event_tlast_unexpected=0;
assign event_tlast_missing=0; assign event_data_in_channel_halt=0;
always @(posedge aclk) if(aresetn && (s_axis_config_tvalid || s_axis_data_tvalid))
$fatal(1,"INERT_FFT_ELABORATION_ONLY_NOT_SERVICE");
endmodule
"""


def test_entire_composition_compile_only_no_vvp(tmp_path):
    check_bench(ROOT)
    snapshot = tmp_path / "source_snapshot"
    names = [name for name in base_pins(ROOT) if name.endswith(".v")]
    includes = [TB+name for name in ["native60_budget_checks.svh", "native60_readback_checks.svh",
        "high_rate_paired_axi.svh", "bank_native60_clock_checks.svh", "bank_native60_source_checks.svh", "bank_native60_fft_checks.svh"]]
    for name in [*names, TOP, *includes]:
        p = snapshot / name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, p)
    stub = snapshot / "inert_fft.v"
    stub.write_text(INERT_FFT)
    before = {p.relative_to(snapshot).as_posix(): sha(p.read_bytes()) for p in snapshot.rglob("*") if p.is_file()}
    (tmp_path/"source-before.json").write_bytes(encoded(before))
    command = ["iverilog", "-g2012", "-Wall", "-I", str(snapshot/TB), "-s", "tb_starlink_pss_60_bank_native_paired",
               "-o", str(tmp_path/"compile-only.vvp"), *[str(snapshot/name) for name in [*names, TOP]], str(stub)]
    r = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    (tmp_path/"compile.log").write_text(r.stdout+r.stderr)
    after = {p.relative_to(snapshot).as_posix(): sha(p.read_bytes()) for p in snapshot.rglob("*") if p.is_file()}
    (tmp_path/"source-after.json").write_bytes(encoded(after))
    (tmp_path/"compile-status.json").write_bytes(encoded({"command": command, "exit": r.returncode,
        "service_executed": False, "vvp_invoked": False, "diagnostic_lines": len((r.stdout+r.stderr).splitlines())}))
    assert before == after
    assert r.returncode == 0, r.stdout+r.stderr
    assert not (tmp_path/"simulate.log").exists()


def test_bench_no_hierarchy_writes_full_drain_after_release():
    check_bench(ROOT)
    top = (ROOT/TOP).read_text()
    assert top.index("wait(native_drain_cycle>=0)") < top.index("quiet_start=cycles") < top.index("report_clocks();")
    assert top.index('HIGH_RATE60_PIL1_SNAPSHOT') < top.index("quiet_start=cycles")
    assert re.search(r"wire native_done=native_released", top)


@pytest.mark.parametrize("literal", ["32'h10008", "32'h020f0403", "1073765335", "pilot_irq} !== 0",
    "wait(native_drain_cycle>=0)", "repeat(256)", "source_range(0,2)", "source_range(2,3111)", "#(500.0/60)"])
def test_bench_safety_identity_source_mutants(tmp_path, literal):
    for name in [TOP, *[TB+"bank_native60_"+s+"_checks.svh" for s in ["source", "fft", "clock"]]]:
        p = tmp_path/name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name,p)
    p = tmp_path/TOP
    p.write_text(p.read_text().replace(literal, "MUTANT", 1))
    with pytest.raises(ValueError, match="missing"):
        check_bench(tmp_path)


def test_tiny_clock_and_unknown_health_logic_only_no_native_or_fft(tmp_path):
    # Reuse the complete actual oscillator observer, but instantiate NO DUT,
    # native engine, filter or FFT IP. This measures only testbench conventions.
    observer = (ROOT/TB/"bank_native60_clock_checks.svh").read_text()
    top = (ROOT/TOP).read_text()
    operator = re.search(r"canonical_flush, pilot.faults, pilot.ddc_fault, pilot.ddc_clips, pilot_irq\} (\S+) 0",top).group(1)
    assert operator == "!=="
    source = '''`timescale 1ns/1fs
module unit_clocks_health_only;
reg clk=0,sample_clk=0,fft_clk=0,resetn=1;
integer cycles=0,source_off_edge=0,quiet_edges=0;
reg [31:0] observations=0;
wire rejected=(observations OPERATOR 0);
always #5 clk=!clk;
always @(posedge clk) cycles=cycles+1;
initial begin #2.1; forever #(500.0/60) sample_clk=!sample_clk; end
initial begin #1.3; forever #(500.0/175) fft_clk=!fft_clk; end
task automatic fail(input string message); $fatal(1,"%s",message); endtask
OBSERVER
initial begin
#1; if(rejected!==0) $fatal(1,"zero health rejected");
observations=32'hxxxxxxxx; #1; if(rejected!==1) $fatal(1,"unknown health escaped");
observations=32'hzzzzzzzz; #1; if(rejected!==1) $fatal(1,"high impedance health escaped");
observations=1; #1; if(rejected!==1) $fatal(1,"known fault escaped");
#196; if(source_edges!=12 || fft_edges!=35) $fatal(1,"clock inventory");
$display("UNIT_CLOCK_HEALTH_ONLY_NO_NATIVE_FFT_SERVICE"); $finish;
end
endmodule
'''.replace("OPERATOR",operator).replace("OBSERVER",observer)
    p=tmp_path/"unit.sv"
    p.write_text(source)
    command=["iverilog","-g2012","-s","unit_clocks_health_only","-o",str(tmp_path/"unit.vvp"),str(p)]
    r=subprocess.run(command,capture_output=True,text=True,timeout=30,check=False)
    (tmp_path/"unit-compile.log").write_text(r.stdout+r.stderr)
    assert r.returncode==0,r.stderr
    r=subprocess.run(["vvp",str(tmp_path/"unit.vvp")],capture_output=True,text=True,timeout=30,check=False)
    (tmp_path/"unit-only.log").write_text(r.stdout+r.stderr)
    assert r.returncode==0,r.stdout+r.stderr
    assert "UNIT_CLOCK_HEALTH_ONLY_NO_NATIVE_FFT_SERVICE" in r.stdout
