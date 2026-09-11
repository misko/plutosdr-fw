"""Exact private descriptor enable split, with unchanged bank controller."""
BANK_CHANGES = [
  [
    "module starlink_pss_forward_return_private_status #(",
    "module starlink_pss_forward_return_private_descriptor #("
  ],
  [
    "  // END PRIVATE CAPTURE PROGRESS\n",
    "  // END PRIVATE CAPTURE PROGRESS\n\n  // Private descriptor storage follows local reservation capacity, even if\n  // this edge also rejects the reservation. Unchanged state/fault logic below\n  // quarantines that copy; it cannot become replay authority before reset.\n  always @(posedge clk or negedge resetn)\n    if (!resetn) descriptor<=0;\n    else if (reserve_valid && reserve_ready) descriptor<=reserve_descriptor;\n"
  ],
  [
    "      descriptor<=0;output_position<=0;done_pulse<=0;",
    "      output_position<=0;done_pulse<=0;"
  ],
  [
    "          descriptor<=reserve_descriptor;state<=CAPTURE;",
    "          state<=CAPTURE;"
  ]
]
TOP_CHANGES = [
  [
    "module starlink_pss_fft_product_retirement_receipt_impl #(",
    "module starlink_pss_fft_private_forward_descriptor_impl #("
  ],
  [
    "  starlink_pss_forward_return_private_status forward_buffer (",
    "  starlink_pss_forward_return_private_descriptor forward_buffer ("
  ]
]
def transform(text,changes):
    for before,after in changes:
        assert text.count(before)==1,before
        text=text.replace(before,after,1)
    return text
def undo(text,changes):
    return transform(text,[(after,before) for before,after in reversed(changes)])
