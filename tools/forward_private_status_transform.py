"""Split private status from the unchanged immediate local/public fault."""
TOP_CHANGES = [
  [
    "module starlink_pss_fft_balanced_forward_identity_impl #(",
    "module starlink_pss_fft_forward_private_status_impl #("
  ],
  [
    "wire forward_buffer_busy, forward_buffer_fault, forward_buffer_read_ready;",
    "wire forward_buffer_busy, forward_buffer_fault, forward_buffer_private_fault, forward_buffer_read_ready;"
  ],
  [
    "assign product_bank_fault = product_ram_fault || product_stage_fault || forward_buffer_fault;",
    "assign product_bank_fault = product_ram_fault || product_stage_fault || forward_buffer_private_fault;"
  ],
  [
    "wire replay_publication_fault = offered_external_fault_now || result_fault ||",
    "wire replay_publication_fault = offered_external_fault_now || forward_buffer_fault || result_fault ||"
  ],
  [
    "  starlink_pss_forward_return_balanced_identity forward_buffer (",
    "  starlink_pss_forward_return_private_status forward_buffer ("
  ],
  [
    "    .busy(forward_buffer_busy),.fault(forward_buffer_fault)",
    "    .busy(forward_buffer_busy),.fault(forward_buffer_fault),.private_fault(forward_buffer_private_fault)"
  ],
  [
    "    (guard_offered_local_fault === 2'b00);",
    "    (guard_offered_local_fault === 2'b00) && (forward_buffer_fault === 1'b0);"
  ],
  [
    "assign registered_quarantine = fast_fault || result_fault ||",
    "assign registered_quarantine = fast_fault || forward_buffer_private_fault || result_fault ||"
  ]
]
BANK_CHANGES = [
  [
    "module starlink_pss_forward_return_balanced_identity #(",
    "module starlink_pss_forward_return_private_status #("
  ],
  [
    "  output wire busy, fault",
    "  output wire busy, fault, private_fault"
  ],
  [
    "  assign fault = resetn && (fault_q || fault_now);",
    "  assign fault = resetn && (fault_q || fault_now);\n  // Private scheduling observes the existing sticky register. Current local\n  // rejection and public publication fences must still consume fault above.\n  assign private_fault = fault_q;"
  ]
]
PRIVATE_READY = ("(forward_buffer_owned && !forward_buffer_fault)", "(forward_buffer_owned && !forward_buffer_private_fault)")

def transform(text,changes):
    for before,after in changes:
        assert text.count(before)==1,before
        text=text.replace(before,after,1)
    return text

def top(text):
    text=transform(text,TOP_CHANGES)
    before,after=PRIVATE_READY
    assert text.count(before)==2
    return text.replace(before,after)

def undo_top(text):
    before,after=PRIVATE_READY
    assert text.count(after)==2
    text=text.replace(after,before)
    for before,after in reversed(TOP_CHANGES):
        assert text.count(after)==1
        text=text.replace(after,before,1)
    return text
