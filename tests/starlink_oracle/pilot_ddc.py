"""Fixed-point oracle for the scanner's proposed 15 -> 2.5 MS/s pilot tap.

This is not an RTL implementation or RF qualification. A 64-phase Q16 mixer
centers the exact published pilot-template mean. A Q17 31-tap halfband /2 and
Q17 255-tap FIR /3 preserve the continuous input-index coordinate. All stages
round ties to even and saturate explicitly to CI16. A reset starts a new filter
history but does not rebase the oscillator or the decimation phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib

import numpy as np


INPUT_RATE_HZ = 15_000_000
OUTPUT_RATE_HZ = 2_500_000
DECIMATION = 6
FIR_FRACTION_BITS = 17
MIXER_FRACTION_BITS = 16
GROUP_DELAY_INPUT_SAMPLES = 269
FILTER_HISTORY_INPUT_SAMPLES = 538
PASSBAND_EDGE_HZ = 1_100_000
STOPBAND_EDGE_HZ = 1_250_000
MIXER_STEP_64 = {"lower": -13, "upper": 12}
COEFFICIENT_SHA256 = {
    31: "c1c98fd0961947236eb391fd02a2569082e37b2ed2b48a4e89b3c5fd3df28e24",
    255: "b0a71f38b82b4b90bd8c0d61e1d9d524ce0ff3c28cf6a8adc55b1737dac2cf0e",
}
MIXER_SHA256 = "7b035fe99445f96e3658d98636e169bf3d721bedd7b3b30efc98fee07c4a4b5d"


def _digest(values: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<i4").tobytes()).hexdigest()


@lru_cache(maxsize=2)
def coefficients(taps: int) -> np.ndarray:
    """Reconstruct and verify the frozen Q17 coefficient bank."""

    if taps == 31:
        sample_rate, cutoff = 15_000_000, 3_750_000
    elif taps == 255:
        sample_rate, cutoff = 7_500_000, 1_175_000
    else:
        raise ValueError("only the frozen 31/255-tap filters are defined")
    offsets = np.arange(taps) - (taps - 1) / 2
    ratio = 2 * cutoff / sample_rate
    values = ratio * np.sinc(ratio * offsets) * np.kaiser(taps, 7.86)
    values /= sum(values)
    quantized = np.rint(values * (1 << FIR_FRACTION_BITS)).astype(np.int64)
    quantized[taps // 2] += (1 << FIR_FRACTION_BITS) - sum(quantized)
    if _digest(quantized) != COEFFICIENT_SHA256[taps]:
        raise RuntimeError("pilot FIR coefficient bytes changed; do not regenerate the golden")
    quantized.flags.writeable = False
    return quantized


@lru_cache(maxsize=1)
def mixer_lut() -> np.ndarray:
    phase = np.arange(64) * 2 * np.pi / 64
    values = np.column_stack((np.cos(phase), -np.sin(phase)))
    quantized = np.rint(values * (1 << MIXER_FRACTION_BITS)).astype(np.int64)
    if _digest(quantized) != MIXER_SHA256:
        raise RuntimeError("pilot mixer bytes changed; do not regenerate the golden")
    quantized.flags.writeable = False
    return quantized


def _round_saturate(values: np.ndarray, fraction_bits: int) -> tuple[np.ndarray, int]:
    magnitude = np.abs(values)
    whole = magnitude >> fraction_bits
    remainder = magnitude & ((1 << fraction_bits) - 1)
    half = 1 << (fraction_bits - 1)
    rounded = whole + ((remainder > half) | ((remainder == half) & ((whole & 1) != 0)))
    rounded = np.where(values < 0, -rounded, rounded)
    saturation_count = int(np.count_nonzero((rounded < -32768) | (rounded > 32767)))
    return np.clip(rounded, -32768, 32767).astype(np.int16), saturation_count


@dataclass(frozen=True)
class PilotDdcResult:
    samples_iq: np.ndarray
    accepted_input_indexes: np.ndarray
    support_valid: np.ndarray
    saturation_events: int


class PilotDdcOracle:
    """Chunk-invariant fixed-point reference with explicit epoch reset."""

    def __init__(self, edge: str) -> None:
        if edge not in MIXER_STEP_64:
            raise ValueError("edge must be lower or upper")
        self.edge = edge
        self.reset()

    def reset(self) -> None:
        self._next_index: int | None = None
        self._epoch_first_index: int | None = None
        self._history_2 = np.zeros((30, 2), dtype=np.int16)
        self._history_3 = np.zeros((254, 2), dtype=np.int16)

    @staticmethod
    def _filter(
        values: np.ndarray, history: np.ndarray, bank: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        joined = np.concatenate((history, values)).astype(np.int64)
        sums = np.column_stack(
            [np.convolve(joined[:, lane], bank, mode="valid") for lane in range(2)]
        )
        return sums, joined[-(len(bank) - 1):].astype(np.int16)

    def process(self, samples_iq: np.ndarray, *, first_index: int) -> PilotDdcResult:
        raw = np.asarray(samples_iq)
        if raw.ndim != 2 or raw.shape[1] != 2 or not np.issubdtype(raw.dtype, np.integer):
            raise ValueError("input must have integer CI16 shape (N, 2)")
        if np.any(raw < -32768) or np.any(raw > 32767):
            raise ValueError("input must fit CI16")
        if (isinstance(first_index, bool) or not isinstance(first_index, int)
                or first_index < 0 or first_index + len(raw) > 1 << 64):
            raise ValueError("input interval must fit the uint64 counter")
        if self._next_index is not None and first_index != self._next_index:
            raise ValueError("input discontinuity requires an explicit epoch reset")
        if not len(raw):
            return PilotDdcResult(
                np.empty((0, 2), dtype=np.int16), np.empty(0, dtype=np.uint64),
                np.empty(0, dtype=bool), 0,
            )
        if self._epoch_first_index is None:
            self._epoch_first_index = first_index
        self._next_index = first_index + len(raw)
        indexes = np.arange(len(raw), dtype=np.uint64) + np.uint64(first_index)
        phases = ((indexes % 64).astype(np.int64) * MIXER_STEP_64[self.edge]) % 64
        rotation = mixer_lut()[phases]
        source = raw.astype(np.int64)
        rotated = np.column_stack((
            source[:, 0] * rotation[:, 0] - source[:, 1] * rotation[:, 1],
            source[:, 0] * rotation[:, 1] + source[:, 1] * rotation[:, 0],
        ))
        mixed, mixer_saturation = _round_saturate(rotated, MIXER_FRACTION_BITS)
        sums_2, self._history_2 = self._filter(mixed, self._history_2, coefficients(31))
        take_2 = indexes % 2 == 0
        stage_2, saturation_2 = _round_saturate(sums_2[take_2], FIR_FRACTION_BITS)
        indexes_2 = indexes[take_2]
        if len(stage_2):
            sums_3, self._history_3 = self._filter(stage_2, self._history_3, coefficients(255))
            take_3 = indexes_2 % 6 == 0
            output, saturation_3 = _round_saturate(sums_3[take_3], FIR_FRACTION_BITS)
            output_indexes = indexes_2[take_3]
        else:
            output = np.empty((0, 2), dtype=np.int16)
            output_indexes = np.empty(0, dtype=np.uint64)
            saturation_3 = 0
        support_valid = (
            output_indexes - np.uint64(self._epoch_first_index) >= FILTER_HISTORY_INPUT_SAMPLES
        )
        return PilotDdcResult(
            output, output_indexes, support_valid,
            mixer_saturation + saturation_2 + saturation_3,
        )


def float_reference(samples_iq: np.ndarray, *, first_index: int, edge: str) -> PilotDdcResult:
    """Independent floating convolution on the same quantized FIR coefficients."""

    if edge not in MIXER_STEP_64:
        raise ValueError("edge must be lower or upper")
    values = np.asarray(samples_iq, dtype=float)
    indexes = np.arange(len(values), dtype=np.uint64) + np.uint64(first_index)
    phases = ((indexes % 64).astype(np.int64) * MIXER_STEP_64[edge]) % 64
    mixed = (values[:, 0] + 1j * values[:, 1]) * np.exp(-2j * np.pi * phases / 64)
    first = np.convolve(mixed, coefficients(31) / (1 << FIR_FRACTION_BITS))[:len(mixed)]
    first = first[indexes % 2 == 0]
    indexes_2 = indexes[indexes % 2 == 0]
    second = np.convolve(first, coefficients(255) / (1 << FIR_FRACTION_BITS))[:len(first)]
    take = indexes_2 % 6 == 0
    output = second[take]
    output_indexes = indexes_2[take]
    return PilotDdcResult(
        np.column_stack((output.real, output.imag)), output_indexes,
        output_indexes - np.uint64(first_index) >= FILTER_HISTORY_INPUT_SAMPLES, 0,
    )
