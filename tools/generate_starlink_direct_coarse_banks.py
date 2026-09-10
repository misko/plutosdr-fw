"""Generate banked direct Q15 taps; verify against the retained provenance."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.starlink_oracle.ddc import conditioned_pss, conditioned_pss_x4
from tests.starlink_oracle.fixed import quantize_q15
from tests.starlink_oracle.waveforms import projected_pss


def generate(output: Path) -> None:
    authority = json.loads(
        (
            ROOT
            / "hdl/library/starlink_pss_direct_coarse/evidence/numerical_extended102.json"
        ).read_text()
    )
    words, banks = [], []
    for source in (15, 30, 60):
        for edge in ("upper", "lower"):
            h = quantize_q15(
                projected_pss(15_000_000, edge)
                if source == 15
                else conditioned_pss(edge)
                if source == 30
                else conditioned_pss_x4(edge)
            )
            digest = hashlib.sha256(h.astype("<i2").tobytes()).hexdigest()
            assert (
                digest == authority["kernels"][f"source{source}_{edge}"]["q15_sha256"]
            )
            for group in range(11):
                word = sum(
                    (((int(q) & 65535) << 16) | (int(i) & 65535)) << (32 * lane)
                    for lane, (i, q) in enumerate(h[group * 6 : group * 6 + 6])
                )
                words.append(f"{word:048x}")
            banks.append(
                {
                    "bank": len(banks),
                    "source_msps": source,
                    "edge": edge,
                    "q15_sha256": digest,
                    "energy": int(np.sum(h.astype(np.int64) ** 2)),
                }
            )
    # Independently decode whole little-endian words back to CI16 bytes;
    # this catches lane/component-order mistakes in the packed ROM format.
    for bank_number, bank in enumerate(banks):
        decoded = b"".join(
            int(word, 16).to_bytes(24, "little")
            for word in words[bank_number * 11 : bank_number * 11 + 11]
        )
        assert hashlib.sha256(decoded).hexdigest() == bank["q15_sha256"]
    output.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(words) + "\n"
    (output / "direct_groups_q15.mem").write_text(payload)
    (output / "direct_banks.json").write_text(
        json.dumps(
            {
                "schema": "starlink-direct-coarse-banks-v1",
                "banks": banks,
                "word_count": 66,
                "word_bits": 192,
                "memory_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
    print("DIRECT_BANKS_PASS banks=6 taps_per_bank=66")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    generate(parser.parse_args().output)
