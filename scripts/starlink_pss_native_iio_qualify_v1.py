#!/usr/bin/env python3
"""Replay-qualify native-IIO PSS trajectories and an on/control/on campaign.

This DNM-only verifier never opens a radio. A role analysis binds one complete
120-second RX-only Ethernet receipt and recomputes the frozen PSS trajectory
policy. A campaign binds positive A, off-slice control, and positive B analyses.
It can claim PSS timing only; it never claims SSS or final frame lock.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
from pathlib import Path
from typing import Any

ROLE_SCHEMA = "plutosdr-fw.starlink-pss-native-iio-role-analysis.v1"
CAMPAIGN_SCHEMA = "plutosdr-fw.starlink-pss-native-iio-live-campaign.v1"
RUN_SCHEMA = "plutosdr-fw.starlink-pss-native-iio-map-soak.v1"
RECEIVER_SERIAL = "104000bac4950008230026001b440a003a"
ROLES = ("on_channel_a", "off_slice_control", "on_channel_b")
CONTROL_ROLES = ("noise_control", "off_slice_control")
POSITIVE_ROLES = ("on_channel_a", "on_channel_b")
EXPECTED_FIRMWARE = {
    30: "starlink-pss30-iio-v1-dnm",
    60: "starlink-pss-iio-v5-dnm",
}
FRAME_SAMPLES = 20_000
MAP_SPAN = 1_280_000
MAP_CHUNKS = 200
DRIFT_BANK = (-12, -8, -4, 0, 4, 8, 12)
POLICY = {
    "minimum_candidate_windows": 32,
    "minimum_peak_to_median": 1.15,
    "minimum_robust_z": 6.0,
    "minimum_positive_pass_fraction": 0.80,
    "minimum_positive_consecutive_track_windows": 8,
    "phase_residual_tolerance_samples": 16,
    "drift_change_tolerance_bins_per_64_frames": 8,
    "maximum_negative_pass_fraction": 0.05,
    "maximum_negative_consecutive_track_windows": 1,
    "minimum_positive_to_negative_median_ratio": 1.10,
    "minimum_off_slice_separation_hz": 30_000_000,
}


class QualificationError(RuntimeError):
    """One retained receipt or qualification claim violates the contract."""


def _load(path: Path, *, label: str) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise QualificationError(f"{label} contains duplicate key {key!r}")
            value[key] = item
        return value

    try:
        value = json.loads(path.read_text(), object_pairs_hook=no_duplicates)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise QualificationError(f"{label} is not readable strict JSON") from error
    if not isinstance(value, dict):
        raise QualificationError(f"{label} is not a JSON object")
    return value


def _identity(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    payload = resolved.read_bytes()
    return {
        "path": str(resolved),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _write_new(path: Path, value: dict[str, Any]) -> dict[str, Any]:
    resolved = path.expanduser().absolute()
    parent = resolved.parent
    if not parent.is_dir() or resolved.exists():
        raise QualificationError("output parent must exist and output must be absent")
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    descriptor = os.open(resolved, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        resolved.unlink(missing_ok=True)
        raise
    return _identity(resolved)


def _integer(value: Any, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise QualificationError(f"{label} is not an integer >= {minimum}")
    return value


def _number(
    value: Any,
    *,
    label: str,
    minimum: float = 0.0,
    allow_positive_infinity: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QualificationError(f"{label} is not numeric")
    result = float(value)
    if result < minimum or (
        not math.isfinite(result)
        and not (allow_positive_infinity and result == math.inf)
    ):
        raise QualificationError(f"{label} is outside its numeric contract")
    return result


def _signed_circular_delta(current: int, previous: int) -> int:
    return (current - previous + FRAME_SAMPLES // 2) % FRAME_SAMPLES - (
        FRAME_SAMPLES // 2
    )


def _validate_window(
    window: dict[str, Any],
    *,
    ordinal: int,
    first_generation: int,
    first_start: int,
    rate_msps: int,
) -> None:
    phase = _integer(window.get("phase_bin"), label="phase bin")
    drift = window.get("drift_bins_per_64_frames")
    reference_generation = _integer(
        window.get("reference_generation"), label="reference generation", minimum=1
    )
    newest_generation = _integer(
        window.get("newest_generation"), label="newest generation", minimum=1
    )
    reference_start = _integer(
        window.get("reference_start_index_canonical"), label="reference start"
    )
    newest_start = _integer(
        window.get("newest_start_index_canonical"), label="newest start"
    )
    candidate = _integer(
        window.get("candidate_start_index_canonical"), label="candidate start"
    )
    source_candidate = _integer(
        window.get("candidate_start_index_source_center"), label="source candidate"
    )
    if (
        phase >= FRAME_SAMPLES
        or drift not in DRIFT_BANK
        or reference_generation != first_generation + ordinal
        or newest_generation != reference_generation + 2
        or reference_start != first_start + ordinal * MAP_SPAN
        or newest_start != reference_start + 2 * MAP_SPAN
        or candidate != reference_start + phase
        or source_candidate != candidate * (rate_msps // 15)
    ):
        raise QualificationError(f"coarse window {ordinal} timing identity is invalid")
    expected_period = FRAME_SAMPLES + drift / 64
    canonical_period = _number(
        window.get("estimated_frame_period_canonical_samples"),
        label="canonical period",
    )
    source_period = _number(
        window.get("estimated_frame_period_source_samples"), label="source period"
    )
    if canonical_period != expected_period or source_period != expected_period * (
        rate_msps // 15
    ):
        raise QualificationError(f"coarse window {ordinal} period scaling is invalid")
    for key in ("combined_score", "combined_median", "median_absolute_deviation"):
        _number(window.get(key), label=key.replace("_", " "))
    for key in ("peak_to_median", "robust_z"):
        _number(
            window.get(key),
            label=key.replace("_", " "),
            allow_positive_infinity=True,
        )


def trajectory_metrics(windows: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the frozen M3/M4 instantaneous and timing-track policy."""

    if not windows:
        raise QualificationError("trajectory contains no candidate windows")
    passes = [
        window["peak_to_median"] >= POLICY["minimum_peak_to_median"]
        and window["robust_z"] >= POLICY["minimum_robust_z"]
        for window in windows
    ]
    longest = 0
    run = 0
    residuals: list[int] = []
    for index, (window, passed) in enumerate(zip(windows, passes, strict=True)):
        if not passed:
            run = 0
            continue
        if index == 0 or not passes[index - 1]:
            run = 1
        else:
            previous = windows[index - 1]
            observed_delta = _signed_circular_delta(
                window["phase_bin"], previous["phase_bin"]
            )
            residual = _signed_circular_delta(
                observed_delta, previous["drift_bins_per_64_frames"]
            )
            residuals.append(residual)
            consistent = (
                abs(residual) <= POLICY["phase_residual_tolerance_samples"]
                and abs(
                    window["drift_bins_per_64_frames"]
                    - previous["drift_bins_per_64_frames"]
                )
                <= POLICY["drift_change_tolerance_bins_per_64_frames"]
            )
            run = run + 1 if consistent else 1
        longest = max(longest, run)
    count = len(windows)
    passing = sum(passes)
    pass_fraction = passing / count
    enough = count >= POLICY["minimum_candidate_windows"]
    positive = (
        enough
        and pass_fraction >= POLICY["minimum_positive_pass_fraction"]
        and longest >= POLICY["minimum_positive_consecutive_track_windows"]
    )
    negative = (
        enough
        and pass_fraction <= POLICY["maximum_negative_pass_fraction"]
        and longest <= POLICY["maximum_negative_consecutive_track_windows"]
    )
    return {
        "candidate_windows": count,
        "passing_windows": passing,
        "pass_fraction": pass_fraction,
        "longest_consecutive_track_windows": longest,
        "median_peak_to_median": statistics.median(
            window["peak_to_median"] for window in windows
        ),
        "maximum_peak_to_median": max(window["peak_to_median"] for window in windows),
        "median_robust_z": statistics.median(window["robust_z"] for window in windows),
        "maximum_robust_z": max(window["robust_z"] for window in windows),
        "median_drift_bins_per_64_frames": statistics.median(
            window["drift_bins_per_64_frames"] for window in windows
        ),
        "maximum_absolute_phase_residual_samples": (
            None if not residuals else max(abs(value) for value in residuals)
        ),
        "minimum_window_count_met": enough,
        "positive_track": positive,
        "negative_control": negative,
        "classification": (
            "positive_track"
            if positive
            else "negative_control"
            if negative
            else "ambiguous"
        ),
    }


def _validate_run(
    receipt: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rate_msps = _integer(receipt.get("rate_msps"), label="rate", minimum=1)
    receiver = receipt.get("receiver")
    stream = receipt.get("stream")
    gates = receipt.get("gates")
    cleanup = receipt.get("cleanup")
    coefficient = receipt.get("coefficient")
    if (
        receipt.get("schema") != RUN_SCHEMA
        or receipt.get("outcome") != "pass"
        or receipt.get("persistent_write") is not False
        or receipt.get("transmitter_opened") is not False
        or rate_msps not in EXPECTED_FIRMWARE
        or receipt.get("sample_rate_hz") != rate_msps * 1_000_000
        or receipt.get("requested_duration_seconds") != 120.0
        or not isinstance(receiver, dict)
        or receiver.get("serial") != RECEIVER_SERIAL
        or receiver.get("transport") != "ethernet"
        or receiver.get("uri") != "ip:192.168.1.17"
        or receiver.get("firmware") != EXPECTED_FIRMWARE[rate_msps]
        or not isinstance(stream, dict)
        or not isinstance(gates, dict)
        or not gates
        or any(value is not True for value in gates.values())
        or not isinstance(cleanup, dict)
        or cleanup.get("verified") is not True
        or cleanup.get("errors") != []
        or cleanup.get("rx_restored") != receiver.get("original")
        or not isinstance(coefficient, dict)
        or not isinstance(coefficient.get("path"), str)
        or not Path(coefficient["path"]).is_absolute()
        or not isinstance(coefficient.get("sha256"), str)
        or len(coefficient["sha256"]) != 64
        or any(
            character not in "0123456789abcdef" for character in coefficient["sha256"]
        )
    ):
        raise QualificationError(
            "native-IIO run receipt violates its live role contract"
        )
    _integer(coefficient.get("generation"), label="coefficient generation", minimum=1)
    coefficient_path = Path(coefficient["path"])
    try:
        coefficient_sha256 = hashlib.sha256(coefficient_path.read_bytes()).hexdigest()
    except OSError as error:
        raise QualificationError("native-IIO coefficient is not readable") from error
    if coefficient_sha256 != coefficient["sha256"]:
        raise QualificationError("native-IIO coefficient changed after acquisition")
    requested_lo = _integer(receiver.get("requested_lo_hz"), label="requested LO")
    selected = receiver.get("selected")
    if (
        not 70_000_000 <= requested_lo <= 6_000_000_000
        or not isinstance(selected, dict)
        or selected.get("lo") != requested_lo
        or selected.get("phy_rate") != rate_msps * 1_000_000
        or selected.get("adc_rate") != rate_msps * 1_000_000
        or selected.get("lo_powerdown") != 0
    ):
        raise QualificationError("native-IIO run receiver selection is invalid")
    elapsed = _number(stream.get("elapsed_seconds"), label="elapsed seconds")
    map_count = _integer(stream.get("complete_maps"), label="complete maps")
    window_count = _integer(stream.get("coarse_window_count"), label="coarse windows")
    windows = stream.get("coarse_windows")
    counters = stream.get("counters")
    map_digest = stream.get("map_digest_sha256")
    if (
        elapsed < 120.0
        or map_count < 1_404
        or window_count != map_count - 2
        or not isinstance(windows, list)
        or len(windows) != window_count
        or not all(isinstance(window, dict) for window in windows)
        or not isinstance(counters, dict)
        or stream.get("logical_map_bytes") != map_count * FRAME_SAMPLES * 2
        or stream.get("transport_bytes") != map_count * MAP_CHUNKS * 256
        or not isinstance(map_digest, str)
        or len(map_digest) != 64
        or any(character not in "0123456789abcdef" for character in map_digest)
        or counters.get("maps_delivered") != map_count
        or counters.get("chunks_delivered") != map_count * MAP_CHUNKS
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
        raise QualificationError("native-IIO run trajectory accounting is invalid")
    first_maps = stream.get("first_maps")
    if (
        not isinstance(first_maps, list)
        or not first_maps
        or not isinstance(first_maps[0], dict)
    ):
        raise QualificationError("native-IIO run lacks its first map identity")
    first_generation = _integer(
        first_maps[0].get("generation"), label="first map generation", minimum=1
    )
    first_start = _integer(
        first_maps[0].get("canonical_start_index"), label="first map start"
    )
    for ordinal, window in enumerate(windows):
        _validate_window(
            window,
            ordinal=ordinal,
            first_generation=first_generation,
            first_start=first_start,
            rate_msps=rate_msps,
        )
    return windows, {
        "serial": RECEIVER_SERIAL,
        "rate_msps": rate_msps,
        "firmware": receiver["firmware"],
        "requested_lo_hz": requested_lo,
        "coefficient": coefficient,
        "elapsed_seconds": elapsed,
        "complete_maps": map_count,
        "coarse_window_count": window_count,
        "map_digest_sha256": map_digest,
    }


def analyze_role(*, role: str, receipt_path: Path, output: Path) -> dict[str, Any]:
    if role not in (*ROLES, "noise_control"):
        raise QualificationError("role is outside the native live role inventory")
    receipt = _load(receipt_path, label="native-IIO run receipt")
    windows, source = _validate_run(receipt)
    metrics = trajectory_metrics(windows)
    expected = "positive_track" if role in POSITIVE_ROLES else "negative_control"
    matches = metrics["classification"] == expected
    analysis = {
        "schema": ROLE_SCHEMA,
        "schema_version": 1,
        "outcome": "pass" if matches else "unqualified",
        "hardware_accessed": False,
        "persistent_write": False,
        "source_receipt": _identity(receipt_path),
        "role": role,
        "expected_classification": expected,
        "classification_matches_role": matches,
        "source": source,
        "policy": POLICY,
        "metrics": metrics,
        "pss_detected": role in POSITIVE_ROLES and matches,
        "sss_detected": False,
        "frame_lock_claim": False,
    }
    identity = _write_new(output, analysis)
    return {"analysis": identity, **analysis}


def _validate_role_analysis(
    path: Path, *, expected_role: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    analysis = _load(path, label=f"{expected_role} role analysis")
    if (
        analysis.get("schema") != ROLE_SCHEMA
        or analysis.get("schema_version") != 1
        or analysis.get("outcome") != "pass"
        or analysis.get("hardware_accessed") is not False
        or analysis.get("persistent_write") is not False
        or analysis.get("role") != expected_role
        or analysis.get("classification_matches_role") is not True
        or analysis.get("policy") != POLICY
        or analysis.get("pss_detected") is not (expected_role in POSITIVE_ROLES)
        or analysis.get("sss_detected") is not False
        or analysis.get("frame_lock_claim") is not False
    ):
        raise QualificationError(
            f"{expected_role} analysis is not a passing exact role"
        )
    source_receipt = analysis.get("source_receipt")
    if (
        not isinstance(source_receipt, dict)
        or _identity(Path(str(source_receipt.get("path")))) != source_receipt
    ):
        raise QualificationError(
            f"{expected_role} source receipt changed after analysis"
        )
    receipt = _load(Path(source_receipt["path"]), label=f"{expected_role} run receipt")
    windows, source = _validate_run(receipt)
    if analysis.get("source") != source or analysis.get(
        "metrics"
    ) != trajectory_metrics(windows):
        raise QualificationError(f"{expected_role} analysis differs from replay")
    return analysis, _identity(path)


def qualify_campaign(
    *, on_a: Path, control: Path, on_b: Path, output: Path
) -> dict[str, Any]:
    paths = (on_a, control, on_b)
    analyses_and_ids = tuple(
        _validate_role_analysis(path, expected_role=role)
        for path, role in zip(paths, ROLES, strict=True)
    )
    analyses = tuple(item[0] for item in analyses_and_ids)
    identities = tuple(item[1] for item in analyses_and_ids)
    sources = tuple(item["source"] for item in analyses)
    if (
        len({source["serial"] for source in sources}) != 1
        or len({source["rate_msps"] for source in sources}) != 1
        or len(
            {json.dumps(source["coefficient"], sort_keys=True) for source in sources}
        )
        != 1
        or sources[0]["requested_lo_hz"] != sources[2]["requested_lo_hz"]
        or abs(sources[1]["requested_lo_hz"] - sources[0]["requested_lo_hz"])
        < POLICY["minimum_off_slice_separation_hz"]
    ):
        raise QualificationError(
            "live campaign source identity or frequency geometry differs"
        )
    contrast = min(
        analyses[0]["metrics"]["median_peak_to_median"],
        analyses[2]["metrics"]["median_peak_to_median"],
    ) / max(analyses[1]["metrics"]["median_peak_to_median"], sys.float_info.min)
    qualified = contrast >= POLICY["minimum_positive_to_negative_median_ratio"]
    campaign = {
        "schema": CAMPAIGN_SCHEMA,
        "schema_version": 1,
        "outcome": "pass" if qualified else "unqualified",
        "hardware_accessed": False,
        "persistent_write": False,
        "role_analyses": dict(zip(ROLES, identities, strict=True)),
        "serial": sources[0]["serial"],
        "rate_msps": sources[0]["rate_msps"],
        "on_channel_lo_hz": sources[0]["requested_lo_hz"],
        "off_slice_lo_hz": sources[1]["requested_lo_hz"],
        "positive_to_control_median_ratio": contrast,
        "policy": POLICY,
        "pss_detected": qualified,
        "timing_trajectory_qualified": qualified,
        "sss_detected": False,
        "frame_lock_claim": False,
    }
    identity = _write_new(output, campaign)
    return {"campaign": identity, **campaign}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    role = commands.add_parser("role", help="replay one 120-second trajectory receipt")
    role.add_argument("--role", choices=(*ROLES, "noise_control"), required=True)
    role.add_argument("--receipt", type=Path, required=True)
    role.add_argument("--output", type=Path, required=True)
    campaign = commands.add_parser("campaign", help="qualify positive/control/positive")
    campaign.add_argument("--on-a", type=Path, required=True)
    campaign.add_argument("--control", type=Path, required=True)
    campaign.add_argument("--on-b", type=Path, required=True)
    campaign.add_argument("--output", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "role":
            result = analyze_role(
                role=arguments.role,
                receipt_path=arguments.receipt,
                output=arguments.output,
            )
        else:
            result = qualify_campaign(
                on_a=arguments.on_a,
                control=arguments.control,
                on_b=arguments.on_b,
                output=arguments.output,
            )
    except (OSError, ValueError, QualificationError) as error:
        print(json.dumps({"outcome": "failed", "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
