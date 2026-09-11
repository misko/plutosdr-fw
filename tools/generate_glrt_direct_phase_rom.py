"""Pack phase-major Q11 coefficients into bounded per-sample FPGA ROM rows."""
from __future__ import annotations

import argparse
from pathlib import Path


def pack_phase_rom(encoded: bytes, *, phases: int, samples: int) -> bytes:
    if type(phases) is not int or phases not in (1, 2, 4, 8):
        raise ValueError("unsupported direct reference phase count")
    if type(samples) is not int or not 1 <= samples <= 79200:
        raise ValueError("invalid native pilot sample count")
    lines = encoded.splitlines()
    if len(lines) != phases*samples or any(
        len(line) != 16 or any(c not in b"0123456789abcdefABCDEF" for c in line)
        for line in lines
    ):
        raise ValueError("phase-major input must contain complete 64-bit coefficient words")
    words = [int(line,16) for line in lines]
    return "".join(
        f"{sum(words[p*samples+n] << (64*p) for p in range(phases)):0{16*phases}x}\n"
        for n in range(samples)
    ).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--phases", type=int, required=True)
    parser.add_argument("--samples", type=int, required=True)
    args = parser.parse_args()
    packed = pack_phase_rom(args.input.read_bytes(), phases=args.phases, samples=args.samples)
    with args.output.open("xb") as output:
        output.write(packed)


if __name__ == "__main__":
    main()
