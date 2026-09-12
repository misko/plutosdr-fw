"""Exact current fault regrouping; no state, latency or public check removed."""
TOP_CHANGES = [
  [
    "module starlink_pss_fft_output_retirement_receipt_impl #(",
    "module starlink_pss_fft_product_publication_cone_impl #("
  ],
  [
    "  wire handoff_fault_now = !next_inverse && forward_committed && product_bank_valid &&\n    (!forward_handoff_identity || product_bank_position != 0 || product_bank_last);",
    "  // Distribute the SAME current ownership predicate over five comparison groups.\n  // Each group combines at most five existing three-bit leaves with one enable.\n  // The full identity above still drives ACK/completion; there is no new state,\n  // delayed certificate, private bypass or changed publication/fault priority.\n  wire handoff_fault_enabled = !next_inverse && forward_committed && product_bank_valid;\n  (* keep = \"true\" *) wire [4:0] handoff_identity_fault;\n  generate for (genvar fault_group = 0; fault_group < 5; fault_group = fault_group + 1) begin : gated_handoff_fault\n    localparam integer LEAVES = fault_group == 4 ? 4 : 5;\n    assign handoff_identity_fault[fault_group] = handoff_fault_enabled &&\n      !( &handoff_leaf_equal[5*fault_group +: LEAVES] );\n  end endgenerate\n  wire handoff_fault_now = (|handoff_identity_fault) ||\n    (handoff_fault_enabled && (product_bank_position != 0 || product_bank_last));"
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
