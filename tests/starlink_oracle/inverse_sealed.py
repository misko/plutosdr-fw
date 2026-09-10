"""Strict additive source derivation for the offline inverse-only composition."""

import hashlib

FAST_SHA = "d9c2382f9087ccd2088fa5a5d3fed5c6fe885359d6d4c367ed2ea81ce099d9f6"
TOP_SHA = "0cb54617eb6757e1d6c719d97b0fd5002ec7f6105c8c4b50c41eba67d4306235"
BENCH_SHA = "5b467f3890d2a16a225a2640642da24cbf8734b72e759adca2cb0d51fdd6a2ce"

FAST_RESET = """    wire common_resetn = input_resetn && output_resetn;
    (* ASYNC_REG = "TRUE" *) reg [1:0] reset_release;
    always @(posedge clk or negedge common_resetn)
      if (!common_resetn) reset_release <= 0;
      else reset_release <= {reset_release[0], 1'b1};
    wire running = common_resetn && reset_release[1];"""
FAST_READER = """        if (!reading && request_sync[1] != acknowledge_toggle && clean) begin
          reading <= 1;
          read_all_loaded <= 0;
          read_address <= 0;
          metadata_out_hold <= metadata_in_hold;
        end
        if (load_read) begin
          read_valid <= 1;
          read_output_position <= read_address;
          if (read_address == 511) read_all_loaded <= 1;
          else read_address <= read_address + 1'b1;
        end else if (output_accept) read_valid <= 0;
        if (output_accept && output_last) begin
          reading <= 0;
          acknowledge_toggle <= request_sync[1];
        end
"""
CDC_READER = """    // Actual slow-domain read/ACK state. No raw fast fault/publication flag
    // controls slow VALID; the outer island supplies its existing slow fault Q.
    always @(posedge output_clk or negedge output_resetn) begin
      if (!output_resetn) begin
        request_sync <= 0; acknowledge_toggle <= 0;
        reading <= 0; read_all_loaded <= 0; read_valid <= 0;
        read_address <= 0; read_output_position <= 0; metadata_out_hold <= 0;
      end else begin
        request_sync <= {request_sync[0], request_toggle};
        if (!reading && request_sync[1] != acknowledge_toggle && output_fault === 1'b0) begin
          reading <= 1; read_all_loaded <= 0; read_address <= 0;
          metadata_out_hold <= metadata_in_hold;
        end
        if (load_read) begin
          read_valid <= 1; read_output_position <= read_address;
          if (read_address == 511) read_all_loaded <= 1;
          else read_address <= read_address + 1'b1;
        end else if (output_accept) read_valid <= 0;
        if (output_accept && output_last) begin
          reading <= 0; acknowledge_toggle <= request_sync[1];
        end
      end
    end
"""

CDC_EDITS = [
    (
        "module starlink_pss_epoch_sealed_bank #(",
        "module starlink_pss_epoch_sealed_bank_cdc #(",
    ),
    (
        "  input wire clk, input_resetn, output_resetn,",
        """  // Each reset is a locally qualified COMMON epoch release, already including
  // both raw resets. Per-transform core reset is forbidden here.
  input wire input_clk, input_resetn, output_clk, output_resetn,
  input wire output_fault,""",
    ),
    (
        "  output wire sealed, published\n",
        "  output wire sealed, published, read_acknowledged, reader_epoch_idle\n",
    ),
    (
        "#(.METADATA_WIDTH(75), .EXPLICIT_COMMIT(1)) original",
        "#(.METADATA_WIDTH(75), .EXPLICIT_COMMIT(1), .RESET_RELEASE_EXTERNAL(1)) original",
    ),
    (".input_clk(clk)", ".input_clk(input_clk)"),
    (".output_clk(clk)", ".output_clk(output_clk)"),
    (
        "    assign published = 0;",
        "    assign published = 0;\n    assign read_acknowledged = 0;\n    assign reader_epoch_idle = 0;",
    ),
    (
        FAST_RESET,
        "    wire running = input_resetn;\n    wire out_running = output_resetn;",
    ),
    (
        "    reg [1:0] request_sync, acknowledge_sync;",
        '    (* ASYNC_REG = "TRUE" *) reg [1:0] request_sync, acknowledge_sync;',
    ),
    (
        "    reg [35:0] read_payload;",
        """    reg [35:0] read_payload;
    (* ASYNC_REG = "TRUE" *) reg [1:0] reader_idle_fast;
    reg reader_idle_slow;
    always @(posedge output_clk or negedge output_resetn)
      if (!output_resetn) reader_idle_slow <= 0;
      else reader_idle_slow <= !reading && !read_valid &&
        request_sync[1] == acknowledge_toggle;
    always @(posedge input_clk or negedge input_resetn)
      if (!input_resetn) reader_idle_fast <= 0;
      else reader_idle_fast <= {reader_idle_fast[0], reader_idle_slow};
    assign reader_epoch_idle = running && reader_idle_fast[1];
    assign read_acknowledged = running && published_q && reader_epoch_idle &&
      acknowledge_sync[1] == request_toggle;""",
    ),
    (
        "acknowledge_sync[1] == request_toggle && !reading && !read_valid && pipe_empty",
        "acknowledge_sync[1] == request_toggle && reader_epoch_idle && pipe_empty",
    ),
    (
        "live_clean && pipe_empty && !read_valid && !reading;",
        "live_clean && pipe_empty && reader_epoch_idle;",
    ),
    (
        "assign output_valid = running && armed && read_valid && clean && publication_current_clean;",
        "assign output_valid = out_running && read_valid && output_fault === 1'b0;",
    ),
    (
        "wire load_read = running && reading && !read_all_loaded &&\n      (!read_valid || output_accept) && clean;",
        "wire load_read = out_running && reading && !read_all_loaded &&\n      (!read_valid || output_accept) && output_fault === 1'b0;",
    ),
    (
        "always @(posedge clk or negedge common_resetn) begin\n      if (!common_resetn) begin",
        "always @(posedge input_clk or negedge input_resetn) begin\n      if (!input_resetn) begin",
    ),
    (
        "        metadata_in_hold <= 0; metadata_out_hold <= 0;",
        "        metadata_in_hold <= 0;",
    ),
    (
        "        request_toggle <= 0; acknowledge_toggle <= 0;",
        "        request_toggle <= 0;",
    ),
    (
        "        request_sync <= 0; acknowledge_sync <= 0;",
        "        acknowledge_sync <= 0;",
    ),
    (
        "        reading <= 0; read_all_loaded <= 0; read_valid <= 0;\n        read_address <= 0; read_output_position <= 0;\n",
        "        // Reader reset belongs to output_clk below.\n",
    ),
    (
        "        request_sync <= {request_sync[0], request_toggle};\n",
        "        // Request synchronizer lives in output_clk below.\n",
    ),
    (FAST_READER, "        // CDC reader state lives below fast control.\n"),
    (
        "    // No RAM clear/reset and no extra payload bank.",
        CDC_READER + "    // No RAM clear/reset and no extra payload bank.",
    ),
    (
        "    always @(posedge clk) begin\n      if (private_take) payload_memory[write_position] <= input_data;\n      if (load_read) read_payload <= payload_memory[read_address];\n    end",
        """    always @(posedge input_clk)
      if (private_take) payload_memory[write_position] <= input_data;
    always @(posedge output_clk)
      if (load_read) read_payload <= payload_memory[read_address];""",
    ),
    (
        "// OFFLINE EXPERIMENT ONLY. One actual 512x36 RAM, fast-clock-only prototype.",
        "// OFFLINE EXPERIMENT ONLY. Additive true dual-clock512x36 sealed-bank variant.",
    ),
]


def rewrite(source, edits, inverse=False):
    for old, new in reversed(edits) if inverse else edits:
        if inverse:
            old, new = new, old
        if not old or source.count(old) != 1:
            raise ValueError("source edit is absent, duplicated, or empty")
        source = source.replace(old, new)
    return source


def derive_cdc(source):
    if hashlib.sha256(source.encode()).hexdigest() != FAST_SHA:
        raise ValueError("wrong frozen fast-only source")
    return rewrite(source, CDC_EDITS)


def restore_cdc(source):
    restored = rewrite(source, CDC_EDITS, inverse=True)
    if hashlib.sha256(restored.encode()).hexdigest() != FAST_SHA:
        raise ValueError("CDC source does not restore literal frozen prototype")
    return restored


OLD_OUTPUT_BANK = """  starlink_pss_block_mailbox #(.METADATA_WIDTH(75), .RESET_RELEASE_EXTERNAL(1),
      .EXPLICIT_COMMIT(1)) output_bank (
    .input_clk(fft_clk), .input_resetn(fast_running),
    .input_valid(return_private_valid && next_inverse),
    .input_commit_authorized(return_commit_valid && next_inverse), .input_ready(output_bank_ready),
    .input_data(return_data), .input_position(return_position), .input_last(return_last),
    .input_metadata(return_metadata), .input_fault(output_bank_fault),
    .input_framing_fault_now(output_bank_framing_fault_now),
    .output_clk(clk), .output_resetn(slow_running),
    .output_valid(slow_output_valid), .output_ready(output_ready && !fault),
    .output_data(output_data), .output_position(output_position), .output_last(output_last),
    .output_metadata(output_metadata)
  );"""
NEW_OUTPUT_BANK = (
    """  generate if (!SEALED_INVERSE_OUTPUT) begin : legacy_inverse_output
    assign inverse_epoch_active = 1'b1;
    assign output_destination_ready = output_bank_ready;
    assign inverse_destination_reserved = output_bank_ready;
"""
    + OLD_OUTPUT_BANK
    + """
  end else begin : sealed_inverse_output
    starlink_pss_inverse_sealed_issuer output_bank (
      .input_clk(fft_clk), .input_resetn(fast_running),
      .output_clk(clk), .output_resetn(slow_running),
      .core_reset_held(!core_aresetn), .inverse_phase(next_inverse), .guard_busy(result_busy),
      .inverse_job_accept(job_accept && next_inverse),
      .guard_private_valid(return_private_valid), .guard_commit_valid(return_commit_valid),
      .guard_data(return_data), .guard_position(return_position), .guard_last(return_last),
      .guard_metadata(return_metadata), .core_output_event(core_output_valid),
      .external_fault_now(external_fault_now || result_fault || preparation_fault_now),
      .output_fault(fault), .guard_destination_ready(output_destination_ready),
      .reusable(output_bank_ready), .reservation(inverse_destination_reserved), .epoch_active(inverse_epoch_active),
      .input_fault(output_bank_fault), .input_framing_fault_now(output_bank_framing_fault_now),
      .output_valid(slow_output_valid), .output_ready(output_ready && !fault),
      .output_data(output_data), .output_position(output_position), .output_last(output_last),
      .output_metadata(output_metadata), .private_take(), .certificate_take(),
      .publication(), .reader_ack(), .lease_release(), .fault_reasons()
    );
  end endgenerate"""
)
TOP_EDITS = [
    (
        "module starlink_pss_fft_bank_owned_local_admission_probe #(",
        "module starlink_pss_fft_bank_owned_inverse_sealed_probe #(",
    ),
    (
        "  parameter integer LOCAL_FIRST_ADMISSION = 0\n",
        "  parameter integer LOCAL_FIRST_ADMISSION = 0,\n  parameter integer SEALED_INVERSE_OUTPUT = 0\n",
    ),
    (
        '  (* ASYNC_REG = "TRUE" *) reg [1:0] slow_reset_fast, fast_reset_fast;',
        """  initial begin
    if (SEALED_INVERSE_OUTPUT !== 0 && SEALED_INVERSE_OUTPUT !== 1)
      $fatal(1, "SEALED_INVERSE_OUTPUT must be zero or one");
  end
  (* ASYNC_REG = "TRUE" *) reg [1:0] slow_reset_fast, fast_reset_fast;""",
    ),
    (
        "  wire slow_running = slow_reset_slow[1] && fast_reset_slow[1];",
        """  wire slow_running = slow_reset_slow[1] && fast_reset_slow[1];
  wire inverse_epoch_active, output_destination_ready, inverse_destination_reserved;
  // Reset assertion reaches both domains through the original qualifiers.
  // Keep fast SOURCE prefetch reset until an actual slow purge/idle ACK has
  // returned. Otherwise a paused slow request=1 can re-prefetch old RAM.
  wire source_reader_running = fast_running &&
    (!SEALED_INVERSE_OUTPUT || inverse_epoch_active);""",
    ),
    (
        "    .output_clk(fft_clk), .output_resetn(fast_running),\n    .output_valid(source_valid)",
        "    .output_clk(fft_clk), .output_resetn(source_reader_running),\n    .output_valid(source_valid)",
    ),
    (
        "    if (!fast_running) source_fault_fast <= 0;",
        "    if (!source_reader_running) source_fault_fast <= 0;",
    ),
    (
        "  wire result_destination_ready = next_inverse ? output_bank_ready :",
        "  wire result_destination_ready = next_inverse ? output_destination_ready :",
    ),
    (
        "  wire destination_reserved = next_inverse ? output_bank_ready : product_bank_ready;",
        """  // Park BEFORE preflight, not after its63-cycle timeout has started. This
  // also holds core release until rearm even with a full fresh forward source.
  wire destination_reserved = (!SEALED_INVERSE_OUTPUT || inverse_epoch_active) &&
    (next_inverse ? inverse_destination_reserved : product_bank_ready);""",
    ),
    (OLD_OUTPUT_BANK, NEW_OUTPUT_BANK),
]


def derive_top(source):
    if hashlib.sha256(source.encode()).hexdigest() != TOP_SHA:
        raise ValueError("wrong frozen L1 top")
    return rewrite(source, TOP_EDITS)


def restore_top(source):
    restored = rewrite(source, TOP_EDITS, inverse=True)
    if hashlib.sha256(restored.encode()).hexdigest() != TOP_SHA:
        raise ValueError("new top does not restore literal L1 top")
    return restored


BENCH_EDITS = [
    (
        "module tb_starlink_bank_arithmetic_ownership;",
        "module tb_starlink_inverse_sealed_ownership;",
    ),
    (
        "  parameter integer R=1, B=1, S=1, CASE=0;",
        "  parameter integer R=1, B=1, S=1, CASE=0, E=1;",
    ),
    (
        "  starlink_pss_fft_bank_owned_arithmetic_probe #(.REGISTERED_SCHEDULING(S),\n    .BOUNDARY_ROUND_SAT(B), .REGISTER_OPERANDS(R)) dut (.*);",
        "  starlink_pss_fft_bank_owned_inverse_sealed_probe #(.REGISTERED_SCHEDULING(S),\n    .BOUNDARY_ROUND_SAT(B), .REGISTER_OPERANDS(R), .LOCAL_FIRST_ADMISSION(1),\n    .SEALED_INVERSE_OUTPUT(E)) dut (.*);",
    ),
]


def derive_bench(source):
    if hashlib.sha256(source.encode()).hexdigest() != BENCH_SHA:
        raise ValueError("wrong original offline arithmetic bench")
    return rewrite(source, BENCH_EDITS)


def restore_bench(source):
    restored = rewrite(source, BENCH_EDITS, inverse=True)
    if hashlib.sha256(restored.encode()).hexdigest() != BENCH_SHA:
        raise ValueError("derived bench does not restore all original checks")
    return restored
