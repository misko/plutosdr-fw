`timescale 1ns/1ps

module DNA_PORT #(
  parameter [56:0] SIM_DNA_VALUE = 57'd0
) (
  output DOUT,
  input CLK,
  input DIN,
  input READ,
  input SHIFT
);
  reg [56:0] shift_register = 57'd0;
  assign DOUT = shift_register[0];
  always @(posedge CLK) begin
    if (READ)
      shift_register <= SIM_DNA_VALUE;
    else if (SHIFT)
      shift_register <= {DIN, shift_register[56:1]};
  end
endmodule

module spf_device_dna_tb;
  reg clk = 1'b0;
  reg resetn = 1'b0;
  wire [31:0] dna_low;
  wire [31:0] dna_high;
  localparam [56:0] EXPECTED = 57'h0123456789abcde;

  always #5 clk = ~clk;

  spf_device_dna dut (
    .clk(clk),
    .resetn(resetn),
    .dna_low(dna_low),
    .dna_high(dna_high)
  );

  initial begin
    repeat (2) @(posedge clk);
    resetn <= 1'b1;
    repeat (130) @(posedge clk);
    if (dna_high[31] !== 1'b1) begin
      $display("FAIL: Device DNA never became valid");
      $finish(1);
    end
    if ({dna_high[24:0], dna_low} !== EXPECTED) begin
      $display(
        "FAIL: got %014x, expected %014x",
        {dna_high[24:0], dna_low},
        EXPECTED
      );
      $finish(1);
    end
    if (dna_high[30:25] !== 6'd0) begin
      $display("FAIL: reserved high bits are non-zero");
      $finish(1);
    end
    $display("PASS");
    $finish(0);
  end
endmodule
