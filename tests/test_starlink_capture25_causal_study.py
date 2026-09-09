"""Bounded policy and mocked lifecycle tests; no capture IQ or radio access."""

import copy
from types import SimpleNamespace

import pytest

from tools import starlink_capture25_causal_study as study


def prior(episode="positive", frequencies=(286_000., 285_000., 512_000.), margins=(.4, .4, .4)):
    start, stop = study.PRIOR_INTERVALS[episode]
    origin = start * 3 // 5
    receipt = {"schema": "starlink-capture25-conditioned-pilot-crosscheck-v1", "status": "complete",
               "error": None, "pss_seeds_used": False, "calibration_attached": False,
               "pilot_saturation_events": 0, "pilot_samples": 800_000,
               "analysis_canonical_interval": [origin, stop * 3 // 5], "first_canonical_index": origin - 2952,
               "group_delay_already_removed_canonical_samples": 269,
               "declared_probe_offsets": [0, 250_000, 500_000],
               "configuration": {"residual_cfo_min_hz": -400_000, "residual_cfo_max_hz": 400_000},
               "source_ci16_sha256": "a" * 64, "probes": []}
    for index, (frequency, margin) in enumerate(zip(frequencies, margins, strict=True)):
        best = {"method": "glrt64", "margin": margin, "tracking_cfo_hz": frequency}
        receipt["probes"].append({"pilot_offset": [0, 250_000, 500_000][index], "sample_count": 50_000,
                                  "acquisition_status": "complete", "best": best, "candidates": [best]})
    return receipt


def test_unique_supported_cluster_retains_large_minority_alias_and_inputs():
    receipt = prior()
    original = copy.deepcopy(receipt)
    decision = study.select_prior(receipt, "positive")
    assert decision["status"] == "selected_provisional"
    assert decision["selected_cfo_hz"] == 285_500
    assert [item["distinct_probe_count"] for item in decision["clusters"]] == [2, 1]
    assert decision["clusters"][1]["median_hz"] == 512_000
    assert decision["alias_identity_resolved"] is False
    assert decision["prior_full_input_source_bounds"] == [899_995_000, 908_005_000]
    assert receipt == original


@pytest.mark.parametrize(("frequencies", "expected", "count"), [
    ((280_000, 289_000, 298_000), None, 2),  # Two overlapping maximal clusters.
    ((280_000, 290_000, 400_000), 285_000, 2),  # Inclusive10k boundary.
    ((280_000, 290_001, 400_000), None, 3),
    ((280_000, 285_000, 290_000), 285_000, 1),
    ((285_000, 285_000, 285_000), 285_000, 1),
])
def test_complete_link_cluster_boundaries(frequencies, expected, count):
    result = study.select_prior(prior(frequencies=frequencies), "positive")
    assert result["selected_cfo_hz"] == expected
    assert len(result["clusters"]) == count
    assert result["status"] == ("abstained" if expected is None else "selected_provisional")


def test_negative_prior_abstains_and_retains_every_low_margin():
    result = study.select_prior(prior("negative", margins=(.006, .005, .006)), "negative")
    assert result["selected_cfo_hz"] is None and result["clusters"] == []
    assert len(result["probes"]) == 3


def test_single_passing_probe_or_missing_candidate_abstains():
    receipt = prior(margins=(.4, .005, .006))
    receipt["probes"][1].update(best=None, candidates=[], acquisition_status="no_result")
    result = study.select_prior(receipt, "positive")
    assert result["status"] == "abstained"
    assert result["clusters"][0]["distinct_probe_count"] == 1


@pytest.mark.parametrize(("field", "value"), [
    ("status", "failed"), ("error", {}), ("pss_seeds_used", True), ("calibration_attached", True),
    ("pilot_saturation_events", 1), ("pilot_samples", 799999), ("first_canonical_index", 0),
    ("group_delay_already_removed_canonical_samples", 0), ("declared_probe_offsets", [0, 350000, 750000]),
])
def test_unqualified_prior_rejected(field, value):
    receipt = prior()
    receipt[field] = value
    with pytest.raises(ValueError):
        study.select_prior(receipt, "positive")


def test_best_ranking_and_candidate_bound_checked():
    receipt = prior()
    receipt["probes"][0]["best"] = {"method": "glrt64", "margin": .3, "tracking_cfo_hz": 0}
    with pytest.raises(ValueError, match="contradicts"):
        study.select_prior(receipt, "positive")
    receipt = prior()
    receipt["probes"][0]["candidates"] *= 9
    with pytest.raises(ValueError, match="unbounded"):
        study.select_prior(receipt, "positive")


@pytest.fixture
def plan_files(tmp_path, monkeypatch):
    monkeypatch.setattr(study, "ROOT", tmp_path)
    reports = tmp_path / "reports"
    reports.mkdir()
    hashes = {}
    for episode in ("negative", "positive"):
        receipt = prior(episode, margins=(.006, .005, .006) if episode == "negative" else (.4, .4, .4))
        payload = study.encode(receipt)
        hashes[episode] = study.sha256(payload)
        (reports / f"starlink-capture25-{episode}-pilot-20260909.json").write_bytes(payload)
    monkeypatch.setattr(study, "PRIOR_HASHES", hashes)
    monkeypatch.setattr(study, "source_hashes", lambda: {"synthetic-helper": "f" * 64})
    return tmp_path


def test_plan_pins_source_order_without_latency_claim(plan_files):
    plan = study.build_plan()
    assert len(plan["cases"]) == 4
    assert [item["primary_cfo_hz"] for item in plan["cases"]] == [None, None, 285500., 285500.]
    assert all(item["gap_after_prior_full_input_samples"] > 0 for item in plan["cases"])
    assert plan["cases"][2]["gap_after_prior_full_input_seconds"] == .1796
    assert plan["online_latency_qualified"] is False
    assert plan["prior_acquisition_processing_seconds"] is None
    assert plan["cfo_policy"]["future_or_same_window_saved_glrt_used"] is False


def test_tampered_prior_and_overlapping_case_rejected(plan_files, monkeypatch):
    path = plan_files / "reports/starlink-capture25-positive-pilot-20260909.json"
    original = path.read_bytes()
    path.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="prior changed"):
        study.build_plan()
    path.write_bytes(original)
    monkeypatch.setattr(study, "CASES", (("bad", "positive", 908_000_000, 916_000_000),))
    with pytest.raises(ValueError, match="overlap"):
        study.build_plan()


def fake_replay(calls, *, fail=False, interrupt=False):
    def run(name, directory, cfo):
        calls.append((name, cfo))
        directory.mkdir()
        if interrupt:
            raise KeyboardInterrupt("synthetic")
        variants = [{"name": variant, "numerical_qualification_pass": True,
                     "three_map_candidate_qualified": False,
                     "maps": {"three_map_existing_epoch_gates_pass": False},
                     "negative_control": {"maps": {"three_map_existing_epoch_gates_pass": False}}}
                    for variant in ["baseline"] + (["assisted"] if cfo is not None else [])]
        study.write_new(directory / "report.json", {"status": "FAILED_PARTIAL" if fail else "REPLAY_COMPLETE",
                                                     "variants": variants})
        return 1 if fail else 0
    return SimpleNamespace(run=run)


def prepare(plan_files):
    output = plan_files / "new-study"
    assert study.main(["plan", "--output", str(output)]) == 0
    return output, output / "plan.json"


def test_plan_phase_does_not_call_iq_helper_then_exact_run_keeps_abstentions(plan_files, monkeypatch):
    calls = []
    monkeypatch.setattr(study, "private_replay", lambda plan: fake_replay(calls))
    output, path = prepare(plan_files)
    assert calls == [] and not (output / "execution-start.json").exists()
    assert study.run_plan(path) == 0
    result, _ = study.read_json(output / "study-result.json")
    assert len(calls) == 4 and [item[1] for item in calls] == [None, None, 285500., 285500.]
    assert result["status"] == "complete" and result["online_latency_qualified"] is False
    assert result["cases"][0]["primary_pss_status"] == "not_attempted_prior_abstained"
    assert result["cases"][0]["primary_pss_candidate_qualified"] is None
    assert result["cases"][2]["primary_pss_candidate_qualified"] is False
    with pytest.raises(FileExistsError):
        study.run_plan(path)
    assert len(calls) == 4


@pytest.mark.parametrize("interrupt", [False, True])
def test_failure_retains_diagnostic_or_inflight_receipt(plan_files, monkeypatch, interrupt):
    calls = []
    monkeypatch.setattr(study, "private_replay", lambda plan: fake_replay(calls, fail=True, interrupt=interrupt))
    output, path = prepare(plan_files)
    with pytest.raises(KeyboardInterrupt if interrupt else ValueError):
        study.run_plan(path)
    result, _ = study.read_json(output / "study-result.json")
    assert result["status"] == "failed" and len(calls) == 1
    if interrupt:
        assert result["case_in_progress"]["name"] == "negative_later_1"
    else:
        assert result["cases"][0]["status"] == "FAILED_PARTIAL"


def test_plan_tamper_rejected_before_execution_marker(plan_files):
    output, path = prepare(plan_files)
    plan, _ = study.read_json(path)
    plan["cases"][0]["primary_cfo_hz"] = 123
    path.write_bytes(study.encode(plan))
    with pytest.raises(ValueError, match="pins changed"):
        study.run_plan(path)
    assert not (output / "execution-start.json").exists()


@pytest.mark.parametrize("payload", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}', b'[]'])
def test_bounded_strict_json(tmp_path, payload):
    path = tmp_path / "bad.json"
    path.write_bytes(payload)
    with pytest.raises(ValueError):
        study.read_json(path)


def test_capture_output_and_alias_rejected(tmp_path, monkeypatch):
    capture = tmp_path / "capture"
    capture.mkdir()
    monkeypatch.setattr(study, "CAPTURE", capture)
    with pytest.raises(ValueError, match="inside the capture"):
        study.output_directory(capture / "new")
    alias = tmp_path / "alias"
    alias.symlink_to(capture, target_is_directory=True)
    with pytest.raises(ValueError, match="alias"):
        study.output_directory(alias / "new")


def test_private_adapter_does_not_mutate_normal_helper():
    from tools import starlink_capture25_pss_replay as replay
    original = dict(replay.WINDOWS)
    plan = {"sources": {str(study.REPLAY): study.sha256(study.REPLAY.read_bytes())},
            "cases": [{"name": "private", "source_bounds": [25000000, 33000000]}]}
    module = study.private_replay(plan)
    assert module.WINDOWS == {"private": (25000000, 33000000)}
    assert replay.WINDOWS == original
