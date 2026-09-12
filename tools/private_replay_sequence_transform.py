"""Only add a private replay offer and connect existing private sequence port."""
BANK_CHANGES = [
  [
    "module starlink_pss_forward_return_private_descriptor #(",
    "module starlink_pss_forward_return_private_replay #("
  ],
  [
    "  output wire output_valid,",
    "  output wire output_valid,\n  output wire private_replay_valid,"
  ],
  [
    "  assign output_valid = resetn && state==REPLAY && replay_valid && !fault;",
    "  assign output_valid = resetn && state==REPLAY && replay_valid && !fault;\n  // Private bookkeeping only: seal and ownership are registered in REPLAY.\n  // A current capture/control fault still vetoes output_valid above and\n  // latches fault_q on this edge. Caller must quarantine any private-only take.\n  assign private_replay_valid = resetn && state==REPLAY && replay_valid && !fault_q && !abort_epoch;"
  ]
]
TOP_CHANGES = [
  [
    "module starlink_pss_fft_output_retirement_receipt_impl #(",
    "module starlink_pss_fft_private_replay_sequence_impl #("
  ],
  [
    "  wire forward_buffer_valid, forward_buffer_last, forward_buffer_done;",
    "  wire forward_buffer_valid, forward_buffer_last, forward_buffer_done;\n  wire forward_buffer_private_replay_valid;"
  ],
  [
    "starlink_pss_forward_return_private_descriptor forward_buffer (",
    "starlink_pss_forward_return_private_replay forward_buffer ("
  ],
  [
    "    .output_valid(forward_buffer_valid),.output_ready(forward_buffer_read_ready),",
    "    .output_valid(forward_buffer_valid),.output_ready(forward_buffer_read_ready),\n    .private_replay_valid(forward_buffer_private_replay_valid),"
  ],
  [
    "    .input_private_valid(forward_buffer_valid && !fast_fault && product_bank_ready),",
    "    // Only hidden sequence state may use the registered private replay offer.\n    // Public input_valid and both actual bank publication vetoes stay current.\n    .input_private_valid(forward_buffer_private_replay_valid && !fast_fault && product_bank_ready),"
  ]
]
def transform(text, changes):
    for before, after in changes:
        assert text.count(before) == 1, before
        text = text.replace(before, after, 1)
    return text
def undo(text, changes):
    for before, after in reversed(changes):
        assert text.count(after) == 1, after
        text = text.replace(after, before, 1)
    return text
