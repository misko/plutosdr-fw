"""Exact private completion-fact experiment; no public checker removal."""
CHANGES = [
  [
    "module starlink_pss_fft_buffered_forward_impl #(",
    "module starlink_pss_fft_completion_local_impl #("
  ],
  [
    "  starlink_pss_admission_certificate #(.CHECKS(42)) completion_gate (",
    "  // Completion requests exist only in ACK_DRAIN. The six preflight facts\n  // (expanded rejection bits 31:26) are zero outside VERIFY_LEASE/ARM_JOB.\n  // Drop only those provably inactive facts from this PRIVATE snapshot.\n  // All public current-fault vetoes, sticky quarantine and identity checks stay.\n  wire [35:0] completion_local_checks = {completion_checks[41:32],completion_checks[25:0]};\n  starlink_pss_admission_certificate #(.CHECKS(36),.PRIVATE_FACT_CAPTURE(1)) completion_gate ("
  ],
  [
    "    .checks_good(completion_checks), .permit(completion_permit),",
    "    .checks_good(completion_local_checks), .permit(completion_permit),"
  ]
]

def transform(text):
    for before,after in CHANGES:
        assert text.count(before)==1,before
        text=text.replace(before,after,1)
    return text

def undo(text):
    for before,after in reversed(CHANGES):
        assert text.count(after)==1,after
        text=text.replace(after,before,1)
    return text
