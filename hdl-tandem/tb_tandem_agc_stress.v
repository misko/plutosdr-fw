// -----------------------------------------------------------------------------
// tb_tandem_agc_stress.v
//
// The tandem_agc_plan.md §8.2 cases the first testbench did not reach:
// randomised detector traffic, reset in every lifecycle state, enable and
// disable at every pulse phase, chattering inputs, long idle intervals, FIFO
// overflow, sequence rollover, and the software/FPGA index-mismatch fault.
//
// The twelve §10 assertions run throughout, so every scenario here is also an
// assertion soak, not just a functional check.
// -----------------------------------------------------------------------------

`timescale 1ns/1ps

module tb_tandem_agc_stress;

  reg l_clk = 1'b0, l_resetn = 1'b0;
  always #5 l_clk = ~l_clk;

  reg [7:0]  cfg_pulse_hi = 8'd4, cfg_pulse_lo = 8'd4;
  reg [15:0] cfg_blank_guard = 16'd8;
  reg [19:0] cfg_pwr_period = 20'd12;
  reg [7:0]  cfg_cooldown = 8'd2, cfg_dwell = 8'd2, cfg_debounce = 8'd1;
  reg [7:0]  cfg_idx_min = 8'd0, cfg_idx_max = 8'd76, cfg_idx_init = 8'd40;

  reg [1:0]  mode_req = 2'd0;
  reg        fault_clear = 1'b0, consumer_ready = 1'b1;
  reg [3:0]  ps_ctl_o = 4'd0, ps_ctl_t = 4'hF;
  reg [7:0]  sw_idx_rx1 = 8'd0, sw_idx_rx2 = 8'd0;
  reg        sw_idx_strobe = 1'b0;
  reg        evt_pop = 1'b0;
  reg [63:0] sample_counter = 64'd0;
  always @(posedge l_clk) sample_counter <= sample_counter + 64'd1;

  reg signed [15:0] rx1_level = -16'sd60, rx2_level = -16'sd60;
  reg armed = 1'b0, ensm_rx = 1'b1;

  wire [3:0] ctl_o, ctl_t;
  wire [7:0] detect;
  wire [2:0] state;
  wire [7:0] epoch, epoch_tomb, expected_index, fault, det_stable;
  wire       pulse_busy, cooldown_active, fpga_owns;
  wire [7:0]  cnt_trans, cnt_inhib, cnt_clamp, cnt_stale;
  wire [103:0] evt_rdata;
  wire       evt_valid;
  wire [6:0] evt_level;
  wire [31:0] evt_ovf;
  wire [7:0] m_rx1, m_rx2;
  wire [31:0] m_acc, m_rej, m_ign;

  integer errors = 0;
  integer seed = 32'd20260811;

  tandem_agc_core core (
    .l_clk(l_clk), .l_resetn(l_resetn),
    .detect_async(detect), .sample_counter(sample_counter),
    .mode_req(mode_req), .fault_clear(fault_clear), .consumer_ready(consumer_ready),
    .cfg_pulse_hi(cfg_pulse_hi), .cfg_pulse_lo(cfg_pulse_lo),
    .cfg_blank_guard(cfg_blank_guard), .cfg_pwr_period(cfg_pwr_period),
    .cfg_cooldown(cfg_cooldown), .cfg_dwell(cfg_dwell), .cfg_debounce(cfg_debounce),
    .cfg_idx_min(cfg_idx_min), .cfg_idx_max(cfg_idx_max), .cfg_idx_init(cfg_idx_init),
    .sw_idx_rx1(sw_idx_rx1), .sw_idx_rx2(sw_idx_rx2), .sw_idx_strobe(sw_idx_strobe),
    .ps_ctl_o(ps_ctl_o), .ps_ctl_t(ps_ctl_t), .ctl_o(ctl_o), .ctl_t(ctl_t),
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
    .clkrf(l_clk), .resetn(l_resetn), .ctrl_in(ctl_o), .ctrl_out(detect),
    .pin_ctrl_armed(armed), .ensm_rx_active(ensm_rx),
    .inc_step(4'd1), .dec_step(4'd1), .pwot(5'd3), .idx_max(8'd76),
    .rx1_level(rx1_level), .rx2_level(rx2_level),
    .th_lg_lmt(-16'sd5), .th_lg_adc(-16'sd8), .th_sm_adc(-16'sd14),
    .th_low_pwr(-16'sd30), .pwr_period(16'd12), .drop_next_pulse(1'b0),
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
    .expected_index(expected_index), .step_size(8'd1), .policing(state == 3'd3),
    .evt_push(core.evt_push), .evt_wdata(core.evt_wdata), .epoch(epoch),
    .a_err(a_err));

  task tick(input integer n); integer i;
    begin for (i=0;i<n;i=i+1) @(posedge l_clk); end endtask

  task check(input cond, input [511:0] name);
    begin if (!cond) begin $display("FAIL: %0s", name); errors=errors+1; end
          else $display("  ok  %0s", name); end endtask

  task go(input [1:0] m);
    begin
      model.rx1_index = cfg_idx_init; model.rx2_index = cfg_idx_init;
      mode_req = m; tick(4); wait (fpga_owns); tick(2); armed = 1'b1; tick(4);
    end
  endtask

  task stop;
    begin mode_req = 2'd0; tick(2); armed = 1'b0; wait (!fpga_owns); tick(4); end
  endtask

  integer k, n_pops;
  reg [31:0] v0, ae0;
  reg ok;

  initial begin
    $display("== tb_tandem_agc_stress ==");
    tick(4); l_resetn = 1'b1; tick(8);

    // -- 1. randomised detector traffic; assertions must survive it ---------
    begin : randomised
      ae0 = a_err;
      go(2'd2);
      for (k = 0; k < 400; k = k + 1) begin
        rx1_level = -($random(seed) % 70) - 16'sd20;
        rx2_level = -($random(seed) % 70) - 16'sd20;
        tick(($random(seed) % 40) + 5);
        // drain sometimes, so the FIFO is exercised both ways
        if (($random(seed) % 4) == 0 && evt_valid) begin
          @(posedge l_clk); evt_pop = 1'b1; @(posedge l_clk); evt_pop = 1'b0;
        end
      end
      check(a_err == ae0, "400 randomised detector rounds raise no assertion");
      check(m_rx1 == m_rx2, "channels remain equal after randomised traffic");
      stop;
    end

    // -- 2. chattering detectors must not chatter the gain ------------------
    begin : chatter
      reg [31:0] t0;
      ae0 = a_err;
      go(2'd2);
      rx1_level = -16'sd60; rx2_level = -16'sd60;
      tick(200);
      t0 = cnt_trans;
      for (k = 0; k < 300; k = k + 1) begin
        rx1_level = (k[0]) ? -16'sd25 : -16'sd95;   // slam between extremes
        rx2_level = (k[0]) ? -16'sd25 : -16'sd95;
        tick(3);                                     // far faster than a period
      end
      check(a_err == ae0, "chattering inputs raise no assertion");
      check(cnt_trans - t0 < 8'd80,
            "dwell and cooldown bound the transition rate under chatter");
      stop;
    end

    // -- 3. long idle: no spurious transitions with a steady mid-band signal
    begin : idle
      reg [31:0] t0;
      go(2'd2);
      rx1_level = -16'sd62; rx2_level = -16'sd62;    // in the hold band
      tick(400);
      t0 = cnt_trans;
      tick(3000);
      check(cnt_trans == t0, "a long idle interval produces no transitions");
      stop;
    end

    // -- 4. reset asserted in EVERY lifecycle state -------------------------
    begin : reset_states
      ok = 1'b1;
      for (k = 0; k < 5; k = k + 1) begin
        mode_req = 2'd0; tick(4);
        model.rx1_index = cfg_idx_init; model.rx2_index = cfg_idx_init;
        case (k)
          0: begin mode_req = 2'd0; end                       // LEGACY
          1: begin consumer_ready = 1'b0; mode_req = 2'd1; tick(2); end // ARMING
          2: begin consumer_ready = 1'b1; mode_req = 2'd1; tick(20); end // OWNED_IDLE
          3: begin consumer_ready = 1'b1; mode_req = 2'd2; tick(20);
                   rx1_level = -16'sd25; rx2_level = -16'sd25; tick(20); end // ACTIVE
          4: begin mode_req = 2'd2; tick(20); mode_req = 2'd0; end // DISARMING
        endcase
        armed = 1'b1;
        l_resetn = 1'b0; armed = 1'b0; mode_req = 2'd0; tick(6);
        l_resetn = 1'b1; tick(8);
        if (state != 3'd0 || fpga_owns !== 1'b0 || ctl_t !== 4'hF) ok = 1'b0;
        consumer_ready = 1'b1;
        fault_clear = 1'b1; tick(2); fault_clear = 1'b0; tick(4);
      end
      check(ok, "reset from every lifecycle state lands in safe LEGACY/high-Z");
    end

    // -- 5. disable at every pulse phase ------------------------------------
    begin : disable_phases
      ae0 = a_err;
      ok = 1'b1;
      for (k = 0; k < 10; k = k + 1) begin
        go(2'd2);
        rx1_level = -16'sd25; rx2_level = -16'sd25;
        tick(60 + k);                       // land at a different pulse phase
        mode_req = 2'd0;                    // request disable mid-pulse
        tick(2); armed = 1'b0;
        wait (!fpga_owns); tick(6);
        if (state != 3'd0 || ctl_o !== 4'd0) ok = 1'b0;
        rx1_level = -16'sd60; rx2_level = -16'sd60; tick(20);
      end
      check(ok, "disable at ten different pulse phases always lands clean");
      check(a_err == ae0, "no assertion fires across the disable sweep");
    end

    // -- 6. FIFO overflow must be sticky and reported, never silent ---------
    begin : overflow
      cfg_pwr_period = 20'd4; cfg_cooldown = 8'd1; cfg_dwell = 8'd1;
      go(2'd2);
      evt_pop = 1'b0;                       // never drain
      for (k = 0; k < 2000; k = k + 1) begin
        rx1_level = (k[0]) ? -16'sd25 : -16'sd95;
        rx2_level = (k[0]) ? -16'sd25 : -16'sd95;
        tick(12);
        if (evt_ovf != 32'd0) k = 2000;     // stop as soon as it overflows
      end
      check(evt_ovf > 32'd0,      "FIFO overflow is counted");
      check(fault[0] == 1'b1,     "FIFO overflow sets a sticky fault");
      check(evt_level == (1 << core.EVT_AW),
            "the FIFO is full at its configured depth");
      stop;
      fault_clear = 1'b1; tick(4); fault_clear = 1'b0; tick(10);
      check(fault == 8'd0, "fault_clear clears the sticky fault");
      cfg_pwr_period = 20'd12; cfg_cooldown = 8'd2; cfg_dwell = 8'd2;
      // drain it out so later cases start clean
      while (evt_valid) begin
        @(posedge l_clk); evt_pop = 1'b1; @(posedge l_clk); evt_pop = 1'b0;
      end
    end

    // -- 7. event sequence rollover ----------------------------------------
    begin : seq_rollover
      reg [15:0] s_before;
      ae0 = a_err;
      go(2'd2);
      // Teleport the counter close to the wrap. This is an artificial jump, not
      // a wrap, so the checker's history is void across it -- re-baseline, or it
      // would (correctly) flag the jump itself as non-monotonic.
      core.evt_seq = 16'hFFFE;
      chk.seq_seen = 1'b0;
      s_before = core.evt_seq;
      rx1_level = -16'sd25; rx2_level = -16'sd25;
      tick(400);
      check(core.evt_seq < s_before, "the event sequence wraps rather than sticking");
      check(a_err == ae0, "sequence rollover raises no assertion");
      stop;
      while (evt_valid) begin
        @(posedge l_clk); evt_pop = 1'b1; @(posedge l_clk); evt_pop = 1'b0;
      end
    end

    // -- 8. 64-bit sample-counter rollover (simulation-only, D-3) ----------
    begin : ctr_rollover
      ae0 = a_err;
      go(2'd2);
      sample_counter = 64'hFFFF_FFFF_FFFF_FFF0;
      rx1_level = -16'sd25; rx2_level = -16'sd25;
      tick(300);
      check(a_err == ae0, "64-bit counter rollover raises no assertion");
      stop;
    end

    // -- 9. software/FPGA index mismatch under the quiescence rule ---------
    begin : mismatch
      go(2'd2);
      rx1_level = -16'sd62; rx2_level = -16'sd62;   // hold band, so it is quiet
      tick(300);
      // agreeing readback must NOT fault
      sw_idx_rx1 = expected_index; sw_idx_rx2 = expected_index;
      @(posedge l_clk); sw_idx_strobe = 1'b1; @(posedge l_clk); sw_idx_strobe = 1'b0;
      tick(10);
      check(fault[1] == 1'b0, "an agreeing quiescent readback does not fault");
      // two consecutive disagreeing quiescent reads must fault
      sw_idx_rx1 = expected_index + 8'd9; sw_idx_rx2 = expected_index + 8'd9;
      @(posedge l_clk); sw_idx_strobe = 1'b1; @(posedge l_clk); sw_idx_strobe = 1'b0;
      tick(6);
      @(posedge l_clk); sw_idx_strobe = 1'b1; @(posedge l_clk); sw_idx_strobe = 1'b0;
      tick(10);
      check(fault[1] == 1'b1, "two disagreeing quiescent readbacks raise the sync fault");
      check(state != 3'd3,    "the sync fault takes the controller out of ACTIVE");
      mode_req = 2'd0; armed = 1'b0; tick(20);
      fault_clear = 1'b1; tick(4); fault_clear = 1'b0; tick(10);
    end

    $display("---- assertion failures: %0d ----", a_err);
    $display("---- scenario failures : %0d ----", errors);
    if (a_err != 0 || errors != 0)
      $fatal(1, "STRESS TESTS FAILED (assert=%0d scenario=%0d)", a_err, errors);
    $display("PASS: tb_tandem_agc_stress");
    $finish;
  end

  initial begin #200000000; $fatal(1, "tb_tandem_agc_stress timeout"); end

endmodule
