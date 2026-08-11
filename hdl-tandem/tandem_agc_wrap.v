// Synthesis wrapper: register file + controller, the unit that integrates into
// the block design. An AXI4-Lite slave attaches to the reg_* port at Stage 3.
`timescale 1ns/1ps
module tandem_agc_wrap (
  input wire l_clk, input wire l_resetn,
  input wire [7:0] detect_async, input wire [63:0] sample_counter,
  input wire [7:0] reg_addr, input wire [31:0] reg_wdata,
  input wire reg_wr, input wire reg_rd, output wire [31:0] reg_rdata,
  input wire consumer_ready,
  input wire [7:0] sw_idx_rx1, input wire [7:0] sw_idx_rx2, input wire sw_idx_strobe,
  input wire [3:0] ps_ctl_o, input wire [3:0] ps_ctl_t,
  output wire [3:0] ctl_o, output wire [3:0] ctl_t);

  wire [1:0] mode_req; wire fault_clear;
  wire [7:0] ph, pl, cd, dw, db, imin, imax, iinit;
  wire [15:0] bg; wire [31:0] pp;
  wire [2:0] state; wire [7:0] epoch, tomb, exp_idx, fault, det;
  wire pb, ca, owns;
  wire [31:0] c_tr, c_in, c_cl, c_st, e_ovf;
  wire [127:0] e_rd; wire e_val, e_pop; wire [8:0] e_lvl;

  tandem_agc_regs u_regs (.l_clk(l_clk), .l_resetn(l_resetn),
    .reg_addr(reg_addr), .reg_wdata(reg_wdata), .reg_wr(reg_wr), .reg_rd(reg_rd),
    .reg_rdata(reg_rdata), .mode_req(mode_req), .fault_clear(fault_clear),
    .cfg_pulse_hi(ph), .cfg_pulse_lo(pl), .cfg_blank_guard(bg),
    .cfg_pwr_period(pp), .cfg_cooldown(cd), .cfg_dwell(dw), .cfg_debounce(db),
    .cfg_idx_min(imin), .cfg_idx_max(imax), .cfg_idx_init(iinit),
    .state(state), .epoch(epoch), .epoch_tomb(tomb), .expected_index(exp_idx),
    .pulse_busy(pb), .cooldown_active(ca), .fpga_owns(owns), .fault(fault),
    .detect(det), .cnt_trans(c_tr), .cnt_inhib(c_in), .cnt_clamp(c_cl),
    .cnt_stale(c_st), .evt_rdata(e_rd), .evt_valid(e_val), .evt_level(e_lvl),
    .evt_ovf(e_ovf), .evt_pop(e_pop));

  tandem_agc_core u_core (.l_clk(l_clk), .l_resetn(l_resetn),
    .detect_async(detect_async), .sample_counter(sample_counter),
    .mode_req(mode_req), .fault_clear(fault_clear), .consumer_ready(consumer_ready),
    .cfg_pulse_hi(ph), .cfg_pulse_lo(pl), .cfg_blank_guard(bg),
    .cfg_pwr_period(pp), .cfg_cooldown(cd), .cfg_dwell(dw), .cfg_debounce(db),
    .cfg_idx_min(imin), .cfg_idx_max(imax), .cfg_idx_init(iinit),
    .sw_idx_rx1(sw_idx_rx1), .sw_idx_rx2(sw_idx_rx2), .sw_idx_strobe(sw_idx_strobe),
    .ps_ctl_o(ps_ctl_o), .ps_ctl_t(ps_ctl_t), .ctl_o(ctl_o), .ctl_t(ctl_t),
    .state_o(state), .epoch_o(epoch), .epoch_tomb_o(tomb),
    .expected_index_o(exp_idx), .pulse_busy_o(pb), .cooldown_active_o(ca),
    .fpga_owns_o(owns), .fault_o(fault), .detect_o(det),
    .cnt_trans_o(c_tr), .cnt_inhib_o(c_in), .cnt_clamp_o(c_cl), .cnt_stale_o(c_st),
    .evt_rdata_o(e_rd), .evt_valid_o(e_val), .evt_pop(e_pop),
    .evt_level_o(e_lvl), .evt_ovf_o(e_ovf));
endmodule
