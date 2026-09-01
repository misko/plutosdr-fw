// -----------------------------------------------------------------------------
// starlink_pss_delay_candidate.v
//
// Experimental RX-only first-stage Starlink PSS candidate detector.
//
// This block intentionally performs only the inexpensive repeated-delay test.
// It does not claim a PSS match; an exact PSS correlator must qualify the
// candidates emitted here.
// -----------------------------------------------------------------------------

`timescale 1ns/1ps

module starlink_pss_delay_candidate #(
  // The only supported compile-time modes are 15, 30, and 60 MS/s.
  parameter integer RATE_MSPS = 15,

  // Q1.15 threshold for |P|^2 / (E0*E1).  24576 is 0.75.
  parameter integer THRESHOLD_Q15 = 24576,

  // Both sides of the delayed window must meet this energy floor.  The
  // default rejects an all-zero window without imposing an ADC-scale policy.
  parameter [40:0] MIN_WINDOW_ENERGY = 41'd1
) (
  input  wire                    clk,
  input  wire                    reset_n,

  input  wire signed [15:0]      in_i,
  input  wire signed [15:0]      in_q,
  input  wire                    in_valid,
  input  wire [63:0]             in_sample_index,

  // One-cycle pulse on the first qualifying window of a threshold excursion.
  output reg                     candidate_valid,

  // Stable reference: inferred first sample of the PSS symbol, modulo 2^64.
  output reg [63:0]              candidate_sample_index,

  // The normalized metric is represented exactly as the unsigned fraction
  // candidate_metric_num / candidate_metric_den.  No divider is inferred.
  output reg [82:0]              candidate_metric_num,
  output reg [81:0]              candidate_metric_den
);

  localparam integer RATE_IS_VALID =
      (RATE_MSPS == 15) || (RATE_MSPS == 30) || (RATE_MSPS == 60);
  localparam integer DELAY_SAMPLES =
      (RATE_MSPS == 60) ? 32 : ((RATE_MSPS == 30) ? 16 : 8);
  localparam integer SYMBOL_SAMPLES =
      (RATE_MSPS == 60) ? 264 : ((RATE_MSPS == 30) ? 132 : 66);
  localparam integer CORRELATION_SAMPLES = SYMBOL_SAMPLES - DELAY_SAMPLES;
  localparam [63:0] SYMBOL_MINUS_ONE = SYMBOL_SAMPLES - 1;

  // Delay memory.  The energy travels with the CI16 sample so the datapath
  // needs two input squarers, rather than recomputing delayed energy.
  reg signed [15:0] delay_i_mem [0:DELAY_SAMPLES-1];
  reg signed [15:0] delay_q_mem [0:DELAY_SAMPLES-1];
  reg        [31:0] delay_energy_mem [0:DELAY_SAMPLES-1];
  reg         [5:0] delay_write_pointer;
  reg         [5:0] delay_count;

  // Sliding-window memories contain one complex delayed product and the two
  // energies for each accepted sample pair.
  reg signed [32:0] product_re_mem [0:CORRELATION_SAMPLES-1];
  reg signed [32:0] product_im_mem [0:CORRELATION_SAMPLES-1];
  reg        [31:0] current_energy_mem [0:CORRELATION_SAMPLES-1];
  reg        [31:0] delayed_energy_mem [0:CORRELATION_SAMPLES-1];
  reg         [7:0] correlation_write_pointer;
  reg         [8:0] correlation_count;

  // Forty-one bits cover the largest 232-pair mode with conservative signed
  // headroom.  See hdl-starlink/README.md for the complete width derivation.
  reg signed [40:0] correlation_re_sum;
  reg signed [40:0] correlation_im_sum;
  reg        [40:0] current_energy_sum;
  reg        [40:0] delayed_energy_sum;

  reg                have_previous_index;
  reg [63:0]         previous_sample_index;
  reg                detector_armed;

  // The metric is pipelined independently of the sliding-sum update.  Stage 0
  // snapshots a complete window; stage 1 registers the three wide products.
  // Threshold comparison and candidate registration occupy the next cycle.
  reg                metric_stage0_valid;
  reg signed [40:0]  metric_stage0_correlation_re;
  reg signed [40:0]  metric_stage0_correlation_im;
  reg        [40:0]  metric_stage0_current_energy;
  reg        [40:0]  metric_stage0_delayed_energy;
  reg        [63:0]  metric_stage0_sample_index;

  reg                metric_stage1_valid;
  reg        [82:0]  metric_stage1_numerator;
  reg        [81:0]  metric_stage1_denominator;
  reg                metric_stage1_energy_ok;
  reg        [63:0]  metric_stage1_sample_index;

  wire signed [15:0] delayed_i = delay_i_mem[delay_write_pointer];
  wire signed [15:0] delayed_q = delay_q_mem[delay_write_pointer];
  wire        [31:0] delayed_sample_energy =
      delay_energy_mem[delay_write_pointer];

  wire signed [31:0] multiply_i_i = $signed(in_i) * $signed(delayed_i);
  wire signed [31:0] multiply_q_q = $signed(in_q) * $signed(delayed_q);
  wire signed [31:0] multiply_q_i = $signed(in_q) * $signed(delayed_i);
  wire signed [31:0] multiply_i_q = $signed(in_i) * $signed(delayed_q);

  // x[n] * conj(x[n-D])
  wire signed [32:0] product_re =
      {{1{multiply_i_i[31]}}, multiply_i_i} +
      {{1{multiply_q_q[31]}}, multiply_q_q};
  wire signed [32:0] product_im =
      {{1{multiply_q_i[31]}}, multiply_q_i} -
      {{1{multiply_i_q[31]}}, multiply_i_q};

  wire [31:0] input_i_square = $signed(in_i) * $signed(in_i);
  wire [31:0] input_q_square = $signed(in_q) * $signed(in_q);
  wire [32:0] input_energy_wide =
      {1'b0, input_i_square} + {1'b0, input_q_square};
  wire [31:0] input_sample_energy = input_energy_wide[31:0];

  wire signed [40:0] product_re_extended =
      {{8{product_re[32]}}, product_re};
  wire signed [40:0] product_im_extended =
      {{8{product_im[32]}}, product_im};
  wire        [40:0] current_energy_extended =
      {9'd0, input_sample_energy};
  wire        [40:0] delayed_energy_extended =
      {9'd0, delayed_sample_energy};

  wire signed [40:0] oldest_product_re_extended =
      {{8{product_re_mem[correlation_write_pointer][32]}},
       product_re_mem[correlation_write_pointer]};
  wire signed [40:0] oldest_product_im_extended =
      {{8{product_im_mem[correlation_write_pointer][32]}},
       product_im_mem[correlation_write_pointer]};
  wire        [40:0] oldest_current_energy_extended =
      {9'd0, current_energy_mem[correlation_write_pointer]};
  wire        [40:0] oldest_delayed_energy_extended =
      {9'd0, delayed_energy_mem[correlation_write_pointer]};

  wire correlation_window_full =
      (correlation_count == CORRELATION_SAMPLES);
  wire correlation_window_becomes_full =
      (correlation_count == (CORRELATION_SAMPLES - 1));

  wire signed [40:0] correlation_re_next =
      correlation_re_sum + product_re_extended -
      (correlation_window_full ? oldest_product_re_extended : 41'sd0);
  wire signed [40:0] correlation_im_next =
      correlation_im_sum + product_im_extended -
      (correlation_window_full ? oldest_product_im_extended : 41'sd0);
  wire        [40:0] current_energy_next =
      current_energy_sum + current_energy_extended -
      (correlation_window_full ? oldest_current_energy_extended : 41'd0);
  wire        [40:0] delayed_energy_next =
      delayed_energy_sum + delayed_energy_extended -
      (correlation_window_full ? oldest_delayed_energy_extended : 41'd0);

  wire [81:0] metric_stage0_correlation_re_square =
      $signed(metric_stage0_correlation_re) *
      $signed(metric_stage0_correlation_re);
  wire [81:0] metric_stage0_correlation_im_square =
      $signed(metric_stage0_correlation_im) *
      $signed(metric_stage0_correlation_im);
  wire [82:0] metric_stage0_numerator =
      {1'b0, metric_stage0_correlation_re_square} +
      {1'b0, metric_stage0_correlation_im_square};
  wire [81:0] metric_stage0_denominator =
      metric_stage0_current_energy * metric_stage0_delayed_energy;
  wire metric_stage0_energy_ok =
      (metric_stage0_current_energy >= MIN_WINDOW_ENERGY) &&
      (metric_stage0_delayed_energy >= MIN_WINDOW_ENERGY);

  // Comparing in Q1.15 form keeps normalization out of the datapath:
  //   |P|^2 * 32768 >= E0 * E1 * THRESHOLD_Q15
  wire [15:0] threshold_q15_value = THRESHOLD_Q15[15:0];
  wire [97:0] normalized_threshold_left =
      {metric_stage1_numerator, 15'd0};
  wire [97:0] normalized_threshold_right =
      metric_stage1_denominator * threshold_q15_value;
  wire metric_above_threshold =
      metric_stage1_valid && metric_stage1_energy_ok &&
      (normalized_threshold_left >= normalized_threshold_right);

  wire [63:0] next_expected_sample_index = previous_sample_index + 64'd1;
  wire sample_index_discontinuity =
      in_valid && have_previous_index &&
      (in_sample_index != next_expected_sample_index);
  wire [5:0] delay_store_pointer =
      sample_index_discontinuity ? 6'd0 : delay_write_pointer;

  // Keep storage writes out of the asynchronous-reset state process.  The
  // memories are validity-gated, so they require no reset values; this style
  // also permits Vivado to infer distributed RAM instead of resettable FFs.
  always @(posedge clk) begin
    if (reset_n && in_valid) begin
      delay_i_mem[delay_store_pointer]      <= in_i;
      delay_q_mem[delay_store_pointer]      <= in_q;
      delay_energy_mem[delay_store_pointer] <= input_sample_energy;

      if (!sample_index_discontinuity &&
          (delay_count >= DELAY_SAMPLES)) begin
        product_re_mem[correlation_write_pointer] <= product_re;
        product_im_mem[correlation_write_pointer] <= product_im;
        current_energy_mem[correlation_write_pointer] <=
            input_sample_energy;
        delayed_energy_mem[correlation_write_pointer] <=
            delayed_sample_energy;
      end
    end
  end

  // Elaboration checks prevent an accidental, silently approximated rate or
  // nonsensical threshold from becoming a hardware candidate.
  generate
    if (!RATE_IS_VALID) begin : g_invalid_rate
      initial begin
        $fatal(1, "RATE_MSPS must be exactly 15, 30, or 60");
      end
    end
    if ((THRESHOLD_Q15 < 1) || (THRESHOLD_Q15 > 32768)) begin : g_invalid_threshold
      initial begin
        $fatal(1, "THRESHOLD_Q15 must be in [1, 32768]");
      end
    end
  endgenerate

  // A low reset, invalid beat, or index discontinuity flushes all state that
  // can qualify a window.  Memory contents need not be reset: the count gates
  // ensure every entry is overwritten before it can be subtracted or scored.
  always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
      candidate_valid             <= 1'b0;
      candidate_sample_index      <= 64'd0;
      candidate_metric_num        <= 83'd0;
      candidate_metric_den        <= 82'd0;
      delay_write_pointer         <= 6'd0;
      delay_count                 <= 6'd0;
      correlation_write_pointer   <= 8'd0;
      correlation_count           <= 9'd0;
      correlation_re_sum          <= 41'sd0;
      correlation_im_sum          <= 41'sd0;
      current_energy_sum          <= 41'd0;
      delayed_energy_sum          <= 41'd0;
      have_previous_index         <= 1'b0;
      previous_sample_index       <= 64'd0;
      detector_armed              <= 1'b1;
      metric_stage0_valid         <= 1'b0;
      metric_stage0_correlation_re <= 41'sd0;
      metric_stage0_correlation_im <= 41'sd0;
      metric_stage0_current_energy <= 41'd0;
      metric_stage0_delayed_energy <= 41'd0;
      metric_stage0_sample_index  <= 64'd0;
      metric_stage1_valid         <= 1'b0;
      metric_stage1_numerator     <= 83'd0;
      metric_stage1_denominator   <= 82'd0;
      metric_stage1_energy_ok     <= 1'b0;
      metric_stage1_sample_index  <= 64'd0;
    end else begin
      candidate_valid <= 1'b0;

      if (!in_valid) begin
        delay_write_pointer       <= 6'd0;
        delay_count               <= 6'd0;
        correlation_write_pointer <= 8'd0;
        correlation_count         <= 9'd0;
        correlation_re_sum        <= 41'sd0;
        correlation_im_sum        <= 41'sd0;
        current_energy_sum        <= 41'd0;
        delayed_energy_sum        <= 41'd0;
        have_previous_index       <= 1'b0;
        previous_sample_index     <= 64'd0;
        detector_armed            <= 1'b1;
        metric_stage0_valid       <= 1'b0;
        metric_stage1_valid       <= 1'b0;
      end else if (sample_index_discontinuity) begin
        // The discontinuous beat becomes sample zero of a fresh history.
        delay_write_pointer       <= 6'd1;
        delay_count               <= 6'd1;
        correlation_write_pointer <= 8'd0;
        correlation_count         <= 9'd0;
        correlation_re_sum        <= 41'sd0;
        correlation_im_sum        <= 41'sd0;
        current_energy_sum        <= 41'd0;
        delayed_energy_sum        <= 41'd0;
        have_previous_index       <= 1'b1;
        previous_sample_index     <= in_sample_index;
        detector_armed            <= 1'b1;
        metric_stage0_valid       <= 1'b0;
        metric_stage1_valid       <= 1'b0;
      end else begin
        have_previous_index   <= 1'b1;
        previous_sample_index <= in_sample_index;

        // Advance the metric pipeline on every accepted, contiguous beat.
        metric_stage1_valid <= metric_stage0_valid;
        if (metric_stage0_valid) begin
          metric_stage1_numerator <= metric_stage0_numerator;
          metric_stage1_denominator <= metric_stage0_denominator;
          metric_stage1_energy_ok <= metric_stage0_energy_ok;
          metric_stage1_sample_index <= metric_stage0_sample_index;
        end
        metric_stage0_valid <= 1'b0;

        if (metric_stage1_valid) begin
          if (metric_above_threshold) begin
            if (detector_armed) begin
              candidate_valid        <= 1'b1;
              candidate_sample_index <= metric_stage1_sample_index;
              candidate_metric_num   <= metric_stage1_numerator;
              candidate_metric_den   <= metric_stage1_denominator;
            end
            detector_armed <= 1'b0;
          end else begin
            detector_armed <= 1'b1;
          end
        end

        if (delay_write_pointer == (DELAY_SAMPLES - 1))
          delay_write_pointer <= 6'd0;
        else
          delay_write_pointer <= delay_write_pointer + 1'b1;

        if (delay_count < DELAY_SAMPLES) begin
          delay_count <= delay_count + 1'b1;
        end else begin
          if (correlation_write_pointer == (CORRELATION_SAMPLES - 1))
            correlation_write_pointer <= 8'd0;
          else
            correlation_write_pointer <= correlation_write_pointer + 1'b1;

          if (correlation_count < CORRELATION_SAMPLES)
            correlation_count <= correlation_count + 1'b1;

          correlation_re_sum <= correlation_re_next;
          correlation_im_sum <= correlation_im_next;
          current_energy_sum <= current_energy_next;
          delayed_energy_sum <= delayed_energy_next;

          if (correlation_window_full ||
              correlation_window_becomes_full) begin
            metric_stage0_valid <= 1'b1;
            metric_stage0_correlation_re <= correlation_re_next;
            metric_stage0_correlation_im <= correlation_im_next;
            metric_stage0_current_energy <= current_energy_next;
            metric_stage0_delayed_energy <= delayed_energy_next;
            metric_stage0_sample_index <=
                in_sample_index - SYMBOL_MINUS_ONE;
          end
        end
      end
    end
  end

endmodule
