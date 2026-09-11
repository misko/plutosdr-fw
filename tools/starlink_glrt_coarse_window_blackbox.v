// Interface for importing the separately qualified, source-matched grid DCP.
(* black_box *) module starlink_glrt_coarse_window #(
  parameter integer EPOCH_COUNT=3333,
  parameter integer SOURCE_INDEX_STRIDE=24,
  parameter COEFFICIENT_FILE="coarse_upper_q9.mem",
  parameter ENERGY_FILE="coarse_upper_energy.mem"
) (
  input wire clk,resetn,flush,arm,input_valid,input_gap,
  input wire signed [15:0] input_i,input_q,
  input wire [63:0] input_index,
  input wire output_ready,
  input wire copy_enable,
  input wire [13:0] copy_address,
  output wire copy_ready,copy_valid,
  output wire [13:0] copy_offset,
  output wire [31:0] copy_data,
  output wire busy,done,fault,output_valid,
  output wire [63:0] window_first_index,
  output wire [11:0] output_epoch,
  output wire [3:0] output_frequency,
  output wire [16:0] output_score,
  output wire [5:0] output_support,
  output wire [31:0] rejected_arms
);
endmodule
