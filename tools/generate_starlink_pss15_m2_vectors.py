#!/usr/bin/env python3
"""Generate one exact periodic PSS score profile and M2 timing matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.starlink_oracle import (
    XfftBitAccModel,
    prepare_installed_cmodel,
    projected_pss,
    quantize_q15,
    xfft_bitacc_match_scores,
)
from tests.starlink_oracle import xfft_bitacc as xfft_model

SCHEMA = "starlink-pss15-m2-periodic-vectors-v1"
PERIOD_SAMPLES = 20_000
TEMPLATE_SAMPLES = 66
FIXTURE_SAMPLES = 130
TEMPLATE_OFFSET = 32
TILE_FRAMES = 64
FFT_SAMPLES = 512
VALID_RESULTS_PER_BLOCK = 447
RANDOM_SEED = 0x1502_6000
DATA_BITS = 18


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def packed_ci16(values: np.ndarray) -> bytes:
    return (
        "\n".join(f"{int(q) & 0xFFFF:04x}{int(i) & 0xFFFF:04x}" for i, q in values)
        + "\n"
    ).encode("ascii")


def expected_phase(injection_start: int, map_start: int) -> int:
    return (injection_start + TEMPLATE_OFFSET - map_start) % PERIOD_SAMPLES


def generate(output_directory: Path) -> dict[str, object]:
    output_directory.mkdir(parents=True, exist_ok=True)
    coefficients = quantize_q15(projected_pss(15_000_000, "upper"))
    fixture = np.ones((FIXTURE_SAMPLES, 2), dtype=np.int16)
    fixture[:, 1] = 0
    fixture[TEMPLATE_OFFSET : TEMPLATE_OFFSET + TEMPLATE_SAMPLES] = coefficients

    # The first period plus 65 samples contains every logical wraparound
    # window. The overlap-save scheduler nevertheless emits only complete
    # 447-result blocks, so extend through the end of block 45 and check only
    # the first 20,000 scores.
    block_count = (PERIOD_SAMPLES + VALID_RESULTS_PER_BLOCK - 1) // (
        VALID_RESULTS_PER_BLOCK
    )
    scheduled_score_count = block_count * VALID_RESULTS_PER_BLOCK
    sample_count = FFT_SAMPLES + (block_count - 1) * VALID_RESULTS_PER_BLOCK
    samples = np.ones((sample_count, 2), dtype=np.int16)
    samples[:, 1] = 0
    for period_start in range(0, sample_count, PERIOD_SAMPLES):
        available = min(FIXTURE_SAMPLES, sample_count - period_start)
        samples[period_start : period_start + available] = fixture[:available]

    xfft_model.XFFT_DATA_BITS = DATA_BITS
    xfft_model.XFFT_FRACTION_BITS = DATA_BITS - 1
    with TemporaryDirectory(prefix="starlink-pss15-m2-xfft-") as temporary:
        model_directory = prepare_installed_cmodel(Path(temporary))
        with XfftBitAccModel(model_directory) as model:
            result = xfft_bitacc_match_scores(samples, coefficients, model)
    all_scores = np.asarray(result.stream.scores, dtype=np.uint8)
    if all_scores.shape != (scheduled_score_count,):
        raise RuntimeError(f"unexpected scheduled score shape {all_scores.shape}")
    scores = all_scores[:PERIOD_SAMPLES]
    maxima = np.flatnonzero(scores == scores.max())
    if int(scores.max()) != 255 or maxima.tolist() != [TEMPLATE_OFFSET]:
        raise RuntimeError(
            f"periodic profile peak changed: max={scores.max()} positions={maxima}"
        )

    samples_payload = packed_ci16(samples)
    scores_payload = ("\n".join(f"{int(value):02x}" for value in scores) + "\n").encode(
        "ascii"
    )
    samples_path = output_directory / "m2_period_samples_ci16.mem"
    scores_path = output_directory / "m2_period_scores_u8.mem"
    samples_path.write_bytes(samples_payload)
    scores_path.write_bytes(scores_payload)

    rng = np.random.default_rng(RANDOM_SEED)
    phases = [0, 1, PERIOD_SAMPLES - 1, 32, 129, 10_000]
    phases.extend(int(value) for value in rng.choice(PERIOD_SAMPLES, 10, replace=False))
    map_start_base = 10_000_000
    matrix = []
    for case_index, phase in enumerate(phases):
        map_start = map_start_base + case_index * TILE_FRAMES * PERIOD_SAMPLES
        delta = (TEMPLATE_OFFSET - phase) % PERIOD_SAMPLES
        injection_start = map_start - delta
        profile = np.roll(scores.astype(np.uint32), phase - TEMPLATE_OFFSET)
        map_values = profile * TILE_FRAMES
        peak_positions = np.flatnonzero(map_values == map_values.max())
        if peak_positions.tolist() != [phase]:
            raise RuntimeError(
                f"case {case_index} peak changed: expected {phase}, got {peak_positions}"
            )
        matrix.append(
            {
                "case": case_index,
                "injection_start": injection_start,
                "map_start": map_start,
                "expected_peak_phase": expected_phase(injection_start, map_start),
                "expected_peak_absolute_index": map_start + phase,
                "peak_value": int(map_values[phase]),
                "runner_up_value": int(np.partition(map_values, -2)[-2]),
            }
        )

    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "sample_rate_hz": 15_000_000,
        "period_samples": PERIOD_SAMPLES,
        "tile_frames": TILE_FRAMES,
        "template_samples": TEMPLATE_SAMPLES,
        "fixture_samples": FIXTURE_SAMPLES,
        "template_offset": TEMPLATE_OFFSET,
        "data_bits": DATA_BITS,
        "input_sample_count": sample_count,
        "score_count": int(scores.size),
        "scheduled_score_count": scheduled_score_count,
        "unique_peak_phase": int(maxima[0]),
        "unique_peak_score": int(scores[maxima[0]]),
        "runner_up_score": int(np.partition(scores, -2)[-2]),
        "score_profile_binary_sha256": sha256_bytes(scores.tobytes(order="C")),
        "samples_memory_sha256": sha256_bytes(samples_payload),
        "scores_memory_sha256": sha256_bytes(scores_payload),
        "forward_block_count": len(result.forward_block_exponents),
        "forward_overflow_blocks": result.forward_overflow_blocks,
        "inverse_overflow_blocks": result.inverse_overflow_blocks,
        "product_overflow_blocks": result.product_overflow_blocks,
        "random_seed": RANDOM_SEED,
        "timing_matrix": matrix,
    }
    evidence_path = output_directory / "m2_periodic_vectors.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "STARLINK_PSS15_M2_VECTORS_PASS "
        f"scores={scores.size} unique_peak={maxima[0]} "
        f"score={scores[maxima[0]]} cases={len(matrix)}"
    )
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_directory", type=Path)
    arguments = parser.parse_args()
    generate(arguments.output_directory.resolve())


if __name__ == "__main__":
    main()
