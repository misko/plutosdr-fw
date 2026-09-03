#!/usr/bin/env python3
"""Generate deterministic bit-exact vectors for the 60-to-15 MS/s cascade."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.starlink_oracle import ddc_x4_contract_sha256, x4_ddc_ci16


SCHEMA = "starlink-pss60-x4-ddc-vectors-v1"
SAMPLE_COUNT = 500
RANDOM_SEED = 0x60DDC15


def _lines(words: list[int], bits: int) -> str:
    digits = (bits + 3) // 4
    return "".join(f"{word:0{digits}x}\n" for word in words)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generate(output_directory: Path) -> dict[str, object]:
    output_directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(RANDOM_SEED)
    samples = rng.integers(-32768, 32768, size=(SAMPLE_COUNT, 2), dtype=np.int16)
    indexes = np.arange(2000, 2000 + SAMPLE_COUNT, dtype=np.uint64)
    indexes[350:] += 7
    gaps = np.zeros(SAMPLE_COUNT, dtype=np.bool_)
    gaps[[0, 180]] = True

    input_words = [
        (int(gap) << 96)
        | (int(index) << 32)
        | ((int(q_value) & 0xFFFF) << 16)
        | (int(i_value) & 0xFFFF)
        for (i_value, q_value), index, gap in zip(
            samples, indexes, gaps, strict=True
        )
    ]
    input_bytes = _lines(input_words, 97).encode("ascii")
    (output_directory / "ddc_x4_input.mem").write_bytes(input_bytes)

    edges: dict[str, object] = {}
    for edge in ("lower", "upper"):
        result = x4_ddc_ci16(
            samples,
            input_indexes=indexes,
            edge=edge,
            gap_before=gaps,
        )
        output_words = [
            (int(gap) << 96)
            | (int(index) << 32)
            | ((int(q_value) & 0xFFFF) << 16)
            | (int(i_value) & 0xFFFF)
            for (i_value, q_value), index, gap in zip(
                result.samples_iq,
                result.output_indexes,
                result.output_gaps,
                strict=True,
            )
        ]
        if len(output_words) > 250:
            raise RuntimeError("x4 DDC vector set exceeds testbench storage")
        output_bytes = _lines(
            output_words + [0] * (250 - len(output_words)), 97
        ).encode("ascii")
        summary_words = [
            result.emitted_samples,
            result.accepted_samples,
            result.discontinuities,
            result.saturation_events,
        ]
        summary_bytes = _lines(summary_words, 32).encode("ascii")
        (output_directory / f"ddc_x4_{edge}_expected.mem").write_bytes(output_bytes)
        (output_directory / f"ddc_x4_{edge}_summary.mem").write_bytes(summary_bytes)
        edges[edge] = {
            "stage_60_to_30_outputs": result.stage_60_to_30.samples_iq.shape[0],
            "outputs": result.emitted_samples,
            "discontinuities": result.discontinuities,
            "saturation_events": result.saturation_events,
            "expected_text_sha256": _sha256(output_bytes),
            "summary_text_sha256": _sha256(summary_bytes),
        }

    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "random_seed": RANDOM_SEED,
        "sample_count": SAMPLE_COUNT,
        "ddc_x4_contract_sha256": ddc_x4_contract_sha256(),
        "input_text_sha256": _sha256(input_bytes),
        "edges": edges,
    }
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    ).encode("ascii")
    (output_directory / "ddc_x4_manifest.json").write_bytes(manifest_bytes)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    manifest = generate(args.output_directory)
    print(
        "STARLINK_PSS60_DDC_VECTORS_PASS "
        f"samples={manifest['sample_count']} "
        f"contract_sha256={manifest['ddc_x4_contract_sha256']}"
    )


if __name__ == "__main__":
    main()
