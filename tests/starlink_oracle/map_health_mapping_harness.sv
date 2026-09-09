// Exercise the actual synchronous PSMA snapshot/register source mapping.
// This is control RTL simulation, not map arithmetic, timing closure or RF.
`timescale 1ns/1ps
module map_health_mapping_harness #(
  parameter integer INPUT_RATE_MSPS = 15,
  parameter integer USE_SHARED_XFFT = 0
);
  reg clk = 0;
  always #5 clk = !clk;
  reg resetn = 0;
  reg [31:0] tag = 32'h12340000;
  reg [31:0] health = 32'h00004001;
  reg [1:0] ready = 2;
  reg [63:0] ddc_accepted = 64'h00000001fffffffd;
  reg [63:0] ddc_emitted = 64'h00000004fffffffe;
  reg [31:0] ddc_discontinuity = 7;
  reg [31:0] ddc_saturation = 0;
  reg awvalid = 0, wvalid = 0, bready = 0, arvalid = 0, rready = 0;
  reg [7:0] awaddr = 0, araddr = 0;
  reg [31:0] wdata = 0;
  wire awready, wready, bvalid, arready, rvalid;
  wire [1:0] bresp, rresp;
  wire [31:0] rdata;

  axi_starlink_pss_phase_map_sync #(
    .INPUT_RATE_MSPS(INPUT_RATE_MSPS), .USE_SHARED_XFFT(USE_SHARED_XFFT)
  ) dut (
    .map_clk(clk), .map_reset(!resetn),
    .map_ready_mask(ready),
    .map_generation_0(tag | 32'h40), .map_generation_1(tag | 32'h44),
    .map_start_index_0({tag | 32'h4c, tag | 32'h48}),
    .map_start_index_1({tag | 32'h54, tag | 32'h50}),
    .map_read_valid(1'b0), .map_read_data(16'd0), .map_read_error(1'b0),
    .accepted_score_count(tag | 32'h58),
    .discarded_score_count(tag | 32'h5c),
    .discontinuity_abort_count(tag | 32'h60),
    .map_publish_count(tag | 32'h64),
    .map_overrun_count(tag | 32'h68),
    .score_protocol_error_count(tag | 32'h6c),
    .map_arithmetic_overflow_count(tag | 32'h70),
    .map_read_error_count(tag | 32'h74),
    .map_release_error_count(tag | 32'h78),
    .detector_health_flags(health), .ingress_overflow_sticky(1'b1),
    .ingress_dropped_sample_count(tag | 32'h8c),
    .ingress_fifo_level(16'h1234), .ingress_maximum_fifo_level(16'h5678),
    .scheduler_gap_count(tag | 32'h94),
    .scheduler_index_error_count(tag | 32'h98),
    .scheduler_overflow_count(tag | 32'h9c),
    .detector_fault_count(tag | 32'ha0),
    .score_phase_index_discontinuity_count(tag | 32'ha4),
    .score_denominator_zero_count(tag | 32'ha8),
    .candidate_fifo_stored_count(10'h123),
    .candidate_fifo_maximum_stored_count(10'h234),
    .ddc_accepted_sample_count(ddc_accepted),
    .ddc_emitted_sample_count(ddc_emitted),
    .ddc_discontinuity_count(ddc_discontinuity),
    .ddc_saturation_event_count(ddc_saturation),
    .s_axi_aclk(clk), .s_axi_aresetn(resetn),
    .s_axi_awvalid(awvalid), .s_axi_awaddr(awaddr), .s_axi_awready(awready),
    .s_axi_wvalid(wvalid), .s_axi_wdata(wdata), .s_axi_wstrb(4'hf),
    .s_axi_wready(wready), .s_axi_bvalid(bvalid), .s_axi_bresp(bresp),
    .s_axi_bready(bready), .s_axi_arvalid(arvalid), .s_axi_araddr(araddr),
    .s_axi_arready(arready), .s_axi_rvalid(rvalid), .s_axi_rresp(rresp),
    .s_axi_rdata(rdata), .s_axi_rready(rready),
    .s_axi_awprot(3'd0), .s_axi_arprot(3'd0)
  );

  task automatic read_expect(input [7:0] address, input [31:0] expected);
    integer count;
    begin
      @(negedge clk);
      araddr = address;
      arvalid = 1;
      rready = 1;
      count = 0;
      while (!arready && count < 100) begin
        @(posedge clk);
        count = count + 1;
      end
      if (count == 100) $fatal(1, "read address timeout");
      @(negedge clk);
      arvalid = 0;
      count = 0;
      while (!rvalid && count < 100) begin
        @(posedge clk);
        count = count + 1;
      end
      if (count == 100 || rresp != 0) $fatal(1, "read response timeout/error");
      if (rdata !== expected)
        $fatal(1, "register %02x actual=%08x expected=%08x", address, rdata, expected);
      @(negedge clk);
      rready = 0;
    end
  endtask

  task automatic snapshot;
    integer count;
    begin
      @(negedge clk);
      awaddr = 8'h30;
      wdata = 1;
      awvalid = 1;
      wvalid = 1;
      bready = 1;
      count = 0;
      while (!(awready && wready) && count < 100) begin
        @(posedge clk);
        count = count + 1;
      end
      if (count == 100) $fatal(1, "write address timeout");
      @(negedge clk);
      awvalid = 0;
      wvalid = 0;
      count = 0;
      while (!bvalid && count < 100) begin
        @(posedge clk);
        count = count + 1;
      end
      if (count == 100 || bresp != 0) $fatal(1, "write response timeout/error");
      @(negedge clk);
      bready = 0;
      repeat (4) @(posedge clk);
      read_expect(8'h34, 1);
    end
  endtask

  task automatic expect_frozen(input [31:0] expected_tag,
    input [31:0] expected_health, input [31:0] expected_ready);
    integer address;
    begin
      read_expect(8'h3c, expected_ready);
      for (address = 'h40; address <= 'h78; address = address + 4)
        read_expect(address[7:0], expected_tag | address);
      read_expect(8'h88, expected_health);
      read_expect(8'h8c, expected_tag | 32'h8c);
      read_expect(8'h90, 32'h56781234);
      for (address = 'h94; address <= 'ha8; address = address + 4)
        read_expect(address[7:0], expected_tag | address);
      read_expect(8'hac, 32'h02340123);
    end
  endtask

  task automatic expect_live_ddc;
    begin
      read_expect(8'he0, INPUT_RATE_MSPS != 15 ? ddc_accepted[31:0] : 0);
      read_expect(8'he4, INPUT_RATE_MSPS != 15 ? ddc_emitted[31:0] : 0);
      read_expect(8'he8, INPUT_RATE_MSPS != 15 ? ddc_discontinuity : 0);
      read_expect(8'hec, INPUT_RATE_MSPS != 15 ? ddc_saturation : 0);
      read_expect(8'hf0, INPUT_RATE_MSPS == 60 ? ddc_accepted[63:32] : 0);
      read_expect(8'hf4, INPUT_RATE_MSPS == 60 ? ddc_emitted[63:32] : 0);
    end
  endtask

  initial begin
    repeat (5) @(posedge clk);
    @(negedge clk);
    resetn = 1;
    repeat (4) @(posedge clk);
    read_expect(8'h04, USE_SHARED_XFFT ? 32'h00010005 :
      INPUT_RATE_MSPS == 60 ? 32'h00010004 :
      INPUT_RATE_MSPS == 30 ? 32'h00010002 : 32'h00010001);
    read_expect(8'hb0, INPUT_RATE_MSPS);
    snapshot();
    read_expect(8'h38, 1);
    expect_frozen(32'h12340000, 32'h00005001, 2);
    expect_live_ddc();

    // Update every source and introduce clipping AFTER the completed snapshot.
    // DDC registers change immediately, but frozen health/map words must not.
    @(negedge clk);
    tag = 32'h56780000;
    health = 32'h00004002;
    ready = 0;
    ddc_accepted = 64'h0000000200000007;
    ddc_emitted = 64'h0000000500000009;
    ddc_discontinuity = 8;
    ddc_saturation = 1;
    repeat (4) @(posedge clk);
    expect_frozen(32'h12340000, 32'h00005001, 2);
    expect_live_ddc();
    read_expect(8'h38, 1);
    snapshot();
    read_expect(8'h38, 2);
    expect_frozen(32'h56780000,
      INPUT_RATE_MSPS != 15 ? 32'h00007002 : 32'h00005002, 0);
    expect_live_ddc();
    $display("MAP_HEALTH_MAPPING_PASS rate=%0d shared=%0d", INPUT_RATE_MSPS, USE_SHARED_XFFT);
    $finish;
  end
  initial begin
    #200000;
    $fatal(1, "mapping test exceeded deadline");
  end
endmodule
