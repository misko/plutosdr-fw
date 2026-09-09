"""Compare retained capture25 JSON evidence; never read IQ or contact a radio.

This targeted, same-recording comparison is not ground truth, blind discovery,
native 25 MS/s firmware qualification, or timing lock. The two numerical paths
share recorded RF and a spectral conditioner; their algorithms are independent,
not their underlying observations. Source support is a conservative dependency
bound, not an assertion that every FFT/FIR input contributes equally to a score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path

MAX_JSON_BYTES = 8 * 1024 * 1024
WINDOWS = {"negative": (12_500_000, 20_500_000), "positive": (900_000_000, 908_000_000)}
SESSION = "cap-20260909T121248-414fb81f488c"
SERIAL = "10400056f695001322002d0010ad1719f2"
MANIFEST_SHA256 = "aaadf18494225b2ce55b9e1247d45a09e31e4a13ea1b88896ccadabff6ebe20a"
PROBE_OFFSETS = [0, 250_000, 500_000]
GLRT_MARGIN_GATE = 0.025
GLRT_GATE_SOURCE = (
    "ea96b2b214f059dbeb03bd67783598e75b6bfc07:"
    "src/leo/analysis/standard/full_capture_glrt20ms.py:FullCaptureGlrt20msConfig.margin_gate"
)
COLUMNS = ["start", "stop", "epoch", "tracking_cfo_hz", "acquired_cfo_hz", "residual_cfo_hz",
           "glrt_exact_score", "glrt_control_score", "glrt_margin", "passed_margin_gate",
           "lattice_frame_count", "measured_frame_count"]


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def integer(value, name: str, minimum: int = 0, maximum: int = (1 << 63) - 1) -> int:
    require(type(value) is int and minimum <= value <= maximum, f"invalid integer {name}")
    return value


def number(value, name: str) -> float:
    require(type(value) in (int, float) and math.isfinite(value), f"invalid number {name}")
    return float(value)


def bounded_list(value, maximum: int, name: str) -> list:
    require(type(value) is list and len(value) <= maximum, f"unbounded or malformed {name}")
    return value


def interval(start, stop) -> tuple[int, int]:
    start, stop = integer(start, "start"), integer(stop, "stop")
    require(start < stop, "empty or reversed interval")
    return start, stop


def contains(outer, inner) -> bool:
    return outer[0] <= inner[0] and inner[1] <= outer[1]


def source_support(canonical) -> tuple[int, int]:
    """481-tap centered FIR at75MHz: ceil((5a-240)/3)..floor((5(b-1)+240)/3)."""
    a, b = interval(*canonical)
    return interval((5 * a - 240 + 2) // 3, (5 * (b - 1) + 240) // 3 + 1)


def circular_delta_us(pss_phase_sample: int, reference_numerator: int, denominator: int) -> float:
    """Signed PSS-minus-reference, exact integer modulo before float conversion.

    Reference is a rational canonical15MHz coordinate. The half-period tie is
    negative, with result in[-666.666...,666.666...)us. No fitted drift is applied.
    """
    integer(pss_phase_sample, "phase", maximum=19_999)
    integer(reference_numerator, "reference numerator", maximum=(1 << 66) - 1)
    integer(denominator, "denominator", minimum=1, maximum=5)
    period = 20_000 * denominator
    delta = (pss_phase_sample * denominator - reference_numerator + period // 2) % period - period // 2
    return delta / denominator / 15


def summary(values) -> dict:
    values = list(values)
    return {"count": len(values), "min": min(values) if values else None,
            "median": statistics.median(values) if values else None,
            "max": max(values) if values else None}


def _candidate(candidate: dict, tiles: int) -> bool:
    phase = integer(candidate["phase_bin"], "phase bin", maximum=19_999)
    require(candidate["phase_bin_start_sample"] == phase
            and candidate["phase_bin_center_sample"] == phase
            and candidate["tile_count"] == tiles, "candidate phase/tile geometry mismatch")
    integer(candidate["combined_score"], "combined score", maximum=tiles * 64 * 255)
    require(number(candidate["combined_median"], "median") >= 0, "negative median")
    gates = []
    for key, threshold in (("peak_to_median", 1.15), ("robust_z", 6.0)):
        unbounded = candidate[key + "_unbounded"]
        require(type(unbounded) is bool, "invalid unbounded metric marker")
        if unbounded:
            require(candidate[key] is None, "contradictory unbounded metric")
            gates.append(True)
        else:
            gates.append(number(candidate[key], key) >= threshold)
    passed = all(gates)
    require(candidate["passes_existing_epoch_gates"] is passed, "PSS gate contradicts metrics")
    drift = number(candidate["drift_bins_per_tile"], "drift")
    require(candidate["estimated_frame_period_samples"] == 20_000 + drift / 64,
            "candidate period/drift mismatch")
    if tiles == 1:
        require(drift == 0, "single-map candidate must have zero drift")
    return passed


def _maps(document: dict, origin: int) -> list[dict]:
    require(document["shape"] == [3, 20_000] and document["phase_bin_samples"] == 1
            and document["tile_frames"] == 64, "unsupported map geometry")
    maps = bounded_list(document["maps"], 3, "maps")
    require(len(maps) == 3, "three complete maps required")
    require(document["discarded_leading_scores"] == 0
            and document["discarded_trailing_scores"] == 960_000, "unexpected score truncation")
    for index, item in enumerate(maps):
        begin, end = origin + index * 1_280_000, origin + (index + 1) * 1_280_000
        require(item["map_index"] == index and item["start_sample_index"] == begin
                and item["stop_sample_index"] == end, "map candidate interval mismatch")
        fft = (origin + (begin - origin) // 447 * 447,
               origin + (end - 1 - origin) // 447 * 447 + 512)
        require((item["canonical_full_fft_dependency_start_index"],
                 item["canonical_full_fft_dependency_stop_index"]) == fft,
                "map FFT dependency mismatch")
        require((item["source_full_fft_and_fir_dependency_start_index"],
                 item["source_full_fft_and_fir_dependency_stop_index"]) == source_support(fft),
                "map conditioner dependency mismatch")
        _candidate(item["candidate_zero_drift"], 1)
    passed = _candidate(document["combined_candidate"], 3)
    require(document["three_map_existing_epoch_gates_pass"] is passed, "combined gate mismatch")
    bank = document["drift_bank_bins_per_tile"]
    require(bank == [-12.0, -8.0, -4.0, 0.0, 4.0, 8.0, 12.0]
            and document["combined_candidate"]["drift_bins_per_tile"] in bank,
            "unexpected drift bank or candidate")
    return maps


def _reference_rows(reference: dict, window: str) -> tuple[dict, list[dict]]:
    require(reference["schema_version"] == 1 and reference["session_id"] == SESSION
            and reference["stream_id"] == "stream-1" and reference["radio_serial"] == SERIAL
            and reference["receiver_id"] == 0 and reference["sample_rate_hz"] == 25_000_000
            and reference["manifest_sha256"] == MANIFEST_SHA256, "reference identity mismatch")
    matches = [item for item in bounded_list(reference["windows"], 2, "reference windows")
               if item["label"] == "targeted_" + window]
    require(len(matches) == 1, "missing/duplicate reference window")
    selected = matches[0]
    require(selected["source_bounds"] == list(WINDOWS[window])
            and selected["columns"] == COLUMNS, "reference columns or interval mismatch")
    rows = []
    previous = -1
    for raw in bounded_list(selected["rows"], 64, "GLRT rows"):
        require(type(raw) is list and len(raw) == len(COLUMNS), "malformed GLRT row")
        row = dict(zip(COLUMNS, raw, strict=True))
        support = interval(row["start"], row["stop"])
        require(contains(WINDOWS[window], support) and row["stop"] - row["start"] == 500_000
                and row["start"] > previous, "GLRT order or support mismatch")
        previous = row["start"]
        integer(row["epoch"], "GLRT epoch", row["start"], row["start"] + 33_334)
        for key in COLUMNS[3:9]:
            number(row[key], key)
        require(row["passed_margin_gate"] is (row["glrt_margin"] >= GLRT_MARGIN_GATE),
                "saved GLRT gate contradicts declared margin policy")
        integer(row["lattice_frame_count"], "lattice frames", maximum=15)
        integer(row["measured_frame_count"], "measured frames", maximum=15)
        rows.append(row)
    require(selected["window_count"] == len(rows)
            and selected["pass_count"] == sum(row["passed_margin_gate"] for row in rows),
            "reference count mismatch")
    return selected, rows


def _pilot_probes(pilot: dict, replay: dict, origin: int) -> list[dict]:
    require(pilot["schema"] == "starlink-capture25-conditioned-pilot-crosscheck-v1",
            "unsupported pilot schema")
    require(pilot["status"] in ("complete", "failed"), "pilot is not terminal")
    derivative = replay["conditioned_ci16"]
    require(pilot["source_ci16_sha256"] == derivative["sha256"]
            and pilot["first_canonical_index"] == derivative["first_canonical_index"]
            and pilot["analysis_canonical_interval"] == [origin, origin + 4_800_000],
            "pilot derivative/origin binding mismatch")
    require(pilot["pss_seeds_used"] is False and pilot["calibration_attached"] is False
            and pilot["group_delay_already_removed_canonical_samples"] == 269
            and pilot["declared_probe_offsets"] == PROBE_OFFSETS, "pilot method contract mismatch")
    config = pilot["configuration"]
    require(config["residual_cfo_min_hz"] == -400_000
            and config["residual_cfo_max_hz"] == 400_000, "pilot independent CFO search changed")
    probes = bounded_list(pilot["probes"], 3, "pilot probes")
    if pilot["status"] == "complete":
        require(pilot["error"] is None and pilot["pilot_samples"] == 800_000
                and pilot["pilot_saturation_events"] == 0 and len(probes) == 3,
                "complete pilot has faults or incomplete data")
    first = origin + (1 - origin) % 6
    if probes:
        require(pilot["first_pilot_canonical_center"] == first
                and pilot["last_pilot_canonical_center"] == first + 799_999 * 6,
                "pilot center lattice mismatch")
    results = []
    for index, probe in enumerate(probes):
        offset = PROBE_OFFSETS[index]
        center = first + offset * 6
        require(probe["pilot_offset"] == offset and probe["sample_count"] == 50_000
                and probe["canonical_center_start"] == center, "probe geometry mismatch")
        candidates = bounded_list(probe["candidates"], 8, "pilot candidates")
        for candidate in candidates:
            epoch = integer(candidate["epoch_sample"], "pilot epoch", maximum=3333)
            absolute = center + 6 * epoch
            require(candidate["frame_start_canonical_center"] == absolute
                    and candidate["frame_start_original25_sample_numerator"] == 5 * absolute
                    and candidate["frame_start_original25_sample_denominator"] == 3
                    and candidate["phase_us_mod_750hz"] == (absolute % 20_000) / 15
                    and candidate["method"] == "glrt64", "pilot candidate coordinate/method mismatch")
            for key in ("exact_score", "control_score", "margin", "residual_cfo_hz", "tracking_cfo_hz"):
                number(candidate[key], key)
        best = max(candidates, key=lambda item: item["margin"], default=None)
        require(probe["best"] == best, "pilot best contradicts retained candidate ranking")
        centers = (center, center + (50_000 - 1) * 6 + 1)
        raw = (centers[0] - 269, centers[1] + 269)
        qualified = (pilot["status"] == "complete" and probe["acquisition_status"] == "complete"
                     and best is not None and best["margin"] >= GLRT_MARGIN_GATE)
        results.append({"raw_probe": probe, "pilot_center_bounds_canonical": list(centers),
                        "pilot_raw_ddc_dependency_canonical": list(raw),
                        "source_full_ddc_and_fir_dependency": list(source_support(raw)),
                        "margin_gate_pass": best is not None and best["margin"] >= GLRT_MARGIN_GATE,
                        "numerical_reference_qualified": qualified})
    return results


def _comparisons(candidate: dict, qualified: bool, nominal: tuple, fft: tuple,
                 rows: list[dict], probes: list[dict]) -> dict:
    dependency = source_support(fft)
    saved = []
    for row in rows:
        full = contains(dependency, (row["start"], row["stop"]))
        nominal_included = 5 * nominal[0] <= 3 * row["start"] and 3 * row["stop"] <= 5 * nominal[1]
        delta = (circular_delta_us(candidate["phase_bin"], 3 * row["epoch"], 5)
                 if qualified and full and row["passed_margin_gate"] else None)
        saved.append({"source_start": row["start"], "source_stop": row["stop"],
                      "full_dependency_included": full, "nominal_score_interval_included": nominal_included,
                      "passed_saved_margin_gate": row["passed_margin_gate"], "circular_delta_us": delta})
    joined = []
    for probe in probes:
        full = (contains(fft, probe["pilot_raw_ddc_dependency_canonical"])
                and contains(dependency, probe["source_full_ddc_and_fir_dependency"]))
        nominal_included = contains(nominal, probe["pilot_center_bounds_canonical"])
        best = probe["raw_probe"]["best"]
        delta = (circular_delta_us(candidate["phase_bin"], best["frame_start_canonical_center"], 1)
                 if qualified and full and probe["numerical_reference_qualified"] else None)
        joined.append({"pilot_offset": probe["raw_probe"]["pilot_offset"],
                       "full_dependency_included": full, "nominal_centers_included": nominal_included,
                       "numerical_reference_qualified": probe["numerical_reference_qualified"],
                       "circular_delta_us": delta})
    included = [row for row, match in zip(rows, saved, strict=True) if match["full_dependency_included"]]
    return {"source_full_dependency": list(dependency), "saved_glrt_matches": saved,
            "saved_glrt_inside_count": len(included),
            "saved_glrt_inside_pass_count": sum(row["passed_margin_gate"] for row in included),
            "saved_glrt_inside_margin": summary(row["glrt_margin"] for row in included),
            "saved_glrt_inside_tracking_cfo_hz": summary(row["tracking_cfo_hz"] for row in included),
            "qualified_saved_circular_delta_us": summary(item["circular_delta_us"] for item in saved
                                                           if item["circular_delta_us"] is not None),
            "pilot_matches": joined}


def compare_window(window: str, replay: dict, pilot: dict, reference: dict) -> dict:
    require(window in WINDOWS, "unknown targeted window")
    require(replay["schema"] == "starlink-capture25-pss-replay-v1"
            and replay["window"] == window, "replay schema/window mismatch")
    require(replay["status"] in ("REPLAY_COMPLETE", "REPLAY_COMPLETE_NUMERICAL_QUALIFICATION_FAILED"),
            "replay not complete; missing/partial data is not a negative detection")
    start, stop = WINDOWS[window]
    origin = start * 3 // 5
    capture = replay["capture"]
    require(capture["manifest_sha256"] == MANIFEST_SHA256 and capture["serial"] == SERIAL
            and capture["stream_id"] == "stream-1" and capture["receiver_id"] == 0
            and capture["source_start_index"] == start and capture["source_stop_index"] == stop,
            "replay capture identity mismatch")
    conditioning = replay["conditioning"]
    require(conditioning["schema"] == "starlink-capture25-condition-v1"
            and conditioning["input_rate_hz"] == 25_000_000 and conditioning["output_rate_hz"] == 15_000_000
            and conditioning["upsample"] == 3 and conditioning["downsample"] == 5
            and conditioning["downmix_hz"] == 5_000_000
            and conditioning["filter"]["taps"] == 481
            and conditioning["filter"]["upsampled_rate_hz"] == 75_000_000
            and conditioning["filter"]["returned_center_delay_source_samples"] == 0,
            "conditioner frequency/delay geometry mismatch")
    selected, rows = _reference_rows(reference, window)
    probes = _pilot_probes(pilot, replay, origin)
    variants = bounded_list(replay["variants"], 2, "variants")
    require([item["name"] for item in variants] == ["baseline", "assisted"],
            "both baseline and explicitly assisted variants required")
    result = {"window": window, "source_interval": [start, stop],
              "pilot_status": pilot["status"], "pilot_error": pilot["error"], "pilot_probes": probes,
              "saved_glrt_columns": COLUMNS, "saved_glrt_rows": selected["rows"],
              "saved_native_pss_context": selected["pss"], "variants": []}
    numerical_passes = []
    for variant in variants:
        assisted = variant["name"] == "assisted"
        assistance_sources = [item["label"] for item in reference["windows"]
                              if item["diagnostic_assisted_residual_hz"] == variant["assisted_cfo_hz"]]
        require(variant["externally_assisted_not_blind"] is assisted
                and variant["assisted_cfo_hz"] == (replay["assisted_cfo_hz_requested"] if assisted else 0)
                and (not assisted or len(assistance_sources) == 1),
                "CFO assistance binding mismatch")
        require(variant["model_first_canonical_index"] == origin
                and variant["retained_score_count"] == 4_800_000
                and variant["zero_padded_input_blocks"] == 0, "model candidate geometry mismatch")
        clips = integer(variant["derotation_clipped_components"], "derotation clips")
        require(variant["conditioning_clipped_components"] == conditioning["clipped_components"],
                "conditioner clip receipt mismatch")
        numeric = clips == 0 and integer(conditioning["clipped_components"], "conditioner clips") == 0
        for key in ("forward_overflow_blocks", "inverse_overflow_blocks", "product_overflow_blocks"):
            numeric = integer(variant[key], key) == 0 and numeric
        require(variant["numerical_qualification_pass"] is numeric, "numerical gate mismatch")
        numerical_passes.append(numeric)
        maps = _maps(variant["maps"], origin)
        control = variant["negative_control"]
        require(control["independent_rf_capture"] is False and control["seed"] == 0xCA250017,
                "scrambled control contract mismatch")
        controls = _maps(control["maps"], origin)
        combined = variant["maps"]["combined_candidate"]
        combined_control = control["maps"]["combined_candidate"]
        require(variant["three_map_candidate_qualified"] is (
            numeric and combined["passes_existing_epoch_gates"]), "variant candidate qualification mismatch")
        output = {"name": variant["name"], "assisted_cfo_hz": variant["assisted_cfo_hz"],
                  "assistance_reference_window": assistance_sources[0] if assisted else None,
                  "externally_assisted_not_blind": assisted, "numerical_qualification_pass": numeric,
                  "qualification_errors": variant["qualification_errors"], "maps": []}
        for item, scrambled in zip(maps, controls, strict=True):
            candidate, null = item["candidate_zero_drift"], scrambled["candidate_zero_drift"]
            qualified = numeric and candidate["passes_existing_epoch_gates"] and not null["passes_existing_epoch_gates"]
            nominal = (item["start_sample_index"], item["stop_sample_index"])
            fft = (item["canonical_full_fft_dependency_start_index"], item["canonical_full_fft_dependency_stop_index"])
            output["maps"].append({"raw_map": item, "scrambled_candidate": null,
                                   "comparison_pss_gate_qualified": qualified,
                                   **_comparisons(candidate, qualified, nominal, fft, rows, probes)})
        bank = variant["maps"]["drift_bank_bins_per_tile"]
        boundary = combined["drift_bins_per_tile"] in (min(bank), max(bank))
        combined_gate = numeric and combined["passes_existing_epoch_gates"] and not combined_control["passes_existing_epoch_gates"]
        # This utility has no qualified drift model. Even an interior nonzero
        # winner is not translated into per-time phase by inventing a fit.
        combined_timing = combined_gate and combined["drift_bins_per_tile"] == 0
        output["combined"] = {
            "candidate": combined, "scrambled_candidate": combined_control,
            "comparison_pss_gate_qualified": combined_gate, "drift_bank_boundary_winner": boundary,
            "drift_fit_qualified": False, "timing_comparison_enabled": combined_timing,
            "timing_policy": "Only zero-drift pooled nominal phase; no inferred drift fit or extrapolation",
            **_comparisons(combined, combined_timing,
                           (maps[0]["start_sample_index"], maps[-1]["stop_sample_index"]),
                           (maps[0]["canonical_full_fft_dependency_start_index"],
                            maps[-1]["canonical_full_fft_dependency_stop_index"]), rows, probes)}
        result["variants"].append(output)
    require(replay["numerical_qualification_pass"] is all(numerical_passes)
            and (replay["status"] == "REPLAY_COMPLETE") is all(numerical_passes),
            "replay terminal qualification mismatch")
    return result


def read_json(path: Path) -> tuple[dict, dict]:
    require(path.is_file() and path.stat().st_size <= MAX_JSON_BYTES, "missing or oversized JSON input")
    with path.open("rb") as source:
        payload = source.read(MAX_JSON_BYTES + 1)
    require(len(payload) <= MAX_JSON_BYTES, "JSON grew beyond byte bound")

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")

    def finite(value):
        return number(float(value), "JSON float")

    document = json.loads(payload, object_pairs_hook=pairs, parse_constant=constant, parse_float=finite)
    require(type(document) is dict, "JSON root must be an object")
    return document, {"path": str(path.resolve()), "bytes": len(payload),
                      "sha256": hashlib.sha256(payload).hexdigest()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--case", required=True, action="append", nargs=3, metavar=("WINDOW", "REPLAY", "PILOT"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    require(not args.output.exists() and not args.output.is_symlink(), "output already exists")
    require(sorted(item[0] for item in args.case) == ["negative", "positive"], "exactly two named cases required")
    receipt = {"schema": "starlink-capture25-comparison-v1", "status": "failed", "error": None,
               "inputs": [], "windows": [], "hardware_access": False, "native_25msps_qualified": False,
               "timing_lock_proven": False, "ground_truth_available": False,
               "pilot_margin_gate": GLRT_MARGIN_GATE, "pilot_margin_gate_source": GLRT_GATE_SOURCE,
               "pss_gates": {"peak_to_median_minimum": 1.15, "robust_z_minimum": 6.0,
                             "matching_scrambled_control_must_fail": True},
               "timing_sign": "PSS minus reference, circular nominal750Hz phase; microseconds",
               "limitations": [
                   "Evidence-selected targeted windows, not blind discovery or false-alarm-rate qualification.",
                   "Host C-model/integer pilot oracle on shared conditioned RF, not RTL or native25MS/s FPGA.",
                   "Negative gates, missing evidence and support exclusions are distinct outcomes.",
                   "All saved rows/candidates retained; overlapping20ms windows are not independent frame counts.",
                   "No de-aliasing, drift fitting, PSS-seeded GLRT, or calibrated absolute timing truth.",
                   "Full processing envelopes are conservative BFP/FIR dependencies, not equal tap contributions.",
                   "First-to-last pilot center bounds exclude its DDC history; strict joining includes history.",
                   "JSON hashes bind retained receipts; IQ/map binary scores are not reread or revalidated here.",
                   "Saved PSS blocks are contextual only, not asserted as same-support agreement.",
                   "A completed comparison reports qualified disagreement as well as agreement; it is not a success gate."],
               "utility_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        reference, metadata = read_json(args.reference)
        receipt["inputs"].append({"role": "reference", **metadata})
        for name, replay_path, pilot_path in sorted(args.case):
            replay, metadata = read_json(Path(replay_path))
            receipt["inputs"].append({"role": name + "_replay", **metadata})
            pilot, metadata = read_json(Path(pilot_path))
            receipt["inputs"].append({"role": name + "_pilot", **metadata})
            receipt["windows"].append(compare_window(name, replay, pilot, reference))
        receipt["status"] = "complete"
    except (ValueError, TypeError, KeyError, OSError, OverflowError, RecursionError) as error:
        receipt["error"] = {"type": type(error).__name__, "repr": repr(error)[:4000]}
    encoded = json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with args.output.open("x") as output:
        output.write(encoded)
    return 0 if receipt["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
