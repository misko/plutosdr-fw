"""Exact late-selector refactor; no state, fault or handshake changes."""
BANK_CHANGES = [
  [
    "module starlink_pss_product_identity_split_capacity (",
    "module starlink_pss_product_identity_parallel_reference ("
  ],
  [
    "  input wire [69:0] input_metadata, reference_metadata,",
    "  input wire [69:0] input_metadata, reference_metadata,\n  input wire [69:0] retiring_metadata,\n  input wire reference_select,"
  ],
  [
    "  wire identity_good = (input_metadata == reference_metadata) === 1'b1;",
    "  // Compare both stable references before the late first-word load selector.\n  // Keep raw four-state equality until after selection; only known true certifies.\n  (* keep = \"true\" *) wire match_held = input_metadata == reference_metadata;\n  (* keep = \"true\" *) wire match_retiring = input_metadata == retiring_metadata;\n  wire identity_good = (reference_select ? match_retiring : match_held) === 1'b1;"
  ]
]
TOP_CHANGES = [
  [
    "module starlink_pss_fft_forward_private_status_impl #(",
    "module starlink_pss_fft_parallel_product_identity_impl #("
  ],
  [
    "  starlink_pss_product_identity_split_capacity product_identity_stage (",
    "  starlink_pss_product_identity_parallel_reference product_identity_stage ("
  ],
  [
    "    .reference_metadata(product_writer_metadata_load ? staged_product_metadata : product_writer_metadata),",
    "    .reference_metadata(product_writer_metadata), .retiring_metadata(staged_product_metadata),\n    .reference_select(product_writer_metadata_load),"
  ]
]
def transform(text,changes):
    for before,after in changes:
        assert text.count(before)==1,before
        text=text.replace(before,after,1)
    return text

def undo(text,changes):
    return transform(text,[(after,before) for before,after in reversed(changes)])
