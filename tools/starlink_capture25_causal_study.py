"""Predeclared, source-ordered capture25 CFO study; offline, never a radio client.

Only earlier, already retained *blind pilot* receipts choose a frequency. Later
PSS results cannot change that decision. Source-order causality is not proof
that acquisition computation would meet an online deadline. The episodes were
selected using historical activity evidence, so this is not blind discovery.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "tools/starlink_capture25_pss_replay.py"
CAPTURE = Path("/srv/bulk/leo/recordings/2026/09/09/cap-20260909T121248-414fb81f488c")
MANIFEST_HASH = "aaadf18494225b2ce55b9e1247d45a09e31e4a13ea1b88896ccadabff6ebe20a"
MAX_JSON_BYTES = 4 * 1024 * 1024
MARGIN_GATE = 0.025
CLUSTER_SPREAD_HZ = 10_000.0
PRIOR_HASHES = {
    "negative": "4ed264271cf5b6a81a16b45f165c03d5656f9582f85affefc17e907ac0effca9",
    "positive": "09f2063a69bbd7c953650d18c7849c3ecc424bd39e40ca5efd33fa4155ea9c1e",
}
PRIOR_INTERVALS = {"negative": (12_500_000, 20_500_000), "positive": (900_000_000, 908_000_000)}
CASES = (
    ("negative_later_1", "negative", 25_000_000, 33_000_000),
    ("negative_later_2", "negative", 37_500_000, 45_500_000),
    ("positive_later_1", "positive", 912_500_000, 920_500_000),
    ("positive_later_2", "positive", 925_000_000, 933_000_000),
)


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def encode(document: dict) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def write_new(path: Path, document: dict) -> None:
    payload = encode(document)
    with path.open("xb") as destination:
        destination.write(payload)


def output_directory(path: Path) -> Path:
    path = path.absolute()
    resolved = path.resolve(strict=False)
    require(path == resolved and resolved != CAPTURE and CAPTURE not in resolved.parents,
            "output must not alias or write inside the capture")
    return path


def read_json(path: Path) -> tuple[dict, bytes]:
    require(path.is_file() and path.stat().st_size <= MAX_JSON_BYTES, "missing/oversized JSON")
    with path.open("rb") as source:
        payload = source.read(MAX_JSON_BYTES + 1)
    require(len(payload) <= MAX_JSON_BYTES, "JSON grew beyond its bound")

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"nonfinite JSON: {value}")

    def number(value):
        result = float(value)
        require(math.isfinite(result), "nonfinite JSON number")
        return result

    document = json.loads(payload, object_pairs_hook=pairs, parse_constant=invalid, parse_float=number)
    require(type(document) is dict, "JSON root must be an object")
    return document, payload


def finite(value, field: str) -> float:
    require(type(value) in (float, int) and math.isfinite(value), f"invalid {field}")
    return float(value)


def select_prior(receipt: dict, episode: str) -> dict:
    """Enumerate every maximal complete-link cluster among three prior bests.

    Unsupported minority aliases remain observations, not silently de-aliased
    values. A unique supported cluster supplies a provisional primary frequency.
    A chain with two overlapping supported clusters abstains, rather than using
    greedy partition order to hide the ambiguity. No later evidence is accepted.
    """
    start, stop = PRIOR_INTERVALS[episode]
    origin = start * 3 // 5
    require(receipt["schema"] == "starlink-capture25-conditioned-pilot-crosscheck-v1"
            and receipt["status"] == "complete" and receipt["error"] is None,
            "prior is not a complete blind pilot receipt")
    require(receipt["pss_seeds_used"] is False and receipt["calibration_attached"] is False
            and receipt["pilot_saturation_events"] == 0 and receipt["pilot_samples"] == 800_000,
            "prior seeds, calibration, sample count or health mismatch")
    require(receipt["analysis_canonical_interval"] == [origin, stop * 3 // 5]
            and receipt["first_canonical_index"] == origin - 2952
            and receipt["group_delay_already_removed_canonical_samples"] == 269
            and receipt["declared_probe_offsets"] == [0, 250_000, 500_000], "prior source geometry mismatch")
    config = receipt["configuration"]
    require(config["residual_cfo_min_hz"] == -400_000 and config["residual_cfo_max_hz"] == 400_000,
            "prior acquisition CFO search mismatch")
    probes = receipt["probes"]
    require(type(probes) is list and len(probes) == 3, "exactly three prior probes required")
    accepted = []
    retained = []
    for index, probe in enumerate(probes):
        require(probe["pilot_offset"] == [0, 250_000, 500_000][index]
                and probe["sample_count"] == 50_000, "prior probe order/size mismatch")
        candidates = probe["candidates"]
        require(type(candidates) is list and len(candidates) <= 8, "unbounded prior candidates")
        for candidate in candidates:
            require(candidate["method"] == "glrt64", "prior method mismatch")
            finite(candidate["margin"], "margin")
            finite(candidate["tracking_cfo_hz"], "tracking CFO")
        best = max(candidates, key=lambda item: item["margin"], default=None)
        require(probe["best"] == best, "best candidate contradicts retained margins")
        passing = (probe["acquisition_status"] == "complete" and best is not None
                   and best["margin"] >= MARGIN_GATE)
        retained.append({"probe_index": index, "raw_probe": probe, "passes_prior_gate": passing})
        if passing:
            accepted.append({"probe_index": index, "cfo_hz": float(best["tracking_cfo_hz"]),
                             "margin": best["margin"]})
    subsets = []
    for count in range(1, len(accepted) + 1):
        for indexes in itertools.combinations(range(len(accepted)), count):
            values = [accepted[index]["cfo_hz"] for index in indexes]
            if max(values) - min(values) <= CLUSTER_SPREAD_HZ:
                subsets.append(frozenset(indexes))
    maximal = [subset for subset in subsets if not any(subset < other for other in subsets)]
    clusters = []
    for subset in sorted(maximal, key=lambda item: tuple(sorted(item))):
        members = [accepted[index] for index in sorted(subset)]
        values = sorted(item["cfo_hz"] for item in members)
        median = (values[(len(values) - 1) // 2] + values[len(values) // 2]) / 2
        clusters.append({"members": members, "distinct_probe_count": len(members),
                         "minimum_hz": values[0], "maximum_hz": values[-1],
                         "median_hz": median, "supported": len(members) >= 2})
    supported = [item for item in clusters if item["supported"]]
    selected = supported[0] if len(supported) == 1 else None
    if selected is not None:
        require(abs(selected["median_hz"]) < 7_500_000, "selected CFO outside canonical Nyquist")
    return {
        "status": "selected_provisional" if selected is not None else "abstained",
        "reason": ("unique supported complete-link cluster; minority aliases retained" if selected else
                   "competing supported clusters" if supported else "no two-probe supported cluster"),
        "selected_cfo_hz": selected["median_hz"] if selected is not None else None,
        "clusters": clusters, "probes": retained, "alias_identity_resolved": False,
        "calibrated_frequency": False,
        "prior_full_input_source_bounds": [start - 5000, stop + 5000],
        "prior_input_bounds_scope": "Conservative full halo admitted by the pinned derivative producer, not just winning-probe centers",
        "pilot_receipt_source_ci16_sha256": receipt["source_ci16_sha256"],
    }


def source_hashes() -> dict:
    paths = [Path(__file__), REPLAY, ROOT / "tools/starlink_capture25_condition.py",
             ROOT / "tools/starlink_pss_acquisition_study.py",
             ROOT / "hdl/library/starlink_pss_acquisition/tb/upper_edge_pss_kernel_q17.mem"]
    paths += sorted((ROOT / "tests/starlink_oracle").glob("*.py"))
    return {str(path.resolve(strict=True)): sha256(path.read_bytes()) for path in paths}


def build_plan() -> dict:
    priors = {}
    for episode in ("negative", "positive"):
        path = ROOT / f"reports/starlink-capture25-{episode}-pilot-20260909.json"
        receipt, payload = read_json(path)
        require(sha256(payload) == PRIOR_HASHES[episode], "pinned blind prior changed")
        priors[episode] = {"path": str(path), "sha256": sha256(payload),
                           "decision": select_prior(receipt, episode)}
    cases = []
    for name, episode, start, stop in CASES:
        prior = priors[episode]["decision"]
        gap = start - 5000 - prior["prior_full_input_source_bounds"][1]
        require(gap > 0 and stop - start == 8_000_000, "prior/held-out input envelopes overlap")
        cases.append({"name": name, "episode": episode, "source_bounds": [start, stop],
                      "loaded_source_halo_bounds": [start - 5000, stop + 5000],
                      "gap_after_prior_full_input_samples": gap,
                      "gap_after_prior_full_input_seconds": gap / 25_000_000,
                      "age_of_prior_analysis_end_at_window_start_seconds":
                          (start - PRIOR_INTERVALS[episode][1]) / 25_000_000,
                      "primary_cfo_hz": prior["selected_cfo_hz"], "baseline_always_retained": True,
                      "primary_status": prior["status"]})
    return {
        "schema": "starlink-capture25-causal-study-plan-v1", "manifest_sha256": MANIFEST_HASH,
        "capture_id": "cap-20260909T121248-414fb81f488c", "stream_id": "stream-1",
        "radio_serial": "10400056f695001322002d0010ad1719f2", "hardware_access": False,
        "case_selection": "Predeclared evidence-selected episodes; later PSS inputs not used to select CFO",
        "cfo_policy": {"prior_best_margin_minimum": MARGIN_GATE, "complete_link_maximum_spread_hz": CLUSTER_SPREAD_HZ,
                       "minimum_distinct_probes": 2, "multiple_supported_clusters": "abstain",
                       "unsupported_aliases": "retain without claiming resolved identity",
                       "future_or_same_window_saved_glrt_used": False, "alternative_later_pss_fitting": False},
        "online_latency_qualified": False,
        "prior_acquisition_processing_seconds": None,
        "prior_acquisition_latency_status": "Not retained/measured; no deadline inference from source order",
        "selected_frequency_uses_earlier_source_inputs_only": True,
        "source_order_is_not_compute_deadline_proof": True,
        "native_25msps_hardware_qualified": False, "timing_lock_proven": False,
        "priors": priors, "cases": cases, "sources": source_hashes(),
        "adapter": "Private instance of frozen replay helper; only explicit WINDOWS configuration differs. No coefficients, model, clocks, arithmetic, gates or originals edited.",
    }


def private_replay(plan: dict):
    """Do not mutate the ordinary imported helper's global window table."""
    require(sha256(REPLAY.read_bytes()) == plan["sources"][str(REPLAY)], "replay source changed")
    spec = importlib.util.spec_from_file_location("_capture25_causal_private_replay", REPLAY)
    require(spec is not None and spec.loader is not None, "cannot load frozen replay helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.WINDOWS = {item["name"]: tuple(item["source_bounds"]) for item in plan["cases"]}
    return module


def run_plan(path: Path) -> int:
    plan, payload = read_json(path)
    require(encode(build_plan()) == payload, "plan or source/prior pins changed since predeclaration")
    output = output_directory(path.absolute().parent)
    start = time.monotonic()
    write_new(output / "execution-start.json", {"plan_sha256": sha256(payload),
                                               "online_latency_qualified": False})
    report = {"schema": "starlink-capture25-causal-study-result-v1", "status": "failed", "error": None,
              "plan_path": str(path.resolve()), "plan_sha256": sha256(payload), "cases": [],
              "hardware_access": False, "online_latency_qualified": False,
              "timing_lock_proven": False, "native_25msps_hardware_qualified": False}
    try:
        replay = private_replay(plan)
        for case in plan["cases"]:
            require(source_hashes() == plan["sources"], "sources changed before held-out replay")
            directory = output / case["name"]
            report["case_in_progress"] = {"name": case["name"], "output_directory": str(directory)}
            began = time.monotonic()
            code = replay.run(case["name"], directory, case["primary_cfo_hz"])
            child, raw = read_json(directory / "report.json")
            result = {"name": case["name"], "primary_frequency_status": case["primary_status"],
                      "primary_cfo_hz": case["primary_cfo_hz"], "return_code": code,
                      "host_processing_seconds": time.monotonic() - began,
                      "online_latency_qualified": False,
                      "report": {"path": str(directory / "report.json"), "sha256": sha256(raw)},
                      "status": child["status"], "primary_pss_candidate_qualified": None,
                      "primary_pss_status": "not_attempted_prior_abstained" if case["primary_cfo_hz"] is None else "attempted",
                      "variants": [{"name": item["name"], "numerical_qualification_pass": item["numerical_qualification_pass"],
                                    "three_map_candidate_qualified": item["three_map_candidate_qualified"],
                                    "maps": item["maps"], "negative_control": item["negative_control"]}
                                   for item in child["variants"]]}
            report["cases"].append(result)
            report.pop("case_in_progress")
            require(code == 0 and child["status"] == "REPLAY_COMPLETE", "held-out numerical replay failed")
            expected = ["baseline"] + (["assisted"] if case["primary_cfo_hz"] is not None else [])
            require([item["name"] for item in child["variants"]] == expected, "unexpected replay variants")
            if case["primary_cfo_hz"] is not None:
                primary = child["variants"][1]
                control_passes = primary["negative_control"]["maps"]["three_map_existing_epoch_gates_pass"]
                result["primary_scrambled_control_passes_existing_gates"] = control_passes
                result["primary_pss_candidate_qualified"] = (
                    primary["three_map_candidate_qualified"] and not control_passes)
        require(source_hashes() == plan["sources"], "sources changed during held-out analysis")
        report["status"] = "complete"
    except BaseException as error:
        report["error"] = {"type": type(error).__name__, "repr": repr(error)[:4000]}
        report["host_processing_seconds"] = time.monotonic() - start
        write_new(output / "study-result.json", report)
        raise
    report["host_processing_seconds"] = time.monotonic() - start
    write_new(output / "study-result.json", report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    prepare = actions.add_parser("plan", help="freeze priors/windows/policy before any held-out IQ read")
    prepare.add_argument("--output", required=True, type=Path, help="new directory with existing parent")
    execute = actions.add_parser("run", help="run the exact frozen plan; never overwrites a prior execution")
    execute.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.action == "run":
        return run_plan(args.plan)
    args.output = output_directory(args.output)
    require(args.output.parent.is_dir(), "output parent must already exist")
    plan = build_plan()
    args.output.mkdir(exist_ok=False)
    write_new(args.output / "plan.json", plan)
    print(json.dumps({"plan_path": str((args.output / "plan.json").resolve()),
                      "plan_sha256": sha256(encode(plan)),
                      "decisions": {key: value["decision"]["status"] for key, value in plan["priors"].items()}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
