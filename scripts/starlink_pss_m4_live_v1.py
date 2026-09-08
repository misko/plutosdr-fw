#!/usr/bin/env python3
"""Plan, run, and qualify the Ethernet-only 15 MS/s live-LNB PSS gate.

This DNM-only command reuses the immutable v7 FPGA image and monitor-v2 ARM
controller. It accepts either the original volatile-RAM receipt or PPU's exact
hardware-qualified persistent-LAN receipt as deployment evidence. It never
transfers continuous IQ to the host. Each live role is
one bounded 25-point receiver-LO scan; every point drains FPGA phase maps for
4.5 seconds, yielding approximately 50 three-map candidate windows.  The scan
handles the carrier offset that a single fixed PSS kernel cannot search.

The command is deliberately strict about claim scope.  A passing result is a
live PSS acquisition and local timing-trajectory result only.  It is not SSS
detection and it is not final frame lock. Volatile deployments still require
recovery through PPU; persistent deployments do not.
"""

from __future__ import annotations

import argparse
import array
import gc
import hashlib
import importlib
import ipaddress
import itertools
import json
import math
import os
import re
import select
import stat
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Sequence
from contextlib import ExitStack, suppress
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.starlink_pss_m3_campaign_v1 as m3
import scripts.starlink_pss_monitor_probe_v1 as monitor_v1
import scripts.starlink_pss_monitor_probe_v2 as monitor_v2
import scripts.starlink_pss_progress_probe_v1 as progress_v1

SOURCE_MANIFEST = ROOT / "manifests/starlink-pss-m4-live-dnm-v1-source.yaml"

PLAN_SCHEMA = "plutosdr-fw.starlink-pss-m4-live-plan.v4"
RECEIPT_SCHEMA = "plutosdr-fw.starlink-pss-m4-live-receipt.v4"
FIXTURE_SCHEMA = "plutosdr-fw.starlink-pss-m4-live-fixture.v1"
CLAIM_SCOPE = "live_lnb_pss_acquisition_and_local_timing_only"
PERSISTENT_PROMOTION_PROFILE = "starlink-pss-15m-rx-only-dnm-v7-persistent-promotion"
EXPECTED_DFU_SHA256 = "dfd38e9e687f881599a3e4dea0070430e3731193debda64e313305a90dfd833d"
EXPECTED_FIT_SHA256 = "9a16418d04b3955f96ef6d903175450c1fb9de485d4a98de29612b3a8e6039cd"
EXPECTED_FIT_SIZE = 12_975_455
EXPECTED_FIRMWARE = monitor_v2.EXPECTED_FIRMWARE
RECEIVER_SERIAL = monitor_v1.probe_v1.ALLOCATED_SERIAL
RUNTIME_TARGET = monitor_v1.probe_v8.RUNTIME_TARGET
EXPECTED_MODEL = monitor_v1.probe_v8.EXPECTED_MODEL
SAMPLE_RATE_HZ = 15_000_000
RF_BANDWIDTH_HZ = 15_000_000
FRAME_SAMPLES = 20_000
LNB_LO_HZ = 9_750_000_000
CHANNEL_SPACING_HZ = 250_000_000
FIRST_CHANNEL_REFERENCE_RF_HZ_X2 = 10_825_117_187 * 2 + 1
EDGE_CENTER_OFFSET_HZ_X2 = 112_382_812 * 2 + 1
DEFAULT_CHANNEL = 4
DEFAULT_EDGE = "upper"
DEFAULT_LAN_HOST = "192.168.1.17"
DEFAULT_LAN_INTERFACE = "enp132s0"
DEFAULT_GAIN_MODE = "slow_attack"
ROLES = ("on_channel_a", "off_slice_control", "on_channel_b")
STABLE_CANDIDATE_WINDOWS_PER_POINT = 32
INITIAL_DISCARD_MAPS = 2
POST_RETUNE_DISCARD_MAPS = 5
ROLE_MONITOR_DURATION_MS = 80_500
DEFAULT_POINT_DURATION_MS = 2_731
DEFAULT_SETTLE_MS = 200
ACCEPTED_SCORE_COUNTER_SATURATION = (1 << 32) - 1
MAXIMUM_ROLE_MAPS = (
    ROLE_MONITOR_DURATION_MS * (SAMPLE_RATE_HZ // 1_000) // monitor_v1.TILE_SAMPLES
    + 3
)
ACCEPTED_SCORE_COUNTER_BUDGET = (
    MAXIMUM_ROLE_MAPS * monitor_v1.TILE_SAMPLES * len(ROLES)
)
DEFAULT_OFF_SLICE_SHIFT_HZ = -50_000_000
RAIL_PROBE_SAMPLES = 32_768
MAXIMUM_RAIL_FRACTION = 0.0001
MAXIMUM_MONITOR_OUTPUT_BYTES = 4 * 1024 * 1024
REMOTE_PREFIX = "/tmp/starlink_pss_m4_monitor"
PHYSICAL_LAN_LOCK_KEY = "__global_physical_lan_192.168.1.0_24__"
FIXTURE_ATTESTATION = (
    "receiver RX1 is connected only to the powered outdoor LNB; no transmitter "
    "or attenuated bench cable is connected"
)
OFFSET_ORDER_HZ = tuple(
    value
    for magnitude in range(0, 1_200_001, 100_000)
    for value in ((0,) if magnitude == 0 else (magnitude, -magnitude))
)
HEX_32 = re.compile(r"^[0-9a-f]{32}$")
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
INTERFACE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
BOOT_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
ProbeError = monitor_v1.ProbeError

POLICY = {
    **m3.POLICY,
    "scan_offset_minimum_hz": -1_200_000,
    "scan_offset_maximum_hz": 1_200_000,
    "scan_offset_step_hz": 100_000,
    "scan_point_count": 25,
    "maximum_rail_fraction": MAXIMUM_RAIL_FRACTION,
    "minimum_off_slice_separation_hz": 30_000_000,
    "minimum_passing_points_per_positive_role": 1,
    "maximum_passing_points_in_control_role": 0,
}

IDENTITY_FIELDS = {"path", "bytes", "sha256"}
FIXTURE_FIELDS = {
    "schema",
    "schema_version",
    "created_at",
    "receiver_serial",
    "physical_rx_port",
    "ethernet_host",
    "usb_data_connected",
    "volatile_runtime_power_continuity_verified",
    "transmitter_connected",
    "outdoor_view_verified",
    "lnb_model",
    "lnb_lo_hz",
    "lo_side",
    "spectral_inversion",
    "polarization",
    "lnb_supply_volts",
    "lnb_power_source",
    "operator_attestation",
}
PLAN_FIELDS = {
    "schema",
    "schema_version",
    "plan_id",
    "created_at",
    "hardware_accessed",
    "persistent_write",
    "do_not_merge",
    "serial",
    "runtime_target",
    "expected_firmware",
    "expected_model",
    "claim_scope",
    "ppu_repository",
    "ppu_source_commit",
    "probe_plan",
    "deployment_mode",
    "deployment_receipt",
    "reboot_receipt",
    "ssh_trust_mode",
    "ssh_known_hosts",
    "runner_source",
    "source_manifest",
    "expected_boot_id",
    "expected_qspi_sha256",
    "controller_binary",
    "fixture_declaration",
    "ethernet_host",
    "host_network_interface",
    "sample_rate_hz",
    "rf_bandwidth_hz",
    "rx_port_select",
    "gain_mode",
    "manual_gain_db",
    "starlink_channel",
    "starlink_edge",
    "lnb_lo_hz",
    "channel_reference_rf_hz_x2",
    "channel_reference_if_hz_x2",
    "edge_center_offset_hz_x2",
    "nominal_on_if_hz",
    "nominal_on_rf_hz",
    "off_slice_shift_hz",
    "nominal_off_if_hz",
    "scan_offsets_hz",
    "point_duration_ms",
    "settle_ms",
    "stable_candidate_windows_per_point",
    "initial_discard_maps",
    "post_retune_discard_maps",
    "role_monitor_duration_ms",
    "accepted_score_counter_budget",
    "role_order",
    "policy",
    "rail_probe_samples",
    "receipt_path",
    "confirmation_phrase",
    "pss_detected",
    "sss_detected",
    "frame_lock_claim",
}


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_time(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise ProbeError(f"M4 {label} timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise ProbeError(f"M4 {label} timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise ProbeError(f"M4 {label} timestamp lacks a timezone")
    return parsed


def _identity(path: Path, *, label: str) -> dict[str, Any]:
    return monitor_v1.probe_v1._identity(path.absolute(), label=label)


def _public_identity(path: Path, *, label: str) -> dict[str, Any]:
    selected = path.absolute()
    try:
        before = selected.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > MAXIMUM_MONITOR_OUTPUT_BYTES
        ):
            raise ProbeError(f"M4 {label} is not one bounded owned regular file")
        payload = selected.read_bytes()
        after = selected.lstat()
    except OSError as error:
        raise ProbeError(f"M4 {label} cannot be read: {error}") from error
    if (
        monitor_v1.probe_v1._stat_identity(before)
        != monitor_v1.probe_v1._stat_identity(after)
        or len(payload) != after.st_size
    ):
        raise ProbeError(f"M4 {label} changed while being read")
    return {
        "path": str(selected),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _load(path: Path, *, label: str) -> dict[str, Any]:
    return monitor_v1.probe_v1._load_private_json(path.absolute(), label=label)


def _load_external_receipt(path: Path, *, label: str) -> dict[str, Any]:
    payload = monitor_v1.probe_v1._private_file(path.absolute(), label=label)
    try:
        value = json.loads(
            payload,
            object_pairs_hook=monitor_v1.probe_v1._json_no_duplicates,
        )
        json.dumps(value, allow_nan=False)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ProbeError(f"M4 {label} is not strict JSON") from error
    if not isinstance(value, dict):
        raise ProbeError(f"M4 {label} is not one JSON object")
    return value


def _validate_identity(value: Any, *, label: str) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != IDENTITY_FIELDS
        or not isinstance(value.get("path"), str)
        or not Path(value["path"]).is_absolute()
        or not isinstance(value.get("bytes"), int)
        or isinstance(value.get("bytes"), bool)
        or value["bytes"] <= 0
        or not isinstance(value.get("sha256"), str)
        or HEX_64.fullmatch(value["sha256"]) is None
    ):
        raise ProbeError(f"M4 {label} identity is invalid")


def _require_unchanged(identity: dict[str, Any], *, label: str) -> None:
    _validate_identity(identity, label=label)
    if _identity(Path(identity["path"]), label=label) != identity:
        raise ProbeError(f"M4 {label} changed after plan sealing")


def _require_public_unchanged(identity: dict[str, Any], *, label: str) -> None:
    _validate_identity(identity, label=label)
    if _public_identity(Path(identity["path"]), label=label) != identity:
        raise ProbeError(f"M4 {label} changed after plan sealing")


def channel_reference_rf_hz_x2(channel: int) -> int:
    if isinstance(channel, bool) or not isinstance(channel, int) or not 1 <= channel <= 8:
        raise ValueError("Starlink channel must be an integer in [1, 8]")
    return FIRST_CHANNEL_REFERENCE_RF_HZ_X2 + 2 * (channel - 1) * CHANNEL_SPACING_HZ


def live_geometry(channel: int, edge: str, lnb_lo_hz: int) -> dict[str, int]:
    """Return exact half-Hz reference values and an integer 15 MHz center."""

    if edge not in {"lower", "upper"}:
        raise ValueError("Starlink edge must be lower or upper")
    if isinstance(lnb_lo_hz, bool) or not isinstance(lnb_lo_hz, int) or lnb_lo_hz <= 0:
        raise ValueError("LNB LO must be a positive integer")
    reference_rf_x2 = channel_reference_rf_hz_x2(channel)
    reference_if_x2 = reference_rf_x2 - 2 * lnb_lo_hz
    signed_offset_x2 = EDGE_CENTER_OFFSET_HZ_X2 * (1 if edge == "upper" else -1)
    center_if_x2 = reference_if_x2 + signed_offset_x2
    if center_if_x2 % 2:
        raise ValueError("15 MS/s edge center does not resolve to an integer-Hz IF")
    center_if_hz = center_if_x2 // 2
    center_rf_hz = center_if_hz + lnb_lo_hz
    if not 70_000_000 <= center_if_hz <= 6_000_000_000:
        raise ValueError("derived 15 MS/s IF center is outside the AD9361 tuning range")
    return {
        "channel_reference_rf_hz_x2": reference_rf_x2,
        "channel_reference_if_hz_x2": reference_if_x2,
        "edge_center_offset_hz_x2": signed_offset_x2,
        "nominal_on_if_hz": center_if_hz,
        "nominal_on_rf_hz": center_rf_hz,
    }


def _validate_fixture(fixture: dict[str, Any]) -> None:
    try:
        host = ipaddress.ip_address(fixture.get("ethernet_host"))
    except (TypeError, ValueError) as error:
        raise ProbeError("M4 fixture Ethernet host is not a literal IP address") from error
    supply = fixture.get("lnb_supply_volts")
    if (
        set(fixture) != FIXTURE_FIELDS
        or fixture.get("schema") != FIXTURE_SCHEMA
        or fixture.get("schema_version") != 1
        or fixture.get("receiver_serial") != RECEIVER_SERIAL
        or fixture.get("physical_rx_port") != "RX1"
        or host.version != 4
        or not host.is_private
        or fixture.get("usb_data_connected") is not False
        or fixture.get("volatile_runtime_power_continuity_verified") is not True
        or fixture.get("transmitter_connected") is not False
        or fixture.get("outdoor_view_verified") is not True
        or not isinstance(fixture.get("lnb_model"), str)
        or not fixture["lnb_model"].strip()
        or fixture.get("lnb_lo_hz") != LNB_LO_HZ
        or fixture.get("lo_side") != "low-side"
        or fixture.get("spectral_inversion") is not False
        or fixture.get("polarization")
        not in {"horizontal", "vertical", "left-circular", "right-circular"}
        or not isinstance(supply, (int, float))
        or isinstance(supply, bool)
        or not math.isfinite(supply)
        or not 10.0 <= float(supply) <= 20.0
        or not isinstance(fixture.get("lnb_power_source"), str)
        or not fixture["lnb_power_source"].strip()
        or fixture.get("operator_attestation") != FIXTURE_ATTESTATION
    ):
        raise ProbeError("M4 fixture declaration violates the live-LNB contract")
    _parse_time(fixture.get("created_at"), label="fixture created_at")


def _load_handoff(base: dict[str, Any]) -> Any:
    with monitor_v2._v7_monitor_contract():
        monitor_v1._validate_base_plan(base)
        # The base-plan validator scopes the v7 AD9361 contract only for its
        # own call.  Keep that contract active while loading the handoff too:
        # it supplies both the AD9361 identity and the v7 profile verifier.
        with monitor_v1._ad9361_v6_contract():
            return monitor_v1.probe_v1._load_handoff(
                ppu_repository=Path(base["ppu_repository"]),
                ppu_commit=base["ppu_source_commit"],
                candidate_path=Path(base["candidate_plan"]["path"]),
                operation_path=Path(base["operation_plan"]["path"]),
                ram_receipt_path=Path(base["ram_receipt"]["path"]),
                rate_msps=15,
            )


def _load_ppu(repository: Path, commit: str) -> Any:
    selected = monitor_v1.probe_v1._verify_ppu_repository(repository, commit)
    return SimpleNamespace(
        ppu=monitor_v1.probe_v1._import_ppu(selected),
        repository=selected,
    )


def _current_ppu_handoff(repository: Path) -> tuple[str, Any]:
    try:
        completed = subprocess.run(
            ("git", "-C", str(repository), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise ProbeError(f"M4 cannot resolve the current PPU commit: {error}") from error
    commit = completed.stdout.strip()
    if HEX_40.fullmatch(commit) is None:
        raise ProbeError("M4 current PPU commit is invalid")
    return commit, _load_ppu(repository, commit)


def _validate_persistent_lan_receipt(receipt: dict[str, Any]) -> tuple[str, str]:
    plan = receipt.get("plan")
    source = receipt.get("read_only_source_attestation")
    returned = receipt.get("read_only_return_attestation")
    rotation = receipt.get("host_key_rotation")
    expected_phases = [
        "preflight_revalidated",
        "remote_preflight_attested",
        "source_tx_quiesced",
        "remote_tx_safe_read_only_attested",
        "pluto_frm_staged",
        "staged_hash_verified",
        "updater_reported_done",
        "mtd3_fit_verified",
        "remote_stage_removed",
        "reboot_dispatched",
        "lan_iio_disappeared",
        "lan_iio_reappeared",
        "return_attested",
        "tx_safe_attested",
        "lan_ssh_host_key_rotated",
        "remote_return_tx_safe_read_only_attested",
    ]
    rotation_fields = {
        "previous_known_hosts_sha256",
        "replacement_known_hosts_sha256",
        "previous_fingerprint",
        "replacement_fingerprint",
        "previous_known_hosts_backup",
        "known_hosts_file",
    }
    return_fields = {
        "serial",
        "firmware",
        "boot_id",
        "qspi_bytes",
        "qspi_sha256",
        "fit_sha256",
        "all_buffer_enable",
        "dds_present",
        "tandem_present",
        "tx_hardwaregain_db",
        "tx_lo_powerdown",
        "tx_buffer_enable",
        "tx_scan_enable",
        "tx_dds_raw",
        "tx_dds_scale",
        "root_marker_present",
        "rx_dma_dt_state",
        "dds_dt_state",
        "tx_dma_dt_state",
        "tandem_dt_state",
    }
    try:
        source_gains = (
            [float(value) for value in source["tx_hardwaregain_db"].split(",")]
            if isinstance(source, dict)
            and isinstance(source.get("tx_hardwaregain_db"), str)
            else []
        )
        source_buffers = (
            [float(value) for value in source["all_buffer_enable"].split(",")]
            if isinstance(source, dict) and isinstance(source.get("all_buffer_enable"), str)
            else []
        )
        source_scans = (
            [float(value) for value in source["tx_scan_enable"].split(",")]
            if isinstance(source, dict) and isinstance(source.get("tx_scan_enable"), str)
            else []
        )
        source_raws = (
            [float(value) for value in source["tx_dds_raw"].split(",")]
            if isinstance(source, dict) and isinstance(source.get("tx_dds_raw"), str)
            else []
        )
        source_scales = (
            [float(value) for value in source["tx_dds_scale"].split(",")]
            if isinstance(source, dict) and isinstance(source.get("tx_dds_scale"), str)
            else []
        )
    except (TypeError, ValueError):
        source_gains = source_buffers = source_scans = source_raws = source_scales = []
    try:
        gains = (
            [float(value) for value in returned["tx_hardwaregain_db"].split(",")]
            if isinstance(returned, dict)
            and isinstance(returned.get("tx_hardwaregain_db"), str)
            else []
        )
    except (TypeError, ValueError):
        gains = []
    if (
        receipt.get("schema_version") != 2
        or receipt.get("transport") != "lan_ssh_frm"
        or receipt.get("outcome") != "success"
        or receipt.get("phases") != expected_phases
        or receipt.get("error") is not None
        or receipt.get("returned_serial") != RECEIVER_SERIAL
        or receipt.get("returned_firmware") != EXPECTED_FIRMWARE
        or receipt.get("returned_phy") != "ad9361"
        or not isinstance(plan, dict)
        or plan.get("host") != DEFAULT_LAN_HOST
        or plan.get("target_serial") != RECEIVER_SERIAL
        or plan.get("before_firmware")
        not in {
            "v0.48-plutoplus-spf-iq-direct-async-v3",
            "v0.49-plutoplus-spf-iq-direct-async-v4",
        }
        or plan.get("before_phy") != "ad9361"
        or plan.get("image_sha256") != EXPECTED_DFU_SHA256
        or plan.get("fit_sha256") != EXPECTED_FIT_SHA256
        or plan.get("fit_size") != EXPECTED_FIT_SIZE
        or plan.get("expected_firmware") != EXPECTED_FIRMWARE
        or plan.get("mutation_profile_id") != PERSISTENT_PROMOTION_PROFILE
        or plan.get("expected_metadata_abi") != 3
        or plan.get("expected_tandem_agc") is not False
        or plan.get("trust_model") != "explicit_lan_tofu"
        or plan.get("source_iio_layout") != "tx-capable-1r1t-v1"
        or plan.get("return_iio_layout") != "rx-only-1r1t-v1"
        or not isinstance(source, dict)
        or set(source) != return_fields
        or source.get("serial") != RECEIVER_SERIAL
        or source.get("firmware") != plan.get("before_firmware")
        or not isinstance(source.get("boot_id"), str)
        or BOOT_ID.fullmatch(source["boot_id"]) is None
        or not isinstance(source.get("qspi_bytes"), str)
        or not source["qspi_bytes"].isdigit()
        or int(source["qspi_bytes"]) <= 0
        or not isinstance(source.get("qspi_sha256"), str)
        or HEX_64.fullmatch(source["qspi_sha256"]) is None
        or not isinstance(source.get("fit_sha256"), str)
        or HEX_64.fullmatch(source["fit_sha256"]) is None
        or source.get("dds_present") != "1"
        or source.get("tandem_present") != "1"
        or len(source_gains) != 1
        or source_gains[0] > -80.0
        or source.get("tx_lo_powerdown") != "1"
        or source.get("tx_buffer_enable") != "0"
        or len(source_buffers) < 2
        or any(value != 0 for value in source_buffers)
        or len(source_scans) != 2
        or any(value != 0 for value in source_scans)
        or len(source_raws) != 4
        or any(value != 0 for value in source_raws)
        or len(source_scales) != 4
        or any(value != 0 for value in source_scales)
        or source.get("root_marker_present") != "0"
        or source.get("rx_dma_dt_state") != "enabled"
        or source.get("dds_dt_state") != "enabled"
        or source.get("tx_dma_dt_state") != "enabled"
        or source.get("tandem_dt_state") != "enabled"
        or not isinstance(rotation, dict)
        or set(rotation) != rotation_fields
        or any(
            not isinstance(rotation.get(key), str)
            or HEX_64.fullmatch(rotation[key]) is None
            for key in (
                "previous_known_hosts_sha256",
                "replacement_known_hosts_sha256",
            )
        )
        or rotation["previous_known_hosts_sha256"]
        == rotation["replacement_known_hosts_sha256"]
        or not isinstance(rotation.get("previous_known_hosts_backup"), str)
        or not Path(rotation["previous_known_hosts_backup"]).is_absolute()
        or not isinstance(rotation.get("known_hosts_file"), str)
        or not Path(rotation["known_hosts_file"]).is_absolute()
        or not isinstance(returned, dict)
        or set(returned) != return_fields
        or returned.get("serial") != RECEIVER_SERIAL
        or returned.get("firmware") != EXPECTED_FIRMWARE
        or not isinstance(returned.get("boot_id"), str)
        or BOOT_ID.fullmatch(returned["boot_id"]) is None
        or not isinstance(returned.get("qspi_bytes"), str)
        or not returned["qspi_bytes"].isdigit()
        or int(returned["qspi_bytes"]) <= 0
        or not isinstance(returned.get("qspi_sha256"), str)
        or HEX_64.fullmatch(returned["qspi_sha256"]) is None
        or returned.get("fit_sha256") != EXPECTED_FIT_SHA256
        or returned.get("dds_present") != "0"
        or returned.get("tandem_present") != "0"
        or len(gains) != 1
        or gains[0] > -80.0
        or returned.get("tx_lo_powerdown") != "1"
        or returned.get("tx_buffer_enable") != ""
        or returned.get("tx_scan_enable") != ""
        or returned.get("tx_dds_raw") != ""
        or returned.get("tx_dds_scale") != ""
        or returned.get("root_marker_present") != "1"
        or returned.get("rx_dma_dt_state") != "enabled"
        or returned.get("dds_dt_state") != "disabled"
        or returned.get("tx_dma_dt_state") != "disabled"
        or returned.get("tandem_dt_state") != "disabled"
        or not isinstance(returned.get("all_buffer_enable"), str)
        or not returned["all_buffer_enable"]
        or any(value != "0" for value in returned["all_buffer_enable"].split(","))
    ):
        raise ProbeError("M4 persistent LAN receipt violates the qualified v7 contract")
    return returned["boot_id"], returned["qspi_sha256"]


def _validate_lan_reboot_receipt(
    receipt: dict[str, Any], deployment: dict[str, Any]
) -> tuple[str, Path]:
    """Bind a PPU network reboot to the persistent image and rotated SSH trust."""

    deployment_boot_id, _qspi_sha256 = _validate_persistent_lan_receipt(deployment)
    deployment_rotation = deployment["host_key_rotation"]
    before = receipt.get("before")
    after = receipt.get("after")
    plan = receipt.get("plan")
    rotation = receipt.get("host_key_rotation")
    outer_fields = {
        "schema_version",
        "receipt_id",
        "plan",
        "started_at",
        "finished_at",
        "outcome",
        "completed_phases",
        "before",
        "after",
        "host_key_rotation",
        "dispatch_error",
        "error",
        "receipt_path",
    }
    attestation_fields = {"serial", "firmware", "boot_id", "capabilities"}
    capability_fields = {
        "board_model",
        "phy_model",
        "rx_scan_channels",
        "tandem_agc",
    }
    plan_fields = {
        "schema_version",
        "plan_id",
        "created_at",
        "serial",
        "ssh_host",
        "known_hosts_sha256",
        "expected_metadata_abi",
        "before",
        "iio_before",
        "confirmation_phrase",
    }
    iio_fields = {
        "serial",
        "firmware",
        "metadata_abi",
        "board_model",
        "phy_model",
        "rx_scan_channels",
        "tandem_agc",
    }
    rotation_fields = {
        "previous_known_hosts_sha256",
        "replacement_known_hosts_sha256",
        "previous_fingerprint",
        "replacement_fingerprint",
        "previous_known_hosts_backup",
        "known_hosts_file",
    }
    phases = [
        "usb_absence_reattested",
        "remote_identity_reattested",
        "lan_iiod_identity_reattested",
        "tx_safe_before_reboot",
        "reboot_dispatch_attempted",
        "reboot_dispatched",
        "lan_iio_disappeared",
        "lan_iio_reappeared",
        "lan_ssh_host_key_rotated",
        "post_reboot_identity_attested",
        "tx_safe_after_reboot",
    ]
    if (
        set(receipt) != outer_fields
        or receipt.get("schema_version") != 2
        or receipt.get("outcome") != "success"
        or receipt.get("completed_phases") != phases
        or receipt.get("error") is not None
        or (
            receipt.get("dispatch_error") is not None
            and not isinstance(receipt.get("dispatch_error"), str)
        )
        or not isinstance(receipt.get("receipt_id"), str)
        or HEX_32.fullmatch(receipt["receipt_id"]) is None
        or not isinstance(receipt.get("receipt_path"), str)
        or not Path(receipt["receipt_path"]).is_absolute()
        or not isinstance(before, dict)
        or set(before) != attestation_fields
        or not isinstance(after, dict)
        or set(after) != attestation_fields
        or not isinstance(plan, dict)
        or set(plan) != plan_fields
        or plan.get("schema_version") != 3
        or not isinstance(plan.get("plan_id"), str)
        or HEX_32.fullmatch(plan["plan_id"]) is None
        or plan.get("serial") != RECEIVER_SERIAL
        or plan.get("ssh_host") != DEFAULT_LAN_HOST
        or plan.get("expected_metadata_abi") != 3
        or plan.get("confirmation_phrase") != f"REBOOT LAN {RECEIVER_SERIAL}"
        or plan.get("before") != before
        or plan.get("known_hosts_sha256")
        != deployment_rotation["replacement_known_hosts_sha256"]
        or not isinstance(rotation, dict)
        or set(rotation) != rotation_fields
        or rotation.get("previous_known_hosts_sha256")
        != plan.get("known_hosts_sha256")
        or not isinstance(rotation.get("replacement_known_hosts_sha256"), str)
        or HEX_64.fullmatch(rotation["replacement_known_hosts_sha256"]) is None
        or rotation["replacement_known_hosts_sha256"]
        == rotation["previous_known_hosts_sha256"]
        or not isinstance(rotation.get("previous_known_hosts_backup"), str)
        or not Path(rotation["previous_known_hosts_backup"]).is_absolute()
        or not isinstance(rotation.get("known_hosts_file"), str)
        or not Path(rotation["known_hosts_file"]).is_absolute()
    ):
        raise ProbeError("M4 LAN reboot receipt violates the network-return contract")
    for label, attestation in (("before", before), ("after", after)):
        capabilities = attestation.get("capabilities")
        if (
            attestation.get("serial") != RECEIVER_SERIAL
            or attestation.get("firmware") != EXPECTED_FIRMWARE
            or not isinstance(attestation.get("boot_id"), str)
            or BOOT_ID.fullmatch(attestation["boot_id"]) is None
            or not isinstance(capabilities, dict)
            or set(capabilities) != capability_fields
            or not isinstance(capabilities.get("board_model"), str)
            or not capabilities["board_model"]
            or capabilities.get("phy_model") != "ad9361"
            or capabilities.get("rx_scan_channels") != ["voltage0", "voltage1"]
            or capabilities.get("tandem_agc") is not False
        ):
            raise ProbeError(f"M4 LAN reboot {label} attestation is invalid")
    iio_before = plan.get("iio_before")
    if (
        before["boot_id"] != deployment_boot_id
        or after["boot_id"] == before["boot_id"]
        or after["capabilities"] != before["capabilities"]
        or not isinstance(iio_before, dict)
        or set(iio_before) != iio_fields
        or iio_before.get("serial") != RECEIVER_SERIAL
        or iio_before.get("firmware") != EXPECTED_FIRMWARE
        or iio_before.get("metadata_abi") != 3
        or iio_before.get("board_model") != EXPECTED_MODEL
        or iio_before.get("phy_model") != "ad9361"
        or iio_before.get("rx_scan_channels") != ["voltage0", "voltage1"]
        or iio_before.get("tandem_agc") is not False
    ):
        raise ProbeError("M4 LAN reboot identity does not continue the deployment epoch")
    started = _parse_time(receipt.get("started_at"), label="LAN reboot started_at")
    finished = _parse_time(receipt.get("finished_at"), label="LAN reboot finished_at")
    created = _parse_time(plan.get("created_at"), label="LAN reboot plan created_at")
    if not created <= started <= finished:
        raise ProbeError("M4 LAN reboot timestamps are reversed")
    return after["boot_id"], Path(rotation["known_hosts_file"])


def _validate_plan(plan: dict[str, Any]) -> None:
    if set(plan) != PLAN_FIELDS:
        raise ProbeError("M4 plan fields differ from the v4 schema")
    try:
        host = ipaddress.ip_address(plan.get("ethernet_host"))
    except (TypeError, ValueError) as error:
        raise ProbeError("M4 plan Ethernet host is not a literal IP address") from error
    manual = plan.get("manual_gain_db")
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan.get("schema_version") != 4
        or not isinstance(plan.get("plan_id"), str)
        or HEX_32.fullmatch(plan["plan_id"]) is None
        or plan.get("hardware_accessed") is not False
        or plan.get("persistent_write") is not False
        or plan.get("do_not_merge") is not True
        or plan.get("deployment_mode") not in {"volatile_ram", "persistent_lan"}
        or plan.get("serial") != RECEIVER_SERIAL
        or plan.get("runtime_target") != RUNTIME_TARGET
        or plan.get("expected_firmware") != EXPECTED_FIRMWARE
        or plan.get("expected_model") != EXPECTED_MODEL
        or plan.get("claim_scope") != CLAIM_SCOPE
        or not isinstance(plan.get("ppu_repository"), str)
        or not Path(plan["ppu_repository"]).is_absolute()
        or not isinstance(plan.get("ppu_source_commit"), str)
        or HEX_40.fullmatch(plan["ppu_source_commit"]) is None
        or not isinstance(plan.get("expected_boot_id"), str)
        or BOOT_ID.fullmatch(plan["expected_boot_id"]) is None
        or not isinstance(plan.get("expected_qspi_sha256"), str)
        or HEX_64.fullmatch(plan["expected_qspi_sha256"]) is None
        or str(host) != DEFAULT_LAN_HOST
        or host.version != 4
        or not host.is_private
        or not isinstance(plan.get("host_network_interface"), str)
        or INTERFACE.fullmatch(plan["host_network_interface"]) is None
        or plan.get("sample_rate_hz") != SAMPLE_RATE_HZ
        or plan.get("rf_bandwidth_hz") != RF_BANDWIDTH_HZ
        or plan.get("rx_port_select") != "A_BALANCED"
        or plan.get("gain_mode") not in {"slow_attack", "manual"}
        or (
            plan.get("gain_mode") == "manual"
            and (
                not isinstance(manual, (int, float))
                or isinstance(manual, bool)
                or not math.isfinite(manual)
                or not -3.0 <= float(manual) <= 71.0
            )
        )
        or (plan.get("gain_mode") != "manual" and manual is not None)
        or plan.get("starlink_channel") != DEFAULT_CHANNEL
        or plan.get("starlink_edge") != DEFAULT_EDGE
        or plan.get("lnb_lo_hz") != LNB_LO_HZ
        or plan.get("off_slice_shift_hz") != DEFAULT_OFF_SLICE_SHIFT_HZ
        or plan.get("nominal_off_if_hz")
        != plan.get("nominal_on_if_hz", 0) + DEFAULT_OFF_SLICE_SHIFT_HZ
        or abs(plan["off_slice_shift_hz"])
        < POLICY["minimum_off_slice_separation_hz"]
        or plan.get("scan_offsets_hz") != list(OFFSET_ORDER_HZ)
        or plan.get("point_duration_ms") != DEFAULT_POINT_DURATION_MS
        or plan.get("settle_ms") != DEFAULT_SETTLE_MS
        or plan.get("stable_candidate_windows_per_point")
        != STABLE_CANDIDATE_WINDOWS_PER_POINT
        or plan.get("initial_discard_maps") != INITIAL_DISCARD_MAPS
        or plan.get("post_retune_discard_maps") != POST_RETUNE_DISCARD_MAPS
        or plan.get("role_monitor_duration_ms") != ROLE_MONITOR_DURATION_MS
        or plan.get("accepted_score_counter_budget")
        != ACCEPTED_SCORE_COUNTER_BUDGET
        or plan["accepted_score_counter_budget"]
        >= ACCEPTED_SCORE_COUNTER_SATURATION
        or plan.get("role_order") != list(ROLES)
        or plan.get("policy") != POLICY
        or plan.get("rail_probe_samples") != RAIL_PROBE_SAMPLES
        or not isinstance(plan.get("receipt_path"), str)
        or not Path(plan["receipt_path"]).is_absolute()
        or plan.get("confirmation_phrase")
        != (
            f"OBSERVE LIVE STARLINK PSS {RECEIVER_SERIAL} CH4 UPPER 15 MSPS"
        )
        or plan.get("pss_detected") is not False
        or plan.get("sss_detected") is not False
        or plan.get("frame_lock_claim") is not False
    ):
        raise ProbeError("M4 plan values violate the v4 live-LNB contract")
    _parse_time(plan.get("created_at"), label="plan created_at")
    for label in (
        "probe_plan",
        "deployment_receipt",
        "runner_source",
        "source_manifest",
        "controller_binary",
        "fixture_declaration",
    ):
        _validate_identity(plan.get(label), label=label)
    if plan["deployment_mode"] == "persistent_lan":
        if plan.get("ssh_trust_mode") != "pinned" or not isinstance(
            plan.get("ssh_known_hosts"), dict
        ):
            raise ProbeError("M4 persistent plan does not bind pinned SSH trust")
        _validate_identity(plan["ssh_known_hosts"], label="SSH known-hosts file")
        if plan.get("reboot_receipt") is not None:
            _validate_identity(plan["reboot_receipt"], label="LAN reboot receipt")
    elif (
        plan.get("ssh_trust_mode") != "legacy_unpinned"
        or plan.get("ssh_known_hosts") is not None
        or plan.get("reboot_receipt") is not None
    ):
        raise ProbeError("M4 volatile plan SSH trust fields are inconsistent")
    expected_geometry = live_geometry(DEFAULT_CHANNEL, DEFAULT_EDGE, LNB_LO_HZ)
    if any(plan.get(key) != value for key, value in expected_geometry.items()):
        raise ProbeError("M4 plan frequency geometry differs from the exact oracle")
    if not 70_000_000 <= plan["nominal_off_if_hz"] <= 6_000_000_000:
        raise ProbeError("M4 control IF is outside the AD9361 tuning range")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    fixture = commands.add_parser("fixture", help="seal the physical outdoor LNB setup")
    fixture.add_argument("--lnb-model", required=True)
    fixture.add_argument(
        "--polarization",
        choices=("horizontal", "vertical", "left-circular", "right-circular"),
        required=True,
    )
    fixture.add_argument("--lnb-supply-volts", type=float, required=True)
    fixture.add_argument("--lnb-power-source", required=True)
    fixture.add_argument("--ethernet-host", default=DEFAULT_LAN_HOST)
    fixture.add_argument("--attest", required=True)
    fixture.add_argument("--output", type=Path, required=True)

    plan = commands.add_parser("plan", help="seal one three-role live campaign")
    plan.add_argument("--probe-plan", type=Path, required=True)
    plan.add_argument("--deployment-receipt", type=Path)
    plan.add_argument("--reboot-receipt", type=Path)
    plan.add_argument("--controller-binary", type=Path, required=True)
    plan.add_argument("--fixture-declaration", type=Path, required=True)
    plan.add_argument("--host-network-interface", default=DEFAULT_LAN_INTERFACE)
    plan.add_argument("--gain-mode", choices=("slow_attack", "manual"), default=DEFAULT_GAIN_MODE)
    plan.add_argument("--manual-gain-db", type=float)
    plan.add_argument("--receipt", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)

    execute = commands.add_parser("execute", help="run the confirmed Ethernet-only campaign")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--ssh-password-file", type=Path, required=True)
    execute.add_argument("--confirm", required=True)
    execute.add_argument("--output", type=Path, required=True)
    execute.add_argument("--timeout-s", type=float, default=30.0)

    verify = commands.add_parser("verify", help="recompute and verify one receipt offline")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    return result


def build_fixture(args: Any) -> dict[str, Any]:
    if args.attest != FIXTURE_ATTESTATION:
        raise ProbeError(f"M4 fixture attestation must be exactly {FIXTURE_ATTESTATION!r}")
    monitor_v1.probe_v1._require_new_private_output(args.output)
    fixture = {
        "schema": FIXTURE_SCHEMA,
        "schema_version": 1,
        "created_at": _now(),
        "receiver_serial": RECEIVER_SERIAL,
        "physical_rx_port": "RX1",
        "ethernet_host": args.ethernet_host,
        "usb_data_connected": False,
        "volatile_runtime_power_continuity_verified": True,
        "transmitter_connected": False,
        "outdoor_view_verified": True,
        "lnb_model": args.lnb_model.strip(),
        "lnb_lo_hz": LNB_LO_HZ,
        "lo_side": "low-side",
        "spectral_inversion": False,
        "polarization": args.polarization,
        "lnb_supply_volts": args.lnb_supply_volts,
        "lnb_power_source": args.lnb_power_source.strip(),
        "operator_attestation": args.attest,
    }
    _validate_fixture(fixture)
    identity = monitor_v1.probe_v1._write_new_private(args.output, fixture)
    return {
        "verdict": "PASS_OFFLINE_M4_LIVE_FIXTURE_ONLY",
        "hardware_accessed": False,
        "fixture": identity,
    }


def build_plan(args: Any) -> dict[str, Any]:
    base_path = args.probe_plan.absolute()
    base = _load(base_path, label="M4 base PSS probe plan")
    fixture_path = args.fixture_declaration.absolute()
    fixture = _load(fixture_path, label="M4 fixture declaration")
    _validate_fixture(fixture)
    binary, _payload = progress_v1._binary_identity(args.controller_binary)
    monitor_v1.probe_v1._require_new_private_output(args.output)
    monitor_v1.probe_v1._require_new_private_output(args.receipt)
    if args.gain_mode == "manual" and args.manual_gain_db is None:
        raise ProbeError("manual gain mode requires --manual-gain-db")
    if args.gain_mode != "manual" and args.manual_gain_db is not None:
        raise ProbeError("--manual-gain-db is valid only with manual gain mode")
    if args.reboot_receipt is not None and args.deployment_receipt is None:
        raise ProbeError("--reboot-receipt requires --deployment-receipt")
    if args.deployment_receipt is None:
        deployment_mode = "volatile_ram"
        handoff = _load_handoff(base)
        deployment_path = Path(base["ram_receipt"]["path"])
        deployment_identity = _identity(deployment_path, label="M4 RAM receipt")
        if deployment_identity != base["ram_receipt"]:
            raise ProbeError("M4 base plan binds a changed RAM receipt")
        post = handoff.receipt.post_runtime
        if post is None:
            raise ProbeError("M4 RAM receipt lacks the candidate runtime")
        expected_boot_id = post.boot_id
        expected_qspi_sha256 = post.qspi.sha256
        ppu_repository = base["ppu_repository"]
        ppu_source_commit = base["ppu_source_commit"]
        ssh_trust_mode = "legacy_unpinned"
        ssh_known_hosts = None
        reboot_identity = None
    else:
        deployment_mode = "persistent_lan"
        with monitor_v2._v7_monitor_contract():
            monitor_v1._validate_base_plan(base)
        deployment_path = args.deployment_receipt.absolute()
        deployment = _load_external_receipt(
            deployment_path, label="persistent LAN receipt"
        )
        expected_boot_id, expected_qspi_sha256 = _validate_persistent_lan_receipt(
            deployment
        )
        deployment_identity = _identity(
            deployment_path, label="M4 persistent LAN receipt"
        )
        ppu_source_commit, handoff = _current_ppu_handoff(
            Path(base["ppu_repository"])
        )
        ppu_repository = str(handoff.repository)
        ssh_trust_mode = "pinned"
        known_hosts_path = Path(deployment["host_key_rotation"]["known_hosts_file"])
        reboot_identity = None
        if args.reboot_receipt is not None:
            reboot_path = args.reboot_receipt.absolute()
            reboot = _load_external_receipt(reboot_path, label="LAN reboot receipt")
            expected_boot_id, known_hosts_path = _validate_lan_reboot_receipt(
                reboot, deployment
            )
            reboot_identity = _identity(reboot_path, label="M4 LAN reboot receipt")
        ssh_known_hosts = _identity(known_hosts_path, label="SSH known-hosts file")
    geometry = live_geometry(DEFAULT_CHANNEL, DEFAULT_EDGE, LNB_LO_HZ)
    plan = {
        "schema": PLAN_SCHEMA,
        "schema_version": 4,
        "plan_id": uuid.uuid4().hex,
        "created_at": _now(),
        "hardware_accessed": False,
        "persistent_write": False,
        "do_not_merge": True,
        "deployment_mode": deployment_mode,
        "ssh_trust_mode": ssh_trust_mode,
        "ssh_known_hosts": ssh_known_hosts,
        "serial": RECEIVER_SERIAL,
        "runtime_target": RUNTIME_TARGET,
        "expected_firmware": EXPECTED_FIRMWARE,
        "expected_model": EXPECTED_MODEL,
        "claim_scope": CLAIM_SCOPE,
        "ppu_repository": ppu_repository,
        "ppu_source_commit": ppu_source_commit,
        "probe_plan": _identity(base_path, label="M4 base PSS probe plan"),
        "deployment_receipt": deployment_identity,
        "reboot_receipt": reboot_identity,
        "runner_source": _public_identity(
            Path(__file__).absolute(), label="M4 runner source"
        ),
        "source_manifest": _public_identity(
            SOURCE_MANIFEST, label="M4 source manifest"
        ),
        "expected_boot_id": expected_boot_id,
        "expected_qspi_sha256": expected_qspi_sha256,
        "controller_binary": binary,
        "fixture_declaration": _identity(fixture_path, label="M4 fixture declaration"),
        "ethernet_host": fixture["ethernet_host"],
        "host_network_interface": args.host_network_interface,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "rf_bandwidth_hz": RF_BANDWIDTH_HZ,
        "rx_port_select": "A_BALANCED",
        "gain_mode": args.gain_mode,
        "manual_gain_db": args.manual_gain_db,
        "starlink_channel": DEFAULT_CHANNEL,
        "starlink_edge": DEFAULT_EDGE,
        "lnb_lo_hz": LNB_LO_HZ,
        **geometry,
        "off_slice_shift_hz": DEFAULT_OFF_SLICE_SHIFT_HZ,
        "nominal_off_if_hz": geometry["nominal_on_if_hz"] + DEFAULT_OFF_SLICE_SHIFT_HZ,
        "scan_offsets_hz": list(OFFSET_ORDER_HZ),
        "point_duration_ms": DEFAULT_POINT_DURATION_MS,
        "settle_ms": DEFAULT_SETTLE_MS,
        "stable_candidate_windows_per_point": STABLE_CANDIDATE_WINDOWS_PER_POINT,
        "initial_discard_maps": INITIAL_DISCARD_MAPS,
        "post_retune_discard_maps": POST_RETUNE_DISCARD_MAPS,
        "role_monitor_duration_ms": ROLE_MONITOR_DURATION_MS,
        "accepted_score_counter_budget": ACCEPTED_SCORE_COUNTER_BUDGET,
        "role_order": list(ROLES),
        "policy": POLICY,
        "rail_probe_samples": RAIL_PROBE_SAMPLES,
        "receipt_path": str(args.receipt.absolute()),
        "confirmation_phrase": (
            f"OBSERVE LIVE STARLINK PSS {RECEIVER_SERIAL} CH4 UPPER 15 MSPS"
        ),
        "pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
    }
    _validate_plan(plan)
    identity = monitor_v1.probe_v1._write_new_private(args.output, plan)
    return {
        "verdict": "PASS_OFFLINE_M4_LIVE_PLAN_ONLY",
        "hardware_accessed": False,
        "persistent_write": False,
        "scan_span_ms_per_role": ROLE_MONITOR_DURATION_MS,
        "nominal_on_if_hz": geometry["nominal_on_if_hz"],
        "nominal_on_rf_hz": geometry["nominal_on_rf_hz"],
        "plan": identity,
        "next_confirmation": plan["confirmation_phrase"],
    }


def _point_metrics(records: list[dict[str, Any]], plan: dict[str, Any]) -> dict[str, Any]:
    if len(records) != plan["stable_candidate_windows_per_point"] or not all(
        record.get("candidate_available") is True for record in records
    ):
        raise ProbeError("M4 point lacks its exact stable candidate-window count")
    return m3.analyze_dwell([{}, {}, *records, {}], plan["policy"])


def _validate_counter_headroom(
    records: list[dict[str, Any]], plan: dict[str, Any]
) -> None:
    if not records or records[-1].get("schema") != monitor_v1.SUMMARY_SCHEMA:
        raise ProbeError("M4 continuous role lacks a counter summary")
    initial = records[-1].get("accepted_scores_before")
    if (
        not isinstance(initial, int)
        or isinstance(initial, bool)
        or initial < 0
        or initial + plan["accepted_score_counter_budget"]
        >= ACCEPTED_SCORE_COUNTER_SATURATION
    ):
        raise ProbeError("M4 FPGA accepted-score counter lacks campaign headroom")


def _positive_point(metrics: dict[str, Any], policy: dict[str, Any]) -> bool:
    return m3._positive_passes(metrics, policy)


def _point_rank(point: dict[str, Any]) -> tuple[float, int, float, int]:
    metrics = point["metrics"]
    return (
        metrics["pass_fraction"],
        metrics["longest_consecutive_track_windows"],
        metrics["median_peak_to_median"],
        -abs(point["offset_hz"]),
    )


def analyze_role(role: str, points: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    if role not in ROLES or len(points) != policy["scan_point_count"]:
        raise ProbeError("M4 role scan has invalid role or point count")
    offsets = [point.get("offset_hz") for point in points]
    if offsets != list(OFFSET_ORDER_HZ):
        raise ProbeError("M4 role scan offset order differs from the sealed interleave")
    for point in points:
        metrics = point.get("metrics")
        records = point.get("monitor_records")
        if not isinstance(metrics, dict) or not isinstance(records, list):
            raise ProbeError("M4 role point lacks metrics or monitor records")
    passing = [point for point in points if _positive_point(point["metrics"], policy)]
    best = max(points, key=_point_rank)
    return {
        "role": role,
        "point_count": len(points),
        "passing_point_count": len(passing),
        "passing_offsets_hz": [point["offset_hz"] for point in passing],
        "best_offset_hz": best["offset_hz"],
        "best_requested_rx_lo_hz": best["requested_rx_lo_hz"],
        "best_metrics": best["metrics"],
        "median_of_point_median_peak_to_median": statistics.median(
            point["metrics"]["median_peak_to_median"] for point in points
        ),
    }


def _evaluate_receipt(plan: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    roles = receipt.get("roles")
    if not isinstance(roles, dict) or list(roles) != list(ROLES):
        raise ProbeError("M4 receipt role inventory or order differs from the plan")
    analyses = {
        role: analyze_role(role, roles[role], plan["policy"]) for role in ROLES
    }
    positive_a = analyses["on_channel_a"]
    control = analyses["off_slice_control"]
    positive_b = analyses["on_channel_b"]
    contrast = min(
        positive_a["best_metrics"]["median_peak_to_median"],
        positive_b["best_metrics"]["median_peak_to_median"],
    ) / max(
        control["best_metrics"]["median_peak_to_median"], sys.float_info.min
    )
    rail = receipt.get("rail_probe")
    if not isinstance(rail, dict):
        raise ProbeError("M4 receipt lacks the bounded clipping probe")
    passed = (
        positive_a["passing_point_count"]
        >= plan["policy"]["minimum_passing_points_per_positive_role"]
        and positive_b["passing_point_count"]
        >= plan["policy"]["minimum_passing_points_per_positive_role"]
        and control["passing_point_count"]
        <= plan["policy"]["maximum_passing_points_in_control_role"]
        and contrast >= plan["policy"]["minimum_positive_to_negative_median_ratio"]
        and rail.get("rail_fraction", math.inf)
        <= plan["policy"]["maximum_rail_fraction"]
    )
    return {
        "role_analyses": analyses,
        "positive_to_control_median_ratio": contrast,
        "rail_fraction": rail.get("rail_fraction"),
        "qualified": passed,
    }


def _attribute(channel: Any, name: str, *, label: str) -> Any:
    value = getattr(channel, "attrs", {}).get(name)
    if value is None:
        raise ProbeError(f"M4 {label} attribute {name!r} is absent")
    return value


def _number(value: Any, *, label: str) -> float:
    try:
        result = float(str(value).strip().split()[0])
    except (IndexError, TypeError, ValueError) as error:
        raise ProbeError(f"M4 {label} is not numeric") from error
    if not math.isfinite(result):
        raise ProbeError(f"M4 {label} is not finite")
    return result


def _read_text(channel: Any, name: str, *, label: str) -> str:
    value = str(_attribute(channel, name, label=label).value).strip()
    if not value:
        raise ProbeError(f"M4 {label} {name} readback is blank")
    return value


def _read_number(channel: Any, name: str, *, label: str) -> float:
    return _number(_attribute(channel, name, label=label).value, label=f"{label} {name}")


def _write_text(channel: Any, name: str, value: str, *, label: str) -> str:
    attribute = _attribute(channel, name, label=label)
    attribute.value = value
    observed = str(attribute.value).strip()
    if observed != value:
        raise ProbeError(f"M4 {label} {name} readback differs from {value!r}")
    return observed


def _write_number(
    channel: Any,
    name: str,
    value: float,
    *,
    tolerance: float,
    label: str,
) -> float:
    attribute = _attribute(channel, name, label=label)
    attribute.value = str(value)
    observed = _number(attribute.value, label=f"{label} {name}")
    if abs(observed - float(value)) > tolerance:
        raise ProbeError(
            f"M4 {label} {name} readback {observed} differs from {value}"
        )
    return observed


def _one_device(context: Any, name: str) -> Any:
    matches = [device for device in context.devices if str(device.name) == name]
    if len(matches) != 1:
        raise ProbeError(f"M4 runtime requires exactly one {name!r} device")
    return matches[0]


def _optional_device(context: Any, name: str) -> Any | None:
    matches = [device for device in context.devices if str(device.name) == name]
    if len(matches) > 1:
        raise ProbeError(f"M4 runtime exposes multiple {name!r} devices")
    return matches[0] if matches else None


def _channel(device: Any, identifier: str, output: bool, *, label: str) -> Any:
    channel = device.find_channel(identifier, output)
    if channel is None:
        raise ProbeError(f"M4 {label} channel {identifier!r} is absent")
    return channel


def _context_objects(context: Any, plan: dict[str, Any]) -> dict[str, Any]:
    attrs = {str(key): str(value) for key, value in context.attrs.items()}
    serial = attrs.get("hw_serial", attrs.get("usb,serial", attrs.get("serial", "")))
    if (
        serial != plan["serial"]
        or attrs.get("fw_version") != plan["expected_firmware"]
        or attrs.get("hw_model") != plan["expected_model"]
        or attrs.get("ad9361-phy,model") != "ad9361"
    ):
        raise ProbeError("M4 Ethernet-IIO identity differs from the sealed runtime")
    phy = _one_device(context, "ad9361-phy")
    rx = _one_device(context, "cf-ad9361-lpc")
    if _optional_device(context, "cf-ad9361-dds-core-lpc") is not None:
        raise ProbeError("M4 RX-only runtime unexpectedly exposes the DDS core")
    if _optional_device(context, "tandem-agc") is not None:
        raise ProbeError("M4 RX-only runtime unexpectedly exposes tandem-agc")
    objects = {
        "attrs": attrs,
        "phy": phy,
        "rx": rx,
        "phy_rx": _channel(phy, "voltage0", False, label="PHY RX1"),
        "capture_i": _channel(rx, "voltage0", False, label="capture I"),
        "capture_q": _channel(rx, "voltage1", False, label="capture Q"),
        "rx_lo": _channel(phy, "altvoltage0", True, label="RX LO"),
    }
    if not all(
        bool(getattr(channel, "scan_element", False))
        for channel in (objects["capture_i"], objects["capture_q"])
    ):
        raise ProbeError("M4 capture I/Q channels are not scan elements")
    return objects


def _open_context(iio_module: Any, plan: dict[str, Any], timeout_s: float) -> tuple[Any, dict[str, Any]]:
    uri = f"ip:{plan['ethernet_host']}"
    deadline = time.monotonic() + timeout_s
    last_error = "Ethernet-IIO context did not settle"
    while True:
        context = None
        try:
            context = iio_module.Context(uri)
            setter = getattr(context, "set_timeout", None)
            if not callable(setter):
                raise ProbeError("M4 Ethernet-IIO context cannot set a timeout")
            setter(min(round(timeout_s * 1_000), 30_000))
            return context, _context_objects(context, plan)
        except (OSError, ProbeError) as error:
            last_error = str(error)
            if context is not None:
                close = getattr(context, "close", None)
                if callable(close):
                    with suppress(BaseException):
                        close()
            if time.monotonic() >= deadline:
                raise ProbeError(f"M4 Ethernet-IIO context failed: {last_error}") from error
            time.sleep(0.25)


def _close_context(handoff: Any, iio_module: Any, context: Any) -> None:
    closer = getattr(handoff.ppu.linux, "_close_iio_context", None)
    if not callable(closer):
        raise ProbeError("attested PPU source lacks deterministic IIO context close")
    try:
        closer(iio_module, context)
    except BaseException as error:
        raise ProbeError(f"M4 deterministic IIO context close failed: {error}") from error
    gc.collect()


def _snapshot_settings(objects: dict[str, Any]) -> dict[str, Any]:
    return {
        "phy_rx_sampling_frequency_hz": round(
            _read_number(objects["phy_rx"], "sampling_frequency", label="PHY RX1")
        ),
        "capture_i_sampling_frequency_hz": round(
            _read_number(objects["capture_i"], "sampling_frequency", label="capture I")
        ),
        "rf_bandwidth_hz": round(
            _read_number(objects["phy_rx"], "rf_bandwidth", label="PHY RX1")
        ),
        "rx_port_select": _read_text(
            objects["phy_rx"], "rf_port_select", label="PHY RX1"
        ),
        "gain_mode": _read_text(
            objects["phy_rx"], "gain_control_mode", label="PHY RX1"
        ),
        "hardwaregain_db": _read_number(
            objects["phy_rx"], "hardwaregain", label="PHY RX1"
        ),
        "rx_lo_hz": round(_read_number(objects["rx_lo"], "frequency", label="RX LO")),
        "rx_lo_powerdown": round(
            _read_number(objects["rx_lo"], "powerdown", label="RX LO")
        ),
    }


def _apply_settings(objects: dict[str, Any], plan: dict[str, Any], center_hz: int) -> dict[str, Any]:
    _write_number(objects["rx_lo"], "powerdown", 0, tolerance=0.0, label="RX LO")
    _write_number(
        objects["phy_rx"],
        "sampling_frequency",
        plan["sample_rate_hz"],
        tolerance=2.0,
        label="PHY RX1",
    )
    # The AD9361 clock must move before the FPGA capture-rate request.  Asking
    # the capture core for 15 MS/s while the PHY remains at (for example)
    # 30.72 MS/s is an invalid transient combination on the real runtime.
    _write_number(
        objects["capture_i"],
        "sampling_frequency",
        plan["sample_rate_hz"],
        tolerance=2.0,
        label="capture I",
    )
    _write_number(
        objects["phy_rx"],
        "rf_bandwidth",
        plan["rf_bandwidth_hz"],
        tolerance=2.0,
        label="PHY RX1",
    )
    _write_text(
        objects["phy_rx"], "rf_port_select", plan["rx_port_select"], label="PHY RX1"
    )
    _write_text(
        objects["phy_rx"], "gain_control_mode", plan["gain_mode"], label="PHY RX1"
    )
    if plan["gain_mode"] == "manual":
        _write_number(
            objects["phy_rx"],
            "hardwaregain",
            plan["manual_gain_db"],
            tolerance=0.1,
            label="PHY RX1",
        )
    _write_number(objects["rx_lo"], "frequency", center_hz, tolerance=2.0, label="RX LO")
    available = tuple(
        int(value)
        for value in _read_text(
            objects["capture_i"], "sampling_frequency_available", label="capture I"
        )
        .replace("[", "")
        .replace("]", "")
        .split()
    )
    reader = getattr(objects["rx"], "reg_read", None)
    if not callable(reader):
        raise ProbeError("M4 capture core lacks the FPGA decimation readback")
    adc_gp_control = int(reader(monitor_v1.probe_v1.ADC_GP_CONTROL_REG)) & 0xFFFFFFFF
    if available != (15_000_000, 1_875_000) or adc_gp_control & 1:
        raise ProbeError("M4 runtime is not the exact factor-one 15 MS/s path")
    selected = _snapshot_settings(objects)
    if (
        selected["phy_rx_sampling_frequency_hz"] != SAMPLE_RATE_HZ
        or selected["capture_i_sampling_frequency_hz"] != SAMPLE_RATE_HZ
        or selected["rf_bandwidth_hz"] != RF_BANDWIDTH_HZ
        or selected["rx_port_select"] != plan["rx_port_select"]
        or selected["gain_mode"] != plan["gain_mode"]
        or selected["rx_lo_hz"] != center_hz
        or selected["rx_lo_powerdown"] != 0
    ):
        raise ProbeError("M4 selected IIO settings differ from their readbacks")
    selected["capture_rates_available_hz"] = list(available)
    selected["adc_gp_control"] = adc_gp_control
    selected["fpga_decimation_factor"] = 1
    return selected


def _restore_settings(objects: dict[str, Any], original: dict[str, Any]) -> dict[str, Any]:
    # Gain restoration is mode-aware: a live AGC gain is telemetry, not a value
    # that can truthfully be restored.  A manual original is restored exactly.
    if original["gain_mode"] == "manual":
        _write_text(objects["phy_rx"], "gain_control_mode", "manual", label="PHY RX1")
        _write_number(
            objects["phy_rx"],
            "hardwaregain",
            original["hardwaregain_db"],
            tolerance=0.1,
            label="PHY RX1",
        )
    else:
        _write_text(
            objects["phy_rx"],
            "gain_control_mode",
            original["gain_mode"],
            label="PHY RX1",
        )
    _write_text(
        objects["phy_rx"],
        "rf_port_select",
        original["rx_port_select"],
        label="PHY RX1",
    )
    _write_number(
        objects["phy_rx"],
        "rf_bandwidth",
        original["rf_bandwidth_hz"],
        tolerance=2.0,
        label="PHY RX1",
    )
    _write_number(
        objects["phy_rx"],
        "sampling_frequency",
        original["phy_rx_sampling_frequency_hz"],
        tolerance=max(2.0, original["phy_rx_sampling_frequency_hz"] * 100e-6),
        label="PHY RX1",
    )
    _write_number(
        objects["capture_i"],
        "sampling_frequency",
        original["capture_i_sampling_frequency_hz"],
        tolerance=max(2.0, original["capture_i_sampling_frequency_hz"] * 100e-6),
        label="capture I",
    )
    _write_number(
        objects["rx_lo"],
        "frequency",
        original["rx_lo_hz"],
        tolerance=2.0,
        label="RX LO",
    )
    _write_number(
        objects["rx_lo"],
        "powerdown",
        original["rx_lo_powerdown"],
        tolerance=0.0,
        label="RX LO",
    )
    observed = _snapshot_settings(objects)
    exact = (
        "phy_rx_sampling_frequency_hz",
        "capture_i_sampling_frequency_hz",
        "rf_bandwidth_hz",
        "rx_port_select",
        "gain_mode",
        "rx_lo_hz",
        "rx_lo_powerdown",
    )
    if any(observed[key] != original[key] for key in exact):
        raise ProbeError("M4 restored IIO settings differ from the initial snapshot")
    if original["gain_mode"] == "manual" and abs(
        observed["hardwaregain_db"] - original["hardwaregain_db"]
    ) > 0.1:
        raise ProbeError("M4 restored manual RX gain differs from the initial snapshot")
    return observed


def _ssh_argv(plan: dict[str, Any], password_path: Path, command: str) -> tuple[str, ...]:
    if not command or "\x00" in command:
        raise ProbeError("M4 fixed SSH command is malformed")
    trust_options = (
        (
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={plan['ssh_known_hosts']['path']}",
            "-o",
            "GlobalKnownHostsFile=/dev/null",
            "-o",
            "CheckHostIP=yes",
        )
        if plan["ssh_trust_mode"] == "pinned"
        else (
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "GlobalKnownHostsFile=/dev/null",
            "-o",
            "CheckHostIP=no",
        )
    )
    return (
        "sshpass",
        "-f",
        str(password_path),
        "ssh",
        "-F",
        "/dev/null",
        "-B",
        plan["host_network_interface"],
        "-o",
        "BatchMode=no",
        "-o",
        "NumberOfPasswordPrompts=1",
        "-o",
        "PreferredAuthentications=password",
        "-o",
        "PasswordAuthentication=yes",
        "-o",
        "PubkeyAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        *trust_options,
        "-o",
        "UpdateHostKeys=no",
        f"root@{plan['ethernet_host']}",
        command,
    )


def _run(
    argv: Sequence[str],
    *,
    timeout_s: float,
    input_bytes: bytes | None = None,
    maximum_stdout_bytes: int = MAXIMUM_MONITOR_OUTPUT_BYTES,
) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            tuple(argv),
            input=input_bytes,
            check=False,
            capture_output=True,
            timeout=timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProbeError(f"M4 child process failed: {error}") from error
    if len(completed.stdout) > maximum_stdout_bytes:
        raise ProbeError("M4 child output exceeds the sealed size bound")
    if completed.returncode:
        detail = (completed.stdout + completed.stderr).decode(errors="replace")[-4_000:]
        raise ProbeError(f"M4 child process returned {completed.returncode}: {detail}")
    return completed


def _route_readback(plan: dict[str, Any]) -> dict[str, str]:
    completed = _run(
        ("ip", "-j", "-4", "route", "get", plan["ethernet_host"]),
        timeout_s=10.0,
        maximum_stdout_bytes=64 * 1024,
    )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ProbeError("M4 physical-LAN route readback is not JSON") from error
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise ProbeError("M4 physical-LAN route readback is not one route")
    route = value[0]
    if route.get("dev") != plan["host_network_interface"] or route.get("dst") != plan["ethernet_host"]:
        raise ProbeError("M4 physical-LAN route uses an unplanned interface or destination")
    source = route.get("prefsrc", route.get("src"))
    if not isinstance(source, str):
        raise ProbeError("M4 physical-LAN route lacks a source address")
    return {
        "destination": plan["ethernet_host"],
        "interface": plan["host_network_interface"],
        "source": source,
    }


def _remote_identity(plan: dict[str, Any], handoff: Any, password_path: Path) -> dict[str, str]:
    script = str(handoff.ppu.linux.REMOTE_RX_ONLY_IDENTITY_SCRIPT)
    completed = _run(
        _ssh_argv(plan, password_path, script), timeout_s=60.0, maximum_stdout_bytes=32 * 1024
    )
    fields: dict[str, str] = {}
    for line in completed.stdout.decode("utf-8").splitlines():
        if "=" not in line:
            raise ProbeError("M4 remote identity contains a malformed line")
        key, value = line.split("=", 1)
        if key in fields:
            raise ProbeError("M4 remote identity contains a duplicate field")
        fields[key] = value
    expected = {
        "boot_id",
        "firmware_version",
        "qspi_partition",
        "qspi_mtd_name",
        "qspi_bytes",
        "qspi_sha256",
        "uboot_attr_name_present",
        "uboot_attr_name",
        "uboot_attr_val_present",
        "uboot_attr_val",
        "uboot_compatible",
        "uboot_mode",
        "root_marker_present",
        "rx_dma_dt_state",
        "dds_dt_state",
        "tx_dma_dt_state",
        "tandem_dt_state",
    }
    if (
        set(fields) != expected
        or fields["boot_id"] != plan["expected_boot_id"]
        or fields["firmware_version"] != plan["expected_firmware"]
        or fields["qspi_partition"] != "/dev/mtdblock3"
        or fields["qspi_mtd_name"] != "qspi-linux"
        or not fields["qspi_bytes"].isdigit()
        or int(fields["qspi_bytes"]) <= 0
        or fields["qspi_sha256"] != plan["expected_qspi_sha256"]
        or fields["uboot_attr_name_present"] != "1"
        or fields["uboot_attr_name"] != "compatible"
        or fields["uboot_attr_val_present"] != "1"
        or fields["uboot_attr_val"] != "ad9361"
        or fields["uboot_compatible"] != "ad9361"
        or fields["uboot_mode"] != "1r1t"
        or fields["root_marker_present"] != "1"
        or fields["rx_dma_dt_state"] != "enabled"
        or fields["dds_dt_state"] != "disabled"
        or fields["tx_dma_dt_state"] != "disabled"
        or fields["tandem_dt_state"] != "disabled"
    ):
        raise ProbeError(
            "M4 remote boot/QSPI/topology identity differs from the deployment receipt"
        )
    return fields


def _upload_controller(plan: dict[str, Any], password_path: Path, payload: bytes) -> str:
    remote = (
        f"{REMOTE_PREFIX}-{plan['plan_id'][:12]}-"
        f"{plan['controller_binary']['sha256'][:12]}"
    )
    command = (
        f"umask 077 && test ! -e {remote} && cat > {remote} && chmod 700 {remote} && "
        f"sha256sum {remote}"
    )
    completed = _run(
        _ssh_argv(plan, password_path, command),
        timeout_s=30.0,
        input_bytes=payload,
        maximum_stdout_bytes=4_096,
    )
    expected = f"{plan['controller_binary']['sha256']}  {remote}"
    if completed.stdout.decode(errors="replace").strip() != expected:
        raise ProbeError("M4 remote controller digest readback differs from the plan")
    return remote


def _remove_controller(plan: dict[str, Any], password_path: Path, remote: str) -> None:
    _run(
        _ssh_argv(plan, password_path, f"rm -f {remote} && test ! -e {remote}"),
        timeout_s=15.0,
        maximum_stdout_bytes=4_096,
    )


def _controller_info(
    plan: dict[str, Any], password_path: Path, remote: str
) -> dict[str, Any]:
    completed = _run(
        _ssh_argv(
            plan,
            password_path,
            f"{remote} --expect-serial {plan['serial']} info",
        ),
        timeout_s=15.0,
        maximum_stdout_bytes=32 * 1024,
    )
    try:
        value = json.loads(
            completed.stdout, object_pairs_hook=monitor_v1.probe_v1._json_no_duplicates
        )
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        raise ProbeError("M4 controller info is not strict JSON") from error
    if not isinstance(value, dict):
        raise ProbeError("M4 controller info is not an object")
    try:
        status = int(str(value.get("status", "")), 0)
    except ValueError as error:
        raise ProbeError("M4 controller status is not numeric") from error
    if (
        value.get("schema") != "starlink-pss-acqctl.info.v1"
        or value.get("serial") != plan["serial"]
        or value.get("input_rate_msps") != 15
        or status & 0x2
    ):
        raise ProbeError("M4 controller info does not prove the engine is disabled")
    return value


def _controller_snapshot(
    plan: dict[str, Any], password_path: Path, remote: str
) -> dict[str, Any]:
    completed = _run(
        _ssh_argv(
            plan,
            password_path,
            f"{remote} --expect-serial {plan['serial']} snapshot --timeout-ms 1000",
        ),
        timeout_s=15.0,
        maximum_stdout_bytes=32 * 1024,
    )
    try:
        value = json.loads(
            completed.stdout, object_pairs_hook=monitor_v1.probe_v1._json_no_duplicates
        )
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        raise ProbeError("M4 controller snapshot is not strict JSON") from error
    if not isinstance(value, dict):
        raise ProbeError("M4 controller snapshot is not an object")
    _validate_preflight_snapshot(value, plan)
    return value


def _validate_preflight_snapshot(
    snapshot: dict[str, Any], plan: dict[str, Any]
) -> None:
    fields = {
        "schema",
        "claim_scope",
        "serial",
        "abi_version",
        "snapshot_generation",
        "ready_mask",
        "map_generations",
        "map_start_indexes",
        "accepted_scores",
        "published_maps",
        "health_flags",
        "fault_free_epoch",
        "discarded_scores",
        "discontinuity_aborts",
        "map_overruns",
        "protocol_errors",
        "arithmetic_overflows",
        "map_read_errors",
        "map_release_errors",
        "ingress_dropped_samples",
        "ingress_fifo_level",
        "ingress_fifo_maximum",
        "scheduler_gaps",
        "scheduler_index_errors",
        "scheduler_overflows",
        "detector_faults",
        "phase_discontinuities",
        "zero_denominators",
        "candidate_fifo_level",
        "candidate_fifo_maximum",
    }
    hard_zero = {
        "map_overruns",
        "protocol_errors",
        "arithmetic_overflows",
        "map_read_errors",
        "map_release_errors",
        "ingress_dropped_samples",
        "scheduler_gaps",
        "scheduler_index_errors",
        "scheduler_overflows",
        "detector_faults",
        "phase_discontinuities",
        "zero_denominators",
    }
    accepted = snapshot.get("accepted_scores")
    discarded = snapshot.get("discarded_scores")
    aborts = snapshot.get("discontinuity_aborts")
    u32_fields = {
        "snapshot_generation",
        "accepted_scores",
        "published_maps",
        "discarded_scores",
        "discontinuity_aborts",
        "ingress_fifo_level",
        "ingress_fifo_maximum",
        "candidate_fifo_level",
        "candidate_fifo_maximum",
    } | hard_zero
    map_generations = snapshot.get("map_generations")
    map_start_indexes = snapshot.get("map_start_indexes")
    if (
        set(snapshot) != fields
        or snapshot.get("schema") != "starlink-pss-acqctl.snapshot.v1"
        or snapshot.get("claim_scope") != "acquisition_telemetry_only"
        or snapshot.get("serial") != plan["serial"]
        or snapshot.get("abi_version") != "0x00010001"
        or snapshot.get("ready_mask") != 0
        or snapshot.get("health_flags") != "0x00000000"
        or any(
            not isinstance(snapshot.get(field), int)
            or isinstance(snapshot.get(field), bool)
            or not 0 <= snapshot[field] <= ACCEPTED_SCORE_COUNTER_SATURATION
            for field in u32_fields
        )
        or not isinstance(map_generations, list)
        or len(map_generations) != 2
        or any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or not 0 <= value <= ACCEPTED_SCORE_COUNTER_SATURATION
            for value in map_generations
        )
        or not isinstance(map_start_indexes, list)
        or len(map_start_indexes) != 2
        or any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or not 0 <= value <= (1 << 64) - 1
            for value in map_start_indexes
        )
        or snapshot.get("ingress_fifo_level", 1)
        > snapshot.get("ingress_fifo_maximum", 0)
        or snapshot.get("candidate_fifo_level", 1)
        > snapshot.get("candidate_fifo_maximum", 0)
        or not isinstance(accepted, int)
        or isinstance(accepted, bool)
        or accepted < 0
        or accepted + plan["accepted_score_counter_budget"]
        >= ACCEPTED_SCORE_COUNTER_SATURATION
        or not isinstance(discarded, int)
        or isinstance(discarded, bool)
        or not 0 <= discarded < ACCEPTED_SCORE_COUNTER_SATURATION
        or not isinstance(aborts, int)
        or isinstance(aborts, bool)
        or not 0 <= aborts < ACCEPTED_SCORE_COUNTER_SATURATION
        or any(snapshot.get(field) != 0 for field in hard_zero)
        or snapshot.get("fault_free_epoch") is not (discarded == 0 and aborts == 0)
    ):
        raise ProbeError("M4 FPGA preflight snapshot lacks clean campaign headroom")


def _rail_probe(plan: dict[str, Any]) -> dict[str, Any]:
    argv = (
        "iio_readdev",
        "-u",
        f"ip:{plan['ethernet_host']}",
        "-T",
        "10000",
        "-b",
        str(plan["rail_probe_samples"]),
        "-s",
        str(plan["rail_probe_samples"]),
        "cf-ad9361-lpc",
        "voltage0",
        "voltage1",
    )
    completed = _run(
        argv,
        timeout_s=30.0,
        maximum_stdout_bytes=plan["rail_probe_samples"] * 4 + 1,
    )
    payload = completed.stdout
    expected_bytes = plan["rail_probe_samples"] * 4
    if len(payload) != expected_bytes:
        raise ProbeError(
            f"M4 rail probe returned {len(payload)} bytes, expected {expected_bytes}"
        )
    components = array.array("h")
    components.frombytes(payload)
    if sys.byteorder != "little":
        components.byteswap()
    rail_count = sum(value <= -2_048 or value >= 2_047 for value in components)
    near_rail_count = sum(value <= -2_040 or value >= 2_039 for value in components)
    square_sum = sum(value * value for value in components)
    return {
        "sample_count": plan["rail_probe_samples"],
        "component_count": len(components),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "minimum_component": min(components),
        "maximum_component": max(components),
        "maximum_absolute_component": max(abs(value) for value in components),
        "rms_component": math.sqrt(square_sum / len(components)),
        "rail_count": rail_count,
        "near_rail_count": near_rail_count,
        "rail_fraction": rail_count / len(components),
        "payload_retained": False,
    }


def _scan_role(
    plan: dict[str, Any],
    role: str,
    objects: dict[str, Any],
    password_path: Path,
    remote: str,
    *,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base_hz = (
        plan["nominal_off_if_hz"]
        if role == "off_slice_control"
        else plan["nominal_on_if_hz"]
    )
    command = (
        f"{remote} --expect-serial {plan['serial']} monitor "
        f"--duration-ms {plan['role_monitor_duration_ms']} --timeout-ms 1000"
    )
    process: subprocess.Popen[bytes] | None = None
    stderr_file: Any = None
    points: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    output_bytes = 0
    discarded = plan["initial_discard_maps"]
    point_index = 0
    offset_hz = plan["scan_offsets_hz"][0]
    requested = base_hz + offset_hz
    readback = round(
        _write_number(objects["rx_lo"], "frequency", requested, tolerance=2.0, label="RX LO")
    )
    sleeper(plan["settle_ms"] / 1_000.0)
    started = _now()
    rssi_before = _read_number(objects["phy_rx"], "rssi", label="PHY RX1")
    gain_before = _read_number(objects["phy_rx"], "hardwaregain", label="PHY RX1")
    deadline = time.monotonic() + 120.0
    try:
        # It must remain open through forced child cleanup in the finally block.
        stderr_file = tempfile.TemporaryFile()  # noqa: SIM115
        process = subprocess.Popen(
            _ssh_argv(plan, password_path, command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            bufsize=0,
        )
        if process.stdout is None:
            raise ProbeError("M4 continuous role lacks a stdout pipe")
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProbeError("M4 continuous role exceeded 120 seconds")
            ready, _, _ = select.select([process.stdout], [], [], min(2.0, remaining))
            if not ready:
                if process.poll() is not None:
                    break
                continue
            line = process.stdout.readline()
            if not line:
                break
            output_bytes += len(line)
            if output_bytes > MAXIMUM_MONITOR_OUTPUT_BYTES:
                raise ProbeError("M4 continuous role output exceeds the sealed size bound")
            try:
                record = json.loads(
                    line, object_pairs_hook=monitor_v1.probe_v1._json_no_duplicates
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                raise ProbeError("M4 continuous role returned invalid NDJSON") from error
            if not isinstance(record, dict):
                raise ProbeError("M4 continuous role returned a non-object record")
            records.append(record)
            if record.get("schema") != monitor_v1.MAP_SCHEMA or point_index >= len(
                plan["scan_offsets_hz"]
            ):
                continue
            if discarded:
                discarded -= 1
                continue
            candidates.append(record)
            if len(candidates) != plan["stable_candidate_windows_per_point"]:
                continue
            rssi_after = _read_number(objects["phy_rx"], "rssi", label="PHY RX1")
            gain_after = _read_number(
                objects["phy_rx"], "hardwaregain", label="PHY RX1"
            )
            points.append(
                {
                    "role": role,
                    "ordinal": point_index + 1,
                    "offset_hz": offset_hz,
                    "base_if_hz": base_hz,
                    "requested_rx_lo_hz": requested,
                    "readback_rx_lo_hz": readback,
                    "started_at": started,
                    "completed_at": _now(),
                    "settle_ms": plan["settle_ms"],
                    "duration_ms": plan["point_duration_ms"],
                    "rssi_before_db": rssi_before,
                    "rssi_after_db": rssi_after,
                    "hardwaregain_before_db": gain_before,
                    "hardwaregain_after_db": gain_after,
                    "monitor_stderr": "",
                    "monitor_start_attempts": 1,
                    "monitor_records": candidates,
                    "metrics": _point_metrics(candidates, plan),
                }
            )
            point_index += 1
            if point_index >= len(plan["scan_offsets_hz"]):
                continue
            offset_hz = plan["scan_offsets_hz"][point_index]
            requested = base_hz + offset_hz
            readback = round(
                _write_number(
                    objects["rx_lo"], "frequency", requested, tolerance=2.0, label="RX LO"
                )
            )
            sleeper(plan["settle_ms"] / 1_000.0)
            started = _now()
            rssi_before = _read_number(objects["phy_rx"], "rssi", label="PHY RX1")
            gain_before = _read_number(
                objects["phy_rx"], "hardwaregain", label="PHY RX1"
            )
            discarded = plan["post_retune_discard_maps"]
            candidates = []
        return_code = process.wait(timeout=5.0)
        stderr_file.seek(0)
        stderr = stderr_file.read().decode(errors="replace")[-4_000:]
        if return_code:
            raise ProbeError(f"M4 continuous role returned {return_code}: {stderr}")
        monitor_v2._validate_monitor_records(
            records,
            {"serial": plan["serial"], "duration_ms": plan["role_monitor_duration_ms"]},
        )
        if len(points) != len(plan["scan_offsets_hz"]):
            raise ProbeError("M4 continuous role ended before all LO points")
        return points, {"monitor_records": records, "monitor_stderr": stderr}
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            with suppress(subprocess.TimeoutExpired):
                process.wait(timeout=5.0)
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5.0)
        if stderr_file is not None:
            stderr_file.close()


def _verify_point(point: dict[str, Any], plan: dict[str, Any], role: str, ordinal: int) -> None:
    required = {
        "role",
        "ordinal",
        "offset_hz",
        "base_if_hz",
        "requested_rx_lo_hz",
        "readback_rx_lo_hz",
        "started_at",
        "completed_at",
        "settle_ms",
        "duration_ms",
        "rssi_before_db",
        "rssi_after_db",
        "hardwaregain_before_db",
        "hardwaregain_after_db",
        "monitor_stderr",
        "monitor_start_attempts",
        "monitor_records",
        "metrics",
    }
    base = plan["nominal_off_if_hz"] if role == "off_slice_control" else plan["nominal_on_if_hz"]
    offset = plan["scan_offsets_hz"][ordinal - 1]
    numeric = (
        "rssi_before_db",
        "rssi_after_db",
        "hardwaregain_before_db",
        "hardwaregain_after_db",
    )
    if (
        set(point) != required
        or point.get("role") != role
        or point.get("ordinal") != ordinal
        or point.get("offset_hz") != offset
        or point.get("base_if_hz") != base
        or point.get("requested_rx_lo_hz") != base + offset
        or abs(point.get("readback_rx_lo_hz", 0) - (base + offset)) > 2
        or point.get("settle_ms") != plan["settle_ms"]
        or point.get("duration_ms") != plan["point_duration_ms"]
        or not isinstance(point.get("monitor_stderr"), str)
        or not isinstance(point.get("monitor_start_attempts"), int)
        or isinstance(point.get("monitor_start_attempts"), bool)
        or point["monitor_start_attempts"] != 1
        or any(
            not isinstance(point.get(key), (int, float))
            or isinstance(point.get(key), bool)
            or not math.isfinite(point[key])
            for key in numeric
        )
    ):
        raise ProbeError(f"M4 {role} point {ordinal} violates the v1 schema")
    started = _parse_time(point.get("started_at"), label=f"{role} point started_at")
    completed = _parse_time(point.get("completed_at"), label=f"{role} point completed_at")
    if completed < started:
        raise ProbeError(f"M4 {role} point timestamps are reversed")
    records = point.get("monitor_records")
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        raise ProbeError(f"M4 {role} point lacks monitor records")
    expected_metrics = _point_metrics(records, plan)
    if point.get("metrics") != expected_metrics:
        raise ProbeError(f"M4 {role} point metrics differ from recomputation")


def _verify_inputs(plan: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    for key, label in (
        ("probe_plan", "base PSS probe plan"),
        ("deployment_receipt", "deployment receipt"),
        ("fixture_declaration", "fixture declaration"),
    ):
        _require_unchanged(plan[key], label=label)
    if plan["ssh_trust_mode"] == "pinned":
        _require_unchanged(plan["ssh_known_hosts"], label="SSH known-hosts file")
    if plan["reboot_receipt"] is not None:
        _require_unchanged(plan["reboot_receipt"], label="LAN reboot receipt")
    for key, label in (
        ("runner_source", "M4 runner source"),
        ("source_manifest", "M4 source manifest"),
        ("controller_binary", "controller binary"),
    ):
        _require_public_unchanged(plan[key], label=label)
    base = _load(Path(plan["probe_plan"]["path"]), label="M4 base PSS probe plan")
    if plan["deployment_mode"] == "volatile_ram":
        handoff = _load_handoff(base)
        if base["ram_receipt"] != plan["deployment_receipt"]:
            raise ProbeError("M4 base PSS plan and live plan bind different RAM receipts")
        post = handoff.receipt.post_runtime
        if (
            post is None
            or post.boot_id != plan["expected_boot_id"]
            or post.qspi.sha256 != plan["expected_qspi_sha256"]
        ):
            raise ProbeError("M4 RAM receipt runtime identity changed from the live plan")
    else:
        with monitor_v2._v7_monitor_contract():
            monitor_v1._validate_base_plan(base)
        if Path(plan["ppu_repository"]).resolve() != Path(base["ppu_repository"]).resolve():
            raise ProbeError("M4 persistent plan changed the base PPU repository")
        handoff = _load_ppu(
            Path(plan["ppu_repository"]), plan["ppu_source_commit"]
        )
        deployment = _load_external_receipt(
            Path(plan["deployment_receipt"]["path"]),
            label="persistent LAN receipt",
        )
        boot_id, qspi_sha256 = _validate_persistent_lan_receipt(deployment)
        if plan["reboot_receipt"] is not None:
            reboot = _load_external_receipt(
                Path(plan["reboot_receipt"]["path"]),
                label="LAN reboot receipt",
            )
            boot_id, known_hosts_path = _validate_lan_reboot_receipt(
                reboot, deployment
            )
            if Path(plan["ssh_known_hosts"]["path"]) != known_hosts_path:
                raise ProbeError("M4 LAN reboot and plan bind different SSH trust files")
        if (
            boot_id != plan["expected_boot_id"]
            or qspi_sha256 != plan["expected_qspi_sha256"]
        ):
            raise ProbeError("M4 persistent deployment identity changed from the live plan")
    fixture = _load(Path(plan["fixture_declaration"]["path"]), label="M4 fixture")
    _validate_fixture(fixture)
    if fixture["ethernet_host"] != plan["ethernet_host"]:
        raise ProbeError("M4 fixture and live plan Ethernet hosts differ")
    return base, handoff


def execute_plan(args: Any) -> dict[str, Any]:
    plan_path = args.plan.absolute()
    plan = _load(plan_path, label="M4 live plan")
    _validate_plan(plan)
    if args.confirm != plan["confirmation_phrase"]:
        raise ProbeError(f"confirmation must be exactly {plan['confirmation_phrase']!r}")
    if args.output.absolute() != Path(plan["receipt_path"]):
        raise ProbeError("M4 execute output differs from the sealed receipt path")
    if not 5.0 <= args.timeout_s <= 120.0:
        raise ProbeError("M4 execution timeout must lie in [5, 120] seconds")
    monitor_v1.probe_v1._require_new_private_output(args.output)
    _base, handoff = _verify_inputs(plan)
    binary, payload = progress_v1._binary_identity(Path(plan["controller_binary"]["path"]))
    if binary != plan["controller_binary"]:
        raise ProbeError("M4 controller binary changed after plan sealing")
    try:
        password = handoff.ppu.lifecycle.validate_password_file(args.ssh_password_file)
        iio_module = importlib.import_module("iio")
        radio_lock = importlib.import_module("pluto_plus.radio_lock")
    except (ImportError, OSError, ValueError) as error:
        raise ProbeError(f"M4 dependency cannot be attested: {error}") from error
    expected_ppu_root = (Path(plan["ppu_repository"]) / "src").resolve()
    if not Path(str(radio_lock.__file__)).resolve().is_relative_to(expected_ppu_root):
        raise ProbeError("M4 radio-lock module is outside the attested PPU checkout")

    started = _now()
    failure: BaseException | None = None
    context: Any = None
    objects: dict[str, Any] | None = None
    original: dict[str, Any] | None = None
    selected: dict[str, Any] | None = None
    restored: dict[str, Any] | None = None
    rail_probe: dict[str, Any] | None = None
    roles: dict[str, list[dict[str, Any]]] = {}
    role_monitors: dict[str, dict[str, Any]] = {}
    route: dict[str, str] | None = None
    runtime_before: dict[str, str] | None = None
    runtime_after: dict[str, str] | None = None
    final_info: dict[str, Any] | None = None
    controller_snapshot_before: dict[str, Any] | None = None
    remote: str | None = None
    remote_removed = False
    context_close_verified = False
    locks_acquired = False
    cleanup_errors: list[str] = []
    evaluation: dict[str, Any] | None = None
    cleanup_performed = False

    def cleanup_hardware() -> None:
        nonlocal context, objects, restored, remote_removed, context_close_verified
        nonlocal cleanup_performed
        if cleanup_performed:
            return
        cleanup_performed = True
        if remote is not None and not remote_removed:
            try:
                _remove_controller(plan, password.path, remote)
                remote_removed = True
            except BaseException as error:  # noqa: BLE001 - retain cleanup detail
                cleanup_errors.append(f"remote controller: {error}")
        if original is not None and restored is None and context is None:
            try:
                context, objects = _open_context(iio_module, plan, args.timeout_s)
            except BaseException as error:  # noqa: BLE001 - retain cleanup detail
                cleanup_errors.append(f"IIO reopen for restore: {error}")
        if context is not None:
            if objects is not None and original is not None and restored is None:
                try:
                    restored = _restore_settings(objects, original)
                except BaseException as error:  # noqa: BLE001 - retain cleanup detail
                    cleanup_errors.append(f"IIO restore: {error}")
            try:
                _close_context(handoff, iio_module, context)
                context_close_verified = True
                context = None
                objects = None
            except BaseException as error:  # noqa: BLE001 - retain cleanup detail
                cleanup_errors.append(f"IIO close: {error}")

    try:
        with ExitStack() as stack:
            stack.enter_context(radio_lock.acquire_radio_lock(plan["serial"]))
            stack.enter_context(radio_lock.acquire_radio_lock(PHYSICAL_LAN_LOCK_KEY))
            # Registered after both locks, so restoration/removal runs before
            # either exclusion lock is released on every exit path.
            stack.callback(cleanup_hardware)
            locks_acquired = True
            route = _route_readback(plan)
            runtime_before = _remote_identity(plan, handoff, password.path)
            context, objects = _open_context(iio_module, plan, args.timeout_s)
            original = _snapshot_settings(objects)
            selected = _apply_settings(objects, plan, plan["nominal_on_if_hz"])
            _close_context(handoff, iio_module, context)
            context = None
            objects = None
            context_close_verified = True

            rail_probe = _rail_probe(plan)
            context, objects = _open_context(iio_module, plan, args.timeout_s)
            selected_after_probe = _snapshot_settings(objects)
            for key in (
                "phy_rx_sampling_frequency_hz",
                "capture_i_sampling_frequency_hz",
                "rf_bandwidth_hz",
                "rx_port_select",
                "gain_mode",
                "rx_lo_hz",
                "rx_lo_powerdown",
            ):
                if selected_after_probe[key] != selected[key]:
                    raise ProbeError("M4 rail probe changed a selected RF setting")

            remote = _upload_controller(plan, password.path, payload)
            controller_snapshot_before = _controller_snapshot(
                plan, password.path, remote
            )
            for role in ROLES:
                roles[role], role_monitors[role] = _scan_role(
                    plan, role, objects, password.path, remote
                )
                if role == ROLES[0]:
                    _validate_counter_headroom(
                        role_monitors[role]["monitor_records"], plan
                    )
            final_info = _controller_info(plan, password.path, remote)
            _remove_controller(plan, password.path, remote)
            remote_removed = True
            restored = _restore_settings(objects, original)
            _close_context(handoff, iio_module, context)
            context = None
            objects = None
            context_close_verified = True
            runtime_after = _remote_identity(plan, handoff, password.path)
            if runtime_after != runtime_before:
                raise ProbeError("M4 remote runtime identity changed during the live campaign")
    except BaseException as error:  # noqa: BLE001 - every hardware outcome gets a receipt
        failure = error
    finally:
        cleanup_hardware()
        if cleanup_errors and failure is None:
            failure = ProbeError("M4 cleanup failed: " + "; ".join(cleanup_errors))

    completed = _now()
    preliminary = {
        "roles": roles,
        "role_monitors": role_monitors,
        "rail_probe": rail_probe,
    }
    if failure is None:
        try:
            evaluation = _evaluate_receipt(plan, preliminary)
        except BaseException as error:  # noqa: BLE001 - qualification failure is durable
            failure = error
    qualified = failure is None and evaluation is not None and evaluation["qualified"] is True
    outcome = "pass" if qualified else ("unqualified" if failure is None else "failed")
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "schema_version": 4,
        "receipt_id": uuid.uuid4().hex,
        "started_at": started,
        "completed_at": completed,
        "outcome": outcome,
        "plan": _identity(plan_path, label="M4 live plan"),
        "serial": plan["serial"],
        "runtime_target": plan["runtime_target"],
        "expected_firmware": plan["expected_firmware"],
        "hardware_accessed": True,
        "persistent_write": False,
        "do_not_merge": True,
        "claim_scope": CLAIM_SCOPE,
        "route_readback": route,
        "radio_and_physical_lan_locks_acquired": locks_acquired,
        "runtime_before": runtime_before,
        "runtime_after": runtime_after,
        "iio_before": original,
        "iio_selected": selected,
        "rail_probe": rail_probe,
        "roles": roles,
        "role_monitors": role_monitors,
        "controller_snapshot_before": controller_snapshot_before,
        "controller_info_after": final_info,
        "controller_binary_removed": remote_removed,
        "iio_restored": restored,
        "iio_context_close_verified": context_close_verified,
        "evaluation": evaluation,
        "live_pss_acquired": qualified,
        "timing_trajectory_qualified": qualified,
        "off_slice_control_rejected": qualified,
        "pss_detected": qualified,
        "sss_detected": False,
        "frame_lock_claim": False,
        "recovery_required": plan["deployment_mode"] == "volatile_ram",
        "cleanup_errors": cleanup_errors,
        "error": None if failure is None else f"{type(failure).__name__}: {failure}",
    }
    identity = monitor_v1.probe_v1._write_new_private(args.output, receipt)
    if not qualified:
        reason = receipt["error"] or "live evidence did not satisfy the frozen M4 policy"
        raise ProbeError(f"M4 campaign did not qualify after writing {identity['path']}: {reason}")
    return {
        "verdict": "PASS_M4_LIVE_LNB_PSS_ACQUISITION_ONLY",
        "hardware_accessed": True,
        "persistent_write": False,
        "pss_detected": True,
        "sss_detected": False,
        "frame_lock_claim": False,
        "recovery_required": plan["deployment_mode"] == "volatile_ram",
        "receipt": identity,
    }


RECEIPT_FIELDS = {
    "schema",
    "schema_version",
    "receipt_id",
    "started_at",
    "completed_at",
    "outcome",
    "plan",
    "serial",
    "runtime_target",
    "expected_firmware",
    "hardware_accessed",
    "persistent_write",
    "do_not_merge",
    "claim_scope",
    "route_readback",
    "radio_and_physical_lan_locks_acquired",
    "runtime_before",
    "runtime_after",
    "iio_before",
    "iio_selected",
    "rail_probe",
    "roles",
    "role_monitors",
    "controller_snapshot_before",
    "controller_info_after",
    "controller_binary_removed",
    "iio_restored",
    "iio_context_close_verified",
    "evaluation",
    "live_pss_acquired",
    "timing_trajectory_qualified",
    "off_slice_control_rejected",
    "pss_detected",
    "sss_detected",
    "frame_lock_claim",
    "recovery_required",
    "cleanup_errors",
    "error",
}


def _validate_runtime_identity(
    value: Any, plan: dict[str, Any], *, label: str
) -> None:
    expected = {
        "boot_id",
        "firmware_version",
        "qspi_partition",
        "qspi_mtd_name",
        "qspi_bytes",
        "qspi_sha256",
        "uboot_attr_name_present",
        "uboot_attr_name",
        "uboot_attr_val_present",
        "uboot_attr_val",
        "uboot_compatible",
        "uboot_mode",
        "root_marker_present",
        "rx_dma_dt_state",
        "dds_dt_state",
        "tx_dma_dt_state",
        "tandem_dt_state",
    }
    if (
        not isinstance(value, dict)
        or set(value) != expected
        or value.get("boot_id") != plan["expected_boot_id"]
        or value.get("firmware_version") != plan["expected_firmware"]
        or value.get("qspi_partition") != "/dev/mtdblock3"
        or value.get("qspi_mtd_name") != "qspi-linux"
        or not isinstance(value.get("qspi_bytes"), str)
        or not value["qspi_bytes"].isdigit()
        or int(value["qspi_bytes"]) <= 0
        or value.get("qspi_sha256") != plan["expected_qspi_sha256"]
        or value.get("uboot_attr_name_present") != "1"
        or value.get("uboot_attr_name") != "compatible"
        or value.get("uboot_attr_val_present") != "1"
        or value.get("uboot_attr_val") != "ad9361"
        or value.get("uboot_compatible") != "ad9361"
        or value.get("uboot_mode") != "1r1t"
        or value.get("root_marker_present") != "1"
        or value.get("rx_dma_dt_state") != "enabled"
        or value.get("dds_dt_state") != "disabled"
        or value.get("tx_dma_dt_state") != "disabled"
        or value.get("tandem_dt_state") != "disabled"
    ):
        raise ProbeError(f"M4 {label} runtime identity is invalid")


def _validate_rail_probe(value: Any, plan: dict[str, Any]) -> None:
    required = {
        "sample_count",
        "component_count",
        "bytes",
        "sha256",
        "minimum_component",
        "maximum_component",
        "maximum_absolute_component",
        "rms_component",
        "rail_count",
        "near_rail_count",
        "rail_fraction",
        "payload_retained",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ProbeError("M4 rail probe fields differ from v1")
    sample_count = plan["rail_probe_samples"]
    component_count = sample_count * 2
    rail_count = value.get("rail_count")
    near_count = value.get("near_rail_count")
    rail_fraction = value.get("rail_fraction")
    rms = value.get("rms_component")
    if (
        value.get("sample_count") != sample_count
        or value.get("component_count") != component_count
        or value.get("bytes") != sample_count * 4
        or not isinstance(value.get("sha256"), str)
        or HEX_64.fullmatch(value["sha256"]) is None
        or not isinstance(value.get("minimum_component"), int)
        or not -2_048 <= value["minimum_component"] <= 2_047
        or not isinstance(value.get("maximum_component"), int)
        or not -2_048 <= value["maximum_component"] <= 2_047
        or value["maximum_component"] < value["minimum_component"]
        or value.get("maximum_absolute_component")
        != max(abs(value["minimum_component"]), abs(value["maximum_component"]))
        or not isinstance(rms, (int, float))
        or isinstance(rms, bool)
        or not math.isfinite(rms)
        or not 0 <= rms <= 2_048
        or not isinstance(rail_count, int)
        or isinstance(rail_count, bool)
        or not 0 <= rail_count <= component_count
        or not isinstance(near_count, int)
        or isinstance(near_count, bool)
        or not rail_count <= near_count <= component_count
        or not isinstance(rail_fraction, (int, float))
        or isinstance(rail_fraction, bool)
        or not math.isfinite(rail_fraction)
        or rail_fraction != rail_count / component_count
        or value.get("payload_retained") is not False
    ):
        raise ProbeError("M4 rail probe values violate v1")


def _validate_settings(receipt: dict[str, Any], plan: dict[str, Any]) -> None:
    before = receipt.get("iio_before")
    selected = receipt.get("iio_selected")
    restored = receipt.get("iio_restored")
    base_fields = {
        "phy_rx_sampling_frequency_hz",
        "capture_i_sampling_frequency_hz",
        "rf_bandwidth_hz",
        "rx_port_select",
        "gain_mode",
        "hardwaregain_db",
        "rx_lo_hz",
        "rx_lo_powerdown",
    }
    if (
        not isinstance(before, dict)
        or set(before) != base_fields
        or not isinstance(selected, dict)
        or set(selected)
        != base_fields
        | {"capture_rates_available_hz", "adc_gp_control", "fpga_decimation_factor"}
        or not isinstance(restored, dict)
        or set(restored) != base_fields
    ):
        raise ProbeError("M4 IIO setting snapshots differ from v1")
    if (
        selected["phy_rx_sampling_frequency_hz"] != SAMPLE_RATE_HZ
        or selected["capture_i_sampling_frequency_hz"] != SAMPLE_RATE_HZ
        or selected["rf_bandwidth_hz"] != RF_BANDWIDTH_HZ
        or selected["rx_port_select"] != plan["rx_port_select"]
        or selected["gain_mode"] != plan["gain_mode"]
        or selected["rx_lo_hz"] != plan["nominal_on_if_hz"]
        or selected["rx_lo_powerdown"] != 0
        or selected["capture_rates_available_hz"] != [15_000_000, 1_875_000]
        or selected["adc_gp_control"] & 1
        or selected["fpga_decimation_factor"] != 1
    ):
        raise ProbeError("M4 selected IIO settings violate the plan")
    exact = base_fields - {"hardwaregain_db"}
    if any(restored[key] != before[key] for key in exact):
        raise ProbeError("M4 final IIO settings differ from the initial snapshot")
    if before["gain_mode"] == "manual" and abs(
        restored["hardwaregain_db"] - before["hardwaregain_db"]
    ) > 0.1:
        raise ProbeError("M4 final manual gain differs from the initial snapshot")
    for snapshot in (before, selected, restored):
        if (
            snapshot["gain_mode"] not in {"manual", "fast_attack", "slow_attack", "hybrid"}
            or not isinstance(snapshot["hardwaregain_db"], (int, float))
            or isinstance(snapshot["hardwaregain_db"], bool)
            or not math.isfinite(snapshot["hardwaregain_db"])
        ):
            raise ProbeError("M4 IIO snapshot contains invalid gain telemetry")


def _validate_passing_receipt(
    receipt: dict[str, Any], plan: dict[str, Any]
) -> dict[str, Any]:
    if receipt.get("outcome") != "pass":
        raise ProbeError("M4 receipt did not qualify")
    _validate_runtime_identity(receipt.get("runtime_before"), plan, label="pre-campaign")
    _validate_runtime_identity(receipt.get("runtime_after"), plan, label="post-campaign")
    if receipt["runtime_after"] != receipt["runtime_before"]:
        raise ProbeError("M4 runtime identity changed during the campaign")
    route = receipt.get("route_readback")
    if route != {
        "destination": plan["ethernet_host"],
        "interface": plan["host_network_interface"],
        "source": route.get("source") if isinstance(route, dict) else None,
    }:
        raise ProbeError("M4 route receipt differs from the sealed endpoint")
    try:
        source = ipaddress.ip_address(route["source"])
    except (KeyError, TypeError, ValueError) as error:
        raise ProbeError("M4 route receipt source is invalid") from error
    if source.version != 4 or not source.is_private:
        raise ProbeError("M4 route receipt source is not private IPv4")
    _validate_settings(receipt, plan)
    _validate_rail_probe(receipt.get("rail_probe"), plan)
    snapshot = receipt.get("controller_snapshot_before")
    if not isinstance(snapshot, dict):
        raise ProbeError("M4 receipt lacks its FPGA preflight snapshot")
    _validate_preflight_snapshot(snapshot, plan)
    roles = receipt.get("roles")
    if not isinstance(roles, dict) or list(roles) != list(ROLES):
        raise ProbeError("M4 role evidence inventory differs from the plan")
    timeline: list[datetime] = []
    role_monitors = receipt.get("role_monitors")
    if not isinstance(role_monitors, dict) or list(role_monitors) != list(ROLES):
        raise ProbeError("M4 continuous role-monitor inventory differs from the plan")
    previous_accepted_score = 0
    for role in ROLES:
        monitor = role_monitors[role]
        if not isinstance(monitor, dict) or set(monitor) != {
            "monitor_records",
            "monitor_stderr",
        }:
            raise ProbeError(f"M4 {role} continuous monitor evidence is invalid")
        records = monitor.get("monitor_records")
        if (
            not isinstance(records, list)
            or not isinstance(monitor.get("monitor_stderr"), str)
        ):
            raise ProbeError(f"M4 {role} continuous monitor payload is invalid")
        monitor_v2._validate_monitor_records(
            records,
            {"serial": plan["serial"], "duration_ms": plan["role_monitor_duration_ms"]},
        )
        summary = records[-1]
        if role == ROLES[0]:
            _validate_counter_headroom(records, plan)
            if summary["accepted_scores_before"] != snapshot["accepted_scores"]:
                raise ProbeError("M4 FPGA counter changed between preflight and campaign")
        elif summary["accepted_scores_before"] < previous_accepted_score:
            raise ProbeError("M4 accepted-score counter is not monotonic across roles")
        previous_accepted_score = summary["accepted_scores_at_cutoff"]
        points = roles[role]
        if not isinstance(points, list) or len(points) != len(OFFSET_ORDER_HZ):
            raise ProbeError(f"M4 {role} evidence has the wrong point count")
        for ordinal, point in enumerate(points, 1):
            if not isinstance(point, dict):
                raise ProbeError(f"M4 {role} point {ordinal} is not an object")
            _verify_point(point, plan, role, ordinal)
            timeline.extend(
                (
                    _parse_time(point["started_at"], label=f"{role} point start"),
                    _parse_time(point["completed_at"], label=f"{role} point completion"),
                )
            )
    if any(right < left for left, right in itertools.pairwise(timeline)):
        raise ProbeError("M4 scan-point evidence is not chronological")
    evaluation = _evaluate_receipt(plan, receipt)
    if not evaluation["qualified"] or receipt.get("evaluation") != evaluation:
        raise ProbeError("M4 receipt differs from recomputed qualification evidence")
    info = receipt.get("controller_info_after")
    try:
        status = int(str(info.get("status", "")), 0)
    except (AttributeError, ValueError) as error:
        raise ProbeError("M4 final controller info status is invalid") from error
    if (
        not isinstance(info, dict)
        or info.get("schema") != "starlink-pss-acqctl.info.v1"
        or info.get("serial") != plan["serial"]
        or info.get("input_rate_msps") != 15
        or status & 0x2
        or receipt.get("radio_and_physical_lan_locks_acquired") is not True
        or receipt.get("controller_binary_removed") is not True
        or receipt.get("iio_context_close_verified") is not True
        or receipt.get("live_pss_acquired") is not True
        or receipt.get("timing_trajectory_qualified") is not True
        or receipt.get("off_slice_control_rejected") is not True
        or receipt.get("pss_detected") is not True
        or receipt.get("sss_detected") is not False
        or receipt.get("frame_lock_claim") is not False
        or receipt.get("recovery_required")
        is not (plan["deployment_mode"] == "volatile_ram")
        or receipt.get("cleanup_errors") != []
        or receipt.get("error") is not None
    ):
        raise ProbeError("M4 passing receipt lacks cleanup, safety, or claim proof")
    return evaluation


def verify_receipt(args: Any) -> dict[str, Any]:
    plan_path = args.plan.absolute()
    plan = _load(plan_path, label="M4 live plan")
    _validate_plan(plan)
    _verify_inputs(plan)
    if args.receipt.absolute() != Path(plan["receipt_path"]):
        raise ProbeError("M4 receipt path differs from the sealed plan")
    receipt = _load(args.receipt.absolute(), label="M4 live receipt")
    receipt_id = receipt.get("receipt_id")
    if (
        set(receipt) != RECEIPT_FIELDS
        or receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("schema_version") != 4
        or not isinstance(receipt_id, str)
        or HEX_32.fullmatch(receipt_id) is None
        or receipt.get("plan") != _identity(plan_path, label="M4 live plan")
        or receipt.get("serial") != plan["serial"]
        or receipt.get("runtime_target") != plan["runtime_target"]
        or receipt.get("expected_firmware") != plan["expected_firmware"]
        or receipt.get("hardware_accessed") is not True
        or receipt.get("persistent_write") is not False
        or receipt.get("do_not_merge") is not True
        or receipt.get("claim_scope") != CLAIM_SCOPE
        or receipt.get("outcome") not in {"pass", "unqualified", "failed"}
    ):
        raise ProbeError("M4 receipt violates its sealed plan")
    started = _parse_time(receipt.get("started_at"), label="receipt started_at")
    completed = _parse_time(receipt.get("completed_at"), label="receipt completed_at")
    if completed < started:
        raise ProbeError("M4 receipt timestamps are reversed")
    if receipt["outcome"] == "pass":
        evaluation = _validate_passing_receipt(receipt, plan)
        return {
            "verdict": "PASS_M4_LIVE_LNB_PSS_ACQUISITION_ONLY",
            "outcome": "pass",
            "pss_detected": True,
            "sss_detected": False,
            "frame_lock_claim": False,
            "recovery_required": plan["deployment_mode"] == "volatile_ram",
            "positive_to_control_median_ratio": evaluation[
                "positive_to_control_median_ratio"
            ],
            "receipt_sha256": hashlib.sha256(args.receipt.read_bytes()).hexdigest(),
        }
    if receipt.get("pss_detected") is not False or receipt.get("frame_lock_claim") is not False:
        raise ProbeError("non-passing M4 receipt makes a positive synchronization claim")
    return {
        "verdict": "PASS_M4_RECEIPT_STRUCTURE_ONLY",
        "outcome": receipt["outcome"],
        "pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
        "recovery_required": plan["deployment_mode"] == "volatile_ram",
        "receipt_sha256": hashlib.sha256(args.receipt.read_bytes()).hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "fixture":
            result = build_fixture(arguments)
        elif arguments.command == "plan":
            result = build_plan(arguments)
        elif arguments.command == "execute":
            result = execute_plan(arguments)
        else:
            result = verify_receipt(arguments)
    except (OSError, ValueError, ProbeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
