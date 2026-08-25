"""Guarded weak/strong/weak hardware execution for transient AGC evidence.

This module complements :mod:`transient_quality` with the smallest hardware
orchestration layer needed by the existing TX2 loopback fixture.  It keeps the
transport duck typed so deterministic fakes can exercise the complete runner.
Only tandem metadata is described as hardware sample time.  Ordinary IIO uses
an explicitly labelled ordinal axis over returned IQ and native gain readbacks
bracketing every returned frame; unobserved refill intervals are not latency.

The caller owns the :class:`Issue46Radio` lifecycle.  This runner requests a
mute on every exit and points ``radio._report_path`` at its atomic report, but
only ``Issue46Radio.close()`` performs and records verified final cleanup.
"""

from __future__ import annotations

import errno
import hashlib
import json
import math
import queue
import statistics
import threading
import time
from builtins import BaseExceptionGroup
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
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
    maximum_tandem_events_per_frame,
    parse_tandem_frame_metadata,
)
from .tandem_quality import (
    AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES,
    MODE_MANUAL,
    MODE_TANDEM,
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
_TRANSIENT_KERNEL_BUFFERS = 1
_TANDEM_CAPTURE_QUEUE_FRAMES = 4
_TANDEM_CAPTURE_TAIL_FRAMES = _TANDEM_CAPTURE_QUEUE_FRAMES + 1
_MAX_DEFERRED_CAPTURE_BYTES = 64 * 1024 * 1024
_CAPTURE_THREAD_WAIT_SECONDS = 6.0
TRANSIENT_MODES = (
    MODE_MANUAL,
    *(native_mode_name(mode) for mode in AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES),
    MODE_TANDEM,
)
_GAP_CONTEXT_CONTINUOUS_RESPONSE = "continuous_response"
_GAP_CONTEXT_PRECONDITION = "precondition_observation"
_GAP_CONTEXT_COMMAND = "command_bracket"
_GAP_CONTEXT_PREFETCH = "precommand_prefetch"
_GAP_CONTEXT_ACQUISITION = "continuous_acquisition_unclassified"
_GAP_CONTEXTS = {
    _GAP_CONTEXT_CONTINUOUS_RESPONSE,
    _GAP_CONTEXT_PRECONDITION,
    _GAP_CONTEXT_COMMAND,
    _GAP_CONTEXT_PREFETCH,
    _GAP_CONTEXT_ACQUISITION,
}
_ORDINARY_TIMING_BASIS = "ordinary_returned_iq_ordinal_axis"
_TANDEM_TIMING_BASIS = "hardware_sample_counter"


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

    def read_rx_sample_counter_low32(self) -> int: ...


@dataclass(frozen=True)
class TransientCaptureOptions:
    """Bounded acquisition and oracle settings for one transient campaign."""

    weak_stimulus_tx_gain_db: float = -45.0
    strong_stimulus_tx_gain_db: float = -30.0
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


@dataclass
class _DeferredFrame:
    """One copied frame whose expensive processing waits for buffer close."""

    record: dict[str, Any]
    raw: bytes
    metadata: TandemFrameMetadata | None
    iq_dir: Path | None = None


def _maximum_deferred_capture_bytes(capture: TransientCaptureOptions) -> int:
    # Tandem may have a bounded producer tail around each command.  Ordinary
    # modes use no producer tail, but this worst case applies uniformly.
    maximum_frames = (
        capture.max_precondition_frames
        + 2 * (capture.response_frames + _TANDEM_CAPTURE_TAIL_FRAMES)
        + _TANDEM_CAPTURE_QUEUE_FRAMES
        + 1
    )
    return maximum_frames * capture.frame_samples * 8


def transient_evidence_policy(
    capture: TransientCaptureOptions,
) -> dict[str, Any]:
    """Return the exact durable policy independently checked for release use."""

    return {
        "ordinary_timing": (
            "ordinary IIO coordinates are ordinals over returned IQ only; host "
            "refill/readback intervals are unobserved, so settling fields are "
            "observation spans, not hardware latency, and must not be ranked "
            "against FPGA-timed tandem latency"
        ),
        "tandem_timing": "metadata-v5 FPGA sample counter",
        "command_latency": (
            "tandem uses coherent FPGA low32 reads around the TX write and "
            "requires two distinct counter advances after an initial post-write "
            "read so the second is causally post-command; ordinary modes retain "
            "returned-IQ ordinal positions only; never point estimates"
        ),
        "initial_condition": (
            "pre-session weak write remains sample-unbounded; retained stable IQ "
            "is an explicitly labelled conditioning anchor"
        ),
        "stimulus": {
            "weak_tx_gain_db": capture.weak_stimulus_tx_gain_db,
            "strong_tx_gain_db": capture.strong_stimulus_tx_gain_db,
            "step_db": (
                capture.strong_stimulus_tx_gain_db - capture.weak_stimulus_tx_gain_db
            ),
            "quality_policy": (
                "explicit trajectory rungs require prior same-band steady "
                "qualification; retain the 10 dB returned-IQ tone-SNR gate"
            ),
        },
        "tandem_acquisition": (
            "one kernel buffer; one bounded acquisition-only thread continuously "
            "refills and copies IQ while commands execute; FFT, hashing, and IQ "
            "artifact writes begin only after buffer close"
        ),
        "tandem_provider_gaps": (
            "reject every buffer/sample gap and every hidden transition; the "
            "provider does not retain exact events or signal response for omitted "
            "frames"
        ),
        "tandem_capture_queue_frames": _TANDEM_CAPTURE_QUEUE_FRAMES,
        "tandem_response_tail_frames": _TANDEM_CAPTURE_TAIL_FRAMES,
        "maximum_deferred_capture_bytes": _MAX_DEFERRED_CAPTURE_BYTES,
        "configured_worst_case_deferred_capture_bytes": (
            _maximum_deferred_capture_bytes(capture)
        ),
        "tandem_event_latency_limit_samples": capture.max_event_latency_samples,
    }


def validate_transient_options(
    quality: TandemQualityOptions, capture: TransientCaptureOptions
) -> None:
    """Reject unsafe or underdetermined transient settings before radio writes."""

    validate_options(quality)
    if quality.native_gain_control_modes != AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES:
        raise ValueError(
            "transient release evidence requires the autonomous native-mode set"
        )
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
    deferred_bytes = _maximum_deferred_capture_bytes(capture)
    if deferred_bytes > _MAX_DEFERRED_CAPTURE_BYTES:
        raise ValueError(
            "transient acquisition-first capture can retain at most "
            f"{_MAX_DEFERRED_CAPTURE_BYTES} deferred IQ bytes; requested bounds "
            f"permit {deferred_bytes} bytes"
        )
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
    stimulus_levels = {
        "weak_stimulus_tx_gain_db": capture.weak_stimulus_tx_gain_db,
        "strong_stimulus_tx_gain_db": capture.strong_stimulus_tx_gain_db,
    }
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in stimulus_levels.values()
    ):
        raise ValueError("transient stimulus levels must be finite numbers")
    weak_level = float(capture.weak_stimulus_tx_gain_db)
    strong_level = float(capture.strong_stimulus_tx_gain_db)
    configured_rungs = {float(value) for value in quality.tx_gain_trajectory_db}
    if weak_level not in configured_rungs or strong_level not in configured_rungs:
        raise ValueError(
            "transient stimulus levels must be configured quality-trajectory rungs"
        )
    if weak_level >= strong_level:
        raise ValueError("transient weak stimulus must be below its strong stimulus")
    if strong_level != quality.strongest_tx_gain_db:
        raise ValueError(
            "transient strong stimulus must equal the authorized quality ceiling"
        )
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
        "observation_count": metadata.observation_count,
        "ownership_epoch": metadata.ownership_epoch,
        "tandem_state": int(metadata.tandem_state),
        "tandem_state_name": metadata.tandem_state.name.lower(),
        "tandem_fault_flags": metadata.tandem_fault_flags,
        "tandem_transition_count": metadata.tandem_transition_count,
        "gain_table_id": int(metadata.gain_table_id),
        "threshold_provenance": metadata.threshold_provenance,
        "gain_db_range": [metadata.minimum_gain_db, metadata.maximum_gain_db],
        "initial_gain_db": metadata.initial_gain_db,
        "gain_index_range": [
            metadata.minimum_gain_index,
            metadata.maximum_gain_index,
        ],
        "bench_gain_indices": list(metadata.bench_gain_indices),
        "event_count": metadata.event_count,
        "observation_overflow_count": metadata.observation_overflow_count,
        "event_overflow_count": metadata.event_overflow_count,
        "temperature_mdeg_c": metadata.ad9361_temperature_mdeg_c,
        "gain_event_count": len(metadata.gain_events),
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
    missing_frame_count: int = 0
    hidden_transition_count: int = 0
    event_sequence_hole_count: int = 0
    last_frame_continuity: dict[str, Any] = field(default_factory=dict)


def _forward_u32_delta(current: int, previous: int, *, context: str) -> int:
    delta = (current - previous) % _UINT32_MODULUS
    if delta >= _UINT32_MODULUS // 2:
        raise EvidenceInvalid(f"{context} regressed ambiguously")
    return delta


def _validate_tandem_metadata(
    metadata: TandemFrameMetadata,
    *,
    raw_bytes: int,
    quality: TandemQualityOptions,
    capture: TransientCaptureOptions,
    state: _CaptureState,
    gap_context: str,
) -> Mapping[str, Any]:
    if gap_context not in _GAP_CONTEXTS:
        raise ValueError(f"unknown transient gap context {gap_context!r}")
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
            "tandem metadata reports unsafe flags "
            f"0x{metadata.flags & TANDEM_UNSAFE_FLAGS:08x}"
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

    buffer_delta: int | None = None
    sample_delta: int | None = None
    missing_frames = 0
    sample_gap_before = 0
    transition_delta: int | None = None
    hidden_transitions = 0
    initial_unrepresented_transitions = 0
    previous = state.previous_metadata
    if previous is not None:
        if (
            metadata.minimum_gain_index != previous.minimum_gain_index
            or metadata.maximum_gain_index != previous.maximum_gain_index
        ):
            raise EvidenceInvalid(
                "tandem transient gain-index range changed inside one session"
            )
        buffer_delta = metadata.buffer_sequence - previous.buffer_sequence
        sample_delta = metadata.first_sample_sequence - previous.first_sample_sequence
        if buffer_delta <= 0 or sample_delta <= 0:
            raise EvidenceInvalid(
                "tandem transient frame counters did not advance "
                f"(buffer {previous.buffer_sequence}->{metadata.buffer_sequence}, "
                "sample "
                f"{previous.first_sample_sequence}->{metadata.first_sample_sequence})"
            )
        if sample_delta % previous.samples_per_channel:
            raise EvidenceInvalid(
                "tandem transient sample sequence did not advance by whole frames "
                f"(delta {sample_delta}, frame {previous.samples_per_channel})"
            )
        expected_sample_delta = buffer_delta * previous.samples_per_channel
        if sample_delta != expected_sample_delta:
            raise EvidenceInvalid(
                "tandem transient buffer/sample deltas disagree "
                f"(buffer delta {buffer_delta}, sample delta {sample_delta}, "
                f"expected {expected_sample_delta})"
            )
        missing_frames = buffer_delta - 1
        sample_gap_before = missing_frames * previous.samples_per_channel
        transition_delta = _forward_u32_delta(
            metadata.tandem_transition_count,
            previous.tandem_transition_count,
            context="tandem transient transition count",
        )
        if transition_delta < len(metadata.gain_events):
            raise EvidenceInvalid(
                "tandem transient frame has more visible events than its "
                f"transition delta ({len(metadata.gain_events)} > "
                f"{transition_delta})"
            )
        hidden_transitions = transition_delta - len(metadata.gain_events)
        if not missing_frames and hidden_transitions:
            raise EvidenceInvalid(
                "adjacent tandem transient frames lost gain-event evidence "
                f"(transition delta {transition_delta}, visible "
                f"{len(metadata.gain_events)})"
            )
        maximum_hidden = missing_frames * maximum_tandem_events_per_frame(
            mode=TandemMode.AUTO,
            samples_per_channel=capture.frame_samples,
            power_measurement_samples=quality.tandem_power_measurement_samples,
            cooldown_periods=quality.tandem_cooldown_periods,
        )
        if hidden_transitions > maximum_hidden:
            raise EvidenceInvalid(
                "tandem transient gap contains more hidden transitions than "
                "omitted frames can hold "
                f"({hidden_transitions} > {maximum_hidden})"
            )
        if missing_frames:
            # The provider consumes events older than the returned IQ frame.
            # Even a zero-transition gap can hide signal settling or overshoot,
            # and a nonzero transition delta loses exact event placement.  The
            # acquisition-first transport is therefore qualification evidence
            # only when every hardware frame is returned.
            raise EvidenceInvalid(
                "tandem transient provider gap is forbidden by continuous "
                "acquisition policy "
                f"(context {gap_context}, buffer "
                f"{previous.buffer_sequence}->{metadata.buffer_sequence}, sample "
                f"{previous.first_sample_sequence}->"
                f"{metadata.first_sample_sequence}, missing frames "
                f"{missing_frames}, transition delta {transition_delta}, visible "
                f"events {len(metadata.gain_events)}, hidden transitions "
                f"{hidden_transitions})"
            )
    elif metadata.tandem_transition_count < len(metadata.gain_events):
        raise EvidenceInvalid(
            "first tandem transient frame has more events than transitions"
        )
    else:
        initial_unrepresented_transitions = metadata.tandem_transition_count - len(
            metadata.gain_events
        )

    for event in metadata.gain_events:
        if event.rx1_gain_index != event.rx2_gain_index:
            raise EvidenceInvalid("tandem transient event contains a torn gain pair")
        if not (
            metadata.first_sample_sequence
            <= event.sample_sequence
            < metadata.first_sample_sequence + metadata.samples_per_channel
        ):
            raise EvidenceInvalid(
                "tandem transient event lies outside its returned IQ frame"
            )
        if not (
            metadata.minimum_gain_index
            <= event.rx1_gain_index
            <= metadata.maximum_gain_index
        ):
            raise EvidenceInvalid(
                "tandem transient event gain lies outside the session range"
            )
        if state.last_event is not None:
            sequence_delta = _forward_u32_delta(
                event.event_sequence,
                state.last_event.event_sequence,
                context="tandem transient event sequence",
            )
            if sequence_delta != 1:
                raise EvidenceInvalid(
                    "tandem transient event sequence has an unreconciled hole "
                    f"(delta {sequence_delta})"
                )
            if event.sample_sequence < state.last_event.sample_sequence:
                raise EvidenceInvalid(
                    "tandem transient events are not globally sample ordered"
                )
            expected = state.last_event.rx1_gain_index + (
                1 if event.direction is TandemEventDirection.INCREASE else -1
            )
            if event.rx1_gain_index != expected:
                raise EvidenceInvalid(
                    "tandem gain event did not take its exact +/-1 step"
                )
        elif previous is not None:
            expected = previous.rx1_gain_index + (
                1 if event.direction is TandemEventDirection.INCREASE else -1
            )
            if event.rx1_gain_index != expected:
                raise EvidenceInvalid(
                    "first tandem transient event disagrees with the prior "
                    "paired endpoint"
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
    if (
        previous is not None
        and not metadata.gain_events
        and metadata.bench_gain_indices != previous.bench_gain_indices
    ):
        raise EvidenceInvalid("tandem endpoint changed without a visible event")

    continuity = {
        "buffer_delta": buffer_delta,
        "sample_delta": sample_delta,
        "missing_frame_count": missing_frames,
        "sample_gap_before": sample_gap_before,
        "provider_gap_accepted": False,
        "gap_context": gap_context,
        "command_boundary_gap_allowed": False,
        "transition_count_delta": transition_delta,
        "visible_event_count": len(metadata.gain_events),
        "hidden_transition_count": hidden_transitions,
        "initial_unrepresented_transition_count": initial_unrepresented_transitions,
        "cumulative_missing_frame_count": state.missing_frame_count,
        "cumulative_hidden_transition_count": state.hidden_transition_count,
        "cumulative_event_sequence_hole_count": state.event_sequence_hole_count,
    }
    state.previous_metadata = metadata
    state.last_frame_continuity = continuity
    return continuity


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
    gap_context: str = _GAP_CONTEXT_CONTINUOUS_RESPONSE,
) -> _DeferredFrame:
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
    continuity: Mapping[str, Any] | None = None
    if metadata_mode:
        if raw_metadata is None:
            raise EvidenceInvalid("tandem transient capture returned no metadata")
        parsed = metadata_parser(raw_metadata)
        continuity = _validate_tandem_metadata(
            parsed,
            raw_bytes=len(raw),
            quality=quality,
            capture=capture,
            state=state,
            gap_context=gap_context,
        )
        sample_gap_before = int(continuity["sample_gap_before"])
        first_sample = parsed.first_sample_sequence
        timing_basis = _TANDEM_TIMING_BASIS
    else:
        if raw_metadata is not None:
            raise EvidenceInvalid(
                "ordinary transient capture unexpectedly returned metadata"
            )
        first_sample = state.next_nominal_sample
        timing_basis = _ORDINARY_TIMING_BASIS

    record: dict[str, Any] = {
        "frame_index": state.frame_index,
        "iq_bytes": len(raw),
        "refill_monotonic_ns": int(refill_ns),
        "timing_basis": timing_basis,
        "first_sample_sequence": first_sample,
        "sample_end_exclusive": first_sample + capture.frame_samples,
        "sample_gap_before": sample_gap_before if metadata_mode else None,
        "physical_sample_continuity_proven": metadata_mode,
        "gap_context": gap_context,
        "command_boundary_gap_allowed": False,
    }
    if before is not None and after is not None:
        record["rx_state_before"] = before
        record["rx_state_after"] = after
    if parsed is not None:
        record["continuity"] = dict(continuity or {})
    state.frame_index += 1
    state.next_nominal_sample = first_sample + capture.frame_samples
    return _DeferredFrame(record=record, raw=raw, metadata=parsed)


def _classify_deferred_frame(
    frame: _DeferredFrame, *, iq_dir: Path, gap_context: str
) -> tuple[dict[str, Any], TandemFrameMetadata | None]:
    """Assign one acquired frame to a durable phase after command timing is known."""

    if gap_context not in _GAP_CONTEXTS:
        raise ValueError(f"unknown transient gap context {gap_context!r}")
    frame.iq_dir = iq_dir
    frame.record["gap_context"] = gap_context
    frame.record["command_boundary_gap_allowed"] = False
    continuity = frame.record.get("continuity")
    if isinstance(continuity, dict):
        continuity["gap_context"] = gap_context
        continuity["command_boundary_gap_allowed"] = False
    return frame.record, frame.metadata


def _materialize_deferred_frames(
    frames: Sequence[_DeferredFrame],
    *,
    quality: TandemQualityOptions,
    capture: TransientCaptureOptions,
    check_deadline: Callable[[], None],
) -> None:
    """Analyze, hash, and optionally persist IQ only after the IIO buffer closes."""

    for frame in frames:
        check_deadline()
        record = frame.record
        record["sha256"] = hashlib.sha256(frame.raw).hexdigest()
        record["analysis"] = dict(
            analyze_immediate_dual_rx(
                frame.raw,
                first_sample_sequence=int(record["first_sample_sequence"]),
                sample_rate_hz=quality.sample_rate_hz,
                expected_tone_hz=quality.tone_hz,
                window_samples=capture.window_samples,
                min_tone_snr_db=quality.thresholds.min_tone_snr_db,
                max_clipping_fraction=quality.thresholds.max_clipping_fraction,
                max_phase_std_deg=quality.thresholds.max_phase_std_deg,
            )
        )
        if frame.metadata is not None:
            record["metadata"] = _metadata_dict(frame.metadata)
        if quality.save_iq:
            if frame.iq_dir is None:
                raise EvidenceInvalid("transient frame lacks its IQ artifact phase")
            iq_path = frame.iq_dir / f"frame-{record['frame_index']:04d}.cs16"
            _atomic_bytes(iq_path, frame.raw)
            record["iq_path"] = str(iq_path)


def _require_returned_window_quality(
    baseline: Sequence[Mapping[str, Any]],
    attack: Sequence[Mapping[str, Any]],
    release: Sequence[Mapping[str, Any]],
    *,
    attack_command: StimulusCommand,
    release_command: StimulusCommand,
) -> None:
    """Reject invalid returned windows outside uncertain command intervals."""

    def command_intersects(window: Mapping[str, Any], command: StimulusCommand) -> bool:
        assert command.sample_sequence_before is not None
        assert command.sample_sequence_after is not None
        return (
            int(window["sample_start"]) < command.sample_sequence_after
            and int(window["sample_end_exclusive"]) > command.sample_sequence_before
        )

    checks = (
        (baseline, None),
        (attack, attack_command),
        (release, release_command),
    )
    for frames, command in checks:
        for frame in frames:
            for window in frame["analysis"]["windows"]:
                if command is not None and command_intersects(window, command):
                    continue
                if window.get("quality_valid") is not True:
                    raise EvidenceInvalid(
                        "transient returned-IQ window outside a command interval "
                        f"failed quality gates: {window.get('quality_reasons')!r}"
                    )


class _TandemCapturePump:
    """Continuously refill tandem IQ on one bounded acquisition-only thread."""

    def __init__(
        self,
        acquire: Callable[[], _DeferredFrame],
        *,
        maximum_frames: int,
        thread_name: str = "tandem-transient-acquisition",
    ) -> None:
        self._acquire = acquire
        self._maximum_frames = maximum_frames
        self._queue: queue.Queue[_DeferredFrame | BaseException] = queue.Queue(
            maxsize=_TANDEM_CAPTURE_QUEUE_FRAMES
        )
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=thread_name,
            daemon=True,
        )
        self.produced_frames = 0
        self.consumed_frames = 0
        self.discarded_tail_frames = 0
        self._terminal_error: BaseException | None = None
        self._started = False

    def start(self) -> None:
        self._thread.start()
        self._started = True

    @property
    def queue_capacity_frames(self) -> int:
        return self._queue.maxsize

    def _offer(self, item: _DeferredFrame | BaseException) -> bool:
        while not self._stop.is_set():
            try:
                self._queue.put(item, timeout=0.05)
                return True
            except queue.Full:
                continue
        return False

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                if self.produced_frames >= self._maximum_frames:
                    raise EvidenceInvalid(
                        "tandem acquisition exceeded its bounded frame budget"
                    )
                frame = self._acquire()
                self.produced_frames += 1
                if not self._offer(frame):
                    self.discarded_tail_frames += 1
                    return
        except BaseException as error:  # noqa: BLE001 - cross-thread propagation
            if (
                self._stop.is_set()
                and isinstance(error, OSError)
                and error.errno == errno.EBADF
            ):
                # iio_buffer_cancel() makes the pending/future refill return
                # EBADF by contract.  Suppress only that explicit stop result.
                return
            self._terminal_error = error
            self._offer(error)

    def take(self) -> _DeferredFrame:
        try:
            item = self._queue.get(timeout=_CAPTURE_THREAD_WAIT_SECONDS)
        except queue.Empty as exc:
            raise EvidenceInvalid(
                "tandem acquisition thread returned no frame before timeout"
            ) from exc
        if isinstance(item, BaseException):
            self._terminal_error = None
            raise item.with_traceback(item.__traceback__)
        self.consumed_frames += 1
        return item

    def request_stop(self) -> None:
        self._stop.set()

    def stop(self) -> None:
        self.request_stop()
        if not self._started:
            return
        self._thread.join(timeout=_CAPTURE_THREAD_WAIT_SECONDS)
        if self._thread.is_alive():
            raise EvidenceInvalid("tandem acquisition thread did not stop")
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, BaseException):
                self._terminal_error = None
                raise item.with_traceback(item.__traceback__)
            self.discarded_tail_frames += 1
        if self._terminal_error is not None:
            error = self._terminal_error
            self._terminal_error = None
            raise error.with_traceback(error.__traceback__)


def _strict_low32_counter(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceInvalid("RX sample-counter readback is not an integer")
    if not 0 <= value < _UINT32_MODULUS:
        raise EvidenceInvalid("RX sample-counter readback lies outside uint32")
    return value


def _extend_low32_near(raw: int, *, reference: int) -> int:
    """Extend a coherent low word to the unique uint64 value nearest a frame."""

    if not 0 <= reference < _UINT64_MODULUS:
        raise EvidenceInvalid("sample-counter extension reference exceeds uint64")
    base = reference & ~(_UINT32_MODULUS - 1)
    candidates = [base | raw]
    if candidates[0] >= _UINT32_MODULUS:
        candidates.append(candidates[0] - _UINT32_MODULUS)
    if candidates[0] + _UINT32_MODULUS < _UINT64_MODULUS:
        candidates.append(candidates[0] + _UINT32_MODULUS)
    distances = [abs(value - reference) for value in candidates]
    minimum = min(distances)
    if minimum >= _UINT32_MODULUS // 2 or distances.count(minimum) != 1:
        raise EvidenceInvalid("RX sample-counter low32 extension is ambiguous")
    return candidates[distances.index(minimum)]


def _timestamp_tandem_command(
    radio: TransientRadioTransport,
    command_id: str,
    requested_level_db: float,
    *,
    last_observed_frame_end: int,
    clock_ns: Callable[[], int],
    max_host_jitter_ns: int,
    max_sample_uncertainty: int,
    readback_tolerance_db: float,
) -> tuple[StimulusCommand, dict[str, Any]]:
    """Bracket a TX write with coherent FPGA-counter reads while refill runs."""

    raw_before = _strict_low32_counter(radio.read_rx_sample_counter_low32())
    extended_before = _extend_low32_near(raw_before, reference=last_observed_frame_end)
    command = timestamp_stimulus_command(
        command_id,
        requested_level_db,
        apply=radio.set_tx2_gain,
        clock_ns=clock_ns,
        max_host_jitter_ns=max_host_jitter_ns,
        readback_tolerance_db=readback_tolerance_db,
    )

    raw_post_write_initial = _strict_low32_counter(radio.read_rx_sample_counter_low32())
    raw_post_write_first_advance: int | None = None
    raw_post_write_causal: int | None = None
    post_write_read_count = 1
    for _ in range(8):
        current = _strict_low32_counter(radio.read_rx_sample_counter_low32())
        post_write_read_count += 1
        if raw_post_write_first_advance is None:
            if current != raw_post_write_initial:
                raw_post_write_first_advance = current
        elif current != raw_post_write_first_advance:
            raw_post_write_causal = current
            break
    else:
        raise EvidenceInvalid(
            f"command {command_id!r} did not observe two post-write FPGA "
            "counter advances"
        )
    assert raw_post_write_first_advance is not None
    assert raw_post_write_causal is not None

    initial_delta = (raw_post_write_initial - raw_before) % _UINT32_MODULUS
    first_advance_delta = (
        raw_post_write_first_advance - raw_post_write_initial
    ) % _UINT32_MODULUS
    causal_advance_delta = (
        raw_post_write_causal - raw_post_write_first_advance
    ) % _UINT32_MODULUS
    if initial_delta >= _UINT32_MODULUS // 2 or not all(
        0 < delta < _UINT32_MODULUS // 2
        for delta in (first_advance_delta, causal_advance_delta)
    ):
        raise EvidenceInvalid(
            f"command {command_id!r} FPGA counter bracket is ambiguous"
        )
    extended_post_write_initial = extended_before + initial_delta
    extended_post_write_first_advance = (
        extended_post_write_initial + first_advance_delta
    )
    extended_after = extended_post_write_first_advance + causal_advance_delta
    if extended_after >= _UINT64_MODULUS:
        raise EvidenceInvalid(
            f"command {command_id!r} FPGA counter bracket exceeds uint64"
        )
    lower = max(last_observed_frame_end, extended_before)
    uncertainty = extended_after - lower
    if uncertainty <= 0:
        raise EvidenceInvalid(
            f"command {command_id!r} FPGA counter bracket is empty or predates "
            "observed IQ"
        )
    if uncertainty > max_sample_uncertainty:
        raise EvidenceInvalid(
            f"command {command_id!r} sample uncertainty {uncertainty} exceeds "
            f"{max_sample_uncertainty} samples"
        )
    bracketed = replace(
        command,
        sample_sequence_before=lower,
        sample_sequence_after=extended_after,
    )
    return bracketed, {
        "register_address": "0x800000b8",
        "counter_width_bits": 32,
        "counter_source": "coherent FPGA RX sample counter low word",
        "extension_reference_sample": last_observed_frame_end,
        "raw_before": raw_before,
        "raw_post_write_initial": raw_post_write_initial,
        "raw_post_write_first_advance": raw_post_write_first_advance,
        "raw_post_write_causal": raw_post_write_causal,
        "extended_before": extended_before,
        "extended_post_write_initial": extended_post_write_initial,
        "extended_post_write_first_advance": (extended_post_write_first_advance),
        "extended_after": extended_after,
        "post_write_read_count": post_write_read_count,
        "lower_clamped_to_last_observed_frame_end": lower != extended_before,
        "sample_sequence_lower": lower,
        "sample_sequence_upper": extended_after,
    }


def _response_gap_context(frame: Mapping[str, Any], command: StimulusCommand) -> str:
    assert command.sample_sequence_before is not None
    assert command.sample_sequence_after is not None
    start = int(frame["first_sample_sequence"])
    end = int(frame["sample_end_exclusive"])
    if end <= command.sample_sequence_before:
        return _GAP_CONTEXT_PREFETCH
    if start < command.sample_sequence_after:
        return _GAP_CONTEXT_COMMAND
    return _GAP_CONTEXT_CONTINUOUS_RESPONSE


def _response_partition(
    frames: Sequence[Mapping[str, Any]],
    command: StimulusCommand,
    *,
    required_fully_post_frames: int,
) -> dict[str, int]:
    """Prove the bounded producer prefix leaves the full response budget."""

    assert command.sample_sequence_before is not None
    assert command.sample_sequence_after is not None
    contexts = [_response_gap_context(frame, command) for frame in frames]
    non_post = sum(
        int(frame["first_sample_sequence"]) < command.sample_sequence_after
        for frame in frames
    )
    fully_post = len(frames) - non_post
    if non_post > _TANDEM_CAPTURE_TAIL_FRAMES:
        raise EvidenceInvalid(
            f"command {command.command_id!r} has {non_post} pre/bracketed tandem "
            f"frames, exceeding the {_TANDEM_CAPTURE_TAIL_FRAMES}-frame producer "
            "tail bound"
        )
    if fully_post < required_fully_post_frames:
        raise EvidenceInvalid(
            f"command {command.command_id!r} retained only {fully_post} fully "
            f"post-command frames, requires {required_fully_post_frames}"
        )
    if contexts != sorted(
        contexts,
        key={
            _GAP_CONTEXT_PREFETCH: 0,
            _GAP_CONTEXT_COMMAND: 1,
            _GAP_CONTEXT_CONTINUOUS_RESPONSE: 2,
        }.__getitem__,
    ):
        raise EvidenceInvalid(
            f"command {command.command_id!r} response phases are not sample ordered"
        )
    return {
        "precommand_prefetch_frames": contexts.count(_GAP_CONTEXT_PREFETCH),
        "command_bracket_frames": contexts.count(_GAP_CONTEXT_COMMAND),
        "fully_post_command_frames": fully_post,
        "required_fully_post_command_frames": required_fully_post_frames,
        "maximum_non_post_command_frames": _TANDEM_CAPTURE_TAIL_FRAMES,
    }


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
    *,
    mode: str,
    capture: TransientCaptureOptions,
    capture_next: Callable[[], _DeferredFrame],
    iq_dir: Path,
    check_deadline: Callable[[], None],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trace: list[dict[str, Any]] = []
    stable_run: list[dict[str, Any]] = []
    previous_metadata: TandemFrameMetadata | None = None
    for attempt in range(1, capture.max_precondition_frames + 1):
        check_deadline()
        frame, metadata = _classify_deferred_frame(
            capture_next(),
            iq_dir=iq_dir / "precondition",
            gap_context=_GAP_CONTEXT_PRECONDITION,
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
                    "returned_iq_observation_span_lower_axis_units": max(
                        0, start - command.sample_sequence_after
                    ),
                    "returned_iq_observation_span_upper_axis_units": max(
                        0, end - command.sample_sequence_before
                    ),
                }
                break
            if after_change >= minimum_change_db:
                found = {
                    "rx_channel": channel,
                    "evidence": "post_refill_readback",
                    "observed_gain_db": after,
                    "returned_iq_observation_span_lower_axis_units": max(
                        0, start - command.sample_sequence_after
                    ),
                    "returned_iq_observation_span_upper_axis_units": max(
                        0, end - command.sample_sequence_before
                    ),
                }
                break
        if found is None:
            raise EvidenceInvalid(
                f"RX{channel} lacks a {minimum_change_db:g} dB native gain response"
            )
        found["hardware_latency_qualified"] = False
        results.append(found)
    return results


def _native_gain_evidence(
    baseline: Sequence[Mapping[str, Any]],
    attack: Sequence[Mapping[str, Any]],
    release: Sequence[Mapping[str, Any]],
    *,
    attack_command: StimulusCommand,
    release_command: StimulusCommand,
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
    return {
        "evidence_valid": True,
        "timing_qualification": "returned_iq_observation_only",
        "hardware_latency_qualified": False,
        "minimum_required_change_db": minimum_change_db,
        "weak_gain_db": list(weak),
        "strong_gain_db": list(strong),
        "returned_weak_gain_db": list(returned),
        "attack_gain_change_db": [strong[index] - weak[index] for index in (0, 1)],
        "release_gain_change_db": [returned[index] - strong[index] for index in (0, 1)],
        "attack_returned_iq_observation_bounds": attack_bounds,
        "release_returned_iq_observation_bounds": release_bounds,
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
        "timing_qualification": "not_applicable_fixed_gain",
        "hardware_latency_qualified": False,
        "expected_gain_db": expected_gain_db,
        "gain_span_db": spans,
        "maximum_readback_error_db": errors,
    }


def _qualify_response_timing(
    response: Mapping[str, Any], *, hardware_latency_qualified: bool
) -> dict[str, Any]:
    qualified = dict(response)
    if hardware_latency_qualified:
        qualified["timing_qualification"] = "fpga_sample_counter_bounded"
        qualified["hardware_latency_qualified"] = True
        qualified["transient_observation_scope"] = "continuous_hardware_sample_record"
        return qualified
    lower = qualified.pop("signal_settling_latency_lower_samples")
    upper = qualified.pop("signal_settling_latency_upper_samples")
    qualified.pop("signal_settling_latency_lower_seconds")
    qualified.pop("signal_settling_latency_upper_seconds")
    qualified.update(
        {
            "timing_qualification": "returned_iq_observation_only",
            "hardware_latency_qualified": False,
            "transient_observation_scope": (
                "returned_iq_windows_with_unobserved_refill_intervals"
            ),
            "observed_returned_iq_settling_span_lower_axis_units": lower,
            "observed_returned_iq_settling_span_upper_axis_units": upper,
        }
    )
    return qualified


def _response_summary(
    response: Mapping[str, Any], *, hardware_latency_qualified: bool
) -> dict[str, Any]:
    summary = {
        "timing_qualification": response["timing_qualification"],
        "hardware_latency_qualified": hardware_latency_qualified,
        "transient_observation_scope": response["transient_observation_scope"],
        "worst_overshoot_db": response["worst_overshoot_db"],
        "ringing_peak_to_peak_db": response["ringing_peak_to_peak_db"],
        "minimum_post_tone_snr_db": response["minimum_post_tone_snr_db"],
        "maximum_post_clipping_fraction": response["maximum_post_clipping_fraction"],
        "maximum_phase_excursion_deg": response["maximum_phase_excursion_deg"],
    }
    if hardware_latency_qualified:
        summary.update(
            {
                "signal_settling_latency_lower_samples": response[
                    "signal_settling_latency_lower_samples"
                ],
                "signal_settling_latency_upper_samples": response[
                    "signal_settling_latency_upper_samples"
                ],
                "signal_settling_latency_lower_seconds": response[
                    "signal_settling_latency_lower_seconds"
                ],
                "signal_settling_latency_upper_seconds": response[
                    "signal_settling_latency_upper_seconds"
                ],
            }
        )
    else:
        summary.update(
            {
                "signal_settling_latency_lower_samples": None,
                "signal_settling_latency_upper_samples": None,
                "signal_settling_latency_lower_seconds": None,
                "signal_settling_latency_upper_seconds": None,
                "observed_returned_iq_settling_span_lower_axis_units": response[
                    "observed_returned_iq_settling_span_lower_axis_units"
                ],
                "observed_returned_iq_settling_span_upper_axis_units": response[
                    "observed_returned_iq_settling_span_upper_axis_units"
                ],
            }
        )
    return summary


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
            f"TX2 readback for {command.command_id!r} violates the "
            "30 dB safety boundary"
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
    """Position a host write on the returned-IQ ordinal axis.

    Ordinary IIO exposes no RF sample counter or continuity.  These coordinates
    run from the end of the last returned pre-command frame through the end of
    the first returned post-command frame.  Unobserved hardware time and sample
    intervals are excluded, so the result is an observation span, not latency.
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
    sample_counter_bracket: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    counter_timed = sample_counter_bracket is not None
    record = {
        **command.as_dict(),
        "effective_attenuation_db": effective_attenuation_db,
        "rx_state_before": rx_state_before,
        "rx_state_after": rx_state_after,
        "timing_role": (
            "host_write_bracketed_by_coherent_fpga_counter"
            if counter_timed
            else "host_write_positioned_on_returned_iq_ordinal_axis"
        ),
        "sample_timing_basis": timing_basis,
        "sample_anchor_policy": (
            "max(last observed frame end, coherent low32 pre-read) through the "
            "second distinct coherent low32 advance observed after an initial "
            "post-write read"
            if counter_timed
            else "last returned pre-command IQ ordinal through end of first "
            "returned post-command frame; unobserved hardware intervals excluded"
        ),
    }
    if sample_counter_bracket is not None:
        record["sample_counter_bracket"] = dict(sample_counter_bracket)
    return record


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
        capture.weak_stimulus_tx_gain_db,
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
        _TANDEM_TIMING_BASIS if mode == MODE_TANDEM else _ORDINARY_TIMING_BASIS
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
    deferred_frames: list[_DeferredFrame] = []
    attack_counter_bracket: Mapping[str, Any] | None = None
    release_counter_bracket: Mapping[str, Any] | None = None
    attack_partition: Mapping[str, int] | None = None
    release_partition: Mapping[str, int] | None = None
    acquisition_stats: dict[str, Any] = {
        "threaded": mode == MODE_TANDEM,
        "kernel_buffers": _TRANSIENT_KERNEL_BUFFERS,
        "queue_capacity_frames": (
            _TANDEM_CAPTURE_QUEUE_FRAMES if mode == MODE_TANDEM else 0
        ),
        "response_tail_frames": (
            _TANDEM_CAPTURE_TAIL_FRAMES if mode == MODE_TANDEM else 0
        ),
    }
    mode_body_error: BaseException | None = None
    try:
        with radio.buffer(
            "metadata" if mode == MODE_TANDEM else "ordinary",
            _TRANSIENT_KERNEL_BUFFERS,
            capture.frame_samples,
            tandem_request=request,
        ) as (buffer, metadata_abi):
            if mode == MODE_TANDEM and metadata_abi != 2:
                raise EvidenceInvalid(
                    f"tandem transient requires metadata ABI 2, got {metadata_abi!r}"
                )
            cancel_capture = getattr(buffer, "cancel", None)
            if mode == MODE_TANDEM and not callable(cancel_capture):
                raise EvidenceInvalid(
                    "tandem transient buffer lacks thread-safe cancellation"
                )

            def acquire_one() -> _DeferredFrame:
                return _capture_frame(
                    radio,
                    buffer,
                    mode=mode,
                    expected_iio_mode=expected_iio_mode,
                    quality=quality,
                    capture=capture,
                    state=state,
                    metadata_parser=metadata_parser,
                    gap_context=(
                        _GAP_CONTEXT_ACQUISITION
                        if mode == MODE_TANDEM
                        else _GAP_CONTEXT_CONTINUOUS_RESPONSE
                    ),
                )

            pump: _TandemCapturePump | None = None
            raw_next: Callable[[], _DeferredFrame] = acquire_one
            if mode == MODE_TANDEM:
                maximum_pump_frames = (
                    capture.max_precondition_frames
                    + 2 * (capture.response_frames + _TANDEM_CAPTURE_TAIL_FRAMES)
                    + _TANDEM_CAPTURE_QUEUE_FRAMES
                    + 1
                )
                pump = _TandemCapturePump(
                    acquire_one, maximum_frames=maximum_pump_frames
                )
                pump.start()
                raw_next = pump.take

            def capture_next() -> _DeferredFrame:
                frame = raw_next()
                deferred_frames.append(frame)
                retained_bytes = sum(len(item.raw) for item in deferred_frames)
                if retained_bytes > _MAX_DEFERRED_CAPTURE_BYTES:
                    raise EvidenceInvalid(
                        "transient deferred IQ exceeded its static memory bound"
                    )
                return frame

            acquisition_error: BaseException | None = None
            try:
                trace, baseline = _precondition(
                    mode=mode,
                    capture=capture,
                    capture_next=capture_next,
                    iq_dir=iq_dir,
                    check_deadline=check_deadline,
                )

                attack_boundary = int(baseline[-1]["sample_end_exclusive"])
                attack_gain_before = (
                    None
                    if mode == MODE_TANDEM
                    else _rx_state(radio, expected_mode=expected_iio_mode)
                )
                if mode == MODE_TANDEM:
                    attack, attack_counter_bracket = _timestamp_tandem_command(
                        radio,
                        "strong_attack",
                        capture.strong_stimulus_tx_gain_db,
                        last_observed_frame_end=attack_boundary,
                        clock_ns=clock_ns,
                        max_host_jitter_ns=capture.max_host_jitter_ns,
                        max_sample_uncertainty=capture.max_sample_uncertainty,
                        readback_tolerance_db=capture.readback_tolerance_db,
                    )
                else:
                    attack = timestamp_stimulus_command(
                        "strong_attack",
                        capture.strong_stimulus_tx_gain_db,
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
                response_capture_frames = capture.response_frames + (
                    _TANDEM_CAPTURE_TAIL_FRAMES if mode == MODE_TANDEM else 0
                )
                for frame_index in range(response_capture_frames):
                    check_deadline()
                    pending = capture_next()
                    gap_context = (
                        _response_gap_context(pending.record, attack)
                        if mode == MODE_TANDEM
                        else (
                            _GAP_CONTEXT_COMMAND
                            if frame_index == 0
                            else _GAP_CONTEXT_CONTINUOUS_RESPONSE
                        )
                    )
                    frame, _metadata = _classify_deferred_frame(
                        pending,
                        iq_dir=iq_dir / "attack",
                        gap_context=gap_context,
                    )
                    attack_frames.append(frame)
                if mode != MODE_TANDEM:
                    attack = _bracket_host_write(
                        attack,
                        last_pre_frame_end=attack_boundary,
                        first_post_frame=attack_frames[0],
                        max_sample_uncertainty=capture.max_sample_uncertainty,
                    )
                else:
                    attack_partition = _response_partition(
                        attack_frames,
                        attack,
                        required_fully_post_frames=capture.response_frames,
                    )

                release_boundary = int(attack_frames[-1]["sample_end_exclusive"])
                release_gain_before = (
                    None
                    if mode == MODE_TANDEM
                    else _rx_state(radio, expected_mode=expected_iio_mode)
                )
                if mode == MODE_TANDEM:
                    release, release_counter_bracket = _timestamp_tandem_command(
                        radio,
                        "weak_release",
                        capture.weak_stimulus_tx_gain_db,
                        last_observed_frame_end=release_boundary,
                        clock_ns=clock_ns,
                        max_host_jitter_ns=capture.max_host_jitter_ns,
                        max_sample_uncertainty=capture.max_sample_uncertainty,
                        readback_tolerance_db=capture.readback_tolerance_db,
                    )
                else:
                    release = timestamp_stimulus_command(
                        "weak_release",
                        capture.weak_stimulus_tx_gain_db,
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
                for frame_index in range(response_capture_frames):
                    check_deadline()
                    pending = capture_next()
                    gap_context = (
                        _response_gap_context(pending.record, release)
                        if mode == MODE_TANDEM
                        else (
                            _GAP_CONTEXT_COMMAND
                            if frame_index == 0
                            else _GAP_CONTEXT_CONTINUOUS_RESPONSE
                        )
                    )
                    frame, _metadata = _classify_deferred_frame(
                        pending,
                        iq_dir=iq_dir / "release",
                        gap_context=gap_context,
                    )
                    release_frames.append(frame)
                if mode != MODE_TANDEM:
                    release = _bracket_host_write(
                        release,
                        last_pre_frame_end=release_boundary,
                        first_post_frame=release_frames[0],
                        max_sample_uncertainty=capture.max_sample_uncertainty,
                    )
                else:
                    release_partition = _response_partition(
                        release_frames,
                        release,
                        required_fully_post_frames=capture.response_frames,
                    )
                    assert attack_partition is not None
                    acquisition_stats["response_partitions"] = {
                        "attack": dict(attack_partition),
                        "release": dict(release_partition),
                    }
            except BaseException as error:  # noqa: BLE001 - preserve interrupts
                acquisition_error = error
            prejoin_mute_error: BaseException | None = None
            if acquisition_error is not None or pump is not None:
                # A failed acquisition can otherwise leave the strong stimulus
                # active for the worker join timeout.  A successful tandem run
                # can also leave its producer blocked in the next refill.  Mute,
                # cancel, and join deterministically before buffer close.
                try:
                    radio.mute_all()
                except BaseException as error:  # noqa: BLE001 - preserve both
                    prejoin_mute_error = error
            cancel_error: BaseException | None = None
            if pump is not None:
                pump.request_stop()
                try:
                    assert callable(cancel_capture)
                    cancel_capture()
                except BaseException as error:  # noqa: BLE001 - preserve all
                    cancel_error = error
                acquisition_stats["buffer_cancelled_before_join"] = cancel_error is None
            pump_stop_error: BaseException | None = None
            if pump is not None:
                try:
                    pump.stop()
                except BaseException as error:  # noqa: BLE001
                    pump_stop_error = error
                acquisition_stats.update(
                    {
                        "produced_frames": pump.produced_frames,
                        "consumed_frames": pump.consumed_frames,
                        "discarded_tail_frames": pump.discarded_tail_frames,
                    }
                )
            acquisition_errors = [
                error
                for error in (
                    acquisition_error,
                    prejoin_mute_error,
                    cancel_error,
                    pump_stop_error,
                )
                if error is not None
            ]
            if len(acquisition_errors) > 1:
                raise BaseExceptionGroup(
                    "transient acquisition, emergency mute, buffer cancel, or "
                    "capture-thread shutdown failed",
                    acquisition_errors,
                )
            if acquisition_errors:
                error = acquisition_errors[0]
                raise error.with_traceback(error.__traceback__)

        # Release tandem ownership and mute RF before any FFT, hashing, or disk IO.
        radio.mute_all()
        _materialize_deferred_frames(
            deferred_frames,
            quality=quality,
            capture=capture,
            check_deadline=check_deadline,
        )
        _require_returned_window_quality(
            baseline,
            attack_frames,
            release_frames,
            attack_command=attack,
            release_command=release,
        )

        initial = _conditioning_anchor(
            initial_unanchored,
            baseline,
            max_sample_uncertainty=capture.max_sample_uncertainty,
        )
        record["acquisition"] = acquisition_stats
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
        record["commands"].extend(
            (
                _command_record(
                    attack,
                    effective_attenuation_db=attack_effective,
                    timing_basis=timing_basis,
                    rx_state_before=attack_gain_before,
                    rx_state_after=attack_gain_after,
                    sample_counter_bracket=attack_counter_bracket,
                ),
                _command_record(
                    release,
                    effective_attenuation_db=release_effective,
                    timing_basis=timing_basis,
                    rx_state_before=release_gain_before,
                    rx_state_after=release_gain_after,
                    sample_counter_bracket=release_counter_bracket,
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
        hardware_latency_qualified = mode == MODE_TANDEM
        record["responses"] = {
            "attack": _qualify_response_timing(
                calculate_transient_response(
                    _flatten_windows([*baseline, *attack_frames]),
                    previous_command=initial,
                    command=attack,
                    **response_kwargs,
                ),
                hardware_latency_qualified=hardware_latency_qualified,
            ),
            "release": _qualify_response_timing(
                calculate_transient_response(
                    _flatten_windows([*attack_frames, *release_frames]),
                    previous_command=attack,
                    command=release,
                    **response_kwargs,
                ),
                hardware_latency_qualified=hardware_latency_qualified,
            ),
        }

        if native_iio_mode is not None:
            record["gain_evidence"] = _native_gain_evidence(
                baseline,
                attack_frames,
                release_frames,
                attack_command=attack,
                release_command=release,
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
            record["gain_evidence"].update(
                {
                    "timing_qualification": "fpga_sample_counter_bounded",
                    "hardware_latency_qualified": True,
                }
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
    comparison = []
    for mode in modes:
        hardware_latency_qualified = mode["mode"] == MODE_TANDEM
        comparison.append(
            {
                "mode": mode["mode"],
                "timing_basis": mode["timing_basis"],
                "attack": _response_summary(
                    mode["responses"]["attack"],
                    hardware_latency_qualified=hardware_latency_qualified,
                ),
                "release": _response_summary(
                    mode["responses"]["release"],
                    hardware_latency_qualified=hardware_latency_qualified,
                ),
                "gain_evidence": mode["gain_evidence"],
            }
        )
    return comparison


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
    """Run four guarded transient cells and atomically preserve all evidence."""

    validate_transient_options(quality, capture)
    if radio.options.sample_rate_hz != quality.sample_rate_hz:
        raise ValueError("radio and transient sample rates differ")
    if abs(float(radio.options.tx_gain_db) - capture.strong_stimulus_tx_gain_db) > 0.01:
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
                "transient hardware campaign exceeded "
                f"{quality.max_seconds:.1f} seconds"
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
            capture.weak_stimulus_tx_gain_db,
            capture.strong_stimulus_tx_gain_db,
            capture.weak_stimulus_tx_gain_db,
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
            "kernel_buffers": _TRANSIENT_KERNEL_BUFFERS,
        },
        "safety": {
            "physical_attenuation_db": quality.physical_attenuation_db,
            "strongest_tx_gain_db": capture.strong_stimulus_tx_gain_db,
            "minimum_effective_attenuation_db": (
                quality.physical_attenuation_db - capture.strong_stimulus_tx_gain_db
            ),
            "required_effective_attenuation_db": 30.0,
            "tx1_policy": "muted below -80 dB for the entire campaign",
        },
        "evidence_policy": transient_evidence_policy(capture),
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
