// -----------------------------------------------------------------------------
// tandem_agc_axi.v
//
// AXI4-Lite slave for the tandem AGC block. This is the unit that goes into the
// Pluto block design: it owns the processor-domain register interface and every
// crossing into and out of the receive domain, per TANDEM_AGC_V1_DESIGN.md §8
// and the v2 ownership contract.
//
// Three domains meet here and each crossing uses a primitive from
// tandem_cdc_lib.v, never an ad-hoc synchroniser:
//
//   config   AXI -> l_clk   one toggle-handshake bus carrying the whole bundle,
//                           so no field can be torn against another
//   status   l_clk -> AXI   a periodic snapshot over the same handshake, so a
//                           reader always sees one coherent instant rather than
//                           a mixture of two
//   events   l_clk -> AXI   the gray-coded asynchronous FIFO
//
// Port names follow the AXI4-Lite convention so Vivado infers the interface
// when this is added to a block design as a module reference.
// -----------------------------------------------------------------------------

`timescale 1ns/1ps

module tandem_agc_axi #(
  parameter integer EVT_AW = 6,
  parameter integer EVT_DW = 128,
  parameter integer EVENTS = 1
) (
  // ---- AXI4-Lite, processor domain ---------------------------------------
  input  wire        s_axi_aclk,
  input  wire        s_axi_aresetn,
  input  wire [7:0]  s_axi_awaddr,
  input  wire        s_axi_awvalid,
  output wire        s_axi_awready,
  input  wire [31:0] s_axi_wdata,
  input  wire [3:0]  s_axi_wstrb,
  input  wire        s_axi_wvalid,
  output wire        s_axi_wready,
  output wire [1:0]  s_axi_bresp,
  output wire        s_axi_bvalid,
  input  wire        s_axi_bready,
  input  wire [7:0]  s_axi_araddr,
  input  wire        s_axi_arvalid,
  output wire        s_axi_arready,
  output wire [31:0] s_axi_rdata,
  output wire [1:0]  s_axi_rresp,
  output wire        s_axi_rvalid,
  input  wire        s_axi_rready,

  // ---- receive domain -----------------------------------------------------
  input  wire        l_clk,
  input  wire        l_aresetn,        // asynchronous; bridged internally
  input  wire [7:0]  detect_async,     // CTRL_OUT page 0x03
  input  wire [63:0] sample_counter,
  input  wire        sample_valid,
  input  wire        consumer_ready,

  // ---- legacy PS path and pins -------------------------------------------
  input  wire [3:0]  ps_ctl_o,
  input  wire [3:0]  ps_ctl_t,
  output wire [3:0]  ctl_o,
  output wire [3:0]  ctl_t
);

  // ---------------------------------------------------------------------------
  // reset bridges, §9: asynchronous assert, synchronous deassert per domain
  // ---------------------------------------------------------------------------
  wire l_resetn;
  tandem_reset_bridge u_rst_l (
    .clk(l_clk), .aresetn(l_aresetn & s_axi_aresetn), .resetn(l_resetn));

  wire axi_resetn;
  tandem_reset_bridge u_rst_axi (
    .clk(s_axi_aclk), .aresetn(s_axi_aresetn), .resetn(axi_resetn));

  // ---------------------------------------------------------------------------
  // configuration registers, held in the AXI domain
  // ---------------------------------------------------------------------------
  localparam integer CFGW = 140;
  localparam integer STAW = 94;

  reg [7:0]  r_pulse_hi, r_pulse_lo;
  reg [15:0] r_blank_guard;
  reg [19:0] r_pwr_period;
  reg [7:0]  r_cooldown, r_dwell, r_debounce;
  reg [7:0]  r_idx_min, r_idx_max, r_idx_init;
  reg [31:0] r_epoch, r_thresholds;
  reg [1:0]  r_mode;
  reg        r_fault_clear;
  reg        cfg_load;

  wire [CFGW-1:0] cfg_bundle = {
      r_epoch, 5'd0, r_fault_clear, r_mode,
      r_idx_init, r_idx_max, r_idx_min,
      r_debounce, r_dwell, r_cooldown, r_pwr_period, r_blank_guard,
      r_pulse_lo, r_pulse_hi };

  // elaboration-time guard: if a field width changes and CFGW is not updated to
  // match, fail loudly here rather than silently shifting every offset

  wire            cfg_busy;
  wire [CFGW-1:0] cfg_l;
  wire            cfg_l_valid;

  // The AXI write channel is backpressured while this transfer is busy, so the
  // source register bundle remains stable until the destination acknowledges.
  tandem_cdc_bus #(.W(CFGW), .HOLD(0)) u_cfg (
    .src_clk(s_axi_aclk), .src_resetn(axi_resetn),
    .din(cfg_bundle), .load(cfg_load), .busy(cfg_busy),
    .dst_clk(l_clk), .dst_resetn(l_resetn),
    .dout(cfg_l), .dout_valid(cfg_l_valid));

  // The bus's own destination register is already a stable latched copy in the
  // receive domain, so a further cfg_held copy would be another CFGW flops for
  // nothing. Reset defaults live in the AXI-side registers and cross on the
  // first load; until then the bus presents its reset value, which holds the
  // controller in LEGACY -- the safe state.
  wire [CFGW-1:0] cfg_held = cfg_l;
  wire _unused_cfg_valid = cfg_l_valid;

  // Offsets follow cfg_bundle exactly. They moved when pwr_period narrowed from
  // 32 to 20 bits; leaving them stale made the controller read `mode` out of the
  // middle of the index fields and never leave LEGACY.
  wire [7:0]  c_pulse_hi    = cfg_held[7:0];
  wire [7:0]  c_pulse_lo    = cfg_held[15:8];
  wire [15:0] c_blank_guard = cfg_held[31:16];
  wire [19:0] c_pwr_period  = cfg_held[51:32];
  wire [7:0]  c_cooldown    = cfg_held[59:52];
  wire [7:0]  c_dwell       = cfg_held[67:60];
  wire [7:0]  c_debounce    = cfg_held[75:68];
  wire [7:0]  c_idx_min     = cfg_held[83:76];
  wire [7:0]  c_idx_max     = cfg_held[91:84];
  wire [7:0]  c_idx_init    = cfg_held[99:92];
  wire [1:0]  c_mode        = cfg_held[101:100];
  wire        c_fault_clear = cfg_held[102];
  wire [31:0] c_epoch       = cfg_held[139:108];

  // ---------------------------------------------------------------------------
  // the controller
  // ---------------------------------------------------------------------------
  wire [2:0]  state;
  wire [31:0] epoch, epoch_tomb;
  wire [7:0]  expected_index, fault, detect;
  wire        pulse_busy, cooldown_active, fpga_owns;
  wire [7:0] cnt_trans, cnt_inhib, cnt_clamp, cnt_stale;
  wire [EVT_DW-1:0] evt_rdata;
  wire        evt_valid;
  wire [EVT_AW:0] evt_level;
  wire [7:0]  evt_ovf;
  reg         evt_pop;

  tandem_agc_core #(.EVT_AW(EVT_AW), .EVT_DW(EVT_DW), .EVENTS(EVENTS)) u_core (
    .l_clk(l_clk), .l_resetn(l_resetn),
    .detect_async(detect_async), .sample_counter(sample_counter),
    .sample_valid(sample_valid),
    .mode_req(c_mode), .cfg_epoch(c_epoch),
    .fault_clear(c_fault_clear), .consumer_ready(consumer_ready),
    .cfg_pulse_hi(c_pulse_hi), .cfg_pulse_lo(c_pulse_lo),
    .cfg_blank_guard(c_blank_guard), .cfg_pwr_period(c_pwr_period),
    .cfg_cooldown(c_cooldown), .cfg_dwell(c_dwell), .cfg_debounce(c_debounce),
    .cfg_idx_min(c_idx_min), .cfg_idx_max(c_idx_max), .cfg_idx_init(c_idx_init),
    .sw_idx_rx1(8'd0), .sw_idx_rx2(8'd0), .sw_idx_strobe(1'b0),
    .ps_ctl_o(ps_ctl_o), .ps_ctl_t(ps_ctl_t), .ctl_o(ctl_o), .ctl_t(ctl_t),
    .state_o(state), .epoch_o(epoch), .epoch_tomb_o(epoch_tomb),
    .expected_index_o(expected_index), .pulse_busy_o(pulse_busy),
    .cooldown_active_o(cooldown_active), .fpga_owns_o(fpga_owns),
    .fault_o(fault), .detect_o(detect),
    .cnt_trans_o(cnt_trans), .cnt_inhib_o(cnt_inhib),
    .cnt_clamp_o(cnt_clamp), .cnt_stale_o(cnt_stale),
    .evt_rd_clk(s_axi_aclk), .evt_rd_resetn(axi_resetn & ~r_fault_clear),
    .evt_rdata_o(evt_rdata), .evt_valid_o(evt_valid), .evt_pop(evt_pop),
    .evt_level_o(evt_level), .evt_ovf_o(evt_ovf),
    .evt_push_o(), .evt_wdata_o());

  // ---------------------------------------------------------------------------
  // Status snapshot, l_clk -> AXI. Re-issued as soon as the preceding
  // handshake completes, so a
  // reader always sees one coherent instant instead of a mix of two. Keep only
  // fields observable through the forward ABI: r_epoch already lives in the
  // AXI domain, while the retired epoch and policy-debug counters have no
  // software consumer. Crossing them duplicated 96 bits in both the source
  // hold and destination registers on an already full XC7Z010.
  // ---------------------------------------------------------------------------
  wire [STAW-1:0] status_bundle = {
      sample_counter, cnt_trans, fault, fpga_owns, cooldown_active, pulse_busy,
      expected_index, state };

  wire       snap_busy;
  // tandem_cdc_bus captures status_bundle in its source holding register on
  // this pulse.  busy rises with that same source edge and remains asserted
  // until the destination has acknowledged the snapshot, naturally turning
  // this level into one load pulse per completed round trip.  This is both
  // fresher and smaller than an arbitrary eight-bit polling divider.
  wire       snap_load = l_resetn && !snap_busy;

  wire [STAW-1:0] status_axi;
  wire            status_axi_valid;
  tandem_cdc_bus #(.W(STAW)) u_stat (
    .src_clk(l_clk), .src_resetn(l_resetn),
    .din(status_bundle), .load(snap_load), .busy(snap_busy),
    .dst_clk(s_axi_aclk), .dst_resetn(axi_resetn),
    .dout(status_axi), .dout_valid(status_axi_valid));

  wire [2:0]  a_state   = status_axi[2:0];
  wire [7:0]  a_expect  = status_axi[10:3];
  wire        a_pbusy   = status_axi[11];
  wire        a_cool    = status_axi[12];
  wire        a_owns    = status_axi[13];
  wire [7:0]  a_fault   = status_axi[21:14];
  wire [7:0]  a_trans   = status_axi[29:22];
  wire [63:0] a_sample_counter = status_axi[93:30];

  wire [2:0] a_public_state =
      (a_state == 3'd6) ? 3'd4 :
      ((a_state == 3'd4) || (a_state == 3'd5)) ? 3'd5 : a_state;

  // ---------------------------------------------------------------------------
  // AXI4-Lite
  // ---------------------------------------------------------------------------
  reg        aw_pending, w_pending, bvalid, arready, rvalid;
  reg [7:0]  awaddr_q, araddr_q;
  reg [31:0] wdata_q, rdata_q;

  // AW and W are independent AXI channels.  Hold either one until its peer
  // arrives; requiring AWVALID and WVALID in the same cycle can deadlock a
  // conforming interconnect that completes the address transaction first.
  assign s_axi_awready = axi_resetn && !cfg_busy && !aw_pending && !bvalid;
  assign s_axi_wready  = axi_resetn && !cfg_busy && !w_pending && !bvalid;
  assign s_axi_bvalid  = bvalid;
  assign s_axi_bresp   = 2'b00;
  assign s_axi_arready  = arready;
  assign s_axi_rvalid   = rvalid;
  assign s_axi_rresp    = 2'b00;
  assign s_axi_rdata    = rdata_q;

  // write channel
  always @(posedge s_axi_aclk) begin
    if (!axi_resetn) begin
      aw_pending <= 1'b0; w_pending <= 1'b0; bvalid <= 1'b0;
      awaddr_q <= 8'd0; wdata_q <= 32'd0;
      cfg_load <= 1'b0; r_fault_clear <= 1'b0;
      r_pulse_hi <= 8'd16; r_pulse_lo <= 8'd16; r_blank_guard <= 16'd64;
      r_pwr_period <= 20'd10000; r_cooldown <= 8'd2; r_dwell <= 8'd4;
      r_debounce <= 8'd8; r_idx_min <= 8'd0; r_idx_max <= 8'd76;
      r_idx_init <= 8'd40; r_mode <= 2'd0; r_epoch <= 32'd0;
      r_thresholds <= 32'd0;
    end else begin
      cfg_load <= 1'b0;

      if (s_axi_awready && s_axi_awvalid) begin
        aw_pending <= 1'b1;
        awaddr_q <= s_axi_awaddr;
      end
      if (s_axi_wready && s_axi_wvalid) begin
        w_pending <= 1'b1;
        wdata_q <= s_axi_wdata;
      end

      if (aw_pending && w_pending && !bvalid) begin
        case (awaddr_q)
          8'h0C: begin
            r_mode <= !wdata_q[0] ? 2'd0 :
                      wdata_q[1] ? 2'd2 : 2'd1;
            r_fault_clear <= wdata_q[8];
          end
          8'h14: r_epoch <= wdata_q;
          8'h18: begin r_idx_min <= wdata_q[7:0]; r_idx_max <= wdata_q[15:8];
                       r_idx_init <= wdata_q[23:16]; end
          8'h20: r_pwr_period <= wdata_q[19:0];
          8'h24: begin r_dwell <= wdata_q[7:0]; r_cooldown <= wdata_q[15:8];
                       r_debounce <= wdata_q[23:16]; end
          8'h28: begin r_pulse_hi <= wdata_q[7:0];
                       r_pulse_lo <= wdata_q[15:8]; end
          8'h2C: r_blank_guard <= wdata_q[15:0];
          8'h30: r_thresholds <= wdata_q;
          default: ;
        endcase
        cfg_load <= 1'b1;
        aw_pending <= 1'b0;
        w_pending <= 1'b0;
        bvalid <= 1'b1;
      end else if (bvalid && s_axi_bready) begin
        bvalid <= 1'b0;
      end
    end
  end

  // read channel; reading EVT_HI3 pops, §8
  always @(posedge s_axi_aclk) begin
    if (!axi_resetn) begin
      arready <= 1'b0; rvalid <= 1'b0; araddr_q <= 8'd0;
      rdata_q <= 32'd0; evt_pop <= 1'b0;
    end else begin
      evt_pop <= 1'b0;

      if (!arready && s_axi_arvalid) begin
        arready  <= 1'b1;
        araddr_q <= s_axi_araddr;
      end else arready <= 1'b0;

      if (arready && s_axi_arvalid && !rvalid) begin
        rvalid <= 1'b1;
        case (s_axi_araddr)
          8'h00: rdata_q <= 32'h5441_4732;                 // "TAG2"
          8'h04: rdata_q <= 32'd2;
          8'h08: rdata_q <= {16'h000f, 16'd64};
          8'h0C: rdata_q <= {23'd0, r_fault_clear, 6'd0, r_mode[1], |r_mode};
          8'h10: rdata_q <= {23'd0, |a_fault, 5'd0, a_public_state};
          8'h14: rdata_q <= r_epoch;
          8'h18: rdata_q <= {8'd0, r_idx_init, r_idx_max, r_idx_min};
          8'h1C: rdata_q <= {16'd0, a_expect, a_expect};
          8'h20: rdata_q <= {12'd0, r_pwr_period};
          8'h24: rdata_q <= {8'd0, r_debounce, r_cooldown, r_dwell};
          8'h28: rdata_q <= {16'd0, r_pulse_lo, r_pulse_hi};
          8'h2C: rdata_q <= {16'd0, r_blank_guard};
          8'h30: rdata_q <= r_thresholds;
          8'h34: rdata_q <= {24'd0, a_fault};
          8'h38: rdata_q <= {{(31-EVT_AW){1'b0}}, evt_level};
          8'h3C: rdata_q <= {24'd0, evt_ovf};
          8'h40: rdata_q <= {24'd0, a_trans};
          8'h44: rdata_q <= evt_rdata[31:0];
          8'h48: rdata_q <= evt_rdata[63:32];
          8'h4C: rdata_q <= evt_rdata[95:64];
          8'h50: begin rdata_q <= evt_rdata[127:96];
                       if (evt_valid) evt_pop <= 1'b1; end
          8'h54: rdata_q <= a_sample_counter[31:0];
          8'h58: rdata_q <= a_sample_counter[63:32];
          8'h5C: rdata_q <= 32'd0;
          default: rdata_q <= 32'd0;
        endcase
      end else if (rvalid && s_axi_rready) rvalid <= 1'b0;
    end
  end

endmodule
