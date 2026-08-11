// -----------------------------------------------------------------------------
// tandem_agc_regs.v
//
// Register file and control surface for the tandem AGC controller, implementing
// the map in TANDEM_AGC_V1_DESIGN.md §8. Presents a simple synchronous
// register port; an AXI4-Lite slave wraps this unchanged at integration.
//
// Reset defaults follow the design contract:
//   pulse width 16 (D-2, RTL floor 4 lives in the core)
//   cooldown 2 and dwell 4 power-measurement periods (§5.5)
//   index window = full usable range (D-7 -- the narrow [40,54] phase-optimal
//   window is available but is deliberately NOT the default)
// -----------------------------------------------------------------------------

`timescale 1ns/1ps

module tandem_agc_regs (
  input  wire        l_clk,
  input  wire        l_resetn,

  // ---- register port ------------------------------------------------------
  input  wire [7:0]  reg_addr,
  input  wire [31:0] reg_wdata,
  input  wire        reg_wr,
  input  wire        reg_rd,
  output reg  [31:0] reg_rdata,

  // ---- to/from the core ---------------------------------------------------
  output wire [1:0]  mode_req,
  output wire        fault_clear,
  output wire [7:0]  cfg_pulse_hi,
  output wire [7:0]  cfg_pulse_lo,
  output wire [15:0] cfg_blank_guard,
  output wire [19:0] cfg_pwr_period,
  output wire [7:0]  cfg_cooldown,
  output wire [7:0]  cfg_dwell,
  output wire [7:0]  cfg_debounce,
  output wire [7:0]  cfg_idx_min,
  output wire [7:0]  cfg_idx_max,
  output wire [7:0]  cfg_idx_init,

  input  wire [2:0]  state,
  input  wire [7:0]  epoch,
  input  wire [7:0]  epoch_tomb,
  input  wire [7:0]  expected_index,
  input  wire        pulse_busy,
  input  wire        cooldown_active,
  input  wire        fpga_owns,
  input  wire [7:0]  fault,
  input  wire [7:0]  detect,
  input  wire [7:0]  cnt_trans,
  input  wire [7:0]  cnt_inhib,
  input  wire [7:0]  cnt_clamp,
  input  wire [7:0]  cnt_stale,
  input  wire [103:0] evt_rdata,
  input  wire        evt_valid,
  input  wire [6:0]  evt_level,
  input  wire [7:0]  evt_ovf,
  output wire        evt_pop
);

  localparam [31:0] ID_MAGIC = 32'h5441_4731;   // "TAG1"

  reg [1:0]  r_mode;
  reg        r_fault_clear;
  reg [7:0]  r_pulse_hi, r_pulse_lo;
  reg [15:0] r_blank_guard;
  reg [19:0] r_pwr_period;
  reg [7:0]  r_cooldown, r_dwell, r_debounce;
  reg [7:0]  r_idx_min, r_idx_max, r_idx_init;

  // §8: reading EVT_HI3 (0x3C) pops the entry, so a partially-read event is
  // impossible -- the pop is the last of the four reads.
  assign evt_pop = reg_rd && (reg_addr == 8'h3C) && evt_valid;

  always @(posedge l_clk) begin
    if (!l_resetn) begin
      r_mode        <= 2'd0;          // legacy is the reset default
      r_fault_clear <= 1'b0;
      r_pulse_hi    <= 8'd16;         // D-2
      r_pulse_lo    <= 8'd16;
      r_blank_guard <= 16'd64;
      r_pwr_period  <= 20'd10000;
      r_cooldown    <= 8'd2;          // §5.5, in power-measurement periods
      r_dwell       <= 8'd4;
      r_debounce    <= 8'd8;
      r_idx_min     <= 8'd0;          // D-7: full usable range by default
      r_idx_max     <= 8'd76;
      r_idx_init    <= 8'd40;
    end else begin
      r_fault_clear <= 1'b0;          // one-shot
      if (reg_wr) begin
        case (reg_addr)
          8'h08: begin r_mode <= reg_wdata[1:0]; r_fault_clear <= reg_wdata[8]; end
          8'h14: begin r_idx_min <= reg_wdata[7:0]; r_idx_max <= reg_wdata[15:8];
                       r_idx_init <= reg_wdata[23:16]; end
          8'h1C: begin r_pulse_hi <= reg_wdata[7:0]; r_pulse_lo <= reg_wdata[15:8];
                       r_blank_guard <= reg_wdata[31:16]; end
          8'h20: r_pwr_period <= reg_wdata[19:0];
          8'h24: begin r_cooldown <= reg_wdata[7:0]; r_dwell <= reg_wdata[15:8];
                       r_debounce <= reg_wdata[23:16]; end
          default: ;
        endcase
      end
    end
  end

  always @(*) begin
    case (reg_addr)
      8'h00: reg_rdata = ID_MAGIC;
      8'h04: reg_rdata = {16'd0, 8'd104, 8'd6};       // record width, depth log2
      8'h08: reg_rdata = {23'd0, 1'b0, 6'd0, r_mode};
      8'h0C: reg_rdata = {24'd0, cooldown_active, pulse_busy,
                          1'b0, fpga_owns, 1'b0, state};
      8'h10: reg_rdata = {16'd0, epoch_tomb, epoch};
      8'h14: reg_rdata = {8'd0, r_idx_init, r_idx_max, r_idx_min};
      8'h18: reg_rdata = {24'd0, expected_index};
      8'h1C: reg_rdata = {r_blank_guard, r_pulse_lo, r_pulse_hi};
      8'h20: reg_rdata = {12'd0, r_pwr_period};
      8'h24: reg_rdata = {8'd0, r_debounce, r_dwell, r_cooldown};
      8'h2C: reg_rdata = {24'd0, fault};
      8'h30: reg_rdata = evt_rdata[31:0];
      8'h34: reg_rdata = evt_rdata[63:32];
      8'h38: reg_rdata = evt_rdata[95:64];
      8'h3C: reg_rdata = {24'd0, evt_rdata[103:96]};
      8'h40: reg_rdata = {25'd0, evt_level};
      8'h44: reg_rdata = {24'd0, evt_ovf};
      8'h48: reg_rdata = {24'd0, cnt_trans};
      8'h4C: reg_rdata = {24'd0, cnt_stale};
      8'h50: reg_rdata = {24'd0, cnt_inhib};
      8'h54: reg_rdata = {24'd0, cnt_clamp};
      8'h5C: reg_rdata = {24'd0, detect};
      default: reg_rdata = 32'd0;
    endcase
  end

  assign mode_req        = r_mode;
  assign fault_clear     = r_fault_clear;
  assign cfg_pulse_hi    = r_pulse_hi;
  assign cfg_pulse_lo    = r_pulse_lo;
  assign cfg_blank_guard = r_blank_guard;
  assign cfg_pwr_period  = r_pwr_period;
  assign cfg_cooldown    = r_cooldown;
  assign cfg_dwell       = r_dwell;
  assign cfg_debounce    = r_debounce;
  assign cfg_idx_min     = r_idx_min;
  assign cfg_idx_max     = r_idx_max;
  assign cfg_idx_init    = r_idx_init;

endmodule
