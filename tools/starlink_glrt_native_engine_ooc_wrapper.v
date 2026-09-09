// Same-clock registered boundaries for every native-engine DUT data port.
module starlink_glrt_native_engine_ooc_wrapper #(
  parameter TEMPLATE_FILE="native_cubic_60000000_upper.mem"
) (
  input wire clk,
  input wire [231:0] stimulus,
  output reg [554:0] observation
);
  reg [231:0] launch;
  wire [554:0] response;
  always @(posedge clk) begin
    launch <= stimulus;
    observation <= response;
  end
  wire resetn,flush,job_valid,input_valid,input_gap,input_closed,input_clipped,result_ready;
  wire [63:0] job_start,input_index,result_start;
  wire [31:0] seed,step,result_seed,result_step;
  wire signed [15:0] ii,iq;
  wire job_ready,active,result_valid;
  wire [16:0] count;
  wire [7:0] fault;
  wire signed [51:0] ri,rq,di,dq;
  wire signed [68:0] ti,tq;
  wire [52:0] energy;
  assign {resetn,flush,job_valid,job_start,seed,step,input_valid,input_gap,input_closed,
      input_clipped,input_index,ii,iq,result_ready} = launch;
  assign response = {job_ready,active,result_valid,result_start,result_seed,result_step,count,fault,ri,rq,di,dq,ti,tq,energy};
  (* keep_hierarchy="yes" *) starlink_glrt_native_engine #(.TEMPLATE_FILE(TEMPLATE_FILE)) dut (
    .clk(clk),.resetn(resetn),.flush(flush),.job_valid(job_valid),.job_ready(job_ready),
    .job_start(job_start),.job_phase_seed(seed),.job_phase_step(step),.input_valid(input_valid),
    .input_gap(input_gap),.input_closed(input_closed),.input_clipped(input_clipped),
    .input_index(input_index),.input_i(ii),.input_q(iq),.active(active),
    .result_valid(result_valid),.result_ready(result_ready),.result_start(result_start),
    .result_phase_seed(result_seed),.result_phase_step(result_step),.result_count(count),.result_fault(fault),
    .reference_sum_i(ri),.reference_sum_q(rq),.delay_sum_i(di),.delay_sum_q(dq),
    .reference_prefix_integral_i(ti),.reference_prefix_integral_q(tq),.observed_energy(energy)
  );
endmodule
