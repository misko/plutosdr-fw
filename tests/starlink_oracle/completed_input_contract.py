"""Exact inverse of the additive completed-input guard specialization.

This adapts earlier whole-source delta checks; it is not a behavioral proof of
the enabled producer premise. Every allowed addition/substitution is explicit,
including the full specialized fault expressions. Full faults/reasons and all
sequential logic are left untouched for the older complete-source comparison.
"""
import re


def _tokens(source):
    return re.sub(r"\s+", "", re.sub(r"//[^\n]*", "", source))


def restore_default_completed_input_guard(source):
    source = _tokens(source)
    additions = (
        ", parameter integer USE_COMPLETED_INPUT_FAULT = 0",
        "input wire completed_input_certified,",
        "input wire completed_input_fault_now,",
        ('if (USE_COMPLETED_INPUT_FAULT != 0 && USE_COMPLETED_INPUT_FAULT != 1) '
         '$fatal(1, "USE_COMPLETED_INPUT_FAULT must be zero or one");'),
        """
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
        wire return_phase_allowed = !USE_COMPLETED_INPUT_FAULT || completed_input_certified;
        wire nonfinal_public_fault = USE_COMPLETED_INPUT_FAULT ? completed_return_fault_now : fault_now;
        wire final_public_fault = USE_COMPLETED_INPUT_FAULT ? completed_final_fault_now : final_fault_now;
        """,
    )
    substitutions = (
        ("""
         assign mailbox_input_valid = resetn && active && !protocol_fault && return_valid &&
           return_phase_allowed &&
           ((!return_last && !nonfinal_public_fault) ||
            (return_last && final_qualified && !final_public_fault));
         """, """
         assign mailbox_input_valid = resetn && active && !protocol_fault && return_valid &&
           ((!return_last && !fault_now) || (return_last && final_qualified && !final_fault_now));
         """),
        ("""
         assign mailbox_commit_valid = resetn && active && !protocol_fault && return_valid &&
           return_phase_allowed && return_last && final_qualified && !final_public_fault;
         """, """
         assign mailbox_commit_valid = resetn && active && !protocol_fault && return_valid &&
           return_last && final_qualified && !final_fault_now;
         """),
    )
    for old, new in [*((addition, "") for addition in additions), *substitutions]:
        old, new = _tokens(old), _tokens(new)
        assert source.count(old) == 1, f"completed-input exact delta mismatch: {old}"
        source = source.replace(old, new, 1)
    return source
