// SPDX-License-Identifier: GPL-2.0
// Used by the explicitly opted-in realtime shared-XFFT service; the default
// non-realtime service is unchanged. Physical qualification is separate.
// One reserved result bank plus one 52-bit return slot; no extra payload RAM.
// The final word stays here until independent status and all explicitly
// certified premises pass. An explicit-commit mailbox may privately rewrite
// that word before qualification, but must not publish on private-write valid.
//
// CALLER OBLIGATIONS (not established by this module):
// - resetn is a common, synchronously released epoch for BOTH mailbox clocks;
// - input_bank_reserved means a complete, checked/prefetched 512-word bank;
// - output_bank_reserved is exclusive whole-bank ownership, not just READY;
// - certified_input_beat denotes an actually delivered, fully checked core beat;
// - certified_input_complete certifies the input framing/identity checks;
// - external_fault_now includes immediate starvation/input/core/ownership faults;
// - final_fence_certified proves all potentially corrupting delayed events have
//   been observed or excluded. NO vendor-event latency bound is inferred here.
// A pulse/claim from an unqualified caller cannot make a qualified FFT service.
// There is no output/status backpressure to the realtime core. Unexpected
// transport stalls fault closed. A new job waits for the mailbox's actual ACK.
`timescale 1ns/1ps

module starlink_pss_result_guard_owner_view #(
  parameter integer WATCHDOG_CYCLES = 8192,
  parameter integer USE_PRIVATE_DESCRIPTOR_OFFER = 0,
  parameter integer ENABLE_OFFERED_FAULT_SUMMARY = 0,
  parameter integer REQUIRE_KNOWN_COMPLETED_INPUT = 0,
  // Opt in only when the caller proves idle input is reset/completed, and
  // final qualification and the full ACK interval imply completed input.
  // The supplied predicate must equal external_fault_now | both input
  // certificates in these phases while the epoch is not already quarantined.
  // Default callers retain the independent, unrestricted input checks.
  parameter integer USE_PHASE_INPUT_FAULT = 0,
  // Separately opt in for an occupied, checked return. The caller must prove
  // that every such return has registered completed input, and provide an
  // exact external-fault predicate in that phase. The certificate closes the
  // independent input guard, so both input certificates must then be zero.
  // Full faults_now/reasons are retained for ALL phases. Defaults unchanged.
  parameter integer USE_COMPLETED_INPUT_FAULT = 0,
  // Caller guarantees no payload/configuration/publication during preflight.
  // A rejected preflight may privately admit on this edge, but this reason Q
  // must quarantine it before any emitted start or public evidence. This input
  // is deliberately NOT a combinational admission/active-publication predicate.
  parameter integer USE_PREFLIGHT_REASON_ONLY = 0,
  // Parallel forward-only retirement, never a replacement for global faults.
  // Caller proves mailbox_input_fault == forward_mailbox_fault | C and
  // C implies inverse_phase from actual mailbox input-valid wiring. Sticky
  // mailbox faults remain in forward_mailbox_fault in EVERY phase.
  parameter integer USE_FORWARD_RETIREMENT = 0
) (
  input wire clk,
  input wire resetn,
  input wire job_valid,
  // Private metadata offer is NOT admission; caller must assert it on every accepted job.
  input wire private_descriptor_offer,
  output wire job_ready,
  input wire [69:0] job_descriptor,
  input wire input_bank_reserved,
  input wire output_bank_reserved,
  input wire certified_input_beat,
  input wire certified_input_complete,
  input wire offered_input_beat, offered_input_complete,
  output wire offered_local_fault_now,
  input wire final_fence_certified,
  input wire external_fault_now,
  input wire phase_input_fault_now,
  input wire completed_input_certified,
  input wire completed_input_fault_now,
  input wire preflight_fault_evidence_now,
  input wire core_event_frame_started,
  input wire [47:0] core_output_tdata,
  input wire [23:0] core_output_tuser,
  input wire core_output_tvalid,
  input wire core_output_tlast,
  input wire [7:0] core_status_tdata,
  input wire core_status_tvalid,
  output wire mailbox_input_valid,
  output wire mailbox_private_valid,
  // Separate final-only authorization for explicit-commit mailboxes. Ordinary
  // mailbox_input_valid remains unchanged for nonfinal result retirement.
  output wire mailbox_commit_valid,
  input wire mailbox_input_ready,
  input wire mailbox_input_fault,
  input wire inverse_phase,
  input wire forward_mailbox_fault,
  output wire forward_retirement_valid,
  output wire [35:0] mailbox_input_data,
  output wire [8:0] mailbox_input_position,
  output wire mailbox_input_last,
  output wire [74:0] mailbox_input_metadata,
  output wire busy,
  output reg commit_pulse,
  output wire protocol_fault,
  output reg [7:0] fault_reasons,
  output wire owner_active, owner_awaiting_ack, owner_fault_now, owner_ack_accept
);
  localparam integer AGE_WIDTH = $clog2(WATCHDOG_CYCLES);
  initial begin
    if (ENABLE_OFFERED_FAULT_SUMMARY !== 0 && ENABLE_OFFERED_FAULT_SUMMARY !== 1)
      $fatal(1, "offered fault summary mode must be known zero or one");
    if (REQUIRE_KNOWN_COMPLETED_INPUT !== 0 && REQUIRE_KNOWN_COMPLETED_INPUT !== 1)
      $fatal(1, "known completed-input mode must be zero or one");
    if (REQUIRE_KNOWN_COMPLETED_INPUT === 1 && USE_COMPLETED_INPUT_FAULT !== 1)
      $fatal(1, "known completed-input mode requires completed-return contract");
    if (USE_PRIVATE_DESCRIPTOR_OFFER !== 0 && USE_PRIVATE_DESCRIPTOR_OFFER !== 1)
      $fatal(1, "private descriptor mode must be known zero or one");
    if (USE_PHASE_INPUT_FAULT != 0 && USE_PHASE_INPUT_FAULT != 1)
      $fatal(1, "USE_PHASE_INPUT_FAULT must be zero or one");
    if (USE_COMPLETED_INPUT_FAULT != 0 && USE_COMPLETED_INPUT_FAULT != 1)
      $fatal(1, "USE_COMPLETED_INPUT_FAULT must be zero or one");
    if (USE_PREFLIGHT_REASON_ONLY != 0 && USE_PREFLIGHT_REASON_ONLY != 1)
      $fatal(1, "USE_PREFLIGHT_REASON_ONLY must be zero or one");
    if (USE_FORWARD_RETIREMENT != 0 && USE_FORWARD_RETIREMENT != 1)
      $fatal(1, "USE_FORWARD_RETIREMENT must be zero or one");
    if (WATCHDOG_CYCLES < 2 || WATCHDOG_CYCLES > 1048576)
      $fatal(1, "realtime result guard requires a finite 2..1048576 cycle watchdog");
  end

  reg active_private, awaiting_ack;
  // faults_now is captured in fault_reasons on the same edge that formerly
  // cleared active. Quarantine that private occupancy through the registered
  // fault bank instead of routing the complete fault tree to another D pin.
  // Effective active still falls on that edge, including for exact next-cycle
  // orphan-event classification. The private bit never authorizes publication.
  wire active = active_private && !protocol_fault;
  reg [69:0] descriptor;
  reg [9:0] input_count, output_count;
  reg input_complete_seen, frame_seen, status_seen, exponent_seen;
  reg [4:0] status_exponent, output_exponent;
  reg [AGE_WIDTH-1:0] age;
  reg return_occupied, return_last;
  wire return_valid = return_occupied && active;
  reg [35:0] return_data;
  reg [8:0] return_position;
  reg [4:0] return_exponent;

  // Exact equality after a possible delivered beat; no wide increment is
  // needed just to decide whether the effective count is 512. This does not
  // remove or defer the independent input guard's ordinal/metadata check.
  wire effective_input_full = (input_count == 511 && certified_input_beat) ||
    (input_count == 512 && !certified_input_beat);
  wire effective_input_complete = input_complete_seen || certified_input_complete;
  wire effective_frame_seen = frame_seen || core_event_frame_started;
  wire reservation_error = active && (!output_bank_reserved ||
    (!input_complete_seen && !input_bank_reserved));
  wire input_error = (certified_input_beat &&
    (!active || input_complete_seen || input_count == 512)) ||
    (certified_input_complete &&
    (!active || input_complete_seen || !effective_input_full));
  wire frame_error = core_event_frame_started &&
    (!active || frame_seen || (input_count == 0 && !certified_input_beat));
  wire status_error = core_status_tvalid &&
    (!active || status_seen || core_status_tdata[7:5] != 0 ||
     (exponent_seen && core_status_tdata[4:0] != output_exponent));
  // Preserve the existing BFP18 layout: two 18-bit values in 24-bit AXI slots;
  // TUSER is {3'b0, exponent[4:0], 7'b0, XK_INDEX[8:0]}.
  // The unused upper component-slot bits are ignored, as in the old adapter.
  wire output_error = core_output_tvalid &&
    (!active || output_count == 512 || !effective_input_complete ||
     !effective_input_full || !effective_frame_seen ||
     core_output_tuser[15:9] != 0 || core_output_tuser[23:21] != 0 ||
     core_output_tuser[8:0] != output_count[8:0] ||
     core_output_tlast != (output_count == 511) ||
     (exponent_seen && core_output_tuser[20:16] != output_exponent) ||
     (status_seen && core_output_tuser[20:16] != status_exponent) ||
     (core_status_tvalid && core_output_tuser[20:16] != core_status_tdata[4:0]));
  wire slot_error = active && return_valid &&
    ((!return_last && !mailbox_input_ready) ||
     (core_output_tvalid && (return_last || !mailbox_input_ready)));
  wire watchdog_error = active && age == WATCHDOG_CYCLES - 1;
  wire [7:0] faults_now = {watchdog_error, slot_error, output_error, status_error,
    frame_error, input_error, reservation_error, external_fault_now || mailbox_input_fault};
  wire fault_now = |faults_now;
  // No inherited external-fault echo. This view does not replace the guard's own
  // state/ACK/publication predicates or delivered-input certification.
  wire summary_effective_input_full = (input_count == 511 && offered_input_beat) ||
    (input_count == 512 && !offered_input_beat);
  wire summary_effective_input_complete = input_complete_seen || offered_input_complete;
  wire summary_effective_frame_seen = frame_seen || core_event_frame_started;
  wire summary_reservation_error = active && (!output_bank_reserved ||
    (!input_complete_seen && !input_bank_reserved));
  wire summary_input_error = (offered_input_beat &&
    (!active || input_complete_seen || input_count == 512)) ||
    (offered_input_complete &&
    (!active || input_complete_seen || !summary_effective_input_full));
  wire summary_frame_error = core_event_frame_started &&
    (!active || frame_seen || (input_count == 0 && !offered_input_beat));
  wire summary_status_error = core_status_tvalid &&
    (!active || status_seen || core_status_tdata[7:5] != 0 ||
     (exponent_seen && core_status_tdata[4:0] != output_exponent));
  // Preserve the existing BFP18 layout: two 18-bit values in 24-bit AXI slots;
  // TUSER is {3'b0, exponent[4:0], 7'b0, XK_INDEX[8:0]}.
  // The unused upper component-slot bits are ignored, as in the old adapter.
  wire summary_output_error = core_output_tvalid &&
    (!active || output_count == 512 || !summary_effective_input_complete ||
     !summary_effective_input_full || !summary_effective_frame_seen ||
     core_output_tuser[15:9] != 0 || core_output_tuser[23:21] != 0 ||
     core_output_tuser[8:0] != output_count[8:0] ||
     core_output_tlast != (output_count == 511) ||
     (exponent_seen && core_output_tuser[20:16] != output_exponent) ||
     (status_seen && core_output_tuser[20:16] != status_exponent) ||
     (core_status_tvalid && core_output_tuser[20:16] != core_status_tdata[4:0]));
  wire summary_slot_error = active && return_valid &&
    ((!return_last && !mailbox_input_ready) ||
     (core_output_tvalid && (return_last || !mailbox_input_ready)));
  wire summary_watchdog_error = active && age == WATCHDOG_CYCLES - 1;
  wire [7:0] summary_faults_now = {summary_watchdog_error, summary_slot_error, summary_output_error, summary_status_error,
    summary_frame_error, summary_input_error, summary_reservation_error, 1'b0 || mailbox_input_fault};
  wire summary_fault_now = |summary_faults_now;
  assign offered_local_fault_now = ENABLE_OFFERED_FAULT_SUMMARY ? summary_fault_now : 1'b0;
  assign protocol_fault = |fault_reasons;
  assign busy = active || awaiting_ack;
  // Admission already requires !active. In that phase reservation, slot and
  // watchdog errors are false; every input/frame/status/output event is an
  // error regardless of its payload. This is exactly faults_now restricted
  // to idle, not a delayed or weaker admission fence. Keep active-job payload
  // validation off this path to the caller's admission/state controls.
  wire phase_input_fault = USE_PHASE_INPUT_FAULT ? phase_input_fault_now :
    (external_fault_now || certified_input_beat || certified_input_complete);
  wire idle_fault_now = phase_input_fault || mailbox_input_fault ||
    core_event_frame_started || core_status_tvalid || core_output_tvalid;
  assign job_ready = resetn && !protocol_fault && !idle_fault_now &&
    !active && !awaiting_ack && !return_valid &&
    input_bank_reserved && output_bank_reserved && mailbox_input_ready;
  wire job_accept = job_valid && job_ready;

  // Only REGISTERED complete evidence opens the final write. A coincident new
  // status, duplicate status, frame event, raw extra word, timeout or external
  // fault still participates in faults_now and directly vetoes that same edge.
  wire final_qualified = input_count == 512 && input_complete_seen &&
    output_count == 512 && frame_seen && exponent_seen && status_seen &&
    output_exponent == status_exponent && final_fence_certified;
  // With a held final word AND final_qualified, every new raw input/frame/
  // status/output event is illegal, input ownership is already retired, and
  // the remaining immediate faults are output ownership, transport/external
  // faults and the watchdog. This is faults_now restricted to that phase.
  // Keep the full fault tree and exact reason accumulation for every phase;
  // never use this reduced predicate for a nonfinal or unqualified word.
  wire final_fault_now = phase_input_fault || mailbox_input_fault ||
    !output_bank_reserved ||
    core_event_frame_started || core_status_tvalid || core_output_tvalid || watchdog_error;
  // A visible held return survived the preceding edge's full output_error.
  // Therefore input_count=512, input_complete_seen, frame_seen and exponent_seen
  // are registered facts. With the caller's closed-input certificate, neither
  // a new input beat nor its metadata comparator can affect this phase. Keep
  // live output/status validation: first matching status is legal NONFINAL;
  // treating every status as a fault here would silently change behavior.
  wire completed_output_error = core_output_tvalid &&
    (output_count == 512 || core_output_tuser[15:9] != 0 ||
     core_output_tuser[23:21] != 0 || core_output_tuser[8:0] != output_count[8:0] ||
     core_output_tlast != (output_count == 511) ||
     core_output_tuser[20:16] != output_exponent ||
     (status_seen && core_output_tuser[20:16] != status_exponent) ||
     (core_status_tvalid && core_output_tuser[20:16] != core_status_tdata[4:0]));
  wire completed_return_fault_now = completed_input_fault_now || mailbox_input_fault ||
    !output_bank_reserved || core_event_frame_started || status_error ||
    completed_output_error || slot_error || watchdog_error;
  wire completed_final_fault_now = completed_input_fault_now || mailbox_input_fault ||
    !output_bank_reserved || core_event_frame_started || core_status_tvalid ||
    core_output_tvalid || watchdog_error;
  // Opt-in fail-closed visibility: X/Z certification is not publication authority.
  // Private storage, unrestricted diagnostics and all ACK gates are unchanged.
  wire return_phase_allowed = !USE_COMPLETED_INPUT_FAULT ||
    (REQUIRE_KNOWN_COMPLETED_INPUT ? completed_input_certified === 1'b1 : completed_input_certified);
  wire nonfinal_public_fault = USE_COMPLETED_INPUT_FAULT ? completed_return_fault_now : fault_now;
  wire final_public_fault = USE_COMPLETED_INPUT_FAULT ? completed_final_fault_now : final_fault_now;
  assign mailbox_input_valid = resetn && active && !protocol_fault && return_valid &&
    return_phase_allowed &&
    ((!return_last && !nonfinal_public_fault) || (return_last && final_qualified && !final_public_fault));
  // A prior certified return word may enter exclusively owned private RAM on
  // a simultaneous new fault. The full current fault still vetoes retirement
  // and publication above, clears return_valid below, and quarantines the
  // epoch. NEVER connect this signal to a legacy publish-on-final mailbox.
  assign mailbox_private_valid = resetn && active && !protocol_fault && return_valid;
  assign mailbox_input_data = return_data;
  assign mailbox_input_position = return_position;
  assign mailbox_input_last = return_last;
  // Same ordering as the existing service: descriptor, then new exponent.
  assign mailbox_input_metadata = {descriptor, return_exponent};
  wire mailbox_accept = mailbox_input_valid && mailbox_input_ready;
  // Expand the final branch explicitly: return_last excludes the nonfinal
  // branch of mailbox_input_valid. This is the same handshake on the same
  // edge, without unnecessarily reconverging the full nonfinal fault tree
  // onto final occupancy/ACK controls. No publication condition is omitted.
  assign mailbox_commit_valid = resetn && active && !protocol_fault && return_valid &&
    return_phase_allowed && return_last && final_qualified && !final_public_fault;
  wire final_commit = mailbox_commit_valid && mailbox_input_ready;

  // BEGIN FORWARD_RETIREMENT: existing public outputs/state stay literal.
  // The inverse mailbox's CURRENT framing fault is structurally impossible
  // when !inverse_phase. Keep its sticky fault and every other current veto.
  // This equals mailbox_input_valid && !inverse_phase under that interface
  // invariant, including held-final qualification. It is NOT private_valid.
  wire forward_nonfinal_fault = USE_COMPLETED_INPUT_FAULT ?
    (completed_input_fault_now || forward_mailbox_fault || !output_bank_reserved ||
     core_event_frame_started || status_error || completed_output_error || slot_error || watchdog_error) :
    ((|faults_now[7:1]) || external_fault_now || forward_mailbox_fault);
  wire forward_final_fault = (USE_COMPLETED_INPUT_FAULT ? completed_input_fault_now : phase_input_fault) ||
    forward_mailbox_fault || !output_bank_reserved || core_event_frame_started ||
    core_status_tvalid || core_output_tvalid || watchdog_error;
  assign forward_retirement_valid = USE_FORWARD_RETIREMENT && !inverse_phase &&
    resetn && active && !protocol_fault && return_valid && return_phase_allowed &&
    ((!return_last && !forward_nonfinal_fault) ||
     (return_last && final_qualified && !forward_final_fault));
  // END FORWARD_RETIREMENT

  always @(posedge clk or negedge resetn) begin
    if (!resetn) begin
      active_private <= 0;
      awaiting_ack <= 0;
      descriptor <= 0;
      input_count <= 0;
      output_count <= 0;
      input_complete_seen <= 0;
      frame_seen <= 0;
      status_seen <= 0;
      exponent_seen <= 0;
      status_exponent <= 0;
      output_exponent <= 0;
      age <= 0;
      return_occupied <= 0;
      return_last <= 0;
      return_data <= 0;
      return_position <= 0;
      return_exponent <= 0;
      commit_pulse <= 0;
      fault_reasons <= 0;
    end else begin
      commit_pulse <= final_commit;
      fault_reasons <= fault_reasons | faults_now |
        {7'b0, (USE_PREFLIGHT_REASON_ONLY && preflight_fault_evidence_now)};
      // Stage only private descriptor bits while idle. Every admitted job
      // satisfies this predicate and captures the same descriptor on the same
      // edge, without putting the active-job fault cone on 70 register enables.
      // Rejected requests may change invalid metadata, never validity or bank
      // ownership. A current fault still quarantines the epoch below; active
      // jobs and the full ACK interval (including its clearing edge) hold the
      // accepted descriptor. Reset purges any speculative value before reuse.
      if (!active && !awaiting_ack && !protocol_fault &&
          (USE_PRIVATE_DESCRIPTOR_OFFER ? private_descriptor_offer : job_valid))
        descriptor <= job_descriptor;
      // Job observations are private while inactive. Clear them during that
      // phase, including the ACK wait, rather than routing the entire current
      // fault/mailbox framing cone through their job_accept reset muxes. Every
      // accepted job is inactive on this edge, so it still starts at zero.
      // Idle events remain errors independent of these values; active checks,
      // same-edge publication veto and sticky quarantine are unchanged. Keep
      // faulted private observations frozen until the common epoch reset.
      if (!active && !protocol_fault) begin
        input_count <= 0;
        output_count <= 0;
        input_complete_seen <= 0;
        frame_seen <= 0;
        status_seen <= 0;
        exponent_seen <= 0;
      end
      // Account the raw arriving beat even if it triggers quarantine. This
      // counter is private; malformed data still cannot become a valid return
      // word or publish. Saturate beyond the one allowed block rather than wrap.
      if (active && !protocol_fault && core_output_tvalid && output_count < 513)
        output_count <= output_count + 1'b1;
      // Speculatively capture ONLY private payload on the arriving edge, so
      // its 51-bit register enable need not traverse the full validation tree.
      // Current faults still clear return_valid below and veto mailbox_input_valid
      // immediately. Sticky quarantine prevents this payload gaining validity
      // later; the epoch reset clears it before another job can be admitted.
      if (active && !protocol_fault && core_output_tvalid) begin
        return_data <= {core_output_tdata[41:24], core_output_tdata[17:0]};
        return_position <= core_output_tuser[8:0];
        return_last <= core_output_tlast;
        return_exponent <= core_output_tuser[20:16];
      end
      // Private watchdog state need not wait for the complete current-cycle
      // fault cone. Admission occurs while inactive, so it still starts at
      // zero; every healthy active edge and the immediate deadline veto are
      // unchanged. On a fault edge only this private age may advance before
      // quarantine clears active. No publication or fault check is delayed.
      if (!active) age <= 0;
      else age <= age + 1'b1;
      // These are private job observations, not publication authority. Capture
      // them without routing the complete current fault tree through every
      // counter/flag/exponent enable. A simultaneous fault still clears active
      // and return_valid below and latches exact reasons on this same edge.
      // Sticky quarantine prevents any changed private observation from
      // authorizing publication or a new job before the common epoch reset.
      // Once inactive, raw events are errors regardless of these private values.
      if (active && !protocol_fault) begin
        if (certified_input_beat) input_count <= input_count + 1'b1;
        if (certified_input_complete) input_complete_seen <= 1;
        if (core_event_frame_started) frame_seen <= 1;
        if (core_status_tvalid) begin
          status_seen <= 1;
          status_exponent <= core_status_tdata[4:0];
        end
        if (core_output_tvalid) begin
          if (!exponent_seen) output_exponent <= core_output_tuser[20:16];
          exponent_seen <= 1;
        end
      end
      // job_accept is already qualified while idle. final_commit is already
      // qualified by the unchanged same-edge final publication fence. A new
      // fault clears effective active/return_valid through fault_reasons on
      // this edge; clearing these hidden occupancy bits can wait until next.
      if (protocol_fault) active_private <= 0;
      else if (job_accept) active_private <= 1;
      else if (final_commit) active_private <= 0;

      if (!active) return_occupied <= 0;
      else begin
        if (!return_last && mailbox_input_ready) return_occupied <= 0;
        if (core_output_tvalid) return_occupied <= 1;
        // Final commit clears effective active, hence return_valid, on this
        // edge. The hidden occupied bit is cleared on the next idle edge.
      end

      // ACK wait is inactive. The optional caller-specific input predicate
      // is exact only under its completed-input contract; all other callers
      // retain idle_fault_now's full independent event checks.
      // Retain a faulted ACK wait and never clear it on a coincident orphan.
      if (awaiting_ack && mailbox_input_ready && !protocol_fault && !idle_fault_now)
        awaiting_ack <= 0;
      if (final_commit) awaiting_ack <= 1;
    end
  end
  // BEGIN RETAINED OWNER OBSERVATIONS: no state or control changes.
  assign owner_active = active;
  assign owner_awaiting_ack = awaiting_ack;
  assign owner_fault_now = fault_now;
  assign owner_ack_accept = awaiting_ack && mailbox_input_ready && !protocol_fault && !idle_fault_now;
  // END RETAINED OWNER OBSERVATIONS
endmodule
