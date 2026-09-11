// SPDX-License-Identifier: GPL-2.0
// Control-only owner; actual RAM/request/ACK remain in the unchanged mailbox.
`timescale 1ns/1ps
module starlink_pss_retained_destination_owner (
  input wire clk, resetn,
  input wire inverse_admit, inverse_publication, inverse_guard_ack, transfer_consumed,
  input wire bank_ready, bank_request, bank_ack_sync,
  input wire common_current_fault,
  output wire reusable, reservation, retained, fault_now,
  output reg transfer_receipt,
  output wire reader_release,
  output reg [7:0] fault_reasons,
  output wire [1:0] current_lease, admitted_lease,
  output wire reserved_state_known
);
  // Seventeen state bits; descriptor stays in exact inverse guard and bank.
  reg reserved, published, busy_seen, expected_request;
  reg [1:0] lease, held_lease;
  // Read-only four-state observation; no physical unknown detector claim.
  assign reserved_state_known = reserved === 1'b0 || reserved === 1'b1;
  assign current_lease = lease;
  assign admitted_lease = held_lease;
  wire fault = |fault_reasons;
  wire controls_known = (bank_ready === 1'b0 || bank_ready === 1'b1) &&
    (bank_request === 1'b0 || bank_request === 1'b1) &&
    (bank_ack_sync === 1'b0 || bank_ack_sync === 1'b1);
  wire event_controls_known = (inverse_admit === 1'b0 || inverse_admit === 1'b1) &&
    (inverse_publication === 1'b0 || inverse_publication === 1'b1) &&
    (inverse_guard_ack === 1'b0 || inverse_guard_ack === 1'b1) &&
    (transfer_consumed === 1'b0 || transfer_consumed === 1'b1);
  wire request_bad = published && bank_request !== expected_request;
  wire lease_bad = reserved && held_lease !== lease;
  assign fault_now = resetn && (!controls_known || request_bad || lease_bad);
  assign reusable = resetn && !fault && !fault_now && !reserved &&
    bank_ready === 1'b1 && bank_request === bank_ack_sync;
  assign reservation = resetn && !fault && (reserved || reusable);
  assign retained = published;
  wire actual_read_ack = published && busy_seen && bank_ready === 1'b1 &&
    bank_request === expected_request && bank_ack_sync === expected_request;
  assign reader_release = resetn && reserved && actual_read_ack && inverse_guard_ack &&
    !fault && !fault_now && common_current_fault === 1'b0 && event_controls_known &&
    inverse_admit === 1'b0 && inverse_publication === 1'b0 &&
    (transfer_consumed === 1'b0 || transfer_receipt === 1'b1);
  // A caller may consume a still-owned transfer receipt with the real ACK.
  // Repeating an already-consumed receipt, or unknown event controls, must not
  // pulse release before their registered diagnostic. No receipt is a fake ACK.
  always @(posedge clk or negedge resetn) begin
    if (!resetn) begin
      reserved <= 0; published <= 0; busy_seen <= 0; expected_request <= 0;
      lease <= 0; held_lease <= 0; transfer_receipt <= 0; fault_reasons <= 0;
    end else begin
      if (transfer_consumed) begin
        if (!transfer_receipt) fault_reasons[7] <= 1;
        transfer_receipt <= 0;
      end
      if (!controls_known || !event_controls_known) fault_reasons[0] <= 1;
      if (request_bad) fault_reasons[1] <= 1;
      if (lease_bad) fault_reasons[2] <= 1;
      // Invalid admissions/publications never create transfer authority. Their
      // diagnostics are registered, not job_ready -> fault -> job_ready loops.
      if (inverse_admit) begin
        if (!reusable || common_current_fault !== 1'b0) fault_reasons[3] <= 1;
        else begin
          reserved <= 1; held_lease <= lease; expected_request <= !bank_request;
        end
      end
      if (inverse_publication) begin
        if (!reserved || published || fault || fault_now || common_current_fault !== 1'b0)
          fault_reasons[4] <= 1;
        else begin published <= 1; transfer_receipt <= 1; end
      end
      if (published && bank_ready === 1'b0) busy_seen <= 1;
      if (inverse_guard_ack && !actual_read_ack) fault_reasons[5] <= 1;
      if (reader_release) begin
        reserved <= 0; published <= 0; busy_seen <= 0; lease <= lease + 1'b1;
      end
      if (common_current_fault !== 1'b0) fault_reasons[6] <= 1;
    end
  end
endmodule
