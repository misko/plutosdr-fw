"""Comparison preserves exact IQ identity, missing-work accounting and denominators.

Fake IIO and fake host reports test contracts; separate oracle/RTL tests supply
numerical evidence. These tests never label their zero IQ as real RF.
"""
import json
from dataclasses import replace

import pytest

from tools import starlink_glrt_local_compare as compare
from tools.starlink_glrt_capture import collect

from .test_local_iio_capture import LocalScenario, local_arguments


@pytest.fixture
def pair(tmp_path, monkeypatch):
    config = {"explicit_test_oracle": True}
    monkeypatch.setattr(compare, "CONFIG_SHA256", compare.canonical_digest(config))
    scenario, args = LocalScenario(), local_arguments(tmp_path)
    result = collect(args, library=scenario, context_factory=scenario.context)
    assert result["status"] == "complete"
    plan = tmp_path/"plan.json"
    compare.save(plan, compare.plan_for(args.output))
    host = tmp_path/"host"
    host.mkdir()
    emit_host(args.output, plan, host, config)
    return args.output, plan, host


def emit_host(capture, plan_path, host, config):
    plan = compare.load(plan_path)
    protocol = {"schema": "gla1-independent-host-replay/v1", "plan_sha256": compare.digest(plan_path),
                "fpga_seed_inputs": [], "config": config, "frequency_center_hz": 0,
                "iq_sha256": plan["iq_sha256"]}
    compare.save(host/"protocol.json", protocol)
    rows = []
    with (capture/"iq.ci16").open("rb") as stream:
        for n, offset in enumerate(plan["window_offsets"]):
            stream.seek(offset*4)
            raw = stream.read(56000)
            candidate = {"refined_epoch_sample": 17, "absolute_cfo_hz": -218700}
            rows.append({"sample_offset": offset, "sample_count": 14000,
                         "iq_sha256": compare.hashlib.sha256(raw).hexdigest(), "supported": n == 0,
                         "reasons": [] if n == 0 else ["no_acquisition_candidate"],
                         "candidates": [candidate] if n == 0 else []})
    (host/"windows.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
    compare.save(host/"summary.json", {"schema": protocol["schema"], "status": "complete",
        "iq_sha256": plan["iq_sha256"], "protocol_sha256": compare.digest(host/"protocol.json"),
        "records_sha256": compare.digest(host/"windows.jsonl"), "window_count": len(rows)})


def edit_host(host, mutate, *, protocol=False):
    path = host/("protocol.json" if protocol else "windows.jsonl")
    data = compare.load(path) if protocol else [json.loads(line) for line in path.read_text().splitlines()]
    mutate(data)
    path.write_text(json.dumps(data)+"\n" if protocol else "".join(json.dumps(r)+"\n" for r in data))
    summary = compare.load(host/"summary.json")
    summary["protocol_sha256" if protocol else "records_sha256"] = compare.digest(path)
    (host/"summary.json").write_text(json.dumps(summary))


def test_same_windows_match_without_premature_release_claim(pair):
    result = compare.compare_capture(*pair)
    assert result["comparable_windows"] == 2
    assert result["host_supported_windows"] == result["recovered_windows"] == 1
    assert result["recovery"] == 1 and result["detection_gate"] == "inconclusive"
    assert result["coverage"]["first_source_index"] > 2**53
    assert result["windows"][0]["epoch_distance_samples"] == result["windows"][0]["cfo_difference_hz"] == 0
    assert not result["hardware_accessed_by_comparator"] and not result["live_detector_qualified"]
    plan = compare.load(pair[1])
    assert plan["fpga_seed_inputs"] == [] and plan["window_offsets"] == [0, 250000]
    assert "events" not in plan and "cfo" not in plan and "candidates" not in plan


@pytest.mark.parametrize("key,value", [("refined_epoch_sample", 30), ("absolute_cfo_hz", 279700)])
def test_real_mismatch_is_not_hidden_by_matching_status_or_circular_cfo(pair, key, value):
    edit_host(pair[2], lambda rows: rows[0]["candidates"][0].update({key: value}))
    result = compare.compare_capture(*pair)
    assert result["host_supported_windows"] == 1 and result["recovered_windows"] == 0
    assert len(result["fpga_additional_or_mismatched"]) == 1


@pytest.mark.parametrize("change", ["offset", "missing", "digest", "bool", "nan", "out_of_band", "rank_geometry"])
def test_rehashed_host_output_still_requires_complete_and_valid_window_binding(pair, change):
    def mutate(rows):
        if change == "offset": rows[0]["sample_offset"] += 1
        elif change == "missing": rows.pop()
        elif change == "digest": rows[0]["iq_sha256"] = "0"*64
        elif change == "bool": rows[0]["supported"] = 1
        elif change == "nan": rows[0]["candidates"][0]["absolute_cfo_hz"] = float("nan")
        elif change == "out_of_band": rows[0]["candidates"][0]["absolute_cfo_hz"] = 500000
        else: rows[0]["candidates"][0]["refined_epoch_sample"] = 3333
    edit_host(pair[2], mutate)
    with pytest.raises(ValueError):
        compare.compare_capture(*pair)


@pytest.mark.parametrize("key,value", [("fpga_seed_inputs", ["timing"]), ("frequency_center_hz", 100000),
    ("plan_sha256", "0"*64), ("config", {"different": True})])
def test_host_search_must_be_independent_and_use_the_frozen_configuration(pair, key, value):
    edit_host(pair[2], lambda p: p.update({key: value}), protocol=True)
    with pytest.raises(ValueError):
        compare.compare_capture(*pair)


@pytest.mark.parametrize("file", ["iq.ci16", "events.raw", "final_local_search_snapshot.txt", "protocol.json"])
def test_changed_capture_is_rejected_before_scientific_comparison(pair, file):
    with (pair[0]/file).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError):
        compare.compare_capture(*pair)


def test_plan_cannot_omit_windows_even_when_host_and_fpga_would_agree(pair):
    plan = compare.load(pair[1])
    plan["window_offsets"].pop()
    pair[1].write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="plan"):
        compare.compare_capture(*pair)


@pytest.mark.parametrize("key", ["verify_minimum_q16", "period_samples", "cfo_unit_hz"])
def test_rehashed_capture_cannot_change_frozen_detector_profile(pair, key):
    capture = pair[0]
    protocol = compare.load(capture/"protocol.json")
    protocol["detector_profile"][key] += 1
    (capture/"protocol.json").write_text(json.dumps(protocol))
    summary = compare.load(capture/"summary.json")
    summary["evidence_sha256"]["protocol.json"] = compare.digest(capture/"protocol.json")
    (capture/"summary.json").write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="local profile"):
        compare.plan_for(capture)


def test_skipped_opportunity_is_separate_from_detector_disagreement(tmp_path, monkeypatch):
    config = {"explicit_test_oracle": True}
    monkeypatch.setattr(compare, "CONFIG_SHA256", compare.canonical_digest(config))
    scenario, args = LocalScenario(), local_arguments(tmp_path)
    e = scenario.evidence
    e["events"] = e["events"][:2]
    e["final"] = replace(e["final"], cpu_read=2, cpu_pushed=2)
    w = list(e["search"].words)
    w[4], w[5], w[7], w[8], w[9] = 2, 2, 1, 1, 1
    e["search"] = replace(e["search"], words=tuple(w))
    assert collect(args, library=scenario, context_factory=scenario.context)["status"] == "complete"
    plan, host = tmp_path/"plan.json", tmp_path/"host"
    compare.save(plan, compare.plan_for(args.output))
    host.mkdir()
    emit_host(args.output, plan, host, config)
    edit_host(host, lambda rows: rows[1].update(supported=True, reasons=[], candidates=rows[0]["candidates"]))
    result = compare.compare_capture(args.output, plan, host)
    assert result["comparable_windows"] == result["host_supported_windows"] == result["recovered_windows"] == 1
    assert result["coverage"]["skipped"] == 1
    assert result["host_windows_without_fpga_completion"][0]["host_supported"] is True


def test_zero_host_positives_are_inconclusive_not_perfect_recovery(pair):
    edit_host(pair[2], lambda rows: rows[0].update(supported=False, reasons=["score"]))
    result = compare.compare_capture(*pair)
    assert result["recovery"] is None and result["detection_gate"] == "inconclusive"
    assert result["fpga_additional_or_mismatched"]
