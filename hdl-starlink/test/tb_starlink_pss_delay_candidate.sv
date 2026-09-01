`timescale 1ns/1ps

module tb_starlink_pss_delay_candidate;

  parameter integer RATE_MSPS = 15;

  localparam integer DELAY_SAMPLES =
      (RATE_MSPS == 60) ? 32 : ((RATE_MSPS == 30) ? 16 : 8);
  localparam integer CYCLIC_PREFIX_SAMPLES =
      (RATE_MSPS == 60) ? 8 : ((RATE_MSPS == 30) ? 4 : 2);
  localparam integer SYMBOL_SAMPLES =
      (RATE_MSPS == 60) ? 264 : ((RATE_MSPS == 30) ? 132 : 66);
  localparam integer OUTPUT_LATENCY = 2;

  reg                    clk = 1'b0;
  reg                    reset_n = 1'b0;
  reg signed [15:0]      in_i = 16'sd0;
  reg signed [15:0]      in_q = 16'sd0;
  reg                    in_valid = 1'b0;
  reg [63:0]             in_sample_index = 64'd0;

  wire                   candidate_valid;
  wire [63:0]            candidate_sample_index;
  wire [82:0]            candidate_metric_num;
  wire [81:0]            candidate_metric_den;

  integer event_count;
  reg [63:0] last_event_index;
  reg [31:0] noise_state;
  integer n;
  integer k;
  integer expected_i;
  integer expected_q;

  always #5 clk = ~clk;

  starlink_pss_delay_candidate #(
    .RATE_MSPS(RATE_MSPS),
    .THRESHOLD_Q15(24576),
    .MIN_WINDOW_ENERGY(41'd1)
  ) dut (
    .clk(clk),
    .reset_n(reset_n),
    .in_i(in_i),
    .in_q(in_q),
    .in_valid(in_valid),
    .in_sample_index(in_sample_index),
    .candidate_valid(candidate_valid),
    .candidate_sample_index(candidate_sample_index),
    .candidate_metric_num(candidate_metric_num),
    .candidate_metric_den(candidate_metric_den)
  );

  function integer base_i;
    input integer position;
    begin
      case (position % 8)
        0: base_i =  12000;
        1: base_i =   5000;
        2: base_i =  -9000;
        3: base_i = -13000;
        4: base_i =  -6000;
        5: base_i =   8000;
        6: base_i =  14000;
        default: base_i = 3000;
      endcase
    end
  endfunction

  function integer base_q;
    input integer position;
    begin
      case (position % 8)
        0: base_q =   3000;
        1: base_q =  13000;
        2: base_q =  10000;
        3: base_q =  -2000;
        4: base_q = -12000;
        5: base_q = -10000;
        6: base_q =   4000;
        default: base_q = 15000;
      endcase
    end
  endfunction

  // Synthetic structural PSS: eight useful repetitions and the published
  // inverted-prefix rule used by the golden oracle.
  function integer pss_i;
    input integer position;
    integer base_position;
    begin
      if (position < CYCLIC_PREFIX_SAMPLES) begin
        base_position = DELAY_SAMPLES - CYCLIC_PREFIX_SAMPLES + position;
        pss_i = -base_i(base_position);
      end else begin
        base_position = (position - CYCLIC_PREFIX_SAMPLES) % DELAY_SAMPLES;
        pss_i = base_i(base_position);
      end
    end
  endfunction

  function integer pss_q;
    input integer position;
    integer base_position;
    begin
      if (position < CYCLIC_PREFIX_SAMPLES) begin
        base_position = DELAY_SAMPLES - CYCLIC_PREFIX_SAMPLES + position;
        pss_q = -base_q(base_position);
      end else begin
        base_position = (position - CYCLIC_PREFIX_SAMPLES) % DELAY_SAMPLES;
        pss_q = base_q(base_position);
      end
    end
  endfunction

  // A deterministic, non-PSS code with period D+1.  Its lag-D products do not
  // add coherently over a Starlink-sized window.
  function integer wrong_i;
    input integer position;
    integer code_position;
    begin
      code_position = position % (DELAY_SAMPLES + 1);
      case (((code_position * code_position * 3) +
             (code_position * 11) + 5) % 8)
        0: wrong_i =  11000;
        1: wrong_i = -11000;
        2: wrong_i =   4000;
        3: wrong_i =  -4000;
        4: wrong_i =   9000;
        5: wrong_i =  -9000;
        6: wrong_i =   2000;
        default: wrong_i = -2000;
      endcase
    end
  endfunction

  function integer wrong_q;
    input integer position;
    integer code_position;
    begin
      code_position = position % (DELAY_SAMPLES + 1);
      case (((code_position * code_position * 5) +
             (code_position * 7) + 3) % 8)
        0: wrong_q =  -3000;
        1: wrong_q =  13000;
        2: wrong_q = -13000;
        3: wrong_q =   6000;
        4: wrong_q =  -6000;
        5: wrong_q =  10000;
        6: wrong_q = -10000;
        default: wrong_q = 3000;
      endcase
    end
  endfunction

  task account_candidate;
    reg [97:0] threshold_left;
    reg [97:0] threshold_right;
    begin
      if (candidate_valid) begin
        event_count = event_count + 1;
        last_event_index = candidate_sample_index;
        if (candidate_metric_den == 0)
          $fatal(1, "rate %0d: candidate carried a zero metric denominator",
                 RATE_MSPS);
        if (candidate_metric_num > {1'b0, candidate_metric_den})
          $fatal(1, "rate %0d: normalized metric exceeded one", RATE_MSPS);
        threshold_left = {candidate_metric_num, 15'd0};
        threshold_right = candidate_metric_den * 16'd24576;
        if (threshold_left < threshold_right)
          $fatal(1, "rate %0d: candidate metric is below threshold", RATE_MSPS);
      end
    end
  endtask

  task drive_sample;
    input integer sample_i;
    input integer sample_q;
    input [63:0] sample_index;
    input integer sample_valid;
    begin
      @(negedge clk);
      in_i = sample_i;
      in_q = sample_q;
      in_sample_index = sample_index;
      in_valid = sample_valid[0];
      @(posedge clk);
      #1;
      account_candidate();
    end
  endtask

  task reset_detector;
    begin
      @(negedge clk);
      reset_n = 1'b0;
      in_valid = 1'b0;
      in_i = 16'sd0;
      in_q = 16'sd0;
      repeat (3) @(posedge clk);
      #1;
      if (candidate_valid || candidate_sample_index != 0 ||
          candidate_metric_num != 0 || candidate_metric_den != 0)
        $fatal(1, "rate %0d: reset outputs are not fail-safe", RATE_MSPS);
      @(negedge clk);
      reset_n = 1'b1;
      event_count = 0;
      last_event_index = 64'd0;
    end
  endtask

  task require_no_candidate;
    input [8*32-1:0] scenario;
    begin
      if (event_count != 0)
        $fatal(1, "rate %0d: unexpected candidate in %0s", RATE_MSPS,
               scenario);
    end
  endtask

  initial begin
    event_count = 0;
    last_event_index = 64'd0;
    noise_state = 32'h1ace_b00c ^ RATE_MSPS;

    // Zero energy must not satisfy the mathematically true 0 >= 0 comparison.
    reset_detector();
    for (n = 0; n < (SYMBOL_SAMPLES * 2); n = n + 1)
      drive_sample(0, 0, 64'd1000 + n, 1);
    require_no_candidate("zero-energy input");

    // Deterministic wideband-like noise is not delay coherent.
    reset_detector();
    for (n = 0; n < (SYMBOL_SAMPLES * 4); n = n + 1) begin
      noise_state = {noise_state[30:0],
                     noise_state[31] ^ noise_state[21] ^
                     noise_state[1] ^ noise_state[0]};
      expected_i = $signed(noise_state[15:0]) >>> 2;
      noise_state = {noise_state[30:0],
                     noise_state[31] ^ noise_state[21] ^
                     noise_state[1] ^ noise_state[0]};
      expected_q = $signed(noise_state[15:0]) >>> 2;
      drive_sample(expected_i, expected_q, 64'd10000 + n, 1);
    end
    require_no_candidate("deterministic noise");

    // A strong wrong-period waveform must not pass merely because it has
    // plenty of energy.
    reset_detector();
    for (n = 0; n < (SYMBOL_SAMPLES * 3); n = n + 1)
      drive_sample(wrong_i(n), wrong_q(n), 64'd20000 + n, 1);
    require_no_candidate("wrong-period waveform");

    // Two almost-complete PSS fragments separated by one invalid beat must
    // not be joined into a complete correlation window.
    reset_detector();
    for (n = 0; n < (SYMBOL_SAMPLES - 1); n = n + 1)
      drive_sample(pss_i(n), pss_q(n), 64'd30000 + n, 1);
    drive_sample(0, 0, 64'd30000 + SYMBOL_SAMPLES - 1, 0);
    for (n = 0; n < (SYMBOL_SAMPLES - 1); n = n + 1)
      drive_sample(pss_i(n), pss_q(n), 64'd30000 + SYMBOL_SAMPLES + n, 1);
    require_no_candidate("valid-gap fragments");

    // A sample-index jump is the same hard boundary even when valid stays high.
    reset_detector();
    for (n = 0; n < (SYMBOL_SAMPLES / 2); n = n + 1)
      drive_sample(pss_i(n), pss_q(n), 64'd40000 + n, 1);
    for (k = 0; k < (SYMBOL_SAMPLES - 1); k = k + 1)
      drive_sample(pss_i(k), pss_q(k), 64'd50000 + k, 1);
    require_no_candidate("sample-index discontinuity");

    // One complete structural PSS must produce one event after the documented
    // pipeline delay. The timestamp is compensated back to the symbol start.
    reset_detector();
    for (n = 0; n < SYMBOL_SAMPLES; n = n + 1) begin
      drive_sample(pss_i(n), pss_q(n),
                   64'd1000000 + (RATE_MSPS * 1000) + n, 1);
      if (candidate_valid)
        $fatal(1, "rate %0d: candidate arrived before pipeline completion",
               RATE_MSPS);
    end
    // Two further contiguous beats drain the registered metric pipeline.
    for (n = 0; n < OUTPUT_LATENCY; n = n + 1) begin
      drive_sample(base_i(n), base_q(n),
                   64'd1000000 + (RATE_MSPS * 1000) + SYMBOL_SAMPLES + n, 1);
      if (candidate_valid && (n != (OUTPUT_LATENCY - 1)))
        $fatal(1, "rate %0d: candidate pipeline latency changed", RATE_MSPS);
    end
    if (event_count != 1)
      $fatal(1, "rate %0d: expected one positive candidate, got %0d",
             RATE_MSPS, event_count);
    if (last_event_index != (64'd1000000 + (RATE_MSPS * 1000)))
      $fatal(1, "rate %0d: symbol-start timestamp mismatch: got %0d",
             RATE_MSPS, last_event_index);

    // Extending the same coherent run does not create a pulse storm.
    for (n = OUTPUT_LATENCY; n < (DELAY_SAMPLES + OUTPUT_LATENCY); n = n + 1)
      drive_sample(base_i(n), base_q(n),
                   64'd1000000 + (RATE_MSPS * 1000) + SYMBOL_SAMPLES + n, 1);
    if (event_count != 1)
      $fatal(1, "rate %0d: detector retriggered without falling below threshold",
             RATE_MSPS);

    $display("PASS RATE_MSPS=%0d D=%0d SYMBOL=%0d", RATE_MSPS,
             DELAY_SAMPLES, SYMBOL_SAMPLES);
    $finish;
  end

endmodule
