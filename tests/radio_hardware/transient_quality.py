"""Deterministic transient-response measurements for dual-RX AGC tests.

The steady-state tandem-quality matrix intentionally drains transitions before
it scores IQ.  This module provides the complementary, transport-independent
pieces needed to retain and score those transitions.  Hardware integration is
limited to injected callbacks: callers timestamp an attribute write, capture
ordinary or metadata IQ with their existing transport, and pass the resulting
bytes, sample counters, and tandem events to the pure analyzers below.

Frame and window sample intervals are half-open.  A stimulus command is known
to have occurred somewhere in the closed bracket
``[sample_sequence_before, sample_sequence_after]``; latencies therefore
remain bounds rather than falsely precise point values.
Malformed, missing, discontinuous, or excessively uncertain evidence raises
``TransientEvidenceError`` instead of producing a best-effort verdict.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from .tone_quality import decode_dual_iq

_UINT32_MODULUS = 1 << 32
_UINT64_MODULUS = 1 << 64


class TransientEvidenceError(ValueError):
    """Transient evidence is incomplete or internally inconsistent."""


@dataclass(frozen=True)
class StimulusCommand:
    """A write bracketed in host time and, when available, RF sample time."""

    command_id: str
    requested_level_db: float
    applied_level_db: float
    host_before_ns: int
    host_after_ns: int
    sample_sequence_before: int | None
    sample_sequence_after: int | None

    @property
    def host_jitter_ns(self) -> int:
        return self.host_after_ns - self.host_before_ns

    @property
    def sample_uncertainty(self) -> int | None:
        if self.sample_sequence_before is None or self.sample_sequence_after is None:
            return None
        return self.sample_sequence_after - self.sample_sequence_before

    def as_dict(self) -> Mapping[str, Any]:
        """Return a JSON-safe representation for an atomic campaign report."""

        return {
            "command_id": self.command_id,
            "requested_level_db": self.requested_level_db,
            "applied_level_db": self.applied_level_db,
            "host_before_ns": self.host_before_ns,
            "host_after_ns": self.host_after_ns,
            "host_jitter_ns": self.host_jitter_ns,
            "sample_sequence_before": self.sample_sequence_before,
            "sample_sequence_after": self.sample_sequence_after,
            "sample_uncertainty": self.sample_uncertainty,
        }


def _finite_float(value: Any, *, name: str) -> float:
    if isinstance(value, bool):
        raise TransientEvidenceError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise TransientEvidenceError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise TransientEvidenceError(f"{name} must be a finite number")
    return result


def _strict_int(value: Any, *, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TransientEvidenceError(f"{name} must be an integer")
    if value < minimum:
        raise TransientEvidenceError(f"{name} must be at least {minimum}")
    return value


def timestamp_stimulus_command(
    command_id: str,
    requested_level_db: float,
    *,
    apply: Callable[[float], float],
    clock_ns: Callable[[], int] = time.monotonic_ns,
    sample_sequence: Callable[[], int] | None = None,
    max_host_jitter_ns: int | None = None,
    max_sample_uncertainty: int | None = None,
    readback_tolerance_db: float = 0.25,
) -> StimulusCommand:
    """Apply one stimulus and retain conservative timing/readback evidence.

    ``apply`` must return the hardware readback, not merely the requested
    value.  An optional ``sample_sequence`` callback is invoked immediately
    before and after the write.  It may read a free-running device counter or
    return a counter anchor supplied by an already-open metadata transport.
    The injected clock makes the operation deterministic in offline oracles.
    """

    if not isinstance(command_id, str) or not command_id:
        raise TransientEvidenceError("command_id must be a nonempty string")
    requested = _finite_float(requested_level_db, name="requested_level_db")
    tolerance = _finite_float(readback_tolerance_db, name="readback_tolerance_db")
    if tolerance < 0:
        raise TransientEvidenceError("readback_tolerance_db cannot be negative")
    if max_host_jitter_ns is not None:
        _strict_int(max_host_jitter_ns, name="max_host_jitter_ns", minimum=1)
    if max_sample_uncertainty is not None:
        _strict_int(
            max_sample_uncertainty,
            name="max_sample_uncertainty",
            minimum=0,
        )

    sample_before = None
    if sample_sequence is not None:
        sample_before = _strict_int(sample_sequence(), name="sample_sequence_before")
    host_before = _strict_int(clock_ns(), name="host_before_ns")
    applied = _finite_float(apply(requested), name="applied_level_db")
    host_after = _strict_int(clock_ns(), name="host_after_ns")
    sample_after = None
    if sample_sequence is not None:
        sample_after = _strict_int(sample_sequence(), name="sample_sequence_after")

    if host_after < host_before:
        raise TransientEvidenceError("host monotonic clock moved backward")
    if sample_before is not None and sample_after is not None:
        if sample_after < sample_before:
            raise TransientEvidenceError("hardware sample sequence moved backward")
        if sample_after >= _UINT64_MODULUS:
            raise TransientEvidenceError("hardware sample sequence exceeds uint64")
    if abs(applied - requested) > tolerance:
        raise TransientEvidenceError(
            "stimulus readback differs from the requested level by more than "
            f"{tolerance:g} dB"
        )

    command = StimulusCommand(
        command_id=command_id,
        requested_level_db=requested,
        applied_level_db=applied,
        host_before_ns=host_before,
        host_after_ns=host_after,
        sample_sequence_before=sample_before,
        sample_sequence_after=sample_after,
    )
    _validate_command_uncertainty(
        command,
        max_host_jitter_ns=max_host_jitter_ns,
        max_sample_uncertainty=max_sample_uncertainty,
        require_sample_bounds=False,
    )
    return command


def _validate_command_uncertainty(
    command: StimulusCommand,
    *,
    max_host_jitter_ns: int | None,
    max_sample_uncertainty: int | None,
    require_sample_bounds: bool,
) -> None:
    if not isinstance(command.command_id, str) or not command.command_id:
        raise TransientEvidenceError("command_id must be a nonempty string")
    _finite_float(command.requested_level_db, name="requested_level_db")
    _finite_float(command.applied_level_db, name="applied_level_db")
    host_before = _strict_int(command.host_before_ns, name="host_before_ns")
    host_after = _strict_int(command.host_after_ns, name="host_after_ns")
    if max_host_jitter_ns is not None:
        _strict_int(max_host_jitter_ns, name="max_host_jitter_ns", minimum=1)
    if max_sample_uncertainty is not None:
        _strict_int(
            max_sample_uncertainty,
            name="max_sample_uncertainty",
            minimum=0,
        )
    if host_after < host_before:
        raise TransientEvidenceError(
            f"command {command.command_id!r} has a backward host bracket"
        )
    if max_host_jitter_ns is not None and command.host_jitter_ns > max_host_jitter_ns:
        raise TransientEvidenceError(
            f"command {command.command_id!r} host jitter "
            f"{command.host_jitter_ns} ns exceeds {max_host_jitter_ns} ns"
        )
    before = command.sample_sequence_before
    after = command.sample_sequence_after
    if before is None or after is None:
        if require_sample_bounds:
            raise TransientEvidenceError(
                f"command {command.command_id!r} lacks sample-sequence bounds"
            )
        return
    before = _strict_int(before, name="sample_sequence_before")
    after = _strict_int(after, name="sample_sequence_after")
    if after < before or after >= _UINT64_MODULUS:
        raise TransientEvidenceError(
            f"command {command.command_id!r} has invalid sample-sequence bounds"
        )
    uncertainty = after - before
    if max_sample_uncertainty is not None and uncertainty > max_sample_uncertainty:
        raise TransientEvidenceError(
            f"command {command.command_id!r} sample uncertainty {uncertainty} "
            f"exceeds {max_sample_uncertainty} samples"
        )


def _numpy() -> Any:
    try:
        import numpy
    except ImportError as exc:
        raise RuntimeError("transient-quality analysis requires numpy") from exc
    return numpy


def _signal_matrix(value: Any) -> Any:
    np = _numpy()
    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            matrix = decode_dual_iq(value)
        except ValueError as exc:
            raise TransientEvidenceError(str(exc)) from exc
    else:
        matrix = np.asarray(value)
    if matrix.ndim != 2 or matrix.shape[0] != 2:
        raise TransientEvidenceError(
            f"dual-RX signal must have shape (2, samples), got {matrix.shape}"
        )
    if not matrix.shape[1]:
        raise TransientEvidenceError("dual-RX signal contains no samples")
    if not np.isfinite(matrix).all():
        raise TransientEvidenceError("dual-RX signal contains non-finite values")
    return matrix.astype(np.complex128, copy=False)


def _circular_stats(phases: Any) -> tuple[float, float]:
    np = _numpy()
    resultant = np.mean(np.exp(1j * phases))
    length = float(np.clip(abs(resultant), 0.0, 1.0))
    standard_deviation = math.sqrt(-2.0 * math.log(max(length, 1e-15)))
    return float(np.angle(resultant)), math.degrees(standard_deviation)


def _select_tone_sign(signal: Any, *, sample_rate_hz: int, tone_hz: float) -> float:
    """Choose one IQ spectral sign for the complete frame and hold it fixed."""

    np = _numpy()
    indexes = np.arange(signal.shape[1], dtype=np.float64)
    centered = signal - np.mean(signal, axis=1)[:, None]
    candidates = (
        math.copysign(abs(tone_hz), tone_hz),
        -math.copysign(abs(tone_hz), tone_hz),
    )
    powers = []
    for candidate in candidates:
        oscillator = np.exp(-2j * np.pi * candidate * indexes / sample_rate_hz)
        amplitudes = np.mean(centered * oscillator[None, :], axis=1)
        powers.append(float(np.sum(np.abs(amplitudes) ** 2)))
    return float(candidates[0] if powers[0] >= powers[1] else candidates[1])


def analyze_immediate_dual_rx(
    signal_or_raw: Any,
    *,
    first_sample_sequence: int,
    sample_rate_hz: int,
    expected_tone_hz: float,
    window_samples: int = 2_048,
    stride_samples: int | None = None,
    phase_segments: int = 4,
    adc_full_scale: float = 2_048.0,
    min_tone_snr_db: float = 10.0,
    max_clipping_fraction: float = 0.0,
    max_phase_std_deg: float = 5.0,
) -> Mapping[str, Any]:
    """Analyze fixed windows starting at the first sample of a dual-RX frame.

    No samples are discarded.  The carrier sign is selected once from the
    complete frame, then a known-frequency complex tone is fitted separately
    in every window.  A level transition inside a window remains in its
    residual and can therefore lower that window's reported SNR, as desired.
    """

    np = _numpy()
    matrix = _signal_matrix(signal_or_raw)
    first_sequence = _strict_int(first_sample_sequence, name="first_sample_sequence")
    rate = _strict_int(sample_rate_hz, name="sample_rate_hz", minimum=1)
    window = _strict_int(window_samples, name="window_samples", minimum=64)
    stride = (
        window
        if stride_samples is None
        else _strict_int(stride_samples, name="stride_samples", minimum=1)
    )
    segments = _strict_int(phase_segments, name="phase_segments", minimum=2)
    if window < segments * 16:
        raise TransientEvidenceError(
            "window_samples must provide at least 16 samples per phase segment"
        )
    full_scale = _finite_float(adc_full_scale, name="adc_full_scale")
    if full_scale <= 1:
        raise TransientEvidenceError("adc_full_scale must be greater than one")
    expected = _finite_float(expected_tone_hz, name="expected_tone_hz")
    if expected == 0 or abs(expected) >= rate / 2:
        raise TransientEvidenceError(
            "expected_tone_hz must be nonzero and strictly inside Nyquist"
        )
    minimum_snr = _finite_float(min_tone_snr_db, name="min_tone_snr_db")
    clipping_limit = _finite_float(max_clipping_fraction, name="max_clipping_fraction")
    phase_limit = _finite_float(max_phase_std_deg, name="max_phase_std_deg")
    if not 0 <= clipping_limit <= 1:
        raise TransientEvidenceError("max_clipping_fraction must lie in [0, 1]")
    if phase_limit < 0:
        raise TransientEvidenceError("max_phase_std_deg cannot be negative")
    if matrix.shape[1] < window:
        raise TransientEvidenceError("frame is shorter than one analysis window")
    if first_sequence + int(matrix.shape[1]) > _UINT64_MODULUS:
        raise TransientEvidenceError("frame sample-sequence range exceeds uint64")

    selected_tone_hz = _select_tone_sign(matrix, sample_rate_hz=rate, tone_hz=expected)
    numerical_floor = np.finfo(np.float64).tiny
    results: list[Mapping[str, Any]] = []
    starts = range(0, int(matrix.shape[1]) - window + 1, stride)
    for window_index, start in enumerate(starts):
        end = start + window
        raw = matrix[:, start:end]
        signal = raw - np.mean(raw, axis=1)[:, None]
        indexes = np.arange(start, end, dtype=np.float64)
        oscillator = np.exp(-2j * np.pi * selected_tone_hz * indexes / rate)
        amplitudes = np.mean(signal * oscillator[None, :], axis=1)
        fitted = amplitudes[:, None] * np.exp(
            2j * np.pi * selected_tone_hz * indexes / rate
        )
        residual_power = np.mean(np.abs(signal - fitted) ** 2, axis=1)
        tone_power = np.abs(amplitudes) ** 2
        with np.errstate(divide="ignore"):
            tone_dbfs = 20.0 * np.log10(
                np.maximum(np.abs(amplitudes), numerical_floor) / full_scale
            )
            tone_snr_db = 10.0 * np.log10(
                np.maximum(tone_power, numerical_floor)
                / np.maximum(residual_power, numerical_floor)
            )
        clipping = np.mean(
            (raw.real <= -full_scale)
            | (raw.real >= full_scale - 1)
            | (raw.imag <= -full_scale)
            | (raw.imag >= full_scale - 1),
            axis=1,
        )

        segment_length = window // segments
        segment_phases: list[float] = []
        for segment_index in range(segments):
            segment_start = segment_index * segment_length
            segment_end = (
                window
                if segment_index == segments - 1
                else segment_start + segment_length
            )
            segment_indexes = indexes[segment_start:segment_end]
            segment_oscillator = np.exp(
                -2j * np.pi * selected_tone_hz * segment_indexes / rate
            )
            segment_amplitude = np.mean(
                signal[:, segment_start:segment_end] * segment_oscillator[None, :],
                axis=1,
            )
            segment_phases.append(
                float(np.angle(segment_amplitude[0] * np.conj(segment_amplitude[1])))
            )
        phase_difference, phase_std_deg = _circular_stats(np.asarray(segment_phases))

        reasons: list[str] = []
        for channel in range(2):
            if tone_snr_db[channel] < minimum_snr:
                reasons.append(f"rx{channel}_tone_snr_low")
            if clipping[channel] > clipping_limit:
                reasons.append(f"rx{channel}_clipping")
        if phase_std_deg > phase_limit:
            reasons.append("within_window_phase_unstable")
        results.append(
            {
                "window_index": window_index,
                "offset_start": start,
                "offset_end_exclusive": end,
                "sample_start": first_sequence + start,
                "sample_end_exclusive": first_sequence + end,
                "tone_dbfs": [float(value) for value in tone_dbfs],
                "mean_tone_dbfs": float(np.mean(tone_dbfs)),
                "tone_snr_db": [float(value) for value in tone_snr_db],
                "clipping_fraction": [float(value) for value in clipping],
                "phase_difference_rad": phase_difference,
                "phase_difference_deg": math.degrees(phase_difference),
                "within_window_phase_std_deg": phase_std_deg,
                "quality_valid": not reasons,
                "quality_reasons": reasons,
            }
        )

    last_end = int(results[-1]["offset_end_exclusive"])
    return {
        "first_sample_sequence": first_sequence,
        "samples_per_channel": int(matrix.shape[1]),
        "sample_rate_hz": rate,
        "expected_tone_hz": expected,
        "selected_tone_hz": selected_tone_hz,
        "window_samples": window,
        "stride_samples": stride,
        "window_count": len(results),
        "uncovered_tail_samples": int(matrix.shape[1]) - last_end,
        "quality_valid": all(bool(item["quality_valid"]) for item in results),
        "windows": results,
    }


def _event_field(event: Any, *names: str) -> Any:
    for name in names:
        if isinstance(event, Mapping) and name in event:
            return event[name]
        if hasattr(event, name):
            return getattr(event, name)
    raise TransientEvidenceError(f"tandem event lacks required field {'/'.join(names)}")


def _event_direction(value: Any) -> str:
    if hasattr(value, "name"):
        value = value.name
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"increase", "decrease"}:
            return normalized
    if isinstance(value, int) and not isinstance(value, bool):
        if value == 1:
            return "increase"
        if value == 2:
            return "decrease"
    raise TransientEvidenceError(f"invalid tandem event direction {value!r}")


def _normalize_events(events: Sequence[Any]) -> list[Mapping[str, Any]]:
    normalized: list[Mapping[str, Any]] = []
    for index, event in enumerate(events):
        sample = _strict_int(
            _event_field(event, "sample_sequence"),
            name=f"event {index} sample_sequence",
        )
        if sample >= _UINT64_MODULUS:
            raise TransientEvidenceError(
                f"event {index} sample_sequence exceeds uint64"
            )
        sequence = _strict_int(
            _event_field(event, "event_sequence"),
            name=f"event {index} event_sequence",
        )
        if sequence >= _UINT32_MODULUS:
            raise TransientEvidenceError(f"event {index} event_sequence exceeds uint32")
        direction_source = _event_field(event, "direction_name", "direction")
        direction = _event_direction(direction_source)
        if (isinstance(event, Mapping) and "rx2_gain_index" in event) or hasattr(
            event, "rx2_gain_index"
        ):
            # Metadata uses AD9361 names RX1/RX2 for the bench's RX0/RX1.
            rx0_source = _event_field(event, "rx1_gain_index")
            rx1_source = _event_field(event, "rx2_gain_index")
        else:
            rx0_source = _event_field(event, "rx0_gain_index")
            rx1_source = _event_field(event, "rx1_gain_index")
        rx0_gain = _strict_int(rx0_source, name=f"event {index} RX0 gain index")
        rx1_gain = _strict_int(rx1_source, name=f"event {index} RX1 gain index")
        if rx0_gain > 255 or rx1_gain > 255:
            raise TransientEvidenceError(f"event {index} gain index exceeds uint8")
        if rx0_gain != rx1_gain:
            raise TransientEvidenceError(f"event {index} contains a torn gain pair")
        current = {
            "sample_sequence": sample,
            "event_sequence": sequence,
            "direction": direction,
            "rx0_gain_index": rx0_gain,
            "rx1_gain_index": rx1_gain,
        }
        if normalized:
            previous = normalized[-1]
            if sample < int(previous["sample_sequence"]):
                raise TransientEvidenceError(
                    "tandem events are not globally sample ordered"
                )
            sequence_delta = (
                sequence - int(previous["event_sequence"])
            ) % _UINT32_MODULUS
            if sequence_delta != 1:
                raise TransientEvidenceError(
                    "tandem event sequence is duplicated or has missing evidence"
                )
            expected_gain = int(previous["rx0_gain_index"]) + (
                1 if direction == "increase" else -1
            )
            if rx0_gain != expected_gain:
                raise TransientEvidenceError(
                    "consecutive tandem event gain does not take its exact +/-1 step"
                )
        normalized.append(current)
    return normalized


def reconcile_tandem_events(
    commands: Sequence[StimulusCommand],
    events: Sequence[Any],
    *,
    sample_rate_hz: int,
    max_host_jitter_ns: int = 5_000_000,
    max_sample_uncertainty: int = 25_000,
    max_latency_samples: int | None = None,
) -> Mapping[str, Any]:
    """Attribute the first paired attack/release event to each TX step.

    Increasing TX level requires a tandem gain decrease (attack); decreasing
    TX level requires a gain increase (release).  Events may fall inside the
    bounded command interval, in which case the latency lower bound is zero.
    An event at or beyond the following command's lower sample bound cannot be
    attributed to the current command.
    """

    rate = _strict_int(sample_rate_hz, name="sample_rate_hz", minimum=1)
    host_limit = _strict_int(max_host_jitter_ns, name="max_host_jitter_ns", minimum=1)
    sample_limit = _strict_int(
        max_sample_uncertainty, name="max_sample_uncertainty", minimum=0
    )
    if max_latency_samples is not None:
        _strict_int(max_latency_samples, name="max_latency_samples", minimum=0)
    if len(commands) < 2:
        raise TransientEvidenceError(
            "at least two stimulus commands are required to prove a response"
        )
    command_list = list(commands)
    for command in command_list:
        if not isinstance(command, StimulusCommand):
            raise TransientEvidenceError("commands must be StimulusCommand records")
        _validate_command_uncertainty(
            command,
            max_host_jitter_ns=host_limit,
            max_sample_uncertainty=sample_limit,
            require_sample_bounds=True,
        )
    for previous, current in pairwise(command_list):
        assert previous.sample_sequence_after is not None
        assert current.sample_sequence_before is not None
        if current.host_before_ns < previous.host_after_ns:
            raise TransientEvidenceError("stimulus command host brackets overlap")
        if current.sample_sequence_before < previous.sample_sequence_after:
            raise TransientEvidenceError("stimulus command sample brackets overlap")

    normalized_events = _normalize_events(events)
    transitions: list[Mapping[str, Any]] = []
    ignored_repeated_commands: list[str] = []
    for index in range(1, len(command_list)):
        previous_command = command_list[index - 1]
        command = command_list[index]
        stimulus_delta = command.applied_level_db - previous_command.applied_level_db
        if stimulus_delta == 0:
            ignored_repeated_commands.append(command.command_id)
            continue
        expected_direction = "decrease" if stimulus_delta > 0 else "increase"
        response_kind = "attack" if stimulus_delta > 0 else "release"
        assert command.sample_sequence_before is not None
        assert command.sample_sequence_after is not None
        interval_end = _UINT64_MODULUS
        if index + 1 < len(command_list):
            next_command = command_list[index + 1]
            assert next_command.sample_sequence_before is not None
            interval_end = next_command.sample_sequence_before
        matching = [
            event
            for event in normalized_events
            if command.sample_sequence_before
            <= int(event["sample_sequence"])
            < interval_end
            and event["direction"] == expected_direction
        ]
        if not matching:
            raise TransientEvidenceError(
                f"command {command.command_id!r} lacks a paired {response_kind} "
                f"event before the next command boundary"
            )
        event = matching[0]
        event_sample = int(event["sample_sequence"])
        lower_samples = max(0, event_sample - command.sample_sequence_after)
        upper_samples = event_sample - command.sample_sequence_before
        if upper_samples < 0:
            raise TransientEvidenceError(
                f"command {command.command_id!r} response predates its sample bracket"
            )
        if max_latency_samples is not None and upper_samples > max_latency_samples:
            raise TransientEvidenceError(
                f"command {command.command_id!r} {response_kind} latency upper bound "
                f"{upper_samples} exceeds {max_latency_samples} samples"
            )
        transitions.append(
            {
                "command_id": command.command_id,
                "response_kind": response_kind,
                "stimulus_delta_db": stimulus_delta,
                "expected_event_direction": expected_direction,
                "command_sample_lower": command.sample_sequence_before,
                "command_sample_upper": command.sample_sequence_after,
                "event": event,
                "event_within_command_bracket": (
                    event_sample <= command.sample_sequence_after
                ),
                "latency_lower_samples": lower_samples,
                "latency_upper_samples": upper_samples,
                "latency_lower_seconds": lower_samples / rate,
                "latency_upper_seconds": upper_samples / rate,
            }
        )
    if not transitions:
        raise TransientEvidenceError("stimulus commands contain no level transition")
    assigned_sequences = {
        int(transition["event"]["event_sequence"]) for transition in transitions
    }
    return {
        "evidence_valid": True,
        "sample_rate_hz": rate,
        "command_count": len(command_list),
        "event_count": len(normalized_events),
        "unassigned_event_count": sum(
            int(event["event_sequence"]) not in assigned_sequences
            for event in normalized_events
        ),
        "ignored_repeated_commands": ignored_repeated_commands,
        "transitions": transitions,
    }


def _window_pair(window: Mapping[str, Any], key: str) -> tuple[float, float]:
    value = window.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TransientEvidenceError(f"transient window lacks two-value {key}")
    if len(value) != 2:
        raise TransientEvidenceError(f"transient window {key} is not dual-RX")
    return (
        _finite_float(value[0], name=f"window {key}[0]"),
        _finite_float(value[1], name=f"window {key}[1]"),
    )


def _circular_distance_degrees(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


def _crossing_count(values: Sequence[float], center: float, deadband: float) -> int:
    previous_sign = 0
    crossings = 0
    for value in values:
        delta = value - center
        sign = 1 if delta > deadband else -1 if delta < -deadband else 0
        if sign and previous_sign and sign != previous_sign:
            crossings += 1
        if sign:
            previous_sign = sign
    return crossings


def calculate_transient_response(
    windows: Sequence[Mapping[str, Any]],
    *,
    previous_command: StimulusCommand,
    command: StimulusCommand,
    sample_rate_hz: int,
    baseline_windows: int = 3,
    steady_windows: int = 3,
    stable_windows: int = 3,
    settling_tolerance_db: float = 1.0,
    ringing_deadband_db: float = 0.25,
    max_host_jitter_ns: int = 5_000_000,
    max_sample_uncertainty: int = 25_000,
) -> Mapping[str, Any]:
    """Calculate window-bounded settling, overshoot, and ringing metrics.

    Input windows must be non-overlapping and sample-contiguous outside the
    uncertain command interval.  A missing range wholly covered by that
    interval is accepted and counted: a host-side write can delay the next
    refill, and hardware metadata can expose that delay as a sample gap.  A
    window intersecting the interval is retained but excluded from
    baseline/post-step statistics.
    """

    rate = _strict_int(sample_rate_hz, name="sample_rate_hz", minimum=1)
    baseline_count = _strict_int(baseline_windows, name="baseline_windows", minimum=1)
    steady_count = _strict_int(steady_windows, name="steady_windows", minimum=1)
    stable_count = _strict_int(stable_windows, name="stable_windows", minimum=1)
    tolerance = _finite_float(settling_tolerance_db, name="settling_tolerance_db")
    deadband = _finite_float(ringing_deadband_db, name="ringing_deadband_db")
    if tolerance < 0 or deadband < 0:
        raise TransientEvidenceError(
            "settling tolerance and ringing deadband cannot be negative"
        )
    for item in (previous_command, command):
        _validate_command_uncertainty(
            item,
            max_host_jitter_ns=max_host_jitter_ns,
            max_sample_uncertainty=max_sample_uncertainty,
            require_sample_bounds=True,
        )
    assert previous_command.sample_sequence_after is not None
    assert command.sample_sequence_before is not None
    if command.host_before_ns < previous_command.host_after_ns:
        raise TransientEvidenceError("stimulus command host brackets overlap")
    if command.sample_sequence_before < previous_command.sample_sequence_after:
        raise TransientEvidenceError("stimulus command sample brackets overlap")
    stimulus_delta = command.applied_level_db - previous_command.applied_level_db
    if stimulus_delta == 0:
        raise TransientEvidenceError("transient response requires a nonzero TX step")
    assert command.sample_sequence_after is not None

    normalized: list[Mapping[str, Any]] = []
    command_bracket_gap_samples = 0
    for index, window in enumerate(windows):
        if not isinstance(window, Mapping):
            raise TransientEvidenceError(f"window {index} is not a record")
        start = _strict_int(window.get("sample_start"), name=f"window {index} start")
        end = _strict_int(
            window.get("sample_end_exclusive"), name=f"window {index} end"
        )
        if end <= start:
            raise TransientEvidenceError(f"window {index} has an empty sample range")
        if end > _UINT64_MODULUS:
            raise TransientEvidenceError(f"window {index} exceeds uint64 sample time")
        tone = _window_pair(window, "tone_dbfs")
        snr = _window_pair(window, "tone_snr_db")
        clipping = _window_pair(window, "clipping_fraction")
        if any(not 0 <= value <= 1 for value in clipping):
            raise TransientEvidenceError(
                f"window {index} clipping fraction lies outside [0, 1]"
            )
        phase = _finite_float(
            window.get("phase_difference_deg"),
            name=f"window {index} phase_difference_deg",
        )
        if normalized:
            previous_end = int(normalized[-1]["sample_end_exclusive"])
            if start < previous_end:
                raise TransientEvidenceError(
                    "transient windows overlap or have a reordered sample range"
                )
            if start > previous_end:
                gap_is_command_bracketed = (
                    previous_end >= command.sample_sequence_before
                    and start <= command.sample_sequence_after
                )
                if not gap_is_command_bracketed:
                    raise TransientEvidenceError(
                        "transient windows have a gap, overlap, or reordered "
                        "sample range outside the command bracket"
                    )
                command_bracket_gap_samples += start - previous_end
        normalized.append(
            {
                "sample_start": start,
                "sample_end_exclusive": end,
                "tone_dbfs": tone,
                "tone_snr_db": snr,
                "clipping_fraction": clipping,
                "phase_difference_deg": phase,
            }
        )
    if not normalized:
        raise TransientEvidenceError("transient response has no IQ windows")

    pre = [
        window
        for window in normalized
        if int(window["sample_end_exclusive"]) <= command.sample_sequence_before
    ]
    post = [
        window
        for window in normalized
        if int(window["sample_start"]) >= command.sample_sequence_after
    ]
    if len(pre) < baseline_count:
        raise TransientEvidenceError("missing pre-command baseline windows")
    if len(post) < max(steady_count, stable_count):
        raise TransientEvidenceError("missing post-command steady-state windows")
    excluded = len(normalized) - len(pre) - len(post)

    np = _numpy()
    baseline = [
        float(
            np.median(
                [window["tone_dbfs"][channel] for window in pre[-baseline_count:]]
            )
        )
        for channel in range(2)
    ]
    steady = [
        float(
            np.median([window["tone_dbfs"][channel] for window in post[-steady_count:]])
        )
        for channel in range(2)
    ]
    direction = 1.0 if stimulus_delta > 0 else -1.0
    overshoot = []
    undershoot = []
    for channel in range(2):
        deviations = [
            direction * (float(window["tone_dbfs"][channel]) - steady[channel])
            for window in post
        ]
        overshoot.append(max(0.0, max(deviations)))
        undershoot.append(max(0.0, -min(deviations)))

    first_stable_index = None
    for start in range(len(post) - stable_count + 1):
        candidate = post[start : start + stable_count]
        if all(
            all(
                abs(float(window["tone_dbfs"][channel]) - steady[channel]) <= tolerance
                for channel in range(2)
            )
            for window in candidate
        ):
            first_stable_index = start
            break
    if first_stable_index is None:
        raise TransientEvidenceError(
            "post-command IQ never supplies the required stable window run"
        )
    stable_first = post[first_stable_index]
    lower_samples = max(
        0, int(stable_first["sample_start"]) - command.sample_sequence_after
    )
    upper_samples = (
        int(stable_first["sample_end_exclusive"]) - command.sample_sequence_before
    )
    if upper_samples < lower_samples:
        raise TransientEvidenceError("signal-settling latency bounds are inverted")

    after_stable = post[first_stable_index + stable_count :]
    ringing_excursions = sum(
        any(
            abs(float(window["tone_dbfs"][channel]) - steady[channel]) > tolerance
            for channel in range(2)
        )
        for window in after_stable
    )
    crossings = [
        _crossing_count(
            [float(window["tone_dbfs"][channel]) for window in post],
            steady[channel],
            deadband,
        )
        for channel in range(2)
    ]
    ringing_peak_to_peak = [
        (
            max(
                float(window["tone_dbfs"][channel])
                for window in post[first_stable_index:]
            )
            - min(
                float(window["tone_dbfs"][channel])
                for window in post[first_stable_index:]
            )
        )
        for channel in range(2)
    ]
    baseline_phase_rad, _baseline_phase_std_deg = _circular_stats(
        np.radians([window["phase_difference_deg"] for window in pre[-baseline_count:]])
    )
    baseline_phase = math.degrees(baseline_phase_rad)
    phase_excursion = max(
        _circular_distance_degrees(
            float(window["phase_difference_deg"]), baseline_phase
        )
        for window in post
    )

    return {
        "evidence_valid": True,
        "command_id": command.command_id,
        "response_kind": "attack" if stimulus_delta > 0 else "release",
        "stimulus_delta_db": stimulus_delta,
        "baseline_tone_dbfs": baseline,
        "steady_tone_dbfs": steady,
        "steady_change_db": [
            steady[channel] - baseline[channel] for channel in range(2)
        ],
        "overshoot_db": overshoot,
        "worst_overshoot_db": max(overshoot),
        "opposite_excursion_db": undershoot,
        "ringing_crossings": crossings,
        "ringing_excursions_after_stable": ringing_excursions,
        "ringing_peak_to_peak_db": ringing_peak_to_peak,
        "signal_settling_latency_lower_samples": lower_samples,
        "signal_settling_latency_upper_samples": upper_samples,
        "signal_settling_latency_lower_seconds": lower_samples / rate,
        "signal_settling_latency_upper_seconds": upper_samples / rate,
        "minimum_post_tone_snr_db": min(min(window["tone_snr_db"]) for window in post),
        "maximum_post_clipping_fraction": max(
            max(window["clipping_fraction"]) for window in post
        ),
        "maximum_phase_excursion_deg": phase_excursion,
        "baseline_window_count": baseline_count,
        "post_window_count": len(post),
        "command_intersecting_window_count": excluded,
        "command_bracket_gap_samples": command_bracket_gap_samples,
    }
