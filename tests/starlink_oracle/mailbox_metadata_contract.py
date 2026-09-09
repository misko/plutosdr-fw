"""Exact allowed comparator delta for older whole-source mailbox contracts."""
import hashlib
import re


def restore_legacy_metadata_comparison(source):
    """Remove only the pinned stateless tree; reject any unreviewed tree edit."""
    if "  wire metadata_matches;" not in source:
        return source
    block = re.search(r"  wire metadata_matches;.*?(?=  wire input_framing_valid)",
                      source, re.DOTALL)
    assert block is not None
    assert hashlib.sha256(block.group().encode()).hexdigest() == (
        "e0e2150481a9988c6b18f72826d05dd6b6f19d04d6bf06ecc8f40ef1d40947cc")
    replacement = "(write_position == 0 || metadata_matches);"
    assert source.count(replacement) == 1
    return source.replace(block.group(), "", 1).replace(replacement,
        "(write_position == 0 || input_metadata == metadata_in_hold);", 1)
