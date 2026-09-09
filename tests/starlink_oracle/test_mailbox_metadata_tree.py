"""All-bit/partial-group metadata checks and frozen mailbox behavior.

RTL and explicitly supplied actual-netlist replay evidence. The arithmetic-free
comparison has no added cycle. Full-receiver routing is a separate measurement.
"""
import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.mailbox_metadata_contract import (
    restore_legacy_metadata_comparison,
)

HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", Path(__file__).resolve().parents[2] / "hdl"))
ACQ = HDL / "library/starlink_pss_acquisition"
BASE = "18c96bb93f0aea5f868fb8b4c15a2eb1bce7a873"
RELATIVE = "library/starlink_pss_acquisition/starlink_pss_block_mailbox.v"


def frozen():
    return subprocess.run(["git", "-C", str(HDL), "show", f"{BASE}:{RELATIVE}"],
                          text=True, capture_output=True, timeout=10, check=True).stdout


def test_only_combinational_metadata_comparison_changes():
    candidate = (HDL / RELATIVE).read_text()
    assert "begin : balanced_metadata" in candidate
    assert restore_legacy_metadata_comparison(candidate) == frozen()


def run(tmp_path, bench, *, mutation=None):
    old, new = tmp_path / "old.v", tmp_path / "new.v"
    old.write_text(frozen().replace("module starlink_pss_block_mailbox #(", "module frozen_mailbox #(", 1))
    source = (HDL / RELATIVE).read_text()
    if mutation:
        before, after = mutation
        assert source.count(before) == 1
        source = source.replace(before, after, 1)
    new.write_text(source)
    stimulus = tmp_path / "probe.sv"
    stimulus.write_text(bench)
    executable = tmp_path / "probe.vvp"
    compiled = subprocess.run(["iverilog", "-g2012", "-Wall", "-s", "probe", "-o", str(executable),
                               str(old), str(new), str(stimulus)], text=True, capture_output=True,
                              timeout=30, check=False)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run(["vvp", str(executable)], text=True, capture_output=True, timeout=60, check=False)
    (tmp_path / "probe.log").write_text(result.stdout + result.stderr)
    return result


def equality_bench(width):
    return f"""`timescale 1ns/1ps
module probe;
  localparam W={width};
  reg [W-1:0] incoming=0, held=0;
  integer bit_index, pattern, digit, checks=0;
  starlink_pss_block_mailbox #(.METADATA_WIDTH(W),.EXPLICIT_COMMIT(1)) dut
    (.input_metadata(incoming),.input_clk(1'b0),.output_clk(1'b0),
     .input_resetn(1'b0),.output_resetn(1'b0),.input_valid(1'b0),
     .input_commit_authorized(1'b0),.input_data(36'd0),.input_position(9'd0),
     .input_last(1'b0),.output_ready(1'b0));
  task check;
    #0.1;
    if (dut.metadata_matches !== (incoming == held))
      $fatal(1,"METADATA_EQUALITY_MISMATCH W=%0d incoming=%h held=%h",W,incoming,held);
    checks=checks+1;
  endtask
  initial begin
    force dut.metadata_in_hold=held;
    check();
    for(bit_index=0;bit_index<W;bit_index=bit_index+1) begin
      incoming=0; held=0; incoming[bit_index]=1; check();
      held[bit_index]=1; check(); incoming[bit_index]=0; check();
      incoming='1; held='1; incoming[bit_index]=0; check();
      held[bit_index]=0; check();
      incoming='0; held='0; incoming[bit_index]=1'bx; check();
      held[bit_index]=1'bx; check(); incoming[bit_index]=1'bz; check();
      if(W>1) begin held[(bit_index+1)%W]=1; check(); end
    end
    if(W==3) for(pattern=0;pattern<4096;pattern=pattern+1) begin
      for(bit_index=0;bit_index<3;bit_index=bit_index+1) begin
        digit=(pattern>>(bit_index*2))&3;
        case(digit) 0:incoming[bit_index]=0; 1:incoming[bit_index]=1;
          2:incoming[bit_index]=1'bx; 3:incoming[bit_index]=1'bz; endcase
        digit=(pattern>>(6+bit_index*2))&3;
        case(digit) 0:held[bit_index]=0; 1:held[bit_index]=1;
          2:held[bit_index]=1'bx; 3:held[bit_index]=1'bz; endcase
      end
      check();
    end
    $display("METADATA_EQUALITY_PASS width=%0d checks=%0d forced_combinational_operands_only=1",W,checks);
    $finish;
  end
endmodule
"""


@pytest.mark.parametrize("width", [1, 2, 3, 4, 6, 7, 17, 18, 19, 70, 75, 76, 109])
def test_all_bits_tail_groups_and_four_state_logic(tmp_path, width):
    result = run(tmp_path, equality_bench(width))
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"METADATA_EQUALITY_PASS width={width} " in result.stdout
    if width == 3:
        assert "checks=4124" in result.stdout


def mailbox_bench(width, explicit, *, address_width=2, external_reset=0, startup_ns=0):
    outputs = {"input_ready": 1, "input_fault": 1, "input_framing_fault_now": 1,
               "output_valid": 1, "output_data": 36, "output_position": address_width,
               "output_last": 1, "output_metadata": width}
    shared = ["input_clk", "output_clk", "input_resetn", "output_resetn", "input_valid",
              "input_commit_authorized", "input_data", "input_position", "input_last",
              "input_metadata", "output_ready"]
    declarations, instances = [], []
    for module, inst in [("starlink_pss_block_mailbox", "n"), ("frozen_mailbox", "g")]:
        declarations += [f"wire [{bits-1}:0] {inst}_{name};" for name, bits in outputs.items()]
        connections = [f".{name}({name})" for name in shared] + [f".{name}({inst}_{name})" for name in outputs]
        instances.append(f"{module} #(.ADDRESS_WIDTH(AW),.METADATA_WIDTH(W),.RESET_RELEASE_EXTERNAL({external_reset}),.EXPLICIT_COMMIT({explicit})) {inst} ({','.join(connections)});")
    return f"""`timescale 1ns/1ps
module probe;
  localparam W={width}, AW={address_width}, DEPTH=1<<AW;
  reg input_clk=0,output_clk=0,input_resetn=0,output_resetn=0;
  always #2.5 input_clk=!input_clk;
  initial begin #1.3; forever #5.3 output_clk=!output_clk; end
  reg input_valid=0,input_commit_authorized=1,input_last=0,output_ready=0;
  reg [35:0] input_data=0;
  reg [AW-1:0] input_position=0;
  reg [W-1:0] input_metadata=0;
  integer bit_index, slot, fault_slot, word, timeout, checks=0, rejected=0, reads=0;
  reg [W-1:0] descriptor;
  {' '.join(declarations)}
  {' '.join(instances)}
  task boot;
    @(negedge input_clk); input_resetn=0;output_resetn=0;input_valid=0;output_ready=0;
    repeat(10) @(negedge input_clk);
    input_resetn=1;output_resetn=1;
    repeat(10) @(negedge input_clk);
    if(!n_input_ready || n_input_fault) $fatal(1,"METADATA_BOOT_FAIL");
  endtask
  task beat(input integer index,input integer bad_bit);
    @(negedge input_clk);input_position=index;input_last=index==DEPTH-1;
    input_data=index+7;input_metadata=descriptor;
    if(bad_bit>=0) input_metadata[bad_bit]=!input_metadata[bad_bit];
    input_valid=1; #0.1;
    if(!n_input_ready) $fatal(1,"METADATA_UNEXPECTED_NOT_READY");
    if(bad_bit>=0 && {explicit} && !n_input_framing_fault_now)
      $fatal(1,"METADATA_SAME_EDGE_VETO_MISSING bit=%0d slot=%0d",bad_bit,index);
    @(posedge input_clk);#0.3;
    if(bad_bit>=0 && (!n_input_fault || n.request_toggle))
      $fatal(1,"METADATA_BAD_BEAT_PUBLISHED");
    @(negedge input_clk);input_valid=0;
  endtask
  always @(posedge input_clk or negedge input_clk) if($realtime>{startup_ns}) begin
    #0.3;
    if({{n_input_ready,n_input_fault,n_input_framing_fault_now,n.request_toggle,n.write_position}} !==
       {{g_input_ready,g_input_fault,g_input_framing_fault_now,g.request_toggle,g.write_position}})
      $fatal(1,"METADATA_PUBLIC_INPUT_MISMATCH");
    checks=checks+1;
  end
  always @(posedge output_clk or negedge output_clk) if($realtime>{startup_ns}) begin
    #0.3;
    if(n_output_valid !== g_output_valid || (n_output_valid &&
      {{n_output_data,n_output_position,n_output_last,n_output_metadata}} !==
      {{g_output_data,g_output_position,g_output_last,g_output_metadata}}))
      $fatal(1,"METADATA_PUBLIC_OUTPUT_MISMATCH");
  end
  always @(posedge output_clk) if(output_ready && n_output_valid) reads=reads+1;
  initial begin
    #{startup_ns};
    descriptor='1;
    // Every bit, on each noninitial slot including the publication edge.
    for(bit_index=0;bit_index<W;bit_index=bit_index+1)
      for(slot=1;slot<4;slot=slot+1) begin
        boot();
        fault_slot=slot==3 ? DEPTH-1 : slot;
        for(word=0;word<=fault_slot;word=word+1) beat(word,word==fault_slot ? bit_index : -1);
        repeat(10) @(negedge input_clk);
        if(!n_input_fault || n_output_valid || n.request_toggle)
          $fatal(1,"METADATA_FAULT_NOT_QUARANTINED");
        rejected=rejected+1;
      end
    // Healthy publication, held output under stalls, and consumer ACK reuse.
    boot();
    for(slot=0;slot<3;slot=slot+1) begin
      descriptor=slot+17;
      for(word=0;word<DEPTH;word=word+1) beat(word,-1);
      repeat(20) @(negedge input_clk);
      if(!n_output_valid || n_input_ready) $fatal(1,"METADATA_PUBLICATION_MISSING");
      output_ready=1;
      for(timeout=0;timeout<DEPTH*8+20 && !n_input_ready;timeout=timeout+1)
        @(negedge input_clk);
      output_ready=0;
      if(!n_input_ready) $fatal(1,"METADATA_ACK_MISSING");
    end
    if(rejected!=W*3 || reads!=DEPTH*3) $fatal(1,"METADATA_COVERAGE_FAIL");
    $display("METADATA_MAILBOX_PASS width=%0d explicit={explicit} rejected=%0d words=%0d comparisons=%0d frozen_public=1",W,rejected,reads,checks);
    $finish;
  end
  initial begin #1000000;$fatal(1,"METADATA_WATCHDOG");end
endmodule
"""


@pytest.mark.parametrize("width", [70, 75, 76])
@pytest.mark.parametrize("explicit", [0, 1])
def test_every_metadata_bit_rejects_before_publication_and_matches_frozen_mailbox(tmp_path, width, explicit):
    result = run(tmp_path, mailbox_bench(width, explicit))
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"METADATA_MAILBOX_PASS width={width} explicit={explicit} rejected={width*3} words=12 " in result.stdout


@pytest.mark.parametrize("replacement", ["1'b1", "1'b0"])
def test_corrupted_tree_is_rejected(tmp_path, replacement):
    result = run(tmp_path, mailbox_bench(75, 1), mutation=(
        "assign metadata_matches = &group_equal;", f"assign metadata_matches = {replacement};"))
    assert result.returncode != 0 and "METADATA_" in result.stdout
    assert "METADATA_MAILBOX_PASS" not in result.stdout


@pytest.mark.parametrize("variant", ["baseline", "candidate"])
def test_actual_synthesized_512_word_mailboxes_match_frozen_public_behavior(tmp_path, variant):
    measured = os.environ.get("STARLINK_PSS_METADATA_TREE_NETLIST_DIR")
    if not measured:
        pytest.skip("explicit actual Vivado metadata-tree measurement required")
    measured = Path(measured)
    scope = (measured / "scope.txt").read_text()
    assert "MAILBOX_METADATA_TREE_MEASURED receiver_timing_and_hardware_unqualified=1" in scope
    assert f"baseline_commit={BASE}\n" in scope
    assert (measured / "baseline.v").read_text() == frozen()
    # The original paths are provenance, not a requirement to restore the
    # archive under its old temporary directory. Validate both frozen hashes
    # and filenames, then bind the candidate to the current source bytes.
    sources = re.search(r"^source_sha256=([0-9a-f]{64})  ([^\n]+)\n"
                        r"([0-9a-f]{64})  ([^\n]+)\n", scope, re.MULTILINE)
    assert sources is not None
    for name, digest, original_path in [
        ("baseline.v", sources[1], sources[2]), ("candidate.v", sources[3], sources[4]),
    ]:
        assert Path(original_path).name == name
        assert hashlib.sha256((measured / name).read_bytes()).hexdigest() == digest
    assert (measured / "candidate.v").read_bytes() == (ACQ / "starlink_pss_block_mailbox.v").read_bytes()
    netlist = measured / f"{variant}_netlist.v"
    assert f"{variant}_netlist_sha256={hashlib.sha256(netlist.read_bytes()).hexdigest()}\n" in scope
    old_path = tmp_path / "golden.v"
    old_path.write_text(frozen().replace("module starlink_pss_block_mailbox #(", "module frozen_mailbox #(", 1))
    bench = mailbox_bench(75, 1, address_width=9, external_reset=1, startup_ns=125)
    old = "starlink_pss_block_mailbox #(.ADDRESS_WIDTH(AW),.METADATA_WIDTH(W),.RESET_RELEASE_EXTERNAL(1),.EXPLICIT_COMMIT(1)) n"
    assert bench.count(old) == 1
    bench = bench.replace(old, "starlink_pss_block_mailbox n", 1)
    # Observe Q nets, not the similarly named FDRE instances. These spellings
    # are checked against the measured netlist; no netlist state deposits.
    netlist_source = netlist.read_text()
    for name, signal, declaration in [
        ("request_toggle", "request_toggle_reg_n_0", r"wire request_toggle_reg_n_0;"),
        ("write_position", "write_position_reg", r"wire \[8:0\]\s*write_position_reg;"),
    ]:
        assert re.search(declaration, netlist_source)
        bench = bench.replace(f"n.{name}", f"n.{signal}")
    bench_path = tmp_path / "probe.sv"
    bench_path.write_text(bench)
    vendor = Path("/opt/Xilinx/Vivado/2022.2")
    environment = dict(os.environ, LD_LIBRARY_PATH=str(vendor / "lib/lnx64.o/SuSE"))
    commands = [
        [str(vendor / "bin/xvlog"), "--sv", str(netlist), str(old_path), str(bench_path),
         str(vendor / "data/verilog/src/glbl.v")],
        [str(vendor / "bin/xelab"), "--debug", "typical", "--relax", "--mt", "2", "-L", "unisims_ver",
         "probe", "glbl", "-s", "metadata_snapshot"],
        [str(vendor / "bin/xsim"), "metadata_snapshot", "-runall"],
    ]
    for index, command in enumerate(commands):
        result = subprocess.run(command, cwd=tmp_path, env=environment, text=True,
                                capture_output=True, timeout=120, check=False)
        (tmp_path / f"netlist_{index}.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
    assert "METADATA_MAILBOX_PASS width=75 explicit=1 rejected=225 words=1536 " in result.stdout
