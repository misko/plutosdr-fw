// Timing fixture only. Real launch/capture registers bound every DUT data port
// on its 100 MHz fabric clock. External fixture I/O is outside this OOC test.
module starlink_glrt_local_moments_ooc_wrapper (
  input wire clk,
  input wire [299:0] stimulus,
  output reg [471:0] observation
);
  reg [299:0] launch;
  wire [471:0] response;
  always @(posedge clk) begin
    launch <= stimulus;
    observation <= response;
  end
  wire resetn, flush, job_valid, input_valid, input_gap, products_closed, result_ready;
  wire [63:0] job_start, input_index;
  wire signed [32:0] pri, prq, pdi, pdq;
  wire [32:0] power;
  assign {resetn,flush,job_valid,job_start,input_valid,input_gap,products_closed,
      input_index,pri,prq,pdi,pdq,power,result_ready} = launch;
  wire job_ready, active, result_valid;
  wire [63:0] result_start;
  wire [16:0] result_count;
  wire [3:0] result_fault;
  wire signed [49:0] ri, rq, di, dq;
  wire signed [66:0] ti, tq;
  wire [49:0] energy;
  assign response = {job_ready,active,result_valid,result_start,result_count,
      result_fault,ri,rq,di,dq,ti,tq,energy};
  (* keep_hierarchy = "yes" *) starlink_glrt_local_moments dut (
    .clk(clk),.resetn(resetn),.flush(flush),
    .job_valid(job_valid),.job_ready(job_ready),.job_start(job_start),
    .input_valid(input_valid),.input_gap(input_gap),.products_closed(products_closed),
    .input_index(input_index),.reference_product_i(pri),.reference_product_q(prq),
    .delay_product_i(pdi),.delay_product_q(pdq),.sample_power(power),
    .active(active),.result_valid(result_valid),.result_ready(result_ready),
    .result_start(result_start),.result_count(result_count),.result_fault(result_fault),
    .reference_sum_i(ri),.reference_sum_q(rq),.delay_sum_i(di),.delay_sum_q(dq),
    .reference_prefix_integral_i(ti),.reference_prefix_integral_q(tq),.observed_energy(energy)
  );
endmodule
