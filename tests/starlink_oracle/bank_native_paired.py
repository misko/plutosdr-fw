"""Independent native TRACK_ONE golden for the frozen shared-source smoke.

This prearranged center is not causal acquisition. No RTL output is an oracle.
The original paired source, coarse vectors, kernel and pilot bytes are read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from .fixed import fixed_correlate_ci16, quantize_q15
from .waveforms import complex64_sha256, projected_pss

FIRST = (1 << 33) - 16
CENTER = FIRST + 447
REQUEST = 0x15004470
GENERATION = 0x15000001
PROFILES = {447: (REQUEST, 0), 520: (0x15005200, -17)}
FILES = {"native_coefficients_q15.mem": (66, 8),
         "native_expected_packet.mem": (26, 8)}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_words(path: Path, count: int, width: int) -> list[int]:
    import re
    rows = path.read_text(encoding="ascii").splitlines()
    if len(rows) != count or any(re.fullmatch(rf"[0-9a-fA-F]{{{width}}}", r) is None
                                 for r in rows):
        raise ValueError(f"malformed geometry: {path.name}")
    return [int(row, 16) for row in rows]


def derive(pilot_directory: Path, *, anchor: int = 447) -> tuple[dict, dict[str, list[int]]]:
    if type(anchor) is not int or anchor not in PROFILES:
        raise ValueError("native anchor must be literal447 or520")
    request, expected_lag = PROFILES[anchor]
    center = FIRST + anchor
    packed = np.asarray(read_words(pilot_directory / "paired_source_ci16.mem", 4096, 8),
                        dtype=np.uint32)
    source = np.column_stack((packed & 65535, packed >> 16)).astype(np.uint16).view(np.int16)
    template = projected_pss(15_000_000, "upper")
    coefficients = quantize_q15(template)
    # Source rows are qqqqiiii; native coefficient files retain iiiiqqqq.
    coefficient_words = [(int(i) & 65535) << 16 | (int(q) & 65535)
                         for i, q in coefficients]
    capture_offset = 768 + anchor - 32
    capture = source[capture_offset:capture_offset + 130]
    rows = {lag: fixed_correlate_ci16(capture[lag + 32:lag + 98], coefficients)
            for lag in range(-32, 33)}
    for lag in range(-30, 31):
        row = rows[lag]
        if not (0 < row.sample_energy < 1 << 38 and
                0 < row.coefficient_energy < 1 << 31 and
                -(1 << 38) <= row.real < 1 << 38 and
                -(1 << 38) <= row.imag < 1 << 38 and row.saturation_events == 0):
            raise ValueError(f"qualified native tuple {lag} violates DSP tuple_score_legal")
    winner = -30
    for lag in range(-29, 31):
        candidate, retained = rows[lag], rows[winner]
        # Constant Eh is excluded from TRACK_ONE's exact P/Ex comparison.
        # Strict greater-than retains the earliest lag on an exact tie.
        if candidate.correlation_power * retained.sample_energy > (
                retained.correlation_power * candidate.sample_energy):
            winner = lag
    result = rows[winner]
    if result.sample_energy <= 0 or result.saturation_events:
        raise ValueError("healthy smoke needs positive energy and no saturation")
    if winner != expected_lag or not np.array_equal(source[768 + 447:768 + 513], coefficients):
        raise ValueError("frozen zero-CFO control/template identity changed")
    power, energy = result.correlation_power, result.sample_energy
    values = [0x31535350, 0x1A010001, request, center, center >> 32,
              center, center >> 32, winner, center + winner, (center + winner) >> 32,
              GENERATION, result.real, result.real >> 32, result.imag, result.imag >> 32,
              energy, energy >> 32, result.coefficient_energy, result.coefficient_energy >> 32,
              result.saturation_events, power, power >> 32, power >> 64,
              energy, energy >> 32, energy >> 64]
    payloads = {"native_coefficients_q15.mem": coefficient_words,
                "native_expected_packet.mem": [value & 0xFFFFFFFF for value in values]}
    manifest = {
        "schema": "starlink-bank-native-paired-smoke-v1",
        "scope": "same-original-source static-anchor numerical smoke, NOT causal acquisition",
        "source_count": 4096, "source_rate_hz": 15_000_000,
        "source_first_index": FIRST - 768, "anchor_offset": anchor, "center_index": center,
        "capture_bounds": [center - 32, center + 98], "qualified_lags": [-30, 30],
        "raw_lags": [-32, 32], "tap_count": 66, "packet_words": 26,
        "request_id": request, "coefficient_generation": GENERATION,
        "coefficient_energy": result.coefficient_energy, "winner_lag": winner,
        "coefficient_cfo_hz": 0, "template_complex64_sha256": complex64_sha256(template),
        "coefficient_ci16le_sha256": hashlib.sha256(coefficients.astype("<i2").tobytes()).hexdigest(),
        "paired_source_sha256": digest(pilot_directory / "paired_source_ci16.mem"),
        "paired_pilot_binary_sha256": digest(pilot_directory / "paired_pilot_expected.ci16"),
        "oracle_sha256": {name: digest(Path(__file__).with_name(name))
                          for name in ("bank_native_paired.py", "fixed.py", "waveforms.py", "numerology.py")},
        "tie_rule": "strict P_candidate*Ex_retained > P_retained*Ex_candidate; earliest lag wins",
        "accumulator_rule": "fixed-correlator-v1 signed48 saturation after each complete tap",
        "qualified_tuple_legality": {
            "checked": 61, "positive_Ex_Eh": True, "saturation_events": 0,
            "correlation_signed39": True, "Ex_unsigned38": True, "Eh_unsigned31": True,
            "max_absolute_component": max(max(abs(rows[k].real), abs(rows[k].imag))
                                          for k in range(-30, 31)),
            "max_sample_energy": max(rows[k].sample_energy for k in range(-30, 31)),
        },
    }
    return manifest, payloads


def generate(pilot_directory: Path, output: Path, *, anchor: int = 447) -> dict:
    if output.exists() or output.is_symlink():
        raise ValueError("refusing to overwrite native evidence")
    manifest, payloads = derive(pilot_directory, anchor=anchor)
    output.mkdir(parents=True)
    for name, values in payloads.items():
        (output / name).write_text("".join(f"{value:08x}\n" for value in values))
    manifest["generated_sha256"] = {name: digest(output / name) for name in FILES}
    (output / "native_oracle.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def verify(pilot_directory: Path, output: Path, *, anchor: int = 447) -> dict:
    manifest, payloads = derive(pilot_directory, anchor=anchor)
    if {p.name for p in output.iterdir()} != {*FILES, "native_oracle.json"}:
        raise ValueError("native oracle inventory mismatch")
    for name, (rows, width) in FILES.items():
        if read_words(output / name, rows, width) != payloads[name]:
            raise ValueError(f"independent native golden mismatch: {name}")
    manifest["generated_sha256"] = {name: digest(output / name) for name in FILES}
    if json.loads((output / "native_oracle.json").read_text()) != manifest:
        raise ValueError("native manifest does not match recomputed independent oracle")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot_directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--anchor", type=int, choices=(447, 520), default=447)
    args = parser.parse_args()
    receipt = (verify if args.verify else generate)(args.pilot_directory, args.output, anchor=args.anchor)
    print(f"BANK_NATIVE_ORACLE_VERIFIED source=4096 taps=66 packet_words=26 anchor={args.anchor} winner_lag={receipt['winner_lag']}")
