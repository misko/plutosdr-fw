// -----------------------------------------------------------------------------
// tb_tandem_agc_axi.v -- dual-clock test of the AXI4-Lite slave.
//
// This is the first test where the processor domain and the receive domain are
// genuinely different clocks, at a deliberately incommensurate ratio. It drives
// the whole §11 enable and disable sequence over AXI, exactly as software will.
// -----------------------------------------------------------------------------

`timescale 1ns/1ps

module tb_tandem_agc_axi;

  // 100 MHz processor domain, ~61.44 MHz receive domain: not an integer ratio
  reg s_axi_aclk = 1'b0;  always #5     s_axi_aclk = ~s_axi_aclk;
  reg l_clk      = 1'b0;  always #8.138 l_clk      = ~l_clk;

  reg s_axi_aresetn = 1'b1;
  reg l_aresetn     = 1'b1;

  reg  [7:0]  awaddr = 8'd0;  reg awvalid = 1'b0;  wire awready;
  reg  [31:0] wdata  = 32'd0; reg wvalid  = 1'b0;  wire wready;
  wire [1:0]  bresp;          wire bvalid;         reg  bready = 1'b0;
  reg  [7:0]  araddr = 8'd0;  reg arvalid = 1'b0;  wire arready;
  wire [31:0] rdata;          wire [1:0] rresp;    wire rvalid;  reg rready = 1'b0;

  reg  [63:0] sample_counter = 64'd0;
  reg         sample_valid = 1'b1;
  always @(posedge l_clk)
    if (sample_valid) sample_counter <= sample_counter + 64'd1;

  wire [3:0] ctl_o, ctl_t;
  wire [7:0] detect_pins;
  reg        use_forced_detect = 1'b0;
  reg  [7:0] forced_detect = 8'd0;
  wire [7:0] tandem_detect = use_forced_detect ? forced_detect : detect_pins;
  wire [7:0] m_rx1, m_rx2;
  wire [31:0] m_acc, m_rej, m_ign;

  reg signed [15:0] rx1_level = -16'sd60, rx2_level = -16'sd60;
  reg armed = 1'b0;
  integer errors = 0;

  tandem_agc_axi dut (
    .s_axi_aclk(s_axi_aclk), .s_axi_aresetn(s_axi_aresetn),
    .s_axi_awaddr(awaddr), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
    .s_axi_wdata(wdata), .s_axi_wstrb(4'hF), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
    .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
    .s_axi_araddr(araddr), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
    .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
    .l_clk(l_clk), .l_aresetn(l_aresetn),
    .detect_async(tandem_detect), .sample_counter(sample_counter),
    .sample_valid(sample_valid),
    .consumer_ready(1'b1),
    .ps_ctl_o(4'd0), .ps_ctl_t(4'hF), .ctl_o(ctl_o), .ctl_t(ctl_t));

  ad9361_gain_model model (
    .clkrf(l_clk), .resetn(l_aresetn), .ctrl_in(ctl_o), .ctrl_out(detect_pins),
    .pin_ctrl_armed(armed), .ensm_rx_active(1'b1),
    .inc_step(4'd1), .dec_step(4'd1), .pwot(5'd3), .idx_max(8'd76),
    .rx1_level(rx1_level), .rx2_level(rx2_level),
    .th_lg_lmt(-16'sd5), .th_lg_adc(-16'sd8), .th_sm_adc(-16'sd14),
    .th_low_pwr(-16'sd30), .pwr_period(16'd20), .drop_next_pulse(1'b0),
    .rx1_index(m_rx1), .rx2_index(m_rx2),
    .n_accepted(m_acc), .n_rejected_short(m_rej), .n_ignored_ensm(m_ign));

  task tick(input integer n); integer i;
    begin for (i=0;i<n;i=i+1) @(posedge s_axi_aclk); end endtask

  task check(input cond, input [511:0] name);
    begin if (!cond) begin $display("FAIL: %0s", name); errors=errors+1; end
          else $display("  ok  %0s", name); end endtask

  task axi_write(input [7:0] a, input [31:0] d);
    begin
      @(posedge s_axi_aclk);
      awaddr <= a; awvalid <= 1'b1; wdata <= d; wvalid <= 1'b1; bready <= 1'b1;
      wait (bvalid); @(posedge s_axi_aclk);
      awvalid <= 1'b0; wvalid <= 1'b0;
      @(posedge s_axi_aclk); bready <= 1'b0;
      tick(2);
    end
  endtask

  task axi_write_fast(input [7:0] a, input [31:0] d);
    begin
      @(posedge s_axi_aclk);
      awaddr <= a; awvalid <= 1'b1; wdata <= d; wvalid <= 1'b1; bready <= 1'b1;
      wait (bvalid); @(posedge s_axi_aclk);
      awvalid <= 1'b0; wvalid <= 1'b0; bready <= 1'b0;
    end
  endtask

  // AXI4-Lite explicitly permits AW and W to arrive independently.  Exercise
  // both legal orderings because a CPU/interconnect is not required to keep
  // AWVALID asserted while it waits to present WVALID (or vice versa).
  task axi_write_aw_first(input [7:0] a, input [31:0] d);
    integer guard;
    begin
      @(posedge s_axi_aclk);
      awaddr <= a; awvalid <= 1'b1; bready <= 1'b1;
      wait (awready); @(posedge s_axi_aclk); awvalid <= 1'b0;
      tick(3);
      wdata <= d; wvalid <= 1'b1;
      guard = 0;
      while (!bvalid && guard < 32) begin tick(1); guard = guard + 1; end
      check(bvalid, "AW-before-W write completes");
      wvalid <= 1'b0;
      if (bvalid) @(posedge s_axi_aclk);
      bready <= 1'b0;
      tick(2);
    end
  endtask

  task axi_write_w_first(input [7:0] a, input [31:0] d);
    integer guard;
    begin
      @(posedge s_axi_aclk);
      wdata <= d; wvalid <= 1'b1; bready <= 1'b1;
      tick(3);
      awaddr <= a; awvalid <= 1'b1;
      guard = 0;
      while (!bvalid && guard < 32) begin tick(1); guard = guard + 1; end
      check(bvalid, "W-before-AW write completes");
      awvalid <= 1'b0; wvalid <= 1'b0;
      if (bvalid) @(posedge s_axi_aclk);
      bready <= 1'b0;
      tick(2);
    end
  endtask

  task axi_read(input [7:0] a, output [31:0] d);
    begin
      @(posedge s_axi_aclk);
      araddr <= a; arvalid <= 1'b1; rready <= 1'b1;
      wait (rvalid); d = rdata; @(posedge s_axi_aclk);
      arvalid <= 1'b0; @(posedge s_axi_aclk); rready <= 1'b0;
      tick(2);
    end
  endtask

  reg [31:0] v;

  initial begin
    $display("== tb_tandem_agc_axi (dual clock, 100 MHz / 61.44 MHz) ==");
    s_axi_aresetn = 1'b0; l_aresetn = 1'b0;
    #200;
    s_axi_aresetn = 1'b1; l_aresetn = 1'b1;
    tick(20);

    axi_read(8'h00, v); check(v == 32'h5441_4732, "TAG2 identity matches the kernel ABI");
    axi_read(8'h04, v); check(v == 32'd1, "FPGA ABI version is one");
    axi_read(8'h08, v); check(v[15:0] == 16'd64, "capabilities report FIFO depth");
    axi_read(8'h10, v); check(v[2:0] == 3'd0, "public state is IDLE after reset");
    axi_read(8'h18, v);
    check(v[7:0] == 8'd0 && v[15:8] == 8'd76,
          "index window default is the full range (D-7 optional)");

    axi_write_aw_first(8'h30, 32'ha55a_1357);
    axi_read(8'h30, v);
    check(v == 32'ha55a_1357, "AW-before-W data and address remain paired");
    axi_write_w_first(8'h30, 32'h5aa5_2468);
    axi_read(8'h30, v);
    check(v == 32'h5aa5_2468, "W-before-AW data and address remain paired");

    // A second AXI write while the first configuration CDC is busy must be
    // retained and delivered after the in-flight snapshot, never discarded.
    axi_write_fast(8'h20, 32'd111);
    wait (dut.cfg_busy);
    axi_write_fast(8'h24, {8'd7, 8'd6, 8'd5});
    tick(100);
    check(dut.c_pwr_period == 20'd111 && dut.c_debounce == 8'd7 &&
          dut.c_cooldown == 8'd6 && dut.c_dwell == 8'd5,
          "back-to-back configuration writes survive CDC busy");

    v = dut.u_core.pwr_div;
    sample_valid = 1'b0;
    tick(100);
    check(dut.u_core.pwr_div == v[19:0],
          "power-measurement time stops without a valid output sample");
    sample_valid = 1'b1;

    // configure for a fast simulation profile, entirely over AXI
    axi_write(8'h28, {16'd0, 8'd4, 8'd4});
    axi_write(8'h2C, 32'd8);
    axi_write(8'h20, 32'd20);
    axi_write(8'h24, {8'd2, 8'd2, 8'd3});
    axi_write(8'h18, {8'd40, 8'd76, 8'd0});
    axi_write(8'h14, 32'h1234_5678);
    axi_write(8'h30, 32'h313a2f30);
    axi_write(8'h0C, 32'h0000_0100); // clear FIFO, counters, and sticky faults
    tick(50);
    axi_read(8'h28, v); check(v[7:0] == 8'd4, "pulse configuration reads back");
    axi_read(8'h30, v); check(v == 32'h313a2f30, "threshold provenance reads back");

    // §11 enable, driven over the bus
    model.rx1_index = 8'd40; model.rx2_index = 8'd40;
    axi_write(8'h0C, 32'd1);
    tick(600);                                   // let the snapshot cross
    axi_read(8'h10, v);
    check(v[2:0] == 3'd2, "HOLD reaches public ARMED_HOLD state");
    armed = 1'b1; tick(20);
    axi_read(8'h14, v); check(v == 32'h1234_5678, "kernel epoch reads back exactly");

    axi_write(8'h0C, 32'd3); tick(600);
    axi_read(8'h10, v); check(v[2:0] == 3'd3, "AUTO reaches public ARMED_AUTO state");

    // run the loop and confirm events cross domains
    rx1_level = -16'sd35; rx2_level = -16'sd35;
    tick(4000);
    axi_read(8'h40, v); check(v > 32'd0, "transition count crossed back non-zero");
    axi_read(8'h38, v); check(v > 32'd0, "event level shows captured records");

    // drain one event through the four-read sequence across the CDC
    begin : drain
      reg [31:0] w0,w1,w2,w3,l0,l1;
      axi_read(8'h38, l0);
      axi_read(8'h44, w0); axi_read(8'h48, w1);
      axi_read(8'h4C, w2); axi_read(8'h50, w3);
      tick(10);
      axi_read(8'h38, l1);
      check(l1 == l0 - 1, "reading event word three pops exactly one entry");
      check(w3[23:16] == w3[31:24], "event carries paired gain indices");
      check(w2 != 32'd0, "event sequence and flags are populated");
      check(w0 != 32'd0 || w1 != 32'd0, "the 64-bit sample counter crossed intact");
    end

    // tandem invariant still holds with the domains truly asynchronous
    check(m_rx1 == m_rx2, "RX1 == RX2 with processor and receive clocks async");

    // Kernel teardown: AUTO -> HOLD-low -> AD9361 disarm -> mux release.
    axi_write(8'h0C, 32'd1); tick(600);
    axi_read(8'h10, v);
    check(v[2:0] == 3'd2, "teardown first reaches ARMED_HOLD");
    check(ctl_t == 4'd0 && ctl_o == 4'd0,
          "HOLD retains ownership and actively drives every CTRL_IN low");
    armed = 1'b0;
    axi_write(8'h0C, 32'd0); tick(600);
    axi_read(8'h10, v);
    check(v[2:0] == 3'd0, "release returns to public IDLE");
    check(ctl_t  == 4'hF, "pins tri-stated back to the legacy path");

    // Reproduce the hardware recovery path end-to-end: fill the asynchronous
    // event FIFO, observe fail-closed, then hold CLEAR across the configuration
    // CDC until the receive-domain sticky fault and FIFO are reset.
    axi_write(8'h0C, 32'h0000_0100); tick(300);
    axi_write(8'h0C, 32'd0); tick(300);
    model.rx1_index = 8'd40; model.rx2_index = 8'd40;
    axi_write(8'h0C, 32'd1); tick(600);
    armed = 1'b1;
    axi_write(8'h0C, 32'd3); tick(600);
    use_forced_detect = 1'b1;
    forced_detect = 8'h88; tick(15000); // both channels low-power
    forced_detect = 8'h44; tick(30000); // large overload on both channels
    axi_read(8'h34, v);
    check(v[0] == 1'b1, "undrained event FIFO raises the sticky overflow fault");
    axi_read(8'h10, v);
    check(v[2:0] == 3'd4, "FIFO overflow enters public FAULTED state");
    armed = 1'b0;
    axi_write(8'h0C, 32'h0000_0100); tick(600);
    axi_read(8'h34, v);
    check(v == 32'd0, "level-held AXI clear reaches the receive-domain fault");
    axi_read(8'h38, v);
    check(v == 32'd0, "level-held AXI clear resets the event FIFO");
    axi_write(8'h0C, 32'd0); tick(600);
    use_forced_detect = 1'b0;
    axi_read(8'h10, v);
    check(v[2:0] == 3'd0, "fault recovery returns to public IDLE");

    $display("---- scenario failures : %0d ----", errors);
    if (errors != 0) $fatal(1, "AXI TESTS FAILED");
    $display("PASS: tb_tandem_agc_axi");
    $finish;
  end

  initial begin #60000000; $fatal(1, "tb_tandem_agc_axi timeout"); end

endmodule
