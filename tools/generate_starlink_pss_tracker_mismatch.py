#!/usr/bin/env python3
"""Generate one energy-identical, deliberately mismatched PSS coefficient bank.

The control applies a deterministic QPSK phase mask to every signed-CI16 tap.
Every output tap is therefore an exact rotation of its matched input tap, so
coefficient energy is identical without rescaling or rounding.  This is an
offline, absent-only generator and never accesses a radio.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

SCHEMA = "plutosdr-fw.starlink-pss-tracker-energy-matched-control.v1"
MASK_DOMAIN = b"starlink-pss-fine-mismatch-v1"
SUPPORTED_RATES_MSPS = (15, 30, 60)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _identity(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    payload = resolved.read_bytes()
    return {"path": str(resolved), "bytes": len(payload), "sha256": _sha256(payload)}


def _signed16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def _read_matched(path: Path, *, rate_msps: int) -> list[tuple[int, int]]:
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("matched coefficient file is not readable ASCII") from error
    expected = 66 * (rate_msps // 15)
    if len(lines) != expected or any(
        len(line) != 8
        or line.lower() != line
        or any(character not in "0123456789abcdef" for character in line)
        for line in lines
    ):
        raise ValueError(
            f"{rate_msps} MS/s matched bank must contain {expected} CI16 taps"
        )
    words = [int(line, 16) for line in lines]
    return [(_signed16(word >> 16), _signed16(word & 0xFFFF)) for word in words]


def _mask_bytes(count: int) -> bytes:
    result = bytearray()
    block = 0
    while len(result) < count:
        result.extend(
            hashlib.sha256(MASK_DOMAIN + block.to_bytes(4, "little")).digest()
        )
        block += 1
    return bytes(result[:count])


def _rotate(value: tuple[int, int], phase: int) -> tuple[int, int]:
    i_value, q_value = value
    if phase == 0:
        result = i_value, q_value
    elif phase == 1:
        result = -q_value, i_value
    elif phase == 2:
        result = -i_value, -q_value
    elif phase == 3:
        result = q_value, -i_value
    else:  # pragma: no cover - phase is masked to two bits
        raise AssertionError("invalid QPSK phase")
    if any(not -32768 <= component <= 32767 for component in result):
        raise ValueError("exact QPSK rotation would overflow signed CI16")
    return result


def _memory_payload(values: list[tuple[int, int]]) -> bytes:
    return "".join(
        f"{i_value & 0xFFFF:04x}{q_value & 0xFFFF:04x}\n" for i_value, q_value in values
    ).encode("ascii")


def _binary_payload(values: list[tuple[int, int]]) -> bytes:
    payload = bytearray()
    for i_value, q_value in values:
        payload.extend(int(i_value).to_bytes(2, "little", signed=True))
        payload.extend(int(q_value).to_bytes(2, "little", signed=True))
    return bytes(payload)


def _energy(values: list[tuple[int, int]]) -> int:
    return sum(i_value * i_value + q_value * q_value for i_value, q_value in values)


def _maximum_overlap_correlation(
    matched: list[tuple[int, int]],
    mismatched: list[tuple[int, int]],
    *,
    aperture: int,
) -> dict[str, float | int]:
    matched_complex = [complex(i_value, q_value) for i_value, q_value in matched]
    mismatch_complex = [complex(i_value, q_value) for i_value, q_value in mismatched]
    values: list[tuple[float, int]] = []
    count = len(matched_complex)
    for lag in range(-aperture, aperture + 1):
        if lag >= 0:
            signal = matched_complex[lag:]
            control = mismatch_complex[: count - lag]
        else:
            signal = matched_complex[: count + lag]
            control = mismatch_complex[-lag:]
        correlation = sum(
            a_value.conjugate() * b_value
            for a_value, b_value in zip(control, signal, strict=True)
        )
        signal_energy = sum(abs(value) ** 2 for value in signal)
        control_energy = sum(abs(value) ** 2 for value in control)
        normalized = abs(correlation) ** 2 / (signal_energy * control_energy)
        if not math.isfinite(normalized):
            raise ValueError("control correlation diagnostic is not finite")
        values.append((normalized, lag))
    maximum, lag = max(values)
    return {
        "aperture_samples": aperture,
        "maximum_overlap_normalized_score": maximum,
        "maximum_overlap_lag": lag,
    }


def generate(
    output_directory: Path,
    *,
    matched_path: Path,
    rate_msps: int,
) -> dict[str, Any]:
    if rate_msps not in SUPPORTED_RATES_MSPS:
        raise ValueError(f"rate_msps must be one of {SUPPORTED_RATES_MSPS}")
    matched = _read_matched(matched_path, rate_msps=rate_msps)
    matched_identity = _identity(matched_path)
    mask = _mask_bytes(len(matched))
    phases = [value & 3 for value in mask]
    mismatched = [
        _rotate(value, phase) for value, phase in zip(matched, phases, strict=True)
    ]
    matched_energy = _energy(matched)
    mismatch_energy = _energy(mismatched)
    if mismatch_energy != matched_energy or mismatched == matched:
        raise ValueError("energy-matched control construction failed")

    output_directory = output_directory.expanduser().resolve()
    stem = f"starlink_pss{rate_msps}_energy_matched_qpsk_mismatch_v1"
    coefficient_path = output_directory / f"{stem}.mem"
    evidence_path = output_directory / f"{stem}.json"
    if coefficient_path.exists() or evidence_path.exists():
        raise FileExistsError("refusing to replace an existing control artifact")
    output_directory.mkdir(parents=True, exist_ok=True)
    memory_payload = _memory_payload(mismatched)
    binary_payload = _binary_payload(mismatched)
    diagnostic = _maximum_overlap_correlation(
        matched,
        mismatched,
        aperture=2 * rate_msps,
    )
    evidence: dict[str, Any] = {
        "schema": SCHEMA,
        "schema_version": 1,
        "claim_scope": "offline_energy_identical_mismatched_tracker_control_only",
        "offline_generation_only": True,
        "radio_access": False,
        "rate_msps": rate_msps,
        "sample_rate_hz": rate_msps * 1_000_000,
        "tap_count": len(matched),
        "matched": matched_identity,
        "matched_coefficient_energy": matched_energy,
        "control_coefficient_energy": mismatch_energy,
        "energy_exact": mismatch_energy == matched_energy,
        "mask": {
            "construction": "sha256-domain-stream-low-two-bits-to-qpsk-rotation",
            "domain_utf8": MASK_DOMAIN.decode("ascii"),
            "domain_sha256": _sha256(MASK_DOMAIN),
            "stream_sha256": _sha256(mask),
            "phase_counts": [phases.count(index) for index in range(4)],
        },
        "correlation_diagnostic": diagnostic,
        "control_ci16le_sha256": _sha256(binary_payload),
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
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(evidence_path, 0o600)
    print(
        "STARLINK_PSS_TRACKER_MISMATCH_PASS "
        f"rate_msps={rate_msps} taps={len(matched)} energy={mismatch_energy} "
        f"sha256={evidence['memory_file']['sha256']}"
    )
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--matched", type=Path, required=True)
    parser.add_argument(
        "--rate-msps", type=int, choices=SUPPORTED_RATES_MSPS, required=True
    )
    arguments = parser.parse_args()
    generate(
        arguments.output_directory,
        matched_path=arguments.matched,
        rate_msps=arguments.rate_msps,
    )


if __name__ == "__main__":
    main()
