// -----------------------------------------------------------------------------
// tandem_agc_canary.v
//
// RESOURCE CANARY for the tandem AGC controller.
//
// Purpose: answer the project's single unbounded risk -- does a block of this
// size and this connectivity place and close timing on a Zynq-7010 that is
// already at 74% LUT and 90% DSP -- BEFORE writing the real controller, its
// twelve checkers and its testbench.
//
// This is deliberately NOT random filler. It is the real block's skeleton:
//   * the same register bank shape as TANDEM_AGC_V1_DESIGN.md section 8
//   * the real 256 x 128 event FIFO from D-9
//   * the real counter set, at the real widths
//   * the real pulse generator and ownership mux, including tri-state
//   * the real 3-stage detector conditioning
// The policy FSM is simplified: it makes decisions from the conditioned
// detectors but the truth table is a placeholder. Everything that consumes
// area or stresses routing is structural and stays.
//
// Consequences of that choice: the utilization number is meaningful, the
// routing stress on the gpio_ctl / gpio_status paths is real, and this file
// becomes the starting point for the actual controller rather than being
// thrown away.
//
// Clock domain: l_clk, per D-1.
// -----------------------------------------------------------------------------

`timescale 1ns/1ps

module tandem_agc_canary #(
  parameter [7:0] EVT_DEPTH_LOG2 = 8,     // 256 entries, D-9
  parameter EVT_WIDTH      = 128    // D-9 record layout, section 7.1
) (
  input  wire        l_clk,
  input  wire        l_resetn,

  // conditioned from gpio_status[7:0] = CTRL_OUT[7:0], page 0x03
  input  wire [ 7:0] detect_async,

  // receive-domain sample counter, section 7.1 field [63:0]
  input  wire [63:0] sample_counter,

  // simplified configuration port (the real block takes AXI4-Lite; the slave
  // is a known-cost standard component and is not what this canary measures)
  input  wire [ 7:0] cfg_addr,
  input  wire [31:0] cfg_wdata,
  input  wire        cfg_wr,
  output reg  [31:0] cfg_rdata,

  // legacy PS path, EMIO gpio_o/gpio_t bits [11:8]
  input  wire [ 3:0] ps_ctl_o,
  input  wire [ 3:0] ps_ctl_t,

  // to the ad_iobuf, section 4
  output wire [ 3:0] ctl_o,
  output wire [ 3:0] ctl_t
);

  // ---------------------------------------------------------------------------
  // lifecycle states, section 2.2
  // ---------------------------------------------------------------------------
  localparam ST_LEGACY     = 3'd0;
  localparam ST_ARMING     = 3'd1;
  localparam ST_OWNED_IDLE = 3'd2;
  localparam ST_ACTIVE     = 3'd3;
  localparam ST_DISARMING  = 3'd4;
  localparam ST_RELEASABLE = 3'd5;
  localparam ST_FAULTED    = 3'd6;

  reg [2:0] state;
  reg [7:0] epoch;
  reg [7:0] epoch_tomb;

  // ---------------------------------------------------------------------------
  // detector conditioning: source register, 2-flop sync, debounce. Section 5.1
  // ---------------------------------------------------------------------------
  reg  [7:0] det_src, det_s1, det_s2;
  reg  [7:0] det_stable;
  reg  [7:0] det_cnt [0:7];
  reg  [7:0] cfg_debounce;

  integer di;
  always @(posedge l_clk) begin
    if (!l_resetn) begin
      det_src <= 8'd0; det_s1 <= 8'd0; det_s2 <= 8'd0; det_stable <= 8'd0;
      for (di = 0; di < 8; di = di + 1) det_cnt[di] <= 8'd0;
    end else begin
      det_src <= detect_async;
      det_s1  <= det_src;
      det_s2  <= det_s1;
      for (di = 0; di < 8; di = di + 1) begin
        if (det_s2[di] != det_stable[di]) begin
          if (det_cnt[di] >= cfg_debounce) begin
            det_stable[di] <= det_s2[di];
            det_cnt[di]    <= 8'd0;
          end else begin
            det_cnt[di] <= det_cnt[di] + 8'd1;
          end
        end else begin
          det_cnt[di] <= 8'd0;
        end
      end
    end
  end

  // page 0x03 bit map, section 3
  wire ch1_lp    = det_stable[7];
  wire ch1_lglmt = det_stable[6];
  wire ch1_lgadc = det_stable[5];
  wire ch1_smadc = det_stable[4];
  wire ch2_lp    = det_stable[3];
  wire ch2_lglmt = det_stable[2];
  wire ch2_lgadc = det_stable[1];
  wire ch2_smadc = det_stable[0];

  // ---------------------------------------------------------------------------
  // configuration registers, section 8 shape
  // ---------------------------------------------------------------------------
  reg [7:0]  cfg_pulse_hi, cfg_pulse_lo;
  reg [15:0] cfg_blank_guard;
  reg [31:0] cfg_pwr_period;
  reg [7:0]  cfg_cooldown, cfg_dwell;
  reg [7:0]  cfg_idx_min, cfg_idx_max, cfg_idx_init;
  reg [7:0]  cfg_policy;
  reg [1:0]  cfg_mode_req;
  reg        cfg_fault_clear;

  // ---------------------------------------------------------------------------
  // policy timing. Section 5.5 -- cooldown and dwell count whole
  // power-measurement periods, per D-10, not clock cycles.
  // ---------------------------------------------------------------------------
  reg [31:0] pwr_div;
  reg        pwr_tick;
  reg [7:0]  cooldown_cnt, dwell_cnt;
  reg [15:0] blank_cnt;
  reg        blanked;

  always @(posedge l_clk) begin
    if (!l_resetn) begin
      pwr_div <= 32'd0; pwr_tick <= 1'b0;
    end else if (pwr_div >= cfg_pwr_period) begin
      pwr_div <= 32'd0; pwr_tick <= 1'b1;
    end else begin
      pwr_div <= pwr_div + 32'd1; pwr_tick <= 1'b0;
    end
  end

  // ---------------------------------------------------------------------------
  // pulse generator, D-2: programmable high and low intervals in l_clk cycles
  // ---------------------------------------------------------------------------
  reg [7:0] pulse_cnt;
  reg [3:0] pulse_out;
  reg       pulse_busy, pulse_phase;
  reg [1:0] pending_dir;   // 0 none, 1 increase, 2 decrease

  wire pulse_in_flight = pulse_busy;

  always @(posedge l_clk) begin
    if (!l_resetn) begin
      pulse_cnt <= 8'd0; pulse_out <= 4'd0;
      pulse_busy <= 1'b0; pulse_phase <= 1'b0;
    end else if (pulse_busy) begin
      if (pulse_cnt != 8'd0) begin
        pulse_cnt <= pulse_cnt - 8'd1;
      end else if (!pulse_phase) begin
        pulse_out   <= 4'd0;           // drop, enter the low interval
        pulse_phase <= 1'b1;
        pulse_cnt   <= cfg_pulse_lo;
      end else begin
        pulse_busy  <= 1'b0;
        pulse_phase <= 1'b0;
      end
    end else if (pending_dir != 2'd0 && state == ST_ACTIVE) begin
      // both channels driven identically and simultaneously -- assertion A-2
      pulse_out  <= (pending_dir == 2'd1) ? 4'b0101 : 4'b1010;
      pulse_cnt  <= cfg_pulse_hi;
      pulse_busy <= 1'b1;
    end
  end

  // ---------------------------------------------------------------------------
  // index model and policy. Section 5.3 truth table is a placeholder here;
  // the structure that consumes area is real.
  // ---------------------------------------------------------------------------
  reg [7:0] expected_index;
  wire want_decrease = ch1_lglmt | ch1_lgadc | ch2_lglmt | ch2_lgadc;
  wire inhibit       = ch1_smadc | ch2_smadc;
  wire want_increase = ch1_lp & ch2_lp & ~inhibit;

  wire cooldown_done = (cooldown_cnt == 8'd0);
  wire dwell_done    = (dwell_cnt >= cfg_dwell);
  wire at_min        = (expected_index <= cfg_idx_min);
  wire at_max        = (expected_index >= cfg_idx_max);

  reg        evt_push;
  reg [31:0] evt_seq;
  reg [31:0] cnt_trans, cnt_stale, cnt_inhib, cnt_clamp, cnt_dupdis;
  reg [3:0]  evt_reason;

  always @(posedge l_clk) begin
    if (!l_resetn) begin
      expected_index <= 8'd0; pending_dir <= 2'd0; evt_push <= 1'b0;
      cooldown_cnt <= 8'd0; dwell_cnt <= 8'd0; evt_seq <= 32'd0;
      cnt_trans <= 32'd0; cnt_inhib <= 32'd0; cnt_clamp <= 32'd0;
      evt_reason <= 4'd0; blank_cnt <= 16'd0; blanked <= 1'b0;
    end else begin
      evt_push    <= 1'b0;
      pending_dir <= 2'd0;

      // blanking guard, section 5.2: detectors are not evaluated inside it
      if (pulse_busy) begin
        blank_cnt <= cfg_blank_guard; blanked <= 1'b1;
      end else if (blank_cnt != 16'd0) begin
        blank_cnt <= blank_cnt - 16'd1;
      end else begin
        blanked <= 1'b0;
      end

      if (pwr_tick) begin
        if (cooldown_cnt != 8'd0) cooldown_cnt <= cooldown_cnt - 8'd1;
        if (want_increase) dwell_cnt <= (dwell_cnt == 8'hFF) ? dwell_cnt : dwell_cnt + 8'd1;
        else               dwell_cnt <= 8'd0;
      end

      if (state == ST_ACTIVE && !blanked && cooldown_done && !pulse_in_flight) begin
        if (want_decrease) begin
          if (at_min) begin
            cnt_clamp <= cnt_clamp + 32'd1;      // no spin: report, do not pulse
          end else begin
            pending_dir    <= 2'd2;
            expected_index <= expected_index - 8'd1;
            evt_reason     <= ch1_lglmt | ch2_lglmt ? 4'd0 : 4'd1;
            evt_push       <= 1'b1;
            cooldown_cnt   <= cfg_cooldown;
            cnt_trans      <= cnt_trans + 32'd1;
            evt_seq        <= evt_seq + 32'd1;
          end
        end else if (want_increase && dwell_done) begin
          if (at_max) begin
            cnt_clamp <= cnt_clamp + 32'd1;
          end else begin
            pending_dir    <= 2'd1;
            expected_index <= expected_index + 8'd1;
            evt_reason     <= 4'd3;
            evt_push       <= 1'b1;
            cooldown_cnt   <= cfg_cooldown;
            cnt_trans      <= cnt_trans + 32'd1;
            evt_seq        <= evt_seq + 32'd1;
            dwell_cnt      <= 8'd0;
          end
        end else if (inhibit && ch1_lp && ch2_lp) begin
          cnt_inhib <= cnt_inhib + 32'd1;
        end
      end
    end
  end

  // ---------------------------------------------------------------------------
  // event FIFO, D-9: 256 x 128, one BRAM36
  // ---------------------------------------------------------------------------
  (* ram_style = "block" *)
  reg [EVT_WIDTH-1:0] evt_mem [0:(1<<EVT_DEPTH_LOG2)-1];

  reg [EVT_DEPTH_LOG2:0] evt_wptr, evt_rptr;
  reg [31:0] evt_ovf;
  reg [EVT_WIDTH-1:0] evt_rdata;

  wire evt_full  = (evt_wptr[EVT_DEPTH_LOG2-1:0] == evt_rptr[EVT_DEPTH_LOG2-1:0]) &&
                   (evt_wptr[EVT_DEPTH_LOG2] != evt_rptr[EVT_DEPTH_LOG2]);
  wire evt_empty = (evt_wptr == evt_rptr);
  wire [EVT_DEPTH_LOG2:0] evt_level = evt_wptr - evt_rptr;

  // record layout, section 7.1
  wire [EVT_WIDTH-1:0] evt_wdata = {
      8'd0,                 // [127:120] reserved
      evt_seq,              // [119:88]  sequence
      epoch,                // [87:80]   ownership epoch
      2'd0,                 // [79:78]   reserved
      pending_dir,          // [77:76]   direction
      evt_reason,           // [75:72]   reason
      expected_index,       // [71:64]   index after transition
      sample_counter        // [63:0]    captured instant
  };

  wire evt_pop = cfg_wr && (cfg_addr == 8'h3C);   // read of EVT_HI3 pops

  always @(posedge l_clk) begin
    if (!l_resetn) begin
      evt_wptr <= 0; evt_rptr <= 0; evt_ovf <= 32'd0;
    end else begin
      if (evt_push) begin
        if (evt_full) begin
          evt_ovf <= evt_ovf + 32'd1;             // never silent
        end else begin
          evt_mem[evt_wptr[EVT_DEPTH_LOG2-1:0]] <= evt_wdata;
          evt_wptr <= evt_wptr + 1'b1;
        end
      end
      if (evt_pop && !evt_empty) begin
        evt_rdata <= evt_mem[evt_rptr[EVT_DEPTH_LOG2-1:0]];
        evt_rptr  <= evt_rptr + 1'b1;
      end
    end
  end

  // ---------------------------------------------------------------------------
  // lifecycle, ownership epoch. Section 2.3 -- never reused, skips zero on wrap
  // ---------------------------------------------------------------------------
  always @(posedge l_clk) begin
    if (!l_resetn) begin
      state <= ST_LEGACY; epoch <= 8'd1; epoch_tomb <= 8'd0;
      cnt_stale <= 32'd0; cnt_dupdis <= 32'd0;
    end else begin
      case (state)
        ST_LEGACY:     if (cfg_mode_req != 2'd0) begin
                         state <= ST_ARMING;
                         epoch <= (epoch == 8'hFF) ? 8'd1 : epoch + 8'd1;
                       end
        ST_ARMING:     state <= ST_OWNED_IDLE;
        ST_OWNED_IDLE: if (cfg_mode_req == 2'd2)      state <= ST_ACTIVE;
                       else if (cfg_mode_req == 2'd0) state <= ST_DISARMING;
        ST_ACTIVE:     if (cfg_mode_req != 2'd2)      state <= ST_DISARMING;
        ST_DISARMING:  if (!pulse_busy)               state <= ST_RELEASABLE;
        ST_RELEASABLE: begin state <= ST_LEGACY; epoch_tomb <= epoch; end
        ST_FAULTED:    if (cfg_fault_clear)           state <= ST_LEGACY;
        default:       state <= ST_LEGACY;
      endcase
    end
  end

  // ---------------------------------------------------------------------------
  // ownership mux, section 4: owns BOTH value and tri-state. Registered.
  // Reset selects legacy. Assertion A-7 -- no edge because ownership changed.
  // ---------------------------------------------------------------------------
  wire fpga_owns = (state == ST_OWNED_IDLE) || (state == ST_ACTIVE) ||
                   (state == ST_DISARMING);

  reg [3:0] ctl_o_r, ctl_t_r;
  always @(posedge l_clk) begin
    if (!l_resetn) begin
      ctl_o_r <= 4'd0; ctl_t_r <= 4'hF;      // legacy: high-Z
    end else if (fpga_owns) begin
      ctl_o_r <= pulse_out;
      ctl_t_r <= 4'd0;                       // drive
    end else begin
      ctl_o_r <= ps_ctl_o;
      ctl_t_r <= ps_ctl_t;
    end
  end

  assign ctl_o = ctl_o_r;
  assign ctl_t = ctl_t_r;

  // ---------------------------------------------------------------------------
  // register file, section 8
  // ---------------------------------------------------------------------------
  always @(posedge l_clk) begin
    if (!l_resetn) begin
      cfg_pulse_hi <= 8'd16; cfg_pulse_lo <= 8'd16;   // D-2 default
      cfg_blank_guard <= 16'd64;
      cfg_pwr_period <= 32'd10000;
      cfg_cooldown <= 8'd2; cfg_dwell <= 8'd4;        // section 5.5
      cfg_idx_min <= 8'd40; cfg_idx_max <= 8'd54;     // D-7 band-common window
      cfg_idx_init <= 8'd47; cfg_policy <= 8'hFF;
      cfg_mode_req <= 2'd0; cfg_debounce <= 8'd8;
      cfg_fault_clear <= 1'b0;
    end else if (cfg_wr) begin
      case (cfg_addr)
        8'h08: begin cfg_mode_req <= cfg_wdata[1:0]; cfg_fault_clear <= cfg_wdata[8]; end
        8'h14: begin cfg_idx_min <= cfg_wdata[7:0]; cfg_idx_max <= cfg_wdata[15:8];
                     cfg_idx_init <= cfg_wdata[23:16]; end
        8'h1C: begin cfg_pulse_hi <= cfg_wdata[7:0]; cfg_pulse_lo <= cfg_wdata[15:8];
                     cfg_blank_guard <= cfg_wdata[31:16]; end
        8'h20: cfg_pwr_period <= cfg_wdata;
        8'h24: begin cfg_cooldown <= cfg_wdata[7:0]; cfg_dwell <= cfg_wdata[15:8];
                     cfg_debounce <= cfg_wdata[23:16]; end
        8'h28: cfg_policy <= cfg_wdata[7:0];
        default: ;
      endcase
    end
  end

  always @(posedge l_clk) begin
    case (cfg_addr)
      8'h00: cfg_rdata <= 32'h5441_4731;                       // "TAG1"
      8'h04: cfg_rdata <= {16'd0, 8'd0, EVT_DEPTH_LOG2[7:0]};
      8'h0C: cfg_rdata <= {24'd0, cooldown_done, pulse_in_flight,
                           1'b0, fpga_owns, 1'b0, state};
      8'h10: cfg_rdata <= {16'd0, epoch_tomb, epoch};
      8'h18: cfg_rdata <= {24'd0, expected_index};
      8'h30: cfg_rdata <= evt_rdata[31:0];
      8'h34: cfg_rdata <= evt_rdata[63:32];
      8'h38: cfg_rdata <= evt_rdata[95:64];
      8'h3C: cfg_rdata <= evt_rdata[127:96];
      8'h40: cfg_rdata <= {{(31-EVT_DEPTH_LOG2){1'b0}}, evt_level};
      8'h44: cfg_rdata <= evt_ovf;
      8'h48: cfg_rdata <= cnt_trans;
      8'h4C: cfg_rdata <= cnt_stale;
      8'h50: cfg_rdata <= cnt_inhib;
      8'h54: cfg_rdata <= cnt_clamp;
      8'h58: cfg_rdata <= cnt_dupdis;
      8'h5C: cfg_rdata <= {24'd0, det_stable};
      default: cfg_rdata <= 32'd0;
    endcase
  end

endmodule
