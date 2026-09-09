#!/usr/bin/env python3
"""Blind offline GLRT on every window of a 2.5 MS/s CI16 observation.

Run with the pinned Leo checkout's Python environment. FPGA events are not an
input; compare this immutable output with them only after acquisition finishes.
The explicit gates describe an engineering experiment, not calibrated RF truth.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import importlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

REFERENCE_COMMIT = "5f25fc57cca3ea564ac42debe3561139592c82b0"
OUTPUT_RATE = 2_500_000
WINDOW_SAMPLES = 50_000
STRIDE_SAMPLES = 25_000


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def document(path: Path, value: object) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def reference_identity(root: Path) -> dict:
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
    commit = git("rev-parse", "HEAD")
    if commit != REFERENCE_COMMIT or git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("reference requires the clean, frozen Leo commit " + REFERENCE_COMMIT)
    files = [root / "uv.lock", root / "pyproject.toml"]
    files += sorted((root / "src/leo/analysis/starlink").glob("*.py"))
    native = sorted((root / "src/leo/analysis/starlink").glob("_native_acquisition*.so"))
    if len(native) != 1:
        raise ValueError("build the pinned reference's native acquisition extension first")
    files += native
    return {"commit": commit, "root": str(root),
            "sha256": {str(p.relative_to(root)): digest(p) for p in files}}


def window_starts(count: int):
    # Keep the final short tail explicit. Windows overlap by 10 ms; their
    # decisions are correlated and must not be counted as independent trials.
    return range(0, count, STRIDE_SAMPLES)


def score_support(epoch: int, count: int, start: int) -> list[list[int]]:
    """Exact integer-symbol support of the frozen 64-symbol scorer, half-open."""
    result = []
    frame = 0
    while True:
        frame_start = epoch + round(frame * Fraction(OUTPUT_RATE, 750))
        left, right = frame_start + 22, frame_start + 726  # symbols 2..65, N=11
        if right > count:
            break
        result.append([start + left, start + right])
        frame += 1
    return result


def frame_scores(methods, values, candidate, edge, start, minimum_exact, minimum_margin):
    """Score each complete frame using only this host's acquired epoch/CFO.

    A multi-frame crossing does not establish that every constituent frame
    contains a pilot. Separate 704-sample scores make that distinction explicit.
    """
    result = []
    for left, right in score_support(candidate.refined_epoch_sample, len(values), start):
        frame_start = left-start-22
        score = methods.conditioned_glrt64_score(
            values[frame_start:right-start], OUTPUT_RATE, epoch_sample=0,
            acquired_cfo_hz=candidate.absolute_cfo_hz, edge=edge, glrt_size=512)
        result.append({"support_output_samples": [left, right], "glrt64": asdict(score),
                       "engineering_positive": score.exact_score >= minimum_exact and score.margin >= minimum_margin,
                       "within_cfo_comparison_band": abs(score.tracking_cfo_hz) <= 100_000})
    return result


def analyze(args) -> dict:
    root, iq_path = args.leo_source.resolve(), args.iq.resolve()
    identity = reference_identity(root)
    size = iq_path.stat().st_size
    if size == 0 or size % 4:
        raise ValueError("input must contain a nonempty whole number of little-endian CI16 words")
    if not all(math.isfinite(v) and 0 <= v <= 1 for v in
               (args.minimum_exact, args.minimum_margin)):
        raise ValueError("engineering score gates must be finite and between zero and one")
    sys.path.insert(0, str(root / "src"))
    import numpy as np
    acquisition = importlib.import_module("leo.analysis.starlink.acquisition")
    methods = importlib.import_module("leo.analysis.starlink.pilot_methods")
    if not Path(acquisition.__file__).resolve().is_relative_to(root):
        raise ValueError("imported acquisition does not belong to the frozen reference")
    if acquisition._native_acquisition is None:
        raise ValueError("native acquisition accelerator failed to import")
    native_path = Path(acquisition._native_acquisition.__file__).resolve()
    if not native_path.is_relative_to(root):
        raise ValueError("native acquisition does not belong to the frozen reference")

    count = size // 4
    iq_sha = digest(iq_path)
    config = acquisition.SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=-100_000, residual_cfo_max_hz=100_000,
        maximum_probe_samples=WINDOW_SAMPLES)
    calibration_record = {"receiver_id": "exported-ci16", "center_hz": 0,
                          "meaning": "receiver-relative digital pilot band center; no RF calibration inferred"}
    calibration_sha = hashlib.sha256(json.dumps(calibration_record, sort_keys=True).encode()).hexdigest()
    calibration = acquisition.ReceiverFrequencyCalibration("exported-ci16", 0, calibration_sha)
    protocol = {
        "schema": "starlink-glrt-blind-host/v1", "sample_rate_hz": OUTPUT_RATE,
        "edge": args.edge, "window_samples": WINDOW_SAMPLES, "stride_samples": STRIDE_SAMPLES,
        "acquisition": asdict(config), "calibration": calibration_record,
        "calibration_sha256": calibration_sha, "glrt_size": 512,
        "minimum_exact": args.minimum_exact, "minimum_margin": args.minimum_margin,
        "cfo_comparison_band_hz": [-100_000, 100_000],
        "glrt_residual_alias_period_hz": float(Fraction(5_000_000, 22)),
        "gate_status": "explicit engineering gates; not calibrated Starlink truth",
        "epoch_refinement": "integer only; 0.4 us sample grid",
        "fpga_seed_inputs": [], "score_normalization": "sum across frames of (sum of absolute symbol correlations)^2",
        "per_frame_evidence": "each complete 704-sample support is also scored alone at independently host-acquired epoch/CFO",
        "limitations": ["at least two frames needed for blind acquisition",
                       "eight retained acquisition basins can miss other hypotheses",
                       "multi-frame host score differs from native single-frame FPGA score",
                       "multi-frame crossings do not label each constituent frame positive; frame scores use the same uncalibrated engineering gates",
                       "acquisition CFO search limited to +/-100 kHz; subsequent periodic GLRT residual can place tracking CFO outside that band",
                       "overlapping windows are not independent trials",
                       "no analog clipping or transport integrity inferred from IQ alone"],
    }
    args.output.mkdir(parents=True, exist_ok=False)
    document(args.output / "protocol.json", protocol)
    document(args.output / "inputs.json", {
        "iq": str(iq_path), "iq_sha256": iq_sha, "bytes": size, "samples": count,
        "reference": identity, "python": sys.version, "numpy": np.__version__,
        "script_sha256": digest(Path(__file__)),
        "started_utc": datetime.now(timezone.utc).isoformat(),
    })
    started = time.monotonic()
    counters = {"windows": 0, "complete": 0, "insufficient": 0, "no_result": 0,
                "windows_with_engineering_positive": 0,
                "windows_with_in_band_engineering_positive": 0}
    samples = np.memmap(iq_path, mode="r", dtype="<i2", shape=(count, 2))
    try:
        with (args.output / "blind-windows.jsonl").open("x") as stream:
            for start in window_starts(count):
                stop = min(count, start + WINDOW_SAMPLES)
                raw = samples[start:stop]
                values = raw[:, 0].astype(np.float64) + 1j * raw[:, 1].astype(np.float64)
                result = acquisition.acquire_symbolwise(values, OUTPUT_RATE, calibration,
                                                       edge=args.edge, config=config)
                scored = []
                for candidate in result.candidates:
                    # All conditioning parameters came from THIS window's
                    # independent acquisition. No FPGA epoch/CFO is loaded.
                    score = methods.conditioned_glrt64_score(
                        values, OUTPUT_RATE, epoch_sample=candidate.refined_epoch_sample,
                        acquired_cfo_hz=candidate.absolute_cfo_hz, edge=args.edge, glrt_size=512)
                    scored.append({"acquisition": asdict(candidate), "glrt64": asdict(score),
                                   "frame_glrt64": frame_scores(methods, values, candidate, args.edge, start,
                                                                args.minimum_exact, args.minimum_margin),
                                   "score_support_output_samples": score_support(
                                       candidate.refined_epoch_sample, len(values), start),
                                   "within_cfo_comparison_band": -100_000 <= score.tracking_cfo_hz <= 100_000,
                                   "engineering_positive": score.exact_score >= args.minimum_exact
                                       and score.margin >= args.minimum_margin})
                winner = max(scored, key=lambda row: (row["glrt64"]["margin"],
                             -row["acquisition"]["rank"]), default=None)
                row = {"start": start, "stop": stop, "status": result.status.value,
                       "reason": result.reason, "candidates": scored,
                       "winner_rank": None if winner is None else winner["acquisition"]["rank"],
                       "rail_components": int(np.count_nonzero((raw == -32768) | (raw == 32767)))}
                stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
                stream.flush()
                counters["windows"] += 1
                counters[result.status.value] += 1
                counters["windows_with_engineering_positive"] += int(any(
                    item["engineering_positive"] for item in scored))
                counters["windows_with_in_band_engineering_positive"] += int(any(
                    item["engineering_positive"] and item["within_cfo_comparison_band"] for item in scored))
                print(f"window {counters['windows']}: [{start},{stop}) {result.status.value}", flush=True)
        if iq_path.stat().st_size != size or digest(iq_path) != iq_sha:
            raise ValueError("IQ changed during blind analysis; output is disqualified")
        if reference_identity(root) != identity:
            raise ValueError("numerical reference changed during analysis; output is disqualified")
        summary = {"schema": protocol["schema"], "status": "complete", **counters,
                   "elapsed_seconds": time.monotonic() - started,
                   "iq_sha256": iq_sha, "samples": count,
                   "protocol_sha256": digest(args.output / "protocol.json"),
                   "windows_sha256": digest(args.output / "blind-windows.jsonl"),
                   "independence": "only CI16 and predeclared edge/search/gates supplied; no FPGA events",
                   "transport_qualified": False, "hardware_qualified": False}
        document(args.output / "summary.json", summary)
        return summary
    except Exception as error:
        document(args.output / "failure.json", {"status": "disqualified", "error": str(error),
                                                **counters})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--leo-source", type=Path, required=True)
    parser.add_argument("--iq", type=Path, required=True)
    parser.add_argument("--edge", choices=("upper", "lower"), required=True)
    parser.add_argument("--minimum-exact", type=float, required=True)
    parser.add_argument("--minimum-margin", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = analyze(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"blind GLRT failed: {error}\n")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
