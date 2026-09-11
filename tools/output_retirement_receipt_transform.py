"""Private output retirement only; public acceptance and bank checks unchanged."""
TOP_CHANGES = [
  [
    "module starlink_pss_fft_private_forward_descriptor_impl #(",
    "module starlink_pss_fft_output_retirement_receipt_impl #("
  ],
  [
    "  starlink_pss_product_identity_split_capacity output_identity_stage (",
    "  // Current output_stage_consume remains publication eligibility. The private\n  // final slot instead retires from registered bank ownership, one edge later.\n  // This receipt cannot authorize bank writes or retained-controller completion.\n  wire output_published_receipt = (output_request ^ output_ack_sync) === 1'b1;\n  wire output_retire_ready = (fast_fault === 1'b0) &&\n    (((output_stage_last === 1'b0) && (output_bank_ready === 1'b1)) ||\n     ((output_stage_last === 1'b1) && output_published_receipt));\n  starlink_pss_product_identity_split_capacity output_identity_stage ("
  ],
  [
    ".output_valid(output_stage_valid),.output_ready(output_stage_consume)",
    ".output_valid(output_stage_valid),.output_ready(output_retire_ready)"
  ]
]
def transform(text):
    for before,after in TOP_CHANGES:
        assert text.count(before)==1,before
        text=text.replace(before,after,1)
    return text
def undo(text):
    for before,after in reversed(TOP_CHANGES):
        assert text.count(after)==1,after
        text=text.replace(after,before,1)
    return text
