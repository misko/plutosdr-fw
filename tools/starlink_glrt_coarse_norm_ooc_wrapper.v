// Registered boundaries isolate the 100 MHz normalization component paths.
module starlink_glrt_coarse_norm_ooc_wrapper (
  input wire clk,
  input wire [162:0] stimulus,
  output reg [51:0] observation
);
  reg [162:0] launch;
  wire [51:0] response;
  always @(posedge clk) begin launch<=stimulus; observation<=response; end
  wire resetn,flush,input_valid,output_valid,zero_energy,ratio_clamped;
  wire [63:0] numerator_power,denominator_power;
  wire [31:0] input_tag,output_tag;
  wire [16:0] score_q16;
  assign {resetn,flush,input_valid,numerator_power,denominator_power,input_tag}=launch;
  assign response={output_valid,score_q16,zero_energy,ratio_clamped,output_tag};
  (* keep_hierarchy="yes" *) starlink_glrt_coarse_norm dut(.*);
endmodule
