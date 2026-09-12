"""Local output capacity; retain sealed FFT replay and actual publication."""
from private_replay_sequence_transform import transform,undo
TOP_CHANGES = [
  [
    "module starlink_pss_fft_private_replay_sequence_impl #(",
    "module starlink_pss_fft_product_registered_capacity_impl #("
  ],
  [
    "    (!product_stage_fault && (product_identity_idle ||\n      ((staged_product_last === 1'b0) && (product_bank_ready === 1'b1) && (fast_fault === 1'b0))) && !fast_fault);",
    "    (!product_stage_fault && product_identity_idle && !fast_fault);"
  ],
  [
    "  starlink_pss_product_identity_parallel_reference product_identity_stage (",
    "  starlink_pss_product_identity_registered_capacity product_identity_stage ("
  ],
  [
    "  // Nonfinal refill and all actual bank publication checks remain unchanged.",
    "  // Nonfinal retirement and all actual bank publication checks remain unchanged.\n  // This elastic product stage intentionally does not refill on retirement."
  ],
  [
    "  // Same live private-slot capacity and final-slot restriction as the actual\n  // product stage. This is lookahead for READY, never publication authority.",
    "  // Local registered occupancy is the only product-stage capacity source.\n  // No same-edge refill from downstream READY; never publication authority."
  ]
]
BANK_CHANGES = [
  [
    "module starlink_pss_product_identity_parallel_reference (",
    "module starlink_pss_product_identity_registered_capacity ("
  ],
  [
    "// Do not pause refill here: the actual FFT return path cannot absorb that gap.",
    "// This variant is only for replay AFTER whole-block FFT capture and seal.\n// It intentionally inserts a refill bubble; throughput must be measured."
  ],
  [
    "  assign input_ready = live && (!full || ((output_last === 1'b0) && refill_capacity));",
    "  assign input_ready = live && !full;"
  ],
  [
    "  // continuous; output retirement and current fault/reset vetoes are unchanged.",
    "  // elastic here; output retirement and current fault/reset vetoes are unchanged."
  ],
  [
    "  // Final publication permission MUST NOT feed this input.",
    "  // Retained for interface compatibility; this variant does not use it."
  ]
]
OBSERVER_CHANGES = [
  [
    "  reg parallel_identity_expected,parallel_identity_take;",
    "  reg parallel_identity_expected,parallel_identity_take;\n  integer capacity_first_retire=0,capacity_first_capture=0;"
  ],
  [
    "      parallel_identity_checks=parallel_identity_checks+1;",
    "      parallel_identity_checks=parallel_identity_checks+1;\n      if(dut.product_stage_ready !== (dut.product_identity_stage.live && !dut.product_identity_stage.full))\n        $fatal(1,\"product input capacity is not registered occupancy\");\n      if(dut.product_writer_metadata_load)begin\n        if(dut.product_stage_ready!==0)$fatal(1,\"product stage refilled on first retirement\");\n        capacity_first_retire=capacity_first_retire+1;\n      end"
  ],
  [
    "        parallel_identity_captures=parallel_identity_captures+1;",
    "        parallel_identity_captures=parallel_identity_captures+1;\n        if(dut.product_identity_stage.input_position==0)capacity_first_capture=capacity_first_capture+1;\n        if(dut.staged_product_valid)$fatal(1,\"product stage overwrote occupied slot\");"
  ],
  [
    "parallel_identity_refills<18",
    "parallel_identity_refills!=0 || capacity_first_retire<18 || capacity_first_capture<18"
  ],
  [
    "\"PARALLEL_PRODUCT_IDENTITY_PASS checks=%0d captures=%0d first_refills=%0d four_state_exact=1 same_edge_capture=1\",",
    "\"REGISTERED_PRODUCT_CAPACITY_PASS checks=%0d captures=%0d first_refills=%0d first_retire=%0d first_capture=%0d four_state_exact=1 same_edge_capture=1\","
  ],
  [
    "parallel_identity_checks,parallel_identity_captures,parallel_identity_refills);",
    "parallel_identity_checks,parallel_identity_captures,parallel_identity_refills,capacity_first_retire,capacity_first_capture);"
  ]
]
