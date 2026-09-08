#!/usr/bin/env python3
"""Run and replay a scanned native-IIO live PSS acquisition campaign.

Each positive/control/positive role scans the same 25 interleaved LO offsets.
Every point discards ten complete maps after retuning, then retains exactly 34
maps to form 32 trajectory windows.  One FPGA map stream remains open across
all 75 points.  This is a coarse PSS acquisition claim only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PPU = Path("/home/mouse9911/gits/pluto-plus-utils")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(PPU / "src") not in sys.path:
    sys.path.insert(0, str(PPU / "src"))

from pluto_plus.hardware.pss_iio import PSS_MAP_CHUNKS, PSS_MAP_SCAN_BYTES, PssIioClient
from pluto_plus.radio_lock import acquire_radio_lock

import scripts.starlink_pss_native_iio_live_campaign_v2 as v2
from scripts.starlink_pss_iio_cabled_v1 import (
    RATE_PROFILES,
    RX_SERIAL,
    QualificationError,
    RateProfile,
    _configure_rx,
    _now,
    _number,
    _required_channel,
    _restore_rx,
    _write_number,
)
from scripts.starlink_pss_native_iio_qualify_v1 import (
    FRAME_SAMPLES,
    MAP_CHUNKS,
    MAP_SCAN_BYTES,
    MAP_SPAN,
    POLICY,
    _identity,
    _integer,
    _load,
    _validate_compact_map,
    _validate_window,
    _write_new,
    trajectory_metrics,
)
from scripts.starlink_pss_native_iio_qualify_v1 import (
    _number as _validated_number,
)

RUN_SCHEMA = "plutosdr-fw.starlink-pss-native-iio-live-scan-run.v3"
ANALYSIS_SCHEMA = "plutosdr-fw.starlink-pss-native-iio-live-scan-analysis.v3"
ROLES = ("on_channel_a", "below_band_control", "on_channel_b")
OFFSET_ORDER_HZ = tuple(
    value
    for magnitude in range(0, 1_200_001, 100_000)
    for value in ((0,) if magnitude == 0 else (magnitude, -magnitude))
)
POINT_WINDOW_COUNT = 32
POINT_MAP_COUNT = POINT_WINDOW_COUNT + 2
RETUNE_DISCARD_MAPS = 10
RETUNE_SETTLE_SECONDS = 0.2
MAXIMUM_ROLE_SECONDS = 120.0
MINIMUM_PASSING_POINTS_PER_POSITIVE_ROLE = 1
MAXIMUM_PASSING_POINTS_IN_CONTROL_ROLE = 0
CONTROL_SCAN_UPPER_RF_HZ = (
    v2.CONTROL_RF_HZ + max(OFFSET_ORDER_HZ) + v2.RX_BANDWIDTH_HZ // 2
)
CONTROL_SCAN_CLEARANCE_HZ = v2.STARLINK_LOWER_RF_HZ - CONTROL_SCAN_UPPER_RF_HZ
MAPS_PER_POINT = RETUNE_DISCARD_MAPS + POINT_MAP_COUNT
EXPECTED_TOTAL_MAPS = len(ROLES) * len(OFFSET_ORDER_HZ) * MAPS_PER_POINT

RUN_FIELDS = {
    "schema",
    "schema_version",
    "started_at",
    "completed_at",
    "outcome",
    "persistent_write",
    "transmitter_opened",
    "serial",
    "rate_msps",
    "sample_rate_hz",
    "role_order",
    "geometry",
    "firmware_source_commit",
    "ppu_source_commit",
    "deployment",
    "coefficient",
    "receiver",
    "roles",
    "stream",
    "gates",
    "evaluation",
    "cleanup",
    "pss_detected",
    "sss_detected",
    "frame_lock_claim",
}
ROLE_FIELDS = {
    "role",
    "base_if_hz",
    "started_at",
    "completed_at",
    "elapsed_seconds",
    "points",
    "analysis",
}
STREAM_FIELDS = {
    "complete_maps",
    "logical_map_bytes",
    "transport_bytes",
    "map_digest_sha256",
    "counters",
}
COUNTER_FIELDS = {
    "maps_delivered",
    "chunks_delivered",
    "map_buffer_push_failures",
    "map_fault_flags",
    "tracker_buffer_push_failures",
    "tracker_packet_validation_failures",
    "tracker_fault_flags",
}
GATE_FIELDS = {
    "active_coefficient_exact",
    "single_map_epoch_exact",
    "driver_map_count_exact",
    "driver_chunk_count_exact",
    "map_push_failure_free",
    "map_fault_free",
    "tracker_push_failure_free",
    "tracker_validation_failure_free",
    "tracker_fault_free",
}
RADIO_STATE_FIELDS = {
    "phy_rate",
    "adc_rate",
    "bandwidth",
    "gain_mode",
    "lo",
    "lo_powerdown",
}
IDENTITY_FIELDS = {"path", "bytes", "sha256"}
DEPLOYMENT_FIELDS = {
    "receipt",
    "boot_id",
    "qspi_sha256",
    "known_hosts",
    "reboots",
    "current_boot_id",
}


def _scan_geometry(on_if_hz: int) -> dict[str, Any]:
    geometry: dict[str, Any] = v2._validate_frequency_plan(on_if_hz)
    if CONTROL_SCAN_CLEARANCE_HZ <= 0:
        raise ValueError("below-band control scan reaches the Starlink boundary")
    geometry.update(
        {
            "scan_offsets_hz": list(OFFSET_ORDER_HZ),
            "scan_point_count": len(OFFSET_ORDER_HZ),
            "scan_offset_step_hz": 100_000,
            "scan_offset_limit_hz": 1_200_000,
            "control_scan_upper_rf_hz": CONTROL_SCAN_UPPER_RF_HZ,
            "control_scan_clearance_hz": CONTROL_SCAN_CLEARANCE_HZ,
            "point_window_count": POINT_WINDOW_COUNT,
            "point_map_count": POINT_MAP_COUNT,
            "post_retune_discard_maps": RETUNE_DISCARD_MAPS,
        }
    )
    return geometry


def _point_rank(point: dict[str, Any]) -> tuple[float, int, float, int]:
    metrics = point["metrics"]
    return (
        metrics["pass_fraction"],
        metrics["longest_consecutive_track_windows"],
        metrics["median_peak_to_median"],
        -abs(point["offset_hz"]),
    )


def analyze_role(role: str, points: list[dict[str, Any]]) -> dict[str, Any]:
    if role not in ROLES or len(points) != len(OFFSET_ORDER_HZ):
        raise QualificationError("scanned role inventory differs")
    if any(
        not isinstance(point, dict) or not isinstance(point.get("metrics"), dict)
        for point in points
    ):
        raise QualificationError("scanned role point structure differs")
    if [point.get("offset_hz") for point in points] != list(OFFSET_ORDER_HZ):
        raise QualificationError("scanned role offset order differs")
    passing = [
        point
        for point in points
        if point["metrics"].get("classification") == "positive_track"
    ]
    best = max(points, key=_point_rank)
    return {
        "role": role,
        "point_count": len(points),
        "passing_point_count": len(passing),
        "passing_offsets_hz": [point["offset_hz"] for point in passing],
        "best_offset_hz": best["offset_hz"],
        "best_requested_lo_hz": best["requested_lo_hz"],
        "best_metrics": best["metrics"],
    }


def campaign_evaluation(roles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if set(roles) != set(ROLES):
        raise QualificationError("scanned campaign role inventory differs")
    analyses = {role: analyze_role(role, roles[role]["points"]) for role in ROLES}
    positive_a = analyses["on_channel_a"]
    control = analyses["below_band_control"]
    positive_b = analyses["on_channel_b"]
    contrast = min(
        positive_a["best_metrics"]["median_peak_to_median"],
        positive_b["best_metrics"]["median_peak_to_median"],
    ) / max(control["best_metrics"]["median_peak_to_median"], sys.float_info.min)
    gates = {
        "positive_a_has_passing_point": positive_a["passing_point_count"]
        >= MINIMUM_PASSING_POINTS_PER_POSITIVE_ROLE,
        "below_band_control_has_no_passing_points": control["passing_point_count"]
        <= MAXIMUM_PASSING_POINTS_IN_CONTROL_ROLE,
        "positive_b_has_passing_point": positive_b["passing_point_count"]
        >= MINIMUM_PASSING_POINTS_PER_POSITIVE_ROLE,
        "positive_to_control_contrast_met": contrast
        >= POLICY["minimum_positive_to_negative_median_ratio"],
    }
    return {
        "qualified": all(gates.values()),
        "gates": gates,
        "positive_to_control_median_ratio": contrast,
        "role_analyses": analyses,
    }


def _capture_point(
    client: PssIioClient,
    stream: v2.ContinuousMapStream,
    *,
    role: str,
    ordinal: int,
    base_if_hz: int,
    offset_hz: int,
) -> dict[str, Any]:
    phy = client.context.find_device("ad9361-phy")
    if phy is None:
        raise QualificationError("AD9361 PHY disappeared during the live scan")
    rx_lo = _required_channel(phy, "altvoltage0", True)
    requested = base_if_hz + offset_hz
    started_at = _now()
    readback = _write_number(rx_lo, "frequency", requested, 2)
    time.sleep(RETUNE_SETTLE_SECONDS)
    discarded = [stream.read_one()[1] for _ in range(RETUNE_DISCARD_MAPS)]
    retained: deque[Any] = deque(maxlen=3)
    windows: list[dict[str, Any]] = []
    first_maps: list[dict[str, int]] = []
    last_maps: deque[dict[str, int]] = deque(maxlen=8)
    started = time.monotonic()
    for _ in range(POINT_MAP_COUNT):
        phase_map, compact = stream.read_one()
        if len(first_maps) < 8:
            first_maps.append(compact)
        last_maps.append(compact)
        retained.append(phase_map)
        if len(retained) == 3:
            windows.append(
                asdict(
                    v2.analyze_phase_maps(tuple(retained), rate_msps=stream.rate_msps)
                )
            )
    if len(windows) != POINT_WINDOW_COUNT:
        raise QualificationError(
            "scan point did not produce exactly 32 trajectory windows"
        )
    return {
        "role": role,
        "ordinal": ordinal,
        "offset_hz": offset_hz,
        "base_if_hz": base_if_hz,
        "requested_lo_hz": requested,
        "readback_lo_hz": readback,
        "started_at": started_at,
        "completed_at": _now(),
        "retained_elapsed_seconds": time.monotonic() - started,
        "settle_seconds": RETUNE_SETTLE_SECONDS,
        "discarded_map_count": len(discarded),
        "discarded_maps": discarded,
        "complete_maps": POINT_MAP_COUNT,
        "coarse_window_count": len(windows),
        "coarse_windows": windows,
        "first_maps": first_maps,
        "last_maps": list(last_maps),
        "metrics": trajectory_metrics(windows),
    }


def _capture_role(
    client: PssIioClient,
    stream: v2.ContinuousMapStream,
    *,
    role: str,
    base_if_hz: int,
) -> dict[str, Any]:
    started_at = _now()
    started = time.monotonic()
    points = [
        _capture_point(
            client,
            stream,
            role=role,
            ordinal=ordinal,
            base_if_hz=base_if_hz,
            offset_hz=offset_hz,
        )
        for ordinal, offset_hz in enumerate(OFFSET_ORDER_HZ, 1)
    ]
    elapsed = time.monotonic() - started
    if elapsed > MAXIMUM_ROLE_SECONDS:
        raise QualificationError("scanned role exceeded its 120-second bound")
    return {
        "role": role,
        "base_if_hz": base_if_hz,
        "started_at": started_at,
        "completed_at": _now(),
        "elapsed_seconds": elapsed,
        "points": points,
        "analysis": analyze_role(role, points),
    }


def run(
    output: Path,
    *,
    profile: RateProfile,
    on_if_hz: int,
    deployment_receipt: Path,
    known_hosts_file: Path,
    reboot_receipts: list[Path],
    firmware_source_commit: str,
    ppu_source_commit: str,
) -> dict[str, Any]:
    geometry = _scan_geometry(on_if_hz)
    firmware_source_commit = v2._validate_source_commit(
        firmware_source_commit, label="firmware source commit"
    )
    ppu_source_commit = v2._validate_source_commit(
        ppu_source_commit, label="PPU source commit"
    )
    v2._verify_source_checkout(
        ROOT,
        firmware_source_commit,
        label="firmware source",
        expected_origin_suffix="/misko/plutosdr-fw",
    )
    v2._verify_source_checkout(
        PPU,
        ppu_source_commit,
        label="PPU source",
        expected_origin_suffix="/misko/pluto-plus-utils",
    )
    deployment = v2._deployment_binding(
        deployment_receipt,
        known_hosts_file,
        rate_msps=profile.rate_msps,
        reboot_receipts=reboot_receipts,
    )
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if v2._sha256(profile.coefficient_path) != profile.coefficient_sha256:
        raise QualificationError("coefficient file identity differs")
    receipt: dict[str, Any] = {
        "schema": RUN_SCHEMA,
        "schema_version": 3,
        "started_at": _now(),
        "outcome": "started",
        "persistent_write": False,
        "transmitter_opened": False,
        "serial": RX_SERIAL,
        "rate_msps": profile.rate_msps,
        "sample_rate_hz": profile.rate_hz,
        "role_order": list(ROLES),
        "geometry": geometry,
        "firmware_source_commit": firmware_source_commit,
        "ppu_source_commit": ppu_source_commit,
        "deployment": deployment,
        "coefficient": {
            "path": str(profile.coefficient_path.resolve()),
            "sha256": profile.coefficient_sha256,
            "generation": profile.coefficient_generation,
        },
        "receiver": {"transport": "ethernet", "uri": v2.ETHERNET_URI},
        "roles": {},
        "cleanup": {"errors": []},
        "pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
    }
    client: PssIioClient | None = None
    before: dict[str, Any] | None = None
    stream: v2.ContinuousMapStream | None = None
    body_error: BaseException | None = None
    lock_stack = ExitStack()
    try:
        lock_stack.enter_context(acquire_radio_lock(RX_SERIAL))
        client = PssIioClient.connect(v2.ETHERNET_URI, expected_serial=RX_SERIAL)
        before, selected = _configure_rx(client, profile, lo_hz=on_if_hz)
        receipt["receiver"].update(
            {"firmware": profile.firmware, "original": before, "selected": selected}
        )
        client.load_coefficient_file(
            profile.coefficient_path, generation=profile.coefficient_generation
        )
        active_generation = _number(client.tracker, "active_coefficient_generation")
        stream = v2.ContinuousMapStream(client, rate_msps=profile.rate_msps)
        client.open_maps(refill_chunks=PSS_MAP_CHUNKS)
        base_by_role = {
            "on_channel_a": on_if_hz,
            "below_band_control": v2.CONTROL_IF_HZ,
            "on_channel_b": on_if_hz,
        }
        for role in ROLES:
            receipt["roles"][role] = _capture_role(
                client, stream, role=role, base_if_hz=base_by_role[role]
            )
        counters = v2._driver_counters(client)
        client.close_maps()
        evaluation = campaign_evaluation(receipt["roles"])
        gates = {
            "active_coefficient_exact": active_generation
            == profile.coefficient_generation,
            "single_map_epoch_exact": stream.count == EXPECTED_TOTAL_MAPS,
            "driver_map_count_exact": counters["maps_delivered"] == stream.count,
            "driver_chunk_count_exact": counters["chunks_delivered"]
            == stream.count * PSS_MAP_CHUNKS,
            "map_push_failure_free": counters["map_buffer_push_failures"] == 0,
            "map_fault_free": counters["map_fault_flags"] == 0,
            "tracker_push_failure_free": counters["tracker_buffer_push_failures"] == 0,
            "tracker_validation_failure_free": counters[
                "tracker_packet_validation_failures"
            ]
            == 0,
            "tracker_fault_free": counters["tracker_fault_flags"] == 0,
        }
        receipt["stream"] = {
            "complete_maps": stream.count,
            "logical_map_bytes": stream.count * FRAME_SAMPLES * 2,
            "transport_bytes": stream.count * PSS_MAP_CHUNKS * PSS_MAP_SCAN_BYTES,
            "map_digest_sha256": stream.digest.hexdigest(),
            "counters": counters,
        }
        receipt["gates"] = gates
        receipt["evaluation"] = evaluation
        failed = [name for name, passed in gates.items() if not passed]
        if failed:
            raise QualificationError(f"native live scan gates failed: {failed}")
        receipt["pss_detected"] = evaluation["qualified"]
        receipt["outcome"] = "pass"
    except BaseException as error:  # noqa: BLE001
        body_error = error
        receipt["outcome"] = "failed"
        receipt["pss_detected"] = False
        receipt["error"] = f"{type(error).__name__}: {error}"
    finally:
        cleanup_errors: list[str] = receipt["cleanup"]["errors"]
        if client is not None:
            try:
                client.close_maps()
            except BaseException as error:  # noqa: BLE001
                cleanup_errors.append(f"RX map close: {error}")
            if before is not None:
                try:
                    receipt["cleanup"]["rx_restored"] = _restore_rx(client, before)
                except BaseException as error:  # noqa: BLE001
                    cleanup_errors.append(f"RX restore: {error}")
            try:
                client.close()
            except BaseException as error:  # noqa: BLE001
                cleanup_errors.append(f"RX context close: {error}")
        try:
            lock_stack.close()
        except BaseException as error:  # noqa: BLE001
            cleanup_errors.append(f"RX lock release: {error}")
        receipt["cleanup"]["verified"] = not cleanup_errors
        if cleanup_errors:
            receipt["outcome"] = "failed"
            receipt["pss_detected"] = False
        receipt["completed_at"] = _now()
        receipt_path = output / "campaign-receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        receipt["receipt"] = str(receipt_path)
    if body_error is not None:
        raise body_error
    if receipt["outcome"] != "pass":
        raise QualificationError("native live scan cleanup did not verify")
    return receipt


POINT_FIELDS = {
    "role",
    "ordinal",
    "offset_hz",
    "base_if_hz",
    "requested_lo_hz",
    "readback_lo_hz",
    "started_at",
    "completed_at",
    "retained_elapsed_seconds",
    "settle_seconds",
    "discarded_map_count",
    "discarded_maps",
    "complete_maps",
    "coarse_window_count",
    "coarse_windows",
    "first_maps",
    "last_maps",
    "metrics",
}


def _validate_point(
    point: dict[str, Any],
    *,
    role: str,
    ordinal: int,
    base_if_hz: int,
    rate_msps: int,
    previous_generation: int | None,
    previous_start: int | None,
) -> tuple[int, int]:
    if not isinstance(point, dict):
        raise QualificationError(f"{role} scan point {ordinal} is not an object")
    offset_hz = OFFSET_ORDER_HZ[ordinal - 1]
    discarded = point.get("discarded_maps")
    windows = point.get("coarse_windows")
    first_maps = point.get("first_maps")
    last_maps = point.get("last_maps")
    if (
        set(point) != POINT_FIELDS
        or point.get("role") != role
        or point.get("ordinal") != ordinal
        or point.get("offset_hz") != offset_hz
        or point.get("base_if_hz") != base_if_hz
        or point.get("requested_lo_hz") != base_if_hz + offset_hz
        or abs(
            _integer(point.get("readback_lo_hz"), label="point LO")
            - (base_if_hz + offset_hz)
        )
        > 2
        or point.get("settle_seconds") != RETUNE_SETTLE_SECONDS
        or point.get("discarded_map_count") != RETUNE_DISCARD_MAPS
        or not isinstance(discarded, list)
        or len(discarded) != RETUNE_DISCARD_MAPS
        or any(not isinstance(record, dict) for record in discarded)
        or point.get("complete_maps") != POINT_MAP_COUNT
        or point.get("coarse_window_count") != POINT_WINDOW_COUNT
        or not isinstance(windows, list)
        or len(windows) != POINT_WINDOW_COUNT
        or not isinstance(first_maps, list)
        or len(first_maps) != 8
        or not isinstance(last_maps, list)
        or len(last_maps) != 8
        or _validated_number(
            point.get("retained_elapsed_seconds"), label="point elapsed", minimum=0.0
        )
        <= 0
    ):
        raise QualificationError(f"{role} scan point {ordinal} violates its contract")
    first_discard_generation = _integer(
        discarded[0].get("generation"), label="discard generation"
    )
    first_discard_start = _integer(
        discarded[0].get("canonical_start_index"), label="discard start"
    )
    if previous_generation is not None and (
        first_discard_generation != previous_generation + 1
        or first_discard_start != previous_start + MAP_SPAN
    ):
        raise QualificationError("map continuity breaks before a scan point")
    for index, record in enumerate(discarded):
        _validate_compact_map(
            record,
            generation=first_discard_generation + index,
            start=first_discard_start + index * MAP_SPAN,
            rate_msps=rate_msps,
        )
    first_generation = first_discard_generation + RETUNE_DISCARD_MAPS
    first_start = first_discard_start + RETUNE_DISCARD_MAPS * MAP_SPAN
    for index, window in enumerate(windows):
        _validate_window(
            window,
            ordinal=index,
            first_generation=first_generation,
            first_start=first_start,
            rate_msps=rate_msps,
        )
    _validate_compact_map(
        first_maps[0],
        generation=first_generation,
        start=first_start,
        rate_msps=rate_msps,
    )
    last_generation = first_generation + POINT_MAP_COUNT - 1
    last_start = first_start + (POINT_MAP_COUNT - 1) * MAP_SPAN
    _validate_compact_map(
        last_maps[-1], generation=last_generation, start=last_start, rate_msps=rate_msps
    )
    if point.get("metrics") != trajectory_metrics(windows):
        raise QualificationError("scan point metrics differ from independent replay")
    return last_generation, last_start


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _valid_identity(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == IDENTITY_FIELDS
        and isinstance(value.get("path"), str)
        and Path(value["path"]).is_absolute()
        and isinstance(value.get("bytes"), int)
        and not isinstance(value.get("bytes"), bool)
        and value["bytes"] > 0
        and _valid_sha256(value.get("sha256"))
    )


def replay(*, receipt_path: Path, output: Path) -> dict[str, Any]:
    receipt = _load(receipt_path, label="native-IIO scanned campaign")
    rate_msps = _integer(receipt.get("rate_msps"), label="rate", minimum=1)
    geometry = receipt.get("geometry")
    receiver = receipt.get("receiver")
    selected = receiver.get("selected") if isinstance(receiver, dict) else None
    roles = receipt.get("roles")
    stream = receipt.get("stream")
    gates = receipt.get("gates")
    cleanup = receipt.get("cleanup")
    coefficient = receipt.get("coefficient")
    deployment = receipt.get("deployment")
    if (
        set(receipt) != RUN_FIELDS
        or receipt.get("schema") != RUN_SCHEMA
        or receipt.get("schema_version") != 3
        or receipt.get("outcome") != "pass"
        or receipt.get("persistent_write") is not False
        or receipt.get("transmitter_opened") is not False
        or receipt.get("serial") != RX_SERIAL
        or rate_msps not in v2.EXPECTED_DEPLOYMENTS
        or receipt.get("sample_rate_hz") != rate_msps * 1_000_000
        or receipt.get("role_order") != list(ROLES)
        or not isinstance(geometry, dict)
        or geometry != _scan_geometry(geometry.get("on_channel_if_hz"))
        or not isinstance(receiver, dict)
        or set(receiver) != {"transport", "uri", "firmware", "original", "selected"}
        or receiver.get("transport") != "ethernet"
        or receiver.get("uri") != v2.ETHERNET_URI
        or receiver.get("firmware") != v2.EXPECTED_DEPLOYMENTS[rate_msps]["firmware"]
        or not isinstance(selected, dict)
        or set(selected) != RADIO_STATE_FIELDS
        or not isinstance(receiver.get("original"), dict)
        or set(receiver["original"]) != RADIO_STATE_FIELDS
        or selected.get("phy_rate") != rate_msps * 1_000_000
        or selected.get("adc_rate") != rate_msps * 1_000_000
        or selected.get("bandwidth") != v2.RX_BANDWIDTH_HZ
        or selected.get("gain_mode") != "slow_attack"
        or selected.get("lo") != geometry["on_channel_if_hz"]
        or selected.get("lo_powerdown") != 0
        or not isinstance(roles, dict)
        or set(roles) != set(ROLES)
        or not isinstance(stream, dict)
        or set(stream) != STREAM_FIELDS
        or not isinstance(gates, dict)
        or set(gates) != GATE_FIELDS
        or any(value is not True for value in gates.values())
        or not isinstance(cleanup, dict)
        or cleanup.get("verified") is not True
        or cleanup.get("errors") != []
        or cleanup.get("rx_restored") != receiver.get("original")
        or not isinstance(coefficient, dict)
        or set(coefficient) != {"path", "sha256", "generation"}
        or not isinstance(coefficient.get("path"), str)
        or not Path(coefficient["path"]).is_absolute()
        or coefficient.get("sha256") != RATE_PROFILES[rate_msps].coefficient_sha256
        or coefficient.get("generation")
        != RATE_PROFILES[rate_msps].coefficient_generation
        or not isinstance(deployment, dict)
        or set(deployment) != DEPLOYMENT_FIELDS
        or not _valid_identity(deployment.get("receipt"))
        or not _valid_identity(deployment.get("known_hosts"))
        or not isinstance(deployment.get("reboots"), list)
        or any(not _valid_identity(value) for value in deployment["reboots"])
        or not isinstance(deployment.get("boot_id"), str)
        or not isinstance(deployment.get("current_boot_id"), str)
        or not _valid_sha256(deployment.get("qspi_sha256"))
    ):
        raise QualificationError(
            "native-IIO scanned campaign violates its root contract"
        )
    v2._validate_source_commit(
        receipt.get("firmware_source_commit"), label="firmware commit"
    )
    v2._validate_source_commit(receipt.get("ppu_source_commit"), label="PPU commit")
    if v2._sha256(Path(coefficient["path"])) != coefficient["sha256"]:
        raise QualificationError("campaign coefficient changed after acquisition")

    base_by_role = {
        "on_channel_a": geometry["on_channel_if_hz"],
        "below_band_control": v2.CONTROL_IF_HZ,
        "on_channel_b": geometry["on_channel_if_hz"],
    }
    previous_generation: int | None = None
    previous_start: int | None = None
    for role in ROLES:
        role_value = roles[role]
        points = role_value.get("points") if isinstance(role_value, dict) else None
        if (
            not isinstance(role_value, dict)
            or set(role_value) != ROLE_FIELDS
            or role_value.get("role") != role
            or role_value.get("base_if_hz") != base_by_role[role]
            or _validated_number(
                role_value.get("elapsed_seconds"), label="role elapsed", minimum=0.0
            )
            <= 0
            or _validated_number(
                role_value.get("elapsed_seconds"), label="role elapsed", minimum=0.0
            )
            > MAXIMUM_ROLE_SECONDS
            or not isinstance(points, list)
            or len(points) != len(OFFSET_ORDER_HZ)
        ):
            raise QualificationError(f"scanned role {role} violates its contract")
        for ordinal, point in enumerate(points, 1):
            previous_generation, previous_start = _validate_point(
                point,
                role=role,
                ordinal=ordinal,
                base_if_hz=base_by_role[role],
                rate_msps=rate_msps,
                previous_generation=previous_generation,
                previous_start=previous_start,
            )
        if role_value.get("analysis") != analyze_role(role, points):
            raise QualificationError("scanned role analysis differs from replay")

    counters = stream.get("counters")
    if (
        stream.get("complete_maps") != EXPECTED_TOTAL_MAPS
        or stream.get("logical_map_bytes") != EXPECTED_TOTAL_MAPS * FRAME_SAMPLES * 2
        or stream.get("transport_bytes")
        != EXPECTED_TOTAL_MAPS * MAP_CHUNKS * MAP_SCAN_BYTES
        or not isinstance(stream.get("map_digest_sha256"), str)
        or len(stream["map_digest_sha256"]) != 64
        or not isinstance(counters, dict)
        or set(counters) != COUNTER_FIELDS
        or counters.get("maps_delivered") != EXPECTED_TOTAL_MAPS
        or counters.get("chunks_delivered") != EXPECTED_TOTAL_MAPS * MAP_CHUNKS
        or any(
            counters.get(key) != 0
            for key in (
                "map_buffer_push_failures",
                "map_fault_flags",
                "tracker_buffer_push_failures",
                "tracker_packet_validation_failures",
                "tracker_fault_flags",
            )
        )
    ):
        raise QualificationError("scanned campaign stream accounting is invalid")
    evaluation = campaign_evaluation(roles)
    if (
        receipt.get("evaluation") != evaluation
        or receipt.get("pss_detected") is not evaluation["qualified"]
        or receipt.get("sss_detected") is not False
        or receipt.get("frame_lock_claim") is not False
    ):
        raise QualificationError("scanned campaign claims differ from replay")
    analysis = {
        "schema": ANALYSIS_SCHEMA,
        "schema_version": 3,
        "outcome": "pass",
        "hardware_accessed": False,
        "persistent_write": False,
        "source_receipt": _identity(receipt_path),
        "serial": RX_SERIAL,
        "rate_msps": rate_msps,
        "geometry": geometry,
        "role_analyses": evaluation["role_analyses"],
        "evaluation": evaluation,
        "pss_detected": evaluation["qualified"],
        "sss_detected": False,
        "frame_lock_claim": False,
    }
    identity = _write_new(output, analysis)
    return {"analysis": identity, **analysis}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    execute = commands.add_parser("run", help="run one scanned live campaign")
    execute.add_argument(
        "--rate-msps", type=int, choices=tuple(RATE_PROFILES), default=30
    )
    execute.add_argument("--on-if-hz", type=int, default=1_937_500_000)
    execute.add_argument("--deployment-receipt", type=Path, required=True)
    execute.add_argument("--known-hosts-file", type=Path, required=True)
    execute.add_argument("--reboot-receipt", type=Path, action="append", default=[])
    execute.add_argument("--firmware-source-commit", required=True)
    execute.add_argument("--ppu-source-commit", required=True)
    execute.add_argument("output", type=Path)
    verify = commands.add_parser("replay", help="independently replay one scan receipt")
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.command == "run":
            result = run(
                arguments.output,
                profile=RATE_PROFILES[arguments.rate_msps],
                on_if_hz=arguments.on_if_hz,
                deployment_receipt=arguments.deployment_receipt,
                known_hosts_file=arguments.known_hosts_file,
                reboot_receipts=arguments.reboot_receipt,
                firmware_source_commit=arguments.firmware_source_commit,
                ppu_source_commit=arguments.ppu_source_commit,
            )
        else:
            result = replay(receipt_path=arguments.receipt, output=arguments.output)
    except BaseException as error:  # noqa: BLE001
        print(json.dumps({"outcome": "failed", "error": str(error)}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "outcome": result["outcome"],
                "rate_msps": result["rate_msps"],
                "pss_detected": result["pss_detected"],
                "sss_detected": result["sss_detected"],
                "frame_lock_claim": result["frame_lock_claim"],
                "receipt": result.get("receipt"),
                "analysis": result.get("analysis"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
