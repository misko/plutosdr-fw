// -----------------------------------------------------------------------------
// tandem_agc_core.v
//
// Tandem AGC controller. Steps the AD9361 RX1 and RX2 manual gain indices
// together, keeping both receivers at one common index, deciding from the
// AD9361's own detectors on CTRL_OUT page 0x03.
//
// Implements TANDEM_AGC_V1_DESIGN.md revision 3. Section references below are
// to that document. Clock domain is l_clk per D-1.
//
// One deliberate refinement of §11: the FPGA takes pin ownership on entry to
// ARMING and immediately drives all four low, rather than at a later step. The
// PS-to-FPGA handover edge therefore happens while AD9361 pin control is still
// disarmed, so it cannot be interpreted as a gain command. Software still arms
// 0x0FB only after the armed acknowledgement, exactly as §11 requires.
// -----------------------------------------------------------------------------

`timescale 1ns/1ps

module tandem_agc_core #(
  parameter integer EVT_AW = 6,      // 64 entries; §7.3 worst case is ~18/frame
  parameter integer EVT_DW = 104,   // record layout, §7.1, exact width
  // EVENTS=0 compiles out the whole event-capture path: FIFO, sequence counter,
  // record registers and overflow tracking. Tandem gain control itself does not
  // depend on any of it, so this is the lever that trades the exact per-sample
  // gain series for area when the device cannot hold both.
  parameter integer EVENTS = 1
) (
  input  wire             l_clk,
  input  wire             l_resetn,

  // ---- detectors, CTRL_OUT page 0x03, asynchronous ------------------------
  input  wire [7:0]       detect_async,

  // ---- receive-domain sample counter, §7.1 [63:0] -------------------------
  input  wire [63:0]      sample_counter,

  // ---- control ------------------------------------------------------------
  input  wire [1:0]       mode_req,        // 0 legacy, 1 hold, 2 auto
  input  wire             fault_clear,
  input  wire             consumer_ready,  // §2.3 readiness before release

  // ---- configuration ------------------------------------------------------
  input  wire [7:0]       cfg_pulse_hi,
  input  wire [7:0]       cfg_pulse_lo,
  input  wire [15:0]      cfg_blank_guard,
  input  wire [19:0]      cfg_pwr_period,
  input  wire [7:0]       cfg_cooldown,    // in power-measurement periods, D-10
  input  wire [7:0]       cfg_dwell,       // in power-measurement periods
  input  wire [7:0]       cfg_debounce,
  input  wire [7:0]       cfg_idx_min,
  input  wire [7:0]       cfg_idx_max,
  input  wire [7:0]       cfg_idx_init,

  // ---- software index readback for the §6.2 quiescence rule ---------------
  input  wire [7:0]       sw_idx_rx1,
  input  wire [7:0]       sw_idx_rx2,
  input  wire             sw_idx_strobe,   // asserted for one cycle per readback

  // ---- legacy PS path, EMIO [11:8] ----------------------------------------
  input  wire [3:0]       ps_ctl_o,
  input  wire [3:0]       ps_ctl_t,

  // ---- to the ad_iobuf ----------------------------------------------------
  output wire [3:0]       ctl_o,
  output wire [3:0]       ctl_t,

  // ---- status -------------------------------------------------------------
  output wire [2:0]       state_o,
  output wire [7:0]       epoch_o,
  output wire [7:0]       epoch_tomb_o,
  output wire [7:0]       expected_index_o,
  output wire             pulse_busy_o,
  output wire             cooldown_active_o,
  output wire             fpga_owns_o,
  output wire [7:0]       fault_o,
  output wire [7:0]       detect_o,
  output wire [7:0]       cnt_trans_o,
  output wire [7:0]       cnt_inhib_o,
  output wire [7:0]       cnt_clamp_o,
  output wire [7:0]       cnt_stale_o,

  // ---- event FIFO. The read side may be in another clock domain (§9); tie
  //      evt_rd_clk to l_clk for a single-clock instantiation.
  input  wire              evt_rd_clk,
  input  wire              evt_rd_resetn,
  output wire [EVT_DW-1:0] evt_rdata_o,
  output wire              evt_valid_o,
  input  wire              evt_pop,
  output wire [EVT_AW:0]   evt_level_o,
  output wire [31:0]       evt_ovf_o,
  output wire              evt_push_o,
  output wire [EVT_DW-1:0] evt_wdata_o
);

  // ---------------------------------------------------------------------------
  // lifecycle, §2.2
  // ---------------------------------------------------------------------------
  localparam ST_LEGACY     = 3'd0;
  localparam ST_ARMING     = 3'd1;
  localparam ST_OWNED_IDLE = 3'd2;
  localparam ST_ACTIVE     = 3'd3;
  localparam ST_DISARMING  = 3'd4;
  localparam ST_RELEASABLE = 3'd5;
  localparam ST_FAULTED    = 3'd6;

  // fault bits, §8 FAULT register
  localparam F_FIFO_OVF   = 0;
  localparam F_IDX_MISMTCH= 1;
  localparam F_NO_CONSUMER= 2;
  localparam F_ILLEGAL    = 3;

  // reason codes, §7.2
  localparam R_LG_LMT   = 4'd0;
  localparam R_LG_ADC   = 4'd1;
  localparam R_SM_INHIB = 4'd2;
  localparam R_BOTH_LP  = 4'd3;
  localparam R_PEER     = 4'd4;
  localparam R_CLAMPED  = 4'd5;
  localparam R_INIT     = 4'd6;

  reg [2:0] state;
  reg [7:0] epoch, epoch_tomb;
  reg [7:0] fault;

  // ---------------------------------------------------------------------------
  // detector conditioning, §5.1: source register, 2-flop sync, debounce
  // ---------------------------------------------------------------------------
  reg [7:0] det_src, det_s1, det_s2, det_stable;
  reg [7:0] det_h1, det_h2;      // agreement history, one shared control set
  reg [7:0] deb_div;
  wire      deb_tick = (deb_div >= cfg_debounce);

  always @(posedge l_clk) begin
    if (!l_resetn) begin
      det_src <= 8'd0; det_s1 <= 8'd0; det_s2 <= 8'd0; det_stable <= 8'd0;
      det_h1 <= 8'd0; det_h2 <= 8'd0; deb_div <= 8'd0;
    end else begin
      det_src <= detect_async;     // source-registered before the synchroniser
      det_s1  <= det_src;
      det_s2  <= det_s1;
      deb_div <= deb_tick ? 8'd0 : deb_div + 8'd1;
      if (deb_tick) begin
        det_h1 <= det_s2;
        det_h2 <= det_h1;
        // a bit only moves after three consecutive agreeing samples
        det_stable <= (det_s2 & det_h1 & det_h2)
                    | (det_stable & ~(~det_s2 & ~det_h1 & ~det_h2));
      end
    end
  end

  // page 0x03 map, §3
  wire ch1_lp    = det_stable[7];
  wire ch1_lglmt = det_stable[6];
  wire ch1_lgadc = det_stable[5];
  wire ch1_smadc = det_stable[4];
  wire ch2_lp    = det_stable[3];
  wire ch2_lglmt = det_stable[2];
  wire ch2_lgadc = det_stable[1];
  wire ch2_smadc = det_stable[0];

  // ---------------------------------------------------------------------------
  // power-measurement tick, D-10
  // ---------------------------------------------------------------------------
  reg [19:0] pwr_div;
  reg        pwr_tick;
  always @(posedge l_clk) begin
    if (!l_resetn) begin
      pwr_div <= 20'd0; pwr_tick <= 1'b0;
    end else if (pwr_div >= cfg_pwr_period) begin
      pwr_div <= 20'd0; pwr_tick <= 1'b1;
    end else begin
      pwr_div <= pwr_div + 20'd1; pwr_tick <= 1'b0;
    end
  end

  // ---------------------------------------------------------------------------
  // pulse generator, D-2. Floor of 4 enforced in RTL.
  // ---------------------------------------------------------------------------
  wire [7:0] pulse_hi_eff = (cfg_pulse_hi < 8'd4) ? 8'd4 : cfg_pulse_hi;
  wire [7:0] pulse_lo_eff = (cfg_pulse_lo < 8'd4) ? 8'd4 : cfg_pulse_lo;

  reg [7:0] pulse_cnt;
  reg [3:0] pulse_out;
  reg       pulse_busy, pulse_phase;
  reg [1:0] fire_dir;              // latched direction for the pulse in flight
  reg       fire_req;
  reg [1:0] req_dir;

  always @(posedge l_clk) begin
    if (!l_resetn) begin
      pulse_cnt <= 8'd0; pulse_out <= 4'd0;
      pulse_busy <= 1'b0; pulse_phase <= 1'b0; fire_dir <= 2'd0;
    end else if (pulse_busy) begin
      if (pulse_cnt > 8'd1) begin
        pulse_cnt <= pulse_cnt - 8'd1;
      end else if (!pulse_phase) begin
        pulse_out   <= 4'd0;
        pulse_phase <= 1'b1;
        pulse_cnt   <= pulse_lo_eff;
      end else begin
        pulse_busy  <= 1'b0;
        pulse_phase <= 1'b0;
        fire_dir    <= 2'd0;
      end
    end else if (fire_req) begin
      // A-2: both channels driven identically, in the same cycle
      pulse_out  <= (req_dir == 2'd1) ? 4'b0101 : 4'b1010;
      pulse_cnt  <= pulse_hi_eff;
      pulse_busy <= 1'b1;
      fire_dir   <= req_dir;
    end
  end

  // ---------------------------------------------------------------------------
  // blanking guard, §5.2: detectors are NOT evaluated inside it
  // ---------------------------------------------------------------------------
  reg [15:0] blank_cnt;
  wire       blanked = (blank_cnt != 16'd0);
  always @(posedge l_clk) begin
    if (!l_resetn)          blank_cnt <= 16'd0;
    else if (pulse_busy)    blank_cnt <= cfg_blank_guard;
    else if (blanked)       blank_cnt <= blank_cnt - 16'd1;
  end

  // ---------------------------------------------------------------------------
  // policy, §5.3. Strict priority DECREASE > INHIBIT > INCREASE > HOLD.
  // Small LMT is deliberately absent -- it is on no CTRL_OUT page (§3).
  // ---------------------------------------------------------------------------
  wire want_decrease = ch1_lglmt | ch1_lgadc | ch2_lglmt | ch2_lgadc;
  wire inhibit       = ch1_smadc | ch2_smadc;
  wire both_lp       = ch1_lp & ch2_lp;
  wire one_lp        = ch1_lp ^ ch2_lp;

  reg [7:0] cooldown_cnt, dwell_cnt;
  wire cooldown_active = (cooldown_cnt != 8'd0);

  reg [7:0]  expected_index;
  wire at_min = (expected_index <= cfg_idx_min);
  wire at_max = (expected_index >= cfg_idx_max);

  // 16 bits is ample for diagnostics and halves the flip-flops these cost
  // both here and in the status crossing.
  reg [7:0] cnt_trans, cnt_inhib, cnt_clamp, cnt_stale;
  reg [15:0] evt_seq;
  reg [3:0]  evt_reason;
  reg        evt_push;

  wire may_decide = (state == ST_ACTIVE) && !blanked && !cooldown_active
                    && !pulse_busy && (fault == 8'd0);

  always @(posedge l_clk) begin
    if (!l_resetn) begin
      expected_index <= 8'd0; cooldown_cnt <= 8'd0; dwell_cnt <= 8'd0;
      cnt_trans <= 8'd0; cnt_inhib <= 8'd0; cnt_clamp <= 8'd0;
      evt_seq <= 16'd0; evt_reason <= 4'd0; evt_push <= 1'b0;
      fire_req <= 1'b0; req_dir <= 2'd0;
    end else begin
      evt_push <= 1'b0;
      fire_req <= 1'b0;

      // seed the model when ownership is taken
      if (state == ST_ARMING) begin
        expected_index <= cfg_idx_init;
        dwell_cnt      <= 8'd0;
        cooldown_cnt   <= 8'd0;
      end

      // dwell and cooldown advance on the power-measurement tick, D-10
      if (pwr_tick) begin
        if (cooldown_cnt != 8'd0) cooldown_cnt <= cooldown_cnt - 8'd1;
        if (both_lp && !inhibit)
          dwell_cnt <= (dwell_cnt == 8'hFF) ? dwell_cnt : dwell_cnt + 8'd1;
        else
          dwell_cnt <= 8'd0;
      end

      if (may_decide) begin
        if (want_decrease) begin
          if (at_min) begin
            cnt_clamp <= (cnt_clamp == 8'hFF) ? cnt_clamp : cnt_clamp + 8'd1;      // report, never spin
          end else begin
            req_dir        <= 2'd2;
            fire_req       <= 1'b1;
            expected_index <= expected_index - 8'd1;
            evt_reason     <= (ch1_lglmt | ch2_lglmt) ? R_LG_LMT : R_LG_ADC;
            evt_push       <= 1'b1;
            evt_seq        <= evt_seq + 16'd1;
            cnt_trans      <= cnt_trans + 32'd1;
            cooldown_cnt   <= cfg_cooldown;
            dwell_cnt      <= 8'd0;
          end
        end else if (inhibit) begin
          if (both_lp) cnt_inhib <= (cnt_inhib == 8'hFF) ? cnt_inhib : cnt_inhib + 8'd1;
        end else if (both_lp && (dwell_cnt >= cfg_dwell)) begin
          if (at_max) begin
            cnt_clamp <= (cnt_clamp == 8'hFF) ? cnt_clamp : cnt_clamp + 8'd1;
          end else begin
            req_dir        <= 2'd1;
            fire_req       <= 1'b1;
            expected_index <= expected_index + 8'd1;
            evt_reason     <= R_BOTH_LP;
            evt_push       <= 1'b1;
            evt_seq        <= evt_seq + 16'd1;
            cnt_trans      <= cnt_trans + 32'd1;
            cooldown_cnt   <= cfg_cooldown;
            dwell_cnt      <= 8'd0;
          end
        end else if (one_lp) begin
          cnt_inhib <= (cnt_inhib == 8'hFF) ? cnt_inhib : cnt_inhib + 8'd1;        // starvation case, §5.4
        end
      end
    end
  end

  // ---------------------------------------------------------------------------
  // synchronisation check, §6.2 quiescence rule
  // ---------------------------------------------------------------------------
  reg mismatch_seen;
  wire quiescent = !pulse_busy && !cooldown_active;
  always @(posedge l_clk) begin
    if (!l_resetn) begin
      mismatch_seen <= 1'b0; cnt_stale <= 8'd0;
    end else if (sw_idx_strobe) begin
      if (state == ST_ACTIVE || state == ST_OWNED_IDLE) begin
        if (quiescent &&
            ((sw_idx_rx1 != expected_index) || (sw_idx_rx2 != expected_index))) begin
          // two consecutive disagreeing quiescent reads are required
          mismatch_seen <= 1'b1;
        end else begin
          mismatch_seen <= 1'b0;
        end
      end
    end
  end

  // ---------------------------------------------------------------------------
  // event FIFO, D-9. Uses the CDC library's gray-coded asynchronous FIFO so the
  // write side stays in l_clk while software reads from the processor domain.
  // ---------------------------------------------------------------------------
  wire [EVT_DW-1:0] evt_wdata = {
      evt_seq, epoch, 2'd0, req_dir, evt_reason, expected_index, sample_counter };

  wire fifo_full;
  generate if (EVENTS) begin : g_events
    tandem_async_fifo #(.W(EVT_DW), .AW(EVT_AW)) u_evt_fifo (
      .wr_clk(l_clk), .wr_resetn(l_resetn), .wr_en(evt_push), .wr_data(evt_wdata),
      .wr_full(fifo_full), .wr_ovf(evt_ovf_o),
      .rd_clk(evt_rd_clk), .rd_resetn(evt_rd_resetn), .rd_en(evt_pop),
      .rd_data(evt_rdata_o), .rd_valid(evt_valid_o), .rd_level(evt_level_o));
  end else begin : g_no_events
    assign fifo_full    = 1'b0;
    assign evt_ovf_o    = 32'd0;
    assign evt_rdata_o  = {EVT_DW{1'b0}};
    assign evt_valid_o  = 1'b0;
    assign evt_level_o  = {(EVT_AW+1){1'b0}};
  end endgenerate

  assign evt_push_o  = evt_push;
  assign evt_wdata_o = evt_wdata;

  // ---------------------------------------------------------------------------
  // faults, sticky
  // ---------------------------------------------------------------------------
  always @(posedge l_clk) begin
    if (!l_resetn) fault <= 8'd0;
    else begin
      if (fault_clear && state == ST_FAULTED) fault <= 8'd0;
      if (evt_push && fifo_full)              fault[F_FIFO_OVF]    <= 1'b1;
      if (mismatch_seen && sw_idx_strobe && quiescent &&
          ((sw_idx_rx1 != expected_index) || (sw_idx_rx2 != expected_index)))
                                              fault[F_IDX_MISMTCH] <= 1'b1;
      if (state == ST_ARMING && !consumer_ready) fault[F_NO_CONSUMER] <= 1'b1;
    end
  end

  // ---------------------------------------------------------------------------
  // lifecycle FSM, §2.2/§2.3
  // ---------------------------------------------------------------------------
  always @(posedge l_clk) begin
    if (!l_resetn) begin
      state <= ST_LEGACY; epoch <= 8'd1; epoch_tomb <= 8'd0;
    end else begin
      case (state)
        ST_LEGACY:
          if (mode_req != 2'd0) begin
            state <= ST_ARMING;
            epoch <= (epoch == 8'hFF) ? 8'd1 : epoch + 8'd1;   // never zero
          end
        ST_ARMING:
          if (fault != 8'd0)            state <= ST_DISARMING;
          else if (consumer_ready)      state <= ST_OWNED_IDLE;
        ST_OWNED_IDLE:
          if (fault != 8'd0)            state <= ST_DISARMING;
          else if (mode_req == 2'd0)    state <= ST_DISARMING;
          else if (mode_req == 2'd2)    state <= ST_ACTIVE;
        ST_ACTIVE:
          if (fault != 8'd0)            state <= ST_DISARMING;
          else if (mode_req != 2'd2)    state <= ST_DISARMING;
        ST_DISARMING:
          if (!pulse_busy)              state <= ST_RELEASABLE;
        ST_RELEASABLE: begin
          epoch_tomb <= epoch;
          state <= (fault != 8'd0) ? ST_FAULTED : ST_LEGACY;
        end
        ST_FAULTED:
          if (fault_clear)              state <= ST_LEGACY;
        default:                        state <= ST_LEGACY;
      endcase
    end
  end

  // ---------------------------------------------------------------------------
  // ownership mux, §4: owns BOTH value and tri-state, registered, reset=legacy
  // ---------------------------------------------------------------------------
  wire fpga_owns = (state == ST_ARMING) || (state == ST_OWNED_IDLE) ||
                   (state == ST_ACTIVE) || (state == ST_DISARMING);

  reg [3:0] ctl_o_r, ctl_t_r;
  always @(posedge l_clk) begin
    if (!l_resetn) begin
      ctl_o_r <= 4'd0; ctl_t_r <= 4'hF;        // legacy: high-Z
    end else if (fpga_owns) begin
      ctl_o_r <= pulse_out;
      ctl_t_r <= 4'd0;
    end else begin
      ctl_o_r <= ps_ctl_o;
      ctl_t_r <= ps_ctl_t;
    end
  end

  assign ctl_o = ctl_o_r;
  assign ctl_t = ctl_t_r;

  // ---------------------------------------------------------------------------
  assign state_o           = state;
  assign epoch_o           = epoch;
  assign epoch_tomb_o      = epoch_tomb;
  assign expected_index_o  = expected_index;
  assign pulse_busy_o      = pulse_busy;
  assign cooldown_active_o = cooldown_active;
  assign fpga_owns_o       = fpga_owns;
  assign fault_o           = fault;
  assign detect_o          = det_stable;
  assign cnt_trans_o       = cnt_trans;
  assign cnt_inhib_o       = cnt_inhib;
  assign cnt_clamp_o       = cnt_clamp;
  assign cnt_stale_o       = cnt_stale;

endmodule
