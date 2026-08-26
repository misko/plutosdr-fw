"""Strict offline validator for the routed tandem-AGC OOC report set."""

from __future__ import annotations

import os
import re
import stat
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path


class ValidationError(RuntimeError):
    """The routed OOC evidence does not match the frozen acceptance contract."""


TOOL_VERSION = "Vivado v.2022.2 (lin64) Build 3671981 Fri Oct 14 04:59:54 MDT 2022"
DESIGN = "tandem_agc_axi"
REPORT_LIMITS = {
    "cdc-summary.rpt": 64 * 1024,
    "cdc-details.rpt": 1024 * 1024,
    "clock_interaction.rpt": 128 * 1024,
    "drc.rpt": 1024 * 1024,
    "methodology.rpt": 2 * 1024 * 1024,
    "route_status.rpt": 64 * 1024,
    "timing_summary.rpt": 8 * 1024 * 1024,
    "utilization.rpt": 1024 * 1024,
    "vivado.log": 16 * 1024 * 1024,
}

CDC_SUMMARY = {
    (
        "Warning",
        "s_axi_aclk",
        "l_clk",
        "No Common Primary Clock",
        "Asynch Clock Groups",
    ): (112, 112, 0, 0, 0),
    (
        "Warning",
        "l_clk",
        "s_axi_aclk",
        "No Common Primary Clock",
        "Asynch Clock Groups",
    ): (39, 39, 0, 0, 0),
}
CDC_RULES = {
    "CDC-3": ("Info", 5, "1-bit synchronized with ASYNC_REG property"),
    "CDC-6": ("Warning", 2, "Multi-bit synchronized with ASYNC_REG property"),
    "CDC-15": ("Warning", 133, "Clock enable controlled CDC structure detected"),
}
CDC_DIRECTIONS = {
    ("s_axi_aclk", "l_clk"): Counter(
        {
            ("CDC-3", "Info", 3): 2,
            ("CDC-6", "Warning", 2): 1,
            ("CDC-15", "Warning", 0): 103,
        }
    ),
    ("l_clk", "s_axi_aclk"): Counter(
        {
            ("CDC-3", "Info", 2): 1,
            ("CDC-3", "Info", 3): 2,
            ("CDC-6", "Warning", 2): 1,
            ("CDC-15", "Warning", 0): 30,
        }
    ),
}
CDC_BUS_WIDTHS = {
    ("s_axi_aclk", "l_clk"): 7,
    ("l_clk", "s_axi_aclk"): 6,
}
DRC_RULES = {
    "REQP-1839": ("Warning", "RAMB36 async control check", 18),
    "ZPS7-1": ("Warning", "PS7 block required", 1),
}
METHODOLOGY_RULES = {
    "LUTAR-1": ("Warning", "LUT drives async reset alert", 1),
    "TIMING-18": ("Warning", "Missing input or output delay", 182),
}
CHECK_TIMING = {
    "no_clock": 0,
    "constant_clock": 0,
    "pulse_width_clock": 0,
    "unconstrained_internal_endpoints": 0,
    "no_input_delay": 137,
    "no_output_delay": 45,
    "multiple_clock": 0,
    "generated_clocks": 0,
    "loops": 0,
    "partial_input_delay": 0,
    "partial_output_delay": 0,
    "latch_loops": 0,
}
TIMING_TOTAL = (
    Decimal("3.765"),
    Decimal("0.000"),
    0,
    1806,
    Decimal("0.079"),
    Decimal("0.000"),
    0,
    1806,
    Decimal("4.500"),
    Decimal("0.000"),
    0,
    698,
)
TIMING_BY_CLOCK = {
    "l_clk": (
        Decimal("9.129"),
        Decimal("0.000"),
        0,
        1001,
        Decimal("0.079"),
        Decimal("0.000"),
        0,
        1001,
        Decimal("7.638"),
        Decimal("0.000"),
        0,
        391,
    ),
    "s_axi_aclk": (
        Decimal("3.765"),
        Decimal("0.000"),
        0,
        805,
        Decimal("0.100"),
        Decimal("0.000"),
        0,
        805,
        Decimal("4.500"),
        Decimal("0.000"),
        0,
        307,
    ),
}
TIMING_MET_PATH_COUNT = 200
ROUTE_COUNTS = {
    "logical nets": 1657,
    "nets not needing routing": 530,
    "internally routed nets": 349,
    "implicitly routed ports": 181,
    "routable nets": 1127,
    "fully routed nets": 1127,
    "nets with routing errors": 0,
}
UTILIZATION = {
    "Slice LUTs": (475, 17600, Decimal("2.70")),
    "Slice Registers": (694, 35200, Decimal("1.97")),
    "Block RAM Tile": (2, 60, Decimal("3.33")),
    "DSPs": (0, 80, Decimal("0.00")),
}
UTILIZATION_OCCURRENCES = {
    "Slice LUTs": 1,
    "Slice Registers": 2,
    "Block RAM Tile": 1,
    "DSPs": 1,
}
HEADED_REPORTS = tuple(name for name in REPORT_LIMITS if name.endswith(".rpt"))


def _fail(message: str) -> None:
    raise ValidationError(message)


def _close_descriptor(descriptor: int, label: str) -> None:
    try:
        os.close(descriptor)
    except OSError as error:
        raise ValidationError(f"cannot close {label}: {error}") from error


def _read_report(directory_fd: int, name: str, limit: int) -> str:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except (OSError, TypeError, ValueError) as error:
        raise ValidationError(f"cannot open {name}: {error}") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            _fail(f"{name} is not a regular file")
        if before.st_size <= 0 or before.st_size > limit:
            _fail(f"{name} size is outside 1..{limit}: {before.st_size}")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                _fail(f"{name} ended before its attested size")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail(f"{name} grew during the bounded read")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
        ):
            _fail(f"{name} identity or size changed during the bounded read")
    except OSError as error:
        raise ValidationError(f"cannot read {name}: {error}") from error
    finally:
        _close_descriptor(descriptor, name)
    try:
        text = b"".join(chunks).decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValidationError(f"{name} is not strict UTF-8") from error
    if "\x00" in text:
        _fail(f"{name} contains a NUL byte")
    return text


def _single_regex(text: str, pattern: str, label: str) -> re.Match[str]:
    matches = list(re.finditer(pattern, text, flags=re.MULTILINE))
    if len(matches) != 1:
        _fail(f"{label} must appear exactly once, found {len(matches)}")
    return matches[0]


def _require_header(
    text: str,
    *,
    name: str,
    device: str,
    command_pattern: str,
) -> None:
    escaped_tool = re.escape(TOOL_VERSION)
    _single_regex(
        text,
        rf"^\| Tool Version\s*:\s*{escaped_tool}\s*$",
        f"{name} tool header",
    )
    _single_regex(
        text,
        rf"^\| Design\s*:\s*{re.escape(DESIGN)}\s*$",
        f"{name} design header",
    )
    _single_regex(
        text,
        rf"^\| Device\s*:\s*{re.escape(device)}\s*$",
        f"{name} device header",
    )
    _single_regex(text, command_pattern, f"{name} command header")


def _split_columns(line: str) -> list[str]:
    return re.split(r"[ \t]{2,}", line.strip())


def _validate_vivado_log(text: str) -> None:
    _single_regex(
        text,
        r"^\*{6} Vivado v2022\.2 \(64-bit\)\s*$",
        "Vivado log tool version",
    )
    _single_regex(
        text,
        r"^\s*\*{4} SW Build 3671981 on Fri Oct 14 04:59:54 MDT 2022\s*$",
        "Vivado log software build",
    )
    _single_regex(
        text,
        r"^\s*\*{4} IP Build 3669848 on Fri Oct 14 08:30:02 MDT 2022\s*$",
        "Vivado log IP build",
    )
    _single_regex(
        text,
        r"^=== TANDEM AXI ROUTE COMPLETE ===\s*$",
        "Vivado log route-complete marker",
    )
    if re.search(
        r"^[ \t]*(?:CRITICAL WARNING|ERROR|FATAL):",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    ):
        _fail("Vivado log contains an error, fatal, or critical warning")

    aggregate_lines = [
        line
        for line in text.splitlines()
        if re.search(r"critical warnings?", line, flags=re.IGNORECASE)
        and re.search(r"errors?\s+encountered", line, flags=re.IGNORECASE)
    ]
    if not aggregate_lines:
        _fail("Vivado log has no message-count aggregate")
    aggregate_pattern = re.compile(
        r"^([0-9]+) Infos, ([0-9]+) Warnings, "
        r"([0-9]+) Critical Warnings and ([0-9]+) Errors encountered\.$"
    )
    for line in aggregate_lines:
        match = aggregate_pattern.fullmatch(line.strip())
        if match is None:
            _fail(f"Vivado log has a malformed message-count aggregate: {line}")
        if int(match.group(3)) != 0 or int(match.group(4)) != 0:
            _fail(f"Vivado log has a nonzero critical/error aggregate: {line}")


def _validate_cdc_summary(text: str) -> None:
    _require_header(
        text,
        name="CDC summary",
        device="7z010-clg400",
        command_pattern=(
            r"^\| Command\s*:\s*report_cdc -no_waiver -file "
            r".+/cdc-summary\.rpt\s*$"
        ),
    )
    header = (
        "Severity  Source Clock  Destination Clock  CDC Type                 "
        "Exceptions           Endpoints  Safe  Unsafe  Unknown  No ASYNC_REG"
    )
    if text.count(header) != 1:
        _fail("CDC summary table header is not unique and exact")
    lines = text.splitlines()
    header_indices = [index for index, line in enumerate(lines) if line.rstrip() == header]
    if len(header_indices) != 1:
        _fail("CDC summary table header is not uniquely scoped")
    header_index = header_indices[0]
    if header_index + 1 >= len(lines) or _split_columns(lines[header_index + 1]) != [
        "--------",
        "------------",
        "-----------------",
        "-----------------------",
        "-------------------",
        "---------",
        "----",
        "------",
        "-------",
        "------------",
    ]:
        _fail("CDC summary table separator is malformed")
    table_lines: list[str] = []
    tail_start = len(lines)
    for index, line in enumerate(lines[header_index + 2 :], start=header_index + 2):
        if not line.strip():
            tail_start = index + 1
            break
        table_lines.append(line)
    if any(line.strip() for line in lines[tail_start:]):
        _fail("CDC summary has nonblank content after its bounded table")
    if len(table_lines) != len(CDC_SUMMARY):
        _fail(f"CDC summary must contain exactly two rows, found {len(table_lines)}")

    rows: dict[tuple[str, str, str, str, str], tuple[int, ...]] = {}
    for line in table_lines:
        fields = _split_columns(line)
        if len(fields) != 10:
            _fail(f"CDC summary row is malformed: {line}")
        key = tuple(fields[:5])
        try:
            counts = tuple(int(value) for value in fields[5:])
        except ValueError as error:
            raise ValidationError("CDC summary has a non-integer count") from error
        if key in rows:
            _fail(f"CDC summary duplicates direction: {key}")
        rows[key] = counts
    if rows != CDC_SUMMARY:
        _fail(f"CDC summary is not exact: {rows}")


def _cdc_rule_summary(text: str) -> dict[str, tuple[str, int, str]]:
    header = "ID      Severity  Count  Description"
    lines = text.splitlines()
    header_indices = [index for index, line in enumerate(lines) if line == header]
    if len(header_indices) != 1:
        _fail("CDC detail rule-summary header is not unique and exact")
    header_index = header_indices[0]
    if header_index + 1 >= len(lines) or not re.fullmatch(
        r"[- ]+", lines[header_index + 1]
    ):
        _fail("CDC detail rule-summary separator is malformed")
    table_lines: list[str] = []
    for line in lines[header_index + 2 :]:
        if not line.strip():
            break
        table_lines.append(line)
    if len(table_lines) != len(CDC_RULES):
        _fail("CDC detail rule summary has the wrong number of rows")
    row_pattern = re.compile(
        r"^(CDC-[0-9]+)[ \t]{2,}(\S+(?:[ \t]+\S+)?)"
        r"[ \t]{2,}([0-9]+)[ \t]{2,}(.+?)\s*$"
    )
    rows: dict[str, tuple[str, int, str]] = {}
    for line in table_lines:
        match = row_pattern.fullmatch(line)
        if match is None:
            _fail(f"CDC detail rule-summary row is malformed: {line}")
        rule, severity, count, description = match.groups()
        if rule in rows:
            _fail(f"CDC detail summary duplicates {rule}")
        rows[rule] = (severity, int(count), description)
    return rows


def _validate_cdc_details(text: str) -> None:
    _require_header(
        text,
        name="CDC details",
        device="7z010-clg400",
        command_pattern=(
            r"^\| Command\s*:\s*report_cdc -details -no_waiver -file "
            r".+/cdc-details\.rpt\s*$"
        ),
    )
    if _cdc_rule_summary(text) != CDC_RULES:
        _fail("CDC detail rule summary is not exact")
    identifiers = set(re.findall(r"\bCDC-[0-9]+\b", text))
    if identifiers != set(CDC_RULES):
        _fail(f"CDC details contain an unknown or missing rule: {identifiers}")

    section_pattern = re.compile(
        r"^Source Clock: (\S+)\n"
        r"Destination Clock: (\S+)\n"
        r"CDC Type: (.+?)\n(?P<body>.*?)(?=^Source Clock: |\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    sections = list(section_pattern.finditer(text))
    found: dict[tuple[str, str], Counter[tuple[str, str, int]]] = {}
    weighted_endpoints: dict[tuple[str, str], int] = {}
    global_counts: Counter[tuple[str, str]] = Counter()
    detail_pattern = re.compile(
        r"^\s*([0-9]+)\s+(CDC-[0-9]+)\s+"
        r"(Info|Warning|Critical Warning|Error)\s+(.+?)\s+([0-9]+)\s+"
        r"(Asynch Clock Groups)\s+(\S+)\s+(\S+)\s*$"
    )
    for section in sections:
        source, destination, cdc_type, body = (
            section.group(1),
            section.group(2),
            section.group(3),
            section.group("body"),
        )
        key = (source, destination)
        if key in found:
            _fail(f"CDC details duplicate direction: {key}")
        if cdc_type != "No Common Primary Clock":
            _fail(f"CDC details have the wrong type for {key}: {cdc_type}")
        counter: Counter[tuple[str, str, int]] = Counter()
        ordinals: list[int] = []
        endpoint_count = 0
        body_lines = body.splitlines()
        detail_header = (
            "Row  ID      Severity  Description                                     "
            "Depth  Exception            Source (From)                                "
            "Destination (To)"
        )
        header_indices = [
            index for index, line in enumerate(body_lines) if line.rstrip() == detail_header
        ]
        if len(header_indices) != 1:
            _fail(f"CDC detail table header is not unique and exact for {key}")
        detail_header_index = header_indices[0]
        if any(line.strip() for line in body_lines[:detail_header_index]):
            _fail(f"CDC detail section has unexpected pre-table content for {key}")
        if detail_header_index + 1 >= len(body_lines) or not re.fullmatch(
            r"[- ]+", body_lines[detail_header_index + 1]
        ):
            _fail(f"CDC detail table separator is malformed for {key}")
        candidate_rows = [
            line
            for line in body_lines[detail_header_index + 2 :]
            if line.strip()
        ]
        for line in candidate_rows:
            match = detail_pattern.fullmatch(line)
            if match is None:
                _fail(f"CDC detail row is malformed: {line}")
            (
                ordinal,
                rule,
                severity,
                description,
                depth,
                _exception,
                source_endpoint,
                destination_endpoint,
            ) = match.groups()
            if rule not in CDC_RULES or description != CDC_RULES[rule][2]:
                _fail(f"CDC detail description is not exact: {line}")
            ordinals.append(int(ordinal))
            counter[(rule, severity, int(depth))] += 1
            global_counts[(rule, severity)] += 1
            if rule == "CDC-6":
                source_ranges = re.findall(
                    r"\[([0-9]+):([0-9]+)\]", source_endpoint
                )
                destination_ranges = re.findall(
                    r"\[([0-9]+):([0-9]+)\]", destination_endpoint
                )
                if len(source_ranges) != 1 or len(destination_ranges) != 1:
                    _fail(f"CDC-6 must have exactly two ranged endpoints for {key}")
                source_width = abs(
                    int(source_ranges[0][0]) - int(source_ranges[0][1])
                ) + 1
                destination_width = abs(
                    int(destination_ranges[0][0]) - int(destination_ranges[0][1])
                ) + 1
                if (
                    source_width != destination_width
                    or source_width != CDC_BUS_WIDTHS[key]
                ):
                    _fail(f"CDC-6 bus width is not exact for {key}: {line}")
                endpoint_count += source_width
            else:
                endpoint_count += 1
        if ordinals != list(range(1, len(ordinals) + 1)):
            _fail(f"CDC detail row ordinals are not contiguous for {key}")
        found[key] = counter
        weighted_endpoints[key] = endpoint_count
    if found != CDC_DIRECTIONS:
        _fail(f"CDC detailed per-direction inventory is not exact: {found}")
    expected_global = Counter(
        {
            (rule, severity): count
            for rule, (severity, count, _description) in CDC_RULES.items()
        }
    )
    if global_counts != expected_global:
        _fail(f"CDC detailed global inventory is not exact: {global_counts}")
    expected_endpoints = {
        (key[1], key[2]): value[0] for key, value in CDC_SUMMARY.items()
    }
    if weighted_endpoints != expected_endpoints:
        _fail(
            "CDC detail endpoint widths do not cross-bind to the summary: "
            f"{weighted_endpoints}"
        )


def _parse_pipe_rule_summary(
    text: str,
    *,
    label: str,
    expected: dict[str, tuple[str, str, int]],
) -> None:
    header_pattern = r"^\| Rule\s+\| Severity\s+\| Description\s+\| Violations \|\s*$"
    header_match = _single_regex(text, header_pattern, f"{label} rule-summary header")
    lines = text.splitlines()
    header_index = text[: header_match.start()].count("\n")
    if header_index + 1 >= len(lines) or not re.fullmatch(
        r"\+[+-]+\+", lines[header_index + 1].strip()
    ):
        _fail(f"{label} rule-summary separator is malformed")
    table_lines: list[str] = []
    for line in lines[header_index + 2 :]:
        if re.fullmatch(r"\+[+-]+\+", line.strip()):
            break
        if not line.strip():
            _fail(f"{label} rule-summary table ended without a separator")
        table_lines.append(line)
    if len(table_lines) != len(expected):
        _fail(f"{label} rule-summary table has the wrong number of rows")
    row_pattern = re.compile(
        r"^\|\s*([A-Z][A-Z0-9_-]*-[0-9]+)\s*\|\s*"
        r"([^|]+?)\s*\|\s*(.+?)\s*\|\s*([0-9]+)\s*\|\s*$"
    )
    rows: dict[str, tuple[str, str, int]] = {}
    for line in table_lines:
        match = row_pattern.fullmatch(line)
        if match is None:
            _fail(f"{label} rule-summary row is malformed: {line}")
        rule, severity, description, count = match.groups()
        if rule in rows:
            _fail(f"{label} summary duplicates {rule}")
        rows[rule] = (severity, description.rstrip(), int(count))
    if rows != expected:
        _fail(f"{label} rule summary is not exact: {rows}")
    total = sum(value[2] for value in expected.values())
    _single_regex(
        text,
        rf"^\s*Violations found:\s*{total}\s*$",
        f"{label} total violation count",
    )
    identifiers = set(re.findall(r"\b[A-Z][A-Z0-9_-]*-[0-9]+\b", text))
    if identifiers != set(expected):
        _fail(f"{label} contains an unknown or missing rule: {identifiers}")
    details: dict[str, list[int]] = {rule: [] for rule in expected}
    detail_heading = re.compile(
        r"^([A-Z][A-Z0-9_-]*-[0-9]+)#([1-9][0-9]*)\s+(.+?)\s*$"
    )
    for index, line in enumerate(lines):
        match = detail_heading.fullmatch(line)
        if match is None:
            continue
        rule, ordinal, severity = match.groups()
        if rule not in expected:
            _fail(f"{label} detail contains an unknown rule: {rule}")
        if severity != expected[rule][0]:
            _fail(f"{label} detail has the wrong severity for {rule}")
        if index + 1 >= len(lines) or lines[index + 1].rstrip() != expected[rule][1]:
            _fail(f"{label} detail has the wrong description for {rule}")
        details[rule].append(int(ordinal))
    for rule, (_severity, description, count) in expected.items():
        if details[rule] != list(range(1, count + 1)):
            _fail(f"{label} detail ordinals are not exact for {rule}")


def _validate_methodology_timing18_details(text: str) -> None:
    lines = text.splitlines()
    input_details = 0
    output_details = 0
    for index, line in enumerate(lines):
        if re.fullmatch(r"TIMING-18#[1-9][0-9]* Warning", line) is None:
            continue
        if index + 2 >= len(lines):
            _fail("TIMING-18 detail is truncated")
        causal_detail = lines[index + 2].strip()
        if re.fullmatch(
            r"An input delay is missing on .+ relative to clock\(s\) .+",
            causal_detail,
        ):
            input_details += 1
        elif re.fullmatch(
            r"An output delay is missing on .+ relative to clock\(s\) .+",
            causal_detail,
        ):
            output_details += 1
        else:
            _fail(f"TIMING-18 has an unsupported detail class: {causal_detail}")
    expected = (
        CHECK_TIMING["no_input_delay"],
        CHECK_TIMING["no_output_delay"],
    )
    if (input_details, output_details) != expected:
        _fail(
            "TIMING-18 input/output detail split does not cross-bind to "
            f"check_timing: {(input_details, output_details)}"
        )


def _validate_drc(text: str) -> None:
    _require_header(
        text,
        name="DRC",
        device="xc7z010clg400-1",
        command_pattern=(
            r"^\| Command\s*:\s*report_drc -ruledeck default -no_waivers "
            r"-file .+/drc\.rpt\s*$"
        ),
    )
    _single_regex(
        text,
        r"^\| Design State\s*:\s*Fully Routed\s*$",
        "DRC routed state",
    )
    _parse_pipe_rule_summary(text, label="DRC", expected=DRC_RULES)


def _validate_methodology(text: str) -> None:
    _require_header(
        text,
        name="methodology",
        device="xc7z010clg400-1",
        command_pattern=(
            r"^\| Command\s*:\s*report_methodology -no_waivers "
            r"-file .+/methodology\.rpt\s*$"
        ),
    )
    _single_regex(
        text,
        r"^\| Design State\s*:\s*Fully Routed\s*$",
        "methodology routed state",
    )
    _parse_pipe_rule_summary(
        text,
        label="methodology",
        expected=METHODOLOGY_RULES,
    )
    _validate_methodology_timing18_details(text)


def _numeric_row(line: str, *, label: str) -> tuple[Decimal | int, ...]:
    fields = line.split()
    if len(fields) != 12:
        _fail(f"{label} must contain exactly 12 numeric fields")
    values: list[Decimal | int] = []
    for index, field in enumerate(fields):
        try:
            if index in {2, 3, 6, 7, 10, 11}:
                if not re.fullmatch(r"[0-9]+", field):
                    _fail(f"{label} integer field {index} is malformed")
                values.append(int(field))
            else:
                if re.fullmatch(r"-?[0-9]+\.[0-9]{3}", field) is None:
                    _fail(f"{label} decimal field {index} is noncanonical")
                values.append(Decimal(field))
        except InvalidOperation as error:
            raise ValidationError(f"{label} has an invalid decimal") from error
    return tuple(values)


def _line_after_table_header(text: str, header_fragment: str, label: str) -> str:
    lines = text.splitlines()
    indices = [index for index, line in enumerate(lines) if header_fragment in line]
    if len(indices) != 1:
        _fail(f"{label} header must appear exactly once")
    for line in lines[indices[0] + 1 :]:
        stripped = line.strip()
        if not stripped or re.fullmatch(r"[- ]+", stripped):
            continue
        return stripped
    _fail(f"{label} data row is missing")


def _unique_section(text: str, start: str, end: str, label: str) -> str:
    if text.count(start) != 1 or text.count(end) != 1:
        _fail(f"{label} section boundaries are not unique")
    prefix, remainder = text.split(start, 1)
    if end in prefix:
        _fail(f"{label} section boundaries are out of order")
    section, _suffix = remainder.split(end, 1)
    return section


def _table_rows_after_header(
    section: str,
    *,
    header_fragment: str,
    label: str,
    expected_tail: tuple[str, ...] = (),
) -> list[str]:
    lines = section.splitlines()
    header_indices = [
        index for index, line in enumerate(lines) if header_fragment in line
    ]
    if len(header_indices) != 1:
        _fail(f"{label} header must appear exactly once")
    header_index = header_indices[0]
    if header_index + 1 >= len(lines) or not re.fullmatch(
        r"[- ]+", lines[header_index + 1].strip()
    ):
        _fail(f"{label} separator is malformed")
    rows: list[str] = []
    tail_start = len(lines)
    for index, line in enumerate(lines[header_index + 2 :], start=header_index + 2):
        if not line.strip():
            tail_start = index + 1
            break
        rows.append(line.rstrip())
    tail = [
        line.strip()
        for line in lines[tail_start:]
        if line.strip() and re.fullmatch(r"-+", line.strip()) is None
    ]
    if tuple(tail) != expected_tail:
        _fail(f"{label} has unexpected content outside its bounded rows: {tail}")
    return rows


def _validate_timing(text: str) -> dict[str, str]:
    _require_header(
        text,
        name="timing",
        device="7z010-clg400",
        command_pattern=(
            r"^\| Command\s*:\s*report_timing_summary -delay_type min_max "
            r"-max_paths 50 -report_unconstrained -check_timing_verbose "
            r"-file .+/timing_summary\.rpt\s*$"
        ),
    )
    design_summary = _unique_section(
        text,
        "| Design Timing Summary",
        "| Clock Summary",
        "design timing summary",
    )
    if design_summary.count("All user specified timing constraints are met.") != 1:
        _fail("timing success sentence is not unique and scoped")
    design_rows = _table_rows_after_header(
        design_summary,
        header_fragment="WNS(ns)      TNS(ns)  TNS Failing Endpoints",
        label="design timing summary",
        expected_tail=("All user specified timing constraints are met.",),
    )
    if len(design_rows) != 1:
        _fail("design timing summary must contain exactly one numeric row")
    total = _numeric_row(design_rows[0], label="design timing summary")
    if total != TIMING_TOTAL:
        _fail(f"design timing summary is not exact: {total}")

    intra_section = _unique_section(
        text,
        "| Intra Clock Table",
        "| Inter Clock Table",
        "timing intra-clock",
    )
    intra_rows = _table_rows_after_header(
        intra_section,
        header_fragment="Clock             WNS(ns)",
        label="timing intra-clock table",
    )
    clock_rows: dict[str, tuple[Decimal | int, ...]] = {}
    for line in intra_rows:
        fields = line.split(maxsplit=1)
        if len(fields) != 2:
            _fail(f"timing intra-clock row is malformed: {line}")
        clock = fields[0]
        if clock in clock_rows:
            _fail(f"timing intra-clock row duplicates {clock}")
        clock_rows[clock] = _numeric_row(fields[1], label=f"{clock} timing row")
    if clock_rows != TIMING_BY_CLOCK:
        _fail(f"per-clock timing inventory is not exact: {clock_rows}")
    if total[3] != sum(row[3] for row in clock_rows.values()):
        _fail("setup endpoint totals do not cross-bind to the two clocks")
    if total[7] != sum(row[7] for row in clock_rows.values()):
        _fail("hold endpoint totals do not cross-bind to the two clocks")
    if total[11] != sum(row[11] for row in clock_rows.values()):
        _fail("pulse endpoint totals do not cross-bind to the two clocks")

    clock_section = _unique_section(
        text,
        "| Clock Summary",
        "| Intra Clock Table",
        "timing clock-summary",
    )
    clock_summary_rows = _table_rows_after_header(
        clock_section,
        header_fragment="Clock       Waveform(ns)",
        label="timing clock-summary table",
    )
    clock_lines: Counter[tuple[str, tuple[str, ...]]] = Counter()
    clock_row_pattern = re.compile(
        r"^(\S+)\s+(\{[0-9.]+ [0-9.]+\})\s+([0-9.]+)\s+([0-9.]+)\s*$"
    )
    for line in clock_summary_rows:
        match = clock_row_pattern.fullmatch(line)
        if match is None:
            _fail(f"timing clock-summary row is malformed: {line}")
        name, waveform, period, frequency = match.groups()
        clock_lines[(name, (*waveform.split(), period, frequency))] += 1
    expected_clocks = Counter(
        {
            ("l_clk", ("{0.000", "8.138}", "16.276", "61.440")): 1,
            ("s_axi_aclk", ("{0.000", "5.000}", "10.000", "100.000")): 1,
        }
    )
    if clock_lines != expected_clocks:
        _fail(f"timing clock inventory is not exact: {clock_lines}")

    checks = re.findall(
        r"^([0-9]+)\. checking ([a-z_]+) \(([0-9]+)\)\s*$",
        text,
        flags=re.MULTILINE,
    )
    expected_checks = [
        (str(ordinal), name, str(count))
        for ordinal, (name, count) in enumerate(CHECK_TIMING.items(), start=1)
    ] * 2
    if checks != expected_checks:
        _fail(f"check_timing inventory is not exact: {checks}")
    if CHECK_TIMING["no_input_delay"] + CHECK_TIMING["no_output_delay"] != 182:
        _fail("TIMING-18 cross-report invariant is internally inconsistent")

    methodology_section = _unique_section(
        text,
        "| Report Methodology",
        "check_timing report",
        "timing embedded methodology",
    )
    embedded_lines = _table_rows_after_header(
        methodology_section,
        header_fragment="Rule       Severity  Description",
        label="timing embedded methodology table",
        expected_tail=(
            (
                "Note: This report is based on the most recent "
                "report_methodology run and may not be up-to-date. Run "
                "report_methodology on the current design for the latest report."
            ),
        ),
    )
    embedded_rows: Counter[tuple[str, str, str, int]] = Counter()
    for line in embedded_lines:
        fields = _split_columns(line)
        if len(fields) != 4 or not fields[3].isdigit():
            _fail(f"timing embedded methodology row is malformed: {line}")
        embedded_rows[(fields[0], fields[1], fields[2], int(fields[3]))] += 1
    if embedded_rows != Counter(
        {
            ("LUTAR-1", "Warning", "LUT drives async reset alert", 1): 1,
            ("TIMING-18", "Warning", "Missing input or output delay", 182): 1,
        }
    ):
        _fail("timing report methodology inventory is not exact")

    if re.search(r"^Slack \(VIOLATED\)\s*:", text, flags=re.MULTILINE):
        _fail("timing report contains a violated detailed path")
    met_slacks = re.findall(
        r"^Slack \(MET\)\s*:\s*([+-]?[0-9]+(?:\.[0-9]+)?)ns\s+"
        r"\((required time - arrival time|arrival time - required time)\)\s*$",
        text,
        flags=re.MULTILINE,
    )
    if len(met_slacks) != TIMING_MET_PATH_COUNT:
        _fail(
            "timing detailed-path inventory is not exact: "
            f"{len(met_slacks)}"
        )
    try:
        setup_slacks = [
            Decimal(value)
            for value, kind in met_slacks
            if kind == "required time - arrival time"
        ]
        hold_slacks = [
            Decimal(value)
            for value, kind in met_slacks
            if kind == "arrival time - required time"
        ]
    except InvalidOperation as error:
        raise ValidationError("timing detailed path has an invalid slack") from error
    if len(setup_slacks) != 100 or len(hold_slacks) != 100:
        _fail("timing detailed-path setup/hold partition is not 100/100")
    if min(setup_slacks) != TIMING_TOTAL[0] or min(hold_slacks) != TIMING_TOTAL[4]:
        _fail("timing detailed-path minima do not cross-bind to WNS/WHS")
    if any(slack < 0 for slack in [*setup_slacks, *hold_slacks]):
        _fail("timing detailed-path inventory contains negative slack")
    return {
        "WNS_ns": str(total[0]),
        "TNS_ns": str(total[1]),
        "TNS_failing_endpoints": str(total[2]),
        "TNS_total_endpoints": str(total[3]),
        "WHS_ns": str(total[4]),
        "THS_ns": str(total[5]),
        "THS_failing_endpoints": str(total[6]),
        "THS_total_endpoints": str(total[7]),
        "WPWS_ns": str(total[8]),
        "TPWS_ns": str(total[9]),
        "TPWS_failing_endpoints": str(total[10]),
        "TPWS_total_endpoints": str(total[11]),
    }


def _validate_route(text: str) -> None:
    lines = text.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) != 11 or lines[0] != "Design Route Status":
        _fail("route-status report does not have the exact table shape")
    if re.fullmatch(r"\s*:\s*# nets\s*:\s*", lines[1]) is None:
        _fail("route-status column header is malformed")
    for separator in (lines[2], lines[10]):
        if re.fullmatch(r"\s*-+\s*:\s*-+\s*:\s*", separator) is None:
            _fail("route-status separator is malformed")
    row_pattern = re.compile(
        r"^\s*# of ([a-z ]+?)\.*\s*:\s*([0-9]+)\s*:\s*$"
    )
    counts: dict[str, int] = {}
    for expected_label, line in zip(ROUTE_COUNTS, lines[3:10], strict=True):
        match = row_pattern.fullmatch(line)
        if match is None:
            _fail(f"route-status row is malformed: {line}")
        label, count = match.groups()
        if label != expected_label or label in counts:
            _fail(f"route-status row order or label is not exact: {label}")
        counts[label] = int(count)
    if counts != ROUTE_COUNTS:
        _fail(f"route inventory is not exact: {counts}")
    if counts["logical nets"] != (
        counts["nets not needing routing"] + counts["routable nets"]
    ):
        _fail("route logical-net equation is inconsistent")
    if counts["nets not needing routing"] != (
        counts["internally routed nets"] + counts["implicitly routed ports"]
    ):
        _fail("route no-routing equation is inconsistent")
    if (
        counts["routable nets"] <= 0
        or counts["fully routed nets"] != counts["routable nets"]
        or counts["nets with routing errors"] != 0
    ):
        _fail("route is incomplete or contains routing errors")


def _validate_clock_interaction(text: str) -> None:
    _require_header(
        text,
        name="clock interaction",
        device="7z010-clg400",
        command_pattern=(
            r"^\| Command\s*:\s*report_clock_interaction -file "
            r".+/clock_interaction\.rpt\s*$"
        ),
    )
    expected = Counter(
        {
            "l_clk l_clk rise - rise 9.13 0.00 0 1001 16.28 Clean Timed": 1,
            "l_clk s_axi_aclk 0 39 Ignored Asynchronous Groups": 1,
            "s_axi_aclk l_clk 0 112 Ignored Asynchronous Groups": 1,
            ("s_axi_aclk s_axi_aclk rise - rise 3.76 0.00 0 805 10.00 Clean Timed"): 1,
        }
    )
    section = text.split("Clock Interaction Table", 1)
    if len(section) != 2 or "Clock Interaction Table" in section[1]:
        _fail("clock-interaction table marker is not unique")
    table_lines = section[1].splitlines()
    header_indices = [
        index
        for index, line in enumerate(table_lines)
        if line.startswith("From Clock    To Clock")
    ]
    if len(header_indices) != 1:
        _fail("clock-interaction table header is not unique")
    header_index = header_indices[0]
    if header_index + 1 >= len(table_lines) or not re.fullmatch(
        r"[- ]+", table_lines[header_index + 1].strip()
    ):
        _fail("clock-interaction table separator is malformed")
    data_lines = [line for line in table_lines[header_index + 2 :] if line.strip()]
    rows = Counter(" ".join(line.split()) for line in data_lines)
    if rows != expected:
        _fail(f"clock-interaction inventory is not exact: {rows}")


def _validate_utilization(text: str) -> None:
    _require_header(
        text,
        name="utilization",
        device="xc7z010clg400-1",
        command_pattern=(
            r"^\| Command\s*:\s*report_utilization -file "
            r".+/utilization\.rpt\s*$"
        ),
    )
    _single_regex(
        text,
        r"^\| Design State\s*:\s*Routed\s*$",
        "utilization routed state",
    )
    found: dict[str, tuple[int, int, Decimal]] = {}
    for label, expected in UTILIZATION.items():
        matches = list(
            re.finditer(
                rf"^\|\s*{re.escape(label)}\s*\|\s*([0-9]+)\s*\|\s*"
                rf"[0-9]+\s*\|\s*[0-9]+\s*\|\s*([0-9]+)\s*\|\s*"
                rf"([0-9]+\.[0-9]+)\s*\|\s*$",
                text,
                flags=re.MULTILINE,
            )
        )
        unique = {
            (int(match.group(1)), int(match.group(2)), Decimal(match.group(3)))
            for match in matches
        }
        if unique != {expected} or len(matches) != UTILIZATION_OCCURRENCES[label]:
            _fail(f"utilization row is not unique and exact for {label}: {unique}")
        found[label] = expected
    if found != UTILIZATION:
        _fail("utilization inventory is incomplete")
    black_box_marker = "\n9. Black Boxes\n--------------\n"
    if text.count(black_box_marker) != 1:
        _fail("utilization black-box section is not unique")
    black_box_section = text.split(black_box_marker, 1)[1]
    end_marker = "\n10. Instantiated Netlists\n"
    if black_box_section.count(end_marker) != 1:
        _fail("utilization black-box section has no unique exact end boundary")
    black_box_section = black_box_section.split(end_marker, 1)[0]
    black_box_lines = [line.strip() for line in black_box_section.splitlines() if line.strip()]
    if black_box_lines != [
        "+----------+------+",
        "| Ref Name | Used |",
        "+----------+------+",
    ]:
        _fail(f"utilization black-box inventory is not empty: {black_box_lines}")


def _validate_report_output_paths(
    reports: dict[str, str], expected_directory: Path
) -> None:
    for name in HEADED_REPORTS:
        if name == "route_status.rpt":
            continue
        command = _single_regex(
            reports[name],
            r"^\| Command\s*:\s*(.+?)\s*$",
            f"{name} command path",
        ).group(1)
        expected_suffix = f" -file {expected_directory / name}"
        if not command.endswith(expected_suffix):
            _fail(
                f"{name} command does not bind the current evidence directory: "
                f"{command}"
            )


def _validate_from_directory_descriptor(
    directory_fd: int,
    expected_directory: Path,
) -> dict[str, str]:
    reports = {
        name: _read_report(directory_fd, name, limit)
        for name, limit in REPORT_LIMITS.items()
    }
    _validate_report_output_paths(reports, expected_directory)
    try:
        for name, text in reports.items():
            if re.search(
                r"^[ \t]*(?:CRITICAL WARNING|ERROR|FATAL):",
                text,
                flags=re.MULTILINE | re.IGNORECASE,
            ):
                _fail(f"{name} contains an error, fatal, or critical warning")
        _validate_vivado_log(reports["vivado.log"])
        _validate_cdc_summary(reports["cdc-summary.rpt"])
        _validate_cdc_details(reports["cdc-details.rpt"])
        _validate_clock_interaction(reports["clock_interaction.rpt"])
        _validate_drc(reports["drc.rpt"])
        _validate_methodology(reports["methodology.rpt"])
        _validate_route(reports["route_status.rpt"])
        metrics = _validate_timing(reports["timing_summary.rpt"])
        _validate_utilization(reports["utilization.rpt"])
    except ValidationError:
        raise
    except (ArithmeticError, OSError, TypeError, UnicodeError, ValueError) as error:
        raise ValidationError(f"malformed OOC report: {error}") from error
    return metrics


def validate_ooc_reports(
    output_directory: Path | None = None,
    *,
    directory_fd: int | None = None,
) -> dict[str, str]:
    """Validate all routed reports and return normalized timing metrics."""

    if (output_directory is None) == (directory_fd is None):
        _fail("exactly one OOC output path or directory descriptor is required")
    opened_fd: int
    if directory_fd is None:
        try:
            opened_fd = os.open(
                output_directory,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
        except (OSError, TypeError, ValueError) as error:
            raise ValidationError(f"cannot open OOC output directory: {error}") from error
    else:
        try:
            opened_fd = os.dup(directory_fd)
        except (OSError, TypeError, ValueError) as error:
            raise ValidationError(f"cannot duplicate OOC directory fd: {error}") from error
    try:
        opened_stat = os.fstat(opened_fd)
        if not stat.S_ISDIR(opened_stat.st_mode):
            _fail("OOC evidence descriptor is not a directory")
        try:
            expected_directory = Path(os.readlink(f"/proc/self/fd/{opened_fd}"))
        except OSError as error:
            raise ValidationError("cannot resolve the OOC evidence descriptor") from error
        if not expected_directory.is_absolute() or str(expected_directory).endswith(
            " (deleted)"
        ):
            _fail("OOC evidence descriptor has no stable absolute pathname")
        return _validate_from_directory_descriptor(opened_fd, expected_directory)
    finally:
        _close_descriptor(opened_fd, "OOC output directory")


def main(argv: list[str]) -> int:
    path_argument = len(argv) == 2
    descriptor_argument = (
        len(argv) == 3 and argv[1] == "--directory-fd" and argv[2].isdigit()
    )
    if not path_argument and not descriptor_argument:
        print(
            "usage: validate_tandem_agc_ooc.py <ooc-output-directory> | "
            "--directory-fd <fd>",
            file=sys.stderr,
        )
        return 2
    try:
        if path_argument:
            metrics = validate_ooc_reports(Path(argv[1]))
        else:
            metrics = validate_ooc_reports(directory_fd=int(argv[2]))
    except ValidationError as error:
        print(f"OOC report validation failed: {error}", file=sys.stderr)
        return 1
    for key, value in metrics.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
