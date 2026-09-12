"""Exact ownership-only lock delta; no publication or completion predicate changes."""
PAIRS = [
  [
    "module starlink_pss_fft_retry_admission_impl",
    "module starlink_pss_fft_ownership_lock_impl"
  ],
  [
    "  reg output_descriptor_locked;",
    "  // Existing mailbox ownership freezes the accepted descriptor. The published\n  // receipt bridges P_EMPTY to the following reader-release consumption edge.\n  // Neither term is publication permission; all current fault vetoes remain.\n  wire output_descriptor_locked = output_publication_busy || retained_published;"
  ],
  [
    "      output_descriptor_locked<=0;\n",
    ""
  ],
  [
    "        output_descriptor_locked<=1;\n",
    ""
  ],
  [
    "inverse_descriptor_live<=0;retained_published<=0;output_descriptor_locked<=0;",
    "inverse_descriptor_live<=0;retained_published<=0;"
  ]
]

def transform(source):
    for before, after in PAIRS:
        if source.count(before) != 1:
            raise ValueError('expected unique ownership delta: '+before)
        source=source.replace(before,after,1)
    return source

