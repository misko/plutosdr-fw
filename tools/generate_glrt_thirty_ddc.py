#!/usr/bin/env python3
"""Create the additive 30-MS/s DDC bank without replacing an existing freeze."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.signal import firwin, freqz

ROOT = Path(__file__).resolve().parents[1] / "hdl/library/starlink_glrt"
MANIFEST = "ddc_30000000_coefficients.json"
BANK = "ddc_30000000_q17.mem"


def generate(output: Path) -> None:
    if (output / MANIFEST).exists() or (output / BANK).exists():
        raise SystemExit("30-MS/s coefficient freeze exists; do not overwrite")
    rate, taps = 30_000_000, 73
    h = np.rint(firwin(taps, 2_500_000, fs=rate, window=("kaiser", 8.6)) * 2**17).astype(np.int64)
    h[taps // 2] += 2**17 - h.sum()
    raw = "".join(f"{int(value) & 0x3ffff:05x}\n" for value in h).encode()
    frequency, response = freqz(h / 2**17, worN=262144, fs=rate)
    ripple = float(np.ptp(20 * np.log10(abs(response[frequency <= 1_100_000]))))
    rejection = float(-20 * np.log10(max(abs(response[frequency >= 3_900_000]))))
    if ripple >= 0.002 or rejection <= 78:
        raise ValueError("30-MS/s bank fails the existing DDC response limits")
    spec = dict(file=BANK, sha256=hashlib.sha256(raw).hexdigest(), taps=taps,
                fraction_bits=17, passband_hz=1_100_000, stopband_hz=3_900_000,
                modeled_ripple_db=ripple, modeled_stopband_rejection_db=rejection)
    manifest = dict(schema="starlink-glrt-ddc-coefficients-v1", banks={str(rate): spec})
    output.mkdir(parents=True, exist_ok=True)
    with (output / BANK).open("xb") as stream:
        stream.write(raw)
    with (output / MANIFEST).open("x") as stream:
        stream.write(json.dumps(manifest, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT)
    generate(parser.parse_args().output_dir)


if __name__ == "__main__":
    main()
