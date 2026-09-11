// Registered complete-search fixture; padding preserves the grid fixture bus.
module starlink_glrt_coarse_search_ooc_wrapper (
  input wire clk,
  input wire [116:0] stimulus,
  output reg [186:0] observation
);
  reg [116:0] launch;
  wire [186:0] response;
  always @(posedge clk) begin launch<=stimulus;observation<=response;end
  wire resetn,flush,arm,input_valid,input_gap,output_ready;
  wire copy_enable,copy_ready,copy_valid;
  wire [13:0] copy_address,copy_offset;
  wire [31:0] copy_data;
  wire signed [15:0] input_i,input_q;
  wire [63:0] input_index,window_first_index;
  wire busy,done,fault,output_valid;
  wire [11:0] output_epoch;
  wire output_epoch_left_tie;
  wire [3:0] output_frequency;
  wire [16:0] output_score;
  wire [2:0] output_rank;
  wire [31:0] rejected_arms;
  assign {resetn,flush,arm,input_valid,input_gap,output_ready,input_i,input_q,input_index,copy_enable,copy_address}=launch;
  assign response={busy,done,fault,output_valid,window_first_index,output_epoch,
      output_frequency,output_score,2'd0,output_epoch_left_tie,output_rank,rejected_arms,
      copy_ready,copy_valid,copy_offset,copy_data};
  (* keep_hierarchy="yes" *) starlink_glrt_coarse_search dut(.*);
endmodule
