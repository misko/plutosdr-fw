"""Only two private abort cones change; public current vetoes stay intact."""
CHANGES = [
  [
    "module starlink_pss_fft_output_identity_impl #(",
    "module starlink_pss_fft_registered_abort_impl #("
  ],
  [
    "    .abort_epoch(fast_fault || result_fault),",
    "    .abort_epoch(fast_fault),"
  ],
  [
    "    .abort_epoch(fast_fault || result_fault || output_bank_ram_fault ||",
    "    .abort_epoch(fast_fault || output_bank_ram_fault ||"
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
