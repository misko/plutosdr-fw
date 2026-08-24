"""Guarded weak/strong/weak hardware execution for transient AGC evidence.

This module complements :mod:`transient_quality` with the smallest hardware
orchestration layer needed by the existing TX2 loopback fixture.  It keeps the
transport duck typed so deterministic fakes can exercise the complete runner.
Only tandem metadata is described as hardware sample time.  Ordinary IIO uses
an explicitly labelled, session-local contiguous refill axis and native gain
readbacks bracketing every returned frame.

The caller owns the :class:`Issue46Radio` lifecycle.  This runner requests a
mute on every exit and points ``radio._report_path`` at its atomic report, but
only ``Issue46Radio.close()`` performs and records verified final cleanup.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
from builtins import BaseExceptionGroup
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from .experiment import EvidenceInvalid, FixtureSafetyError, Issue46Radio
from .metadata_abi import (
    TANDEM_UNSAFE_FLAGS,
    TandemEventDirection,
    TandemFrameMetadata,
    TandemMode,
    TandemState,
    build_tandem_request,
    parse_tandem_frame_metadata,
)
from .tandem_quality import (
    MODE_MANUAL,
    MODE_TANDEM,
    NATIVE_GAIN_CONTROL_MODES,
    TandemQualityOptions,
    expected_tandem_gain_table,
    native_gain_control_mode,
    native_mode_name,
    validate_options,
)
from .transient_quality import (
    StimulusCommand,
    analyze_immediate_dual_rx,
    calculate_transient_response,
    reconcile_tandem_events,
    timestamp_stimulus_command,
)

_UINT32_MODULUS = 1 << 32
_UINT64_MODULUS = 1 << 64
TRANSIENT_MODES = (
    MODE_MANUAL,
    *(native_mode_name(mode) for mode in NATIVE_GAIN_CONTROL_MODES),
    MODE_TANDEM,
)


class TransientRadioTransport(Protocol):
    """The existing radio operations used by the transient runner."""

    options: Any
    identity: Mapping[str, Any]
    _report_path: Path | None

    def mute_all(self) -> None: ...

    def arm_tx2_tone(self, *, tone_hz: int, scale: float) -> None: ...

    def set_tx2_gain(self, gain_db: float) -> float: ...

    def configure_rx(
        self, mode: str, *, manual_gain_db: float | None = None
    ) -> None: ...

    def read_rx_state(self) -> Mapping[str, Sequence[Any]]: ...

    def read_center_frequency(self) -> Mapping[str, int]: ...

    def tandem_status(self) -> Mapping[str, int]: ...

    def buffer(
        self,
        api: str,
        kernel_buffers: int,
        samples_per_channel: int,
        *,
        tandem_request: bytes | None = None,
    ) -> Any: ...

    def capture_iq(
        self, buffer: Any, *, metadata: bool, samples_per_channel: int
    ) -> tuple[bytes, bytes | None, int]: ...


@dataclass(frozen=True)
class TransientCaptureOptions:
    """Bounded acquisition and oracle settings for one transient campaign."""

    frame_samples: int = 8_192
    window_samples: int = 1_024
    response_frames: int = 8
    baseline_frames: int = 1
    precondition_stable_frames: int = 3
    max_precondition_frames: int = 64
    baseline_windows: int = 3
    steady_windows: int = 3
    stable_windows: int = 3
    settling_tolerance_db: float = 1.0
    ringing_deadband_db: float = 0.25
    max_host_jitter_ns: int = 50_000_000
    max_sample_uncertainty: int = 16_384
    max_event_latency_samples: int = 65_536
    readback_tolerance_db: float = 0.25
    minimum_native_gain_change_db: float = 1.0


_DEFAULT_TRANSIENT_CAPTURE_OPTIONS = TransientCaptureOptions()


def validate_transient_options(
    quality: TandemQualityOptions, capture: TransientCaptureOptions
) -> None:
    """Reject unsafe or underdetermined transient settings before radio writes."""

    validate_options(quality)
    integer_fields = {
        "frame_samples": capture.frame_samples,
        "window_samples": capture.window_samples,
        "response_frames": capture.response_frames,
        "baseline_frames": capture.baseline_frames,
        "precondition_stable_frames": capture.precondition_stable_frames,
        "max_precondition_frames": capture.max_precondition_frames,
        "baseline_windows": capture.baseline_windows,
        "steady_windows": capture.steady_windows,
        "stable_windows": capture.stable_windows,
        "max_host_jitter_ns": capture.max_host_jitter_ns,
        "max_sample_uncertainty": capture.max_sample_uncertainty,
        "max_event_latency_samples": capture.max_event_latency_samples,
    }
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in integer_fields.values()
    ):
        raise ValueError(
            "transient frame, window, count, and jitter limits must be integers"
        )
    if capture.frame_samples < 1_024:
        raise ValueError("transient frame_samples must be at least 1024")
    if capture.frame_samples > quality.samples_per_channel:
        raise ValueError("transient frames cannot exceed the authorized quality frame")
    if capture.window_samples < 64 or capture.frame_samples % capture.window_samples:
        raise ValueError(
            "transient windows must divide each frame and contain at least 64 samples"
        )
    if capture.response_frames <= 0 or capture.baseline_frames <= 0:
        raise ValueError(
            "transient baseline and response frame counts must be positive"
        )
    if capture.precondition_stable_frames < capture.baseline_frames:
        raise ValueError("preconditioning must retain every requested baseline frame")
    if capture.max_precondition_frames < capture.precondition_stable_frames + 1:
        raise ValueError("preconditioning bound cannot drain and prove stability")
    windows_per_frame = capture.frame_samples // capture.window_samples
    if capture.baseline_frames * windows_per_frame < capture.baseline_windows:
        raise ValueError("baseline captures do not contain enough analysis windows")
    # The first post-write frame closes the conservative command bracket.  Its
    # windows intersect that bracket, so only later frames are post-command
    # evidence.
    available_post_windows = (capture.response_frames - 1) * windows_per_frame
    if available_post_windows < max(capture.steady_windows, capture.stable_windows):
        raise ValueError("response captures do not contain enough steady windows")
    if capture.max_host_jitter_ns <= 0 or capture.max_sample_uncertainty < 0:
        raise ValueError("transient jitter limits are invalid")
    minimum_anchor_span = capture.baseline_frames * capture.frame_samples
    if capture.max_sample_uncertainty < minimum_anchor_span:
        raise ValueError(
            "maximum sample uncertainty must cover the retained baseline "
            f"anchor ({minimum_anchor_span} samples)"
        )
    if capture.max_event_latency_samples < 0:
        raise ValueError("maximum event latency must be a nonnegative integer")
    finite_nonnegative = {
        "settling_tolerance_db": capture.settling_tolerance_db,
        "ringing_deadband_db": capture.ringing_deadband_db,
        "readback_tolerance_db": capture.readback_tolerance_db,
        "minimum_native_gain_change_db": capture.minimum_native_gain_change_db,
    }
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
        for value in finite_nonnegative.values()
    ):
        raise ValueError("transient tolerances must be finite and nonnegative")
    if quality.weakest_tx_gain_db == quality.strongest_tx_gain_db:
        raise ValueError("transient campaign needs distinct weak and strong TX levels")


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def _exception_text(error: BaseException) -> str:
    number = getattr(error, "errno", None)
    suffix = f" errno={number}" if number is not None else ""
    return f"{type(error).__name__}{suffix}: {error}"


def _finite_pair(values: Any, *, name: str) -> tuple[float, float]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise EvidenceInvalid(f"{name} is not a dual-RX sequence")
    if len(values) != 2:
        raise EvidenceInvalid(f"{name} does not contain exactly two receivers")
    result = tuple(float(value) for value in values)
    if any(not math.isfinite(value) for value in result):
        raise EvidenceInvalid(f"{name} contains a non-finite value")
    return result[0], result[1]


def _rx_state(
    radio: TransientRadioTransport, *, expected_mode: str
) -> dict[str, list[Any]]:
    state = radio.read_rx_state()
    modes = state.get("modes")
    if isinstance(modes, (str, bytes)) or not isinstance(modes, Sequence):
        raise EvidenceInvalid("RX state lacks a two-channel mode readback")
    if tuple(str(value) for value in modes) != (expected_mode, expected_mode):
        raise EvidenceInvalid(
            f"RX mode readback {tuple(modes)!r} differs from {expected_mode!r}"
        )
    gains = _finite_pair(state.get("gains_db"), name="RX gain readback")
    return {"modes": [expected_mode, expected_mode], "gains_db": list(gains)}


def _wait_for_idle(
    radio: TransientRadioTransport,
    *,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    timeout_seconds: float = 2.0,
) -> dict[str, int]:
    deadline = monotonic() + timeout_seconds
    while True:
        status = {name: int(value) for name, value in radio.tandem_status().items()}
        if (
            status.get("state") == int(TandemState.IDLE)
            and status.get("fault_flags") == 0
            and status.get("fifo_level") == 0
        ):
            return status
        if monotonic() >= deadline:
            raise EvidenceInvalid(f"tandem controller did not return to IDLE: {status}")
        sleep(0.01)


def _event_dict(event: Any) -> dict[str, Any]:
    return {
        "sample_sequence": int(event.sample_sequence),
        "event_sequence": int(event.event_sequence),
        "flags": int(event.flags),
        "direction": int(event.direction),
        "direction_name": event.direction.name.lower(),
        "reason": int(event.reason),
        "reason_name": event.reason.name.lower(),
        "rx1_gain_index": int(event.rx1_gain_index),
        "rx2_gain_index": int(event.rx2_gain_index),
    }


def _metadata_dict(metadata: TandemFrameMetadata) -> dict[str, Any]:
    return {
        "stream_id": metadata.stream_id,
        "buffer_sequence": metadata.buffer_sequence,
        "first_sample_sequence": metadata.first_sample_sequence,
        "samples_per_channel": metadata.samples_per_channel,
        "flags": metadata.flags,
        "ownership_epoch": metadata.ownership_epoch,
        "tandem_state": int(metadata.tandem_state),
        "tandem_state_name": metadata.tandem_state.name.lower(),
        "tandem_transition_count": metadata.tandem_transition_count,
        "gain_table_id": int(metadata.gain_table_id),
        "threshold_provenance": metadata.threshold_provenance,
        "bench_gain_indices": list(metadata.bench_gain_indices),
        "event_count": metadata.event_count,
        "observation_overflow_count": metadata.observation_overflow_count,
        "event_overflow_count": metadata.event_overflow_count,
        "gain_events": [_event_dict(event) for event in metadata.gain_events],
    }


@dataclass
class _CaptureState:
    next_nominal_sample: int = 0
    frame_index: int = 0
    previous_metadata: TandemFrameMetadata | None = None
    stream_id: int | None = None
    ownership_epoch: int | None = None
    last_event: Any = None


def _validate_tandem_metadata(
    metadata: TandemFrameMetadata,
    *,
    raw_bytes: int,
    quality: TandemQualityOptions,
    capture: TransientCaptureOptions,
    state: _CaptureState,
    allow_command_boundary_gap: bool,
) -> int:
    if metadata.samples_per_channel != capture.frame_samples:
        raise EvidenceInvalid(
            "tandem metadata sample count differs from transient frame"
        )
    if metadata.iq_payload_bytes != raw_bytes:
        raise EvidenceInvalid("tandem metadata IQ length differs from returned payload")
    if metadata.enabled_scan_mask != 0x0F or metadata.channel_count != 2:
        raise EvidenceInvalid("tandem metadata does not describe dual complex RX")
    if metadata.flags & TANDEM_UNSAFE_FLAGS:
        raise EvidenceInvalid(
            f"tandem metadata reports unsafe flags 0x{metadata.flags & TANDEM_UNSAFE_FLAGS:08x}"
        )
    if metadata.observation_overflow_count or metadata.event_overflow_count:
        raise EvidenceInvalid("tandem transient metadata capacity overflowed")
    if metadata.tandem_state is not TandemState.ARMED_AUTO:
        raise EvidenceInvalid("tandem controller left AUTO during transient capture")
    if metadata.gain_table_id is not expected_tandem_gain_table(
        quality.center_frequency_hz
    ):
        raise EvidenceInvalid("tandem transient selected the wrong gain table")
    if (
        metadata.minimum_gain_db != 0
        or metadata.maximum_gain_db != 62
        or metadata.initial_gain_db != int(quality.manual_gain_db)
    ):
        raise EvidenceInvalid("tandem transient metadata differs from its request")
    if metadata.rx1_gain_index != metadata.rx2_gain_index:
        raise EvidenceInvalid("tandem transient metadata contains a torn endpoint")
    if metadata.first_sample_sequence + capture.frame_samples > _UINT64_MODULUS:
        raise EvidenceInvalid("tandem transient frame exceeds uint64 sample time")

    if state.stream_id is None:
        state.stream_id = metadata.stream_id
        state.ownership_epoch = metadata.ownership_epoch
    elif (
        metadata.stream_id != state.stream_id
        or metadata.ownership_epoch != state.ownership_epoch
    ):
        raise EvidenceInvalid("tandem stream or ownership changed inside one session")

    sample_gap_before = 0
    previous = state.previous_metadata
    if previous is not None:
        if metadata.buffer_sequence != previous.buffer_sequence + 1:
            raise EvidenceInvalid("tandem transient buffer sequence has a gap")
        expected_first_sample = (
            previous.first_sample_sequence + previous.samples_per_channel
        )
        if metadata.first_sample_sequence < expected_first_sample:
            raise EvidenceInvalid("tandem transient sample sequence overlaps")
        sample_gap_before = metadata.first_sample_sequence - expected_first_sample
        if sample_gap_before and not allow_command_boundary_gap:
            raise EvidenceInvalid("tandem transient sample sequence has a gap")
        transition_delta = (
            metadata.tandem_transition_count - previous.tandem_transition_count
        ) % _UINT32_MODULUS
        if transition_delta != len(metadata.gain_events):
            raise EvidenceInvalid(
                "adjacent tandem transient frames lost gain-event evidence"
            )
        if metadata.gain_events:
            first = metadata.gain_events[0]
            expected = previous.rx1_gain_index + (
                1 if first.direction is TandemEventDirection.INCREASE else -1
            )
            if first.rx1_gain_index != expected:
                raise EvidenceInvalid(
                    "first tandem event disagrees with the prior paired endpoint"
                )
        elif metadata.bench_gain_indices != previous.bench_gain_indices:
            raise EvidenceInvalid("tandem endpoint changed without a visible event")

    for event in metadata.gain_events:
        if state.last_event is not None:
            if (
                event.event_sequence
                != (state.last_event.event_sequence + 1) % _UINT32_MODULUS
            ):
                raise EvidenceInvalid("tandem event sequence has a hole")
            expected = state.last_event.rx1_gain_index + (
                1 if event.direction is TandemEventDirection.INCREASE else -1
            )
            if event.rx1_gain_index != expected:
                raise EvidenceInvalid(
                    "tandem gain event did not take its exact +/-1 step"
                )
        state.last_event = event
    if metadata.gain_events and (
        metadata.bench_gain_indices
        != (
            metadata.gain_events[-1].rx1_gain_index,
            metadata.gain_events[-1].rx2_gain_index,
        )
    ):
        raise EvidenceInvalid("tandem endpoint differs from its final visible event")
    state.previous_metadata = metadata
    return sample_gap_before


def _capture_frame(
    radio: TransientRadioTransport,
    buffer: Any,
    *,
    mode: str,
    expected_iio_mode: str,
    quality: TandemQualityOptions,
    capture: TransientCaptureOptions,
    state: _CaptureState,
    metadata_parser: Callable[[bytes], TandemFrameMetadata],
    iq_dir: Path,
    allow_command_boundary_gap: bool = False,
) -> tuple[dict[str, Any], TandemFrameMetadata | None]:
    metadata_mode = mode == MODE_TANDEM
    before = (
        None if metadata_mode else _rx_state(radio, expected_mode=expected_iio_mode)
    )
    raw, raw_metadata, refill_ns = radio.capture_iq(
        buffer,
        metadata=metadata_mode,
        samples_per_channel=capture.frame_samples,
    )
    after = None if metadata_mode else _rx_state(radio, expected_mode=expected_iio_mode)
    if len(raw) != capture.frame_samples * 8:
        raise EvidenceInvalid("transient IQ payload has the wrong byte count")

    parsed = None
    sample_gap_before = 0
    if metadata_mode:
        if raw_metadata is None:
            raise EvidenceInvalid("tandem transient capture returned no metadata")
        parsed = metadata_parser(raw_metadata)
        sample_gap_before = _validate_tandem_metadata(
            parsed,
            raw_bytes=len(raw),
            quality=quality,
            capture=capture,
            state=state,
            allow_command_boundary_gap=allow_command_boundary_gap,
        )
        first_sample = parsed.first_sample_sequence
        timing_basis = "hardware_sample_counter"
    else:
        if raw_metadata is not None:
            raise EvidenceInvalid(
                "ordinary transient capture unexpectedly returned metadata"
            )
        first_sample = state.next_nominal_sample
        timing_basis = "ordinary_session_local_contiguous_refill_axis"

    analysis = dict(
        analyze_immediate_dual_rx(
            raw,
            first_sample_sequence=first_sample,
            sample_rate_hz=quality.sample_rate_hz,
            expected_tone_hz=quality.tone_hz,
            window_samples=capture.window_samples,
            min_tone_snr_db=quality.thresholds.min_tone_snr_db,
            max_clipping_fraction=quality.thresholds.max_clipping_fraction,
            max_phase_std_deg=quality.thresholds.max_phase_std_deg,
        )
    )
    record: dict[str, Any] = {
        "frame_index": state.frame_index,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "iq_bytes": len(raw),
        "refill_monotonic_ns": int(refill_ns),
        "timing_basis": timing_basis,
        "first_sample_sequence": first_sample,
        "sample_end_exclusive": first_sample + capture.frame_samples,
        "sample_gap_before": sample_gap_before,
        "command_boundary_gap_allowed": bool(allow_command_boundary_gap),
        "analysis": analysis,
    }
    if before is not None and after is not None:
        record["rx_state_before"] = before
        record["rx_state_after"] = after
    if parsed is not None:
        record["metadata"] = _metadata_dict(parsed)
    if quality.save_iq:
        iq_path = iq_dir / f"frame-{state.frame_index:04d}.cs16"
        _atomic_bytes(iq_path, raw)
        record["iq_path"] = str(iq_path)
    state.frame_index += 1
    state.next_nominal_sample = first_sample + capture.frame_samples
    return record, parsed


def _ordinary_stable_run(
    run: Sequence[Mapping[str, Any]], *, tolerance_db: float
) -> bool:
    gains: list[list[float]] = [[], []]
    for frame in run:
        for key in ("rx_state_before", "rx_state_after"):
            pair = _finite_pair(frame[key]["gains_db"], name="precondition gain")
            for channel in (0, 1):
                gains[channel].append(pair[channel])
    return all(max(values) - min(values) <= tolerance_db for values in gains)


def _precondition(
    radio: TransientRadioTransport,
    buffer: Any,
    *,
    mode: str,
    expected_iio_mode: str,
    quality: TandemQualityOptions,
    capture: TransientCaptureOptions,
    state: _CaptureState,
    metadata_parser: Callable[[bytes], TandemFrameMetadata],
    iq_dir: Path,
    check_deadline: Callable[[], None],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trace: list[dict[str, Any]] = []
    stable_run: list[dict[str, Any]] = []
    previous_metadata: TandemFrameMetadata | None = None
    for attempt in range(1, capture.max_precondition_frames + 1):
        check_deadline()
        frame, metadata = _capture_frame(
            radio,
            buffer,
            mode=mode,
            expected_iio_mode=expected_iio_mode,
            quality=quality,
            capture=capture,
            state=state,
            metadata_parser=metadata_parser,
            iq_dir=iq_dir / "precondition",
        )
        if mode == MODE_TANDEM:
            assert metadata is not None
            stable = bool(
                attempt > 1
                and not metadata.gain_events
                and previous_metadata is not None
                and metadata.tandem_transition_count
                == previous_metadata.tandem_transition_count
                and metadata.bench_gain_indices == previous_metadata.bench_gain_indices
            )
            previous_metadata = metadata
            stable_run = [*stable_run, frame] if stable else []
        else:
            tolerance = 0.1 if mode == MODE_MANUAL else 1.0
            candidate = [*stable_run, frame]
            stable_run = (
                candidate
                if _ordinary_stable_run(candidate, tolerance_db=tolerance)
                else [frame]
            )
        frame["precondition_stable_run"] = len(stable_run)
        trace.append(frame)
        if attempt > 1 and len(stable_run) >= capture.precondition_stable_frames:
            return trace, stable_run[-capture.baseline_frames :]
    raise EvidenceInvalid(
        f"{mode} did not establish a transient baseline in "
        f"{capture.max_precondition_frames} small frames"
    )


def _flatten_windows(frames: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [window for frame in frames for window in frame["analysis"]["windows"]]


def _gain_at_end(frames: Sequence[Mapping[str, Any]]) -> tuple[float, float]:
    selected = frames[-min(3, len(frames)) :]
    return tuple(
        float(
            statistics.median(
                float(frame["rx_state_after"]["gains_db"][channel])
                for frame in selected
            )
        )
        for channel in (0, 1)
    )  # type: ignore[return-value]


def _gain_transition_bounds(
    frames: Sequence[Mapping[str, Any]],
    *,
    command: StimulusCommand,
    reference_gain_db: tuple[float, float],
    expected_sign: int,
    minimum_change_db: float,
) -> list[dict[str, Any]]:
    assert command.sample_sequence_before is not None
    assert command.sample_sequence_after is not None
    results: list[dict[str, Any]] = []
    for channel in (0, 1):
        found: dict[str, Any] | None = None
        for frame in frames:
            start = int(frame["first_sample_sequence"])
            end = int(frame["sample_end_exclusive"])
            before = float(frame["rx_state_before"]["gains_db"][channel])
            after = float(frame["rx_state_after"]["gains_db"][channel])
            before_change = expected_sign * (before - reference_gain_db[channel])
            after_change = expected_sign * (after - reference_gain_db[channel])
            if before_change >= minimum_change_db:
                found = {
                    "rx_channel": channel,
                    "evidence": "pre_refill_readback",
                    "observed_gain_db": before,
                    "latency_lower_samples": max(
                        0, start - command.sample_sequence_after
                    ),
                    "latency_upper_samples": max(
                        0, end - command.sample_sequence_before
                    ),
                }
                break
            if after_change >= minimum_change_db:
                found = {
                    "rx_channel": channel,
                    "evidence": "post_refill_readback",
                    "observed_gain_db": after,
                    "latency_lower_samples": max(
                        0, start - command.sample_sequence_after
                    ),
                    "latency_upper_samples": max(
                        0, end - command.sample_sequence_before
                    ),
                }
                break
        if found is None:
            raise EvidenceInvalid(
                f"RX{channel} lacks a {minimum_change_db:g} dB native gain response"
            )
        found["latency_lower_seconds"] = found["latency_lower_samples"] / 1.0
        found["latency_upper_seconds"] = found["latency_upper_samples"] / 1.0
        results.append(found)
    return results


def _native_gain_evidence(
    baseline: Sequence[Mapping[str, Any]],
    attack: Sequence[Mapping[str, Any]],
    release: Sequence[Mapping[str, Any]],
    *,
    attack_command: StimulusCommand,
    release_command: StimulusCommand,
    sample_rate_hz: int,
    minimum_change_db: float,
) -> dict[str, Any]:
    weak = _gain_at_end(baseline)
    strong = _gain_at_end(attack)
    returned = _gain_at_end(release)
    attack_bounds = _gain_transition_bounds(
        attack,
        command=attack_command,
        reference_gain_db=weak,
        expected_sign=-1,
        minimum_change_db=minimum_change_db,
    )
    release_bounds = _gain_transition_bounds(
        release,
        command=release_command,
        reference_gain_db=strong,
        expected_sign=1,
        minimum_change_db=minimum_change_db,
    )
    for result in (*attack_bounds, *release_bounds):
        result["latency_lower_seconds"] = (
            result["latency_lower_samples"] / sample_rate_hz
        )
        result["latency_upper_seconds"] = (
            result["latency_upper_samples"] / sample_rate_hz
        )
    return {
        "evidence_valid": True,
        "minimum_required_change_db": minimum_change_db,
        "weak_gain_db": list(weak),
        "strong_gain_db": list(strong),
        "returned_weak_gain_db": list(returned),
        "attack_gain_change_db": [strong[index] - weak[index] for index in (0, 1)],
        "release_gain_change_db": [returned[index] - strong[index] for index in (0, 1)],
        "attack_latency_bounds": attack_bounds,
        "release_latency_bounds": release_bounds,
    }


def _manual_gain_evidence(
    frames: Sequence[Mapping[str, Any]], *, expected_gain_db: float
) -> dict[str, Any]:
    values: list[list[float]] = [[], []]
    for frame in frames:
        for key in ("rx_state_before", "rx_state_after"):
            for channel in (0, 1):
                values[channel].append(float(frame[key]["gains_db"][channel]))
    spans = [max(channel) - min(channel) for channel in values]
    errors = [
        max(abs(value - expected_gain_db) for value in channel) for channel in values
    ]
    if any(span > 0.1 for span in spans) or any(error > 0.1 for error in errors):
        raise EvidenceInvalid("manual RX gain moved during the transient campaign")
    return {
        "evidence_valid": True,
        "expected_gain_db": expected_gain_db,
        "gain_span_db": spans,
        "maximum_readback_error_db": errors,
    }


def _response_summary(response: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "signal_settling_latency_lower_samples": response[
            "signal_settling_latency_lower_samples"
        ],
        "signal_settling_latency_upper_samples": response[
            "signal_settling_latency_upper_samples"
        ],
        "worst_overshoot_db": response["worst_overshoot_db"],
        "ringing_peak_to_peak_db": response["ringing_peak_to_peak_db"],
        "minimum_post_tone_snr_db": response["minimum_post_tone_snr_db"],
        "maximum_post_clipping_fraction": response["maximum_post_clipping_fraction"],
        "maximum_phase_excursion_deg": response["maximum_phase_excursion_deg"],
    }


def _build_tandem_request(
    quality: TandemQualityOptions, capture: TransientCaptureOptions
) -> bytes:
    return build_tandem_request(
        mode=TandemMode.AUTO,
        initial_gain_db=int(quality.manual_gain_db),
        power_measurement_samples=quality.tandem_power_measurement_samples,
        low_power_dwell_periods=quality.tandem_low_power_dwell_periods,
        cooldown_periods=quality.tandem_cooldown_periods,
        low_power_threshold=quality.tandem_low_power_threshold,
        large_lmt_overload_threshold=quality.tandem_large_lmt_overload_threshold,
        large_adc_overload_threshold=quality.tandem_large_adc_overload_threshold,
        small_adc_overload_threshold=quality.tandem_small_adc_overload_threshold,
        samples_per_channel=capture.frame_samples,
    )


def _check_effective_attenuation(
    quality: TandemQualityOptions, command: StimulusCommand
) -> float:
    effective = quality.physical_attenuation_db - command.applied_level_db
    if effective < 30.0:
        raise EvidenceInvalid(
            f"TX2 readback for {command.command_id!r} violates the 30 dB safety boundary"
        )
    return effective


def _conditioning_anchor(
    command: StimulusCommand,
    baseline: Sequence[Mapping[str, Any]],
    *,
    max_sample_uncertainty: int,
) -> StimulusCommand:
    """Represent an observed stable condition without dating the original write.

    The weak write occurs before the streaming session, so it has no defensible
    sample-time bracket.  Analyzers still need a preceding level interval.  Use
    the retained stable baseline as that interval and label it separately in
    the report; these bounds are evidence of conditioning, not write timing.
    """

    if not baseline:
        raise EvidenceInvalid("transient conditioning anchor has no baseline frame")
    lower = int(baseline[0]["first_sample_sequence"])
    upper = int(baseline[-1]["sample_end_exclusive"])
    uncertainty = upper - lower
    if uncertainty <= 0:
        raise EvidenceInvalid("transient conditioning anchor is empty")
    if uncertainty > max_sample_uncertainty:
        raise EvidenceInvalid(
            "conditioning-anchor sample uncertainty "
            f"{uncertainty} exceeds {max_sample_uncertainty} samples"
        )
    return replace(
        command,
        command_id="weak_conditioning_anchor",
        sample_sequence_before=lower,
        sample_sequence_after=upper,
    )


def _bracket_host_write(
    command: StimulusCommand,
    *,
    last_pre_frame_end: int,
    first_post_frame: Mapping[str, Any],
    max_sample_uncertainty: int,
) -> StimulusCommand:
    """Close a host write bracket with the first observed post-write frame.

    A host attribute write cannot read the RF sample counter atomically.  Its
    conservative closed bracket therefore begins at the last observed
    pre-write frame end and ends at the first observed post-write frame end.
    Any hardware-metadata gap before that frame is automatically included.
    """

    lower = int(last_pre_frame_end)
    first_post_start = int(first_post_frame["first_sample_sequence"])
    upper = int(first_post_frame["sample_end_exclusive"])
    if first_post_start < lower:
        raise EvidenceInvalid(
            f"command {command.command_id!r} post-write frame overlaps its "
            "pre-write boundary"
        )
    if upper <= first_post_start:
        raise EvidenceInvalid(
            f"command {command.command_id!r} post-write frame is empty"
        )
    uncertainty = upper - lower
    if uncertainty <= 0:
        raise EvidenceInvalid(
            f"command {command.command_id!r} has no observed sample interval"
        )
    if uncertainty > max_sample_uncertainty:
        raise EvidenceInvalid(
            f"command {command.command_id!r} sample uncertainty {uncertainty} "
            f"exceeds {max_sample_uncertainty} samples"
        )
    return replace(
        command,
        sample_sequence_before=lower,
        sample_sequence_after=upper,
    )


def _command_record(
    command: StimulusCommand,
    *,
    effective_attenuation_db: float,
    timing_basis: str,
    rx_state_before: Mapping[str, Any] | None,
    rx_state_after: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        **command.as_dict(),
        "effective_attenuation_db": effective_attenuation_db,
        "rx_state_before": rx_state_before,
        "rx_state_after": rx_state_after,
        "timing_role": "host_write_bracketed_by_observed_iq",
        "sample_timing_basis": timing_basis,
        "sample_anchor_policy": (
            "last observed pre-frame end through first observed post-write frame end"
        ),
    }


def _run_mode_body(
    radio: TransientRadioTransport,
    *,
    mode: str,
    quality: TandemQualityOptions,
    capture: TransientCaptureOptions,
    check_deadline: Callable[[], None],
    clock_ns: Callable[[], int],
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    metadata_parser: Callable[[bytes], TandemFrameMetadata],
    output_dir: Path,
) -> dict[str, Any]:
    radio.mute_all()
    status_before = _wait_for_idle(radio, monotonic=monotonic, sleep=sleep)
    radio.configure_rx("manual", manual_gain_db=quality.manual_gain_db)
    radio.arm_tx2_tone(tone_hz=quality.tone_hz, scale=quality.dds_scale)

    native_iio_mode = native_gain_control_mode(mode)
    if native_iio_mode is not None:
        radio.configure_rx(native_iio_mode)
        expected_iio_mode = native_iio_mode
    elif mode == MODE_MANUAL or mode == MODE_TANDEM:
        expected_iio_mode = "manual"
    else:
        raise ValueError(f"unknown transient mode {mode!r}")

    initial_gain_state_before = (
        None
        if mode == MODE_TANDEM
        else _rx_state(radio, expected_mode=expected_iio_mode)
    )
    initial_unanchored = timestamp_stimulus_command(
        "weak_initial",
        quality.weakest_tx_gain_db,
        apply=radio.set_tx2_gain,
        clock_ns=clock_ns,
        max_host_jitter_ns=capture.max_host_jitter_ns,
        readback_tolerance_db=capture.readback_tolerance_db,
    )
    initial_effective = _check_effective_attenuation(quality, initial_unanchored)
    initial_gain_state_after = (
        None
        if mode == MODE_TANDEM
        else _rx_state(radio, expected_mode=expected_iio_mode)
    )

    request = _build_tandem_request(quality, capture) if mode == MODE_TANDEM else None
    timing_basis = (
        "hardware_sample_counter"
        if mode == MODE_TANDEM
        else "ordinary_session_local_contiguous_refill_axis"
    )
    record: dict[str, Any] = {
        "mode": mode,
        "timing_basis": timing_basis,
        "tandem_status_before": status_before,
        "commands": [],
        "preconditioning": {},
        "baseline_frames": [],
        "attack_frames": [],
        "release_frames": [],
    }
    state = _CaptureState()
    iq_dir = output_dir / mode
    metadata_abi = None
    mode_body_error: BaseException | None = None
    try:
        with radio.buffer(
            "metadata" if mode == MODE_TANDEM else "ordinary",
            1,
            capture.frame_samples,
            tandem_request=request,
        ) as (buffer, metadata_abi):
            if mode == MODE_TANDEM and metadata_abi != 2:
                raise EvidenceInvalid(
                    f"tandem transient requires metadata ABI 2, got {metadata_abi!r}"
                )
            trace, baseline = _precondition(
                radio,
                buffer,
                mode=mode,
                expected_iio_mode=expected_iio_mode,
                quality=quality,
                capture=capture,
                state=state,
                metadata_parser=metadata_parser,
                iq_dir=iq_dir,
                check_deadline=check_deadline,
            )
            initial = _conditioning_anchor(
                initial_unanchored,
                baseline,
                max_sample_uncertainty=capture.max_sample_uncertainty,
            )
            record["preconditioning"] = {
                "frame_count": len(trace),
                "trace": trace,
                "retained_baseline_frame_indices": [
                    int(frame["frame_index"]) for frame in baseline
                ],
            }
            record["baseline_frames"] = baseline
            record["commands"].append(
                {
                    **initial_unanchored.as_dict(),
                    "effective_attenuation_db": initial_effective,
                    "rx_state_before": initial_gain_state_before,
                    "rx_state_after": initial_gain_state_after,
                    "timing_role": "pre_session_conditioning_write",
                    "sample_timing_basis": None,
                    "sample_anchor_policy": (
                        "unbounded in sample time; the write predates the open "
                        "capture session"
                    ),
                }
            )
            record["conditioning_anchor"] = {
                **initial.as_dict(),
                "timing_role": "observed_stable_conditioning_interval",
                "sample_timing_basis": timing_basis,
                "sample_anchor_policy": (
                    "retained stable baseline interval; not the initial write time"
                ),
            }

            attack_boundary = int(baseline[-1]["sample_end_exclusive"])
            attack_gain_before = (
                None
                if mode == MODE_TANDEM
                else _rx_state(radio, expected_mode=expected_iio_mode)
            )
            attack = timestamp_stimulus_command(
                "strong_attack",
                quality.strongest_tx_gain_db,
                apply=radio.set_tx2_gain,
                clock_ns=clock_ns,
                max_host_jitter_ns=capture.max_host_jitter_ns,
                readback_tolerance_db=capture.readback_tolerance_db,
            )
            attack_effective = _check_effective_attenuation(quality, attack)
            attack_gain_after = (
                None
                if mode == MODE_TANDEM
                else _rx_state(radio, expected_mode=expected_iio_mode)
            )
            attack_frames: list[dict[str, Any]] = []
            check_deadline()
            first_attack_frame, _metadata = _capture_frame(
                radio,
                buffer,
                mode=mode,
                expected_iio_mode=expected_iio_mode,
                quality=quality,
                capture=capture,
                state=state,
                metadata_parser=metadata_parser,
                iq_dir=iq_dir / "attack",
                allow_command_boundary_gap=mode == MODE_TANDEM,
            )
            attack_frames.append(first_attack_frame)
            attack = _bracket_host_write(
                attack,
                last_pre_frame_end=attack_boundary,
                first_post_frame=first_attack_frame,
                max_sample_uncertainty=capture.max_sample_uncertainty,
            )
            for _ in range(capture.response_frames - 1):
                check_deadline()
                frame, _metadata = _capture_frame(
                    radio,
                    buffer,
                    mode=mode,
                    expected_iio_mode=expected_iio_mode,
                    quality=quality,
                    capture=capture,
                    state=state,
                    metadata_parser=metadata_parser,
                    iq_dir=iq_dir / "attack",
                )
                attack_frames.append(frame)

            release_boundary = int(attack_frames[-1]["sample_end_exclusive"])
            release_gain_before = (
                None
                if mode == MODE_TANDEM
                else _rx_state(radio, expected_mode=expected_iio_mode)
            )
            release = timestamp_stimulus_command(
                "weak_release",
                quality.weakest_tx_gain_db,
                apply=radio.set_tx2_gain,
                clock_ns=clock_ns,
                max_host_jitter_ns=capture.max_host_jitter_ns,
                readback_tolerance_db=capture.readback_tolerance_db,
            )
            release_effective = _check_effective_attenuation(quality, release)
            release_gain_after = (
                None
                if mode == MODE_TANDEM
                else _rx_state(radio, expected_mode=expected_iio_mode)
            )
            release_frames: list[dict[str, Any]] = []
            check_deadline()
            first_release_frame, _metadata = _capture_frame(
                radio,
                buffer,
                mode=mode,
                expected_iio_mode=expected_iio_mode,
                quality=quality,
                capture=capture,
                state=state,
                metadata_parser=metadata_parser,
                iq_dir=iq_dir / "release",
                allow_command_boundary_gap=mode == MODE_TANDEM,
            )
            release_frames.append(first_release_frame)
            release = _bracket_host_write(
                release,
                last_pre_frame_end=release_boundary,
                first_post_frame=first_release_frame,
                max_sample_uncertainty=capture.max_sample_uncertainty,
            )
            for _ in range(capture.response_frames - 1):
                check_deadline()
                frame, _metadata = _capture_frame(
                    radio,
                    buffer,
                    mode=mode,
                    expected_iio_mode=expected_iio_mode,
                    quality=quality,
                    capture=capture,
                    state=state,
                    metadata_parser=metadata_parser,
                    iq_dir=iq_dir / "release",
                )
                release_frames.append(frame)

            record["commands"].extend(
                (
                    _command_record(
                        attack,
                        effective_attenuation_db=attack_effective,
                        timing_basis=timing_basis,
                        rx_state_before=attack_gain_before,
                        rx_state_after=attack_gain_after,
                    ),
                    _command_record(
                        release,
                        effective_attenuation_db=release_effective,
                        timing_basis=timing_basis,
                        rx_state_before=release_gain_before,
                        rx_state_after=release_gain_after,
                    ),
                )
            )
            record["attack_frames"] = attack_frames
            record["release_frames"] = release_frames

            response_kwargs = {
                "sample_rate_hz": quality.sample_rate_hz,
                "baseline_windows": capture.baseline_windows,
                "steady_windows": capture.steady_windows,
                "stable_windows": capture.stable_windows,
                "settling_tolerance_db": capture.settling_tolerance_db,
                "ringing_deadband_db": capture.ringing_deadband_db,
                "max_host_jitter_ns": capture.max_host_jitter_ns,
                "max_sample_uncertainty": capture.max_sample_uncertainty,
            }
            attack_response = dict(
                calculate_transient_response(
                    _flatten_windows([*baseline, *attack_frames]),
                    previous_command=initial,
                    command=attack,
                    **response_kwargs,
                )
            )
            release_response = dict(
                calculate_transient_response(
                    _flatten_windows([*attack_frames, *release_frames]),
                    previous_command=attack,
                    command=release,
                    **response_kwargs,
                )
            )
            record["responses"] = {
                "attack": attack_response,
                "release": release_response,
            }

            if native_iio_mode is not None:
                record["gain_evidence"] = _native_gain_evidence(
                    baseline,
                    attack_frames,
                    release_frames,
                    attack_command=attack,
                    release_command=release,
                    sample_rate_hz=quality.sample_rate_hz,
                    minimum_change_db=capture.minimum_native_gain_change_db,
                )
            elif mode == MODE_MANUAL:
                record["gain_evidence"] = _manual_gain_evidence(
                    [*baseline, *attack_frames, *release_frames],
                    expected_gain_db=quality.manual_gain_db,
                )
            else:
                tandem_frames = [*attack_frames, *release_frames]
                events = [
                    event
                    for frame in tandem_frames
                    for event in frame["metadata"]["gain_events"]
                ]
                record["gain_evidence"] = dict(
                    reconcile_tandem_events(
                        (initial, attack, release),
                        events,
                        sample_rate_hz=quality.sample_rate_hz,
                        max_host_jitter_ns=capture.max_host_jitter_ns,
                        max_sample_uncertainty=capture.max_sample_uncertainty,
                        max_latency_samples=capture.max_event_latency_samples,
                    )
                )
    except BaseException as error:  # noqa: BLE001 - preserve shutdown interrupts
        mode_body_error = error
    mute_error: BaseException | None = None
    try:
        radio.mute_all()
    except BaseException as error:  # noqa: BLE001 - mute is mandatory on every exit
        mute_error = error
    if mode_body_error is not None and mute_error is not None:
        raise BaseExceptionGroup(
            f"transient mode {mode!r} failed and its mute request also failed",
            [mode_body_error, mute_error],
        )
    if mode_body_error is not None:
        raise mode_body_error.with_traceback(mode_body_error.__traceback__)
    if mute_error is not None:
        raise mute_error.with_traceback(mute_error.__traceback__)

    record["metadata_abi"] = metadata_abi
    record["tandem_status_after"] = _wait_for_idle(
        radio, monotonic=monotonic, sleep=sleep
    )
    radio.configure_rx("manual", manual_gain_db=quality.manual_gain_db)
    record["final_rx_state"] = _rx_state(radio, expected_mode="manual")
    record["verdict"] = "pass"
    return record


def _run_mode(
    radio: TransientRadioTransport,
    *,
    mode: str,
    quality: TandemQualityOptions,
    capture: TransientCaptureOptions,
    check_deadline: Callable[[], None],
    clock_ns: Callable[[], int],
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    metadata_parser: Callable[[bytes], TandemFrameMetadata],
    output_dir: Path,
) -> dict[str, Any]:
    """Run a mode while preserving both its body and fail-safe mute errors."""

    mode_error: BaseException | None = None
    result: dict[str, Any] | None = None
    try:
        result = _run_mode_body(
            radio,
            mode=mode,
            quality=quality,
            capture=capture,
            check_deadline=check_deadline,
            clock_ns=clock_ns,
            monotonic=monotonic,
            sleep=sleep,
            metadata_parser=metadata_parser,
            output_dir=output_dir,
        )
    except BaseException as error:  # noqa: BLE001 - preserve body and cleanup errors
        mode_error = error

    mute_error: BaseException | None = None
    try:
        radio.mute_all()
    except BaseException as error:  # noqa: BLE001 - mute is mandatory on every exit
        mute_error = error
    if mode_error is not None and mute_error is not None:
        raise BaseExceptionGroup(
            f"transient mode {mode!r} failed and final mute also failed",
            [mode_error, mute_error],
        )
    if mode_error is not None:
        raise mode_error.with_traceback(mode_error.__traceback__)
    if mute_error is not None:
        raise mute_error.with_traceback(mute_error.__traceback__)
    assert result is not None
    return result


def _comparison(modes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "mode": mode["mode"],
            "timing_basis": mode["timing_basis"],
            "attack": _response_summary(mode["responses"]["attack"]),
            "release": _response_summary(mode["responses"]["release"]),
            "gain_evidence": mode["gain_evidence"],
        }
        for mode in modes
    ]


def run_transient_hardware(
    radio: Issue46Radio | TransientRadioTransport,
    quality: TandemQualityOptions,
    *,
    capture: TransientCaptureOptions = _DEFAULT_TRANSIENT_CAPTURE_OPTIONS,
    clock_ns: Callable[[], int] = time.monotonic_ns,
    monotonic: Callable[[], float] = time.monotonic,
    wall_clock_ns: Callable[[], int] = time.time_ns,
    sleep: Callable[[float], None] = time.sleep,
    metadata_parser: Callable[
        [bytes], TandemFrameMetadata
    ] = parse_tandem_frame_metadata,
    report_writer: Callable[[Path, Mapping[str, Any]], None] = _atomic_json,
) -> tuple[dict[str, Any], Path]:
    """Run five guarded transient cells and atomically preserve all evidence."""

    validate_transient_options(quality, capture)
    if radio.options.sample_rate_hz != quality.sample_rate_hz:
        raise ValueError("radio and transient sample rates differ")
    if abs(float(radio.options.tx_gain_db) - quality.strongest_tx_gain_db) > 0.01:
        raise ValueError("radio TX authorization differs from the transient ceiling")
    if radio.options.center_frequency_hz != quality.center_frequency_hz:
        raise ValueError("radio and transient center frequencies differ")
    center_frequency = {
        key: int(value) for key, value in radio.read_center_frequency().items()
    }
    if any(
        abs(value - quality.center_frequency_hz) > 2
        for value in center_frequency.values()
    ):
        raise EvidenceInvalid(
            "live RX/TX LO readback differs from transient configuration"
        )

    serial = str(radio.options.serial)
    report_path = quality.output_dir / serial / "tandem-agc-transient-report.json"
    radio._report_path = report_path
    started = monotonic()

    def check_deadline() -> None:
        if monotonic() - started >= quality.max_seconds:
            raise TimeoutError(
                f"transient hardware campaign exceeded {quality.max_seconds:.1f} seconds"
            )

    quality_configuration = asdict(quality)
    quality_configuration["output_dir"] = str(quality.output_dir)
    quality_configuration["thresholds"] = asdict(quality.thresholds)
    report: dict[str, Any] = {
        "schema": "plutosdr-fw.tandem-agc-transient.v1",
        "started_unix_ns": wall_clock_ns(),
        "identity": dict(radio.identity),
        "bench_port_mapping": {
            "stimulus": "bench TX2 = AD9361/IIO TX2",
            "receivers": [
                "bench RX0 = AD9361/IIO RX1",
                "bench RX1 = AD9361/IIO RX2",
            ],
        },
        "trajectory_db": [
            quality.weakest_tx_gain_db,
            quality.strongest_tx_gain_db,
            quality.weakest_tx_gain_db,
        ],
        "required_modes": list(TRANSIENT_MODES),
        "rf": {
            "center_frequency_hz_requested": quality.center_frequency_hz,
            "center_frequency_hz_readback": center_frequency,
            "tone_hz": quality.tone_hz,
            "dds_scale": quality.dds_scale,
        },
        "configuration": {
            "quality": quality_configuration,
            "transient_capture": asdict(capture),
            "kernel_buffers": 1,
        },
        "safety": {
            "physical_attenuation_db": quality.physical_attenuation_db,
            "strongest_tx_gain_db": quality.strongest_tx_gain_db,
            "minimum_effective_attenuation_db": quality.minimum_effective_attenuation_db,
            "required_effective_attenuation_db": 30.0,
            "tx1_policy": "muted below -80 dB for the entire campaign",
        },
        "evidence_policy": {
            "ordinary_timing": (
                "session-local contiguous refill axis reset for each mode; "
                "never compared across sessions and not a hardware timestamp"
            ),
            "tandem_timing": "metadata-v5 FPGA sample counter",
            "command_latency": (
                "closed lower/upper bound from the last observed pre-frame end "
                "through the first observed post-write frame end; never a point "
                "estimate"
            ),
            "initial_condition": (
                "pre-session weak write remains sample-unbounded; retained stable "
                "IQ is an explicitly labelled conditioning anchor"
            ),
            "tandem_event_latency_limit_samples": (capture.max_event_latency_samples),
        },
        "modes": [],
        "cleanup": {
            "verified": False,
            "status": "pending_radio_lifecycle_close",
            "owner": "Issue46Radio.close",
        },
        "verdict": "running",
    }
    report_writer(report_path, report)
    campaign_error: BaseException | None = None
    try:
        for mode in TRANSIENT_MODES:
            check_deadline()
            mode_record = _run_mode(
                radio,
                mode=mode,
                quality=quality,
                capture=capture,
                check_deadline=check_deadline,
                clock_ns=clock_ns,
                monotonic=monotonic,
                sleep=sleep,
                metadata_parser=metadata_parser,
                output_dir=report_path.parent / "transient-iq",
            )
            report["modes"].append(mode_record)
            report_writer(report_path, report)
        report["comparison"] = _comparison(report["modes"])
        report["verdict"] = "pass"
    except BaseException as error:  # noqa: BLE001 - preserve shutdown interrupts
        campaign_error = error
        report["verdict"] = "invalid"
        report["fatal_error"] = _exception_text(error)

    mute_error: BaseException | None = None
    try:
        radio.mute_all()
    except BaseException as error:  # noqa: BLE001 - final mute is unconditional
        mute_error = error
        report["verdict"] = "invalid"
        report["cleanup_request_error"] = _exception_text(error)
    report["elapsed_seconds"] = monotonic() - started
    report["completed_unix_ns"] = wall_clock_ns()

    report_error: BaseException | None = None
    try:
        report_writer(report_path, report)
    except BaseException as error:  # noqa: BLE001 - retain report-write failures
        report_error = error

    errors = [
        error
        for error in (campaign_error, mute_error, report_error)
        if error is not None
    ]
    if len(errors) > 1:
        raise BaseExceptionGroup(
            "transient campaign and exit handling reported multiple failures",
            errors,
        )
    if errors:
        error = errors[0]
        raise error.with_traceback(error.__traceback__)
    return report, report_path


def run_serial_transient_hardware(
    iio_module: Any,
    radio_options: Any,
    quality: TandemQualityOptions,
    *,
    capture: TransientCaptureOptions = _DEFAULT_TRANSIENT_CAPTURE_OPTIONS,
    radio_factory: Callable[[Any, Any], Issue46Radio] = Issue46Radio,
    clock_ns: Callable[[], int] = time.monotonic_ns,
    monotonic: Callable[[], float] = time.monotonic,
    wall_clock_ns: Callable[[], int] = time.time_ns,
    sleep: Callable[[float], None] = time.sleep,
    metadata_parser: Callable[
        [bytes], TandemFrameMetadata
    ] = parse_tandem_frame_metadata,
    report_writer: Callable[[Path, Mapping[str, Any]], None] = _atomic_json,
) -> tuple[dict[str, Any], Path]:
    """Own one serial-attested radio and reload close-time cleanup evidence."""

    # Static failures must occur before a USB context or fixture lock is opened.
    validate_transient_options(quality, capture)
    radio = radio_factory(iio_module, radio_options)
    body_error: BaseException | None = None
    result: tuple[dict[str, Any], Path] | None = None
    try:
        result = run_transient_hardware(
            radio,
            quality,
            capture=capture,
            clock_ns=clock_ns,
            monotonic=monotonic,
            wall_clock_ns=wall_clock_ns,
            sleep=sleep,
            metadata_parser=metadata_parser,
            report_writer=report_writer,
        )
    except BaseException as error:  # noqa: BLE001 - close after every exit
        body_error = error

    close_error: BaseException | None = None
    try:
        radio.close()
    except BaseException as error:  # noqa: BLE001 - preserve close failures too
        close_error = FixtureSafetyError(
            f"radio close failed after transient campaign: {_exception_text(error)}"
        )

    report_path_value = (
        result[1] if result is not None else getattr(radio, "_report_path", None)
    )
    report_path = Path(report_path_value) if report_path_value is not None else None
    durable_report: dict[str, Any] | None = None
    durable_error: BaseException | None = None
    if close_error is None:
        try:
            if not bool(getattr(radio, "cleanup_verified", False)):
                raise FixtureSafetyError(
                    "radio close did not verify final transient hardware cleanup"
                )
            if report_path is not None:
                if not report_path.is_file():
                    raise EvidenceInvalid("post-close transient report is missing")
                if report_path.with_suffix(report_path.suffix + ".tmp").exists():
                    raise EvidenceInvalid(
                        "post-close transient atomic report temp file remains"
                    )
                parsed = json.loads(report_path.read_text(encoding="utf-8"))
                if not isinstance(parsed, dict):
                    raise EvidenceInvalid(
                        "post-close transient report is not a JSON object"
                    )
                cleanup = parsed.get("cleanup")
                if not isinstance(cleanup, Mapping) or not bool(
                    cleanup.get("verified", False)
                ):
                    raise FixtureSafetyError(
                        "durable post-close transient report does not prove cleanup"
                    )
                failures = cleanup.get("failures")
                if not isinstance(failures, list) or failures:
                    raise FixtureSafetyError(
                        "durable post-close transient cleanup contains failures"
                    )
                durable_report = parsed
            elif result is not None:
                raise EvidenceInvalid(
                    "successful transient campaign has no durable report path"
                )
        except BaseException as error:  # noqa: BLE001 - durable proof is mandatory
            durable_error = error

    exit_errors = [
        error for error in (body_error, close_error, durable_error) if error is not None
    ]
    if len(exit_errors) > 1:
        raise BaseExceptionGroup(
            "transient campaign, radio close, or durable cleanup proof failed",
            exit_errors,
        )
    if exit_errors:
        error = exit_errors[0]
        raise error.with_traceback(error.__traceback__)
    assert result is not None
    assert report_path is not None
    assert durable_report is not None
    return durable_report, report_path


__all__ = [
    "TRANSIENT_MODES",
    "TransientCaptureOptions",
    "TransientRadioTransport",
    "run_serial_transient_hardware",
    "run_transient_hardware",
    "validate_transient_options",
]
