"""Synthetic JSON receipts only: no IQ, native model, or radio access."""

import copy
import hashlib
import json

import pytest

from tools import starlink_capture25_compare as compare


def candidate(passed=True, tiles=1, drift=0):
    return {"phase_bin": 6000, "phase_bin_start_sample": 6000, "phase_bin_center_sample": 6000.0,
            "tile_count": tiles, "combined_score": 1000, "combined_median": 100.0,
            "peak_to_median": 10.0, "peak_to_median_unbounded": False,
            "robust_z": 10.0 if passed else 1.0, "robust_z_unbounded": False,
            "passes_existing_epoch_gates": passed, "drift_bins_per_tile": drift,
            "estimated_frame_period_samples": 20_000 + drift / 64}


def maps(origin, passed=True):
    items = []
    for index in range(3):
        start, stop = origin + index * 1_280_000, origin + (index + 1) * 1_280_000
        fft = (origin + (start - origin) // 447 * 447,
               origin + (stop - 1 - origin) // 447 * 447 + 512)
        source = compare.source_support(fft)
        items.append({"map_index": index, "start_sample_index": start, "stop_sample_index": stop,
                      "canonical_full_fft_dependency_start_index": fft[0],
                      "canonical_full_fft_dependency_stop_index": fft[1],
                      "source_full_fft_and_fir_dependency_start_index": source[0],
                      "source_full_fft_and_fir_dependency_stop_index": source[1],
                      "candidate_zero_drift": candidate(passed)})
    return {"shape": [3, 20_000], "phase_bin_samples": 1, "tile_frames": 64, "maps": items,
            "discarded_leading_scores": 0, "discarded_trailing_scores": 960_000,
            "combined_candidate": candidate(passed, 3), "three_map_existing_epoch_gates_pass": passed,
            "drift_bank_bins_per_tile": [-12., -8., -4., 0., 4., 8., 12.]}


def case(window="positive"):
    start, stop = compare.WINDOWS[window]
    origin = start * 3 // 5
    first = origin + (1 - origin) % 6
    replay = {"schema": "starlink-capture25-pss-replay-v1", "window": window,
              "status": "REPLAY_COMPLETE", "numerical_qualification_pass": True,
              "assisted_cfo_hz_requested": 285_000.0,
              "capture": {"manifest_sha256": compare.MANIFEST_SHA256, "serial": compare.SERIAL,
                          "stream_id": "stream-1", "receiver_id": 0, "source_start_index": start,
                          "source_stop_index": stop},
              "conditioning": {"schema": "starlink-capture25-condition-v1", "input_rate_hz": 25_000_000,
                               "output_rate_hz": 15_000_000, "upsample": 3, "downsample": 5,
                               "downmix_hz": 5_000_000, "clipped_components": 0,
                               "filter": {"taps": 481, "upsampled_rate_hz": 75_000_000,
                                          "returned_center_delay_source_samples": 0}},
              "conditioned_ci16": {"sha256": "a" * 64, "first_canonical_index": origin - 2952},
              "variants": []}
    for name in ("baseline", "assisted"):
        replay["variants"].append({"name": name, "externally_assisted_not_blind": name == "assisted",
                                   "assisted_cfo_hz": 285_000.0 if name == "assisted" else 0,
                                   "model_first_canonical_index": origin, "retained_score_count": 4_800_000,
                                   "zero_padded_input_blocks": 0, "derotation_clipped_components": 0,
                                   "conditioning_clipped_components": 0, "forward_overflow_blocks": 0,
                                   "inverse_overflow_blocks": 0, "product_overflow_blocks": 0,
                                   "numerical_qualification_pass": True, "three_map_candidate_qualified": True,
                                   "qualification_errors": [], "maps": maps(origin),
                                   "negative_control": {"seed": 0xCA250017, "independent_rf_capture": False,
                                                        "maps": maps(origin, False)}})
    pilot = {"schema": "starlink-capture25-conditioned-pilot-crosscheck-v1", "status": "complete",
             "error": None, "source_ci16_sha256": "a" * 64, "first_canonical_index": origin - 2952,
             "analysis_canonical_interval": [origin, origin + 4_800_000], "pss_seeds_used": False,
             "calibration_attached": False, "group_delay_already_removed_canonical_samples": 269,
             "declared_probe_offsets": compare.PROBE_OFFSETS,
             "configuration": {"residual_cfo_min_hz": -400_000, "residual_cfo_max_hz": 400_000},
             "pilot_samples": 800_000, "pilot_saturation_events": 0,
             "first_pilot_canonical_center": first, "last_pilot_canonical_center": first + 799_999 * 6,
             "probes": []}
    for offset in compare.PROBE_OFFSETS:
        center = first + 6 * offset
        absolute = center + 6000
        best = {"epoch_sample": 1000, "frame_start_canonical_center": absolute,
                "frame_start_original25_sample_numerator": 5 * absolute,
                "frame_start_original25_sample_denominator": 3,
                "phase_us_mod_750hz": (absolute % 20_000) / 15,
                "method": "glrt64", "exact_score": .5, "control_score": .1, "margin": .4,
                "residual_cfo_hz": 300, "tracking_cfo_hz": 512_500 if offset == 500_000 else 285_000}
        pilot["probes"].append({"pilot_offset": offset, "sample_count": 50_000,
                                "canonical_center_start": center, "acquisition_status": "complete",
                                "best": best, "candidates": [best]})
    reference = {"schema_version": 1, "session_id": compare.SESSION, "stream_id": "stream-1",
                 "radio_serial": compare.SERIAL, "receiver_id": 0, "sample_rate_hz": 25_000_000,
                 "manifest_sha256": compare.MANIFEST_SHA256, "windows": []}
    for name, bounds in compare.WINDOWS.items():
        rows = [[bounds[0] + offset, bounds[0] + offset + 500_000, bounds[0] + offset + 10_000,
                 8_097_500., 8_097_000., 500., .5, .1, .4, True, 14, 14]
                for offset in range(0, 7_500_001, 250_000)]
        reference["windows"].append({"label": "targeted_" + name, "source_bounds": list(bounds),
                                     "columns": compare.COLUMNS, "rows": rows, "window_count": 31,
                                     "pass_count": 31, "diagnostic_assisted_residual_hz":
                                     285_000. if name == "positive" else -128_000.,
                                     "pss": {"overlapping_blocks": [], "adjacent_blocks": []}})
    return replay, pilot, reference


def test_support_join_retains_first_probe_but_excludes_its_filter_halo():
    result = compare.compare_window("positive", *case())
    probe = result["variants"][0]["maps"][0]["pilot_matches"][0]
    assert probe["nominal_centers_included"] is True
    assert probe["full_dependency_included"] is False
    assert probe["circular_delta_us"] is None
    second = result["variants"][0]["maps"][1]["pilot_matches"][1]
    assert second["full_dependency_included"] is True
    assert second["circular_delta_us"] == pytest.approx(-1 / 15)
    assert result["pilot_probes"][2]["raw_probe"]["best"]["tracking_cfo_hz"] == 512_500
    combined = result["variants"][0]["combined"]
    assert combined["saved_glrt_inside_count"] == 24
    assert len(result["saved_glrt_rows"]) == 31


def test_source_support_endpoints():
    assert compare.source_support((300, 600)) == (420, 1079)
    assert compare.source_support((300, 301)) == (420, 581)
    with pytest.raises(ValueError):
        compare.source_support((0, 1))


@pytest.mark.parametrize(("phase", "numerator", "denominator", "expected"), [
    (0, 19_999, 1, 1 / 15), (19_999, 0, 1, -1 / 15), (0, 10_000, 1, -10_000 / 15),
    (6000, 30_001, 5, -1 / 75), (6000, 30_000 + 100_000 * 10**10, 5, 0),
])
def test_exact_circular_integer_mapping(phase, numerator, denominator, expected):
    assert compare.circular_delta_us(phase, numerator, denominator) == pytest.approx(expected)


@pytest.mark.parametrize("drift", [-12, -4, 4, 12])
def test_nonzero_combined_drift_never_becomes_fitted_timing(drift):
    replay, pilot, reference = case()
    replay["variants"][0]["maps"]["combined_candidate"] = candidate(tiles=3, drift=drift)
    combined = compare.compare_window("positive", replay, pilot, reference)["variants"][0]["combined"]
    assert combined["comparison_pss_gate_qualified"] is True
    assert combined["drift_bank_boundary_winner"] is (abs(drift) == 12)
    assert combined["timing_comparison_enabled"] is False
    assert combined["qualified_saved_circular_delta_us"]["count"] == 0


def test_negative_window_assistance_explicitly_comes_from_positive_reference():
    result = compare.compare_window("negative", *case("negative"))
    assert result["variants"][1]["assistance_reference_window"] == "targeted_positive"


@pytest.mark.parametrize("reason", ["pss_negative", "scrambled_positive", "numerical_fault", "pilot_negative", "late_pilot_failure"])
def test_failed_gate_suppresses_delta_but_keeps_metrics(reason):
    replay, pilot, reference = case()
    variant = replay["variants"][0]
    if reason == "pss_negative":
        variant["maps"] = maps(540_000_000, False)
        variant["three_map_candidate_qualified"] = False
    elif reason == "scrambled_positive":
        variant["negative_control"]["maps"] = maps(540_000_000)
    elif reason == "numerical_fault":
        variant.update(derotation_clipped_components=1, numerical_qualification_pass=False,
                       three_map_candidate_qualified=False, qualification_errors=["clipped"])
        replay.update(numerical_qualification_pass=False, status="REPLAY_COMPLETE_NUMERICAL_QUALIFICATION_FAILED")
    elif reason == "pilot_negative":
        for probe in pilot["probes"]:
            probe["best"]["margin"] = .006
    else:
        pilot.update(status="failed", error={"type": "RuntimeError", "repr": "late source hash failure"})
    result = compare.compare_window("positive", replay, pilot, reference)
    assert len(result["pilot_probes"]) == 3
    assert all(row["circular_delta_us"] is None for item in result["variants"][0]["maps"]
               for row in item["pilot_matches"])


def test_negative_glrt_rows_and_no_candidate_probe_retained():
    replay, pilot, reference = case()
    ref = reference["windows"][1]
    for row in ref["rows"]:
        row[8], row[9] = .006, False
    ref["pass_count"] = 0
    pilot["probes"][1].update(candidates=[], best=None, acquisition_status="no_result")
    result = compare.compare_window("positive", replay, pilot, reference)
    combined = result["variants"][0]["combined"]
    assert combined["saved_glrt_inside_count"] == 24
    assert combined["saved_glrt_inside_pass_count"] == 0
    assert combined["qualified_saved_circular_delta_us"]["count"] == 0
    assert result["pilot_probes"][1]["numerical_reference_qualified"] is False


@pytest.mark.parametrize(("owner", "path", "value"), [
    (0, ("capture", "serial"), "wrong"), (0, ("capture", "source_start_index"), 900_000_001),
    (0, ("status",), "FAILED_PARTIAL"), (0, ("conditioning", "downmix_hz"), 4_882_812.5),
    (0, ("conditioning", "filter", "returned_center_delay_source_samples"), 80),
    (0, ("variants", 0, "maps", "maps", 1, "canonical_full_fft_dependency_start_index"), 541_280_000),
    (0, ("variants", 0, "maps", "maps", 1, "source_full_fft_and_fir_dependency_stop_index"), 904_267_546),
    (0, ("variants", 0, "maps", "maps", 1, "candidate_zero_drift", "passes_existing_epoch_gates"), False),
    (0, ("variants", 0, "zero_padded_input_blocks"), 1),
    (0, ("variants", 1, "assisted_cfo_hz"), 123), (1, ("source_ci16_sha256",), "b" * 64),
    (1, ("first_canonical_index",), 0), (1, ("group_delay_already_removed_canonical_samples",), 0),
    (1, ("configuration", "residual_cfo_max_hz"), 600_000), (1, ("pilot_saturation_events",), 1),
    (1, ("probes", 0, "canonical_center_start"), 540_000_000),
    (1, ("probes", 0, "candidates", 0, "frame_start_original25_sample_numerator"), 0),
    (1, ("probes", 0, "candidates", 0, "method"), "symbolwise"),
    (2, ("windows", 1, "rows", 0, 9), False), (2, ("windows", 1, "rows", 0, 1), 900_500_001),
])
def test_mismatches_fail_closed(owner, path, value):
    documents = case()
    target = documents[owner]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        compare.compare_window("positive", *documents)


def test_no_input_mutation():
    documents = case()
    original = copy.deepcopy(documents)
    compare.compare_window("positive", *documents)
    assert documents == original


@pytest.mark.parametrize("payload", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}', b'[]'])
def test_strict_json_loader(tmp_path, payload):
    path = tmp_path / "input.json"
    path.write_bytes(payload)
    with pytest.raises(ValueError):
        compare.read_json(path)


def test_json_bound_and_exact_bytes_hash(tmp_path, monkeypatch):
    path = tmp_path / "input.json"
    payload = b'{ "hello" : 123 }\n'
    path.write_bytes(payload)
    document, receipt = compare.read_json(path)
    assert document == {"hello": 123}
    assert receipt["sha256"] == hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(compare, "MAX_JSON_BYTES", len(payload) - 1)
    with pytest.raises(ValueError):
        compare.read_json(path)


@pytest.fixture
def command(tmp_path):
    args = ["--output", str(tmp_path / "result.json")]
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(case()[2]))
    args += ["--reference", str(path)]
    for name in ("negative", "positive"):
        replay, pilot, _ = case(name)
        args += ["--case", name]
        for kind, value in (("replay", replay), ("pilot", pilot)):
            path = tmp_path / (name + "-" + kind + ".json")
            path.write_text(json.dumps(value))
            args.append(str(path))
    return args, tmp_path


def test_main_success_and_no_overwrite(command):
    args, root = command
    assert compare.main(args) == 0
    receipt = json.loads((root / "result.json").read_text())
    assert receipt["status"] == "complete" and len(receipt["inputs"]) == 5
    assert receipt["hardware_access"] is False and receipt["ground_truth_available"] is False
    with pytest.raises(ValueError, match="already exists"):
        compare.main(args)


@pytest.mark.parametrize("missing", [False, True])
def test_main_failure_keeps_completed_window_and_input_hashes(command, missing):
    args, root = command
    if missing:
        args[-1] = str(root / "absent.json")
    else:
        path = root / "positive-pilot.json"
        pilot = json.loads(path.read_text())
        pilot["group_delay_already_removed_canonical_samples"] = 0
        path.write_text(json.dumps(pilot))
    assert compare.main(args) == 1
    receipt = json.loads((root / "result.json").read_text())
    assert receipt["status"] == "failed"
    assert [item["window"] for item in receipt["windows"]] == ["negative"]
    assert len(receipt["inputs"]) == (4 if missing else 5)
    assert receipt["error"]["type"] == "ValueError"
