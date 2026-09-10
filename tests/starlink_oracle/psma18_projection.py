"""Exact full-body inverse of the additive, default-off PSMA1.8 delta."""

import hashlib
import json
from pathlib import Path


def inverse_stage_a60(path: str, source: str) -> str:
    entry = json.loads(Path(__file__).with_name("psma18_stage_a_delta.json").read_text())["files"][path]
    digest = hashlib.sha256(source.encode()).hexdigest()
    if digest == entry["before_sha256"]:
        return source
    assert digest == entry["after_sha256"], "unreviewed complete Stage A60 source body"
    lines = source.split("\n")
    restored, cursor = [], 0
    for hunk in entry["hunks"]:
        start = hunk["new_index"]
        assert start >= cursor, "overlapping or unordered Stage A60 hunks"
        restored.extend(lines[cursor:start])
        assert len(restored) == hunk["old_index"], "Stage A60 inverse position mismatch"
        assert lines[start:start + len(hunk["after"])] == hunk["after"], "Stage A60 inverse hunk mismatch"
        restored.extend(hunk["before"])
        cursor = start + len(hunk["after"])
    restored.extend(lines[cursor:])
    result = "\n".join(restored)
    assert hashlib.sha256(result.encode()).hexdigest() == entry["before_sha256"], \
        "Stage A60 inverse did not restore the complete Stage A30 body"
    return result
