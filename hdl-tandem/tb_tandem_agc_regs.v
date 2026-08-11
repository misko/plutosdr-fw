// -----------------------------------------------------------------------------
// tb_tandem_agc_regs.v -- register-map and control-surface test.
//
// Drives the controller entirely through the §8 register map, the way software
// will, and exercises the §11 enable and disable sequences through it.
// -----------------------------------------------------------------------------

`timescale 1ns/1ps

module tb_tandem_agc_regs;

  reg l_clk = 1'b0, l_resetn = 1'b0;
  always #5 l_clk = ~l_clk;

  reg  [7:0]  reg_addr = 8'd0;
  reg  [31:0] reg_wdata = 32'd0;
  reg         reg_wr = 1'b0, reg_rd = 1'b0;
  wire [31:0] reg_rdata;

  wire [1:0]  mode_req;  wire fault_clear;
  wire [7:0]  cfg_pulse_hi, cfg_pulse_lo, cfg_cooldown, cfg_dwell, cfg_debounce;
  wire [15:0] cfg_blank_guard;
  wire [31:0] cfg_pwr_period;
  wire [7:0]  cfg_idx_min, cfg_idx_max, cfg_idx_init;

  wire [2:0]  state;
  wire [7:0]  epoch, epoch_tomb, expected_index, fault, detect;
  wire        pulse_busy, cooldown_active, fpga_owns;
  wire [31:0] cnt_trans, cnt_inhib, cnt_clamp, cnt_stale;
  wire [127:0] evt_rdata;
  wire        evt_valid, evt_pop;
  wire [8:0]  evt_level;
  wire [31:0] evt_ovf;

  wire [3:0]  ctl_o, ctl_t;
  wire [7:0]  detect_pins;
  wire [7:0]  m_rx1, m_rx2;
  wire [31:0] m_acc, m_rej, m_ign;

  reg  [63:0] sample_counter = 64'd0;
  always @(posedge l_clk) sample_counter <= sample_counter + 64'd1;

  reg signed [15:0] rx1_level = -16'sd60, rx2_level = -16'sd60;
  reg armed = 1'b0;
  integer errors = 0;

  tandem_agc_regs regs (
    .l_clk(l_clk), .l_resetn(l_resetn),
    .reg_addr(reg_addr), .reg_wdata(reg_wdata), .reg_wr(reg_wr), .reg_rd(reg_rd),
    .reg_rdata(reg_rdata),
    .mode_req(mode_req), .fault_clear(fault_clear),
    .cfg_pulse_hi(cfg_pulse_hi), .cfg_pulse_lo(cfg_pulse_lo),
    .cfg_blank_guard(cfg_blank_guard), .cfg_pwr_period(cfg_pwr_period),
    .cfg_cooldown(cfg_cooldown), .cfg_dwell(cfg_dwell), .cfg_debounce(cfg_debounce),
    .cfg_idx_min(cfg_idx_min), .cfg_idx_max(cfg_idx_max), .cfg_idx_init(cfg_idx_init),
    .state(state), .epoch(epoch), .epoch_tomb(epoch_tomb),
    .expected_index(expected_index), .pulse_busy(pulse_busy),
    .cooldown_active(cooldown_active), .fpga_owns(fpga_owns),
    .fault(fault), .detect(detect),
    .cnt_trans(cnt_trans), .cnt_inhib(cnt_inhib),
    .cnt_clamp(cnt_clamp), .cnt_stale(cnt_stale),
    .evt_rdata(evt_rdata), .evt_valid(evt_valid), .evt_level(evt_level),
    .evt_ovf(evt_ovf), .evt_pop(evt_pop));

  tandem_agc_core core (
    .l_clk(l_clk), .l_resetn(l_resetn),
    .detect_async(detect_pins), .sample_counter(sample_counter),
    .mode_req(mode_req), .fault_clear(fault_clear), .consumer_ready(1'b1),
    .cfg_pulse_hi(cfg_pulse_hi), .cfg_pulse_lo(cfg_pulse_lo),
    .cfg_blank_guard(cfg_blank_guard), .cfg_pwr_period(cfg_pwr_period),
    .cfg_cooldown(cfg_cooldown), .cfg_dwell(cfg_dwell), .cfg_debounce(cfg_debounce),
    .cfg_idx_min(cfg_idx_min), .cfg_idx_max(cfg_idx_max), .cfg_idx_init(cfg_idx_init),
    .sw_idx_rx1(8'd0), .sw_idx_rx2(8'd0), .sw_idx_strobe(1'b0),
    .ps_ctl_o(4'd0), .ps_ctl_t(4'hF),
    .ctl_o(ctl_o), .ctl_t(ctl_t),
    .state_o(state), .epoch_o(epoch), .epoch_tomb_o(epoch_tomb),
    .expected_index_o(expected_index), .pulse_busy_o(pulse_busy),
    .cooldown_active_o(cooldown_active), .fpga_owns_o(fpga_owns),
    .fault_o(fault), .detect_o(detect),
    .cnt_trans_o(cnt_trans), .cnt_inhib_o(cnt_inhib),
    .cnt_clamp_o(cnt_clamp), .cnt_stale_o(cnt_stale),
    .evt_rdata_o(evt_rdata), .evt_valid_o(evt_valid), .evt_pop(evt_pop),
    .evt_level_o(evt_level), .evt_ovf_o(evt_ovf));

  ad9361_gain_model model (
    .clkrf(l_clk), .resetn(l_resetn),
    .ctrl_in(ctl_o), .ctrl_out(detect_pins),
    .pin_ctrl_armed(armed), .ensm_rx_active(1'b1),
    .inc_step(4'd1), .dec_step(4'd1), .pwot(5'd3), .idx_max(8'd76),
    .rx1_level(rx1_level), .rx2_level(rx2_level),
    .th_lg_lmt(-16'sd5), .th_lg_adc(-16'sd8), .th_sm_adc(-16'sd14),
    .th_low_pwr(-16'sd30), .pwr_period(16'd20), .drop_next_pulse(1'b0),
    .rx1_index(m_rx1), .rx2_index(m_rx2),
    .n_accepted(m_acc), .n_rejected_short(m_rej), .n_ignored_ensm(m_ign));

  task tick(input integer n); integer i;
    begin for (i=0;i<n;i=i+1) @(posedge l_clk); end endtask

  task wr(input [7:0] a, input [31:0] d);
    begin @(posedge l_clk); reg_addr=a; reg_wdata=d; reg_wr=1'b1;
          @(posedge l_clk); reg_wr=1'b0; end endtask

  task rd(input [7:0] a, output [31:0] d);
    begin @(posedge l_clk); reg_addr=a; reg_rd=1'b1; #1; d=reg_rdata;
          @(posedge l_clk); reg_rd=1'b0; end endtask

  task check(input cond, input [511:0] name);
    begin if (!cond) begin $display("FAIL: %0s", name); errors=errors+1; end
          else $display("  ok  %0s", name); end endtask

  reg [31:0] v;

  initial begin
    $display("== tb_tandem_agc_regs ==");
    tick(4); l_resetn = 1'b1; tick(4);

    rd(8'h00, v); check(v == 32'h5441_4731, "ID register reads the magic");
    rd(8'h0C, v); check(v[2:0] == 3'd0,     "STATUS reports LEGACY after reset");
    rd(8'h1C, v);
    check(v[7:0]  == 8'd16, "pulse width defaults to 16 (D-2)");
    rd(8'h24, v);
    check(v[7:0]  == 8'd2,  "cooldown defaults to 2 power-measurement periods");
    check(v[15:8] == 8'd4,  "dwell defaults to 4 periods");
    rd(8'h14, v);
    check(v[7:0]  == 8'd0 && v[15:8] == 8'd76,
          "index window defaults to the FULL range, not [40,54] (D-7 optional)");

    // configure a fast profile for simulation, then drive the lifecycle
    wr(8'h1C, {16'd8, 8'd4, 8'd4});      // blank_guard, lo, hi
    wr(8'h20, 32'd20);                   // pwr_period
    wr(8'h24, {8'd0, 8'd2, 8'd3, 8'd2}); // debounce, dwell, cooldown
    wr(8'h14, {8'd0, 8'd40, 8'd76, 8'd0});
    rd(8'h1C, v); check(v[7:0] == 8'd4,  "pulse width readback matches the write");
    rd(8'h20, v); check(v == 32'd20,     "pwr_period readback matches the write");

    // §11 enable through the register map
    model.rx1_index = 8'd40; model.rx2_index = 8'd40;
    wr(8'h08, 32'd1);                    // mode = tandem-hold
    tick(10);
    rd(8'h0C, v);
    check(v[2:0] == 3'd2, "writing mode 1 reaches OWNED_IDLE");
    check(v[4]   == 1'b1, "STATUS reports the FPGA owns the pins");
    armed = 1'b1; tick(4);
    rd(8'h10, v); check(v[7:0] == 8'd2, "EPOCH advanced on arming");

    wr(8'h08, 32'd2); tick(10);          // mode = tandem-auto
    rd(8'h0C, v); check(v[2:0] == 3'd3, "writing mode 2 reaches ACTIVE");

    rx1_level = -16'sd35; rx2_level = -16'sd35;   // drive an overload
    tick(600);
    rd(8'h48, v); check(v > 32'd0,       "CNT_TRANS counts transitions");
    rd(8'h40, v); check(v > 32'd0,       "EVT_LEVEL shows captured events");

    // drain one event through the four-read sequence; the last read pops
    begin : drain
      reg [31:0] w0,w1,w2,w3; reg [31:0] lvl0, lvl1;
      rd(8'h40, lvl0);
      rd(8'h30, w0); rd(8'h34, w1); rd(8'h38, w2); rd(8'h3C, w3);
      tick(2);
      rd(8'h40, lvl1);
      check(lvl1 == lvl0 - 1, "reading EVT_HI3 pops exactly one entry");
      check(w2[23:16] == {24'd0, epoch}, "the drained event carries the epoch (w2[23:16], §7.1)");
      check(w3[23:0] != 32'd0 || w2[31:24] != 8'd0, "the sequence field is populated");
      check(w0 != 32'd0 || w1 != 32'd0, "the sample counter field is populated");
    end

    // §11 disable through the register map
    wr(8'h08, 32'd0); tick(4); armed = 1'b0; tick(20);
    rd(8'h0C, v);
    check(v[2:0] == 3'd0, "writing mode 0 returns to LEGACY");
    check(v[4]   == 1'b0, "ownership returned to the PS");
    rd(8'h10, v); check(v[15:8] == 8'd2, "the retired epoch is tombstoned");

    $display("---- scenario failures : %0d ----", errors);
    if (errors != 0) $fatal(1, "REGISTER TESTS FAILED");
    $display("PASS: tb_tandem_agc_regs");
    $finish;
  end

  initial begin #20000000; $fatal(1, "tb_tandem_agc_regs timeout"); end

endmodule
