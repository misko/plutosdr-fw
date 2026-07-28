// Read the factory-programmed, read-only 57-bit 7-series Device DNA once.
//
// The two outputs feed a read-only AXI GPIO. dna_high[31] is a validity bit;
// dna_high[24:0] contains Device DNA bits 56:32. No software write path exists.
module spf_device_dna (
  input             clk,
  input             resetn,
  output     [31:0] dna_low,
  output     [31:0] dna_high
);

  localparam STATE_LOAD    = 3'd0;
  localparam STATE_WAIT    = 3'd1;
  localparam STATE_CAPTURE = 3'd2;
  localparam STATE_SHIFT   = 3'd3;
  localparam STATE_DONE    = 3'd4;

  reg [2:0] state = STATE_LOAD;
  reg [5:0] bit_index = 6'd0;
  reg [56:0] dna = 57'd0;
  reg dna_valid = 1'b0;
  reg dna_read = 1'b0;
  reg dna_shift = 1'b0;
  wire dna_dout;

  assign dna_low = dna[31:0];
  assign dna_high = {dna_valid, 6'd0, dna[56:32]};

  DNA_PORT #(
    .SIM_DNA_VALUE(57'h0123456789abcde)
  ) i_device_dna (
    .DOUT(dna_dout),
    .CLK(clk),
    .DIN(1'b0),
    .READ(dna_read),
    .SHIFT(dna_shift)
  );

  always @(posedge clk) begin
    if (!resetn) begin
      state <= STATE_LOAD;
      bit_index <= 6'd0;
      dna <= 57'd0;
      dna_valid <= 1'b0;
      dna_read <= 1'b0;
      dna_shift <= 1'b0;
    end else begin
      case (state)
        STATE_LOAD: begin
          dna_read <= 1'b1;
          dna_shift <= 1'b0;
          state <= STATE_WAIT;
        end
        STATE_WAIT: begin
          dna_read <= 1'b0;
          state <= STATE_CAPTURE;
        end
        STATE_CAPTURE: begin
          dna[bit_index] <= dna_dout;
          if (bit_index == 6'd56) begin
            dna_valid <= 1'b1;
            state <= STATE_DONE;
          end else begin
            dna_shift <= 1'b1;
            state <= STATE_SHIFT;
          end
        end
        STATE_SHIFT: begin
          // Capture and shift use separate cycles so DOUT is sampled only
          // after the primitive has completed the preceding synchronous shift.
          dna_shift <= 1'b0;
          bit_index <= bit_index + 1'b1;
          state <= STATE_CAPTURE;
        end
        default: begin
          dna_read <= 1'b0;
          dna_shift <= 1'b0;
          state <= STATE_DONE;
        end
      endcase
    end
  end

endmodule
