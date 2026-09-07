#!/usr/bin/env python3
"""Generate the sealed 15 MS/s cyclic PSS waveform for a cabled-RF test.

This offline tool only writes a CI16 waveform and its evidence record.  It does
not discover, configure, or transmit with a radio.  The waveform is not
authorized for over-the-air use.
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

from tests.starlink_oracle import (
    complex64_sha256,
    projected_pss,
    quantize_q15,
)

SCHEMA = "plutosdr-fw.starlink-pss15-cabled-waveform.v1"
SAMPLE_RATE_HZ = 15_000_000
FRAME_SAMPLES = 20_000
TEMPLATE_SAMPLES = 66
TEMPLATE_PHASE = 4_096
EDGE = "upper"
MINIMUM_EFFECTIVE_ATTENUATION_DB = 30
WAVEFORM_NAME = "starlink_pss15_upper_cabled_ci16le.bin"
EVIDENCE_NAME = "starlink_pss15_upper_cabled_waveform.json"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _ci16le(values: np.ndarray) -> bytes:
    if values.shape != (FRAME_SAMPLES, 2) or values.dtype != np.int16:
        raise ValueError("waveform must be one 20,000-sample CI16 frame")
    return np.asarray(values, dtype="<i2").tobytes(order="C")


def generate(output_directory: Path) -> dict[str, object]:
    """Create an absent-only waveform/evidence pair and return the evidence."""

    output_directory = output_directory.resolve()
    waveform_path = output_directory / WAVEFORM_NAME
    evidence_path = output_directory / EVIDENCE_NAME
    for path in (waveform_path, evidence_path):
        if path.exists():
            raise FileExistsError(f"refusing to replace existing output: {path}")
    output_directory.mkdir(parents=True, exist_ok=True)

    projected = projected_pss(SAMPLE_RATE_HZ, EDGE)
    template = quantize_q15(projected)
    if template.shape != (TEMPLATE_SAMPLES, 2):
        raise RuntimeError("15 MS/s PSS template geometry changed")
    waveform = np.zeros((FRAME_SAMPLES, 2), dtype=np.int16)
    waveform[TEMPLATE_PHASE : TEMPLATE_PHASE + TEMPLATE_SAMPLES] = template

    template_payload = np.asarray(template, dtype="<i2").tobytes(order="C")
    waveform_payload = _ci16le(waveform)
    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "schema_version": 1,
        "claim_scope": "deterministic_cabled_rf_stimulus_only",
        "offline_generation_only": True,
        "cabled_only": True,
        "over_the_air_authorized": False,
        "transmitter_configuration_included": False,
        "minimum_effective_attenuation_db": MINIMUM_EFFECTIVE_ATTENUATION_DB,
        "sample_format": "signed-ci16-little-endian-interleaved-iq",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "cyclic": True,
        "frame_samples": FRAME_SAMPLES,
        "frame_duration_ns_numerator": FRAME_SAMPLES * 1_000_000_000,
        "frame_duration_ns_denominator": SAMPLE_RATE_HZ,
        "edge": EDGE,
        "template_samples": TEMPLATE_SAMPLES,
        "template_phase_bin": TEMPLATE_PHASE,
        "nominal_detector_peak_phase_bin": TEMPLATE_PHASE,
        "nonzero_complex_samples": int(np.count_nonzero(np.any(waveform, axis=1))),
        "nonzero_components": int(np.count_nonzero(waveform)),
        "minimum_component": int(waveform.min()),
        "maximum_component": int(waveform.max()),
        "maximum_absolute_component": int(
            np.abs(waveform.astype(np.int32)).max()
        ),
        "quantized_template_energy": int(
            np.sum(template.astype(np.int64) ** 2, dtype=np.int64)
        ),
        "projected_template_complex64_sha256": complex64_sha256(projected),
        "quantized_template_ci16le_sha256": _sha256(template_payload),
        "waveform": {
            "name": WAVEFORM_NAME,
            "bytes": len(waveform_payload),
            "sha256": _sha256(waveform_payload),
        },
    }
    waveform_path.write_bytes(waveform_payload)
    os.chmod(waveform_path, 0o600)
    evidence_path.write_text(
        json.dumps(
            evidence, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n",
        encoding="utf-8",
    )
    os.chmod(evidence_path, 0o600)
    print(
        "STARLINK_PSS15_CABLED_WAVEFORM_PASS "
        f"samples={FRAME_SAMPLES} phase={TEMPLATE_PHASE} "
        f"sha256={evidence['waveform']['sha256']}"
    )
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    arguments = parser.parse_args()
    generate(arguments.output_directory)


if __name__ == "__main__":
    main()
