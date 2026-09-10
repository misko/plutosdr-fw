"""Explicit GLF1 coarse-IQ geometry; no legacy GLR1 event/scorer claims."""
from __future__ import annotations

from .starlink_glrt_abi import Closure, Snapshot, U64_MAX, require


class LeanSnapshot(Snapshot):
    @classmethod
    def decode(cls, text: str) -> LeanSnapshot:
        result = cls._decode(text, magic="GLF1")
        require(result.source_rate == 60_000_000, "GLF1 requires 60 MS/s native source")
        return result

    def require_iq_health(self, *, expected_visit: int, expected_rate: int) -> None:
        super().require_iq_health(expected_visit=expected_visit, expected_rate=expected_rate)
        require(not any((self.cpu_read, self.cpu_pushed, self.cpu_disabled, self.cpu_full,
                         self.cpu_malformed, self.cpu_fault)), "GLF1 cannot contain legacy CPU events")
        require(not any(self.words[n] for n in (*range(34, 40), *range(50, 57))) and
                not self.words[61] & 7,
                "GLF1 cannot contain legacy scorer work or events")

    def require_live_prefix(self, *, expected_visit: int, received_samples: int) -> int:
        """Return integer native signal origin for an actually received prefix.

        This binds coordinates provisionally during the active visit; it does
        not attest the final file, RF identity or continuity after this snapshot.
        The operator must separately bind GLS1 epoch and invalidate on new gaps.
        """
        self.require_iq_health(expected_visit=expected_visit, expected_rate=60_000_000)
        require(type(received_samples) is int and 0 < received_samples <= self.samples,
                "host prefix exceeds observed admitted samples")
        first, last = self.u64(0), self.u64(2)
        require(self.words[19] & 24 == 24, "source snapshot has no armed nonempty prefix")
        require(first % 24 == 0 and first >= 2544 and
                last == first+24*(self.samples-1) <= U64_MAX, "invalid GLF1 native endpoints")
        return first-1272

    def require_events(self, events, *, baseline):
        raise ValueError("GLF1 provides IQ and timing proposals, not legacy scored events")


class LeanClosure(Closure):
    @classmethod
    def decode(cls, text: str) -> LeanClosure:
        result = cls._decode(text, magic="GLF1")
        require(result.source_rate == 60_000_000, "GLF1 closure requires native 60 MS/s")
        return result

    def require_complete(self, final: LeanSnapshot, *, baseline: LeanClosure,
                         base_snapshot: LeanSnapshot) -> None:
        require(isinstance(final, LeanSnapshot) and isinstance(base_snapshot, LeanSnapshot) and
                isinstance(baseline, LeanClosure), "GLF1 closure requires its explicit IQ profile")
        self.require_pair(final)
        baseline.require_pair(base_snapshot)
        require(self.visit == baseline.visit and not any(baseline.words), "GLF1 baseline is not pre-ARM")
        final.require_stopped_iq(expected_visit=self.visit, expected_rate=60_000_000)
        base_snapshot.require_iq_health(expected_visit=self.visit, expected_rate=60_000_000)
        require(not base_snapshot.words[19] & 0x1f and not base_snapshot.samples,
                "GLF1 IQ baseline is not pre-ARM")
        require(self.words[0] == 7 and not self.words[1] and self.u64(2) >= final.u64(2),
                "GLF1 source closure incomplete or faulted")
        require(not final.words[61], "GLF1 timing selector remains pending at closure")
        require(not any(self.words[n] for n in range(4, 16) if n not in (6, 7)),
                "GLF1 closure cannot contain legacy native/scorer work")
        # extension[6:8] counts discarded timing-selector groups. Such proposals
        # are not admissions to a removed scorer; never apply the GLX1 equation.

    def require_event_support(self, events):
        raise ValueError("GLF1 closure does not attest legacy event support")
