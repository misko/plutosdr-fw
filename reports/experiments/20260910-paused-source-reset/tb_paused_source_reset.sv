`timescale 1ns/1ps
// Diagnostic of the unchanged L1 source-mailbox reset boundary, not a fix.
module tb_paused_source_reset;
  reg clk=0, fft_clk=0, slow_enable=1;
  always #5 if (slow_enable) clk=~clk; else clk=0;
  always #2.857 fft_clk=~fft_clk;
  reg resetn=0, fft_resetn=0;
  reg [1:0] slow_reset_fast=0, fast_reset_fast=0;
  reg [1:0] slow_reset_slow=0, fast_reset_slow=0;
  // Literal outer L1 qualification equations and clock/reset sensitivities.
  always @(posedge fft_clk or negedge resetn)
    if(!resetn) slow_reset_fast<=0; else slow_reset_fast<={slow_reset_fast[0],1'b1};
  always @(posedge fft_clk or negedge fft_resetn)
    if(!fft_resetn) fast_reset_fast<=0; else fast_reset_fast<={fast_reset_fast[0],1'b1};
  always @(posedge clk or negedge resetn)
    if(!resetn) slow_reset_slow<=0; else slow_reset_slow<={slow_reset_slow[0],1'b1};
  always @(posedge clk or negedge fft_resetn)
    if(!fft_resetn) fast_reset_slow<=0; else fast_reset_slow<={fast_reset_slow[0],1'b1};
  wire fast_running=slow_reset_fast[1] && fast_reset_fast[1];
  wire slow_running=slow_reset_slow[1] && fast_reset_slow[1];
  reg valid=0;
  reg [35:0] data=0;
  reg [8:0] position=0;
  reg last=0;
  wire ready, fault, out_valid, out_last;
  wire [35:0] out_data;
  wire [8:0] out_position;
  wire [69:0] out_metadata;
  integer i, side=0;
  starlink_pss_block_mailbox #(.RESET_RELEASE_EXTERNAL(1)) bank (
    .input_clk(clk), .input_resetn(slow_running), .input_valid(valid),
    .input_ready(ready), .input_data(data), .input_position(position),
    .input_last(last), .input_metadata({1'b0,64'h23456789,5'b0}),
    .input_commit_authorized(1'b0), .input_fault(fault), .input_framing_fault_now(),
    .output_clk(fft_clk), .output_resetn(fast_running), .output_valid(out_valid),
    .output_ready(1'b0), .output_data(out_data), .output_position(out_position),
    .output_last(out_last), .output_metadata(out_metadata)
  );
  initial begin
    if(!$value$plusargs("SIDE=%d",side)) side=0;
    #1; resetn=1; fft_resetn=1;
    repeat(6) @(negedge clk);
    for(i=0;i<512;i=i+1) begin
      @(negedge clk); valid=1; data=36'h123450000+i; position=i; last=(i==511);
      @(posedge clk); if(!ready) $fatal(1,"initial owned bank not ready");
    end
    @(negedge clk); valid=0;
    wait(out_valid);
    @(negedge clk); slow_enable=0;
    #1; if(side==0) resetn=0; else fft_resetn=0;
    repeat(5) @(negedge fft_clk);
    if(fast_running || slow_running || out_valid) $fatal(1,"reset did not purge fast view");
    if(bank.request_toggle!==1'b1) $fatal(1,"paused producer unexpectedly reset");
    if(side==0) resetn=1; else fft_resetn=1;
    repeat(12) @(negedge fft_clk);
    if(!fast_running || slow_running) $fatal(1,"did not exercise skewed release");
    if(!out_valid || out_position!==0 || out_data!==36'h123450000)
      $fatal(1,"predicted stale prefetch absent");
    $display("STALE_PREFETCH_WHILE_SLOW_PAUSED side=%0d data=%h position=%0d",side,out_data,out_position);
    slow_enable=1;
    repeat(8) @(negedge clk);
    repeat(8) @(negedge fft_clk);
    if(!slow_running || bank.request_toggle!==0 || !out_valid ||
       out_position!==0 || out_data!==36'h123450000)
      $fatal(1,"predicted stale retained head absent after producer purge");
    $display("BASELINE_STALE_HEAD_REPRODUCED_NOT_A_SAFETY_PASS side=%0d request=%b output_valid=%b data=%h",side,bank.request_toggle,out_valid,out_data);
    $finish(0);
  end
  initial begin #20000; $fatal(1,"diagnostic watchdog"); end
endmodule
