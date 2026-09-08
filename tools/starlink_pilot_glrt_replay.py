#!/usr/bin/env python3
"""Offline pilot-export/GLRT cross-check; never opens or qualifies a radio.

Use an explicitly supplied Leo source checkout as a development oracle only.
Optional Icarus replay verifies the IQ analyzed by GLRT is bit-identical to
the assembled pilot DDC RTL, not just its numerical reference.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import tempfile

import numpy as np

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from tests.starlink_oracle.pilot_ddc import PilotDdcOracle, MIXER_STEP_64
from tests.starlink_oracle.waveforms import projected_pss


SOURCE_RATE = 15_000_000
OUTPUT_RATE = 2_500_000
SOURCE_COUNT = 300_540  # exactly 20 ms of supported exported samples
SOURCE_EPOCH = 10_003
SOURCE_CFO_HZ = 42_000.0


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ci16_digest(samples: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(samples, dtype="<i2").tobytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--leo-source", type=Path, required=True,
                        help="explicit checkout containing src/leo; read-only oracle")
    parser.add_argument("--edge", choices=("lower", "upper"), required=True)
    parser.add_argument("--kind", choices=("positive", "noise"), default="positive")
    parser.add_argument("--rtl", action="store_true", help="also replay the exact source through Icarus")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.error("the supplied Leo oracle requires Python >=3.12")
    if args.output.exists():
        parser.error("output already exists; preserve previous evidence and choose a new path")
    leo_source = args.leo_source.resolve()
    paths = [leo_source / "src/leo/analysis/starlink" / name
             for name in ("templates.py", "acquisition.py", "pilot_methods.py")]
    if not all(path.is_file() for path in paths):
        parser.error("Leo source checkout is incomplete")
    sys.path.insert(0, str(leo_source / "src"))
    from leo.analysis.starlink.templates import qin_edge_pilot_frame
    from leo.analysis.starlink.acquisition import (
        ReceiverFrequencyCalibration, SymbolwiseAcquisitionConfig, acquire_symbolwise,
    )
    from leo.analysis.starlink.pilot_methods import conditioned_glrt64_scores

    rng = np.random.default_rng(170118)
    signal = np.zeros(SOURCE_COUNT, dtype=np.complex128)
    indexes = np.arange(SOURCE_COUNT)
    if args.kind == "positive":
        pilot = np.asarray(qin_edge_pilot_frame(SOURCE_RATE, args.edge), dtype=np.complex128)
        carrier = np.exp(2j*np.pi*MIXER_STEP_64[args.edge]*indexes/64)
        pss = projected_pss(SOURCE_RATE, args.edge) * np.sqrt(66)
        for start in range(SOURCE_EPOCH, SOURCE_COUNT, 20_000):
            count = min(len(pilot), SOURCE_COUNT-start)
            signal[start:start+count] += 6000*pilot[:count]*carrier[start:start+count]
            pss_count = min(len(pss), SOURCE_COUNT-start)
            signal[start:start+pss_count] += 6000*pss[:pss_count]
        signal *= np.exp(2j*np.pi*SOURCE_CFO_HZ*indexes/SOURCE_RATE)
    signal += 1500*(rng.standard_normal(SOURCE_COUNT) + 1j*rng.standard_normal(SOURCE_COUNT))
    unquantized = np.rint(np.column_stack((signal.real, signal.imag)))
    source_clips = int(np.count_nonzero((unquantized < -32768) | (unquantized > 32767)))
    samples = np.clip(unquantized, -32768, 32767).astype(np.int16)
    print(f"pilot fixture edge={args.edge} kind={args.kind} source_samples={len(samples)}", flush=True)
    reference = PilotDdcOracle(args.edge).process(samples, first_index=0)
    rtl_evidence = None
    if args.rtl:
        # These are explicitly test-only replay helpers, not a production
        # dependency from PPU or a firmware service into the Leo repository.
        from tests.starlink_oracle.test_pilot_ddc_rtl import _compile, _records, _run
        with tempfile.TemporaryDirectory(prefix="pilot-glrt-rtl-") as temporary:
            simulator = _compile(Path(temporary))
            outputs, status = _run(simulator, _records(samples, edge=args.edge))
        expected = [(int(index), 1, int(i), int(q), int(support))
                    for index, (i, q), support in zip(reference.accepted_input_indexes,
                                                     reference.samples_iq, reference.support_valid)]
        if [row[:5] for row in outputs] != expected:
            raise RuntimeError("RTL/reference mismatch; GLRT evidence is not qualified")
        if status[:5] != (0, 0, len(samples), len(expected), reference.saturation_events):
            raise RuntimeError(f"RTL continuity/counter mismatch: {status}")
        rtl_evidence = {
            "bit_exact": True, "accepted": status[2], "emitted": status[3],
            "saturation_events": status[4], "fifo_high_water": status[5],
        }
        print("RTL replay matches every IQ sample, index and support flag", flush=True)

    supported_iq = reference.samples_iq[reference.support_valid]
    supported_indexes = reference.accepted_input_indexes[reference.support_valid]
    if len(supported_iq) != 50_000 or not np.all(np.diff(supported_indexes) == 6):
        raise RuntimeError("expected exactly 20 ms of continuous supported IQ")
    probe = supported_iq[:, 0].astype(float) + 1j*supported_iq[:, 1]
    configuration = SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=-100_000, residual_cfo_max_hz=100_000,
        retained_candidate_count=10, candidate_epoch_separation_samples=5,
        candidate_cfo_separation_hz=10_000,
    )
    print("Running blind host acquisition then GLRT on every retained candidate", flush=True)
    acquired = acquire_symbolwise(
        probe, OUTPUT_RATE, ReceiverFrequencyCalibration("synthetic-pilot-ddc", 0, "0"*64),
        edge=args.edge, config=configuration,
    )
    scores = conditioned_glrt64_scores(
        probe, OUTPUT_RATE, edge=args.edge,
        epoch_samples=[candidate.refined_epoch_sample for candidate in acquired.candidates],
        acquired_cfo_hz=[candidate.absolute_cfo_hz for candidate in acquired.candidates],
    )
    rows = [dict(epoch_sample=int(candidate.refined_epoch_sample),
                 acquired_cfo_hz=float(candidate.absolute_cfo_hz), **asdict(score))
            for candidate, score in zip(acquired.candidates, scores)]
    best = max(rows, key=lambda row: row["margin"], default=None)
    expected_epoch = (SOURCE_EPOCH + 269 - int(supported_indexes[0])) / 6
    epoch_error = None
    cfo_error = None
    if best is not None and args.kind == "positive":
        period = OUTPUT_RATE / 750
        epoch_error = (best["epoch_sample"] - expected_epoch + period/2) % period - period/2
        cfo_error = best["tracking_cfo_hz"] - SOURCE_CFO_HZ
    if args.kind == "positive":
        verified = (source_clips == 0 and best is not None and best["margin"] > 0.15
                    and abs(epoch_error) < 3 and abs(cfo_error) < 1000)
    else:
        verified = source_clips == 0 and (best is None or best["margin"] < 0.05)
    hdl = REPOSITORY / "hdl/library/starlink_pss_acquisition"
    evidence = {
        "schema": "starlink-pilot-export-glrt-replay-v1",
        "scope": "synthetic software/RTL replay; not RF or FPGA PSS lock",
        "hardware_accessed": False, "deployed": False, "live_glrt_evidence": False,
        "fpga_pss_lock": False, "fixture_verified": bool(verified),
        "edge": args.edge, "kind": args.kind, "source_rate_hz": SOURCE_RATE,
        "output_rate_hz": OUTPUT_RATE, "source_samples": SOURCE_COUNT,
        "supported_output_samples": len(supported_iq),
        "first_output_newest_canonical_index": int(supported_indexes[0]),
        "pilot_group_delay_canonical_samples": 269,
        "source_clipping_events": source_clips,
        "ddc_saturation_events": reference.saturation_events,
        "input_ci16_sha256": ci16_digest(samples),
        "supported_iq_sha256": ci16_digest(supported_iq),
        "rtl": rtl_evidence, "numpy_version": np.__version__,
        "independent_acquisition": True, "pss_seeds_used": False,
        "acquisition_configuration": asdict(configuration),
        "best": best, "candidates": rows,
        "known_fixture_epoch_error_output_samples": epoch_error,
        "known_fixture_cfo_error_hz": cfo_error,
        "leo_source_sha256": {path.name: digest(path) for path in paths},
        "source_sha256": {name: digest(hdl/name) for name in (
            "starlink_pilot_ddc.v", "starlink_pilot_halfband2.v", "starlink_pilot_fir3.v",
            "pilot_mixer_q16.mem", "pilot_halfband2_q17.mem", "pilot_fir3_q17.mem")},
        "replay_script_sha256": digest(Path(__file__)),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(evidence, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"fixture_verified": bool(verified), "best": best, "report": str(args.output)}), flush=True)
    if not verified:
        raise SystemExit("synthetic fixture gate failed; inspect evidence, do not promote firmware")


if __name__ == "__main__":
    main()
