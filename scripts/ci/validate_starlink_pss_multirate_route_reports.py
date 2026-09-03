#!/usr/bin/env python3
"""Validate the exact routed CDC and bus-skew inventory of multirate PSS RX."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MAX_REPORT_BYTES = 32 * 1024 * 1024
EXPECTED_SUMMARY = {
    ("CDC-1", "Critical"): 1,
    ("CDC-3", "Info"): 31,
    ("CDC-4", "Critical"): 1,
    ("CDC-6", "Warning"): 9,
    ("CDC-9", "Info"): 5,
    ("CDC-15", "Warning"): 217,
    ("CDC-17", "Warning"): 8,
}
EXPECTED_BUS_SKEW_MET = 6
EXPECTED_BUS_SKEW_ENDPOINTS = (8, 8, 32, 64, 4, 4)

DETAIL_ROW = re.compile(
    r"^[ \t]*[0-9]+[ \t]+(CDC-[0-9]+)[ \t]+"
    r"(Critical|Warning|Info)[ \t]+.*$",
    re.MULTILINE,
)
SUMMARY_ROW = re.compile(
    r"^(CDC-[0-9]+)[ \t]+(Critical|Warning|Info)[ \t]+([0-9]+)[ \t]+.*$",
    re.MULTILINE,
)

CRITICAL_CROSSINGS = (
    (
        "CDC-1",
        "cpack_timestamp/inst/overflow_sync/input_reg_reg[0]/C",
        "cpack_timestamp/inst/overflow_sync/output_reg_reg[0]/D",
    ),
    (
        "CDC-4",
        "cpack_timestamp/inst/timestamp_cpu_sync/input_reg_reg[31:0]/C",
        "cpack_timestamp/inst/timestamp_cpu_sync/output_reg_reg[31:0]/D",
    ),
)

MULTIBIT_CROSSINGS = (
    ("sample_cdc/source_dropped_count_gray_reg[31:0]/C", "sample_cdc/dropped_count_gray_sync_1_reg[31:0]/D"),
    ("sample_cdc/source_pointer_gray_reg[6:0]/C", "sample_cdc/write_pointer_gray_sync_1_reg[6:0]/D"),
    ("i_command_fifo/read_gray_reg[3:0]/C", "i_command_fifo/read_gray_write_sync_1_reg[3:0]/D"),
    ("i_descriptor_fifo/write_gray_reg[1:0]/C", "i_descriptor_fifo/write_gray_read_sync_1_reg[1:0]/D"),
    ("starlink_pss_tracker/inst/sample_index_gray_reg[63:0]/C", "starlink_pss_tracker/inst/sample_index_gray_sync_1_reg[63:0]/D"),
    ("sample_cdc/acquisition_pointer_gray_reg[6:0]/C", "sample_cdc/read_pointer_gray_sync_1_reg[6:0]/D"),
    ("i_command_fifo/write_gray_reg[2:0]/C", "i_command_fifo/write_gray_read_sync_1_reg[2:0]/D"),
    ("i_descriptor_fifo/read_gray_reg[2:0]/C", "i_descriptor_fifo/read_gray_write_sync_1_reg[2:0]/D"),
    ("i_capture_bridge/engine_release_toggle_reg[1:0]/C", "i_capture_bridge/sample_release_toggle_sync_1_reg[1:0]/D"),
)

BUS_SKEW_SOURCES = (
    "starlink_pss_acquisition/inst/sample_cdc/source_pointer_binary_reg[0]",
    "starlink_pss_acquisition/inst/sample_cdc/acquisition_pointer_binary_reg[0]",
    "starlink_pss_acquisition/inst/sample_cdc/source_dropped_count_gray_reg[0]",
    "starlink_pss_tracker/inst/sample_index_gray_reg[0]",
    "gen_cdc_pntr.wr_pntr_cdc_inst/src_gray_ff_reg[0]",
    "gen_cdc_pntr.rd_pntr_cdc_inst/src_gray_ff_reg[0]",
)


class ValidationError(RuntimeError):
    """A routed report differs from the reviewed multirate inventory."""


def _read_report(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValidationError(f"cannot stat routed report {path}: {exc}") from exc
    if size <= 0 or size > MAX_REPORT_BYTES:
        raise ValidationError(f"routed report {path} has invalid size {size} bytes")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"cannot read routed report {path}: {exc}") from exc


def validate_cdc_report(text: str) -> None:
    summary_rows = SUMMARY_ROW.findall(text)
    summary = {(rule, severity): int(count) for rule, severity, count in summary_rows}
    if summary != EXPECTED_SUMMARY or len(summary_rows) != len(EXPECTED_SUMMARY):
        raise ValidationError(
            f"multirate CDC summary differs: expected {EXPECTED_SUMMARY}, got {summary}"
        )

    rows = [match.group(0) for match in DETAIL_ROW.finditer(text)]
    if len(rows) != sum(EXPECTED_SUMMARY.values()):
        raise ValidationError(
            "multirate CDC detail count differs: "
            f"expected {sum(EXPECTED_SUMMARY.values())}, got {len(rows)}"
        )

    critical_rows = [row for row in rows if " Critical " in f" {row} "]
    if len(critical_rows) != len(CRITICAL_CROSSINGS):
        raise ValidationError(
            f"expected exactly two reviewed Critical crossings, got {len(critical_rows)}"
        )
    for rule, source, destination in CRITICAL_CROSSINGS:
        matches = [
            row
            for row in critical_rows
            if rule in row and source in row and destination in row
        ]
        if len(matches) != 1:
            raise ValidationError(f"reviewed critical crossing is missing or duplicated: {source}")

    multibit_rows = [
        row for row in rows if re.search(r"[ \t]CDC-6[ \t]+Warning[ \t]", row)
    ]
    if len(multibit_rows) != len(MULTIBIT_CROSSINGS):
        raise ValidationError(
            f"expected {len(MULTIBIT_CROSSINGS)} reviewed CDC-6 rows, got {len(multibit_rows)}"
        )
    for source, destination in MULTIBIT_CROSSINGS:
        matches = [
            row for row in multibit_rows if source in row and destination in row
        ]
        if len(matches) != 1:
            raise ValidationError(f"reviewed multibit crossing is missing or duplicated: {source}")


def validate_bus_skew_report(text: str) -> None:
    if "Slack (VIOLATED)" in text:
        raise ValidationError("multirate routed bus-skew report has a violation")
    met = text.count("Slack (MET)")
    if met != EXPECTED_BUS_SKEW_MET:
        raise ValidationError(
            f"expected exactly {EXPECTED_BUS_SKEW_MET} met bus-skew constraints, got {met}"
        )
    endpoint_counts = tuple(
        int(value) for value in re.findall(r"^Endpoints:[ \t]+([0-9]+)$", text, re.MULTILINE)
    )
    if endpoint_counts != EXPECTED_BUS_SKEW_ENDPOINTS:
        raise ValidationError(
            "multirate bus-skew endpoint inventory differs: "
            f"expected {EXPECTED_BUS_SKEW_ENDPOINTS}, got {endpoint_counts}"
        )
    commands = re.findall(
        r"^set_bus_skew .*?(?=^Requirement:)", text, re.MULTILINE | re.DOTALL
    )
    if len(commands) != EXPECTED_BUS_SKEW_MET:
        raise ValidationError(
            f"expected six set_bus_skew command inventories, got {len(commands)}"
        )
    for source in BUS_SKEW_SOURCES:
        matches = [command for command in commands if source in command]
        if len(matches) != 1:
            raise ValidationError(f"reviewed bus-skew source is missing or duplicated: {source}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cdc_report", type=Path)
    parser.add_argument("bus_skew_report", type=Path)
    args = parser.parse_args(argv)
    try:
        validate_cdc_report(_read_report(args.cdc_report))
        validate_bus_skew_report(_read_report(args.bus_skew_report))
    except ValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS exact multirate PSS RX routed CDC and six-constraint bus-skew inventories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
