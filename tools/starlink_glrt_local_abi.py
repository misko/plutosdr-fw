"""GLA1 direct-rate local acquisition records and exact saved-IQ binding.

These checks attest transport, source support and search accounting. Numerical
equivalence and RF identity require independent replay and deployment evidence.
GLR1/GLF1 contracts remain unchanged.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass

if __package__:
    from .starlink_glrt_abi import U64_MAX, Closure, Snapshot, integer, require
else:
    from starlink_glrt_abi import U64_MAX, Closure, Snapshot, integer, require

RATE = 2_500_000
PERIOD = 250_000
WINDOW = 14_000
MAGIC = 0x474c4131


class LocalIQSnapshot(Snapshot):
    @classmethod
    def decode(cls, text: str) -> LocalIQSnapshot:
        result = cls._decode(text, magic="GLA1")
        require(result.source_rate == RATE, "GLA1 requires direct 2.5 MS/s IQ")
        return result

    def require_iq_health(self, *, expected_visit: int, expected_rate: int) -> None:
        super().require_iq_health(expected_visit=expected_visit, expected_rate=expected_rate)
        require(not any(self.words[n] for n in (*range(30, 40), *range(50, 57), 61)),
                "GLA1 contains legacy detector work, faults or pending state")

    def require_events(self, events, *, baseline):
        raise ValueError("GLA1 results require local search accounting")


class LocalSourceClosure(Closure):
    @classmethod
    def decode(cls, text: str) -> LocalSourceClosure:
        result = cls._decode(text, magic="GLA1")
        require(result.source_rate == RATE, "GLA1 source closure requires 2.5 MS/s")
        return result

    def require_complete(self, final: LocalIQSnapshot, *, baseline: LocalSourceClosure,
                         base_snapshot: LocalIQSnapshot) -> None:
        require(isinstance(final, LocalIQSnapshot) and isinstance(base_snapshot, LocalIQSnapshot)
                and isinstance(baseline, LocalSourceClosure), "GLA1 requires its explicit IQ profile")
        self.require_pair(final)
        baseline.require_pair(base_snapshot)
        require(self.visit == baseline.visit and not any(baseline.words),
                "GLA1 source baseline is not pre-ARM")
        final.require_stopped_iq(expected_visit=self.visit, expected_rate=RATE)
        base_snapshot.require_iq_health(expected_visit=self.visit, expected_rate=RATE)
        require(not base_snapshot.words[19] & 0x1f and not base_snapshot.samples,
                "GLA1 IQ baseline is not pre-ARM")
        require(self.words[0] == 7 and not self.words[1] and self.u64(2) >= final.u64(2)
                and not any(self.words[4:]), "GLA1 source closure incomplete or contains legacy work")

    def require_event_support(self, events):
        raise ValueError("GLA1 results must be bound to the admitted IQ prefix")


@dataclass(frozen=True)
class LocalEvent:
    words: tuple[int, ...]

    @property
    def visit(self) -> int:
        return self.words[1]

    @classmethod
    def decode(cls, data: bytes) -> LocalEvent:
        require(len(data) == 64, "GLA1 record requires 64 bytes")
        w = struct.unpack("<16I", data)
        event = cls(w)
        flags = w[5]
        require(w[0] == MAGIC and w[1] != 0, "GLA1 record identity invalid")
        require(flags >> 28 == 0 and event.epoch < 3333 and (flags >> 12 & 15) <= 10
                and (flags >> 6 & 7) <= 4, "GLA1 record flags invalid")
        require(-400_000 <= event.cfo_hz <= 400_000 and all(v <= 65536 for v in w[7:12]),
                "GLA1 CFO or score out of range")
        require(w[12] == WINDOW and not any(w[13:]) and event.first <= U64_MAX-WINDOW+1,
                "GLA1 window or reserved fields invalid")
        if event.reasons & 1:
            require(flags == 3 and not any(w[6:12]), "GLA1 empty decision has payload")
        else:
            require(w[7] != 0 and (event.decision or event.reasons == 0),
                    "GLA1 candidate has zero score or decision reasons")
        return event

    @property
    def first(self) -> int:
        return self.words[3] | self.words[4] << 32

    @property
    def epoch(self) -> int:
        return self.words[5] >> 16 & 4095

    @property
    def decision(self) -> bool:
        return bool(self.words[5] & 1)

    @property
    def reasons(self) -> int:
        return self.words[5] >> 1 & 31

    @property
    def cfo_hz(self) -> int:
        value = self.words[6]
        return (value if value < 1 << 31 else value-(1 << 32))*100

    @property
    def candidate_payload(self) -> tuple[int, ...]:
        return (self.words[5] & ~63, *self.words[6:12])


@dataclass(frozen=True)
class LocalSearchSnapshot:
    generation: int
    words: tuple[int, ...]

    @classmethod
    def decode(cls, text: str) -> LocalSearchSnapshot:
        fields = text.split()
        require(len(fields) == 22 and fields[:2] == ["GLA1", "00010000"],
                "unsupported GLA1 search snapshot")
        generation, rate, period, window = (integer(v, 32) for v in fields[2:6])
        require(generation and (rate, period, window) == (RATE, PERIOD, WINDOW),
                "GLA1 generation or geometry invalid")
        require(all(re.fullmatch(r"[0-9a-fA-F]{8}", w) for w in fields[6:]),
                "invalid GLA1 search word")
        words = tuple(int(w, 16) for w in fields[6:])
        require(not words[0] >> 9 and not words[1] >> 6 and words[2] <= words[3] <= 16,
                "GLA1 reserved status or queue bounds invalid")
        return cls(generation, words)

    def require_complete(self, final: LocalIQSnapshot, *, baseline: LocalSearchSnapshot,
                         base_snapshot: LocalIQSnapshot, events: list[LocalEvent]) -> None:
        w, b = self.words, baseline.words
        require(w[13] == b[13] == final.words[20] == base_snapshot.words[20] != 0,
                "GLA1 search visit mismatch")
        require(not any(b[:13]) and not any(b[14:]), "GLA1 search baseline is not pre-ARM")
        require(w[0] & 0x113 == 0x113 and not w[0] & 0x4c and not w[1] and not w[2],
                "GLA1 search unsettled, faulted or not drained")
        require(w[4] == w[5] == len(events) and w[6] == w[7]+w[8]
                and w[7] == w[9]+w[11] and w[10] <= w[9] and not w[12]
                and w[9] <= w[4] <= w[7]*9 and (not w[11] or w[0] & 128),
                "GLA1 search accounting incomplete")
        first = w[14] | w[15] << 32
        require(first == final.u64(0) and w[6] == (final.samples+PERIOD-1)//PERIOD,
                "GLA1 search cadence differs from saved IQ")
        require(not final.cpu_fault and not base_snapshot.cpu_fault,
                "GLA1 CPU event fault")
        require(all(getattr(final, name) == getattr(base_snapshot, name)
                    for name in ("cpu_disabled", "cpu_full", "cpu_malformed")),
                "GLA1 CPU event loss")
        require(final.cpu_read-base_snapshot.cpu_read ==
                final.cpu_pushed-base_snapshot.cpu_pushed == len(events), "GLA1 CPU count differs")

        groups: dict[int, list[LocalEvent]] = {}
        decisions = supported = 0
        for sequence, event in enumerate(events):
            require(event.words[1] == w[13] and event.words[2] == sequence,
                    "GLA1 missing, reordered or wrong-visit record")
            offset = event.first-first
            require(offset >= 0 and offset % PERIOD == 0 and offset+WINDOW <= final.samples,
                    "GLA1 record outside saved search window")
            require(not groups or event.first >= next(reversed(groups)),
                    "GLA1 search windows reordered")
            group = groups.setdefault(event.first, [])
            require(not group or not group[-1].decision, "GLA1 record follows final decision")
            if event.decision:
                decisions += 1
                supported += event.reasons == 0
                if event.reasons & 1:
                    require(not group, "GLA1 empty decision follows candidates")
                else:
                    require(any(event.candidate_payload == e.candidate_payload for e in group),
                            "GLA1 decision lacks matching candidate evidence")
            else:
                require(len(group) < 8 and (event.words[5] >> 9 & 7) == len(group),
                        "GLA1 candidate rank missing or reordered")
            group.append(event)
        unfinished = sum(not group[-1].decision for group in groups.values())
        require(decisions == w[9] and supported == w[10] and len(groups) <= w[7]
                and unfinished <= w[11], "GLA1 decisions or aborted evidence unaccounted")


def attest_capture(*, final: LocalIQSnapshot, baseline: LocalIQSnapshot,
                   source: LocalSourceClosure, source_baseline: LocalSourceClosure,
                   search: LocalSearchSnapshot, search_baseline: LocalSearchSnapshot,
                   events: list[LocalEvent], received_bytes: int) -> dict:
    """Attest both streams; returned windows are the completed searches only."""
    source.require_complete(final, baseline=source_baseline, base_snapshot=baseline)
    final.require_iq_prefix(expected_visit=source.visit, expected_rate=RATE, received_bytes=received_bytes)
    search.require_complete(final, baseline=search_baseline, base_snapshot=baseline, events=events)
    return {"source_rate": RATE, "samples": final.samples, "first_source_index": final.u64(0),
            "opportunities": search.words[6], "admitted": search.words[7], "skipped": search.words[8],
            "completed": search.words[9], "supported": search.words[10], "aborted": search.words[11],
            "completed_windows": [{"first_source_index": event.first, "samples": WINDOW,
                                   "supported": event.reasons == 0}
                                  for event in events if event.decision]}
