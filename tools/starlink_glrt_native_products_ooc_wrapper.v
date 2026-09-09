// Same-clock registered boundaries for every native-products DUT data port.
module starlink_glrt_native_products_ooc_wrapper (
  input wire clk,
  input wire [198:0] stimulus,
  output reg [244:0] observation
);
  reg [198:0] launch;
  wire [244:0] response;
  always @(posedge clk) begin
    launch <= stimulus;
    observation <= response;
  end
  wire resetn, flush, input_valid;
  wire [63:0] input_index, output_index;
  wire [31:0] phase;
  wire signed [15:0] ii,iq,ri,rq,di,dq;
  wire [3:0] clipped, output_clipped;
  wire output_valid;
  wire signed [34:0] pri,prq,pdi,pdq;
  wire [35:0] power;
  assign {resetn,flush,input_valid,input_index,ii,iq,phase,ri,rq,di,dq,clipped} = launch;
  assign response = {output_valid,output_index,output_clipped,pri,prq,pdi,pdq,power};
  (* keep_hierarchy = "yes" *) starlink_glrt_native_products dut (
    .clk(clk),.resetn(resetn),.flush(flush),.input_valid(input_valid),.input_index(input_index),
    .input_i(ii),.input_q(iq),.input_phase(phase),.reference_i(ri),.reference_q(rq),
    .derivative_i(di),.derivative_q(dq),.input_clipped(clipped),.output_valid(output_valid),
    .output_index(output_index),.output_clipped(output_clipped),.reference_product_i(pri),
    .reference_product_q(prq),.delay_product_i(pdi),.delay_product_q(pdq),.sample_power(power)
  );
endmodule
