// -----------------------------------------------------------------------------
// tb_ad9361_model.v -- self-test for the behavioural AD9361 gain model.
//
// The controller is tested against this model, so the model has to be right
// first. Each check below corresponds to a documented or measured behaviour;
// if one of these fails the model is lying and every downstream result is void.
// -----------------------------------------------------------------------------

`timescale 1ns/1ps

module tb_ad9361_model;

  reg         clkrf = 1'b0;
  reg         resetn = 1'b0;
  reg  [3:0]  ctrl_in = 4'd0;
  wire [7:0]  ctrl_out;

  reg         pin_ctrl_armed = 1'b0;
  reg         ensm_rx_active = 1'b1;
  reg  [3:0]  inc_step = 4'd1;
  reg  [3:0]  dec_step = 4'd1;
  reg  [4:0]  pwot = 5'd3;
  reg  [7:0]  idx_max = 8'd76;

  reg signed [15:0] rx1_level = -16'sd60;
  reg signed [15:0] rx2_level = -16'sd60;
  reg signed [15:0] th_lg_lmt = -16'sd5;
  reg signed [15:0] th_lg_adc = -16'sd8;
  reg signed [15:0] th_sm_adc = -16'sd14;
  reg signed [15:0] th_low_pwr = -16'sd24;
  reg [15:0]  pwr_period = 16'd20;
  reg         drop_next_pulse = 1'b0;

  wire [7:0]  rx1_index, rx2_index;
  wire [31:0] n_accepted, n_rejected_short, n_ignored_ensm;

  integer errors = 0;

  ad9361_gain_model dut (
    .clkrf(clkrf), .resetn(resetn), .ctrl_in(ctrl_in), .ctrl_out(ctrl_out),
    .pin_ctrl_armed(pin_ctrl_armed), .ensm_rx_active(ensm_rx_active),
    .inc_step(inc_step), .dec_step(dec_step), .pwot(pwot), .idx_max(idx_max),
    .rx1_level(rx1_level), .rx2_level(rx2_level),
    .th_lg_lmt(th_lg_lmt), .th_lg_adc(th_lg_adc), .th_sm_adc(th_sm_adc),
    .th_low_pwr(th_low_pwr), .pwr_period(pwr_period),
    .drop_next_pulse(drop_next_pulse),
    .rx1_index(rx1_index), .rx2_index(rx2_index),
    .n_accepted(n_accepted), .n_rejected_short(n_rejected_short),
    .n_ignored_ensm(n_ignored_ensm));

  always #5 clkrf = ~clkrf;

  task tick(input integer n);
    integer i;
    begin for (i = 0; i < n; i = i + 1) @(posedge clkrf); end
  endtask

  // emit a pulse on pin `p`: `hi` cycles high then `lo` cycles low
  task pulse(input integer p, input integer hi, input integer lo);
    begin
      @(negedge clkrf); ctrl_in[p] = 1'b1;
      repeat (hi) @(negedge clkrf);
      ctrl_in[p] = 1'b0;
      repeat (lo) @(negedge clkrf);
    end
  endtask

  task check(input cond, input [511:0] name);
    begin
      if (!cond) begin
        $display("FAIL: %0s", name);
        errors = errors + 1;
      end else begin
        $display("  ok  %0s", name);
      end
    end
  endtask

  initial begin
    $display("== tb_ad9361_model ==");
    tick(4); resetn = 1'b1; tick(4);

    // -- 1. not armed: a perfectly legal pulse must do nothing ---------------
    pulse(0, 4, 4);
    check(rx1_index == 8'd0, "unarmed pulse does not move the index");

    // -- 2. armed and RX-active: a legal pulse moves by inc_step -------------
    pin_ctrl_armed = 1'b1; tick(2);
    pulse(0, 4, 4);
    check(rx1_index == 8'd1, "armed legal pulse moves RX1 by inc_step=1");
    check(rx2_index == 8'd0, "RX1 pulse leaves RX2 alone");

    // -- 3. step size is honoured ------------------------------------------
    inc_step = 4'd2; tick(2);
    pulse(0, 4, 4);
    check(rx1_index == 8'd3, "inc_step=2 moves two indices");
    inc_step = 4'd1; tick(2);

    // -- 4. THE trap: a 1-cycle pulse must be rejected ----------------------
    begin : short_pulse
      reg [7:0] idx0; reg [31:0] rej0;
      idx0 = rx1_index; rej0 = n_rejected_short;
      pulse(0, 1, 4);
      check(rx1_index == idx0, "1-ClkRF pulse is REJECTED (UG-570 2-cycle rule)");
      check(n_rejected_short == rej0 + 1, "short pulse is counted as rejected");
    end

    // -- 5. a 2-cycle pulse is the boundary and must be accepted ------------
    begin : boundary
      reg [7:0] idx0;
      idx0 = rx1_index;
      pulse(0, 2, 4);
      check(rx1_index == idx0 + 1, "2-ClkRF pulse is accepted (boundary)");
    end

    // -- 6. too-short LOW interval also disqualifies ------------------------
    begin : short_low
      reg [7:0] idx0;
      idx0 = rx1_index;
      pulse(0, 4, 0);      // legal high, only ONE low sampling edge
      pulse(0, 4, 4);      // this one's low-history is bad
      check(rx1_index == idx0 + 1, "pulse after a <2-cycle low is rejected");
    end

    // -- 7. ENSM: edges ignored outside RX (E-AGC1 H6) ----------------------
    begin : ensm
      reg [7:0] idx0; reg [31:0] ig0;
      idx0 = rx1_index; ig0 = n_ignored_ensm;
      ensm_rx_active = 1'b0; tick(2);
      pulse(0, 4, 4); pulse(0, 4, 4); pulse(0, 4, 4);
      check(rx1_index == idx0, "edges IGNORED when ENSM is not RX-active");
      check(n_ignored_ensm == ig0 + 3, "ignored edges are counted");
      ensm_rx_active = 1'b1; tick(2);
      pulse(0, 4, 4);
      check(rx1_index == idx0 + 1, "edges honoured again once RX-active");
    end

    // -- 8. RX2 pins are independent ----------------------------------------
    begin : rx2
      reg [7:0] b1, b2;
      b1 = rx1_index; b2 = rx2_index;
      pulse(2, 4, 4);
      check(rx2_index == b2 + 1, "CTRL_IN2 raises RX2");
      check(rx1_index == b1,     "CTRL_IN2 leaves RX1 alone");
      pulse(3, 4, 4);
      check(rx2_index == b2,     "CTRL_IN3 lowers RX2");
    end

    // -- 9. decrease and the floor clamp ------------------------------------
    begin : floor_clamp
      integer i;
      for (i = 0; i < 40; i = i + 1) pulse(1, 4, 4);
      check(rx1_index == 8'd0, "RX1 clamps at 0 and does not wrap");
    end

    // -- 10. ceiling clamp ---------------------------------------------------
    begin : ceil_clamp
      integer i;
      idx_max = 8'd10; tick(2);
      for (i = 0; i < 20; i = i + 1) pulse(0, 4, 4);
      check(rx1_index == 8'd10, "RX1 clamps at idx_max");
      idx_max = 8'd76; tick(2);
    end

    // -- 11. deliberate misbehaviour: one pulse swallowed -------------------
    begin : drop
      reg [7:0] idx0;
      idx0 = rx1_index;
      drop_next_pulse = 1'b1; tick(2); drop_next_pulse = 1'b0;
      pulse(0, 4, 4);
      check(rx1_index == idx0, "drop_next_pulse swallows exactly one command");
      pulse(0, 4, 4);
      check(rx1_index == idx0 + 1, "the following pulse is honoured");
    end

    // -- 12. overload latches until the gain changes ------------------------
    begin : latch
      rx1_level = -16'sd10;      // index ~11 -> effective ~+1, above every thresh
      tick(pwr_period + 8);
      check(ctrl_out[6] == 1'b1, "large LMT asserts on overload");
      rx1_level = -16'sd60;      // remove the signal entirely
      tick(pwr_period + 8);
      check(ctrl_out[6] == 1'b1, "large LMT LATCHES high after the cause is gone");
      pulse(1, 4, 4);            // a gain change is what clears it
      tick(pwot + 4);
      check(ctrl_out[6] == 1'b0, "a gain change clears the latched overload");
    end

    // -- 13. blanking after a gain change -----------------------------------
    begin : blank
      rx1_level = -16'sd10;
      tick(pwr_period + 8);
      check(ctrl_out[6] == 1'b1, "overload re-asserts with signal present");
      @(posedge clkrf);
      pulse(1, 4, 4);
      // immediately after the change the detector is held in reset
      check(ctrl_out[6] == 1'b0, "detectors are blanked immediately after a step");
      rx1_level = -16'sd60; tick(pwr_period + 8);
    end

    // -- 14. low power is sampled per period, not continuously --------------
    begin : lowpwr
      rx1_level = -16'sd60; rx2_level = -16'sd60;
      tick(pwr_period * 2 + 4);
      check(ctrl_out[7] == 1'b1, "low power asserts when the signal is weak");
      check(ctrl_out[3] == 1'b1, "low power asserts on CH2 too");
      rx1_level = -16'sd10;
      tick(2);                                  // less than one period
      check(ctrl_out[7] == 1'b1, "low power does NOT update faster than a period");
      tick(pwr_period + 4);
      check(ctrl_out[7] == 1'b0, "low power clears after a full period");
    end

    $display("== tb_ad9361_model: %0d error(s) ==", errors);
    if (errors != 0) $fatal(1, "MODEL SELF-TEST FAILED");
    $display("PASS: ad9361_gain_model self-test");
    $finish;
  end

  initial begin
    #500000;
    $fatal(1, "tb_ad9361_model timeout");
  end

endmodule
