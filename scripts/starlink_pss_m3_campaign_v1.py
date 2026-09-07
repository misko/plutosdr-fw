#!/usr/bin/env python3
"""Seal and qualify the positive/mute/positive 15 MS/s cabled PSS campaign.

This command never accesses hardware.  ``plan`` freezes the physical-fixture
declaration, waveform, three v7 receiver-monitor plans, future stimulus
receipt paths, and decision policy before data collection.  ``qualify``
validates the completed receipts and writes one offline M3 result.  A separate
transmitter controller is intentionally required to create the stimulus-state
receipts; this script cannot key a transmitter.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import statistics
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.starlink_pss_monitor_probe_v1 as monitor_v1
import scripts.starlink_pss_monitor_probe_v2 as monitor_v2
from tools.generate_starlink_pss15_cabled_waveform import (
    FRAME_SAMPLES,
    MINIMUM_EFFECTIVE_ATTENUATION_DB,
    SAMPLE_RATE_HZ,
)
from tools.generate_starlink_pss15_cabled_waveform import (
    SCHEMA as WAVEFORM_SCHEMA,
)

PLAN_SCHEMA = "plutosdr-fw.starlink-pss-m3-campaign-plan.v1"
RECEIPT_SCHEMA = "plutosdr-fw.starlink-pss-m3-campaign-receipt.v1"
FIXTURE_SCHEMA = "plutosdr-fw.starlink-pss15-cabled-fixture.v1"
STIMULUS_SCHEMA = "plutosdr-fw.starlink-pss15-cabled-stimulus-receipt.v1"
CLAIM_SCOPE = "cabled_pss_acquisition_and_timing_only"
RECEIVER_SERIAL = monitor_v1.probe_v1.ALLOCATED_SERIAL
EXPECTED_FIRMWARE = monitor_v2.EXPECTED_FIRMWARE
RUNTIME_TARGET = monitor_v1.probe_v8.RUNTIME_TARGET
MINIMUM_DWELL_MS = 5_000
MAXIMUM_TX_CLOCK_OFFSET_PPM = 100

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
}

IDENTITY_FIELDS = {"path", "bytes", "sha256"}
FIXTURE_FIELDS = {
    "schema",
    "schema_version",
    "created_at",
    "receiver_serial",
    "transmitter_serial",
    "direct_coaxial_path_verified",
    "antenna_connected",
    "over_the_air_authorized",
    "tx_port",
    "rx_port",
    "attenuation_components",
    "effective_attenuation_db",
    "cable_path_description",
    "operator_attestation",
}
FIXTURE_ATTESTATION = "direct cabled path verified; no antenna is connected"
STIMULUS_FIELDS = {
    "schema",
    "schema_version",
    "receipt_id",
    "started_at",
    "completed_at",
    "outcome",
    "fixture_declaration",
    "transmitter_serial",
    "state",
    "hardware_accessed",
    "persistent_write",
    "cabled_only",
    "over_the_air_transmission",
    "waveform_evidence",
    "waveform_binary",
    "requested_sample_rate_hz",
    "readback_sample_rate_hz",
    "cyclic_buffer_active",
    "tx_lo_hz",
    "tx_hardwaregain_db",
    "tx_buffer_disabled",
    "tx_lo_powerdown",
    "cleanup_verified",
    "error",
}
DWELL_FIELDS = {
    "role",
    "expected_stimulus_state",
    "monitor_plan",
    "monitor_receipt_path",
    "stimulus_receipt_path",
}
PLAN_FIELDS = {
    "schema",
    "schema_version",
    "plan_id",
    "created_at",
    "hardware_accessed",
    "persistent_write",
    "do_not_merge",
    "receiver_serial",
    "transmitter_serial",
    "runtime_target",
    "expected_firmware",
    "transmitter_sample_rate_hz",
    "transmitter_lo_hz",
    "transmitter_hardwaregain_db",
    "claim_scope",
    "waveform_evidence",
    "waveform_binary",
    "fixture_declaration",
    "policy",
    "dwells",
    "final_mute_stimulus_receipt_path",
    "receipt_path",
    "pss_detected",
    "sss_detected",
    "frame_lock_claim",
}

ProbeError = monitor_v1.ProbeError
probe_v1 = monitor_v1.probe_v1


def _identity(path: Path, *, label: str) -> dict[str, Any]:
    return probe_v1._identity(path.absolute(), label=label)


def _load(path: Path, *, label: str) -> dict[str, Any]:
    return probe_v1._load_private_json(path.absolute(), label=label)


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
        or probe_v1.HEX_64.fullmatch(value["sha256"]) is None
    ):
        raise ProbeError(f"M3 {label} identity is invalid")


def _parse_time(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise ProbeError(f"M3 {label} timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ProbeError(f"M3 {label} timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise ProbeError(f"M3 {label} timestamp lacks a timezone")
    return parsed


def _validate_fixture(fixture: dict[str, Any]) -> None:
    attenuation = fixture.get("effective_attenuation_db")
    components = fixture.get("attenuation_components")
    transmitter = fixture.get("transmitter_serial")
    if (
        set(fixture) != FIXTURE_FIELDS
        or fixture.get("schema") != FIXTURE_SCHEMA
        or fixture.get("schema_version") != 1
        or fixture.get("receiver_serial") != RECEIVER_SERIAL
        or not isinstance(transmitter, str)
        or not 8 <= len(transmitter) <= 64
        or transmitter == RECEIVER_SERIAL
        or fixture.get("direct_coaxial_path_verified") is not True
        or fixture.get("antenna_connected") is not False
        or fixture.get("over_the_air_authorized") is not False
        or not isinstance(fixture.get("tx_port"), str)
        or not fixture["tx_port"]
        or not isinstance(fixture.get("rx_port"), str)
        or not fixture["rx_port"]
        or not isinstance(components, list)
        or not components
        or not all(isinstance(item, str) and item for item in components)
        or not isinstance(attenuation, (int, float))
        or isinstance(attenuation, bool)
        or not math.isfinite(attenuation)
        or not MINIMUM_EFFECTIVE_ATTENUATION_DB <= attenuation <= 120
        or not isinstance(fixture.get("cable_path_description"), str)
        or not fixture["cable_path_description"]
        or fixture.get("operator_attestation") != FIXTURE_ATTESTATION
    ):
        raise ProbeError("M3 fixture declaration violates the cabled-only contract")
    _parse_time(fixture.get("created_at"), label="fixture created_at")


def _load_waveform_evidence(
    evidence_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    evidence = _load(evidence_path, label="M3 waveform evidence")
    waveform = evidence.get("waveform")
    if (
        evidence.get("schema") != WAVEFORM_SCHEMA
        or evidence.get("schema_version") != 1
        or evidence.get("claim_scope") != "deterministic_cabled_rf_stimulus_only"
        or evidence.get("offline_generation_only") is not True
        or evidence.get("cabled_only") is not True
        or evidence.get("over_the_air_authorized") is not False
        or evidence.get("transmitter_configuration_included") is not False
        or evidence.get("minimum_effective_attenuation_db")
        != MINIMUM_EFFECTIVE_ATTENUATION_DB
        or evidence.get("sample_rate_hz") != SAMPLE_RATE_HZ
        or evidence.get("frame_samples") != FRAME_SAMPLES
        or evidence.get("cyclic") is not True
        or not isinstance(waveform, dict)
        or set(waveform) != {"name", "bytes", "sha256"}
        or waveform.get("name") is None
        or Path(str(waveform["name"])).name != waveform["name"]
        or waveform.get("bytes") != FRAME_SAMPLES * 4
        or not isinstance(waveform.get("sha256"), str)
        or probe_v1.HEX_64.fullmatch(waveform["sha256"]) is None
    ):
        raise ProbeError("M3 waveform evidence violates its generated contract")
    waveform_path = evidence_path.absolute().parent / waveform["name"]
    waveform_identity = _identity(waveform_path, label="M3 waveform binary")
    if (
        waveform_identity["bytes"] != waveform["bytes"]
        or waveform_identity["sha256"] != waveform["sha256"]
    ):
        raise ProbeError("M3 waveform binary differs from its evidence")
    return evidence, _identity(evidence_path, label="M3 waveform evidence"), waveform_identity


def _validate_monitor_plan(plan: dict[str, Any]) -> None:
    monitor_v2._validate_plan(plan)
    if plan["duration_ms"] < MINIMUM_DWELL_MS:
        raise ProbeError(f"M3 monitor dwell must be at least {MINIMUM_DWELL_MS} ms")


def _validate_plan(plan: dict[str, Any]) -> None:
    if set(plan) != PLAN_FIELDS:
        raise ProbeError("M3 campaign plan fields differ from v1")
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan.get("schema_version") != 1
        or not isinstance(plan.get("plan_id"), str)
        or len(plan["plan_id"]) != 32
        or any(character not in "0123456789abcdef" for character in plan["plan_id"])
        or plan.get("hardware_accessed") is not False
        or plan.get("persistent_write") is not False
        or plan.get("do_not_merge") is not True
        or plan.get("receiver_serial") != RECEIVER_SERIAL
        or not isinstance(plan.get("transmitter_serial"), str)
        or plan["transmitter_serial"] == RECEIVER_SERIAL
        or plan.get("runtime_target") != RUNTIME_TARGET
        or plan.get("expected_firmware") != EXPECTED_FIRMWARE
        or not isinstance(plan.get("transmitter_sample_rate_hz"), int)
        or isinstance(plan.get("transmitter_sample_rate_hz"), bool)
        or abs(plan["transmitter_sample_rate_hz"] - SAMPLE_RATE_HZ)
        > SAMPLE_RATE_HZ * MAXIMUM_TX_CLOCK_OFFSET_PPM // 1_000_000
        or not isinstance(plan.get("transmitter_lo_hz"), int)
        or isinstance(plan.get("transmitter_lo_hz"), bool)
        or not 70_000_000 <= plan["transmitter_lo_hz"] <= 6_000_000_000
        or not isinstance(plan.get("transmitter_hardwaregain_db"), (int, float))
        or isinstance(plan.get("transmitter_hardwaregain_db"), bool)
        or not math.isfinite(plan["transmitter_hardwaregain_db"])
        or not -89.75 <= plan["transmitter_hardwaregain_db"] <= -10.0
        or plan.get("claim_scope") != CLAIM_SCOPE
        or plan.get("policy") != POLICY
        or plan.get("pss_detected") is not False
        or plan.get("sss_detected") is not False
        or plan.get("frame_lock_claim") is not False
        or not isinstance(plan.get("receipt_path"), str)
        or not Path(plan["receipt_path"]).is_absolute()
        or not isinstance(plan.get("final_mute_stimulus_receipt_path"), str)
        or not Path(plan["final_mute_stimulus_receipt_path"]).is_absolute()
    ):
        raise ProbeError("M3 campaign plan values violate the v1 contract")
    _parse_time(plan.get("created_at"), label="plan created_at")
    for label in ("waveform_evidence", "waveform_binary", "fixture_declaration"):
        _validate_identity(plan.get(label), label=label)
    dwells = plan.get("dwells")
    roles = ("positive_a", "negative_muted", "positive_b")
    states = ("active", "muted", "active")
    if not isinstance(dwells, list) or len(dwells) != 3:
        raise ProbeError("M3 campaign must contain positive/mute/positive dwells")
    monitor_receipts: set[str] = set()
    stimulus_receipts: set[str] = set()
    for dwell, role, state in zip(dwells, roles, states, strict=True):
        if (
            not isinstance(dwell, dict)
            or set(dwell) != DWELL_FIELDS
            or dwell.get("role") != role
            or dwell.get("expected_stimulus_state") != state
            or not isinstance(dwell.get("monitor_receipt_path"), str)
            or not Path(dwell["monitor_receipt_path"]).is_absolute()
            or not isinstance(dwell.get("stimulus_receipt_path"), str)
            or not Path(dwell["stimulus_receipt_path"]).is_absolute()
        ):
            raise ProbeError(f"M3 {role} dwell violates the v1 contract")
        _validate_identity(dwell.get("monitor_plan"), label=f"{role} monitor plan")
        monitor_receipts.add(dwell["monitor_receipt_path"])
        stimulus_receipts.add(dwell["stimulus_receipt_path"])
    if len(monitor_receipts) != 3 or len(stimulus_receipts) != 3:
        raise ProbeError("M3 campaign receipt paths must be distinct")
    if plan["final_mute_stimulus_receipt_path"] in stimulus_receipts:
        raise ProbeError("M3 final mute receipt path must be distinct")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    fixture = commands.add_parser(
        "fixture", help="write one explicit physical cabled-fixture declaration"
    )
    fixture.add_argument("--transmitter-serial", required=True)
    fixture.add_argument("--tx-port", required=True)
    fixture.add_argument("--rx-port", required=True)
    fixture.add_argument(
        "--attenuation-component", action="append", required=True
    )
    fixture.add_argument("--effective-attenuation-db", type=float, required=True)
    fixture.add_argument("--cable-path-description", required=True)
    fixture.add_argument("--attest", required=True)
    fixture.add_argument("--output", type=Path, required=True)
    plan = commands.add_parser("plan", help="seal an offline M3 campaign plan")
    plan.add_argument("--waveform-evidence", type=Path, required=True)
    plan.add_argument("--fixture-declaration", type=Path, required=True)
    plan.add_argument("--transmitter-sample-rate-hz", type=int, required=True)
    plan.add_argument("--transmitter-lo-hz", type=int, required=True)
    plan.add_argument("--transmitter-hardwaregain-db", type=float, required=True)
    for role in ("positive-a", "negative", "positive-b"):
        plan.add_argument(f"--{role}-monitor-plan", type=Path, required=True)
        plan.add_argument(f"--{role}-stimulus-receipt", type=Path, required=True)
    plan.add_argument("--final-mute-stimulus-receipt", type=Path, required=True)
    plan.add_argument("--receipt", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    qualify = commands.add_parser("qualify", help="evaluate sealed completed receipts")
    qualify.add_argument("--plan", type=Path, required=True)
    qualify.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify", help="verify an M3 qualification receipt")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    return result


def build_fixture(args: Any) -> dict[str, Any]:
    if args.attest != FIXTURE_ATTESTATION:
        raise ProbeError(f"fixture attestation must be exactly {FIXTURE_ATTESTATION!r}")
    fixture = {
        "schema": FIXTURE_SCHEMA,
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "receiver_serial": RECEIVER_SERIAL,
        "transmitter_serial": args.transmitter_serial,
        "direct_coaxial_path_verified": True,
        "antenna_connected": False,
        "over_the_air_authorized": False,
        "tx_port": args.tx_port,
        "rx_port": args.rx_port,
        "attenuation_components": args.attenuation_component,
        "effective_attenuation_db": args.effective_attenuation_db,
        "cable_path_description": args.cable_path_description,
        "operator_attestation": args.attest,
    }
    _validate_fixture(fixture)
    identity = probe_v1._write_new_private(args.output, fixture)
    return {
        "verdict": "PASS_OFFLINE_M3_FIXTURE_DECLARATION_ONLY",
        "hardware_accessed": False,
        "over_the_air_authorized": False,
        "fixture": identity,
    }


def build_plan(args: Any) -> dict[str, Any]:
    evidence_path = args.waveform_evidence.absolute()
    _evidence, evidence_identity, waveform_identity = _load_waveform_evidence(
        evidence_path
    )
    fixture_path = args.fixture_declaration.absolute()
    fixture = _load(fixture_path, label="M3 fixture declaration")
    _validate_fixture(fixture)

    monitor_paths = (
        args.positive_a_monitor_plan.absolute(),
        args.negative_monitor_plan.absolute(),
        args.positive_b_monitor_plan.absolute(),
    )
    stimulus_paths = (
        args.positive_a_stimulus_receipt.absolute(),
        args.negative_stimulus_receipt.absolute(),
        args.positive_b_stimulus_receipt.absolute(),
    )
    roles = ("positive_a", "negative_muted", "positive_b")
    states = ("active", "muted", "active")
    monitor_plans: list[dict[str, Any]] = []
    dwells: list[dict[str, Any]] = []
    for path, stimulus_path, role, state in zip(
        monitor_paths, stimulus_paths, roles, states, strict=True
    ):
        selected = _load(path, label=f"M3 {role} monitor plan")
        _validate_monitor_plan(selected)
        if Path(selected["receipt_path"]).exists():
            raise ProbeError(f"M3 {role} monitor receipt already exists")
        if stimulus_path.exists():
            raise ProbeError(f"M3 {role} stimulus receipt already exists")
        monitor_plans.append(selected)
        dwells.append(
            {
                "role": role,
                "expected_stimulus_state": state,
                "monitor_plan": _identity(path, label=f"M3 {role} monitor plan"),
                "monitor_receipt_path": selected["receipt_path"],
                "stimulus_receipt_path": str(stimulus_path),
            }
        )
    if len({selected["plan_id"] for selected in monitor_plans}) != 3:
        raise ProbeError("M3 monitor plans must have distinct plan IDs")
    for field in ("duration_ms", "probe_plan", "controller_binary"):
        if any(selected[field] != monitor_plans[0][field] for selected in monitor_plans[1:]):
            raise ProbeError(f"M3 monitor plans differ in sealed {field}")

    final_mute = args.final_mute_stimulus_receipt.absolute()
    for future in (*stimulus_paths, final_mute, args.receipt.absolute(), args.output.absolute()):
        probe_v1._require_new_private_output(future)
    plan = {
        "schema": PLAN_SCHEMA,
        "schema_version": 1,
        "plan_id": uuid.uuid4().hex,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "hardware_accessed": False,
        "persistent_write": False,
        "do_not_merge": True,
        "receiver_serial": RECEIVER_SERIAL,
        "transmitter_serial": fixture["transmitter_serial"],
        "runtime_target": RUNTIME_TARGET,
        "expected_firmware": EXPECTED_FIRMWARE,
        "transmitter_sample_rate_hz": args.transmitter_sample_rate_hz,
        "transmitter_lo_hz": args.transmitter_lo_hz,
        "transmitter_hardwaregain_db": args.transmitter_hardwaregain_db,
        "claim_scope": CLAIM_SCOPE,
        "waveform_evidence": evidence_identity,
        "waveform_binary": waveform_identity,
        "fixture_declaration": _identity(
            fixture_path, label="M3 fixture declaration"
        ),
        "policy": POLICY,
        "dwells": dwells,
        "final_mute_stimulus_receipt_path": str(final_mute),
        "receipt_path": str(args.receipt.absolute()),
        "pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
    }
    _validate_plan(plan)
    identity = probe_v1._write_new_private(args.output, plan)
    return {
        "verdict": "PASS_OFFLINE_M3_CAMPAIGN_PLAN_ONLY",
        "hardware_accessed": False,
        "persistent_write": False,
        "plan": identity,
        "next_gate": "create sealed stimulus receipts and execute positive/mute/positive receiver dwells",
    }


def _validate_stimulus(
    receipt: dict[str, Any],
    *,
    expected_state: str,
    plan: dict[str, Any],
) -> None:
    if set(receipt) != STIMULUS_FIELDS:
        raise ProbeError("M3 stimulus receipt fields differ from v1")
    gain = receipt.get("tx_hardwaregain_db")
    readback = receipt.get("readback_sample_rate_hz")
    if (
        receipt.get("schema") != STIMULUS_SCHEMA
        or receipt.get("schema_version") != 1
        or not isinstance(receipt.get("receipt_id"), str)
        or len(receipt["receipt_id"]) != 32
        or receipt.get("outcome") != "pass"
        or receipt.get("fixture_declaration") != plan["fixture_declaration"]
        or receipt.get("transmitter_serial") != plan["transmitter_serial"]
        or receipt.get("state") != expected_state
        or receipt.get("hardware_accessed") is not True
        or receipt.get("persistent_write") is not False
        or receipt.get("cabled_only") is not True
        or receipt.get("over_the_air_transmission") is not False
        or not isinstance(gain, (int, float))
        or isinstance(gain, bool)
        or not math.isfinite(gain)
        or not -89.75 <= gain <= -10.0
        or receipt.get("error") is not None
    ):
        raise ProbeError("M3 stimulus receipt violates its cabled-only contract")
    started = _parse_time(receipt.get("started_at"), label="stimulus started_at")
    completed = _parse_time(receipt.get("completed_at"), label="stimulus completed_at")
    if completed < started:
        raise ProbeError("M3 stimulus receipt timestamps are reversed")
    if expected_state == "active":
        if (
            receipt.get("waveform_evidence") != plan["waveform_evidence"]
            or receipt.get("waveform_binary") != plan["waveform_binary"]
            or receipt.get("requested_sample_rate_hz")
            != plan["transmitter_sample_rate_hz"]
            or not isinstance(readback, int)
            or isinstance(readback, bool)
            or abs(readback - plan["transmitter_sample_rate_hz"])
            > max(2, plan["transmitter_sample_rate_hz"] // 10_000)
            or receipt.get("cyclic_buffer_active") is not True
            or receipt.get("tx_lo_hz") != plan["transmitter_lo_hz"]
            or gain != plan["transmitter_hardwaregain_db"]
            or receipt.get("tx_buffer_disabled") is not False
            or receipt.get("tx_lo_powerdown") is not False
            or receipt.get("cleanup_verified") is not False
        ):
            raise ProbeError("M3 active stimulus receipt lacks a sealed cyclic TX state")
    elif expected_state == "muted":
        if (
            receipt.get("waveform_evidence") is not None
            or receipt.get("waveform_binary") is not None
            or receipt.get("requested_sample_rate_hz") is not None
            or receipt.get("readback_sample_rate_hz") is not None
            or receipt.get("cyclic_buffer_active") is not False
            or receipt.get("tx_lo_hz") is not None
            or gain > -80.0
            or receipt.get("tx_buffer_disabled") is not True
            or receipt.get("tx_lo_powerdown") is not True
            or receipt.get("cleanup_verified") is not True
        ):
            raise ProbeError("M3 muted stimulus receipt does not prove TX shutdown")
    else:
        raise ProbeError("M3 stimulus state is unknown")


def _candidate_passes(record: dict[str, Any], policy: dict[str, Any]) -> bool:
    robust_z = record["robust_z"]
    return (
        isinstance(robust_z, (int, float))
        and not isinstance(robust_z, bool)
        and math.isfinite(robust_z)
        and record["peak_to_median"] is not None
        and record["peak_to_median"] >= policy["minimum_peak_to_median"]
        and robust_z >= policy["minimum_robust_z"]
    )


def _signed_circular_delta(current: int, previous: int) -> int:
    return (current - previous + FRAME_SAMPLES // 2) % FRAME_SAMPLES - (
        FRAME_SAMPLES // 2
    )


def analyze_dwell(
    records: list[dict[str, Any]], policy: dict[str, Any]
) -> dict[str, Any]:
    candidates = records[2:-1]
    if len(candidates) < policy["minimum_candidate_windows"]:
        raise ProbeError("M3 dwell has too few candidate windows")
    passes = [_candidate_passes(record, policy) for record in candidates]
    longest = 0
    run = 0
    residuals: list[int] = []
    for index, (record, passed) in enumerate(zip(candidates, passes, strict=True)):
        if not passed:
            run = 0
            continue
        if index == 0 or not passes[index - 1]:
            run = 1
        else:
            previous = candidates[index - 1]
            observed_delta = _signed_circular_delta(
                record["phase_bin"], previous["phase_bin"]
            )
            residual = _signed_circular_delta(
                observed_delta, previous["drift_bins_per_64_frames"]
            )
            residuals.append(residual)
            consistent = (
                abs(residual) <= policy["phase_residual_tolerance_samples"]
                and abs(
                    record["drift_bins_per_64_frames"]
                    - previous["drift_bins_per_64_frames"]
                )
                <= policy["drift_change_tolerance_bins_per_64_frames"]
            )
            run = run + 1 if consistent else 1
        longest = max(longest, run)
    ratios = [float(record["peak_to_median"]) for record in candidates]
    robust_values = [
        float(record["robust_z"])
        for record in candidates
        if isinstance(record["robust_z"], (int, float))
        and not isinstance(record["robust_z"], bool)
        and math.isfinite(record["robust_z"])
    ]
    drifts = [int(record["drift_bins_per_64_frames"]) for record in candidates]
    return {
        "candidate_windows": len(candidates),
        "passing_windows": sum(passes),
        "pass_fraction": sum(passes) / len(candidates),
        "longest_consecutive_track_windows": longest,
        "median_peak_to_median": statistics.median(ratios),
        "maximum_peak_to_median": max(ratios),
        "median_robust_z": (
            None if not robust_values else statistics.median(robust_values)
        ),
        "median_drift_bins_per_64_frames": statistics.median(drifts),
        "maximum_absolute_phase_residual_samples": (
            None if not residuals else max(abs(value) for value in residuals)
        ),
        "first_passing_phase_bin": next(
            (record["phase_bin"] for record, passed in zip(candidates, passes, strict=True) if passed),
            None,
        ),
        "last_passing_phase_bin": next(
            (
                record["phase_bin"]
                for record, passed in zip(
                    reversed(candidates), reversed(passes), strict=True
                )
                if passed
            ),
            None,
        ),
    }


def _positive_passes(metrics: dict[str, Any], policy: dict[str, Any]) -> bool:
    return (
        metrics["pass_fraction"] >= policy["minimum_positive_pass_fraction"]
        and metrics["longest_consecutive_track_windows"]
        >= policy["minimum_positive_consecutive_track_windows"]
    )


def _negative_passes(metrics: dict[str, Any], policy: dict[str, Any]) -> bool:
    return (
        metrics["pass_fraction"] <= policy["maximum_negative_pass_fraction"]
        and metrics["longest_consecutive_track_windows"]
        <= policy["maximum_negative_consecutive_track_windows"]
    )


def _load_monitor_result(
    dwell: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    plan_path = Path(dwell["monitor_plan"]["path"])
    if _identity(plan_path, label="M3 monitor plan") != dwell["monitor_plan"]:
        raise ProbeError("M3 monitor plan changed after campaign sealing")
    monitor_plan = _load(plan_path, label="M3 monitor plan")
    _validate_monitor_plan(monitor_plan)
    receipt_path = Path(dwell["monitor_receipt_path"])
    monitor_v2.verify_receipt(SimpleNamespace(plan=plan_path, receipt=receipt_path))
    receipt = _load(receipt_path, label="M3 monitor receipt")
    if receipt.get("outcome") != "pass":
        raise ProbeError("M3 monitor receipt did not pass")
    records = receipt.get("measurement", {}).get("monitor_records")
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        raise ProbeError("M3 monitor receipt lacks strict candidate records")
    monitor_v2._validate_monitor_records(records, monitor_plan)
    return monitor_plan, receipt, records


def _ensure_inputs_unchanged(plan: dict[str, Any]) -> None:
    for key, label in (
        ("waveform_evidence", "M3 waveform evidence"),
        ("waveform_binary", "M3 waveform binary"),
        ("fixture_declaration", "M3 fixture declaration"),
    ):
        identity = plan[key]
        if _identity(Path(identity["path"]), label=label) != identity:
            raise ProbeError(f"{label} changed after campaign sealing")
    evidence, evidence_identity, waveform_identity = _load_waveform_evidence(
        Path(plan["waveform_evidence"]["path"])
    )
    if (
        evidence_identity != plan["waveform_evidence"]
        or waveform_identity != plan["waveform_binary"]
        or evidence["waveform"]["sha256"] != waveform_identity["sha256"]
    ):
        raise ProbeError("M3 sealed waveform identities are inconsistent")
    fixture = _load(
        Path(plan["fixture_declaration"]["path"]), label="M3 fixture declaration"
    )
    _validate_fixture(fixture)
    if fixture["transmitter_serial"] != plan["transmitter_serial"]:
        raise ProbeError("M3 fixture transmitter changed after campaign sealing")


def _evaluate_campaign(plan: dict[str, Any]) -> dict[str, Any]:
    """Revalidate all inputs and return the deterministic M3 decision payload."""

    _ensure_inputs_unchanged(plan)
    metrics: dict[str, Any] = {}
    monitor_receipts: dict[str, Any] = {}
    stimulus_receipts: dict[str, Any] = {}
    timeline: list[datetime] = []
    for dwell in plan["dwells"]:
        role = dwell["role"]
        expected_state = dwell["expected_stimulus_state"]
        stimulus_path = Path(dwell["stimulus_receipt_path"])
        stimulus = _load(stimulus_path, label=f"M3 {role} stimulus receipt")
        _validate_stimulus(stimulus, expected_state=expected_state, plan=plan)
        _monitor_plan, monitor_receipt, records = _load_monitor_result(dwell)
        stimulus_completed = _parse_time(
            stimulus["completed_at"], label=f"{role} stimulus completed_at"
        )
        monitor_started = _parse_time(
            monitor_receipt["started_at"], label=f"{role} monitor started_at"
        )
        monitor_completed = _parse_time(
            monitor_receipt["completed_at"], label=f"{role} monitor completed_at"
        )
        if stimulus_completed > monitor_started or monitor_completed < monitor_started:
            raise ProbeError(f"M3 {role} stimulus/monitor timestamps are inconsistent")
        timeline.extend((stimulus_completed, monitor_started, monitor_completed))
        metrics[role] = analyze_dwell(records, plan["policy"])
        monitor_receipts[role] = _identity(
            Path(dwell["monitor_receipt_path"]), label=f"M3 {role} monitor receipt"
        )
        stimulus_receipts[role] = _identity(
            stimulus_path, label=f"M3 {role} stimulus receipt"
        )
    if any(right < left for left, right in itertools.pairwise(timeline)):
        raise ProbeError("M3 positive/mute/positive events are not chronologically ordered")

    final_mute_path = Path(plan["final_mute_stimulus_receipt_path"])
    final_mute = _load(final_mute_path, label="M3 final mute stimulus receipt")
    _validate_stimulus(final_mute, expected_state="muted", plan=plan)
    final_mute_completed = _parse_time(
        final_mute["completed_at"], label="final mute completed_at"
    )
    if final_mute_completed < timeline[-1]:
        raise ProbeError("M3 final mute did not occur after the final positive dwell")

    positive_a = metrics["positive_a"]
    negative = metrics["negative_muted"]
    positive_b = metrics["positive_b"]
    contrast = min(
        positive_a["median_peak_to_median"],
        positive_b["median_peak_to_median"],
    ) / max(negative["median_peak_to_median"], sys.float_info.min)
    passed = (
        _positive_passes(positive_a, plan["policy"])
        and _negative_passes(negative, plan["policy"])
        and _positive_passes(positive_b, plan["policy"])
        and contrast >= plan["policy"]["minimum_positive_to_negative_median_ratio"]
    )
    if not passed:
        raise ProbeError(
            "M3 campaign does not satisfy the frozen positive/mute/positive policy"
        )
    return {
        "monitor_receipts": monitor_receipts,
        "stimulus_receipts": stimulus_receipts,
        "final_mute_stimulus_receipt": _identity(
            final_mute_path, label="M3 final mute stimulus receipt"
        ),
        "metrics": metrics,
        "positive_to_negative_median_ratio": contrast,
    }


def qualify(args: Any) -> dict[str, Any]:
    plan_path = args.plan.absolute()
    plan = _load(plan_path, label="M3 campaign plan")
    _validate_plan(plan)
    if args.output.absolute() != Path(plan["receipt_path"]):
        raise ProbeError("M3 qualification output differs from the sealed receipt path")
    probe_v1._require_new_private_output(args.output)
    evaluation = _evaluate_campaign(plan)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "schema_version": 1,
        "receipt_id": uuid.uuid4().hex,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "outcome": "pass",
        "plan": _identity(plan_path, label="M3 campaign plan"),
        "receiver_serial": plan["receiver_serial"],
        "transmitter_serial": plan["transmitter_serial"],
        "claim_scope": CLAIM_SCOPE,
        "hardware_accessed_by_qualifier": False,
        "persistent_write": False,
        "do_not_merge": True,
        **evaluation,
        "cabled_pss_acquired": True,
        "timing_trajectory_qualified": True,
        "negative_control_rejected": True,
        "pss_detected": True,
        "sss_detected": False,
        "frame_lock_claim": False,
        "receiver_recovery_required": True,
        "transmitter_cleanup_verified": True,
    }
    identity = probe_v1._write_new_private(args.output, receipt)
    return {
        "verdict": "PASS_M3_CABLED_PSS_ACQUISITION_ONLY",
        "pss_detected": True,
        "sss_detected": False,
        "frame_lock_claim": False,
        "receiver_recovery_required": True,
        "receipt": identity,
    }


def verify_receipt(args: Any) -> dict[str, Any]:
    plan_path = args.plan.absolute()
    plan = _load(plan_path, label="M3 campaign plan")
    _validate_plan(plan)
    if args.receipt.absolute() != Path(plan["receipt_path"]):
        raise ProbeError("M3 receipt path differs from the sealed campaign plan")
    receipt = _load(args.receipt.absolute(), label="M3 campaign receipt")
    required = {
        "schema",
        "schema_version",
        "receipt_id",
        "created_at",
        "outcome",
        "plan",
        "receiver_serial",
        "transmitter_serial",
        "claim_scope",
        "hardware_accessed_by_qualifier",
        "persistent_write",
        "do_not_merge",
        "monitor_receipts",
        "stimulus_receipts",
        "final_mute_stimulus_receipt",
        "metrics",
        "positive_to_negative_median_ratio",
        "cabled_pss_acquired",
        "timing_trajectory_qualified",
        "negative_control_rejected",
        "pss_detected",
        "sss_detected",
        "frame_lock_claim",
        "receiver_recovery_required",
        "transmitter_cleanup_verified",
    }
    receipt_id = receipt.get("receipt_id")
    ratio = receipt.get("positive_to_negative_median_ratio")
    if (
        set(receipt) != required
        or receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("schema_version") != 1
        or not isinstance(receipt_id, str)
        or len(receipt_id) != 32
        or any(character not in "0123456789abcdef" for character in receipt_id)
        or receipt.get("outcome") != "pass"
        or receipt.get("plan") != _identity(plan_path, label="M3 campaign plan")
        or receipt.get("receiver_serial") != RECEIVER_SERIAL
        or receipt.get("transmitter_serial") != plan["transmitter_serial"]
        or receipt.get("claim_scope") != CLAIM_SCOPE
        or receipt.get("hardware_accessed_by_qualifier") is not False
        or receipt.get("persistent_write") is not False
        or receipt.get("do_not_merge") is not True
        or receipt.get("cabled_pss_acquired") is not True
        or receipt.get("timing_trajectory_qualified") is not True
        or receipt.get("negative_control_rejected") is not True
        or receipt.get("pss_detected") is not True
        or receipt.get("sss_detected") is not False
        or receipt.get("frame_lock_claim") is not False
        or receipt.get("receiver_recovery_required") is not True
        or receipt.get("transmitter_cleanup_verified") is not True
        or not isinstance(ratio, (int, float))
        or isinstance(ratio, bool)
        or not math.isfinite(ratio)
    ):
        raise ProbeError("M3 qualification receipt violates its sealed plan")
    _parse_time(receipt.get("created_at"), label="qualification created_at")
    evaluation = _evaluate_campaign(plan)
    if any(receipt.get(key) != value for key, value in evaluation.items()):
        raise ProbeError("M3 qualification receipt differs from recomputed evidence")
    return {
        "verdict": "PASS_M3_RECEIPT_STRUCTURE",
        "pss_detected": True,
        "sss_detected": False,
        "frame_lock_claim": False,
        "receipt_sha256": hashlib.sha256(args.receipt.read_bytes()).hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "fixture":
            result = build_fixture(arguments)
        elif arguments.command == "plan":
            result = build_plan(arguments)
        elif arguments.command == "qualify":
            result = qualify(arguments)
        else:
            result = verify_receipt(arguments)
    except (OSError, ValueError, ProbeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
