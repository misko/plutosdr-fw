// Registered boundaries for all result-queue signals at the 100 MHz AXI clock.
module starlink_glrt_native_queue_ooc_wrapper (
  input wire clk,
  input wire [42:0] stimulus,
  output reg [115:0] observation
);
  reg [42:0] launch;
  wire [115:0] response;
  always @(posedge clk) begin launch<=stimulus; observation<=response; end
  wire resetn,reserve,write_valid,write_last,read_request,pop;
  wire [31:0] write_data,read_data,committed,popped;
  wire [4:0] read_word;
  wire space,reserved,write_ready,read_valid,head_valid,fault;
  wire [6:0] count,high_water;
  assign {resetn,reserve,write_valid,write_data,write_last,read_request,read_word,pop}=launch;
  assign response={space,reserved,write_ready,read_valid,read_data,head_valid,count,
                   high_water,committed,popped,fault};
  (* keep_hierarchy="yes" *) starlink_glrt_native_result_queue dut (
    .clk(clk),.resetn(resetn),.reserve(reserve),.space(space),.reserved(reserved),
    .write_valid(write_valid),.write_data(write_data),.write_last(write_last),
    .write_ready(write_ready),.read_request(read_request),.read_word(read_word),
    .read_valid(read_valid),.read_data(read_data),.pop(pop),.head_valid(head_valid),
    .count(count),.high_water(high_water),.committed(committed),.popped(popped),.fault(fault)
  );
endmodule
