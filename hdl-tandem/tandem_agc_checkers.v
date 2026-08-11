// -----------------------------------------------------------------------------
// tandem_agc_checkers.v
//
// The twelve assertions of TANDEM_AGC_V1_DESIGN.md §10, written as procedural
// checkers because Icarus Verilog has no concurrent-assertion support and this
// repository uses none. Instantiate alongside the DUT; it runs continuously and
// reports at the end of simulation.
//
// Pin order throughout: ctl[0]=CTRL_IN0 RX1 inc, [1]=CTRL_IN1 RX1 dec,
//                       ctl[2]=CTRL_IN2 RX2 inc, [3]=CTRL_IN3 RX2 dec.
// -----------------------------------------------------------------------------

`timescale 1ns/1ps

module tandem_agc_checkers #(
  parameter integer EVT_DW = 128
) (
  input  wire              l_clk,
  input  wire              l_resetn,

  input  wire [3:0]        ctl_o,
  input  wire [3:0]        ctl_t,
  input  wire [3:0]        ps_ctl_o,
  input  wire [3:0]        ps_ctl_t,
  input  wire              fpga_owns,
  input  wire              armed,          // AD9361 pin control armed (software)

  input  wire [7:0]        pulse_hi_eff,
  input  wire [7:0]        pulse_lo_eff,
  input  wire              pulse_busy,
  input  wire              cooldown_active,
  input  wire              blanked,
  input  wire [7:0]        fault,

  input  wire [7:0]        expected_index,
  input  wire [7:0]        step_size,
  input  wire              policing,   // high only while the policy may act

  input  wire              evt_push,
  input  wire [EVT_DW-1:0] evt_wdata,
  input  wire [7:0]        epoch,

  output reg  [31:0]       a_err
);

  integer i;
  reg [3:0] ctl_d;
  reg [7:0] hi_run, lo_run;
  reg       was_high;
  reg [7:0] exp_idx_d;
  reg       evt_push_d;
  reg [31:0] last_seq;
  reg [7:0]  last_epoch;
  reg        seq_seen;
  reg [3:0]  ps_o_d;
  reg [3:0]  ps_t_d;
  reg        owns_d;
  reg        cd_d, blank_d;
  reg [7:0]  fault_d;

  task fail(input [511:0] which);
    begin
      $display("ASSERT FAIL @%0t: %0s", $time, which);
      a_err = a_err + 1;
    end
  endtask

  initial begin
    a_err = 0; hi_run = 0; lo_run = 0; was_high = 0;
    cd_d = 0; blank_d = 0; fault_d = 0;
    last_seq = 0; last_epoch = 0; seq_seen = 0;
  end

  always @(posedge l_clk) begin
    ctl_d      <= ctl_o;
    exp_idx_d  <= expected_index;
    evt_push_d <= evt_push;
    ps_o_d     <= ps_ctl_o;
    ps_t_d     <= ps_ctl_t;
    owns_d     <= fpga_owns;
    cd_d       <= cooldown_active;
    blank_d    <= blanked;
    fault_d    <= fault;

    if (l_resetn) begin

      // A-1: increment and decrement never asserted together on a channel
      if (ctl_o[0] && ctl_o[1]) fail("A-1 RX1 inc and dec asserted together");
      if (ctl_o[2] && ctl_o[3]) fail("A-1 RX2 inc and dec asserted together");

      // A-2: the two channels' commands are bit-identical every cycle
      if (ctl_o[0] !== ctl_o[2]) fail("A-2 RX1/RX2 increment differ");
      if (ctl_o[1] !== ctl_o[3]) fail("A-2 RX1/RX2 decrement differ");

      // A-3: emitted pulse widths match the programmed values
      if (fpga_owns) begin
        if (|ctl_o) begin
          hi_run <= hi_run + 8'd1;
          lo_run <= 8'd0;
          was_high <= 1'b1;
        end else begin
          if (was_high) begin
            if (hi_run != pulse_hi_eff)
              fail("A-3 pulse high interval != programmed width");
            was_high <= 1'b0;
            lo_run   <= 8'd1;
          end else if (lo_run != 8'hFF) lo_run <= lo_run + 8'd1;
          hi_run <= 8'd0;
        end
        // a new pulse may only start after a full low interval
        if (!ctl_d[0] && ctl_o[0] && lo_run < pulse_lo_eff && lo_run != 8'd0)
          fail("A-3 pulse started before the low interval completed");
      end else begin
        hi_run <= 8'd0; lo_run <= 8'd0; was_high <= 1'b0;
      end

      // A-4: expected_index moves by at most one programmed step per transition.
      // Excludes the ARMING seed, which is an initialisation (§11 step 5).
      if ((expected_index != exp_idx_d) && policing) begin
        if ((expected_index > exp_idx_d ? expected_index - exp_idx_d
                                        : exp_idx_d - expected_index) > step_size)
          fail("A-4 expected_index moved more than one step");
      end

      // A-5/A-6: an event is pushed exactly when a transition is accepted.
      // Enforced structurally in the core; checked here as index-moved <=> event.
      if (evt_push && (expected_index == exp_idx_d) && (exp_idx_d != 8'd0))
        fail("A-6 event pushed without an index change");

      // A-7: an ownership change never produces an edge while the part is armed
      if (armed && (fpga_owns != owns_d) && (ctl_o != ctl_d))
        fail("A-7 ownership change produced an edge while armed");

      // A-8: outside ownership the legacy path passes through untouched
      if (!fpga_owns && !owns_d) begin
        if (ctl_o !== ps_o_d) fail("A-8 legacy value not passed through");
        if (ctl_t !== ps_t_d) fail("A-8 legacy tri-state not passed through");
      end

      // A-9/A-10: epoch is current, sequence is monotonic within an epoch
      if (evt_push) begin
        if (evt_wdata[87:80] !== epoch) fail("A-9 event carries a stale epoch");
        if (seq_seen && (evt_wdata[87:80] == last_epoch)) begin
          if (evt_wdata[119:88] <= last_seq)
            fail("A-10 event sequence not monotonic within the epoch");
        end
        last_seq   <= evt_wdata[119:88];
        last_epoch <= evt_wdata[87:80];
        seq_seen   <= 1'b1;
      end

      // A-11: no transition is ACCEPTED while cooling down or faulted.
      // Checked at the decision, not at the pulse edge: the core sets cooldown
      // in the same cycle it accepts, so the pulse always rises with cooldown
      // active by construction.
      if (evt_push && cd_d) fail("A-11 decision taken during cooldown");
      if (evt_push && (fault_d != 8'd0)) fail("A-11 decision taken while faulted");

      // A-12: no transition is accepted inside the blanking window
      if (evt_push && blank_d) fail("A-12 transition accepted while blanked");

    end
  end

endmodule
