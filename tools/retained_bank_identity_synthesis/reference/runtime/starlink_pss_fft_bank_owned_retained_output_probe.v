`timescale 1ns/1ps
module starlink_pss_fft_bank_owned_retained_output_probe #(
  parameter integer ENABLE_RETAINED_OUTPUT = 0,
  parameter KERNEL_ROM_FILE = "upper_edge_pss_kernel_q17.mem",
  parameter integer REGISTERED_SCHEDULING = 0,
  parameter integer BOUNDARY_ROUND_SAT = 0,
  parameter integer REGISTER_OPERANDS = 0,
  parameter integer LOCAL_FIRST_ADMISSION = 0,
  parameter integer PRIVATE_DESCRIPTOR_OFFER = 0,
  parameter integer CLOSED_INPUT_CUTOVER = 0,
  parameter integer INPUT_OFFER_FAULT_SUMMARY = 0,
  parameter integer BANK_LOCAL_IDENTITY_EQ = 0
) (
  input wire clk, resetn, fft_clk, fft_resetn,
  input wire input_valid,
  output wire input_ready,
  input wire [35:0] input_data,
  input wire [8:0] input_position,
  input wire input_last,
  input wire [63:0] input_block_start,
  output wire output_valid,
  input wire output_ready,
  output wire [35:0] output_data,
  output wire [8:0] output_position,
  output wire output_last,
  output wire [74:0] output_metadata,
  output wire fault
);

  initial begin
    if (BANK_LOCAL_IDENTITY_EQ !== 0 && BANK_LOCAL_IDENTITY_EQ !== 1)
      $fatal(1, "bank-local identity mode must be known zero or one");
    if (INPUT_OFFER_FAULT_SUMMARY !== 0 && INPUT_OFFER_FAULT_SUMMARY !== 1)
      $fatal(1, "input-offer summary mode must be known zero or one");
    if (CLOSED_INPUT_CUTOVER !== 0 && CLOSED_INPUT_CUTOVER !== 1)
      $fatal(1, "closed-input cutover mode must be known zero or one");
    if (PRIVATE_DESCRIPTOR_OFFER !== 0 && PRIVATE_DESCRIPTOR_OFFER !== 1)
      $fatal(1, "private descriptor mode must be known zero or one");
    if (ENABLE_RETAINED_OUTPUT !== 0 && ENABLE_RETAINED_OUTPUT !== 1)
      $fatal(1, "ENABLE_RETAINED_OUTPUT must be known zero or one");
    if (ENABLE_RETAINED_OUTPUT === 1 && (REGISTERED_SCHEDULING !== 1 ||
        BOUNDARY_ROUND_SAT !== 1 || REGISTER_OPERANDS !== 1 || LOCAL_FIRST_ADMISSION !== 1))
      $fatal(1, "retained prototype requires exact R1/B1/O1/L1");
  end
  generate if (ENABLE_RETAINED_OUTPUT === 1) begin : retained
    starlink_pss_fft_retained_output_impl #(
      .KERNEL_ROM_FILE(KERNEL_ROM_FILE), .REGISTERED_SCHEDULING(REGISTERED_SCHEDULING),
      .BOUNDARY_ROUND_SAT(BOUNDARY_ROUND_SAT), .REGISTER_OPERANDS(REGISTER_OPERANDS),
      .LOCAL_FIRST_ADMISSION(LOCAL_FIRST_ADMISSION),
      .PRIVATE_DESCRIPTOR_OFFER(PRIVATE_DESCRIPTOR_OFFER),
      .CLOSED_INPUT_CUTOVER(CLOSED_INPUT_CUTOVER),
      .INPUT_OFFER_FAULT_SUMMARY(INPUT_OFFER_FAULT_SUMMARY),
      .BANK_LOCAL_IDENTITY_EQ(BANK_LOCAL_IDENTITY_EQ)) island (.*);
  end else begin : unchanged
    starlink_pss_fft_bank_owned_local_admission_probe #(
      .KERNEL_ROM_FILE(KERNEL_ROM_FILE), .REGISTERED_SCHEDULING(REGISTERED_SCHEDULING),
      .BOUNDARY_ROUND_SAT(BOUNDARY_ROUND_SAT), .REGISTER_OPERANDS(REGISTER_OPERANDS),
      .LOCAL_FIRST_ADMISSION(LOCAL_FIRST_ADMISSION)) island (.*);
  end endgenerate
endmodule
