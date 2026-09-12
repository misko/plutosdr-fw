"""GLT1 v1.0 native tracking association; no radio I/O or legacy relabeling."""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from fractions import Fraction

if __package__:
    from .starlink_glrt_native_abi import require, wide
else:
    from starlink_glrt_native_abi import require, wide

MAGIC = 0x474C5431
VERSION = 0x10000
RATES = (2500000, 15000000, 30000000, 60000000)


def bank_id(rate: int) -> int:
    require(type(rate) is int and rate in RATES, "unsupported tracking rate")
    return 0xdc509401 if rate == 2500000 else 0xb04a2fab


@dataclass(frozen=True)
class TrackingBatch:
    rate: int
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
        bank_id(self.rate)
        for name, bits in (("epoch", 32), ("tag", 32), ("start", 64), ("fraction", 16),
                           ("period", 48), ("step", 48), ("delta", 48), ("seed", 32),
                           ("repeats", 8), ("expires", 64)):
            value = getattr(self, name)
            require(type(value) is int and 0 <= value < 1 << bits, f"invalid tracking {name}")
        stride = 60000000//self.rate
        minimum, issue = (64+stride-1)//stride, (512+stride-1)//stride
        require(self.epoch > 0 and self.tag > 0 and 1 <= self.repeats <= 64,
                "tracking requires epoch, tag and bounded repeats")
        require(self.start >= issue and self.expires >= self.start, "invalid tracking interval")
        require((self.samples+2*minimum)*65536 <= self.period <= (81000//stride)*65536,
                "unsupported tracking period")

    @property
    def samples(self) -> int:
        return self.rate*33//25000

    def encode(self) -> str:
        """Versioned submit payload; the driver must match rate/bank to hardware."""
        return f"GLT1 {VERSION:08x} {self.rate:08x} {bank_id(self.rate):08x} "+" ".join(
            f"{getattr(self, name):x}" for name in (
                "epoch", "tag", "start", "fraction", "period", "step", "delta", "seed",
                "repeats", "expires"))+"\n"

    def prediction(self, repeat: int) -> tuple[int, int, int]:
        require(type(repeat) is int and 0 <= repeat < self.repeats, "repeat outside tracking batch")
        phases = 4 if self.rate == 2500000 else 1
        origin = Fraction(self.start*65536+self.fraction+repeat*self.period, 65536)
        start, phase = divmod(round(origin*phases), phases)
        require(start+self.samples-1 < 2**64 and start+self.samples-1 <= self.expires,
                "tracking pilot exceeds source expiry")
        step = round(Fraction((self.step+repeat*self.delta) % 2**48, 65536)) % 2**32
        return start, step, phase


@dataclass(frozen=True)
class TrackingResult:
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
    rate: int
    repeat: int
    reference_phase: int

    @classmethod
    def decode(cls, payload: bytes, *, epoch: int) -> TrackingResult:
        require(type(epoch) is int and 0 < epoch < 2**32, "missing tracking source epoch")
        require(len(payload) == 128, "GLT1 requires 128 bytes")
        w = struct.unpack("<32I", payload)
        require(w[0] == MAGIC and w[2] != 0, "missing GLT1 head/tag")
        require(w[29] == bank_id(w[25]) and w[30:] == (VERSION, 0),
                "unsupported tracking reference/version/reserved word")
        samples = w[25]*33//25000
        phases = 4 if w[25] == 2500000 else 1
        require(w[26] == samples and w[27] < 64 and w[28] < phases,
                "unsupported tracking geometry/repeat/phase")
        require(w[8] & ~0x3ff == 0, "unknown tracking fault")
        require(w[7] <= samples and (w[8] != 0 or w[7] == samples), "invalid tracking count")
        start = w[3] | w[4] << 32
        require(not w[7] or start+w[7]-1 < 2**64, "tracking prefix wraps source index")
        bits = (samples-1).bit_length()
        reference = tuple(wide(w[i:i+2], 35+bits, signed=True) for i in (9, 11))
        delay = tuple(wide(w[i:i+2], 35+bits, signed=True) for i in (13, 15))
        prefix = tuple(wide(w[i:i+3], 35+2*bits, signed=True) for i in (17, 20))
        energy = wide(w[23:25], 36+bits, signed=False)
        require(w[7] or not any((*reference, *delay, *prefix, energy)),
                "empty tracking result has nonzero moments")
        return cls(epoch, w[1], w[2], start, w[5], w[6], w[7], w[8],
                   reference, delay, prefix, energy, w[25], w[27], w[28])

    @classmethod
    def from_sysfs(cls, text: str) -> TrackingResult:
        fields = text.split()
        require(len(fields) == 35 and fields[0] == "GLT1", "invalid GLT1 envelope")
        require(all(re.fullmatch(r"[0-9a-fA-F]{8}", word) for word in fields[1:]),
                "GLT1 requires canonical u32 hexadecimal words")
        words = tuple(int(word, 16) for word in fields[1:])
        require(words[0] == VERSION, "unsupported GLT1 envelope version")
        return cls.decode(struct.pack("<32I", *words[2:]), epoch=words[1])

    def require_association(self, batch: TrackingBatch, *, sequence: int) -> None:
        require(self.epoch == batch.epoch and self.tag == batch.tag and
                self.sequence == sequence and self.rate == batch.rate,
                "tracking epoch/tag/sequence/rate mismatch")
        start, step, phase = batch.prediction(self.repeat)
        require((self.start, self.phase_step, self.reference_phase, self.phase_seed) ==
                (start, step, phase, batch.seed), "tracking prediction mismatch")

    def require_complete(self) -> None:
        require(self.fault == 0 and self.count == self.rate*33//25000,
                "tracking arithmetic failed/incomplete")

    def acknowledgement(self) -> str:
        """Only after raw retention and association; not proof of a supported fit."""
        return f"{self.epoch:08x} {self.sequence:08x}\n"
