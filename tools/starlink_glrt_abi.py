#!/usr/bin/env python3
"""Strict offline GLR1 decoding. No IIO, radio control, or detector timing seeds."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import re
import struct

RATES = (2_500_000, 5_000_000, 10_000_000, 25_000_000, 60_000_000)
DELAYS = dict(zip(RATES, (0, 100, 212, 530, 1272)))
OUTPUT_RATE = 2_500_000
U64_MAX = (1 << 64)-1


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def integer(value: str, bits: int, *, signed=False) -> int:
    require(bool(re.fullmatch(r"-?[0-9]+" if signed else r"[0-9]+", value)), "invalid decimal field")
    result = int(value)
    require(-(1 << (bits-1)) <= result < (1 << (bits-1)) if signed else 0 <= result < (1 << bits),
            "decimal field out of range")
    return result


@dataclass(frozen=True)
class Snapshot:
    source_rate: int
    generation: int
    recovery_failed: bool
    readback_rate: int
    dma_error: int
    cpu_read: int
    cpu_pushed: int
    cpu_disabled: int
    cpu_full: int
    cpu_malformed: int
    cpu_fault: int
    words: tuple[int, ...]

    @classmethod
    def decode(cls, text: str) -> Snapshot:
        return cls._decode(text, magic="GLR1")

    @classmethod
    def _decode(cls, text: str, *, magic: str) -> Snapshot:
        fields = text.split()
        require(len(fields) == 78, "GLR1 snapshot requires 14 header fields and 64 words")
        require(fields[:2] == [magic, "00010000"], f"unsupported {magic} ABI")
        rate, output, generation, recovery, readback = (integer(v, 32) for v in fields[2:7])
        require(rate in RATES and output == OUTPUT_RATE, "unsupported source/output rate")
        require(generation != 0 and recovery in (0, 1), "invalid snapshot generation/recovery flag")
        dma_error = integer(fields[7], 32, signed=True)
        require(dma_error <= 0, "invalid DMA error code")
        cpu = [integer(v, 64) for v in fields[8:13]]
        cpu_fault = integer(fields[13], 32)
        require(all(re.fullmatch(r"[0-9a-fA-F]{8}", w) for w in fields[14:]), "invalid fabric word")
        words = tuple(int(w, 16) for w in fields[14:])
        require(words[62] == rate and words[63] == DELAYS[rate], "fabric geometry disagrees with header")
        require(words[19] >> 12 == 0 and words[23] <= 1, "reserved status bits")
        require(words[48] >> 16 == 0 and words[49] >> 14 == 0, "reserved source FIFO bits")
        require(words[52] >> 11 == 0 and words[61] >> 4 == 0, "reserved event/pending bits")
        require(all(v <= 65536 for v in words[57:60]) and words[60] <= 1, "invalid GLRT configuration")
        require(cpu[0] == sum(cpu[1:]) or cpu_fault & 1, "CPU event accounting is inconsistent")
        return cls(rate, generation, bool(recovery), readback, dma_error, *cpu, cpu_fault, words)

    def u64(self, word: int) -> int:
        return self.words[word] | self.words[word+1] << 32

    @property
    def ratio(self) -> int:
        return self.source_rate//OUTPUT_RATE

    @property
    def samples(self) -> int:
        return self.u64(4)

    @property
    def duration_seconds(self) -> Fraction:
        return Fraction(self.samples, OUTPUT_RATE)

    def source_center(self, output_index: int) -> int:
        require(type(output_index) is int and 0 <= output_index < self.samples, "sample outside admitted prefix")
        return self.u64(0)+self.ratio*output_index-DELAYS[self.source_rate]

    def require_iq_health(self, *, expected_visit: int, expected_rate: int) -> None:
        """Check image, visit and recorded transport faults, including while active."""
        w = self.words
        require(self.source_rate == expected_rate == self.readback_rate, "source clock/image mismatch")
        require(w[20] == expected_visit and expected_visit != 0, "visit mismatch")
        require(not self.recovery_failed and self.dma_error == 0, "DMA/recovery failure")
        require(w[17] == w[18] == 0, "DDC/transport fault invalidates complete-prefix qualification")
        require(w[44] == w[45] and w[46] == w[47], "source FIFO dropped samples")

    def require_stopped_iq(self, *, expected_visit: int, expected_rate: int,
                           expected_samples: int | None = None) -> None:
        """Require complete fabric-to-DMA counters; this says nothing about host bytes."""
        self.require_iq_health(expected_visit=expected_visit, expected_rate=expected_rate)
        w = self.words
        require(not w[19] & 3 and w[19] & 8 and w[19] & 16, "capture is active, queued, unused or empty")
        require(self.samples > 0 and self.u64(6) == self.samples and w[22] == 0, "IQ not fully drained")
        first, last = self.u64(0), self.u64(2)
        require(first % self.ratio == 0 and first >= 2*DELAYS[self.source_rate], "invalid output phase/support")
        require(last == first+self.ratio*(self.samples-1) <= U64_MAX, "noncontiguous source endpoints")
        require(self.samples+self.u64(8) <= self.u64(14) <= self.u64(12), "DDC output accounting is inconsistent")
        require(0 < w[21] <= 256, "invalid IQ FIFO high water")
        if expected_samples is not None:
            require(type(expected_samples) is int and expected_samples == self.samples, "requested sample count differs")

    def require_iq_prefix(self, *, expected_visit: int, expected_rate: int,
                          received_bytes: int, expected_samples: int | None = None) -> None:
        """Require stopped, drained counters plus the caller's actual saved byte count.

        Counter consistency does not attest file provenance, ADC analog clipping,
        radio configuration, or live RF.
        """
        self.require_stopped_iq(expected_visit=expected_visit, expected_rate=expected_rate,
                                expected_samples=expected_samples)
        require(type(received_bytes) is int and received_bytes == 4*self.samples, "host bytes differ from AXIS prefix")

    def require_events(self, events: list[Event], *, baseline: Snapshot) -> None:
        """Require all fabric results and all CPU transfers for one settled visit.

        Does not equate complete result transport with complete detection:
        candidate busy rejections, pending support, clipping and threshold
        sensitivity remain separate evidence.
        """
        w = self.words
        require(self.source_rate == baseline.source_rate, "event baseline image mismatch")
        require(baseline.words[20] == w[20] and baseline.words[57:61] == w[57:61],
                "event baseline visit/configuration mismatch")
        require(not baseline.words[19] & 0x1f and baseline.samples == 0 and
                baseline.u64(38) == baseline.u64(53) == baseline.u64(55) == 0,
                "event baseline was not captured before ARM")
        require(not w[19] & 1 and w[50] == w[51] == 0 and not w[52] & 0x41f,
                "active capture, detector fault, event overflow or undrained queue")
        require(not w[61] & 6, "scorer or registered candidate is still pending")
        require(not self.cpu_fault and not baseline.cpu_fault, "CPU event fault")
        for attr in ("cpu_disabled", "cpu_full", "cpu_malformed"):
            require(getattr(self, attr) == getattr(baseline, attr), "CPU event loss during observation")
        count = self.u64(38)
        require(count == self.u64(53) == self.u64(55) == len(events), "fabric result accounting differs")
        require(self.cpu_read-baseline.cpu_read == self.cpu_pushed-baseline.cpu_pushed == count,
                "CPU result accounting differs")
        for sequence, event in enumerate(events):
            require(event.visit == w[20] and event.sequence == sequence, "missing/reordered/wrong-visit event")
            event.require_decision(threshold=w[58], margin=w[59], enabled=bool(w[60]))


@dataclass(frozen=True)
class Closure:
    """Additive GLX1 evidence; GLR1 wire data and conservative checks stay intact."""
    generation: int
    visit: int
    source_rate: int
    words: tuple[int, ...]

    @classmethod
    def decode(cls, text: str) -> Closure:
        return cls._decode(text, magic="GLX1")

    @classmethod
    def _decode(cls, text: str, *, magic: str) -> Closure:
        fields = text.split()
        require(len(fields) == 21 and fields[:2] == [magic, "00010000"], f"unsupported {magic} closure snapshot")
        generation, visit, rate = (integer(value, 32) for value in fields[2:5])
        require(generation != 0 and rate in RATES, "invalid closure generation/rate")
        require(all(re.fullmatch(r"[0-9a-fA-F]{8}", word) for word in fields[5:]), "invalid closure fabric word")
        words = tuple(int(word, 16) for word in fields[5:])
        require(words[0] >> 3 == 0 and words[1] >> 1 == 0,
                "reserved closure bits")
        return cls(generation, visit, rate, words)

    def u64(self, offset: int) -> int:
        return self.words[offset] | self.words[offset+1] << 32

    def require_pair(self, snapshot: Snapshot) -> None:
        require((self.generation, self.visit, self.source_rate) ==
                (snapshot.generation, snapshot.words[20], snapshot.source_rate), "closure/base snapshot identity mismatch")

    def require_complete(self, final: Snapshot, *, baseline: Closure, base_snapshot: Snapshot) -> None:
        self.require_pair(final)
        baseline.require_pair(base_snapshot)
        require(self.visit == baseline.visit and self.source_rate == baseline.source_rate,
                "closure baseline visit/image mismatch")
        require(not any(baseline.words), "closure baseline is not pre-ARM")
        require(self.words[0] == 7 and self.words[1] == 0, "source/detector closure is incomplete or faulted")
        require(not final.recovery_failed and final.dma_error == 0 and not final.words[19] & 3 and
                final.words[50] == final.words[51] == final.words[61] == 0,
                "closure has failed recovery, detector fault or pending work")
        require(self.u64(2) >= final.u64(2), "native closure endpoint precedes exported IQ")
        require(final.u64(30) == final.u64(34)+final.u64(36)+self.u64(12),
                "selected candidates are unaccounted at closure")
        require(self.u64(14) <= final.u64(36), "expired candidates exceed busy rejections")
        require(final.u64(34) == self.u64(8)+self.u64(4), "admitted native candidates are unaccounted at closure")
        require(self.u64(8) == self.u64(10) == final.u64(38), "complete native/scorer vectors were lost at closure")

    def evidence(self) -> dict:
        return {"native_endpoint": self.u64(2), "incomplete_native_tails": self.u64(4),
                "discarded_selector_groups": self.u64(6), "completed_native_vectors": self.u64(8),
                "completed_scorer_vectors": self.u64(10), "selected_close_rejections": self.u64(12),
                "expired_candidates": self.u64(14)}

    def require_event_support(self, events: list[Event]) -> None:
        """Completed results need native samples even when IQ export cannot see them."""
        ratio = self.source_rate//OUTPUT_RATE
        for event in events:
            require(event.visit == self.visit and event.epoch+726*ratio-1 <= self.u64(2),
                    "completed event extends beyond the closed native observation")


@dataclass(frozen=True)
class Event:
    words: tuple[int, ...]

    @classmethod
    def decode(cls, data: bytes) -> Event:
        require(len(data) == 64, "GLR1 event requires exactly 64 bytes")
        w = struct.unpack("<16I", data)
        require(w[0] != 0 and w[5] <= 65536 and w[6] <= 65536, "invalid event visit/score")
        require(w[7] >> 28 == 0 and w[9] >> 23 == 0 and w[11] >> 23 == 0 and
                w[13] >> 19 == 0 and w[15] >> 19 == 0, "reserved event bits")
        event = cls(w)
        for bank, offset in enumerate((8, 10)):
            energy = event.u64(offset)
            peak = event.u64(offset+4)
            score = w[5+bank]
            zero = bool(w[7] & (1 << (23+bank)))
            clamp = bool(w[7] & (1 << (25+bank)))
            raw = (peak << 22)//energy if energy else 0
            require(zero == (energy == 0) and score == min(raw, 65536) and clamp == (raw > 65536),
                    "event raw statistic, flags and score disagree")
        return event

    def u64(self, word: int) -> int:
        return self.words[word] | self.words[word+1] << 32

    @property
    def visit(self) -> int:
        return self.words[0]

    @property
    def sequence(self) -> int:
        return self.u64(1)

    @property
    def epoch(self) -> int:
        return self.u64(3)

    @property
    def detected(self) -> bool:
        return bool(self.words[7] & (1 << 27))

    def cfo_hz(self, *, control=False) -> Fraction:
        b = (self.words[7] >> (9 if control else 0)) & 511
        return Fraction((b if b < 256 else b-512)*5_000_000, 512*22)

    def require_decision(self, *, threshold: int, margin: int, enabled: bool) -> None:
        w = self.words
        expected = enabled and not bool(w[7] & (1 << 23)) and w[5] >= threshold and w[5] >= w[6]+margin
        require(self.detected == expected, "event decision disagrees with captured gates")

    def observable_interval(self, snapshot: Snapshot) -> tuple[Fraction, Fraction] | None:
        """Full native GLRT support mapped onto exported sample coordinates.

        None means the complete symbol-2..65 support is outside the admitted
        IQ prefix. Fractional coordinates retain decimator/time uncertainty;
        they are for comparison only, never host acquisition initialization.
        """
        require(self.visit == snapshot.words[20], "event/snapshot visit mismatch")
        n = 11*snapshot.ratio
        origin = snapshot.source_center(0)
        begin = Fraction(self.epoch+2*n-origin, snapshot.ratio)
        end = Fraction(self.epoch+66*n-origin, snapshot.ratio)
        return (begin, end) if begin >= 0 and end <= snapshot.samples else None
