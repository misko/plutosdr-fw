`timescale 1ps/1ps
module tb #(
  parameter integer WRITER_HALF=2857, READER_HALF=5000, READER_PHASE=0
);
reg fast_clk=0,slow_clk=0,fast_enable=1,slow_enable=1;
initial forever begin #(WRITER_HALF);if(fast_enable)fast_clk=~fast_clk;else fast_clk=0;end
initial begin #(READER_PHASE);forever begin #(READER_HALF);if(slow_enable)slow_clk=~slow_clk;else slow_clk=0;end end
reg resetn=0,fft_resetn=0;
reg [1:0] slow_reset_fast=0,fast_reset_fast=0,slow_reset_slow=0,fast_reset_slow=0;
always @(posedge fast_clk or negedge resetn)
  if(!resetn)slow_reset_fast<=0;else slow_reset_fast<={slow_reset_fast[0],1'b1};
always @(posedge fast_clk or negedge fft_resetn)
  if(!fft_resetn)fast_reset_fast<=0;else fast_reset_fast<={fast_reset_fast[0],1'b1};
always @(posedge slow_clk or negedge resetn)
  if(!resetn)slow_reset_slow<=0;else slow_reset_slow<={slow_reset_slow[0],1'b1};
always @(posedge slow_clk or negedge fft_resetn)
  if(!fft_resetn)fast_reset_slow<=0;else fast_reset_slow<={fast_reset_slow[0],1'b1};
wire fast_running,slow_running,writer_idle,reader_idle;
starlink_pss_retained_epoch_barrier barrier(
 .slow_clk(slow_clk),.fast_clk(fast_clk),.resetn(resetn),.fft_resetn(fft_resetn),
 .outer_slow_running(slow_reset_slow[1]&&fast_reset_slow[1]),
 .outer_fast_running(slow_reset_fast[1]&&fast_reset_fast[1]),
 .slow_mailboxes_reset_idle(reader_idle),.fast_mailboxes_reset_idle(writer_idle),
 .slow_running(slow_running),.fast_running(fast_running));
reg input_valid=0,input_last=0,authorize=0,select_replay=0,drain=0;
reg [35:0] input_data=0;
reg [8:0] input_position=0;
reg [36:0] live_metadata=0,replay_metadata=0;
wire ready,framing,bank_fault,valid,last,request,ack;
wire [35:0] data;wire [8:0] position;wire [36:0] metadata;
integer reader_ticks=0;
always @(posedge slow_clk)reader_ticks<=reader_ticks+1;
wire consume=drain && (reader_ticks%7!=0);
starlink_pss_mailbox_split_metadata_view #(.METADATA_WIDTH(37),.EXPLICIT_COMMIT(1),.RESET_RELEASE_EXTERNAL(1)) dut(
 .input_clk(fast_clk),.input_resetn(fast_running),.input_valid(input_valid),
 .input_commit_authorized(authorize&&!framing),.input_ready(ready),.input_data(input_data),
 .input_position(input_position),.input_last(input_last),
 .input_metadata_live(live_metadata),.input_metadata_replay(replay_metadata),.input_metadata_select(select_replay),
 .input_fault(bank_fault),.input_framing_fault_now(framing),
 .output_clk(slow_clk),.output_resetn(slow_running),.output_valid(valid),.output_ready(consume),
 .output_data(data),.output_position(position),.output_last(last),.output_metadata(metadata),
 .owner_request(request),.owner_ack_sync(ack),.writer_reset_idle(writer_idle),.reader_reset_idle(reader_idle));

integer frame=0,reads=0,completed=0,captures=0,publications=0,first_writes=0,resets=0;
integer expected_position=0,hold_checks=0,reset_checks=0;
reg bundle_exists=0,published=0,old_request=0,old_ack=0,reader_bundle=0;
reg [36:0] bundle_reference=0,reader_reference=0;
reg [35:0] reader_data_base=0,bundle_data_base=0;
time first_time=0,publish_time=0,last_ack_time=0;
time minimum_publish_capture=64'h7fffffffffffffff,minimum_first_capture=64'h7fffffffffffffff;
time minimum_ack_rewrite=64'h7fffffffffffffff;
reg had_ack=0;

// Score the actual source register and ownership transition, not the offered
// input bus. The writer cannot change a live bundle before real reader ACK.
always @(posedge fast_clk)begin : writer_monitor
 reg loading;
 loading=dut.metadata_load;
 if(!fast_running)begin bundle_exists=0;published=0;old_request=0;had_ack=0;end
 else begin
  if(bundle_exists && dut.metadata_in_hold!==bundle_reference)$fatal(1,"bundle changed before permitted rewrite");
  if(loading)begin
   if(bundle_exists && (!published || request!==ack))$fatal(1,"metadata rewrite before ownership return");
   if(had_ack)begin
    if($time-last_ack_time<4*WRITER_HALF-2)$fatal(1,"ACK-to-rewrite synchronizer budget violated");
    if($time-last_ack_time<minimum_ack_rewrite)minimum_ack_rewrite=$time-last_ack_time;
   end
   bundle_reference=dut.input_metadata;bundle_data_base=input_data;
   bundle_exists=1;published=0;first_time=$time;first_writes=first_writes+1;
  end
  #1;
  if(request!==old_request)begin
   if(!bundle_exists || $time-first_time<1022*WRITER_HALF)$fatal(1,"publication before complete stable bundle");
   published=1;publish_time=$time-1;publications=publications+1;
  end
  old_request=request;
  if(bundle_exists && dut.metadata_in_hold!==bundle_reference)$fatal(1,"source metadata changed outside first capture");
  if(bundle_exists)hold_checks=hold_checks+1;
 end
end

always @(posedge slow_clk)begin : reader_monitor
 reg capturing,taking_last;
 capturing=slow_running && !dut.reading && dut.request_sync[1]!=dut.acknowledge_toggle;
 taking_last=valid&&consume&&last;
 if(!slow_running)begin reader_bundle=0;old_ack=0;expected_position=0;end
 else begin
  if(capturing)begin
   if(!bundle_exists || !published)$fatal(1,"reader captured unpublished metadata");
   if($time-publish_time<4*READER_HALF-2)$fatal(1,"request-to-capture synchronizer budget violated");
   if($time-first_time<1022*WRITER_HALF+4*READER_HALF-2)$fatal(1,"first-write-to-capture budget violated");
   if($time-publish_time<minimum_publish_capture)minimum_publish_capture=$time-publish_time;
   if($time-first_time<minimum_first_capture)minimum_first_capture=$time-first_time;
   reader_reference=bundle_reference;reader_data_base=bundle_data_base;reader_bundle=1;captures=captures+1;
  end
  if(valid)begin
   if(!reader_bundle || metadata!==reader_reference)$fatal(1,"reader observed torn or stale descriptor");
   if(data!==reader_data_base+position)$fatal(1,"reader observed wrong payload generation");
  end
  if(valid&&consume)begin
   if(position!==expected_position[8:0])$fatal(1,"reader ordinal mismatch");
   reads=reads+1;
   if(last)begin expected_position=0;completed=completed+1;last_ack_time=$time;had_ack=1;end
   else expected_position=expected_position+1;
  end
  #1;
  if(capturing && metadata!==reader_reference)$fatal(1,"capture did not retain stable bundle");
  if(dut.acknowledge_toggle!==old_ack && !taking_last)$fatal(1,"ACK without real final read");
  old_ack=dut.acknowledge_toggle;
 end
end

task start_epoch;
 begin
  resetn=0;fft_resetn=0;input_valid=0;drain=0;authorize=0;fast_enable=1;slow_enable=1;
  repeat(8)@(negedge fast_clk);repeat(8)@(negedge slow_clk);
  resetn=1;fft_resetn=1;
  while(!fast_running || !slow_running || !ready)@(negedge fast_clk);
 end
endtask
task begin_frame;
 begin
  frame=frame+1;select_replay=0;authorize=0;drain=0;
  live_metadata=37'h123400000+frame;replay_metadata=live_metadata;
 end
endtask
task send_word(input integer n);
 begin
  @(negedge fast_clk);input_valid=1;input_position=n;input_last=(n==511);input_data=frame*4096+n;
  if(!ready)$fatal(1,"driver unexpectedly lacks writer ownership");
  @(posedge fast_clk);#2;
 end
endtask
task write_block;
 integer n;
 begin begin_frame;for(n=0;n<512;n=n+1)send_word(n);end
endtask
task publish_block;
 reg before_request;
 begin
  @(negedge fast_clk);select_replay=1;before_request=request;
  repeat(13)@(negedge fast_clk);authorize=1;
  @(posedge fast_clk);#2;if(request===before_request)$fatal(1,"missing actual publication");
  @(negedge fast_clk);authorize=0;input_valid=0;
 end
endtask
task finish_frame;
 integer before_reads,before_complete;
 begin
  before_reads=reads;before_complete=completed;
  // Churn queued next input while the reader is stalled. It must not change
  // the held bundle; stop offering before the reader can return ownership.
  @(negedge fast_clk);input_valid=1;input_position=0;input_last=0;select_replay=0;
  live_metadata=37'h1fffffffff;input_data=36'habcdef;
  repeat(17)begin @(negedge slow_clk);if(ready)$fatal(1,"unread bundle returned writer ownership");end
  @(negedge fast_clk);input_valid=0;drain=1;
  while(completed==before_complete || !ready)@(negedge fast_clk);
  if(reads-before_reads!=512)$fatal(1,"incomplete reader block");drain=0;
 end
endtask
task cancel_epoch(input integer side,input integer pause_writer);
 begin
  input_valid=0;drain=0;
  if(pause_writer)begin @(negedge fast_clk);fast_enable=0;end
  #3;if(side==0)resetn=0;else fft_resetn=0;
  #2;if(valid || ready || fast_running || slow_running)$fatal(1,"raw reset did not fence both domains");
  repeat(8)begin #10001;if(valid || ready)$fatal(1,"reset/stopped-clock epoch escaped");reset_checks=reset_checks+1;end
  fast_enable=1;slow_enable=1;
  repeat(8)@(negedge fast_clk);repeat(8)@(negedge slow_clk);
  resetn=1;fft_resetn=1;
  while(!fast_running || !slow_running || !ready)@(negedge fast_clk);
  repeat(8)begin @(negedge slow_clk);if(valid)$fatal(1,"stale request survived coordinated purge");end
  resets=resets+1;
 end
endtask
integer side,boundary,n;
initial begin
 start_epoch;
 // Back-to-back generations exercise the full synchronized ACK-to-rewrite path.
 repeat(3)begin write_block;publish_block;finish_frame;end
 for(side=0;side<2;side=side+1)for(boundary=0;boundary<5;boundary=boundary+1)begin
  begin_frame;
  if(boundary==2)begin @(negedge slow_clk);slow_enable=0;end
  for(n=0;n<(boundary==0 ? 17 : 512);n=n+1)send_word(n);
  if(boundary>=2)publish_block;
  if(boundary==3)while(!dut.reading)@(negedge slow_clk);
  if(boundary==4)begin drain=1;n=reads;while(reads<n+17)@(negedge slow_clk);drain=0;end
  cancel_epoch(side,boundary==3);
  write_block;publish_block;finish_frame;
 end
 if(completed!=13 || resets!=10 || captures<13 || publications<13 || hold_checks<1000 || minimum_ack_rewrite==64'h7fffffffffffffff)
  $fatal(1,"incomplete CDC coverage");
 $display("OUTPUT_CDC_CONTRACT_PASS writer_period_ps=%0d reader_period_ps=%0d phase_ps=%0d completed=%0d resets=%0d captures=%0d publications=%0d first_writes=%0d hold_checks=%0d reset_checks=%0d min_publish_capture_ps=%0d min_first_capture_ps=%0d min_ack_rewrite_ps=%0d",
  2*WRITER_HALF,2*READER_HALF,READER_PHASE,completed,resets,captures,publications,first_writes,hold_checks,reset_checks,minimum_publish_capture,minimum_first_capture,minimum_ack_rewrite);
 $finish;
end
initial begin #2000000000;$fatal(1,"CDC contract absolute deadline");end
endmodule
