"""Explicit rate-bound GLT1 review/recovery over the internal GLRJ1 framing.

The caller attests full firmware/reference identity and owns the radio lease.
This module does not discover radios, start RX, or invent acquisition evidence.
"""
from __future__ import annotations

import re
import time

from .starlink_glrt_native_journal import JournalCodec, _descriptors, _recover, _review
from .starlink_glrt_tracking_abi import (
    VERSION,
    TrackingBatch,
    TrackingResult,
    TrackingSnapshot,
    bank_id,
)


def batch(text: str, *, rate: int) -> TrackingBatch:
    fields = text.split()
    if (not text.startswith("GLT1 ") or len(fields) != 14 or fields[0] != "GLT1" or
            not all(re.fullmatch(r"[0-9a-fA-F]{8}", s) for s in fields[1:4]) or
            not all(re.fullmatch(r"[0-9a-fA-F]{1,16}", s) for s in fields[4:])):
        raise ValueError("invalid retained GLT1 descriptor")
    if tuple(int(s,16) for s in fields[1:4]) != (VERSION, rate, bank_id(rate)):
        raise ValueError("retained tracking profile differs from attested rate")
    result = TrackingBatch(rate, *(int(s,16) for s in fields[4:]))
    result.prediction(result.repeats-1)  # Entire pilot must fit expiry and u64 source coordinates.
    return result


def _codec(rate: int) -> JournalCodec:
    bank_id(rate)

    def snapshot(text: str) -> TrackingSnapshot:
        result = TrackingSnapshot.from_sysfs(text)
        if result.rate != rate:
            raise ValueError("tracking snapshot crosses sample-rate profile")
        return result

    def head(text: str) -> TrackingResult:
        result = TrackingResult.from_sysfs(text)
        if result.rate != rate:
            raise ValueError("tracking head crosses sample-rate profile")
        return result

    return JournalCodec(lambda text: batch(text, rate=rate), snapshot, head, "tracking_")


def descriptors(entries, *, epoch: int, rate: int) -> dict[int, tuple[int, TrackingBatch]]:
    return _descriptors(entries, epoch=epoch, codec=_codec(rate))


def review(data: bytes, *, epoch: int, rate: int) -> dict:
    """Validate GLT1 ownership, fit association and complete drain/clear.

    This does not recompute numerical estimates or prove physical accuracy.
    The GLS1 reviewer continues to reject these versioned bodies.
    """
    return _review(data, epoch=epoch, codec=_codec(rate))


def recover(device, data: bytes, *, epoch: int, rate: int, writer_stopped: bool,
            retain, deadline: float, clock=time.monotonic, sleep=time.sleep) -> TrackingSnapshot:
    """Retain and associate before POP; reconcile uncertain POP without retry."""
    return _recover(device, data, epoch=epoch, writer_stopped=writer_stopped,
                    retain=retain, deadline=deadline, codec=_codec(rate), clock=clock, sleep=sleep)
