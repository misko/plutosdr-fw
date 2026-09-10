"""Predeclared offline pilot-coarse feasibility; no radio or production changes.

The plan pins bounded input probes before evaluation. The actual fixed CI16
pilot DDC feeds blind acquisition/GLRT; neither later PSS maps nor saved GLRT
epochs seed that search. An earlier blind-pilot receipt may supply only a
pre-filter frequency correction, explicitly separate from residual CFO.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import platform
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.starlink_oracle import pilot_ddc as ddc
from tests.starlink_oracle.waveforms import projected_pss
from tools import starlink_capture25_causal_study as causal

RATE = 15_000_000
OUTPUT_RATE = 2_500_000
PROBE_SAMPLES = 300_000
HALO = 600
PILOT_CARRIERS = (np.arange(8) - 3.5) * 234_375
PRIOR = 285_941.79442491336
CASES = tuple((edge, cfo, correction, kind)
              for edge in ("lower", "upper")
              for cfo, correction, kind in (
                  (0., 0., "positive"), (250_000., 0., "positive"),
                  (400_000., 0., "positive"), (1_200_000., 0., "positive"),
                  (1_200_000., 1_200_000., "positive"), (0., 0., "noise")))


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def encode(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def write_new(path: Path, value: dict) -> None:
    with path.open("xb") as stream:
        stream.write(encode(value))


def coverage(residual_hz: float) -> dict:
    if not math.isfinite(residual_hz):
        raise ValueError("CFO must be finite")
    frequencies = PILOT_CARRIERS + residual_hz
    count = int(np.count_nonzero(np.abs(frequencies) <= ddc.PASSBAND_EDGE_HZ))
    return {
        "residual_cfo_hz": residual_hz,
        "carrier_frequencies_after_mixing_hz": frequencies.tolist(),
        "passband_carrier_count": count,
        "stopband_carrier_count": int(np.count_nonzero(np.abs(frequencies) >= ddc.STOPBAND_EDGE_HZ)),
        "status": "nominal_carriers_supported" if count == 8 else "unobservable_full_pilot_contract",
        "modulated_sidelobes_fully_preserved": False,
    }


def budget(processing_seconds: float, *, input_seconds: float = .020,
           transport_seconds: float = 0., command_seconds: float = 0.,
           frames_after_handoff: int = 1) -> dict:
    if any(not math.isfinite(x) or x < 0 for x in
           (processing_seconds, input_seconds, transport_seconds, command_seconds)):
        raise ValueError("latency components must be finite and nonnegative")
    if type(frames_after_handoff) is not int or frames_after_handoff < 1:
        raise ValueError("positive fine frame count required")
    arrival = input_seconds + ddc.GROUP_DELAY_INPUT_SAMPLES / RATE
    available = arrival + processing_seconds + transport_seconds + command_seconds
    finish = available + frames_after_handoff / 750
    return {
        "input_seconds": input_seconds, "measured_processing_seconds": processing_seconds,
        "transport_seconds_assumed": transport_seconds, "command_seconds_assumed": command_seconds,
        "pilot_group_delay_seconds": ddc.GROUP_DELAY_INPUT_SAMPLES / RATE,
        "earliest_handoff_seconds": available,
        "earliest_next_fine_frame_complete_seconds": finish,
        "fits_120ms_with_supplied_latencies": finish <= .120,
        "full_60msps_ci16_retrospective_ring_bytes": math.ceil(available * 60_000_000) * 4,
        "pilot_ci16_pending_bytes": math.ceil(available * OUTPUT_RATE) * 4,
        "transport_and_command_measured": False,
        "zynq_or_arm_realtime_qualified": False,
    }


def read_probe(item: dict) -> tuple[np.ndarray, int, bytes]:
    path = Path(item["path"])
    first = item["center_start"] - HALO
    offset = first - item["file_first_canonical_index"]
    count = PROBE_SAMPLES + 2 * HALO
    if offset < 0 or (offset + count) * 4 > path.stat().st_size:
        raise ValueError("probe lacks real source halos")
    with path.open("rb") as stream:
        stream.seek(offset * 4)
        payload = stream.read(count * 4)
    if len(payload) != count * 4:
        raise ValueError("bounded probe changed size")
    if "probe_sha256" in item and sha(payload) != item["probe_sha256"]:
        raise ValueError("planned probe bytes changed")
    return np.frombuffer(payload, dtype="<i2").reshape(-1, 2), first, payload


def build_plan(evidence_root: Path, leo_root: Path) -> dict:
    # Criteria are fixed here before reading any probe bytes or candidate scores.
    plan = {
        "schema": "starlink-narrow-coarse-plan-v1",
        "acceptance": {
            "known_supported_positive_margin_strictly_greater_than": .15,
            "known_positive_abs_epoch_error_output_samples_strictly_less_than": 3,
            "known_positive_abs_cfo_error_hz_strictly_less_than": 1000,
            "synthetic_noise_margin_strictly_less_than": .025,
            "heldout_candidate_margin_strictly_greater_than": .025,
            "heldout_candidates_are_not_rf_truth": True,
            "outside_all_carriers_passband": "diagnostic_only_unobservable_full_pilot_contract",
            "saturation_events_required": 0,
            "short_dwell_budget_seconds": .120,
            "qualify_online_if_transport_or_command_unmeasured": False,
            "weak_signal_detection_probability_or_false_alarm_rate_claim": False,
        },
        "synthetic_cases": [{"edge": e, "injected_cfo_hz": c, "applied_prefilter_correction_hz": a, "kind": k}
                            for e, c, a, k in CASES],
        "synthetic_seed": 20260910, "synthetic_epoch_canonical": 10_003,
        "synthetic_pilot_amplitude": 6000, "synthetic_noise_std_per_component": 1500,
        "synthetic_retuned_1200khz_case": "Known-truth coverage demonstration, not causal acquisition",
        "search_residual_domain_hz": [-400_000, 400_000],
        "pss_timing_or_frequency_seeds_used": False,
        "heldout_selection": "First fixed 20ms of four already evidence-selected later windows",
        "input_probe_complex_samples_including_halos": PROBE_SAMPLES + 2 * HALO,
        "python_and_host_not_target_arm": True,
        "evidence_root": str(evidence_root.resolve()), "leo_root": str(leo_root.resolve()),
        "source_hashes": {}, "probes": [],
    }
    files = [Path(__file__), ROOT / "tests/starlink_oracle/pilot_ddc.py",
             ROOT / "tests/starlink_oracle/waveforms.py", ROOT / "tools/starlink_capture25_causal_study.py"]
    files += [leo_root / "src/leo/analysis/starlink" / f"{name}.py"
              for name in ("templates", "acquisition", "pilot_methods")]
    for episode in ("negative", "positive"):
        receipt_path = evidence_root / f"reports/starlink-capture25-{episode}-pilot-20260909.json"
        receipt, raw = causal.read_json(receipt_path)
        if sha(raw) != causal.PRIOR_HASHES[episode]:
            raise ValueError("historical prior receipt differs from frozen study")
        decision = causal.select_prior(receipt, episode)
        plan[f"{episode}_prior"] = decision
        files.append(receipt_path)
        if episode == "positive":
            if decision["selected_cfo_hz"] != PRIOR:
                raise ValueError("prior selection changed")
            for index, offset in enumerate((0, 1_500_000, 3_000_000)):
                plan["probes"].append({
                    "name": f"positive_prior_{index}", "role": "prior_runtime_repeat",
                    "path": receipt["source_ci16"],
                    "file_first_canonical_index": receipt["first_canonical_index"],
                    "center_start": receipt["analysis_canonical_interval"][0] + offset,
                    "applied_prefilter_correction_hz": 0.,
                })
    directory = evidence_root / "hdl/library/starlink_pss_acquisition/build/capture25-causal-heldout-v1"
    for name, episode, start, _ in causal.CASES:
        receipt_path = directory / name / "report.json"
        receipt, _ = causal.read_json(receipt_path)
        files.append(receipt_path)
        for applied in ((0., PRIOR) if episode == "positive" else (0.,)):
            plan["probes"].append({
                "name": name + ("_prior_corrected" if applied else "_uncorrected"),
                "role": "heldout", "historical_episode_label_not_truth": episode,
                "path": str(directory / name / "conditioned-15msps.ci16"),
                "file_first_canonical_index": receipt["conditioning"]["first_canonical_index"],
                "center_start": start * 3 // 5,
                "applied_prefilter_correction_hz": applied,
                "prior_full_original25_source_bounds": plan[f"{episode}_prior"]["prior_full_input_source_bounds"],
                "historical_pss_report": str(receipt_path),
            })
    for item in plan["probes"]:
        _, first, payload = read_probe(item)
        item.update(probe_sha256=sha(payload), input_canonical_bounds=[first, first + len(payload) // 4],
                    byte_count_read=len(payload))
    plan["source_hashes"] = {str(p.resolve()): sha(p.read_bytes()) for p in files}
    return plan


def filter_probe(iq: np.ndarray, first: int, center_start: int, *, edge: str,
                 correction_hz: float = 0.) -> tuple[np.ndarray, np.ndarray, dict]:
    started = time.perf_counter()
    corrections_clipped = 0
    if correction_hz:
        # Constant initial phase is irrelevant to GLRT; relative indexes avoid
        # large floating oscillator arguments and preserve continuous phase.
        phase = -2j * np.pi * correction_hz * np.arange(len(iq)) / RATE
        raw = (iq[:, 0].astype(float) + 1j * iq[:, 1]) * np.exp(phase)
        rounded = np.rint(np.column_stack((raw.real, raw.imag)))
        corrections_clipped = int(np.count_nonzero((rounded < -32768) | (rounded > 32767)))
        iq = np.clip(rounded, -32768, 32767).astype(np.int16)
    result = ddc.PilotDdcOracle(edge).process(iq, first_index=first)
    centers = result.accepted_input_indexes.astype(np.int64) - ddc.GROUP_DELAY_INPUT_SAMPLES
    take = result.support_valid & (centers >= center_start) & (centers < center_start + PROBE_SAMPLES)
    values = result.samples_iq[take]
    centers = centers[take]
    if len(values) != 50_000 or not np.all(np.diff(centers) == 6):
        raise ValueError("pilot is not exactly 20ms of supported contiguous samples")
    return values[:, 0].astype(float) + 1j * values[:, 1], centers, {
        "fixed_ddc_processing_seconds": time.perf_counter() - started,
        "applied_prefilter_correction_hz": correction_hz,
        "pre_filter_correction_saturations": corrections_clipped,
        "ddc_saturations": result.saturation_events,
        "supported_pilot_sha256": sha(values.astype("<i2").tobytes()),
        "first_pilot_canonical_center": int(centers[0]),
        "last_pilot_canonical_center": int(centers[-1]),
        "pilot_samples": len(values),
    }


def load_leo(root: Path) -> tuple[dict, dict]:
    sys.path.insert(0, str(root / "src"))
    modules = {name: importlib.import_module(f"leo.analysis.starlink.{name}")
               for name in ("templates", "acquisition", "pilot_methods")}
    loaded = {}
    for name, module in modules.items():
        expected = (root / "src/leo/analysis/starlink" / f"{name}.py").resolve()
        if Path(module.__file__).resolve() != expected:
            raise ValueError("loaded Leo source disagrees with plan")
    for name, module in tuple(sys.modules.items()):
        path = getattr(module, "__file__", None)
        if name.startswith("leo.") and path and path.endswith((".so", ".pyd")):
            loaded[name] = {"path": path, "sha256": sha(Path(path).read_bytes())}
    return modules, loaded


def blind(values: np.ndarray, edge: str, modules: dict) -> dict:
    acquisition = modules["acquisition"]
    config = acquisition.SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=-400_000, residual_cfo_max_hz=400_000,
        retained_candidate_count=8, candidate_epoch_separation_samples=20,
        candidate_cfo_separation_hz=80_000)
    started = time.perf_counter()
    result = acquisition.acquire_symbolwise(
        values, OUTPUT_RATE,
        acquisition.ReceiverFrequencyCalibration("offline-uncalibrated-narrow-study", 0, "0" * 64),
        edge=edge, config=config)
    acquisition_seconds = time.perf_counter() - started
    started = time.perf_counter()
    scores = modules["pilot_methods"].conditioned_glrt64_scores(
        values, OUTPUT_RATE, edge=edge,
        epoch_samples=[candidate.refined_epoch_sample for candidate in result.candidates],
        acquired_cfo_hz=[candidate.absolute_cfo_hz for candidate in result.candidates])
    glrt_seconds = time.perf_counter() - started
    candidates = [dict(epoch_sample=int(candidate.refined_epoch_sample),
                       acquired_residual_cfo_hz=float(candidate.absolute_cfo_hz), **asdict(score))
                  for candidate, score in zip(result.candidates, scores, strict=True)]
    return {
        "status": str(result.status), "configuration": asdict(config),
        "acquisition_seconds": acquisition_seconds, "glrt_seconds": glrt_seconds,
        "total_search_seconds": acquisition_seconds + glrt_seconds,
        "best": max(candidates, key=lambda x: x["margin"], default=None),
        "candidates": candidates, "pss_seeds_used": False,
    }


def spectrum_study() -> dict:
    # Linear frozen-FIR spectrum is an information-loss diagnostic. It does
    # not assert a new matched filter is numerically equal to frozen FPGA PSS.
    expanded = np.zeros(509)
    expanded[::2] = ddc.coefficients(255) / 2**17
    impulse = np.convolve(ddc.coefficients(31) / 2**17, expanded)
    nfft = 65536
    frequencies = np.fft.fftfreq(nfft, 1 / RATE)
    response = np.fft.fft(impulse, nfft)
    rows = []
    for edge in ("lower", "upper"):
        template = projected_pss(RATE, edge)
        center = ddc.MIXER_STEP_64[edge] * RATE / 64
        for cfo in (0., PRIOR, 1_200_000., -1_200_000.):
            canonical = template * np.exp(2j * np.pi * cfo * np.arange(len(template)) / RATE)
            canonical_energy = abs(np.fft.fft(canonical, nfft))**2
            mixed = template * np.exp(2j * np.pi * (cfo - center) * np.arange(len(template)) / RATE)
            energy = abs(np.fft.fft(mixed, nfft))**2
            filtered = energy * abs(response)**2
            retained = float(np.sum(filtered) / np.sum(energy))
            # Ideal white-noise band-selection bound; excludes alias, colored
            # covariance, nuisance CFO/channel, finite SNR and multipath.
            selected = energy * (abs(frequencies) <= ddc.PASSBAND_EDGE_HZ)
            def timing_information(weights):
                mean = np.sum(weights * frequencies) / np.sum(weights)
                return float(np.sum(weights * (frequencies - mean)**2))
            rows.append({
                "edge": edge, "uncorrected_cfo_hz": cfo,
                "pss_energy_after_filter_fraction": retained,
                "pss_energy_after_filter_db": 10 * math.log10(retained),
                "ideal_band_timing_information_fraction": timing_information(selected) / timing_information(canonical_energy),
                "coverage": coverage(cfo),
            })
    return {"rows": rows, "fft_points": nfft,
            "canonical_template_samples": 66, "narrow_sample_spacing_ns": 400,
            "source60_sample_spacing_ns": 1e9 / 60_000_000,
            "timing_accuracy_demonstrated": False,
            "fixed_fir_sha256": ddc.COEFFICIENT_SHA256,
            "full_pilot_carrier_residual_bound_hz": ddc.PASSBAND_EDGE_HZ - float(max(PILOT_CARRIERS)),
            "first_null_main_lobe_residual_bound_hz": ddc.PASSBAND_EDGE_HZ - float(max(PILOT_CARRIERS)) - 234_375,
            "first_null_bound_is_not_strict_modulated_support": True}


def synthetic(case: dict, plan: dict, modules: dict) -> dict:
    edge = case["edge"]
    count = PROBE_SAMPLES + 2 * HALO
    indexes = np.arange(count)
    rng = np.random.default_rng(plan["synthetic_seed"])
    values = np.zeros(count, dtype=np.complex128)
    epoch = plan["synthetic_epoch_canonical"]
    if case["kind"] == "positive":
        pilot = modules["templates"].qin_edge_pilot_frame(RATE, edge)
        pss = projected_pss(RATE, edge) * np.sqrt(66)
        carrier = np.exp(2j * np.pi * ddc.MIXER_STEP_64[edge] * indexes / 64)
        for start in range(epoch, count, 20_000):
            length = min(len(pilot), count - start)
            values[start:start + length] += 6000 * pilot[:length] * carrier[start:start + length]
            length = min(len(pss), count - start)
            values[start:start + length] += 6000 * pss[:length]
        values *= np.exp(2j * np.pi * case["injected_cfo_hz"] * indexes / RATE)
    values += 1500 * (rng.standard_normal(count) + 1j * rng.standard_normal(count))
    rounded = np.rint(np.column_stack((values.real, values.imag)))
    clipped = int(np.count_nonzero((rounded < -32768) | (rounded > 32767)))
    iq = np.clip(rounded, -32768, 32767).astype(np.int16)
    values, centers, filtered = filter_probe(
        iq, 0, HALO, edge=edge, correction_hz=case["applied_prefilter_correction_hz"])
    result = blind(values, edge, modules)
    residual = case["injected_cfo_hz"] - case["applied_prefilter_correction_hz"]
    support = coverage(residual)
    best = result["best"]
    delta = None if best is None else (best["epoch_sample"] - (epoch - centers[0]) / 6
                                      + OUTPUT_RATE / 1500) % (OUTPUT_RATE / 750) - OUTPUT_RATE / 1500
    cfo_error = None if best is None else best["tracking_cfo_hz"] - residual
    if case["kind"] == "noise":
        classification = "noise_control"
        passed = best is None or best["margin"] < .025
    elif support["status"] != "nominal_carriers_supported":
        classification = support["status"]
        passed = None
    else:
        classification = "known_supported_positive"
        passed = bool(best and best["margin"] > .15 and abs(delta) < 3 and abs(cfo_error) < 1000)
    valid = clipped + filtered["ddc_saturations"] + filtered["pre_filter_correction_saturations"] == 0
    return {"case": case, "filter": filtered, "blind_search": result, "coverage": support,
            "classification": classification, "source_saturations": clipped,
            "all_arithmetic_valid": valid, "predeclared_fixture_acceptance_pass": passed,
            "known_epoch_error_output_samples": None if delta is None else float(delta),
            "known_residual_cfo_error_hz": cfo_error,
            "known_epoch_error_source60_samples": None if delta is None else float(delta * 24),
            "budget_fpga_filter_host_search_only": budget(result["total_search_seconds"])}


def heldout(item: dict, modules: dict) -> dict:
    iq, first, _ = read_probe(item)
    values, centers, filtered = filter_probe(
        iq, first, item["center_start"], edge="upper",
        correction_hz=item["applied_prefilter_correction_hz"])
    result = blind(values, "upper", modules)
    best = result["best"]
    candidate = best is not None and best["margin"] > .025
    status = "pilot_candidate_coverage_estimated" if candidate else "no_candidate_coverage_unknown"
    summary = {
        "item": item, "filter": filtered, "blind_search": result,
        "classification": status, "independent_rf_truth": False,
        "calibrated_observability": False, "fine_timing_truth": False,
        "budget_fpga_filter_host_search_only": budget(result["total_search_seconds"]),
    }
    if best is not None:
        center = int(centers[0]) + 6 * best["epoch_sample"]
        summary.update(
            estimated_residual_cfo_hz=best["tracking_cfo_hz"],
            estimated_uncorrected_cfo_hz=best["tracking_cfo_hz"] + item["applied_prefilter_correction_hz"],
            candidate_frame_phase_us=(center % 20_000) / 15,
            estimated_coverage=coverage(best["tracking_cfo_hz"]),
            candidate_frame_original25_numerator=5 * center,
            candidate_frame_original25_denominator=3)
    if item["role"] == "heldout":
        prior_stop = item["prior_full_original25_source_bounds"][1] / 25_000_000
        summary["gap_prior_full_support_to_probe_input_seconds"] = first / RATE - prior_stop
    return summary


def run(path: Path) -> None:
    plan, raw = causal.read_json(path)
    for source, digest in plan["source_hashes"].items():
        if sha(Path(source).read_bytes()) != digest:
            raise ValueError(f"planned source changed: {source}")
    if encode(build_plan(Path(plan["evidence_root"]), Path(plan["leo_root"]))) != raw:
        raise ValueError("plan or probes changed since predeclaration")
    write_new(path.parent / "execution-start.json", {"plan_sha256": sha(raw)})
    modules, native = load_leo(Path(plan["leo_root"]))
    result = {
        "schema": "starlink-narrow-coarse-result-v1", "plan_sha256": sha(raw),
        "host": {"node": platform.node(), "platform": platform.platform(),
                 "python": sys.version, "executable": sys.executable, "numpy": np.__version__},
        "native_backend": native, "spectrum": spectrum_study(), "synthetic": [], "probes": [],
        "hardware_access": False, "online_qualified": False, "architecture_selected": False,
    }
    started = time.perf_counter()
    for index, case in enumerate(plan["synthetic_cases"]):
        row = synthetic(case, plan, modules)
        write_new(path.parent / f"synthetic-{index:02d}.json", row)
        result["synthetic"].append(row)
        print(json.dumps({"synthetic": case, "classification": row["classification"],
                          "accepted": row["predeclared_fixture_acceptance_pass"],
                          "seconds": row["blind_search"]["total_search_seconds"]}), flush=True)
    for item in plan["probes"]:
        row = heldout(item, modules)
        write_new(path.parent / f"{item['name']}.json", row)
        result["probes"].append(row)
        print(json.dumps({"probe": item["name"], "classification": row["classification"],
                          "best": row["blind_search"]["best"],
                          "seconds": row["blind_search"]["total_search_seconds"]}), flush=True)
    result["total_wall_seconds"] = time.perf_counter() - started
    result["all_predeclared_observable_fixtures_pass"] = all(
        row["all_arithmetic_valid"] and row["predeclared_fixture_acceptance_pass"] is not False
        for row in result["synthetic"])
    write_new(path.parent / "study-result.json", result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan_parser = commands.add_parser("plan")
    plan_parser.add_argument("--evidence-root", type=Path, required=True)
    plan_parser.add_argument("--leo-root", type=Path, required=True)
    plan_parser.add_argument("--output", type=Path, required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "plan":
        output = args.output.resolve()
        if ROOT not in output.parents:
            parser.error("study artifacts must be inside this assigned firmware worktree")
        plan = build_plan(args.evidence_root.resolve(), args.leo_root.resolve())
        output.mkdir(parents=True, exist_ok=False)
        write_new(output / "plan.json", plan)
        print(str(output / "plan.json"))
    else:
        path = args.plan.resolve()
        if ROOT not in path.parents:
            parser.error("study artifacts must be inside this assigned firmware worktree")
        run(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
