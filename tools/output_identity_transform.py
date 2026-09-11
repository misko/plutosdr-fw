"""Exact derived output identity experiment; reference modules stay unchanged."""
TOP_CHANGES = [
  [
    "module starlink_pss_fft_buffered_forward_impl #(",
    "module starlink_pss_fft_output_identity_impl #("
  ],
  [
    "  wire output_bank_ready, output_bank_fault, output_bank_framing_fault_now;",
    "  wire output_bank_ready, output_bank_fault, output_bank_framing_fault_now;\n  wire output_bank_ram_fault,output_stage_fault,output_stage_ready,output_stage_valid;\n  wire output_stage_last,output_stage_identity_good,output_stage_consume,output_stage_idle;\n  wire [35:0] output_stage_data;\n  wire [8:0] output_stage_position;\n  wire [69:0] output_stage_metadata;\n  wire [36:0] output_writer_metadata;\n  wire output_writer_metadata_load;\n  wire output_stage_final_valid = output_stage_valid && output_stage_last;"
  ],
  [
    "  assign inverse_guard_ready = (output_bank_ready && output_complete_ready) || output_released_valid;",
    "  assign inverse_guard_ready = (output_bank_ready && output_complete_ready && output_stage_ready) || output_released_valid;"
  ],
  [
    "  wire output_replay_private_ready = output_bank_ready && output_descriptor_valid;",
    "  wire output_replay_private_ready = output_bank_ready && output_descriptor_valid && output_stage_final_valid;"
  ],
  [
    "    assign output_replay_accept = output_replay_valid && output_descriptor_valid && output_bank_ready && !common_current_fault;",
    "    assign output_replay_accept = output_replay_valid && output_descriptor_valid && output_bank_ready && output_stage_final_valid && !common_current_fault;"
  ],
  [
    "    assign output_replay_accept = output_replay_valid && output_descriptor_valid && output_bank_ready &&\n",
    "    assign output_replay_accept = output_replay_valid && output_descriptor_valid && output_bank_ready && output_stage_final_valid &&\n"
  ],
  [
    "  starlink_pss_output_reset_receipt #(.METADATA_WIDTH(37), .RESET_RELEASE_EXTERNAL(1),\n      .EXPLICIT_COMMIT(1)) output_bank (\n    .input_clk(fft_clk), .input_resetn(fast_running),\n    // Payload selection follows registered private ownership, not a fault-\n    // gated public-valid signal. A fault must not switch the metadata mux and\n    // then traverse a wide framing comparator back into global control.\n    .input_valid(output_publication_busy ? output_replay_valid : guard_private_out[1]),\n    .input_commit_authorized(output_replay_accept), .input_ready(output_bank_ready),\n    .input_data(output_publication_busy ? output_replay_data : guard_return_data[1]),\n    .input_position(output_publication_busy ? 9'd511 : guard_return_position[1]),\n    .input_last(output_publication_busy ? 1'b1 : guard_last_out[1]),\n    .input_metadata_select(output_publication_busy),\n    .input_metadata_live({inverse_tag,guard_return_metadata[1][4:0]}),\n    .input_metadata_replay({output_replay_tag,output_descriptor_payload[4:0]}), .input_fault(output_bank_fault),\n    .input_framing_fault_now(output_bank_framing_fault_now),\n    .output_clk(clk), .output_resetn(slow_running),\n    .output_valid(slow_output_valid), .output_ready(output_ready && slow_metadata_valid && !fault),\n    .output_data(output_data), .output_position(output_position), .output_last(output_last),\n    .output_metadata(output_bank_metadata), .owner_request(output_request), .owner_ack_sync(output_ack_sync),\n    .writer_reset_idle(output_writer_idle), .reader_reset_idle(output_reader_idle)\n  );\n",
    "  // BEGIN INVERSE OUTPUT IDENTITY STAGE\n  // Stream only the nonfinal prefix privately. The retained controller's\n  // replay supplies the sole final word, and waits for its actual RAM commit.\n  wire output_stage_offer_valid = output_publication_busy ? output_replay_valid :\n    (guard_private_out[1] && !guard_last_out[1]);\n  wire [36:0] output_stage_offer_metadata = output_publication_busy ?\n    {output_replay_tag,output_descriptor_payload[4:0]} :\n    {inverse_tag,guard_return_metadata[1][4:0]};\n  assign output_bank_fault = output_bank_ram_fault || output_stage_fault;\n  assign output_stage_consume = (output_bank_ready === 1'b1) && (fast_fault === 1'b0) &&\n    ((output_stage_last === 1'b0) || (output_replay_accept === 1'b1));\n  starlink_pss_product_identity_split_capacity output_identity_stage (\n    .clk(fft_clk),.resetn(fast_running),\n    .abort_epoch(fast_fault || result_fault || output_bank_ram_fault ||\n      (output_bank_ready !== 1'b0 && output_bank_ready !== 1'b1)),\n    .input_valid(output_stage_offer_valid && !fast_fault),.input_ready(output_stage_ready),\n    .input_data(output_publication_busy ? output_replay_data : guard_return_data[1]),\n    .input_position(output_publication_busy ? 9'd511 : guard_return_position[1]),\n    .input_last(output_publication_busy ? 1'b1 : guard_last_out[1]),\n    .input_metadata({33'b0,output_stage_offer_metadata}),\n    .reference_metadata({33'b0,(output_writer_metadata_load ?\n      output_stage_metadata[36:0] : output_writer_metadata)}),\n    .output_valid(output_stage_valid),.output_ready(output_stage_consume),\n    .refill_capacity((output_bank_ready === 1'b1) && (fast_fault === 1'b0)),\n    .output_data(output_stage_data),.output_position(output_stage_position),\n    .output_last(output_stage_last),.output_identity_good(output_stage_identity_good),\n    .output_metadata(output_stage_metadata),.idle(output_stage_idle),.fault(output_stage_fault)\n  );\n  starlink_pss_output_mailbox_staged_identity #(.METADATA_WIDTH(37), .RESET_RELEASE_EXTERNAL(1),\n      .EXPLICIT_COMMIT(1)) output_bank (\n    .input_clk(fft_clk), .input_resetn(fast_running),\n    .input_valid(output_stage_valid && !fast_fault),\n    .input_commit_authorized(output_replay_accept), .input_ready(output_bank_ready),\n    .input_data(output_stage_data),.input_position(output_stage_position),.input_last(output_stage_last),\n    .input_metadata(output_stage_metadata[36:0]),.input_metadata_certified(output_stage_identity_good),\n    .writer_identity_metadata(output_writer_metadata),.writer_identity_load(output_writer_metadata_load),\n    .input_fault(output_bank_ram_fault),.input_framing_fault_now(output_bank_framing_fault_now),\n    .output_clk(clk), .output_resetn(slow_running),\n    .output_valid(slow_output_valid), .output_ready(output_ready && slow_metadata_valid && !fault),\n    .output_data(output_data), .output_position(output_position), .output_last(output_last),\n    .output_metadata(output_bank_metadata), .owner_request(output_request), .owner_ack_sync(output_ack_sync),\n    .writer_reset_idle(output_writer_idle), .reader_reset_idle(output_reader_idle)\n  );\n  // END INVERSE OUTPUT IDENTITY STAGE\n"
  ]
]
BANK_CHANGES = [
  [
    "module starlink_pss_output_reset_receipt #(",
    "module starlink_pss_output_mailbox_staged_identity #("
  ],
  [
    "  input wire [METADATA_WIDTH-1:0] input_metadata_live, input_metadata_replay,\n  input wire input_metadata_select,",
    "  input wire [METADATA_WIDTH-1:0] input_metadata,\n  input wire input_metadata_certified,\n  output wire [METADATA_WIDTH-1:0] writer_identity_metadata,\n  output wire writer_identity_load,"
  ],
  [
    "  initial begin\n",
    "  initial begin\n    if (EXPLICIT_COMMIT !== 1 || RESET_RELEASE_EXTERNAL !== 1)\n      $fatal(1, \"output identity requires explicit publication and common reset\");\n"
  ],
  [
    "  // BEGIN SPLIT METADATA COMPARISON\n  // Keep both source comparisons ahead of phase selection. No registered\n  // certificate or delayed fault: the selected current metadata is checked\n  // against the real first-word descriptor on this same edge.\n  wire [METADATA_WIDTH-1:0] input_metadata = input_metadata_select ?\n    input_metadata_replay : input_metadata_live;\n  wire metadata_matches;\n  generate if (EXPLICIT_COMMIT) begin : split_metadata\n    (* keep = \"true\" *) wire [1:0] branch_matches;\n    for (genvar branch = 0; branch < 2; branch = branch + 1) begin : branches\n      wire [METADATA_WIDTH-1:0] branch_metadata = branch == 0 ?\n        input_metadata_live : input_metadata_replay;\n      localparam integer LEAF_COUNT = (METADATA_WIDTH + 2) / 3;\n      localparam integer GROUP_COUNT = (LEAF_COUNT + 5) / 6;\n      (* keep = \"true\" *) wire [LEAF_COUNT-1:0] leaf_equal;\n      (* keep = \"true\" *) wire [GROUP_COUNT-1:0] group_equal;\n      for (genvar leaf = 0; leaf < LEAF_COUNT; leaf = leaf + 1) begin : leaves\n        localparam integer BITS = (METADATA_WIDTH - 3 * leaf < 3) ?\n            METADATA_WIDTH - 3 * leaf : 3;\n        assign leaf_equal[leaf] = branch_metadata[3*leaf +: BITS] ==\n            metadata_in_hold[3*leaf +: BITS];\n      end\n      for (genvar group_index = 0; group_index < GROUP_COUNT; group_index = group_index + 1) begin : groups\n        localparam integer BITS = (LEAF_COUNT - 6 * group_index < 6) ?\n            LEAF_COUNT - 6 * group_index : 6;\n        assign group_equal[group_index] = &leaf_equal[6*group_index +: BITS];\n      end\n      assign branch_matches[branch] = &group_equal;\n    end\n    // A four-state selector merges metadata bits in the original interface.\n    // Selecting two equality results is not generally equivalent in that case.\n    // Preserve original four-state behavior rather than claim that assumption.\n    assign metadata_matches = input_metadata_select === 1'b0 ? branch_matches[0] :\n      input_metadata_select === 1'b1 ? branch_matches[1] :\n      (input_metadata == metadata_in_hold);\n  end else begin : legacy_metadata\n    assign metadata_matches = input_metadata == metadata_in_hold;\n  end endgenerate\n  // END SPLIT METADATA COMPARISON",
    "  // Wide equality belongs to the held private word's registered certificate.\n  // Ordinal/LAST and actual publication/ACK/reset logic remain local and current.\n  wire metadata_matches = input_metadata_certified === 1'b1;"
  ],
  [
    "  reg reading;\n",
    "  assign writer_identity_metadata = metadata_in_hold;\n  assign writer_identity_load = metadata_load;\n\n  reg reading;\n"
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
