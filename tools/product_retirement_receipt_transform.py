"""Private final retirement from registered ownership; public gates unchanged."""
TOP_CHANGES = [
  [
    "module starlink_pss_fft_parallel_product_identity_impl #(",
    "module starlink_pss_fft_product_retirement_receipt_impl #("
  ],
  [
    "  // RAM may rewrite an unpublished LAST, but the private slot retires only\n  // on actual qualified publication. Known-only readiness avoids a control-X\n  // feedback loop through the stage's immediate control-fault detection.",
    "  // Public eligibility remains current and is also the fault-injection boundary.\n  // Private LAST retirement instead observes the bank's registered ownership.\n  // Nonfinal refill and all actual bank publication checks remain unchanged."
  ],
  [
    "    ((staged_product_last === 1'b0) || (product_commit_authorized === 1'b1));",
    "    ((staged_product_last === 1'b0) || (product_commit_authorized === 1'b1));\n  wire product_owner_request, product_owner_ack_sync;\n  wire product_published_receipt = (product_owner_request ^ product_owner_ack_sync) === 1'b1;\n  wire product_retire_ready = (fast_fault === 1'b0) &&\n    (((staged_product_last === 1'b0) && (product_bank_ready === 1'b1)) ||\n     ((staged_product_last === 1'b1) && product_published_receipt));"
  ],
  [
    "    .output_valid(staged_product_valid), .output_ready(staged_product_ready),",
    "    .output_valid(staged_product_valid), .output_ready(product_retire_ready),"
  ],
  [
    "    .owner_request(), .owner_ack_sync(), .writer_reset_idle(product_writer_idle),",
    "    .owner_request(product_owner_request), .owner_ack_sync(product_owner_ack_sync), .writer_reset_idle(product_writer_idle),"
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
