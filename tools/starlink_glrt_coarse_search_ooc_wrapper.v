// Registered complete-search fixture; padding preserves the grid fixture bus.
module starlink_glrt_coarse_search_ooc_wrapper (
  input wire clk,
  input wire [101:0] stimulus,
  output reg [138:0] observation
);
  reg [101:0] launch;
  wire [138:0] response;
  always @(posedge clk) begin launch<=stimulus;observation<=response;end
  wire resetn,flush,arm,input_valid,input_gap,output_ready;
  wire signed [15:0] input_i,input_q;
  wire [63:0] input_index,window_first_index;
  wire busy,done,fault,output_valid;
  wire [11:0] output_epoch;
  wire [3:0] output_frequency;
  wire [16:0] output_score;
  wire [2:0] output_rank;
  wire [31:0] rejected_arms;
  assign {resetn,flush,arm,input_valid,input_gap,output_ready,input_i,input_q,input_index}=launch;
  assign response={busy,done,fault,output_valid,window_first_index,output_epoch,
      output_frequency,output_score,3'd0,output_rank,rejected_arms};
  (* keep_hierarchy="yes" *) starlink_glrt_coarse_search dut(.*);
endmodule
