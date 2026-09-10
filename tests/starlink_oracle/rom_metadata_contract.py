"""Literal inverse for the separate metadata-only read-ahead experiment."""

BASE = "b83a45267a8cb8039eb7c7b4eaed5e5d6c3bb489"
METADATA_BODY = """  // The checker-visible block tuple remains exact on every cycle. Only its
  // private capture excludes current acceptance/framing; the selector follows
  // the original nested first-beat update, including procedural X/Z semantics.
  generate if (PRIVATE_BLOCK_METADATA_READ_AHEAD) begin : private_block_metadata_read_ahead
    reg [68:0] speculative_metadata;
    reg [68:0] retained_metadata;
    reg metadata_selected;
    always @(posedge clk)
      if (input_ready && at_block_start)
        speculative_metadata <= {input_block_start_index, input_block_exponent};
    always @(posedge clk) begin
      if (!resetn || flush) begin
        retained_metadata <= 0;
        metadata_selected <= 0;
      end else begin
        if (metadata_selected)
          retained_metadata <= speculative_metadata;
        metadata_selected <= 0;
        if (input_accept) begin
          if (protocol_error_now)
            metadata_selected <= 0;
          else if (at_block_start)
            metadata_selected <= 1;
        end
      end
    end
    assign {block_start_index, block_exponent} =
      metadata_selected ? speculative_metadata : retained_metadata;
  end else begin : legacy_block_metadata
    reg [68:0] legacy_metadata;
    always @(posedge clk) begin
      if (!resetn || flush)
        legacy_metadata <= 0;
      else if (input_accept) begin
        if (protocol_error_now) begin
          // The original fault branch does not update block metadata.
        end else begin
          if (at_block_start)
            legacy_metadata <= {input_block_start_index, input_block_exponent};
        end
      end
    end
    assign {block_start_index, block_exponent} = legacy_metadata;
  end endgenerate

"""
WORD_COMMENT = "  // Read-ahead is private. The mux and retained word preserve every visible\n"
FINAL_TEST = "          if (expected_bin_index == 9'd511) begin\n"
EDITS = (
    ("  parameter integer PRIVATE_ROM_READ_AHEAD = 0\n",
     ("  parameter integer PRIVATE_ROM_READ_AHEAD = 0,\n"
      "  parameter integer PRIVATE_BLOCK_METADATA_READ_AHEAD = 0\n")),
    ("  reg [4:0] block_exponent;\n  reg [63:0] block_start_index;\n",
     "  wire [4:0] block_exponent;\n  wire [63:0] block_start_index;\n"),
    ("  initial begin\n", ("  initial begin\n"
     "    if (PRIVATE_BLOCK_METADATA_READ_AHEAD !== 0 && PRIVATE_BLOCK_METADATA_READ_AHEAD !== 1)\n"
     '      $fatal(1, "PRIVATE_BLOCK_METADATA_READ_AHEAD must be zero or one");\n')),
    (WORD_COMMENT, METADATA_BODY + WORD_COMMENT),
    (("      expected_bin_index <= 0;\n      block_exponent <= 0;\n"
      "      block_start_index <= 0;\n      expected_next_block_start <= 0;\n"),
     "      expected_bin_index <= 0;\n      expected_next_block_start <= 0;\n"),
    ("          if (at_block_start) begin\n"
     "            block_exponent <= input_block_exponent;\n"
     "            block_start_index <= input_block_start_index;\n"
     "          end\n\n" + FINAL_TEST, FINAL_TEST),
)


def restore_metadata(source):
    """Reject any altered new body; restore the entire old module exactly."""
    for before, after in reversed(EDITS):
        assert source.count(after) == 1, after
        source = source.replace(after, before, 1)
    return source
