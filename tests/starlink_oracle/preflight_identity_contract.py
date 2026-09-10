"""Exact inverse of the held preflight tuple/two-comparator experiment."""
from tests.starlink_oracle.payload_bubble_contract import restore_payload_wrapper

PREFLIGHT_ADDITION = '''  // VERIFY/ARM own the captured phase. Discovery remains state-selected, but
  // this current preflight tuple need not put scheduler state before equality.
  wire preflight_phase = REGISTERED_SCHEDULING ? held_phase : next_inverse;
  wire preflight_valid = preflight_phase ? product_bank_valid : source_valid;
  wire [35:0] preflight_data = preflight_phase ? product_bank_data : source_data;
  wire [8:0] preflight_position = preflight_phase ? product_bank_position : source_position;
  wire preflight_last = preflight_phase ? product_bank_last : source_last;
  wire [69:0] preflight_metadata = preflight_phase ? product_bank_metadata : source_metadata;
  wire preflight_lease = preflight_phase ? product_consume_generation : source_consume_generation;
  wire [1:0] preflight_identity_equal;
  generate if (REGISTERED_SCHEDULING) begin : balanced_preflight
    for (genvar comparison = 0; comparison < 2; comparison = comparison + 1) begin : comparisons
      wire [69:0] lhs = comparison == 0 ? preflight_metadata : engine_metadata;
      wire [69:0] rhs = comparison == 0 ? engine_metadata : expected_product_metadata;
      (* keep = "true" *) wire [23:0] leaf_equal;
      (* keep = "true" *) wire [3:0] group_equal;
      for (genvar leaf = 0; leaf < 24; leaf = leaf + 1) begin : leaves
        localparam integer BITS = leaf == 23 ? 1 : 3;
        assign leaf_equal[leaf] = lhs[3*leaf +: BITS] == rhs[3*leaf +: BITS];
      end
      for (genvar group_index = 0; group_index < 4; group_index = group_index + 1) begin : groups
        assign group_equal[group_index] = &leaf_equal[6*group_index +: 6];
      end
      assign preflight_identity_equal[comparison] = &group_equal;
    end
  end else begin : legacy_preflight
    assign preflight_identity_equal[0] = preflight_metadata == engine_metadata;
    assign preflight_identity_equal[1] = engine_metadata == expected_product_metadata;
  end endgenerate
'''


def restore_held_preflight_wrapper(source):
    # Compose only the separately tested, exact later data-only opt-in delta.
    if "PRIVATE_PAYLOAD_BUBBLES" in source:
        source = restore_payload_wrapper(source)
    replacements = [
        (PREFLIGHT_ADDITION, ""),
        ("(held_phase ? preflight_identity_equal[1] : engine_metadata[4:0] == 0)",
         "(held_phase ? engine_metadata == expected_product_metadata : engine_metadata[4:0] == 0)"),
        (("wire preparation_valid = preflight_valid && preflight_position == 0 && !preflight_last &&\n"
          "    preflight_lease == held_lease && preflight_identity_equal[0] &&"),
         ("wire preparation_valid = selected_valid && selected_position == 0 && !selected_last &&\n"
          "    selected_lease == held_lease && selected_metadata == engine_metadata &&")),
        (("(!preflight_identity_equal[0] || !descriptor_header_valid),\n"
         "     (preflight_lease != held_lease), (preflight_position != 0 || preflight_last),\n"
         "     !preflight_valid} : 6'b0;"),
         ("(selected_metadata != engine_metadata || !descriptor_header_valid),\n"
         "     (selected_lease != held_lease), (selected_position != 0 || selected_last),\n"
         "     !selected_valid} : 6'b0;")),
    ]
    for new, old in replacements:
        assert source.count(new) == 1
        source = source.replace(new, old, 1)
    return source
