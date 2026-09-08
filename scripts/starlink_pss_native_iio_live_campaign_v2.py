#!/usr/bin/env python3
"""Run and independently replay the corrected native-IIO live PSS campaign.

The one authorized Ethernet receiver is observed at the Starlink channel IF,
at a receiver-noise control whose complete passband is below the declared Ku
downlink boundary, and again at the original IF.  One map stream stays open for
all three roles.  This gate can claim coarse PSS acquisition/timing only; it
never claims fine-template selectivity, SSS, or frame lock.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
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

from pluto_plus.hardware.pss_iio import (
    PSS_MAP_CHUNKS,
    PSS_MAP_SCAN_BYTES,
    PssIioClient,
    PssMapReassembler,
    PssPhaseMap,
    analyze_phase_maps,
)
from pluto_plus.radio_lock import acquire_radio_lock

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
    _validate_campaign_role,
    _validate_compact_map,
    _write_new,
    trajectory_metrics,
)
from scripts.starlink_pss_native_iio_qualify_v1 import (
    _number as _validated_number,
)
from scripts.starlink_pss_native_iio_soak_v1 import (
    _minimum_complete_maps,
    _validate_transition,
)

RUN_SCHEMA = "plutosdr-fw.starlink-pss-native-iio-live-campaign-run.v2"
ANALYSIS_SCHEMA = "plutosdr-fw.starlink-pss-native-iio-live-campaign-analysis.v2"
ETHERNET_URI = "ip:192.168.1.17"
ROLES = ("on_channel_a", "below_band_control", "on_channel_b")
POSITIVE_ROLES = ("on_channel_a", "on_channel_b")
LNB_LO_HZ = 9_750_000_000
STARLINK_LOWER_RF_HZ = 10_700_000_000
CONTROL_RF_HZ = 10_600_000_000
CONTROL_IF_HZ = CONTROL_RF_HZ - LNB_LO_HZ
RX_BANDWIDTH_HZ = 20_000_000
RETUNE_SETTLE_SECONDS = 0.2
RETUNE_DISCARD_MAPS = 10
EXPECTED_DEPLOYMENTS = {
    30: {
        "firmware": "starlink-pss30-iio-v1-dnm",
        "profile": "starlink-pss-30m-iio-v1-dnm-persistent-promotion",
        "image_sha256": "ec00dfcbcc999f6011c980c98ffc5ee21f61172296b7865df795a7c28dd28931",
        "fit_sha256": "ca1ba8b794f9a91d8bf4674aa7121498a92758bf00453884d33b8b427fa26e95",
    },
    60: {
        "firmware": "starlink-pss-iio-v5-dnm",
        "profile": "starlink-pss-60m-iio-v5-dnm-persistent-promotion",
        "image_sha256": "7c5f5c3b8307cc49fadbe416da5f19ceb86350c0ddd9e6bd15f98cd423dd1038",
        "fit_sha256": "ee4fa9448f9b40af04abfdc4b889e4741003d6ed5298e977271d914d268f702f",
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_source_commit(value: str, *, label: str) -> str:
    if len(value) != 40 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be one full lowercase Git commit")
    return value


def _verify_source_checkout(
    repository: Path,
    commit: str,
    *,
    label: str,
    expected_origin_suffix: str,
) -> None:
    """Prove a supplied source identity against its exact clean checkout."""
    selected = repository.absolute()
    commit = _validate_source_commit(commit, label=f"{label} commit")

    def git(*arguments: str) -> str:
        try:
            completed = subprocess.run(
                ("git", "-C", str(selected), *arguments),
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (
            OSError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ) as error:
            raise QualificationError(f"{label} checkout cannot be attested") from error
        return completed.stdout.strip()

    origin = git("remote", "get-url", "origin")
    normalized_origin = origin.removesuffix(".git").replace(":", "/")
    if (
        Path(git("rev-parse", "--show-toplevel")).absolute() != selected
        or git("rev-parse", "--verify", "HEAD^{commit}") != commit
        or git("status", "--porcelain=v1", "--untracked-files=all")
        or not normalized_origin.endswith(expected_origin_suffix)
    ):
        raise QualificationError(f"{label} checkout is not the exact clean source")


def _validate_frequency_plan(on_if_hz: int) -> dict[str, int]:
    if isinstance(on_if_hz, bool) or not isinstance(on_if_hz, int):
        raise TypeError("on-channel IF must be an integer")
    if not 70_000_000 <= on_if_hz <= 6_000_000_000:
        raise ValueError("on-channel IF must lie in [70000000, 6000000000] Hz")
    control_upper_rf_hz = CONTROL_RF_HZ + RX_BANDWIDTH_HZ // 2
    if control_upper_rf_hz >= STARLINK_LOWER_RF_HZ:
        raise ValueError("below-band control passband reaches the Starlink boundary")
    return {
        "lnb_lo_hz": LNB_LO_HZ,
        "on_channel_if_hz": on_if_hz,
        "on_channel_rf_hz": LNB_LO_HZ + on_if_hz,
        "control_if_hz": CONTROL_IF_HZ,
        "control_rf_hz": CONTROL_RF_HZ,
        "control_upper_rf_hz": control_upper_rf_hz,
        "starlink_lower_rf_hz": STARLINK_LOWER_RF_HZ,
        "control_guard_hz": STARLINK_LOWER_RF_HZ - control_upper_rf_hz,
        "rx_bandwidth_hz": RX_BANDWIDTH_HZ,
    }


def _validate_deployment(path: Path, *, rate_msps: int) -> dict[str, Any]:
    receipt = _load(path, label="PPU persistent deployment receipt")
    expected = EXPECTED_DEPLOYMENTS[rate_msps]
    plan = receipt.get("plan")
    returned = receipt.get("read_only_return_attestation")
    rotation = receipt.get("host_key_rotation")
    if (
        receipt.get("schema_version") != 2
        or receipt.get("transport") != "lan_ssh_frm"
        or receipt.get("outcome") != "success"
        or receipt.get("error") is not None
        or receipt.get("returned_serial") != RX_SERIAL
        or receipt.get("returned_phy") != "ad9361"
        or receipt.get("returned_firmware") != expected["firmware"]
        or not isinstance(plan, dict)
        or plan.get("host") != "192.168.1.17"
        or plan.get("target_serial") != RX_SERIAL
        or plan.get("expected_firmware") != expected["firmware"]
        or plan.get("mutation_profile_id") != expected["profile"]
        or plan.get("image_sha256") != expected["image_sha256"]
        or plan.get("fit_sha256") != expected["fit_sha256"]
        or plan.get("expected_metadata_abi") != 3
        or plan.get("expected_tandem_agc") is not False
        or plan.get("return_iio_layout") != "detector-only-1r1t-v1"
        or not isinstance(returned, dict)
        or returned.get("serial") != RX_SERIAL
        or returned.get("firmware") != expected["firmware"]
        or returned.get("fit_sha256") != expected["fit_sha256"]
        or returned.get("root_marker_present") != "1"
        or returned.get("rx_dma_dt_state") != "disabled"
        or returned.get("dds_present") != "0"
        or returned.get("dds_dt_state") != "disabled"
        or returned.get("tx_dma_dt_state") != "disabled"
        or returned.get("tandem_present") != "0"
        or returned.get("tandem_dt_state") != "disabled"
        or returned.get("tx_lo_powerdown") != "1"
        or not isinstance(rotation, dict)
        or len(str(rotation.get("replacement_known_hosts_sha256", ""))) != 64
    ):
        raise QualificationError(
            "PPU deployment receipt violates the native-IIO contract"
        )
    return receipt


def _deployment_binding(
    deployment_receipt: Path,
    known_hosts_file: Path,
    *,
    rate_msps: int,
    reboot_receipts: list[Path],
) -> dict[str, Any]:
    receipt = _validate_deployment(deployment_receipt, rate_msps=rate_msps)
    expected = EXPECTED_DEPLOYMENTS[rate_msps]
    expected_key_hash = receipt["host_key_rotation"]["replacement_known_hosts_sha256"]
    current_boot_id = receipt["read_only_return_attestation"]["boot_id"]
    reboot_identities: list[dict[str, Any]] = []
    for path in reboot_receipts:
        reboot = _load(path, label="PPU detector-only reboot receipt")
        plan = reboot.get("plan")
        before = reboot.get("before")
        after = reboot.get("after")
        rotation = reboot.get("host_key_rotation")
        before_capabilities = (
            before.get("capabilities") if isinstance(before, dict) else None
        )
        after_capabilities = (
            after.get("capabilities") if isinstance(after, dict) else None
        )
        if (
            reboot.get("schema_version") != 2
            or reboot.get("outcome") != "success"
            or reboot.get("error") is not None
            or reboot.get("dispatch_error") is not None
            or not isinstance(plan, dict)
            or plan.get("schema_version") != 3
            or plan.get("serial") != RX_SERIAL
            or plan.get("ssh_host") != "192.168.1.17"
            or plan.get("known_hosts_sha256") != expected_key_hash
            or not isinstance(before, dict)
            or before.get("serial") != RX_SERIAL
            or before.get("firmware") != expected["firmware"]
            or before.get("boot_id") != current_boot_id
            or not isinstance(before_capabilities, dict)
            or before_capabilities.get("phy_model") != "ad9361"
            or before_capabilities.get("rx_scan_channels") != []
            or before_capabilities.get("tandem_agc") is not False
            or before_capabilities.get("detector_only") is not True
            or not isinstance(after, dict)
            or after.get("serial") != RX_SERIAL
            or after.get("firmware") != expected["firmware"]
            or not isinstance(after.get("boot_id"), str)
            or after.get("boot_id") == current_boot_id
            or not isinstance(after_capabilities, dict)
            or after_capabilities.get("phy_model") != "ad9361"
            or after_capabilities.get("rx_scan_channels") != []
            or after_capabilities.get("tandem_agc") is not False
            or after_capabilities.get("detector_only") is not True
            or not isinstance(rotation, dict)
            or rotation.get("previous_known_hosts_sha256") != expected_key_hash
            or len(str(rotation.get("replacement_known_hosts_sha256", ""))) != 64
        ):
            raise QualificationError(
                "PPU reboot receipt breaks the detector-only boot chain"
            )
        expected_key_hash = rotation["replacement_known_hosts_sha256"]
        current_boot_id = after["boot_id"]
        reboot_identities.append(_identity(path))
    known_hosts = known_hosts_file.expanduser().resolve(strict=True)
    if _sha256(known_hosts) != expected_key_hash:
        raise QualificationError("current known_hosts differs from the reboot chain")
    return {
        "receipt": _identity(deployment_receipt),
        "boot_id": receipt["read_only_return_attestation"]["boot_id"],
        "qspi_sha256": receipt["read_only_return_attestation"]["qspi_sha256"],
        "known_hosts": _identity(known_hosts),
        "reboots": reboot_identities,
        "current_boot_id": current_boot_id,
    }


def _compact_map(phase_map: PssPhaseMap, *, rate_msps: int) -> dict[str, int]:
    peak_score = max(phase_map.bins)
    return {
        "generation": phase_map.generation,
        "canonical_start_index": phase_map.start_index,
        "source_start_index": phase_map.source_start_index(rate_msps=rate_msps),
        "peak_bin": phase_map.bins.index(peak_score),
        "peak_score": peak_score,
    }


class ContinuousMapStream:
    """Read, hash, and continuity-check exactly one FPGA map epoch."""

    def __init__(self, client: PssIioClient, *, rate_msps: int) -> None:
        self.client = client
        self.rate_msps = rate_msps
        self.reassembler = PssMapReassembler()
        self.pending: deque[PssPhaseMap] = deque()
        self.previous: PssPhaseMap | None = None
        self.digest = hashlib.sha256()
        self.count = 0

    def read_one(self) -> tuple[PssPhaseMap, dict[str, int]]:
        while not self.pending:
            self.pending.extend(self.client.read_maps(self.reassembler))
        phase_map = self.pending.popleft()
        if self.previous is not None:
            _validate_transition(self.previous, phase_map)
        self.digest.update(
            struct.pack(
                "<IIQ",
                phase_map.abi_version,
                phase_map.generation,
                phase_map.start_index,
            )
        )
        self.digest.update(struct.pack(f"<{len(phase_map.bins)}H", *phase_map.bins))
        record = _compact_map(phase_map, rate_msps=self.rate_msps)
        self.previous = phase_map
        self.count += 1
        return phase_map, record


def _capture_role(
    stream: ContinuousMapStream,
    *,
    role: str,
    requested_lo_hz: int,
    readback_lo_hz: int,
    duration_seconds: float,
) -> dict[str, Any]:
    maps: deque[PssPhaseMap] = deque(maxlen=3)
    windows: list[dict[str, Any]] = []
    first_records: list[dict[str, int]] = []
    last_records: deque[dict[str, int]] = deque(maxlen=8)
    started_at = _now()
    started = time.monotonic()
    while time.monotonic() - started < duration_seconds:
        phase_map, record = stream.read_one()
        if len(first_records) < 8:
            first_records.append(record)
        last_records.append(record)
        maps.append(phase_map)
        if len(maps) == 3:
            windows.append(
                asdict(analyze_phase_maps(tuple(maps), rate_msps=stream.rate_msps))
            )
    elapsed = time.monotonic() - started
    map_count = len(windows) + 2
    minimum_maps = _minimum_complete_maps(duration_seconds)
    if map_count < minimum_maps:
        raise QualificationError(f"{role} produced too few complete maps")
    return {
        "role": role,
        "started_at": started_at,
        "completed_at": _now(),
        "requested_duration_seconds": duration_seconds,
        "elapsed_seconds": elapsed,
        "requested_lo_hz": requested_lo_hz,
        "readback_lo_hz": readback_lo_hz,
        "complete_maps": map_count,
        "minimum_complete_maps": minimum_maps,
        "coarse_window_count": len(windows),
        "coarse_windows": windows,
        "first_maps": first_records,
        "last_maps": list(last_records),
        "metrics": trajectory_metrics(windows),
    }


def _retune_and_discard(
    client: PssIioClient,
    stream: ContinuousMapStream,
    *,
    from_role: str,
    to_role: str,
    requested_lo_hz: int,
) -> dict[str, Any]:
    phy = client.context.find_device("ad9361-phy")
    if phy is None:
        raise QualificationError("AD9361 PHY disappeared before campaign retune")
    rx_lo = _required_channel(phy, "altvoltage0", True)
    started_at = _now()
    readback = _write_number(rx_lo, "frequency", requested_lo_hz, 2)
    time.sleep(RETUNE_SETTLE_SECONDS)
    discarded = [stream.read_one()[1] for _ in range(RETUNE_DISCARD_MAPS)]
    return {
        "from_role": from_role,
        "to_role": to_role,
        "started_at": started_at,
        "completed_at": _now(),
        "requested_lo_hz": requested_lo_hz,
        "readback_lo_hz": readback,
        "settle_seconds": RETUNE_SETTLE_SECONDS,
        "discarded_map_count": len(discarded),
        "discarded_maps": discarded,
    }


def _driver_counters(client: PssIioClient) -> dict[str, int]:
    return {
        "maps_delivered": _number(client.phase_map, "maps_delivered"),
        "chunks_delivered": _number(client.phase_map, "chunks_delivered"),
        "map_buffer_push_failures": _number(client.phase_map, "buffer_push_failures"),
        "map_fault_flags": _number(client.phase_map, "fault_flags"),
        "tracker_buffer_push_failures": _number(client.tracker, "buffer_push_failures"),
        "tracker_packet_validation_failures": _number(
            client.tracker, "packet_validation_failures"
        ),
        "tracker_fault_flags": _number(client.tracker, "fault_flags"),
    }


def campaign_evaluation(roles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if set(roles) != set(ROLES):
        raise QualificationError("campaign role inventory differs")
    on_a, control, on_b = (roles[role] for role in ROLES)
    positive_median = min(
        _validated_number(
            on_a["metrics"].get("median_peak_to_median"), label="on-A median"
        ),
        _validated_number(
            on_b["metrics"].get("median_peak_to_median"), label="on-B median"
        ),
    )
    control_median = _validated_number(
        control["metrics"].get("median_peak_to_median"), label="control median"
    )
    contrast = positive_median / max(control_median, sys.float_info.min)
    gates = {
        "duration_qualified": all(
            value.get("requested_duration_seconds") == 120.0
            and _validated_number(value.get("elapsed_seconds"), label=f"{role} elapsed")
            >= 120.0
            for role, value in roles.items()
        ),
        "positive_a_track": on_a["metrics"].get("classification") == "positive_track",
        "below_band_control_rejected": control["metrics"].get("classification")
        == "negative_control",
        "positive_b_track": on_b["metrics"].get("classification") == "positive_track",
        "positive_to_control_contrast_met": contrast
        >= POLICY["minimum_positive_to_negative_median_ratio"],
    }
    return {
        "qualified": all(gates.values()),
        "gates": gates,
        "positive_to_control_median_ratio": contrast,
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
    role_duration_seconds: float = 120.0,
) -> dict[str, Any]:
    if not 1.0 <= role_duration_seconds <= 120.0:
        raise ValueError("role duration must lie in [1, 120] seconds")
    geometry = _validate_frequency_plan(on_if_hz)
    firmware_source_commit = _validate_source_commit(
        firmware_source_commit, label="firmware source commit"
    )
    ppu_source_commit = _validate_source_commit(
        ppu_source_commit, label="PPU source commit"
    )
    deployment = _deployment_binding(
        deployment_receipt,
        known_hosts_file,
        rate_msps=profile.rate_msps,
        reboot_receipts=reboot_receipts,
    )
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if _sha256(profile.coefficient_path) != profile.coefficient_sha256:
        raise QualificationError("coefficient file identity differs")
    receipt: dict[str, Any] = {
        "schema": RUN_SCHEMA,
        "schema_version": 2,
        "started_at": _now(),
        "outcome": "started",
        "persistent_write": False,
        "transmitter_opened": False,
        "serial": RX_SERIAL,
        "rate_msps": profile.rate_msps,
        "sample_rate_hz": profile.rate_hz,
        "role_order": list(ROLES),
        "role_duration_seconds": role_duration_seconds,
        "geometry": geometry,
        "retune_settle_seconds": RETUNE_SETTLE_SECONDS,
        "retune_discard_maps": RETUNE_DISCARD_MAPS,
        "firmware_source_commit": firmware_source_commit,
        "ppu_source_commit": ppu_source_commit,
        "deployment": deployment,
        "coefficient": {
            "path": str(profile.coefficient_path.resolve()),
            "sha256": profile.coefficient_sha256,
            "generation": profile.coefficient_generation,
        },
        "receiver": {"transport": "ethernet", "uri": ETHERNET_URI},
        "roles": {},
        "transitions": [],
        "cleanup": {"errors": []},
        "pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
    }
    client: PssIioClient | None = None
    before: dict[str, Any] | None = None
    stream: ContinuousMapStream | None = None
    body_error: BaseException | None = None
    lock_stack = ExitStack()
    try:
        lock_stack.enter_context(acquire_radio_lock(RX_SERIAL))
        client = PssIioClient.connect(ETHERNET_URI, expected_serial=RX_SERIAL)
        before, selected = _configure_rx(client, profile, lo_hz=on_if_hz)
        receipt["receiver"].update(
            {"firmware": profile.firmware, "original": before, "selected": selected}
        )
        client.load_coefficient_file(
            profile.coefficient_path, generation=profile.coefficient_generation
        )
        active_generation = _number(client.tracker, "active_coefficient_generation")
        stream = ContinuousMapStream(client, rate_msps=profile.rate_msps)
        client.open_maps(refill_chunks=PSS_MAP_CHUNKS)
        requested_by_role = {
            "on_channel_a": on_if_hz,
            "below_band_control": CONTROL_IF_HZ,
            "on_channel_b": on_if_hz,
        }
        readback = int(selected["lo"])
        previous_role: str | None = None
        for role in ROLES:
            requested = requested_by_role[role]
            if previous_role is not None:
                transition = _retune_and_discard(
                    client,
                    stream,
                    from_role=previous_role,
                    to_role=role,
                    requested_lo_hz=requested,
                )
                receipt["transitions"].append(transition)
                readback = int(transition["readback_lo_hz"])
            receipt["roles"][role] = _capture_role(
                stream,
                role=role,
                requested_lo_hz=requested,
                readback_lo_hz=readback,
                duration_seconds=role_duration_seconds,
            )
            previous_role = role
        counters = _driver_counters(client)
        client.close_maps()
        role_maps = sum(value["complete_maps"] for value in receipt["roles"].values())
        transition_maps = sum(
            value["discarded_map_count"] for value in receipt["transitions"]
        )
        expected_count = role_maps + transition_maps
        gates = {
            "active_coefficient_exact": active_generation
            == profile.coefficient_generation,
            "single_map_epoch_exact": stream.count == expected_count,
            "driver_map_count_exact": counters["maps_delivered"] == stream.count,
            "driver_chunk_count_exact": counters["chunks_delivered"]
            == stream.count * PSS_MAP_CHUNKS,
            "role_map_counts_exact": all(
                value["coarse_window_count"] == value["complete_maps"] - 2
                and value["complete_maps"] >= value["minimum_complete_maps"]
                for value in receipt["roles"].values()
            ),
            "retune_discard_counts_exact": len(receipt["transitions"]) == 2
            and all(
                value["discarded_map_count"] == RETUNE_DISCARD_MAPS
                for value in receipt["transitions"]
            ),
            "map_push_failure_free": counters["map_buffer_push_failures"] == 0,
            "map_fault_free": counters["map_fault_flags"] == 0,
            "tracker_push_failure_free": counters["tracker_buffer_push_failures"] == 0,
            "tracker_validation_failure_free": counters[
                "tracker_packet_validation_failures"
            ]
            == 0,
            "tracker_fault_free": counters["tracker_fault_flags"] == 0,
        }
        evaluation = campaign_evaluation(receipt["roles"])
        receipt["stream"] = {
            "complete_maps": stream.count,
            "role_maps": role_maps,
            "transition_discard_maps": transition_maps,
            "logical_map_bytes": stream.count * FRAME_SAMPLES * 2,
            "transport_bytes": stream.count * PSS_MAP_CHUNKS * PSS_MAP_SCAN_BYTES,
            "map_digest_sha256": stream.digest.hexdigest(),
            "counters": counters,
        }
        receipt["gates"] = gates
        receipt["evaluation"] = evaluation
        failed = [name for name, passed in gates.items() if not passed]
        if failed:
            raise QualificationError(f"native live campaign gates failed: {failed}")
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
        raise QualificationError("native live campaign cleanup did not verify")
    return receipt


def replay(*, receipt_path: Path, output: Path) -> dict[str, Any]:
    receipt = _load(receipt_path, label="corrected native-IIO campaign")
    rate_msps = _integer(receipt.get("rate_msps"), label="rate", minimum=1)
    duration = _validated_number(
        receipt.get("role_duration_seconds"), label="role duration", minimum=1.0
    )
    geometry = receipt.get("geometry")
    receiver = receipt.get("receiver")
    roles = receipt.get("roles")
    transitions = receipt.get("transitions")
    stream = receipt.get("stream")
    gates = receipt.get("gates")
    cleanup = receipt.get("cleanup")
    coefficient = receipt.get("coefficient")
    deployment = receipt.get("deployment")
    selected = receiver.get("selected") if isinstance(receiver, dict) else None
    if (
        receipt.get("schema") != RUN_SCHEMA
        or receipt.get("schema_version") != 2
        or receipt.get("outcome") != "pass"
        or receipt.get("persistent_write") is not False
        or receipt.get("transmitter_opened") is not False
        or receipt.get("serial") != RX_SERIAL
        or rate_msps not in EXPECTED_DEPLOYMENTS
        or receipt.get("sample_rate_hz") != rate_msps * 1_000_000
        or receipt.get("role_order") != list(ROLES)
        or not 1.0 <= duration <= 120.0
        or not isinstance(geometry, dict)
        or geometry != _validate_frequency_plan(geometry.get("on_channel_if_hz"))
        or receipt.get("retune_settle_seconds") != RETUNE_SETTLE_SECONDS
        or receipt.get("retune_discard_maps") != RETUNE_DISCARD_MAPS
        or not isinstance(receiver, dict)
        or set(receiver) != {"transport", "uri", "firmware", "original", "selected"}
        or receiver.get("transport") != "ethernet"
        or receiver.get("uri") != ETHERNET_URI
        or receiver.get("firmware") != EXPECTED_DEPLOYMENTS[rate_msps]["firmware"]
        or not isinstance(selected, dict)
        or selected.get("phy_rate") != rate_msps * 1_000_000
        or selected.get("adc_rate") != rate_msps * 1_000_000
        or selected.get("bandwidth") != RX_BANDWIDTH_HZ
        or selected.get("gain_mode") != "slow_attack"
        or selected.get("lo") != geometry["on_channel_if_hz"]
        or selected.get("lo_powerdown") != 0
        or not isinstance(roles, dict)
        or set(roles) != set(ROLES)
        or not isinstance(transitions, list)
        or len(transitions) != 2
        or not isinstance(stream, dict)
        or not isinstance(gates, dict)
        or not gates
        or any(value is not True for value in gates.values())
        or not isinstance(cleanup, dict)
        or cleanup.get("verified") is not True
        or cleanup.get("errors") != []
        or cleanup.get("rx_restored") != receiver.get("original")
        or not isinstance(coefficient, dict)
        or set(coefficient) != {"path", "sha256", "generation"}
        or not isinstance(deployment, dict)
        or set(deployment)
        != {
            "receipt",
            "boot_id",
            "qspi_sha256",
            "known_hosts",
            "reboots",
            "current_boot_id",
        }
        or not isinstance(deployment.get("reboots"), list)
        or not isinstance(deployment.get("current_boot_id"), str)
    ):
        raise QualificationError("corrected campaign violates its root contract")
    _validate_source_commit(
        receipt.get("firmware_source_commit"), label="firmware source commit"
    )
    _validate_source_commit(receipt.get("ppu_source_commit"), label="PPU source commit")
    if _sha256(Path(coefficient["path"])) != coefficient["sha256"]:
        raise QualificationError("campaign coefficient changed after acquisition")

    requested_by_role = {
        "on_channel_a": geometry["on_channel_if_hz"],
        "below_band_control": CONTROL_IF_HZ,
        "on_channel_b": geometry["on_channel_if_hz"],
    }
    endpoints: dict[str, tuple[int, int, int, int]] = {}
    for role in ROLES:
        endpoints[role] = _validate_campaign_role(
            roles[role],
            role=role,
            requested_lo_hz=requested_by_role[role],
            duration_seconds=duration,
            rate_msps=rate_msps,
        )
    for index, transition in enumerate(transitions):
        from_role, to_role = ROLES[index], ROLES[index + 1]
        records = (
            transition.get("discarded_maps") if isinstance(transition, dict) else None
        )
        previous_generation, previous_start = endpoints[from_role][2:]
        if (
            not isinstance(transition, dict)
            or transition.get("from_role") != from_role
            or transition.get("to_role") != to_role
            or transition.get("requested_lo_hz") != requested_by_role[to_role]
            or abs(
                _integer(transition.get("readback_lo_hz"), label="retune LO")
                - requested_by_role[to_role]
            )
            > 2
            or transition.get("settle_seconds") != RETUNE_SETTLE_SECONDS
            or transition.get("discarded_map_count") != RETUNE_DISCARD_MAPS
            or not isinstance(records, list)
            or len(records) != RETUNE_DISCARD_MAPS
        ):
            raise QualificationError("corrected campaign retune contract is invalid")
        for ordinal, record in enumerate(records, 1):
            _validate_compact_map(
                record,
                generation=previous_generation + ordinal,
                start=previous_start + ordinal * MAP_SPAN,
                rate_msps=rate_msps,
            )
        if endpoints[to_role][0] != previous_generation + RETUNE_DISCARD_MAPS + 1:
            raise QualificationError(
                "generation continuity breaks across corrected retune"
            )
        if (
            endpoints[to_role][1]
            != previous_start + (RETUNE_DISCARD_MAPS + 1) * MAP_SPAN
        ):
            raise QualificationError("index continuity breaks across corrected retune")

    role_maps = sum(roles[role]["complete_maps"] for role in ROLES)
    total_maps = role_maps + 2 * RETUNE_DISCARD_MAPS
    counters = stream.get("counters")
    if (
        stream.get("complete_maps") != total_maps
        or stream.get("role_maps") != role_maps
        or stream.get("transition_discard_maps") != 2 * RETUNE_DISCARD_MAPS
        or stream.get("logical_map_bytes") != total_maps * FRAME_SAMPLES * 2
        or stream.get("transport_bytes") != total_maps * MAP_CHUNKS * MAP_SCAN_BYTES
        or not isinstance(counters, dict)
        or counters.get("maps_delivered") != total_maps
        or counters.get("chunks_delivered") != total_maps * MAP_CHUNKS
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
        raise QualificationError("corrected campaign stream accounting is invalid")
    evaluation = campaign_evaluation(roles)
    if (
        receipt.get("evaluation") != evaluation
        or receipt.get("pss_detected") is not evaluation["qualified"]
        or receipt.get("sss_detected") is not False
        or receipt.get("frame_lock_claim") is not False
    ):
        raise QualificationError("corrected campaign claims differ from replay")
    analysis = {
        "schema": ANALYSIS_SCHEMA,
        "schema_version": 2,
        "outcome": "pass",
        "hardware_accessed": False,
        "persistent_write": False,
        "source_receipt": _identity(receipt_path),
        "serial": RX_SERIAL,
        "rate_msps": rate_msps,
        "role_duration_seconds": duration,
        "geometry": geometry,
        "role_metrics": {role: roles[role]["metrics"] for role in ROLES},
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
    execute = commands.add_parser("run", help="run one corrected live campaign")
    execute.add_argument(
        "--rate-msps", type=int, choices=tuple(RATE_PROFILES), default=30
    )
    execute.add_argument("--on-if-hz", type=int, default=1_937_500_000)
    execute.add_argument("--role-duration-seconds", type=float, default=120.0)
    execute.add_argument("--deployment-receipt", type=Path, required=True)
    execute.add_argument("--known-hosts-file", type=Path, required=True)
    execute.add_argument(
        "--reboot-receipt",
        type=Path,
        action="append",
        default=[],
        help="ordered PPU reboot receipt; repeat for every reboot after deployment",
    )
    execute.add_argument("--firmware-source-commit", required=True)
    execute.add_argument("--ppu-source-commit", required=True)
    execute.add_argument("output", type=Path)
    verify = commands.add_parser(
        "replay", help="independently replay one campaign receipt"
    )
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
                role_duration_seconds=arguments.role_duration_seconds,
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
