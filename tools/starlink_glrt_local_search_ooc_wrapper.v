// Registered fixture around both overlapping stages and local decisions.
module starlink_glrt_local_search_ooc_wrapper (
  input wire clk,
  input wire [101:0] stimulus,
  output reg [226:0] observation
);
  reg [101:0] launch;
  wire [226:0] response;
  always @(posedge clk) begin launch<=stimulus;observation<=response;end
  wire resetn,flush,arm,input_valid,input_gap,output_ready;
  wire signed [15:0] input_i,input_q;
  wire [63:0] input_index,window_first_index;
  wire busy,arm_ready,done,fault,output_valid,output_decision;
  wire [31:0] rejected_arms;
  wire [4:0] output_reasons;
  wire [2:0] output_rank,output_support;
  wire [11:0] output_epoch;
  wire [3:0] output_coarse_frequency;
  wire [16:0] output_coarse_score,output_acquire,output_verify,output_control,output_conditioned;
  wire signed [12:0] output_cfo_units;
  assign {resetn,flush,arm,input_valid,input_gap,output_ready,input_i,input_q,input_index}=launch;
  assign response={busy,arm_ready,done,fault,rejected_arms,window_first_index,output_valid,output_decision,
      output_reasons,output_rank,output_epoch,output_coarse_frequency,output_coarse_score,output_cfo_units,
      output_acquire,output_verify,output_control,output_conditioned,output_support};
  (* keep_hierarchy="yes" *) starlink_glrt_local_search dut(.*);
endmodule
