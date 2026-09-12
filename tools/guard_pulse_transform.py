"""Retimed private occupancy from the existing checked completion pulse."""
PAIRS={
  "TOP": [
    [
      "module starlink_pss_fft_retry_admission_impl",
      "module starlink_pss_fft_guard_pulse_impl"
    ],
    [
      "  starlink_pss_result_guard_owner_view #(",
      "  starlink_pss_result_guard_commit_pulse #("
    ]
  ],
  "GUARD": [
    [
      "module starlink_pss_result_guard_owner_view",
      "module starlink_pss_result_guard_commit_pulse"
    ],
    [
      "  reg active_private, awaiting_ack;",
      "  // The existing checked completion pulse provides the visible transition\n  // immediately; private storage consumes it on the following edge. Case\n  // equality preserves procedural-if behavior for an unknown final commit.\n  reg active_storage, ack_storage;\n  wire completion_receipt = commit_pulse === 1'b1;\n  wire active_private = active_storage && !completion_receipt;\n  wire awaiting_ack = ack_storage || completion_receipt;"
    ],
    [
      "      active_private <= 0;\n      awaiting_ack <= 0;",
      "      active_storage <= 0;\n      ack_storage <= 0;"
    ],
    [
      "      if (protocol_fault) active_private <= 0;\n      else if (job_accept) active_private <= 1;\n      else if (final_commit) active_private <= 0;",
      "      if (protocol_fault) active_storage <= 0;\n      else if (job_accept) active_storage <= 1;\n      else if (completion_receipt) active_storage <= 0;"
    ],
    [
      "      if (awaiting_ack && mailbox_input_ready && !protocol_fault && private_ack_clear_allowed)\n        awaiting_ack <= 0;\n      if (final_commit) awaiting_ack <= 1;",
      "      // A legal ACK during the pulse consumes it, rather than resurrecting\n      // a private wait after that pulse falls. Current ACK checks stay literal.\n      if (completion_receipt) ack_storage <= 1;\n      if (awaiting_ack && mailbox_input_ready && !protocol_fault && private_ack_clear_allowed)\n        ack_storage <= 0;"
    ]
  ]
}
NAMES={
  "TOP": [
    "starlink_pss_fft_retry_admission_impl",
    "starlink_pss_fft_guard_pulse_impl"
  ],
  "GUARD": [
    "starlink_pss_result_guard_owner_view",
    "starlink_pss_result_guard_commit_pulse"
  ]
}

def transform(source,kind):
    for before,after in PAIRS[kind]:
        if source.count(before)!=1:raise ValueError('expected unique delta: '+before)
        source=source.replace(before,after,1)
    return source
