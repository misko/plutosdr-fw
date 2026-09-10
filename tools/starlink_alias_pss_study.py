"""Frozen prior aliases versus exact one-map PSS: offline, never RF truth.

One 64-frame map uses the existing Q17 vendor arithmetic, kernel, score and map
contract. Applying the existing scalar thresholds to only one map is explicitly
exploratory: the three-map production qualification always remains unavailable.
"""

from __future__ import annotations

import argparse
import platform
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.starlink_oracle import projected_pss, quantize_q15, xfft_bitacc
from tools import starlink_capture25_causal_study as causal
from tools import starlink_capture25_pss_replay as replay
from tools import starlink_narrow_coarse_study as narrow
from tools.starlink_pss_acquisition_study import _scramble_complete_frames

SCORES = 64 * 20_000
HALO = 600
PROBE_OFFSETS = (0, 300_000, 600_000, 900_000, 980_000)
NOISE_SEED = 2026091002


def prior_branches(receipt: dict, episode: str) -> dict:
    decision = causal.select_prior(receipt, episode)
    # The frozen three-probe receipts have only one passing candidate per
    # probe. Refuse unexpected extra aliases instead of silently discarding.
    for probe in receipt["probes"]:
        passing = [row for row in probe["candidates"] if row["margin"] >= causal.MARGIN_GATE]
        if len(passing) > 1:
            raise ValueError("prior now has multiple passing candidates: new policy required")
    branches = [{"name": "baseline", "cfo_hz": 0., "kind": "uncorrected_baseline"}]
    for index, cluster in enumerate(decision["clusters"]):
        branches.append({"name": f"prior_alias_{index}", "cfo_hz": cluster["median_hz"],
                         "kind": "supported_prior_cluster" if cluster["supported"] else "minority_prior_alias",
                         "cluster": cluster})
    return {"decision": decision, "branches": branches, "alias_identity_resolved": False}


def source_bounds(first: int, count: int) -> dict:
    if count <= 0:
        raise ValueError("source span must be positive")
    # Exact dependency coordinates of the existing centered 481-tap /5
    # conditioner on its 75 MHz lattice: +/-240 high-rate ticks.
    original_start = (5 * first - 240 + 2) // 3
    original_stop = (5 * (first + count - 1) + 240) // 3 + 1
    return {"canonical_bounds": [first, first + count],
            "original25_full_support_bounds": [original_start, original_stop],
            "original25_support_seconds": (original_stop - original_start) / 25_000_000}


def read_input(case: dict) -> np.ndarray:
    if case["kind"] == "known_noise":
        rng = np.random.default_rng(NOISE_SEED)
        raw = np.rint(1500 * rng.standard_normal((SCORES + 2 * HALO, 2)))
        if np.any(abs(raw) > 32767):
            raise ValueError("synthetic noise unexpectedly clipped")
        samples = raw.astype("<i2")
    else:
        offset = case["canonical_start"] - HALO - case["file_first_canonical_index"]
        count = SCORES + 2 * HALO
        path = Path(case["path"])
        if offset < 0 or (offset + count) * 4 > path.stat().st_size:
            raise ValueError("source lacks complete real halos")
        with path.open("rb") as stream:
            stream.seek(offset * 4)
            payload = stream.read(count * 4)
        if len(payload) != count * 4:
            raise ValueError("bounded source read changed size")
        samples = np.frombuffer(payload, dtype="<i2").reshape(-1, 2)
    if "input_sha256" in case and narrow.sha(samples.tobytes()) != case["input_sha256"]:
        raise ValueError("predeclared source bytes changed")
    return samples


def score_prefix(path: Path) -> bytes:
    with path.open("rb") as stream:
        payload = stream.read(SCORES)
    if len(payload) != SCORES:
        raise ValueError("frozen numerical prefix is incomplete")
    return payload


def build_plan(evidence_root: Path, leo_root: Path) -> dict:
    # These policy choices precede reading later IQ, map/score products or GLRT.
    plan = {
        "schema": "starlink-prior-alias-one-map-plan-v1",
        "acceptance": {
            "alias_source": "Only complete-link clusters of earlier retained blind pilot bests",
            "retain_minority_clusters": True, "prior_margin_minimum": .025,
            "one_map_robust_z_minimum": 6., "one_map_peak_to_median_minimum": 1.15,
            "one_map_threshold_application": "Exploratory; not production qualification or same false-alarm behavior",
            "production_required_maps": 3, "available_maps": 1,
            "production_handoff_status": "insufficient_integration",
            "one_map_alias_consistency": "Exactly one prior alias passes and every scrambled branch fails; otherwise abstain",
            "alias_identity_resolved": False,
            "independent_glrt_margin_strictly_greater_than": .025,
            "require_frozen_baseline_and_primary_score_prefix_equality": True,
            "require_zero_model_overflow_and_derotation_saturation": True,
            "maximum_source_support_seconds": .120,
        },
        "score_count": SCORES, "map_frames": 64, "phase_bin_samples": 1,
        "nominal_pss_score_seconds": SCORES / 15_000_000,
        "blind_glrt_probe_offsets_canonical": list(PROBE_OFFSETS),
        "blind_glrt_probes_overlap_not_independent_replicates": True,
        "blind_glrt_canonical_center_union": [0, SCORES],
        "later_glrt_or_pss_used_to_select_aliases": False,
        "noise_seed": NOISE_SEED,
        "evidence_root": str(evidence_root), "leo_root": str(leo_root),
        "priors": {}, "cases": [], "source_hashes": {},
        "cmodel_archive_sha256": xfft_bitacc.INSTALLED_CMODEL_SHA256,
    }
    files = [Path(__file__), Path(narrow.__file__), Path(causal.__file__), Path(replay.__file__),
             ROOT / "tools/starlink_pss_acquisition_study.py", replay.KERNEL,
             ROOT / "tests/starlink_oracle/pilot_ddc.py"]
    files += [ROOT / "tests/starlink_oracle" / f"{name}.py"
              for name in ("__init__", "acquisition", "fixed", "numerology", "waveforms", "xfft_bitacc")]
    files += [leo_root / "src/leo/analysis/starlink" / f"{name}.py"
              for name in ("templates", "acquisition", "pilot_methods")]
    for episode in ("negative", "positive"):
        path = evidence_root / f"reports/starlink-capture25-{episode}-pilot-20260909.json"
        receipt, payload = causal.read_json(path)
        if narrow.sha(payload) != causal.PRIOR_HASHES[episode]:
            raise ValueError("earlier prior identity changed")
        plan["priors"][episode] = prior_branches(receipt, episode)
        files.append(path)
    directory = evidence_root / "hdl/library/starlink_pss_acquisition/build/capture25-causal-heldout-v1"
    for name, episode, source_start, _ in causal.CASES:
        path = directory / name / "report.json"
        receipt, _ = causal.read_json(path)
        files.append(path)
        first = source_start * 3 // 5
        prior = plan["priors"][episode]
        full_support = source_bounds(first - HALO, SCORES + 2 * HALO)
        if full_support["original25_support_seconds"] > .120:
            raise ValueError("source envelope exceeds declared dwell")
        if full_support["original25_full_support_bounds"][0] <= prior["decision"]["prior_full_input_source_bounds"][1]:
            raise ValueError("prior and held-out source envelopes overlap")
        case = {"name": name, "kind": "recorded_unknown_truth", "historical_episode_label": episode,
                "canonical_start": first,
                "path": str(directory / name / "conditioned-15msps.ci16"),
                "file_first_canonical_index": receipt["conditioning"]["first_canonical_index"],
                "prior_full_original25_source_bounds": prior["decision"]["prior_full_input_source_bounds"],
                "branches": prior["branches"], "frozen_prefixes": {}, "shared_read_support": full_support,
                "conditioning_saturations": receipt["conditioning"]["clipped_components"]}
        if case["conditioning_saturations"]:
            raise ValueError("previous conditioning clipped")
        for branch in case["branches"]:
            previous = "baseline" if branch["name"] == "baseline" else (
                "assisted" if branch["cfo_hz"] == prior["decision"]["selected_cfo_hz"] else None)
            if previous is not None:
                file = directory / name / f"{previous}.scores.u8"
                case["frozen_prefixes"][branch["name"]] = {
                    "path": str(file), "sha256": narrow.sha(score_prefix(file)), "bytes": SCORES}
        case["input_sha256"] = narrow.sha(read_input(case).tobytes())
        plan["cases"].append(case)
    noise = {"name": "known_noise", "kind": "known_noise", "canonical_start": 20_000,
             "branches": plan["priors"]["positive"]["branches"], "frozen_prefixes": {},
             "conditioning_saturations": 0, "synthetic_not_causal_rf_observation": True}
    noise["input_sha256"] = narrow.sha(read_input(noise).tobytes())
    plan["cases"].append(noise)
    plan["source_hashes"] = {str(path.resolve()): narrow.sha(path.read_bytes()) for path in files}
    return plan


def branch_result(iq: np.ndarray, case: dict, branch: dict, model, coefficients: np.ndarray,
                  kernel: dict, output: Path) -> dict:
    started = time.perf_counter()
    blocks, count = replay.fft_geometry(SCORES)
    raw = iq[HALO:HALO + count]
    if len(raw) != count:
        raise ValueError("FFT lacks complete unpadded input")
    corrected, clips = replay.derotate_ci16(raw, case["canonical_start"], branch["cfo_hz"])
    result = xfft_bitacc.xfft_bitacc_match_scores(
        corrected, coefficients, model, first_sample_index=case["canonical_start"])
    if (result.block_count != blocks or len(result.stream.scores) != blocks * 447
            or result.kernel_sha256 != kernel["int32le_sha256"]):
        raise ValueError("frozen kernel or whole-block score contract mismatch")
    if result.forward_overflow_blocks or result.inverse_overflow_blocks or result.product_overflow_blocks or clips:
        raise ValueError("arithmetic overflow or derotation clipping")
    stream = replace(result.stream, scores=result.stream.scores[:SCORES])
    if np.any(stream.scores > 255):
        raise ValueError("score exceeds frozen u8 contract")
    payload = stream.scores.astype("u1").tobytes()
    previous = case["frozen_prefixes"].get(branch["name"])
    if previous is not None and narrow.sha(payload) != previous["sha256"]:
        raise ValueError("score prefix differs from frozen prior replay")
    maps = replay.describe_maps(stream, output, branch["name"], required_maps=1)
    scrambled = replay.describe_maps(_scramble_complete_frames(stream, seed=0xCA250017), output,
                                     branch["name"] + ".frame-scrambled", required_maps=1)
    return {
        "branch": branch, "score_sha256": narrow.sha(payload), "score_count": SCORES,
        "frozen_score_prefix_bit_identical": True if previous is not None else None,
        "input_ci16_sha256_before_correction": narrow.sha(raw.tobytes()),
        "corrected_input_ci16_sha256": narrow.sha(corrected.tobytes()),
        "full_fft_source_support": source_bounds(case["canonical_start"], count),
        "map": maps, "scrambled_control": scrambled,
        "numerical_qualification_pass": True, "model_overflow_blocks": 0,
        "derotation_saturations": clips, "offline_processing_seconds": time.perf_counter() - started,
        "one_map_exploratory_candidate": maps["combined_candidate"]["passes_existing_epoch_gates"],
        "production_status": "insufficient_integration", "rf_truth": False,
    }


def summarize_aliases(branches: list[dict]) -> dict:
    admitted = [row["branch"]["name"] for row in branches
                if row["branch"]["kind"] != "uncorrected_baseline" and row["one_map_exploratory_candidate"]]
    bad_controls = [row["branch"]["name"] for row in branches
                    if row["scrambled_control"]["combined_candidate"]["passes_existing_epoch_gates"]]
    status = ("no_prior_aliases" if len(branches) == 1 else
              "one_map_consistent_with_one_prior_alias" if len(admitted) == 1 and not bad_controls else
              "competing_alias_candidates" if len(admitted) > 1 else
              "control_failed" if bad_controls else "no_alias_candidate")
    return {"exploratory_status": status, "passing_aliases": admitted,
            "passing_scrambled_controls": bad_controls, "alias_identity_resolved": False,
            "production_handoff_status": "insufficient_integration",
            "available_maps": 1, "required_maps": 3,
            "production_lock_or_false_alarm_behavior_qualified": False}


def pilot_probes(iq: np.ndarray, case: dict, modules: dict) -> list[dict]:
    rows = []
    for offset in PROBE_OFFSETS:
        values, centers, filtered = narrow.filter_probe(
            iq[offset:offset + narrow.PROBE_SAMPLES + 2 * HALO],
            case["canonical_start"] - HALO + offset,
            case["canonical_start"] + offset, edge="upper")
        result = narrow.blind(values, "upper", modules)
        best = result["best"]
        admitted = best is not None and best["margin"] > .025
        rows.append({
            "offset_canonical": offset, "filter": filtered, "blind_search": result,
            "classification": "pilot_candidate_coverage_estimated" if admitted else "no_candidate_coverage_unknown",
            "coverage_known": False, "pss_seeds_used": False, "prior_correction_applied": False,
            "first_pilot_canonical_center": int(centers[0]), "last_pilot_canonical_center": int(centers[-1]),
            "original25_input_support": source_bounds(case["canonical_start"] - HALO + offset,
                                                       narrow.PROBE_SAMPLES + 2 * HALO),
            "candidate_phase_us": None if best is None else
                ((int(centers[0]) + 6 * best["epoch_sample"]) % 20_000) / 15,
        })
    return rows


def run(path: Path) -> None:
    plan, payload = causal.read_json(path)
    if narrow.encode(build_plan(Path(plan["evidence_root"]), Path(plan["leo_root"]))) != payload:
        raise ValueError("plan, source or held-out bytes changed")
    narrow.write_new(path.parent / "execution-start.json", {"plan_sha256": narrow.sha(payload)})
    modules, native = narrow.load_leo(Path(plan["leo_root"]))
    result = {"schema": "starlink-prior-alias-one-map-result-v1", "plan_sha256": narrow.sha(payload),
              "cases": [], "host": {"node": platform.node(), "platform": platform.platform(),
                                    "python": sys.version, "executable": sys.executable, "numpy": np.__version__},
              "native_acquisition_backend": native, "rf_truth": False, "online_deadline_qualified": False,
              "production_handoff_status": "insufficient_integration"}
    cmodel_path = ROOT / "build" / path.parent.name / "cmodel"
    cmodel_path.parent.mkdir(parents=True, exist_ok=True)
    directory = xfft_bitacc.prepare_installed_cmodel(cmodel_path)
    result["cmodel"] = {"archive_sha256": xfft_bitacc.INSTALLED_CMODEL_SHA256,
                        "data_bits": 18, "fraction_bits": 17, "fft_samples": 512,
                        "arithmetic_not_realtime_core_protocol": True}
    coefficients = quantize_q15(projected_pss(15_000_000, "upper"))
    started = time.perf_counter()
    with replay.model_q17(directory) as model:
        kernel = replay.check_kernel(model, coefficients)
        result["kernel"] = kernel
        for case in plan["cases"]:
            iq = read_input(case)
            output = path.parent / case["name"]
            output.mkdir(exist_ok=False)
            row = {"case": case, "branches": [], "pilot_probes": []}
            for branch in case["branches"]:
                print(f"PSS {case['name']} {branch['name']} cfo={branch['cfo_hz']}", flush=True)
                measured = branch_result(iq, case, branch, model, coefficients, kernel, output)
                narrow.write_new(output / f"{branch['name']}.json", measured)
                row["branches"].append(measured)
            row["alias_summary"] = summarize_aliases(row["branches"])
            row["pilot_probes"] = pilot_probes(iq, case, modules)
            narrow.write_new(output / "case-result.json", row)
            result["cases"].append(row)
            print(f"CASE {case['name']} {row['alias_summary']['exploratory_status']}", flush=True)
    result["total_offline_seconds"] = time.perf_counter() - started
    result["numerical_qualification_pass"] = all(
        branch["numerical_qualification_pass"] for case in result["cases"] for branch in case["branches"])
    narrow.write_new(path.parent / "study-result.json", result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("plan")
    freeze.add_argument("--evidence-root", type=Path, required=True)
    freeze.add_argument("--leo-root", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    execute = commands.add_parser("run")
    execute.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args(argv)
    target = (args.output if args.command == "plan" else args.plan).resolve()
    if ROOT not in target.parents:
        parser.error("artifacts must stay inside this assigned firmware worktree")
    if args.command == "plan":
        plan = build_plan(args.evidence_root.resolve(), args.leo_root.resolve())
        target.mkdir(parents=True, exist_ok=False)
        narrow.write_new(target / "plan.json", plan)
        print(target / "plan.json")
    else:
        run(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
