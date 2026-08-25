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

import ctypes
import errno
import hashlib
import json
import math
import queue
import statistics
import sys
import threading
import time
from builtins import BaseExceptionGroup
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from dataclasses import fields as dataclass_fields
from enum import Enum
from itertools import pairwise
from pathlib import Path
from typing import Any, Protocol

from .experiment import TX_MUTE_DB, EvidenceInvalid, FixtureSafetyError, Issue46Radio
from .metadata_abi import (
    FEATURE_AD9361_TEMPERATURE,
    FEATURE_FPGA_GAIN_EVENTS,
    FEATURE_HARDWARE_SAMPLE_COUNTER,
    FEATURE_TANDEM_METADATA,
    FLAG_HARDWARE_SAMPLE_COUNTER_VALID,
    FLAG_SAMPLE_SEQUENCE_VALID,
    FLAG_TANDEM_METADATA_VALID,
    TANDEM_REQUEST,
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

# Release tandem is deliberately a different transport from every ordinary
# comparison cell.  These constants describe the one previously qualified
# libiio batch shape and are not user-tunable knobs.
_TANDEM_FRAME_SAMPLES = 65_536
_TANDEM_KERNEL_BUFFERS = 8
_TANDEM_BATCH_FRAMES = 64
_TANDEM_METADATA_CAPACITY_BYTES = 64 * 1024
_TANDEM_INITIAL_GAIN_DB = 62
_TANDEM_ATTACK_TARGET_FRAMES = 16
_TANDEM_RELEASE_TARGET_FRAMES = 40
_TANDEM_WEAK_FIRST_COMMAND_ID = "weak_reassertion_16f"
_TANDEM_WEAK_SECOND_COMMAND_ID = "weak_reassertion_40f"
_TANDEM_WEAK_COMMAND_LEVEL_DB = -45.0
_TANDEM_WEAK_ARTIFACT_DIRECTORY = "weak_dual_target"
_TANDEM_WEAK_ARTIFACT_POLICY = (
    "mandatory_exact_weak_dual_target_preflight_sidecars"
)
_TANDEM_REQUIRED_PARTITION_FRAMES = 8
_TANDEM_CONDITIONING_TAIL_SAMPLES = 8_192
_TANDEM_WINDOW_SAMPLES = 1_024
_TANDEM_MAX_TARGET_OVERSHOOT_SAMPLES = 16_384
_TANDEM_MAX_CAUSAL_UNCERTAINTY_SAMPLES = 16_384
_TANDEM_TARGET_COARSE_GUARD_SAMPLES = 65_536
_TANDEM_TARGET_FINE_SLEEP_SAMPLES = 4_096
_TANDEM_TARGET_MAX_POLL_READS = 64
_TANDEM_FRAME_IQ_BYTES = _TANDEM_FRAME_SAMPLES * 8
_TANDEM_BATCH_CACHE_BYTES = _TANDEM_BATCH_FRAMES * (
    _TANDEM_FRAME_IQ_BYTES
    + _TANDEM_METADATA_CAPACITY_BYTES
    + 2 * ctypes.sizeof(ctypes.c_size_t)
)
_TANDEM_MAXIMUM_PYTHON_RAW_BYTES = (
    _TANDEM_BATCH_FRAMES * _TANDEM_FRAME_IQ_BYTES
)
_TANDEM_MAXIMUM_PYTHON_RAW_METADATA_BYTES = (
    _TANDEM_BATCH_FRAMES * _TANDEM_METADATA_CAPACITY_BYTES
)
_TANDEM_PARSED_EVIDENCE_RESERVATION_BYTES = 8 * 1024 * 1024
_TANDEM_POST_CLOSE_FFT_WORKSPACE_BYTES = 8 * 1024 * 1024
_TANDEM_MAXIMUM_AGGREGATE_BYTES = 96 * 1024 * 1024
_TANDEM_EVIDENCE_PROJECTION_SCHEMA = "plutosdr-fw.tandem-evidence-projection.v1"
_TANDEM_EVIDENCE_PROJECTION_METHOD = (
    "canonical-json-v1: finished tandem mode with attestation value fields "
    "replaced by fixed sentinels plus 64 normalized reparsed metadata records"
)
_TANDEM_AGGREGATE_RESIDENT_BYTES = sum(
    (
        _TANDEM_BATCH_CACHE_BYTES,
        _TANDEM_FRAME_IQ_BYTES,  # ordinary libiio C buffer
        _TANDEM_MAXIMUM_PYTHON_RAW_BYTES,
        _TANDEM_MAXIMUM_PYTHON_RAW_METADATA_BYTES,
        _TANDEM_FRAME_IQ_BYTES,  # transient Buffer.read() bytearray
        _TANDEM_METADATA_CAPACITY_BYTES,  # ctypes refill scratch
        _TANDEM_METADATA_CAPACITY_BYTES,  # returned metadata bytes
        _TANDEM_PARSED_EVIDENCE_RESERVATION_BYTES,
        _TANDEM_KERNEL_BUFFERS * _TANDEM_FRAME_IQ_BYTES,  # K8 DMA reservation
    )
)
assert _TANDEM_AGGREGATE_RESIDENT_BYTES <= _TANDEM_MAXIMUM_AGGREGATE_BYTES
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
_TANDEM_REQUIRED_METADATA_FLAGS = (
    FLAG_SAMPLE_SEQUENCE_VALID
    | FLAG_HARDWARE_SAMPLE_COUNTER_VALID
    | FLAG_TANDEM_METADATA_VALID
)
# RC2 assigns every metadata flag bit from 0 through 22.  Reject higher bits so
# a future or corrupted wire record cannot silently acquire safety semantics
# that this release runner does not understand.
_TANDEM_KNOWN_METADATA_FLAGS = (1 << 23) - 1
_TANDEM_REQUIRED_METADATA_FEATURES = (
    FEATURE_AD9361_TEMPERATURE
    | FEATURE_FPGA_GAIN_EVENTS
    | FEATURE_HARDWARE_SAMPLE_COUNTER
    | FEATURE_TANDEM_METADATA
)
# RC2 defines feature bits 0 through 9.  Known optional bits remain accepted,
# including the observed full 0x3ff provider mask, while unknown future bits
# fail closed for a release qualification.
_TANDEM_KNOWN_METADATA_FEATURES = (1 << 10) - 1
_TANDEM_METADATA_HEADER_BYTES = 180 + 64 * 32 + 64 * 16 + 4
_TANDEM_MINIMUM_TEMPERATURE_MDEG_C = -40_000
_TANDEM_MAXIMUM_TEMPERATURE_MDEG_C = 125_000


class _TandemBatchProfile(Enum):
    """Closed profiles sharing the audited one-session batch transport."""

    PRODUCTION_ATTACK_RELEASE = "production_attack_release"
    WEAK_DUAL_TARGET_TRANSPORT = "weak_dual_target_transport"


class TransientRadioTransport(Protocol):
    """The existing radio operations used by the transient runner."""

    options: Any
    identity: Mapping[str, Any]
    _report_path: Path | None

    def mute_all(self) -> Mapping[str, Any] | None: ...

    def arm_tx2_tone(self, *, tone_hz: int, scale: float) -> None: ...

    def set_tx2_gain(self, gain_db: float) -> float: ...

    def write_tx2_gain_exact(self, gain_db: float) -> None: ...

    def read_tx2_gain(self) -> float: ...

    def attest_tx1_muted(self) -> float: ...

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
        batch_frames: int = 1,
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
    raw_metadata: bytes | None = None
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
            "one continuous AUTO metadata session; one F65536/K8/batch64 refill "
            "and 63 cached replays on a bounded acquisition-only thread; both "
            "commands execute while the initiating refill is in flight; FFT, "
            "hashing, and IQ artifact writes begin only after normal buffer close"
        ),
        "tandem_provider_gaps": (
            "reject every buffer/sample gap and every hidden transition; the "
            "provider does not retain exact events or signal response for omitted "
            "frames"
        ),
        "tandem_provider_frame_samples": _TANDEM_FRAME_SAMPLES,
        "tandem_kernel_buffers": _TANDEM_KERNEL_BUFFERS,
        "tandem_batch_frames": _TANDEM_BATCH_FRAMES,
        "tandem_capture_queue_frames": _TANDEM_CAPTURE_QUEUE_FRAMES,
        "tandem_attack_target_frames_after_s0": _TANDEM_ATTACK_TARGET_FRAMES,
        "tandem_release_target_frames_after_s0": _TANDEM_RELEASE_TARGET_FRAMES,
        "tandem_maximum_target_overshoot_samples": (
            _TANDEM_MAX_TARGET_OVERSHOOT_SAMPLES
        ),
        "tandem_maximum_a_to_c_uncertainty_samples": (
            _TANDEM_MAX_CAUSAL_UNCERTAINTY_SAMPLES
        ),
        "tandem_required_partition_frames": _TANDEM_REQUIRED_PARTITION_FRAMES,
        "tandem_conditioning_tail_samples": _TANDEM_CONDITIONING_TAIL_SAMPLES,
        "tandem_analysis_window_samples": _TANDEM_WINDOW_SAMPLES,
        "tandem_batch_cache_bytes": _TANDEM_BATCH_CACHE_BYTES,
        "tandem_aggregate_resident_bytes": _TANDEM_AGGREGATE_RESIDENT_BYTES,
        "tandem_success_close": (
            "full 1+63 replay; normal close; no cancel"
        ),
        "tandem_post_close": (
            "IDLE/fault0/overflow0/FIFO0/unowned; retain pre-close diagnostics "
            "without exact retired-tail claim"
        ),
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
    if quality.samples_per_channel < _TANDEM_FRAME_SAMPLES:
        raise ValueError(
            "transient release quality authorization must cover the frozen "
            f"{_TANDEM_FRAME_SAMPLES}-sample tandem provider frame"
        )
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
    names = (
        "state",
        "fault_flags",
        "overflow_count",
        "fifo_level",
        "ownership_epoch",
        "transition_count",
        "rx1_gain_index",
        "rx2_gain_index",
    )
    expected_names = set(names)
    while True:
        raw = radio.tandem_status()
        if not isinstance(raw, Mapping) or set(raw) != expected_names:
            raise EvidenceInvalid("tandem IDLE status fields are incomplete")
        try:
            values = {name: raw[name] for name in names}
        except (KeyError, TypeError) as error:
            raise EvidenceInvalid("tandem IDLE status is incomplete") from error
        if any(type(value) is not int for value in values.values()):
            raise EvidenceInvalid("tandem IDLE status contains a non-exact integer")
        status = dict(values)
        if (
            status["rx1_gain_index"] != status["rx2_gain_index"]
            or not 0 <= status["rx1_gain_index"] <= 127
        ):
            raise EvidenceInvalid(
                "tandem IDLE endpoint is not a paired 7-bit gain index"
            )
        if (
            status["fault_flags"]
            or status["overflow_count"]
        ):
            raise EvidenceInvalid(f"tandem controller status is unsafe: {status}")
        if (
            status.get("state") == int(TandemState.IDLE)
            and status.get("fault_flags") == 0
            and status.get("overflow_count") == 0
            and status.get("fifo_level") == 0
            and status.get("ownership_epoch") == 0
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
        "version": metadata.version,
        "header_bytes": metadata.header_bytes,
        "features": metadata.features,
        "stream_id": metadata.stream_id,
        "buffer_sequence": metadata.buffer_sequence,
        "first_sample_sequence": metadata.first_sample_sequence,
        "samples_per_channel": metadata.samples_per_channel,
        "iq_payload_bytes": metadata.iq_payload_bytes,
        "enabled_scan_mask": metadata.enabled_scan_mask,
        "flags": metadata.flags,
        "sample_format": metadata.sample_format,
        "channel_count": metadata.channel_count,
        "observation_count": metadata.observation_count,
        "observation_capacity": metadata.observation_capacity,
        "event_capacity": metadata.event_capacity,
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
        "rx1_gain_index": metadata.rx1_gain_index,
        "rx2_gain_index": metadata.rx2_gain_index,
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
    temperature_valid_seen: bool = False
    temperature_valid_count: int = 0
    temperature_omission_count: int = 0
    temperature_first_valid_ordinal: int | None = None
    temperature_minimum_valid_mdeg_c: int | None = None
    temperature_maximum_valid_mdeg_c: int | None = None


def _observe_tandem_temperature(
    metadata: TandemFrameMetadata, *, state: _CaptureState
) -> None:
    temperature = metadata.ad9361_temperature_mdeg_c
    if temperature is None:
        if state.temperature_valid_seen:
            raise EvidenceInvalid(
                "tandem temperature became unavailable after its first valid sample"
            )
        state.temperature_omission_count += 1
        return
    if (
        type(temperature) is not int
        or not _TANDEM_MINIMUM_TEMPERATURE_MDEG_C
        <= temperature
        <= _TANDEM_MAXIMUM_TEMPERATURE_MDEG_C
    ):
        raise EvidenceInvalid("tandem temperature is outside provider provenance")
    if not state.temperature_valid_seen:
        state.temperature_valid_seen = True
        state.temperature_first_valid_ordinal = state.frame_index
    state.temperature_valid_count += 1
    state.temperature_minimum_valid_mdeg_c = (
        temperature
        if state.temperature_minimum_valid_mdeg_c is None
        else min(state.temperature_minimum_valid_mdeg_c, temperature)
    )
    state.temperature_maximum_valid_mdeg_c = (
        temperature
        if state.temperature_maximum_valid_mdeg_c is None
        else max(state.temperature_maximum_valid_mdeg_c, temperature)
    )


def _require_tandem_temperature_session(
    state: _CaptureState, *, frame_count: int
) -> None:
    if (
        frame_count != _TANDEM_BATCH_FRAMES
        or state.frame_index != frame_count
        or state.temperature_valid_count < 1
        or state.temperature_valid_count + state.temperature_omission_count
        != frame_count
        or state.temperature_first_valid_ordinal != state.temperature_omission_count
        or state.temperature_minimum_valid_mdeg_c is None
        or state.temperature_maximum_valid_mdeg_c is None
    ):
        raise EvidenceInvalid(
            "tandem batch lacks one complete valid temperature session"
        )


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
    expected_initial_gain_db: int,
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
    if (
        metadata.version != 5
        or metadata.header_bytes != _TANDEM_METADATA_HEADER_BYTES
        or metadata.features & _TANDEM_REQUIRED_METADATA_FEATURES
        != _TANDEM_REQUIRED_METADATA_FEATURES
        or metadata.features & ~_TANDEM_KNOWN_METADATA_FEATURES
        or metadata.sample_format != 1
    ):
        raise EvidenceInvalid("tandem metadata v5 wire provenance changed")
    if metadata.flags & _TANDEM_REQUIRED_METADATA_FLAGS != (
        _TANDEM_REQUIRED_METADATA_FLAGS
    ):
        raise EvidenceInvalid("tandem metadata lacks required valid flags")
    if metadata.flags & ~_TANDEM_KNOWN_METADATA_FLAGS:
        raise EvidenceInvalid("tandem metadata contains unrecognized flags")
    if metadata.flags & TANDEM_UNSAFE_FLAGS:
        raise EvidenceInvalid(
            "tandem metadata reports unsafe flags "
            f"0x{metadata.flags & TANDEM_UNSAFE_FLAGS:08x}"
        )
    if metadata.observation_overflow_count or metadata.event_overflow_count:
        raise EvidenceInvalid("tandem transient metadata capacity overflowed")
    if metadata.observation_capacity != 64 or metadata.event_capacity != 64:
        raise EvidenceInvalid("tandem transient metadata capacity changed")
    maximum_observations = (
        capture.frame_samples // (capture.frame_samples // 4) + 1
    )
    if not 1 <= metadata.observation_count <= maximum_observations:
        raise EvidenceInvalid(
            "tandem transient observation count exceeds the overlap-safe bound"
        )
    maximum_events = maximum_tandem_events_per_frame(
        mode=TandemMode.AUTO,
        samples_per_channel=capture.frame_samples,
        power_measurement_samples=quality.tandem_power_measurement_samples,
        cooldown_periods=quality.tandem_cooldown_periods,
    )
    if (
        metadata.event_count != len(metadata.gain_events)
        or not 0 <= metadata.event_count <= maximum_events
    ):
        raise EvidenceInvalid(
            "tandem transient event count exceeds the configured physics bound"
        )
    if metadata.tandem_state is not TandemState.ARMED_AUTO:
        raise EvidenceInvalid("tandem controller left AUTO during transient capture")
    if metadata.gain_table_id is not expected_tandem_gain_table(
        quality.center_frequency_hz
    ):
        raise EvidenceInvalid("tandem transient selected the wrong gain table")
    if (
        metadata.minimum_gain_db != 0
        or metadata.maximum_gain_db != 62
        or metadata.initial_gain_db != expected_initial_gain_db
    ):
        raise EvidenceInvalid("tandem transient metadata differs from its request")
    expected_threshold_provenance = (
        quality.tandem_low_power_threshold
        | quality.tandem_large_lmt_overload_threshold << 8
        | quality.tandem_large_adc_overload_threshold << 16
        | quality.tandem_small_adc_overload_threshold << 24
    )
    if metadata.threshold_provenance != expected_threshold_provenance:
        raise EvidenceInvalid(
            "tandem transient threshold provenance differs from its request"
        )
    if metadata.rx1_gain_index != metadata.rx2_gain_index:
        raise EvidenceInvalid("tandem transient metadata contains a torn endpoint")
    if metadata.first_sample_sequence + capture.frame_samples > _UINT64_MODULUS:
        raise EvidenceInvalid("tandem transient frame exceeds uint64 sample time")
    _observe_tandem_temperature(metadata, state=state)

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
            if event.sample_sequence < state.last_event.sample_sequence:
                raise EvidenceInvalid(
                    "tandem transient events are not globally sample ordered"
                )
            minimum_event_spacing = quality.tandem_power_measurement_samples * (
                quality.tandem_cooldown_periods + 1
            )
            if (
                event.sample_sequence - state.last_event.sample_sequence
                < minimum_event_spacing
            ):
                raise EvidenceInvalid(
                    "tandem transient gain events violate cooldown spacing"
                )
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
    expected_tandem_initial_gain_db: int | None = None,
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
        if not 0 < len(raw_metadata) <= _TANDEM_METADATA_CAPACITY_BYTES:
            raise EvidenceInvalid(
                "tandem transient raw metadata exceeds its retained-byte bound"
            )
        parsed = metadata_parser(raw_metadata)
        if parsed.header_bytes != len(raw_metadata):
            raise EvidenceInvalid(
                "tandem transient declared metadata bytes differ from sidecar"
            )
        continuity = _validate_tandem_metadata(
            parsed,
            raw_bytes=len(raw),
            quality=quality,
            capture=capture,
            state=state,
            gap_context=gap_context,
            expected_initial_gain_db=(
                int(quality.manual_gain_db)
                if expected_tandem_initial_gain_db is None
                else expected_tandem_initial_gain_db
            ),
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
    return _DeferredFrame(
        record=record,
        raw=raw,
        metadata=parsed,
        raw_metadata=raw_metadata,
    )


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
        self._queue: queue.Queue[_DeferredFrame] = queue.Queue(
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

    def _offer(self, item: _DeferredFrame) -> bool:
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


class _TandemBatchWorker:
    """Replay exactly one 64-frame metadata batch on one bounded thread."""

    def __init__(self, acquire: Callable[[], _DeferredFrame]) -> None:
        self._acquire = acquire
        self._queue: queue.Queue[_DeferredFrame | BaseException] = queue.Queue(
            maxsize=_TANDEM_CAPTURE_QUEUE_FRAMES
        )
        self._stop = threading.Event()
        self._first_refill_started = threading.Event()
        self._first_refill_completed = threading.Event()
        self._finished = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="tandem-transient-batch-acquisition",
            daemon=True,
        )
        self._terminal_error_lock = threading.Lock()
        self._terminal_error: BaseException | None = None
        self._started = False
        self.produced_frames = 0
        self.consumed_frames = 0
        self.discarded_tail_frames = 0

    @property
    def queue_capacity_frames(self) -> int:
        return self._queue.maxsize

    @property
    def first_refill_in_flight(self) -> bool:
        return self._first_refill_started.is_set() and not (
            self._first_refill_completed.is_set()
        )

    @property
    def finished(self) -> bool:
        return self._finished.is_set()

    def start(self) -> None:
        self._thread.start()
        self._started = True
        if not self._first_refill_started.wait(_CAPTURE_THREAD_WAIT_SECONDS):
            raise EvidenceInvalid(
                "tandem batch worker did not initiate its first refill"
            )

    def _offer(self, item: _DeferredFrame | BaseException) -> bool:
        while not self._stop.is_set():
            try:
                self._queue.put(item, timeout=0.05)
                return True
            except queue.Full:
                continue
        return False

    def _claim_terminal_error(self) -> BaseException | None:
        with self._terminal_error_lock:
            error = self._terminal_error
            self._terminal_error = None
            return error

    def _run(self) -> None:
        try:
            for index in range(_TANDEM_BATCH_FRAMES):
                if self._stop.is_set():
                    return
                if index == 0:
                    self._first_refill_started.set()
                try:
                    frame = self._acquire()
                finally:
                    if index == 0:
                        self._first_refill_completed.set()
                self.produced_frames += 1
                if not self._offer(frame):
                    self.discarded_tail_frames += 1
                    return
        except BaseException as error:  # noqa: BLE001 - cross-thread propagation
            if not (
                self._stop.is_set()
                and isinstance(error, OSError)
                and error.errno == errno.EBADF
            ):
                with self._terminal_error_lock:
                    self._terminal_error = error
        finally:
            self._finished.set()

    def require_first_refill_in_flight(self) -> None:
        if self.first_refill_in_flight:
            return
        error = self._claim_terminal_error()
        if error is not None:
            raise error.with_traceback(error.__traceback__)
        raise EvidenceInvalid(
            "tandem metadata batch completed before a predeclared command target"
        )

    def take(self) -> _DeferredFrame:
        deadline = time.monotonic() + _CAPTURE_THREAD_WAIT_SECONDS
        while True:
            error = self._claim_terminal_error()
            if error is not None:
                raise error.with_traceback(error.__traceback__)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise EvidenceInvalid(
                    "tandem batch worker returned no cached frame before timeout"
                )
            try:
                item = self._queue.get(timeout=min(0.05, remaining))
            except queue.Empty:
                if self._finished.is_set():
                    error = self._claim_terminal_error()
                    if error is not None:
                        raise error.with_traceback(error.__traceback__)
                continue
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
            raise EvidenceInvalid("tandem batch worker did not stop")
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
            self.discarded_tail_frames += 1
        error = self._claim_terminal_error()
        if error is not None:
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


def _tandem_memory_ledger() -> dict[str, Any]:
    """Return the frozen worst-case host/device resident-byte accounting."""

    components = {
        "core_batch_cache_bytes": _TANDEM_BATCH_CACHE_BYTES,
        "ordinary_libiio_c_buffer_bytes": _TANDEM_FRAME_IQ_BYTES,
        "maximum_python_retained_raw_bytes": _TANDEM_MAXIMUM_PYTHON_RAW_BYTES,
        "maximum_python_retained_raw_metadata_bytes": (
            _TANDEM_MAXIMUM_PYTHON_RAW_METADATA_BYTES
        ),
        "transient_buffer_read_bytearray_bytes": _TANDEM_FRAME_IQ_BYTES,
        "ctypes_refill_scratch_bytes": _TANDEM_METADATA_CAPACITY_BYTES,
        "returned_metadata_bytes": _TANDEM_METADATA_CAPACITY_BYTES,
        "parsed_evidence_reservation_bytes": (
            _TANDEM_PARSED_EVIDENCE_RESERVATION_BYTES
        ),
        "device_k8_dma_reservation_bytes": (
            _TANDEM_KERNEL_BUFFERS * _TANDEM_FRAME_IQ_BYTES
        ),
    }
    calculated = sum(components.values())
    if calculated != _TANDEM_AGGREGATE_RESIDENT_BYTES:
        raise EvidenceInvalid("tandem resident-memory ledger calculation changed")
    post_close_materialization = sum(
        (
            _TANDEM_MAXIMUM_PYTHON_RAW_BYTES,
            _TANDEM_MAXIMUM_PYTHON_RAW_METADATA_BYTES,
            _TANDEM_PARSED_EVIDENCE_RESERVATION_BYTES,
            _TANDEM_POST_CLOSE_FFT_WORKSPACE_BYTES,
        )
    )
    return {
        **components,
        "post_close_fft_workspace_bytes": _TANDEM_POST_CLOSE_FFT_WORKSPACE_BYTES,
        "capture_phase_envelope_bytes": calculated,
        "post_close_materialization_envelope_bytes": post_close_materialization,
        "maximum_phase_envelope_bytes": max(calculated, post_close_materialization),
        "aggregate_resident_bytes": calculated,
        "maximum_aggregate_bytes": _TANDEM_MAXIMUM_AGGREGATE_BYTES,
        "within_cap": calculated <= _TANDEM_MAXIMUM_AGGREGATE_BYTES,
        "measured_finished_mode_and_parsed_metadata_bytes": None,
        "measured_evidence_within_reservation": None,
        "canonical_evidence_projection_method": (
            _TANDEM_EVIDENCE_PROJECTION_METHOD
        ),
        "canonical_evidence_projection_bytes": None,
        "canonical_evidence_projection_sha256": None,
        "accounting_scope": (
            "campaign-owned conservative payload envelope; excludes interpreter, "
            "library and allocator state, thread stacks, JSON serialization, and "
            "page cache"
        ),
        "phase_overlap_policy": (
            "core batch cache and K8 DMA capture precede normal close; the 8MiB "
            "FFT workspace is counted only in the post-close materialization "
            "envelope, and the larger conservative capture envelope governs"
        ),
        "python_raw_ownership": (
            "retained list, queue4, and producer own disjoint frames from the "
            "same exact 64-frame batch"
        ),
    }


def _recursive_resident_bytes(value: Any, seen: set[int] | None = None) -> int:
    """Measure one bounded campaign-owned Python object graph without aliases."""

    visited = set() if seen is None else seen
    identity = id(value)
    if identity in visited:
        return 0
    visited.add(identity)
    total = sys.getsizeof(value)
    if isinstance(value, Mapping):
        return total + sum(
            _recursive_resident_bytes(key, visited)
            + _recursive_resident_bytes(item, visited)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set, frozenset)):
        return total + sum(_recursive_resident_bytes(item, visited) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        return total + sum(
            _recursive_resident_bytes(getattr(value, item.name), visited)
            for item in dataclass_fields(value)
        )
    return total


def _canonical_tandem_evidence_bytes(
    record: Mapping[str, Any],
    parsed_metadata: Sequence[TandemFrameMetadata],
) -> bytes:
    """Encode the durable alias-independent evidence projection."""

    mode_projection = dict(record)
    acquisition_projection = dict(record["acquisition"])
    ledger_projection = dict(acquisition_projection["memory_ledger"])
    ledger_projection.update(
        {
            "measured_finished_mode_and_parsed_metadata_bytes": 0,
            "measured_evidence_within_reservation": True,
            "canonical_evidence_projection_bytes": 0,
            "canonical_evidence_projection_sha256": "0" * 64,
        }
    )
    acquisition_projection["memory_ledger"] = ledger_projection
    mode_projection["acquisition"] = acquisition_projection
    projection = {
        "schema": _TANDEM_EVIDENCE_PROJECTION_SCHEMA,
        "mode": mode_projection,
        "reparsed_metadata": [_metadata_dict(item) for item in parsed_metadata],
    }
    return json.dumps(
        projection,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _attest_tandem_evidence_reservation(
    record: Mapping[str, Any], frames: Sequence[_DeferredFrame]
) -> None:
    ledger = record["acquisition"]["memory_ledger"]
    reservation = ledger.get("parsed_evidence_reservation_bytes")
    if (
        type(reservation) is not int
        or reservation != _TANDEM_PARSED_EVIDENCE_RESERVATION_BYTES
    ):
        raise EvidenceInvalid("tandem parsed-evidence reservation was substituted")
    if len(frames) != _TANDEM_BATCH_FRAMES or any(
        frame.metadata is None for frame in frames
    ):
        raise EvidenceInvalid(
            "tandem evidence measurement lacks the exact parsed batch"
        )
    parsed_metadata = tuple(frame.metadata for frame in frames)
    if ledger.get("canonical_evidence_projection_method") != (
        _TANDEM_EVIDENCE_PROJECTION_METHOD
    ):
        raise EvidenceInvalid("tandem canonical evidence method was substituted")
    canonical = _canonical_tandem_evidence_bytes(record, parsed_metadata)
    ledger["canonical_evidence_projection_bytes"] = len(canonical)
    ledger["canonical_evidence_projection_sha256"] = hashlib.sha256(
        canonical
    ).hexdigest()
    measured = 0
    for _ in range(4):
        ledger["measured_finished_mode_and_parsed_metadata_bytes"] = measured
        ledger["measured_evidence_within_reservation"] = (
            measured <= reservation
        )
        updated = _recursive_resident_bytes((record, parsed_metadata))
        if updated == measured:
            break
        measured = updated
    else:
        raise EvidenceInvalid("tandem evidence measurement did not converge")
    if not len(canonical) <= measured <= reservation:
        raise EvidenceInvalid(
            "tandem canonical/live evidence sizes violate the retained "
            "evidence reservation"
        )


def _schedule_timestamp(clock_ns: Callable[[], int], *, name: str) -> int:
    value = clock_ns()
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvidenceInvalid(f"tandem {name} is not a monotonic timestamp")
    return value


def _new_batch_command_diagnostics(
    *, command_id: str, requested_level_db: float, target_frames: int, s0_raw: int
) -> dict[str, Any]:
    target_samples = target_frames * _TANDEM_FRAME_SAMPLES
    return {
        "status": "pending",
        "qualified": False,
        "current_stage": "created",
        "failure_stage": None,
        "failure_error": None,
        "command_id": command_id,
        "requested_level_db": requested_level_db,
        "applied_level_db": None,
        "target": {
            "s0_raw": s0_raw,
            "offset_frames": target_frames,
            "offset_samples": target_samples,
            "target_raw": (s0_raw + target_samples) % _UINT32_MODULUS,
            "last_below_raw": None,
            "raw_a_prewrite": None,
            "poll_read_count": 0,
            "poll_observations": [],
            "total_requested_sleep_samples": 0,
            "overshoot_samples": None,
            "overshoot_limit_samples": _TANDEM_MAX_TARGET_OVERSHOOT_SAMPLES,
        },
        "worker_in_flight_observations": [],
        "tx1_mute_assurance": {
            phase: {
                "attempt_count": 0,
                "host_before_ns": None,
                "host_after_ns": None,
                "observed_level_db": None,
                "passed": False,
                "error": None,
            }
            for phase in ("pre", "post")
        },
        "write_ack": {
            "operation": "one_exact_tx2_hardwaregain_write",
            "attempt_count": 0,
            "host_before_ns": None,
            "host_after_ns": None,
            "host_jitter_ns": None,
            "acknowledged": False,
            "error": None,
        },
        "counter_reads": [],
        "raw_bracket": {
            "register_address": "0x800000b8",
            "counter_width_bits": 32,
            "counter_source": "coherent FPGA RX sample counter low word",
            "raw_a_prewrite": None,
            "raw_post_write_initial": None,
            "raw_b_first_advance": None,
            "raw_c_causal_advance": None,
            "initial_from_a_samples": None,
            "b_from_initial_samples": None,
            "c_from_b_samples": None,
            "post_write_read_count": 0,
            "causal_uncertainty_samples": None,
            "causal_uncertainty_limit_samples": None,
            "worker_in_flight_at_command": False,
        },
        "deferred_tx2_readback": {
            "operation": "one_exact_tx2_hardwaregain_read",
            "attempt_count": 0,
            "host_before_ns": None,
            "host_after_ns": None,
            "observed_level_db": None,
            "tolerance_db": None,
            "passed": False,
            "error": None,
        },
    }


def _mark_batch_command_failure(
    diagnostics: dict[str, Any], error: BaseException
) -> None:
    if diagnostics.get("status") == "complete":
        return
    diagnostics["status"] = "failed"
    diagnostics["qualified"] = False
    diagnostics["failure_stage"] = str(diagnostics.get("current_stage", "unknown"))
    diagnostics["failure_error"] = _exception_text(error)


def _schedule_tandem_batch_command(
    radio: TransientRadioTransport,
    worker: _TandemBatchWorker,
    *,
    command_id: str,
    requested_level_db: float,
    target_frames: int,
    s0_raw: int,
    diagnostics: dict[str, Any],
    check_deadline: Callable[[], None],
    clock_ns: Callable[[], int],
    sleep: Callable[[float], None],
    sample_rate_hz: int,
    max_host_jitter_ns: int,
    max_sample_uncertainty: int,
    readback_tolerance_db: float,
) -> StimulusCommand:
    """Apply one exact TX2 write at an S0-relative target during the refill."""

    target = diagnostics["target"]
    raw_bracket = diagnostics["raw_bracket"]
    counter_reads = diagnostics["counter_reads"]

    def set_stage(value: str) -> None:
        diagnostics["current_stage"] = value

    def record_worker(stage: str) -> None:
        diagnostics["worker_in_flight_observations"].append(
            {
                "stage": stage,
                "first_refill_in_flight": worker.first_refill_in_flight,
            }
        )

    def read_counter(role: str) -> int:
        observation: dict[str, Any] = {
            "ordinal": len(counter_reads),
            "role": role,
            "host_before_ns": _schedule_timestamp(
                clock_ns, name=f"{command_id} {role} read start"
            ),
            "host_after_ns": None,
            "raw": None,
            "error": None,
        }
        counter_reads.append(observation)
        try:
            observed = _strict_low32_counter(radio.read_rx_sample_counter_low32())
        except BaseException as error:
            observation["host_after_ns"] = _schedule_timestamp(
                clock_ns, name=f"{command_id} {role} failed read completion"
            )
            observation["error"] = _exception_text(error)
            raise
        observation["host_after_ns"] = _schedule_timestamp(
            clock_ns, name=f"{command_id} {role} read completion"
        )
        observation["raw"] = observed
        if observation["host_after_ns"] < observation["host_before_ns"]:
            raise EvidenceInvalid(
                f"command {command_id!r} counter read clock moved backward"
            )
        return observed

    def attest_tx1(phase: str) -> None:
        evidence = diagnostics["tx1_mute_assurance"][phase]
        evidence["attempt_count"] = 1
        evidence["host_before_ns"] = _schedule_timestamp(
            clock_ns, name=f"{command_id} TX1 {phase} mute start"
        )
        try:
            observed = float(radio.attest_tx1_muted())
        except BaseException as error:
            evidence["host_after_ns"] = _schedule_timestamp(
                clock_ns, name=f"{command_id} TX1 {phase} failed completion"
            )
            evidence["error"] = _exception_text(error)
            raise
        evidence["host_after_ns"] = _schedule_timestamp(
            clock_ns, name=f"{command_id} TX1 {phase} mute completion"
        )
        evidence["observed_level_db"] = observed
        if (
            not math.isfinite(observed)
            or abs(observed - TX_MUTE_DB) > 0.26
            or evidence["host_after_ns"] < evidence["host_before_ns"]
        ):
            raise EvidenceInvalid(
                f"command {command_id!r} TX1 {phase} mute assurance failed"
            )
        evidence["passed"] = True

    try:
        if diagnostics.get("command_id") != command_id or (
            diagnostics.get("requested_level_db") != requested_level_db
        ):
            raise EvidenceInvalid("tandem command diagnostics identity changed")
        target_samples = target_frames * _TANDEM_FRAME_SAMPLES
        if (
            target.get("s0_raw") != s0_raw
            or target.get("offset_frames") != target_frames
            or target.get("offset_samples") != target_samples
            or target.get("target_raw")
            != (s0_raw + target_samples) % _UINT32_MODULUS
        ):
            raise EvidenceInvalid("tandem command diagnostic target changed")
        if not 0 < target_samples < _UINT32_MODULUS // 2:
            raise EvidenceInvalid(f"command {command_id!r} target is ambiguous")

        set_stage("pre_tx1_mute_assurance")
        worker.require_first_refill_in_flight()
        record_worker("pre_tx1_mute_assurance")
        attest_tx1("pre")

        set_stage("target_poll")
        last_below_raw: int | None = None
        raw_a: int | None = None
        overshoot: int | None = None
        for _ in range(_TANDEM_TARGET_MAX_POLL_READS):
            check_deadline()
            worker.require_first_refill_in_flight()
            current = read_counter("target_poll")
            advance = (current - s0_raw) % _UINT32_MODULUS
            if advance >= _UINT32_MODULUS // 2:
                raise EvidenceInvalid(
                    f"command {command_id!r} target poll crossed ambiguous wrap"
                )
            remaining = target_samples - advance
            if remaining > 0:
                last_below_raw = current
                if remaining > _TANDEM_TARGET_COARSE_GUARD_SAMPLES:
                    phase = "coarse_sleep"
                    sleep_samples = remaining - _TANDEM_TARGET_COARSE_GUARD_SAMPLES
                elif remaining > 2 * _TANDEM_TARGET_FINE_SLEEP_SAMPLES:
                    phase = "fine_sleep"
                    sleep_samples = _TANDEM_TARGET_FINE_SLEEP_SAMPLES
                else:
                    phase = "tail_poll"
                    sleep_samples = 0
                target["poll_observations"].append(
                    {
                        "raw": current,
                        "advance_samples": advance,
                        "remaining_samples": remaining,
                        "phase": phase,
                        "requested_sleep_samples": sleep_samples,
                    }
                )
                target["poll_read_count"] += 1
                target["last_below_raw"] = current
                if sleep_samples:
                    target["total_requested_sleep_samples"] += sleep_samples
                    sleep(sleep_samples / sample_rate_hz)
                    check_deadline()
                continue
            raw_a = current
            overshoot = advance - target_samples
            counter_reads[-1]["role"] = "raw_a_prewrite"
            target["poll_observations"].append(
                {
                    "raw": current,
                    "advance_samples": advance,
                    "remaining_samples": 0,
                    "phase": "target_reached",
                    "requested_sleep_samples": 0,
                }
            )
            target["poll_read_count"] += 1
            target["raw_a_prewrite"] = raw_a
            target["overshoot_samples"] = overshoot
            break
        if raw_a is None:
            raise EvidenceInvalid(
                f"command {command_id!r} exceeded its target-poll read budget"
            )
        if last_below_raw is None:
            raise EvidenceInvalid(
                f"command {command_id!r} target lacks a last-below counter read"
            )
        set_stage("target_overshoot_validation")
        if overshoot is None or overshoot > _TANDEM_MAX_TARGET_OVERSHOOT_SAMPLES:
            raise EvidenceInvalid(
                f"command {command_id!r} target overshoot {overshoot} exceeds "
                f"{_TANDEM_MAX_TARGET_OVERSHOOT_SAMPLES} samples"
            )

        set_stage("exact_tx2_write")
        worker.require_first_refill_in_flight()
        record_worker("exact_tx2_write")
        raw_bracket["worker_in_flight_at_command"] = True
        write_ack = diagnostics["write_ack"]
        write_ack["attempt_count"] = 1
        write_ack["host_before_ns"] = _schedule_timestamp(
            clock_ns, name=f"{command_id} exact TX2 write start"
        )
        try:
            radio.write_tx2_gain_exact(requested_level_db)
        except BaseException as error:
            write_ack["host_after_ns"] = _schedule_timestamp(
                clock_ns, name=f"{command_id} failed exact TX2 write completion"
            )
            write_ack["host_jitter_ns"] = (
                write_ack["host_after_ns"] - write_ack["host_before_ns"]
            )
            write_ack["error"] = _exception_text(error)
            raise
        write_ack["host_after_ns"] = _schedule_timestamp(
            clock_ns, name=f"{command_id} exact TX2 write acknowledgement"
        )
        write_ack["host_jitter_ns"] = (
            write_ack["host_after_ns"] - write_ack["host_before_ns"]
        )
        write_ack["acknowledged"] = True

        set_stage("raw_post_write_initial")
        raw_initial = read_counter("raw_post_write_initial")
        raw_bracket["raw_a_prewrite"] = raw_a
        raw_bracket["raw_post_write_initial"] = raw_initial
        initial_delta = (raw_initial - raw_a) % _UINT32_MODULUS
        raw_bracket["initial_from_a_samples"] = initial_delta
        raw_bracket["post_write_read_count"] = 1
        raw_b: int | None = None
        raw_c: int | None = None
        b_delta: int | None = None
        c_delta: int | None = None
        uncertainty: int | None = None
        set_stage("causal_counter_advances")
        for _ in range(8):
            current = read_counter("post_write_advance_candidate")
            raw_bracket["post_write_read_count"] += 1
            if raw_b is None and current != raw_initial:
                raw_b = current
                counter_reads[-1]["role"] = "raw_b_first_advance"
                b_delta = (raw_b - raw_initial) % _UINT32_MODULUS
                raw_bracket["raw_b_first_advance"] = raw_b
                raw_bracket["b_from_initial_samples"] = b_delta
            elif raw_b is not None and current != raw_b:
                raw_c = current
                counter_reads[-1]["role"] = "raw_c_causal_advance"
                c_delta = (raw_c - raw_b) % _UINT32_MODULUS
                uncertainty = initial_delta + b_delta + c_delta
                raw_bracket["raw_c_causal_advance"] = raw_c
                raw_bracket["c_from_b_samples"] = c_delta
                raw_bracket["causal_uncertainty_samples"] = uncertainty
                raw_bracket["causal_uncertainty_limit_samples"] = (
                    max_sample_uncertainty
                )
                break
        if raw_b is None or raw_c is None:
            raise EvidenceInvalid(
                f"command {command_id!r} did not observe causal B and C advances"
            )
        assert b_delta is not None and c_delta is not None and uncertainty is not None

        set_stage("deferred_tx2_readback")
        readback = diagnostics["deferred_tx2_readback"]
        readback["tolerance_db"] = readback_tolerance_db
        readback["attempt_count"] = 1
        readback["host_before_ns"] = _schedule_timestamp(
            clock_ns, name=f"{command_id} deferred TX2 readback start"
        )
        try:
            applied_level_db = float(radio.read_tx2_gain())
        except BaseException as error:
            readback["host_after_ns"] = _schedule_timestamp(
                clock_ns, name=f"{command_id} failed deferred readback completion"
            )
            readback["error"] = _exception_text(error)
            raise
        readback["host_after_ns"] = _schedule_timestamp(
            clock_ns, name=f"{command_id} deferred TX2 readback completion"
        )
        readback["observed_level_db"] = applied_level_db
        if (
            readback["host_after_ns"] < readback["host_before_ns"]
            or not math.isfinite(applied_level_db)
            or abs(applied_level_db - requested_level_db) > readback_tolerance_db
        ):
            raise EvidenceInvalid(
                f"command {command_id!r} deferred TX2 readback differs from request"
            )
        readback["passed"] = True
        diagnostics["applied_level_db"] = applied_level_db

        set_stage("post_tx1_mute_assurance")
        attest_tx1("post")

        set_stage("schedule_validation")
        if initial_delta >= _UINT32_MODULUS // 2 or not all(
            0 < value < _UINT32_MODULUS // 2 for value in (b_delta, c_delta)
        ):
            raise EvidenceInvalid(
                f"command {command_id!r} A-to-initial-to-B-to-C bracket is ambiguous"
            )
        if not 0 < uncertainty <= max_sample_uncertainty:
            raise EvidenceInvalid(
                f"command {command_id!r} causal uncertainty {uncertainty} exceeds "
                f"{max_sample_uncertainty} samples"
            )
        if (
            write_ack["host_after_ns"] < write_ack["host_before_ns"]
            or not 0 <= write_ack["host_jitter_ns"] <= max_host_jitter_ns
        ):
            raise EvidenceInvalid(
                f"command {command_id!r} exact write host bracket is invalid"
            )
        diagnostics["status"] = "complete"
        diagnostics["qualified"] = True
        diagnostics["current_stage"] = "complete"
        return StimulusCommand(
            command_id=command_id,
            requested_level_db=requested_level_db,
            applied_level_db=applied_level_db,
            host_before_ns=write_ack["host_before_ns"],
            host_after_ns=write_ack["host_after_ns"],
            sample_sequence_before=None,
            sample_sequence_after=None,
        )
    except BaseException as error:
        _mark_batch_command_failure(diagnostics, error)
        raise


def _bind_tandem_batch_command(
    frames: Sequence[_DeferredFrame],
    command: StimulusCommand,
    diagnostics: Mapping[str, Any],
) -> tuple[StimulusCommand, dict[str, Any]]:
    """Extend one low32 schedule against the exact retained batch."""

    if len(frames) != _TANDEM_BATCH_FRAMES:
        raise EvidenceInvalid("tandem command cannot bind an incomplete batch")
    first_start = int(frames[0].record["first_sample_sequence"])
    last_end = int(frames[-1].record["sample_end_exclusive"])
    target = diagnostics.get("target")
    raw_bracket = diagnostics.get("raw_bracket")
    if not isinstance(target, Mapping) or not isinstance(raw_bracket, Mapping):
        raise EvidenceInvalid("tandem command lacks raw schedule diagnostics")
    s0_raw = _strict_low32_counter(target.get("s0_raw"))
    s0 = _extend_low32_near(s0_raw, reference=first_start)
    target_samples = int(target.get("offset_samples", -1))
    target_sample = s0 + target_samples
    if not first_start <= target_sample < last_end:
        raise EvidenceInvalid("tandem command target lies outside its retained batch")

    raw_p = _strict_low32_counter(target.get("last_below_raw"))
    raw_a = _strict_low32_counter(target.get("raw_a_prewrite"))
    raw_initial = _strict_low32_counter(raw_bracket.get("raw_post_write_initial"))
    raw_b = _strict_low32_counter(raw_bracket.get("raw_b_first_advance"))
    raw_c = _strict_low32_counter(raw_bracket.get("raw_c_causal_advance"))
    p_delta = (raw_p - s0_raw) % _UINT32_MODULUS
    a_delta = (raw_a - s0_raw) % _UINT32_MODULUS
    initial_delta = (raw_initial - raw_a) % _UINT32_MODULUS
    b_delta = (raw_b - raw_initial) % _UINT32_MODULUS
    c_delta = (raw_c - raw_b) % _UINT32_MODULUS
    if any(
        value >= _UINT32_MODULUS // 2
        for value in (p_delta, a_delta, initial_delta)
    ) or any(
        not 0 < value < _UINT32_MODULUS // 2 for value in (b_delta, c_delta)
    ):
        raise EvidenceInvalid("tandem command counter extension is ambiguous")
    extended_p = s0 + p_delta
    extended_a = s0 + a_delta
    extended_initial = extended_a + initial_delta
    extended_b = extended_initial + b_delta
    extended_c = extended_b + c_delta
    overshoot = extended_a - target_sample
    uncertainty = extended_c - extended_a
    if not extended_p < target_sample <= extended_a:
        raise EvidenceInvalid("tandem last-below/target/A ordering is invalid")
    if not 0 < extended_a - extended_p < _UINT32_MODULUS // 2:
        raise EvidenceInvalid("tandem last-below to A advance is ambiguous")
    if not 0 <= overshoot <= _TANDEM_MAX_TARGET_OVERSHOOT_SAMPLES:
        raise EvidenceInvalid("tandem posthoc target overshoot exceeds policy")
    uncertainty_limit = raw_bracket.get("causal_uncertainty_limit_samples")
    if (
        isinstance(uncertainty_limit, bool)
        or not isinstance(uncertainty_limit, int)
        or not 0 < uncertainty <= uncertainty_limit
    ):
        raise EvidenceInvalid("tandem posthoc causal bracket exceeds policy")
    if (
        target.get("target_raw") != target_sample % _UINT32_MODULUS
        or target.get("overshoot_samples") != overshoot
        or target.get("overshoot_limit_samples")
        != _TANDEM_MAX_TARGET_OVERSHOOT_SAMPLES
        or raw_bracket.get("raw_a_prewrite") != raw_a
        or raw_bracket.get("initial_from_a_samples") != initial_delta
        or raw_bracket.get("b_from_initial_samples") != b_delta
        or raw_bracket.get("c_from_b_samples") != c_delta
        or raw_bracket.get("causal_uncertainty_samples") != uncertainty
        or raw_bracket.get("worker_in_flight_at_command") is not True
    ):
        raise EvidenceInvalid("tandem raw and extended command schedules disagree")
    bracketed = replace(
        command,
        sample_sequence_before=extended_a,
        sample_sequence_after=extended_c,
    )
    return bracketed, {
        "register_address": "0x800000b8",
        "counter_width_bits": 32,
        "counter_source": "coherent FPGA RX sample counter low word",
        "first_batch_sample": first_start,
        "last_batch_sample_exclusive": last_end,
        "post_open_s0_raw": s0_raw,
        "post_open_s0_sample": s0,
        "target_offset_frames": target.get("offset_frames"),
        "target_offset_samples": target_samples,
        "target_raw": target.get("target_raw"),
        "target_sample": target_sample,
        "last_below_raw": raw_p,
        "last_below_sample": extended_p,
        "raw_a_prewrite": raw_a,
        "a_prewrite_sample": extended_a,
        "raw_post_write_initial": raw_initial,
        "post_write_initial_sample": extended_initial,
        "raw_b_first_advance": raw_b,
        "b_first_advance_sample": extended_b,
        "raw_c_causal_advance": raw_c,
        "c_causal_advance_sample": extended_c,
        "target_overshoot_samples": overshoot,
        "target_overshoot_limit_samples": _TANDEM_MAX_TARGET_OVERSHOOT_SAMPLES,
        "causal_uncertainty_samples": uncertainty,
        "causal_uncertainty_limit_samples": uncertainty_limit,
        "command_interval": "[A,C)",
    }


_TANDEM_PARTITION_PHASES = (
    "fully_pre_attack",
    "attack_bracket",
    "fully_post_attack_pre_release",
    "release_bracket",
    "fully_post_release",
)

_TANDEM_WEAK_PARTITION_PHASES = (
    "fully_pre_first",
    "first_command_bracket",
    "fully_between_commands",
    "second_command_bracket",
    "fully_post_second",
)


def _partition_tandem_batch(
    frames: Sequence[_DeferredFrame],
    *,
    attack: StimulusCommand,
    release: StimulusCommand,
) -> dict[str, Any]:
    """Classify every retained frame into the five ordered transient regions."""

    attack_lower = attack.sample_sequence_before
    attack_upper = attack.sample_sequence_after
    release_lower = release.sample_sequence_before
    release_upper = release.sample_sequence_after
    if None in (attack_lower, attack_upper, release_lower, release_upper):
        raise EvidenceInvalid("tandem partition commands lack hardware brackets")
    assert attack_lower is not None and attack_upper is not None
    assert release_lower is not None and release_upper is not None
    if not attack_lower < attack_upper <= release_lower < release_upper:
        raise EvidenceInvalid("tandem attack/release command brackets overlap")

    phase_by_frame: list[str] = []
    groups: dict[str, list[int]] = {name: [] for name in _TANDEM_PARTITION_PHASES}
    for frame in frames:
        start = int(frame.record["first_sample_sequence"])
        end = int(frame.record["sample_end_exclusive"])
        if end <= attack_lower:
            phase = "fully_pre_attack"
        elif start < attack_upper and end > attack_lower:
            phase = "attack_bracket"
        elif start >= attack_upper and end <= release_lower:
            phase = "fully_post_attack_pre_release"
        elif start < release_upper and end > release_lower:
            phase = "release_bracket"
        elif start >= release_upper:
            phase = "fully_post_release"
        else:
            raise EvidenceInvalid(
                "tandem frame cannot be assigned to an exact command partition"
            )
        frame.record["batch_phase"] = phase
        frame.record["gap_context"] = phase
        continuity = frame.record.get("continuity")
        if isinstance(continuity, dict):
            continuity["gap_context"] = phase
        phase_by_frame.append(phase)
        groups[phase].append(int(frame.record["frame_index"]))

    phase_order = {name: index for index, name in enumerate(_TANDEM_PARTITION_PHASES)}
    if phase_by_frame != sorted(phase_by_frame, key=phase_order.__getitem__):
        raise EvidenceInvalid("tandem five-way frame partition is not ordered")
    required = {
        "fully_pre_attack": _TANDEM_REQUIRED_PARTITION_FRAMES,
        "fully_post_attack_pre_release": _TANDEM_REQUIRED_PARTITION_FRAMES,
        "fully_post_release": _TANDEM_REQUIRED_PARTITION_FRAMES,
    }
    for phase, minimum in required.items():
        if len(groups[phase]) < minimum:
            raise EvidenceInvalid(
                f"tandem partition {phase!r} has {len(groups[phase])} frames; "
                f"requires {minimum}"
            )
    if not groups["attack_bracket"] or not groups["release_bracket"]:
        raise EvidenceInvalid("tandem command bracket lacks a retained frame")

    # AUTO starts at the request maximum specifically to preclude an
    # unobserved low-power startup ramp before the attack.
    for frame in frames:
        if frame.record["batch_phase"] != "fully_pre_attack":
            continue
        metadata = frame.metadata
        if metadata is None:
            raise EvidenceInvalid("tandem pre-attack frame lacks metadata")
        if (
            metadata.tandem_transition_count != 0
            or metadata.gain_events
            or metadata.bench_gain_indices
            != (metadata.maximum_gain_index, metadata.maximum_gain_index)
        ):
            raise EvidenceInvalid(
                "tandem pre-attack AUTO evidence contains a startup transition"
            )

    return {
        "phase_order": list(_TANDEM_PARTITION_PHASES),
        "phase_by_frame": phase_by_frame,
        "groups": {
            name: {"count": len(indices), "frame_indices": indices}
            for name, indices in groups.items()
        },
        "minimum_required_fully_pre_attack_frames": (
            _TANDEM_REQUIRED_PARTITION_FRAMES
        ),
        "minimum_required_fully_post_attack_pre_release_frames": (
            _TANDEM_REQUIRED_PARTITION_FRAMES
        ),
        "minimum_required_fully_post_release_frames": (
            _TANDEM_REQUIRED_PARTITION_FRAMES
        ),
        "frame_count": len(frames),
    }


def _partition_weak_tandem_batch(
    frames: Sequence[_DeferredFrame],
    *,
    first: StimulusCommand,
    second: StimulusCommand,
) -> dict[str, Any]:
    """Classify the weak preflight without attack/release semantics."""

    first_lower = first.sample_sequence_before
    first_upper = first.sample_sequence_after
    second_lower = second.sample_sequence_before
    second_upper = second.sample_sequence_after
    if None in (first_lower, first_upper, second_lower, second_upper):
        raise EvidenceInvalid("weak dual-target commands lack hardware brackets")
    assert first_lower is not None and first_upper is not None
    assert second_lower is not None and second_upper is not None
    if not first_lower < first_upper <= second_lower < second_upper:
        raise EvidenceInvalid("weak dual-target command brackets overlap or reorder")

    phase_by_frame: list[str] = []
    groups: dict[str, list[int]] = {
        name: [] for name in _TANDEM_WEAK_PARTITION_PHASES
    }
    for frame in frames:
        start = int(frame.record["first_sample_sequence"])
        end = int(frame.record["sample_end_exclusive"])
        if end <= first_lower:
            phase = "fully_pre_first"
        elif start < first_upper and end > first_lower:
            phase = "first_command_bracket"
        elif start >= first_upper and end <= second_lower:
            phase = "fully_between_commands"
        elif start < second_upper and end > second_lower:
            phase = "second_command_bracket"
        elif start >= second_upper:
            phase = "fully_post_second"
        else:
            raise EvidenceInvalid(
                "weak dual-target frame cannot be assigned to an exact partition"
            )
        frame.record["batch_phase"] = phase
        frame.record["gap_context"] = phase
        continuity = frame.record.get("continuity")
        if isinstance(continuity, dict):
            continuity["gap_context"] = phase
        phase_by_frame.append(phase)
        groups[phase].append(int(frame.record["frame_index"]))

    order = {
        name: index for index, name in enumerate(_TANDEM_WEAK_PARTITION_PHASES)
    }
    if phase_by_frame != sorted(phase_by_frame, key=order.__getitem__):
        raise EvidenceInvalid("weak dual-target five-way partition is not ordered")
    required = {
        "fully_pre_first": _TANDEM_REQUIRED_PARTITION_FRAMES,
        "fully_between_commands": _TANDEM_REQUIRED_PARTITION_FRAMES,
        "fully_post_second": _TANDEM_REQUIRED_PARTITION_FRAMES,
    }
    for phase, minimum in required.items():
        if len(groups[phase]) < minimum:
            raise EvidenceInvalid(
                f"weak dual-target partition {phase!r} has "
                f"{len(groups[phase])} frames; requires {minimum}"
            )
    if not groups["first_command_bracket"] or not groups[
        "second_command_bracket"
    ]:
        raise EvidenceInvalid(
            "weak dual-target command bracket lacks a retained frame"
        )

    for index, frame in enumerate(frames):
        metadata = frame.metadata
        if metadata is None:
            raise EvidenceInvalid(
                f"weak dual-target frame {index} lacks tandem metadata"
            )
        if (
            metadata.tandem_state is not TandemState.ARMED_AUTO
            or metadata.tandem_fault_flags != 0
            or metadata.observation_overflow_count != 0
            or metadata.event_overflow_count != 0
            or metadata.tandem_transition_count != 0
            or metadata.event_count != 0
            or metadata.gain_events
            or metadata.rx1_gain_index != metadata.maximum_gain_index
            or metadata.rx2_gain_index != metadata.maximum_gain_index
            or metadata.bench_gain_indices
            != (metadata.maximum_gain_index, metadata.maximum_gain_index)
        ):
            raise EvidenceInvalid(
                "weak dual-target batch is not globally transition-free at the "
                "maximum-gain endpoint"
            )

    return {
        "phase_order": list(_TANDEM_WEAK_PARTITION_PHASES),
        "phase_by_frame": phase_by_frame,
        "groups": {
            name: {"count": len(indices), "frame_indices": indices}
            for name, indices in groups.items()
        },
        "minimum_required_fully_pre_first_frames": (
            _TANDEM_REQUIRED_PARTITION_FRAMES
        ),
        "minimum_required_fully_between_commands_frames": (
            _TANDEM_REQUIRED_PARTITION_FRAMES
        ),
        "minimum_required_fully_post_second_frames": (
            _TANDEM_REQUIRED_PARTITION_FRAMES
        ),
        "frame_count": len(frames),
    }


def _validate_exact_tandem_batch(frames: Sequence[_DeferredFrame]) -> None:
    if len(frames) != _TANDEM_BATCH_FRAMES:
        raise EvidenceInvalid("tandem batch did not retain exactly 64 frames")
    first = frames[0].metadata
    if first is None:
        raise EvidenceInvalid("tandem batch first frame lacks metadata")
    if first.buffer_sequence != 0:
        raise EvidenceInvalid("tandem batch first provider sequence is not zero")
    if first.stream_id <= 0 or first.ownership_epoch <= 0:
        raise EvidenceInvalid("tandem batch stream/ownership identity is invalid")
    for index, frame in enumerate(frames):
        metadata = frame.metadata
        if metadata is None:
            raise EvidenceInvalid(f"tandem batch frame {index} lacks metadata")
        if (
            int(frame.record["frame_index"]) != index
            or metadata.buffer_sequence != index
            or metadata.stream_id != first.stream_id
            or metadata.ownership_epoch != first.ownership_epoch
            or metadata.first_sample_sequence
            != first.first_sample_sequence + index * _TANDEM_FRAME_SAMPLES
            or int(frame.record["first_sample_sequence"])
            != metadata.first_sample_sequence
            or int(frame.record["sample_end_exclusive"])
            != metadata.first_sample_sequence + _TANDEM_FRAME_SAMPLES
            or len(frame.raw) != _TANDEM_FRAME_IQ_BYTES
        ):
            raise EvidenceInvalid(
                f"tandem batch frame {index} breaks exact stream continuity"
            )


def _checked_transient_output_relative_path(
    path: Path, *, output_root: Path, label: str
) -> Path:
    """Resolve a planned output without following an output-tree symlink."""

    lexical_root = output_root.absolute()
    lexical_path = path.absolute()
    try:
        relative = lexical_path.relative_to(lexical_root)
    except ValueError as error:
        raise EvidenceInvalid(
            f"{label} path escapes the configured output directory"
        ) from error
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise EvidenceInvalid(f"{label} relative path is not canonical")

    current = lexical_root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise EvidenceInvalid(
                f"{label} path contains a symlink: {relative.as_posix()}"
            )
    temporary = lexical_path.with_suffix(lexical_path.suffix + ".tmp")
    if temporary.is_symlink():
        raise EvidenceInvalid(
            f"{label} temporary path is a symlink: {relative.as_posix()}"
        )
    try:
        lexical_path.resolve(strict=False).relative_to(
            lexical_root.resolve(strict=False)
        )
    except ValueError as error:
        raise EvidenceInvalid(
            f"{label} resolved path escapes the configured output directory"
        ) from error
    return relative


def _safe_transient_serial_component(value: Any) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 128
        or value in {".", ".."}
        or not value[0].isalnum()
        or any(not (character.isalnum() or character in "._-") for character in value)
    ):
        raise ValueError("transient serial is not one safe path component")
    return value


def _preflight_transient_output_paths(
    output_root: Path,
    serial: Any,
    *,
    sidecar_inventory_policy: str = "empty",
) -> Path:
    """Create and recheck the exact report/sidecar tree before radio access."""

    selected_serial = _safe_transient_serial_component(serial)
    if output_root.is_symlink():
        raise EvidenceInvalid("transient configured output directory is a symlink")
    output_root.mkdir(parents=True, exist_ok=True)
    if output_root.is_symlink() or not output_root.is_dir():
        raise EvidenceInvalid("transient configured output directory is unsafe")

    serial_directory = output_root / selected_serial
    sidecar_directory = serial_directory / "transient-iq" / MODE_TANDEM / "batch"
    current = output_root
    for component in (
        selected_serial,
        "transient-iq",
        MODE_TANDEM,
        "batch",
    ):
        current /= component
        _checked_transient_output_relative_path(
            current,
            output_root=output_root,
            label="transient output directory",
        )
        current.mkdir(exist_ok=True)
        _checked_transient_output_relative_path(
            current,
            output_root=output_root,
            label="transient output directory",
        )
        if not current.is_dir():
            raise EvidenceInvalid("transient output component is not a directory")

    report_path = serial_directory / "tandem-agc-transient-report.json"
    _checked_transient_output_relative_path(
        report_path,
        output_root=output_root,
        label="transient atomic report",
    )
    allowed_sidecar_names: set[str] = set()
    for frame_index in range(_TANDEM_BATCH_FRAMES):
        for suffix in (".cs16", ".metadata.bin"):
            filename = f"frame-{frame_index:04d}{suffix}"
            allowed_sidecar_names.add(filename)
            _checked_transient_output_relative_path(
                sidecar_directory / filename,
                output_root=output_root,
                label="tandem sidecar",
            )
    if sidecar_inventory_policy not in {"empty", "partial", "complete"}:
        raise ValueError("unknown transient sidecar inventory policy")
    observed: set[str] = set()
    allowed_partial_names = {
        *allowed_sidecar_names,
        *(f"{name}.tmp" for name in allowed_sidecar_names),
    }
    for existing in sidecar_directory.iterdir():
        observed.add(existing.name)
        allowed = (
            allowed_partial_names
            if sidecar_inventory_policy == "partial"
            else allowed_sidecar_names
        )
        if (
            existing.name not in allowed
            or existing.is_symlink()
            or not existing.is_file()
        ):
            raise EvidenceInvalid(
                "tandem sidecar directory contains an unplanned artifact"
            )
    if sidecar_inventory_policy == "empty" and observed:
        raise EvidenceInvalid("tandem sidecar directory is not empty before RF")
    if (
        sidecar_inventory_policy == "complete"
        and observed != allowed_sidecar_names
    ):
        raise EvidenceInvalid(
            "tandem sidecar directory does not contain the exact 128-file inventory"
        )
    return report_path


def _prepare_tandem_artifact_inventory(
    frames: Sequence[_DeferredFrame],
    *,
    quality: TandemQualityOptions,
    iq_dir: Path,
    artifact_directory: str = MODE_TANDEM,
    artifact_policy: str = "mandatory_exact_release_sidecars",
) -> None:
    """Predeclare and validate the exact 128 sidecars before the first write."""

    if quality.output_dir.is_symlink():
        raise EvidenceInvalid(
            "tandem configured output directory must not be a symlink"
        )
    try:
        relative_directory = iq_dir.absolute().relative_to(
            quality.output_dir.absolute()
        )
    except ValueError as error:
        raise EvidenceInvalid(
            "tandem sidecar directory escapes the configured output directory"
        ) from error
    if (
        len(relative_directory.parts) != 4
        or relative_directory.parts[1:]
        != ("transient-iq", artifact_directory, "batch")
    ):
        raise EvidenceInvalid(
            "tandem sidecar directory does not use the exact serial-scoped layout"
        )

    planned_paths: set[str] = set()
    for frame in frames:
        frame_index = int(frame.record["frame_index"])
        if frame.metadata is None:
            raise EvidenceInvalid("tandem retained frame lacks metadata")
        if frame.raw_metadata is None:
            raise EvidenceInvalid("tandem retained frame lacks raw metadata")
        iq_path = iq_dir / f"frame-{frame_index:04d}.cs16"
        metadata_path = iq_dir / f"frame-{frame_index:04d}.metadata.bin"
        iq_relative = _checked_transient_output_relative_path(
            iq_path, output_root=quality.output_dir, label="tandem sidecar"
        )
        metadata_relative = _checked_transient_output_relative_path(
            metadata_path,
            output_root=quality.output_dir,
            label="tandem sidecar",
        )
        for relative in (iq_relative, metadata_relative):
            encoded = relative.as_posix()
            if encoded in planned_paths:
                raise EvidenceInvalid("tandem sidecar inventory contains a duplicate")
            planned_paths.add(encoded)
        frame.record.update(
            {
                "sha256": hashlib.sha256(frame.raw).hexdigest(),
                "iq_path": iq_relative.as_posix(),
                "raw_metadata_path": metadata_relative.as_posix(),
                "raw_metadata_bytes": len(frame.raw_metadata),
                "raw_metadata_sha256": hashlib.sha256(
                    frame.raw_metadata
                ).hexdigest(),
                "artifact_policy": artifact_policy,
                "artifact_write_status": {
                    "iq_write_completed": False,
                    "raw_metadata_write_completed": False,
                },
            }
        )
    if len(planned_paths) != 2 * _TANDEM_BATCH_FRAMES:
        raise EvidenceInvalid("tandem sidecar inventory is not exactly 128 files")


def _materialize_tandem_batch(
    frames: Sequence[_DeferredFrame],
    *,
    quality: TandemQualityOptions,
    check_deadline: Callable[[], None],
) -> None:
    """Hash, analyze, and persist every frame only after normal buffer close."""

    for frame in frames:
        check_deadline()
        if frame.metadata is None:
            raise EvidenceInvalid("tandem retained frame lacks metadata")
        if frame.raw_metadata is None:
            raise EvidenceInvalid("tandem retained frame lacks raw metadata")
        frame.record["metadata"] = _metadata_dict(frame.metadata)
        frame.record["analysis"] = dict(
            analyze_immediate_dual_rx(
                frame.raw,
                first_sample_sequence=int(frame.record["first_sample_sequence"]),
                sample_rate_hz=quality.sample_rate_hz,
                expected_tone_hz=quality.tone_hz,
                window_samples=_TANDEM_WINDOW_SAMPLES,
                min_tone_snr_db=quality.thresholds.min_tone_snr_db,
                max_clipping_fraction=quality.thresholds.max_clipping_fraction,
                max_phase_std_deg=quality.thresholds.max_phase_std_deg,
            )
        )
        iq_path = quality.output_dir / frame.record["iq_path"]
        metadata_path = quality.output_dir / frame.record["raw_metadata_path"]
        _atomic_bytes(iq_path, frame.raw)
        frame.record["artifact_write_status"]["iq_write_completed"] = True
        _atomic_bytes(metadata_path, frame.raw_metadata)
        frame.record["artifact_write_status"][
            "raw_metadata_write_completed"
        ] = True


def _tandem_artifact_manifest(frames: Sequence[_DeferredFrame]) -> dict[str, Any]:
    entries = [
        {
            "frame_index": int(frame.record["frame_index"]),
            "iq_path": frame.record["iq_path"],
            "iq_bytes": int(frame.record["iq_bytes"]),
            "iq_sha256": frame.record["sha256"],
            "raw_metadata_path": frame.record["raw_metadata_path"],
            "raw_metadata_bytes": int(frame.record["raw_metadata_bytes"]),
            "raw_metadata_sha256": frame.record["raw_metadata_sha256"],
            "write_status": frame.record["artifact_write_status"],
        }
        for frame in frames
    ]
    if len(entries) != _TANDEM_BATCH_FRAMES:
        raise EvidenceInvalid("tandem artifact manifest is not exactly 64 frames")
    encoded = json.dumps(
        entries, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return {
        "path_root": "quality.output_dir",
        "relative_directory": (
            f"{frames[0].record['iq_path'].rsplit('/', 1)[0]}"
        ),
        "frame_count": len(entries),
        "file_count": 2 * len(entries),
        "iq_total_bytes": sum(item["iq_bytes"] for item in entries),
        "raw_metadata_total_bytes": sum(
            item["raw_metadata_bytes"] for item in entries
        ),
        "completed_iq_files": sum(
            item["write_status"]["iq_write_completed"] for item in entries
        ),
        "completed_raw_metadata_files": sum(
            item["write_status"]["raw_metadata_write_completed"]
            for item in entries
        ),
        "write_complete": all(
            item["write_status"]["iq_write_completed"]
            and item["write_status"]["raw_metadata_write_completed"]
            for item in entries
        ),
        "entries": entries,
        "entries_canonical_json_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _require_tandem_batch_window_quality(
    frames: Sequence[_DeferredFrame],
    *,
    commands: Sequence[StimulusCommand],
) -> None:
    brackets: list[tuple[int, int]] = []
    for command in commands:
        if (
            command.sample_sequence_before is None
            or command.sample_sequence_after is None
        ):
            raise EvidenceInvalid("tandem quality gate command lacks a bracket")
        brackets.append(
            (command.sample_sequence_before, command.sample_sequence_after)
        )
    for frame in frames:
        for window in frame.record["analysis"]["windows"]:
            start = int(window["sample_start"])
            end = int(window["sample_end_exclusive"])
            intersects_command = any(
                start < upper and end > lower for lower, upper in brackets
            )
            if not intersects_command and window.get("quality_valid") is not True:
                raise EvidenceInvalid(
                    "tandem returned-IQ window outside both command brackets "
                    f"failed quality gates: {window.get('quality_reasons')!r}"
                )


def _analyze_tandem_frame_slice(
    frame: _DeferredFrame,
    *,
    offset_samples: int,
    sample_count: int,
    role: str,
    quality: TandemQualityOptions,
) -> dict[str, Any]:
    if (
        offset_samples < 0
        or sample_count <= 0
        or offset_samples + sample_count > _TANDEM_FRAME_SAMPLES
        or sample_count % _TANDEM_WINDOW_SAMPLES
    ):
        raise EvidenceInvalid(f"tandem {role} analysis slice is invalid")
    byte_start = offset_samples * 8
    byte_end = byte_start + sample_count * 8
    raw = frame.raw[byte_start:byte_end]
    first_sample = int(frame.record["first_sample_sequence"]) + offset_samples
    analysis = dict(
        analyze_immediate_dual_rx(
            raw,
            first_sample_sequence=first_sample,
            sample_rate_hz=quality.sample_rate_hz,
            expected_tone_hz=quality.tone_hz,
            window_samples=_TANDEM_WINDOW_SAMPLES,
            min_tone_snr_db=quality.thresholds.min_tone_snr_db,
            max_clipping_fraction=quality.thresholds.max_clipping_fraction,
            max_phase_std_deg=quality.thresholds.max_phase_std_deg,
        )
    )
    if analysis.get("quality_valid") is not True:
        raise EvidenceInvalid(f"tandem {role} returned-IQ slice failed quality gates")
    return {
        "role": role,
        "source_frame_index": int(frame.record["frame_index"]),
        "source_frame_sha256": frame.record.get("sha256"),
        "sample_offset_in_frame": offset_samples,
        "samples_per_channel": sample_count,
        "byte_offset_in_frame": byte_start,
        "byte_end_exclusive_in_frame": byte_end,
        "iq_bytes": len(raw),
        "first_sample_sequence": first_sample,
        "sample_end_exclusive": first_sample + sample_count,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "analysis": analysis,
    }


def _stable_tandem_partition_suffix(
    frames: Sequence[_DeferredFrame],
    *,
    frame_indices: Sequence[int],
    label: str,
    tolerance_db: float,
) -> dict[str, Any]:
    selected_indices = list(frame_indices[-_TANDEM_REQUIRED_PARTITION_FRAMES:])
    if len(selected_indices) != _TANDEM_REQUIRED_PARTITION_FRAMES:
        raise EvidenceInvalid(f"tandem {label} lacks an exact eight-frame suffix")
    selected = [frames[index] for index in selected_indices]
    metadata = [frame.metadata for frame in selected]
    if any(item is None for item in metadata):
        raise EvidenceInvalid(f"tandem {label} stable suffix lacks metadata")
    typed = [item for item in metadata if item is not None]
    transition_counts = {item.tandem_transition_count for item in typed}
    endpoints = {item.bench_gain_indices for item in typed}
    if (
        len(transition_counts) != 1
        or len(endpoints) != 1
        or any(item.gain_events for item in typed)
    ):
        raise EvidenceInvalid(
            f"tandem {label} eight-frame suffix is not event/endpoint stable"
        )
    windows = [
        window
        for frame in selected
        for window in frame.record["analysis"]["windows"]
    ]
    if not windows or any(window.get("quality_valid") is not True for window in windows):
        raise EvidenceInvalid(f"tandem {label} stable suffix failed RF quality")
    frame_channel_medians = [
        [
            float(
                statistics.median(
                    float(window["tone_dbfs"][channel])
                    for window in frame.record["analysis"]["windows"]
                )
            )
            for channel in (0, 1)
        ]
        for frame in selected
    ]
    suffix_channel_medians = [
        float(
            statistics.median(
                float(window["tone_dbfs"][channel]) for window in windows
            )
        )
        for channel in (0, 1)
    ]
    maximum_frame_median_deviations = [
        max(
            abs(row[channel] - suffix_channel_medians[channel])
            for row in frame_channel_medians
        )
        for channel in (0, 1)
    ]
    maximum_window_deviations = [
        max(
            abs(float(window["tone_dbfs"][channel]) - suffix_channel_medians[channel])
            for window in windows
        )
        for channel in (0, 1)
    ]
    if any(value > tolerance_db for value in maximum_window_deviations):
        raise EvidenceInvalid(
            f"tandem {label} stable suffix exceeds its RF tolerance"
        )
    endpoint = typed[-1].bench_gain_indices
    return {
        "frame_indices": selected_indices,
        "required_frame_count": _TANDEM_REQUIRED_PARTITION_FRAMES,
        "transition_count": typed[-1].tandem_transition_count,
        "bench_gain_indices": [endpoint[0], endpoint[1]],
        "event_count": 0,
        "rf_window_count": len(windows),
        "rf_quality_valid": True,
        "frame_channel_median_tone_dbfs": frame_channel_medians,
        "suffix_channel_median_tone_dbfs": suffix_channel_medians,
        "maximum_frame_median_deviation_db": maximum_frame_median_deviations,
        "maximum_frame_median_deviation_limit_db": tolerance_db,
        "maximum_window_deviation_db": maximum_window_deviations,
        "maximum_window_deviation_limit_db": tolerance_db,
    }


def _require_weak_tandem_batch_window_quality(
    frames: Sequence[_DeferredFrame],
) -> None:
    """Require every weak same-level window, including both write brackets."""

    expected_windows = _TANDEM_FRAME_SAMPLES // _TANDEM_WINDOW_SAMPLES
    for frame in frames:
        analysis = frame.record.get("analysis")
        windows = analysis.get("windows") if isinstance(analysis, Mapping) else None
        if (
            not isinstance(windows, list)
            or len(windows) != expected_windows
            or any(
                not isinstance(window, Mapping)
                or window.get("quality_valid") is not True
                for window in windows
            )
        ):
            raise EvidenceInvalid(
                "weak dual-target returned-IQ window failed a quality gate"
            )


def _weak_cross_suffix_stability(
    suffixes: Mapping[str, Mapping[str, Any]], *, tolerance_db: float
) -> dict[str, Any]:
    """Bind equal weak RF level across pre, middle, and post suffixes."""

    phase_order = (
        "fully_pre_first",
        "fully_between_commands",
        "fully_post_second",
    )
    medians: list[list[float]] = []
    endpoints: list[list[int]] = []
    for phase in phase_order:
        suffix = suffixes.get(phase)
        if not isinstance(suffix, Mapping):
            raise EvidenceInvalid(
                f"weak dual-target {phase} suffix evidence is missing"
            )
        raw_medians = suffix.get("suffix_channel_median_tone_dbfs")
        raw_endpoint = suffix.get("bench_gain_indices")
        if (
            not isinstance(raw_medians, list)
            or len(raw_medians) != 2
            or not isinstance(raw_endpoint, list)
            or len(raw_endpoint) != 2
        ):
            raise EvidenceInvalid(
                f"weak dual-target {phase} suffix geometry is invalid"
            )
        medians.append([float(value) for value in raw_medians])
        endpoints.append([int(value) for value in raw_endpoint])
    spans = [
        max(row[channel] for row in medians)
        - min(row[channel] for row in medians)
        for channel in (0, 1)
    ]
    if any(value > tolerance_db for value in spans):
        raise EvidenceInvalid(
            "weak dual-target pre/middle/post RF suffixes disagree"
        )
    if len({tuple(endpoint) for endpoint in endpoints}) != 1:
        raise EvidenceInvalid(
            "weak dual-target pre/middle/post endpoints disagree"
        )
    return {
        "phase_order": list(phase_order),
        "suffix_channel_median_tone_dbfs": medians,
        "maximum_cross_suffix_span_db": spans,
        "maximum_cross_suffix_span_limit_db": tolerance_db,
        "bench_gain_indices": endpoints[0],
    }


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
    del capture  # Tandem release transport is frozen independently of ordinary cells.
    return build_tandem_request(
        mode=TandemMode.AUTO,
        initial_gain_db=_TANDEM_INITIAL_GAIN_DB,
        power_measurement_samples=quality.tandem_power_measurement_samples,
        low_power_dwell_periods=quality.tandem_low_power_dwell_periods,
        cooldown_periods=quality.tandem_cooldown_periods,
        low_power_threshold=quality.tandem_low_power_threshold,
        large_lmt_overload_threshold=quality.tandem_large_lmt_overload_threshold,
        large_adc_overload_threshold=quality.tandem_large_adc_overload_threshold,
        small_adc_overload_threshold=quality.tandem_small_adc_overload_threshold,
        samples_per_channel=_TANDEM_FRAME_SAMPLES,
    )


_TANDEM_REQUEST_FIELD_NAMES = (
    "magic",
    "abi_version",
    "request_bytes",
    "required_features",
    "mode",
    "observation_capacity",
    "event_capacity",
    "minimum_gain_db",
    "maximum_gain_db",
    "initial_gain_db",
    "power_measurement_samples",
    "low_power_dwell_periods",
    "cooldown_periods",
    "pulse_high_cycles",
    "pulse_low_cycles",
    "detector_blanking_cycles",
    "low_power_threshold",
    "large_lmt_overload_threshold",
    "large_adc_overload_threshold",
    "small_adc_overload_threshold",
    "observation_overflow_policy",
    "event_overflow_policy",
    "reserved_0",
    "reserved_1",
    "reserved_2",
    "reserved_3",
    "reserved_4",
    "reserved_5",
    "reserved_6",
    "reserved_7",
)


def _tandem_request_evidence(request: bytes) -> dict[str, Any]:
    decoded = dict(
        zip(_TANDEM_REQUEST_FIELD_NAMES, TANDEM_REQUEST.unpack(request), strict=True)
    )
    return {
        "wire_bytes": len(request),
        "wire_hex": request.hex(),
        "sha256": hashlib.sha256(request).hexdigest(),
        "decoded": decoded,
    }


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


def _batch_command_record(
    command: StimulusCommand,
    *,
    effective_attenuation_db: float,
    sample_counter_bracket: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        **command.as_dict(),
        "effective_attenuation_db": effective_attenuation_db,
        "rx_state_before": None,
        "rx_state_after": None,
        "timing_role": (
            "s0_targeted_one_write_bracketed_by_coherent_fpga_counter"
        ),
        "sample_timing_basis": _TANDEM_TIMING_BASIS,
        "sample_anchor_policy": (
            "post-open S0 plus frozen target; exact one-TX2-write interval is "
            "[A,C) during initiating batch refill"
        ),
        "sample_counter_bracket": dict(sample_counter_bracket),
    }


def _strict_tandem_status(
    radio: TransientRadioTransport, *, owned: bool, label: str
) -> dict[str, int]:
    names = (
        "state",
        "fault_flags",
        "overflow_count",
        "fifo_level",
        "ownership_epoch",
        "transition_count",
        "rx1_gain_index",
        "rx2_gain_index",
    )
    raw = radio.tandem_status()
    try:
        values = {name: raw[name] for name in names}
    except (KeyError, TypeError) as error:
        raise EvidenceInvalid(f"{label} tandem status is incomplete") from error
    if any(type(value) is not int for value in values.values()):
        raise EvidenceInvalid(f"{label} tandem status contains a non-exact integer")
    status = dict(values)
    if status["fault_flags"] or status["overflow_count"]:
        raise EvidenceInvalid(f"{label} tandem status reports a fault/overflow")
    if not all(
        0 <= status[name] < _UINT32_MODULUS
        for name in (
            "fault_flags",
            "overflow_count",
            "fifo_level",
            "ownership_epoch",
            "transition_count",
        )
    ):
        raise EvidenceInvalid(f"{label} tandem status counter lies outside uint32")
    if status["rx1_gain_index"] != status["rx2_gain_index"]:
        raise EvidenceInvalid(f"{label} tandem endpoint is torn")
    if not 0 <= status["rx1_gain_index"] <= 127:
        raise EvidenceInvalid(f"{label} tandem endpoint lies outside uint7")
    if owned:
        if (
            status["state"] != int(TandemState.ARMED_AUTO)
            or status["ownership_epoch"] <= 0
            or not 0 <= status["fifo_level"] <= 64
        ):
            raise EvidenceInvalid(f"{label} tandem AUTO ownership is invalid")
    elif (
        status["state"] != int(TandemState.IDLE)
        or status["fifo_level"] != 0
        or status["ownership_epoch"] != 0
    ):
        raise EvidenceInvalid(f"{label} tandem controller is not fully idle")
    return status


def _response_window_ledger(
    frames: Sequence[_DeferredFrame],
    *,
    sample_start: int,
    sample_end_exclusive: int,
    label: str,
) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    windows = [
        window
        for frame in frames
        for window in frame.record["analysis"]["windows"]
        if int(window["sample_start"]) >= sample_start
        and int(window["sample_end_exclusive"]) <= sample_end_exclusive
    ]
    if not windows:
        raise EvidenceInvalid(f"tandem {label} response window selection is empty")
    for previous, current in pairwise(windows):
        if int(previous["sample_end_exclusive"]) != int(current["sample_start"]):
            raise EvidenceInvalid(
                f"tandem {label} response windows are not sample contiguous"
            )
    selected_indices = sorted(
        {
            int(frame.record["frame_index"])
            for frame in frames
            if any(window in frame.record["analysis"]["windows"] for window in windows)
        }
    )
    return windows, {
        "frame_indices": selected_indices,
        "sample_sequence_before": int(windows[0]["sample_start"]),
        "sample_sequence_after": int(windows[-1]["sample_end_exclusive"]),
        "window_samples": _TANDEM_WINDOW_SAMPLES,
        "window_count": len(windows),
        "selection": (
            "all complete persisted batch-frame windows inside the stated "
            "half-open sample interval"
        ),
    }


def _run_tandem_batch_mode_body(
    radio: TransientRadioTransport,
    *,
    quality: TandemQualityOptions,
    capture: TransientCaptureOptions,
    check_deadline: Callable[[], None],
    clock_ns: Callable[[], int],
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    metadata_parser: Callable[[bytes], TandemFrameMetadata],
    output_dir: Path,
    failure_sink: Callable[[Mapping[str, Any]], None] | None,
    profile: _TandemBatchProfile = (
        _TandemBatchProfile.PRODUCTION_ATTACK_RELEASE
    ),
) -> dict[str, Any]:
    """Run the closed production or weak qualification batch profile."""

    if type(profile) is not _TandemBatchProfile:
        raise TypeError("tandem batch profile is not a closed profile member")
    if profile is _TandemBatchProfile.PRODUCTION_ATTACK_RELEASE:
        selected_specs = (
            (
                "strong_attack",
                capture.strong_stimulus_tx_gain_db,
                _TANDEM_ATTACK_TARGET_FRAMES,
            ),
            (
                "weak_release",
                capture.weak_stimulus_tx_gain_db,
                _TANDEM_RELEASE_TARGET_FRAMES,
            ),
        )
        artifact_directory = MODE_TANDEM
        artifact_policy = "mandatory_exact_release_sidecars"
    else:
        if float(capture.weak_stimulus_tx_gain_db) != (
            _TANDEM_WEAK_COMMAND_LEVEL_DB
        ):
            raise ValueError(
                "weak dual-target profile is hard-capped at -45 dB TX2"
            )
        selected_specs = (
            (
                _TANDEM_WEAK_FIRST_COMMAND_ID,
                _TANDEM_WEAK_COMMAND_LEVEL_DB,
                _TANDEM_ATTACK_TARGET_FRAMES,
            ),
            (
                _TANDEM_WEAK_SECOND_COMMAND_ID,
                _TANDEM_WEAK_COMMAND_LEVEL_DB,
                _TANDEM_RELEASE_TARGET_FRAMES,
            ),
        )
        artifact_directory = _TANDEM_WEAK_ARTIFACT_DIRECTORY
        artifact_policy = _TANDEM_WEAK_ARTIFACT_POLICY

    normalized_specs = tuple(
        (command_id, float(level_db), target_frames)
        for command_id, level_db, target_frames in selected_specs
    )
    expected_specs = (
        (
            "strong_attack",
            float(capture.strong_stimulus_tx_gain_db),
            _TANDEM_ATTACK_TARGET_FRAMES,
        ),
        (
            "weak_release",
            float(capture.weak_stimulus_tx_gain_db),
            _TANDEM_RELEASE_TARGET_FRAMES,
        ),
    ) if profile is _TandemBatchProfile.PRODUCTION_ATTACK_RELEASE else (
        (
            _TANDEM_WEAK_FIRST_COMMAND_ID,
            _TANDEM_WEAK_COMMAND_LEVEL_DB,
            _TANDEM_ATTACK_TARGET_FRAMES,
        ),
        (
            _TANDEM_WEAK_SECOND_COMMAND_ID,
            _TANDEM_WEAK_COMMAND_LEVEL_DB,
            _TANDEM_RELEASE_TARGET_FRAMES,
        ),
    )
    if normalized_specs != expected_specs:
        raise ValueError(
            "tandem batch commands differ from their closed profile"
        )

    memory_ledger = _tandem_memory_ledger()
    if memory_ledger["within_cap"] is not True:
        raise EvidenceInvalid("tandem batch resident-memory ledger exceeds its cap")
    record: dict[str, Any] = {
        "mode": MODE_TANDEM,
        "verdict": "running",
        "timing_basis": _TANDEM_TIMING_BASIS,
        "commands": [],
        "batch_frames": [],
        "partition": None,
        "conditioning_anchor": None,
        "response_observations": {},
        "responses": {},
        "gain_evidence": None,
        "metadata_request": None,
        "acquisition": {
            "transport": "single_metadata_batch",
            "provider_frame_samples": _TANDEM_FRAME_SAMPLES,
            "kernel_buffers": _TANDEM_KERNEL_BUFFERS,
            "batch_frames": _TANDEM_BATCH_FRAMES,
            "queue_capacity_frames": _TANDEM_CAPTURE_QUEUE_FRAMES,
            "metadata_capacity_bytes": _TANDEM_METADATA_CAPACITY_BYTES,
            "metadata_physics_policy": {
                "protocol_version": 5,
                "header_bytes": _TANDEM_METADATA_HEADER_BYTES,
                "required_features": _TANDEM_REQUIRED_METADATA_FEATURES,
                "required_flags": _TANDEM_REQUIRED_METADATA_FLAGS,
                "sample_format": 1,
                "observation_capacity": 64,
                "event_capacity": 64,
                "maximum_observations_per_frame": 5,
                "maximum_events_per_frame": maximum_tandem_events_per_frame(
                    mode=TandemMode.AUTO,
                    samples_per_channel=_TANDEM_FRAME_SAMPLES,
                    power_measurement_samples=(
                        quality.tandem_power_measurement_samples
                    ),
                    cooldown_periods=quality.tandem_cooldown_periods,
                ),
                "minimum_event_spacing_samples": (
                    quality.tandem_power_measurement_samples
                    * (quality.tandem_cooldown_periods + 1)
                ),
            },
            "metadata_abi": None,
            "configured_batch_frames": None,
            "configured_batch_cache_bytes": None,
            "batch_cache_attested": False,
            "memory_ledger": memory_ledger,
            "s0_read": {
                "host_before_ns": None,
                "host_after_ns": None,
                "raw": None,
            },
            "post_open_s0_raw": None,
            "targets": {},
            "schedule_diagnostics": {},
            "schedule_frozen_before_worker_start": False,
            "schedule_plan": {
                "s0_read_host_after_ns": None,
                "targets_frozen_host_ns": None,
                "worker_start_requested_ns": None,
                "worker_start_returned_ns": None,
                "commands": [],
            },
            "unbound_commands": {},
            "initiating_batch_refill_calls": 0,
            "public_refill_calls": 0,
            "cached_replay_refill_calls": 0,
            "batch_cache_fully_replayed": False,
            "initiating_refill_completion_monotonic_ns": None,
            "produced_frames": 0,
            "consumed_frames": 0,
            "discarded_tail_frames": 0,
            "pre_close_tandem_status": None,
            "buffer_close_completed": False,
            "post_close_tandem_status": None,
            "close_counter_ledger": None,
            "artifact_manifest": None,
            "shutdown": {
                "events": [],
                "worker_in_flight_before_shutdown": None,
                "cancel_required": None,
                "cancel_called": False,
                "cancel_succeeded": None,
                "worker_stopped": False,
                "batch_fully_consumed": False,
                "shutdown_path": None,
            },
        },
    }
    if profile is _TandemBatchProfile.WEAK_DUAL_TARGET_TRANSPORT:
        for release_only_key in (
            "response_observations",
            "responses",
            "gain_evidence",
        ):
            record.pop(release_only_key)
        record.update(
            {
                "batch_profile": profile.value,
                "release_pass_eligible": False,
                "strong_tx_write_permitted": False,
                "gain_transient_exercised": False,
                "qualification_scope": (
                    "weak-only same-level dual-target transport, ordering, "
                    "retention, provenance, RF-stability, and cleanup evidence; "
                    "no gain-transient or latency qualification"
                ),
                "transport_stability": None,
            }
        )
    acquisition = record["acquisition"]
    frames: list[_DeferredFrame] = []
    initial_unanchored: StimulusCommand | None = None
    bound_commands: dict[str, StimulusCommand] = {}
    command_brackets: dict[str, Mapping[str, Any]] = {}

    try:
        radio.mute_all()
        record["tandem_status_before"] = _wait_for_idle(
            radio, monotonic=monotonic, sleep=sleep
        )
        radio.configure_rx("manual", manual_gain_db=quality.manual_gain_db)
        radio.arm_tx2_tone(tone_hz=quality.tone_hz, scale=quality.dds_scale)
        initial_unanchored = timestamp_stimulus_command(
            "weak_initial",
            capture.weak_stimulus_tx_gain_db,
            apply=radio.set_tx2_gain,
            clock_ns=clock_ns,
            max_host_jitter_ns=capture.max_host_jitter_ns,
            readback_tolerance_db=capture.readback_tolerance_db,
        )
        initial_effective = _check_effective_attenuation(quality, initial_unanchored)
        record["commands"].append(
            {
                **initial_unanchored.as_dict(),
                "effective_attenuation_db": initial_effective,
                "rx_state_before": None,
                "rx_state_after": None,
                "timing_role": "pre_session_weak_conditioning_write",
                "sample_timing_basis": None,
                "sample_anchor_policy": (
                    "unbounded in hardware sample time; write predates AUTO62 "
                    "batch ownership"
                ),
            }
        )
        request = _build_tandem_request(quality, capture)
        record["metadata_request"] = _tandem_request_evidence(request)
        state = _CaptureState()
        tandem_capture = replace(
            capture,
            frame_samples=_TANDEM_FRAME_SAMPLES,
            window_samples=_TANDEM_WINDOW_SAMPLES,
        )
        worker: _TandemBatchWorker | None = None
        cancel_capture: Callable[[], Any] | None = None
        session_error: BaseException | None = None
        try:
            with radio.buffer(
                "metadata",
                _TANDEM_KERNEL_BUFFERS,
                _TANDEM_FRAME_SAMPLES,
                tandem_request=request,
                batch_frames=_TANDEM_BATCH_FRAMES,
            ) as (buffer, metadata_abi):
                cancel_value = getattr(buffer, "cancel", None)
                cancel_capture = cancel_value if callable(cancel_value) else None
                configured_batch_frames = getattr(buffer, "batch_frames", None)
                configured_batch_cache_bytes = getattr(
                    buffer, "batch_cache_bytes", None
                )
                acquisition.update(
                    {
                        "metadata_abi": metadata_abi,
                        "configured_batch_frames": configured_batch_frames,
                        "configured_batch_cache_bytes": configured_batch_cache_bytes,
                    }
                )
                try:
                    if (
                        metadata_abi != 2
                        or cancel_capture is None
                        or type(configured_batch_frames) is not int
                        or configured_batch_frames != _TANDEM_BATCH_FRAMES
                        or type(configured_batch_cache_bytes) is not int
                        or configured_batch_cache_bytes != _TANDEM_BATCH_CACHE_BYTES
                    ):
                        raise EvidenceInvalid(
                            "tandem release requires ABI2, batch64 cache "
                            "attestation, and thread-safe cancel"
                        )
                    acquisition["batch_cache_attested"] = True
                    s0_read = acquisition["s0_read"]
                    s0_read["host_before_ns"] = _schedule_timestamp(
                        clock_ns, name="post-open S0 read start"
                    )
                    s0_raw = _strict_low32_counter(
                        radio.read_rx_sample_counter_low32()
                    )
                    s0_read["host_after_ns"] = _schedule_timestamp(
                        clock_ns, name="post-open S0 read completion"
                    )
                    if s0_read["host_after_ns"] < s0_read["host_before_ns"]:
                        raise EvidenceInvalid("post-open S0 read clock moved backward")
                    s0_read["raw"] = s0_raw
                    acquisition["post_open_s0_raw"] = s0_raw

                    def acquire_one() -> _DeferredFrame:
                        return _capture_frame(
                            radio,
                            buffer,
                            mode=MODE_TANDEM,
                            expected_iio_mode="manual",
                            quality=quality,
                            capture=tandem_capture,
                            state=state,
                            metadata_parser=metadata_parser,
                            gap_context=_GAP_CONTEXT_ACQUISITION,
                            expected_tandem_initial_gain_db=(
                                _TANDEM_INITIAL_GAIN_DB
                            ),
                        )

                    worker = _TandemBatchWorker(acquire_one)
                    if worker.queue_capacity_frames != _TANDEM_CAPTURE_QUEUE_FRAMES:
                        raise EvidenceInvalid(
                            "tandem batch worker queue differs from memory ledger"
                        )
                    for command_id, level_db, target_frames in selected_specs:
                        diagnostics = _new_batch_command_diagnostics(
                            command_id=command_id,
                            requested_level_db=level_db,
                            target_frames=target_frames,
                            s0_raw=s0_raw,
                        )
                        acquisition["schedule_diagnostics"][command_id] = diagnostics
                        acquisition["targets"][command_id] = {
                            "offset_frames": target_frames,
                            "offset_samples": (
                                target_frames * _TANDEM_FRAME_SAMPLES
                            ),
                            "target_raw": diagnostics["target"]["target_raw"],
                        }
                    schedule_plan = acquisition["schedule_plan"]
                    schedule_plan["s0_read_host_after_ns"] = s0_read[
                        "host_after_ns"
                    ]
                    schedule_plan["commands"] = [
                        {
                            "command_id": command_id,
                            "requested_level_db": level_db,
                            **acquisition["targets"][command_id],
                        }
                        for command_id, level_db, _target_frames in selected_specs
                    ]
                    schedule_plan["targets_frozen_host_ns"] = _schedule_timestamp(
                        clock_ns, name="both tandem targets frozen"
                    )
                    acquisition["schedule_frozen_before_worker_start"] = True
                    schedule_plan["worker_start_requested_ns"] = _schedule_timestamp(
                        clock_ns, name="tandem worker start requested"
                    )
                    worker.start()
                    schedule_plan["worker_start_returned_ns"] = _schedule_timestamp(
                        clock_ns, name="tandem worker start returned"
                    )
                    chronology = (
                        schedule_plan["s0_read_host_after_ns"],
                        schedule_plan["targets_frozen_host_ns"],
                        schedule_plan["worker_start_requested_ns"],
                        schedule_plan["worker_start_returned_ns"],
                    )
                    if list(chronology) != sorted(chronology):
                        raise EvidenceInvalid(
                            "tandem schedule freeze/start chronology is invalid"
                        )
                    unbound_commands: dict[str, StimulusCommand] = {}
                    for command_id, level_db, target_frames in selected_specs:
                        diagnostics = acquisition["schedule_diagnostics"][command_id]
                        unbound = _schedule_tandem_batch_command(
                            radio,
                            worker,
                            command_id=command_id,
                            requested_level_db=level_db,
                            target_frames=target_frames,
                            s0_raw=s0_raw,
                            diagnostics=diagnostics,
                            check_deadline=check_deadline,
                            clock_ns=clock_ns,
                            sleep=sleep,
                            sample_rate_hz=quality.sample_rate_hz,
                            max_host_jitter_ns=capture.max_host_jitter_ns,
                            max_sample_uncertainty=min(
                                capture.max_sample_uncertainty,
                                _TANDEM_MAX_CAUSAL_UNCERTAINTY_SAMPLES,
                            ),
                            readback_tolerance_db=capture.readback_tolerance_db,
                        )
                        unbound_commands[command_id] = unbound
                        acquisition["unbound_commands"][command_id] = {
                            **unbound.as_dict(),
                            "effective_attenuation_db": _check_effective_attenuation(
                                quality, unbound
                            ),
                        }

                    for _ in range(_TANDEM_BATCH_FRAMES):
                        check_deadline()
                        frame = worker.take()
                        frames.append(frame)
                        retained_bytes = sum(len(item.raw) for item in frames)
                        if retained_bytes > _TANDEM_MAXIMUM_PYTHON_RAW_BYTES:
                            raise EvidenceInvalid(
                                "tandem retained raw IQ exceeds its exact memory bound"
                            )
                        retained_metadata_bytes = sum(
                            len(item.raw_metadata or b"") for item in frames
                        )
                        if retained_metadata_bytes > (
                            _TANDEM_MAXIMUM_PYTHON_RAW_METADATA_BYTES
                        ):
                            raise EvidenceInvalid(
                                "tandem retained raw metadata exceeds its exact "
                                "memory bound"
                            )
                    acquisition.update(
                        {
                            "initiating_batch_refill_calls": 1,
                            "public_refill_calls": _TANDEM_BATCH_FRAMES,
                            "cached_replay_refill_calls": _TANDEM_BATCH_FRAMES - 1,
                            "batch_cache_fully_replayed": True,
                            "initiating_refill_completion_monotonic_ns": int(
                                frames[0].record["refill_monotonic_ns"]
                            ),
                        }
                    )
                    _require_tandem_temperature_session(
                        state, frame_count=len(frames)
                    )
                    _validate_exact_tandem_batch(frames)
                    record["batch_frames"] = [frame.record for frame in frames]
                    for command_id, _level_db, _target_frames in selected_specs:
                        bound, bracket = _bind_tandem_batch_command(
                            frames,
                            unbound_commands[command_id],
                            acquisition["schedule_diagnostics"][command_id],
                        )
                        bound_commands[command_id] = bound
                        command_brackets[command_id] = bracket
                        record["commands"].append(
                            _batch_command_record(
                                bound,
                                effective_attenuation_db=(
                                    _check_effective_attenuation(quality, bound)
                                ),
                                sample_counter_bracket=bracket,
                            )
                        )
                    first_command = bound_commands[selected_specs[0][0]]
                    second_command = bound_commands[selected_specs[1][0]]
                    if profile is _TandemBatchProfile.PRODUCTION_ATTACK_RELEASE:
                        record["partition"] = _partition_tandem_batch(
                            frames,
                            attack=first_command,
                            release=second_command,
                        )
                    else:
                        record["partition"] = _partition_weak_tandem_batch(
                            frames,
                            first=first_command,
                            second=second_command,
                        )
                    initiating_completion = acquisition[
                        "initiating_refill_completion_monotonic_ns"
                    ]
                    if initial_unanchored.host_after_ns > (
                        first_command.host_before_ns
                    ) or any(
                        command.host_after_ns > initiating_completion
                        for command in bound_commands.values()
                    ):
                        raise EvidenceInvalid(
                            "tandem commands did not complete inside the initiating "
                            "batch refill"
                        )
                    first_diagnostics = acquisition["schedule_diagnostics"][
                        selected_specs[0][0]
                    ]
                    second_diagnostics = acquisition["schedule_diagnostics"][
                        selected_specs[1][0]
                    ]
                    first_post = first_diagnostics["tx1_mute_assurance"]["post"]
                    second_pre = second_diagnostics["tx1_mute_assurance"]["pre"]
                    first_pre = first_diagnostics["tx1_mute_assurance"]["pre"]
                    if (
                        initial_unanchored.host_after_ns
                        > acquisition["s0_read"]["host_before_ns"]
                        or acquisition["schedule_plan"][
                            "worker_start_returned_ns"
                        ]
                        > first_pre["host_before_ns"]
                        or first_command.sample_sequence_after is None
                        or second_command.sample_sequence_before is None
                        or first_command.sample_sequence_after
                        > second_command.sample_sequence_before
                        or first_command.host_after_ns > second_command.host_before_ns
                        or first_post["host_after_ns"]
                        > second_pre["host_before_ns"]
                    ):
                        raise EvidenceInvalid(
                            "tandem first/second command chronology overlaps or "
                            "reorders"
                        )
                except BaseException as error:  # noqa: BLE001 - preserve interrupts
                    session_error = error

                shutdown = acquisition["shutdown"]

                def shutdown_event(name: str) -> None:
                    shutdown["events"].append(
                        {"event": name, "monotonic_ns": time.monotonic_ns()}
                    )

                mute_error: BaseException | None = None
                shutdown_event("prejoin_mute_start")
                try:
                    radio.mute_all()
                except BaseException as error:  # noqa: BLE001
                    mute_error = error
                    shutdown_event("prejoin_mute_failed")
                else:
                    shutdown_event("prejoin_mute_complete")
                preclose_status_error: BaseException | None = None
                if session_error is None and mute_error is None:
                    try:
                        acquisition["pre_close_tandem_status"] = (
                            _strict_tandem_status(
                                radio, owned=True, label="pre-close after mute"
                            )
                        )
                    except BaseException as error:  # noqa: BLE001
                        preclose_status_error = error
                worker_in_flight = bool(
                    worker is not None and worker.first_refill_in_flight
                )
                batch_fully_consumed = bool(
                    worker is not None
                    and len(frames) == _TANDEM_BATCH_FRAMES
                    and worker.produced_frames == _TANDEM_BATCH_FRAMES
                    and worker.consumed_frames == _TANDEM_BATCH_FRAMES
                )
                cancel_required = (
                    session_error is not None
                    or mute_error is not None
                    or preclose_status_error is not None
                    or worker_in_flight
                )
                if worker is not None:
                    worker.request_stop()
                cancel_error: BaseException | None = None
                cancel_called = False
                if cancel_required:
                    cancel_called = True
                    shutdown_event("cancel_start")
                    if cancel_capture is None:
                        cancel_error = EvidenceInvalid(
                            "tandem error path lacks buffer cancellation"
                        )
                        shutdown_event("cancel_failed")
                    else:
                        try:
                            cancel_capture()
                        except BaseException as error:  # noqa: BLE001
                            cancel_error = error
                            shutdown_event("cancel_failed")
                        else:
                            shutdown_event("cancel_complete")
                stop_error: BaseException | None = None
                if worker is not None:
                    shutdown_event("worker_stop_start")
                    try:
                        worker.stop()
                    except BaseException as error:  # noqa: BLE001
                        stop_error = error
                        shutdown_event("worker_stop_failed")
                    else:
                        shutdown_event("worker_stop_complete")
                    acquisition.update(
                        {
                            "produced_frames": worker.produced_frames,
                            "consumed_frames": worker.consumed_frames,
                            "discarded_tail_frames": worker.discarded_tail_frames,
                        }
                    )
                shutdown.update(
                    {
                        "worker_in_flight_before_shutdown": worker_in_flight,
                        "cancel_required": cancel_required,
                        "cancel_called": cancel_called,
                        "cancel_succeeded": (
                            cancel_error is None if cancel_called else None
                        ),
                        "worker_stopped": stop_error is None,
                        "batch_fully_consumed": batch_fully_consumed,
                        "shutdown_path": (
                            "cancel_after_error_or_in_flight_batch"
                            if cancel_required
                            else "normal_close_after_full_cache_replay"
                        ),
                    }
                )
                errors = [
                    error
                    for error in (
                        session_error,
                        mute_error,
                        preclose_status_error,
                        cancel_error,
                        stop_error,
                    )
                    if error is not None
                ]
                if len(errors) > 1:
                    raise BaseExceptionGroup(
                        "tandem batch acquisition or shutdown reported multiple "
                        "failures",
                        errors,
                    )
                if errors:
                    error = errors[0]
                    raise error.with_traceback(error.__traceback__)
            acquisition["buffer_close_completed"] = True
        except BaseException:
            acquisition["buffer_close_completed"] = False
            raise

        acquisition["post_close_tandem_status"] = _strict_tandem_status(
            radio, owned=False, label="post-close"
        )
        pre_close_status = acquisition["pre_close_tandem_status"]
        post_close_status = acquisition["post_close_tandem_status"]
        last_frame_metadata = frames[-1].metadata
        if last_frame_metadata is None:
            raise EvidenceInvalid("tandem final retained frame lacks metadata")
        frame_to_pre_delta = _forward_u32_delta(
            pre_close_status["transition_count"],
            last_frame_metadata.tandem_transition_count,
            context="tandem final frame to pre-close transition count",
        )
        transition_delta = _forward_u32_delta(
            post_close_status["transition_count"],
            pre_close_status["transition_count"],
            context="tandem pre-close to post-close transition count",
        )
        if frame_to_pre_delta > 64 or transition_delta > 64:
            raise EvidenceInvalid(
                "tandem close transition diagnostics exceed the FIFO retirement "
                "bound"
            )
        if pre_close_status["ownership_epoch"] != (
            last_frame_metadata.ownership_epoch
        ):
            raise EvidenceInvalid(
                "tandem pre-close ownership epoch differs from retained batch"
            )
        minimum_gain_index = last_frame_metadata.minimum_gain_index
        maximum_gain_index = last_frame_metadata.maximum_gain_index
        frame_endpoint = last_frame_metadata.bench_gain_indices[0]
        pre_endpoint_value = pre_close_status["rx1_gain_index"]
        post_endpoint_value = post_close_status["rx1_gain_index"]
        if any(
            not minimum_gain_index <= value <= maximum_gain_index
            for value in (frame_endpoint, pre_endpoint_value, post_endpoint_value)
        ):
            raise EvidenceInvalid(
                "tandem close endpoint lies outside the retained gain-index range"
            )

        def require_endpoint_delta(
            before: int, after: int, transitions: int, *, label: str
        ) -> None:
            difference = abs(after - before)
            if difference > transitions or (transitions - difference) % 2:
                raise EvidenceInvalid(
                    f"{label} endpoint movement disagrees with transition count"
                )

        require_endpoint_delta(
            frame_endpoint,
            pre_endpoint_value,
            frame_to_pre_delta,
            label="tandem final-frame to pre-close",
        )
        require_endpoint_delta(
            pre_endpoint_value,
            post_endpoint_value,
            transition_delta,
            label="tandem pre-close to post-close",
        )
        acquisition["close_counter_ledger"] = {
            "last_frame_transition_count": (
                last_frame_metadata.tandem_transition_count
            ),
            "pre_transition_count": pre_close_status["transition_count"],
            "post_transition_count": post_close_status["transition_count"],
            "last_frame_to_pre_close_forward_delta": frame_to_pre_delta,
            "transition_count_forward_delta": transition_delta,
            "maximum_forward_delta": 64,
            "pre_fifo_level": pre_close_status["fifo_level"],
            "post_fifo_level": post_close_status["fifo_level"],
            "pre_endpoint": [
                pre_close_status["rx1_gain_index"],
                pre_close_status["rx2_gain_index"],
            ],
            "post_endpoint": [
                post_close_status["rx1_gain_index"],
                post_close_status["rx2_gain_index"],
            ],
            "exact_retired_tail_count_claim": None,
            "policy": (
                "preserve forward modulo-u32 diagnostics across buffer close "
                "without claiming an exact retired FIFO tail count"
                if profile is _TandemBatchProfile.WEAK_DUAL_TARGET_TRANSPORT
                else "preserve forward modulo-u32 diagnostics across RELEASE "
                "without claiming an exact retired FIFO tail count"
            ),
        }
        if profile is _TandemBatchProfile.WEAK_DUAL_TARGET_TRANSPORT:
            maximum_endpoint = last_frame_metadata.maximum_gain_index
            if (
                last_frame_metadata.tandem_transition_count != 0
                or pre_close_status["transition_count"] != 0
                or post_close_status["transition_count"] != 0
                or frame_to_pre_delta != 0
                or transition_delta != 0
                or pre_close_status["rx1_gain_index"] != maximum_endpoint
                or pre_close_status["rx2_gain_index"] != maximum_endpoint
                or post_close_status["rx1_gain_index"] != maximum_endpoint
                or post_close_status["rx2_gain_index"] != maximum_endpoint
            ):
                raise EvidenceInvalid(
                    "weak dual-target controller changed transition count or "
                    "maximum-gain endpoint through close"
                )
        radio.mute_all()
        _prepare_tandem_artifact_inventory(
            frames,
            quality=quality,
            iq_dir=output_dir / artifact_directory / "batch",
            artifact_directory=artifact_directory,
            artifact_policy=artifact_policy,
        )
        acquisition["artifact_manifest"] = _tandem_artifact_manifest(frames)
        try:
            _materialize_tandem_batch(
                frames,
                quality=quality,
                check_deadline=check_deadline,
            )
        finally:
            acquisition["artifact_manifest"] = _tandem_artifact_manifest(frames)
        if profile is _TandemBatchProfile.PRODUCTION_ATTACK_RELEASE:
            _require_tandem_batch_window_quality(
                frames,
                commands=[
                    bound_commands[selected_specs[0][0]],
                    bound_commands[selected_specs[1][0]],
                ],
            )
        else:
            _require_weak_tandem_batch_window_quality(frames)
        record["batch_frames"] = [frame.record for frame in frames]

        if profile is _TandemBatchProfile.WEAK_DUAL_TARGET_TRANSPORT:
            partition = record["partition"]
            groups = partition["groups"]
            stable_suffixes = {
                phase: _stable_tandem_partition_suffix(
                    frames,
                    frame_indices=groups[phase]["frame_indices"],
                    label=phase,
                    tolerance_db=capture.settling_tolerance_db,
                )
                for phase in (
                    "fully_pre_first",
                    "fully_between_commands",
                    "fully_post_second",
                )
            }
            partition["stable_suffixes"] = stable_suffixes
            cross_suffix = _weak_cross_suffix_stability(
                stable_suffixes, tolerance_db=capture.settling_tolerance_db
            )
            anchor_index = groups["fully_pre_first"]["frame_indices"][-1]
            anchor = _analyze_tandem_frame_slice(
                frames[anchor_index],
                offset_samples=(
                    _TANDEM_FRAME_SAMPLES - _TANDEM_CONDITIONING_TAIL_SAMPLES
                ),
                sample_count=_TANDEM_CONDITIONING_TAIL_SAMPLES,
                role="weak_pre_first_conditioning_tail",
                quality=quality,
            )
            record["conditioning_anchor"] = {
                "timing_role": "exact_retained_pre_first_tail",
                "sample_timing_basis": _TANDEM_TIMING_BASIS,
                "sample_anchor_policy": (
                    "exact final 8192 samples of the final fully-pre-first "
                    "frame; weak conditioning only, not latency evidence"
                ),
                "release_latency_evidence": False,
                "source": anchor,
            }
            first_metadata = frames[0].metadata
            assert first_metadata is not None
            record["transport_stability"] = {
                "frame_count": _TANDEM_BATCH_FRAMES,
                "global_transition_count": 0,
                "global_gain_event_count": 0,
                "maximum_gain_index": first_metadata.maximum_gain_index,
                "bench_gain_indices": [
                    first_metadata.maximum_gain_index,
                    first_metadata.maximum_gain_index,
                ],
                "all_frames_at_maximum_gain": True,
                "all_windows_quality_valid": True,
                "stable_suffixes": stable_suffixes,
                "cross_suffix_stability": cross_suffix,
            }
            record["metadata_abi"] = acquisition["metadata_abi"]
            record["tandem_status_after"] = acquisition[
                "post_close_tandem_status"
            ]
            radio.configure_rx("manual", manual_gain_db=quality.manual_gain_db)
            record["final_rx_state"] = _rx_state(
                radio, expected_mode="manual"
            )
            record["verdict"] = "qualified_transport"
            _attest_tandem_evidence_reservation(record, frames)
            return record

        attack = bound_commands[selected_specs[0][0]]
        release = bound_commands[selected_specs[1][0]]
        partition = record["partition"]
        groups = partition["groups"]
        partition["stable_suffixes"] = {
            phase: _stable_tandem_partition_suffix(
                frames,
                frame_indices=groups[phase]["frame_indices"],
                label=phase,
                tolerance_db=capture.settling_tolerance_db,
            )
            for phase in (
                "fully_post_attack_pre_release",
                "fully_post_release",
            )
        }
        pre_attack_metadata = frames[
            groups["fully_pre_attack"]["frame_indices"][-1]
        ].metadata
        if pre_attack_metadata is None:
            raise EvidenceInvalid("tandem pre-attack endpoint evidence is missing")
        pre_attack_endpoint = pre_attack_metadata.bench_gain_indices[0]
        middle_endpoint = partition["stable_suffixes"][
            "fully_post_attack_pre_release"
        ]["bench_gain_indices"][0]
        final_endpoint = partition["stable_suffixes"]["fully_post_release"][
            "bench_gain_indices"
        ][0]
        if not (
            middle_endpoint < pre_attack_endpoint
            and final_endpoint > middle_endpoint
        ):
            raise EvidenceInvalid(
                "tandem stable endpoints do not prove the commanded "
                "attack decrease and release increase"
            )
        anchor_index = groups["fully_pre_attack"]["frame_indices"][-1]
        anchor_frame = frames[anchor_index]
        anchor_observation = _analyze_tandem_frame_slice(
            anchor_frame,
            offset_samples=(
                _TANDEM_FRAME_SAMPLES - _TANDEM_CONDITIONING_TAIL_SAMPLES
            ),
            sample_count=_TANDEM_CONDITIONING_TAIL_SAMPLES,
            role="weak_conditioning_tail",
            quality=quality,
        )
        assert initial_unanchored is not None
        conditioning_command = replace(
            initial_unanchored,
            command_id="weak_conditioning_anchor",
            sample_sequence_before=anchor_observation["first_sample_sequence"],
            sample_sequence_after=anchor_observation["sample_end_exclusive"],
        )
        record["conditioning_anchor"] = {
            **conditioning_command.as_dict(),
            "timing_role": "exact_retained_pre_attack_tail",
            "sample_timing_basis": _TANDEM_TIMING_BASIS,
            "sample_anchor_policy": (
                "exact final 8192 samples of the final fully-pre-attack frame; "
                "conditioning evidence, not initial-write timing"
            ),
            "source": anchor_observation,
        }

        release_baseline_index = groups[
            "fully_post_attack_pre_release"
        ]["frame_indices"][-1]
        release_baseline = _analyze_tandem_frame_slice(
            frames[release_baseline_index],
            offset_samples=(
                _TANDEM_FRAME_SAMPLES - _TANDEM_CONDITIONING_TAIL_SAMPLES
            ),
            sample_count=_TANDEM_CONDITIONING_TAIL_SAMPLES,
            role="strong_pre_release_tail",
            quality=quality,
        )
        attack_windows, attack_window_ledger = _response_window_ledger(
            frames,
            sample_start=anchor_observation["first_sample_sequence"],
            sample_end_exclusive=release.sample_sequence_before,
            label="attack",
        )
        release_windows, release_window_ledger = _response_window_ledger(
            frames,
            sample_start=release_baseline["first_sample_sequence"],
            sample_end_exclusive=int(frames[-1].record["sample_end_exclusive"]),
            label="release",
        )
        record["response_observations"] = {
            "attack": {
                **attack_window_ledger,
                "baseline_anchor": anchor_observation,
            },
            "release": {
                **release_window_ledger,
                "baseline_anchor": release_baseline,
            },
        }
        record["baseline_frames"] = [anchor_observation]
        record["attack_frames"] = [
            frames[index].record
            for index in (
                groups["attack_bracket"]["frame_indices"]
                + groups["fully_post_attack_pre_release"]["frame_indices"]
            )
        ]
        record["release_frames"] = [
            frames[index].record
            for index in (
                groups["release_bracket"]["frame_indices"]
                + groups["fully_post_release"]["frame_indices"]
            )
        ]
        record["preconditioning"] = {
            "frame_count": groups["fully_pre_attack"]["count"],
            "trace_frame_indices": groups["fully_pre_attack"]["frame_indices"],
            "retained_baseline_frame_indices": [anchor_index],
            "auto_initial_gain_db": _TANDEM_INITIAL_GAIN_DB,
            "startup_transition_count": 0,
        }

        response_kwargs = {
            "sample_rate_hz": quality.sample_rate_hz,
            "baseline_windows": capture.baseline_windows,
            "steady_windows": capture.steady_windows,
            "stable_windows": capture.stable_windows,
            "settling_tolerance_db": capture.settling_tolerance_db,
            "ringing_deadband_db": capture.ringing_deadband_db,
            "max_host_jitter_ns": capture.max_host_jitter_ns,
            "max_sample_uncertainty": min(
                capture.max_sample_uncertainty,
                _TANDEM_MAX_CAUSAL_UNCERTAINTY_SAMPLES,
            ),
        }
        record["responses"] = {
            "attack": _qualify_response_timing(
                calculate_transient_response(
                    attack_windows,
                    previous_command=conditioning_command,
                    command=attack,
                    **response_kwargs,
                ),
                hardware_latency_qualified=True,
            ),
            "release": _qualify_response_timing(
                calculate_transient_response(
                    release_windows,
                    previous_command=attack,
                    command=release,
                    **response_kwargs,
                ),
                hardware_latency_qualified=True,
            ),
        }
        events = [
            event
            for frame in frames
            if frame.metadata is not None
            for event in frame.metadata.gain_events
        ]
        record["gain_evidence"] = dict(
            reconcile_tandem_events(
                (conditioning_command, attack, release),
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
        record["metadata_abi"] = acquisition["metadata_abi"]
        record["tandem_status_after"] = acquisition[
            "post_close_tandem_status"
        ]
        radio.configure_rx("manual", manual_gain_db=quality.manual_gain_db)
        record["final_rx_state"] = _rx_state(radio, expected_mode="manual")
        record["verdict"] = "pass"
        _attest_tandem_evidence_reservation(record, frames)
        return record
    except BaseException as error:
        if frames and not record["batch_frames"]:
            partial_records: list[dict[str, Any]] = []
            for frame in frames:
                partial = frame.record
                if frame.metadata is not None and "metadata" not in partial:
                    partial["metadata"] = _metadata_dict(frame.metadata)
                partial_records.append(partial)
            record["batch_frames"] = partial_records
        record["verdict"] = "invalid"
        record["fatal_error"] = _exception_text(error)
        if failure_sink is not None:
            failure_sink(record)
        raise


def _run_weak_dual_target_batch_preflight_body(
    radio: TransientRadioTransport,
    *,
    quality: TandemQualityOptions,
    capture: TransientCaptureOptions,
    check_deadline: Callable[[], None],
    clock_ns: Callable[[], int],
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    metadata_parser: Callable[[bytes], TandemFrameMetadata],
    output_dir: Path,
    failure_sink: Callable[[Mapping[str, Any]], None] | None,
) -> dict[str, Any]:
    """Enter the weak profile only through the guarded probe-v4 wrapper."""

    return _run_tandem_batch_mode_body(
        radio,
        quality=quality,
        capture=capture,
        check_deadline=check_deadline,
        clock_ns=clock_ns,
        monotonic=monotonic,
        sleep=sleep,
        metadata_parser=metadata_parser,
        output_dir=output_dir,
        failure_sink=failure_sink,
        profile=_TandemBatchProfile.WEAK_DUAL_TARGET_TRANSPORT,
    )


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
    failure_sink: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if mode == MODE_TANDEM:
        return _run_tandem_batch_mode_body(
            radio,
            quality=quality,
            capture=capture,
            check_deadline=check_deadline,
            clock_ns=clock_ns,
            monotonic=monotonic,
            sleep=sleep,
            metadata_parser=metadata_parser,
            output_dir=output_dir,
            failure_sink=failure_sink,
        )

    radio.mute_all()
    status_before = _wait_for_idle(radio, monotonic=monotonic, sleep=sleep)
    radio.configure_rx("manual", manual_gain_db=quality.manual_gain_db)
    radio.arm_tx2_tone(tone_hz=quality.tone_hz, scale=quality.dds_scale)

    native_iio_mode = native_gain_control_mode(mode)
    if native_iio_mode is None and mode != MODE_MANUAL:
        raise ValueError(f"unknown transient mode {mode!r}")

    initial_gain_state_before = _rx_state(radio, expected_mode="manual")
    initial_unanchored = timestamp_stimulus_command(
        "weak_initial",
        capture.weak_stimulus_tx_gain_db,
        apply=radio.set_tx2_gain,
        clock_ns=clock_ns,
        max_host_jitter_ns=capture.max_host_jitter_ns,
        readback_tolerance_db=capture.readback_tolerance_db,
    )
    initial_effective = _check_effective_attenuation(quality, initial_unanchored)
    initial_gain_state_after = _rx_state(radio, expected_mode="manual")
    if native_iio_mode is not None:
        # Preload the actual weak stimulus before entering native AGC.  Fast
        # attack may otherwise lock on the muted state and retain a prior run's
        # lock level through this trajectory.
        radio.configure_rx(native_iio_mode)
        expected_iio_mode = native_iio_mode
    else:
        expected_iio_mode = "manual"

    request = None
    timing_basis = _ORDINARY_TIMING_BASIS
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
    failure_sink: Callable[[Mapping[str, Any]], None] | None = None,
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
            failure_sink=failure_sink,
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
        if mode == MODE_TANDEM and result is not None:
            cleanup_error = _exception_text(mute_error)
            result["verdict"] = "invalid"
            result["fatal_error"] = cleanup_error
            result["cleanup_request_error"] = cleanup_error
            if failure_sink is not None:
                failure_sink(result)
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
    report_path = _preflight_transient_output_paths(
        quality.output_dir, radio.options.serial
    )
    serial = report_path.parent.name
    radio._report_path = report_path
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

    started = monotonic()

    def report_inventory_policy(value: Mapping[str, Any]) -> str:
        if value.get("verdict") == "invalid":
            return "partial"
        modes = value.get("modes")
        if isinstance(modes, list) and any(
            isinstance(mode, Mapping) and mode.get("mode") == MODE_TANDEM
            for mode in modes
        ):
            return "complete"
        return "empty"

    def write_report(value: Mapping[str, Any]) -> None:
        inventory_policy = report_inventory_policy(value)
        checked_path = _preflight_transient_output_paths(
            quality.output_dir,
            serial,
            sidecar_inventory_policy=inventory_policy,
        )
        if checked_path != report_path:
            raise EvidenceInvalid("transient report path changed after preflight")
        report_writer(report_path, value)
        try:
            checked_after = _preflight_transient_output_paths(
                quality.output_dir,
                serial,
                sidecar_inventory_policy=inventory_policy,
            )
            if checked_after != report_path:
                raise EvidenceInvalid("transient report path changed after write")
        except BaseException as post_error:  # noqa: BLE001 - demote durable PASS
            recovery_error: BaseException | None = None
            if isinstance(value, dict):
                value["verdict"] = "invalid"
                value["fatal_error"] = _exception_text(post_error)
                try:
                    if (
                        _preflight_transient_output_paths(
                            quality.output_dir,
                            serial,
                            sidecar_inventory_policy="partial",
                        )
                        != report_path
                    ):
                        raise EvidenceInvalid(
                            "transient report path changed during invalid recovery"
                        )
                    report_writer(report_path, value)
                except BaseException as error:  # noqa: BLE001
                    recovery_error = error
            if recovery_error is not None:
                raise BaseExceptionGroup(
                    "transient output recheck and invalid-report recovery failed",
                    [post_error, recovery_error],
                )
            raise post_error.with_traceback(post_error.__traceback__)

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
        "schema": "plutosdr-fw.tandem-agc-transient.v2",
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
            "tandem_transport": {
                "provider_frame_samples": _TANDEM_FRAME_SAMPLES,
                "kernel_buffers": _TANDEM_KERNEL_BUFFERS,
                "batch_frames": _TANDEM_BATCH_FRAMES,
                "queue_capacity_frames": _TANDEM_CAPTURE_QUEUE_FRAMES,
                "metadata_abi": 2,
            },
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
        "failure_evidence": None,
        "verdict": "running",
    }
    write_report(report)
    campaign_error: BaseException | None = None
    try:
        for mode in TRANSIENT_MODES:
            check_deadline()
            failed_mode: dict[str, Any] = {}

            def preserve_failed_mode(
                value: Mapping[str, Any], sink: dict[str, Any] = failed_mode
            ) -> None:
                # Keep the progressively populated object in memory while the
                # batch is active.  The enclosing failure path writes it only
                # after mute/cancel/join/close have completed.
                sink.clear()
                sink.update(value)

            try:
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
                    failure_sink=(
                        preserve_failed_mode if mode == MODE_TANDEM else None
                    ),
                )
            except BaseException:
                if failed_mode:
                    report["failure_evidence"] = failed_mode
                    report["modes"].append(failed_mode)
                raise
            report["modes"].append(mode_record)
            write_report(report)
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
        write_report(report)
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
    expected_report_path = _preflight_transient_output_paths(
        quality.output_dir, radio_options.serial
    )
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
            if (
                _preflight_transient_output_paths(
                    quality.output_dir,
                    radio_options.serial,
                    sidecar_inventory_policy="partial",
                )
                != expected_report_path
            ):
                raise EvidenceInvalid(
                    "post-close transient report path changed after preflight"
                )
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
                if parsed.get("verdict") == "pass":
                    _preflight_transient_output_paths(
                        quality.output_dir,
                        radio_options.serial,
                        sidecar_inventory_policy="complete",
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
