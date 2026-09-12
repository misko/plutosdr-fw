"""Separate duplicate upstream cancellation; preserve full buffer behavior."""
from private_replay_sequence_transform import transform,undo
TOP_CHANGES = [
  [
    "module starlink_pss_fft_replay_capacity_ring_impl #(",
    "module starlink_pss_fft_replay_local_fault_impl #("
  ],
  [
    "  wire replay_valid,replay_private_valid,replay_fifo_fault,replay_fifo_empty;",
    "  wire replay_valid,replay_private_valid,replay_fifo_fault,replay_fifo_empty;\n  wire replay_fifo_local_fault;"
  ],
  [
    " || replay_fifo_fault;",
    " || replay_fifo_local_fault;"
  ],
  [
    "  starlink_pss_replay_capacity_ring #(.WIDTH(121)) replay_fifo (",
    "  starlink_pss_replay_local_fault_ring #(.WIDTH(121)) replay_fifo ("
  ],
  [
    ".empty(replay_fifo_empty),.fault(replay_fifo_fault)",
    ".empty(replay_fifo_empty),.fault(replay_fifo_fault),.local_fault(replay_fifo_local_fault)"
  ]
]
BANK_CHANGES = [
  [
    "module starlink_pss_replay_capacity_ring #(",
    "module starlink_pss_replay_local_fault_ring #("
  ],
  [
    "  output wire empty,fault",
    "  output wire empty,fault,local_fault"
  ],
  [
    "  assign fault=resetn && (fault_q || control_bad);",
    "  assign fault=resetn && (fault_q || control_bad);\n  // Known upstream cancellation already directly vetoes both publication sites.\n  // Do not echo it into the same-edge shared guard path. Malformed controls and\n  // sticky cancellation remain local faults; all ownership behavior is unchanged.\n  wire local_control_bad=(abort_epoch !== 1'b0) ||\n    (cancel_now !== 1'b0 && cancel_now !== 1'b1) ||\n    (input_valid !== 1'b0 && input_valid !== 1'b1) ||\n    (output_ready !== 1'b0 && output_ready !== 1'b1) || count>2;\n  assign local_fault=resetn && (fault_q || local_control_bad);"
  ]
]
