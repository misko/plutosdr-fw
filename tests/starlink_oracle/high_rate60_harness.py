"""Additive healthy60 paired preparation; no numeric regeneration or service run."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .high_rate60_harness_recipe import recipe
from .native60_budget import check_cohort, encoded, require, sha
from .native60_budget_recipe import recipe as native_recipe
from .native60_readback_contract import limits as readback_limits

RECIPE_SHA = "1b24f01680b09313dcfd827cce45a8771d86892adef6773f0457c7b5fefba385"
PROFILE = "60-upper-bank175-native264-pil1-447x2-healthy-v1"


def check_recipe(value=None):
    r = recipe() if value is None else value
    require(encoded(r) == encoded(recipe()), "unadmitted paired60 recipe/types/limits")
    require(sha(Path(__file__).with_name("high_rate60_harness_recipe.py").read_bytes()) == RECIPE_SHA,
            "pre-evaluation paired60 recipe source changed")
    n = native_recipe()
    for new, old in [("native_command_trigger", "command_trigger"), ("native_handshake_closed", "command_handshake_closed"),
                     ("native_lead_closed", "command_lead_closed"), ("native_command_limit_cycles", "command_limit_control_cycles"),
                     ("native_capture", "native_capture_count"), ("native_taps", "native_taps"),
                     ("native_raw", "native_raw_count"), ("native_qualified", "native_qualified_count"),
                     ("native_publication_full_drain_limit", "publication_and_full_drain_limit_cycles"),
                     ("native_public_release_limit", "post_capture_limit_cycles")]:
        require(r[new] == n[old], f"original native service limit changed: {old}")
    require(readback_limits() == {"capture_lag": 2, "return_cycles": 48, "return_lag": 31}, "native readback limit")
    require(r["original_raw_preroll"] == 4*(768-1)+43 == 3111 and
            r["original_raw_count"]-r["original_raw_preroll"] == r["continuous_original_raw_count"] == 13312,
            "preroll/continuous support arithmetic")
    require(r["enabled_original_raw_closed"][0] == 4*(3609-1)+43 == 14475,
            "pilot support-only raw lower bound")
    return r


def rows(payload, count, width):
    words = payload.decode("ascii").splitlines()
    require(len(words) == count and all(re.fullmatch(rf"[0-9a-f]{{{width}}}", word) for word in words),
            "wrong paired60 fixture count/packing")
    return [int(word, 16) for word in words]


def mem(values, width):
    require(all(type(v) is int and 0 <= v < 1 << (4*width) for v in values), "serializer range/type")
    return "".join(f"{v:0{width}x}\n" for v in values).encode("ascii")


def fixture_payloads(cohort):
    r = check_recipe()
    original = check_cohort(cohort)
    require(sha((cohort / "cohort.json").read_bytes()) == r["cohort_sha256"], "wrong paired60 cohort identity")
    payloads = {name: (cohort / name).read_bytes() for name in original["files"]}
    require(all(not (cohort / name).is_symlink() for name in payloads), "numerical symlink")
    source = rows(payloads["source_ci16.mem"], 16423, 8)
    indexes = rows(payloads["source_index_u64.mem"], 16423, 16)
    require(indexes == list(range(*r["source_half_open"])), "raw support/phase changed")
    payloads["paired_source_ci16.mem"] = mem([*r["disabled_prime_ci16_q_hi_i_lo"], *source], 8)
    payloads["paired_source_index_u64.mem"] = mem(list(range(r["disabled_prime_half_open"][0], r["source_half_open"][1])), 16)
    info = {"profile": PROFILE, "recipe": r, "original69": {name: value["sha256"] for name, value in original["files"].items()},
            "files": {name: {"sha256": sha(data), "bytes": len(data)} for name, data in sorted(payloads.items())},
            "added_files": ["paired_source_ci16.mem", "paired_source_index_u64.mem"], "tail_added": False}
    return payloads, info


def prepare_vectors(cohort, output):
    require(not any(parent.is_symlink() for parent in [output, *output.parents]),
            "no symlink destination or parent")
    require(not output.exists() and not output.is_symlink(), "refusing to overwrite paired60 vectors")
    payloads, info = fixture_payloads(cohort)
    output.mkdir(parents=True)
    for name, data in payloads.items():
        (output / name).write_bytes(data)
    (output / "harness.json").write_bytes(encoded(info))
    verify_vectors(cohort, output)
    return info


def verify_vectors(cohort, output):
    require(not any(parent.is_symlink() for parent in [output, *output.parents]),
            "no symlink destination or parent")
    payloads, info = fixture_payloads(cohort)
    require({p.name for p in output.iterdir()} == {*payloads, "harness.json"}, "missing/extra paired60 fixture")
    require((output / "harness.json").read_bytes() == encoded(info), "paired60 recipe/source receipt mismatch")
    for name, expected in payloads.items():
        require(not (output / name).is_symlink() and (output / name).read_bytes() == expected,
                f"paired60 fixture changed: {name}")
    return info


def digest_rows(payloads):
    """Compact artifact identity, not a replacement numerical oracle."""
    return hashlib.sha256(encoded({name: sha(data) for name, data in sorted(payloads.items())})).hexdigest()
