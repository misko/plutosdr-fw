"""Exact held-job request delta; current guard/publication predicates retained."""
from private_replay_sequence_transform import transform,undo
TOP_CHANGES = [
  [
    "module starlink_pss_fft_private_replay_sequence_impl #(",
    "module starlink_pss_fft_retry_admission_impl #("
  ],
  [
    "  // Availability may legitimately rise while inverse allocation is pending.\n  // Do not freeze a rejected capacity snapshot; begin validation only after\n  // these small private-capacity predicates are ready. No fault tree here.\n  wire admission_request = CERTIFIED_ADMISSION && job_valid &&\n    guard_capacity[next_inverse] && cutover_admission_capacity &&\n    (!next_inverse || inverse_descriptor_live);\n  starlink_pss_admission_certificate #(.CHECKS(36),.PRIVATE_FACT_CAPTURE(1)) admission_gate (",
    "  // The request identifies a held job, not current cross-block readiness.\n  // Retry rejected private snapshots while allocation/reset capacity settles.\n  // Current guard readiness, quarantine, core-cutover validation and all\n  // publication vetoes remain independent authorities, exactly as before.\n  wire admission_request = CERTIFIED_ADMISSION && job_valid;\n  starlink_pss_admission_retry_certificate #(.CHECKS(36)) admission_gate ("
  ]
]
