// Timing fixture: same-clock launch/capture FFs bound every DUT data port.
module starlink_glrt_cubic_coefficients_ooc_wrapper #(
  parameter TEMPLATE_FILE = "native_cubic_60000000_upper.mem"
) (
  input wire clk,
  input wire [3:0] stimulus,
  output reg [88:0] observation
);
  reg [3:0] launch;
  wire [88:0] response;
  always @(posedge clk) begin
    launch <= stimulus;
    observation <= response;
  end
  wire job_ready, output_valid, output_last, aborted;
  wire signed [15:0] ri, rq, di, dq;
  wire [16:0] output_index;
  wire [3:0] clipped;
  assign response = {job_ready,output_valid,output_last,aborted,output_index,clipped,ri,rq,di,dq};
  (* keep_hierarchy = "yes" *) starlink_glrt_cubic_coefficients #(
    .TEMPLATE_FILE(TEMPLATE_FILE)
  ) dut (
    .clk(clk),.resetn(launch[3]),.flush(launch[2]),.job_valid(launch[1]),
    .output_ready(launch[0]),.job_ready(job_ready),.output_valid(output_valid),
    .reference_i(ri),.reference_q(rq),.derivative_i(di),.derivative_q(dq),
    .output_index(output_index),.output_last(output_last),.output_clipped(clipped),.aborted(aborted)
  );
endmodule
