// SPDX-License-Identifier: GPL-2.0
// PG109 reset flush is a vendor interface premise, not a synthetic token tag.
`timescale 1ns/1ps
module starlink_pss_core_job_cutover #(
  parameter integer ENABLE_CLOSED_INPUT_VIEW = 0,
  parameter integer ENABLE_OFFERED_FAULT_SUMMARY = 0
) (
  input wire clk, resetn, core_resetn,
  input wire job_accept, job_inverse, producer_closed, config_accept,
  input wire input_beat, input_complete,
  input wire offered_input_beat, offered_input_complete,
  input wire raw_frame, raw_output, raw_status,
  input wire [2:0] raw_vendor_faults,
  output wire admission_allowed, configuration_allowed, fault_now,
  output wire routed_inverse,
  output wire closed_input_fault_now,
  output wire offered_fault_now,
  output reg [7:0] fault_reasons
);
  initial begin
    if (ENABLE_OFFERED_FAULT_SUMMARY !== 0 && ENABLE_OFFERED_FAULT_SUMMARY !== 1)
      $fatal(1, "offered fault summary mode must be known zero or one");
    if (ENABLE_CLOSED_INPUT_VIEW !== 0 && ENABLE_CLOSED_INPUT_VIEW !== 1)
      $fatal(1, "closed-input cutover view must be known zero or one");
  end
  // Seventeen state bits, all common-epoch reset except the reset observations.
  reg owner_open, owner_inverse, configured, quiet_released, reset_flushed;
  reg fresh_frame, fresh_full;
  reg [1:0] low_count;
  wire known = (core_resetn === 1'b0 || core_resetn === 1'b1) &&
    (raw_frame === 1'b0 || raw_frame === 1'b1) &&
    (raw_output === 1'b0 || raw_output === 1'b1) &&
    (raw_status === 1'b0 || raw_status === 1'b1) &&
    (^raw_vendor_faults !== 1'bx) &&
    (input_beat === 1'b0 || input_beat === 1'b1) &&
    (input_complete === 1'b0 || input_complete === 1'b1);
  wire any_raw = raw_frame || raw_output || raw_status;
  wire configured_owner = owner_open && configured && core_resetn === 1'b1 && reset_flushed;
  wire orphan = any_raw && !configured_owner;
  wire premature_reset = owner_open && configured && core_resetn === 1'b0;
  wire early_result = (raw_output || raw_status) &&
    (!(fresh_frame || raw_frame) || !(fresh_full || input_complete));
  assign fault_now = resetn && (!known || raw_vendor_faults !== 3'b0 || orphan || early_result || premature_reset);
  // Summary-only parallel predicate. No offered input is sampled into state.
  wire summary_fault_now;
  wire summary_known = (core_resetn === 1'b0 || core_resetn === 1'b1) &&
    (raw_frame === 1'b0 || raw_frame === 1'b1) &&
    (raw_output === 1'b0 || raw_output === 1'b1) &&
    (raw_status === 1'b0 || raw_status === 1'b1) &&
    (^raw_vendor_faults !== 1'bx) &&
    (offered_input_beat === 1'b0 || offered_input_beat === 1'b1) &&
    (offered_input_complete === 1'b0 || offered_input_complete === 1'b1);
  wire summary_any_raw = raw_frame || raw_output || raw_status;
  wire summary_configured_owner = owner_open && configured && core_resetn === 1'b1 && reset_flushed;
  wire summary_orphan = summary_any_raw && !summary_configured_owner;
  wire summary_premature_reset = owner_open && configured && core_resetn === 1'b0;
  wire summary_early_result = (raw_output || raw_status) &&
    (!(fresh_frame || raw_frame) || !(fresh_full || offered_input_complete));
  assign summary_fault_now = resetn && (!summary_known || raw_vendor_faults !== 3'b0 || summary_orphan || summary_early_result || summary_premature_reset);
  assign offered_fault_now = ENABLE_OFFERED_FAULT_SUMMARY ? summary_fault_now : 1'b0;
  // Parallel observation only: literal fault predicate with the two input
  // strobes set to zero. Caller may consume only in a KNOWN completed-input
  // public-return phase. Unrestricted current diagnostics remain above/below.
  wire closed_known = (core_resetn === 1'b0 || core_resetn === 1'b1) &&
    (raw_frame === 1'b0 || raw_frame === 1'b1) &&
    (raw_output === 1'b0 || raw_output === 1'b1) &&
    (raw_status === 1'b0 || raw_status === 1'b1) &&
    (^raw_vendor_faults !== 1'bx) &&
    (1'b0 === 1'b0 || 1'b0 === 1'b1) &&
    (1'b0 === 1'b0 || 1'b0 === 1'b1);
  wire closed_early_result = (raw_output || raw_status) &&
    (!(fresh_frame || raw_frame) || !(fresh_full || 1'b0));
  assign closed_input_fault_now = ENABLE_CLOSED_INPUT_VIEW ? resetn &&
    (!closed_known || raw_vendor_faults !== 3'b0 || orphan || closed_early_result || premature_reset) : 1'b0;
  assign routed_inverse = owner_inverse;
  assign admission_allowed = resetn && !owner_open && !(|fault_reasons) &&
    core_resetn === 1'b0 && low_count == 2 && !fault_now;
  assign configuration_allowed = resetn && owner_open && !configured && reset_flushed &&
    quiet_released && core_resetn === 1'b1 && !(|fault_reasons) && !fault_now;
  always @(posedge clk or negedge resetn) begin
    if (!resetn) begin
      owner_open <= 0; owner_inverse <= 0; configured <= 0; quiet_released <= 0;
      reset_flushed <= 0; fresh_frame <= 0; fresh_full <= 0; low_count <= 0; fault_reasons <= 0;
    end else begin
      if (!known || (job_accept !== 1'b0 && job_accept !== 1'b1) ||
          (config_accept !== 1'b0 && config_accept !== 1'b1) ||
          (producer_closed !== 1'b0 && producer_closed !== 1'b1)) fault_reasons[0] <= 1;
      if (raw_vendor_faults !== 3'b0) fault_reasons[1] <= 1;
      if (orphan) fault_reasons[2] <= 1;
      if (early_result) fault_reasons[3] <= 1;
      if (core_resetn === 1'b0) begin
        if (low_count != 2) low_count <= low_count + 1'b1;
        if (low_count >= 1) reset_flushed <= 1;
        configured <= 0; quiet_released <= 0; fresh_frame <= 0; fresh_full <= 0;
      end else begin
        low_count <= 0;
        if (reset_flushed && !any_raw && raw_vendor_faults === 3'b0) quiet_released <= 1;
      end
      if (job_accept) begin
        if (!admission_allowed || (job_inverse !== 1'b0 && job_inverse !== 1'b1))
          fault_reasons[4] <= 1;
        else begin owner_open <= 1; owner_inverse <= job_inverse; end
      end
      if (config_accept) begin
        if (!configuration_allowed) fault_reasons[5] <= 1;
        else configured <= 1;
      end
      if ((input_beat && !configured_owner) || premature_reset) fault_reasons[6] <= 1;
      if (configured_owner && raw_frame) fresh_frame <= 1;
      if (configured_owner && input_complete) fresh_full <= 1;
      if (producer_closed) begin
        if (!owner_open || !configured || !fresh_frame || !fresh_full) fault_reasons[7] <= 1;
        owner_open <= 0; configured <= 0; reset_flushed <= 0; quiet_released <= 0;
        fresh_frame <= 0; fresh_full <= 0;
      end
    end
  end
endmodule
