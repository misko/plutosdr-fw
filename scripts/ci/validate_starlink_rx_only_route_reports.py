#!/usr/bin/env python3
"""Validate the exact routed CDC and bus-skew inventory of the DNM RX shell."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EXPECTED_BUS_SKEW_MET = 3
EXPECTED_MONITOR_PAYLOAD_ROWS = 293
EXPECTED_MONITOR_TOGGLE_ROWS = 2
EXPECTED_MONITOR_ROWS = EXPECTED_MONITOR_PAYLOAD_ROWS + EXPECTED_MONITOR_TOGGLE_ROWS
MAX_REPORT_BYTES = 32 * 1024 * 1024

MONITOR_SCOPE = "starlink_pss_candidate_monitor/inst/i_event_cdc/"
OVERFLOW_SCOPE = "cpack_timestamp/inst/overflow_sync/"
TIMESTAMP_SCOPE = "cpack_timestamp/inst/timestamp_cpu_sync/"

DETAIL_ROW = re.compile(
    r"^[ \t]*[0-9]+[ \t]+CDC-[0-9]+[ \t]+"
    r"(?:Critical|Warning|Info)[ \t]+.*$",
    re.MULTILINE,
)


class ValidationError(RuntimeError):
    """A routed report differs from the reviewed RX-only inventory."""


def _read_report(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValidationError(f"cannot stat routed report {path}: {exc}") from exc
    if size <= 0 or size > MAX_REPORT_BYTES:
        raise ValidationError(
            f"routed report {path} has invalid size {size} bytes"
        )
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"cannot read routed report {path}: {exc}") from exc


def _has_kind(row: str, rule: str, severity: str) -> bool:
    return re.search(
        rf"[ \t]{re.escape(rule)}[ \t]+{re.escape(severity)}[ \t]", row
    ) is not None


def validate_cdc_report(text: str) -> None:
    rows = DETAIL_ROW.findall(text)
    if not rows:
        raise ValidationError("routed CDC detail inventory is empty or malformed")

    monitor_rows = [row for row in rows if MONITOR_SCOPE in row]
    monitor_critical = [
        row for row in monitor_rows if " Critical " in f" {row} "
    ]
    if monitor_critical:
        raise ValidationError(
            "diagnostic monitor contributes Critical routed CDC rows"
        )

    monitor_cdc15 = [
        row for row in monitor_rows if _has_kind(row, "CDC-15", "Warning")
    ]
    monitor_payload = [
        row
        for row in monitor_cdc15
        if "mailbox_" in row and "snapshot_" in row
    ]
    if len(monitor_cdc15) != EXPECTED_MONITOR_PAYLOAD_ROWS:
        raise ValidationError(
            "diagnostic monitor CDC-15 inventory differs: "
            f"expected {EXPECTED_MONITOR_PAYLOAD_ROWS}, got {len(monitor_cdc15)}"
        )
    if len(monitor_payload) != EXPECTED_MONITOR_PAYLOAD_ROWS:
        raise ValidationError(
            "diagnostic monitor CDC-15 rows do not exactly cover the reviewed "
            "mailbox-to-snapshot payload"
        )

    monitor_cdc3 = [
        row for row in monitor_rows if _has_kind(row, "CDC-3", "Info")
    ]
    monitor_toggles = [
        row
        for row in monitor_cdc3
        if "_toggle_reg" in row and "_sync_1_reg" in row
    ]
    if len(monitor_cdc3) != EXPECTED_MONITOR_TOGGLE_ROWS:
        raise ValidationError(
            "diagnostic monitor CDC-3 inventory differs: "
            f"expected {EXPECTED_MONITOR_TOGGLE_ROWS}, got {len(monitor_cdc3)}"
        )
    if len(monitor_toggles) != EXPECTED_MONITOR_TOGGLE_ROWS:
        raise ValidationError(
            "diagnostic monitor CDC-3 rows do not exactly cover the reviewed "
            "request/acknowledgement toggles"
        )
    if len(monitor_rows) != EXPECTED_MONITOR_ROWS:
        raise ValidationError(
            "diagnostic monitor routed CDC inventory differs: "
            f"expected {EXPECTED_MONITOR_ROWS} total rows, got {len(monitor_rows)}"
        )

    critical_rows = [row for row in rows if " Critical " in f" {row} "]
    if len(critical_rows) != 2:
        raise ValidationError(
            "RX-only routed CDC critical inventory differs from the two "
            f"reviewed crossings: got {len(critical_rows)}"
        )
    overflow_rows = [
        row
        for row in critical_rows
        if _has_kind(row, "CDC-1", "Critical") and OVERFLOW_SCOPE in row
    ]
    timestamp_rows = [
        row
        for row in critical_rows
        if _has_kind(row, "CDC-4", "Critical") and TIMESTAMP_SCOPE in row
    ]
    if len(overflow_rows) != 1:
        raise ValidationError(
            "RX-only routed CDC report lacks the one reviewed overflow "
            "snapshot crossing"
        )
    if len(timestamp_rows) != 1:
        raise ValidationError(
            "RX-only routed CDC report lacks the one reviewed timestamp "
            "snapshot crossing"
        )


def validate_bus_skew_report(text: str) -> None:
    violated = text.count("Slack (VIOLATED)")
    if violated:
        raise ValidationError(
            f"RX-only routed bus-skew report has {violated} violated constraints"
        )
    met = text.count("Slack (MET)")
    if met != EXPECTED_BUS_SKEW_MET:
        raise ValidationError(
            "RX-only routed bus-skew inventory differs: "
            f"expected exactly {EXPECTED_BUS_SKEW_MET} met constraints, got {met}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdc-report", required=True, type=Path)
    parser.add_argument("--bus-skew-report", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        validate_cdc_report(_read_report(args.cdc_report))
        validate_bus_skew_report(_read_report(args.bus_skew_report))
    except ValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(
        "PASS exact RX-only routed CDC and three-constraint bus-skew inventories"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
