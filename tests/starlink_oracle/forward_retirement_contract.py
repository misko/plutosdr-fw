"""Literal inverse of the additive forward-only certified retirement output."""
import re

from tests.starlink_oracle.exact_control_contract import restore_exact_control


def once(source, new, old=""):
    assert source.count(new) == 1, new
    return source.replace(new, old, 1)


FORWARD_BODY = '''
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
'''


def restore_forward_guard(source):
    source = once(source, '''  parameter integer USE_PREFLIGHT_REASON_ONLY = 0,
  // Parallel forward-only retirement, never a replacement for global faults.
  // Caller proves mailbox_input_fault == forward_mailbox_fault | C and
  // C implies inverse_phase from actual mailbox input-valid wiring. Sticky
  // mailbox faults remain in forward_mailbox_fault in EVERY phase.
  parameter integer USE_FORWARD_RETIREMENT = 0
''', "  parameter integer USE_PREFLIGHT_REASON_ONLY = 0\n")
    source = once(source, '''  input wire inverse_phase,
  input wire forward_mailbox_fault,
  output wire forward_retirement_valid,
''')
    source = once(source, '''    if (USE_FORWARD_RETIREMENT != 0 && USE_FORWARD_RETIREMENT != 1)
      $fatal(1, "USE_FORWARD_RETIREMENT must be zero or one");
''')
    return once(source, FORWARD_BODY)


def restore_forward_wrapper(source):
    if "parameter integer DISTRIBUTED_FAST_FAULT" in source:
        source = restore_exact_control(source, "fft_bank_owned_slice")
    source = once(source, "  wire forward_retirement_valid;\n")
    source = once(source, '''    .USE_PREFLIGHT_REASON_ONLY(REGISTERED_SCHEDULING),
    .USE_FORWARD_RETIREMENT(REGISTERED_SCHEDULING)) result_guard''',
        "    .USE_PREFLIGHT_REASON_ONLY(REGISTERED_SCHEDULING)) result_guard")
    source = once(source, '''    .inverse_phase(next_inverse), .forward_mailbox_fault(output_bank_fault),
    .forward_retirement_valid(forward_retirement_valid),
''')
    return once(source, '''.input_valid((REGISTERED_SCHEDULING ? forward_retirement_valid :
      (return_valid && !next_inverse)) && !fast_fault && product_bank_ready)''',
        ".input_valid(return_valid && !next_inverse && !fast_fault && product_bank_ready)")


def restore_forward_actual(source):
    for addition in ("SHADOW", "RECEIPT"):
        pattern = rf"^  *// BEGIN FORWARD_RETIREMENT_{addition}.*?^  *// END FORWARD_RETIREMENT_{addition}\n"
        source, count = re.subn(pattern, "", source, flags=re.MULTILINE | re.DOTALL)
        assert count == 1
    return source
