"""Only remove phase-inactive preflight from quiet publication, not acquisition."""
PAIRS=[
  [
    "module starlink_pss_fft_guard_pulse_impl",
    "module starlink_pss_fft_phase_publication_impl"
  ],
  [
    "  wire output_replay_accept;",
    "  // Quiet publication already requires !preparing. Its phase-gated current\n  // preflight term is therefore zero, including four-state behavior. Keep the\n  // full predicate above and all acquisition/diagnostic checks unchanged.\n  wire replay_phase_fault = offered_external_fault_now || forward_buffer_fault || result_fault ||\n    output_bank_fault || output_bank_framing_fault_now ||\n    core_status_valid || core_output_valid || event_frame ||\n    summary_offer_beat || summary_offer_complete;\n  wire output_replay_accept;"
  ],
  [
    "      replay_publication_context && !replay_publication_fault;",
    "      replay_publication_context && !replay_phase_fault;"
  ]
]

def transform(source):
    for before,after in PAIRS:
        if source.count(before)!=1:raise ValueError('expected unique phase delta: '+before)
        source=source.replace(before,after,1)
    return source
