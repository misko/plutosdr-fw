"""Exact product-publication fence delta, with the rejected parent intact."""
CHANGES = [
  [
    "module starlink_pss_fft_local_fault_pipeline_impl #(",
    "module starlink_pss_fft_product_current_fence_impl #("
  ],
  [
    "  wire product_commit_authorized = forward_committed && !external_fault_now && !result_fault;",
    "  // A current guard-local event must veto the actual final product write.\n  // Waiting for its latched diagnostic cannot retract bank ownership.\n  wire product_commit_authorized = forward_committed && !external_fault_now && !result_fault &&\n    (guard_offered_local_fault === 2'b00);"
  ]
]

def transform(text):
    for before,after in CHANGES:
        assert text.count(before)==1,before
        text=text.replace(before,after,1)
    return text

def undo(text):
    for before,after in reversed(CHANGES):
        assert text.count(after)==1,after
        text=text.replace(after,before,1)
    return text
