"""Strict GLS1 decoding and finite prediction association, without radio I/O."""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from fractions import Fraction

if __package__:
    from .starlink_glrt_native_abi import RATE, SAMPLES, require, wide
else:
    from starlink_glrt_native_abi import RATE, SAMPLES, require, wide

MAGIC = 0x474C5331
VERSION = 0x10000
CAPACITY = 64


def _words(text: str, prefix: str, count: int) -> tuple[int, ...]:
    fields = text.split()
    require(len(fields) == count+2 and fields[0] == prefix, "invalid GLS1 text envelope")
    require(all(re.fullmatch(r"[0-9a-fA-F]{8}", item) for item in fields[1:]),
            "GLS1 requires canonical u32 hexadecimal words")
    require(int(fields[1], 16) == VERSION, "unsupported GLS1 version")
    return tuple(int(item, 16) for item in fields[2:])


@dataclass(frozen=True)
class ScheduleBatch:
    epoch: int
    tag: int
    start: int
    fraction: int
    period: int
    step: int
    delta: int
    seed: int
    repeats: int
    expires: int

    def __post_init__(self) -> None:
        for name, bits in (("epoch",32),("tag",32),("start",64),("fraction",16),
                           ("period",48),("step",48),("delta",48),("seed",32),
                           ("repeats",8),("expires",64)):
            value = getattr(self, name)
            require(type(value) is int and 0 <= value < 1 << bits, f"invalid batch {name}")
        require(self.epoch > 0 and self.tag > 0 and 1 <= self.repeats <= 64,
                "batch requires epoch, tag and bounded repeat count")
        require(self.start >= 512 and self.expires >= self.start, "invalid batch source interval")
        require((SAMPLES+128)*65536 <= self.period <= 81000*65536,
                "unsupported native repeat period")

    def encode(self) -> str:
        """Exact Linux native_schedule_submit payload; no implicit retry."""
        return " ".join(f"{getattr(self, name):x}" for name in (
            "epoch", "tag", "start", "fraction", "period", "step", "delta",
            "seed", "repeats", "expires"))+"\n"

    def prediction(self, repeat: int) -> tuple[int, int]:
        require(type(repeat) is int and 0 <= repeat < self.repeats, "repeat outside batch")
        start = round(Fraction(self.start*65536+self.fraction+repeat*self.period, 65536))
        step = round(Fraction((self.step+repeat*self.delta) % 2**48, 65536)) % 2**32
        return start, step


@dataclass(frozen=True)
class ScheduledResult:
    epoch: int
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
    repeat: int

    @classmethod
    def decode(cls, payload: bytes, *, epoch: int) -> ScheduledResult:
        require(type(epoch) is int and 0 < epoch < 2**32, "missing scheduled source epoch")
        require(len(payload) == 128, "GLS1 result requires 128 bytes")
        w = struct.unpack("<32I", payload)
        require(w[0] == MAGIC and w[2] != 0, "missing GLS1 head/nonzero tag")
        require(w[25:27] == (RATE, SAMPLES), "unsupported scheduled geometry")
        require(w[27] < 64 and w[28:] == (0, 0, 0, 0), "invalid repeat/reserved words")
        require(w[8] & ~0x3ff == 0, "unknown scheduled fault")
        require(w[7] <= SAMPLES and (w[8] != 0 or w[7] == SAMPLES),
                "invalid scheduled arithmetic count")
        start = w[3] | w[4] << 32
        require(not w[7] or start+w[7]-1 < 2**64, "scheduled prefix wraps source index")
        reference = tuple(wide(w[i:i+2], 52, signed=True) for i in (9, 11))
        delay = tuple(wide(w[i:i+2], 52, signed=True) for i in (13, 15))
        prefix = tuple(wide(w[i:i+3], 69, signed=True) for i in (17, 20))
        energy = wide(w[23:25], 53, signed=False)
        require(w[7] != 0 or not any((*reference, *delay, *prefix, energy)),
                "empty scheduled result has nonzero moments")
        return cls(epoch, w[1], w[2], start, w[5], w[6], w[7], w[8],
                   reference, delay, prefix, energy, w[27])

    @classmethod
    def from_sysfs(cls, text: str) -> ScheduledResult:
        words = _words(text, "GLS1", 33)
        return cls.decode(struct.pack("<32I", *words[1:]), epoch=words[0])

    def acknowledgement(self) -> str:
        """Emit only after the caller has retained the raw head and association."""
        return f"{self.epoch:08x} {self.sequence:08x}\n"

    def require_association(self, batch: ScheduleBatch, *, sequence: int) -> None:
        require(self.epoch == batch.epoch and self.tag == batch.tag and self.sequence == sequence,
                "scheduled epoch/tag/sequence mismatch")
        start, step = batch.prediction(self.repeat)
        require(self.start == start and self.phase_step == step and self.phase_seed == batch.seed,
                "scheduled prediction mismatch")
        require(start+SAMPLES-1 <= batch.expires, "scheduled pilot exceeds descriptor expiry")

    def require_complete(self) -> None:
        # Completeness alone is not evidence of a detected pilot or precision.
        require(self.fault == 0 and self.count == SAMPLES, "scheduled arithmetic failed/incomplete")


@dataclass(frozen=True)
class ScheduleSnapshot:
    generation: int
    epoch: int
    latest_index: int
    status: int
    faults: int
    configured: int
    admitted: int
    late: int
    no_space: int
    unavailable: int
    expired: int
    cancelled: int
    committed: int
    popped: int
    queued: int
    high_water: int
    cdc_drops: int
    pacer_drops: int

    @classmethod
    def from_sysfs(cls, text: str) -> ScheduleSnapshot:
        w = _words(text, "GLS1SNAP", 20)
        require(w[0] == MAGIC and w[1] > 0, "invalid snapshot identity/generation")
        require(w[5] & ~0xff == 0 and w[6] & ~0xf == 0, "unknown snapshot status/fault")
        require(sum(w[8:14]) <= w[7], "terminal opportunities exceed configured repeats")
        require(w[15] <= w[14] <= w[8] and w[8]-w[14] <= 1,
                "inconsistent admitted/committed/popped counters")
        require(w[16] == w[14]-w[15] <= w[17] <= CAPACITY, "inconsistent result queue counts")
        return cls(w[1], w[2], w[3] | w[4] << 32, *w[5:])

    def require_drained(self) -> None:
        require(not self.status & (1 << 2) and self.queued == 0,
                "scheduled work or results remain reserved")
        require(self.configured == sum((self.admitted, self.late, self.no_space,
                                       self.unavailable, self.expired, self.cancelled)) and
                self.admitted == self.committed == self.popped,
                "terminal loss accounting is incomplete")
