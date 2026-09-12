`timescale 1ns/1ps
module cpack_counter_tb;
 reg clk=0, reset=1, valid=0;
 reg [63:0] counter=64'h1ffffff00;
 wire wr, sync, overflow;
 wire [63:0] packed_data;
 integer outputs=0, tick=0, period=1;
 reg [63:0] expected=64'h1ffffff00;
 always #5 clk=~clk;
 always @(posedge clk) if(valid) counter<=counter+1;
 util_cpack2 #(.NUM_OF_CHANNELS(4),.SAMPLE_DATA_WIDTH(16),.SAMPLES_PER_CHANNEL(1)) dut(
 .clk(clk),.reset(reset),.enable_0(1'b1),.enable_1(1'b1),.enable_2(1'b0),.enable_3(1'b0),
 .fifo_wr_en(valid),.fifo_wr_overflow(overflow),
 .fifo_wr_data_0(counter[15:0]),.fifo_wr_data_1(~counter[15:0]),
 .fifo_wr_data_2(16'hdead),.fifo_wr_data_3(16'hbeef),
 .packed_fifo_wr_en(wr),.packed_fifo_wr_sync(sync),.packed_fifo_wr_data(packed_data),
 .packed_fifo_wr_overflow(1'b0));
 always @(posedge clk) if(wr) begin
  if(counter !== expected+2) $fatal(1,"prefix counter is not first sample plus two");
  expected=expected+2;
  if (outputs<10) $display("pack: counter=%h iq=%h delta=%0d",counter,packed_data,counter[15:0]-packed_data[15:0]);
  if(packed_data[31:16] !== ~packed_data[15:0] ||
     packed_data[47:32] !== (packed_data[15:0]+16'd1) ||
     packed_data[63:48] !== ~packed_data[47:32]) $fatal(1,"CI16 packing corrupt");
  outputs=outputs+1;
 end
 initial begin
  repeat(6) @(negedge clk); reset=0;
  repeat(6) @(negedge clk); valid=1;
  for(tick=0;tick<5000;tick=tick+1) begin
   @(negedge clk);
   // Exercise every-cycle, intermittent, and CMOS-like valid cadence.
   if(tick<1000) valid=1;
   else if(tick<2000) valid=(tick%2)==0;
   else if(tick<3000) valid=(tick%4)==0;
   else valid=($random & 7)<5;
  end
  if(outputs<100) $fatal(1,"too few outputs");
  $display("PASS: %0d RX0 CI16 packed words", outputs);$finish;
 end
endmodule
