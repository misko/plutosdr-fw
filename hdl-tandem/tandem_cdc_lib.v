// -----------------------------------------------------------------------------
// tandem_cdc_lib.v
//
// The clock-domain-crossing primitives for the tandem AGC block, per
// TANDEM_AGC_V1_DESIGN.md §9. Every crossing in this design uses one of these;
// nothing crosses ad hoc.
//
// This file exists because RC3 and RC4 failed Vivado CDC-10 and RC5 and RC6
// failed on boot-dependent clock and reset ordering. Four candidates were lost
// to crossings that were written inline and looked fine. The rules here are
// therefore explicit:
//
//   * every asynchronous input is registered in its source domain BEFORE the
//     synchroniser, so the synchroniser never samples combinational logic;
//   * no multi-bit field crosses without a qualifying handshake or a gray code;
//   * reset asserts asynchronously and DEASSERTS synchronously in each
//     destination domain;
//   * every crossing carries an ASYNC_REG attribute so the placer keeps the
//     synchroniser flops together.
// -----------------------------------------------------------------------------

`timescale 1ns/1ps

// -----------------------------------------------------------------------------
// Single-bit level synchroniser. The input MUST already be registered in its
// source domain.
// -----------------------------------------------------------------------------
module tandem_sync_bit #(
  parameter integer STAGES = 2
) (
  input  wire clk,
  input  wire resetn,
  input  wire d,
  output wire q
);
  (* ASYNC_REG = "TRUE" *) reg [STAGES-1:0] sync;
  integer i;
  always @(posedge clk) begin
    if (!resetn) sync <= {STAGES{1'b0}};
    else begin
      sync[0] <= d;
      for (i = 1; i < STAGES; i = i + 1) sync[i] <= sync[i-1];
    end
  end
  assign q = sync[STAGES-1];
endmodule

// -----------------------------------------------------------------------------
// Reset bridge: asynchronous assert, synchronous deassert in the destination
// domain. Correct when the destination clock is stopped or starts late, which
// is the RC5/RC6 failure mode.
// -----------------------------------------------------------------------------
module tandem_reset_bridge (
  input  wire clk,
  input  wire aresetn,       // asynchronous, active low
  output wire resetn
);
  (* ASYNC_REG = "TRUE" *) reg [1:0] sync;
  always @(posedge clk or negedge aresetn) begin
    if (!aresetn) sync <= 2'b00;
    else          sync <= {sync[0], 1'b1};
  end
  assign resetn = sync[1];
endmodule

// -----------------------------------------------------------------------------
// Multi-bit crossing by toggle handshake. The source presents `din` and pulses
// `load`; the payload is captured in the source domain and held stable while a
// toggle crosses, so the destination only ever samples settled data.
//
// The source must not issue a new `load` until `busy` is low.
// -----------------------------------------------------------------------------
module tandem_cdc_bus #(
  parameter integer W = 32
) (
  input  wire         src_clk,
  input  wire         src_resetn,
  input  wire [W-1:0] din,
  input  wire         load,
  output wire         busy,

  input  wire         dst_clk,
  input  wire         dst_resetn,
  output reg  [W-1:0] dout,
  output reg          dout_valid
);
  reg [W-1:0] hold;
  reg         tog;
  always @(posedge src_clk) begin
    if (!src_resetn) begin
      hold <= {W{1'b0}}; tog <= 1'b0;
    end else if (load && !busy) begin
      hold <= din;                 // registered in the SOURCE domain
      tog  <= ~tog;
    end
  end

  wire tog_dst;
  tandem_sync_bit #(.STAGES(3)) u_tog (
    .clk(dst_clk), .resetn(dst_resetn), .d(tog), .q(tog_dst));

  reg tog_dst_d;
  always @(posedge dst_clk) begin
    if (!dst_resetn) begin
      tog_dst_d <= 1'b0; dout <= {W{1'b0}}; dout_valid <= 1'b0;
    end else begin
      tog_dst_d  <= tog_dst;
      dout_valid <= (tog_dst != tog_dst_d);
      if (tog_dst != tog_dst_d) dout <= hold;   // stable for >= 3 dst cycles
    end
  end

  // acknowledge back so the source knows the payload has landed
  wire ack_src;
  tandem_sync_bit #(.STAGES(3)) u_ack (
    .clk(src_clk), .resetn(src_resetn), .d(tog_dst), .q(ack_src));
  assign busy = (ack_src != tog);
endmodule

// -----------------------------------------------------------------------------
// Asynchronous FIFO with gray-coded pointers. Used for the event path, which
// is written in the receive domain and read from the processor domain.
// -----------------------------------------------------------------------------
module tandem_async_fifo #(
  parameter integer W  = 128,
  parameter integer AW = 8
) (
  input  wire          wr_clk,
  input  wire          wr_resetn,
  input  wire          wr_en,
  input  wire [W-1:0]  wr_data,
  output wire          wr_full,
  output reg  [31:0]   wr_ovf,

  input  wire          rd_clk,
  input  wire          rd_resetn,
  input  wire          rd_en,
  output wire [W-1:0]  rd_data,
  output wire          rd_valid,
  output wire [AW:0]   rd_level
);
  localparam integer DEPTH = (1 << AW);

  (* ram_style = "block" *) reg [W-1:0] mem [0:DEPTH-1];

  // wr_full MUST be a register. Deriving it combinationally from wgray_nxt
  // creates wr_full -> wbin_nxt -> wgray_nxt -> wr_full, a zero-delay loop that
  // hangs simulation and is a combinational loop in synthesis. This is the
  // standard structure: the flag is registered, and the next-state arithmetic
  // uses the registered value.
  reg  [AW:0] wbin, wgray, rbin, rgray;
  reg         full_r;
  wire [AW:0] wbin_nxt  = wbin + (wr_en && !full_r);
  wire [AW:0] wgray_nxt = (wbin_nxt >> 1) ^ wbin_nxt;
  wire [AW:0] rbin_nxt  = rbin + (rd_en && rd_valid);
  wire        full_nxt;
  wire [AW:0] rgray_nxt = (rbin_nxt >> 1) ^ rbin_nxt;

  // gray pointers crossing, one bit each, all ASYNC_REG
  (* ASYNC_REG = "TRUE" *) reg [AW:0] wgray_s1, wgray_s2;
  (* ASYNC_REG = "TRUE" *) reg [AW:0] rgray_s1, rgray_s2;

  always @(posedge wr_clk) begin
    if (!wr_resetn) begin
      wbin <= 0; wgray <= 0; wr_ovf <= 32'd0; full_r <= 1'b0;
      rgray_s1 <= 0; rgray_s2 <= 0;
    end else begin
      rgray_s1 <= rgray;
      rgray_s2 <= rgray_s1;
      if (wr_en) begin
        if (full_r) wr_ovf <= wr_ovf + 32'd1;       // never silent, §7.5
        else        mem[wbin[AW-1:0]] <= wr_data;
      end
      wbin   <= wbin_nxt;
      wgray  <= wgray_nxt;
      full_r <= full_nxt;
    end
  end

  always @(posedge rd_clk) begin
    if (!rd_resetn) begin
      rbin <= 0; rgray <= 0; wgray_s1 <= 0; wgray_s2 <= 0;
    end else begin
      wgray_s1 <= wgray;
      wgray_s2 <= wgray_s1;
      rbin  <= rbin_nxt;
      rgray <= rgray_nxt;
    end
  end

  assign full_nxt = (wgray_nxt == {~rgray_s2[AW:AW-1], rgray_s2[AW-2:0]});
  assign wr_full  = full_r;
  assign rd_valid = (rgray != wgray_s2);

  // Synchronous read, indexed by the NEXT pointer. An asynchronous
  // `assign rd_data = mem[rbin]` cannot map to block RAM and inferred 891 LUT
  // of distributed RAM with zero BRAM when first measured. Indexing by rbin_nxt
  // rather than rbin is what keeps the registered output from being one entry
  // stale after a read.
  reg [W-1:0] rd_data_r;
  always @(posedge rd_clk) begin
    if (!rd_resetn) rd_data_r <= {W{1'b0}};
    else            rd_data_r <= mem[rbin_nxt[AW-1:0]];
  end
  assign rd_data = rd_data_r;

  // approximate occupancy for status; exact ordering is not required of it
  function [AW:0] gray2bin(input [AW:0] g);
    integer i; begin
      gray2bin[AW] = g[AW];
      for (i = AW-1; i >= 0; i = i - 1) gray2bin[i] = gray2bin[i+1] ^ g[i];
    end
  endfunction
  assign rd_level = gray2bin(wgray_s2) - rbin;

endmodule
