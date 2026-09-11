"""Combinational topology only; no fault, seal, replay or reset latency change."""
TOP_CHANGES = [
  [
    "module starlink_pss_fft_product_current_fence_impl #(",
    "module starlink_pss_fft_balanced_forward_identity_impl #("
  ],
  [
    "  starlink_pss_forward_return_bank forward_buffer (",
    "  starlink_pss_forward_return_balanced_identity forward_buffer ("
  ]
]
BANK_CHANGES = [
  [
    "module starlink_pss_forward_return_bank #(",
    "module starlink_pss_forward_return_balanced_identity #("
  ],
  [
    "  wire capture_bad = capture_valid && (!capture_ready ||",
    "  // Preserve same-edge four-state equality, but keep each three-bit pair\n  // comparison as a separate six-input cone rather than a wide carry chain.\n  (* keep = \"true\" *) wire [23:0] capture_descriptor_groups_equal;\n  generate for (genvar group_index=0; group_index<23; group_index=group_index+1) begin : descriptor_groups\n    assign capture_descriptor_groups_equal[group_index] =\n      capture_descriptor[group_index*3 +: 3] == descriptor[group_index*3 +: 3];\n  end endgenerate\n  assign capture_descriptor_groups_equal[23] = capture_descriptor[69] == descriptor[69];\n  (* keep = \"true\" *) wire [3:0] capture_descriptor_tiles_equal;\n  generate for (genvar tile_index=0; tile_index<4; tile_index=tile_index+1) begin : descriptor_tiles\n    assign capture_descriptor_tiles_equal[tile_index] = &capture_descriptor_groups_equal[tile_index*6 +: 6];\n  end endgenerate\n  wire capture_descriptor_equal = &capture_descriptor_tiles_equal;\n  wire capture_bad = capture_valid && (!capture_ready ||"
  ],
  [
    "    ((capture_descriptor == descriptor) !== 1'b1) ||",
    "    (capture_descriptor_equal !== 1'b1) ||"
  ]
]

def transform(text,changes):
    for before,after in changes:
        assert text.count(before)==1,before
        text=text.replace(before,after,1)
    return text

def undo(text,changes):
    for before,after in reversed(changes):
        assert text.count(after)==1,after
        text=text.replace(after,before,1)
    return text
