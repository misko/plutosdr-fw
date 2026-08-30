// -----------------------------------------------------------------------------
// tb_tandem_cdc.v -- tests for the CDC primitives.
//
// RC3 and RC4 failed Vivado CDC-10; RC5 and RC6 failed on boot-dependent clock
// and reset ordering. These tests target exactly those failure modes:
// a stopped destination clock, a late-starting destination clock, every reset
// ordering, and data integrity across incommensurate clock ratios.
// -----------------------------------------------------------------------------

`timescale 1ns/1ps

module tb_tandem_cdc;

  integer errors = 0;

  task check(input cond, input [511:0] name);
    begin if (!cond) begin $display("FAIL: %0s", name); errors=errors+1; end
          else $display("  ok  %0s", name); end endtask

  // ===========================================================================
  // 1. reset bridge: async assert, sync deassert, stopped and late clocks
  // ===========================================================================
  reg  rb_clk = 1'b0;
  reg  rb_run = 1'b0;          // gates the clock so it can be stopped entirely
  reg  rb_aresetn = 1'b1;
  wire rb_resetn;

  always #5 if (rb_run) rb_clk = ~rb_clk;

  tandem_reset_bridge u_rb (.clk(rb_clk), .aresetn(rb_aresetn), .resetn(rb_resetn));

  // ===========================================================================
  // 2. multi-bit bus crossing, incommensurate clocks
  // ===========================================================================
  reg src_clk = 1'b0, dst_clk = 1'b0;
  always #5    src_clk = ~src_clk;      // 100 MHz
  always #16.3 dst_clk = ~dst_clk;      // ~30.7 MHz, deliberately not a ratio

  reg         src_resetn = 1'b0, dst_resetn = 1'b0;
  reg  [31:0] bus_din = 32'd0;
  reg         bus_load = 1'b0;
  wire        bus_busy;
  wire [31:0] bus_dout;
  wire        bus_dout_valid;

  tandem_cdc_bus #(.W(32)) u_bus (
    .src_clk(src_clk), .src_resetn(src_resetn), .din(bus_din),
    .load(bus_load), .busy(bus_busy),
    .dst_clk(dst_clk), .dst_resetn(dst_resetn),
    .dout(bus_dout), .dout_valid(bus_dout_valid));

  // capture everything the destination sees
  integer n_seen = 0;
  reg [31:0] seen [0:255];
  always @(posedge dst_clk) begin
    if (dst_resetn && bus_dout_valid && n_seen < 256) begin
      seen[n_seen] = bus_dout;
      n_seen = n_seen + 1;
    end
  end

  // ===========================================================================
  // 3. asynchronous event FIFO
  // ===========================================================================
  reg  fw_clk = 1'b0, fr_clk = 1'b0;
  always #5   fw_clk = ~fw_clk;         // write side 100 MHz
  always #13  fr_clk = ~fr_clk;         // read side ~38 MHz, incommensurate

  reg  fw_resetn = 1'b0, fr_resetn = 1'b0;
  reg  fw_en = 1'b0;
  reg  [127:0] fw_data = 128'd0;
  wire fw_full;
  wire [7:0] fw_ovf;
  reg  fr_en = 1'b0;
  wire [127:0] fr_data;
  wire fr_valid;
  wire [8:0] fr_level;

  tandem_async_fifo #(.W(128), .AW(8)) u_fifo (
    .wr_clk(fw_clk), .wr_resetn(fw_resetn), .wr_en(fw_en), .wr_data(fw_data),
    .wr_full(fw_full), .wr_ovf(fw_ovf),
    .rd_clk(fr_clk), .rd_resetn(fr_resetn), .rd_en(fr_en),
    .rd_data(fr_data), .rd_valid(fr_valid), .rd_level(fr_level));

  integer n_read = 0;
  integer read_ok = 1;
  always @(posedge fr_clk) begin
    if (fr_resetn && fr_en && fr_valid) begin
      if (fr_data !== {96'd0, n_read[31:0]}) read_ok = 0;   // exact order
      n_read = n_read + 1;
    end
  end

  // ===========================================================================
  // 4. BRAM-backed coherent latest-snapshot mailbox
  // ===========================================================================
  reg mb_src_clk = 1'b0, mb_dst_clk = 1'b0;
  reg mb_src_run = 1'b1, mb_dst_run = 1'b1;
  always #8.138 if (mb_src_run) mb_src_clk = ~mb_src_clk;  // 61.44 MHz
  always #5     if (mb_dst_run) mb_dst_clk = ~mb_dst_clk;  // 100 MHz

  reg mb_src_resetn = 1'b0, mb_dst_resetn = 1'b0;
  reg [31:0] mb_counter = 32'd0;
  wire [63:0] mb_din = {~mb_counter, mb_counter};
  wire [63:0] mb_dout;
  wire mb_valid;

  tandem_cdc_mailbox #(.W(64), .AW(2)) u_mailbox (
    .src_clk(mb_src_clk), .src_resetn(mb_src_resetn), .din(mb_din),
    .dst_clk(mb_dst_clk), .dst_resetn(mb_dst_resetn),
    .dout(mb_dout), .dout_valid(mb_valid));

  always @(posedge mb_src_clk) begin
    if (!mb_src_resetn) mb_counter <= 32'd0;
    else                mb_counter <= mb_counter + 32'd1;
  end

  integer mb_seen = 0;
  integer mb_bad = 0;
  reg [31:0] mb_last = 32'd0;
  always @(posedge mb_dst_clk) begin
    if (mb_dst_resetn && mb_valid) begin
      if (mb_dout[63:32] !== ~mb_dout[31:0]) mb_bad = mb_bad + 1;
      if (mb_seen != 0 && mb_dout[31:0] < mb_last) mb_bad = mb_bad + 1;
      mb_last = mb_dout[31:0];
      mb_seen = mb_seen + 1;
    end
  end

  integer i;

  initial begin
    $display("== tb_tandem_cdc ==");

    // ---- reset bridge -----------------------------------------------------
    rb_run = 1'b0;
    #10 rb_aresetn = 1'b0;      // the asynchronous assertion edge
    #100;
    check(rb_resetn === 1'b0, "reset asserts with the destination clock STOPPED");

    // release reset while the clock is still stopped: must stay asserted
    rb_aresetn = 1'b1;
    #100;
    check(rb_resetn === 1'b0,
          "reset stays asserted until the destination clock actually runs");

    // now start the clock late: deassertion must be synchronous
    rb_run = 1'b1;
    @(posedge rb_clk);
    check(rb_resetn === 1'b0, "still asserted one edge after a late clock start");
    @(posedge rb_clk); @(posedge rb_clk); #1;
    check(rb_resetn === 1'b1, "deasserts synchronously after two edges");

    // asynchronous re-assert must take effect without a clock edge
    rb_run = 1'b0; #20;
    rb_aresetn = 1'b0; #1;
    check(rb_resetn === 1'b0, "re-asserts asynchronously with the clock stopped");
    rb_aresetn = 1'b1; rb_run = 1'b1;

    $display("MARK reset-bridge done @%0t", $time);
    // ---- multi-bit bus ----------------------------------------------------
    src_resetn = 1'b1; dst_resetn = 1'b1;
    repeat (4) @(posedge src_clk);

    for (i = 0; i < 64; i = i + 1) begin
      @(posedge src_clk);
      while (bus_busy) @(posedge src_clk);
      bus_din  <= 32'hA5A5_0000 + i;
      bus_load <= 1'b1;
      @(posedge src_clk);
      bus_load <= 1'b0;
      repeat (3 + (i % 7)) @(posedge src_clk);
    end
    repeat (40) @(posedge dst_clk);

    check(n_seen == 64, "every multi-bit payload crossed exactly once");
    begin : bus_integrity
      integer bad; bad = 0;
      for (i = 0; i < n_seen; i = i + 1)
        if (seen[i] !== 32'hA5A5_0000 + i) bad = bad + 1;
      check(bad == 0, "no payload was torn or reordered crossing domains");
    end

    $display("MARK bus done @%0t", $time);
    // ---- asynchronous FIFO ------------------------------------------------
    fw_resetn = 1'b1; fr_resetn = 1'b1;
    repeat (4) @(posedge fw_clk);

    // write 200 entries while reading concurrently from the slower domain
    fork
      begin : writer
        for (i = 0; i < 200; i = i + 1) begin
          @(posedge fw_clk);
          while (fw_full) @(posedge fw_clk);
          fw_data <= {96'd0, i[31:0]};
          fw_en   <= 1'b1;
          @(posedge fw_clk);
          fw_en   <= 1'b0;
        end
      end
      begin : reader
        repeat (30) @(posedge fr_clk);      // start late, so the FIFO fills first
        fr_en = 1'b1;
        repeat (900) @(posedge fr_clk);
        fr_en = 1'b0;
      end
    join

    repeat (50) @(posedge fr_clk);
    check(n_read == 200,  "every FIFO entry crossed exactly once, none lost");
    check(read_ok == 1,   "FIFO preserved exact order across the domains");
    check(fw_ovf == 8'd0,"no spurious overflow while the reader kept up");

    $display("MARK fifo-rw done @%0t", $time);
    // ---- deliberate overflow ---------------------------------------------
    fr_en = 1'b0;
    for (i = 0; i < 400; i = i + 1) begin
      @(posedge fw_clk);
      fw_data <= {96'd0, 32'hDEAD_0000 + i};
      fw_en   <= 1'b1;
      @(posedge fw_clk);
      fw_en   <= 1'b0;
    end
    repeat (20) @(posedge fw_clk);
    check(fw_full == 1'b1,  "the FIFO reports full when the reader stops");
    check(fw_ovf > 8'd0,    "overflow is counted, never silent");

    // ---- coherent status mailbox ----------------------------------------
    // Both domains first receive their configuration/GSR reset state. Stop the
    // destination after that initialization, fill from the source, and restart
    // it late. The source must not overwrite in-flight slots, and every
    // delivered 64-bit relation must remain atomic across asynchronous clocks.
    mb_dst_run = 1'b0;
    repeat (4) @(posedge mb_src_clk);
    mb_src_resetn = 1'b1;
    repeat (20) @(posedge mb_src_clk);
    check(mb_valid === 1'b0,
          "mailbox remains empty while the destination clock is stopped");
    mb_dst_run = 1'b1;
    repeat (3) @(posedge mb_dst_clk);
    mb_dst_resetn = 1'b1;
    repeat (160) @(posedge mb_dst_clk);
    check(mb_seen > 20, "mailbox resumes and publishes after a late clock start");
    check(mb_bad == 0, "mailbox snapshots are coherent and never regress");
    check(mb_valid, "mailbox retains one last committed snapshot");

    mb_src_run = 1'b0;
    repeat (50) @(posedge mb_dst_clk);
    begin : mailbox_hold
      reg [63:0] held;
      held = mb_dout;
      repeat (20) @(posedge mb_dst_clk);
      check(mb_valid && mb_dout === held,
            "mailbox holds its last snapshot when the producer stops");
    end

    $display("---- scenario failures : %0d ----", errors);
    if (errors != 0) $fatal(1, "CDC TESTS FAILED");
    $display("PASS: tb_tandem_cdc");
    $finish;
  end

  initial begin #20000000; $fatal(1, "tb_tandem_cdc timeout"); end

endmodule
