#!/usr/bin/env python3
"""Freeze native FPGA pilot templates and DFT twiddles; never replaces a bank."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.starlink_glrt.ddc import BANK_ROOT, RATES
from tests.starlink_glrt.pilot import CODE_SHA256, templates


def main():
    manifest = BANK_ROOT / "native_templates.json"
    if manifest.exists():
        raise SystemExit("native template freeze exists; review before changing scientific goldens")
    files = {}
    for rate in RATES:
        for edge in ("lower", "upper"):
            # One ROM with two independent read ports: exact symbol j is row
            # j+17; rolled-control symbol j is row j. No duplicated ROM bank.
            bank = templates(rate, edge)[np.arange(-17, 64) % 300].astype(np.int64)
            words = ((bank[:, :, 1] & 255) << 8) | (bank[:, :, 0] & 255)
            raw = "".join(f"{int(word):04x}\n" for word in words.flat).encode()
            name = f"pilot_{rate}_{edge}_q7.mem"
            with (BANK_ROOT / name).open("xb") as stream:
                stream.write(raw)
            files[name] = dict(sha256=hashlib.sha256(raw).hexdigest(),
                              words=int(words.size), symbol_samples=int(words.shape[1]))
    phase = 2*np.pi*np.arange(512)/512
    twiddle = np.rint(np.column_stack((np.cos(phase), -np.sin(phase)))*32768).astype(np.int64)
    words = ((twiddle[:, 1] & 0x1ffff) << 17) | (twiddle[:, 0] & 0x1ffff)
    raw = "".join(f"{int(word):09x}\n" for word in words).encode()
    name = "glrt_dft512_q15.mem"
    with (BANK_ROOT / name).open("xb") as stream:
        stream.write(raw)
    files[name] = dict(sha256=hashlib.sha256(raw).hexdigest(), words=512)
    manifest.write_text(json.dumps(dict(schema="starlink-glrt-native-template-v1",
        published_codes_sha256=CODE_SHA256, files=files), indent=2) + "\n")


if __name__ == "__main__":
    main()
