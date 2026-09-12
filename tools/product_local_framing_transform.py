"""Exact source delta: cofactor only the product bank's own framing fault."""
from private_replay_sequence_transform import transform, undo
BANK_CHANGES = [
  [
    "module starlink_pss_product_mailbox_staged_identity #(",
    "module starlink_pss_product_mailbox_local_framing #("
  ],
  [
    "  input wire input_commit_authorized,",
    "  input wire input_commit_authorized,\n  // Excludes only this bank's own current framing fault. Publication below\n  // requires known-good local framing; the original full permit remains visible.\n  input wire input_other_commit_authorized,"
  ],
  [
    "          if (!EXPLICIT_COMMIT || input_commit_authorized)",
    "          if ((!EXPLICIT_COMMIT || input_other_commit_authorized) &&\n              (input_framing_valid === 1'b1))"
  ]
]
TOP_CHANGES = [
  [
    "module starlink_pss_fft_private_replay_sequence_impl #(",
    "module starlink_pss_fft_product_local_framing_impl #("
  ],
  [
    "  wire product_commit_authorized = forward_committed && !external_fault_now && !result_fault &&",
    "  // Only the product bank may cofactor its own current framing check. Keep\n  // external_fault_now and original permission unchanged for all diagnostics,\n  // public eligibility and other consumers. The bank requires known-good framing.\n  wire product_nonlocal_fault_now = input_fault_now || input_guard_fault || slow_faults_fast ||\n    vendor_fault_now || fast_fault || kernel_fault || product_overflow || product_bank_fault ||\n    handoff_fault_now || cutover_fault_now ||\n    (|cutover_reasons) || retained_fault_now || (|retained_reasons);\n  wire product_other_commit_authorized = forward_committed && !product_nonlocal_fault_now && !result_fault &&\n    (guard_offered_local_fault === 2'b00) && (forward_buffer_fault === 1'b0);\n  wire product_commit_authorized = forward_committed && !external_fault_now && !result_fault &&"
  ],
  [
    "starlink_pss_product_mailbox_staged_identity #(",
    "starlink_pss_product_mailbox_local_framing #("
  ],
  [
    "    .input_commit_authorized(product_commit_authorized),",
    "    .input_commit_authorized(product_commit_authorized),\n    .input_other_commit_authorized(product_other_commit_authorized),"
  ]
]

