"""Strict offline GLN1 result decoding; no radio access or precision claims."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from fractions import Fraction

RATE = 60_000_000
SAMPLES = 79_200
MAGIC = 0x474c4e31


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def wide(words: tuple[int, ...], width: int, *, signed: bool) -> int:
    value = sum(word << (32*n) for n, word in enumerate(words))
    if signed and words[-1] >> 31:
        value -= 1 << (32*len(words))
    low, high = (-(1 << (width-1)), 1 << (width-1)) if signed else (0, 1 << width)
    require(low <= value < high, "noncanonical wide integer/sign extension")
    return value


@dataclass(frozen=True)
class NativeResult:
    sequence: int
    tag: int
    start: int
    phase_seed: int
    phase_step: int
    count: int
    fault: int
    reference_sum: tuple[int, int]
    delay_sum: tuple[int, int]
    reference_prefix_integral: tuple[int, int]
    observed_energy: int
    capture_requested: bool
    capture_accepted: int
    capture_delivered: int

    @classmethod
    def decode(cls, payload: bytes) -> NativeResult:
        require(len(payload) == 128, "GLN1 result requires 128 bytes")
        w = struct.unpack("<32I", payload)
        require(w[0] == MAGIC and w[2] != 0, "missing GLN1 head/nonzero tag")
        require(w[25:27] == (RATE, SAMPLES), "unsupported native geometry")
        require(w[27] in (0, 1) and w[30:] == (0, 0), "reserved native flags/words")
        require(w[8] & ~0x7ff == 0, "unknown native fault")
        require(w[7] <= SAMPLES, "arithmetic count exceeds pilot")
        require(w[28] == w[29] <= SAMPLES, "native IQ head has an undrained/invalid prefix")
        if not w[27]:
            require(w[28] == 0, "capture-off result reports native IQ")
        else:
            require(w[7] <= w[28], "arithmetic exceeds original IQ evidence")
        start = w[3] | w[4] << 32
        require(w[7] == 0 or start+w[7]-1 < 1 << 64, "native prefix wraps source index")
        if w[8] == 0:
            require(w[7] == SAMPLES, "fault-free result has incomplete arithmetic")
            require(not w[27] or w[28] == SAMPLES, "fault-free native capture is incomplete")
        reference = tuple(wide(w[i:i+2], 52, signed=True) for i in (9, 11))
        delay = tuple(wide(w[i:i+2], 52, signed=True) for i in (13, 15))
        prefix = tuple(wide(w[i:i+3], 69, signed=True) for i in (17, 20))
        energy = wide(w[23:25], 53, signed=False)
        if w[7] == 0:
            require(not any((*reference, *delay, *prefix, energy)), "empty arithmetic has nonzero moments")
        return cls(w[1], w[2], start, w[5], w[6], w[7], w[8],
            (reference[0], reference[1]), (delay[0], delay[1]), (prefix[0], prefix[1]), energy,
            bool(w[27]), w[28], w[29])

    @property
    def predicted_cfo_hz(self) -> Fraction:
        step = self.phase_step if self.phase_step < 1 << 31 else self.phase_step-(1 << 32)
        return Fraction(step*RATE, 1 << 32)

    def require_native_evidence(self, *, received_bytes: int, expected_tag: int, expected_start: int) -> None:
        """Check saved-byte length and job association, including partial faults.

        This does not attest sample contents, DDR completion, firmware identity,
        analog clipping, receiver calibration or supported pilot precision.
        """
        require(self.capture_requested, "job did not request native evidence")
        require(type(received_bytes) is int and received_bytes == 4*self.capture_delivered,
            "received bytes differ from native FIFO prefix")
        require(self.tag == expected_tag and self.start == expected_start, "native job association mismatch")

    def require_complete(self) -> None:
        require(self.fault == 0 and self.count == SAMPLES, "native arithmetic failed/incomplete")
