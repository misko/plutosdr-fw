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
  always @(posedge l_clk) sample_counter <= sample_counter + 64'd1;

  wire [3:0] ctl_o, ctl_t;
  wire [7:0] detect_pins;
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
    .detect_async(detect_pins), .sample_counter(sample_counter),
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

    axi_read(8'h00, v); check(v == 32'h5441_4731, "AXI read of ID returns the magic");
    axi_read(8'h0C, v); check(v[2:0] == 3'd0,     "STATUS crosses back: LEGACY at reset");
    axi_read(8'h14, v);
    check(v[7:0] == 8'd0 && v[15:8] == 8'd76,
          "index window default is the full range (D-7 optional)");

    // configure for a fast simulation profile, entirely over AXI
    axi_write(8'h1C, {16'd8, 8'd4, 8'd4});
    axi_write(8'h20, 32'd20);
    axi_write(8'h24, {8'd0, 8'd2, 8'd3, 8'd2});
    axi_write(8'h14, {8'd0, 8'd40, 8'd76, 8'd0});
    tick(50);
    axi_read(8'h1C, v); check(v[7:0] == 8'd4, "config write reads back over AXI");

    // §11 enable, driven over the bus
    model.rx1_index = 8'd40; model.rx2_index = 8'd40;
    axi_write(8'h08, 32'd1);
    tick(600);                                   // let the snapshot cross
    axi_read(8'h0C, v);
    check(v[2:0] == 3'd2, "mode 1 reaches OWNED_IDLE, observed across the CDC");
    check(v[4]   == 1'b1, "ownership is reported across the CDC");
    armed = 1'b1; tick(20);
    axi_read(8'h10, v); check(v[7:0] == 8'd2, "EPOCH crossed back correctly");

    axi_write(8'h08, 32'd2); tick(600);
    axi_read(8'h0C, v); check(v[2:0] == 3'd3, "mode 2 reaches ACTIVE");

    // run the loop and confirm events cross domains
    rx1_level = -16'sd35; rx2_level = -16'sd35;
    tick(4000);
    axi_read(8'h48, v); check(v > 32'd0, "CNT_TRANS crossed back non-zero");
    axi_read(8'h40, v); check(v > 32'd0, "EVT_LEVEL shows events in the async FIFO");

    // drain one event through the four-read sequence across the CDC
    begin : drain
      reg [31:0] w0,w1,w2,w3,l0,l1;
      axi_read(8'h40, l0);
      axi_read(8'h30, w0); axi_read(8'h34, w1);
      axi_read(8'h38, w2); axi_read(8'h3C, w3);
      tick(10);
      axi_read(8'h40, l1);
      check(l1 == l0 - 1, "reading EVT_HI3 over AXI pops exactly one entry");
      check(w2[23:16] == 32'd2, "the event carries the epoch across the CDC");
      check(w0 != 32'd0 || w1 != 32'd0, "the 64-bit sample counter crossed intact");
    end

    // tandem invariant still holds with the domains truly asynchronous
    check(m_rx1 == m_rx2, "RX1 == RX2 with processor and receive clocks async");

    // §11 disable over the bus
    axi_write(8'h08, 32'd0); tick(20); armed = 1'b0; tick(600);
    axi_read(8'h0C, v);
    check(v[2:0] == 3'd0, "mode 0 returns to LEGACY");
    check(v[4]   == 1'b0, "ownership returned to the PS");
    check(ctl_t  == 4'hF, "pins tri-stated back to the legacy path");

    $display("---- scenario failures : %0d ----", errors);
    if (errors != 0) $fatal(1, "AXI TESTS FAILED");
    $display("PASS: tb_tandem_agc_axi");
    $finish;
  end

  initial begin #60000000; $fatal(1, "tb_tandem_agc_axi timeout"); end

endmodule
