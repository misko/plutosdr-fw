"""Explicit observer relocation to the actual buffered consumer interface."""
OBSERVER_CHANGES = [
  [
    "dut.forward_buffer_position",
    "dut.joiner.input_bin_index"
  ],
  [
    "dut.forward_buffer_exponent",
    "dut.joiner.input_block_exponent"
  ],
  [
    "dut.forward_buffer_last",
    "dut.joiner.input_last"
  ],
  [
    "dut.forward_buffer_descriptor[68:5]",
    "dut.joiner.input_block_start_index"
  ],
  [
    "dut.forward_buffer_fault!==1",
    "(dut.forward_buffer_fault!==1 && dut.replay_fifo_fault!==1)"
  ],
  [
    "dut.forward_buffer.state!==3 || dut.forward_buffer.replay_valid!==1",
    "dut.replay_occupancy==0 || dut.replay_private_valid!==1"
  ],
  [
    "dut.forward_buffer_private_fault!==1 || dut.forward_buffer_private_replay_valid!==0",
    "dut.replay_fifo.fault_q!==1 || dut.replay_private_valid!==0"
  ]
]
BOUNDARY_CHANGES = [
  [
    "dut.forward_buffer_valid && dut.kernel_ready && dut.forward_buffer_position==position_target",
    "dut.joiner.input_valid && dut.kernel_ready && dut.joiner.input_bin_index==position_target"
  ]
]
