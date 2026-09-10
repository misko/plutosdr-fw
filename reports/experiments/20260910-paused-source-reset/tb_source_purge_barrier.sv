`timescale 1ns/1ps
// Independent reset-barrier prototype, NOT the new integrated inverse bank.
module tb_source_purge_barrier;
  parameter integer BARRIER=1;
  reg clk=0, fft_clk=0, slow_enable=1, fast_enable=1;
  always #5 if(slow_enable) clk=~clk; else clk=0;
  always #2.857 if(fast_enable) fft_clk=~fft_clk; else fft_clk=0;
  reg resetn=0, fft_resetn=0;
  reg [1:0] slow_reset_fast=0, fast_reset_fast=0;
  reg [1:0] slow_reset_slow=0, fast_reset_slow=0;
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
  // Acknowledgement goes high only on a slow edge after local reset release;
  // the preceding slow edge has actually executed the source producer purge.
  reg slow_purged=0;
  always @(posedge clk or negedge resetn or negedge fft_resetn)
    if(!resetn || !fft_resetn) slow_purged<=0; else slow_purged<=slow_running;
  (* ASYNC_REG="TRUE" *) reg [1:0] purge_sync=0;
  always @(posedge fft_clk or negedge fast_running)
    if(!fast_running) purge_sync<=0; else purge_sync<={purge_sync[0],slow_purged};
  wire reader_running=fast_running && (BARRIER ? purge_sync[1] : 1'b1);
  reg valid=0, take_output=0;
  reg [35:0] data=0;
  reg [8:0] position=0;
  reg last=0;
  wire ready, fault, out_valid, out_last;
  wire [35:0] out_data;
  wire [8:0] out_position;
  wire [69:0] out_metadata;
  integer i, side=0, fill_before_fast=0, reads=0;
  starlink_pss_block_mailbox #(.RESET_RELEASE_EXTERNAL(1)) bank (
    .input_clk(clk), .input_resetn(slow_running), .input_valid(valid),
    .input_ready(ready), .input_data(data), .input_position(position),
    .input_last(last), .input_metadata({1'b0,64'h23456789,5'b0}),
    .input_commit_authorized(1'b0), .input_fault(fault), .input_framing_fault_now(),
    .output_clk(fft_clk), .output_resetn(reader_running), .output_valid(out_valid),
    .output_ready(take_output), .output_data(out_data), .output_position(out_position),
    .output_last(out_last), .output_metadata(out_metadata)
  );
  task fill(input [35:0] base);
    for(i=0;i<512;i=i+1) begin
      @(negedge clk); valid=1; data=base+i; position=i; last=(i==511);
      @(posedge clk); if(!ready) $fatal(1,"owned source capacity absent");
    end
    @(negedge clk); valid=0;
  endtask
  always @(posedge fft_clk) if(out_valid && take_output) begin
    if(out_position!==reads || out_data!==(36'h234560000+reads) ||
       out_last!==(reads==511) || out_metadata!=={1'b0,64'h23456789,5'b0})
      $fatal(1,"fresh epoch source data/order/metadata mismatch");
    reads=reads+1;
  end
  initial begin
    if(!$value$plusargs("SIDE=%d",side)) side=0;
    if(!$value$plusargs("FILL_BEFORE_FAST=%d",fill_before_fast)) fill_before_fast=0;
    #1; resetn=1; fft_resetn=1;
    repeat(6) @(negedge clk);
    fill(36'h123450000);
    wait(out_valid);
    @(negedge clk); slow_enable=0;
    #1; if(side==0) resetn=0; else fft_resetn=0;
    repeat(5) @(negedge fft_clk);
    if(fast_running || slow_running || out_valid) $fatal(1,"reset failed fast purge");
    if(bank.request_toggle!==1) $fatal(1,"producer not actually paused full");
    if(side==0) resetn=1; else fft_resetn=1;
    repeat(12) @(negedge fft_clk);
    if(!fast_running || slow_running) $fatal(1,"missing skewed-release stimulus");
    if(reader_running || out_valid) $fatal(1,"stale source reader reopened before remote purge");
    if(fill_before_fast) fast_enable=0;
    slow_enable=1;
    repeat(8) @(negedge clk);
    if(!slow_running || bank.request_toggle!==0 || out_valid)
      $fatal(1,"old request/prefetch survived slow purge");
    fill(36'h234560000);
    if(fill_before_fast) begin
      if(bank.request_toggle!==1 || reader_running)
        $fatal(1,"new-epoch full source before fast rejoin not exercised");
      fast_enable=1;
    end
    wait(out_valid);
    @(negedge fft_clk); take_output=1;
    wait(reads==512);
    @(negedge fft_clk); take_output=0;
    repeat(6) @(negedge clk);
    if(fault || out_valid || !ready) $fatal(1,"fresh epoch failed complete release");
    $display("SOURCE_PURGE_BARRIER_PROTOTYPE_PASS side=%0d fill_before_fast=%0d words=%0d",side,fill_before_fast,reads);
    $finish(0);
  end
  initial begin #40000; $fatal(1,"barrier diagnostic watchdog"); end
endmodule
