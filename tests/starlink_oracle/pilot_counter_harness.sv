`timescale 1ns/1ps
module pilot_counter_harness #(
  parameter integer PAIRED = 0
);
  reg clk = 0;
  always #5 clk = ~clk;
  reg resetn = 0;
  axi_starlink_pss_acquisition #(
    .INPUT_RATE_MSPS(30), .ENABLE_PILOT_TAP(PAIRED)
  ) dut (
    .sample_clk(clk), .fft_clk(clk), .fft_resetn(resetn), .sample_reset(!resetn),
    .sample_strobe(1'b0), .sample_enable(1'b0), .sample_gap(1'b0),
    .sample_i(16'd0), .sample_q(16'd0), .sample_index(64'd0),
    .pilot_enable(1'b1), .s_axi_aclk(clk), .s_axi_aresetn(resetn),
    .s_axi_awvalid(1'b0), .s_axi_awaddr(8'd0), .s_axi_wvalid(1'b0),
    .s_axi_wdata(32'd0), .s_axi_wstrb(4'd0), .s_axi_bready(1'b0),
    .s_axi_arvalid(1'b0), .s_axi_araddr(8'd0), .s_axi_rready(1'b0),
    .s_axi_awprot(3'd0), .s_axi_arprot(3'd0)
  );
  reg [63:0] want;
  integer n;
  initial begin
    if (dut.g_rate_30.acquisition_ddc.WIDE_OBSERVATION_COUNTERS != PAIRED)
      $fatal(1, "paired-only wide-counter selection is wrong");
    repeat (3) @(negedge clk);
    resetn = 1;
    force dut.conditioner_enable = 1'b1;
    force dut.ingress_sample_valid = 1'b1;
    force dut.g_rate_30.acquisition_ddc.quantized_valid = 1'b1;
    dut.g_rate_30.acquisition_ddc.accepted_sample_count = 64'hfffffffd;
    dut.g_rate_30.acquisition_ddc.emitted_sample_count = 64'hfffffffd;
    want = 64'hfffffffd;
    for (n = 0; n < 8; n = n + 1) begin
      @(posedge clk); #1;
      if (PAIRED || want != 64'hffffffff) want = want + 1;
      if (dut.ddc_accepted_sample_count !== want || dut.ddc_emitted_sample_count !== want)
        $fatal(1, "observation counters disagree at 32-bit boundary");
    end
    @(negedge clk);
    force dut.acquisition_flush = 1'b1;
    repeat (3) @(negedge clk);
    if (dut.ddc_accepted_sample_count !== want || dut.ddc_emitted_sample_count !== want)
      $fatal(1, "flush erased cumulative counts");
    release dut.acquisition_flush;
    if (PAIRED) begin
      dut.g_rate_30.acquisition_ddc.accepted_sample_count = 64'hfffffffffffffffe;
      dut.g_rate_30.acquisition_ddc.emitted_sample_count = 64'hfffffffffffffffe;
      repeat (3) @(negedge clk);
      if (dut.ddc_accepted_sample_count !== 64'hffffffffffffffff ||
          dut.ddc_emitted_sample_count !== 64'hffffffffffffffff)
        $fatal(1, "wide counters wrapped instead of saturating");
    end
    $display("PILOT_COUNTER_WIDTH_PASS paired=%0d", PAIRED);
    $finish;
  end
endmodule
