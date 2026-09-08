#!/usr/bin/env python3
"""Create the first GLRT DDC coefficient bank; refuses to overwrite a freeze."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.signal import firwin, freqz

ROOT = Path(__file__).resolve().parents[1] / "hdl/library/starlink_glrt"


def main() -> None:
    manifest = ROOT / "ddc_coefficients.json"
    if manifest.exists():
        raise SystemExit("coefficient freeze exists; do not regenerate qualification goldens")
    ROOT.mkdir(parents=True, exist_ok=True)
    banks = {}
    for rate, taps, cutoff, stop in (
        (5_000_000, 201, 1_175_000, 1_250_000),
        (10_000_000, 25, 2_500_000, 3_900_000),
        (25_000_000, 61, 2_500_000, 3_900_000),
        (60_000_000, 145, 2_500_000, 3_900_000),
    ):
        h = np.rint(firwin(taps, cutoff, fs=rate, window=("kaiser", 8.6)) * 2**17).astype(np.int64)
        h[taps // 2] += 2**17 - h.sum()
        raw = "".join(f"{int(v) & 0x3ffff:05x}\n" for v in h).encode()
        name = f"ddc_{rate}_q17.mem"
        with (ROOT / name).open("xb") as stream:
            stream.write(raw)
        frequency, response = freqz(h / 2**17, worN=262144, fs=rate)
        passband = 20 * np.log10(abs(response[frequency <= 1_100_000]))
        banks[str(rate)] = dict(file=name, sha256=hashlib.sha256(raw).hexdigest(),
            taps=taps, fraction_bits=17, passband_hz=1_100_000, stopband_hz=stop,
            modeled_ripple_db=float(np.ptp(passband)),
            modeled_stopband_rejection_db=float(-20 * np.log10(max(abs(response[frequency >= stop])))))
    manifest.write_text(json.dumps(dict(schema="starlink-glrt-ddc-coefficients-v1", banks=banks), indent=2) + "\n")


if __name__ == "__main__":
    main()
