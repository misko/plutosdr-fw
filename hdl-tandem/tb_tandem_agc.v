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
  reg [19:0] cfg_pwr_period = 20'd20;
  reg [7:0]  cfg_cooldown  = 8'd2;
  reg [7:0]  cfg_dwell     = 8'd3;
  reg [7:0]  cfg_debounce  = 8'd2;
  reg [7:0]  cfg_idx_min   = 8'd0;
  reg [7:0]  cfg_idx_max   = 8'd76;
  reg [7:0]  cfg_idx_init  = 8'd40;

  reg [1:0] mode_req = 2'd0;
  reg [31:0] cfg_epoch = 32'd1;
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
  wire [31:0]  epoch, epoch_tomb;
  wire [7:0]   expected_index, fault, det_stable;
  wire         pulse_busy, cooldown_active, fpga_owns;
  wire [7:0]   cnt_trans, cnt_inhib, cnt_clamp, cnt_stale;
  wire [127:0] evt_rdata;
  wire         evt_valid;
  wire [6:0]   evt_level;
  wire [7:0]   evt_ovf;
  wire [7:0]   m_rx1, m_rx2;
  wire [31:0]  m_acc, m_rej, m_ign;

  integer errors = 0;

  tandem_agc_core core (
    .l_clk(l_clk), .l_resetn(l_resetn),
    .detect_async(detect), .sample_counter(sample_counter), .sample_valid(1'b1),
    .mode_req(mode_req), .cfg_epoch(cfg_epoch),
    .fault_clear(fault_clear), .consumer_ready(consumer_ready),
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
    .evt_rd_clk(l_clk), .evt_rd_resetn(l_resetn),
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
      cfg_epoch = cfg_epoch + 32'd1;
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
    check(epoch == 32'd2,       "requested epoch accepted on arming");
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

    // -- 6a. stale small-ADC latch plus both-low must clear safely ---------
    // UG-570 says the small-ADC overload output stays latched until a gain
    // change, while MGC low-power continues to follow the current average.
    // First establish the small-only detector state at the current index, then
    // remove the signal.  The resulting small-overload + both-low combination
    // used to deadlock forever because small-overload inhibited the increase
    // that was needed to clear it.  The first recovery edge must be a
    // conservative DECREASE, never an unsafe both-low INCREASE.
    begin : stale_small_clear
      integer wait_cycles;
      reg [7:0] idx0;
      reg [31:0] t0, accepted0;
      reg saw_clear, saw_recovery, clear_physical, fresh_guard_ok;
      reg saw_large, rearm_guard_ok;

      // One low-power channel plus a small overload on its peer is not the
      // two-channel contradiction and must remain HOLD.
      rx1_level = -16'sd120;
      rx2_level = -16'sd10 - $signed({8'd0, m_rx2});
      settle(4);
      idx0 = m_rx1;
      t0 = cnt_trans;
      settle(4);
      check(det_stable == 8'h81,
            "one-low-power plus peer-small detector state is explicit");
      check(m_rx1 == idx0 && cnt_trans == t0,
            "one-low-power plus peer-small remains HOLD");
      check(core.small_latch_dwell_cnt == 8'd0,
            "one-channel evidence cannot accumulate clear dwell");

      // A small latch on either receiver is shared safety evidence.  Preserve
      // the RX2-only latch established above, then prove its clear pulse still
      // moves the pair.
      rx1_level = -16'sd20 - $signed({8'd0, m_rx1});
      rx2_level = -16'sd10 - $signed({8'd0, m_rx2});
      settle(4);
      check(det_stable == 8'h01,
            "one receiver can hold the small-ADC latch without a gain edge");
      idx0 = m_rx1;
      t0 = cnt_trans;
      accepted0 = m_acc;
      saw_clear = 1'b0;

      rx1_level = -16'sd120; rx2_level = -16'sd120;
      for (wait_cycles = 0;
           wait_cycles < 2000 &&
           core.small_latch_dwell_cnt < cfg_dwell - 8'd1;
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
      end
      check(core.small_latch_dwell_cnt == cfg_dwell - 8'd1 &&
            cnt_trans == t0 && !core.evt_push,
            "first two conflict ticks cannot act before dwell three");
      for (wait_cycles = 0;
           wait_cycles < 1000 && core.small_latch_dwell_cnt < cfg_dwell;
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
      end
      check(core.small_latch_dwell_cnt == cfg_dwell &&
            cnt_trans == t0 && !core.evt_push,
            "third conflict tick matures but does not skip handoff");
      for (wait_cycles = 0; wait_cycles < 1000 && !saw_clear;
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
        if (core.evt_push) begin
          saw_clear = 1'b1;
          check(core.evt_reason == 4'd2,
                "stale small-ADC recovery event carries SMALL_ADC_INHIBIT reason");
          check(core.req_dir == 2'd2,
                "stale small-ADC recovery first moves gain in the safe direction");
          check(core.evt_wdata[127:120] == idx0 - 8'd1 &&
                core.evt_wdata[119:112] == idx0 - 8'd1,
                "stale small-ADC event records one paired index down");
        end
      end
      check(saw_clear && cnt_trans == t0 + 32'd1,
            "stale small-ADC gets one conservative clear edge");
      clear_physical = 1'b0;
      for (wait_cycles = 0; wait_cycles < 1000 && !clear_physical;
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
        if (m_rx1 == idx0 - 8'd1 && m_rx2 == idx0 - 8'd1)
          clear_physical = 1'b1;
      end
      check(clear_physical && m_acc == accepted0 + 32'd1,
            "reason-2 request becomes one physical paired decrement");

      fresh_guard_ok = 1'b1;
      for (wait_cycles = 0;
           wait_cycles < 2000 &&
           (core.pulse_pending || core.blanked || cooldown_active);
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
        if (core.dwell_cnt != 8'd0 ||
            core.small_latch_dwell_cnt != 8'd0 ||
            core.small_latch_rearm_dwell_cnt != 8'd0)
          fresh_guard_ok = 1'b0;
      end
      check(fresh_guard_ok && !core.pulse_pending && !core.blanked &&
            !cooldown_active,
            "all dwell evidence stays zero through clear pulse and guard");

      saw_recovery = 1'b0;
      for (wait_cycles = 0; wait_cycles < 2000 && !saw_recovery;
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
        if (core.evt_push) begin
          saw_recovery = 1'b1;
          check(core.evt_reason == 4'd3 && core.req_dir == 2'd1,
                "first post-clear transition is an ordinary low-power increase");
          check(core.evt_wdata[127:120] == idx0 &&
                core.evt_wdata[119:112] == idx0,
                "post-clear event records the paired pre-clear endpoint");
        end
      end
      check(saw_recovery, "clean both-low dwell recovers after the clear edge");
      for (wait_cycles = 0; wait_cycles < 1000 && m_rx1 != idx0;
           wait_cycles = wait_cycles + 1)
        @(posedge l_clk);
      check(m_rx1 == idx0 && m_rx2 == idx0,
            "physical gain pair returns to its pre-clear endpoint");
      check(m_rx1 == m_rx2,
            "stale-latch recovery preserves paired receiver gain");

      // A detector dropout or quiet hold-band interval alone cannot re-arm the
      // consumed clear.  A genuinely new episode requires an ordinary large-
      // overload decrease followed by a separate, fresh full dwell with
      // neither low-power bit asserted.
      rx1_level = -16'sd20 - $signed({8'd0, m_rx1});
      rx2_level = -16'sd20 - $signed({8'd0, m_rx2});
      settle(4);
      check(core.small_latch_clear_attempted &&
            !core.small_latch_rearm_pending,
            "low-power deassertion alone cannot re-arm a consumed clear");

      rx1_level = -16'sd20; rx2_level = -16'sd20;
      saw_large = 1'b0;
      for (wait_cycles = 0; wait_cycles < 1000 && !saw_large;
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
        if (core.evt_push &&
            (core.evt_reason == 4'd0 || core.evt_reason == 4'd1))
          saw_large = 1'b1;
      end
      check(saw_large && core.small_latch_rearm_pending,
            "ordinary large decrease starts re-arm proof");
      rx1_level = -16'sd20 - $signed({8'd0, expected_index});
      rx2_level = -16'sd20 - $signed({8'd0, expected_index});
      rearm_guard_ok = 1'b1;
      for (wait_cycles = 0;
           wait_cycles < 2000 &&
           (core.pulse_pending || core.blanked || cooldown_active);
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
        if (core.small_latch_rearm_dwell_cnt != 8'd0)
          rearm_guard_ok = 1'b0;
      end
      check(rearm_guard_ok && !core.pulse_pending && !core.blanked &&
            !cooldown_active,
            "strong re-arm proof cannot accrue through pulse and guard");

      // Accumulate only a partial proof, then prove HOLD and a one-LP interval
      // each erase it without clearing the consumed token.
      for (wait_cycles = 0;
           wait_cycles < 1000 && core.small_latch_rearm_dwell_cnt == 8'd0;
           wait_cycles = wait_cycles + 1)
        @(posedge l_clk);
      check(core.small_latch_rearm_dwell_cnt != 8'd0 &&
            core.small_latch_clear_attempted,
            "eligible neither-low evidence begins the re-arm dwell");
      mode_req = 2'd1; tick(4);
      check(core.small_latch_rearm_dwell_cnt == 8'd0 &&
            core.small_latch_clear_attempted &&
            core.small_latch_rearm_pending,
            "HOLD resets partial re-arm dwell without restoring availability");
      rx1_level = -16'sd120;
      rx2_level = -16'sd20 - $signed({8'd0, m_rx2});
      mode_req = 2'd2; tick(4); settle(4);
      check(core.small_latch_rearm_dwell_cnt == 8'd0 &&
            core.small_latch_clear_attempted,
            "one low-power bit resets re-arm proof");

      // A later accepted large decrease restarts the proof from zero.
      rx1_level = -16'sd20; rx2_level = -16'sd20;
      saw_large = 1'b0;
      for (wait_cycles = 0; wait_cycles < 1000 && !saw_large;
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
        if (core.evt_push &&
            (core.evt_reason == 4'd0 || core.evt_reason == 4'd1))
          saw_large = 1'b1;
      end
      check(saw_large && core.small_latch_rearm_dwell_cnt == 8'd0,
            "later large decrease restarts re-arm proof at zero");
      rx1_level = -16'sd20 - $signed({8'd0, expected_index});
      rx2_level = -16'sd20 - $signed({8'd0, expected_index});
      rearm_guard_ok = 1'b1;
      for (wait_cycles = 0;
           wait_cycles < 2000 &&
           (core.pulse_pending || core.blanked || cooldown_active);
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
        if (core.small_latch_rearm_dwell_cnt != 8'd0)
          rearm_guard_ok = 1'b0;
      end
      check(rearm_guard_ok && !core.pulse_pending && !core.blanked &&
            !cooldown_active,
            "re-arm dwell stays zero while the second edge is guarded");
      for (wait_cycles = 0;
           wait_cycles < 2000 &&
           core.small_latch_rearm_dwell_cnt < cfg_dwell - 8'd1;
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
      end
      check(core.small_latch_rearm_dwell_cnt == cfg_dwell - 8'd1 &&
            core.small_latch_clear_attempted,
            "first two strong ticks cannot re-arm before dwell three");
      for (wait_cycles = 0;
           wait_cycles < 1000 &&
           core.small_latch_rearm_dwell_cnt < cfg_dwell;
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
      end
      check(core.small_latch_rearm_dwell_cnt == cfg_dwell &&
            core.small_latch_clear_attempted,
            "third strong tick matures re-arm without skipping handoff");
      for (wait_cycles = 0;
           wait_cycles < 2000 && core.small_latch_clear_attempted;
           wait_cycles = wait_cycles + 1)
        @(posedge l_clk);
      check(!core.small_latch_clear_attempted &&
            !core.small_latch_rearm_pending,
            "fresh neither-low dwell re-arms after the ordinary decrease");

      // Prove the new episode gets one clear edge, and that withdrawing AUTO
      // in its fire-request handoff cannot expose HOLD before the physical
      // pulse completes.
      rx1_level = -16'sd10 - $signed({8'd0, m_rx1});
      rx2_level = -16'sd10 - $signed({8'd0, m_rx2});
      settle(4);
      idx0 = m_rx1;
      t0 = cnt_trans;
      rx1_level = -16'sd120; rx2_level = -16'sd120;
      saw_clear = 1'b0;
      for (wait_cycles = 0; wait_cycles < 1000 && !saw_clear;
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
        if (core.fire_req && core.evt_reason == 4'd2)
          saw_clear = 1'b1;
      end
      check(saw_clear, "re-armed episode produces a bounded clear request");
      @(negedge l_clk); mode_req = 2'd1;
      @(posedge l_clk); #1;
      check(cnt_trans == t0 + 32'd1 && expected_index == idx0 - 8'd1,
            "a new contradiction episode gets exactly one clear edge");
      check(state == 3'd3 && pulse_busy,
            "HOLD waits for a queued small-latch clear pulse");
      for (wait_cycles = 0;
           wait_cycles < 2000 && (core.fire_req || pulse_busy);
           wait_cycles = wait_cycles + 1)
        @(posedge l_clk);
      check(!core.fire_req && !pulse_busy,
            "small-latch clear pulse finishes within the bounded handoff");
      tick(2);
      check(state == 3'd2,
            "HOLD follows only after the small-latch clear pulse completes");
      // A full ownership release/re-acquire starts the later legacy scenarios
      // with a fresh clear budget, as the real driver does for a new buffer.
      disable_tandem;
      enable_tandem(2'd2);
      check(!core.small_latch_clear_attempted &&
            !core.small_latch_rearm_pending &&
            core.small_latch_dwell_cnt == 8'd0 &&
            core.small_latch_rearm_dwell_cnt == 8'd0,
            "new ownership resets clear token and proof counters");
    end

    // -- 7. tandem invariant holds through a full up/down cycle ------------
    begin : invariant
      integer k; reg ok;
      ok = 1'b1;
      for (k = 0; k < 6; k = k + 1) begin
        rx1_level = -16'sd40; rx2_level = -16'sd42;
        settle(3);
        if (m_rx1 !== m_rx2) ok = 1'b0;
        rx1_level = -16'sd95; rx2_level = -16'sd95;
        settle(3);
        if (m_rx1 !== m_rx2 || fault != 8'd0) ok = 1'b0;
        // Each iteration represents a separate buffer ownership session.  The
        // real acquire path clears detector latches and starts a fresh budget.
        if (k != 5) begin
          disable_tandem;
          enable_tandem(2'd2);
        end
      end
      check(ok, "RX1 == RX2 across six independent gain cycles");
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
      check(evt_level > 7'd0,  "events were captured");
      // Drain and verify the fixed v2 post-change paired-gain record.
      ok = 1'b1; popped = 0;
      while (evt_valid && popped < 64) begin
        if (evt_rdata[119:112] !== evt_rdata[127:120]) ok = 1'b0;
        @(posedge l_clk); evt_pop = 1'b1; @(posedge l_clk); evt_pop = 1'b0;
        popped = popped + 1;
      end
      check(ok, "every drained event carries paired post-change indices");
      check(popped > 0, "the FIFO drained");
    end

    // -- 10. disable returns the pins cleanly -------------------------------
    disable_tandem;
    check(state == 3'd0,     "disable returns to LEGACY");
    check(fpga_owns == 1'b0, "ownership returned to the PS");
    check(ctl_t == 4'hF,     "pins tri-stated again");
    check(epoch_tomb == cfg_epoch,"the retired epoch is tombstoned");

    // -- 11. re-enable takes a NEW epoch ------------------------------------
    enable_tandem(2'd2);
    check(epoch == cfg_epoch, "re-arming takes the requested new epoch");
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

    // -- 16. persistent/high-PAPR conflict faults after one clear ----------
    begin : persistent_small_conflict
      integer wait_cycles;
      reg [7:0] idx0, t0, clamp0;
      reg [31:0] accepted0;
      reg saw_clear, saw_fresh_tick, fresh_guard_ok;

      cfg_cooldown = 8'd0;
      cfg_dwell = 8'd0;
      rx1_level = -16'sd60; rx2_level = -16'sd60;
      enable_tandem(2'd2);
      rx1_level = -16'sd10 - $signed({8'd0, m_rx1});
      rx2_level = -16'sd10 - $signed({8'd0, m_rx2});
      settle(4);
      idx0 = m_rx1;
      t0 = cnt_trans;
      clamp0 = cnt_clamp;
      accepted0 = m_acc;
      saw_clear = 1'b0;
      saw_fresh_tick = 1'b0;

      // The scalar model cannot independently express low average power and
      // small-ADC peak overload, so hold its already-sampled low-power bits
      // high while the real overload-latch logic continues to run.
      @(negedge l_clk); core.pwr_div = 20'd0;
      force model.samp_lp1 = 1'b1;
      force model.samp_lp2 = 1'b1;
      for (wait_cycles = 0; wait_cycles < 1000 && !saw_clear;
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
        if (core.small_latch_dwell_cnt != 8'd0)
          saw_fresh_tick = 1'b1;
        if (core.evt_push) begin
          saw_clear = 1'b1;
          check(core.evt_reason == 4'd2 && core.req_dir == 2'd2,
                "high-PAPR conflict first emits the conservative clear edge");
        end
      end
      check(saw_fresh_tick && saw_clear,
            "zero configured dwell still requires one fresh conflict tick");
      cfg_dwell = 8'd3;

      // Keep the conflict true through the pulse/blanking interval, then drop
      // both sampled LP bits for longer than a dwell while the attempt is
      // consumed.  This models average-power/high-PAPR chatter and proves that
      // neither detector flicker nor the post-pulse blanking interval re-arms
      // another reason-2 decrement.
      fresh_guard_ok = 1'b1;
      for (wait_cycles = 0;
           wait_cycles < 2000 &&
           (core.pulse_pending || core.blanked || cooldown_active);
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
        if (core.small_latch_dwell_cnt != 8'd0 || core.dwell_cnt != 8'd0 ||
            core.small_latch_rearm_dwell_cnt != 8'd0)
          fresh_guard_ok = 1'b0;
      end
      check(fresh_guard_ok && !core.pulse_pending && !core.blanked &&
            !cooldown_active,
            "pulse, blanking, and cooldown cannot pre-credit either dwell");
      force model.samp_lp1 = 1'b0;
      force model.samp_lp2 = 1'b0;
      settle(4);
      check(det_stable == 8'h11,
            "LP dropout leaves only the debounced small-ADC latches");
      check(core.small_latch_clear_attempted &&
            !core.small_latch_rearm_pending,
            "low-power dropout without a large decrease cannot re-arm clear");
      force model.samp_lp1 = 1'b1;
      force model.samp_lp2 = 1'b1;
      for (wait_cycles = 0; wait_cycles < 2000 && !fault[3];
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
      end
      check(fault == 8'h08,
            "persistent conflict raises sticky illegal fault");
      check(cnt_trans == t0 + 8'd1 && expected_index == idx0 - 8'd1,
            "persistent conflict cannot ratchet below one clear step");
      check(m_rx1 == idx0 - 8'd1 && m_rx2 == idx0 - 8'd1 &&
            m_acc == accepted0 + 32'd1,
            "persistent conflict accepts exactly one physical paired pulse");
      check(cnt_clamp == clamp0,
            "non-minimum persistent conflict does not claim a clamp");
      tick(4);
      check(state == 3'd6 && fpga_owns && ctl_o == 4'd0 && ctl_t == 4'd0 &&
            !core.pulse_pending && !core.evt_push,
            "persistent fault reaches pulse-quiet owned FAULTED state");
      release model.samp_lp1;
      release model.samp_lp2;
      rx1_level = -16'sd60; rx2_level = -16'sd60;
      tick(8);
      check(fault[3], "persistent-conflict fault remains sticky after evidence clears");
      mode_req = 2'd0; armed = 1'b0; tick(8);
      l_resetn = 1'b0; tick(6); l_resetn = 1'b1; tick(8);
      cfg_cooldown = 8'd2;
      cfg_dwell = 8'd3;
    end

    // -- 17. a conflict at the configured minimum faults without a pulse ---
    begin : small_conflict_at_min
      integer wait_cycles;
      reg [7:0] t0, clamp0;
      reg [31:0] accepted0;

      cfg_idx_min = cfg_idx_init;
      rx1_level = -16'sd60; rx2_level = -16'sd60;
      enable_tandem(2'd2);
      rx1_level = -16'sd10 - $signed({8'd0, m_rx1});
      rx2_level = -16'sd10 - $signed({8'd0, m_rx2});
      settle(4);
      t0 = cnt_trans;
      clamp0 = cnt_clamp;
      accepted0 = m_acc;
      rx1_level = -16'sd120; rx2_level = -16'sd120;
      for (wait_cycles = 0; wait_cycles < 1000 && !fault[3];
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
      end
      check(fault == 8'h08,
            "minimum-index conflict raises only sticky illegal fault");
      check(cnt_trans == t0 && expected_index == cfg_idx_min &&
            m_acc == accepted0,
            "minimum-index conflict emits no pulse and cannot underflow");
      check(m_rx1 == cfg_idx_min && m_rx2 == cfg_idx_min,
            "minimum-index conflict leaves the physical gain pair unchanged");
      check(cnt_clamp == clamp0 + 8'd1,
            "minimum-index conflict increments the clamp diagnostic once");
      tick(4);
      check(state == 3'd6 && fpga_owns && ctl_o == 4'd0 && ctl_t == 4'd0 &&
            !core.pulse_pending && !core.evt_push,
            "minimum conflict reaches pulse-quiet owned FAULTED state");
      mode_req = 2'd0; armed = 1'b0; tick(8);
      cfg_idx_min = 8'd0;
      l_resetn = 1'b0; tick(6); l_resetn = 1'b1; tick(8);
    end

    // -- 18. a true large overload retains strict priority -----------------
    begin : large_overload_priority
      integer wait_cycles;
      reg saw_event;

      rx1_level = -16'sd60; rx2_level = -16'sd60;
      enable_tandem(2'd2);
      saw_event = 1'b0;
      force model.samp_lp1 = 1'b1;
      force model.samp_lp2 = 1'b1;
      rx1_level = -16'sd20; rx2_level = -16'sd20;
      for (wait_cycles = 0; wait_cycles < 1000 && !saw_event;
           wait_cycles = wait_cycles + 1) begin
        @(posedge l_clk); #1;
        if (core.evt_push) begin
          saw_event = 1'b1;
          check((core.evt_reason == 4'd0 || core.evt_reason == 4'd1) &&
                core.req_dir == 2'd2,
                "large overload outranks contradictory low-power evidence");
        end
      end
      check(saw_event, "large-overload priority still produces a decrease");
      release model.samp_lp1;
      release model.samp_lp2;
      disable_tandem;
    end

    // -- 19. shared dwell timer never carries credit across evidence kinds --
    // The implementation shares one counter between three mutually-exclusive
    // proofs to save area.  Exercise direct kind changes on a power tick so a
    // nearly mature ordinary/re-arm dwell can never shorten the safety dwell
    // for a newly observed stale-latch conflict.
    begin : shared_dwell_kind_transitions
      reg [7:0] forced_det;
      reg [7:0] t0;

      cfg_cooldown = 8'd0;
      cfg_dwell = 8'd3;
      rx1_level = -16'sd60; rx2_level = -16'sd60;
      enable_tandem(2'd2);
      wait (!core.blanked && !cooldown_active && !core.pulse_pending);

      // Nearly mature ordinary both-low evidence must be discarded when a
      // small-ADC latch appears in the same power-measurement cycle.
      forced_det = 8'h88;
      force core.det_stable = forced_det;
      force core.pwr_tick = 1'b1;
      while (!(core.dwell_kind == 2'd1 &&
               core.dwell_cnt == cfg_dwell - 8'd1)) begin
        @(posedge l_clk); #1;
      end
      t0 = cnt_trans;
      @(negedge l_clk); forced_det = 8'h99;
      @(posedge l_clk); #1;
      check(core.dwell_kind == 2'd2 && core.dwell_cnt == 8'd1 &&
            core.small_latch_dwell_cnt == 8'd1 && cnt_trans == t0 &&
            !core.evt_push && fault == 8'd0,
            "normal-to-conflict starts a fresh tagged dwell at one");
      @(posedge l_clk); #1;
      check(core.dwell_cnt == 8'd2 && cnt_trans == t0 && !core.evt_push,
            "normal credit cannot satisfy the second conflict tick");
      @(posedge l_clk); #1;
      check(core.dwell_cnt == cfg_dwell && cnt_trans == t0 && !core.evt_push,
            "normal credit cannot satisfy the full conflict dwell");
      @(posedge l_clk); #1;
      check(core.evt_push && core.evt_reason == 4'd2 &&
            cnt_trans == t0 + 8'd1,
            "fresh conflict dwell alone authorizes the conservative edge");

      release core.pwr_tick;
      release core.det_stable;
      mode_req = 2'd0; armed = 1'b0; tick(8);
      l_resetn = 1'b0; tick(6); l_resetn = 1'b1; tick(8);

      // The reverse boundary protects gain safety: stale-conflict history may
      // not authorize an immediate increase when the latch disappears.  Make
      // this switch between power ticks as an additional zero-seed boundary.
      rx1_level = -16'sd60; rx2_level = -16'sd60;
      enable_tandem(2'd2);
      wait (!core.blanked && !cooldown_active && !core.pulse_pending);
      forced_det = 8'h99;
      force core.det_stable = forced_det;
      force core.pwr_tick = 1'b1;
      while (!(core.dwell_kind == 2'd2 &&
               core.dwell_cnt == cfg_dwell - 8'd1)) begin
        @(posedge l_clk); #1;
      end
      t0 = cnt_trans;
      @(negedge l_clk);
      forced_det = 8'h88;
      release core.pwr_tick;
      force core.pwr_tick = 1'b0;
      @(posedge l_clk); #1;
      check(core.dwell_kind == 2'd1 && core.dwell_cnt == 8'd0 &&
            cnt_trans == t0 && !core.evt_push,
            "conflict-to-normal between ticks seeds no increase credit");
      @(negedge l_clk);
      release core.pwr_tick;
      force core.pwr_tick = 1'b1;
      @(posedge l_clk); #1;
      check(core.dwell_cnt == 8'd1 && cnt_trans == t0 && !core.evt_push,
            "first fresh normal tick cannot reuse conflict credit");
      @(posedge l_clk); #1;
      check(core.dwell_cnt == 8'd2 && cnt_trans == t0 && !core.evt_push,
            "second fresh normal tick cannot reuse conflict credit");
      @(posedge l_clk); #1;
      check(core.dwell_cnt == cfg_dwell && cnt_trans == t0 && !core.evt_push,
            "third fresh normal tick matures without an early increase");
      @(posedge l_clk); #1;
      check(core.evt_push && core.evt_reason == 4'd3 &&
            cnt_trans == t0 + 8'd1,
            "only a full fresh normal dwell authorizes the increase");

      release core.pwr_tick;
      release core.det_stable;
      mode_req = 2'd0; armed = 1'b0; tick(8);
      l_resetn = 1'b0; tick(6); l_resetn = 1'b1; tick(8);

      // A conflict can also disappear into the strong-signal evidence used to
      // re-arm a consumed clear.  Its prior count must not shorten that proof.
      rx1_level = -16'sd60; rx2_level = -16'sd60;
      enable_tandem(2'd2);
      wait (!core.blanked && !cooldown_active && !core.pulse_pending);
      forced_det = 8'h99;
      force core.det_stable = forced_det;
      force core.pwr_tick = 1'b1;
      force core.small_latch_clear_attempted = 1'b1;
      force core.small_latch_rearm_pending = 1'b1;
      while (!(core.dwell_kind == 2'd2 &&
               core.dwell_cnt == cfg_dwell - 8'd1)) begin
        @(posedge l_clk); #1;
      end
      t0 = cnt_trans;
      @(negedge l_clk); forced_det = 8'h00;
      @(posedge l_clk); #1;
      check(core.dwell_kind == 2'd3 && core.dwell_cnt == 8'd1 &&
            cnt_trans == t0 && fault == 8'd0 && !core.evt_push,
            "conflict-to-rearm starts a fresh tagged dwell at one");
      @(posedge l_clk); #1;
      check(core.dwell_cnt == 8'd2 && fault == 8'd0,
            "conflict credit cannot satisfy the second re-arm tick");
      @(posedge l_clk); #1;
      check(core.dwell_cnt == cfg_dwell && fault == 8'd0,
            "conflict credit cannot mature re-arm early");
      @(posedge l_clk); #1;
      check(core.dwell_kind == 2'd0 && core.dwell_cnt == 8'd0 &&
            cnt_trans == t0 && fault == 8'd0 && !core.evt_push,
            "re-arm completes only after its own full fresh dwell");

      release core.small_latch_clear_attempted;
      release core.small_latch_rearm_pending;
      release core.pwr_tick;
      release core.det_stable;
      mode_req = 2'd0; armed = 1'b0; tick(8);
      l_resetn = 1'b0; tick(6); l_resetn = 1'b1; tick(8);

      // Nearly mature re-arm evidence is particularly sensitive: carrying it
      // into a conflict would make a consumed clear fault too early.  Hold the
      // episode tokens only to isolate this counter-class boundary.
      rx1_level = -16'sd60; rx2_level = -16'sd60;
      enable_tandem(2'd2);
      wait (!core.blanked && !cooldown_active && !core.pulse_pending);
      forced_det = 8'h00;
      force core.det_stable = forced_det;
      force core.pwr_tick = 1'b1;
      force core.small_latch_clear_attempted = 1'b1;
      force core.small_latch_rearm_pending = 1'b1;
      while (!(core.dwell_kind == 2'd3 &&
               core.dwell_cnt == cfg_dwell - 8'd1)) begin
        @(posedge l_clk); #1;
      end
      t0 = cnt_trans;
      @(negedge l_clk); forced_det = 8'h99;
      @(posedge l_clk); #1;
      check(core.dwell_kind == 2'd2 && core.dwell_cnt == 8'd1 &&
            cnt_trans == t0 && fault == 8'd0 && !core.evt_push,
            "rearm-to-conflict starts a fresh tagged dwell at one");
      @(posedge l_clk); #1;
      check(core.dwell_cnt == 8'd2 && fault == 8'd0,
            "re-arm credit cannot satisfy the second conflict tick");
      @(posedge l_clk); #1;
      check(core.dwell_cnt == cfg_dwell && fault == 8'd0,
            "re-arm credit cannot mature the conflict early");
      @(posedge l_clk); #1;
      check(fault == 8'h08 && cnt_trans == t0 && !core.evt_push,
            "consumed conflict faults only after its own full fresh dwell");

      release core.small_latch_clear_attempted;
      release core.small_latch_rearm_pending;
      release core.pwr_tick;
      release core.det_stable;
      mode_req = 2'd0; armed = 1'b0; tick(8);
      l_resetn = 1'b0; tick(6); l_resetn = 1'b1; tick(8);
      cfg_cooldown = 8'd2;
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
