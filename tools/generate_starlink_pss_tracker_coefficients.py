#!/usr/bin/env python3
"""Generate an exact full-rate PSS coefficient bank for FPGA tracking.

This is an offline, absent-only generator.  It has no radio or IIO access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.starlink_oracle import complex64_sha256, projected_pss, quantize_q15

SCHEMA = "plutosdr-fw.starlink-pss-tracker-coefficients.v1"
SUPPORTED_RATES_MSPS = (15, 30, 60)
SUPPORTED_EDGES = ("lower", "upper")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _pack_ci16_lines(values: np.ndarray) -> bytes:
    return "".join(
        f"{int(i) & 0xffff:04x}{int(q) & 0xffff:04x}\n" for i, q in values
    ).encode("ascii")


def generate(
    output_directory: Path,
    *,
    rate_msps: int,
    edge: str = "upper",
    cfo_hz: float = 0.0,
) -> dict[str, object]:
    if rate_msps not in SUPPORTED_RATES_MSPS:
        raise ValueError(f"rate_msps must be one of {SUPPORTED_RATES_MSPS}")
    if edge not in SUPPORTED_EDGES:
        raise ValueError(f"edge must be one of {SUPPORTED_EDGES}")
    if not np.isfinite(cfo_hz):
        raise ValueError("cfo_hz must be finite")

    output_directory = output_directory.resolve()
    stem = f"starlink_pss{rate_msps}_{edge}_{cfo_hz:+.3f}hz"
    coefficient_path = output_directory / f"{stem}_coefficients_q15.mem"
    evidence_path = output_directory / f"{stem}_coefficients.json"
    for path in (coefficient_path, evidence_path):
        if path.exists():
            raise FileExistsError(f"refusing to replace existing output: {path}")
    output_directory.mkdir(parents=True, exist_ok=True)

    sample_rate_hz = rate_msps * 1_000_000
    projected = np.asarray(projected_pss(sample_rate_hz, edge), dtype=np.complex128)
    sample_indices = np.arange(projected.size, dtype=np.float64)
    conditioned = projected * np.exp(
        2j * np.pi * cfo_hz * sample_indices / sample_rate_hz
    )
    coefficients = quantize_q15(conditioned)
    binary_payload = np.asarray(coefficients, dtype="<i2").tobytes(order="C")
    memory_payload = _pack_ci16_lines(coefficients)
    coefficient_energy = int(
        np.sum(coefficients.astype(np.int64) ** 2, dtype=np.int64)
    )
    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "schema_version": 1,
        "claim_scope": "offline_full_rate_tracker_coefficient_generation_only",
        "offline_generation_only": True,
        "radio_access": False,
        "sample_rate_hz": sample_rate_hz,
        "rate_msps": rate_msps,
        "edge": edge,
        "cfo_hz": cfo_hz,
        "tap_count": int(coefficients.shape[0]),
        "coefficient_energy": coefficient_energy,
        "conditioned_template_complex64_sha256": complex64_sha256(conditioned),
        "coefficient_ci16le_sha256": _sha256(binary_payload),
        "memory_file": {
            "name": coefficient_path.name,
            "bytes": len(memory_payload),
            "sha256": _sha256(memory_payload),
            "line_encoding": "iiiiqqqq hexadecimal; signed CI16; one tap per line",
        },
    }
    coefficient_path.write_bytes(memory_payload)
    os.chmod(coefficient_path, 0o600)
    evidence_path.write_text(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.chmod(evidence_path, 0o600)
    print(
        "STARLINK_PSS_TRACKER_COEFFICIENTS_PASS "
        f"rate_msps={rate_msps} taps={coefficients.shape[0]} "
        f"energy={coefficient_energy} sha256={evidence['memory_file']['sha256']}"
    )
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--rate-msps", type=int, choices=SUPPORTED_RATES_MSPS, required=True)
    parser.add_argument("--edge", choices=SUPPORTED_EDGES, default="upper")
    parser.add_argument("--cfo-hz", type=float, default=0.0)
    arguments = parser.parse_args()
    generate(
        arguments.output_directory,
        rate_msps=arguments.rate_msps,
        edge=arguments.edge,
        cfo_hz=arguments.cfo_hz,
    )


if __name__ == "__main__":
    main()
