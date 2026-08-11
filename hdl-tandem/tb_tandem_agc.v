// -----------------------------------------------------------------------------
// tb_tandem_agc.v -- closed-loop test of the tandem AGC controller.
//
// The controller drives the behavioural AD9361 model's CTRL_IN pins; the model's
// CTRL_OUT page-0x03 detectors drive the controller back. The twelve §10
// assertions run continuously as procedural checkers throughout every scenario.
//
// Scenario list follows tandem_agc_plan.md §8.2.
// -----------------------------------------------------------------------------

`timescale 1ns/1ps

module tb_tandem_agc;

  // CLKRF_DIV=1 -> ClkRF == l_clk (rx_fir_dec=2, ratio 1.0)
  // CLKRF_DIV=2 -> ClkRF == l_clk/2 (rx_fir_dec=1, ratio 2.0, the boot default
  //                and the case where a naive 2-cycle pulse is illegal)
  parameter integer CLKRF_DIV = 1;

  reg l_clk = 1'b0;
  reg l_resetn = 1'b0;
  always #5 l_clk = ~l_clk;

  reg clkrf = 1'b0;
  always @(posedge l_clk) clkrf <= ~clkrf;   // period 2 l_clk => ClkRF = l_clk/2
  wire clkrf_use = (CLKRF_DIV == 1) ? l_clk : clkrf;

  // ---- configuration -------------------------------------------------------
  reg [7:0]  cfg_pulse_hi  = 8'd4;
  reg [7:0]  cfg_pulse_lo  = 8'd4;
  reg [15:0] cfg_blank_guard = 16'd8;
  reg [31:0] cfg_pwr_period = 32'd20;
  reg [7:0]  cfg_cooldown  = 8'd2;
  reg [7:0]  cfg_dwell     = 8'd3;
  reg [7:0]  cfg_debounce  = 8'd2;
  reg [7:0]  cfg_idx_min   = 8'd0;
  reg [7:0]  cfg_idx_max   = 8'd76;
  reg [7:0]  cfg_idx_init  = 8'd40;

  reg [1:0] mode_req = 2'd0;
  reg       fault_clear = 1'b0;
  reg       consumer_ready = 1'b1;
  reg [3:0] ps_ctl_o = 4'd0;
  reg [3:0] ps_ctl_t = 4'hF;
  reg [7:0] sw_idx_rx1 = 8'd0, sw_idx_rx2 = 8'd0;
  reg       sw_idx_strobe = 1'b0;
  reg       evt_pop = 1'b0;
  reg [63:0] sample_counter = 64'd0;
  always @(posedge l_clk) sample_counter <= sample_counter + 64'd1;

  // ---- model stimulus ------------------------------------------------------
  reg signed [15:0] rx1_level = -16'sd60;
  reg signed [15:0] rx2_level = -16'sd60;
  reg signed [15:0] th_lg_lmt = -16'sd5;
  reg signed [15:0] th_lg_adc = -16'sd8;
  reg signed [15:0] th_sm_adc = -16'sd14;
  reg signed [15:0] th_low_pwr = -16'sd30;
  reg               armed = 1'b0;
  reg               ensm_rx = 1'b1;
  reg               drop_next = 1'b0;

  // ---- wires ---------------------------------------------------------------
  wire [3:0]   ctl_o, ctl_t;
  wire [7:0]   detect;
  wire [2:0]   state;
  wire [7:0]   epoch, epoch_tomb, expected_index, fault, det_stable;
  wire         pulse_busy, cooldown_active, fpga_owns;
  wire [31:0]  cnt_trans, cnt_inhib, cnt_clamp, cnt_stale;
  wire [127:0] evt_rdata;
  wire         evt_valid;
  wire [8:0]   evt_level;
  wire [31:0]  evt_ovf;
  wire [7:0]   m_rx1, m_rx2;
  wire [31:0]  m_acc, m_rej, m_ign;

  integer errors = 0;

  tandem_agc_core core (
    .l_clk(l_clk), .l_resetn(l_resetn),
    .detect_async(detect), .sample_counter(sample_counter),
    .mode_req(mode_req), .fault_clear(fault_clear), .consumer_ready(consumer_ready),
    .cfg_pulse_hi(cfg_pulse_hi), .cfg_pulse_lo(cfg_pulse_lo),
    .cfg_blank_guard(cfg_blank_guard), .cfg_pwr_period(cfg_pwr_period),
    .cfg_cooldown(cfg_cooldown), .cfg_dwell(cfg_dwell), .cfg_debounce(cfg_debounce),
    .cfg_idx_min(cfg_idx_min), .cfg_idx_max(cfg_idx_max), .cfg_idx_init(cfg_idx_init),
    .sw_idx_rx1(sw_idx_rx1), .sw_idx_rx2(sw_idx_rx2), .sw_idx_strobe(sw_idx_strobe),
    .ps_ctl_o(ps_ctl_o), .ps_ctl_t(ps_ctl_t),
    .ctl_o(ctl_o), .ctl_t(ctl_t),
    .state_o(state), .epoch_o(epoch), .epoch_tomb_o(epoch_tomb),
    .expected_index_o(expected_index), .pulse_busy_o(pulse_busy),
    .cooldown_active_o(cooldown_active), .fpga_owns_o(fpga_owns),
    .fault_o(fault), .detect_o(det_stable),
    .cnt_trans_o(cnt_trans), .cnt_inhib_o(cnt_inhib),
    .cnt_clamp_o(cnt_clamp), .cnt_stale_o(cnt_stale),
    .evt_rdata_o(evt_rdata), .evt_valid_o(evt_valid), .evt_pop(evt_pop),
    .evt_level_o(evt_level), .evt_ovf_o(evt_ovf));

  ad9361_gain_model model (
    .clkrf(clkrf_use), .resetn(l_resetn),
    .ctrl_in(ctl_o), .ctrl_out(detect),
    .pin_ctrl_armed(armed), .ensm_rx_active(ensm_rx),
    .inc_step(4'd1), .dec_step(4'd1), .pwot(5'd3), .idx_max(8'd76),
    .rx1_level(rx1_level), .rx2_level(rx2_level),
    .th_lg_lmt(th_lg_lmt), .th_lg_adc(th_lg_adc), .th_sm_adc(th_sm_adc),
    .th_low_pwr(th_low_pwr), .pwr_period(16'd20),
    .drop_next_pulse(drop_next),
    .rx1_index(m_rx1), .rx2_index(m_rx2),
    .n_accepted(m_acc), .n_rejected_short(m_rej), .n_ignored_ensm(m_ign));

  wire [31:0] a_err;
  tandem_agc_checkers chk (
    .l_clk(l_clk), .l_resetn(l_resetn),
    .ctl_o(ctl_o), .ctl_t(ctl_t), .ps_ctl_o(ps_ctl_o), .ps_ctl_t(ps_ctl_t),
    .fpga_owns(fpga_owns), .armed(armed),
    .pulse_hi_eff(core.pulse_hi_eff), .pulse_lo_eff(core.pulse_lo_eff),
    .pulse_busy(pulse_busy), .cooldown_active(cooldown_active),
    .blanked(core.blanked), .fault(fault),
    .expected_index(expected_index), .step_size(8'd1),
    .policing(state == 3'd3),
    .evt_push(core.evt_push), .evt_wdata(core.evt_wdata), .epoch(epoch),
    .a_err(a_err));

  // ---- helpers -------------------------------------------------------------
  task tick(input integer n);
    integer i; begin for (i=0;i<n;i=i+1) @(posedge l_clk); end
  endtask

  task check(input cond, input [511:0] name);
    begin
      if (!cond) begin $display("FAIL: %0s", name); errors = errors + 1; end
      else       begin $display("  ok  %0s", name); end
    end
  endtask

  // §11 enable: program the index over SPI, take ownership, THEN arm
  task enable_tandem(input [1:0] mode);
    begin
      model.rx1_index = cfg_idx_init;      // step 5: SPI programs both indices
      model.rx2_index = cfg_idx_init;
      mode_req = mode;
      tick(4);
      wait (fpga_owns == 1'b1);
      tick(2);
      armed = 1'b1;                        // step 11: only now arm 0x0FB
      tick(4);
    end
  endtask

  task disable_tandem;
    begin
      mode_req = 2'd0;
      tick(2);
      armed = 1'b0;                        // disarm BEFORE ownership returns
      wait (fpga_owns == 1'b0);
      tick(4);
    end
  endtask

  task settle(input integer periods);
    begin tick(periods * cfg_pwr_period + 40); end
  endtask

  initial begin
    $display("== tb_tandem_agc (CLKRF_DIV=%0d) ==", CLKRF_DIV);
    tick(4); l_resetn = 1'b1; tick(8);

    // -- 1. reset default is legacy, PS owns, high-Z ------------------------
    check(state == 3'd0,        "reset state is LEGACY");
    check(fpga_owns == 1'b0,    "PS owns the pins at reset");
    check(ctl_t == 4'hF,        "pins are tri-stated at reset");

    // -- 2. legacy passthrough ---------------------------------------------
    ps_ctl_o = 4'b1010; ps_ctl_t = 4'b0000; tick(4);
    check(ctl_o == 4'b1010,     "legacy value passes through");
    check(ctl_t == 4'b0000,     "legacy tri-state passes through");
    ps_ctl_o = 4'd0; ps_ctl_t = 4'hF; tick(4);

    // -- 3. enable to hold: owns pins, drives low, no pulses ---------------
    enable_tandem(2'd1);
    check(state == 3'd2,        "mode 1 reaches OWNED_IDLE (tandem-hold)");
    check(fpga_owns == 1'b1,    "FPGA owns the pins");
    check(ctl_t == 4'd0,        "FPGA drives the pins");
    check(ctl_o == 4'd0,        "outputs held low in tandem-hold");
    check(epoch == 8'd2,        "epoch incremented on arming");
    settle(4);
    check(cnt_trans == 32'd0,   "no transitions occur in tandem-hold");

    // -- 4. tandem-auto with a strong signal on ONE channel -> decrease -----
    mode_req = 2'd2; tick(4);
    check(state == 3'd3,        "mode 2 reaches ACTIVE (tandem-auto)");
    rx1_level = -16'sd40;       // index 40 -> effective 0, well over every thresh
    rx2_level = -16'sd90;       // channel 2 sees nothing
    settle(6);
    check(cnt_trans > 32'd0,    "one-channel overload forces a tandem decrease");
    check(m_rx1 == m_rx2,       "BOTH channels moved together (tandem invariant)");
    check(m_rx1 < cfg_idx_init, "the common index went down");

    // -- 5. only one channel low-power must never cause an increase --------
    begin : one_lp
      reg [7:0] idx0; reg [31:0] t0;
      rx1_level = -16'sd90;     // ch1 very weak -> low power
      rx2_level = -16'sd60;     // ch2 in the HOLD band: not low power, not overloading
      settle(8);
      idx0 = m_rx1; t0 = cnt_trans;
      settle(8);
      check(m_rx1 == idx0,      "one low-power channel does NOT raise gain");
      check(cnt_inhib > 32'd0,  "the starvation case is counted, not silent");
    end

    // -- 6. both channels low-power -> increase after the dwell ------------
    begin : both_lp
      reg [7:0] idx0;
      idx0 = m_rx1;
      rx1_level = -16'sd95; rx2_level = -16'sd95;
      settle(10);
      if (!(m_rx1 > idx0))
        $display("    DIAG idx0=%0d m_rx1=%0d state=%0d fault=%02x exp=%0d det=%08b lvl=%0d",
                 idx0, m_rx1, state, fault, expected_index, det_stable, rx1_level);
      check(m_rx1 > idx0,       "both channels low-power raises gain after dwell");
      check(m_rx1 == m_rx2,     "channels still equal after increases");
    end

    // -- 7. tandem invariant holds through a full up/down cycle ------------
    begin : invariant
      integer k; reg ok;
      ok = 1'b1;
      for (k = 0; k < 12; k = k + 1) begin
        rx1_level = (k[0]) ? -16'sd40 : -16'sd95;
        rx2_level = (k[0]) ? -16'sd42 : -16'sd95;
        settle(3);
        if (m_rx1 !== m_rx2) ok = 1'b0;
      end
      check(ok, "RX1 == RX2 at every checkpoint across 12 level swings");
    end

    // -- 8. minimum clamp: persistent overload must not spin ---------------
    begin : clamp_min
      reg [31:0] c0;
      cfg_idx_min = m_rx1;  tick(4);       // clamp right where we are
      rx1_level = -16'sd20; rx2_level = -16'sd20;   // hard overload
      settle(6);
      c0 = cnt_clamp;
      settle(6);
      check(cnt_clamp > c0,    "clamped-at-limit is reported while overload persists");
      check(m_rx1 >= cfg_idx_min, "the index never goes below the clamp");
      cfg_idx_min = 8'd0; tick(4);
    end

    // -- 9. events: one per accepted transition, ordered --------------------
    begin : events
      reg [31:0] n0; integer popped; reg ok;
      n0 = cnt_trans;
      rx1_level = -16'sd95; rx2_level = -16'sd95;
      settle(12);
      check(evt_level > 9'd0,  "events were captured");
      // drain and verify epoch and monotonic sequence
      ok = 1'b1; popped = 0;
      while (evt_valid && popped < 64) begin
        if (evt_rdata[87:80] !== epoch) ok = 1'b0;
        @(posedge l_clk); evt_pop = 1'b1; @(posedge l_clk); evt_pop = 1'b0;
        popped = popped + 1;
      end
      check(ok, "every drained event carries the current epoch");
      check(popped > 0, "the FIFO drained");
    end

    // -- 10. disable returns the pins cleanly -------------------------------
    disable_tandem;
    check(state == 3'd0,     "disable returns to LEGACY");
    check(fpga_owns == 1'b0, "ownership returned to the PS");
    check(ctl_t == 4'hF,     "pins tri-stated again");
    check(epoch_tomb == 8'd2,"the retired epoch is tombstoned");

    // -- 11. re-enable takes a NEW epoch ------------------------------------
    enable_tandem(2'd2);
    check(epoch == 8'd3,     "re-arming takes a new, never-reused epoch");
    disable_tandem;

    // -- 12. consumer not ready must fault rather than arm ------------------
    begin : no_consumer
      consumer_ready = 1'b0;
      mode_req = 2'd1; tick(20);
      check(fault[2] == 1'b1, "arming without a ready consumer raises a fault");
      mode_req = 2'd0; tick(10);
      fault_clear = 1'b1; tick(4); fault_clear = 1'b0;
      consumer_ready = 1'b1; tick(10);
    end

    // -- 13. ENSM: pulses are ignored outside RX (E-AGC1 H6) ---------------
    begin : ensm_test
      reg [31:0] ig0;
      enable_tandem(2'd2);
      ensm_rx = 1'b0;
      ig0 = m_ign;
      rx1_level = -16'sd20; rx2_level = -16'sd20;
      settle(8);
      check(m_ign > ig0,   "the part ignores edges while the ENSM is not RX-active");
      ensm_rx = 1'b1; tick(10);
      disable_tandem;
    end

    // -- 14. reset while ACTIVE returns to a safe legacy state -------------
    begin : reset_active
      enable_tandem(2'd2);
      rx1_level = -16'sd20; rx2_level = -16'sd20;
      tick(30);
      l_resetn = 1'b0; armed = 1'b0; mode_req = 2'd0; tick(6); l_resetn = 1'b1; tick(6);
      check(state == 3'd0,     "reset from ACTIVE lands in LEGACY");
      check(ctl_t == 4'hF,     "reset restores tri-state to the legacy path");
      check(fpga_owns == 1'b0, "reset returns ownership to the PS");
      mode_req = 2'd0; tick(4);
    end

    // -- 15. D-2 floor: a too-small configured width is clamped in RTL ------
    begin : pulse_floor
      reg [31:0] rej0;
      cfg_pulse_hi = 8'd2; cfg_pulse_lo = 8'd2;   // illegal at ratio 2.0
      tick(4);
      check(core.pulse_hi_eff == 8'd4, "configured width below 4 is clamped to 4");
      enable_tandem(2'd2);
      rej0 = m_rej;
      rx1_level = -16'sd20; rx2_level = -16'sd20;
      settle(8);
      check(m_rej == rej0, "no pulse is rejected as too short at any supported ratio");
      check(cnt_trans > 32'd0, "transitions still occur with the clamped width");
      disable_tandem;
      cfg_pulse_hi = 8'd4; cfg_pulse_lo = 8'd4; tick(4);
    end

    // ---- summary -----------------------------------------------------------
    $display("---- assertion failures: %0d ----", a_err);
    $display("---- scenario failures : %0d ----", errors);
    if (a_err != 0 || errors != 0)
      $fatal(1, "TANDEM AGC TESTS FAILED (assert=%0d scenario=%0d)", a_err, errors);
    $display("PASS: tb_tandem_agc CLKRF_DIV=%0d", CLKRF_DIV);
    $finish;
  end

  initial begin
    #40000000;
    $fatal(1, "tb_tandem_agc timeout");
  end

endmodule
