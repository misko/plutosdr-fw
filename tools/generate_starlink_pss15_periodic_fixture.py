#!/usr/bin/env python3
"""Generate the exact 130-sample Stage-15 periodic-injection fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.starlink_oracle import projected_pss, quantize_q15
from tests.starlink_oracle.waveforms import complex64_sha256

SCHEMA = "starlink-pss15-periodic-injection-fixture-v1"
SAMPLE_RATE_HZ = 15_000_000
EDGE = "upper"
FIXTURE_SAMPLES = 130
TEMPLATE_OFFSET = 32
PERIOD_SAMPLES = 20_000
REPETITIONS = 130


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def generate(output_directory: Path) -> dict[str, object]:
    output_directory.mkdir(parents=True, exist_ok=True)
    template = projected_pss(SAMPLE_RATE_HZ, EDGE)
    coefficients = quantize_q15(template)
    if coefficients.shape != (66, 2):
        raise RuntimeError(f"unexpected PSS shape {coefficients.shape}")

    fixture = np.ones((FIXTURE_SAMPLES, 2), dtype=np.int16)
    fixture[:, 1] = 0
    fixture[TEMPLATE_OFFSET : TEMPLATE_OFFSET + coefficients.shape[0]] = coefficients

    lines = [f"{int(i) & 0xFFFF:04x}{int(q) & 0xFFFF:04x}" for i, q in fixture]
    memory_payload = ("\n".join(lines) + "\n").encode("ascii")
    canonical_payload = np.asarray(fixture, dtype="<i2").tobytes(order="C")
    coefficient_payload = np.asarray(coefficients, dtype="<i2").tobytes(order="C")

    memory_path = output_directory / "upper_edge_pss_periodic_fixture_ci16.mem"
    memory_path.write_bytes(memory_payload)
    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "edge": EDGE,
        "fixture_samples": FIXTURE_SAMPLES,
        "template_samples": int(coefficients.shape[0]),
        "template_offset": TEMPLATE_OFFSET,
        "period_samples": PERIOD_SAMPLES,
        "repetitions": REPETITIONS,
        "last_sample_offset": (REPETITIONS - 1) * PERIOD_SAMPLES + FIXTURE_SAMPLES - 1,
        "inter_fixture_i": 1,
        "inter_fixture_q": 0,
        "projected_pss_complex64_sha256": complex64_sha256(template),
        "coefficient_ci16_sha256": sha256_bytes(coefficient_payload),
        "fixture_ci16_sha256": sha256_bytes(canonical_payload),
        "fixture_memory_sha256": sha256_bytes(memory_payload),
        "expected_score_offset": TEMPLATE_OFFSET,
        "expected_exact_match_score_u8": 255,
    }
    evidence_path = output_directory / "upper_edge_pss_periodic_fixture_ci16.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "STARLINK_PSS15_PERIODIC_FIXTURE_PASS "
        f"samples={FIXTURE_SAMPLES} template_offset={TEMPLATE_OFFSET} "
        f"memory_sha256={evidence['fixture_memory_sha256']}"
    )
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_directory", type=Path)
    arguments = parser.parse_args()
    generate(arguments.output_directory.resolve())


if __name__ == "__main__":
    main()
