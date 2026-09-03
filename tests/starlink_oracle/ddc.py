"""Exact software contract for the acquisition-only rate conditioners.

The sparse tracker and RX DMA remain at the source rate.  This model covers
only the bounded continuous-acquisition branch.  One stage converts 30 to
15 MS/s; two identical stages convert 60 to 30 to 15 MS/s.  Every stage uses
an absolute-phase quadrant mixer, a fixed Q1.15 half-band FIR, convergent
rounding, CI16 saturation, and an exact source-to-output index map.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Literal

import numpy as np
import numpy.typing as npt

from .waveforms import complex64_sha256, projected_pss


DDC_ORACLE_SCHEMA = "starlink-pss-acquisition-ddc-v1"
DDC_X4_ORACLE_SCHEMA = "starlink-pss-acquisition-ddc-x4-v1"
INPUT_RATE_HZ = 30_000_000
OUTPUT_RATE_HZ = 15_000_000
DECIMATION = 2
MIXER_MAGNITUDE_HZ = 7_500_000
FIR_Q15 = (-572, 0, 1260, 0, -2923, 0, 10235, 16384, 10235, 0, -2923, 0, 1260, 0, -572)
GROUP_DELAY_INPUT_SAMPLES = 7
OUTPUT_SOURCE_PHASE = 0


@dataclass(frozen=True, slots=True)
class DdcResult:
    samples_iq: npt.NDArray[np.int16]
    output_indexes: npt.NDArray[np.uint64]
    output_gaps: npt.NDArray[np.bool_]
    accepted_samples: int
    discontinuities: int
    saturation_events: int


@dataclass(frozen=True, slots=True)
class DdcX4Result:
    """Result and stage evidence for the 60-to-15 MS/s cascade."""

    stage_60_to_30: DdcResult
    stage_30_to_15: DdcResult

    @property
    def samples_iq(self) -> npt.NDArray[np.int16]:
        return self.stage_30_to_15.samples_iq

    @property
    def output_indexes(self) -> npt.NDArray[np.uint64]:
        return self.stage_30_to_15.output_indexes

    @property
    def output_gaps(self) -> npt.NDArray[np.bool_]:
        return self.stage_30_to_15.output_gaps

    @property
    def accepted_samples(self) -> int:
        return self.stage_60_to_30.accepted_samples

    @property
    def emitted_samples(self) -> int:
        return int(self.stage_30_to_15.samples_iq.shape[0])

    @property
    def discontinuities(self) -> int:
        return self.stage_30_to_15.discontinuities

    @property
    def saturation_events(self) -> int:
        return (
            self.stage_60_to_30.saturation_events
            + self.stage_30_to_15.saturation_events
        )


def _ci16_matrix(values: npt.ArrayLike) -> npt.NDArray[np.int64]:
    array = np.asarray(values)
    if array.ndim != 2 or array.shape[1] != 2:
        raise ValueError("samples must have shape (count, 2)")
    if not np.issubdtype(array.dtype, np.integer):
        raise TypeError("samples must be integer CI16 values")
    wide = np.asarray(array, dtype=np.int64)
    if np.any(wide < -32768) or np.any(wide > 32767):
        raise ValueError("samples must fit signed CI16")
    return wide


def _round_shift_q15(value: int) -> tuple[int, bool]:
    magnitude = abs(value)
    integer = magnitude >> 15
    remainder = magnitude & 0x7FFF
    if remainder > 0x4000 or (remainder == 0x4000 and (integer & 1)):
        integer += 1
    rounded = -integer if value < 0 else integer
    saturated = rounded < -32768 or rounded > 32767
    return min(32767, max(-32768, rounded)), saturated


def _mix(i_value: int, q_value: int, index: int, edge: str) -> tuple[int, int]:
    phase = index & 3
    if phase == 0:
        return i_value, q_value
    if phase == 2:
        return -i_value, -q_value
    if edge == "upper":
        return (q_value, -i_value) if phase == 1 else (-q_value, i_value)
    if edge == "lower":
        return (-q_value, i_value) if phase == 1 else (q_value, -i_value)
    raise ValueError("edge must be 'lower' or 'upper'")


def x2_ddc_ci16(
    samples_iq: npt.ArrayLike,
    *,
    first_input_index: int = 0,
    input_indexes: npt.ArrayLike | None = None,
    edge: Literal["lower", "upper"] = "upper",
    gap_before: npt.ArrayLike | None = None,
) -> DdcResult:
    """Apply the bit-exact streaming DDC to one indexed CI16 sequence."""

    samples = _ci16_matrix(samples_iq)
    if input_indexes is None:
        if (
            isinstance(first_input_index, bool)
            or not isinstance(first_input_index, int)
            or first_input_index < 0
            or first_input_index + samples.shape[0] > 1 << 64
        ):
            raise ValueError("input index range must fit unsigned 64 bits")
        source_indexes = np.arange(
            first_input_index,
            first_input_index + samples.shape[0],
            dtype=np.uint64,
        )
    else:
        raw_indexes = np.asarray(input_indexes)
        if raw_indexes.shape != (samples.shape[0],) or not np.issubdtype(
            raw_indexes.dtype, np.integer
        ):
            raise ValueError("input_indexes must contain one integer per sample")
        if np.any(raw_indexes < 0):
            raise ValueError("input indexes must fit unsigned 64 bits")
        source_indexes = np.asarray(raw_indexes, dtype=np.uint64)
    if edge not in ("lower", "upper"):
        raise ValueError("edge must be 'lower' or 'upper'")
    if gap_before is None:
        gaps = np.zeros(samples.shape[0], dtype=np.bool_)
        if gaps.size:
            gaps[0] = True
    else:
        gaps = np.asarray(gap_before, dtype=np.bool_)
        if gaps.shape != (samples.shape[0],):
            raise ValueError("gap_before must contain one flag per input sample")

    history: list[tuple[int, int]] = []
    outputs: list[tuple[int, int]] = []
    indexes: list[int] = []
    output_gaps: list[bool] = []
    gap_pending = True
    discontinuities = 0
    saturation_events = 0

    previous_index: int | None = None
    for (i_value, q_value), explicit_gap, raw_source_index in zip(
        samples, gaps, source_indexes, strict=True
    ):
        source_index = int(raw_source_index)
        discontinuity = bool(explicit_gap) or (
            previous_index is not None and source_index != previous_index + 1
        )
        previous_index = source_index
        if discontinuity:
            history.clear()
            gap_pending = True
            discontinuities += 1
        mixed = _mix(int(i_value), int(q_value), source_index, edge)
        history.append(mixed)
        if len(history) > len(FIR_Q15):
            history.pop(0)
        if (
            len(history) == len(FIR_Q15)
            and (source_index - GROUP_DELAY_INPUT_SAMPLES) % DECIMATION
            == OUTPUT_SOURCE_PHASE
        ):
            accumulator_i = sum(
                coefficient * sample[0]
                for coefficient, sample in zip(FIR_Q15, reversed(history), strict=True)
            )
            accumulator_q = sum(
                coefficient * sample[1]
                for coefficient, sample in zip(FIR_Q15, reversed(history), strict=True)
            )
            result_i, saturated_i = _round_shift_q15(accumulator_i)
            result_q, saturated_q = _round_shift_q15(accumulator_q)
            outputs.append((result_i, result_q))
            indexes.append((source_index - GROUP_DELAY_INPUT_SAMPLES) // DECIMATION)
            output_gaps.append(gap_pending)
            gap_pending = False
            saturation_events += int(saturated_i) + int(saturated_q)

    output_array = np.asarray(outputs, dtype=np.int16).reshape((-1, 2))
    index_array = np.asarray(indexes, dtype=np.uint64)
    gap_array = np.asarray(output_gaps, dtype=np.bool_)
    output_array.flags.writeable = False
    index_array.flags.writeable = False
    gap_array.flags.writeable = False
    return DdcResult(
        samples_iq=output_array,
        output_indexes=index_array,
        output_gaps=gap_array,
        accepted_samples=samples.shape[0],
        discontinuities=discontinuities,
        saturation_events=saturation_events,
    )


def x4_ddc_ci16(
    samples_iq: npt.ArrayLike,
    *,
    first_input_index: int = 0,
    input_indexes: npt.ArrayLike | None = None,
    edge: Literal["lower", "upper"] = "upper",
    gap_before: npt.ArrayLike | None = None,
) -> DdcX4Result:
    """Apply the bit-exact 60-to-30-to-15 MS/s acquisition cascade."""

    stage_60_to_30 = x2_ddc_ci16(
        samples_iq,
        first_input_index=first_input_index,
        input_indexes=input_indexes,
        edge=edge,
        gap_before=gap_before,
    )
    stage_30_to_15 = x2_ddc_ci16(
        stage_60_to_30.samples_iq,
        input_indexes=stage_60_to_30.output_indexes,
        edge=edge,
        gap_before=stage_60_to_30.output_gaps,
    )
    return DdcX4Result(
        stage_60_to_30=stage_60_to_30,
        stage_30_to_15=stage_30_to_15,
    )


def conditioned_pss(edge: Literal["lower", "upper"]) -> npt.NDArray[np.complex64]:
    """Return the unit-energy 66-tap template after the frozen float DDC."""

    if edge not in ("lower", "upper"):
        raise ValueError("edge must be 'lower' or 'upper'")
    pss_start = 128
    source = np.zeros(pss_start + 132 + 24, dtype=np.complex128)
    source[pss_start : pss_start + 132] = projected_pss(INPUT_RATE_HZ, edge)
    indexes = np.arange(source.size, dtype=np.int64)
    mixer_sign = -1.0 if edge == "upper" else 1.0
    mixed = source * np.exp(
        mixer_sign * 2j * np.pi * MIXER_MAGNITUDE_HZ * indexes / INPUT_RATE_HZ
    )
    filtered = np.convolve(mixed, np.asarray(FIR_Q15, dtype=float) / (1 << 15))
    newest = np.arange(filtered.size, dtype=np.int64)
    selected = newest[
        (newest >= GROUP_DELAY_INPUT_SAMPLES)
        & ((newest - GROUP_DELAY_INPUT_SAMPLES) % DECIMATION == OUTPUT_SOURCE_PHASE)
    ]
    output_indexes = (selected - GROUP_DELAY_INPUT_SAMPLES) // DECIMATION
    first = pss_start // DECIMATION
    wanted = (output_indexes >= first) & (output_indexes < first + 66)
    result = filtered[selected[wanted]]
    if result.shape != (66,):
        raise RuntimeError("conditioned PSS did not close to 66 output taps")
    norm = float(np.linalg.norm(result))
    if not np.isfinite(norm) or norm <= 0:
        raise RuntimeError("conditioned PSS has no finite energy")
    output = np.asarray(result / norm, dtype=np.complex64)
    output.flags.writeable = False
    return output


def conditioned_pss_x4(
    edge: Literal["lower", "upper"],
) -> npt.NDArray[np.complex64]:
    """Return the unit-energy 66-tap template after the frozen float cascade."""

    if edge not in ("lower", "upper"):
        raise ValueError("edge must be 'lower' or 'upper'")
    pss_start = 256
    source = np.zeros(pss_start + 264 + 64, dtype=np.complex128)
    source[pss_start : pss_start + 264] = projected_pss(60_000_000, edge)
    mixer_sign = -1.0 if edge == "upper" else 1.0
    coefficients = np.asarray(FIR_Q15, dtype=float) / (1 << 15)

    indexes_60 = np.arange(source.size, dtype=np.int64)
    mixed_60 = source * np.exp(
        mixer_sign * 2j * np.pi * (60_000_000 / 4) * indexes_60 / 60_000_000
    )
    filtered_30 = np.convolve(mixed_60, coefficients)
    newest_60 = np.arange(filtered_30.size, dtype=np.int64)
    selected_60 = newest_60[
        (newest_60 >= GROUP_DELAY_INPUT_SAMPLES)
        & ((newest_60 - GROUP_DELAY_INPUT_SAMPLES) % DECIMATION
           == OUTPUT_SOURCE_PHASE)
    ]
    indexes_30 = (selected_60 - GROUP_DELAY_INPUT_SAMPLES) // DECIMATION
    samples_30 = filtered_30[selected_60]

    mixed_30 = samples_30 * np.exp(
        mixer_sign * 2j * np.pi * MIXER_MAGNITUDE_HZ
        * indexes_30 / INPUT_RATE_HZ
    )
    filtered_15 = np.convolve(mixed_30, coefficients)
    newest_30 = indexes_30[0] + np.arange(filtered_15.size, dtype=np.int64)
    selected_30_relative = np.arange(filtered_15.size, dtype=np.int64)[
        (newest_30 >= GROUP_DELAY_INPUT_SAMPLES)
        & ((newest_30 - GROUP_DELAY_INPUT_SAMPLES) % DECIMATION
           == OUTPUT_SOURCE_PHASE)
    ]
    indexes_15 = (
        newest_30[selected_30_relative] - GROUP_DELAY_INPUT_SAMPLES
    ) // DECIMATION
    samples_15 = filtered_15[selected_30_relative]

    first = pss_start // 4
    wanted = (indexes_15 >= first) & (indexes_15 < first + 66)
    result = samples_15[wanted]
    if result.shape != (66,):
        raise RuntimeError("x4-conditioned PSS did not close to 66 output taps")
    norm = float(np.linalg.norm(result))
    if not np.isfinite(norm) or norm <= 0:
        raise RuntimeError("x4-conditioned PSS has no finite energy")
    output = np.asarray(result / norm, dtype=np.complex64)
    output.flags.writeable = False
    return output


def ddc_contract_sha256() -> str:
    """Hash the implementation-defining, JSON-canonical DDC contract."""

    payload = {
        "schema": DDC_ORACLE_SCHEMA,
        "input_rate_hz": INPUT_RATE_HZ,
        "output_rate_hz": OUTPUT_RATE_HZ,
        "decimation": DECIMATION,
        "mixer_magnitude_hz": MIXER_MAGNITUDE_HZ,
        "fir_q15": FIR_Q15,
        "group_delay_input_samples": GROUP_DELAY_INPUT_SAMPLES,
        "output_source_phase": OUTPUT_SOURCE_PHASE,
        "conditioned_pss_complex64_sha256": {
            edge: complex64_sha256(conditioned_pss(edge))
            for edge in ("lower", "upper")
        },
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def ddc_x4_contract_sha256() -> str:
    """Hash the implementation-defining 60-to-15 cascade contract."""

    payload = {
        "schema": DDC_X4_ORACLE_SCHEMA,
        "input_rate_hz": 60_000_000,
        "output_rate_hz": OUTPUT_RATE_HZ,
        "stage_count": 2,
        "stage_contract_sha256": ddc_contract_sha256(),
        "total_decimation": DECIMATION * DECIMATION,
        "total_group_delay_input_samples": 21,
        "output_source_phase": OUTPUT_SOURCE_PHASE,
        "telemetry": {
            "accepted_samples": "stage_60_to_30",
            "emitted_samples": "stage_30_to_15",
            "discontinuities": "stage_30_to_15",
            "saturation_events": "sum_of_both_stages",
        },
        "conditioned_pss_complex64_sha256": {
            edge: complex64_sha256(conditioned_pss_x4(edge))
            for edge in ("lower", "upper")
        },
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()
