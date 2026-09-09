"""Private bridge fault summary against an immutable complete controller.

Decoder-injected controller tests, not native AXI/core/RF evidence. Separate
test_stop_health_integration replays the actual AXI + map workload. Here every
counter increment site, immediate veto, observation phase, reset and seeded
saturation is checked without changing the frozen controller's fault policy.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", ROOT / "hdl"))
SOURCE = "library/axi_starlink_pss_acquisition/axi_starlink_pss_phase_map_sync.v"
BASE = "6090190c4442d2fd0e825136d87b692e2ad6deef"
COUNTERS = ["bridge_read_error_count", "bridge_release_error_count", "snapshot_request_overrun_count"]


def frozen():
    return subprocess.run(["git", "-C", str(HDL), "show", f"{BASE}:{SOURCE}"],
                          capture_output=True, text=True, check=True, timeout=10).stdout


def tokens(source):
    return re.sub(r"\s+", "", re.sub(r"//[^\n]*", "", source))


def test_only_private_atomic_summary_changes_and_all_current_vetoes_survive():
    old, new = tokens(frozen()), tokens((HDL / SOURCE).read_text())
    for fragment in ["regbridge_counter_fault;", "bridge_counter_fault<=1'b0;"]:
        assert new.count(fragment) == 1
        new = new.replace(fragment, "", 1)
    for name, count in zip(COUNTERS, [2, 2, 1], strict=True):
        update = f"{name}<=increment_saturating_32({name});"
        atomic = f"{{bridge_counter_fault,{name}}}<={{1'b1,increment_saturating_32({name})}};"
        assert new.count(atomic) == count and old.count(update) == count
        assert old.count(f"{name}<=32'd0;") == 1
        new = new.replace(atomic, update)
    before = "wirestop_bridge_fault_now=bridge_counter_fault||"
    after = "wirestop_bridge_fault_now=|bridge_read_error_count|||bridge_release_error_count|||snapshot_request_overrun_count||"
    assert new.count(before) == 1
    assert new.replace(before, after, 1) == old


STIMULUS = r"""
  reg wq=0, rq=0;
  reg [5:0] wa=0, ra=0;
  reg [31:0] wd=0;
  reg [3:0] ws=0;
  integer checks=0, events[0:4], mode, kind, cycle;
  reg [31:0] random_state=32'h27182818;
  task automatic step;
    @(posedge clk); #2; @(negedge clk); #0.1;
  endtask
  task automatic write_command(input [5:0] address, input [31:0] value);
    wq=1; wa=address; wd=value; ws=15; step(); wq=0;
  endtask
  task automatic boot(input bit use_map_reset);
    wq=0; rq=0; map_read_error=0; map_read_valid=0; map_ready_mask=3;
    stop_ack=0; stop_done=0; stop_complete=0; stop_failed=0; stop_ready=1;
    if (use_map_reset) map_reset=1; else s_axi_aresetn=0;
    step(); step(); map_reset=0; s_axi_aresetn=1; step();
    if ({n.bridge_read_error_count,n.bridge_release_error_count,
         n.snapshot_request_overrun_count,n.bridge_counter_fault} !== 97'd0)
      $fatal(1,"BRIDGE_RESET_FAIL");
    write_command(6'h05,1); step();
  endtask
  // Only the decoded bus is injected; pending flags come from real controller
  // execution. The public AXI engine serializes some write coincidences, so
  // these additional handler tests must not be described as native AXI proof.
  task automatic prepare_event(input integer event_kind, input bit stage);
    if (stage) begin wq=1; wa=6'h3e; wd=1; ws=15; end
    case (event_kind)
      0,2: begin rq=1; ra=9; step(); rq=0; wq=0; end
      1,4: begin write_command(6'ha,1); end
      3: begin write_command(6'hc,1); end
    endcase
    case (event_kind)
      0: map_read_error=1;
      1: map_ready_mask=0;
      2: begin wq=1; wa=6'ha; wd=1; ws=15; end
      3: begin wq=1; wa=6'hc; wd=1; ws=15; end
      4: begin rq=1; ra=9; end
    endcase
    #0.2;
    if (n.stop_bridge_fault_now !== 1 || g.stop_bridge_fault_now !== 1)
      $fatal(1,"BRIDGE_IMMEDIATE_VETO_MISSING event=%0d",event_kind);
    if (stage && (!n.stop_staged || n.stop_request !== 0))
      $fatal(1,"BRIDGE_STAGED_VETO_MISSING");
  endtask
  task automatic finish_event;
    step(); wq=0; rq=0; map_read_error=0; map_ready_mask=3; map_read_valid=1;
    step(); map_read_valid=0; step();
    if (!n.bridge_counter_fault) $fatal(1,"BRIDGE_SUMMARY_LOST");
  endtask
  task automatic fire(input integer event_kind);
    prepare_event(event_kind,0); finish_event();
  endtask
  always @(posedge clk) begin
    if (s_axi_aresetn && !map_reset) begin
      if (n.read_pending && map_read_error) events[0]=events[0]+1;
      if (n.release_pending && !map_ready_mask[n.map_release_bank]) events[1]=events[1]+1;
      if (wq && wa==10 && ws[0] && wd[0] && (n.read_pending || n.release_pending))
        events[2]=events[2]+1;
      if (wq && wa==12 && ws[0] && wd[0] && n.snapshot_pending) events[3]=events[3]+1;
      if (rq && ra==9 && !n.register_read_pending && !n.read_pending && n.release_pending)
        events[4]=events[4]+1;
    end
  end
  always @(posedge clk or negedge clk) begin
    #1;
    if ({PUBLIC_NEW} !== {PUBLIC_OLD}) $fatal(1,"BRIDGE_PUBLIC_MISMATCH");
    if ({PRIVATE_NEW} !== {PRIVATE_OLD}) $fatal(1,"BRIDGE_PRIVATE_MISMATCH");
    if (n.bridge_counter_fault !== (|n.bridge_read_error_count ||
        |n.bridge_release_error_count || |n.snapshot_request_overrun_count))
      $fatal(1,"BRIDGE_COUNTER_SUMMARY_MISMATCH");
    checks=checks+1;
  end
  initial begin
    FORCE_DECODER
    for (kind=0;kind<5;kind=kind+1) events[kind]=0;
    // Three observation phases: before stop, active, and retained terminal.
    for (mode=0;mode<(ENABLED ? 3 : 1);mode=mode+1) begin
      for (kind=0;kind<5;kind=kind+1) begin
        boot(kind%2);
        if (mode>0) begin
          write_command(6'h3e,1); step();
          if (!n.stop_active) $fatal(1,"BRIDGE_ACTIVE_COVERAGE_MISSING");
        end
        if (mode==2) begin
          stop_ack=1; stop_done=1; stop_complete=1; step(); stop_ack=0; stop_done=0;
          if (!n.stop_terminal_valid) $fatal(1,"BRIDGE_TERMINAL_COVERAGE_MISSING");
        end
        fire(kind);
        if (mode>0 && !n.stop_visible_failure[2]) $fatal(1,"BRIDGE_REASON_MISSING");
        if (n.bridge_read_error_count !== ((kind==0 || kind==4) ? 32'd1 : 32'd0) ||
            n.bridge_release_error_count !== ((kind==1 || kind==2) ? 32'd1 : 32'd0) ||
            n.snapshot_request_overrun_count !== (kind==3 ? 32'd1 : 32'd0))
          $fatal(1,"BRIDGE_EXACT_EVENT_COUNT_FAIL kind=%0d",kind);
      end
    end
    // Read and write decoders can independently stage a read and stop ticket.
    if (ENABLED) for (kind=0;kind<3;kind=kind+2) begin
      boot(0); prepare_event(kind,1); finish_event();
      if (n.stop_accepted_ticket != 0 || n.stop_command_status != 5 || n.stop_active)
        $fatal(1,"BRIDGE_STAGED_ACCEPTANCE_FAIL");
    end
    // Do not pretend billions of events were simulated: seed BOTH unchanged
    // counters near saturation, after the same real event set the summary.
    SATURATION_CASES
    boot(1);
    for (cycle=0;cycle<1024;cycle=cycle+1) begin
      random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
      wq=random_state[0]; rq=random_state[1]; ws=random_state[5:2]; wd=random_state;
      case (random_state[8:6])
        0: wa=5; 1: wa=7; 2: wa=8; 3: wa=10; 4: wa=12; 5: wa=62; default: wa=63;
      endcase
      ra=random_state[9] ? 9 : random_state[15:10];
      map_read_valid=random_state[16]; map_read_error=random_state[17];
      map_ready_mask=random_state[19:18];
      stop_ready=random_state[20]; stop_ack=random_state[21]; stop_done=random_state[22];
      stop_complete=random_state[23]; stop_failed=random_state[24];
      step();
    end
    boot(0); boot(1);
    for (kind=0;kind<5;kind=kind+1)
      if (events[kind]<2) $fatal(1,"BRIDGE_EVENT_COVERAGE_MISSING");
    if (checks<2200) $fatal(1,"BRIDGE_COMPARISON_COVERAGE_MISSING");
    $display("BRIDGE_SUMMARY_PASS enabled=%0d checks=%0d sites=5 resets=2 saturation_seeded=3 decoder_injection=1 hardware_qualified=0",ENABLED,checks);
    $finish;
  end
  initial begin #1000000; $fatal(1,"BRIDGE_TIMEOUT"); end
"""


def run_probe(tmp_path, enabled, mutation=None):
    baseline, candidate = frozen(), (HDL / SOURCE).read_text()
    if mutation is not None and mutation.startswith("site_"):
        site = int(mutation.removeprefix("site_"))
        matches = list(re.finditer(r"\{1'b1, increment_saturating_32\(", candidate))
        assert len(matches) == 5
        start = matches[site].start()
        candidate = candidate[:start] + candidate[start:].replace("{1'b1,", "{1'b0,", 1)
    elif mutation == "delayed":
        candidate, count = re.subn(r"\{1'b1, increment_saturating_32\((\w+)\)\}",
                                   r"{|\1, increment_saturating_32(\1)}", candidate)
        assert count == 5
    elif mutation == "no_immediate":
        candidate, count = re.subn(r"wire stop_bridge_fault_now =.*?;",
                                   "wire stop_bridge_fault_now = bridge_counter_fault;",
                                   candidate, flags=re.DOTALL)
        assert count == 1
    old_path, new_path = tmp_path / "old.v", tmp_path / "new.v"
    old_path.write_text(baseline.replace("module axi_starlink_pss_phase_map_sync #(", "module frozen_controller #(", 1))
    new_path.write_text(candidate)
    header = baseline.split(");", 1)[0]
    ports = re.findall(r"^\s*(input|output)\s+(?:wire|reg)\s+(\[[^\]]+\])?\s*(\w+)\s*,?\s*$", header, re.MULTILINE)
    assert len(ports) == 78
    assert len(ports) == len(re.findall(r"^\s*(?:input|output)\b", header, re.MULTILINE))
    declarations, connections = [], {"n": [], "g": []}
    outputs = []
    for direction, width, name in ports:
        if direction == "input":
            if name not in {"map_clk", "s_axi_aclk"}:
                declarations.append(f"reg {width} {name}=0;")
            for signals in connections.values():
                signals.append(f".{name}({'clk' if name in {'map_clk', 's_axi_aclk'} else name})")
        else:
            outputs.append(name)
            for instance, signals in connections.items():
                declarations.append(f"wire {width} {instance}_{name};")
                signals.append(f".{name}({instance}_{name})")
    private = [*COUNTERS, "stop_bridge_fault_now", "stop_visible_failure", "stop_accepted_ticket",
               "stop_staged", "stop_active", "stop_terminal_valid", "stop_command_status"]
    force_decoder = "\n".join(f"force {inst}.{name}={driver};" for inst in connections for name, driver in
        [("up_wreq", "wq"), ("up_waddr", "wa"), ("up_wdata", "wd"), ("up_wstrb", "ws"),
         ("up_rreq", "rq"), ("up_raddr", "ra")])
    saturation = "\n".join(f"""
      boot(0); fire({kind});
      n.{name}=32'hfffffffe; g.{name}=32'hfffffffe;
      fire({kind}); if(n.{name}!==32'hffffffff) $fatal(1,"BRIDGE_SATURATION_FAIL");
      fire({kind}); if(n.{name}!==32'hffffffff) $fatal(1,"BRIDGE_WRAP_FAIL");
    """ for name, kind in zip(COUNTERS, [0, 1, 3], strict=True))
    stimulus = STIMULUS.replace("PUBLIC_NEW", ",".join(f"n_{p}" for p in outputs))
    stimulus = stimulus.replace("PUBLIC_OLD", ",".join(f"g_{p}" for p in outputs))
    stimulus = stimulus.replace("PRIVATE_NEW", ",".join(f"n.{p}" for p in private))
    stimulus = stimulus.replace("PRIVATE_OLD", ",".join(f"g.{p}" for p in private))
    stimulus = stimulus.replace("FORCE_DECODER", force_decoder).replace("SATURATION_CASES", saturation)
    bench = tmp_path / "probe.sv"
    instances = "\n".join(f"""{module} #(.PHASE_BINS(8),.PHASE_INDEX_WIDTH(3),.TILE_FRAMES(4),
      .USE_SHARED_XFFT(1),.ENABLE_BOUNDARY_STOP(ENABLED),.HEALTH_COUNTERS_FROM_FLAGS(1),
      .MAP_COUNTERS_FROM_FLAG(1)) {inst} ({','.join(connections[inst])});"""
      for module, inst in [("axi_starlink_pss_phase_map_sync", "n"), ("frozen_controller", "g")])
    bench.write_text(f"""`timescale 1ns/1ps
module probe;
  localparam PHASE_INDEX_WIDTH=3, MAP_WIDTH=16, ENABLED={enabled};
  reg clk=0; always #5 clk=!clk;
  {' '.join(declarations)}
  {instances}
  {stimulus}
endmodule
""")
    executable = tmp_path / "probe.vvp"
    compiled = subprocess.run(["iverilog", "-g2012", "-Wall", "-s", "probe", "-o", str(executable),
        str(old_path), str(new_path), str(HDL / "library/axi_starlink_pss_phase_map/starlink_pss_axi_lite.v"),
        str(bench)], capture_output=True, text=True, timeout=30, check=False)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run(["vvp", str(executable)], capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "probe.log").write_text(result.stdout + result.stderr)
    return result


@pytest.mark.parametrize("enabled", [0, 1])
def test_complete_controller_matches_frozen_outputs_for_all_bridge_increment_sites(tmp_path, enabled):
    result = run_probe(tmp_path, enabled)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count(f"BRIDGE_SUMMARY_PASS enabled={enabled}") == 1


@pytest.mark.parametrize("mutation", [*(f"site_{n}" for n in range(5)), "delayed", "no_immediate"])
def test_probe_rejects_each_missing_or_delayed_fault_and_removed_current_veto(tmp_path, mutation):
    result = run_probe(tmp_path, 1, mutation)
    assert result.returncode != 0 and "BRIDGE_" in result.stdout
    assert "BRIDGE_SUMMARY_PASS" not in result.stdout
