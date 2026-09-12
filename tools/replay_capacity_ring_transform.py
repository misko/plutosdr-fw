"""Alternating private storage; original top and fault vetoes retained."""
from private_replay_sequence_transform import transform,undo
TOP_CHANGES = [
  [
    "module starlink_pss_fft_replay_capacity_buffer_impl #(",
    "module starlink_pss_fft_replay_capacity_ring_impl #("
  ],
  [
    "  starlink_pss_replay_capacity_buffer #(.WIDTH(121)) replay_fifo (",
    "  starlink_pss_replay_capacity_ring #(.WIDTH(121)) replay_fifo ("
  ],
  [
    "    .input_valid(forward_buffer_valid),.input_ready(forward_buffer_read_ready),",
    "    // Cancelled replay may write private bytes only; cancel_now above kills\n    // occupancy and publication on that edge. Healthy source handshakes match.\n    .input_valid(forward_buffer_private_replay_valid),.input_ready(forward_buffer_read_ready),"
  ]
]
