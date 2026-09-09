"""Same-edge map counter summary: frozen source contract and real map replays.

This qualifies binary reachable counter/summary behavior, not physical timing,
CDC, IIO, RF or a formal proof. Existing counter increments remain unchanged.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", ROOT / "hdl"))
ACQ = HDL / "library/starlink_pss_acquisition"
BASE = "52f921f69cbc1fd38e30db79911ef7ed761d229d"
MAP_PATH = "library/starlink_pss_acquisition/starlink_pss_phase_map.v"
ERRORS = {
    "discarded_score_count": 8,
    "discontinuity_abort_count": 2,
    "map_overrun_count": 2,
    "score_protocol_error_count": 1,
    "map_read_error_count": 1,
    "map_release_error_count": 1,
}
COUNTERS = ["accepted_score_count", *ERRORS, "map_publish_count", "map_arithmetic_overflow_count"]


def frozen(path):
    return subprocess.run(["git", "-C", str(HDL), "show", f"{BASE}:{path}"],
                          check=True, capture_output=True, text=True, timeout=10).stdout


def tokens(source):
    return re.sub(r"\s+", "", re.sub(r"//[^\n]*", "", source))


def test_every_error_increment_sets_summary_atomically_and_no_other_map_behavior_changes():
    baseline = tokens(frozen(MAP_PATH))
    candidate = tokens((HDL / MAP_PATH).read_text())
    for fragment in ["outputregmap_counter_fault,", "map_counter_fault<=1'b0;"]:
        assert candidate.count(fragment) == 1
        candidate = candidate.replace(fragment, "", 1)
    for counter, count in ERRORS.items():
        old = f"{counter}<=increment_saturating_32({counter});"
        new = f"{{map_counter_fault,{counter}}}<={{1'b1,increment_saturating_32({counter})}};"
        assert baseline.count(old) == count and candidate.count(new) == count
        candidate = candidate.replace(new, old)
    old_fault = re.search(r"wirelocal_map_fault=.*?;", baseline).group()
    new_fault = old_fault.replace(
        "|discarded_score_count|||discontinuity_abort_count|||map_overrun_count||"
        "|score_protocol_error_count|||map_arithmetic_overflow_count|||map_read_error_count||"
        "|map_release_error_count", "map_counter_fault", 1)
    assert candidate.count(new_fault) == 1 and new_fault != old_fault
    assert candidate.replace(new_fault, old_fault, 1) == baseline
    # No map error counter clears outside common reset, wraps, or changes width.
    for counter in [*ERRORS, "map_arithmetic_overflow_count"]:
        assert baseline.count(f"{counter}<=32'd0;") == 1


def probe(tmp_path, *, stop, bins=8, frames=4, mutant=False):
    width, frame_width = (bins - 1).bit_length(), (frames - 1).bit_length()
    stimulus = "tb_starlink_pss_phase_map_stop" if stop else "tb_starlink_pss_phase_map"
    instantiation = f"{stimulus} #(.BINS({bins}), .FRAMES({frames})) stimulus();" if stop else f"{stimulus} stimulus();"
    old = frozen(MAP_PATH).replace("module starlink_pss_phase_map #(", "module frozen_phase_map #(", 1)
    golden = tmp_path / "golden.v"
    golden.write_text(old)
    bench = ACQ / "tb" / f"{stimulus}.sv"
    if stop:
        # Existing directed test seeds generation exhaustion instead of
        # simulating billions of maps. Apply that same stimulus to BOTH maps.
        source = bench.read_text()
        seed = "dut.map_publish_count = 32'hfffffffe;"
        assert source.count(seed) == 1
        bench = tmp_path / "stop_stimulus.sv"
        bench.write_text(source.replace(seed, seed +
                         " map_summary_probe.golden.map_publish_count = 32'hfffffffe;", 1))
    runtime = ACQ / "starlink_pss_phase_map.v"
    if mutant:
        source = runtime.read_text()
        assert source.count("{1'b1, increment_saturating_32(") == 15
        runtime = tmp_path / "mutant.v"
        runtime.write_text(source.replace("{1'b1, increment_saturating_32(", "{1'b0, increment_saturating_32("))
    outputs = {
        "map_ready_mask": 2, "map_generation_0": 32, "map_generation_1": 32,
        "map_start_index_0": 64, "map_start_index_1": 64,
        "map_read_valid": 1, "map_read_data": 16, "map_read_error": 1,
        **dict.fromkeys(COUNTERS, 32),
        **dict.fromkeys(["stop_pending", "stop_ack", "stop_done", "stop_complete", "stop_failed", "stop_has_map"], 1),
        "stop_failure_reason": 6, "stop_generation": 32, "stop_start_index": 64, "stop_end_index": 64,
    }
    inputs = ["clk", "resetn", "acquisition_enable", "score_valid", "score_start_index", "score_phase",
              "score_value", "stream_discontinuity", "map_read_request", "map_read_bank", "map_read_index",
              "map_release", "map_release_bank", "stop_request"]
    declarations = "\n".join(f"wire [{bits - 1}:0] old_{name};" for name, bits in outputs.items())
    connections = ",\n".join([*(f".{name}(stimulus.dut.{name})" for name in inputs),
                                *(f".{name}(old_{name})" for name in outputs)])
    compared = [name for name in outputs if name != "map_read_data"]
    new_fields = ",".join(f"stimulus.dut.{name}" for name in compared)
    old_fields = ",".join(f"old_{name}" for name in compared)
    fault_or = " || ".join(f"|stimulus.dut.{name}" for name in [*ERRORS, "map_arithmetic_overflow_count"])
    harness = tmp_path / "summary.sv"
    harness.write_text(f'''`timescale 1ns/1ps
module map_summary_probe;
  {instantiation}
  {declarations}
  frozen_phase_map #(.PHASE_BINS({bins}), .PHASE_INDEX_WIDTH({width}),
    .TILE_FRAMES({frames}), .TILE_FRAME_WIDTH({frame_width}),
    .MAP_SEGMENT_ADDRESS_WIDTH({width}), .MAP_SEGMENT_COUNT(1), .MAP_SEGMENT_INDEX_WIDTH(1),
    .ENABLE_BOUNDARY_STOP({int(stop)})) golden ({connections});
  integer checks=0, fault_rows=0;
  reg failed=0;
  always @(posedge stimulus.clk or negedge stimulus.clk) begin
    #1.1;
    if ({{{new_fields}}} !== {{{old_fields}}}) begin
      failed=1; $fatal(1, "MAP_SUMMARY_PUBLIC_MISMATCH"); end
    if (old_map_read_valid && stimulus.dut.map_read_data !== old_map_read_data) begin
      failed=1; $fatal(1, "MAP_SUMMARY_PAYLOAD_MISMATCH"); end
    if (stimulus.dut.map_counter_fault !== ({fault_or})) begin
      failed=1; $fatal(1, "MAP_SUMMARY_COUNTER_MISMATCH time=%0t", $time); end
    checks=checks+1;
    if (stimulus.dut.map_counter_fault) fault_rows=fault_rows+1;
  end
  final begin
    if (checks < 50 || fault_rows == 0) $fatal(1, "MAP_SUMMARY_COVERAGE_MISSING");
    if (!failed) $display("MAP_COUNTER_SUMMARY_PASS stop={int(stop)} bins={bins} frames={frames} public_golden=1 same_edge_counters=1");
  end
endmodule
''')
    executable = tmp_path / "summary.vvp"
    (tmp_path / "build").mkdir()
    subprocess.run(["iverilog", "-g2012", "-Wall", "-s", "map_summary_probe", "-o", str(executable),
                    str(runtime), str(golden), str(ACQ / "starlink_pss_phase_map_bank.v"),
                    str(bench), str(harness)],
                   check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run(["vvp", str(executable)], cwd=tmp_path, check=False,
                            capture_output=True, text=True, timeout=30)
    (tmp_path / "summary.log").write_text(result.stdout + result.stderr)
    return result


@pytest.mark.parametrize("stop,bins,frames", [(False, 8, 4), (True, 4, 2), (True, 8, 4), (True, 16, 4)])
def test_exact_summary_and_frozen_public_map_behavior(tmp_path, stop, bins, frames):
    result = probe(tmp_path, stop=stop, bins=bins, frames=frames)
    text = result.stdout + result.stderr
    assert result.returncode == 0 and "FATAL" not in text and "FAIL" not in text, text
    assert text.splitlines().count(
        f"MAP_COUNTER_SUMMARY_PASS stop={int(stop)} bins={bins} frames={frames} public_golden=1 same_edge_counters=1"
    ) == 1


@pytest.mark.parametrize("stop", [False, True])
def test_actual_counter_events_reject_a_summary_that_omits_errors(tmp_path, stop):
    result = probe(tmp_path, stop=stop, mutant=True)
    assert result.returncode != 0 and "MAP_SUMMARY_COUNTER_MISMATCH" in result.stdout
