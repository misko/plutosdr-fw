#!/usr/bin/env python3
"""Measure bounded FPGA PSS phase-map geometries on one continuity-safe CI16 file.

This is an offline experimental tool.  It reads but never modifies its IQ
input.  A deterministic frame-scrambled score stream supplies a cadence
negative control without pretending to be an independent RF recording.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from tests.starlink_oracle import (
    ACQUISITION_ORACLE_SCHEMA,
    AcquisitionConfig,
    FixedMatchScoreStream,
    fold_phase_map_tiles,
    overlap_save_fixed_match_scores,
    projected_pss,
    quantize_q15,
    search_phase_map_drift,
)

_READ_CHUNK_BYTES = 8 * 1024 * 1024


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="CI16 little-endian file, optionally .zst")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--edge", choices=("lower", "upper"), required=True)
    parser.add_argument("--first-sample-index", type=int, default=0)
    parser.add_argument("--maximum-samples", type=int)
    parser.add_argument("--score-bits", type=int, default=8)
    parser.add_argument(
        "--phase-bin-samples",
        type=int,
        nargs="+",
        default=(1, 2, 4, 5, 8),
    )
    parser.add_argument(
        "--tile-frames",
        type=int,
        nargs="+",
        default=(8, 16, 32, 64),
    )
    parser.add_argument("--maximum-period-error-ppm", type=float, default=10.0)
    parser.add_argument("--period-step-ppm", type=float, default=3.125)
    parser.add_argument("--expected-phase-sample", type=float)
    parser.add_argument(
        "--generated-at-utc",
        help="fixed ISO-8601 UTC evidence timestamp; defaults to the current time",
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(_READ_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _generated_at_utc(value: str | None) -> str:
    if value is None:
        return datetime.now(UTC).isoformat()
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("generated_at_utc must name an explicit UTC instant")
    return parsed.astimezone(UTC).isoformat()


def _read_ci16(path: Path, maximum_samples: int | None) -> np.ndarray:
    if maximum_samples is not None and maximum_samples <= 0:
        raise ValueError("maximum_samples must be positive")
    if path.suffix == ".zst":
        command = ["zstd", "--decompress", "--stdout", "--quiet", str(path)]
        completed = subprocess.run(command, check=True, stdout=subprocess.PIPE)
        payload = completed.stdout
    else:
        payload = path.read_bytes()
    if len(payload) % 4:
        raise ValueError("CI16 input byte count must be divisible by four")
    values = np.frombuffer(payload, dtype="<i2").reshape(-1, 2)
    if maximum_samples is not None:
        values = values[:maximum_samples]
    return np.asarray(values, dtype=np.int16)


def _drift_bank(config: AcquisitionConfig, maximum_ppm: float, step_ppm: float) -> np.ndarray:
    if not math.isfinite(maximum_ppm) or maximum_ppm < 0:
        raise ValueError("maximum period error must be finite and nonnegative")
    if not math.isfinite(step_ppm) or step_ppm <= 0:
        raise ValueError("period step must be finite and positive")
    steps = math.floor(maximum_ppm / step_ppm + 1e-12)
    ppm = np.arange(-steps, steps + 1, dtype=float) * step_ppm
    period_delta_per_frame = config.frame_samples * ppm * 1e-6
    return period_delta_per_frame * config.tile_frames / config.phase_bin_samples


def _scramble_complete_frames(
    stream: FixedMatchScoreStream,
    *,
    seed: int,
) -> FixedMatchScoreStream:
    frame_samples = 20_000
    leading = (-stream.first_sample_index) % frame_samples
    complete_count = max(0, (stream.scores.size - leading) // frame_samples)
    values = np.array(stream.scores, copy=True)
    rng = np.random.default_rng(seed)
    for frame in range(complete_count):
        start = leading + frame * frame_samples
        stop = start + frame_samples
        values[start:stop] = np.roll(
            values[start:stop], int(rng.integers(0, frame_samples))
        )
    values.flags.writeable = False
    return FixedMatchScoreStream(
        first_sample_index=stream.first_sample_index,
        scores=values,
        template_samples=stream.template_samples,
        coefficient_energy=stream.coefficient_energy,
        fft_samples=stream.fft_samples,
        maximum_fft_rounding_residual=stream.maximum_fft_rounding_residual,
    )


def _candidate_document(
    stream: FixedMatchScoreStream,
    *,
    phase_bin_samples: int,
    tile_frames: int,
    score_bits: int,
    maximum_period_error_ppm: float,
    period_step_ppm: float,
    expected_phase_sample: float | None,
) -> dict[str, object]:
    maximum_map_value = tile_frames * ((1 << score_bits) - 1)
    config = AcquisitionConfig(
        phase_bin_samples=phase_bin_samples,
        tile_frames=tile_frames,
        score_bits=score_bits,
        phase_map_word_bits=16 if maximum_map_value <= 65_535 else 32,
    )
    tiles = fold_phase_map_tiles(stream, config)
    base: dict[str, object] = {
        "phase_bin_samples": phase_bin_samples,
        "phase_bins": config.phase_bins,
        "tile_frames": tile_frames,
        "score_bits": score_bits,
        "phase_map_word_bits": config.phase_map_word_bits,
        "complete_tile_count": int(tiles.maps.shape[0]),
        "discarded_leading_scores": tiles.discarded_leading_scores,
        "discarded_trailing_scores": tiles.discarded_trailing_scores,
        "phase_map_bytes": config.phase_map_bytes,
        "phase_map_bytes_per_second": config.phase_map_bytes_per_second,
    }
    if not tiles.maps.shape[0]:
        return {**base, "candidate": None}
    candidate = search_phase_map_drift(
        tiles,
        drift_bins_per_tile=_drift_bank(
            config, maximum_period_error_ppm, period_step_ppm
        ),
    )
    phase_error = None
    if expected_phase_sample is not None:
        direct = abs(candidate.phase_bin_center_sample - expected_phase_sample)
        phase_error = min(direct, config.frame_samples - direct)
    return {
        **base,
        "candidate": {
            "phase_bin": candidate.phase_bin,
            "phase_bin_start_sample": candidate.phase_bin_start_sample,
            "phase_bin_center_sample": candidate.phase_bin_center_sample,
            "phase_error_samples": phase_error,
            "drift_bins_per_tile": candidate.drift_bins_per_tile,
            "estimated_frame_period_samples": candidate.estimated_frame_period_samples,
            "estimated_period_error_ppm": (
                (candidate.estimated_frame_period_samples - config.frame_samples)
                / config.frame_samples
                * 1e6
            ),
            "combined_score": candidate.combined_score,
            "combined_median": candidate.combined_median,
            "peak_to_median": (
                candidate.peak_to_median
                if math.isfinite(candidate.peak_to_median)
                else None
            ),
            "peak_to_median_unbounded": math.isinf(candidate.peak_to_median),
            "robust_z": candidate.robust_z if math.isfinite(candidate.robust_z) else None,
            "robust_z_unbounded": math.isinf(candidate.robust_z),
            "passes_existing_epoch_gates": (
                candidate.peak_to_median >= 1.15 and candidate.robust_z >= 6.0
            ),
        },
    }


def main() -> None:
    args = _arguments()
    source = args.input.resolve(strict=True)
    output = args.output.resolve(strict=False)
    if output.exists() and not args.force:
        raise FileExistsError(f"refusing to replace existing output: {output}")
    if args.first_sample_index < 0:
        raise ValueError("first_sample_index must be nonnegative")
    if len(set(args.phase_bin_samples)) != len(args.phase_bin_samples):
        raise ValueError("phase-bin geometries must be unique")
    if len(set(args.tile_frames)) != len(args.tile_frames):
        raise ValueError("tile-frame geometries must be unique")

    samples = _read_ci16(source, args.maximum_samples)
    coefficients = quantize_q15(projected_pss(15_000_000, args.edge))
    matched = overlap_save_fixed_match_scores(
        samples,
        coefficients,
        first_sample_index=args.first_sample_index,
        score_bits=args.score_bits,
    )
    scrambled = _scramble_complete_frames(matched, seed=0x15AC001)

    geometries = tuple(
        (phase_bin_samples, tile_frames)
        for phase_bin_samples in args.phase_bin_samples
        for tile_frames in args.tile_frames
    )
    document = {
        "schema": ACQUISITION_ORACLE_SCHEMA,
        "analysis_kind": "offline-pss-phase-map-geometry-study",
        "generated_at_utc": _generated_at_utc(args.generated_at_utc),
        "candidate_only": True,
        "over_the_air_starlink_pss_qualified": False,
        "input": {
            "path": str(source),
            "compressed_sha256": _sha256(source),
            "sample_format": "ci16_le",
            "sample_count": int(samples.shape[0]),
            "first_sample_index": args.first_sample_index,
        },
        "template": {
            "edge": args.edge,
            "sample_rate_hz": 15_000_000,
            "sample_count": int(coefficients.shape[0]),
            "coefficient_energy": matched.coefficient_energy,
        },
        "score_stream": {
            "score_bits": args.score_bits,
            "score_count": int(matched.scores.size),
            "fft_samples": matched.fft_samples,
            "valid_outputs_per_fft": matched.fft_samples - matched.template_samples + 1,
            "maximum_fft_rounding_residual": matched.maximum_fft_rounding_residual,
        },
        "drift_search": {
            "maximum_period_error_ppm": args.maximum_period_error_ppm,
            "period_step_ppm": args.period_step_ppm,
        },
        "expected_phase_sample": args.expected_phase_sample,
        "matched": [
            _candidate_document(
                matched,
                phase_bin_samples=phase_bin_samples,
                tile_frames=tile_frames,
                score_bits=args.score_bits,
                maximum_period_error_ppm=args.maximum_period_error_ppm,
                period_step_ppm=args.period_step_ppm,
                expected_phase_sample=args.expected_phase_sample,
            )
            for phase_bin_samples, tile_frames in geometries
        ],
        "frame_scrambled_negative_control": {
            "description": (
                "deterministic independent circular shift per complete nominal frame; "
                "preserves score distribution but destroys repeated epoch"
            ),
            "seed": "0x15ac001",
            "results": [
                _candidate_document(
                    scrambled,
                    phase_bin_samples=phase_bin_samples,
                    tile_frames=tile_frames,
                    score_bits=args.score_bits,
                    maximum_period_error_ppm=args.maximum_period_error_ppm,
                    period_step_ppm=args.period_step_ppm,
                    expected_phase_sample=None,
                )
                for phase_bin_samples, tile_frames in geometries
            ],
        },
    }
    payload = (json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(output)
    print(f"wrote {output} ({len(payload)} bytes)")
    print(f"sha256:{hashlib.sha256(payload).hexdigest()}")


if __name__ == "__main__":
    main()
