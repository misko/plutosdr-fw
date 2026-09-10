"""Literal inverse to the frozen pre-experiment three-module bodies."""

from tests.starlink_oracle.fault_cdc_contract import restore_fault_cdc

BASE = "dec20d6371f2d77b6e09c4bcdda2f3d7f8715776"


def once(source, new, old=""):
    assert source.count(new) == 1, new
    return source.replace(new, old, 1)


def restore_exact_control(source, kind):
    if kind == "fft_bank_owned_slice":
        if "parameter integer PER_CAUSE_FAULT_CDC" in source:
            source = restore_fault_cdc(source)
        source = once(source, "  parameter integer REGISTERED_SCHEDULING = 0,\n"
            "  parameter integer DISTRIBUTED_FAST_FAULT = 0,\n"
            "  parameter integer PRIVATE_NEXT_START_SCRATCH = 0\n",
            "  parameter integer REGISTERED_SCHEDULING = 0\n")
        source = once(source, "    .BALANCED_BLOCK_IDENTITY_EQ(REGISTERED_SCHEDULING),\n"
            "    .PRIVATE_NEXT_START_SCRATCH(PRIVATE_NEXT_START_SCRATCH)) joiner (",
            "    .BALANCED_BLOCK_IDENTITY_EQ(REGISTERED_SCHEDULING)) joiner (")
        source = once(source, '''  initial begin
    if (DISTRIBUTED_FAST_FAULT !== 0 && DISTRIBUTED_FAST_FAULT !== 1)
      $fatal(1, "DISTRIBUTED_FAST_FAULT must be zero or one");
    if (PRIVATE_NEXT_START_SCRATCH !== 0 && PRIVATE_NEXT_START_SCRATCH !== 1)
      $fatal(1, "PRIVATE_NEXT_START_SCRATCH must be zero or one");
  end
''')
        begin = source.index("  // BEGIN DISTRIBUTED_FAST_FAULT:")
        end = source.index("  // END DISTRIBUTED_FAST_FAULT\n") + len("  // END DISTRIBUTED_FAST_FAULT\n")
        source = source[:begin] + "  always @(posedge fft_clk)\n" \
            "    if (!fast_running) fast_fault <= 0;\n" \
            "    else if (any_fast_fault) fast_fault <= 1;\n" + source[end:]
    elif kind in {"forward_kernel_join", "kernel_rom"}:
        source = once(source, '''    if (PRIVATE_NEXT_START_SCRATCH !== 0 && PRIVATE_NEXT_START_SCRATCH !== 1)
      $fatal(1, "PRIVATE_NEXT_START_SCRATCH must be zero or one");
''')
        source = once(source, "  parameter integer BALANCED_BLOCK_IDENTITY_EQ = 0,\n"
            "  parameter integer PRIVATE_NEXT_START_SCRATCH = 0\n",
            "  parameter integer BALANCED_BLOCK_IDENTITY_EQ = 0\n")
        if kind == "forward_kernel_join":
            source = once(source, "    .BALANCED_BLOCK_IDENTITY_EQ(BALANCED_BLOCK_IDENTITY_EQ),\n"
                "    .PRIVATE_NEXT_START_SCRATCH(PRIVATE_NEXT_START_SCRATCH)\n",
                "    .BALANCED_BLOCK_IDENTITY_EQ(BALANCED_BLOCK_IDENTITY_EQ)\n")
        else:
            begin = source.index("      // BEGIN PRIVATE_NEXT_START_SCRATCH:")
            end = source.index("      // END PRIVATE_NEXT_START_SCRATCH\n\n") + len(
                "      // END PRIVATE_NEXT_START_SCRATCH\n\n")
            source = source[:begin] + source[end:]
            source = once(source, "            if (!PRIVATE_NEXT_START_SCRATCH)\n"
                "              expected_next_block_start <= input_block_start_index +\n"
                "                                           VALID_RESULTS_PER_BLOCK;\n",
                "            expected_next_block_start <= input_block_start_index +\n"
                "                                         VALID_RESULTS_PER_BLOCK;\n")
    return source
