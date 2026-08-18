// -----------------------------------------------------------------------------
// ad9361_gain_model.v
//
// Behavioural model of the AD9361 manual-gain pin interface and the CTRL_OUT
// page 0x03 detectors, for testing the tandem AGC controller without hardware.
//
// Every behaviour here is either quoted from UG-570 Rev. A or measured on the
// part by experiment E-AGC1. Sources are given inline. Where the two disagree,
// the measurement wins.
//
//   * CTRL_IN0/1/2/3 = RX1 inc / RX1 dec / RX2 inc / RX2 dec   (E-AGC1 H1, 40/40)
//   * a pulse is detected only if its high AND low intervals are each at least
//     two ClkRF cycles                                          (UG-570 p.39)
//   * edges are IGNORED unless the ENSM is RX-active            (E-AGC1 H6)
//   * an edge moves the index by the programmed step            (E-AGC1 H2)
//   * overload outputs latch high until the gain changes, then are held in
//     reset until Peak Overload Wait Time expires               (UG-570 pp.75-76)
//   * the low-power flag is UNFILTERED in MGC and updates once per
//     power-measurement period                                  (UG-570 p.36)
//
// Signal levels are in dB relative to a notional full scale at gain index 0, so
// effective = level + index, since one full-table index is exactly 1 dB.
// -----------------------------------------------------------------------------

`timescale 1ns/1ps

module ad9361_gain_model #(
  parameter integer IDX_MAX_DEFAULT = 76
) (
  input  wire               clkrf,
  input  wire               resetn,

  // ---- pin interface -------------------------------------------------------
  input  wire [3:0]         ctrl_in,        // asynchronous, edge detected
  output reg  [7:0]         ctrl_out,       // page 0x03

  // ---- SPI-equivalent configuration ---------------------------------------
  input  wire               pin_ctrl_armed, // REG_AGC_CONFIG_2[1:0]
  input  wire               ensm_rx_active, // E-AGC1 H6
  input  wire [3:0]         inc_step,       // 1..8, REG_AGC_CONFIG_3[7:5]+1
  input  wire [3:0]         dec_step,       // 1..8, REG_PEAK_WAIT_TIME[7:5]+1
  input  wire [4:0]         pwot,           // REG_PEAK_WAIT_TIME[4:0], ClkRF
  input  wire [7:0]         idx_max,

  // ---- stimulus ------------------------------------------------------------
  input  wire signed [15:0] rx1_level,      // dB at index 0
  input  wire signed [15:0] rx2_level,
  input  wire signed [15:0] th_lg_lmt,
  input  wire signed [15:0] th_lg_adc,
  input  wire signed [15:0] th_sm_adc,
  input  wire signed [15:0] th_low_pwr,
  input  wire [15:0]        pwr_period,     // ClkRF cycles

  // ---- misbehaviour injection ---------------------------------------------
  input  wire               drop_next_pulse,

  // ---- observation ---------------------------------------------------------
  output reg  [7:0]         rx1_index,
  output reg  [7:0]         rx2_index,
  output reg  [31:0]        n_accepted,
  output reg  [31:0]        n_rejected_short,
  output reg  [31:0]        n_ignored_ensm
);

  // ---------------------------------------------------------------------------
  // pulse qualification: high and low each >= 2 ClkRF cycles (UG-570 p.39)
  // ---------------------------------------------------------------------------
  reg  [3:0] ci_d;
  reg  [7:0] hi_cnt  [0:3];
  reg  [7:0] lo_cnt  [0:3];
  reg  [3:0] lo_ok;               // the low interval before this pulse was legal
  reg  [3:0] event_pulse;         // one-cycle accept strobe per pin

  integer p;
  always @(posedge clkrf) begin
    if (!resetn) begin
      ci_d <= 4'd0; lo_ok <= 4'hF; event_pulse <= 4'd0;
      n_rejected_short <= 32'd0;
      for (p = 0; p < 4; p = p + 1) begin
        hi_cnt[p] <= 8'd0; lo_cnt[p] <= 8'hFF;
      end
    end else begin
      ci_d        <= ctrl_in;
      event_pulse <= 4'd0;
      for (p = 0; p < 4; p = p + 1) begin
        if (ctrl_in[p]) begin
          hi_cnt[p] <= (hi_cnt[p] == 8'hFF) ? hi_cnt[p] : hi_cnt[p] + 8'd1;
          if (!ci_d[p]) begin                       // rising edge
            lo_ok[p]  <= (lo_cnt[p] >= 8'd2);
            hi_cnt[p] <= 8'd1;
          end
          lo_cnt[p] <= 8'd0;
        end else begin
          lo_cnt[p] <= (lo_cnt[p] == 8'hFF) ? lo_cnt[p] : lo_cnt[p] + 8'd1;
          if (ci_d[p]) begin                        // falling edge: qualify
            if (hi_cnt[p] >= 8'd2 && lo_ok[p]) event_pulse[p] <= 1'b1;
            else                               n_rejected_short <= n_rejected_short + 32'd1;
          end
          hi_cnt[p] <= 8'd0;
        end
      end
    end
  end

  // ---------------------------------------------------------------------------
  // index update. Gated by arming and by ENSM state (E-AGC1 H6).
  // ---------------------------------------------------------------------------
  wire gate = pin_ctrl_armed & ensm_rx_active;
  reg  gain_changed;              // pulses for one cycle on any index change
  reg  drop_armed;

  always @(posedge clkrf) begin
    if (!resetn) begin
      rx1_index <= 8'd0; rx2_index <= 8'd0; gain_changed <= 1'b0;
      n_accepted <= 32'd0; n_ignored_ensm <= 32'd0; drop_armed <= 1'b0;
    end else begin
      gain_changed <= 1'b0;
      if (drop_next_pulse) drop_armed <= 1'b1;

      if (|event_pulse) begin
        if (!gate) begin
          // armed but not RX-active, or not armed at all: silently ignored
          if (pin_ctrl_armed) n_ignored_ensm <= n_ignored_ensm + 32'd1;
        end else if (drop_armed) begin
          drop_armed <= 1'b0;                       // deliberately swallow one
        end else begin
          n_accepted <= n_accepted + 32'd1;
          if (event_pulse[0]) begin                 // RX1 increase
            rx1_index <= (rx1_index + inc_step > idx_max) ? idx_max
                                                          : rx1_index + inc_step;
            gain_changed <= 1'b1;
          end
          if (event_pulse[1]) begin                 // RX1 decrease
            rx1_index <= (rx1_index < dec_step) ? 8'd0 : rx1_index - dec_step;
            gain_changed <= 1'b1;
          end
          if (event_pulse[2]) begin                 // RX2 increase
            rx2_index <= (rx2_index + inc_step > idx_max) ? idx_max
                                                          : rx2_index + inc_step;
            gain_changed <= 1'b1;
          end
          if (event_pulse[3]) begin                 // RX2 decrease
            rx2_index <= (rx2_index < dec_step) ? 8'd0 : rx2_index - dec_step;
            gain_changed <= 1'b1;
          end
        end
      end
    end
  end

  // ---------------------------------------------------------------------------
  // detector conditions. effective = level + index, one index = 1 dB.
  // ---------------------------------------------------------------------------
  wire signed [15:0] eff1 = rx1_level + $signed({8'd0, rx1_index});
  wire signed [15:0] eff2 = rx2_level + $signed({8'd0, rx2_index});

  wire raw_lglmt1 = (eff1 > th_lg_lmt);
  wire raw_lgadc1 = (eff1 > th_lg_adc);
  wire raw_smadc1 = (eff1 > th_sm_adc);
  wire raw_lp1    = (eff1 < th_low_pwr);
  wire raw_lglmt2 = (eff2 > th_lg_lmt);
  wire raw_lgadc2 = (eff2 > th_lg_adc);
  wire raw_smadc2 = (eff2 > th_sm_adc);
  wire raw_lp2    = (eff2 < th_low_pwr);

  // ---------------------------------------------------------------------------
  // Peak Overload Wait Time: after a gain change the detectors are held in
  // reset for `pwot` ClkRF cycles (UG-570 p.37, pp.75-76).
  // ---------------------------------------------------------------------------
  reg [5:0] blank_cnt;
  wire      blanking = (blank_cnt != 6'd0);

  always @(posedge clkrf) begin
    if (!resetn)          blank_cnt <= 6'd0;
    else if (gain_changed) blank_cnt <= {1'b0, pwot};
    else if (blanking)     blank_cnt <= blank_cnt - 6'd1;
  end

  // ---------------------------------------------------------------------------
  // overload outputs: latch high until the gain changes; low while blanking
  // ---------------------------------------------------------------------------
  reg lat_lglmt1, lat_lgadc1, lat_smadc1;
  reg lat_lglmt2, lat_lgadc2, lat_smadc2;

  always @(posedge clkrf) begin
    if (!resetn) begin
      lat_lglmt1 <= 1'b0; lat_lgadc1 <= 1'b0; lat_smadc1 <= 1'b0;
      lat_lglmt2 <= 1'b0; lat_lgadc2 <= 1'b0; lat_smadc2 <= 1'b0;
    end else if (gain_changed) begin
      lat_lglmt1 <= 1'b0; lat_lgadc1 <= 1'b0; lat_smadc1 <= 1'b0;
      lat_lglmt2 <= 1'b0; lat_lgadc2 <= 1'b0; lat_smadc2 <= 1'b0;
    end else if (!blanking) begin
      if (raw_lglmt1) lat_lglmt1 <= 1'b1;
      if (raw_lgadc1) lat_lgadc1 <= 1'b1;
      if (raw_smadc1) lat_smadc1 <= 1'b1;
      if (raw_lglmt2) lat_lglmt2 <= 1'b1;
      if (raw_lgadc2) lat_lgadc2 <= 1'b1;
      if (raw_smadc2) lat_smadc2 <= 1'b1;
    end
  end

  // ---------------------------------------------------------------------------
  // low power: unfiltered in MGC, but only re-evaluated once per
  // power-measurement period (UG-570 p.36 and the driver's clamp)
  // ---------------------------------------------------------------------------
  reg [15:0] pwr_div;
  reg        samp_lp1, samp_lp2;

  always @(posedge clkrf) begin
    if (!resetn) begin
      pwr_div <= 16'd0; samp_lp1 <= 1'b0; samp_lp2 <= 1'b0;
    end else if (pwr_div >= pwr_period) begin
      pwr_div  <= 16'd0;
      samp_lp1 <= raw_lp1;
      samp_lp2 <= raw_lp2;
    end else begin
      pwr_div <= pwr_div + 16'd1;
    end
  end

  // ---------------------------------------------------------------------------
  // page 0x03 assembly (UG-570 Table 44, and E-AGC1 H3 confirmed the map)
  //   D7 CH1 low power   D6 CH1 lg LMT   D5 CH1 lg ADC   D4 CH1 sm ADC
  //   D3 CH2 low power   D2 CH2 lg LMT   D1 CH2 lg ADC   D0 CH2 sm ADC
  // ---------------------------------------------------------------------------
  always @(*) begin
    ctrl_out[7] = samp_lp1;
    ctrl_out[6] = lat_lglmt1 & ~blanking;
    ctrl_out[5] = lat_lgadc1 & ~blanking;
    ctrl_out[4] = lat_smadc1 & ~blanking;
    ctrl_out[3] = samp_lp2;
    ctrl_out[2] = lat_lglmt2 & ~blanking;
    ctrl_out[1] = lat_lgadc2 & ~blanking;
    ctrl_out[0] = lat_smadc2 & ~blanking;
  end

endmodule
