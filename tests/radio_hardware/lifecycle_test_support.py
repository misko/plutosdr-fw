"""Pure producer-shaped v5 lifecycle archive fixtures for offline tests."""

from __future__ import annotations

import hashlib
import re
import struct
import zlib
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from . import muted_metadata_batch_lifecycle as lifecycle
from .metadata_abi import (
    GAIN_EVENT_BYTES,
    GAIN_OBSERVATION_BYTES,
    METADATA_MAGIC,
    TANDEM_V5_EXTENSION,
    V5_PREFIX_BYTES,
    TandemFrameMetadata,
    TandemGainTable,
    TandemState,
)

_RUNTIME_FIELDS = {
    "uri",
    "firmware_version",
    "kernel_version",
    "hardware_model",
    "libiio_source_commit",
    "libiio_source_ref",
    "libiio_sha256",
}


def _status(
    *, state: TandemState, epoch: int = 0, endpoint: int = 43
) -> dict[str, int]:
    return {
        "state": int(state),
        "fault_flags": 0,
        "overflow_count": 0,
        "fifo_level": 0,
        "ownership_epoch": epoch,
        "transition_count": 0,
        "rx1_gain_index": endpoint,
        "rx2_gain_index": endpoint,
    }


def _hold_status(epoch: int) -> dict[str, int]:
    return _status(state=TandemState.ARMED_HOLD, epoch=epoch)


def _idle_status(endpoint: int = 43) -> dict[str, int]:
    return _status(state=TandemState.IDLE, endpoint=endpoint)


def _mute() -> dict[str, Any]:
    return {
        "verified": True,
        "tx1_gain_db": lifecycle.TX_MUTE_DB,
        "tx2_gain_db": lifecycle.TX_MUTE_DB,
        "selectors": [lifecycle.DAC_SELECT_ZERO] * 4,
        "dds": {
            f"altvoltage{index}": {
                "present": True,
                "raw": 0.0,
                "scale": 0.0,
            }
            for index in range(8)
        },
        "failures": [],
    }


def _rx(*, boot: bool = False) -> dict[str, Any]:
    if boot:
        return {"modes": ["slow_attack"] * 2, "gains_db": [71.0] * 2}
    return {"modes": ["manual"] * 2, "gains_db": [40.0] * 2}


def _rf(*, normalized: bool) -> dict[str, Any]:
    rx_lo = lifecycle.CENTER_FREQUENCY_HZ if normalized else 2_400_000_000
    tx_lo = lifecycle.CENTER_FREQUENCY_HZ if normalized else 2_450_000_000
    rate = lifecycle.SAMPLE_RATE_HZ if normalized else 30_720_000
    bandwidth = lifecycle.RF_BANDWIDTH_HZ if normalized else 18_000_000
    return {
        "rx_lo_hz": rx_lo,
        "tx_lo_hz": tx_lo,
        "channels": {
            role: {
                "sampling_frequency_hz": rate,
                "rf_bandwidth_hz": bandwidth,
            }
            for role in ("rx0", "rx1", "tx0", "tx1")
        },
    }


def _scan() -> dict[str, Any]:
    return {
        "enabled_channel_ids": list(lifecycle.RX_SCAN_IDS),
        "enabled_scan_mask": lifecycle.RX_SCAN_MASK,
        "sample_size_bytes": lifecycle.RX_SCAN_SAMPLE_BYTES,
        "layout": [
            {
                "id": channel_id,
                "index": index,
                "format": dict(lifecycle.RX_SCAN_FORMAT),
            }
            for index, channel_id in enumerate(lifecycle.RX_SCAN_IDS)
        ],
    }


def _normalization() -> dict[str, Any]:
    operations: list[dict[str, Any]] = []
    clock = 1_100
    for ordinal, (target, attribute, requested, tolerance) in enumerate(
        lifecycle._normalization_operation_contract()
    ):
        operations.append(
            {
                "ordinal": ordinal,
                "target": target,
                "attribute": attribute,
                "requested": requested,
                "readback": (
                    requested if isinstance(requested, str) else float(requested)
                ),
                "tolerance": tolerance,
                "host_before_ns": clock,
                "host_after_ns": clock + 1,
            }
        )
        clock += 10
    return {
        "verified": True,
        "policy": (
            "safe preflight, complete mute barrier, then RF/RX normalization; "
            "zero metadata buffers until every readback passes"
        ),
        "started_monotonic_ns": 1_050,
        "mute_barrier_completed_monotonic_ns": 1_075,
        "completed_monotonic_ns": 1_300,
        "metadata_buffer_open_count_before": 0,
        "metadata_buffer_open_count_after": 0,
        "mute_barrier": _mute(),
        "tandem_status_before": _idle_status(65),
        "operations": operations,
        "rf_state_after": _rf(normalized=True),
        "rx_state_after": _rx(),
        "mute_after": _mute(),
        "tandem_status_after": _idle_status(65),
        "expected_gain_table": {
            "selection_basis": "common RX/TX LO at or below 1300000000 Hz",
            "center_frequency_hz": lifecycle.CENTER_FREQUENCY_HZ,
            "gain_table_id": int(lifecycle.EXPECTED_GAIN_TABLE),
            "gain_table_name": lifecycle.EXPECTED_GAIN_TABLE.name.lower(),
            "hold_frame_attestation_required": True,
        },
    }


def _frames() -> list[TandemFrameMetadata]:
    base = TandemFrameMetadata(
        version=5,
        header_bytes=lifecycle.RAW_METADATA_BYTES,
        features=lifecycle.EXACT_METADATA_FEATURES,
        flags=lifecycle.EXACT_HOLD_METADATA_FLAGS,
        stream_id=7,
        buffer_sequence=0,
        first_sample_sequence=123_456,
        samples_per_channel=lifecycle.FRAME_SAMPLES,
        iq_payload_bytes=lifecycle.EXPECTED_IQ_BYTES,
        enabled_scan_mask=lifecycle.RX_SCAN_MASK,
        sample_format=1,
        channel_count=2,
        observation_count=4,
        observation_capacity=64,
        event_count=0,
        event_capacity=64,
        observation_overflow_count=0,
        event_overflow_count=0,
        ownership_epoch=11,
        tandem_state=TandemState.ARMED_HOLD,
        tandem_fault_flags=0,
        tandem_transition_count=0,
        gain_table_id=TandemGainTable.MHZ_200_1300,
        threshold_provenance=lifecycle.EXPECTED_THRESHOLD_PROVENANCE,
        minimum_gain_db=lifecycle.EXPECTED_MINIMUM_GAIN_DB,
        maximum_gain_db=lifecycle.EXPECTED_MAXIMUM_GAIN_DB,
        initial_gain_db=lifecycle.HOLD_GAIN_DB,
        minimum_gain_index=lifecycle.EXPECTED_MINIMUM_GAIN_INDEX,
        maximum_gain_index=lifecycle.EXPECTED_MAXIMUM_GAIN_INDEX,
        rx1_gain_index=lifecycle.EXPECTED_HOLD_GAIN_INDEX,
        rx2_gain_index=lifecycle.EXPECTED_HOLD_GAIN_INDEX,
        ad9361_temperature_mdeg_c=35_000,
        gain_events=(),
    )
    return [
        replace(
            base,
            buffer_sequence=index,
            first_sample_sequence=(
                base.first_sample_sequence + index * lifecycle.FRAME_SAMPLES
            ),
        )
        for index in range(lifecycle.BATCH_FRAMES)
    ]


def _metadata_wire(metadata: TandemFrameMetadata) -> bytes:
    payload = bytearray(lifecycle.RAW_METADATA_BYTES)
    struct.pack_into(
        "<IHHIIQQQIIIHB",
        payload,
        0,
        METADATA_MAGIC,
        5,
        lifecycle.RAW_METADATA_BYTES,
        metadata.features,
        metadata.flags,
        metadata.stream_id,
        metadata.buffer_sequence,
        metadata.first_sample_sequence,
        metadata.samples_per_channel,
        metadata.iq_payload_bytes,
        metadata.enabled_scan_mask,
        metadata.sample_format,
        metadata.channel_count,
    )
    struct.pack_into("<bbbbB", payload, 55, *(lifecycle.HOLD_GAIN_DB,) * 4, 0)
    struct.pack_into("<IIII", payload, 60, 1_000, 1_000, 0xFFFFFFFF, 0xFFFFFFFF)
    struct.pack_into("<HHHH", payload, 76, 100, 100, 100, 100)
    struct.pack_into("<III", payload, 84, 1_000, 1_000, lifecycle.FRAME_SAMPLES // 4)
    struct.pack_into(
        "<HHHHHHII",
        payload,
        96,
        metadata.observation_count,
        metadata.observation_capacity,
        GAIN_OBSERVATION_BYTES,
        metadata.event_count,
        metadata.event_capacity,
        GAIN_EVENT_BYTES,
        metadata.observation_overflow_count,
        metadata.event_overflow_count,
    )
    TANDEM_V5_EXTENSION.pack_into(
        payload,
        124,
        metadata.ownership_epoch,
        int(metadata.tandem_state),
        metadata.tandem_fault_flags,
        metadata.tandem_transition_count,
        int(metadata.gain_table_id),
        metadata.threshold_provenance,
        metadata.minimum_gain_db,
        metadata.maximum_gain_db,
        metadata.initial_gain_db,
        metadata.minimum_gain_index,
        metadata.maximum_gain_index,
        metadata.rx1_gain_index,
        metadata.rx2_gain_index,
        (
            lifecycle.TEMPERATURE_INVALID_SENTINEL
            if metadata.ad9361_temperature_mdeg_c is None
            else metadata.ad9361_temperature_mdeg_c
        ),
        0,
        0,
        0,
    )
    for index in range(metadata.observation_count):
        sample_before = metadata.first_sample_sequence + index * (
            lifecycle.FRAME_SAMPLES // 4
        )
        lifecycle.GAIN_OBSERVATION.pack_into(
            payload,
            V5_PREFIX_BYTES + index * GAIN_OBSERVATION_BYTES,
            sample_before,
            sample_before + 1,
            1_000,
            lifecycle.GAIN_OBSERVATION_FLAGS,
            metadata.rx1_gain_index,
            metadata.rx2_gain_index,
            lifecycle.HOLD_GAIN_DB,
            lifecycle.HOLD_GAIN_DB,
            0,
            0,
        )
    struct.pack_into("<I", payload, len(payload) - 4, 0)
    struct.pack_into("<I", payload, len(payload) - 4, zlib.crc32(payload) & 0xFFFFFFFF)
    return bytes(payload)


def _configuration(
    *, serial: str, firmware: str, kernel: str, hardware: str
) -> dict[str, Any]:
    return {
        "serial": serial,
        "firmware_pattern": rf"\A{re.escape(firmware)}\Z",
        "firmware_version": firmware,
        "kernel_version": kernel,
        "hardware_model": hardware,
        "tx_policy": "fully muted; no DDS/DMA enable and no TX gain increase",
        "normalization_policy": (
            "under verified mute with zero buffers: common LO, all PHY rates and "
            "bandwidths, then RX manual 40"
        ),
        "iq_evidence_policy": lifecycle.IQ_EVIDENCE_POLICY,
        "temperature_policy": lifecycle.TEMPERATURE_POLICY,
        "temperature_producer_policy": lifecycle.TEMPERATURE_PRODUCER_POLICY,
        "temperature_qualification_policy": (
            lifecycle.TEMPERATURE_QUALIFICATION_POLICY
        ),
        "temperature_producer_range_mdeg_c": [
            lifecycle.MINIMUM_TEMPERATURE_MDEG_C,
            lifecycle.MAXIMUM_TEMPERATURE_MDEG_C,
        ],
        "temperature_invalid_sentinel": lifecycle.TEMPERATURE_INVALID_SENTINEL,
        "temperature_policy_predecessor": lifecycle._temperature_policy_predecessor(),
        "observation_retention_policy": lifecycle.OBSERVATION_RETENTION_POLICY,
        "observation_retention_policy_predecessor": (
            lifecycle._observation_retention_policy_predecessor()
        ),
        "failure_artifact_policy": lifecycle.FAILURE_ARTIFACT_POLICY,
        "center_frequency_hz": lifecycle.CENTER_FREQUENCY_HZ,
        "sample_rate_hz": lifecycle.SAMPLE_RATE_HZ,
        "rf_bandwidth_hz": lifecycle.RF_BANDWIDTH_HZ,
        "expected_gain_table_id": int(lifecycle.EXPECTED_GAIN_TABLE),
        "expected_gain_table_name": lifecycle.EXPECTED_GAIN_TABLE.name.lower(),
        "tandem_mode": "hold",
        "hold_gain_db": lifecycle.HOLD_GAIN_DB,
        "frame_samples_per_channel": lifecycle.FRAME_SAMPLES,
        "kernel_buffers": lifecycle.KERNEL_BUFFERS,
        "batch_frames": lifecycle.BATCH_FRAMES,
        "metadata_capacity_bytes": lifecycle.METADATA_CAPACITY,
        "expected_batch_cache_bytes": lifecycle.EXPECTED_BATCH_CACHE_BYTES,
    }


def build_lifecycle_v5_archive(
    *,
    report_path: Path,
    lineage: Mapping[str, object],
    runner_provenance: Mapping[str, object],
    serial: str,
    runtime: Mapping[str, str],
) -> tuple[dict[str, object], dict[str, bytes]]:
    """Return one exact producer-shaped report and its 65 archived raw wires."""

    if set(runtime) != _RUNTIME_FIELDS or any(
        type(value) is not str or not value for value in runtime.values()
    ):
        raise ValueError("lifecycle test runtime fields are not exact nonempty strings")
    report_path = report_path.absolute()
    if report_path.name != lifecycle.REPORT_FILENAME or ".." in report_path.parts:
        raise ValueError("lifecycle test report path is not canonical v5 output")
    firmware = runtime["firmware_version"]
    kernel = runtime["kernel_version"]
    hardware = runtime["hardware_model"]
    libiio_commit = runtime["libiio_source_commit"]
    libiio_ref = runtime["libiio_source_ref"]
    libiio_sha = runtime["libiio_sha256"]
    source_values = lineage.get("source_manifest")
    source_values = (
        source_values.get("values") if isinstance(source_values, Mapping) else None
    )
    expected_lineage = {
        "serial": serial,
        "firmware_version": firmware,
        "kernel_version": kernel,
        "hardware_model": hardware,
        "firmware_pattern": rf"\A{re.escape(firmware)}\Z",
    }
    if any(lineage.get(key) != value for key, value in expected_lineage.items()):
        raise ValueError("lifecycle test runtime differs from candidate lineage")
    if (
        not isinstance(source_values, Mapping)
        or source_values.get("libiio_0_25_source") != libiio_commit
        or source_values.get("libiio_0_25_ref") != libiio_ref
        or re.fullmatch(r"[0-9a-f]{40}", libiio_commit) is None
        or not libiio_ref.startswith("refs/tags/")
        or re.fullmatch(r"[0-9a-f]{64}", libiio_sha) is None
        or not runtime["uri"].startswith("usb:")
    ):
        raise ValueError("lifecycle test host/runtime identity is invalid")

    frames = _frames()
    full_wires = [_metadata_wire(frame) for frame in frames]
    cancel_metadata = replace(
        frames[0],
        stream_id=8,
        ownership_epoch=12,
        first_sample_sequence=9_000_000,
    )
    cancel_wire = _metadata_wire(cancel_metadata)
    frame_records = [
        lifecycle._frame_evidence(
            index,
            frame,
            duration_ns=index + 1,
            returned_iq_sha256_in_process="a" * 64,
            metadata_sha256=hashlib.sha256(full_wires[index]).hexdigest(),
        )
        for index, frame in enumerate(frames)
    ]
    cancel_record = lifecycle._frame_evidence(
        0,
        cancel_metadata,
        duration_ns=10,
        returned_iq_sha256_in_process="c" * 64,
        metadata_sha256=hashlib.sha256(cancel_wire).hexdigest(),
    )
    captures = [
        *(("full_drain", index, payload) for index, payload in enumerate(full_wires)),
        ("cancel_first", 0, cancel_wire),
    ]
    metadata_artifacts = lifecycle._new_metadata_artifact_manifest(captures)
    for entry in metadata_artifacts["entries"]:
        entry["write_completed"] = True
    metadata_artifacts["completed_file_count"] = lifecycle.RAW_METADATA_FILE_COUNT
    metadata_artifacts["inventory_state"] = "complete"
    raw_metadata = {
        lifecycle._metadata_relative_path(role, ordinal).as_posix(): payload
        for role, ordinal, payload in captures
    }

    final_status = _idle_status()
    cleanup = _mute()
    cleanup.update(
        {
            "started_monotonic_ns": 1_810,
            "mute_completed_monotonic_ns": 1_820,
            "idle_verified_monotonic_ns": 1_830,
            "rx_completed_monotonic_ns": 1_840,
            "final_idle_verified_monotonic_ns": 1_850,
            "rf_readback_completed_monotonic_ns": 1_860,
            "operation_order": [
                "force_mute",
                "verify_idle",
                "configure_manual40",
                "verify_final_idle",
                "read_final_rf",
            ],
            "tandem_status": final_status,
            "rx_state": _rx(),
            "rf_state": _rf(normalized=True),
            "errors": [],
        }
    )
    preflight = {
        "verdict": "GO",
        "serial": serial,
        "uri": runtime["uri"],
        "firmware_version": firmware,
        "context_attrs": {
            "hw_serial": serial,
            "fw_version": firmware,
            "hw_model": hardware,
            "ad9361-phy,model": "ad9361",
            "local,kernel": kernel,
            "iio,buffer-metadata": "2",
            "uri": runtime["uri"],
        },
        "mute": _mute(),
        "rx_state": _rx(boot=True),
        "rf_state": _rf(normalized=False),
        "tandem_status": _idle_status(65),
        "started_monotonic_ns": 900,
        "completed_monotonic_ns": 1_000,
        "configuration_write_count": 0,
        "metadata_buffer_open_count": 0,
    }
    host_root = report_path.parent / ".observed-host-libiio"
    host_source = host_root / "source"
    host_build = host_root / "build"
    host_library = host_build / "libiio.so.0.25"
    host = {
        "source_commit": libiio_commit,
        "protected_source_tag": libiio_ref.removeprefix("refs/tags/"),
        "source_directory": str(host_source),
        "build_directory": str(host_build),
        "mapped_shared_objects": [str(host_library)],
        "mapped_shared_object": str(host_library),
        "mapped_shared_object_sha256": libiio_sha,
        "runner_shared_object_sha256": libiio_sha,
        "pylibiio_file": str(host_source / "bindings/python/iio.py"),
    }
    output_parent = report_path.parent
    output_preflight = {
        "verified": True,
        "absolute_report_path": str(report_path),
        "absolute_temporary_path": str(
            report_path.with_suffix(report_path.suffix + ".tmp")
        ),
        "absolute_raw_metadata_directory": str(
            output_parent / lifecycle.RAW_METADATA_DIRECTORY
        ),
        "report_existed_before_context": False,
        "temporary_existed_before_context": False,
        "raw_metadata_directory_existed_before_context": False,
        "symlink_components": 0,
        "output_parent_device": 1,
        "output_parent_inode": 1,
    }
    report: dict[str, object] = {
        "schema": lifecycle.SCHEMA,
        "verdict": "PASS",
        "release_claim": "none; muted host-transport lifecycle qualification only",
        "release_pass_eligible": False,
        "hardware_qualified": False,
        "started_unix_ns": 1,
        "completed_unix_ns": 2,
        "host_libiio": host,
        "runner_provenance": dict(runner_provenance),
        "expected_device_firmware_lineage": dict(lineage),
        "device_firmware_provenance": lifecycle._observed_device_firmware_provenance(
            lineage, preflight=preflight
        ),
        "configuration": _configuration(
            serial=serial,
            firmware=firmware,
            kernel=kernel,
            hardware=hardware,
        ),
        "output_preflight": output_preflight,
        "preflight": preflight,
        "normalization": _normalization(),
        "rx_scan": _scan(),
        "full_drain": {
            "kernel_buffers": lifecycle.KERNEL_BUFFERS,
            "batch_frames": lifecycle.BATCH_FRAMES,
            "metadata_capacity_bytes": lifecycle.METADATA_CAPACITY,
            "batch_cache_bound_bytes": lifecycle.EXPECTED_BATCH_CACHE_BYTES,
            "expected_batch_cache_bytes": lifecycle.EXPECTED_BATCH_CACHE_BYTES,
            "normalization_completed_monotonic_ns": 1_300,
            "first_buffer_open_requested_monotonic_ns": 1_400,
            "status_after_open": _hold_status(11),
            "status_before_close": _hold_status(11),
            "close_method": "explicit_normal_close",
            "close_completed_monotonic_ns": 1_500,
            "frames": frame_records,
            "continuity": {
                "verified": True,
                "frame_count": lifecycle.BATCH_FRAMES,
                "stream_id": 7,
                "ownership_epoch": 11,
                "buffer_sequence_range": [0, lifecycle.BATCH_FRAMES - 1],
                "sample_sequence_range": [
                    123_456,
                    123_456 + lifecycle.BATCH_FRAMES * lifecycle.FRAME_SAMPLES,
                ],
                "sample_gaps": 0,
                "gain_events": 0,
                "faults": 0,
                "overflows": 0,
            },
            "status_after_close": _idle_status(),
        },
        "post_full_drain_barrier": {
            "verified": True,
            "policy": "force mute, verify closed HOLD IDLE, then read RX without writes",
            "started_monotonic_ns": 1_510,
            "mute_completed_monotonic_ns": 1_520,
            "idle_verified_monotonic_ns": 1_530,
            "completed_monotonic_ns": 1_540,
            "metadata_buffer_open_count": 0,
            "operation_order": ["force_mute", "verify_idle", "read_rx_state"],
            "mute": _mute(),
            "tandem_status": _idle_status(),
            "rx_state": _rx(),
        },
        "cancel_lifecycle": {
            "verified": True,
            "kernel_buffers": lifecycle.KERNEL_BUFFERS,
            "batch_frames": lifecycle.BATCH_FRAMES,
            "old_buffer_open_requested_monotonic_ns": 1_600,
            "operation_order": [
                "first_cached_frame_returned",
                "old_buffer_cancel",
                "second_open_ebusy",
                "old_refill_ebadf",
                "old_buffer_close",
                "mute_after_old_close",
                "verify_old_close_idle",
                "fresh_buffer_open",
                "fresh_buffer_close",
            ],
            "status_after_old_open": _hold_status(12),
            "first_returned_cached_frame": cancel_record,
            "second_open_error": {
                "type": "OSError",
                "errno": 16,
                "message": "busy",
            },
            "poison_refill_error": {
                "type": "OSError",
                "errno": 9,
                "message": "bad fd",
            },
            "old_buffer_close_completed_monotonic_ns": 1_700,
            "mute_after_old_close_started_monotonic_ns": 1_710,
            "mute_after_old_close": _mute(),
            "mute_after_old_close_completed_monotonic_ns": 1_720,
            "old_close_idle_verified_monotonic_ns": 1_730,
            "status_after_old_close": _idle_status(),
            "fresh_buffer_open_requested_monotonic_ns": 1_740,
            "status_after_fresh_open": _hold_status(13),
            "status_after_fresh_close": final_status,
            "fresh_buffer_close_completed_monotonic_ns": 1_800,
        },
        "temperature_evidence": lifecycle._temperature_evidence(
            [frame.ad9361_temperature_mdeg_c for frame in frames],
            cancel_metadata.ad9361_temperature_mdeg_c,
        ),
        "metadata_artifacts": metadata_artifacts,
        "final_tandem_status": final_status,
        "final_rx_state": _rx(),
        "final_rf_state": _rf(normalized=True),
        "cleanup": cleanup,
    }
    lifecycle.validate_archived_pass_report(report, raw_metadata=raw_metadata)
    return report, raw_metadata
