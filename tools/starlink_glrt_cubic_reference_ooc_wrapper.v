// Timing fixture: same-clock launch/capture FFs bound every DUT data port.
module starlink_glrt_cubic_reference_ooc_wrapper #(
  parameter TEMPLATE_FILE = "native_cubic_60000000_upper.mem"
) (
  input wire clk,
  input wire [3:0] stimulus,
  output reg [76:0] observation
);
  reg [3:0] launch;
  wire [76:0] response;
  always @(posedge clk) begin
    launch <= stimulus;
    observation <= response;
  end
  wire job_ready, output_valid, output_last, aborted;
  wire signed [27:0] oi, oq;
  wire [16:0] output_index;
  assign response = {job_ready,output_valid,output_last,aborted,output_index,oi,oq};
  (* keep_hierarchy = "yes" *) starlink_glrt_cubic_reference #(
    .TEMPLATE_FILE(TEMPLATE_FILE)
  ) dut (
    .clk(clk),.resetn(launch[3]),.flush(launch[2]),.job_valid(launch[1]),
    .output_ready(launch[0]),.job_ready(job_ready),.output_valid(output_valid),
    .output_i(oi),.output_q(oq),.output_index(output_index),.output_last(output_last),.aborted(aborted)
  );
endmodule
