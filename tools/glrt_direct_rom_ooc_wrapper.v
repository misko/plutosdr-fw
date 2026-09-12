// Registered fixture boundaries, not deployed receiver logic.
module glrt_direct_rom_ooc_wrapper #(
  parameter integer PACKED=0,
  parameter TEMPLATE_FILE=""
) (
  input wire clk,
  input wire [5:0] stimulus,
  output reg [83:0] observation
);
  reg [5:0] launch;
  wire [83:0] response;
  always @(posedge clk) begin launch<=stimulus;observation<=response;end
  wire resetn,flush,job_valid,output_ready;
  wire [1:0] phase;
  wire ready,valid,last,aborted;
  wire signed [15:0] ri,rq,di,dq;
  wire [11:0] index;
  wire [3:0] clipped;
  assign {resetn,flush,job_valid,output_ready,phase}=launch;
  assign response={ready,valid,ri,rq,di,dq,index,last,clipped,aborted};
  generate if(PACKED) begin : g_packed
    starlink_glrt_packed_direct_coefficients #(.SAMPLE_COUNT(3300),.PHASE_COUNT(4),.TEMPLATE_FILE(TEMPLATE_FILE)) dut (
      .clk(clk),.resetn(resetn),.flush(flush),.job_valid(job_valid),.job_phase(phase),.job_ready(ready),
      .output_valid(valid),.output_ready(output_ready),.reference_i(ri),.reference_q(rq),
      .derivative_i(di),.derivative_q(dq),.output_index(index),.output_last(last),.output_clipped(clipped),.aborted(aborted));
  end else begin : g_wide
    starlink_glrt_direct_coefficients #(.SAMPLE_COUNT(3300),.PHASE_COUNT(4),.TEMPLATE_FILE(TEMPLATE_FILE)) dut (
      .clk(clk),.resetn(resetn),.flush(flush),.job_valid(job_valid),.job_phase(phase),.job_ready(ready),
      .output_valid(valid),.output_ready(output_ready),.reference_i(ri),.reference_q(rq),
      .derivative_i(di),.derivative_q(dq),.output_index(index),.output_last(last),.output_clipped(clipped),.aborted(aborted));
  end endgenerate
endmodule
