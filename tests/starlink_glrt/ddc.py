"""Frozen-coefficient, chunk-invariant GLRT IQ-export arithmetic reference.

The receiver LO centers the published eight-pilot band. Digital translation is
zero. Each filtered output carries its newest source index; subtract the declared
group delay to locate its signal center. Unity has zero arithmetic delay.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import numpy as np

RATES = (2_500_000, 5_000_000, 10_000_000, 25_000_000, 60_000_000)
# DDC-only qualification does not enable a new whole-receiver profile.
COMPONENT_RATES = tuple(sorted((*RATES, 15_000_000)))
OUTPUT_RATE = 2_500_000
FRACTION_BITS = 17
BANK_ROOT = Path(__file__).resolve().parents[2] / "hdl/library/starlink_glrt"


@lru_cache(maxsize=5)
def coefficients(rate: int) -> np.ndarray:
    manifest_name = "ddc_15000000_coefficients.json" if rate == 15_000_000 else "ddc_coefficients.json"
    manifest = json.loads((BANK_ROOT / manifest_name).read_text())
    spec = manifest["banks"][str(rate)]
    raw = (BANK_ROOT / spec["file"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != spec["sha256"]:
        raise ValueError("frozen GLRT DDC coefficient identity changed")
    values = np.array([int(word, 16) for word in raw.split()], dtype=np.int64)
    values = np.where(values & (1 << 17), values - (1 << 18), values)
    if len(values) != spec["taps"] or sum(values) != 1 << FRACTION_BITS:
        raise ValueError("invalid GLRT DDC coefficient shape or gain")
    if not np.array_equal(values, values[::-1]):
        raise ValueError("GLRT DDC requires exactly symmetric coefficients")
    values.flags.writeable = False
    return values


def stages(rate: int) -> tuple[tuple[int, int], ...]:
    if isinstance(rate, bool) or rate not in COMPONENT_RATES:
        raise ValueError("DDC source rate must be 2.5/5/10/15/25/60 MS/s")
    if rate == OUTPUT_RATE:
        return ()
    return (() if rate == 5_000_000 else ((rate, rate // 5_000_000),)) + ((5_000_000, 2),)


def group_delay(rate: int) -> int:
    delay = 0
    stride = 1
    for stage_rate, decimation in stages(rate):
        delay += stride * (len(coefficients(stage_rate)) - 1) // 2
        stride *= decimation
    return delay


def quantize(values: np.ndarray) -> tuple[np.ndarray, int]:
    # Floor quotient plus ties-even increment is defined for both signs.
    floor = np.asarray(values, dtype=np.int64) >> FRACTION_BITS
    remainder = np.asarray(values, dtype=np.int64) & ((1 << FRACTION_BITS) - 1)
    half = 1 << (FRACTION_BITS - 1)
    rounded = floor + ((remainder > half) | ((remainder == half) & ((floor & 1) != 0)))
    clips = int(np.count_nonzero((rounded < -32768) | (rounded > 32767)))
    return np.clip(rounded, -32768, 32767).astype(np.int16), clips


@dataclass(frozen=True)
class Result:
    iq: np.ndarray
    indexes: np.ndarray
    supported: np.ndarray
    clips: int


class Ddc:
    def __init__(self, rate: int):
        self.rate = rate
        self.geometry = stages(rate)
        self.reset()

    def reset(self) -> None:
        self.next_index = None
        self.first_index = None
        self.histories = [np.zeros((len(coefficients(fs)) - 1, 2), dtype=np.int16)
                          for fs, _ in self.geometry]

    def process(self, iq: np.ndarray, first_index: int) -> Result:
        raw = np.asarray(iq)
        if raw.ndim != 2 or raw.shape[1] != 2 or not np.issubdtype(raw.dtype, np.integer):
            raise ValueError("input requires integer CI16 shape (N, 2)")
        if np.any(raw < -32768) or np.any(raw > 32767):
            raise ValueError("input outside CI16")
        if (isinstance(first_index, bool) or not isinstance(first_index, int)
                or first_index < 0 or first_index + len(raw) > 1 << 64):
            raise ValueError("input support outside uint64")
        if self.next_index is not None and first_index != self.next_index:
            raise ValueError("source discontinuity requires reset and a new epoch")
        if not len(raw):
            return Result(raw.astype(np.int16), np.empty(0, dtype=np.uint64),
                          np.empty(0, dtype=bool), 0)
        self.next_index = first_index + len(raw)
        if self.first_index is None:
            self.first_index = first_index
        values = raw.astype(np.int16)
        indexes = np.arange(len(raw), dtype=np.uint64) + np.uint64(first_index)
        stride = 1
        clips = 0
        for number, (fs, decimation) in enumerate(self.geometry):
            if not len(values):
                break
            bank = coefficients(fs)
            joined = np.concatenate((self.histories[number], values)).astype(np.int64)
            sums = np.column_stack([np.convolve(joined[:, lane], bank, "valid")
                                    for lane in range(2)])
            self.histories[number] = joined[-(len(bank) - 1):].astype(np.int16)
            stride *= decimation
            take = indexes % stride == 0
            values, clipped = quantize(sums[take])
            clips += clipped
            indexes = indexes[take]
        supported = indexes - np.uint64(self.first_index) >= 2 * group_delay(self.rate)
        return Result(values, indexes, supported, clips)
