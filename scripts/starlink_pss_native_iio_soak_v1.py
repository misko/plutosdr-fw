#!/usr/bin/env python3
"""Soak one exact RX-only PSS phase-map stream over USB or Ethernet.

The runner never opens a transmitter and never writes persistent radio storage.
It consumes one continuous map session for the complete dwell, records compact
map identities instead of IQ, and fails on the first generation/index gap.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import time
from collections import deque
from contextlib import ExitStack, nullcontext
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
    PSS_MAP_CANONICAL_SPAN,
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
    _receiver_uri,
    _restore_rx,
)


def _minimum_complete_maps(duration_seconds: float) -> int:
    """Allow two boundary maps around the exact canonical production rate."""

    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("soak duration must be finite and positive")
    maps_per_second = 15_000_000 / PSS_MAP_CANONICAL_SPAN
    return max(1, math.floor(duration_seconds * maps_per_second) - 2)


def _validate_transition(previous: PssPhaseMap, current: PssPhaseMap) -> None:
    if current.generation != previous.generation + 1:
        raise QualificationError("phase-map generation is discontinuous")
    if current.start_index != previous.start_index + PSS_MAP_CANONICAL_SPAN:
        raise QualificationError("phase-map canonical start index is discontinuous")
    if current.abi_version != previous.abi_version:
        raise QualificationError("phase-map ABI changed during the soak")


def _record_map(
    phase_map: PssPhaseMap, *, digest: Any, rate_msps: int
) -> dict[str, int]:
    """Hash one complete logical map and return a compact peak identity."""

    digest.update(
        struct.pack(
            "<IIQ", phase_map.abi_version, phase_map.generation, phase_map.start_index
        )
    )
    digest.update(struct.pack(f"<{len(phase_map.bins)}H", *phase_map.bins))
    peak_score = max(phase_map.bins)
    return {
        "generation": phase_map.generation,
        "canonical_start_index": phase_map.start_index,
        "source_start_index": phase_map.source_start_index(rate_msps=rate_msps),
        "peak_bin": phase_map.bins.index(peak_score),
        "peak_score": peak_score,
    }


def run(
    output: Path,
    *,
    profile: RateProfile,
    receiver_transport: str,
    duration_seconds: float,
) -> dict[str, Any]:
    if not 1.0 <= duration_seconds <= 120.0:
        raise ValueError("soak duration must lie in [1, 120] seconds")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if (
        hashlib.sha256(profile.coefficient_path.read_bytes()).hexdigest()
        != profile.coefficient_sha256
    ):
        raise QualificationError("coefficient file identity differs")
    receipt: dict[str, Any] = {
        "schema": "plutosdr-fw.starlink-pss-native-iio-map-soak.v1",
        "started_at": _now(),
        "outcome": "started",
        "persistent_write": False,
        "transmitter_opened": False,
        "receiver": {
            "serial": RX_SERIAL,
            "transport": receiver_transport,
        },
        "rate_msps": profile.rate_msps,
        "sample_rate_hz": profile.rate_hz,
        "requested_duration_seconds": duration_seconds,
        "coefficient": {
            "path": str(profile.coefficient_path),
            "sha256": profile.coefficient_sha256,
            "generation": profile.coefficient_generation,
        },
        "cleanup": {"errors": []},
    }
    client: PssIioClient | None = None
    before: dict[str, Any] | None = None
    body_error: BaseException | None = None
    lock_stack = ExitStack()
    try:
        lock_stack.enter_context(acquire_radio_lock(RX_SERIAL))
        with nullcontext():
            uri = _receiver_uri(receiver_transport)
            client = PssIioClient.connect(uri, expected_serial=RX_SERIAL)
            before, selected = _configure_rx(client, profile)
            receipt["receiver"].update(
                {
                    "uri": uri,
                    "firmware": profile.firmware,
                    "original": before,
                    "selected": selected,
                }
            )
            client.load_coefficient_file(
                profile.coefficient_path, generation=profile.coefficient_generation
            )
            active_generation = _number(client.tracker, "active_coefficient_generation")
            reassembler = PssMapReassembler()
            digest = hashlib.sha256()
            first_records: list[dict[str, int]] = []
            last_records: deque[dict[str, int]] = deque(maxlen=8)
            last_maps: deque[PssPhaseMap] = deque(maxlen=3)
            previous: PssPhaseMap | None = None
            map_count = 0

            client.open_maps(refill_chunks=PSS_MAP_CHUNKS)
            started = time.monotonic()
            while time.monotonic() - started < duration_seconds:
                maps = client.read_maps(reassembler)
                for phase_map in maps:
                    if previous is not None:
                        _validate_transition(previous, phase_map)
                    record = _record_map(
                        phase_map, digest=digest, rate_msps=profile.rate_msps
                    )
                    if len(first_records) < 8:
                        first_records.append(record)
                    last_records.append(record)
                    last_maps.append(phase_map)
                    previous = phase_map
                    map_count += 1
            elapsed = time.monotonic() - started
            counters = {
                "maps_delivered": _number(client.phase_map, "maps_delivered"),
                "chunks_delivered": _number(client.phase_map, "chunks_delivered"),
                "map_buffer_push_failures": _number(
                    client.phase_map, "buffer_push_failures"
                ),
                "map_fault_flags": _number(client.phase_map, "fault_flags"),
                "tracker_buffer_push_failures": _number(
                    client.tracker, "buffer_push_failures"
                ),
                "tracker_packet_validation_failures": _number(
                    client.tracker, "packet_validation_failures"
                ),
                "tracker_fault_flags": _number(client.tracker, "fault_flags"),
            }
            client.close_maps()
            if len(last_maps) != 3:
                raise QualificationError("soak produced fewer than three complete maps")
            coarse = analyze_phase_maps(tuple(last_maps), rate_msps=profile.rate_msps)
            transport_bytes = map_count * PSS_MAP_CHUNKS * PSS_MAP_SCAN_BYTES
            minimum_maps = _minimum_complete_maps(duration_seconds)
            gates = {
                "duration_met": elapsed >= duration_seconds,
                "minimum_map_count_met": map_count >= minimum_maps,
                "driver_map_count_exact": counters["maps_delivered"] == map_count,
                "driver_chunk_count_exact": counters["chunks_delivered"]
                == map_count * PSS_MAP_CHUNKS,
                "active_coefficient_exact": active_generation
                == profile.coefficient_generation,
                "map_push_failure_free": counters["map_buffer_push_failures"] == 0,
                "map_fault_free": counters["map_fault_flags"] == 0,
                "tracker_push_failure_free": counters["tracker_buffer_push_failures"]
                == 0,
                "tracker_validation_failure_free": counters[
                    "tracker_packet_validation_failures"
                ]
                == 0,
                "tracker_fault_free": counters["tracker_fault_flags"] == 0,
            }
            receipt["stream"] = {
                "elapsed_seconds": elapsed,
                "complete_maps": map_count,
                "minimum_complete_maps": minimum_maps,
                "logical_map_bytes": map_count * 20_000 * 2,
                "transport_bytes": transport_bytes,
                "transport_bytes_per_second": transport_bytes / elapsed,
                "map_digest_sha256": digest.hexdigest(),
                "first_maps": first_records,
                "last_maps": list(last_records),
                "last_three_coarse_estimate": asdict(coarse),
                "counters": counters,
            }
            receipt["gates"] = gates
            failed = [name for name, passed in gates.items() if not passed]
            if failed:
                raise QualificationError(f"native-IIO map-soak gates failed: {failed}")
            receipt["outcome"] = "pass"
    except BaseException as error:  # noqa: BLE001 - receipt every hardware outcome
        body_error = error
        receipt["outcome"] = "failed"
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
        receipt["completed_at"] = _now()
        receipt_path = output / "run-receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        receipt["receipt"] = str(receipt_path)
    if body_error is not None:
        raise body_error
    if receipt["outcome"] != "pass":
        raise QualificationError("native-IIO map-soak cleanup did not verify")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rate-msps", type=int, choices=tuple(RATE_PROFILES), default=30
    )
    parser.add_argument(
        "--receiver-transport", choices=("usb", "ethernet"), default="ethernet"
    )
    parser.add_argument("--duration-seconds", type=float, default=120.0)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    if not 1.0 <= arguments.duration_seconds <= 120.0:
        parser.error("--duration-seconds must lie in [1, 120]")
    try:
        receipt = run(
            arguments.output,
            profile=RATE_PROFILES[arguments.rate_msps],
            receiver_transport=arguments.receiver_transport,
            duration_seconds=arguments.duration_seconds,
        )
    except BaseException as error:  # noqa: BLE001 - guarded CLI boundary
        print(json.dumps({"outcome": "failed", "error": str(error)}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "outcome": receipt["outcome"],
                "receiver": receipt["receiver"],
                "rate_msps": receipt["rate_msps"],
                "stream": receipt["stream"],
                "gates": receipt["gates"],
                "cleanup": receipt["cleanup"],
                "receipt": receipt["receipt"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
