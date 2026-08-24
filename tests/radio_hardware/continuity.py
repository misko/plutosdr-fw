"""Counter and independent-PN continuity decisions for issue 46."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

from .metadata_abi import FrameMetadata


class ContinuityError(ValueError):
    """Evidence is internally inconsistent and cannot produce a verdict."""


class ContinuityKind(str, Enum):
    CONTIGUOUS = "contiguous"
    GAP = "gap"
    REGRESSION = "regression"


@dataclass(frozen=True)
class CounterTransition:
    kind: ContinuityKind
    expected_first_sample: int
    observed_first_sample: int
    missing_samples: int


@dataclass(frozen=True)
class PnTransition:
    period: int
    expected_phase_delta: int
    observed_phase_delta: int
    missing_samples_modulo_period: int

    @property
    def contiguous(self) -> bool:
        return self.missing_samples_modulo_period == 0


@dataclass(frozen=True)
class BoundaryVerdict:
    verdict: str
    classification: str
    reason: str


def counter_transition(
    previous: FrameMetadata, current: FrameMetadata
) -> CounterTransition:
    if previous.stream_id != current.stream_id:
        raise ContinuityError("metadata stream_id changed within one buffer session")
    expected = previous.first_sample_sequence + previous.samples_per_channel
    observed = current.first_sample_sequence
    if observed < expected:
        return CounterTransition(
            ContinuityKind.REGRESSION, expected, observed, observed - expected
        )
    sample_delta = current.first_sample_sequence - previous.first_sample_sequence
    buffer_delta = current.buffer_sequence - previous.buffer_sequence
    if sample_delta <= 0 or buffer_delta <= 0:
        raise ContinuityError("metadata sample or buffer sequence did not advance")
    if sample_delta % previous.samples_per_channel:
        raise ContinuityError("metadata sample delta is not an integral frame count")
    if buffer_delta != sample_delta // previous.samples_per_channel:
        raise ContinuityError(
            "buffer_sequence is not derived from the FPGA sample counter"
        )
    if observed == expected:
        return CounterTransition(ContinuityKind.CONTIGUOUS, expected, observed, 0)
    return CounterTransition(
        ContinuityKind.GAP, expected, observed, observed - expected
    )


def pn_transition(
    previous_phase: int,
    current_phase: int,
    samples_per_channel: int,
    *,
    period: int,
) -> PnTransition:
    if period <= 0 or samples_per_channel <= 0:
        raise ValueError("period and samples_per_channel must be positive")
    expected_delta = samples_per_channel % period
    observed_delta = (current_phase - previous_phase) % period
    return PnTransition(
        period=period,
        expected_phase_delta=expected_delta,
        observed_phase_delta=observed_delta,
        missing_samples_modulo_period=(observed_delta - expected_delta) % period,
    )


def agree_dual_rx(transitions: Sequence[PnTransition]) -> PnTransition:
    if len(transitions) != 2:
        raise ContinuityError("the TX2 tee fixture must supply exactly two RX witnesses")
    first, second = transitions
    if first.period != second.period:
        raise ContinuityError("RX witnesses used different PN periods")
    if first.missing_samples_modulo_period != second.missing_samples_modulo_period:
        raise ContinuityError(
            "RX0 and RX1 disagree about the PN boundary discontinuity"
        )
    return first


def evaluate_boundary(
    *,
    api: str,
    capacity_safe: bool,
    pn: Optional[PnTransition],
    counter: Optional[CounterTransition],
    overflow_flag: bool,
    refill_error: Optional[str] = None,
) -> BoundaryVerdict:
    """Apply the explicit RED/GREEN contract from issue 46.

    A visible failure outside the queue's promised capacity is acceptable.
    Returning IQ after an unrepresented discontinuity is always RED.
    """

    if api not in {"ordinary", "metadata"}:
        raise ValueError(f"unknown IIO API {api!r}")
    if refill_error is not None:
        if capacity_safe:
            return BoundaryVerdict(
                "red", "premature_failure", "refill failed inside the safe queue bound"
            )
        return BoundaryVerdict(
            "green", "explicit_failure", "refill failed visibly after queue saturation"
        )
    if pn is None:
        raise ContinuityError("a returned IQ boundary lacks the PN witness")
    if counter is not None and counter.kind is ContinuityKind.REGRESSION:
        raise ContinuityError("the FPGA sample counter regressed")

    pn_missing = pn.missing_samples_modulo_period
    if counter is not None:
        counter_missing = max(counter.missing_samples, 0) % pn.period
        if counter_missing != pn_missing:
            raise ContinuityError(
                "metadata counter and PN witness disagree about omitted RF time"
            )

    actual_gap = not pn.contiguous
    if not actual_gap:
        if counter is not None and counter.kind is ContinuityKind.GAP:
            raise ContinuityError("counter reports a gap while PN reports adjacency")
        return BoundaryVerdict("green", "contiguous", "counter-proven IQ adjacency")

    if capacity_safe:
        return BoundaryVerdict(
            "red", "gap_inside_safe_bound", "RF samples were omitted inside queue capacity"
        )
    if api == "ordinary":
        return BoundaryVerdict(
            "red",
            "ordinary_unrepresented_gap",
            "ordinary IIO resumed with a PN-proven but unrepresented gap",
        )
    if counter is None or counter.kind is not ContinuityKind.GAP:
        raise ContinuityError("metadata IQ gap lacks an exact counter gap")
    if not overflow_flag:
        return BoundaryVerdict(
            "red",
            "metadata_unflagged_gap",
            "metadata counted omitted samples but did not mark device overflow",
        )
    return BoundaryVerdict(
        "green", "explicit_segmented_gap", "metadata explicitly segmented the RF-time gap"
    )
