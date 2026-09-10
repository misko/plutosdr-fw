"""Strict inverse of the reviewed Stage A delta for historical body checks.

No regex deletion, whitespace normalization, fuzzy context, or unpinned input:
both complete source bodies and every changed hunk are independently checked.
Historical cycle-trace tests still run the live controller, not this projection.
"""

import hashlib
import json
from pathlib import Path


def inverse_stage_a(path: str, source: str) -> str:
    manifest = json.loads(Path(__file__).with_name("psma17_stage_a_delta.json").read_text())
    entry = manifest["files"][path]
    digest = hashlib.sha256(source.encode()).hexdigest()
    if digest not in (entry["before_sha256"], entry["after_sha256"]):
        from .psma18_projection import inverse_stage_a60
        source = inverse_stage_a60(path, source)
        digest = hashlib.sha256(source.encode()).hexdigest()
    # Historical isolated HDL trees remain valid inputs to the old tests.
    if digest == entry["before_sha256"]:
        return source
    assert digest == entry["after_sha256"], "unreviewed complete Stage A source body"
    lines = source.split("\n")
    restored = []
    cursor = 0
    for hunk in entry["hunks"]:
        start = hunk["new_index"]
        assert start >= cursor, "overlapping or unordered Stage A hunks"
        restored.extend(lines[cursor:start])
        assert len(restored) == hunk["old_index"], "inverse source position mismatch"
        assert lines[start:start + len(hunk["after"])] == hunk["after"], "inverse hunk mismatch"
        restored.extend(hunk["before"])
        cursor = start + len(hunk["after"])
    restored.extend(lines[cursor:])
    result = "\n".join(restored)
    assert hashlib.sha256(result.encode()).hexdigest() == entry["before_sha256"], \
        "inverse did not restore the entire historical body"
    return result
