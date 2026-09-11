"""Private fault snapshots; immediate public gates and scalar CDC stay literal."""
CHANGES = [
  [
    "module starlink_pss_fft_registered_abort_impl #(",
    "module starlink_pss_fft_local_fault_pipeline_impl #("
  ],
  [
    "  always @(posedge fft_clk)\n    if (!fast_running) fast_fault <= 0;\n    else if (|sticky_fault_sources) fast_fault <= 1;",
    "  // Private facts are sampled independently, before the guard/global ORs.\n  // Keep the scalar fault register as the direct CDC source. Current public\n  // vetoes and direct already-registered guard faults remain on their old edge.\n  // Other source events reach this global diagnostic one clock later.\n  reg [32:0] local_fault_snapshot;\n  always @(posedge fft_clk)\n    if (!fast_running) local_fault_snapshot <= 0;\n    else local_fault_snapshot <= admission_reject_expanded;\n  wire local_fault_profile = (INPUT_OFFER_FAULT_SUMMARY === 1) &&\n    (CONTEXTUAL_DESTINATION_SUMMARY === 1) && (retained_reserved_known === 1'b1);\n  always @(posedge fft_clk)\n    if (!fast_running) fast_fault <= 0;\n    else if (local_fault_profile ? (result_fault || (|local_fault_snapshot)) :\n      (|sticky_fault_sources)) fast_fault <= 1;"
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
