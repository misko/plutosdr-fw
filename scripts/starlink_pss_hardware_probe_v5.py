#!/usr/bin/env python3
"""Dependency-safe source-rate launcher for the Starlink PSS probe.

The immutable v1-v4 revisions remain unchanged.  This revision snapshots every
RFIC/capture attribute before changing the RFIC parent clock, so restoration
never combines an old parent rate with a transient child-selector value.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.starlink_pss_hardware_probe as probe_v1
import scripts.starlink_pss_hardware_probe_v3 as probe_v3

ProbeError = probe_v3.ProbeError
build_plan = probe_v3.build_plan
verify_receipt = probe_v3.verify_receipt
parser = probe_v3.parser


def _snapshot_and_apply(
    settings: tuple[tuple[Any, str, int, str], ...],
) -> tuple[dict[str, str], list[tuple[Any, str, str, str]], dict[str, int]]:
    """Snapshot the whole dependency graph before applying any rate change."""

    before: dict[str, str] = {}
    originals: list[tuple[Any, str, str, str]] = []
    selected: dict[str, int] = {}
    for channel, name, _requested, label in settings:
        attribute = probe_v1._attribute(channel, name, label=label)
        original = str(attribute.value)
        key = f"{label.lower().replace(' ', '_')}_{name}"
        before[key] = original
        originals.append((channel, name, original, label))
    for channel, name, requested, label in settings:
        key = f"{label.lower().replace(' ', '_')}_{name}"
        tolerance = max(2.0, requested * 100e-6)
        selected[key] = probe_v1._write_numeric(
            channel, name, requested, tolerance, label=label
        )
    return before, originals, selected


def _measure(
    plan: dict[str, Any],
    handoff: Any,
    backend: Any,
    password: Any,
    iio_module: Any,
    ssh_builder: Callable[..., tuple[str, ...]],
) -> dict[str, Any]:
    target = handoff.operation.target
    context: Any = None
    originals: list[tuple[Any, str, str, str]] = []
    restored = False
    restored_values: dict[str, int] = {}
    measurement: dict[str, Any] | None = None
    try:
        uri = f"usb:{target.bus_number}.{target.device_number}.5"
        context = iio_module.Context(uri)
        setter = getattr(context, "set_timeout", None)
        if not callable(setter):
            raise ProbeError("exact USB-IIO context cannot set a timeout")
        setter(5000)
        attrs = {str(key): str(value) for key, value in context.attrs.items()}
        serial = attrs.get("hw_serial", attrs.get("usb,serial", attrs.get("serial", "")))
        if (
            serial != plan["serial"]
            or attrs.get("fw_version") != plan["expected_firmware"]
            or attrs.get("hw_model") != probe_v1.EXPECTED_MODEL
        ):
            raise ProbeError("USB-IIO serial, firmware, or model differs from the plan")
        phy = context.find_device("ad9361-phy")
        rx = context.find_device("cf-ad9361-lpc")
        if phy is None or rx is None:
            raise ProbeError("RX-only runtime lacks PHY or RX capture core")
        phy_rx = probe_v1._channel(phy, "voltage0", False, label="PHY RX")
        capture_rx = probe_v1._channel(rx, "voltage0", False, label="capture RX")
        settings = (
            (phy_rx, "sampling_frequency", plan["sample_rate_hz"], "PHY RX"),
            (capture_rx, "sampling_frequency", plan["sample_rate_hz"], "capture RX"),
            (phy_rx, "rf_bandwidth", plan["rf_bandwidth_hz"], "PHY RX"),
        )
        before, originals, selected = _snapshot_and_apply(settings)

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
        if available != (
            plan["sample_rate_hz"],
            plan["sample_rate_hz"] // 8,
        ) or adc_gp_control & 1:
            raise ProbeError("RX rate is not an exact factor-one capture path")

        serial = plan["serial"]
        common = f"/usr/sbin/starlink_pss_acqctl --expect-serial {serial}"
        timeout_s = max(10.0, plan["controller_timeout_ms"] / 1000.0 + 5.0)
        info = probe_v1._remote_json(
            backend,
            target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            command=f"{common} info",
            timeout_s=timeout_s,
            ssh_builder=ssh_builder,
        )
        before_snapshot = probe_v1._remote_json(
            backend,
            target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            command=f"{common} snapshot --timeout-ms {plan['controller_timeout_ms']}",
            timeout_s=timeout_s,
            ssh_builder=ssh_builder,
        )
        candidate = probe_v1._remote_json(
            backend,
            target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            command=f"{common} candidate --timeout-ms {plan['controller_timeout_ms']}",
            timeout_s=timeout_s,
            ssh_builder=ssh_builder,
        )
        after_snapshot = probe_v1._remote_json(
            backend,
            target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            command=f"{common} snapshot --timeout-ms {plan['controller_timeout_ms']}",
            timeout_s=timeout_s,
            ssh_builder=ssh_builder,
        )
        final_info = probe_v1._remote_json(
            backend,
            target,
            ssh_host=handoff.operation.ssh_host,
            password_path=password.path,
            command=f"{common} info",
            timeout_s=timeout_s,
            ssh_builder=ssh_builder,
        )
        try:
            initial_status = int(str(info.get("status", "")), 0)
            final_status = int(str(final_info.get("status", "")), 0)
        except ValueError as error:
            raise ProbeError("controller status is not a numeric hex word") from error
        if (
            info.get("schema") != "starlink-pss-acqctl.info.v1"
            or info.get("claim_scope") != "hardware_contract_only"
            or info.get("serial") != serial
            or info.get("input_rate_msps") != plan["rate_msps"]
            or initial_status & 0x2
            or before_snapshot.get("schema") != "starlink-pss-acqctl.snapshot.v1"
            or before_snapshot.get("serial") != serial
            or candidate.get("schema") != "starlink-pss-acqctl.candidate.v1"
            or candidate.get("claim_scope") != "candidate_measurement_only"
            or candidate.get("serial") != serial
            or candidate.get("input_rate_msps") != plan["rate_msps"]
            or candidate.get("continuity_ok") is not True
            or candidate.get("threshold_decision") is not None
            or candidate.get("frame_lock_claim") is not False
            or candidate.get("fault_free_epoch") is not True
            or after_snapshot.get("schema") != "starlink-pss-acqctl.snapshot.v1"
            or after_snapshot.get("serial") != serial
            or after_snapshot.get("fault_free_epoch") is not True
            or final_info.get("schema") != "starlink-pss-acqctl.info.v1"
            or final_info.get("serial") != serial
            or final_info.get("input_rate_msps") != plan["rate_msps"]
            or final_status & 0x2
        ):
            raise ProbeError("controller JSON does not satisfy the measurement-only contract")
        measurement = {
            "iio_uri": uri,
            "iio_before": before,
            "iio_selected": selected,
            "capture_rates_available_hz": available,
            "adc_gp_control": adc_gp_control,
            "fpga_decimation_factor": 1,
            "controller_info": info,
            "snapshot_before": before_snapshot,
            "candidate": candidate,
            "snapshot_after": after_snapshot,
            "controller_info_after": final_info,
        }
    finally:
        errors: list[str] = []
        priorities = {
            ("PHY RX", "rf_bandwidth"): 0,
            ("PHY RX", "sampling_frequency"): 1,
            ("capture RX", "sampling_frequency"): 2,
        }
        restore_order = sorted(
            originals,
            key=lambda item: priorities.get((item[3], item[1]), 3),
        )
        for channel, name, original, label in restore_order:
            try:
                attribute = probe_v1._attribute(channel, name, label=label)
                attribute.value = original
                requested = probe_v1._number(original, label=f"original {label} {name}")
                observed = probe_v1._number(
                    attribute.value, label=f"restored {label} {name}"
                )
                if abs(observed - requested) > max(2.0, abs(requested) * 100e-6):
                    raise ProbeError(
                        f"restored {label} {name} readback {observed} differs from {requested}"
                    )
                key = f"{label.lower().replace(' ', '_')}_{name}"
                restored_values[key] = round(observed)
            except Exception as error:  # noqa: BLE001 - best-effort restoration inventory
                errors.append(f"{label} {name}: {error}")
        restored = bool(originals) and not errors
        if context is not None:
            close = getattr(context, "close", None)
            if callable(close):
                with suppress(BaseException):
                    close()
        if errors:
            raise ProbeError("RX attribute restoration failed: " + "; ".join(errors))
        if originals and not restored:
            raise ProbeError("RX attribute restoration was not verified")
    if measurement is None:
        raise ProbeError("probe measurement did not complete")
    measurement["iio_restore_verified"] = restored
    measurement["iio_restored"] = restored_values
    return measurement


def execute_plan(args: Any) -> dict[str, Any]:
    original = probe_v1._measure
    probe_v1._measure = _measure
    try:
        return probe_v3.execute_plan(args)
    finally:
        probe_v1._measure = original


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
