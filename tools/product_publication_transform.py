"""Conservative writer-phase product publication; reader checks remain full."""
PAIRS=[
  [
    "module starlink_pss_fft_phase_publication_impl",
    "module starlink_pss_fft_product_publication_impl"
  ],
  [
    "  wire product_commit_authorized = forward_committed && !external_fault_now && !result_fault &&\n    (guard_offered_local_fault === 2'b00) && (forward_buffer_fault === 1'b0);",
    "  // Preserve the complete handoff predicate for reader ACK and diagnostics.\n  // The same-clock bank cannot be reader-valid while writer-ready. An explicit\n  // known-idle reader fence makes handoff_fault_now inactive at publication;\n  // unknown or reader-owned states cannot authorize a new bank publication.\n  wire product_writer_fault = input_fault_now || input_guard_fault || slow_faults_fast ||\n    vendor_fault_now || fast_fault || kernel_fault || product_overflow || product_bank_fault ||\n    product_bank_framing_fault_now || cutover_fault_now ||\n    (|cutover_reasons) || retained_fault_now || (|retained_reasons);\n  wire original_product_commit_authorized = forward_committed && !external_fault_now && !result_fault &&\n    (guard_offered_local_fault === 2'b00) && (forward_buffer_fault === 1'b0);\n  wire product_commit_authorized = forward_committed && (product_bank_valid === 1'b0) &&\n    !product_writer_fault && !result_fault &&\n    (guard_offered_local_fault === 2'b00) && (forward_buffer_fault === 1'b0);"
  ]
]
def transform(source):
    for before,after in PAIRS:
        if source.count(before)!=1:raise ValueError('expected unique product delta: '+before)
        source=source.replace(before,after,1)
    return source
