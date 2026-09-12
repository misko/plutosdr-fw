"""Losslessly pack coefficients into 4096-row, 9-bit-column block ROMs."""
from __future__ import annotations

import argparse
from pathlib import Path


def pack_direct_rom(encoded: bytes, *, phases: int, samples: int) -> bytes:
    if type(phases) is not int or phases not in (1, 2, 4, 8):
        raise ValueError("unsupported phase count")
    if type(samples) is not int or not 1 <= samples <= 79200:
        raise ValueError("invalid sample count")
    rows = encoded.splitlines()
    if len(rows) != phases*samples or any(len(row) != 16 or
        any(c not in b"0123456789abcdefABCDEF" for c in row) for row in rows):
        raise ValueError("requires complete phase-major 64-bit coefficient words")
    # Streaming little-bit-endian packing, with no arithmetic/quantization.
    packed, bits, width = [], 0, 0
    for row in rows:
        bits |= int(row,16) << width
        width += 64
        while width >= 9:
            packed.append(bits & 511)
            bits >>= 9
            width -= 9
    if width:
        packed.append(bits)
    # The reader fetches eight words and may prefetch two unused guard words.
    packed.extend((0,0))
    banks=(len(packed)+4095)//4096
    packed.extend([0]*(banks*4096-len(packed)))
    # One 36-Kbit block per column, with a narrow selection bus. An unbounded
    # deep array can map to a power-of-two depth and waste over a third of RAM.
    digits=(9*banks+3)//4
    return "".join(f"{sum(packed[b*4096+n] << (9*b) for b in range(banks)):0{digits}x}\n"
        for n in range(4096)).encode()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--phases",type=int,required=True)
    parser.add_argument("--samples",type=int,required=True)
    args=parser.parse_args()
    result=pack_direct_rom(args.input.read_bytes(),phases=args.phases,samples=args.samples)
    with args.output.open("xb") as stream:stream.write(result)


if __name__ == "__main__":
    main()
