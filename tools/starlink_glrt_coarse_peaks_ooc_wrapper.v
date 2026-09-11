module starlink_glrt_coarse_peaks_ooc_wrapper (
  input wire clk,
  input wire [37:0] stimulus,
  output reg [41:0] observation
);
  reg [37:0] launch;
  wire [41:0] response;
  always @(posedge clk) begin launch<=stimulus;observation<=response;end
  wire resetn,flush,arm,input_valid,output_ready,input_ready,busy,output_valid,done,fault;
  wire [11:0] input_epoch,output_epoch;
  wire [3:0] input_frequency,output_frequency;
  wire [16:0] input_score,output_score;
  wire [2:0] output_rank;
  wire output_epoch_left_tie;
  assign {resetn,flush,arm,input_valid,output_ready,input_epoch,input_frequency,input_score}=launch;
  assign response={input_ready,busy,output_valid,done,fault,output_rank,output_epoch,
      output_epoch_left_tie,output_frequency,output_score};
  (* keep_hierarchy="yes" *) starlink_glrt_coarse_peaks dut(.*);
endmodule
