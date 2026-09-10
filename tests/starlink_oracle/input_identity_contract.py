"""Strict inverse of the opt-in balanced equality, not a predicate exemption."""
import re


def tokens(source):
    return re.sub(r"\s+", "", re.sub(r"//[^\n]*", "", source))


def restore_legacy_identity_guard(source):
    candidate = tokens(source)
    fragments = [
        ",parameterintegerBALANCED_IDENTITY_EQ=0",
        ('if(BALANCED_IDENTITY_EQ!=0&&BALANCED_IDENTITY_EQ!=1)'
         '$fatal(1,"BALANCED_IDENTITY_EQmustbezeroorone");'),
        tokens('''wire identity_matches;
          generate if (BALANCED_IDENTITY_EQ) begin : balanced_identity
            (* keep = "true" *) wire [23:0] leaf_equal;
            (* keep = "true" *) wire [3:0] group_equal;
            for (genvar leaf = 0; leaf < 24; leaf = leaf + 1) begin : leaves
              localparam integer BITS = leaf == 23 ? 1 : 3;
              assign leaf_equal[leaf] = input_metadata[3*leaf +: BITS] == descriptor[3*leaf +: BITS];
            end
            for (genvar group_index = 0; group_index < 4; group_index = group_index + 1) begin : groups
              assign group_equal[group_index] = &leaf_equal[6*group_index +: 6];
            end
            assign identity_matches = &group_equal;
          end else begin : legacy_identity
            assign identity_matches = input_metadata == descriptor;
          end endgenerate'''),
    ]
    for fragment in fragments:
        assert candidate.count(fragment) == 1
        candidate = candidate.replace(fragment, "", 1)
    anchor = "(!CHECK_INPUT_BLOCK_IDENTITY||identity_matches)"
    assert candidate.count(anchor) == 1
    return candidate.replace(anchor,
        "(!CHECK_INPUT_BLOCK_IDENTITY||input_metadata==descriptor)", 1)
