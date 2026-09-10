"""Exact inverses of the data-only enables and both full ROM equalities."""
from tests.starlink_oracle.input_identity_contract import tokens


def once(source, new, old=""):
    assert source.count(new) == 1, new
    return source.replace(new, old, 1)


def restore_payload_wrapper(source):
    source = once(source,
        ".DATA_WIDTH(18),\n    .PRIVATE_PAYLOAD_BUBBLES(REGISTERED_SCHEDULING),\n"
        "    .BALANCED_BLOCK_IDENTITY_EQ(REGISTERED_SCHEDULING)) joiner",
        ".DATA_WIDTH(18)) joiner")
    return once(source, ".DATA_WIDTH(18),\n    .PRIVATE_PAYLOAD_BUBBLES(REGISTERED_SCHEDULING)) product",
                ".DATA_WIDTH(18)) product")


def restore_payload_module(source, kind):
    source = tokens(source)
    if kind in {"forward_kernel_join", "spectrum_product"}:
        source = once(source, ",parameterintegerPRIVATE_PAYLOAD_BUBBLES=0")
        source = once(source, tokens('''initial begin
          if (PRIVATE_PAYLOAD_BUBBLES != 0 && PRIVATE_PAYLOAD_BUBBLES != 1)
            $fatal(1, "PRIVATE_PAYLOAD_BUBBLES must be zero or one");
        end'''))
    if kind == "forward_kernel_join":
        source = once(source, ",parameterintegerBALANCED_BLOCK_IDENTITY_EQ=0")
        source = once(source, ",.BALANCED_BLOCK_IDENTITY_EQ(BALANCED_BLOCK_IDENTITY_EQ)")
        source = once(source, "PRIVATE_PAYLOAD_BUBBLES?input_ready:input_accept", "input_accept")
    elif kind == "spectrum_product":
        source = once(source, tokens('''if (PRIVATE_PAYLOAD_BUBBLES || input_valid) begin
          product_ii <= input_i * kernel_i;
          product_qq <= input_q * kernel_q;
          product_iq <= input_i * kernel_q;
          product_qi <= input_q * kernel_i;
        end
        if (input_valid) begin'''), tokens('''if (input_valid) begin
          product_ii <= input_i * kernel_i;
          product_qq <= input_q * kernel_q;
          product_iq <= input_i * kernel_q;
          product_qi <= input_q * kernel_i;'''))
    elif kind == "kernel_rom":
        source = once(source, ",parameterintegerBALANCED_BLOCK_IDENTITY_EQ=0")
        source = once(source, tokens('''if (BALANCED_BLOCK_IDENTITY_EQ != 0 && BALANCED_BLOCK_IDENTITY_EQ != 1)
          $fatal(1, "BALANCED_BLOCK_IDENTITY_EQ must be zero or one");'''))
        source = once(source, tokens('''wire [1:0] block_identity_equal;
          generate if (BALANCED_BLOCK_IDENTITY_EQ) begin : balanced_block_identity
            for (genvar comparison = 0; comparison < 2; comparison = comparison + 1) begin : comparisons
              wire [63:0] rhs = comparison == 0 ? block_start_index : expected_next_block_start;
              (* keep = "true" *) wire [21:0] leaf_equal;
              (* keep = "true" *) wire [3:0] group_equal;
              for (genvar leaf = 0; leaf < 22; leaf = leaf + 1) begin : leaves
                localparam integer BITS = leaf == 21 ? 1 : 3;
                assign leaf_equal[leaf] = input_block_start_index[3*leaf +: BITS] == rhs[3*leaf +: BITS];
              end
              for (genvar group_index = 0; group_index < 4; group_index = group_index + 1) begin : groups
                localparam integer BITS = group_index == 3 ? 4 : 6;
                assign group_equal[group_index] = &leaf_equal[6*group_index +: BITS];
              end
              assign block_identity_equal[comparison] = &group_equal;
            end
          end else begin : legacy_block_identity
            assign block_identity_equal[0] = input_block_start_index == block_start_index;
            assign block_identity_equal[1] = input_block_start_index == expected_next_block_start;
          end endgenerate'''))
        source = once(source, "!block_identity_equal[0]", "input_block_start_index!=block_start_index")
        source = once(source, "!block_identity_equal[1]", "input_block_start_index!=expected_next_block_start")
    else:
        raise AssertionError(kind)
    return source
