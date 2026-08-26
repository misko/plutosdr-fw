#!/usr/bin/env python3
"""Fail-closed validation for the integrated tandem-AGC routed design."""

from __future__ import annotations

import argparse
import collections
import hashlib
import io
import json
import os
import re
import stat
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, NoReturn

WAIVER_SCHEMA = "plutosdr-fw.integrated-route-waivers.v1"
VERDICT_SCHEMA = "plutosdr-fw.integrated-route-verdict.v1"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
RULE = re.compile(r"[A-Z][A-Z0-9]*-[0-9]+\Z")
CHECK_NAMES = (
    "no_clock",
    "constant_clock",
    "pulse_width_clock",
    "unconstrained_internal_endpoints",
    "no_input_delay",
    "no_output_delay",
    "multiple_clock",
    "generated_clocks",
    "loops",
    "partial_input_delay",
    "partial_output_delay",
    "latch_loops",
)
UTILIZATION_RESOURCES = (
    ("1. Slice Logic", "Slice LUTs"),
    ("1. Slice Logic", "Slice Registers"),
    ("3. Memory", "Block RAM Tile"),
    ("4. DSP", "DSPs"),
    ("5. IO and GT Specific", "Bonded IOB"),
    ("6. Clocking", "BUFGCTRL"),
)
VALIDATED_INPUTS = (
    ("source-manifest", "source_manifest"),
    ("waiver-inventory", "waiver_inventory"),
    ("routed-dcp", "routed_dcp"),
    ("routed-utilization", "utilization_report"),
    ("routed-timing", "timing_report"),
    ("routed-route-status", "route_status_report"),
    ("routed-drc", "drc_report"),
    ("routed-methodology", "methodology_report"),
    ("routed-cdc", "cdc_report"),
    ("routed-bus-skew", "bus_skew_report"),
)
DCP_FILES = {
    "system_top.xdc": "XDC",
    "system_top.hwdef": "HWDEF",
    "system_top_stub.vhdl": "VHDL_STUB",
    "system_top_board.xdc": "XDC_BOARD",
    "system_top.wdf": "WDF",
    "system_top.devns": "PHYSDB_DEVICE_NAME_STORE",
    "system_top.shape": "SHAPE",
    "system_top_late.xdc": "XDC_LATE",
    "system_top.xn": "XN",
    "system_top.pdb": "PHYSDB_PLACE",
    "system_top.rda": "RDA",
    "system_top.clkdb": "PHYSDB_CLOCK_DATA",
    "system_top_stub.v": "VERILOG_STUB",
    "system_top.rdb": "PHYSDB_ROUTE",
    "system_top.edf": "EDIF",
    "system_top.dfxdb": "PHYSDB_DFX_DATA",
    "system_top_early.xdc": "XDC_EARLY",
    "system_top_iPhysOpt.replay": "REPLAY",
    "system_top_rda.json": "JSON_RDA",
    "system_top.nnlns": "PHYSDB_NEW_NETLIST_NAME_STORE",
    "system_top.sta": "STA",
    "system_top.xbdc": "XBDC",
    "system_top.incr": "INCR",
}


class ValidationError(RuntimeError):
    """Release evidence is malformed or does not satisfy the policy."""


def fail(message: str) -> NoReturn:
    raise ValidationError(message)


def exact_keys(value: dict[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        fail(f"{name} keys are not exact")


def mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{name} must be an object")
    return value


def array(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        fail(f"{name} must be an array")
    return value


def strict_json(path: Path, *, limit: int = 1_000_000) -> dict[str, Any]:
    payload = safe_bytes(path, limit=limit, name="JSON input")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                fail(f"JSON input contains duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"), object_pairs_hook=pairs
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"invalid strict JSON in {path}") from error
    return mapping(value, "JSON root")


def safe_bytes(path: Path, *, limit: int, name: str) -> bytes:
    try:
        info = path.lstat()
    except OSError as error:
        raise ValidationError(f"cannot stat {name}: {path}") from error
    if not stat.S_ISREG(info.st_mode) or path.is_symlink():
        fail(f"{name} is not a regular non-symlink file: {path}")
    if info.st_uid != os.getuid():
        fail(f"{name} is not owned by the current user: {path}")
    if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        fail(f"{name} is group/world writable: {path}")
    if info.st_size <= 0 or info.st_size > limit:
        fail(f"{name} has an invalid size: {path}")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise ValidationError(f"cannot read {name}: {path}") from error
    after = path.lstat()
    identity = lambda value: (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )
    if len(payload) != info.st_size or identity(after) != identity(info):
        fail(f"{name} changed while it was read: {path}")
    return payload


def safe_text(path: Path, *, limit: int, name: str) -> tuple[str, bytes]:
    payload = safe_bytes(path, limit=limit, name=name)
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValidationError(f"{name} is not strict UTF-8") from error
    if "\x00" in text or "\r" in text:
        fail(f"{name} contains forbidden NUL/CR bytes")
    return text, payload


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        fail(f"{name} must be a nonempty trimmed string")
    return value


def positive_or_zero(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        fail(f"{name} must be a nonnegative integer")
    return value


def parse_rule_inventory(value: Any, name: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(array(value, name)):
        entry = mapping(raw, f"{name}[{index}]")
        exact_keys(
            entry, {"rule", "severity", "count", "rationale"}, f"{name}[{index}]"
        )
        rule = nonempty(entry["rule"], f"{name}[{index}].rule")
        if not RULE.fullmatch(rule) or rule in seen:
            fail(f"{name} has an invalid or duplicate rule {rule!r}")
        seen.add(rule)
        severity = nonempty(entry["severity"], f"{name}[{index}].severity")
        if severity not in {"Critical", "Warning", "Advisory", "Info"}:
            fail(f"{name} has an unsupported severity")
        count = positive_or_zero(entry["count"], f"{name}[{index}].count")
        if count == 0:
            fail(f"{name} must not carry zero-count waivers")
        rationale = nonempty(entry["rationale"], f"{name}[{index}].rationale")
        if len(rationale) < 20:
            fail(f"{name} rationale is not reviewable")
        result.append({"rule": rule, "severity": severity, "count": count})
    if not result:
        fail(f"{name} must not be empty")
    return result


def parse_policy(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = safe_bytes(path, limit=1_000_000, name="waiver inventory")
    policy = strict_json(path)
    exact_keys(
        policy,
        {
            "schema",
            "schema_version",
            "review",
            "tool",
            "design",
            "utilization",
            "check_timing",
            "drc",
            "methodology",
            "cdc",
            "bus_skew",
        },
        "waiver inventory",
    )
    if policy["schema"] != WAIVER_SCHEMA or policy["schema_version"] != 1:
        fail("unsupported waiver inventory schema")

    review = mapping(policy["review"], "review")
    exact_keys(review, {"owner", "applies_to", "rationale"}, "review")
    for key in review:
        if len(nonempty(review[key], f"review.{key}")) < (
            20 if key == "rationale" else 3
        ):
            fail(f"review.{key} is not reviewable")

    tool = mapping(policy["tool"], "tool")
    exact_keys(tool, {"name", "version", "build"}, "tool")
    if tool != {"name": "Vivado", "version": "2022.2", "build": "3671981"}:
        fail("waiver inventory is not pinned to qualified Vivado 2022.2 build 3671981")

    design = mapping(policy["design"], "design")
    exact_keys(design, {"name", "devices"}, "design")
    if design["name"] != "system_top":
        fail("waiver inventory design is not system_top")
    devices = array(design["devices"], "design.devices")
    if devices != ["7z010-clg400", "xc7z010clg400-1"]:
        fail("waiver inventory device aliases are not exact")

    utilization: list[dict[str, Any]] = []
    for index, raw in enumerate(array(policy["utilization"], "utilization")):
        entry = mapping(raw, f"utilization[{index}]")
        exact_keys(
            entry,
            {
                "section",
                "resource",
                "available",
                "max_used",
                "max_utilization_percent",
                "rationale",
            },
            f"utilization[{index}]",
        )
        section = nonempty(entry["section"], f"utilization[{index}].section")
        resource = nonempty(entry["resource"], f"utilization[{index}].resource")
        available = positive_or_zero(
            entry["available"], f"utilization[{index}].available"
        )
        max_used = positive_or_zero(entry["max_used"], f"utilization[{index}].max_used")
        maximum = entry["max_utilization_percent"]
        if type(maximum) not in {int, float} or not 0 < float(maximum) <= 100:
            fail("utilization maximum percentage must be in (0, 100]")
        if available <= 0 or max_used > available:
            fail("utilization available/max_used values are inconsistent")
        rationale = nonempty(entry["rationale"], f"utilization[{index}].rationale")
        if len(rationale) < 20:
            fail("utilization rationale is not reviewable")
        utilization.append(
            {
                "section": section,
                "resource": resource,
                "available": available,
                "max_used": max_used,
                "max_utilization_percent": float(maximum),
            }
        )
    if [(entry["section"], entry["resource"]) for entry in utilization] != list(
        UTILIZATION_RESOURCES
    ):
        fail("utilization inventory is not complete and ordered")

    checks: list[dict[str, Any]] = []
    for index, raw in enumerate(array(policy["check_timing"], "check_timing")):
        entry = mapping(raw, f"check_timing[{index}]")
        exact_keys(entry, {"check", "count", "rationale"}, f"check_timing[{index}]")
        check = nonempty(entry["check"], f"check_timing[{index}].check")
        count = positive_or_zero(entry["count"], f"check_timing[{index}].count")
        if len(nonempty(entry["rationale"], f"check_timing[{index}].rationale")) < 20:
            fail("check_timing rationale is not reviewable")
        checks.append({"check": check, "count": count})
    if [entry["check"] for entry in checks] != list(CHECK_NAMES):
        fail("check_timing inventory is not complete and ordered")

    drc = parse_rule_inventory(policy["drc"], "drc")
    methodology = parse_rule_inventory(policy["methodology"], "methodology")
    cdc = mapping(policy["cdc"], "cdc")
    exact_keys(cdc, {"summary", "critical_paths"}, "cdc")
    cdc_summary = parse_rule_inventory(cdc["summary"], "cdc.summary")
    critical_paths: list[dict[str, str]] = []
    for index, raw in enumerate(array(cdc["critical_paths"], "cdc.critical_paths")):
        entry = mapping(raw, f"cdc.critical_paths[{index}]")
        exact_keys(
            entry,
            {"rule", "source", "destination", "rationale"},
            f"cdc.critical_paths[{index}]",
        )
        parsed = {
            key: nonempty(entry[key], f"cdc.critical_paths[{index}].{key}")
            for key in ("rule", "source", "destination", "rationale")
        }
        if len(parsed["rationale"]) < 20:
            fail("critical CDC rationale is not reviewable")
        critical_paths.append(parsed)
    critical_rules = sorted(
        entry["rule"] for entry in cdc_summary if entry["severity"] == "Critical"
    )
    if sorted(entry["rule"] for entry in critical_paths) != critical_rules:
        fail("each critical CDC rule must have exactly one named reviewed path")

    bus = mapping(policy["bus_skew"], "bus_skew")
    exact_keys(bus, {"requirement_ns", "endpoints", "constraints"}, "bus_skew")
    if (
        type(bus["requirement_ns"]) not in {int, float}
        or float(bus["requirement_ns"]) <= 0
    ):
        fail("bus-skew requirement must be positive")
    endpoints = positive_or_zero(bus["endpoints"], "bus_skew.endpoints")
    if endpoints <= 1:
        fail("bus-skew endpoints must exceed one")
    constraints = [
        nonempty(item, "bus_skew constraint")
        for item in array(bus["constraints"], "bus_skew.constraints")
    ]
    if (
        len(constraints) != 4
        or constraints != sorted(constraints)
        or len(set(constraints)) != 4
    ):
        fail("bus-skew constraints must be four sorted unique scopes")

    normalized = {
        "tool": tool,
        "design": design,
        "utilization": utilization,
        "check_timing": checks,
        "drc": drc,
        "methodology": methodology,
        "cdc_summary": cdc_summary,
        "critical_paths": critical_paths,
        "bus_skew": {
            "requirement_ns": float(bus["requirement_ns"]),
            "endpoints": endpoints,
            "constraints": constraints,
        },
    }
    return normalized, payload


def validate_metadata(
    text: str, policy: dict[str, Any], name: str, *, require_routed: bool
) -> None:
    version_matches = re.findall(
        r"^\| Tool Version : Vivado v\.([0-9.]+) \(lin64\) Build ([0-9]+) ",
        text,
        re.MULTILINE,
    )
    if version_matches != [(policy["tool"]["version"], policy["tool"]["build"])]:
        fail(f"{name} tool identity is not exact")
    design_matches = re.findall(r"^\| Design       : (\S+)\s*$", text, re.MULTILINE)
    if design_matches != [policy["design"]["name"]]:
        fail(f"{name} design identity is not exact")
    device_matches = re.findall(r"^\| Device       : (\S+)\s*$", text, re.MULTILINE)
    if len(device_matches) != 1 or device_matches[0] not in policy["design"]["devices"]:
        fail(f"{name} device identity is not qualified")
    state_matches = re.findall(r"^\| Design State : (.+?)\s*$", text, re.MULTILINE)
    if require_routed and state_matches != ["Fully Routed"]:
        fail(f"{name} does not uniquely attest Fully Routed state")
    if not require_routed and state_matches:
        fail(f"{name} contains an unexpected design-state field")


def validate_route(text: str) -> dict[str, int]:
    patterns = {
        "logical_nets": r"^\s*# of logical nets\.+\s*:\s*([0-9]+)\s*:$",
        "not_needing_routing": r"^\s*# of nets not needing routing\.+\s*:\s*([0-9]+)\s*:$",
        "routable_nets": r"^\s*# of routable nets\.+\s*:\s*([0-9]+)\s*:$",
        "fully_routed_nets": r"^\s*# of fully routed nets\.+\s*:\s*([0-9]+)\s*:$",
        "routing_errors": r"^\s*# of nets with routing errors\.+\s*:\s*([0-9]+)\s*:$",
    }
    values: dict[str, int] = {}
    if text.count("Design Route Status") != 1:
        fail("route-status report heading is not unique")
    for key, pattern in patterns.items():
        matches = re.findall(pattern, text, re.MULTILINE)
        if len(matches) != 1:
            fail(f"route-status field {key} is not unique")
        values[key] = int(matches[0])
    if values["logical_nets"] <= 0 or values["routable_nets"] <= 0:
        fail("route-status inventory is empty")
    if (
        values["not_needing_routing"] + values["routable_nets"]
        != values["logical_nets"]
    ):
        fail("route-status net accounting is inconsistent")
    if (
        values["fully_routed_nets"] != values["routable_nets"]
        or values["routing_errors"] != 0
    ):
        fail("design is not completely routed")
    return values


def validate_utilization(
    text: str, policy: dict[str, Any]
) -> dict[str, dict[str, float | int]]:
    validate_metadata(text, policy, "utilization report", require_routed=True)
    result: dict[str, dict[str, float | int]] = {}
    for entry in policy["utilization"]:
        section_marker = f"{entry['section']}\n{'-' * len(entry['section'])}\n"
        if text.count(section_marker) != 1:
            fail(f"utilization section {entry['section']!r} is not unique")
        tail = text.split(section_marker, 1)[1]
        next_section = re.search(r"(?m)^\d+(?:\.\d+)?\. .+\n-+\n", tail)
        section = tail[: next_section.start()] if next_section else tail
        row_pattern = re.compile(
            rf"^\|\s*{re.escape(entry['resource'])}\s*\|\s*([0-9]+)\s*\|"
            r"\s*([0-9]+)\s*\|\s*([0-9]+)\s*\|\s*([0-9]+)\s*\|"
            r"\s*([0-9]+(?:\.[0-9]+)?)\s*\|$",
            re.MULTILINE,
        )
        matches = row_pattern.findall(section)
        if len(matches) != 1:
            fail(f"utilization row {entry['resource']!r} is not unique")
        used_text, _fixed, _prohibited, available_text, percent_text = matches[0]
        used = int(used_text)
        available = int(available_text)
        percent = float(percent_text)
        if available != entry["available"]:
            fail(f"utilization capacity changed for {entry['resource']}")
        expected_percent = f"{100.0 * used / available:.2f}"
        if percent_text != expected_percent:
            fail(f"utilization percentage is inconsistent for {entry['resource']}")
        if used > entry["max_used"] or percent > entry["max_utilization_percent"]:
            fail(f"utilization guardrail exceeded for {entry['resource']}")
        result[entry["resource"]] = {
            "used": used,
            "available": available,
            "utilization_percent": percent,
        }
    return result


def validate_dcp(payload: bytes) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except (OSError, zipfile.BadZipFile) as error:
        raise ValidationError("routed DCP is not a valid ZIP checkpoint") from error
    with archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        expected_names = {"dcp.xml", *DCP_FILES}
        if len(names) != len(set(names)) or set(names) != expected_names:
            fail("routed DCP member inventory is not exact and unique")
        expanded = 0
        members: dict[str, bytes] = {}
        for entry in entries:
            mode = entry.external_attr >> 16
            if (
                entry.filename.startswith(("/", "\\"))
                or "/" in entry.filename
                or "\\" in entry.filename
                or entry.filename in {".", ".."}
                or entry.flag_bits & 0x1
                or entry.compress_type != zipfile.ZIP_DEFLATED
                or not stat.S_ISREG(mode)
                or entry.file_size <= 0
                or entry.file_size > 64 * 1024 * 1024
            ):
                fail(f"routed DCP has an unsafe member: {entry.filename}")
            expanded += entry.file_size
            if expanded > 128 * 1024 * 1024:
                fail("routed DCP expanded size exceeds the release limit")
            try:
                member = archive.read(entry)
            except (OSError, RuntimeError, zipfile.BadZipFile) as error:
                raise ValidationError(
                    f"cannot CRC-verify routed DCP member {entry.filename}"
                ) from error
            if len(member) != entry.file_size:
                fail(f"routed DCP member size changed: {entry.filename}")
            members[entry.filename] = member

    xml_payload = members["dcp.xml"]
    if b"<!DOCTYPE" in xml_payload or b"<!ENTITY" in xml_payload:
        fail("routed DCP XML contains a forbidden declaration")
    try:
        root = ET.fromstring(xml_payload)
    except ET.ParseError as error:
        raise ValidationError("routed DCP XML is malformed") from error
    if root.tag != "Checkpoint" or root.attrib != {"Version": "19", "Minor": "0"}:
        fail("routed DCP checkpoint schema is not exact")
    identities = {
        "BUILD_NUMBER": "3671981",
        "FULL_BUILD": "SW Build 3671981 on Fri Oct 14 04:59:54 MDT 2022",
        "PRODUCT": "Vivado v2022.2 (64-bit)",
        "Part": "xc7z010clg400-1",
        "Top": "system_top",
        "DisableAutoIOBuffers": "0",
        "OutOfContext": "0",
        "HDPlatform": "0",
    }
    children: dict[str, list[ET.Element]] = {}
    for child in root:
        children.setdefault(child.tag, []).append(child)
    if set(children) != {*identities, "File"}:
        fail("routed DCP XML contains unknown or missing elements")
    for tag, expected in identities.items():
        elements = children[tag]
        if len(elements) != 1 or elements[0].attrib != {"Name": expected}:
            fail(f"routed DCP XML identity {tag} is not exact")
    file_inventory: collections.Counter[tuple[str, str]] = collections.Counter()
    for element in children["File"]:
        if set(element.attrib) != {"Type", "Name", "ModTime"}:
            fail("routed DCP XML File attributes are not exact")
        if not element.attrib["ModTime"].isdigit():
            fail("routed DCP XML File ModTime is malformed")
        file_inventory[(element.attrib["Name"], element.attrib["Type"])] += 1
    expected_inventory: collections.Counter[tuple[str, str]] = collections.Counter(
        DCP_FILES.items()
    )
    # Vivado 2022.2 records HWDEF twice in dcp.xml while storing one member.
    expected_inventory[("system_top.hwdef", "HWDEF")] = 2
    if file_inventory != expected_inventory:
        fail("routed DCP XML file/type inventory is not exact")


def validate_timing(text: str, policy: dict[str, Any]) -> dict[str, float | int]:
    validate_metadata(text, policy, "timing report", require_routed=False)
    if text.count("All user specified timing constraints are met.") != 1:
        fail("timing constraints-met statement is not unique")
    for entry in policy["check_timing"]:
        matches = re.findall(
            rf"^\d+\. checking {re.escape(entry['check'])} \(([0-9]+)\)$",
            text,
            re.MULTILINE,
        )
        if matches != [str(entry["count"]), str(entry["count"])]:
            fail(f"check_timing count changed for {entry['check']}")
    headings = [
        match.start()
        for match in re.finditer(r"^\| Design Timing Summary$", text, re.MULTILINE)
    ]
    if len(headings) != 1:
        fail("Design Timing Summary is not unique")
    section = text[headings[0] :]
    summary = re.search(
        r"^\s*WNS\(ns\).*\n\s*-+.*\n\s*"
        r"(-?[0-9]+(?:\.[0-9]+)?)\s+(-?[0-9]+(?:\.[0-9]+)?)\s+([0-9]+)\s+[0-9]+\s+"
        r"(-?[0-9]+(?:\.[0-9]+)?)\s+(-?[0-9]+(?:\.[0-9]+)?)\s+([0-9]+)\s+[0-9]+\s+"
        r"(-?[0-9]+(?:\.[0-9]+)?)\s+(-?[0-9]+(?:\.[0-9]+)?)\s+([0-9]+)\s+[0-9]+\s*$",
        section,
        re.MULTILINE,
    )
    if summary is None:
        fail("cannot parse the authoritative design timing summary")
    wns, tns, setup_failing, whs, ths, hold_failing, wpws, tpws, pulse_failing = (
        summary.groups()
    )
    metrics: dict[str, float | int] = {
        "wns_ns": float(wns),
        "tns_ns": float(tns),
        "setup_failing_endpoints": int(setup_failing),
        "whs_ns": float(whs),
        "ths_ns": float(ths),
        "hold_failing_endpoints": int(hold_failing),
        "wpws_ns": float(wpws),
        "tpws_ns": float(tpws),
        "pulse_failing_endpoints": int(pulse_failing),
    }
    if any(metrics[key] < 0 for key in ("wns_ns", "whs_ns", "wpws_ns")):
        fail("routed timing has negative slack")
    if any(metrics[key] != 0 for key in ("tns_ns", "ths_ns", "tpws_ns")):
        fail("routed timing has nonzero total violation")
    if any(
        metrics[key] != 0
        for key in (
            "setup_failing_endpoints",
            "hold_failing_endpoints",
            "pulse_failing_endpoints",
        )
    ):
        fail("routed timing has failing endpoints")
    return metrics


def summary_body(text: str, name: str) -> str:
    marker = "1. REPORT SUMMARY\n-----------------\n"
    if text.count(marker) != 1:
        fail(f"{name} authoritative summary is not unique")
    tail = text.split(marker, 1)[1]
    end = "\n2. REPORT DETAILS\n-----------------\n"
    if tail.count(end) != 1:
        fail(f"{name} authoritative details boundary is not unique")
    return tail.split(end, 1)[0]


def validate_rule_report(
    text: str, policy: dict[str, Any], name: str, expected: list[dict[str, Any]]
) -> None:
    validate_metadata(text, policy, name, require_routed=True)
    body = summary_body(text, name)
    total_matches = re.findall(
        r"^\s*Violations found:\s*([0-9]+)\s*$", body, re.MULTILINE
    )
    if total_matches != [str(sum(entry["count"] for entry in expected))]:
        fail(f"{name} total violation count changed")
    rows = re.findall(
        r"^\|\s*([A-Z][A-Z0-9]*-[0-9]+)\s*\|\s*(Critical|Warning|Advisory|Info)\s*\|.*\|\s*([0-9]+)\s*\|$",
        body,
        re.MULTILINE,
    )
    actual = [
        {"rule": rule, "severity": severity, "count": int(count)}
        for rule, severity, count in rows
    ]
    if actual != expected:
        fail(f"{name} rule/severity/count inventory changed")
    for entry in expected:
        details = re.findall(
            rf"^{re.escape(entry['rule'])}#[0-9]+ {re.escape(entry['severity'])}$",
            text,
            re.MULTILINE,
        )
        if len(details) != entry["count"]:
            fail(f"{name} detail count changed for {entry['rule']}")
    detail_rules = re.findall(
        r"^([A-Z][A-Z0-9]*-[0-9]+)#[0-9]+ (?:Critical|Warning|Advisory|Info)$",
        text,
        re.MULTILINE,
    )
    if set(detail_rules) != {entry["rule"] for entry in expected}:
        fail(f"{name} contains unreviewed detail rules")


def validate_cdc(text: str, policy: dict[str, Any]) -> None:
    validate_metadata(text, policy, "CDC report", require_routed=False)
    if text.count("CDC Report\n") != 1:
        fail("CDC report heading is not unique")
    rows = re.findall(
        r"^(CDC-[0-9]+)\s+(Critical|Warning|Info)\s+([0-9]+)\s+.+$",
        text,
        re.MULTILINE,
    )
    actual = [
        {"rule": rule, "severity": severity, "count": int(count)}
        for rule, severity, count in rows
    ]
    if actual != policy["cdc_summary"]:
        fail("CDC summary rule/severity/count inventory changed")
    detail_pattern = re.compile(
        r"^\s*[0-9]+\s+(CDC-[0-9]+)\s+(Critical|Warning|Info)\s+.+?\s+"
        r"(\S+)\s+(\S+)\s*$",
        re.MULTILINE,
    )
    details = detail_pattern.findall(text)
    counts: dict[str, int] = {}
    for rule, severity, _source, _destination in details:
        counts[rule] = counts.get(rule, 0) + 1
        expected = next(
            (item for item in policy["cdc_summary"] if item["rule"] == rule), None
        )
        if expected is None or expected["severity"] != severity:
            fail("CDC details contain an unreviewed rule or severity")
    if counts != {entry["rule"]: entry["count"] for entry in policy["cdc_summary"]}:
        fail("CDC detail inventory does not reproduce the summary")
    critical_actual = sorted(
        (rule, source, destination)
        for rule, severity, source, destination in details
        if severity == "Critical"
    )
    critical_expected = sorted(
        (entry["rule"], entry["source"], entry["destination"])
        for entry in policy["critical_paths"]
    )
    if critical_actual != critical_expected:
        fail("critical CDC paths are not the exact reviewed crossings")


def validate_bus_skew(text: str, policy: dict[str, Any]) -> dict[str, float | int]:
    validate_metadata(text, policy, "bus-skew report", require_routed=False)
    if text.count("Bus Skew Report\n") != 1 or "Slack (VIOLATED)" in text:
        fail("bus-skew report is malformed or contains a violation")
    blocks = re.split(r"(?m)^Id: ([0-9]+)\n", text)
    if len(blocks) != 1 + 2 * len(policy["bus_skew"]["constraints"]):
        fail("bus-skew detail inventory is not exact")
    found: list[str] = []
    minimum_slack: float | None = None
    for offset in range(1, len(blocks), 2):
        identifier = int(blocks[offset])
        block = blocks[offset + 1]
        if identifier != (offset + 1) // 2:
            fail("bus-skew constraint IDs are not contiguous")
        command_matches = re.findall(r"^set_bus_skew .+$", block, re.MULTILINE)
        requirement_matches = re.findall(
            r"^Requirement: ([0-9]+(?:\.[0-9]+)?)ns$", block, re.MULTILINE
        )
        endpoint_matches = re.findall(r"^Endpoints: ([0-9]+)$", block, re.MULTILINE)
        slack_matches = re.findall(
            r"^Slack \(MET\) :\s+([0-9]+(?:\.[0-9]+)?)ns", block, re.MULTILINE
        )
        if not (
            len(command_matches)
            == len(requirement_matches)
            == len(endpoint_matches)
            == len(slack_matches)
            == 1
        ):
            fail("bus-skew constraint block is incomplete or ambiguous")
        if float(requirement_matches[0]) != policy["bus_skew"]["requirement_ns"]:
            fail("bus-skew requirement changed")
        if int(endpoint_matches[0]) != policy["bus_skew"]["endpoints"]:
            fail("bus-skew endpoint width changed")
        command_halves = command_matches[0].split(" -to ")
        if len(command_halves) != 2:
            fail("bus-skew command does not have one from/to boundary")
        matching = [
            scope
            for scope in policy["bus_skew"]["constraints"]
            if scope in command_halves[0] and scope in command_halves[1]
        ]
        if len(matching) != 1:
            fail("bus-skew constraint scope is not uniquely reviewed")
        found.extend(matching)
        slack = float(slack_matches[0])
        minimum_slack = slack if minimum_slack is None else min(minimum_slack, slack)
    if sorted(found) != policy["bus_skew"]["constraints"]:
        fail("bus-skew constraints do not cover the reviewed scope")
    return {"constraints_met": len(found), "minimum_slack_ns": minimum_slack or 0.0}


def write_absent(path: Path, value: dict[str, Any]) -> None:
    if not path.is_absolute():
        fail("verdict output path must be absolute")
    if path.exists() or path.is_symlink():
        fail("verdict output must be absent")
    parent = path.parent
    if not parent.is_dir() or parent.is_symlink():
        fail("verdict output parent must be an existing non-symlink directory")
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        os.unlink(temporary)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--waiver-inventory", required=True, type=Path)
    parser.add_argument("--routed-dcp", required=True, type=Path)
    parser.add_argument("--utilization-report", required=True, type=Path)
    parser.add_argument("--timing-report", required=True, type=Path)
    parser.add_argument("--route-status-report", required=True, type=Path)
    parser.add_argument("--drc-report", required=True, type=Path)
    parser.add_argument("--methodology-report", required=True, type=Path)
    parser.add_argument("--cdc-report", required=True, type=Path)
    parser.add_argument("--bus-skew-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not HEX40.fullmatch(args.source_commit):
        fail("source commit must be a lowercase full Git object ID")
    policy, waiver_payload = parse_policy(args.waiver_inventory)
    manifest_payload = safe_bytes(
        args.source_manifest, limit=1_000_000, name="source manifest"
    )
    dcp_payload = safe_bytes(
        args.routed_dcp, limit=256 * 1024 * 1024, name="routed DCP"
    )
    validate_dcp(dcp_payload)

    utilization, utilization_payload = safe_text(
        args.utilization_report,
        limit=32 * 1024 * 1024,
        name="utilization report",
    )

    timing, timing_payload = safe_text(
        args.timing_report, limit=32 * 1024 * 1024, name="timing report"
    )
    route, route_payload = safe_text(
        args.route_status_report, limit=2 * 1024 * 1024, name="route-status report"
    )
    drc, drc_payload = safe_text(
        args.drc_report, limit=32 * 1024 * 1024, name="DRC report"
    )
    methodology, methodology_payload = safe_text(
        args.methodology_report, limit=32 * 1024 * 1024, name="methodology report"
    )
    cdc, cdc_payload = safe_text(
        args.cdc_report, limit=64 * 1024 * 1024, name="CDC report"
    )
    bus, bus_payload = safe_text(
        args.bus_skew_report, limit=32 * 1024 * 1024, name="bus-skew report"
    )

    validate_metadata(route, policy, "route-status report", require_routed=True)
    route_metrics = validate_route(route)
    utilization_metrics = validate_utilization(utilization, policy)
    timing_metrics = validate_timing(timing, policy)
    validate_rule_report(drc, policy, "DRC report", policy["drc"])
    validate_rule_report(
        methodology, policy, "methodology report", policy["methodology"]
    )
    validate_cdc(cdc, policy)
    bus_metrics = validate_bus_skew(bus, policy)

    payloads = {
        "source_manifest": manifest_payload,
        "waiver_inventory": waiver_payload,
        "routed_dcp": dcp_payload,
        "utilization_report": utilization_payload,
        "timing_report": timing_payload,
        "route_status_report": route_payload,
        "drc_report": drc_payload,
        "methodology_report": methodology_payload,
        "cdc_report": cdc_payload,
        "bus_skew_report": bus_payload,
    }
    output_parent = args.output.absolute().parent
    validated_inputs: list[dict[str, Any]] = []
    for role, attribute in VALIDATED_INPUTS:
        path = getattr(args, attribute).absolute()
        if path.parent != output_parent or path.name in {"", ".", ".."}:
            fail(f"validated input {role} must be a direct sibling of the verdict")
        payload = payloads[attribute]
        validated_inputs.append(
            {
                "role": role,
                "path": path.name,
                "bytes": len(payload),
                "sha256": sha256(payload),
            }
        )

    verdict = {
        "schema": VERDICT_SCHEMA,
        "verdict": "PASS",
        "source_commit": args.source_commit,
        "source_manifest_sha256": sha256(manifest_payload),
        "routed_dcp_sha256": sha256(dcp_payload),
        "waiver_inventory_sha256": sha256(waiver_payload),
        "validated_inputs": validated_inputs,
        "firmware_release_eligible": True,
    }
    write_absent(args.output, verdict)
    print(
        "PASS integrated route: "
        f"nets={route_metrics['fully_routed_nets']} "
        f"WNS={timing_metrics['wns_ns']:.3f}ns "
        f"WHS={timing_metrics['whs_ns']:.3f}ns "
        f"bus_skew_min={bus_metrics['minimum_slack_ns']:.3f}ns "
        f"DSP={utilization_metrics['DSPs']['used']}/"
        f"{utilization_metrics['DSPs']['available']}"
    )
    return verdict


def main(argv: list[str] | None = None) -> int:
    try:
        run(parse_args(sys.argv[1:] if argv is None else argv))
    except ValidationError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
