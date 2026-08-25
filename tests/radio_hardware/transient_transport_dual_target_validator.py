"""Durable validator for the weak-only dual-target transport preflight.

This module deliberately does not import validation helpers from the capture
runtime.  Reported JSON is treated as an untrusted index into the exact 128
sidecars; the validator rereads, reparses, and reanalyses those artifacts and
reconstructs the qualification ledgers from that independent evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import statistics
import struct
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any

from .experiment import TX_MUTE_DB, EvidenceInvalid, FixtureSafetyError
from .metadata_abi import (
    FEATURE_AD9361_TEMPERATURE,
    FEATURE_FPGA_GAIN_EVENTS,
    FEATURE_HARDWARE_SAMPLE_COUNTER,
    FEATURE_TANDEM_METADATA,
    FLAG_HARDWARE_SAMPLE_COUNTER_VALID,
    FLAG_SAMPLE_SEQUENCE_VALID,
    FLAG_TANDEM_METADATA_VALID,
    GAIN_OBSERVATION_BYTES,
    TANDEM_REQUEST,
    TANDEM_UNSAFE_FLAGS,
    V5_PREFIX_BYTES,
    TandemFrameMetadata,
    TandemMode,
    TandemState,
    build_tandem_request,
    maximum_tandem_events_per_frame,
    parse_tandem_frame_metadata,
)
from .tandem_quality import TandemQualityOptions, expected_tandem_gain_table
from .transient_quality import analyze_immediate_dual_rx

_SCHEMA = "plutosdr-fw.tandem-agc-transient-transport-probe.v4"
_PROBE_MODE = "weak_dual_target_transport"
_MODE = "tandem_auto"
_MODE_PROFILE = "weak_dual_target_transport"
_MODE_VERDICT = "qualified_transport"
_PENDING_VERDICT = "qualified_transport_pending_cleanup"
_FINAL_VERDICT = "qualified_transport"
_SERIAL = "1040007c4a94000211000b009186843ef2"
_FRAME_SAMPLES = 65_536
_FRAME_BYTES = _FRAME_SAMPLES * 8
_KERNEL_BUFFERS = 8
_BATCH_FRAMES = 64
_QUEUE_FRAMES = 4
_METADATA_CAPACITY_BYTES = 65_536
_METADATA_HEADER_BYTES = 3_256
_BATCH_CACHE_BYTES = 37_749_760
_WINDOW_SAMPLES = 1_024
_ANCHOR_SAMPLES = 8_192
_INITIAL_GAIN_DB = 62
_MINIMUM_GAIN_INDEX = 3
_MAXIMUM_GAIN_INDEX = 65
_COMMAND_LEVEL_DB = -45.0
_COMMAND_SPECS = (
    ("weak_reassertion_16f", 16),
    ("weak_reassertion_40f", 40),
)
_ARTIFACT_DIRECTORY = "weak_dual_target"
_ARTIFACT_POLICY = "mandatory_exact_weak_dual_target_preflight_sidecars"
_PHASES = (
    "fully_pre_first",
    "first_command_bracket",
    "fully_between_commands",
    "second_command_bracket",
    "fully_post_second",
)
_STABLE_PHASES = (
    "fully_pre_first",
    "fully_between_commands",
    "fully_post_second",
)
_MINIMUM_PHASE_FRAMES = 8
_UINT32 = 1 << 32
_UINT64 = 1 << 64
_MAX_OVERSHOOT = 16_384
_MAX_UNCERTAINTY = 16_384
_MAX_PROVENANCE_FILE_BYTES = 64 * 1024 * 1024
_GAIN_OBSERVATION = struct.Struct("<QQIHBBbbHI")
_GAIN_OBSERVATION_FLAGS = 0x0003
_GAIN_OBSERVATION_CAPACITY = 64
_PROVIDER_OBSERVATION_INTERVAL_SAMPLES = _FRAME_SAMPLES // 4
assert _GAIN_OBSERVATION.size == GAIN_OBSERVATION_BYTES
_REQUIRED_FEATURES = (
    FEATURE_AD9361_TEMPERATURE
    | FEATURE_FPGA_GAIN_EVENTS
    | FEATURE_HARDWARE_SAMPLE_COUNTER
    | FEATURE_TANDEM_METADATA
)
_EXACT_METADATA_FEATURES = 0x000003FF
_REQUIRED_FLAGS = (
    FLAG_SAMPLE_SEQUENCE_VALID
    | FLAG_HARDWARE_SAMPLE_COUNTER_VALID
    | FLAG_TANDEM_METADATA_VALID
)
_EXACT_METADATA_FLAGS = (
    _REQUIRED_FLAGS
    | (1 << 0)  # valid start endpoint
    | (1 << 1)  # valid end endpoint
    | (1 << 10)  # full gain table
    | (1 << 15)  # valid start RSSI
    | (1 << 16)  # valid end RSSI
    | (1 << 18)  # gain-dB endpoints
    | (1 << 19)  # gain-observation series
)
_FORBIDDEN_CHANGE_FLAGS = (1 << 2) | (1 << 3) | (1 << 6) | (1 << 7)
_PROJECTION_SCHEMA = "plutosdr-fw.tandem-evidence-projection.v1"
_PROJECTION_METHOD = (
    "canonical-json-v1: finished tandem mode with attestation value fields "
    "replaced by fixed sentinels plus 64 normalized reparsed metadata records"
)
_PARSED_RESERVATION_BYTES = 8 * 1024 * 1024
_FFT_WORKSPACE_BYTES = 8 * 1024 * 1024
_MAXIMUM_AGGREGATE_BYTES = 96 * 1024 * 1024
_QUALIFICATION_SCOPE = (
    "weak-only tandem AUTO dual-target transport, ordering, retention, "
    "provenance, RF-stability, and cleanup evidence; no commanded loudness "
    "step, gain-transient, response, or latency qualification"
)
_LIBIIO_COMMIT = "70739d25ec1fa7b95d9069bd26a3e4192fdb3851"
_LIBIIO_TAG = "tandem-agc-v8-rc3-source/libiio-v1"
_LIBIIO_REF = f"refs/tags/{_LIBIIO_TAG}"
_MANIFEST_PATH = "manifests/tandem-agc-v8-rc3-source.yaml"
_RUNTIME_DEPENDENCIES = (
    "pytest.ini",
    "scripts/run_tandem_agc_quality_hardware.sh",
    _MANIFEST_PATH,
    "tests/__init__.py",
    "tests/radio_hardware/__init__.py",
    "tests/radio_hardware/conftest.py",
    "tests/radio_hardware/continuity.py",
    "tests/radio_hardware/experiment.py",
    "tests/radio_hardware/metadata_abi.py",
    "tests/radio_hardware/pnxx.py",
    "tests/radio_hardware/requirements.txt",
    "tests/radio_hardware/tandem_quality.py",
    "tests/radio_hardware/test_transient_transport_probe.py",
    "tests/radio_hardware/test_transient_transport_dual_target_probe.py",
    "tests/radio_hardware/tone_quality.py",
    "tests/radio_hardware/transient_hardware.py",
    "tests/radio_hardware/transient_quality.py",
    "tests/radio_hardware/transient_transport_dual_target_validator.py",
    "tests/radio_hardware/transient_transport_probe.py",
)
_MODE_SCOPE = (
    "weak-only same-level dual-target transport, ordering, retention, "
    "provenance, RF-stability, and cleanup evidence; no gain-transient or "
    "latency qualification"
)
_SHA256 = re.compile(r"[0-9a-f]{64}")

_FRAME_FIELDS = {
    "analysis",
    "artifact_policy",
    "artifact_write_status",
    "batch_phase",
    "command_boundary_gap_allowed",
    "continuity",
    "first_sample_sequence",
    "frame_index",
    "gap_context",
    "iq_bytes",
    "iq_path",
    "metadata",
    "physical_sample_continuity_proven",
    "raw_metadata_bytes",
    "raw_metadata_path",
    "raw_metadata_sha256",
    "refill_monotonic_ns",
    "sample_end_exclusive",
    "sample_gap_before",
    "sha256",
    "timing_basis",
}
_METADATA_FIELDS = {
    "version",
    "header_bytes",
    "features",
    "stream_id",
    "buffer_sequence",
    "first_sample_sequence",
    "samples_per_channel",
    "iq_payload_bytes",
    "enabled_scan_mask",
    "flags",
    "sample_format",
    "channel_count",
    "observation_count",
    "observation_capacity",
    "event_capacity",
    "ownership_epoch",
    "tandem_state",
    "tandem_state_name",
    "tandem_fault_flags",
    "tandem_transition_count",
    "gain_table_id",
    "threshold_provenance",
    "gain_db_range",
    "initial_gain_db",
    "gain_index_range",
    "bench_gain_indices",
    "rx1_gain_index",
    "rx2_gain_index",
    "event_count",
    "observation_overflow_count",
    "event_overflow_count",
    "temperature_mdeg_c",
    "gain_event_count",
    "gain_events",
}
_CONTINUITY_FIELDS = {
    "buffer_delta",
    "sample_delta",
    "missing_frame_count",
    "sample_gap_before",
    "provider_gap_accepted",
    "gap_context",
    "command_boundary_gap_allowed",
    "transition_count_delta",
    "visible_event_count",
    "hidden_transition_count",
    "initial_unrepresented_transition_count",
    "cumulative_missing_frame_count",
    "cumulative_hidden_transition_count",
    "cumulative_event_sequence_hole_count",
}


def _fail(message: str) -> None:
    raise EvidenceInvalid("weak dual-target durable evidence: " + message)


def _exact_int(value: Any, *, minimum: int = 0, maximum: int | None = None) -> int:
    if (
        type(value) is not int
        or value < minimum
        or (maximum is not None and value > maximum)
    ):
        _fail("expected an exact bounded integer")
    return value


def _finite(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("expected a finite number")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        _fail("expected a finite number")
    if not math.isfinite(result):
        _fail("expected a finite number")
    return result


def _mapping(value: Any, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
        _fail(f"{name} is not a JSON object")
    return value


def _list(value: Any, *, name: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(f"{name} is not a JSON array")
    return value


def _exact_fields(value: Mapping[str, Any], fields: set[str], *, name: str) -> None:
    if set(value) != fields:
        _fail(f"{name} fields changed")


def _json_identical(value: Any, expected: Any) -> bool:
    if type(value) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(value) == set(expected) and all(
            _json_identical(value[key], expected[key]) for key in expected
        )
    if isinstance(expected, list):
        return len(value) == len(expected) and all(
            _json_identical(left, right)
            for left, right in zip(value, expected, strict=True)
        )
    return value == expected


def _json_domain(value: Any) -> Any:
    """Copy an acyclic finite JSON graph while rejecting hostile numerics."""

    seen: set[int] = set()
    nodes = 0

    def visit(item: Any, depth: int) -> Any:
        nonlocal nodes
        nodes += 1
        if nodes > 1_000_000 or depth > 128:
            _fail("JSON evidence exceeds its structural bound")
        if item is None or type(item) in {str, bool}:
            return item
        if type(item) is int:
            _finite(item)
            return item
        if type(item) is float:
            _finite(item)
            return item
        if isinstance(item, Mapping):
            identity = id(item)
            if identity in seen:
                _fail("JSON evidence contains a cycle")
            seen.add(identity)
            try:
                if any(type(key) is not str for key in item):
                    _fail("JSON object contains a non-string key")
                return {key: visit(child, depth + 1) for key, child in item.items()}
            finally:
                seen.remove(identity)
        if isinstance(item, list):
            identity = id(item)
            if identity in seen:
                _fail("JSON evidence contains a cycle")
            seen.add(identity)
            try:
                return [visit(child, depth + 1) for child in item]
            finally:
                seen.remove(identity)
        _fail("evidence contains a non-JSON value")

    return visit(value, 0)


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


def _expected_threshold_provenance(quality: TandemQualityOptions) -> int:
    return (
        quality.tandem_low_power_threshold
        | quality.tandem_large_lmt_overload_threshold << 8
        | quality.tandem_large_adc_overload_threshold << 16
        | quality.tandem_small_adc_overload_threshold << 24
    )


def _expected_request(quality: TandemQualityOptions) -> dict[str, Any]:
    request = build_tandem_request(
        mode=TandemMode.AUTO,
        initial_gain_db=_INITIAL_GAIN_DB,
        power_measurement_samples=quality.tandem_power_measurement_samples,
        low_power_dwell_periods=quality.tandem_low_power_dwell_periods,
        cooldown_periods=quality.tandem_cooldown_periods,
        low_power_threshold=quality.tandem_low_power_threshold,
        large_lmt_overload_threshold=quality.tandem_large_lmt_overload_threshold,
        large_adc_overload_threshold=quality.tandem_large_adc_overload_threshold,
        small_adc_overload_threshold=quality.tandem_small_adc_overload_threshold,
        samples_per_channel=_FRAME_SAMPLES,
    )
    names = (
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
        *(f"reserved_{index}" for index in range(8)),
    )
    decoded = dict(zip(names, TANDEM_REQUEST.unpack(request), strict=True))
    return {
        "wire_bytes": len(request),
        "wire_hex": request.hex(),
        "sha256": hashlib.sha256(request).hexdigest(),
        "decoded": decoded,
    }


def _safe_serial(value: Any) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 128
        or value in {".", ".."}
        or not value[0].isalnum()
        or any(not (character.isalnum() or character in "._-") for character in value)
    ):
        _fail("serial is not one safe path component")
    return value


def _trusted_root(phase_root: Path, quality: TandemQualityOptions) -> Path:
    root = Path(phase_root).absolute()
    configured = Path(quality.output_dir).absolute()
    current = Path(root.anchor)
    ancestor_symlink = False
    for part in root.parts[1:]:
        current /= part
        if current.is_symlink():
            ancestor_symlink = True
            break
    if root != configured or ancestor_symlink or root.is_symlink() or not root.is_dir():
        _fail("phase root is not the configured non-symlink output directory")
    return root


def _safe_sidecar_path(
    root: Path, relative: Any, expected: str, *, expected_bytes: int
) -> Path:
    if type(relative) is not str or relative != expected:
        _fail("sidecar relative path changed")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        _fail("sidecar path is not canonical relative POSIX")
    current = root
    for part in pure.parts:
        current /= part
        if current.is_symlink():
            _fail("sidecar path contains a symlink")
    try:
        current.absolute().relative_to(root)
        current.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise EvidenceInvalid(
            "weak dual-target sidecar escapes its trusted root"
        ) from error
    try:
        before = current.stat()
    except OSError as error:
        raise EvidenceInvalid("weak dual-target sidecar cannot be stated") from error
    if not stat.S_ISREG(before.st_mode) or before.st_size != expected_bytes:
        _fail("sidecar is not a regular file of the exact expected size")
    return current


def _read_exact(path: Path, expected_bytes: int, *, root: Path) -> bytes:
    descriptor: int | None = None
    try:
        before = path.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_size != expected_bytes:
            _fail("sidecar size changed before read")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_size != expected_bytes
            or opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
        ):
            _fail("sidecar target changed before bounded read")
        chunks: list[bytes] = []
        remaining = expected_bytes + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = path.stat()
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except OSError as error:
        raise EvidenceInvalid("weak dual-target sidecar read failed") from error
    except ValueError as error:
        raise EvidenceInvalid("weak dual-target sidecar escaped during read") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        len(payload) != expected_bytes
        or before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        _fail("sidecar changed during bounded read")
    return payload


def _analysis(raw: bytes, first: int, quality: TandemQualityOptions) -> dict[str, Any]:
    return dict(
        analyze_immediate_dual_rx(
            raw,
            first_sample_sequence=first,
            sample_rate_hz=quality.sample_rate_hz,
            expected_tone_hz=quality.tone_hz,
            window_samples=_WINDOW_SAMPLES,
            min_tone_snr_db=quality.thresholds.min_tone_snr_db,
            max_clipping_fraction=quality.thresholds.max_clipping_fraction,
            max_phase_std_deg=quality.thresholds.max_phase_std_deg,
        )
    )


def _expected_continuity(index: int, phase: str) -> dict[str, Any]:
    return {
        "buffer_delta": None if index == 0 else 1,
        "sample_delta": None if index == 0 else _FRAME_SAMPLES,
        "missing_frame_count": 0,
        "sample_gap_before": 0,
        "provider_gap_accepted": False,
        "gap_context": phase,
        "command_boundary_gap_allowed": False,
        "transition_count_delta": None if index == 0 else 0,
        "visible_event_count": 0,
        "hidden_transition_count": 0,
        "initial_unrepresented_transition_count": 0,
        "cumulative_missing_frame_count": 0,
        "cumulative_hidden_transition_count": 0,
        "cumulative_event_sequence_hole_count": 0,
    }


def _validate_gain_observation_wire(
    payload: bytes,
    metadata: TandemFrameMetadata,
    *,
    index: int,
) -> tuple[tuple[int, ...], ...]:
    """Validate the observation array omitted by ``metadata_abi``'s parser."""

    if (
        len(payload) != _METADATA_HEADER_BYTES
        or metadata.observation_capacity != _GAIN_OBSERVATION_CAPACITY
        or not 1 <= metadata.observation_count <= 5
    ):
        _fail(f"frame {index} has an invalid gain-observation wire layout")
    try:
        (
            rx1_db_start,
            rx2_db_start,
            rx1_db_end,
            rx2_db_end,
            prefix_reserved,
            start_read_duration_ns,
            end_read_duration_ns,
            rx1_first_change_sample,
            rx2_first_change_sample,
            rx1_rssi_start_qdb,
            rx2_rssi_start_qdb,
            rx1_rssi_end_qdb,
            rx2_rssi_end_qdb,
            _rssi_start_read_duration_ns,
            _rssi_end_read_duration_ns,
            provider_interval,
        ) = struct.unpack_from("<bbbbBIIIIHHHHIII", payload, 55)
        prefix_reserved1, prefix_reserved2 = struct.unpack_from("<II", payload, 116)
    except struct.error as error:
        raise EvidenceInvalid(
            f"frame {index} gain-observation prefix is truncated"
        ) from error
    if provider_interval != _PROVIDER_OBSERVATION_INTERVAL_SAMPLES:
        _fail(f"frame {index} provider observation interval changed")

    frame_start = metadata.first_sample_sequence
    frame_end = frame_start + metadata.samples_per_channel
    previous_after: int | None = None
    previous_before: int | None = None
    observations: list[tuple[int, ...]] = []
    for slot in range(_GAIN_OBSERVATION_CAPACITY):
        offset = V5_PREFIX_BYTES + slot * _GAIN_OBSERVATION.size
        record_bytes = payload[offset : offset + _GAIN_OBSERVATION.size]
        if len(record_bytes) != _GAIN_OBSERVATION.size:
            _fail(f"frame {index} gain-observation array is truncated")
        if slot >= metadata.observation_count:
            if any(record_bytes):
                _fail(f"frame {index} has a nonzero unused observation slot")
            continue
        try:
            record = _GAIN_OBSERVATION.unpack(record_bytes)
        except struct.error as error:
            raise EvidenceInvalid(
                f"frame {index} gain observation {slot} cannot be decoded"
            ) from error
        (
            sample_before,
            sample_after,
            _read_duration_ns,
            flags,
            rx1_gain_index,
            rx2_gain_index,
            rx1_gain_db,
            rx2_gain_db,
            reserved0,
            reserved1,
        ) = record
        if (
            flags != _GAIN_OBSERVATION_FLAGS
            or reserved0 != 0
            or reserved1 != 0
            or rx1_gain_index != metadata.maximum_gain_index
            or rx2_gain_index != metadata.maximum_gain_index
            or rx1_gain_db != metadata.maximum_gain_db
            or rx2_gain_db != metadata.maximum_gain_db
            or sample_before > sample_after
            or sample_after < frame_start
            or sample_before >= frame_end
            or (previous_after is not None and sample_before < previous_after)
            or (
                previous_before is not None
                and sample_before - previous_before
                < _PROVIDER_OBSERVATION_INTERVAL_SAMPLES
            )
        ):
            _fail(f"frame {index} gain observation {slot} violates provenance")
        previous_after = sample_after
        previous_before = sample_before
        observations.append(record)

    first = observations[0]
    last = observations[-1]
    if (
        prefix_reserved != 0
        or prefix_reserved1 != 0
        or prefix_reserved2 != 0
        or rx1_first_change_sample != _UINT32 - 1
        or rx2_first_change_sample != _UINT32 - 1
        or 0xFFFF
        in {
            rx1_rssi_start_qdb,
            rx2_rssi_start_qdb,
            rx1_rssi_end_qdb,
            rx2_rssi_end_qdb,
        }
        or (rx1_db_start, rx2_db_start, rx1_db_end, rx2_db_end)
        != (metadata.maximum_gain_db,) * 4
        or start_read_duration_ns != first[2]
        or end_read_duration_ns != last[2]
    ):
        _fail(f"frame {index} endpoint prefix differs from observation wire")
    return tuple(observations)


def _validate_metadata(
    metadata: TandemFrameMetadata,
    *,
    index: int,
    first: TandemFrameMetadata | None,
    quality: TandemQualityOptions,
) -> None:
    maximum_events = maximum_tandem_events_per_frame(
        mode=TandemMode.AUTO,
        samples_per_channel=_FRAME_SAMPLES,
        power_measurement_samples=quality.tandem_power_measurement_samples,
        cooldown_periods=quality.tandem_cooldown_periods,
    )
    if (
        metadata.version != 5
        or metadata.header_bytes != _METADATA_HEADER_BYTES
        or metadata.features != _EXACT_METADATA_FEATURES
        or metadata.flags != _EXACT_METADATA_FLAGS
        or metadata.flags & _FORBIDDEN_CHANGE_FLAGS
        or metadata.flags & TANDEM_UNSAFE_FLAGS
        or metadata.samples_per_channel != _FRAME_SAMPLES
        or metadata.iq_payload_bytes != _FRAME_BYTES
        or metadata.enabled_scan_mask != 0x0F
        or metadata.sample_format != 1
        or metadata.channel_count != 2
        or metadata.observation_capacity != 64
        or metadata.event_capacity != 64
        or not 1 <= metadata.observation_count <= 5
        or not 0 <= metadata.event_count <= maximum_events
        or metadata.event_count != len(metadata.gain_events)
        or metadata.ownership_epoch <= 0
        or metadata.tandem_state is not TandemState.ARMED_AUTO
        or metadata.tandem_fault_flags != 0
        or metadata.tandem_transition_count != 0
        or metadata.observation_overflow_count != 0
        or metadata.event_overflow_count != 0
        or metadata.gain_events
        or int(metadata.gain_table_id)
        != int(expected_tandem_gain_table(quality.center_frequency_hz))
        or (metadata.minimum_gain_db, metadata.maximum_gain_db) != (0, 62)
        or metadata.initial_gain_db != _INITIAL_GAIN_DB
        or (metadata.minimum_gain_index, metadata.maximum_gain_index)
        != (_MINIMUM_GAIN_INDEX, _MAXIMUM_GAIN_INDEX)
        or metadata.threshold_provenance != _expected_threshold_provenance(quality)
        or metadata.rx1_gain_index != metadata.maximum_gain_index
        or metadata.rx2_gain_index != metadata.maximum_gain_index
        or type(metadata.ad9361_temperature_mdeg_c) is not int
    ):
        _fail(f"frame {index} metadata violates the weak transport contract")
    if first is None:
        if metadata.buffer_sequence != 0 or metadata.stream_id <= 0:
            _fail("first metadata record is not a fresh provider stream")
    elif (
        metadata.buffer_sequence != index
        or metadata.stream_id != first.stream_id
        or metadata.ownership_epoch != first.ownership_epoch
        or metadata.first_sample_sequence
        != first.first_sample_sequence + index * _FRAME_SAMPLES
        or metadata.features != first.features
        or metadata.minimum_gain_index != first.minimum_gain_index
        or metadata.maximum_gain_index != first.maximum_gain_index
    ):
        _fail(f"frame {index} metadata is not contiguous in one stream/epoch")


def _inventory(root: Path, serial: str) -> None:
    directory = root / serial / "transient-iq" / _ARTIFACT_DIRECTORY / "batch"
    current = root
    for part in (serial, "transient-iq", _ARTIFACT_DIRECTORY, "batch"):
        current /= part
        if current.is_symlink() or not current.is_dir():
            _fail("sidecar directory contains a symlink or is missing")
    expected = {
        *(f"frame-{index:04d}.cs16" for index in range(_BATCH_FRAMES)),
        *(f"frame-{index:04d}.metadata.bin" for index in range(_BATCH_FRAMES)),
    }
    try:
        entries = list(directory.iterdir())
    except OSError as error:
        raise EvidenceInvalid(
            "weak dual-target sidecar inventory cannot be read"
        ) from error
    if (
        {entry.name for entry in entries} != expected
        or len(entries) != 2 * _BATCH_FRAMES
        or any(entry.is_symlink() or not entry.is_file() for entry in entries)
    ):
        _fail("sidecar directory does not contain the exact 128-file inventory")


def _load_frames(
    value: Any,
    *,
    phases: Sequence[str],
    quality: TandemQualityOptions,
    root: Path,
    serial: str,
) -> tuple[list[Mapping[str, Any]], list[bytes], list[TandemFrameMetadata]]:
    frames = _list(value, name="batch_frames")
    if len(frames) != _BATCH_FRAMES or len(phases) != _BATCH_FRAMES:
        _fail("batch does not contain exactly 64 partitioned frames")
    _inventory(root, serial)
    typed: list[Mapping[str, Any]] = []
    raw_frames: list[bytes] = []
    parsed: list[TandemFrameMetadata] = []
    previous_observations: tuple[tuple[int, ...], ...] | None = None
    seen_observations: set[tuple[int, ...]] = set()
    last_distinct_observation_before: int | None = None
    first_metadata: TandemFrameMetadata | None = None
    previous_refill = -1
    for index, item in enumerate(frames):
        frame = _mapping(item, name=f"frame {index}")
        _exact_fields(frame, _FRAME_FIELDS, name=f"frame {index}")
        phase = phases[index]
        first = _exact_int(frame.get("first_sample_sequence"), maximum=_UINT64 - 1)
        end = _exact_int(frame.get("sample_end_exclusive"), minimum=1, maximum=_UINT64)
        refill = _exact_int(frame.get("refill_monotonic_ns"))
        if (
            frame.get("frame_index") != index
            or type(frame.get("frame_index")) is not int
            or frame.get("iq_bytes") != _FRAME_BYTES
            or type(frame.get("iq_bytes")) is not int
            or end != first + _FRAME_SAMPLES
            or refill < previous_refill
            or frame.get("timing_basis") != "hardware_sample_counter"
            or frame.get("physical_sample_continuity_proven") is not True
            or frame.get("batch_phase") != phase
            or frame.get("gap_context") != phase
            or frame.get("command_boundary_gap_allowed") is not False
            or not _json_identical(frame.get("sample_gap_before"), 0)
            or frame.get("artifact_policy") != _ARTIFACT_POLICY
            or not _json_identical(
                frame.get("artifact_write_status"),
                {
                    "iq_write_completed": True,
                    "raw_metadata_write_completed": True,
                },
            )
        ):
            _fail(f"frame {index} capture/provenance ledger changed")
        previous_refill = refill
        expected_prefix = f"{serial}/transient-iq/{_ARTIFACT_DIRECTORY}/batch"
        iq_relative = f"{expected_prefix}/frame-{index:04d}.cs16"
        md_relative = f"{expected_prefix}/frame-{index:04d}.metadata.bin"
        iq_path = _safe_sidecar_path(
            root, frame.get("iq_path"), iq_relative, expected_bytes=_FRAME_BYTES
        )
        md_path = _safe_sidecar_path(
            root,
            frame.get("raw_metadata_path"),
            md_relative,
            expected_bytes=_METADATA_HEADER_BYTES,
        )
        if (
            frame.get("raw_metadata_bytes") != _METADATA_HEADER_BYTES
            or type(frame.get("raw_metadata_bytes")) is not int
        ):
            _fail(f"frame {index} raw metadata byte count changed")
        raw = _read_exact(iq_path, _FRAME_BYTES, root=root)
        raw_metadata = _read_exact(md_path, _METADATA_HEADER_BYTES, root=root)
        if (
            _SHA256.fullmatch(str(frame.get("sha256"))) is None
            or hashlib.sha256(raw).hexdigest() != frame.get("sha256")
            or _SHA256.fullmatch(str(frame.get("raw_metadata_sha256"))) is None
            or hashlib.sha256(raw_metadata).hexdigest()
            != frame.get("raw_metadata_sha256")
        ):
            _fail(f"frame {index} sidecar digest changed")
        try:
            metadata = parse_tandem_frame_metadata(raw_metadata)
        except (TypeError, ValueError) as error:
            raise EvidenceInvalid(
                f"weak dual-target frame {index} metadata cannot be reparsed"
            ) from error
        if metadata.header_bytes != len(raw_metadata):
            _fail(f"frame {index} metadata length differs from its header")
        observations = _validate_gain_observation_wire(
            raw_metadata, metadata, index=index
        )
        if previous_observations is not None:
            inherited = tuple(
                record
                for record in observations
                if record[0] < metadata.first_sample_sequence
            )
            retained = tuple(
                record
                for record in previous_observations
                if record[1] >= metadata.first_sample_sequence
            )
            if inherited != retained:
                _fail(f"frame {index} observation boundary retention changed")
        for record in observations:
            if record in seen_observations:
                continue
            if (
                last_distinct_observation_before is not None
                and record[0] - last_distinct_observation_before
                < _PROVIDER_OBSERVATION_INTERVAL_SAMPLES
            ):
                _fail(f"frame {index} global observation cadence changed")
            seen_observations.add(record)
            last_distinct_observation_before = record[0]
        previous_observations = observations
        _validate_metadata(metadata, index=index, first=first_metadata, quality=quality)
        if first_metadata is None:
            first_metadata = metadata
        normalized = _metadata_dict(metadata)
        reported_metadata = _mapping(
            frame.get("metadata"), name=f"frame {index} metadata"
        )
        _exact_fields(
            reported_metadata, _METADATA_FIELDS, name=f"frame {index} metadata"
        )
        if not _json_identical(dict(reported_metadata), normalized):
            _fail(f"frame {index} metadata differs from raw sidecar")
        if first != metadata.first_sample_sequence:
            _fail(f"frame {index} IQ bounds differ from raw metadata")
        continuity = _mapping(frame.get("continuity"), name=f"frame {index} continuity")
        _exact_fields(continuity, _CONTINUITY_FIELDS, name=f"frame {index} continuity")
        if not _json_identical(dict(continuity), _expected_continuity(index, phase)):
            _fail(f"frame {index} continuity differs from recomputation")
        recomputed = _analysis(raw, first, quality)
        if recomputed.get("quality_valid") is not True or any(
            not isinstance(window, Mapping) or window.get("quality_valid") is not True
            for window in recomputed.get("windows", [])
        ):
            _fail(f"frame {index} contains an invalid RF analysis window")
        if not _json_identical(frame.get("analysis"), recomputed):
            _fail(f"frame {index} analysis differs from raw IQ recomputation")
        typed.append(frame)
        raw_frames.append(raw)
        parsed.append(metadata)
    _inventory(root, serial)
    return typed, raw_frames, parsed


def _extend_low32(raw: int, reference: int) -> int:
    raw = _exact_int(raw, maximum=_UINT32 - 1)
    reference = _exact_int(reference, maximum=_UINT64 - 1)
    candidate = (reference & ~(_UINT32 - 1)) | raw
    choices = (candidate - _UINT32, candidate, candidate + _UINT32)
    result = min(choices, key=lambda item: abs(item - reference))
    if result < 0 or result >= _UINT64 or abs(result - reference) >= _UINT32 // 2:
        _fail("low32 sample counter is ambiguous around the retained batch")
    return result


def _timestamp_pair(value: Mapping[str, Any], *, name: str) -> tuple[int, int]:
    before = _exact_int(value.get("host_before_ns"))
    after = _exact_int(value.get("host_after_ns"))
    if after < before:
        _fail(f"{name} host clock moved backward")
    return before, after


def _validate_initial_command(
    value: Any, quality: TandemQualityOptions, probe: Any
) -> tuple[int, int]:
    command = _mapping(value, name="initial command")
    fields = {
        "command_id",
        "requested_level_db",
        "applied_level_db",
        "host_before_ns",
        "host_after_ns",
        "host_jitter_ns",
        "sample_sequence_before",
        "sample_sequence_after",
        "sample_uncertainty",
        "effective_attenuation_db",
        "rx_state_before",
        "rx_state_after",
        "timing_role",
        "sample_timing_basis",
        "sample_anchor_policy",
    }
    _exact_fields(command, fields, name="initial command")
    before, after = _timestamp_pair(command, name="initial command")
    requested = _finite(command.get("requested_level_db"))
    applied = _finite(command.get("applied_level_db"))
    tolerance = _finite(getattr(probe, "readback_tolerance_db", None))
    if (
        command.get("command_id") != "weak_initial"
        or type(command.get("requested_level_db")) is not float
        or type(command.get("applied_level_db")) is not float
        or requested != _COMMAND_LEVEL_DB
        or abs(applied - _COMMAND_LEVEL_DB) > tolerance
        or not _json_identical(command.get("host_jitter_ns"), after - before)
        or after - before > _exact_int(getattr(probe, "max_host_jitter_ns", None))
        or command.get("sample_sequence_before") is not None
        or command.get("sample_sequence_after") is not None
        or command.get("sample_uncertainty") is not None
        or not _release_attenuation_matches(
            command.get("effective_attenuation_db"),
            quality.physical_attenuation_db - applied,
        )
        or command.get("rx_state_before") is not None
        or command.get("rx_state_after") is not None
        or command.get("timing_role") != "pre_session_weak_conditioning_write"
        or command.get("sample_timing_basis") is not None
        or command.get("sample_anchor_policy")
        != ("unbounded in hardware sample time; write predates AUTO62 batch ownership")
    ):
        _fail("initial weak conditioning command changed")
    if quality.physical_attenuation_db - applied < 30.0:
        _fail("initial command violates the attenuation boundary")
    return before, after


def _validate_schedule(
    value: Any,
    command: Any,
    *,
    command_id: str,
    target_frames: int,
    s0_raw: int,
    first_batch_sample: int,
    last_batch_sample_exclusive: int,
    initiating_completion_ns: int,
    quality: TandemQualityOptions,
    probe: Any,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Reconstruct one exact S0+target A->initial->B->C state machine."""

    diagnostics = _mapping(value, name=f"{command_id} diagnostics")
    command_record = _mapping(command, name=f"{command_id} command")
    diagnostic_fields = {
        "status",
        "qualified",
        "current_stage",
        "failure_stage",
        "failure_error",
        "command_id",
        "requested_level_db",
        "applied_level_db",
        "target",
        "worker_in_flight_observations",
        "tx1_mute_assurance",
        "write_ack",
        "counter_reads",
        "raw_bracket",
        "deferred_tx2_readback",
    }
    _exact_fields(diagnostics, diagnostic_fields, name=f"{command_id} diagnostics")
    if (
        diagnostics.get("status") != "complete"
        or diagnostics.get("qualified") is not True
        or diagnostics.get("current_stage") != "complete"
        or diagnostics.get("failure_stage") is not None
        or diagnostics.get("failure_error") is not None
        or diagnostics.get("command_id") != command_id
        or type(diagnostics.get("requested_level_db")) is not float
        or _finite(diagnostics.get("requested_level_db")) != _COMMAND_LEVEL_DB
        or not _json_identical(
            diagnostics.get("worker_in_flight_observations"),
            [
                {
                    "stage": "pre_tx1_mute_assurance",
                    "first_refill_in_flight": True,
                },
                {"stage": "exact_tx2_write", "first_refill_in_flight": True},
            ],
        )
    ):
        _fail(f"{command_id} was not exactly qualified in the first refill")

    target = _mapping(diagnostics.get("target"), name=f"{command_id} target")
    target_fields = {
        "s0_raw",
        "offset_frames",
        "offset_samples",
        "target_raw",
        "last_below_raw",
        "raw_a_prewrite",
        "poll_read_count",
        "poll_observations",
        "total_requested_sleep_samples",
        "overshoot_samples",
        "overshoot_limit_samples",
    }
    _exact_fields(target, target_fields, name=f"{command_id} target")
    target_samples = target_frames * _FRAME_SAMPLES
    target_raw = (s0_raw + target_samples) % _UINT32
    raw_p = _exact_int(target.get("last_below_raw"), maximum=_UINT32 - 1)
    raw_a = _exact_int(target.get("raw_a_prewrite"), maximum=_UINT32 - 1)
    polls = _list(target.get("poll_observations"), name=f"{command_id} polls")
    poll_count = _exact_int(target.get("poll_read_count"), minimum=2, maximum=64)
    if (
        not _json_identical(target.get("s0_raw"), s0_raw)
        or not _json_identical(target.get("offset_frames"), target_frames)
        or not _json_identical(target.get("offset_samples"), target_samples)
        or not _json_identical(target.get("target_raw"), target_raw)
        or len(polls) != poll_count
        or not _json_identical(target.get("overshoot_limit_samples"), _MAX_OVERSHOOT)
    ):
        _fail(f"{command_id} frozen target changed")
    total_sleep = 0
    prior_advance = -1
    poll_raw: list[int] = []
    for index, item in enumerate(polls):
        observation = _mapping(item, name=f"{command_id} poll {index}")
        _exact_fields(
            observation,
            {
                "raw",
                "advance_samples",
                "remaining_samples",
                "phase",
                "requested_sleep_samples",
            },
            name=f"{command_id} poll {index}",
        )
        raw = _exact_int(observation.get("raw"), maximum=_UINT32 - 1)
        advance = _exact_int(
            observation.get("advance_samples"), maximum=_UINT32 // 2 - 1
        )
        remaining = _exact_int(observation.get("remaining_samples"))
        requested_sleep = _exact_int(observation.get("requested_sleep_samples"))
        if raw != (s0_raw + advance) % _UINT32 or advance < prior_advance:
            _fail(f"{command_id} poll counter sequence changed")
        prior_advance = advance
        poll_raw.append(raw)
        if index == poll_count - 1:
            expected_remaining, expected_phase, expected_sleep = 0, "target_reached", 0
            if raw != raw_a or advance < target_samples:
                _fail(f"{command_id} final poll is not A")
        else:
            expected_remaining = target_samples - advance
            if expected_remaining <= 0:
                _fail(f"{command_id} reached target before final poll")
            if expected_remaining > _FRAME_SAMPLES:
                expected_phase = "coarse_sleep"
                expected_sleep = expected_remaining - _FRAME_SAMPLES
            elif expected_remaining > 8_192:
                expected_phase, expected_sleep = "fine_sleep", 4_096
            else:
                expected_phase, expected_sleep = "tail_poll", 0
            total_sleep += expected_sleep
        if (
            remaining != expected_remaining
            or observation.get("phase") != expected_phase
            or requested_sleep != expected_sleep
        ):
            _fail(f"{command_id} target polling policy changed")
    if poll_raw[-2] != raw_p or not _json_identical(
        target.get("total_requested_sleep_samples"), total_sleep
    ):
        _fail(f"{command_id} last-below/sleep ledger changed")

    bracket = _mapping(diagnostics.get("raw_bracket"), name=f"{command_id} raw bracket")
    bracket_fields = {
        "register_address",
        "counter_width_bits",
        "counter_source",
        "raw_a_prewrite",
        "raw_post_write_initial",
        "raw_b_first_advance",
        "raw_c_causal_advance",
        "initial_from_a_samples",
        "b_from_initial_samples",
        "c_from_b_samples",
        "post_write_read_count",
        "causal_uncertainty_samples",
        "causal_uncertainty_limit_samples",
        "worker_in_flight_at_command",
    }
    _exact_fields(bracket, bracket_fields, name=f"{command_id} raw bracket")
    raw_initial = _exact_int(bracket.get("raw_post_write_initial"), maximum=_UINT32 - 1)
    raw_b = _exact_int(bracket.get("raw_b_first_advance"), maximum=_UINT32 - 1)
    raw_c = _exact_int(bracket.get("raw_c_causal_advance"), maximum=_UINT32 - 1)
    initial_delta = (raw_initial - raw_a) % _UINT32
    b_delta = (raw_b - raw_initial) % _UINT32
    c_delta = (raw_c - raw_b) % _UINT32
    uncertainty = initial_delta + b_delta + c_delta
    post_count = _exact_int(bracket.get("post_write_read_count"), minimum=3, maximum=9)
    if (
        bracket.get("register_address") != "0x800000b8"
        or not _json_identical(bracket.get("counter_width_bits"), 32)
        or bracket.get("counter_source") != "coherent FPGA RX sample counter low word"
        or not _json_identical(bracket.get("raw_a_prewrite"), raw_a)
        or initial_delta >= _UINT32 // 2
        or not 0 < b_delta < _UINT32 // 2
        or not 0 < c_delta < _UINT32 // 2
        or not _json_identical(bracket.get("initial_from_a_samples"), initial_delta)
        or not _json_identical(bracket.get("b_from_initial_samples"), b_delta)
        or not _json_identical(bracket.get("c_from_b_samples"), c_delta)
        or not _json_identical(bracket.get("causal_uncertainty_samples"), uncertainty)
        or not _json_identical(
            bracket.get("causal_uncertainty_limit_samples"), _MAX_UNCERTAINTY
        )
        or not 0 < uncertainty <= _MAX_UNCERTAINTY
        or bracket.get("worker_in_flight_at_command") is not True
    ):
        _fail(f"{command_id} raw causal bracket changed")
    overshoot = ((raw_a - s0_raw) % _UINT32) - target_samples
    if not 0 <= overshoot <= _MAX_OVERSHOOT or not _json_identical(
        target.get("overshoot_samples"), overshoot
    ):
        _fail(f"{command_id} target overshoot changed")

    s0 = _extend_low32(s0_raw, first_batch_sample)
    target_sample = s0 + target_samples
    extended_p = s0 + (raw_p - s0_raw) % _UINT32
    extended_a = s0 + (raw_a - s0_raw) % _UINT32
    extended_initial = extended_a + initial_delta
    extended_b = extended_initial + b_delta
    extended_c = extended_b + c_delta
    if not (
        first_batch_sample <= target_sample < last_batch_sample_exclusive
        and target_sample <= extended_a < extended_c <= last_batch_sample_exclusive
    ):
        _fail(f"{command_id} does not lie inside the retained batch")

    command_fields = {
        "command_id",
        "requested_level_db",
        "applied_level_db",
        "host_before_ns",
        "host_after_ns",
        "host_jitter_ns",
        "sample_sequence_before",
        "sample_sequence_after",
        "sample_uncertainty",
        "effective_attenuation_db",
        "rx_state_before",
        "rx_state_after",
        "timing_role",
        "sample_timing_basis",
        "sample_anchor_policy",
        "sample_counter_bracket",
    }
    _exact_fields(command_record, command_fields, name=f"{command_id} command")
    expected_bound = {
        "register_address": "0x800000b8",
        "counter_width_bits": 32,
        "counter_source": "coherent FPGA RX sample counter low word",
        "first_batch_sample": first_batch_sample,
        "last_batch_sample_exclusive": last_batch_sample_exclusive,
        "post_open_s0_raw": s0_raw,
        "post_open_s0_sample": s0,
        "target_offset_frames": target_frames,
        "target_offset_samples": target_samples,
        "target_raw": target_raw,
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
        "target_overshoot_limit_samples": _MAX_OVERSHOOT,
        "causal_uncertainty_samples": uncertainty,
        "causal_uncertainty_limit_samples": _MAX_UNCERTAINTY,
        "command_interval": "[A,C)",
    }
    if (
        command_record.get("command_id") != command_id
        or type(command_record.get("requested_level_db")) is not float
        or _finite(command_record.get("requested_level_db")) != _COMMAND_LEVEL_DB
        or not _json_identical(command_record.get("sample_sequence_before"), extended_a)
        or not _json_identical(command_record.get("sample_sequence_after"), extended_c)
        or not _json_identical(command_record.get("sample_uncertainty"), uncertainty)
        or command_record.get("rx_state_before") is not None
        or command_record.get("rx_state_after") is not None
        or command_record.get("timing_role")
        != "s0_targeted_one_write_bracketed_by_coherent_fpga_counter"
        or command_record.get("sample_timing_basis") != "hardware_sample_counter"
        or command_record.get("sample_anchor_policy")
        != (
            "post-open S0 plus frozen target; exact one-TX2-write interval is "
            "[A,C) during initiating batch refill"
        )
        or not _json_identical(
            command_record.get("sample_counter_bracket"), expected_bound
        )
    ):
        _fail(f"{command_id} bound command differs from raw schedule")

    write = _mapping(diagnostics.get("write_ack"), name=f"{command_id} write")
    _exact_fields(
        write,
        {
            "operation",
            "attempt_count",
            "host_before_ns",
            "host_after_ns",
            "host_jitter_ns",
            "acknowledged",
            "error",
        },
        name=f"{command_id} write",
    )
    write_before, write_after = _timestamp_pair(write, name=f"{command_id} write")
    max_jitter = _exact_int(getattr(probe, "max_host_jitter_ns", None), minimum=1)
    if (
        write.get("operation") != "one_exact_tx2_hardwaregain_write"
        or not _json_identical(write.get("attempt_count"), 1)
        or not _json_identical(write.get("host_jitter_ns"), write_after - write_before)
        or write_after - write_before > max_jitter
        or write.get("acknowledged") is not True
        or write.get("error") is not None
        or write_after > initiating_completion_ns
        or not _json_identical(command_record.get("host_before_ns"), write_before)
        or not _json_identical(command_record.get("host_after_ns"), write_after)
        or not _json_identical(
            command_record.get("host_jitter_ns"), write_after - write_before
        )
    ):
        _fail(f"{command_id} exact one-write proof changed")

    readback = _mapping(
        diagnostics.get("deferred_tx2_readback"), name=f"{command_id} readback"
    )
    _exact_fields(
        readback,
        {
            "operation",
            "attempt_count",
            "host_before_ns",
            "host_after_ns",
            "observed_level_db",
            "tolerance_db",
            "passed",
            "error",
        },
        name=f"{command_id} readback",
    )
    read_before, read_after = _timestamp_pair(readback, name=f"{command_id} readback")
    observed = _finite(readback.get("observed_level_db"))
    tolerance = _finite(getattr(probe, "readback_tolerance_db", None))
    if (
        readback.get("operation") != "one_exact_tx2_hardwaregain_read"
        or not _json_identical(readback.get("attempt_count"), 1)
        or type(readback.get("observed_level_db")) is not float
        or abs(observed - _COMMAND_LEVEL_DB) > tolerance
        or type(readback.get("tolerance_db")) is not float
        or readback.get("tolerance_db") != tolerance
        or readback.get("passed") is not True
        or readback.get("error") is not None
        or type(diagnostics.get("applied_level_db")) is not float
        or diagnostics.get("applied_level_db") != observed
        or type(command_record.get("applied_level_db")) is not float
        or command_record.get("applied_level_db") != observed
        or not _release_attenuation_matches(
            command_record.get("effective_attenuation_db"),
            quality.physical_attenuation_db - observed,
        )
    ):
        _fail(f"{command_id} deferred readback proof changed")

    tx1 = _mapping(diagnostics.get("tx1_mute_assurance"), name=f"{command_id} TX1")
    _exact_fields(tx1, {"pre", "post"}, name=f"{command_id} TX1")
    tx1_times: dict[str, tuple[int, int]] = {}
    for phase in ("pre", "post"):
        evidence = _mapping(tx1.get(phase), name=f"{command_id} TX1 {phase}")
        _exact_fields(
            evidence,
            {
                "attempt_count",
                "host_before_ns",
                "host_after_ns",
                "observed_level_db",
                "passed",
                "error",
            },
            name=f"{command_id} TX1 {phase}",
        )
        pair = _timestamp_pair(evidence, name=f"{command_id} TX1 {phase}")
        if (
            not _json_identical(evidence.get("attempt_count"), 1)
            or type(evidence.get("observed_level_db")) is not float
            or abs(_finite(evidence.get("observed_level_db")) - TX_MUTE_DB) > 0.26
            or evidence.get("passed") is not True
            or evidence.get("error") is not None
        ):
            _fail(f"{command_id} TX1 {phase} mute assurance changed")
        tx1_times[phase] = pair

    reads = _list(diagnostics.get("counter_reads"), name=f"{command_id} counter reads")
    if len(reads) != poll_count + post_count:
        _fail(f"{command_id} counter-read inventory changed")
    normalized_reads: list[Mapping[str, Any]] = []
    previous_after = -1
    for ordinal, item in enumerate(reads):
        read = _mapping(item, name=f"{command_id} counter read {ordinal}")
        _exact_fields(
            read,
            {"ordinal", "role", "host_before_ns", "host_after_ns", "raw", "error"},
            name=f"{command_id} counter read {ordinal}",
        )
        before, after = _timestamp_pair(
            read, name=f"{command_id} counter read {ordinal}"
        )
        if (
            not _json_identical(read.get("ordinal"), ordinal)
            or before < previous_after
            or type(read.get("role")) is not str
            or _exact_int(read.get("raw"), maximum=_UINT32 - 1) < 0
            or read.get("error") is not None
        ):
            _fail(f"{command_id} counter read chronology changed")
        previous_after = after
        normalized_reads.append(read)
    if [item.get("raw") for item in normalized_reads[:poll_count]] != poll_raw:
        _fail(f"{command_id} target polls differ from raw counter reads")
    roles = [item.get("role") for item in normalized_reads]
    post_roles = roles[poll_count:]
    if (
        roles[: poll_count - 1] != ["target_poll"] * (poll_count - 1)
        or roles[poll_count - 1] != "raw_a_prewrite"
        or not post_roles
        or post_roles[0] != "raw_post_write_initial"
        or post_roles[-1] != "raw_c_causal_advance"
        or post_roles.count("raw_b_first_advance") != 1
    ):
        _fail(f"{command_id} counter-read roles changed")
    b_index = post_roles.index("raw_b_first_advance")
    if b_index < 1 or b_index >= len(post_roles) - 1:
        _fail(f"{command_id} B/C counter state machine changed")
    expected_post_raw = [raw_initial] * b_index + [raw_b] * (
        len(post_roles) - b_index - 2
    )
    candidate_records = [
        item
        for offset, item in enumerate(normalized_reads[poll_count:])
        if offset not in {b_index, len(post_roles) - 1}
    ]
    if any(
        item.get("role")
        not in {"raw_post_write_initial", "post_write_advance_candidate"}
        for item in candidate_records
    ):
        _fail(f"{command_id} post-write candidate role changed")
    observed_candidates = [item.get("raw") for item in candidate_records]
    if observed_candidates != expected_post_raw:
        _fail(f"{command_id} post-write candidates do not hold initial/B")
    role_raw = {
        "raw_post_write_initial": raw_initial,
        "raw_b_first_advance": raw_b,
        "raw_c_causal_advance": raw_c,
    }
    for role, raw in role_raw.items():
        matches = [item for item in normalized_reads if item.get("role") == role]
        if len(matches) != 1 or matches[0].get("raw") != raw:
            _fail(f"{command_id} {role} record changed")
    a_read = normalized_reads[poll_count - 1]
    initial_read = normalized_reads[poll_count]
    c_read = normalized_reads[-1]
    if not (
        tx1_times["pre"][1] <= normalized_reads[0]["host_before_ns"]
        and a_read["host_after_ns"] <= write_before
        and write_after <= initial_read["host_before_ns"]
        and c_read["host_after_ns"] <= read_before
        and read_after <= tx1_times["post"][0]
    ):
        _fail(f"{command_id} host scheduler chronology changed")
    return (extended_a, extended_c), (tx1_times["pre"][0], tx1_times["post"][1])


def _release_attenuation_matches(value: Any, expected: float) -> bool:
    if type(value) is not float:
        return False
    try:
        observed = _finite(value)
    except EvidenceInvalid:
        return False
    return observed == expected and observed >= 30.0


def _partition(
    frames: Sequence[Any],
    first_interval: tuple[int, int],
    second_interval: tuple[int, int],
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    first_lower, first_upper = first_interval
    second_lower, second_upper = second_interval
    if not first_lower < first_upper <= second_lower < second_upper:
        _fail("dual command intervals overlap or reorder")
    phases: list[str] = []
    groups: dict[str, dict[str, Any]] = {
        phase: {"count": 0, "frame_indices": []} for phase in _PHASES
    }
    for index, item in enumerate(frames):
        frame = _mapping(item, name=f"partition frame {index}")
        start = _exact_int(frame.get("first_sample_sequence"), maximum=_UINT64 - 1)
        end = _exact_int(frame.get("sample_end_exclusive"), minimum=1, maximum=_UINT64)
        if end != start + _FRAME_SAMPLES:
            _fail(f"partition frame {index} has invalid bounds")
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
            _fail(f"frame {index} cannot be assigned to the five-way partition")
        phases.append(phase)
        groups[phase]["frame_indices"].append(index)
        groups[phase]["count"] += 1
    order = {phase: index for index, phase in enumerate(_PHASES)}
    if phases != sorted(phases, key=order.__getitem__):
        _fail("five-way partition is not ordered")
    for phase in _STABLE_PHASES:
        if groups[phase]["count"] < _MINIMUM_PHASE_FRAMES:
            _fail(f"partition {phase} lacks eight complete frames")
    if (
        not groups["first_command_bracket"]["count"]
        or not groups["second_command_bracket"]["count"]
    ):
        _fail("a command bracket has no retained frame")
    return phases, groups


def _stable_suffix(
    frames: Sequence[Mapping[str, Any]], indices: Sequence[int], *, tolerance: float
) -> dict[str, Any]:
    selected_indices = list(indices[-_MINIMUM_PHASE_FRAMES:])
    if len(selected_indices) != _MINIMUM_PHASE_FRAMES:
        _fail("stable suffix lacks eight frames")
    selected = [frames[index] for index in selected_indices]
    metadata = [
        _mapping(frame.get("metadata"), name="stable metadata") for frame in selected
    ]
    analyses = [
        _mapping(frame.get("analysis"), name="stable analysis") for frame in selected
    ]
    endpoints = {tuple(item.get("bench_gain_indices", [])) for item in metadata}
    transitions = {item.get("tandem_transition_count") for item in metadata}
    if (
        transitions != {0}
        or len(endpoints) != 1
        or any(
            len(endpoint) != 2 or endpoint[0] != endpoint[1] for endpoint in endpoints
        )
        or any(
            item.get("gain_events") != [] or item.get("event_count") != 0
            for item in metadata
        )
    ):
        _fail("stable suffix is not event/endpoint stable")
    windows_by_frame: list[list[Mapping[str, Any]]] = []
    for analysis in analyses:
        windows = _list(analysis.get("windows"), name="stable windows")
        if len(windows) != _FRAME_SAMPLES // _WINDOW_SAMPLES:
            _fail("stable suffix has the wrong RF window count")
        typed = [_mapping(window, name="stable window") for window in windows]
        if any(window.get("quality_valid") is not True for window in typed):
            _fail("stable suffix contains an invalid RF window")
        windows_by_frame.append(typed)
    try:
        frame_medians = [
            [
                float(
                    statistics.median(
                        _finite(window.get("tone_dbfs")[channel]) for window in windows
                    )
                )
                for channel in (0, 1)
            ]
            for windows in windows_by_frame
        ]
        all_windows = [window for windows in windows_by_frame for window in windows]
        suffix_medians = [
            float(
                statistics.median(
                    _finite(window.get("tone_dbfs")[channel]) for window in all_windows
                )
            )
            for channel in (0, 1)
        ]
    except (IndexError, TypeError, statistics.StatisticsError) as error:
        raise EvidenceInvalid(
            "weak dual-target suffix RF values are malformed"
        ) from error
    frame_deviation = [
        max(abs(row[channel] - suffix_medians[channel]) for row in frame_medians)
        for channel in (0, 1)
    ]
    window_deviation = [
        max(
            abs(_finite(window.get("tone_dbfs")[channel]) - suffix_medians[channel])
            for window in all_windows
        )
        for channel in (0, 1)
    ]
    if any(value > tolerance for value in window_deviation):
        _fail("stable suffix exceeds whole-window RF tolerance")
    endpoint = next(iter(endpoints))
    return {
        "frame_indices": selected_indices,
        "required_frame_count": _MINIMUM_PHASE_FRAMES,
        "transition_count": 0,
        "bench_gain_indices": list(endpoint),
        "event_count": 0,
        "rf_window_count": len(all_windows),
        "rf_quality_valid": True,
        "frame_channel_median_tone_dbfs": frame_medians,
        "suffix_channel_median_tone_dbfs": suffix_medians,
        "maximum_frame_median_deviation_db": frame_deviation,
        "maximum_frame_median_deviation_limit_db": tolerance,
        "maximum_window_deviation_db": window_deviation,
        "maximum_window_deviation_limit_db": tolerance,
    }


def _partition_evidence(
    reported: Any,
    frames: Sequence[Mapping[str, Any]],
    phases: list[str],
    groups: dict[str, dict[str, Any]],
    *,
    tolerance: float,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    suffixes = {
        phase: _stable_suffix(
            frames, groups[phase]["frame_indices"], tolerance=tolerance
        )
        for phase in _STABLE_PHASES
    }
    expected = {
        "phase_order": list(_PHASES),
        "phase_by_frame": phases,
        "groups": groups,
        "minimum_required_fully_pre_first_frames": _MINIMUM_PHASE_FRAMES,
        "minimum_required_fully_between_commands_frames": _MINIMUM_PHASE_FRAMES,
        "minimum_required_fully_post_second_frames": _MINIMUM_PHASE_FRAMES,
        "frame_count": _BATCH_FRAMES,
        "stable_suffixes": suffixes,
    }
    if not _json_identical(reported, expected):
        _fail("five-way partition/stable suffix ledger differs from recomputation")
    medians = [
        suffixes[phase]["suffix_channel_median_tone_dbfs"] for phase in _STABLE_PHASES
    ]
    spans = [
        max(row[channel] for row in medians) - min(row[channel] for row in medians)
        for channel in (0, 1)
    ]
    if any(value > tolerance for value in spans):
        _fail("pre/middle/post weak RF suffixes disagree")
    endpoints = [suffixes[phase]["bench_gain_indices"] for phase in _STABLE_PHASES]
    if len({tuple(endpoint) for endpoint in endpoints}) != 1:
        _fail("pre/middle/post maximum endpoints disagree")
    cross = {
        "phase_order": list(_STABLE_PHASES),
        "suffix_channel_median_tone_dbfs": medians,
        "maximum_cross_suffix_span_db": spans,
        "maximum_cross_suffix_span_limit_db": tolerance,
        "bench_gain_indices": endpoints[0],
    }
    return suffixes, cross


def _anchor(
    reported: Any,
    frames: Sequence[Mapping[str, Any]],
    raw_frames: Sequence[bytes],
    groups: Mapping[str, Mapping[str, Any]],
    quality: TandemQualityOptions,
) -> None:
    indices = groups["fully_pre_first"]["frame_indices"]
    source_index = indices[-1]
    frame = frames[source_index]
    offset = _FRAME_SAMPLES - _ANCHOR_SAMPLES
    byte_start = offset * 8
    byte_end = byte_start + _ANCHOR_SAMPLES * 8
    raw = raw_frames[source_index][byte_start:byte_end]
    first = int(frame["first_sample_sequence"]) + offset
    analysis = _analysis(raw, first, quality)
    if analysis.get("quality_valid") is not True:
        _fail("conditioning anchor RF evidence is invalid")
    source = {
        "role": "weak_pre_first_conditioning_tail",
        "source_frame_index": source_index,
        "source_frame_sha256": frame["sha256"],
        "sample_offset_in_frame": offset,
        "samples_per_channel": _ANCHOR_SAMPLES,
        "byte_offset_in_frame": byte_start,
        "byte_end_exclusive_in_frame": byte_end,
        "iq_bytes": len(raw),
        "first_sample_sequence": first,
        "sample_end_exclusive": first + _ANCHOR_SAMPLES,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "analysis": analysis,
    }
    expected = {
        "timing_role": "exact_retained_pre_first_tail",
        "sample_timing_basis": "hardware_sample_counter",
        "sample_anchor_policy": (
            "exact final 8192 samples of the final fully-pre-first frame; weak "
            "conditioning only, not latency evidence"
        ),
        "release_latency_evidence": False,
        "source": source,
    }
    if not _json_identical(reported, expected):
        _fail("conditioning anchor differs from exact IQ slice recomputation")


def _manifest(frames: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entries = [
        {
            "frame_index": index,
            "iq_path": frame["iq_path"],
            "iq_bytes": frame["iq_bytes"],
            "iq_sha256": frame["sha256"],
            "raw_metadata_path": frame["raw_metadata_path"],
            "raw_metadata_bytes": frame["raw_metadata_bytes"],
            "raw_metadata_sha256": frame["raw_metadata_sha256"],
            "write_status": frame["artifact_write_status"],
        }
        for index, frame in enumerate(frames)
    ]
    encoded = json.dumps(
        entries, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    directory = str(frames[0]["iq_path"]).rsplit("/", 1)[0]
    return {
        "path_root": "quality.output_dir",
        "relative_directory": directory,
        "frame_count": _BATCH_FRAMES,
        "file_count": 2 * _BATCH_FRAMES,
        "iq_total_bytes": _BATCH_FRAMES * _FRAME_BYTES,
        "raw_metadata_total_bytes": _BATCH_FRAMES * _METADATA_HEADER_BYTES,
        "completed_iq_files": _BATCH_FRAMES,
        "completed_raw_metadata_files": _BATCH_FRAMES,
        "write_complete": True,
        "entries": entries,
        "entries_canonical_json_sha256": hashlib.sha256(encoded).hexdigest(),
    }


_STATUS_FIELDS = {
    "state",
    "fault_flags",
    "overflow_count",
    "fifo_level",
    "ownership_epoch",
    "transition_count",
    "rx1_gain_index",
    "rx2_gain_index",
}


def _status(value: Any, *, owned: bool, name: str) -> Mapping[str, Any]:
    result = _mapping(value, name=name)
    _exact_fields(result, _STATUS_FIELDS, name=name)
    for field in result:
        maximum = 127 if field in {"rx1_gain_index", "rx2_gain_index"} else _UINT32 - 1
        _exact_int(result[field], maximum=maximum)
    if (
        result.get("fault_flags") != 0
        or result.get("overflow_count") != 0
        or result.get("rx1_gain_index") != result.get("rx2_gain_index")
    ):
        _fail(f"{name} reports a fault, overflow, or torn endpoint")
    if owned:
        if (
            result.get("state") != int(TandemState.ARMED_AUTO)
            or result.get("ownership_epoch", 0) <= 0
            or result.get("fifo_level", 65) > 64
        ):
            _fail(f"{name} is not one owned AUTO session")
    elif (
        result.get("state") != int(TandemState.IDLE)
        or result.get("fifo_level") != 0
        or result.get("ownership_epoch") != 0
    ):
        _fail(f"{name} is not unowned IDLE/FIFO0")
    return result


def _memory_ledger(value: Any) -> Mapping[str, Any]:
    ledger = _mapping(value, name="memory ledger")
    iq = _FRAME_BYTES
    raw = _BATCH_FRAMES * iq
    raw_metadata = _BATCH_FRAMES * _METADATA_CAPACITY_BYTES
    capture_envelope = sum(
        (
            _BATCH_CACHE_BYTES,
            iq,
            raw,
            raw_metadata,
            iq,
            _METADATA_CAPACITY_BYTES,
            _METADATA_CAPACITY_BYTES,
            _PARSED_RESERVATION_BYTES,
            _KERNEL_BUFFERS * iq,
        )
    )
    post_close = raw + raw_metadata + _PARSED_RESERVATION_BYTES + _FFT_WORKSPACE_BYTES
    measured = ledger.get("measured_finished_mode_and_parsed_metadata_bytes")
    canonical_bytes = ledger.get("canonical_evidence_projection_bytes")
    canonical_sha = ledger.get("canonical_evidence_projection_sha256")
    _exact_int(measured, minimum=1, maximum=_PARSED_RESERVATION_BYTES)
    _exact_int(canonical_bytes, minimum=1, maximum=_PARSED_RESERVATION_BYTES)
    if canonical_bytes > measured:
        _fail("canonical evidence bytes exceed the live retained-evidence gate")
    if type(canonical_sha) is not str or _SHA256.fullmatch(canonical_sha) is None:
        _fail("canonical evidence digest is malformed")
    expected = {
        "core_batch_cache_bytes": _BATCH_CACHE_BYTES,
        "ordinary_libiio_c_buffer_bytes": iq,
        "maximum_python_retained_raw_bytes": raw,
        "maximum_python_retained_raw_metadata_bytes": raw_metadata,
        "transient_buffer_read_bytearray_bytes": iq,
        "ctypes_refill_scratch_bytes": _METADATA_CAPACITY_BYTES,
        "returned_metadata_bytes": _METADATA_CAPACITY_BYTES,
        "parsed_evidence_reservation_bytes": _PARSED_RESERVATION_BYTES,
        "device_k8_dma_reservation_bytes": _KERNEL_BUFFERS * iq,
        "post_close_fft_workspace_bytes": _FFT_WORKSPACE_BYTES,
        "capture_phase_envelope_bytes": capture_envelope,
        "post_close_materialization_envelope_bytes": post_close,
        "maximum_phase_envelope_bytes": max(capture_envelope, post_close),
        "aggregate_resident_bytes": capture_envelope,
        "maximum_aggregate_bytes": _MAXIMUM_AGGREGATE_BYTES,
        "within_cap": True,
        "measured_finished_mode_and_parsed_metadata_bytes": measured,
        "measured_evidence_within_reservation": True,
        "canonical_evidence_projection_method": _PROJECTION_METHOD,
        "canonical_evidence_projection_bytes": canonical_bytes,
        "canonical_evidence_projection_sha256": canonical_sha,
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
    if capture_envelope != 89_261_056 or post_close != 54_525_952:
        _fail("independent memory arithmetic changed")
    if not _json_identical(dict(ledger), expected):
        _fail("memory ledger differs from independent byte arithmetic")
    return ledger


def _canonical(mode: Mapping[str, Any], parsed: Sequence[TandemFrameMetadata]) -> bytes:
    mode_projection = dict(mode)
    acquisition = dict(_mapping(mode.get("acquisition"), name="canonical acquisition"))
    ledger = dict(_mapping(acquisition.get("memory_ledger"), name="canonical memory"))
    ledger.update(
        {
            "measured_finished_mode_and_parsed_metadata_bytes": 0,
            "measured_evidence_within_reservation": True,
            "canonical_evidence_projection_bytes": 0,
            "canonical_evidence_projection_sha256": "0" * 64,
        }
    )
    acquisition["memory_ledger"] = ledger
    mode_projection["acquisition"] = acquisition
    projection = {
        "schema": _PROJECTION_SCHEMA,
        "mode": mode_projection,
        "reparsed_metadata": [_metadata_dict(item) for item in parsed],
    }
    try:
        return json.dumps(
            projection,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (OverflowError, TypeError, ValueError) as error:
        raise EvidenceInvalid("weak dual-target canonical projection failed") from error


def _shutdown(value: Any, *, final_refill_ns: int) -> None:
    shutdown = _mapping(value, name="shutdown")
    _exact_fields(
        shutdown,
        {
            "events",
            "worker_in_flight_before_shutdown",
            "cancel_required",
            "cancel_called",
            "cancel_succeeded",
            "worker_stopped",
            "batch_fully_consumed",
            "shutdown_path",
        },
        name="shutdown",
    )
    if (
        shutdown.get("worker_in_flight_before_shutdown") is not False
        or shutdown.get("cancel_required") is not False
        or shutdown.get("cancel_called") is not False
        or shutdown.get("cancel_succeeded") is not None
        or shutdown.get("worker_stopped") is not True
        or shutdown.get("batch_fully_consumed") is not True
        or shutdown.get("shutdown_path") != "normal_close_after_full_cache_replay"
    ):
        _fail("successful shutdown was not a normal no-cancel close")
    events = _list(shutdown.get("events"), name="shutdown events")
    names = [
        "prejoin_mute_start",
        "prejoin_mute_complete",
        "worker_stop_start",
        "worker_stop_complete",
    ]
    if len(events) != len(names):
        _fail("shutdown stage count changed")
    previous = final_refill_ns
    for index, (item, expected_name) in enumerate(zip(events, names, strict=True)):
        event = _mapping(item, name=f"shutdown event {index}")
        _exact_fields(event, {"event", "monotonic_ns"}, name=f"shutdown event {index}")
        timestamp = _exact_int(event.get("monotonic_ns"))
        if event.get("event") != expected_name or timestamp < previous:
            _fail("shutdown began early or its stages reordered")
        previous = timestamp


def _close_lifecycle(
    acquisition: Mapping[str, Any],
    frames: Sequence[Mapping[str, Any]],
    parsed: Sequence[TandemFrameMetadata],
) -> None:
    if (
        not _json_identical(acquisition.get("initiating_batch_refill_calls"), 1)
        or not _json_identical(acquisition.get("public_refill_calls"), _BATCH_FRAMES)
        or not _json_identical(
            acquisition.get("cached_replay_refill_calls"), _BATCH_FRAMES - 1
        )
        or acquisition.get("batch_cache_fully_replayed") is not True
        or not _json_identical(acquisition.get("produced_frames"), _BATCH_FRAMES)
        or not _json_identical(acquisition.get("consumed_frames"), _BATCH_FRAMES)
        or not _json_identical(acquisition.get("discarded_tail_frames"), 0)
        or acquisition.get("buffer_close_completed") is not True
    ):
        _fail("full initiating-refill plus 63 replay ledger changed")
    completion = _exact_int(
        acquisition.get("initiating_refill_completion_monotonic_ns")
    )
    if completion != frames[0]["refill_monotonic_ns"]:
        _fail("initiating refill completion is not frame-0 refill completion")
    _shutdown(
        acquisition.get("shutdown"), final_refill_ns=frames[-1]["refill_monotonic_ns"]
    )
    pre = _status(
        acquisition.get("pre_close_tandem_status"), owned=True, name="pre-close status"
    )
    post = _status(
        acquisition.get("post_close_tandem_status"),
        owned=False,
        name="post-close status",
    )
    maximum = parsed[-1].maximum_gain_index
    if (
        parsed[-1].tandem_transition_count != 0
        or pre.get("transition_count") != 0
        or post.get("transition_count") != 0
        or pre.get("ownership_epoch") != parsed[-1].ownership_epoch
        or [pre.get("rx1_gain_index"), pre.get("rx2_gain_index")] != [maximum, maximum]
        or [post.get("rx1_gain_index"), post.get("rx2_gain_index")]
        != [maximum, maximum]
    ):
        _fail("weak controller changed transition count/maximum endpoint through close")
    expected_close = {
        "last_frame_transition_count": 0,
        "pre_transition_count": 0,
        "post_transition_count": 0,
        "last_frame_to_pre_close_forward_delta": 0,
        "transition_count_forward_delta": 0,
        "maximum_forward_delta": 64,
        "pre_fifo_level": pre["fifo_level"],
        "post_fifo_level": 0,
        "pre_endpoint": [maximum, maximum],
        "post_endpoint": [maximum, maximum],
        "exact_retired_tail_count_claim": None,
        "policy": (
            "preserve forward modulo-u32 diagnostics across buffer close without "
            "claiming an exact retired FIFO tail count"
        ),
    }
    if not _json_identical(acquisition.get("close_counter_ledger"), expected_close):
        _fail("close transition/endpoint ledger differs from recomputation")


_ACQUISITION_FIELDS = {
    "transport",
    "provider_frame_samples",
    "kernel_buffers",
    "batch_frames",
    "queue_capacity_frames",
    "metadata_capacity_bytes",
    "metadata_physics_policy",
    "metadata_abi",
    "configured_batch_frames",
    "configured_batch_cache_bytes",
    "batch_cache_attested",
    "memory_ledger",
    "s0_read",
    "post_open_s0_raw",
    "targets",
    "schedule_diagnostics",
    "schedule_frozen_before_worker_start",
    "schedule_plan",
    "unbound_commands",
    "initiating_batch_refill_calls",
    "public_refill_calls",
    "cached_replay_refill_calls",
    "batch_cache_fully_replayed",
    "initiating_refill_completion_monotonic_ns",
    "produced_frames",
    "consumed_frames",
    "discarded_tail_frames",
    "pre_close_tandem_status",
    "buffer_close_completed",
    "post_close_tandem_status",
    "close_counter_ledger",
    "artifact_manifest",
    "shutdown",
}


def _physics_policy(quality: TandemQualityOptions) -> dict[str, Any]:
    return {
        "protocol_version": 5,
        "header_bytes": _METADATA_HEADER_BYTES,
        "required_features": _REQUIRED_FEATURES,
        "required_flags": _REQUIRED_FLAGS,
        "sample_format": 1,
        "observation_capacity": 64,
        "event_capacity": 64,
        "maximum_observations_per_frame": 5,
        "maximum_events_per_frame": maximum_tandem_events_per_frame(
            mode=TandemMode.AUTO,
            samples_per_channel=_FRAME_SAMPLES,
            power_measurement_samples=quality.tandem_power_measurement_samples,
            cooldown_periods=quality.tandem_cooldown_periods,
        ),
        "minimum_event_spacing_samples": quality.tandem_power_measurement_samples
        * (quality.tandem_cooldown_periods + 1),
    }


def _unbound_command(
    value: Any,
    bound: Mapping[str, Any],
    quality: TandemQualityOptions,
) -> None:
    unbound = _mapping(value, name="unbound command")
    expected = {
        key: bound[key]
        for key in (
            "command_id",
            "requested_level_db",
            "applied_level_db",
            "host_before_ns",
            "host_after_ns",
            "host_jitter_ns",
        )
    }
    expected.update(
        {
            "sample_sequence_before": None,
            "sample_sequence_after": None,
            "sample_uncertainty": None,
            "effective_attenuation_db": (
                quality.physical_attenuation_db - float(bound["applied_level_db"])
            ),
        }
    )
    if not _json_identical(dict(unbound), expected):
        _fail("unbound command differs from the one bound after replay")


def _validate_mode_impl(
    mode: Mapping[str, Any],
    quality: TandemQualityOptions,
    probe: Any,
    *,
    phase_root: Path,
    serial: str,
) -> None:
    mode_fields = {
        "mode",
        "verdict",
        "timing_basis",
        "commands",
        "batch_frames",
        "partition",
        "conditioning_anchor",
        "metadata_request",
        "acquisition",
        "batch_profile",
        "release_pass_eligible",
        "strong_tx_write_permitted",
        "gain_transient_exercised",
        "qualification_scope",
        "transport_stability",
        "tandem_status_before",
        "metadata_abi",
        "tandem_status_after",
        "final_rx_state",
    }
    _exact_fields(mode, mode_fields, name="mode evidence")
    if (
        mode.get("mode") != _MODE
        or mode.get("verdict") != _MODE_VERDICT
        or mode.get("timing_basis") != "hardware_sample_counter"
        or mode.get("batch_profile") != _MODE_PROFILE
        or mode.get("release_pass_eligible") is not False
        or mode.get("strong_tx_write_permitted") is not False
        or mode.get("gain_transient_exercised") is not False
        or mode.get("qualification_scope") != _MODE_SCOPE
        or not _json_identical(mode.get("metadata_abi"), 2)
    ):
        _fail("mode qualification/profile semantics changed")
    if not _json_identical(mode.get("metadata_request"), _expected_request(quality)):
        _fail("AUTO62 metadata request differs from independent reconstruction")

    acquisition = _mapping(mode.get("acquisition"), name="acquisition")
    _exact_fields(acquisition, _ACQUISITION_FIELDS, name="acquisition")
    if (
        acquisition.get("transport") != "single_metadata_batch"
        or not _json_identical(
            acquisition.get("provider_frame_samples"), _FRAME_SAMPLES
        )
        or not _json_identical(acquisition.get("kernel_buffers"), _KERNEL_BUFFERS)
        or not _json_identical(acquisition.get("batch_frames"), _BATCH_FRAMES)
        or not _json_identical(acquisition.get("queue_capacity_frames"), _QUEUE_FRAMES)
        or not _json_identical(
            acquisition.get("metadata_capacity_bytes"), _METADATA_CAPACITY_BYTES
        )
        or not _json_identical(
            acquisition.get("metadata_physics_policy"), _physics_policy(quality)
        )
        or not _json_identical(acquisition.get("metadata_abi"), 2)
        or not _json_identical(
            acquisition.get("configured_batch_frames"), _BATCH_FRAMES
        )
        or not _json_identical(
            acquisition.get("configured_batch_cache_bytes"), _BATCH_CACHE_BYTES
        )
        or acquisition.get("batch_cache_attested") is not True
        or acquisition.get("schedule_frozen_before_worker_start") is not True
    ):
        _fail("F65536/K8/batch64/queue4/ABI2 acquisition contract changed")
    ledger = _memory_ledger(acquisition.get("memory_ledger"))

    frames_value = _list(mode.get("batch_frames"), name="batch frames")
    if len(frames_value) != _BATCH_FRAMES or any(
        not isinstance(frame, Mapping) for frame in frames_value
    ):
        _fail("batch frame inventory is malformed")
    frame0 = _mapping(frames_value[0], name="frame 0")
    frame63 = _mapping(frames_value[-1], name="frame 63")
    first_batch_sample = _exact_int(
        frame0.get("first_sample_sequence"), maximum=_UINT64 - 1
    )
    last_batch_sample = _exact_int(
        frame63.get("sample_end_exclusive"), minimum=1, maximum=_UINT64
    )
    completion = _exact_int(
        acquisition.get("initiating_refill_completion_monotonic_ns")
    )

    commands = _list(mode.get("commands"), name="commands")
    if len(commands) != 3:
        _fail("mode must contain initial plus exactly two target commands")
    _initial_before, initial_after = _validate_initial_command(
        commands[0], quality, probe
    )
    s0_read = _mapping(acquisition.get("s0_read"), name="S0 read")
    _exact_fields(s0_read, {"host_before_ns", "host_after_ns", "raw"}, name="S0 read")
    s0_before, s0_after = _timestamp_pair(s0_read, name="S0 read")
    s0_raw = _exact_int(s0_read.get("raw"), maximum=_UINT32 - 1)
    if initial_after > s0_before or not _json_identical(
        acquisition.get("post_open_s0_raw"), s0_raw
    ):
        _fail("S0 was not frozen after the initial weak write")

    targets = _mapping(acquisition.get("targets"), name="targets")
    diagnostics = _mapping(acquisition.get("schedule_diagnostics"), name="diagnostics")
    unbound = _mapping(acquisition.get("unbound_commands"), name="unbound commands")
    expected_ids = {command_id for command_id, _ in _COMMAND_SPECS}
    if (
        set(targets) != expected_ids
        or set(diagnostics) != expected_ids
        or set(unbound) != expected_ids
    ):
        _fail("dual-target schedule inventories changed")
    expected_targets: dict[str, dict[str, Any]] = {}
    for command_id, offset_frames in _COMMAND_SPECS:
        expected_targets[command_id] = {
            "offset_frames": offset_frames,
            "offset_samples": offset_frames * _FRAME_SAMPLES,
            "target_raw": (s0_raw + offset_frames * _FRAME_SAMPLES) % _UINT32,
        }
    if not _json_identical(dict(targets), expected_targets):
        _fail("frozen S0+16F/+40F targets changed")

    schedule_plan = _mapping(acquisition.get("schedule_plan"), name="schedule plan")
    _exact_fields(
        schedule_plan,
        {
            "s0_read_host_after_ns",
            "targets_frozen_host_ns",
            "worker_start_requested_ns",
            "worker_start_returned_ns",
            "commands",
        },
        name="schedule plan",
    )
    plan_commands = [
        {
            "command_id": command_id,
            "requested_level_db": _COMMAND_LEVEL_DB,
            **expected_targets[command_id],
        }
        for command_id, _ in _COMMAND_SPECS
    ]
    freeze = _exact_int(schedule_plan.get("targets_frozen_host_ns"))
    start_requested = _exact_int(schedule_plan.get("worker_start_requested_ns"))
    start_returned = _exact_int(schedule_plan.get("worker_start_returned_ns"))
    if (
        not _json_identical(schedule_plan.get("s0_read_host_after_ns"), s0_after)
        or not _json_identical(schedule_plan.get("commands"), plan_commands)
        or not s0_after <= freeze <= start_requested <= start_returned
    ):
        _fail("pre-start S0/target/worker chronology changed")

    intervals: list[tuple[int, int]] = []
    host_envelopes: list[tuple[int, int]] = []
    for index, (command_id, offset_frames) in enumerate(_COMMAND_SPECS, start=1):
        interval, envelope = _validate_schedule(
            diagnostics[command_id],
            commands[index],
            command_id=command_id,
            target_frames=offset_frames,
            s0_raw=s0_raw,
            first_batch_sample=first_batch_sample,
            last_batch_sample_exclusive=last_batch_sample,
            initiating_completion_ns=completion,
            quality=quality,
            probe=probe,
        )
        intervals.append(interval)
        host_envelopes.append(envelope)
        bound = _mapping(commands[index], name=f"{command_id} bound command")
        _unbound_command(unbound[command_id], bound, quality)
    first_command = _mapping(commands[1], name="first command")
    second_command = _mapping(commands[2], name="second command")
    if (
        start_returned > host_envelopes[0][0]
        or host_envelopes[0][1] > host_envelopes[1][0]
        or intervals[0][1] > intervals[1][0]
        or first_command["host_after_ns"] > second_command["host_before_ns"]
    ):
        _fail("first/second scheduler chronology overlaps or reorders")

    phases, groups = _partition(frames_value, intervals[0], intervals[1])
    root = _trusted_root(phase_root, quality)
    frames, raw_frames, parsed = _load_frames(
        frames_value, phases=phases, quality=quality, root=root, serial=serial
    )
    if first_batch_sample != parsed[0].first_sample_sequence or last_batch_sample != (
        parsed[-1].first_sample_sequence + _FRAME_SAMPLES
    ):
        _fail("schedule batch bounds differ from reparsed sidecars")
    tolerance = _finite(getattr(probe, "settling_tolerance_db", 1.0))
    # The v4 adapter freezes this policy at 1 dB even though it shares a
    # TransientCaptureOptions field internally.
    if tolerance != 1.0:
        tolerance = 1.0
    suffixes, cross = _partition_evidence(
        mode.get("partition"), frames, phases, groups, tolerance=tolerance
    )
    _anchor(mode.get("conditioning_anchor"), frames, raw_frames, groups, quality)

    maximum = parsed[0].maximum_gain_index
    expected_stability = {
        "frame_count": _BATCH_FRAMES,
        "global_transition_count": 0,
        "global_gain_event_count": 0,
        "maximum_gain_index": maximum,
        "bench_gain_indices": [maximum, maximum],
        "all_frames_at_maximum_gain": True,
        "all_windows_quality_valid": True,
        "stable_suffixes": suffixes,
        "cross_suffix_stability": cross,
    }
    if not _json_identical(mode.get("transport_stability"), expected_stability):
        _fail("global zero-transition/max-endpoint/RF-stability ledger changed")

    expected_manifest = _manifest(frames)
    if not _json_identical(acquisition.get("artifact_manifest"), expected_manifest):
        _fail("aggregate 128-sidecar manifest differs from recomputation")
    _close_lifecycle(acquisition, frames, parsed)

    before = _status(
        mode.get("tandem_status_before"), owned=False, name="pre-session status"
    )
    if before.get("transition_count") != 0:
        _fail("weak pre-session status has a nonzero transition count")
    if not _json_identical(
        mode.get("tandem_status_after"), acquisition.get("post_close_tandem_status")
    ):
        _fail("mode post-session status differs from acquisition close status")
    final_rx = _mapping(mode.get("final_rx_state"), name="final RX state")
    _exact_fields(final_rx, {"modes", "gains_db"}, name="final RX state")
    gains = _list(final_rx.get("gains_db"), name="final RX gains")
    if (
        final_rx.get("modes") != ["manual", "manual"]
        or len(gains) != 2
        or any(abs(_finite(gain) - quality.manual_gain_db) > 0.1 for gain in gains)
    ):
        _fail("final RX state is not restored manual gain")

    canonical = _canonical(mode, parsed)
    canonical_bytes = ledger["canonical_evidence_projection_bytes"]
    measured = ledger["measured_finished_mode_and_parsed_metadata_bytes"]
    if (
        len(parsed) != _BATCH_FRAMES
        or len(canonical) != canonical_bytes
        or hashlib.sha256(canonical).hexdigest()
        != ledger["canonical_evidence_projection_sha256"]
        or not len(canonical) <= measured <= _PARSED_RESERVATION_BYTES
    ):
        _fail("canonical/live retained-evidence attestation changed")


def validate_dual_target_report_mode(
    mode_evidence: Any,
    quality: TandemQualityOptions,
    probe: Any,
    *,
    phase_root: Path,
    serial: str,
) -> None:
    """Validate only the v4 ``mode_evidence`` object for the probe wrapper."""

    try:
        value = _json_domain(mode_evidence)
        mode = _mapping(value, name="mode_evidence")
        _validate_mode_impl(
            mode,
            quality,
            probe,
            phase_root=Path(phase_root),
            serial=_safe_serial(serial),
        )
    except (EvidenceInvalid, FixtureSafetyError):
        raise
    except (
        AttributeError,
        IndexError,
        KeyError,
        MemoryError,
        OSError,
        OverflowError,
        TypeError,
        ValueError,
    ) as error:
        raise EvidenceInvalid(
            "weak dual-target mode evidence is malformed: "
            f"{type(error).__name__}: {error}"
        ) from error


def _quality_configuration(quality: TandemQualityOptions) -> dict[str, Any]:
    result = asdict(quality)
    result["output_dir"] = str(quality.output_dir)
    result["thresholds"] = asdict(quality.thresholds)
    result["tx_gain_trajectory_db"] = list(result["tx_gain_trajectory_db"])
    result["native_gain_control_modes"] = list(result["native_gain_control_modes"])
    return result


def _probe_configuration(probe: Any) -> dict[str, Any]:
    names = (
        "weak_stimulus_tx_gain_db",
        "auto_initial_gain_db",
        "frame_samples",
        "kernel_buffers",
        "batch_frames",
        "anchor_samples",
        "window_samples",
        "max_host_jitter_ns",
        "max_target_overshoot_samples",
        "max_command_sample_uncertainty",
        "readback_tolerance_db",
        "maximum_retained_raw_bytes",
        "maximum_core_batch_bytes",
        "maximum_aggregate_bytes",
    )
    try:
        return {name: getattr(probe, name) for name in names}
    except AttributeError as error:
        raise EvidenceInvalid(
            "weak dual-target probe options are incomplete"
        ) from error


def _evidence_policy(probe: Any) -> dict[str, Any]:
    return {
        "transport": "one continuous AUTO metadata batch session",
        "provider_frame_samples": _FRAME_SAMPLES,
        "kernel_buffers": _KERNEL_BUFFERS,
        "batch_frames": _BATCH_FRAMES,
        "queue_capacity_frames": _QUEUE_FRAMES,
        "targets": [
            {
                "command_id": command_id,
                "requested_level_db": _COMMAND_LEVEL_DB,
                "offset_frames": offset,
                "offset_samples": offset * _FRAME_SAMPLES,
            }
            for command_id, offset in _COMMAND_SPECS
        ],
        "targets_frozen_before_initiating_refill": True,
        "command_primitive": (
            "exact one TX2 write in [A,C), one deferred readback, and TX1 "
            "pre/post mute assurance while the initiating refill is in flight"
        ),
        "maximum_target_overshoot_samples": probe.max_target_overshoot_samples,
        "maximum_a_to_c_uncertainty_samples": probe.max_command_sample_uncertainty,
        "provider_gaps": "forbidden",
        "hidden_transitions": "forbidden",
        "all_64_frames": (
            "transition_count=0, event_count=0, AUTO fault-free, and paired "
            "maximum-gain endpoint"
        ),
        "partition": (
            "ordered five-way first/second command partition with at least eight "
            "fully-pre, fully-between, and fully-post frames"
        ),
        "stable_suffix_frames_per_phase": _MINIMUM_PHASE_FRAMES,
        "whole_window_and_cross_suffix_tolerance_db": 1.0,
        "sidecars": (
            "exact 64 IQ plus 64 raw-metadata files, independently reread, "
            "reparsed, and reanalyzed"
        ),
        "success_close": (
            "full initiating refill plus 63 cached replays; no cancel; normal "
            "close; transition count remains zero"
        ),
        "release_claim": "never eligible",
    }


def _safety(quality: TandemQualityOptions, probe: Any) -> dict[str, Any]:
    return {
        "physical_attenuation_db": quality.physical_attenuation_db,
        "authorized_tx2_gain_ceiling_db": _COMMAND_LEVEL_DB,
        "initial_tx2_gain_db": _COMMAND_LEVEL_DB,
        "exact_reassertion_levels_db": [_COMMAND_LEVEL_DB, _COMMAND_LEVEL_DB],
        "minimum_effective_attenuation_db": (
            quality.physical_attenuation_db - _COMMAND_LEVEL_DB
        ),
        "required_effective_attenuation_db": 30.0,
        "strong_tx_write_permitted": False,
        "tx1_policy": "exact mute assurance before and after each TX2 write",
        "release_pass_eligible": False,
        "configured_weak_level_matches_probe": (
            probe.weak_stimulus_tx_gain_db == _COMMAND_LEVEL_DB
        ),
    }


def _cleanup(value: Any, *, required: bool) -> None:
    if not required:
        expected = {
            "verified": False,
            "status": "pending_radio_lifecycle_close",
            "owner": "Issue46Radio.close",
        }
        if not _json_identical(value, expected):
            _fail("pending cleanup ledger changed")
        return
    cleanup = _mapping(value, name="cleanup")
    _exact_fields(
        cleanup,
        {"verified", "tx1_gain_db", "tx2_gain_db", "selectors", "dds", "failures"},
        name="cleanup",
    )
    if cleanup.get("verified") is not True or cleanup.get("failures") != []:
        raise FixtureSafetyError("weak dual-target durable cleanup is not verified")
    if any(
        _finite(cleanup.get(name)) > -80.0 for name in ("tx1_gain_db", "tx2_gain_db")
    ):
        raise FixtureSafetyError("weak dual-target durable TX cleanup is unsafe")
    if not _json_identical(cleanup.get("selectors"), [3, 3, 3, 3]):
        raise FixtureSafetyError("weak dual-target durable selectors are not ZERO")
    dds = _mapping(cleanup.get("dds"), name="cleanup DDS")
    names = {f"altvoltage{index}" for index in range(8)}
    if set(dds) != names:
        raise FixtureSafetyError("weak dual-target durable DDS inventory changed")
    for name in names:
        channel = _mapping(dds[name], name=f"cleanup DDS {name}")
        _exact_fields(channel, {"present", "scale", "raw"}, name=f"cleanup DDS {name}")
        if (
            channel.get("present") is not True
            or _finite(channel.get("scale")) != 0.0
            or _finite(channel.get("raw")) != 0.0
        ):
            raise FixtureSafetyError(f"weak dual-target durable DDS {name} is unsafe")


def _top_identity(value: Any, *, runtime: Mapping[str, Any]) -> str:
    identity = _mapping(value, name="identity")
    _exact_fields(
        identity,
        {
            "serial",
            "uri",
            "context_name",
            "context_description",
            "context_version",
            "context_attrs",
            "pylibiio_file",
            "libiio_source_commit",
        },
        name="identity",
    )
    serial = _safe_serial(identity.get("serial"))
    attrs = _mapping(identity.get("context_attrs"), name="identity attributes")
    version = _list(identity.get("context_version"), name="context version")
    host = _mapping(runtime.get("host_libiio"), name="identity host provenance")
    if (
        serial != _SERIAL
        or type(identity.get("uri")) is not str
        or not identity["uri"].startswith("usb:")
        or identity.get("context_name") != "usb"
        or type(identity.get("context_description")) is not str
        or not identity.get("context_description")
        or not _json_identical(version, [0, 25, "v0.25"])
        or attrs.get("hw_serial") != serial
        or attrs.get("usb,serial") != serial
        or attrs.get("iio,buffer-metadata") != "2"
        or attrs.get("fw_version") != "v0.41-plutoplus-spf-tandem-agc-v8-rc2"
        or attrs.get("uri") != identity.get("uri")
        or identity.get("libiio_source_commit") != _LIBIIO_COMMIT
        or identity.get("pylibiio_file") != host.get("pylibiio_path")
    ):
        _fail("identity is not the exact local USB RC2 radio")
    return serial


def _firmware_repository() -> Path:
    return Path(__file__).resolve().parents[2]


def _git_bytes(repository: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ("git", "-C", str(repository), *arguments),
            check=True,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        _fail(f"provenance git {' '.join(arguments)} failed: {error}")
    return completed.stdout


def _git_text(repository: Path, *arguments: str) -> str:
    try:
        return _git_bytes(repository, *arguments).decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise EvidenceInvalid("provenance git output is not UTF-8") from error


def _manifest_source_identity(raw: bytes) -> dict[str, str]:
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise EvidenceInvalid("source manifest is not UTF-8") from error
    values: dict[str, str] = {}
    for line in lines:
        key, separator, value = line.partition(":")
        if separator and key in {"libiio_0_25_source", "libiio_0_25_ref"}:
            values[key] = value.strip()
    expected = {
        "libiio_0_25_source": _LIBIIO_COMMIT,
        "libiio_0_25_ref": _LIBIIO_REF,
    }
    if values != expected:
        _fail("source manifest protected libiio identity changed")
    return values


def _cmake_source_directory(path: Path) -> Path:
    descriptor: int | None = None
    try:
        before = path.stat()
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size < 1
            or before.st_size > 1024 * 1024
            or path.resolve(strict=True) != path
        ):
            _fail("CMake cache is not one bounded canonical regular file")
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
            or opened.st_size != before.st_size
        ):
            _fail("CMake cache changed before bounded read")
        chunks: list[bytes] = []
        remaining = before.st_size + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = path.stat()
    except OSError as error:
        raise EvidenceInvalid("CMake cache cannot be reread") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        len(raw) != before.st_size
        or after.st_dev != before.st_dev
        or after.st_ino != before.st_ino
        or after.st_mtime_ns != before.st_mtime_ns
    ):
        _fail("CMake cache changed during bounded read")
    try:
        entries = [
            line.split("=", 1)[1]
            for line in raw.decode("utf-8").splitlines()
            if line.startswith("CMAKE_HOME_DIRECTORY:INTERNAL=")
        ]
    except (IndexError, UnicodeDecodeError) as error:
        raise EvidenceInvalid("CMake cache source record is malformed") from error
    if len(entries) != 1:
        _fail("CMake cache lacks one exact source directory")
    return Path(entries[0]).resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor: int | None = None
    try:
        if path.resolve(strict=True) != path:
            _fail("provenance file path contains symlink indirection")
        before = path.stat()
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size < 0
            or before.st_size > _MAX_PROVENANCE_FILE_BYTES
        ):
            _fail("provenance file is not one bounded regular file")
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_size != before.st_size
            or opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
        ):
            _fail("provenance file changed before bounded read")
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            digest.update(chunk)
        after = path.stat()
        if (
            remaining != 0
            or after.st_dev != before.st_dev
            or after.st_ino != before.st_ino
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
        ):
            _fail("provenance file changed during bounded read")
    except OSError as error:
        raise EvidenceInvalid(
            "weak dual-target provenance file cannot be reread"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return digest.hexdigest()


def _runtime_provenance(value: Any) -> Mapping[str, Any]:
    runtime = _mapping(value, name="runtime provenance")
    _exact_fields(
        runtime, {"host_libiio", "firmware_runner"}, name="runtime provenance"
    )
    host = _mapping(runtime.get("host_libiio"), name="host libiio provenance")
    host_fields = {
        "source_commit",
        "protected_source_tag",
        "protected_source_ref",
        "source_directory",
        "source_head_commit",
        "protected_tag_commit",
        "source_tracked_clean",
        "build_directory",
        "cmake_cache_path",
        "cmake_source_directory",
        "mapped_shared_objects",
        "mapped_shared_object",
        "mapped_shared_object_sha256",
        "pylibiio_path",
        "pylibiio_sha256",
        "pylibiio_commit_blob_sha256",
    }
    _exact_fields(host, host_fields, name="host libiio provenance")
    if (
        host.get("source_commit") != _LIBIIO_COMMIT
        or host.get("protected_source_tag") != _LIBIIO_TAG
        or host.get("protected_source_ref") != _LIBIIO_REF
        or host.get("source_head_commit") != _LIBIIO_COMMIT
        or host.get("protected_tag_commit") != _LIBIIO_COMMIT
        or host.get("source_tracked_clean") is not True
    ):
        _fail("protected host libiio identity changed")
    path_names = (
        "source_directory",
        "build_directory",
        "cmake_cache_path",
        "cmake_source_directory",
        "mapped_shared_object",
        "pylibiio_path",
    )
    paths: dict[str, Path] = {}
    for name in path_names:
        raw = host.get(name)
        if type(raw) is not str or not Path(raw).is_absolute():
            _fail(f"host provenance {name} is not an absolute path")
        path = Path(raw).resolve()
        if str(path) != raw:
            _fail(f"host provenance {name} is not canonical")
        paths[name] = path
    if (
        paths["cmake_source_directory"] != paths["source_directory"]
        or paths["cmake_cache_path"] != paths["build_directory"] / "CMakeCache.txt"
        or paths["mapped_shared_object"].parent != paths["build_directory"]
        or paths["pylibiio_path"]
        != paths["source_directory"] / "bindings/python/iio.py"
        or not _json_identical(
            host.get("mapped_shared_objects"), [str(paths["mapped_shared_object"])]
        )
    ):
        _fail("host libiio paths are not cross-bound")
    source = paths["source_directory"]
    if _cmake_source_directory(paths["cmake_cache_path"]) != source:
        _fail("durable CMake source differs from protected libiio source")
    source_head = _git_text(source, "rev-parse", "HEAD")
    protected_tag = _git_text(source, "rev-parse", f"{_LIBIIO_REF}^{{commit}}")
    if (
        source_head != _LIBIIO_COMMIT
        or protected_tag != _LIBIIO_COMMIT
        or source_head != host.get("source_head_commit")
        or protected_tag != host.get("protected_tag_commit")
        or _git_text(source, "status", "--porcelain", "--untracked-files=no")
    ):
        _fail("durable protected libiio checkout identity changed")
    for field in (
        "mapped_shared_object_sha256",
        "pylibiio_sha256",
        "pylibiio_commit_blob_sha256",
    ):
        if type(host.get(field)) is not str or _SHA256.fullmatch(host[field]) is None:
            _fail(f"host provenance {field} is malformed")
    protected_pylibiio_sha256 = hashlib.sha256(
        _git_bytes(source, "show", f"{_LIBIIO_COMMIT}:bindings/python/iio.py")
    ).hexdigest()
    if (
        _sha256_file(paths["mapped_shared_object"])
        != host["mapped_shared_object_sha256"]
        or _sha256_file(paths["pylibiio_path"]) != host["pylibiio_sha256"]
        or not host["pylibiio_sha256"]
        == host["pylibiio_commit_blob_sha256"]
        == protected_pylibiio_sha256
    ):
        _fail("host libiio file digests changed")

    runner = _mapping(runtime.get("firmware_runner"), name="runner provenance")
    _exact_fields(
        runner,
        {
            "repository",
            "commit",
            "local_dependencies",
            "manifest_relative_path",
            "manifest_libiio_identity",
        },
        name="runner provenance",
    )
    repository_value = runner.get("repository")
    if type(repository_value) is not str or not Path(repository_value).is_absolute():
        _fail("runner repository path is not absolute")
    repository = Path(repository_value).resolve()
    commit = runner.get("commit")
    if (
        str(repository) != repository_value
        or repository != _firmware_repository()
        or not repository.is_dir()
        or type(commit) is not str
        or re.fullmatch(r"[0-9a-f]{40}", commit) is None
    ):
        _fail("runner repository/commit provenance is malformed")
    if (
        _git_text(repository, "rev-parse", f"{commit}^{{commit}}") != commit
        or _git_text(repository, "rev-parse", "HEAD") != commit
    ):
        _fail("runner commit is not the current resolvable firmware HEAD")
    dependencies = _list(runner.get("local_dependencies"), name="runner dependencies")
    if len(dependencies) != len(_RUNTIME_DEPENDENCIES):
        _fail("runner dependency inventory changed")
    manifest_blob: bytes | None = None
    for expected_path, item in zip(_RUNTIME_DEPENDENCIES, dependencies, strict=True):
        dependency = _mapping(item, name=f"dependency {expected_path}")
        _exact_fields(
            dependency,
            {"relative_path", "absolute_path", "observed_sha256", "commit_blob_sha256"},
            name=f"dependency {expected_path}",
        )
        lexical = repository / expected_path
        current = repository
        for component in PurePosixPath(expected_path).parts:
            current /= component
            if current.is_symlink():
                _fail(f"runner dependency {expected_path} contains a symlink")
        try:
            absolute = lexical.resolve(strict=True)
            absolute.relative_to(repository)
        except (OSError, ValueError) as error:
            raise EvidenceInvalid(
                f"runner dependency {expected_path} escapes the repository"
            ) from error
        observed = dependency.get("observed_sha256")
        committed = dependency.get("commit_blob_sha256")
        committed_blob = _git_bytes(repository, "show", f"{commit}:{expected_path}")
        expected_digest = hashlib.sha256(committed_blob).hexdigest()
        if (
            dependency.get("relative_path") != expected_path
            or dependency.get("absolute_path") != str(absolute)
            or type(observed) is not str
            or _SHA256.fullmatch(observed) is None
            or type(committed) is not str
            or _SHA256.fullmatch(committed) is None
            or observed != expected_digest
            or committed != expected_digest
            or _sha256_file(absolute) != expected_digest
        ):
            _fail(f"runner dependency {expected_path} changed")
        if expected_path == _MANIFEST_PATH:
            manifest_blob = committed_blob
    if (
        runner.get("manifest_relative_path") != _MANIFEST_PATH
        or manifest_blob is None
        or not _json_identical(
            runner.get("manifest_libiio_identity"),
            _manifest_source_identity(manifest_blob),
        )
    ):
        _fail("runner source manifest identity changed")
    return runtime


def validate_dual_target_report(
    report: Mapping[str, Any],
    quality: TandemQualityOptions,
    probe: Any,
    *,
    phase_root: Path,
    require_cleanup: bool,
) -> None:
    """Strictly validate one complete serialized v4 report and all sidecars."""

    try:
        value = _mapping(_json_domain(report), name="report")
        fields = {
            "schema",
            "probe_mode",
            "started_unix_ns",
            "completed_unix_ns",
            "elapsed_seconds",
            "identity",
            "runtime_provenance",
            "release_pass_eligible",
            "strong_tx_write_permitted",
            "qualification_scope",
            "rf",
            "configuration",
            "safety",
            "evidence_policy",
            "mode_evidence",
            "cleanup",
            "verdict",
        }
        _exact_fields(value, fields, name="report")
        expected_verdict = _FINAL_VERDICT if require_cleanup else _PENDING_VERDICT
        started = _exact_int(value.get("started_unix_ns"))
        completed = _exact_int(value.get("completed_unix_ns"))
        elapsed = _finite(value.get("elapsed_seconds"))
        if (
            value.get("schema") != _SCHEMA
            or value.get("probe_mode") != _PROBE_MODE
            or value.get("verdict") != expected_verdict
            or value.get("release_pass_eligible") is not False
            or value.get("strong_tx_write_permitted") is not False
            or value.get("qualification_scope") != _QUALIFICATION_SCOPE
            or completed < started
            or type(value.get("elapsed_seconds")) is not float
            or elapsed < 0
        ):
            _fail("top-level qualification/clock contract changed")
        runtime = _runtime_provenance(value.get("runtime_provenance"))
        serial = _top_identity(value.get("identity"), runtime=runtime)
        expected_configuration = {
            "quality": _quality_configuration(quality),
            "probe": _probe_configuration(probe),
            "dual_target": {
                "command_ids": [item[0] for item in _COMMAND_SPECS],
                "target_frames": [item[1] for item in _COMMAND_SPECS],
                "requested_levels_db": [_COMMAND_LEVEL_DB, _COMMAND_LEVEL_DB],
                "artifact_directory": _ARTIFACT_DIRECTORY,
                "artifact_policy": _ARTIFACT_POLICY,
            },
        }
        if not _json_identical(value.get("configuration"), expected_configuration):
            _fail("top-level configuration differs from frozen options")
        if not _json_identical(value.get("safety"), _safety(quality, probe)):
            _fail("top-level weak-only safety policy changed")
        if not _json_identical(value.get("evidence_policy"), _evidence_policy(probe)):
            _fail("top-level evidence policy changed")
        expected_rf = {
            "center_frequency_hz_requested": quality.center_frequency_hz,
            "center_frequency_hz_readback": {
                "rx_lo_hz": quality.center_frequency_hz,
                "tx_lo_hz": quality.center_frequency_hz,
            },
            "sample_rate_hz": quality.sample_rate_hz,
            "tone_hz": quality.tone_hz,
            "dds_scale": quality.dds_scale,
            "weak_tx2_gain_db": _COMMAND_LEVEL_DB,
        }
        rf = _mapping(value.get("rf"), name="RF ledger")
        readback = _mapping(rf.get("center_frequency_hz_readback"), name="LO readback")
        if (
            set(rf) != set(expected_rf)
            or set(readback) != {"rx_lo_hz", "tx_lo_hz"}
            or any(
                abs(_exact_int(readback.get(name)) - quality.center_frequency_hz) > 2
                for name in ("rx_lo_hz", "tx_lo_hz")
            )
            or any(
                not _json_identical(rf.get(name), expected)
                for name, expected in expected_rf.items()
                if name != "center_frequency_hz_readback"
            )
        ):
            _fail("top-level RF ledger changed")
        _validate_mode_impl(
            _mapping(value.get("mode_evidence"), name="mode evidence"),
            quality,
            probe,
            phase_root=Path(phase_root),
            serial=serial,
        )
        _cleanup(value.get("cleanup"), required=require_cleanup)
    except (EvidenceInvalid, FixtureSafetyError):
        raise
    except (
        AttributeError,
        IndexError,
        KeyError,
        MemoryError,
        OSError,
        OverflowError,
        TypeError,
        ValueError,
    ) as error:
        raise EvidenceInvalid(
            f"weak dual-target report is malformed: {type(error).__name__}: {error}"
        ) from error


__all__ = ["validate_dual_target_report", "validate_dual_target_report_mode"]
