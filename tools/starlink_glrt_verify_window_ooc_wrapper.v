// Registered component fixture; timing exceptions apply only to fixture IO.
module starlink_glrt_verify_window_ooc_wrapper (
  input wire clk,
  input wire [139:0] stimulus,
  output reg [130:0] observation
);
  reg [139:0] launch;
  wire [130:0] response;
  always @(posedge clk) begin launch<=stimulus;observation<=response;end
  wire resetn,flush,arm,input_valid,input_gap,output_ready,job_valid,job_step_500;
  wire signed [15:0] input_i,input_q;
  wire [63:0] input_index,window_first_index;
  wire [11:0] job_epoch;
  wire signed [12:0] job_cfo_units;
  wire [8:0] job_frequency_count,output_frequency;
  wire [1:0] job_subset;
  wire busy,job_ready,window_loaded,done,fault,output_valid;
  wire [16:0] output_score;
  wire [2:0] output_support;
  wire [31:0] rejected_arms;
  assign {resetn,flush,arm,input_valid,input_gap,output_ready,input_i,input_q,input_index,
      job_valid,job_epoch,job_cfo_units,job_step_500,job_frequency_count,job_subset}=launch;
  assign response={busy,job_ready,window_loaded,done,fault,output_valid,window_first_index,
      output_frequency,output_score,output_support,rejected_arms};
  (* keep_hierarchy="yes" *) starlink_glrt_verify_window3 dut(.*);
endmodule
