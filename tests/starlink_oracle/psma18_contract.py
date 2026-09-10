"""Bounded Stage A60 specimens. No FFT/native/PIL1 execution.

The map specimen strictly adapts the complete frozen PSMA17 bench, retaining
every lifetime/assertion/counter test. Its single actual x2 fault producer is
at the controller's public counter boundary, NOT a claimed source60 cascade.
The separate wrapper bench exercises the real two-stage cascade and CDC.
"""

import hashlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = Path(os.environ.get("STARLINK_PSS_TEST_HDL", ROOT / "hdl")) / "library"
WRAPPER = "library/axi_starlink_pss_acquisition/axi_starlink_pss_acquisition.v"
CONTROLLER = "library/axi_starlink_pss_acquisition/axi_starlink_pss_phase_map_sync.v"
BANK_FIELDS = ["ENABLE_BANK60_PAIRED", "INPUT_RATE_MSPS", "USE_BANK_OWNED_XFFT",
               "ENABLE_PILOT_TAP", "USE_SHARED_XFFT", "USE_REALTIME_XFFT", "ENABLE_BOUNDARY_STOP"]
PARAMETERS = dict.fromkeys(BANK_FIELDS, 1) | {"INPUT_RATE_MSPS": 60}


def replace_exact(source, before, after, count=1):
    assert source.count(before) == count, f"unexpected source context: {before!r}"
    return source.replace(before, after)


def lifecycle_source():
    original = (LIB / "axi_starlink_pss_acquisition/tb/tb_axi_starlink_pss_psma17.sv").read_text()
    assert hashlib.sha256(original.encode()).hexdigest() == \
        "d4837e3c749f6f789c4c89f315c317f489f109d0a7833957d5a27af6c4f00cd7"
    changes = [
        ("tb_axi_starlink_pss_psma17", "tb_axi_starlink_pss_psma18", 1),
        ("parameter integer INPUT_RATE_MSPS = 30", "parameter integer INPUT_RATE_MSPS = 60", 1),
        ("parameter [30:0] COEFFICIENT_ENERGY = 31'd1073744004", "parameter [30:0] COEFFICIENT_ENERGY = 31'd1073765335", 1),
        ("  ) control (.map_clk(clk)", "    , .ENABLE_BANK60_PAIRED(1)\n  ) control (.map_clk(clk)", 1),
        ("32'h10007", "32'h10008", 1),
        ("expect_register(8'hb0, 30)", "expect_register(8'hb0, 60)", 1),
        ("32'h000f0203", "32'h020f0403", 1),
        ("expect_register(8'hb8, 7)", "expect_register(8'hb8, 21)", 1),
        ("expect_register(8'hbc, 1073744004)", "expect_register(8'hbc, 1073765335)", 1),
        *[(a, b, 1) for a, b in zip(
            ["73142604", "7077b036", "f9213db3", "574e4a55", "6fd424b9", "7a293843", "bd6ee085", "c2bf33af"],
            ["8e807d15", "d5372b0a", "9669d119", "0d899697", "e7c2911a", "73ddfb23", "095806c2", "a31de5b2"], strict=True)],
        ("PSMA17_", "PSMA18_", 3),
        ("real_ddc=1 synthetic_scores=1", "single_real_x2_public_fault_producer=1 synthetic_scores=1", 1),
    ]
    result = original
    for before, after, count in changes:
        result = replace_exact(result, before, after, count)
    restored = result
    for before, after, count in reversed(changes):
        restored = replace_exact(restored, after, before, count)
    assert restored == original, "entire lifecycle body must be recoverable"
    return result


# Deliberately synthetic stage-output interface, used ONLY to exercise the
# wrapper's 33-bit aggregation at first/second/both/overflow boundaries.
# Public source-index bits carry each stage's requested counter value. No
# hierarchy writes or forced real counters, no DDC arithmetic claim.
COUNTER_STAGE_STUB = """`timescale 1ns/1ps
module starlink_pss_x2_ddc #(
  parameter integer EDGE_UPPER=1, WIDE_OBSERVATION_COUNTERS=0
) (
  input wire clk, resetn, enable, flush, input_valid, input_gap,
  input wire signed [15:0] input_i, input_q,
  input wire [63:0] input_index,
  output wire output_enable,
  output reg output_valid=0, output_gap=0,
  output reg signed [15:0] output_i=0, output_q=0,
  output reg [63:0] output_index=0,
  output reg [63:0] accepted_sample_count=0, emitted_sample_count=0,
  output reg [31:0] discontinuity_count=0, saturation_event_count=0
);
  assign output_enable=enable && resetn && !flush;
  always @(posedge clk) begin
    if (!resetn) begin
      output_valid<=0; discontinuity_count<=0; saturation_event_count<=0;
      accepted_sample_count<=0; emitted_sample_count<=0;
    end else if (!enable || flush) output_valid<=0;
    else begin
      output_valid<=input_valid;
      if(input_valid) begin
        discontinuity_count<=input_index[31:0];
        saturation_event_count<={input_q,input_i};
        output_index<={32'd0,input_index[63:32]};
        output_i<=input_i; output_q<=input_q;
        accepted_sample_count<=accepted_sample_count+1;
        emitted_sample_count<=emitted_sample_count+1;
      end
    end
  end
endmodule
"""
