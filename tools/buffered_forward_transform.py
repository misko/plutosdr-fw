"""Bounded experimental derivation; the reference top stays byte-identical."""
CHANGES = [
  [
    "// Experimental three-bank, one-core FFT/product/IFFT island. No receiver use.\n// Actual banks: source CDC (slow->fast), private product (fast->fast), and\n// inverse output CDC (fast->slow). No stored forward-result bank or copy.",
    "// Experimental four-bank, one-core FFT/product/IFFT island. No receiver use.\n// Source CDC, sealed raw forward return, private product, inverse output CDC.\n// The additional forward RAM decouples realtime return from elastic arithmetic."
  ],
  [
    "module starlink_pss_fft_staged_output_impl #(",
    "module starlink_pss_fft_buffered_forward_impl #("
  ],
  [
    "  wire fast_running, slow_running;\n",
    "  wire fast_running, slow_running;\n  // BEGIN BUFFERED FORWARD DECLARATIONS\n  // One explicitly owned raw-return bank. Its lifetime is independent of the\n  // product bank; both must have completed before the phase may be reused.\n  wire forward_buffer_reserve_ready, forward_buffer_capture_ready;\n  wire forward_buffer_valid, forward_buffer_last, forward_buffer_done;\n  wire forward_buffer_busy, forward_buffer_fault, forward_buffer_read_ready;\n  wire [35:0] forward_buffer_data;\n  wire [8:0] forward_buffer_position;\n  wire [4:0] forward_buffer_exponent;\n  wire [69:0] forward_buffer_descriptor;\n  reg forward_buffer_owned;\n  // END BUFFERED FORWARD DECLARATIONS\n"
  ],
  [
    "  assign product_bank_fault = product_ram_fault || product_stage_fault;",
    "  assign product_bank_fault = product_ram_fault || product_stage_fault || forward_buffer_fault;"
  ],
  [
    "    (forward_receipt_wait ? product_bank_valid : (kernel_ready && product_bank_ready));",
    "    (forward_receipt_wait ? product_bank_valid : (forward_buffer_owned && !forward_buffer_fault));"
  ],
  [
    "    (output_bank_ready && (retained_reserved || inverse_allocation_pending || retained_reusable)) : product_bank_ready;",
    "    (output_bank_ready && (retained_reserved || inverse_allocation_pending || retained_reusable)) :\n    (product_bank_ready && (forward_buffer_owned ||\n      ((state==WAIT_BANK || state==VERIFY_LEASE) && forward_buffer_reserve_ready)));"
  ],
  [
    "    .output_bank_reserved(OWNER == 1 ? retained_reserved : engine_output_reserved),",
    "    .output_bank_reserved(OWNER == 1 ? retained_reserved : (engine_output_reserved && forward_buffer_owned)),"
  ],
  [
    "      (forward_receipt_wait ? product_bank_valid : (kernel_ready && product_bank_ready))),",
    "      (forward_receipt_wait ? product_bank_valid : (forward_buffer_owned && !forward_buffer_fault))),"
  ],
  [
    "  assign forward_retirement_valid = guard_forward_retire[0];",
    "  // BEGIN BUFFERED FORWARD OWNERSHIP\n  wire forward_buffer_reserve = state==VERIFY_LEASE && !held_phase;\n  always @(posedge fft_clk) begin\n    if (!fast_running) forward_buffer_owned<=0;\n    else begin\n      if (forward_buffer_reserve && forward_buffer_reserve_ready)\n        forward_buffer_owned<=1;\n      if (completion_accept && !held_phase) forward_buffer_owned<=0;\n    end\n  end\n  assign forward_buffer_read_ready = kernel_ready && product_bank_ready && !fast_fault;\n  starlink_pss_forward_return_bank forward_buffer (\n    .clk(fft_clk),.resetn(fast_running),\n    // A current fault may advance private storage, never product publication.\n    // Use registered quarantine here to avoid a self-referential fault cone.\n    .abort_epoch(fast_fault || result_fault),\n    .reserve_valid(forward_buffer_reserve),.reserve_ready(forward_buffer_reserve_ready),\n    .reserve_descriptor(engine_metadata),\n    .capture_valid(core_output_valid && !routed_inverse),.capture_ready(forward_buffer_capture_ready),\n    .capture_data({core_output_data[41:24],core_output_data[17:0]}),\n    .capture_position(core_output_user[8:0]),.capture_last(core_output_last),\n    .capture_exponent(core_output_user[20:16]),.capture_descriptor(engine_metadata),\n    .seal_valid(guard_commit[0] && !next_inverse),\n    .output_valid(forward_buffer_valid),.output_ready(forward_buffer_read_ready),\n    .output_data(forward_buffer_data),.output_position(forward_buffer_position),\n    .output_last(forward_buffer_last),.output_exponent(forward_buffer_exponent),\n    .output_descriptor(forward_buffer_descriptor),.done_pulse(forward_buffer_done),\n    .busy(forward_buffer_busy),.fault(forward_buffer_fault)\n  );\n  // END BUFFERED FORWARD OWNERSHIP\n  assign forward_retirement_valid = guard_forward_retire[0];"
  ],
  [
    "    .input_valid((REGISTERED_SCHEDULING ? forward_retirement_valid :\n      (return_valid && !next_inverse)) && !fast_fault && product_bank_ready),\n    .input_private_valid(guard_forward_private_offer[0] && !fast_fault && product_bank_ready),\n    .input_ready(kernel_ready),\n    .input_i(return_data[17:0]), .input_q(return_data[35:18]),\n    .input_bin_index(return_position), .input_block_exponent(return_metadata[4:0]),\n    .input_last(return_last), .input_block_start_index(return_metadata[73:10]),",
    "    .input_valid(forward_buffer_valid && !fast_fault && product_bank_ready),\n    .input_private_valid(forward_buffer_valid && !fast_fault && product_bank_ready),\n    .input_ready(kernel_ready),\n    .input_i(forward_buffer_data[17:0]), .input_q(forward_buffer_data[35:18]),\n    .input_bin_index(forward_buffer_position), .input_block_exponent(forward_buffer_exponent),\n    .input_last(forward_buffer_last), .input_block_start_index(forward_buffer_descriptor[68:5]),"
  ],
  [
    "  // Nonfinal checked results may compute privately before independent status.\n  // The final result is admitted ONLY on the original guard's qualified commit.",
    "  // The forward bank captures raw results locally; kernel/product processing\n  // starts only after the original guard has independently qualified the seal."
  ],
  [
    "    // Match the guard's exact retirement event, including a held final word.\n    // An owned bank should remain ready, but a readiness fault/stall must never\n    // let the joiner consume a word that the guard has not retired.",
    "    // Sealed replay is elastic. The realtime FFT is no longer backpressured\n    // by kernel/product capacity. Public product commit keeps current vetoes."
  ]
]

def transform(text):
    for before,after in CHANGES:
        assert text.count(before)==1, before
        text=text.replace(before,after,1)
    return text

def undo(text):
    for before,after in reversed(CHANGES):
        assert text.count(after)==1, after
        text=text.replace(after,before,1)
    return text
