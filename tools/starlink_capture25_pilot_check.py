"""Blind pilot cross-check on an explicitly conditioned recording derivative.

Offline only. This does not open IIO, use PSS seeds, or qualify live FPGA timing.
The supplied canonical input must include real filter history on both sides of
the requested interval. Its index names the original 15 MS/s canonical lattice.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import stat
import sys
from dataclasses import asdict
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.starlink_oracle.pilot_ddc import PilotDdcOracle

MAX_CANONICAL_SAMPLES = 4_900_000
ANALYSIS_SAMPLES = 4_800_000
SIGNED_INDEX_LIMIT = 1 << 63
PROBE_OFFSETS = (0, 250_000, 500_000)


def _bounded_input(source: Path) -> bytes:
    info = source.stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_size % 4 or
            not ANALYSIS_SAMPLES * 4 <= info.st_size <= MAX_CANONICAL_SAMPLES * 4):
        raise ValueError("expected bounded 320 ms CI16 derivative plus real halos")
    with source.open("rb") as stream:
        payload = stream.read(MAX_CANONICAL_SAMPLES * 4 + 1)
    if len(payload) != info.st_size:
        raise ValueError("canonical input size changed during bounded read")
    return payload


def _loaded_oracle(leo_source: Path):
    """Verify actual Python import origins, including a cached wrong checkout."""
    source_root = (leo_source / "src").resolve(strict=True)
    sys.path.insert(0, str(source_root))
    modules, hashes = {}, {}
    for name in ("templates", "acquisition", "pilot_methods"):
        expected = (source_root / "leo/analysis/starlink" / (name + ".py")).resolve(strict=True)
        module = importlib.import_module("leo.analysis.starlink." + name)
        actual = Path(module.__file__).resolve(strict=True)
        if actual != expected:
            raise ValueError(f"loaded Leo {name} does not match the explicit checkout: {actual}")
        hashes[str(actual)] = hashlib.sha256(actual.read_bytes()).hexdigest()
        modules[name] = module
    # Record the actual loaded Leo native backend separately. Its presence is
    # not assumed from PYTHONPATH and does not imply that every probe used it.
    native = {}
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if (name.startswith("leo.") and isinstance(filename, str) and
                any(filename.endswith(suffix) for suffix in EXTENSION_SUFFIXES)):
            actual = Path(filename).resolve(strict=True)
            native[name] = {"path": str(actual), "sha256": hashlib.sha256(
                actual.read_bytes()).hexdigest()}
    backend = getattr(modules["acquisition"], "_native_acquisition", None)
    if backend is not None and getattr(backend, "__name__", None) not in native:
        raise ValueError("loaded acquisition native backend lacks native-module provenance")
    return modules, hashes, native


def _write_receipt(path: Path, evidence: dict) -> None:
    # A serialization error cannot leave a partially serialized evidence file.
    encoded = json.dumps(evidence, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as output:
        output.write(encoded)


def _require_source_hashes(hashes: dict, native: dict) -> None:
    expected = {**hashes, **{value["path"]: value["sha256"] for value in native.values()}}
    for filename, digest in expected.items():
        if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != digest:
            raise ValueError(f"loaded oracle source changed during analysis: {filename}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-ci16", type=Path, required=True)
    parser.add_argument("--first-canonical-index", type=int, required=True)
    parser.add_argument("--start-canonical-index", type=int, required=True)
    parser.add_argument("--leo-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite evidence")
    if args.first_canonical_index < 0 or args.start_canonical_index < 0:
        parser.error("canonical indexes must be nonnegative")
    source = args.canonical_ci16.resolve(strict=True)
    try:
        payload = _bounded_input(source)
    except ValueError as error:
        parser.error(str(error))
    source_hash = hashlib.sha256(payload).hexdigest()
    iq = np.frombuffer(payload, dtype="<i2").reshape(-1, 2)
    start, stop = args.start_canonical_index, args.start_canonical_index + ANALYSIS_SAMPLES
    if args.first_canonical_index + len(iq) > SIGNED_INDEX_LIMIT or stop > SIGNED_INDEX_LIMIT:
        parser.error("canonical interval must fit the signed index arithmetic")
    if start - args.first_canonical_index < 538 or (
        args.first_canonical_index + len(iq) - stop < 538
    ):
        parser.error("real filter halos do not surround the requested interval")
    modules, hashes, native = _loaded_oracle(args.leo_source)
    acquisition, methods = modules["acquisition"], modules["pilot_methods"]
    for filename in (Path(__file__), ROOT / "tests/starlink_oracle/pilot_ddc.py"):
        actual = filename.resolve(strict=True)
        hashes[str(actual)] = hashlib.sha256(actual.read_bytes()).hexdigest()
    configuration = acquisition.SymbolwiseAcquisitionConfig()
    rows = []
    evidence = {
        "schema": "starlink-capture25-conditioned-pilot-crosscheck-v1",
        "status": "incomplete", "error": None,
        "scope": "Recorded RF, offline canonical derivative and integer pilot model; not RTL/DMA/IIO",
        "hardware_access": False, "native_25msps_fpga_qualification": False,
        "fpga_pss_lock": False, "pss_seeds_used": False,
        "calibration_attached": False,
        "frequency_prior": "Zero uncalibrated hypothesis; independent search within +/-400 kHz",
        "source_ci16": str(source), "source_ci16_sha256": source_hash,
        "first_canonical_index": args.first_canonical_index,
        "analysis_canonical_interval": [start, stop],
        "pilot_samples": None, "pilot_saturation_events": None,
        "pilot_ci16_sha256": None,
        "first_pilot_canonical_center": None,
        "last_pilot_canonical_center": None,
        "group_delay_already_removed_canonical_samples": 269,
        "configuration": asdict(configuration), "probes": rows,
        "declared_probe_offsets": list(PROBE_OFFSETS),
        "probe_policy": "Fixed20ms probes at0,100,200ms inside first256ms nominal three-map span; exact processing support must still be joined.",
        "limitations": [
            "Three fixed20ms probes, not all windows or the complete recording.",
            "Legacy explicit Leo development oracle, not a rerun of deployed analysis.",
            "GLRT candidates/score margins are estimates, not absolute PSS timing truth.",
            "No calibration was attached to the recording; zero is a search origin only.",
        ],
        "source_sha256": hashes, "loaded_native_modules": native,
        "provenance_scope": "Actual three imported Leo module paths plus loaded Leo native modules; not all Python/NumPy transitive dependencies.",
        "numpy_version": np.__version__,
    }
    try:
        oracle = PilotDdcOracle("upper")
        pieces, indexes = [], []
        clips = 0
        for offset in range(0, len(iq), 60_000):
            result = oracle.process(iq[offset:offset + 60_000],
                                    first_index=args.first_canonical_index + offset)
            center = result.accepted_input_indexes.astype(np.int64) - 269
            selected = result.support_valid & (center >= start) & (center < stop)
            pieces.append(result.samples_iq[selected])
            indexes.append(center[selected])
            clips += result.saturation_events
            evidence["pilot_saturation_events"] = clips
        pilot = np.concatenate(pieces)
        centers = np.concatenate(indexes)
        evidence.update(pilot_samples=len(pilot),
                        pilot_ci16_sha256=hashlib.sha256(pilot.astype("<i2").tobytes()).hexdigest())
        if (len(pilot) != 800_000 or not np.all(np.diff(centers) == 6) or
                int(centers[0]) != start + ((1 - start) % 6)):
            raise RuntimeError("pilot output is not the exact contiguous 320 ms center lattice")
        evidence.update(first_pilot_canonical_center=int(centers[0]),
                        last_pilot_canonical_center=int(centers[-1]))
        if clips:
            raise RuntimeError(f"pilot saturation invalidates replay: {clips}")
        # Fixed windows, never chosen from PSS peaks or measured pilot scores.
        for offset in PROBE_OFFSETS:
            probe = pilot[offset:offset + 50_000]
            values = probe[:, 0].astype(float) + 1j * probe[:, 1]
            print(f"blind pilot probe offset={offset} samples={len(probe)}", flush=True)
            acquired = acquisition.acquire_symbolwise(
                values, 2_500_000,
                acquisition.ReceiverFrequencyCalibration(
                    "uncalibrated-recording-hypothesis", 0, source_hash),
                edge="upper", config=configuration,
            )
            scores = methods.conditioned_glrt64_scores(
                values, 2_500_000, edge="upper",
                epoch_samples=[candidate.refined_epoch_sample for candidate in acquired.candidates],
                acquired_cfo_hz=[candidate.absolute_cfo_hz for candidate in acquired.candidates],
            )
            candidates = []
            for candidate, score in zip(acquired.candidates, scores, strict=True):
                epoch = candidate.refined_epoch_sample
                if (isinstance(epoch, (bool, np.bool_)) or not isinstance(epoch, (int, np.integer))
                        or not 0 <= epoch < 3334):
                    raise ValueError("acquired epoch is outside the 2.5 MS/s frame lattice")
                global_center = int(centers[offset]) + 6 * int(epoch)
                candidates.append({
                    "epoch_sample": int(epoch),
                    "frame_start_canonical_center": global_center,
                    "frame_start_original25_sample_numerator": 5 * global_center,
                    "frame_start_original25_sample_denominator": 3,
                    "phase_us_mod_750hz": (global_center % 20_000) / 15,
                    **asdict(score),
                })
            best = max(candidates, key=lambda row: row["margin"], default=None)
            row = {"pilot_offset": offset, "sample_count": len(probe),
                   "canonical_center_start": int(centers[offset]),
                   "acquisition_status": str(acquired.status),
                   "best": best, "candidates": candidates}
            json.dumps(row, allow_nan=False)  # Admit only serializable complete rows.
            rows.append(row)
            print(json.dumps({"pilot_offset": offset, "best": best}, allow_nan=False), flush=True)
        _require_source_hashes(hashes, native)
        evidence["status"] = "complete"
    except BaseException as error:
        evidence["status"] = "failed"
        evidence["error"] = {"type": type(error).__name__, "repr": repr(error)[:4000]}
        _write_receipt(args.output, evidence)
        raise
    _write_receipt(args.output, evidence)


if __name__ == "__main__":
    main()
