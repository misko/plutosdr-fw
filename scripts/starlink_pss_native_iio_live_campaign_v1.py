#!/usr/bin/env python3
"""Run one RX-only native-IIO PSS on/control/on campaign over Ethernet.

The FPGA map stream is opened exactly once. The AD9361 receiver LO is retuned
between roles while the stream remains open, and five complete maps are
discarded after each retune. No transmitter is opened and no persistent radio
storage is written. A live PSS timing claim requires three 120-second roles;
shorter durations are allowed only for structural hardware qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
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
    POLICY,
    ROLES,
    campaign_evaluation,
    trajectory_metrics,
)
from scripts.starlink_pss_native_iio_soak_v1 import (
    _minimum_complete_maps,
    _validate_transition,
)

SCHEMA = "plutosdr-fw.starlink-pss-native-iio-live-campaign-run.v1"
ETHERNET_URI = "ip:192.168.1.17"
RETUNE_SETTLE_SECONDS = 0.2
RETUNE_DISCARD_MAPS = 5


def _validate_frequency_plan(on_lo_hz: int, off_lo_hz: int) -> None:
    for label, value in (("on-channel", on_lo_hz), ("off-slice", off_lo_hz)):
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 70_000_000 <= value <= 6_000_000_000
        ):
            raise ValueError(f"{label} RX LO must lie in [70000000, 6000000000] Hz")
    if abs(off_lo_hz - on_lo_hz) < POLICY["minimum_off_slice_separation_hz"]:
        raise ValueError("off-slice RX LO must be separated by at least 30 MHz")


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
    metrics = trajectory_metrics(windows)
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
        "metrics": metrics,
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


def run(
    output: Path,
    *,
    profile: RateProfile,
    on_lo_hz: int,
    off_lo_hz: int,
    role_duration_seconds: float = 120.0,
) -> dict[str, Any]:
    if not 1.0 <= role_duration_seconds <= 120.0:
        raise ValueError("role duration must lie in [1, 120] seconds")
    _validate_frequency_plan(on_lo_hz, off_lo_hz)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if (
        hashlib.sha256(profile.coefficient_path.read_bytes()).hexdigest()
        != profile.coefficient_sha256
    ):
        raise QualificationError("coefficient file identity differs")
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "started_at": _now(),
        "outcome": "started",
        "persistent_write": False,
        "transmitter_opened": False,
        "serial": RX_SERIAL,
        "rate_msps": profile.rate_msps,
        "sample_rate_hz": profile.rate_hz,
        "role_order": list(ROLES),
        "role_duration_seconds": role_duration_seconds,
        "on_channel_lo_hz": on_lo_hz,
        "off_slice_lo_hz": off_lo_hz,
        "retune_settle_seconds": RETUNE_SETTLE_SECONDS,
        "retune_discard_maps": RETUNE_DISCARD_MAPS,
        "coefficient": {
            "path": str(profile.coefficient_path),
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
    body_error: BaseException | None = None
    stream: ContinuousMapStream | None = None
    lock_stack = ExitStack()
    try:
        lock_stack.enter_context(acquire_radio_lock(RX_SERIAL))
        client = PssIioClient.connect(ETHERNET_URI, expected_serial=RX_SERIAL)
        before, selected = _configure_rx(client, profile, lo_hz=on_lo_hz)
        receipt["receiver"].update(
            {
                "firmware": profile.firmware,
                "original": before,
                "selected": selected,
            }
        )
        client.load_coefficient_file(
            profile.coefficient_path, generation=profile.coefficient_generation
        )
        active_generation = _number(client.tracker, "active_coefficient_generation")
        stream = ContinuousMapStream(client, rate_msps=profile.rate_msps)
        client.open_maps(refill_chunks=PSS_MAP_CHUNKS)
        frequency_by_role = {
            "on_channel_a": on_lo_hz,
            "off_slice_control": off_lo_hz,
            "on_channel_b": on_lo_hz,
        }
        readback = int(selected["lo"])
        previous_role: str | None = None
        for role in ROLES:
            requested = frequency_by_role[role]
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
        role_map_count = sum(
            role["complete_maps"] for role in receipt["roles"].values()
        )
        transition_map_count = sum(
            transition["discarded_map_count"] for transition in receipt["transitions"]
        )
        expected_count = role_map_count + transition_map_count
        gates = {
            "active_coefficient_exact": active_generation
            == profile.coefficient_generation,
            "single_map_epoch_exact": stream.count == expected_count,
            "driver_map_count_exact": counters["maps_delivered"] == stream.count,
            "driver_chunk_count_exact": counters["chunks_delivered"]
            == stream.count * PSS_MAP_CHUNKS,
            "role_map_counts_exact": all(
                role["coarse_window_count"] == role["complete_maps"] - 2
                and role["complete_maps"] >= role["minimum_complete_maps"]
                for role in receipt["roles"].values()
            ),
            "retune_discard_counts_exact": len(receipt["transitions"]) == 2
            and all(
                transition["discarded_map_count"] == RETUNE_DISCARD_MAPS
                for transition in receipt["transitions"]
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
            "role_maps": role_map_count,
            "transition_discard_maps": transition_map_count,
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
    except BaseException as error:  # noqa: BLE001 - receipt every hardware outcome
        body_error = error
        receipt["outcome"] = "failed"
        receipt["pss_detected"] = False
        receipt["error"] = f"{type(error).__name__}: {error}"
    finally:
        cleanup_errors: list[str] = receipt["cleanup"]["errors"]
        if client is not None:
            try:
                client.close_maps()
            except BaseException as error:  # noqa: BLE001 - continue cleanup
                cleanup_errors.append(f"RX map close: {error}")
            if before is not None:
                try:
                    receipt["cleanup"]["rx_restored"] = _restore_rx(client, before)
                except BaseException as error:  # noqa: BLE001 - continue cleanup
                    cleanup_errors.append(f"RX restore: {error}")
            try:
                client.close()
            except BaseException as error:  # noqa: BLE001 - continue cleanup
                cleanup_errors.append(f"RX context close: {error}")
        try:
            lock_stack.close()
        except BaseException as error:  # noqa: BLE001 - continue cleanup
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rate-msps", type=int, choices=tuple(RATE_PROFILES), default=30
    )
    parser.add_argument("--on-lo-hz", type=int, required=True)
    parser.add_argument("--off-lo-hz", type=int, required=True)
    parser.add_argument("--role-duration-seconds", type=float, default=120.0)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    try:
        receipt = run(
            arguments.output,
            profile=RATE_PROFILES[arguments.rate_msps],
            on_lo_hz=arguments.on_lo_hz,
            off_lo_hz=arguments.off_lo_hz,
            role_duration_seconds=arguments.role_duration_seconds,
        )
    except BaseException as error:  # noqa: BLE001 - guarded CLI boundary
        print(json.dumps({"outcome": "failed", "error": str(error)}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "outcome": receipt["outcome"],
                "serial": receipt["serial"],
                "rate_msps": receipt["rate_msps"],
                "roles": {
                    role: {
                        "complete_maps": value["complete_maps"],
                        "coarse_window_count": value["coarse_window_count"],
                        "metrics": value["metrics"],
                    }
                    for role, value in receipt["roles"].items()
                },
                "stream": receipt["stream"],
                "gates": receipt["gates"],
                "evaluation": receipt["evaluation"],
                "cleanup": receipt["cleanup"],
                "receipt": receipt["receipt"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
