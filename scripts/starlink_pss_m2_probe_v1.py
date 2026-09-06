#!/usr/bin/env python3
"""Receipt-bound deterministic 15 MS/s PSS timing qualification.

The offline ``plan`` binds a passing v7 RAM receipt, the exact static ARM
controller, and both deterministic vector files.  ``execute`` acquires PPU's
exact radio and route locks, selects the factor-one 15 MS/s RX path, uploads
the three sealed inputs only to ``/tmp``, checks three exact 20,000-bin FPGA
maps, removes every upload, restores IIO attributes, and writes a receipt.
It never writes persistent storage and makes no live-PSS, SSS, or frame-lock
claim.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import stat
import subprocess
import sys
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.starlink_pss_hardware_probe_v9 as probe_v9
import scripts.starlink_pss_progress_probe_v1 as progress_v1

PLAN_SCHEMA = "plutosdr-fw.starlink-pss-m2-probe-plan.v1"
RECEIPT_SCHEMA = "plutosdr-fw.starlink-pss-m2-probe-receipt.v1"
CASE_SCHEMA = "starlink-pss-m2ctl.case.v1"
SUMMARY_SCHEMA = "starlink-pss-m2ctl.summary.v1"
INFO_SCHEMA = "starlink-pss-m2ctl.info.v1"
CLAIM_SCOPE = "deterministic_internal_timing_only"
INFO_CLAIM_SCOPE = "deterministic_qualification_contract_only"
EXPECTED_FIRMWARE = probe_v9.EXPECTED_FIRMWARE
PHASES = (0, 19_999, 7_311)
PHASE_TEXT = "0,19999,7311"
FIXTURE_SHA256 = "a983f90ccc0c4e8717ff40a5b0717a4abbea54aaacdd4fb7815adcb86f2dc6f3"
SCORES_SHA256 = "cc3904e652c80ed51bca28f4dd110caaae1dceef33b95a0d827698c4063f468b"
FIXTURE_BYTES = 130 * 9
SCORES_BYTES = 20_000 * 3
TILE_SAMPLES = 20_000 * 64
PSSI_FIXTURE_GENERATION = 0x15020001
PSSI_FORBIDDEN_STATUS = 0xEC
MAXIMUM_VECTOR_BYTES = 128 * 1024
MAXIMUM_OUTPUT_BYTES = 64 * 1024
REMOTE_PREFIX = "/tmp/starlink_pss_m2"

ProbeError = probe_v9.ProbeError
probe_v1 = probe_v9.probe_v1
probe_v2 = probe_v9.probe_v2
probe_v3 = probe_v9.probe_v8.probe_v7.probe_v5.probe_v3
probe_v5 = probe_v9.probe_v8.probe_v7.probe_v5

IDENTITY_FIELDS = {"path", "bytes", "sha256"}
INFO_FIELDS = {
    "schema",
    "claim_scope",
    "serial",
    "input_rate_msps",
    "psma_version",
    "psma_status",
    "psma_enabled",
    "pssi_identification",
    "pssi_version",
    "pssi_capabilities",
    "pssi_geometry",
    "pssi_period_samples",
    "pssi_last_sample_offset",
    "pssi_current_index",
    "pssi_status",
    "pssi_fixture_count",
    "pssi_fault_free",
    "live_pss_detected",
    "sss_detected",
    "frame_lock_claim",
}
CASE_FIELDS = {
    "schema",
    "stimulus",
    "serial",
    "case",
    "requested_phase",
    "injection_start_index",
    "target_map_start_index",
    "map_generation",
    "actual_peak_phase",
    "actual_peak_value",
    "actual_runner_up_value",
    "mismatch_count",
    "unique_peak",
    "exact_map",
    "completed_generation",
    "completed_repetitions",
    "pss_timing_qualified",
    "live_pss_detected",
    "sss_detected",
    "frame_lock_claim",
}
SUMMARY_FIELDS = {
    "schema",
    "stimulus",
    "serial",
    "input_rate_msps",
    "cases_requested",
    "cases_passed",
    "maps_copied",
    "first_map_generation",
    "last_map_generation",
    "final_health_flags",
    "fault_free_epoch",
    "continuity_ok",
    "pss_timing_qualified",
    "live_pss_detected",
    "sss_detected",
    "frame_lock_claim",
}


def _is_uint(value: Any, maximum: int = (1 << 64) - 1) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= maximum
    )


def _hex32(value: Any) -> int | None:
    if not isinstance(value, str) or re.fullmatch(r"0x[0-9a-f]{8}", value) is None:
        return None
    return int(value, 16)


def _stable_payload(path: Path, *, label: str) -> bytes:
    selected = path.absolute()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        before = selected.lstat()
        descriptor = os.open(selected, flags)
    except OSError as error:
        raise ProbeError(f"{label} cannot be opened safely: {error}") from error
    try:
        opened = os.fstat(descriptor)
        identity = probe_v1._stat_identity(opened)
        mode = stat.S_IMODE(opened.st_mode)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
            or mode not in (0o600, 0o644)
            or opened.st_size <= 0
            or opened.st_size > MAXIMUM_VECTOR_BYTES
            or identity != probe_v1._stat_identity(before)
        ):
            raise ProbeError(f"{label} is not one stable owned read-only input")
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1 << 16))
            if not chunk:
                raise ProbeError(f"{label} was truncated while reading")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1) or identity != probe_v1._stat_identity(os.fstat(descriptor)):
            raise ProbeError(f"{label} changed while reading")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _vector_identity(path: Path, *, kind: str) -> tuple[dict[str, Any], bytes]:
    if kind == "fixture":
        expected_hash, expected_bytes, words, digits = (
            FIXTURE_SHA256,
            FIXTURE_BYTES,
            130,
            8,
        )
    elif kind == "scores":
        expected_hash, expected_bytes, words, digits = (
            SCORES_SHA256,
            SCORES_BYTES,
            20_000,
            2,
        )
    else:
        raise ProbeError("unknown M2 vector kind")
    payload = _stable_payload(path, label=f"M2 {kind} vector")
    digest = hashlib.sha256(payload).hexdigest()
    lines = payload.splitlines(keepends=True)
    pattern = re.compile(rb"[0-9a-f]{" + str(digits).encode() + rb"}\n")
    if (
        len(payload) != expected_bytes
        or digest != expected_hash
        or len(lines) != words
        or any(pattern.fullmatch(line) is None for line in lines)
    ):
        raise ProbeError(f"M2 {kind} vector identity or geometry is invalid")
    return {
        "path": str(path.absolute()),
        "bytes": len(payload),
        "sha256": digest,
    }, payload


def _validate_identity(identity: Any, *, label: str) -> None:
    if (
        not isinstance(identity, dict)
        or set(identity) != IDENTITY_FIELDS
        or not isinstance(identity.get("path"), str)
        or not Path(identity["path"]).is_absolute()
        or isinstance(identity.get("bytes"), bool)
        or not isinstance(identity.get("bytes"), int)
        or identity["bytes"] <= 0
        or not isinstance(identity.get("sha256"), str)
        or probe_v1.HEX_64.fullmatch(identity["sha256"]) is None
    ):
        raise ProbeError(f"M2 plan {label} identity is invalid")


def _validate_base_plan(base: dict[str, Any]) -> None:
    with probe_v9._ad9361_v7_acquisition_injection_contract():
        probe_v2._validate_plan(base)
    if (
        base.get("serial") != probe_v1.ALLOCATED_SERIAL
        or base.get("runtime_target") != probe_v9.RUNTIME_TARGET
        or base.get("rate_msps") != 15
        or base.get("sample_rate_hz") != 15_000_000
        or base.get("expected_firmware") != EXPECTED_FIRMWARE
        or not isinstance(base.get("rf_bandwidth_hz"), int)
        or isinstance(base.get("rf_bandwidth_hz"), bool)
        or not 1 <= base["rf_bandwidth_hz"] <= 15_000_000
    ):
        raise ProbeError("base probe plan is not the allocated AD9361 15 MS/s v7 trial")


def _load_handoff(base: dict[str, Any]) -> Any:
    with probe_v9._ad9361_v7_acquisition_injection_contract():
        return probe_v1._load_handoff(
            ppu_repository=Path(base["ppu_repository"]),
            ppu_commit=base["ppu_source_commit"],
            candidate_path=Path(base["candidate_plan"]["path"]),
            operation_path=Path(base["operation_plan"]["path"]),
            ram_receipt_path=Path(base["ram_receipt"]["path"]),
            rate_msps=15,
        )


def _validate_plan(plan: dict[str, Any]) -> None:
    required = {
        "schema",
        "schema_version",
        "plan_id",
        "created_at",
        "hardware_accessed",
        "persistent_write",
        "serial",
        "rate_msps",
        "sample_rate_hz",
        "rf_bandwidth_hz",
        "runtime_target",
        "expected_firmware",
        "phases",
        "controller_timeout_ms",
        "ppu_repository",
        "ppu_source_commit",
        "probe_plan",
        "controller_binary",
        "fixture_vector",
        "score_vector",
        "receipt_path",
        "confirmation_phrase",
    }
    if set(plan) != required:
        raise ProbeError("M2 plan fields differ from the v1 schema")
    try:
        created = datetime.fromisoformat(
            str(plan.get("created_at", "")).removesuffix("Z") + "+00:00"
        )
    except ValueError as error:
        raise ProbeError("M2 plan timestamp is invalid") from error
    phrase = (
        f"QUALIFY STARLINK PSS TIMING {probe_v1.ALLOCATED_SERIAL} "
        f"15 MSPS PHASES {PHASE_TEXT}"
    )
    timeout = plan.get("controller_timeout_ms")
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan.get("schema_version") != 1
        or probe_v1.HEX_32.fullmatch(str(plan.get("plan_id", ""))) is None
        or not str(plan.get("created_at", "")).endswith("Z")
        or created.tzinfo != UTC
        or plan.get("hardware_accessed") is not False
        or plan.get("persistent_write") is not False
        or plan.get("serial") != probe_v1.ALLOCATED_SERIAL
        or plan.get("rate_msps") != 15
        or plan.get("sample_rate_hz") != 15_000_000
        or isinstance(plan.get("rf_bandwidth_hz"), bool)
        or not isinstance(plan.get("rf_bandwidth_hz"), int)
        or not 1 <= plan["rf_bandwidth_hz"] <= 15_000_000
        or plan.get("runtime_target") != probe_v9.RUNTIME_TARGET
        or plan.get("expected_firmware") != EXPECTED_FIRMWARE
        or plan.get("phases") != list(PHASES)
        or isinstance(timeout, bool)
        or not isinstance(timeout, int)
        or not 1_000 <= timeout <= 60_000
        or not isinstance(plan.get("ppu_repository"), str)
        or not Path(plan["ppu_repository"]).is_absolute()
        or probe_v1.HEX_40.fullmatch(str(plan.get("ppu_source_commit", ""))) is None
        or not isinstance(plan.get("receipt_path"), str)
        or not Path(plan["receipt_path"]).is_absolute()
        or plan.get("confirmation_phrase") != phrase
    ):
        raise ProbeError("M2 plan values violate the deterministic v1 contract")
    for label in ("probe_plan", "controller_binary", "fixture_vector", "score_vector"):
        _validate_identity(plan.get(label), label=label)
    if (
        plan["fixture_vector"]["bytes"] != FIXTURE_BYTES
        or plan["fixture_vector"]["sha256"] != FIXTURE_SHA256
        or plan["score_vector"]["bytes"] != SCORES_BYTES
        or plan["score_vector"]["sha256"] != SCORES_SHA256
    ):
        raise ProbeError("M2 plan vector identities are not the qualified fixtures")
    paths = [
        Path(plan[label]["path"])
        for label in ("probe_plan", "controller_binary", "fixture_vector", "score_vector")
    ] + [Path(plan["receipt_path"])]
    if len(paths) != len(set(paths)):
        raise ProbeError("M2 plan inputs and receipt path must be distinct")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="seal one offline M2 qualification plan")
    plan.add_argument("--probe-plan", type=Path, required=True)
    plan.add_argument("--controller-binary", type=Path, required=True)
    plan.add_argument("--fixture-vector", type=Path, required=True)
    plan.add_argument("--score-vector", type=Path, required=True)
    plan.add_argument("--receipt", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    execute = commands.add_parser("execute", help="run one confirmed M2 qualification")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--ssh-password-file", type=Path, required=True)
    execute.add_argument("--state-root", type=Path, required=True)
    execute.add_argument("--timeout-s", type=float, default=90.0)
    execute.add_argument("--confirm", required=True)
    execute.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify", help="verify one M2 receipt offline")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    return result


def build_plan(args: Any) -> dict[str, Any]:
    base_path = args.probe_plan.absolute()
    base = probe_v1._load_private_json(base_path, label="PSS probe plan")
    _validate_base_plan(base)
    _load_handoff(base)
    controller, _controller_payload = progress_v1._binary_identity(args.controller_binary)
    fixture, _fixture_payload = _vector_identity(args.fixture_vector, kind="fixture")
    scores, _score_payload = _vector_identity(args.score_vector, kind="scores")
    probe_v1._require_new_private_output(args.output)
    probe_v1._require_new_private_output(args.receipt)
    plan = {
        "schema": PLAN_SCHEMA,
        "schema_version": 1,
        "plan_id": uuid.uuid4().hex,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "hardware_accessed": False,
        "persistent_write": False,
        "serial": base["serial"],
        "rate_msps": 15,
        "sample_rate_hz": 15_000_000,
        "rf_bandwidth_hz": base["rf_bandwidth_hz"],
        "runtime_target": probe_v9.RUNTIME_TARGET,
        "expected_firmware": EXPECTED_FIRMWARE,
        "phases": list(PHASES),
        "controller_timeout_ms": base["controller_timeout_ms"],
        "ppu_repository": base["ppu_repository"],
        "ppu_source_commit": base["ppu_source_commit"],
        "probe_plan": probe_v1._identity(base_path, label="PSS probe plan"),
        "controller_binary": controller,
        "fixture_vector": fixture,
        "score_vector": scores,
        "receipt_path": str(args.receipt.absolute()),
        "confirmation_phrase": (
            f"QUALIFY STARLINK PSS TIMING {base['serial']} "
            f"15 MSPS PHASES {PHASE_TEXT}"
        ),
    }
    _validate_plan(plan)
    identity = probe_v1._write_new_private(args.output, plan)
    return {
        "verdict": "PASS_OFFLINE_M2_PLAN_ONLY",
        "hardware_accessed": False,
        "persistent_write": False,
        "plan": identity,
        "next_confirmation": plan["confirmation_phrase"],
    }


def _validate_info(info: dict[str, Any], plan: dict[str, Any], *, after: bool) -> None:
    psma_status = _hex32(info.get("psma_status"))
    pssi_status = _hex32(info.get("pssi_status"))
    if (
        set(info) != INFO_FIELDS
        or info.get("schema") != INFO_SCHEMA
        or info.get("claim_scope") != INFO_CLAIM_SCOPE
        or info.get("serial") != plan["serial"]
        or info.get("input_rate_msps") != 15
        or info.get("psma_version") != "0x00010001"
        or psma_status is None
        or psma_status & 0x1E
        or info.get("psma_enabled") is not False
        or info.get("pssi_identification") != "0x50535349"
        or info.get("pssi_version") != "0x00010000"
        or info.get("pssi_capabilities") != "0x0000000f"
        or info.get("pssi_geometry") != "0x00820082"
        or info.get("pssi_period_samples") != 20_000
        or info.get("pssi_last_sample_offset") != 2_580_129
        or not _is_uint(info.get("pssi_current_index"))
        or pssi_status is None
        or pssi_status & PSSI_FORBIDDEN_STATUS
        or not _is_uint(info.get("pssi_fixture_count"), 130)
        or info.get("pssi_fault_free") is not True
        or info.get("live_pss_detected") is not False
        or info.get("sss_detected") is not False
        or info.get("frame_lock_claim") is not False
    ):
        raise ProbeError("M2 controller info violates the disabled fault-free contract")
    if after and (
        info["pssi_fixture_count"] != 130 or pssi_status & 0x11 != 0x11
    ):
        raise ProbeError("post-M2 controller info lacks completed fixture state")


def _validate_qualification_records(
    records: list[dict[str, Any]], plan: dict[str, Any]
) -> dict[str, Any]:
    if len(records) != len(PHASES) + 1:
        raise ProbeError("M2 output must contain exactly three cases and one summary")
    cases, summary = records[:-1], records[-1]
    previous: dict[str, Any] | None = None
    for index, (record, phase) in enumerate(zip(cases, PHASES, strict=True)):
        delta = (32 + 20_000 - phase) % 20_000
        if (
            set(record) != CASE_FIELDS
            or record.get("schema") != CASE_SCHEMA
            or record.get("stimulus") != "deterministic_internal"
            or record.get("serial") != plan["serial"]
            or record.get("case") != index
            or record.get("requested_phase") != phase
            or not _is_uint(record.get("injection_start_index"))
            or not _is_uint(record.get("target_map_start_index"))
            or record["injection_start_index"] + delta
            != record["target_map_start_index"]
            or record["target_map_start_index"] % TILE_SAMPLES
            or not _is_uint(record.get("map_generation"), (1 << 32) - 1)
            or record.get("actual_peak_phase") != phase
            or record.get("actual_peak_value") != 16_320
            or record.get("actual_runner_up_value") != 7_424
            or record.get("mismatch_count") != 0
            or record.get("unique_peak") is not True
            or record.get("exact_map") is not True
            or record.get("completed_generation") != PSSI_FIXTURE_GENERATION
            or record.get("completed_repetitions") != 130
            or record.get("pss_timing_qualified") is not True
            or record.get("live_pss_detected") is not False
            or record.get("sss_detected") is not False
            or record.get("frame_lock_claim") is not False
        ):
            raise ProbeError(f"M2 case {index} violates its exact-map contract")
        if previous is not None:
            tile_delta = (
                record["target_map_start_index"]
                - previous["target_map_start_index"]
            ) // TILE_SAMPLES
            if (
                record["target_map_start_index"]
                <= previous["target_map_start_index"]
                or record["map_generation"] <= previous["map_generation"]
                or record["map_generation"] - previous["map_generation"] != tile_delta
            ):
                raise ProbeError("M2 cases are not contiguous in map generation")
        previous = record
    if (
        set(summary) != SUMMARY_FIELDS
        or summary.get("schema") != SUMMARY_SCHEMA
        or summary.get("stimulus") != "deterministic_internal"
        or summary.get("serial") != plan["serial"]
        or summary.get("input_rate_msps") != 15
        or summary.get("cases_requested") != len(PHASES)
        or summary.get("cases_passed") != len(PHASES)
        or not _is_uint(summary.get("maps_copied"), (1 << 32) - 1)
        or not _is_uint(summary.get("first_map_generation"), (1 << 32) - 1)
        or not _is_uint(summary.get("last_map_generation"), (1 << 32) - 1)
        or summary["last_map_generation"] < summary["first_map_generation"]
        or summary["maps_copied"]
        != summary["last_map_generation"] - summary["first_map_generation"] + 1
        or summary["first_map_generation"] > cases[0]["map_generation"]
        or summary["last_map_generation"] != cases[-1]["map_generation"]
        or summary.get("final_health_flags") != "0x00000000"
        or summary.get("fault_free_epoch") is not True
        or summary.get("continuity_ok") is not True
        or summary.get("pss_timing_qualified") is not True
        or summary.get("live_pss_detected") is not False
        or summary.get("sss_detected") is not False
        or summary.get("frame_lock_claim") is not False
    ):
        raise ProbeError("M2 summary violates the exact timing qualification contract")
    return {"cases": cases, "summary": summary}


def _run_remote_qualification(
    *,
    target: Any,
    ssh_host: str,
    password_path: Path,
    ssh_builder: Any,
    controller: str,
    fixture: str,
    scores: str,
    plan: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    command = (
        f"{controller} --expect-serial {plan['serial']} "
        f"--fixture {fixture} --scores {scores} qualify "
        f"--phases {PHASE_TEXT} --timeout-ms {plan['controller_timeout_ms']}"
    )
    argv = ssh_builder(
        target,
        ssh_host=ssh_host,
        password_path=password_path,
        remote_command=command,
    )
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            timeout=max(60.0, plan["controller_timeout_ms"] / 1000.0 * 16.0),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProbeError(f"remote M2 qualification failed: {error}") from error
    if len(completed.stdout) > MAXIMUM_OUTPUT_BYTES:
        raise ProbeError("remote M2 output exceeds the sealed bound")
    stderr = completed.stderr.decode(errors="replace")[-4_000:]
    if completed.returncode:
        raise ProbeError(f"remote M2 qualifier returned {completed.returncode}: {stderr}")
    try:
        records = [
            json.loads(line, object_pairs_hook=probe_v1._json_no_duplicates)
            for line in completed.stdout.decode("utf-8").splitlines()
            if line
        ]
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ProbeError("remote M2 qualifier did not return strict NDJSON") from error
    if not all(isinstance(record, dict) for record in records):
        raise ProbeError("remote M2 NDJSON contains a non-object")
    _validate_qualification_records(records, plan)
    return records, stderr


def _execute_measurement(
    plan: dict[str, Any],
    base: dict[str, Any],
    handoff: Any,
    backend: Any,
    password: Any,
    iio_module: Any,
    ssh_builder: Any,
    controller_payload: bytes,
    fixture_payload: bytes,
    score_payload: bytes,
) -> dict[str, Any]:
    target = handoff.operation.target
    context: Any = None
    originals: list[tuple[Any, str, str, str]] = []
    remote_paths: list[str] = []
    removed: set[str] = set()
    restored_values: dict[str, int] = {}
    measurement: dict[str, Any] | None = None
    try:
        uri = f"usb:{target.bus_number}.{target.device_number}.5"
        context = iio_module.Context(uri)
        setter = getattr(context, "set_timeout", None)
        if not callable(setter):
            raise ProbeError("exact USB-IIO context cannot set a timeout")
        setter(5_000)
        attrs = {str(key): str(value) for key, value in context.attrs.items()}
        serial = attrs.get("hw_serial", attrs.get("usb,serial", attrs.get("serial", "")))
        if (
            serial != plan["serial"]
            or attrs.get("fw_version") != EXPECTED_FIRMWARE
            or attrs.get("hw_model") != probe_v9.EXPECTED_MODEL
        ):
            raise ProbeError("USB-IIO serial, firmware, or model differs from the M2 plan")
        phy = context.find_device("ad9361-phy")
        rx = context.find_device("cf-ad9361-lpc")
        if phy is None or rx is None:
            raise ProbeError("RX-only runtime lacks PHY or RX capture core")
        phy_rx = probe_v1._channel(phy, "voltage0", False, label="PHY RX")
        capture_rx = probe_v1._channel(rx, "voltage0", False, label="capture RX")
        settings = (
            (phy_rx, "sampling_frequency", 15_000_000, "PHY RX"),
            (capture_rx, "sampling_frequency", 15_000_000, "capture RX"),
            (phy_rx, "rf_bandwidth", base["rf_bandwidth_hz"], "PHY RX"),
        )
        before, originals, selected = probe_v5._snapshot_and_apply(settings)
        available = tuple(
            int(value)
            for value in str(
                probe_v1._attribute(
                    capture_rx, "sampling_frequency_available", label="capture RX"
                ).value
            )
            .strip()
            .replace("[", "")
            .replace("]", "")
            .split()
        )
        reader = getattr(rx, "reg_read", None)
        if not callable(reader):
            raise ProbeError("capture RX does not expose FPGA decimation readback")
        try:
            adc_gp_control = int(reader(probe_v1.ADC_GP_CONTROL_REG)) & 0xFFFFFFFF
        except (OSError, TypeError, ValueError) as error:
            raise ProbeError("FPGA decimation readback failed") from error
        if available != (15_000_000, 1_875_000) or adc_gp_control & 1:
            raise ProbeError("RX rate is not an exact factor-one 15 MS/s path")

        suffix = plan["plan_id"][:12]
        uploads = (
            (
                f"{REMOTE_PREFIX}ctl-{suffix}-{plan['controller_binary']['sha256'][:12]}",
                controller_payload,
                plan["controller_binary"]["sha256"],
            ),
            (
                f"{REMOTE_PREFIX}fixture-{suffix}-{FIXTURE_SHA256[:12]}",
                fixture_payload,
                FIXTURE_SHA256,
            ),
            (
                f"{REMOTE_PREFIX}scores-{suffix}-{SCORES_SHA256[:12]}",
                score_payload,
                SCORES_SHA256,
            ),
        )
        for remote, payload, digest in uploads:
            remote_paths.append(remote)
            progress_v1._upload_binary(
                backend=backend,
                target=target,
                ssh_host=handoff.operation.ssh_host,
                password_path=password.path,
                ssh_builder=ssh_builder,
                payload=payload,
                digest=digest,
                remote=remote,
                timeout_s=30.0,
            )
        controller_remote, fixture_remote, scores_remote = remote_paths
        common = f"{controller_remote} --expect-serial {plan['serial']}"
        info_before = probe_v1._remote_json(
            backend,
            target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            command=f"{common} info",
            timeout_s=15.0,
            ssh_builder=ssh_builder,
        )
        _validate_info(info_before, plan, after=False)
        records, qualifier_stderr = _run_remote_qualification(
            target=target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            ssh_builder=ssh_builder,
            controller=controller_remote,
            fixture=fixture_remote,
            scores=scores_remote,
            plan=plan,
        )
        info_after = probe_v1._remote_json(
            backend,
            target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            command=f"{common} info",
            timeout_s=15.0,
            ssh_builder=ssh_builder,
        )
        _validate_info(info_after, plan, after=True)
        for remote in reversed(remote_paths):
            progress_v1._remove_binary(
                backend=backend,
                target=target,
                ssh_host=handoff.operation.ssh_host,
                password_path=password.path,
                ssh_builder=ssh_builder,
                remote=remote,
                timeout_s=15.0,
            )
            removed.add(remote)
        measurement = {
            "iio_uri": uri,
            "iio_before": before,
            "iio_selected": selected,
            "capture_rates_available_hz": available,
            "adc_gp_control": adc_gp_control,
            "fpga_decimation_factor": 1,
            "uploads_verified": True,
            "uploads_removed": True,
            "controller_info_before": info_before,
            "qualification_records": records,
            "qualifier_stderr": qualifier_stderr,
            "controller_info_after": info_after,
            "engine_disable_verified": True,
            "exact_maps_verified": True,
        }
    finally:
        cleanup_errors: list[str] = []
        for remote in reversed(remote_paths):
            if remote in removed:
                continue
            try:
                progress_v1._remove_binary(
                    backend=backend,
                    target=target,
                    ssh_host=handoff.operation.ssh_host,
                    password_path=password.path,
                    ssh_builder=ssh_builder,
                    remote=remote,
                    timeout_s=15.0,
                )
                removed.add(remote)
            except Exception as error:  # noqa: BLE001 - retain cleanup evidence
                cleanup_errors.append(f"remote input {remote}: {error}")
        priorities = {
            ("PHY RX", "rf_bandwidth"): 0,
            ("PHY RX", "sampling_frequency"): 1,
            ("capture RX", "sampling_frequency"): 2,
        }
        for channel, name, original, label in sorted(
            originals, key=lambda item: priorities.get((item[3], item[1]), 3)
        ):
            try:
                attribute = probe_v1._attribute(channel, name, label=label)
                attribute.value = original
                requested = probe_v1._number(original, label=f"original {label} {name}")
                observed = probe_v1._number(
                    attribute.value, label=f"restored {label} {name}"
                )
                if abs(observed - requested) > max(2.0, abs(requested) * 100e-6):
                    raise ProbeError(f"restored {label} {name} differs from original")
                restored_values[f"{label.lower().replace(' ', '_')}_{name}"] = round(
                    observed
                )
            except Exception as error:  # noqa: BLE001 - retain cleanup evidence
                cleanup_errors.append(f"{label} {name}: {error}")
        if context is not None:
            close = getattr(context, "close", None)
            if callable(close):
                with suppress(BaseException):
                    close()
        if cleanup_errors:
            raise ProbeError("M2 cleanup failed: " + "; ".join(cleanup_errors))
        if measurement is not None:
            measurement["iio_restore_verified"] = bool(originals)
            measurement["iio_restored"] = restored_values
    if measurement is None:
        raise ProbeError("M2 measurement did not complete")
    return measurement


def execute_plan(args: Any) -> dict[str, Any]:
    plan_path = args.plan.absolute()
    plan = probe_v1._load_private_json(plan_path, label="M2 plan")
    _validate_plan(plan)
    if args.confirm != plan["confirmation_phrase"]:
        raise ProbeError(f"confirmation must be exactly {plan['confirmation_phrase']!r}")
    if Path(plan["receipt_path"]) != args.output.absolute():
        raise ProbeError("execute output differs from the sealed M2 receipt path")
    probe_v1._require_new_private_output(args.output)
    observed_probe = probe_v1._identity(
        Path(plan["probe_plan"]["path"]), label="PSS probe plan"
    )
    if observed_probe != plan["probe_plan"]:
        raise ProbeError("bound PSS probe plan changed")
    controller, controller_payload = progress_v1._binary_identity(
        Path(plan["controller_binary"]["path"])
    )
    fixture, fixture_payload = _vector_identity(
        Path(plan["fixture_vector"]["path"]), kind="fixture"
    )
    scores, score_payload = _vector_identity(
        Path(plan["score_vector"]["path"]), kind="scores"
    )
    if (
        controller != plan["controller_binary"]
        or fixture != plan["fixture_vector"]
        or scores != plan["score_vector"]
    ):
        raise ProbeError("one or more sealed M2 inputs changed")
    base = probe_v1._load_private_json(
        Path(plan["probe_plan"]["path"]), label="PSS probe plan"
    )
    _validate_base_plan(base)
    handoff = _load_handoff(base)
    if args.timeout_s <= 0 or not args.state_root.is_absolute() or ".." in args.state_root.parts:
        raise ProbeError("M2 execution timeout and state root are invalid")
    try:
        password = handoff.ppu.lifecycle.validate_password_file(args.ssh_password_file)
        iio_module = importlib.import_module("iio")
    except (ImportError, OSError, ValueError) as error:
        raise ProbeError(f"M2 dependency cannot be attested: {error}") from error
    backend = handoff.ppu.linux.LinuxRxOnlyReleaseCandidateBackend(
        state_root=args.state_root.absolute(), timeout_s=args.timeout_s
    )
    started = datetime.now(UTC)
    route = None
    route_released = False
    runtime: Any = None
    measurement: dict[str, Any] | None = None
    failure: BaseException | None = None
    try:
        live_target = probe_v3._resolve_live_target(backend, handoff.operation.target)
        with backend.transaction_locks(live_target, handoff.operation.ssh_host):
            fresh = backend.revalidate_target(live_target)
            if fresh != live_target:
                raise ProbeError("live target changed during exact M2 revalidation")
            live_operation = handoff.operation.model_copy(update={"target": live_target})
            live_handoff = SimpleNamespace(
                ppu=handoff.ppu,
                candidate=handoff.candidate,
                operation=live_operation,
                receipt=handoff.receipt,
                repository=handoff.repository,
            )
            route = backend.acquire_host_route(live_target, live_operation.ssh_host)
            try:
                runtime = backend.attest_rx_only_runtime_v2(
                    live_target,
                    runtime_target=probe_v9.RUNTIME_TARGET,
                    expected_firmware=EXPECTED_FIRMWARE,
                    password=password,
                    route=route,
                )
                measurement = _execute_measurement(
                    plan,
                    base,
                    live_handoff,
                    backend,
                    password,
                    iio_module,
                    handoff.ppu.lifecycle.ssh_fixed_argv,
                    controller_payload,
                    fixture_payload,
                    score_payload,
                )
            finally:
                if route is not None:
                    backend.release_host_route(route)
                    route_released = True
    except Exception as error:  # noqa: BLE001 - every hardware outcome gets a receipt
        failure = error
    completed = datetime.now(UTC)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "schema_version": 1,
        "receipt_id": uuid.uuid4().hex,
        "outcome": "pass" if failure is None else "failed",
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "completed_at": completed.isoformat().replace("+00:00", "Z"),
        "plan": probe_v1._identity(plan_path, label="M2 plan"),
        "serial": plan["serial"],
        "rate_msps": 15,
        "runtime_target": probe_v9.RUNTIME_TARGET,
        "expected_firmware": EXPECTED_FIRMWARE,
        "hardware_accessed": True,
        "persistent_write": False,
        "claim_scope": CLAIM_SCOPE,
        "pss_timing_qualified": failure is None,
        "live_pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
        "runtime": None if runtime is None else runtime.model_dump(mode="json"),
        "measurement": measurement,
        "route_release_verified": route_released,
        "recovery_required": True,
        "error": None if failure is None else f"{type(failure).__name__}: {failure}",
    }
    identity = probe_v1._write_new_private(args.output, receipt)
    if failure is not None:
        raise ProbeError(f"M2 qualification failed after writing {identity['path']}: {failure}")
    return {
        "verdict": "PASS_DETERMINISTIC_PSS_TIMING_QUALIFICATION",
        "hardware_accessed": True,
        "persistent_write": False,
        "pss_timing_qualified": True,
        "live_pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
        "receipt": identity,
        "next_gate": "PPU candidate-ram recover and verify persistent AD9361 target",
    }


def verify_receipt(args: Any) -> dict[str, Any]:
    plan_path = args.plan.absolute()
    receipt_path = args.receipt.absolute()
    plan = probe_v1._load_private_json(plan_path, label="M2 plan")
    _validate_plan(plan)
    receipt = probe_v1._load_private_json(receipt_path, label="M2 receipt")
    try:
        started = datetime.fromisoformat(
            str(receipt.get("started_at", "")).removesuffix("Z") + "+00:00"
        )
        completed = datetime.fromisoformat(
            str(receipt.get("completed_at", "")).removesuffix("Z") + "+00:00"
        )
    except ValueError as error:
        raise ProbeError("M2 receipt timestamps are invalid") from error
    required = {
        "schema",
        "schema_version",
        "receipt_id",
        "outcome",
        "started_at",
        "completed_at",
        "plan",
        "serial",
        "rate_msps",
        "runtime_target",
        "expected_firmware",
        "hardware_accessed",
        "persistent_write",
        "claim_scope",
        "pss_timing_qualified",
        "live_pss_detected",
        "sss_detected",
        "frame_lock_claim",
        "runtime",
        "measurement",
        "route_release_verified",
        "recovery_required",
        "error",
    }
    if (
        set(receipt) != required
        or receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("schema_version") != 1
        or probe_v1.HEX_32.fullmatch(str(receipt.get("receipt_id", ""))) is None
        or not str(receipt.get("started_at", "")).endswith("Z")
        or not str(receipt.get("completed_at", "")).endswith("Z")
        or started.tzinfo != UTC
        or completed.tzinfo != UTC
        or completed < started
        or receipt.get("plan") != probe_v1._identity(plan_path, label="M2 plan")
        or Path(plan["receipt_path"]) != receipt_path
        or receipt.get("serial") != plan["serial"]
        or receipt.get("rate_msps") != 15
        or receipt.get("runtime_target") != probe_v9.RUNTIME_TARGET
        or receipt.get("expected_firmware") != EXPECTED_FIRMWARE
        or receipt.get("hardware_accessed") is not True
        or receipt.get("persistent_write") is not False
        or receipt.get("claim_scope") != CLAIM_SCOPE
        or receipt.get("live_pss_detected") is not False
        or receipt.get("sss_detected") is not False
        or receipt.get("frame_lock_claim") is not False
        or receipt.get("recovery_required") is not True
        or receipt.get("outcome") not in ("pass", "failed")
    ):
        raise ProbeError("M2 receipt violates its deterministic qualification plan")
    if receipt["outcome"] == "pass":
        measurement = receipt.get("measurement")
        runtime = receipt.get("runtime")
        if (
            receipt.get("pss_timing_qualified") is not True
            or not isinstance(measurement, dict)
            or not isinstance(runtime, dict)
            or runtime.get("serial") != plan["serial"]
            or runtime.get("firmware_version") != EXPECTED_FIRMWARE
            or runtime.get("hardware_model") != probe_v9.EXPECTED_MODEL
            or runtime.get("single_rx_setup", {}).get("runtime_target")
            != probe_v9.RUNTIME_TARGET
            or measurement.get("uploads_verified") is not True
            or measurement.get("uploads_removed") is not True
            or measurement.get("iio_restore_verified") is not True
            or measurement.get("engine_disable_verified") is not True
            or measurement.get("exact_maps_verified") is not True
            or receipt.get("route_release_verified") is not True
            or receipt.get("error") is not None
        ):
            raise ProbeError("passing M2 receipt lacks runtime, exact-map, or cleanup proof")
        info_before = measurement.get("controller_info_before")
        info_after = measurement.get("controller_info_after")
        records = measurement.get("qualification_records")
        if (
            not isinstance(info_before, dict)
            or not isinstance(info_after, dict)
            or not isinstance(records, list)
            or not all(isinstance(record, dict) for record in records)
        ):
            raise ProbeError("passing M2 receipt lacks strict controller records")
        _validate_info(info_before, plan, after=False)
        _validate_qualification_records(records, plan)
        _validate_info(info_after, plan, after=True)
    elif (
        receipt.get("pss_timing_qualified") is not False
        or not isinstance(receipt.get("error"), str)
        or not receipt["error"]
        or receipt.get("measurement") is not None
    ):
        raise ProbeError("failed M2 receipt lacks its fail-closed state")
    return {
        "verdict": "PASS_RECEIPT_STRUCTURE",
        "outcome": receipt["outcome"],
        "persistent_write": False,
        "pss_timing_qualified": receipt["pss_timing_qualified"],
        "live_pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
        "recovery_required": True,
        "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "plan":
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
