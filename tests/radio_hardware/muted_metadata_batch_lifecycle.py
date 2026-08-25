"""Guarded, RF-muted USB metadata-batch lifecycle qualification.

This module deliberately has no transmit-arm operation.  Its only TX writes
are three independent mute barriers: both hardware attenuators at -89.75 dB,
all DDS raw/scale attributes at zero, and all DAC selectors at ZERO.  The
acquisition request is tandem HOLD at 40 dB, so no gain event is expected.
"""

# Fail-safe mute, close, unlock, and evidence persistence must also run for
# cancellation signals and other non-Exception exits.
# ruff: noqa: BLE001

from __future__ import annotations

import argparse
import ctypes
import errno
import fcntl
import gc
import hashlib
import json
import math
import os
import pathlib
import re
import sys
import time
from collections.abc import Mapping, Sequence
from typing import Any

from .metadata_abi import (
    FEATURE_AD9361_TEMPERATURE,
    FEATURE_FPGA_GAIN_EVENTS,
    FEATURE_HARDWARE_SAMPLE_COUNTER,
    FEATURE_TANDEM_METADATA,
    FLAG_HARDWARE_SAMPLE_COUNTER_VALID,
    FLAG_SAMPLE_SEQUENCE_VALID,
    FLAG_TANDEM_METADATA_VALID,
    TANDEM_UNSAFE_FLAGS,
    TandemFrameMetadata,
    TandemGainTable,
    TandemMode,
    TandemState,
    build_tandem_request,
    close_iio_object,
    create_metadata_buffer,
    parse_tandem_frame_metadata,
)

SCHEMA = "plutosdr-fw.muted-metadata-batch-lifecycle.v1"
EXACT_LIBIIO_COMMIT = "70739d25ec1fa7b95d9069bd26a3e4192fdb3851"
DEFAULT_R18_SERIAL = "1040007c4a94000211000b009186843ef2"
TX_MUTE_DB = -89.75
DAC_SELECT_ZERO = 0x3
FRAME_SAMPLES = 65_536
KERNEL_BUFFERS = 8
BATCH_FRAMES = 64
METADATA_CAPACITY = 64 * 1024
HOLD_GAIN_DB = 40
EXPECTED_IQ_BYTES = FRAME_SAMPLES * 8
EXPECTED_BATCH_CACHE_BYTES = BATCH_FRAMES * (
    EXPECTED_IQ_BYTES + METADATA_CAPACITY + 2 * ctypes.sizeof(ctypes.c_size_t)
)
REQUIRED_FEATURES = (
    FEATURE_AD9361_TEMPERATURE
    | FEATURE_FPGA_GAIN_EVENTS
    | FEATURE_HARDWARE_SAMPLE_COUNTER
    | FEATURE_TANDEM_METADATA
)
REQUIRED_FLAGS = (
    FLAG_HARDWARE_SAMPLE_COUNTER_VALID
    | FLAG_SAMPLE_SEQUENCE_VALID
    | FLAG_TANDEM_METADATA_VALID
)
EXPECTED_GAIN_TABLE = TandemGainTable.MHZ_200_1300
EXPECTED_MINIMUM_GAIN_DB = 0
EXPECTED_MAXIMUM_GAIN_DB = 62
EXPECTED_MINIMUM_GAIN_INDEX = 3
EXPECTED_MAXIMUM_GAIN_INDEX = 65
RX_SCAN_IDS = ("voltage0", "voltage1", "voltage2", "voltage3")
RX_SCAN_MASK = 0x0F
RX_SCAN_SAMPLE_BYTES = 8
RX_SCAN_FORMAT = {
    "length": 16,
    "bits": 16,
    "shift": 0,
    "is_signed": True,
    "is_be": False,
    "repeat": 1,
}


class QualificationError(RuntimeError):
    """Evidence is unsafe, incomplete, or inconsistent."""


def _atomic_json(path: pathlib.Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _error_record(error: BaseException) -> dict[str, Any]:
    return {
        "type": type(error).__name__,
        "errno": getattr(error, "errno", None),
        "message": str(error),
    }


def _first_float(value: Any) -> float:
    return float(str(value).strip().split()[0])


def _read_attr(owner: Any, name: str) -> str:
    if name not in owner.attrs:
        raise QualificationError(f"{getattr(owner, 'id', owner)!r} lacks {name}")
    return str(owner.attrs[name].value)


def _write_numeric(owner: Any, name: str, value: float, *, tolerance: float) -> float:
    if name not in owner.attrs:
        raise QualificationError(f"{getattr(owner, 'id', owner)!r} lacks {name}")
    owner.attrs[name].value = str(value)
    observed = _first_float(owner.attrs[name].value)
    if abs(observed - value) > tolerance:
        raise QualificationError(
            f"{getattr(owner, 'id', owner)!r} {name} readback {observed} "
            f"differs from {value}"
        )
    return observed


def _channel(device: Any, name: str, output: bool) -> Any:
    value = device.find_channel(name, output)
    if value is None:
        raise QualificationError(f"{device.id} lacks channel {name!r}, output={output}")
    return value


def _selector_address(index: int) -> int:
    return 0x0418 + index * 0x40


def _legacy_address(index: int) -> int:
    return 0x0414 + index * 0x40


def _mapped_libiio() -> list[str]:
    paths = {
        str(pathlib.Path(line.rsplit(maxsplit=1)[-1]).resolve())
        for line in pathlib.Path("/proc/self/maps")
        .read_text(encoding="utf-8")
        .splitlines()
        if "/libiio.so" in line.rsplit(maxsplit=1)[-1]
    }
    return sorted(paths)


def _sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _attest_mapped_libiio() -> dict[str, Any]:
    mapped = _mapped_libiio()
    if len(mapped) != 1:
        raise QualificationError(f"expected one mapped libiio, got {mapped}")
    mapped_path = pathlib.Path(mapped[0]).resolve()
    expected_path_text = os.environ.get("PLUTOSDR_FW_LIBIIO_PATH", "")
    build_text = os.environ.get("PLUTOSDR_FW_LIBIIO_BUILD", "")
    source_text = os.environ.get("PLUTOSDR_FW_LIBIIO_SOURCE", "")
    expected_sha = os.environ.get("PLUTOSDR_FW_LIBIIO_SHA256", "")
    if not all((expected_path_text, build_text, source_text)):
        raise QualificationError("runner omitted libiio path/build/source attestation")
    expected_path = pathlib.Path(expected_path_text).resolve()
    build = pathlib.Path(build_text).resolve()
    source = pathlib.Path(source_text).resolve()
    if mapped_path != expected_path or not mapped_path.is_relative_to(build):
        raise QualificationError(
            f"mapped libiio {mapped_path} is not runner build artifact {expected_path}"
        )
    calculated_sha = _sha256_file(mapped_path)
    if calculated_sha != expected_sha:
        raise QualificationError(
            f"mapped libiio SHA-256 {calculated_sha} != runner {expected_sha}"
        )
    cache = build / "CMakeCache.txt"
    if not cache.is_file():
        raise QualificationError(f"libiio build cache is absent: {cache}")
    home = None
    for line in cache.read_text(encoding="utf-8").splitlines():
        if line.startswith("CMAKE_HOME_DIRECTORY:INTERNAL="):
            home = pathlib.Path(line.split("=", 1)[1]).resolve()
            break
    if home != source:
        raise QualificationError(
            f"libiio build source {home} does not match runner source {source}"
        )
    return {
        "source_commit": EXACT_LIBIIO_COMMIT,
        "source_directory": str(source),
        "build_directory": str(build),
        "mapped_shared_objects": [str(mapped_path)],
        "mapped_shared_object": str(mapped_path),
        "mapped_shared_object_sha256": calculated_sha,
        "runner_shared_object_sha256": expected_sha,
    }


def _attest_runner_provenance() -> dict[str, str]:
    commit = os.environ.get("PLUTOSDR_FW_RUNNER_COMMIT", "")
    module_sha = os.environ.get("PLUTOSDR_FW_RUNNER_MODULE_SHA256", "")
    module_head_sha = os.environ.get("PLUTOSDR_FW_RUNNER_MODULE_HEAD_SHA256", "")
    shell_sha = os.environ.get("PLUTOSDR_FW_RUNNER_SHELL_SHA256", "")
    shell_head_sha = os.environ.get("PLUTOSDR_FW_RUNNER_SHELL_HEAD_SHA256", "")
    shell_text = os.environ.get("PLUTOSDR_FW_RUNNER_SHELL_PATH", "")
    metadata_abi_sha = os.environ.get("PLUTOSDR_FW_RUNNER_METADATA_ABI_SHA256", "")
    metadata_abi_head_sha = os.environ.get(
        "PLUTOSDR_FW_RUNNER_METADATA_ABI_HEAD_SHA256", ""
    )
    metadata_abi_text = os.environ.get("PLUTOSDR_FW_RUNNER_METADATA_ABI_PATH", "")
    module_path = pathlib.Path(__file__).resolve()
    shell_path = pathlib.Path(shell_text).resolve() if shell_text else pathlib.Path()
    metadata_abi_path = (
        pathlib.Path(metadata_abi_text).resolve()
        if metadata_abi_text
        else pathlib.Path()
    )
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise QualificationError("runner firmware-repository commit is invalid")
    if not shell_text or not shell_path.is_absolute() or not shell_path.is_file():
        raise QualificationError("runner shell path is absent or non-absolute")
    if (
        not metadata_abi_text
        or not metadata_abi_path.is_absolute()
        or not metadata_abi_path.is_file()
        or metadata_abi_path != module_path.parent / "metadata_abi.py"
    ):
        raise QualificationError(
            "runner metadata ABI path is absent, non-absolute, or unexpected"
        )
    calculated_module_sha = _sha256_file(module_path)
    calculated_shell_sha = _sha256_file(shell_path)
    calculated_metadata_abi_sha = _sha256_file(metadata_abi_path)
    if (
        calculated_module_sha != module_sha
        or calculated_module_sha != module_head_sha
        or calculated_shell_sha != shell_sha
        or calculated_shell_sha != shell_head_sha
        or calculated_metadata_abi_sha != metadata_abi_sha
        or calculated_metadata_abi_sha != metadata_abi_head_sha
    ):
        raise QualificationError("runner source SHA-256 does not match its process")
    return {
        "firmware_repo_commit": commit,
        "python_module_path": str(module_path),
        "python_module_sha256": calculated_module_sha,
        "python_module_head_blob_sha256": module_head_sha,
        "shell_runner_path": str(shell_path),
        "shell_runner_sha256": calculated_shell_sha,
        "shell_runner_head_blob_sha256": shell_head_sha,
        "metadata_abi_path": str(metadata_abi_path),
        "metadata_abi_sha256": calculated_metadata_abi_sha,
        "metadata_abi_head_blob_sha256": metadata_abi_head_sha,
    }


def _read_mute(phy: Any, tx: Any) -> dict[str, Any]:
    gains = [
        _first_float(_read_attr(_channel(phy, f"voltage{i}", True), "hardwaregain"))
        for i in (0, 1)
    ]
    dds: dict[str, Any] = {}
    for index in range(8):
        name = f"altvoltage{index}"
        channel = tx.find_channel(name, True)
        record: dict[str, Any] = {"present": channel is not None}
        if channel is not None:
            for attribute in ("raw", "scale"):
                if attribute in channel.attrs:
                    record[attribute] = _first_float(channel.attrs[attribute].value)
        dds[name] = record
    selectors = [int(tx.reg_read(_selector_address(i))) & 0xF for i in range(4)]
    failures: list[str] = []
    if any(gain > -80.0 for gain in gains):
        failures.append(f"TX hardware gains are not muted: {gains}")
    if selectors != [DAC_SELECT_ZERO] * 4:
        failures.append(f"DAC selectors are not ZERO: {selectors}")
    expected_dds = {f"altvoltage{i}" for i in range(8)}
    if set(dds) != expected_dds or any(not item["present"] for item in dds.values()):
        failures.append("DDS evidence does not cover all eight channels")
    for name, item in dds.items():
        for attribute in ("raw", "scale"):
            if attribute not in item or abs(float(item[attribute])) > 1e-9:
                failures.append(f"{name} {attribute} is not zero")
    return {
        "verified": not failures,
        "tx1_gain_db": gains[0],
        "tx2_gain_db": gains[1],
        "selectors": selectors,
        "dds": dds,
        "failures": failures,
    }


def _force_mute(phy: Any, tx: Any) -> dict[str, Any]:
    failures: list[str] = []
    for index in (0, 1):
        try:
            _write_numeric(
                _channel(phy, f"voltage{index}", True),
                "hardwaregain",
                TX_MUTE_DB,
                tolerance=0.26,
            )
        except BaseException as error:  # preserve attempts on every mute path
            failures.append(f"TX{index + 1} gain mute: {error}")
    for index in range(8):
        channel = tx.find_channel(f"altvoltage{index}", True)
        if channel is None:
            failures.append(f"DDS altvoltage{index} missing")
            continue
        for attribute in ("raw", "scale"):
            try:
                _write_numeric(channel, attribute, 0.0, tolerance=1e-9)
            except BaseException as error:
                failures.append(f"DDS altvoltage{index} {attribute}: {error}")
    for index in range(4):
        try:
            legacy = int(tx.reg_read(_legacy_address(index)))
            tx.reg_write(_legacy_address(index), legacy & ~1)
            tx.reg_write(_selector_address(index), DAC_SELECT_ZERO)
        except BaseException as error:
            failures.append(f"DAC selector {index} ZERO: {error}")
    evidence = _read_mute(phy, tx)
    failures.extend(evidence["failures"])
    evidence["failures"] = failures
    evidence["verified"] = not failures
    if failures:
        raise QualificationError("; ".join(failures))
    return evidence


def _read_rx_state(phy: Any) -> dict[str, list[Any]]:
    channels = [_channel(phy, f"voltage{i}", False) for i in (0, 1)]
    return {
        "modes": [_read_attr(channel, "gain_control_mode") for channel in channels],
        "gains_db": [
            _first_float(_read_attr(channel, "hardwaregain")) for channel in channels
        ],
    }


def _configure_manual_40(phy: Any) -> dict[str, list[Any]]:
    channels = [_channel(phy, f"voltage{i}", False) for i in (0, 1)]
    for channel in channels:
        channel.attrs["gain_control_mode"].value = "manual"
    for channel in channels:
        _write_numeric(channel, "hardwaregain", HOLD_GAIN_DB, tolerance=0.1)
    state = _read_rx_state(phy)
    if state["modes"] != ["manual", "manual"] or any(
        abs(gain - HOLD_GAIN_DB) > 0.1 for gain in state["gains_db"]
    ):
        raise QualificationError(f"RX manual-40 readback failed: {state}")
    return state


def _configure_dual_complex_rx_scan(rx: Any) -> dict[str, Any]:
    """Enable exact I0/Q0/I1/Q1 scalar lanes and attest their CS16LE shape."""

    expected_ids = set(RX_SCAN_IDS)
    scan_channels: dict[str, Any] = {}
    for channel in rx.channels:
        if not channel.scan_element:
            continue
        if channel.id in expected_ids:
            if channel.id in scan_channels:
                raise QualificationError(f"duplicate RX scan channel {channel.id!r}")
            scan_channels[channel.id] = channel
    if set(scan_channels) != expected_ids:
        missing = sorted(expected_ids - set(scan_channels))
        raise QualificationError(f"RX scan layout lacks channels {missing}")

    layout: list[dict[str, Any]] = []
    observed_indices: list[int] = []
    for expected_index, channel_id in enumerate(RX_SCAN_IDS):
        channel = scan_channels[channel_id]
        try:
            observed_index = channel.index
        except AttributeError as error:
            raise QualificationError(
                f"RX {channel_id} does not expose its scan index"
            ) from error
        if type(observed_index) is not int:
            raise QualificationError(
                f"RX {channel_id} scan index is not an exact integer"
            )
        if observed_index != expected_index:
            raise QualificationError(
                f"RX {channel_id} scan index {observed_index}, expected "
                f"{expected_index}"
            )
        if observed_index in observed_indices:
            raise QualificationError(f"duplicate RX scan index {observed_index}")
        observed_indices.append(observed_index)

        observed_format: dict[str, Any] | None = None
        try:
            data_format = channel.data_format
        except AttributeError as error:
            raise QualificationError(
                f"RX {channel_id} does not expose its scan format"
            ) from error
        try:
            observed_format = {
                "length": data_format.length,
                "bits": data_format.bits,
                "shift": data_format.shift,
                "is_signed": data_format.is_signed,
                "is_be": data_format.is_be,
                "repeat": data_format.repeat,
            }
        except AttributeError as error:
            raise QualificationError(
                f"RX {channel_id} does not expose its complete scan format"
            ) from error
        for field in ("length", "bits", "shift", "repeat"):
            if type(observed_format[field]) is not int:
                raise QualificationError(
                    f"RX {channel_id} scan format {field} is not an exact integer"
                )
        for field in ("is_signed", "is_be"):
            if type(observed_format[field]) is not bool:
                raise QualificationError(
                    f"RX {channel_id} scan format {field} is not an exact boolean"
                )
        if observed_format != RX_SCAN_FORMAT:
            raise QualificationError(
                f"RX {channel_id} scan format {observed_format}, expected "
                f"{RX_SCAN_FORMAT}"
            )
        layout.append(
            {
                "id": channel_id,
                "index": observed_index,
                "format": observed_format,
            }
        )

    for channel in rx.channels:
        if channel.scan_element:
            channel.enabled = channel.id in expected_ids

    enabled_readback: list[tuple[int, str]] = []
    for channel in rx.channels:
        if not channel.scan_element:
            continue
        enabled = channel.enabled
        if type(enabled) is not bool:
            raise QualificationError(
                f"RX {channel.id} enabled readback is not an exact boolean"
            )
        if not enabled:
            continue
        index = channel.index
        if type(index) is not int:
            raise QualificationError(
                f"enabled RX {channel.id} scan index is not an exact integer"
            )
        enabled_readback.append((index, channel.id))
    enabled_readback.sort()
    expected_readback = list(enumerate(RX_SCAN_IDS))
    if enabled_readback != expected_readback:
        raise QualificationError(
            f"RX enabled scan readback changed: {enabled_readback}"
        )
    enabled_ids = [channel_id for _, channel_id in enabled_readback]
    enabled_mask = sum(1 << index for index, _ in enabled_readback)
    if enabled_mask != RX_SCAN_MASK:
        raise QualificationError(
            f"RX enabled scan mask 0x{enabled_mask:02x}, expected 0x{RX_SCAN_MASK:02x}"
        )
    sample_size = rx.sample_size
    if type(sample_size) is not int:
        raise QualificationError("dual-complex RX sample size is not an exact integer")
    if sample_size != RX_SCAN_SAMPLE_BYTES:
        raise QualificationError(
            f"dual-complex RX sample size is {sample_size}, expected "
            f"{RX_SCAN_SAMPLE_BYTES}"
        )
    return {
        "enabled_channel_ids": enabled_ids,
        "enabled_scan_mask": enabled_mask,
        "sample_size_bytes": sample_size,
        "layout": layout,
    }


_STATUS_NAMES = (
    "state",
    "fault_flags",
    "overflow_count",
    "fifo_level",
    "ownership_epoch",
    "transition_count",
    "rx1_gain_index",
    "rx2_gain_index",
)


def _status(tandem: Any) -> dict[str, int]:
    return {name: int(_read_attr(tandem, name)) for name in _STATUS_NAMES}


def _require_idle(status: Mapping[str, Any], *, label: str) -> dict[str, int]:
    if set(status) != set(_STATUS_NAMES) or any(
        type(status.get(name)) is not int for name in _STATUS_NAMES
    ):
        raise QualificationError(f"{label} status fields are not exact integers")
    result = {name: status[name] for name in _STATUS_NAMES}
    required = {
        "state": int(TandemState.IDLE),
        "fault_flags": 0,
        "overflow_count": 0,
        "fifo_level": 0,
        "ownership_epoch": 0,
        "transition_count": 0,
    }
    if any(result[name] != expected for name, expected in required.items()):
        raise QualificationError(f"{label} is not clean IDLE: {result}")
    if result["rx1_gain_index"] != result["rx2_gain_index"]:
        raise QualificationError(f"{label} endpoints are not paired: {result}")
    return result


def _require_hold(status: Mapping[str, Any], *, label: str) -> dict[str, int]:
    if set(status) != set(_STATUS_NAMES) or any(
        type(status.get(name)) is not int for name in _STATUS_NAMES
    ):
        raise QualificationError(f"{label} status fields are not exact integers")
    result = {name: status[name] for name in _STATUS_NAMES}
    if (
        result["state"] != int(TandemState.ARMED_HOLD)
        or result["ownership_epoch"] <= 0
        or result["fault_flags"] != 0
        or result["overflow_count"] != 0
        or result["fifo_level"] != 0
        or result["transition_count"] != 0
        or result["rx1_gain_index"] != result["rx2_gain_index"]
    ):
        raise QualificationError(f"{label} is not clean owned HOLD: {result}")
    return result


def _wait_idle(tandem: Any, *, label: str) -> dict[str, int]:
    deadline = time.monotonic() + 2.0
    while True:
        current = _status(tandem)
        try:
            return _require_idle(current, label=label)
        except QualificationError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.01)


def _frame_record(
    ordinal: int, metadata_bytes: bytes, iq: bytes, duration_ns: int
) -> tuple[dict[str, Any], TandemFrameMetadata]:
    metadata = parse_tandem_frame_metadata(metadata_bytes)
    if len(iq) != EXPECTED_IQ_BYTES:
        raise QualificationError(
            f"frame {ordinal} IQ bytes {len(iq)} != {EXPECTED_IQ_BYTES}"
        )
    record = _frame_evidence(
        ordinal,
        metadata,
        duration_ns=duration_ns,
        iq_sha256=hashlib.sha256(iq).hexdigest(),
        metadata_sha256=hashlib.sha256(metadata_bytes).hexdigest(),
    )
    if record["metadata_bytes"] != len(metadata_bytes):
        raise QualificationError(
            f"frame {ordinal} metadata bytes {len(metadata_bytes)} changed"
        )
    return record, metadata


def _frame_evidence(
    ordinal: int,
    metadata: TandemFrameMetadata,
    *,
    duration_ns: int,
    iq_sha256: str,
    metadata_sha256: str,
) -> dict[str, Any]:
    """Build the JSON-domain record separately from wire parsing for oracles."""

    return {
        "ordinal": ordinal,
        "refill_duration_ns": duration_ns,
        "iq_bytes": EXPECTED_IQ_BYTES,
        "iq_sha256": iq_sha256,
        "metadata_bytes": metadata.header_bytes,
        "metadata_sha256": metadata_sha256,
        "version": metadata.version,
        "header_bytes": metadata.header_bytes,
        "features": metadata.features,
        "stream_id": metadata.stream_id,
        "buffer_sequence": metadata.buffer_sequence,
        "first_sample_sequence": metadata.first_sample_sequence,
        "samples_per_channel": metadata.samples_per_channel,
        "iq_payload_bytes": metadata.iq_payload_bytes,
        "enabled_scan_mask": metadata.enabled_scan_mask,
        "sample_format": metadata.sample_format,
        "channel_count": metadata.channel_count,
        "flags": metadata.flags,
        "observation_count": metadata.observation_count,
        "observation_capacity": metadata.observation_capacity,
        "event_capacity": metadata.event_capacity,
        "ownership_epoch": metadata.ownership_epoch,
        "tandem_state": int(metadata.tandem_state),
        "tandem_state_name": metadata.tandem_state.name.lower(),
        "tandem_fault_flags": metadata.tandem_fault_flags,
        "tandem_transition_count": metadata.tandem_transition_count,
        "gain_table_id": int(metadata.gain_table_id),
        "gain_table_name": metadata.gain_table_id.name.lower(),
        "threshold_provenance": metadata.threshold_provenance,
        "minimum_gain_db": metadata.minimum_gain_db,
        "maximum_gain_db": metadata.maximum_gain_db,
        "initial_gain_db": metadata.initial_gain_db,
        "minimum_gain_index": metadata.minimum_gain_index,
        "maximum_gain_index": metadata.maximum_gain_index,
        "rx1_gain_index": metadata.rx1_gain_index,
        "rx2_gain_index": metadata.rx2_gain_index,
        "event_count": metadata.event_count,
        "observation_overflow_count": metadata.observation_overflow_count,
        "event_overflow_count": metadata.event_overflow_count,
    }


def _validate_hold_metadata(metadata: TandemFrameMetadata, *, ordinal: int) -> None:
    if metadata.stream_id <= 0 or metadata.ownership_epoch <= 0:
        raise QualificationError(f"frame {ordinal} stream/epoch is not nonzero")
    if metadata.features & REQUIRED_FEATURES != REQUIRED_FEATURES:
        raise QualificationError(f"frame {ordinal} lacks a required feature")
    if metadata.flags & REQUIRED_FLAGS != REQUIRED_FLAGS:
        raise QualificationError(f"frame {ordinal} lacks a required validity flag")
    if metadata.flags & TANDEM_UNSAFE_FLAGS or metadata.tandem_fault_flags:
        raise QualificationError(f"frame {ordinal} carries an unsafe flag")
    if (
        metadata.version != 5
        or metadata.header_bytes != 3_256
        or metadata.samples_per_channel != FRAME_SAMPLES
        or metadata.iq_payload_bytes != EXPECTED_IQ_BYTES
        or metadata.enabled_scan_mask != 0x0F
        or metadata.sample_format != 1
        or metadata.channel_count != 2
        or metadata.observation_capacity != 64
        or metadata.event_capacity != 64
    ):
        raise QualificationError(f"frame {ordinal} wire layout changed")
    if (
        not 0 <= metadata.observation_count <= metadata.observation_capacity
        or metadata.threshold_provenance <= 0
    ):
        raise QualificationError(f"frame {ordinal} observation/provenance is invalid")
    if metadata.tandem_state is not TandemState.ARMED_HOLD:
        raise QualificationError(f"frame {ordinal} is not HOLD")
    if (
        metadata.gain_table_id is not EXPECTED_GAIN_TABLE
        or metadata.minimum_gain_db != EXPECTED_MINIMUM_GAIN_DB
        or metadata.maximum_gain_db != EXPECTED_MAXIMUM_GAIN_DB
        or metadata.initial_gain_db != HOLD_GAIN_DB
        or metadata.minimum_gain_index != EXPECTED_MINIMUM_GAIN_INDEX
        or metadata.maximum_gain_index != EXPECTED_MAXIMUM_GAIN_INDEX
    ):
        raise QualificationError(f"frame {ordinal} HOLD gain provenance changed")
    if not (
        metadata.minimum_gain_index
        <= metadata.rx1_gain_index
        == metadata.rx2_gain_index
        <= metadata.maximum_gain_index
    ):
        raise QualificationError(f"frame {ordinal} endpoint is torn or out of range")
    if (
        metadata.tandem_transition_count != 0
        or metadata.event_count != 0
        or metadata.gain_events
    ):
        raise QualificationError(f"frame {ordinal} contains a gain event")
    if metadata.observation_overflow_count or metadata.event_overflow_count:
        raise QualificationError(f"frame {ordinal} reports metadata overflow")


def validate_full_drain_frames(
    frames: Sequence[TandemFrameMetadata],
    *,
    status_after_open: Mapping[str, Any],
    status_before_close: Mapping[str, Any],
    frame_samples: int = FRAME_SAMPLES,
) -> dict[str, Any]:
    """Require one exact 64-frame, event-free HOLD stream."""

    if len(frames) != BATCH_FRAMES:
        raise QualificationError(
            f"full drain returned {len(frames)} frames, expected {BATCH_FRAMES}"
        )
    first = frames[0]
    open_status = _require_hold(status_after_open, label="full-drain open binding")
    close_status = _require_hold(status_before_close, label="full-drain close binding")
    if open_status != close_status:
        raise QualificationError("full-drain owned status changed")
    if first.buffer_sequence != 0:
        raise QualificationError("full drain did not begin at buffer sequence zero")
    for ordinal, metadata in enumerate(frames):
        _validate_hold_metadata(metadata, ordinal=ordinal)
        if (
            metadata.stream_id != first.stream_id
            or metadata.ownership_epoch != first.ownership_epoch
        ):
            raise QualificationError("stream ID or ownership epoch changed")
        if metadata.buffer_sequence != ordinal:
            raise QualificationError(f"buffer sequence at {ordinal} is not exact")
        expected_sample = first.first_sample_sequence + ordinal * frame_samples
        if metadata.first_sample_sequence != expected_sample:
            raise QualificationError(f"sample sequence at {ordinal} is not contiguous")
        if metadata.samples_per_channel != frame_samples:
            raise QualificationError(f"sample count at {ordinal} changed")
        if (
            metadata.ownership_epoch != open_status["ownership_epoch"]
            or metadata.rx1_gain_index != open_status["rx1_gain_index"]
            or metadata.rx2_gain_index != open_status["rx2_gain_index"]
        ):
            raise QualificationError(
                f"frame {ordinal} does not bind to owned HOLD status"
            )
    return {
        "verified": True,
        "frame_count": len(frames),
        "stream_id": first.stream_id,
        "ownership_epoch": first.ownership_epoch,
        "buffer_sequence_range": [0, BATCH_FRAMES - 1],
        "sample_sequence_range": [
            first.first_sample_sequence,
            first.first_sample_sequence + BATCH_FRAMES * frame_samples,
        ],
        "sample_gaps": 0,
        "gain_events": 0,
        "faults": 0,
        "overflows": 0,
    }


def _hold_request() -> bytes:
    return build_tandem_request(
        mode=TandemMode.HOLD,
        initial_gain_db=HOLD_GAIN_DB,
        samples_per_channel=FRAME_SAMPLES,
    )


def _new_buffer(iio_module: Any, rx: Any) -> Any:
    value, abi = create_metadata_buffer(
        iio_module,
        rx,
        FRAME_SAMPLES,
        metadata_capacity=METADATA_CAPACITY,
        tandem_request=_hold_request(),
        batch_frames=BATCH_FRAMES,
    )
    if abi != 2:
        close_iio_object(value)
        raise QualificationError(f"metadata ABI {abi} is not request ABI 2")
    if value.batch_frames != BATCH_FRAMES:
        close_iio_object(value)
        raise QualificationError("pylibiio batch frame readback changed")
    return value


def _full_drain(iio_module: Any, rx: Any, tandem: Any) -> dict[str, Any]:
    rx.set_kernel_buffers_count(KERNEL_BUFFERS)
    buffer = _new_buffer(iio_module, rx)
    frames: list[TandemFrameMetadata] = []
    records: list[dict[str, Any]] = []
    close_method = "explicit_normal_close"
    try:
        status_open = _require_hold(_status(tandem), label="full-drain open")
        for ordinal in range(BATCH_FRAMES):
            started = time.monotonic_ns()
            metadata_bytes = bytes(buffer.refill())
            completed = time.monotonic_ns()
            iq = bytes(buffer.read())
            record, metadata = _frame_record(
                ordinal, metadata_bytes, iq, completed - started
            )
            records.append(record)
            frames.append(metadata)
        status_before_close = _require_hold(
            _status(tandem), label="full-drain before close"
        )
        cache_bytes = int(buffer.batch_cache_bytes)
        if cache_bytes != EXPECTED_BATCH_CACHE_BYTES:
            raise QualificationError(
                f"batch cache bound {cache_bytes} != {EXPECTED_BATCH_CACHE_BYTES}"
            )
        continuity = validate_full_drain_frames(
            frames,
            status_after_open=status_open,
            status_before_close=status_before_close,
        )
    finally:
        close_iio_object(buffer)
        buffer = None
        gc.collect()
    return {
        "kernel_buffers": KERNEL_BUFFERS,
        "batch_frames": BATCH_FRAMES,
        "metadata_capacity_bytes": METADATA_CAPACITY,
        "batch_cache_bound_bytes": cache_bytes,
        "expected_batch_cache_bytes": EXPECTED_BATCH_CACHE_BYTES,
        "status_after_open": status_open,
        "status_before_close": status_before_close,
        "close_method": close_method,
        "frames": records,
        "continuity": continuity,
        "status_after_close": _wait_idle(tandem, label="full-drain close"),
    }


def _expect_oserror(call: Any, expected_errno: int, *, label: str) -> dict[str, Any]:
    try:
        call()
    except OSError as error:
        if error.errno != expected_errno:
            raise QualificationError(
                f"{label} errno {error.errno}, expected {expected_errno}"
            ) from error
        return _error_record(error)
    raise QualificationError(f"{label} unexpectedly succeeded")


def _cancel_lifecycle(iio_module: Any, rx: Any, tandem: Any) -> dict[str, Any]:
    rx.set_kernel_buffers_count(KERNEL_BUFFERS)
    old = _new_buffer(iio_module, rx)
    busy: Any = None
    fresh: Any = None
    result: dict[str, Any] = {
        "kernel_buffers": KERNEL_BUFFERS,
        "batch_frames": BATCH_FRAMES,
        "operation_order": [],
    }
    try:
        result["status_after_old_open"] = _require_hold(
            _status(tandem), label="cancel old open"
        )
        started = time.monotonic_ns()
        metadata_bytes = bytes(old.refill())
        completed = time.monotonic_ns()
        iq = bytes(old.read())
        first_record, first_metadata = _frame_record(
            0, metadata_bytes, iq, completed - started
        )
        _validate_hold_metadata(first_metadata, ordinal=0)
        if first_metadata.buffer_sequence != 0:
            raise QualificationError(
                "canceled session first frame is not sequence zero"
            )
        old_status = result["status_after_old_open"]
        if (
            first_metadata.ownership_epoch != old_status["ownership_epoch"]
            or first_metadata.rx1_gain_index != old_status["rx1_gain_index"]
            or first_metadata.rx2_gain_index != old_status["rx2_gain_index"]
        ):
            raise QualificationError(
                "canceled session first frame does not bind to owned HOLD status"
            )
        result["first_returned_cached_frame"] = first_record
        result["operation_order"].append("first_cached_frame_returned")
        old.cancel()
        result["operation_order"].append("old_buffer_cancel")

        def attempt_busy_open() -> None:
            nonlocal busy
            busy = _new_buffer(iio_module, rx)

        result["second_open_error"] = _expect_oserror(
            attempt_busy_open, errno.EBUSY, label="second metadata open"
        )
        result["operation_order"].append("second_open_ebusy")
        result["poison_refill_error"] = _expect_oserror(
            old.refill, errno.EBADF, label="old poisoned refill"
        )
        result["operation_order"].append("old_refill_ebadf")
        close_iio_object(old)
        old = None
        gc.collect()
        result["operation_order"].append("old_buffer_close")
        result["status_after_old_close"] = _wait_idle(
            tandem, label="canceled old close"
        )

        fresh = _new_buffer(iio_module, rx)
        result["operation_order"].append("fresh_buffer_open")
        result["status_after_fresh_open"] = _require_hold(
            _status(tandem), label="fresh recovery open"
        )
        close_iio_object(fresh)
        fresh = None
        gc.collect()
        result["operation_order"].append("fresh_buffer_close")
        result["status_after_fresh_close"] = _wait_idle(
            tandem, label="fresh recovery close"
        )
        result["verified"] = True
        return result
    finally:
        close_iio_object(busy)
        close_iio_object(fresh)
        close_iio_object(old)
        gc.collect()


def _preflight(
    context: Any,
    phy: Any,
    tx: Any,
    tandem: Any,
    *,
    serial: str,
    uri: str,
    firmware_pattern: str,
) -> dict[str, Any]:
    attrs = {str(name): str(value) for name, value in context.attrs.items()}
    observed_serial = attrs.get("hw_serial", attrs.get("serial", ""))
    if observed_serial != serial:
        raise QualificationError(
            f"opened serial {observed_serial!r}, expected {serial!r}"
        )
    firmware = attrs.get("fw_version", "")
    if re.fullmatch(firmware_pattern, firmware) is None:
        raise QualificationError(
            f"firmware {firmware!r} does not fullmatch {firmware_pattern!r}"
        )
    mute = _read_mute(phy, tx)
    if not mute["verified"]:
        raise QualificationError(
            "read-only preflight refuses to touch a radio not already muted: "
            + "; ".join(mute["failures"])
        )
    rx_state = _read_rx_state(phy)
    if rx_state["modes"] != ["manual", "manual"] or any(
        abs(gain - HOLD_GAIN_DB) > 0.1 for gain in rx_state["gains_db"]
    ):
        raise QualificationError(f"preflight RX is not manual 40 dB: {rx_state}")
    status = _require_idle(_status(tandem), label="read-only preflight")
    return {
        "verdict": "GO",
        "serial": observed_serial,
        "uri": uri,
        "firmware_version": firmware,
        "context_attrs": attrs,
        "mute": mute,
        "rx_state": rx_state,
        "tandem_status": status,
    }


def _resolve_uri(iio_module: Any, serial: str) -> str:
    contexts = iio_module.scan_contexts()
    matches = [
        uri
        for uri, description in contexts.items()
        if uri.startswith("usb:") and serial in str(description)
    ]
    if len(matches) != 1:
        raise QualificationError(
            f"expected exactly one local USB context for {serial}; got {matches}"
        )
    return matches[0]


def _lock_path(serial: str) -> pathlib.Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", serial)
    return pathlib.Path(f"/tmp/plutosdr-fw-radio-{safe}.lock")


def _required_mapping(value: Any, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise QualificationError(f"durable {name} is not an object")
    return value


def _required_list(value: Any, *, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise QualificationError(f"durable {name} is not a list")
    return value


def _required_int(value: Any, *, name: str, minimum: int | None = None) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        raise QualificationError(f"durable {name} is not an exact bounded integer")
    return value


def _required_number(value: Any, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QualificationError(f"durable {name} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise QualificationError(f"durable {name} is not finite")
    return result


def _validate_mute_record(value: Any, *, name: str) -> None:
    record = _required_mapping(value, name=name)
    if record.get("verified") is not True or record.get("failures") != []:
        raise QualificationError(f"durable {name} is not verified")
    for gain_name in ("tx1_gain_db", "tx2_gain_db"):
        if _required_number(record.get(gain_name), name=f"{name} {gain_name}") > -80:
            raise QualificationError(f"durable {name} {gain_name} is not muted")
    if record.get("selectors") != [DAC_SELECT_ZERO] * 4:
        raise QualificationError(f"durable {name} selectors are not ZERO")
    dds = _required_mapping(record.get("dds"), name=f"{name} DDS")
    if set(dds) != {f"altvoltage{i}" for i in range(8)}:
        raise QualificationError(f"durable {name} DDS coverage changed")
    for channel_name, channel_value in dds.items():
        channel = _required_mapping(channel_value, name=f"{name} {channel_name}")
        if channel.get("present") is not True:
            raise QualificationError(f"durable {name} {channel_name} is absent")
        for attribute in ("raw", "scale"):
            if (
                abs(
                    _required_number(
                        channel.get(attribute),
                        name=f"{name} {channel_name} {attribute}",
                    )
                )
                > 1e-9
            ):
                raise QualificationError(
                    f"durable {name} {channel_name} {attribute} is nonzero"
                )


def _validate_rx_record(value: Any, *, name: str) -> None:
    record = _required_mapping(value, name=name)
    if record.get("modes") != ["manual", "manual"]:
        raise QualificationError(f"durable {name} modes are not manual/manual")
    gains = _required_list(record.get("gains_db"), name=f"{name} gains")
    if len(gains) != 2 or any(
        abs(_required_number(gain, name=f"{name} gain") - HOLD_GAIN_DB) > 0.1
        for gain in gains
    ):
        raise QualificationError(f"durable {name} gains are not 40/40")


def _validate_frame_json(
    value: Any,
    *,
    name: str,
    ordinal: int,
    status: Mapping[str, Any],
    expected_stream_id: int | None,
    expected_first_sample: int | None,
) -> tuple[int, int, int, int]:
    record = _required_mapping(value, name=name)
    exact = {
        "ordinal": ordinal,
        "buffer_sequence": ordinal,
        "version": 5,
        "header_bytes": 3_256,
        "samples_per_channel": FRAME_SAMPLES,
        "iq_payload_bytes": EXPECTED_IQ_BYTES,
        "iq_bytes": EXPECTED_IQ_BYTES,
        "enabled_scan_mask": 0x0F,
        "sample_format": 1,
        "channel_count": 2,
        "observation_capacity": 64,
        "event_capacity": 64,
        "tandem_state": int(TandemState.ARMED_HOLD),
        "tandem_state_name": "armed_hold",
        "tandem_fault_flags": 0,
        "tandem_transition_count": 0,
        "gain_table_id": int(EXPECTED_GAIN_TABLE),
        "gain_table_name": EXPECTED_GAIN_TABLE.name.lower(),
        "minimum_gain_db": EXPECTED_MINIMUM_GAIN_DB,
        "maximum_gain_db": EXPECTED_MAXIMUM_GAIN_DB,
        "initial_gain_db": HOLD_GAIN_DB,
        "minimum_gain_index": EXPECTED_MINIMUM_GAIN_INDEX,
        "maximum_gain_index": EXPECTED_MAXIMUM_GAIN_INDEX,
        "event_count": 0,
        "observation_overflow_count": 0,
        "event_overflow_count": 0,
    }
    for field, expected in exact.items():
        if record.get(field) != expected:
            raise QualificationError(
                f"durable {name} {field} {record.get(field)!r} != {expected!r}"
            )
    features = _required_int(record.get("features"), name=f"{name} features")
    flags = _required_int(record.get("flags"), name=f"{name} flags")
    if features & REQUIRED_FEATURES != REQUIRED_FEATURES:
        raise QualificationError(f"durable {name} lacks required features")
    if flags & REQUIRED_FLAGS != REQUIRED_FLAGS or flags & TANDEM_UNSAFE_FLAGS:
        raise QualificationError(f"durable {name} validity/unsafe flags changed")
    stream_id = _required_int(record.get("stream_id"), name=f"{name} stream", minimum=1)
    epoch = _required_int(
        record.get("ownership_epoch"), name=f"{name} epoch", minimum=1
    )
    first_sample = _required_int(
        record.get("first_sample_sequence"), name=f"{name} first sample", minimum=0
    )
    rx1 = _required_int(record.get("rx1_gain_index"), name=f"{name} RX1 index")
    rx2 = _required_int(record.get("rx2_gain_index"), name=f"{name} RX2 index")
    if expected_stream_id is not None and stream_id != expected_stream_id:
        raise QualificationError(f"durable {name} stream changed")
    if expected_first_sample is not None and first_sample != expected_first_sample:
        raise QualificationError(f"durable {name} sample sequence is not contiguous")
    if (
        epoch != status["ownership_epoch"]
        or rx1 != status["rx1_gain_index"]
        or rx2 != status["rx2_gain_index"]
        or not EXPECTED_MINIMUM_GAIN_INDEX <= rx1 == rx2 <= EXPECTED_MAXIMUM_GAIN_INDEX
    ):
        raise QualificationError(f"durable {name} does not bind to owned HOLD")
    observations = _required_int(
        record.get("observation_count"), name=f"{name} observations", minimum=0
    )
    if observations > 64:
        raise QualificationError(f"durable {name} observations exceed capacity")
    _required_int(
        record.get("threshold_provenance"),
        name=f"{name} threshold provenance",
        minimum=1,
    )
    _required_int(record.get("refill_duration_ns"), name=f"{name} duration", minimum=0)
    if record.get("metadata_bytes") != 3_256:
        raise QualificationError(f"durable {name} metadata length changed")
    for digest_name in ("iq_sha256", "metadata_sha256"):
        if re.fullmatch(r"[0-9a-f]{64}", str(record.get(digest_name, ""))) is None:
            raise QualificationError(f"durable {name} {digest_name} is invalid")
    return stream_id, epoch, first_sample, rx1


def _validate_errno_record(value: Any, expected: int, *, name: str) -> None:
    record = _required_mapping(value, name=name)
    if record.get("errno") != expected or not isinstance(record.get("message"), str):
        raise QualificationError(f"durable {name} does not prove errno {expected}")


def validate_durable_pass_report(value: Any) -> None:
    """Reject any durable artifact that could otherwise claim a false PASS."""

    report = _required_mapping(value, name="report")
    if report.get("schema") != SCHEMA or report.get("verdict") != "PASS":
        raise QualificationError("durable report schema/verdict changed")
    if report.get("release_claim") != (
        "none; muted host-transport lifecycle qualification only"
    ):
        raise QualificationError("durable report overclaims release evidence")
    if "error" in report:
        raise QualificationError("durable PASS contains an error record")
    started = _required_int(report.get("started_unix_ns"), name="start time", minimum=1)
    completed = _required_int(
        report.get("completed_unix_ns"), name="completion time", minimum=started
    )
    if completed < started:
        raise QualificationError("durable report completion predates start")

    host = _required_mapping(report.get("host_libiio"), name="host libiio")
    if host.get("source_commit") != EXACT_LIBIIO_COMMIT:
        raise QualificationError("durable host libiio commit changed")
    mapped = _required_list(
        host.get("mapped_shared_objects"), name="mapped shared objects"
    )
    if mapped != [host.get("mapped_shared_object")]:
        raise QualificationError("durable mapped libiio identity is ambiguous")
    calculated_sha = str(host.get("mapped_shared_object_sha256", ""))
    if (
        re.fullmatch(r"[0-9a-f]{64}", calculated_sha) is None
        or host.get("runner_shared_object_sha256") != calculated_sha
    ):
        raise QualificationError("durable mapped libiio SHA binding failed")
    source = pathlib.Path(str(host.get("source_directory", "")))
    build = pathlib.Path(str(host.get("build_directory", "")))
    library = pathlib.Path(str(host.get("mapped_shared_object", "")))
    if not source.is_absolute() or not build.is_absolute() or not library.is_absolute():
        raise QualificationError("durable libiio paths are not absolute")
    if not library.is_relative_to(build):
        raise QualificationError("durable mapped libiio is outside its build")
    pylibiio = pathlib.Path(str(host.get("pylibiio_file", "")))
    if pylibiio != source / "bindings/python/iio.py":
        raise QualificationError("durable pylibiio is outside exact source tree")

    provenance = _required_mapping(
        report.get("runner_provenance"), name="runner provenance"
    )
    if (
        re.fullmatch(r"[0-9a-f]{40}", str(provenance.get("firmware_repo_commit", "")))
        is None
    ):
        raise QualificationError("durable runner commit is invalid")
    for observed_name, head_name in (
        ("python_module_sha256", "python_module_head_blob_sha256"),
        ("shell_runner_sha256", "shell_runner_head_blob_sha256"),
        ("metadata_abi_sha256", "metadata_abi_head_blob_sha256"),
    ):
        observed = str(provenance.get(observed_name, ""))
        head = str(provenance.get(head_name, ""))
        if (
            re.fullmatch(r"[0-9a-f]{64}", observed) is None
            or re.fullmatch(r"[0-9a-f]{64}", head) is None
            or observed != head
        ):
            raise QualificationError(
                f"durable runner {observed_name} is not its exact HEAD blob"
            )
    module_path = pathlib.Path(str(provenance.get("python_module_path", "")))
    shell_path = pathlib.Path(str(provenance.get("shell_runner_path", "")))
    metadata_abi_path = pathlib.Path(str(provenance.get("metadata_abi_path", "")))
    if (
        not module_path.is_absolute()
        or not shell_path.is_absolute()
        or not metadata_abi_path.is_absolute()
        or metadata_abi_path != module_path.parent / "metadata_abi.py"
    ):
        raise QualificationError("durable runner source paths are not absolute")

    configuration = _required_mapping(report.get("configuration"), name="configuration")
    exact_configuration = {
        "tx_policy": "fully muted; no DDS/DMA enable and no TX gain increase",
        "tandem_mode": "hold",
        "hold_gain_db": HOLD_GAIN_DB,
        "frame_samples_per_channel": FRAME_SAMPLES,
        "kernel_buffers": KERNEL_BUFFERS,
        "batch_frames": BATCH_FRAMES,
        "metadata_capacity_bytes": METADATA_CAPACITY,
        "expected_batch_cache_bytes": EXPECTED_BATCH_CACHE_BYTES,
    }
    for field, expected in exact_configuration.items():
        if configuration.get(field) != expected:
            raise QualificationError(f"durable configuration {field} changed")
    serial = str(configuration.get("serial", ""))
    firmware_pattern = str(configuration.get("firmware_pattern", ""))
    if not serial or not firmware_pattern:
        raise QualificationError("durable serial/firmware gate is empty")

    preflight = _required_mapping(report.get("preflight"), name="preflight")
    if (
        preflight.get("verdict") != "GO"
        or preflight.get("serial") != serial
        or not str(preflight.get("uri", "")).startswith("usb:")
        or re.fullmatch(firmware_pattern, str(preflight.get("firmware_version", "")))
        is None
    ):
        raise QualificationError("durable read-only preflight is not exact GO")
    context_attrs = _required_mapping(
        preflight.get("context_attrs"), name="preflight context attrs"
    )
    if (
        context_attrs.get("hw_serial") != serial
        or context_attrs.get("fw_version") != preflight.get("firmware_version")
        or context_attrs.get("iio,buffer-metadata") != "2"
    ):
        raise QualificationError("durable preflight identity/capability changed")
    _validate_mute_record(preflight.get("mute"), name="preflight mute")
    _validate_rx_record(preflight.get("rx_state"), name="preflight RX")
    _require_idle(
        _required_mapping(preflight.get("tandem_status"), name="preflight tandem"),
        label="durable preflight tandem",
    )
    for field in (
        "forced_mute_before",
        "mute_after_full_drain",
    ):
        _validate_mute_record(report.get(field), name=field)
    for field in ("rx_manual_before", "rx_after_full_drain"):
        _validate_rx_record(report.get(field), name=field)
    scan = _required_mapping(report.get("rx_scan"), name="RX scan")
    if set(scan) != {
        "enabled_channel_ids",
        "enabled_scan_mask",
        "sample_size_bytes",
        "layout",
    }:
        raise QualificationError("durable RX scan evidence fields changed")
    enabled_channel_ids = _required_list(
        scan.get("enabled_channel_ids"), name="RX enabled channel IDs"
    )
    if (
        any(type(channel_id) is not str for channel_id in enabled_channel_ids)
        or enabled_channel_ids != list(RX_SCAN_IDS)
        or _required_int(scan.get("enabled_scan_mask"), name="RX enabled scan mask")
        != RX_SCAN_MASK
        or _required_int(scan.get("sample_size_bytes"), name="RX sample size")
        != RX_SCAN_SAMPLE_BYTES
    ):
        raise QualificationError("durable RX scan selection/mask/size changed")
    layout = _required_list(scan.get("layout"), name="RX scan layout")
    if len(layout) != len(RX_SCAN_IDS):
        raise QualificationError("durable RX scan layout is not four scalar lanes")
    for expected_index, (channel_id, channel_value) in enumerate(
        zip(RX_SCAN_IDS, layout, strict=True)
    ):
        channel = _required_mapping(channel_value, name=f"RX scan layout {channel_id}")
        if set(channel) != {"id", "index", "format"}:
            raise QualificationError(
                f"durable RX scan lane {channel_id} fields changed"
            )
        if type(channel.get("id")) is not str or channel.get("id") != channel_id:
            raise QualificationError(f"durable RX scan lane {channel_id} ID changed")
        if (
            _required_int(channel.get("index"), name=f"RX scan lane {channel_id} index")
            != expected_index
        ):
            raise QualificationError(
                f"durable RX scan lane {channel_id} index/format changed"
            )
        scan_format = _required_mapping(
            channel.get("format"), name=f"RX scan lane {channel_id} format"
        )
        if set(scan_format) != set(RX_SCAN_FORMAT):
            raise QualificationError(
                f"durable RX scan lane {channel_id} format fields changed"
            )
        for field in ("length", "bits", "shift", "repeat"):
            if (
                _required_int(
                    scan_format.get(field),
                    name=f"RX scan lane {channel_id} format {field}",
                )
                != RX_SCAN_FORMAT[field]
            ):
                raise QualificationError(
                    f"durable RX scan lane {channel_id} format {field} changed"
                )
        for field in ("is_signed", "is_be"):
            value = scan_format.get(field)
            if type(value) is not bool or value is not RX_SCAN_FORMAT[field]:
                raise QualificationError(
                    f"durable RX scan lane {channel_id} format {field} changed"
                )

    full = _required_mapping(report.get("full_drain"), name="full drain")
    if (
        full.get("kernel_buffers") != KERNEL_BUFFERS
        or full.get("batch_frames") != BATCH_FRAMES
        or full.get("metadata_capacity_bytes") != METADATA_CAPACITY
        or full.get("batch_cache_bound_bytes") != EXPECTED_BATCH_CACHE_BYTES
        or full.get("expected_batch_cache_bytes") != EXPECTED_BATCH_CACHE_BYTES
        or full.get("close_method") != "explicit_normal_close"
    ):
        raise QualificationError("durable full-drain configuration changed")
    status_open = _require_hold(
        _required_mapping(full.get("status_after_open"), name="full open status"),
        label="durable full open",
    )
    status_before_close = _require_hold(
        _required_mapping(
            full.get("status_before_close"), name="full before-close status"
        ),
        label="durable full before close",
    )
    if status_open != status_before_close:
        raise QualificationError("durable full-drain status changed while open")
    frames = _required_list(full.get("frames"), name="full frames")
    if len(frames) != BATCH_FRAMES:
        raise QualificationError("durable full drain is not exactly 64 frames")
    first_sample = None
    stream_id = None
    threshold = None
    endpoint = None
    for ordinal, frame in enumerate(frames):
        expected_sample = (
            None if first_sample is None else first_sample + ordinal * FRAME_SAMPLES
        )
        current_stream, current_epoch, current_sample, current_endpoint = (
            _validate_frame_json(
                frame,
                name=f"full frame {ordinal}",
                ordinal=ordinal,
                status=status_open,
                expected_stream_id=stream_id,
                expected_first_sample=expected_sample,
            )
        )
        if first_sample is None:
            first_sample = current_sample
            stream_id = current_stream
            endpoint = current_endpoint
            threshold = frame["threshold_provenance"]
        elif (
            current_epoch != status_open["ownership_epoch"]
            or current_endpoint != endpoint
        ):
            raise QualificationError("durable full frame epoch/endpoint changed")
        if frame["threshold_provenance"] != threshold:
            raise QualificationError("durable full frame threshold provenance changed")
    assert first_sample is not None and stream_id is not None
    expected_continuity = {
        "verified": True,
        "frame_count": BATCH_FRAMES,
        "stream_id": stream_id,
        "ownership_epoch": status_open["ownership_epoch"],
        "buffer_sequence_range": [0, BATCH_FRAMES - 1],
        "sample_sequence_range": [
            first_sample,
            first_sample + BATCH_FRAMES * FRAME_SAMPLES,
        ],
        "sample_gaps": 0,
        "gain_events": 0,
        "faults": 0,
        "overflows": 0,
    }
    if full.get("continuity") != expected_continuity:
        raise QualificationError("durable continuity summary is not frame-derived")
    _require_idle(
        _required_mapping(full.get("status_after_close"), name="full close status"),
        label="durable full close",
    )

    cancel = _required_mapping(report.get("cancel_lifecycle"), name="cancel lifecycle")
    if (
        cancel.get("verified") is not True
        or cancel.get("kernel_buffers") != KERNEL_BUFFERS
        or cancel.get("batch_frames") != BATCH_FRAMES
        or cancel.get("operation_order")
        != [
            "first_cached_frame_returned",
            "old_buffer_cancel",
            "second_open_ebusy",
            "old_refill_ebadf",
            "old_buffer_close",
            "fresh_buffer_open",
            "fresh_buffer_close",
        ]
    ):
        raise QualificationError("durable cancel lifecycle order/config changed")
    old_status = _require_hold(
        _required_mapping(
            cancel.get("status_after_old_open"), name="cancel old open status"
        ),
        label="durable cancel old open",
    )
    _validate_frame_json(
        cancel.get("first_returned_cached_frame"),
        name="cancel first cached frame",
        ordinal=0,
        status=old_status,
        expected_stream_id=None,
        expected_first_sample=None,
    )
    _validate_errno_record(
        cancel.get("second_open_error"), errno.EBUSY, name="second open"
    )
    _validate_errno_record(
        cancel.get("poison_refill_error"), errno.EBADF, name="poison refill"
    )
    _require_idle(
        _required_mapping(
            cancel.get("status_after_old_close"), name="cancel old close status"
        ),
        label="durable cancel old close",
    )
    fresh_status = _require_hold(
        _required_mapping(
            cancel.get("status_after_fresh_open"), name="fresh open status"
        ),
        label="durable fresh open",
    )
    if (
        len(
            {
                status_open["ownership_epoch"],
                old_status["ownership_epoch"],
                fresh_status["ownership_epoch"],
            }
        )
        != 3
    ):
        raise QualificationError("durable sessions do not have distinct epochs")
    fresh_close = _require_idle(
        _required_mapping(
            cancel.get("status_after_fresh_close"), name="fresh close status"
        ),
        label="durable fresh close",
    )

    final_status = _require_idle(
        _required_mapping(report.get("final_tandem_status"), name="final status"),
        label="durable final status",
    )
    if final_status != fresh_close:
        raise QualificationError("durable final status changed after recovery close")
    _validate_rx_record(report.get("final_rx_state"), name="final RX")
    cleanup = _required_mapping(report.get("cleanup"), name="cleanup")
    _validate_mute_record(cleanup, name="cleanup mute")
    if cleanup.get("errors") != []:
        raise QualificationError("durable cleanup contains errors")
    if cleanup.get("tandem_status") != final_status:
        raise QualificationError("durable cleanup tandem status is not final")
    if cleanup.get("rx_state") != report.get("final_rx_state"):
        raise QualificationError("durable cleanup RX state is not final")


def _json_domain(value: Any) -> Any:
    return json.loads(json.dumps(value, allow_nan=False))


def _reread_exact_report(
    path: pathlib.Path, expected: Mapping[str, Any]
) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if parsed != _json_domain(expected):
        raise QualificationError("atomic report reread differs from in-memory evidence")
    if parsed.get("verdict") == "PASS":
        validate_durable_pass_report(parsed)
    return parsed


def _close_resources_and_persist(
    report: dict[str, Any],
    *,
    output_path: pathlib.Path,
    context: Any,
    lock: Any,
    lock_acquired: bool,
    cleanup_errors: list[dict[str, Any]],
    primary_error: BaseException | None,
) -> tuple[dict[str, Any], BaseException | None]:
    """Close fallibly, unlock unconditionally, and persist an exact report."""

    if context is not None:
        try:
            close_iio_object(context)
        except BaseException as error:
            cleanup_errors.append(_error_record(error))
        finally:
            context = None
            gc.collect()
    if lock is not None:
        if lock_acquired:
            try:
                fcntl.flock(lock, fcntl.LOCK_UN)
            except BaseException as error:
                cleanup_errors.append(_error_record(error))
        try:
            lock.close()
        except BaseException as error:
            cleanup_errors.append(_error_record(error))

    cleanup_record = report.setdefault("cleanup", {})
    cleanup_record["rx_state"] = report.get("final_rx_state")
    cleanup_record["tandem_status"] = report.get("final_tandem_status")
    cleanup_record["errors"] = cleanup_errors
    cleanup_record["verified"] = bool(
        cleanup_record.get("verified") and not cleanup_errors
    )
    report["completed_unix_ns"] = time.time_ns()
    if cleanup_errors:
        report["verdict"] = "FAIL"
        cleanup_failure = QualificationError(
            f"durable cleanup failed: {cleanup_errors}"
        )
        if primary_error is None:
            primary_error = cleanup_failure
            report["error"] = _error_record(cleanup_failure)
    if report.get("verdict") == "PASS":
        try:
            validate_durable_pass_report(report)
        except BaseException as error:
            report["verdict"] = "FAIL"
            report["error"] = _error_record(error)
            if primary_error is None:
                primary_error = error

    _atomic_json(output_path, report)
    try:
        durable_report = _reread_exact_report(output_path, report)
    except BaseException as error:
        # Never leave a durable false PASS after a validation/reread error.
        report["verdict"] = "FAIL"
        report["error"] = _error_record(error)
        _atomic_json(output_path, report)
        durable_report = _reread_exact_report(output_path, report)
        if primary_error is None:
            primary_error = error
    return durable_report, primary_error


def run_hardware(
    iio_module: Any,
    *,
    serial: str,
    firmware_pattern: str,
    output_path: pathlib.Path,
) -> dict[str, Any]:
    expected_commit = os.environ.get("PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT", "")
    if expected_commit != EXACT_LIBIIO_COMMIT:
        raise QualificationError(
            f"host libiio attestation {expected_commit!r} is not exact "
            f"{EXACT_LIBIIO_COMMIT}"
        )
    runner_library_sha = os.environ.get("PLUTOSDR_FW_LIBIIO_SHA256", "")
    if re.fullmatch(r"[0-9a-f]{64}", runner_library_sha) is None:
        raise QualificationError("runner did not attest the mapped libiio SHA-256")
    host_libiio = _attest_mapped_libiio()
    host_libiio["pylibiio_file"] = str(pathlib.Path(iio_module.__file__).resolve())
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": "running",
        "release_claim": "none; muted host-transport lifecycle qualification only",
        "started_unix_ns": time.time_ns(),
        "host_libiio": host_libiio,
        "runner_provenance": _attest_runner_provenance(),
        "configuration": {
            "serial": serial,
            "firmware_pattern": firmware_pattern,
            "tx_policy": "fully muted; no DDS/DMA enable and no TX gain increase",
            "tandem_mode": "hold",
            "hold_gain_db": HOLD_GAIN_DB,
            "frame_samples_per_channel": FRAME_SAMPLES,
            "kernel_buffers": KERNEL_BUFFERS,
            "batch_frames": BATCH_FRAMES,
            "metadata_capacity_bytes": METADATA_CAPACITY,
            "expected_batch_cache_bytes": EXPECTED_BATCH_CACHE_BYTES,
        },
        "cleanup": {"verified": False},
    }
    lock: Any = None
    lock_acquired = False
    context: Any = None
    primary_error: BaseException | None = None
    cleanup_errors: list[dict[str, Any]] = []
    try:
        lock = _lock_path(serial).open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock_acquired = True
        except BlockingIOError as error:
            lock.seek(0)
            raise QualificationError(
                f"R18 process lock is held: {lock.read().strip()}"
            ) from error
        lock.seek(0)
        lock.truncate()
        lock.write(f"pid={os.getpid()} suite=muted-metadata-batch-lifecycle\n")
        lock.flush()
        uri = _resolve_uri(iio_module, serial)
        context = iio_module.Context(uri)
        context.set_timeout(10_000)
        phy = context.find_device("ad9361-phy")
        rx = context.find_device("cf-ad9361-lpc")
        tx = context.find_device("cf-ad9361-dds-core-lpc")
        tandem = context.find_device("tandem-agc")
        if any(value is None for value in (phy, rx, tx, tandem)):
            raise QualificationError("required PHY/RX/TX/tandem device is absent")
        report["preflight"] = _preflight(
            context,
            phy,
            tx,
            tandem,
            serial=serial,
            uri=uri,
            firmware_pattern=firmware_pattern,
        )
        report["forced_mute_before"] = _force_mute(phy, tx)
        report["rx_manual_before"] = _configure_manual_40(phy)
        report["rx_scan"] = _configure_dual_complex_rx_scan(rx)
        report["full_drain"] = _full_drain(iio_module, rx, tandem)
        report["rx_after_full_drain"] = _configure_manual_40(phy)
        report["mute_after_full_drain"] = _force_mute(phy, tx)
        report["cancel_lifecycle"] = _cancel_lifecycle(iio_module, rx, tandem)
        report["final_tandem_status"] = _wait_idle(tandem, label="final status")
        report["final_rx_state"] = _configure_manual_40(phy)
        report["cleanup"] = _force_mute(phy, tx)
        report["cleanup"]["tandem_status"] = report["final_tandem_status"]
        report["cleanup"]["rx_state"] = report["final_rx_state"]
        report["verdict"] = "PASS"
    except BaseException as error:
        primary_error = error
        report["verdict"] = "FAIL"
        report["error"] = _error_record(error)
    finally:
        if context is not None:
            phy = context.find_device("ad9361-phy")
            tx = context.find_device("cf-ad9361-dds-core-lpc")
            tandem = context.find_device("tandem-agc")
            try:
                report["final_rx_state"] = _configure_manual_40(phy)
            except BaseException as error:
                cleanup_errors.append(_error_record(error))
            try:
                cleanup = _force_mute(phy, tx)
                report["cleanup"] = cleanup
            except BaseException as error:
                cleanup_errors.append(_error_record(error))
            try:
                final_status = _wait_idle(tandem, label="durable cleanup")
                report["final_tandem_status"] = final_status
            except BaseException as error:
                cleanup_errors.append(_error_record(error))
        durable_report, primary_error = _close_resources_and_persist(
            report,
            output_path=output_path,
            context=context,
            lock=lock,
            lock_acquired=lock_acquired,
            cleanup_errors=cleanup_errors,
            primary_error=primary_error,
        )
        context = None
        lock = None
    if primary_error is not None:
        raise primary_error.with_traceback(primary_error.__traceback__)
    validate_durable_pass_report(durable_report)
    return durable_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hardware", action="store_true")
    parser.add_argument("--serial", default=DEFAULT_R18_SERIAL)
    parser.add_argument("--firmware-pattern", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.hardware:
        raise SystemExit("refusing hardware access without explicit --hardware")
    import iio

    try:
        report = run_hardware(
            iio,
            serial=args.serial,
            firmware_pattern=args.firmware_pattern,
            output_path=args.output.resolve(),
        )
    except BaseException as error:
        print(f"FAIL: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    artifact = args.output.resolve()
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    print(f"PASS: {artifact}")
    print(f"SHA256: {digest}")
    print(
        "full drain: "
        f"{report['full_drain']['continuity']['frame_count']} exact frames; "
        "cancel/EBUSY/EBADF/reopen lifecycle verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
