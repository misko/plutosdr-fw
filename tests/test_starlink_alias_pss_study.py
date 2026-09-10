"""Prior-only branching, unknown outcomes, exact support and oracle fencing."""

import copy

import numpy as np
import pytest

from tests.test_starlink_capture25_causal_study import prior
from tools import starlink_alias_pss_study as study


def test_prior_branches_keep_minority_alias_and_no_later_input():
    receipt = prior(frequencies=(286_000., 285_000., 512_000.))
    original = copy.deepcopy(receipt)
    result = study.prior_branches(receipt, "positive")
    assert [row["cfo_hz"] for row in result["branches"]] == [0., 285_500., 512_000.]
    assert result["branches"][2]["kind"] == "minority_prior_alias"
    assert not result["alias_identity_resolved"]
    assert receipt == original


def test_negative_prior_retains_abstention_and_only_zero_baseline():
    result = study.prior_branches(prior("negative", margins=(.005, .006, .007)), "negative")
    assert result["decision"]["status"] == "abstained"
    assert len(result["branches"]) == 1
    assert result["branches"][0]["cfo_hz"] == 0


def test_new_passing_prior_candidates_require_new_explicit_policy():
    receipt = prior()
    receipt["probes"][0]["candidates"].append(
        {"method": "glrt64", "margin": .05, "tracking_cfo_hz": 740_000})
    with pytest.raises(ValueError, match="multiple passing"):
        study.prior_branches(receipt, "positive")


def row(name, *, passes=False, control=False, baseline=False):
    return {"branch": {"name": name, "kind": "uncorrected_baseline" if baseline else "minority_prior_alias"},
            "one_map_exploratory_candidate": passes,
            "scrambled_control": {"combined_candidate": {"passes_existing_epoch_gates": control}}}


@pytest.mark.parametrize(("branches", "expected"), [
    ([row("baseline", baseline=True)], "no_prior_aliases"),
    ([row("a"), row("b")], "no_alias_candidate"),
    ([row("a", passes=True), row("b")], "one_map_consistent_with_one_prior_alias"),
    ([row("a", passes=True), row("b", passes=True)], "competing_alias_candidates"),
    ([row("a", passes=True), row("b", control=True)], "control_failed"),
])
def test_one_map_never_resolves_alias_identity_or_production_lock(branches, expected):
    result = study.summarize_aliases(branches)
    assert result["exploratory_status"] == expected
    assert result["production_handoff_status"] == "insufficient_integration"
    assert not result["alias_identity_resolved"]
    assert not result["production_lock_or_false_alarm_behavior_qualified"]


def test_actual_source_envelope_includes_both_resampler_halos():
    result = study.source_bounds(15_000_000 - study.HALO, study.SCORES + 2 * study.HALO)
    assert result["original25_full_support_bounds"][0] == 24_998_920
    assert result["original25_support_seconds"] > study.SCORES / 15e6
    assert result["original25_support_seconds"] < .120
    with pytest.raises(ValueError):
        study.source_bounds(0, 0)


def test_probe_intervals_cover_whole_pss_centers_and_fit_bounded_read():
    assert study.PROBE_OFFSETS[0] == 0
    assert study.PROBE_OFFSETS[-1] + study.narrow.PROBE_SAMPLES == study.SCORES
    assert all(a + study.narrow.PROBE_SAMPLES >= b
               for a, b in zip(study.PROBE_OFFSETS, study.PROBE_OFFSETS[1:]))
    assert study.PROBE_OFFSETS[-1] + study.narrow.PROBE_SAMPLES + 2 * study.HALO == study.SCORES + 2 * study.HALO


def test_bounded_input_hash_rejects_changed_noise_plan():
    case = {"kind": "known_noise"}
    samples = study.read_input(case)
    assert samples.dtype == np.dtype("<i2")
    assert samples.shape == (study.SCORES + 2 * study.HALO, 2)
    case["input_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source bytes"):
        study.read_input(case)
