"""Add two registered-capacity words; retain all original runtime modules."""
from private_replay_sequence_transform import transform,undo
TOP_CHANGES = [
  [
    "module starlink_pss_fft_private_replay_sequence_impl #(",
    "module starlink_pss_fft_replay_capacity_buffer_impl #("
  ],
  [
    "  wire forward_buffer_private_replay_valid;",
    "  wire forward_buffer_private_replay_valid;\n  wire replay_valid,replay_private_valid,replay_fifo_fault,replay_fifo_empty;\n  wire [1:0] replay_occupancy;\n  wire [120:0] replay_payload;\n  wire [35:0] replay_data=replay_payload[35:0];\n  wire [8:0] replay_position=replay_payload[44:36];\n  wire replay_last=replay_payload[45];\n  wire [4:0] replay_exponent=replay_payload[50:46];\n  wire [69:0] replay_descriptor=replay_payload[120:51];"
  ],
  [
    "  assign product_bank_fault = product_ram_fault || product_stage_fault || forward_buffer_private_fault;",
    "  assign product_bank_fault = product_ram_fault || product_stage_fault || forward_buffer_private_fault || replay_fifo_fault;"
  ],
  [
    "  assign forward_buffer_read_ready = kernel_ready && product_bank_ready && !fast_fault;",
    "  // Capacity stops at two registered replay slots. No current downstream READY\n  // reaches the forward bank's read enable. Actual product publication stays fenced.\n  starlink_pss_replay_capacity_buffer #(.WIDTH(121)) replay_fifo (\n    .clk(fft_clk),.resetn(fast_running),.abort_epoch(fast_fault),\n    .cancel_now(forward_buffer_fault),\n    .input_valid(forward_buffer_valid),.input_ready(forward_buffer_read_ready),\n    .input_data({forward_buffer_descriptor,forward_buffer_exponent,forward_buffer_last,forward_buffer_position,forward_buffer_data}),\n    .output_valid(replay_valid),.output_private_valid(replay_private_valid),\n    .output_ready(kernel_ready && product_bank_ready && !fast_fault),\n    .output_data(replay_payload),.occupancy(replay_occupancy),.empty(replay_fifo_empty),.fault(replay_fifo_fault)\n  );"
  ],
  [
    "    .input_valid(forward_buffer_valid && !fast_fault && product_bank_ready),",
    "    .input_valid(replay_valid && !fast_fault && product_bank_ready),"
  ],
  [
    "    .input_private_valid(forward_buffer_private_replay_valid && !fast_fault && product_bank_ready),",
    "    .input_private_valid(replay_private_valid && !fast_fault && product_bank_ready),"
  ],
  [
    "    .input_i(forward_buffer_data[17:0]), .input_q(forward_buffer_data[35:18]),",
    "    .input_i(replay_data[17:0]), .input_q(replay_data[35:18]),"
  ],
  [
    "    .input_bin_index(forward_buffer_position), .input_block_exponent(forward_buffer_exponent),",
    "    .input_bin_index(replay_position), .input_block_exponent(replay_exponent),"
  ],
  [
    "    .input_last(forward_buffer_last), .input_block_start_index(forward_buffer_descriptor[68:5]),",
    "    .input_last(replay_last), .input_block_start_index(replay_descriptor[68:5]),"
  ]
]
