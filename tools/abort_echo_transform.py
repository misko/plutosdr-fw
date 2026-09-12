"""Exact abort-echo isolation; no state, latency or original veto removal."""
PAIRS={
  "TOP": [
    [
      "module starlink_pss_fft_retry_admission_impl",
      "module starlink_pss_fft_abort_echo_impl"
    ],
    [
      "  wire output_published_valid, output_released_valid, output_control_fault;",
      "  wire output_published_valid, output_released_valid, output_control_fault;\n  wire output_stage_local_fault;\n  wire output_bank_local_fault = output_bank_ram_fault || output_stage_local_fault;"
    ],
    [
      "starlink_pss_completion_mailbox_stage #(.PRIVATE_FINAL_CAPTURE(1)) output_control",
      "starlink_pss_completion_local_fault #(.PRIVATE_FINAL_CAPTURE(1)) output_control"
    ],
    [
      ".bank_fault(output_bank_fault),",
      ".bank_fault(output_bank_local_fault),"
    ],
    [
      "starlink_pss_product_identity_split_capacity output_identity_stage",
      "starlink_pss_identity_local_fault output_identity_stage"
    ],
    [
      "    .abort_epoch(fast_fault || output_bank_ram_fault ||\n      (output_bank_ready !== 1'b0 && output_bank_ready !== 1'b1)),",
      "    .abort_epoch(fast_fault || output_bank_ram_fault ||\n      (output_bank_ready !== 1'b0 && output_bank_ready !== 1'b1)),\n    .local_abort_epoch(output_bank_ram_fault ||\n      (output_bank_ready !== 1'b0 && output_bank_ready !== 1'b1)),\n    .local_fault(output_stage_local_fault),"
    ]
  ],
  "STAGE": [
    [
      "module starlink_pss_product_identity_split_capacity",
      "module starlink_pss_identity_local_fault"
    ],
    [
      "  input wire clk, resetn, abort_epoch,",
      "  input wire clk, resetn, abort_epoch,\n  // Local abort excludes only an upstream abort separately vetoed by caller.\n  input wire local_abort_epoch,\n  output wire local_fault,"
    ],
    [
      "  assign fault = resetn && (fault_q || control_fault);",
      "  assign fault = resetn && (fault_q || control_fault);\n  // Additive diagnostic view. Original fault, state and handshakes are intact.\n  assign local_fault = resetn && (fault_q || (local_abort_epoch !== 1'b0) ||\n    (input_valid !== 1'b0 && input_valid !== 1'b1) ||\n    (output_ready !== 1'b0 && output_ready !== 1'b1));"
    ]
  ],
  "LEDGER": [
    [
      "module starlink_pss_descriptor_commands",
      "module starlink_pss_descriptor_local_fault"
    ],
    [
      "  output wire tags_exhausted, fault",
      "  output wire tags_exhausted, fault,\n  output wire local_fault"
    ],
    [
      "  assign fault = resetn && (fault_q || abort_now || (pending && !pending_good));",
      "  assign fault = resetn && (fault_q || abort_now || (pending && !pending_good));\n  // Caller retains abort_epoch as an immediate veto. Do not echo it through\n  // another hierarchy of fault reductions; every intrinsic cause stays live.\n  assign local_fault = resetn && (fault_q || (pending && !pending_good) ||\n    (command_valid !== 1'b0 && command_valid !== 1'b1) ||\n    (response_ready !== 1'b0 && response_ready !== 1'b1));"
    ]
  ],
  "CONTROL": [
    [
      "module starlink_pss_completion_mailbox_stage",
      "module starlink_pss_completion_local_fault"
    ],
    [
      "  wire ledger_fault, command_ready, response_valid;",
      "  wire ledger_fault, ledger_local_fault, command_ready, response_valid;"
    ],
    [
      "  assign fault = resetn && (fault_q || scalar_fault || ledger_fault);",
      "  // Child abort is exactly scalar_fault || fault_q, already vetoed here.\n  // Keep intrinsic ledger faults current, without re-importing that abort.\n  assign fault = resetn && (fault_q || scalar_fault || ledger_local_fault);"
    ],
    [
      "  starlink_pss_descriptor_commands #(",
      "  starlink_pss_descriptor_local_fault #("
    ],
    [
      ".tags_exhausted(tags_exhausted),.fault(ledger_fault)",
      ".tags_exhausted(tags_exhausted),.fault(ledger_fault),.local_fault(ledger_local_fault)"
    ]
  ]
}
NAMES={
  "TOP": [
    "starlink_pss_fft_retry_admission_impl",
    "starlink_pss_fft_abort_echo_impl"
  ],
  "STAGE": [
    "starlink_pss_product_identity_split_capacity",
    "starlink_pss_identity_local_fault"
  ],
  "LEDGER": [
    "starlink_pss_descriptor_commands",
    "starlink_pss_descriptor_local_fault"
  ],
  "CONTROL": [
    "starlink_pss_completion_mailbox_stage",
    "starlink_pss_completion_local_fault"
  ]
}

def transform(source,kind):
    for before,after in PAIRS[kind]:
        if source.count(before)!=1:raise ValueError('expected unique delta: '+before)
        source=source.replace(before,after,1)
    return source
