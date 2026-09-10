"""Strict additive local-first-admission source recipe; no tool launch."""

BASE = "5b68bb8b488a886c3861537eaf9643ec940003e0"
OLD_GUARD = "starlink_pss_realtime_input_guard"
GUARD = OLD_GUARD + "_local_admission"
OLD_TOP = "starlink_pss_fft_bank_owned_arithmetic_probe"
TOP = "starlink_pss_fft_bank_owned_local_admission_probe"
LOCAL = """      // BEGIN LOCAL_FIRST_ADMISSION
      // With job_started=0 the checker slot is closed: no current framing,
      // delivery or duplicate event can veto this first descriptor capture.
      // With job_started=1 a new start is a duplicate and must not overwrite it.
      // Keep every current beat/fault/certificate equation unchanged below.
      if (LOCAL_FIRST_ADMISSION && !protocol_fault && job_start && !job_started) begin
        job_started <= 1;
        descriptor <= job_descriptor;
      end
      // END LOCAL_FIRST_ADMISSION
"""


def guard_edits():
    return (
        (f"module {OLD_GUARD} #(\n", f"module {GUARD} #(\n"),
        (
            "  parameter integer BALANCED_IDENTITY_EQ = 0\n",
            "  parameter integer BALANCED_IDENTITY_EQ = 0,\n  parameter integer LOCAL_FIRST_ADMISSION = 0\n",
        ),
        (
            "  initial begin\n",
            '  initial begin\n    if (LOCAL_FIRST_ADMISSION !== 0 && LOCAL_FIRST_ADMISSION !== 1)\n      $fatal(1, "LOCAL_FIRST_ADMISSION must be zero or one");\n',
        ),
        (
            "      if (!protocol_fault && !fault_now) begin\n",
            LOCAL + "      if (!protocol_fault && !fault_now) begin\n",
        ),
        (
            "        if (job_start) begin\n",
            "        if (!LOCAL_FIRST_ADMISSION && job_start) begin\n",
        ),
    )


def top_edits():
    return (
        (f"module {OLD_TOP} #(\n", f"module {TOP} #(\n"),
        (
            "  parameter integer REGISTER_OPERANDS = 0\n",
            "  parameter integer REGISTER_OPERANDS = 0,\n  parameter integer LOCAL_FIRST_ADMISSION = 0\n",
        ),
        (
            f"  {OLD_GUARD} #(.CHECK_INPUT_BLOCK_IDENTITY(1),\n    .BALANCED_IDENTITY_EQ(REGISTERED_SCHEDULING)) input_guard (",
            f"  {GUARD} #(.CHECK_INPUT_BLOCK_IDENTITY(1),\n    .BALANCED_IDENTITY_EQ(REGISTERED_SCHEDULING),\n    .LOCAL_FIRST_ADMISSION(LOCAL_FIRST_ADMISSION)) input_guard (",
        ),
    )


def apply(source, edits, inverse=False):
    for old, new in reversed(edits) if inverse else edits:
        if inverse:
            old, new = new, old
        if source.count(old) != 1:
            raise ValueError("nonunique local-admission adaptation anchor")
        source = source.replace(old, new, 1)
    return source
