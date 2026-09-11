// SPDX-License-Identifier: GPL-2.0
// ISOLATED EXPERIMENT; no production instantiation or realtime qualification.
// One reset epoch admits exactly one reserved 512-word input job. The caller
// owns reservation, core reset/configuration, result guard and event policy.
// Register the admission/start token; do not form a combinational loop from
// result job_ready through job_start/duplicate_start/fault_now back to job_ready.
// This checker certifies actual correctly framed input handshakes, not output
// numerics, bank ownership, or a bound on delayed vendor events.
//
// PG109 (May 4, 2022), pp51-53: after the first realtime input word, every
// asserted TREADY requires a valid word; ordinary pre-first-word idle and core
// waitstates are legal. Detect a violated demand immediately, even if the
// caller accidentally withdraws input_enable. Do not wait for vendor halt.
`timescale 1ns/1ps
module starlink_pss_realtime_input_guard_local_admission #(
  parameter integer CHECK_INPUT_BLOCK_IDENTITY = 1,
  parameter integer BALANCED_IDENTITY_EQ = 0,
  parameter integer LOCAL_FIRST_ADMISSION = 0,
  parameter integer BANK_LOCAL_IDENTITY_EQ = 0
) (
  input wire clk,
  input wire resetn,
  input wire job_start,
  input wire [69:0] job_descriptor,
  input wire input_enable,
  input wire input_valid,
  output wire input_ready,
  output wire input_transport_ready,
  input wire [35:0] input_data,
  input wire [8:0] input_position,
  input wire input_last,
  input wire [69:0] input_metadata,
  output wire [47:0] core_input_tdata,
  output wire core_input_tvalid,
  input wire core_input_tready,
  output wire core_input_tlast,
  output wire certified_input_beat,
  output wire certified_input_complete,
  output reg input_complete,
  output wire fault_now,
  // In the registered input_complete phase, slot_open is closed: this is
  // exactly fault_now, not a delayed sample of it. Per-beat checks remain live
  // during input delivery and still feed the unchanged full reason bank.
  output wire duplicate_start_fault_now,
  output wire [2:0] fault_events_now,
  output wire protocol_fault,
  output reg [2:0] fault_reasons,
  input wire bank_input_phase,
  input wire [69:0] source_input_metadata, product_input_metadata
);
  initial begin
    if (BANK_LOCAL_IDENTITY_EQ !== 0 && BANK_LOCAL_IDENTITY_EQ !== 1)
      $fatal(1, "bank-local identity mode must be known zero or one");
    if (LOCAL_FIRST_ADMISSION !== 0 && LOCAL_FIRST_ADMISSION !== 1)
      $fatal(1, "LOCAL_FIRST_ADMISSION must be zero or one");
    if (CHECK_INPUT_BLOCK_IDENTITY != 0 && CHECK_INPUT_BLOCK_IDENTITY != 1)
      $fatal(1, "CHECK_INPUT_BLOCK_IDENTITY must be zero or one");
    if (BALANCED_IDENTITY_EQ != 0 && BALANCED_IDENTITY_EQ != 1)
      $fatal(1, "BALANCED_IDENTITY_EQ must be zero or one");
  end
  reg job_started, input_started;
  reg [69:0] descriptor;
  reg [8:0] expected_position;
  assign protocol_fault = |fault_reasons;
  wire slot_open = resetn && job_started && !input_complete && !protocol_fault;
  wire eligible = slot_open && input_enable;
  wire identity_matches;
  wire selected_identity_matches;
  generate if (BALANCED_IDENTITY_EQ) begin : balanced_identity
    // All 70 bits remain live on this edge. Preserve LUT-sized equalities and
    // balanced reductions; no state, hash, delayed veto or phase exemption.
    (* keep = "true" *) wire [23:0] leaf_equal;
    (* keep = "true" *) wire [3:0] group_equal;
    for (genvar leaf = 0; leaf < 24; leaf = leaf + 1) begin : leaves
      localparam integer BITS = leaf == 23 ? 1 : 3;
      assign leaf_equal[leaf] = input_metadata[3*leaf +: BITS] == descriptor[3*leaf +: BITS];
    end
    for (genvar group_index = 0; group_index < 4; group_index = group_index + 1) begin : groups
      assign group_equal[group_index] = &leaf_equal[6*group_index +: 6];
    end
    assign selected_identity_matches = &group_equal;
  end else begin : legacy_identity
    assign selected_identity_matches = input_metadata == descriptor;
  end endgenerate
  // The comparison owner is the unchanged private admission descriptor.
  // Unknown phase must retain mux-before-equality, not merge scalar results.
  generate if (BANK_LOCAL_IDENTITY_EQ) begin : bank_local_identity
    wire [1:0] bank_equal;
    for (genvar bank_index = 0; bank_index < 2; bank_index = bank_index + 1) begin : banks
      wire [69:0] bank_metadata = bank_index == 0 ? source_input_metadata : product_input_metadata;
      if (BALANCED_IDENTITY_EQ) begin : balanced
        (* keep = "true" *) wire [23:0] leaf_equal;
        (* keep = "true" *) wire [3:0] group_equal;
        for (genvar leaf = 0; leaf < 24; leaf = leaf + 1) begin : leaves
          localparam integer BITS = leaf == 23 ? 1 : 3;
          assign leaf_equal[leaf] = bank_metadata[3*leaf +: BITS] == descriptor[3*leaf +: BITS];
        end
        for (genvar group_index = 0; group_index < 4; group_index = group_index + 1) begin : groups
          assign group_equal[group_index] = &leaf_equal[6*group_index +: 6];
        end
        assign bank_equal[bank_index] = &group_equal;
      end else begin : legacy
        assign bank_equal[bank_index] = bank_metadata == descriptor;
      end
    end
    assign identity_matches = bank_input_phase === 1'b0 ? bank_equal[0] :
      bank_input_phase === 1'b1 ? bank_equal[1] : selected_identity_matches;
  end else begin : selected_identity
    assign identity_matches = selected_identity_matches;
  end endgenerate
  wire metadata_valid = input_position == expected_position &&
    input_last == (expected_position == 511) &&
    (!CHECK_INPUT_BLOCK_IDENTITY || identity_matches);
  // Checker consumes malformed presented input even while the core stalls.
  // Mailbox retirement uses the explicitly metadata-independent transport cone.
  assign input_ready = eligible && (metadata_valid ? core_input_tready : 1'b1);
  assign input_transport_ready = eligible && core_input_tready;
  assign core_input_tdata = {6'b0, input_data[35:18], 6'b0, input_data[17:0]};
  assign core_input_tvalid = eligible && input_valid && metadata_valid;
  assign core_input_tlast = input_last;
  wire framing_error = eligible && input_valid && !metadata_valid;
  wire delivery_error = slot_open && input_started && core_input_tready &&
    !core_input_tvalid;
  wire duplicate_start = resetn && job_start && job_started;
  assign duplicate_start_fault_now = duplicate_start;
  wire [2:0] errors_now = {duplicate_start, framing_error, delivery_error};
  assign fault_events_now = errors_now;
  assign fault_now = |errors_now;
  // A current malformed/duplicate/delivery event cannot certify that edge.
  // The result guard must also consume fault_now as a direct commit veto.
  assign certified_input_beat = core_input_tvalid && core_input_tready && !fault_now;
  assign certified_input_complete = certified_input_beat && expected_position == 511;

  always @(posedge clk or negedge resetn) begin
    if (!resetn) begin
      job_started <= 0;
      input_started <= 0;
      input_complete <= 0;
      descriptor <= 0;
      expected_position <= 0;
      fault_reasons <= 0;
    end else begin
      fault_reasons <= fault_reasons | errors_now;
      // BEGIN LOCAL_FIRST_ADMISSION
      // With job_started=0 the checker slot is closed: no current framing,
      // delivery or duplicate event can veto this first descriptor capture.
      // With job_started=1 a new start is a duplicate and must not overwrite it.
      // Keep every current beat/fault/certificate equation unchanged below.
      if (LOCAL_FIRST_ADMISSION && !protocol_fault && job_start && !job_started) begin
        job_started <= 1;
        descriptor <= job_descriptor;
      end
      // END LOCAL_FIRST_ADMISSION
      if (!protocol_fault && !fault_now) begin
        if (!LOCAL_FIRST_ADMISSION && job_start) begin
          job_started <= 1;
          descriptor <= job_descriptor;
        end
        if (certified_input_beat) begin
          input_started <= 1;
          if (certified_input_complete) input_complete <= 1;
        end
      end
      // This cursor is private, not a delivered-beat certificate. A presented
      // malformed/duplicate beat may advance it on its fault edge; unchanged
      // errors_now sets sticky quarantine on that same edge, closing slot_open
      // before any later certificate or delivery. All public checks still use
      // the original pre-edge ordinal. Saturate rather than wrap at the final
      // slot, and purge the private value only through the existing reset.
      // Keep the ordinal/metadata comparator off this counter's enable path.
      if (slot_open && input_enable && input_valid && core_input_tready &&
          expected_position != 511)
        expected_position <= expected_position + 1'b1;
    end
  end
endmodule
