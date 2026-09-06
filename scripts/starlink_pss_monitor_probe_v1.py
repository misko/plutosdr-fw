#!/usr/bin/env python3
"""Receipt-bound continuous phase-map monitor for the 15 MS/s v6 candidate.

This DNM-only command never loads firmware or writes persistent radio storage.
It binds one static ARM controller into an offline plan, uploads it only to the
allocated candidate runtime's ``/tmp``, continuously drains FPGA phase maps,
validates the complete NDJSON trajectory, removes the controller, restores RX
attributes, and writes a canonical receipt.  It deliberately makes no PSS,
SSS, or frame-lock claim.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import subprocess
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.starlink_pss_hardware_probe_v8 as probe_v8
import scripts.starlink_pss_progress_probe_v1 as progress_v1

PLAN_SCHEMA = "plutosdr-fw.starlink-pss-monitor-probe-plan.v1"
RECEIPT_SCHEMA = "plutosdr-fw.starlink-pss-monitor-probe-receipt.v1"
MAP_SCHEMA = "starlink-pss-acqctl.monitor-map.v1"
SUMMARY_SCHEMA = "starlink-pss-acqctl.monitor-summary.v1"
CLAIM_SCOPE = "continuous_map_transport_only"
EXPECTED_FIRMWARE = "v0.50-plutoplus-starlink-pss-15m-rx-only-dnm-v6"
REMOTE_PREFIX = "/tmp/starlink_pss_monitor"
MINIMUM_DURATION_MS = 1_000
MAXIMUM_DURATION_MS = 120_000
MAXIMUM_OUTPUT_BYTES = 4 * 1024 * 1024
TILE_SAMPLES = 20_000 * 64
ProbeError = probe_v8.ProbeError
probe_v1 = probe_v8.probe_v7.probe_v5.probe_v1
probe_v2 = probe_v8.probe_v7.probe_v2
probe_v3 = probe_v8.probe_v7.probe_v5.probe_v3
probe_v5 = probe_v8.probe_v7.probe_v5

MAP_BASE_FIELDS = {
    "schema",
    "claim_scope",
    "serial",
    "sequence",
    "bank",
    "generation",
    "start_index_canonical",
    "accepted_scores",
    "published_maps",
    "health_flags",
    "fault_free_epoch",
    "candidate_available",
    "threshold_decision",
    "pss_detected",
    "frame_lock_claim",
}
MAP_CANDIDATE_FIELDS = {
    "phase_bin",
    "drift_bins_per_64_frames",
    "combined_score",
    "combined_median",
    "peak_to_median",
    "robust_z",
    "estimated_frame_period_canonical_samples",
}
SUMMARY_FIELDS = {
    "schema",
    "claim_scope",
    "serial",
    "input_rate_msps",
    "canonical_rate_msps",
    "duration_requested_ms",
    "duration_observed_ms",
    "maps_copied",
    "candidate_windows",
    "first_generation",
    "last_generation",
    "first_start_index_canonical",
    "last_start_index_canonical",
    "accepted_scores_before",
    "accepted_scores_at_cutoff",
    "accepted_scores_delta",
    "published_maps_before",
    "published_maps_at_cutoff",
    "published_maps_delta",
    "post_loop_published_maps",
    "post_loop_ready_mask",
    "discarded_scores_at_cutoff",
    "discontinuity_aborts_at_cutoff",
    "map_overruns_at_cutoff",
    "score_protocol_errors_at_cutoff",
    "arithmetic_overflows_at_cutoff",
    "map_read_errors_at_cutoff",
    "map_release_errors_at_cutoff",
    "ingress_dropped_at_cutoff",
    "scheduler_gaps_at_cutoff",
    "scheduler_index_errors_at_cutoff",
    "scheduler_overflows_at_cutoff",
    "detector_faults_at_cutoff",
    "phase_discontinuities_at_cutoff",
    "denominator_zero_at_cutoff",
    "ingress_fifo_level_at_cutoff",
    "ingress_fifo_maximum_at_cutoff",
    "candidate_fifo_level_at_cutoff",
    "candidate_fifo_maximum_at_cutoff",
    "health_flags_at_cutoff",
    "ddc_accepted_before",
    "ddc_accepted_after",
    "ddc_emitted_before",
    "ddc_emitted_after",
    "ddc_discontinuity_after",
    "ddc_saturation_after",
    "continuity_ok",
    "fault_free_epoch",
    "post_loop_fault_free",
    "threshold_decision",
    "pss_detected",
    "frame_lock_claim",
}
ZERO_SUMMARY_FIELDS = {
    "discarded_scores_at_cutoff",
    "discontinuity_aborts_at_cutoff",
    "map_overruns_at_cutoff",
    "score_protocol_errors_at_cutoff",
    "arithmetic_overflows_at_cutoff",
    "map_read_errors_at_cutoff",
    "map_release_errors_at_cutoff",
    "ingress_dropped_at_cutoff",
    "scheduler_gaps_at_cutoff",
    "scheduler_index_errors_at_cutoff",
    "scheduler_overflows_at_cutoff",
    "detector_faults_at_cutoff",
    "phase_discontinuities_at_cutoff",
    "denominator_zero_at_cutoff",
    "ddc_accepted_before",
    "ddc_accepted_after",
    "ddc_emitted_before",
    "ddc_emitted_after",
    "ddc_discontinuity_after",
    "ddc_saturation_after",
}
SUMMARY_INTEGER_FIELDS = SUMMARY_FIELDS - {
    "schema",
    "claim_scope",
    "serial",
    "health_flags_at_cutoff",
    "continuity_ok",
    "fault_free_epoch",
    "post_loop_fault_free",
    "threshold_decision",
    "pss_detected",
    "frame_lock_claim",
}


@contextmanager
def _ad9361_v6_contract() -> Iterator[None]:
    with (
        probe_v8._ad9361_1r1t_identity(),
        probe_v8.probe_v7._v6_candidate_identity(),
    ):
        yield


def _validate_base_plan(base: dict[str, Any]) -> None:
    with _ad9361_v6_contract():
        probe_v2._validate_plan(base)
    if (
        base.get("serial") != probe_v1.ALLOCATED_SERIAL
        or base.get("runtime_target") != probe_v8.RUNTIME_TARGET
        or base.get("rate_msps") != 15
        or base.get("sample_rate_hz") != 15_000_000
        or base.get("expected_firmware") != EXPECTED_FIRMWARE
    ):
        raise ProbeError("base probe plan is not the allocated AD9361 15 MS/s v6 trial")


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
        "runtime_target",
        "expected_firmware",
        "duration_ms",
        "controller_timeout_ms",
        "ppu_repository",
        "ppu_source_commit",
        "probe_plan",
        "controller_binary",
        "receipt_path",
        "confirmation_phrase",
    }
    if set(plan) != required:
        raise ProbeError("monitor plan fields differ from the v1 schema")
    phrase = (
        f"MONITOR STARLINK PSS MAPS {probe_v1.ALLOCATED_SERIAL} "
        f"15 MSPS {plan.get('duration_ms')} MS"
    )
    if (
        plan["schema"] != PLAN_SCHEMA
        or plan["schema_version"] != 1
        or plan["hardware_accessed"] is not False
        or plan["persistent_write"] is not False
        or plan["serial"] != probe_v1.ALLOCATED_SERIAL
        or plan["rate_msps"] != 15
        or plan["runtime_target"] != probe_v8.RUNTIME_TARGET
        or plan["expected_firmware"] != EXPECTED_FIRMWARE
        or not isinstance(plan["duration_ms"], int)
        or isinstance(plan["duration_ms"], bool)
        or not MINIMUM_DURATION_MS <= plan["duration_ms"] <= MAXIMUM_DURATION_MS
        or not isinstance(plan["controller_timeout_ms"], int)
        or isinstance(plan["controller_timeout_ms"], bool)
        or not 1 <= plan["controller_timeout_ms"] <= 60_000
        or not isinstance(plan["ppu_repository"], str)
        or not Path(plan["ppu_repository"]).is_absolute()
        or not isinstance(plan["ppu_source_commit"], str)
        or not probe_v1.HEX_40.fullmatch(plan["ppu_source_commit"])
        or not isinstance(plan["plan_id"], str)
        or len(plan["plan_id"]) != 32
        or any(character not in "0123456789abcdef" for character in plan["plan_id"])
        or plan["confirmation_phrase"] != phrase
        or not isinstance(plan["receipt_path"], str)
        or not Path(plan["receipt_path"]).is_absolute()
    ):
        raise ProbeError("monitor plan values violate the v1 contract")
    for label in ("probe_plan", "controller_binary"):
        identity = plan[label]
        if (
            not isinstance(identity, dict)
            or set(identity) != {"path", "bytes", "sha256"}
            or not isinstance(identity["path"], str)
            or not Path(identity["path"]).is_absolute()
            or not isinstance(identity["bytes"], int)
            or isinstance(identity["bytes"], bool)
            or identity["bytes"] <= 0
            or not isinstance(identity["sha256"], str)
            or not probe_v1.HEX_64.fullmatch(identity["sha256"])
        ):
            raise ProbeError(f"monitor plan {label} identity is invalid")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="seal one offline map-monitor plan")
    plan.add_argument("--probe-plan", type=Path, required=True)
    plan.add_argument("--controller-binary", type=Path, required=True)
    plan.add_argument("--duration-ms", type=int, default=MAXIMUM_DURATION_MS)
    plan.add_argument("--receipt", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    execute = commands.add_parser("execute", help="run one confirmed monitor")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--ssh-password-file", type=Path, required=True)
    execute.add_argument("--state-root", type=Path, required=True)
    execute.add_argument("--timeout-s", type=float, default=240.0)
    execute.add_argument("--confirm", required=True)
    execute.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify", help="verify one monitor receipt offline")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    return result


def build_plan(args: Any) -> dict[str, Any]:
    base_path = args.probe_plan.absolute()
    base = probe_v1._load_private_json(base_path, label="PSS probe plan")
    _validate_base_plan(base)
    binary, _payload = progress_v1._binary_identity(args.controller_binary)
    if not MINIMUM_DURATION_MS <= args.duration_ms <= MAXIMUM_DURATION_MS:
        raise ProbeError("monitor duration must lie in [1000, 120000] ms")
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
        "runtime_target": probe_v8.RUNTIME_TARGET,
        "expected_firmware": base["expected_firmware"],
        "duration_ms": args.duration_ms,
        "controller_timeout_ms": base["controller_timeout_ms"],
        "ppu_repository": base["ppu_repository"],
        "ppu_source_commit": base["ppu_source_commit"],
        "probe_plan": probe_v1._identity(base_path, label="PSS probe plan"),
        "controller_binary": binary,
        "receipt_path": str(args.receipt.absolute()),
        "confirmation_phrase": (
            f"MONITOR STARLINK PSS MAPS {base['serial']} "
            f"15 MSPS {args.duration_ms} MS"
        ),
    }
    _validate_plan(plan)
    identity = probe_v1._write_new_private(args.output, plan)
    return {
        "verdict": "PASS_OFFLINE_MONITOR_PLAN_ONLY",
        "hardware_accessed": False,
        "persistent_write": False,
        "plan": identity,
        "next_confirmation": plan["confirmation_phrase"],
    }


def _finite_or_none(value: Any) -> bool:
    return value is None or (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_uint(value: Any, maximum: int = (1 << 64) - 1) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= maximum
    )


def _validate_monitor_records(
    records: list[dict[str, Any]], plan: dict[str, Any]
) -> dict[str, Any]:
    if len(records) < 4:
        raise ProbeError("monitor output does not contain maps plus one summary")
    maps = records[:-1]
    summary = records[-1]
    if set(summary) != SUMMARY_FIELDS or summary.get("schema") != SUMMARY_SCHEMA:
        raise ProbeError("monitor summary fields or schema differ from v1")
    if any(not _is_uint(summary[field]) for field in SUMMARY_INTEGER_FIELDS):
        raise ProbeError("monitor summary contains a non-unsigned integer field")
    previous: dict[str, Any] | None = None
    for index, record in enumerate(maps, 1):
        candidate_expected = index >= 3
        expected_fields = MAP_BASE_FIELDS | (
            MAP_CANDIDATE_FIELDS if candidate_expected else set()
        )
        if set(record) != expected_fields:
            raise ProbeError(f"monitor map {index} fields differ from v1")
        if (
            record["schema"] != MAP_SCHEMA
            or record["claim_scope"] != CLAIM_SCOPE
            or record["serial"] != plan["serial"]
            or record["sequence"] != index
            or record["bank"] not in (0, 1)
            or not _is_uint(record["generation"], (1 << 32) - 1)
            or not _is_uint(record["start_index_canonical"])
            or not _is_uint(record["accepted_scores"], (1 << 32) - 1)
            or not _is_uint(record["published_maps"], (1 << 32) - 1)
            or record["health_flags"] != "0x00000000"
            or record["fault_free_epoch"] is not True
            or record["candidate_available"] is not candidate_expected
            or record["threshold_decision"] is not None
            or record["pss_detected"] is not False
            or record["frame_lock_claim"] is not False
        ):
            raise ProbeError(f"monitor map {index} violates the transport-only contract")
        if previous is not None and (
            record["generation"] != previous["generation"] + 1
            or record["start_index_canonical"]
            != previous["start_index_canonical"] + TILE_SAMPLES
            or record["accepted_scores"] < previous["accepted_scores"]
            or record["published_maps"] < previous["published_maps"]
        ):
            raise ProbeError(f"monitor map {index} is not contiguous and monotonic")
        if candidate_expected and (
            not _is_uint(record["phase_bin"], 19_999)
            or not isinstance(record["drift_bins_per_64_frames"], int)
            or isinstance(record["drift_bins_per_64_frames"], bool)
            or record["drift_bins_per_64_frames"]
            not in {-12, -8, -4, 0, 4, 8, 12}
            or not _is_uint(record["combined_score"], (1 << 32) - 1)
            or any(
                not _finite_or_none(record[field])
                for field in (
                    "combined_median",
                    "peak_to_median",
                    "robust_z",
                    "estimated_frame_period_canonical_samples",
                )
            )
        ):
            raise ProbeError(f"monitor map {index} candidate fields are invalid")
        previous = record

    expected_maps = plan["duration_ms"] * 15_000 // TILE_SAMPLES
    if not expected_maps - 2 <= len(maps) <= expected_maps + 3:
        raise ProbeError("monitor map count differs from the bounded-rate expectation")
    first, last = maps[0], maps[-1]
    if (
        summary["claim_scope"] != CLAIM_SCOPE
        or summary["serial"] != plan["serial"]
        or summary["input_rate_msps"] != 15
        or summary["canonical_rate_msps"] != 15
        or summary["duration_requested_ms"] != plan["duration_ms"]
        or not plan["duration_ms"]
        <= summary["duration_observed_ms"]
        <= plan["duration_ms"] + 5_000
        or summary["maps_copied"] != len(maps)
        or summary["candidate_windows"] != len(maps) - 2
        or summary["first_generation"] != first["generation"]
        or summary["last_generation"] != last["generation"]
        or summary["first_start_index_canonical"]
        != first["start_index_canonical"]
        or summary["last_start_index_canonical"] != last["start_index_canonical"]
        or summary["accepted_scores_at_cutoff"] != last["accepted_scores"]
        or summary["accepted_scores_delta"]
        != summary["accepted_scores_at_cutoff"] - summary["accepted_scores_before"]
        or summary["published_maps_at_cutoff"] != last["published_maps"]
        or summary["published_maps_delta"] != len(maps)
        or summary["published_maps_delta"]
        != summary["published_maps_at_cutoff"] - summary["published_maps_before"]
        or not 0
        <= summary["post_loop_published_maps"]
        - summary["published_maps_at_cutoff"]
        <= 1
        or summary["post_loop_ready_mask"] not in (0, 1, 2)
        or summary["health_flags_at_cutoff"] != "0x00000000"
        or any(summary[field] != 0 for field in ZERO_SUMMARY_FIELDS)
        or summary["continuity_ok"] is not True
        or summary["fault_free_epoch"] is not True
        or summary["post_loop_fault_free"] is not True
        or summary["threshold_decision"] is not None
        or summary["pss_detected"] is not False
        or summary["frame_lock_claim"] is not False
    ):
        raise ProbeError("monitor summary violates the zero-loss transport contract")
    return {
        "maps": maps,
        "summary": summary,
        "expected_maps": expected_maps,
    }


def _run_remote_monitor(
    *,
    target: Any,
    ssh_host: str,
    password_path: Path,
    ssh_builder: Any,
    remote: str,
    plan: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    command = (
        f"{remote} --expect-serial {plan['serial']} monitor "
        f"--duration-ms {plan['duration_ms']} "
        f"--timeout-ms {plan['controller_timeout_ms']}"
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
            timeout=plan["duration_ms"] / 1000.0 + 60.0,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProbeError(f"continuous remote monitor failed: {error}") from error
    if len(completed.stdout) > MAXIMUM_OUTPUT_BYTES:
        raise ProbeError("continuous monitor output exceeds the sealed bound")
    stderr = completed.stderr.decode(errors="replace")[-4_000:]
    if completed.returncode:
        raise ProbeError(f"continuous monitor returned {completed.returncode}: {stderr}")
    try:
        records = [
            json.loads(line, object_pairs_hook=probe_v1._json_no_duplicates)
            for line in completed.stdout.decode("utf-8").splitlines()
            if line
        ]
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ProbeError("continuous monitor did not return strict NDJSON") from error
    if not all(isinstance(record, dict) for record in records):
        raise ProbeError("continuous monitor NDJSON contains a non-object record")
    _validate_monitor_records(records, plan)
    return records, stderr


def _execute_measurement(
    plan: dict[str, Any],
    base: dict[str, Any],
    handoff: Any,
    backend: Any,
    password: Any,
    iio_module: Any,
    ssh_builder: Any,
    payload: bytes,
) -> dict[str, Any]:
    target = handoff.operation.target
    context: Any = None
    originals: list[tuple[Any, str, str, str]] = []
    remote: str | None = None
    removed = False
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
            or attrs.get("fw_version") != plan["expected_firmware"]
            or attrs.get("hw_model") != probe_v8.EXPECTED_MODEL
        ):
            raise ProbeError("USB-IIO serial, firmware, or model differs from the plan")
        phy = context.find_device("ad9361-phy")
        rx = context.find_device("cf-ad9361-lpc")
        if phy is None or rx is None:
            raise ProbeError("RX-only runtime lacks PHY or RX capture core")
        phy_rx = probe_v1._channel(phy, "voltage0", False, label="PHY RX")
        capture_rx = probe_v1._channel(rx, "voltage0", False, label="capture RX")
        settings = (
            (phy_rx, "sampling_frequency", base["sample_rate_hz"], "PHY RX"),
            (capture_rx, "sampling_frequency", base["sample_rate_hz"], "capture RX"),
            (phy_rx, "rf_bandwidth", base["rf_bandwidth_hz"], "PHY RX"),
        )
        before, originals, selected = probe_v5._snapshot_and_apply(settings)
        available = tuple(
            int(value)
            for value in str(
                probe_v1._attribute(
                    capture_rx,
                    "sampling_frequency_available",
                    label="capture RX",
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
            raise ProbeError("RX rate is not an exact factor-one capture path")
        remote = (
            f"{REMOTE_PREFIX}-{plan['plan_id'][:12]}-"
            f"{plan['controller_binary']['sha256'][:12]}"
        )
        progress_v1._upload_binary(
            backend=backend,
            target=target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            ssh_builder=ssh_builder,
            payload=payload,
            digest=plan["controller_binary"]["sha256"],
            remote=remote,
            timeout_s=30.0,
        )
        records, monitor_stderr = _run_remote_monitor(
            target=target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            ssh_builder=ssh_builder,
            remote=remote,
            plan=plan,
        )
        final_info = probe_v1._remote_json(
            backend,
            target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            command=f"{remote} --expect-serial {plan['serial']} info",
            timeout_s=15.0,
            ssh_builder=ssh_builder,
        )
        try:
            final_status = int(str(final_info.get("status", "")), 0)
        except ValueError as error:
            raise ProbeError("post-monitor controller status is not numeric") from error
        if (
            final_info.get("schema") != "starlink-pss-acqctl.info.v1"
            or final_info.get("serial") != plan["serial"]
            or final_info.get("input_rate_msps") != 15
            or final_status & 0x2
        ):
            raise ProbeError("post-monitor controller does not prove engine disable")
        progress_v1._remove_binary(
            backend=backend,
            target=target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            ssh_builder=ssh_builder,
            remote=remote,
            timeout_s=15.0,
        )
        removed = True
        validated = _validate_monitor_records(records, plan)
        measurement = {
            "iio_uri": uri,
            "iio_before": before,
            "iio_selected": selected,
            "capture_rates_available_hz": available,
            "adc_gp_control": adc_gp_control,
            "fpga_decimation_factor": 1,
            "controller_binary_upload_verified": True,
            "controller_binary_removed": True,
            "monitor_stderr": monitor_stderr,
            "monitor_records": records,
            "monitor_expected_maps": validated["expected_maps"],
            "controller_info_after": final_info,
            "engine_disable_verified": True,
        }
    finally:
        cleanup_errors: list[str] = []
        if remote is not None and not removed:
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
                removed = True
            except Exception as error:  # noqa: BLE001 - preserve cleanup evidence
                cleanup_errors.append(f"remote binary: {error}")
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
            except Exception as error:  # noqa: BLE001 - preserve cleanup evidence
                cleanup_errors.append(f"{label} {name}: {error}")
        if context is not None:
            close = getattr(context, "close", None)
            if callable(close):
                with suppress(BaseException):
                    close()
        if cleanup_errors:
            raise ProbeError("monitor cleanup failed: " + "; ".join(cleanup_errors))
        if measurement is not None:
            measurement["iio_restore_verified"] = bool(originals)
            measurement["iio_restored"] = restored_values
    if measurement is None:
        raise ProbeError("monitor measurement did not complete")
    return measurement


def execute_plan(args: Any) -> dict[str, Any]:
    plan_path = args.plan.absolute()
    plan = probe_v1._load_private_json(plan_path, label="monitor plan")
    _validate_plan(plan)
    if args.confirm != plan["confirmation_phrase"]:
        raise ProbeError(f"confirmation must be exactly {plan['confirmation_phrase']!r}")
    if Path(plan["receipt_path"]) != args.output.absolute():
        raise ProbeError("execute output differs from the sealed receipt path")
    probe_v1._require_new_private_output(args.output)
    observed_probe = probe_v1._identity(
        Path(plan["probe_plan"]["path"]), label="PSS probe plan"
    )
    if observed_probe != plan["probe_plan"]:
        raise ProbeError("bound PSS probe plan changed")
    binary, payload = progress_v1._binary_identity(
        Path(plan["controller_binary"]["path"])
    )
    if binary != plan["controller_binary"]:
        raise ProbeError("bound controller binary changed")
    base = probe_v1._load_private_json(
        Path(plan["probe_plan"]["path"]), label="PSS probe plan"
    )
    _validate_base_plan(base)
    with _ad9361_v6_contract():
        handoff = probe_v2._load_handoff(
            ppu_repository=Path(base["ppu_repository"]),
            ppu_commit=base["ppu_source_commit"],
            candidate_path=Path(base["candidate_plan"]["path"]),
            operation_path=Path(base["operation_plan"]["path"]),
            ram_receipt_path=Path(base["ram_receipt"]["path"]),
            rate_msps=15,
        )
    if args.timeout_s <= 0 or not args.state_root.is_absolute() or ".." in args.state_root.parts:
        raise ProbeError("execution timeout and state root are invalid")
    try:
        password = handoff.ppu.lifecycle.validate_password_file(args.ssh_password_file)
        iio_module = importlib.import_module("iio")
    except (ImportError, OSError, ValueError) as error:
        raise ProbeError(f"monitor dependency cannot be attested: {error}") from error
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
                raise ProbeError("live target changed during exact revalidation")
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
                    runtime_target=probe_v8.RUNTIME_TARGET,
                    expected_firmware=plan["expected_firmware"],
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
                    payload,
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
        "plan": probe_v1._identity(plan_path, label="monitor plan"),
        "serial": plan["serial"],
        "rate_msps": 15,
        "runtime_target": probe_v8.RUNTIME_TARGET,
        "expected_firmware": plan["expected_firmware"],
        "hardware_accessed": True,
        "persistent_write": False,
        "claim_scope": CLAIM_SCOPE,
        "pss_detected": False,
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
        raise ProbeError(f"monitor failed after writing {identity['path']}: {failure}")
    return {
        "verdict": "PASS_CONTINUOUS_MAP_TRANSPORT_ONLY",
        "hardware_accessed": True,
        "persistent_write": False,
        "pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
        "receipt": identity,
        "next_gate": "PPU candidate-ram recover and verify persistent AD9361 target",
    }


def verify_receipt(args: Any) -> dict[str, Any]:
    plan = probe_v1._load_private_json(args.plan.absolute(), label="monitor plan")
    _validate_plan(plan)
    receipt = probe_v1._load_private_json(args.receipt.absolute(), label="monitor receipt")
    if (
        receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("schema_version") != 1
        or receipt.get("plan")
        != probe_v1._identity(args.plan.absolute(), label="monitor plan")
        or receipt.get("serial") != plan["serial"]
        or receipt.get("rate_msps") != 15
        or receipt.get("runtime_target") != probe_v8.RUNTIME_TARGET
        or receipt.get("expected_firmware") != EXPECTED_FIRMWARE
        or receipt.get("hardware_accessed") is not True
        or receipt.get("persistent_write") is not False
        or receipt.get("claim_scope") != CLAIM_SCOPE
        or receipt.get("pss_detected") is not False
        or receipt.get("sss_detected") is not False
        or receipt.get("frame_lock_claim") is not False
        or receipt.get("recovery_required") is not True
        or receipt.get("outcome") not in ("pass", "failed")
    ):
        raise ProbeError("monitor receipt violates its transport-only plan")
    if receipt["outcome"] == "pass":
        measurement = receipt.get("measurement")
        runtime = receipt.get("runtime")
        if (
            not isinstance(measurement, dict)
            or not isinstance(runtime, dict)
            or runtime.get("serial") != plan["serial"]
            or runtime.get("firmware_version") != EXPECTED_FIRMWARE
            or runtime.get("hardware_model") != probe_v8.EXPECTED_MODEL
            or runtime.get("single_rx_setup", {}).get("runtime_target")
            != probe_v8.RUNTIME_TARGET
            or measurement.get("controller_binary_upload_verified") is not True
            or measurement.get("controller_binary_removed") is not True
            or measurement.get("iio_restore_verified") is not True
            or measurement.get("engine_disable_verified") is not True
            or receipt.get("route_release_verified") is not True
            or receipt.get("error") is not None
        ):
            raise ProbeError("passing monitor receipt lacks cleanup or runtime proof")
        records = measurement.get("monitor_records")
        if not isinstance(records, list) or not all(
            isinstance(record, dict) for record in records
        ):
            raise ProbeError("passing monitor receipt lacks strict NDJSON records")
        _validate_monitor_records(records, plan)
    return {
        "verdict": "PASS_RECEIPT_STRUCTURE",
        "outcome": receipt["outcome"],
        "persistent_write": False,
        "pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
        "recovery_required": True,
        "receipt_sha256": hashlib.sha256(args.receipt.read_bytes()).hexdigest(),
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
