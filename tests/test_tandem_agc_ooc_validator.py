"""Mutation oracles for the strict routed tandem-AGC OOC report validator."""

from __future__ import annotations

import importlib.util
import random
import warnings
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "scripts" / "validate_tandem_agc_ooc.py"


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "tandem_agc_ooc_validator", VALIDATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_validator()
DCP_PAD = random.Random(0).randbytes(600 * 1024)
DCP_FILE_TYPES = {
    "tandem_agc_axi_stub.v": "VERILOG_STUB",
    "tandem_agc_axi_stub.vhdl": "VHDL_STUB",
    "tandem_agc_axi_iPhysOpt.replay": "REPLAY",
    "tandem_agc_axi.xdc": "XDC",
    "tandem_agc_axi_in_context.xdc": "XDC_IN_CONTEXT",
    "tandem_agc_axi.shape": "SHAPE",
    "tandem_agc_axi.xn": "XN",
    "tandem_agc_axi.xbdc": "XBDC",
    "tandem_agc_axi.edf": "EDIF",
    "tandem_agc_axi.sta": "STA",
    "tandem_agc_axi.devns": "PHYSDB_DEVICE_NAME_STORE",
    "tandem_agc_axi.pdb": "PHYSDB_PLACE",
    "tandem_agc_axi.rdb": "PHYSDB_ROUTE",
    "tandem_agc_axi.dfxdb": "PHYSDB_DFX_DATA",
    "tandem_agc_axi.clkdb": "PHYSDB_CLOCK_DATA",
    "tandem_agc_axi.nnlns": "PHYSDB_NEW_NETLIST_NAME_STORE",
    "tandem_agc_axi.incr": "INCR",
    "tandem_agc_axi.rda": "RDA",
    "tandem_agc_axi_rda.json": "JSON_RDA",
    "tandem_agc_axi.wdf": "WDF",
    "tandem_agc_axi.synth": "SYNTH",
    "tandem_agc_axi.mvs": "METHODOLOGY_VIO_SUMMARY",
}
DCP_ARCHIVE_ORDER = (
    "tandem_agc_axi.rdb",
    "tandem_agc_axi.shape",
    "tandem_agc_axi.synth",
    "tandem_agc_axi.sta",
    "tandem_agc_axi.nnlns",
    "tandem_agc_axi_iPhysOpt.replay",
    "tandem_agc_axi.xn",
    "tandem_agc_axi.xbdc",
    "tandem_agc_axi.incr",
    "tandem_agc_axi.clkdb",
    "tandem_agc_axi.pdb",
    "tandem_agc_axi.devns",
    "tandem_agc_axi.xdc",
    "tandem_agc_axi.wdf",
    "tandem_agc_axi_stub.v",
    "tandem_agc_axi.dfxdb",
    "tandem_agc_axi.rda",
    "tandem_agc_axi_stub.vhdl",
    "tandem_agc_axi.mvs",
    "tandem_agc_axi.edf",
    "tandem_agc_axi_rda.json",
    "tandem_agc_axi_in_context.xdc",
)


def _header(command: str, device: str, state: str | None = None) -> str:
    separator = "-" * 100
    speed_file = "-1  PRODUCTION 1.12 2019-11-22" if device == "7z010-clg400" else "-1"
    lines = [
        "Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.",
        separator,
        (
            "| Tool Version : Vivado v.2022.2 (lin64) Build 3671981 "
            "Fri Oct 14 04:59:54 MDT 2022"
        ),
        "| Date         : nondeterministic and deliberately ignored",
        "| Host         : nondeterministic and deliberately ignored",
        f"| Command      : {command}",
        "| Design       : tandem_agc_axi",
        f"| Device       : {device}",
        f"| Speed File   : {speed_file}",
    ]
    if state is not None:
        lines.append(f"| Design State : {state}")
    lines.extend([separator, ""])
    return "\n".join(lines)


def _cdc_summary() -> str:
    return (
        _header(
            "report_cdc -no_waiver -file /evidence/cdc-summary.rpt",
            "7z010-clg400",
        )
        + """CDC Report

Severity  Source Clock  Destination Clock  CDC Type                 Exceptions           Endpoints  Safe  Unsafe  Unknown  No ASYNC_REG
--------  ------------  -----------------  -----------------------  -------------------  ---------  ----  ------  -------  ------------
Warning   s_axi_aclk    l_clk              No Common Primary Clock  Asynch Clock Groups        113   113       0        0             0
Warning   l_clk         s_axi_aclk         No Common Primary Clock  Asynch Clock Groups         18    18       0        0             0
"""
    )


def _cdc_detail_row(
    ordinal: int,
    rule: str,
    severity: str,
    description: str,
    depth: int,
    width: int | None,
) -> str:
    if width is None:
        source = f"source_{ordinal}/C"
        destination = f"destination_{ordinal}/D"
    else:
        source = f"source_{ordinal}[{width - 1}:0]/C"
        destination = f"destination_{ordinal}[{width - 1}:0]/D"
    return (
        f"{ordinal:3d}  {rule:<6}  {severity:<8}  {description:<46}  "
        f"{depth:5d}  Asynch Clock Groups  {source}  {destination}"
    )


def _cdc_section(source: str, destination: str) -> str:
    if (source, destination) == ("s_axi_aclk", "l_clk"):
        specifications = [
            (
                "CDC-15",
                "Warning",
                "Clock enable controlled CDC structure detected",
                0,
                None,
            )
        ] * 103 + [
            (
                "CDC-6",
                "Warning",
                "Multi-bit synchronized with ASYNC_REG property",
                2,
                7,
            ),
            (
                "CDC-3",
                "Info",
                "1-bit synchronized with ASYNC_REG property",
                3,
                None,
            ),
            (
                "CDC-3",
                "Info",
                "1-bit synchronized with ASYNC_REG property",
                3,
                None,
            ),
            (
                "CDC-3",
                "Info",
                "1-bit synchronized with ASYNC_REG property",
                3,
                None,
            ),
        ]
    else:
        specifications = [
            (
                "CDC-15",
                "Warning",
                "Clock enable controlled CDC structure detected",
                0,
                None,
            )
        ] * 8 + [
            (
                "CDC-6",
                "Warning",
                "Multi-bit synchronized with ASYNC_REG property",
                2,
                6,
            ),
            (
                "CDC-3",
                "Info",
                "1-bit synchronized with ASYNC_REG property",
                2,
                None,
            ),
            (
                "CDC-3",
                "Info",
                "1-bit synchronized with ASYNC_REG property",
                3,
                None,
            ),
            (
                "CDC-3",
                "Info",
                "1-bit synchronized with ASYNC_REG property",
                3,
                None,
            ),
            (
                "CDC-3",
                "Info",
                "1-bit synchronized with ASYNC_REG property",
                3,
                None,
            ),
        ]
    rows = [
        _cdc_detail_row(ordinal, *specification)
        for ordinal, specification in enumerate(specifications, start=1)
    ]
    return "\n".join(
        [
            f"Source Clock: {source}",
            f"Destination Clock: {destination}",
            "CDC Type: No Common Primary Clock",
            "",
            (
                "Row  ID      Severity  Description                                     "
                "Depth  Exception            Source (From)                                "
                "Destination (To)"
            ),
            "---",
            *rows,
            "",
        ]
    )


def _cdc_details() -> str:
    return (
        _header(
            "report_cdc -details -no_waiver -file /evidence/cdc-details.rpt",
            "7z010-clg400",
        )
        + """CDC Report

ID      Severity  Count  Description
------  --------  -----  ----------------------------------------------
CDC-3   Info          7  1-bit synchronized with ASYNC_REG property
CDC-6   Warning       2  Multi-bit synchronized with ASYNC_REG property
CDC-15  Warning     111  Clock enable controlled CDC structure detected

"""
        + _cdc_section("s_axi_aclk", "l_clk")
        + _cdc_section("l_clk", "s_axi_aclk")
    )


def _rule_report(
    *,
    command: str,
    rules: list[tuple[str, str, str, int]],
) -> str:
    total = sum(count for _rule, _severity, _description, count in rules)
    decoration = "+-----------+----------+-------------------------------+------------+"
    summary = [
        f"Violations found: {total}",
        decoration,
        "| Rule      | Severity | Description                   | Violations |",
        decoration,
    ]
    summary.extend(
        f"| {rule:<9} | {severity:<8} | {description:<29} | {count:<10} |"
        for rule, severity, description, count in rules
    )
    summary.append(decoration)
    details: list[str] = []
    for rule, severity, description, count in rules:
        for ordinal in range(1, count + 1):
            details.extend([f"{rule}#{ordinal} {severity}", description])
            if rule == "TIMING-18":
                kind = "input" if ordinal <= 137 else "output"
                details.append(
                    f"An {kind} delay is missing on synthetic_{ordinal} "
                    "relative to clock(s) synthetic_clock"
                )
            elif rule == "SYNTH-4":
                details.append(
                    "The instance u_stat/mem_reg is implemented as block RAM but "
                    "is better mapped onto distributed LUT RAM for the following "
                    "reason: The depth (1 address bits) is shallow. Please use "
                    'attribute (* ram_style = "distributed" *)  to instruct Vivado '
                    "to infer distributed LUT RAM."
                )
            else:
                details.append("Synthetic exact-detail payload")
            details.extend(["Related violations: <none>", ""])
    return (
        _header(command, "xc7z010clg400-1", "Fully Routed")
        + "\n".join([*summary, "", *details])
        + "\n"
    )


def _drc() -> str:
    return _rule_report(
        command=("report_drc -ruledeck default -no_waivers -file /evidence/drc.rpt"),
        rules=[
            ("REQP-1839", "Warning", "RAMB36 async control check", 4),
            ("ZPS7-1", "Warning", "PS7 block required", 1),
        ],
    )


def _methodology() -> str:
    return _rule_report(
        command=("report_methodology -no_waivers -file /evidence/methodology.rpt"),
        rules=[
            ("LUTAR-1", "Warning", "LUT drives async reset alert", 1),
            (
                "SYNTH-4",
                "Warning",
                "Shallow depth for a dedicated block RAM",
                1,
            ),
            ("TIMING-18", "Warning", "Missing input or output delay", 182),
        ],
    )


def _timing() -> str:
    checks = [
        ("no_clock", 0),
        ("constant_clock", 0),
        ("pulse_width_clock", 0),
        ("unconstrained_internal_endpoints", 0),
        ("no_input_delay", 137),
        ("no_output_delay", 45),
        ("multiple_clock", 0),
        ("generated_clocks", 0),
        ("loops", 0),
        ("partial_input_delay", 0),
        ("partial_output_delay", 0),
        ("latch_loops", 0),
    ]
    check_lines = [
        f"{ordinal}. checking {name} ({count})"
        for ordinal, (name, count) in enumerate(checks, start=1)
    ]
    detailed_slacks = "\n".join(
        [("Slack (MET) :             3.765ns  (required time - arrival time)")] * 100
        + [("Slack (MET) :             0.079ns  (arrival time - required time)")] * 100
    )
    return (
        _header(
            "report_timing_summary -delay_type min_max -max_paths 50 "
            "-report_unconstrained -check_timing_verbose "
            "-file /evidence/timing_summary.rpt",
            "7z010-clg400",
        )
        + """Timing Summary Report

| Report Methodology
Rule       Severity  Description                    Violations
---------  --------  -----------------------------  ----------
LUTAR-1    Warning   LUT drives async reset alert   1
SYNTH-4    Warning   Shallow depth for a dedicated block RAM  1
TIMING-18  Warning   Missing input or output delay  182

Note: This report is based on the most recent report_methodology run and may not be up-to-date. Run report_methodology on the current design for the latest report.

check_timing report
"""
        + "\n".join(check_lines)
        + "\n"
        + "\n".join(check_lines)
        + """

| Design Timing Summary
    WNS(ns)      TNS(ns)  TNS Failing Endpoints  TNS Total Endpoints      WHS(ns)      THS(ns)  THS Failing Endpoints  THS Total Endpoints     WPWS(ns)     TPWS(ns)  TPWS Failing Endpoints  TPWS Total Endpoints
    -------      -------  ---------------------  -------------------      -------      -------  ---------------------  -------------------     --------     --------  ----------------------  --------------------
      3.765        0.000                      0                 1806        0.079        0.000                      0                 1806        4.500        0.000                       0                   698

All user specified timing constraints are met.

| Clock Summary
Clock       Waveform(ns)       Period(ns)      Frequency(MHz)
-----       ------------       ----------      --------------
l_clk       {0.000 8.138}      16.276          61.440
s_axi_aclk  {0.000 5.000}      10.000          100.000

| Intra Clock Table
Clock             WNS(ns)      TNS(ns)  TNS Failing Endpoints  TNS Total Endpoints      WHS(ns)      THS(ns)  THS Failing Endpoints  THS Total Endpoints     WPWS(ns)     TPWS(ns)  TPWS Failing Endpoints  TPWS Total Endpoints
-----             -------      -------  ---------------------  -------------------      -------      -------  ---------------------  -------------------     --------     --------  ----------------------  --------------------
l_clk               9.129        0.000                      0                 1001        0.079        0.000                      0                 1001        7.638        0.000                       0                   391
s_axi_aclk          3.765        0.000                      0                  805        0.100        0.000                      0                  805        4.500        0.000                       0                   307

| Inter Clock Table
"""
        + detailed_slacks
        + "\n"
    )


def _clock_interaction_row(
    from_clock: str,
    to_clock: str,
    *,
    edges: str,
    wns: str,
    tns: str,
    failing: int,
    total: int,
    requirement: str,
    classification: str,
    constraints: str,
) -> str:
    return (
        f"{from_clock:<12}  {to_clock:<12}  {edges:<11}  {wns:>7}  {tns:>7}  "
        f"{failing:>11}  {total:>11}  {requirement:>15}  "
        f"{classification:<19}  {constraints:<19}  "
    )


def _clock_interaction(
    *,
    l_clk_wns: str = "9.13",
    l_clk_endpoints: int = 1001,
    l_to_axi_endpoints: int = 18,
    axi_to_l_endpoints: int = 113,
    axi_wns: str = "3.76",
    axi_endpoints: int = 805,
) -> str:
    rows = (
        _clock_interaction_row(
            "l_clk",
            "l_clk",
            edges="rise - rise",
            wns=l_clk_wns,
            tns="0.00",
            failing=0,
            total=l_clk_endpoints,
            requirement="16.28",
            classification="Clean",
            constraints="Timed",
        ),
        _clock_interaction_row(
            "l_clk",
            "s_axi_aclk",
            edges="",
            wns="",
            tns="",
            failing=0,
            total=l_to_axi_endpoints,
            requirement="",
            classification="Ignored",
            constraints="Asynchronous Groups",
        ),
        _clock_interaction_row(
            "s_axi_aclk",
            "l_clk",
            edges="",
            wns="",
            tns="",
            failing=0,
            total=axi_to_l_endpoints,
            requirement="",
            classification="Ignored",
            constraints="Asynchronous Groups",
        ),
        _clock_interaction_row(
            "s_axi_aclk",
            "s_axi_aclk",
            edges="rise - rise",
            wns=axi_wns,
            tns="0.00",
            failing=0,
            total=axi_endpoints,
            requirement="10.00",
            classification="Clean",
            constraints="Timed",
        ),
    )
    return (
        _header(
            "report_clock_interaction -file /evidence/clock_interaction.rpt",
            "7z010-clg400",
        )
        + """
Clock Interaction Report

Clock Interaction Table
-----------------------

                            WNS                            TNS Failing  TNS Total    WNS Path         Clock-Pair           Inter-Clock
From Clock    To Clock      Clock Edges  WNS(ns)  TNS(ns)    Endpoints    Endpoints  Requirement(ns)  Classification       Constraints
------------  ------------  -----------  -------  -------  -----------  -----------  ---------------  -------------------  -------------------
"""
        + "\n".join(rows)
        + "\n"
    )


def _route() -> str:
    return """Design Route Status
                                               :      # nets :
   ------------------------------------------- : ----------- :
   # of logical nets.......................... :        1657 :
       # of nets not needing routing.......... :         530 :
           # of internally routed nets........ :         349 :
           # of implicitly routed ports....... :         181 :
       # of routable nets..................... :        1127 :
           # of fully routed nets............. :        1127 :
       # of nets with routing errors.......... :           0 :
   ------------------------------------------- : ----------- :
"""


def _vivado_log() -> str:
    return """****** Vivado v2022.2 (64-bit)
  **** SW Build 3671981 on Fri Oct 14 04:59:54 MDT 2022
  **** IP Build 3669848 on Fri Oct 14 08:30:02 MDT 2022
35 Infos, 21 Warnings, 0 Critical Warnings and 0 Errors encountered.
103 Infos, 125 Warnings, 0 Critical Warnings and 0 Errors encountered.
=== TANDEM AXI ROUTE COMPLETE ===
"""


def _utilization() -> str:
    return (
        _header(
            "report_utilization -file /evidence/utilization.rpt",
            "xc7z010clg400-1",
            "Routed",
        )
        + """Utilization Design Information

Table of Contents
-----------------
1. Slice Logic
1.1 Summary of Registers by Type
2. Slice Logic Distribution
3. Memory
4. DSP
5. IO and GT Specific
6. Clocking
7. Specific Feature
8. Primitives
9. Black Boxes
10. Instantiated Netlists

1. Slice Logic
--------------

| Slice LUTs              |  509 |     0 |          0 |     17600 |  2.89 |
| Slice Registers         |  587 |     0 |          0 |     35200 |  1.67 |

1.1 Summary of Registers by Type
--------------------------------

2. Slice Logic Distribution
---------------------------

| Slice                    |  204 |     0 |          0 |      4400 |  4.64 |

3. Memory
---------

| Block RAM Tile          |    3 |     0 |          0 |        60 |  5.00 |

4. DSP
------

| DSPs                    |    2 |     0 |          0 |        80 |  2.50 |

5. IO and GT Specific
---------------------

9. Black Boxes
--------------

+----------+------+
| Ref Name | Used |
+----------+------+


10. Instantiated Netlists
-------------------------
"""
    )


def _write_dcp(path: Path) -> None:
    metadata = [
        '<?xml version="1.0"?>',
        '<Checkpoint Version="19" Minor="0">',
        '  <BUILD_NUMBER Name="3671981"/>',
        '  <FULL_BUILD Name="SW Build 3671981 on Fri Oct 14 04:59:54 MDT 2022"/>',
        '  <PRODUCT Name="Vivado v2022.2 (64-bit)"/>',
        '  <Part Name="xc7z010clg400-1"/>',
        '  <Top Name="tandem_agc_axi"/>',
        '  <DisableAutoIOBuffers Name="1"/>',
        '  <OutOfContext Name="1"/>',
        '  <HDPlatform Name="0"/>',
    ]
    metadata.extend(
        f'  <File Type="{kind}" Name="{name}" ModTime="1787701238"/>'
        for name, kind in DCP_FILE_TYPES.items()
    )
    metadata.append("</Checkpoint>")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("dcp.xml", "\n".join(metadata) + "\n")
        for name in DCP_ARCHIVE_ORDER:
            payload = DCP_PAD if name == "tandem_agc_axi.pdb" else b"x"
            archive.writestr(name, payload)


def _rewrite_dcp(
    path: Path,
    mutation: str,
) -> None:
    with zipfile.ZipFile(path, "r") as archive:
        members = [
            (info.filename, archive.read(info.filename)) for info in archive.infolist()
        ]
    if mutation == "missing-route-db":
        members = [
            (name, payload) for name, payload in members if not name.endswith(".rdb")
        ]
    elif mutation == "duplicate-route-db":
        members.append(next(member for member in members if member[0].endswith(".rdb")))
    elif mutation == "extra-member":
        members.append(("unexpected-member", b"x"))
    elif mutation == "reordered":
        members = [members[0], *reversed(members[1:])]
    elif mutation == "wrong-part":
        members = [
            (
                name,
                payload.replace(b'Part Name="xc7z010clg400-1"', b'Part Name="wrong"'),
            )
            if name == "dcp.xml"
            else (name, payload)
            for name, payload in members
        ]
    elif mutation == "traversal":
        members[-1] = ("../escaped", members[-1][1])
    elif mutation in {"unknown-encoding", "nested-node", "doctype"}:
        rewritten: list[tuple[str, bytes]] = []
        for name, payload in members:
            if name == "dcp.xml":
                if mutation == "unknown-encoding":
                    payload = payload.replace(b'encoding="1.0"', b'encoding="x-nope"')
                    if b'encoding="x-nope"' not in payload:
                        payload = payload.replace(
                            b'<?xml version="1.0"?>',
                            b'<?xml version="1.0" encoding="x-nope"?>',
                        )
                elif mutation == "nested-node":
                    payload = payload.replace(
                        b'<Part Name="xc7z010clg400-1"/>',
                        b'<Part Name="xc7z010clg400-1"><rogue/></Part>',
                    )
                else:
                    payload = payload.replace(
                        b'<?xml version="1.0"?>',
                        b'<?xml version="1.0"?>\n<!DOCTYPE Checkpoint>',
                    )
            rewritten.append((name, payload))
        members = rewritten
    else:
        raise AssertionError(f"unknown DCP mutation: {mutation}")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in members:
                archive.writestr(name, payload)


def _valid_reports(directory: Path) -> None:
    reports = {
        "vivado.log": _vivado_log(),
        "cdc-summary.rpt": _cdc_summary(),
        "cdc-details.rpt": _cdc_details(),
        "clock_interaction.rpt": _clock_interaction(),
        "drc.rpt": _drc(),
        "methodology.rpt": _methodology(),
        "route_status.rpt": _route(),
        "timing_summary.rpt": _timing(),
        "utilization.rpt": _utilization(),
    }
    for name, text in reports.items():
        (directory / name).write_text(
            text.replace("/evidence", str(directory)),
            encoding="utf-8",
        )
    _write_dcp(directory / VALIDATOR.DCP_NAME)


def _replace(path: Path, old: str, new: str, *, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == count
    path.write_text(text.replace(old, new), encoding="utf-8")


def _replace_fixed_field(
    line: str,
    start: int,
    end: int,
    value: str,
    *,
    left_aligned: bool = False,
) -> str:
    width = end - start
    assert len(value) <= width
    replacement = f"{value:<{width}}" if left_aligned else f"{value:>{width}}"
    return line[:start] + replacement + line[end:]


def _validate(directory: Path) -> dict[str, str]:
    return VALIDATOR.validate_ooc_reports(directory)


def test_valid_exact_report_set_passes(tmp_path: Path) -> None:
    _valid_reports(tmp_path)
    metrics = _validate(tmp_path)

    assert metrics == {
        "WNS_ns": "3.765",
        "TNS_ns": "0.000",
        "TNS_failing_endpoints": "0",
        "TNS_total_endpoints": "1806",
        "WHS_ns": "0.079",
        "THS_ns": "0.000",
        "THS_failing_endpoints": "0",
        "THS_total_endpoints": "1806",
        "WPWS_ns": "4.500",
        "TPWS_ns": "0.000",
        "TPWS_failing_endpoints": "0",
        "TPWS_total_endpoints": "698",
    }


def test_valid_rc6_metric_variant_passes_without_rc5_numeric_baselines(
    tmp_path: Path,
) -> None:
    _valid_reports(tmp_path)
    interaction = _clock_interaction(
        l_clk_wns="9.27",
        l_clk_endpoints=791,
        axi_wns="3.68",
        axi_endpoints=805,
    ).replace("/evidence", str(tmp_path))
    (tmp_path / "clock_interaction.rpt").write_text(interaction, encoding="utf-8")

    route = (tmp_path / "route_status.rpt").read_text(encoding="utf-8")
    for old, new in (
        ("1657", "1529"),
        ("530", "439"),
        ("349", "258"),
        ("1127", "1090"),
    ):
        route = route.replace(old, new)
    (tmp_path / "route_status.rpt").write_text(route, encoding="utf-8")

    timing = tmp_path / "timing_summary.rpt"
    replacements = (
        (
            (
                "3.765        0.000                      0                 1806"
                "        0.079        0.000                      0                 1806"
                "        4.500        0.000                       0"
                "                   698"
            ),
            (
                "3.684        0.000                      0                 1596"
                "        0.044        0.000                      0                 1596"
                "        4.500        0.000                       0"
                "                   626"
            ),
            1,
        ),
        (
            (
                "l_clk               9.129        0.000                      0"
                "                 1001        0.079        0.000"
                "                      0                 1001        7.638"
                "        0.000                       0                   391"
            ),
            (
                "l_clk               9.270        0.000                      0"
                "                  791        0.044        0.000"
                "                      0                  791        7.638"
                "        0.000                       0                   319"
            ),
            1,
        ),
        (
            (
                "s_axi_aclk          3.765        0.000                      0"
                "                  805        0.100        0.000"
                "                      0                  805        4.500"
                "        0.000                       0                   307"
            ),
            (
                "s_axi_aclk          3.684        0.000                      0"
                "                  805        0.100        0.000"
                "                      0                  805        4.500"
                "        0.000                       0                   307"
            ),
            1,
        ),
        (
            "Slack (MET) :             3.765ns",
            "Slack (MET) :             3.684ns",
            100,
        ),
        (
            "Slack (MET) :             0.079ns",
            "Slack (MET) :             0.044ns",
            100,
        ),
    )
    for old, new, count in replacements:
        _replace(timing, old, new, count=count)

    utilization = tmp_path / "utilization.rpt"
    for old, new in (
        ("| Slice LUTs              |  509 |", "| Slice LUTs              |  520 |"),
        ("| Slice Registers         |  587 |", "| Slice Registers         |  620 |"),
        ("| Slice                    |  204 |", "| Slice                    |  200 |"),
        ("|     17600 |  2.89 |", "|     17600 |  2.95 |"),
        ("|     35200 |  1.67 |", "|     35200 |  1.76 |"),
        ("|      4400 |  4.64 |", "|      4400 |  4.55 |"),
    ):
        _replace(utilization, old, new)

    assert _validate(tmp_path) == {
        "WNS_ns": "3.684",
        "TNS_ns": "0.000",
        "TNS_failing_endpoints": "0",
        "TNS_total_endpoints": "1596",
        "WHS_ns": "0.044",
        "THS_ns": "0.000",
        "THS_failing_endpoints": "0",
        "THS_total_endpoints": "1596",
        "WPWS_ns": "4.500",
        "TPWS_ns": "0.000",
        "TPWS_failing_endpoints": "0",
        "TPWS_total_endpoints": "626",
    }


def test_directory_fd_validation_and_command_path_binding(tmp_path: Path) -> None:
    _valid_reports(tmp_path)
    descriptor = VALIDATOR.os.open(tmp_path, VALIDATOR.os.O_RDONLY)
    try:
        assert (
            VALIDATOR.validate_ooc_reports(directory_fd=descriptor)["WNS_ns"] == "3.765"
        )
    finally:
        VALIDATOR.os.close(descriptor)

    _replace(
        tmp_path / "cdc-summary.rpt",
        f"-file {tmp_path}/cdc-summary.rpt",
        "-file /stale/copied/cdc-summary.rpt",
    )
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong-part",
        "traversal",
        "unknown-encoding",
        "nested-node",
        "doctype",
    ],
)
def test_routed_dcp_inventory_and_identity_are_strict(
    tmp_path: Path,
    mutation: str,
) -> None:
    _valid_reports(tmp_path)
    _rewrite_dcp(tmp_path / VALIDATOR.DCP_NAME, mutation)

    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


@pytest.mark.parametrize(
    "mutation",
    ["missing-route-db", "duplicate-route-db", "extra-member"],
)
def test_routed_dcp_member_inventory_is_exact(
    tmp_path: Path,
    mutation: str,
) -> None:
    _valid_reports(tmp_path)
    _rewrite_dcp(tmp_path / VALIDATOR.DCP_NAME, mutation)

    with pytest.raises(VALIDATOR.ValidationError, match="member inventory"):
        _validate(tmp_path)


def test_routed_dcp_exact_member_set_is_order_independent(tmp_path: Path) -> None:
    _valid_reports(tmp_path)
    dcp = tmp_path / VALIDATOR.DCP_NAME
    _rewrite_dcp(dcp, "reordered")

    assert _validate(tmp_path)["WNS_ns"] == "3.765"


def test_routed_dcp_rejects_pk_prefixed_junk_and_bounds_before_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _valid_reports(tmp_path)
    dcp = tmp_path / VALIDATOR.DCP_NAME
    dcp.write_bytes(b"PK\x03\x04" + DCP_PAD)
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)

    with dcp.open("wb") as stream:
        stream.truncate(VALIDATOR.DCP_MAX_BYTES + 1)
    directory_fd = VALIDATOR.os.open(tmp_path, VALIDATOR.os.O_RDONLY)
    try:

        def forbidden_read(*_args: object, **_kwargs: object) -> bytes:
            raise AssertionError("oversized DCP was read before its fstat size gate")

        monkeypatch.setattr(VALIDATOR.os, "read", forbidden_read)
        with pytest.raises(VALIDATOR.ValidationError, match="size is outside"):
            VALIDATOR._read_bounded_file(
                directory_fd,
                VALIDATOR.DCP_NAME,
                minimum=VALIDATOR.DCP_MIN_BYTES,
                maximum=VALIDATOR.DCP_MAX_BYTES,
            )
    finally:
        VALIDATOR.os.close(directory_fd)


def test_public_cli_normalizes_corrupt_dcp_deflate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _valid_reports(tmp_path)

    def corrupt_testzip(_archive: object) -> str | None:
        raise VALIDATOR.zlib.error("planted corrupt deflate stream")

    monkeypatch.setattr(VALIDATOR.zipfile.ZipFile, "testzip", corrupt_testzip)
    assert VALIDATOR.main([str(VALIDATOR_PATH), str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("OOC report validation failed:")
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    ("name", "old", "new", "count"),
    [
        (
            "cdc-summary.rpt",
            "113   113       0        0             0",
            "113   112       1        0             0",
            1,
        ),
        ("cdc-details.rpt", "CDC-15  Warning", "CDC-10  Warning", 112),
        ("cdc-details.rpt", "CDC-6   Warning       2", "CDC-6   Info          2", 1),
        (
            "cdc-details.rpt",
            "Clock enable controlled CDC structure detected",
            "Changed CDC detail description",
            112,
        ),
        ("drc.rpt", "Violations found: 5", "Violations found: 6", 1),
        ("drc.rpt", "ZPS7-1    | Warning", "ZPS7-1    | Error  ", 1),
        ("drc.rpt", "ZPS7-1", "UNKNOWN-1", 2),
        (
            "methodology.rpt",
            "TIMING-18 | Warning  | Missing input or output delay | 182",
            "TIMING-18 | Warning  | Missing input or output delay | 181",
            1,
        ),
        (
            "timing_summary.rpt",
            "3.765        0.000",
            "-0.001        0.000",
            2,
        ),
        (
            "timing_summary.rpt",
            "3.765        0.000                      0                 1806",
            "3.765        0.001                      0                 1806",
            1,
        ),
        (
            "timing_summary.rpt",
            "5. checking no_input_delay (137)",
            "5. checking no_input_delay (136)",
            2,
        ),
        (
            "route_status.rpt",
            "# of nets with routing errors.......... :           0 :",
            "# of nets with routing errors.......... :           1 :",
            1,
        ),
        (
            "route_status.rpt",
            "# of logical nets.......................... :        1657 :",
            "# of logical nets.......................... :        1658 :",
            1,
        ),
        (
            "clock_interaction.rpt",
            "0          113                   Ignored              Asynchronous Groups",
            "0          113                   Unsafe               Timed",
            1,
        ),
        (
            "utilization.rpt",
            "| Slice LUTs              |  509",
            "| Slice LUTs              | 17601",
            1,
        ),
        (
            "utilization.rpt",
            "| Block RAM Tile          |    3",
            "| Block RAM Tile          |    4",
            1,
        ),
        (
            "timing_summary.rpt",
            "l_clk       {0.000 8.138}      16.276",
            "l_clk       {0.000 8.138}      16.275",
            1,
        ),
        (
            "cdc-summary.rpt",
            "Build 3671981 Fri Oct 14 04:59:54 MDT 2022",
            "Build 3671982 Fri Oct 14 04:59:54 MDT 2022",
            1,
        ),
    ],
)
def test_exact_report_mutations_reject(
    tmp_path: Path,
    name: str,
    old: str,
    new: str,
    count: int,
) -> None:
    _valid_reports(tmp_path)
    _replace(tmp_path / name, old, new, count=count)

    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


def test_cdc_per_direction_inventory_is_independent(tmp_path: Path) -> None:
    _valid_reports(tmp_path)
    path = tmp_path / "cdc-details.rpt"
    text = path.read_text(encoding="utf-8")
    forward, reverse = text.split("Source Clock: l_clk", 1)
    forward = forward.replace(
        "CDC-3   Info      1-bit synchronized with ASYNC_REG property",
        "CDC-15  Warning   Clock enable controlled CDC structure detected",
        1,
    )
    reverse = reverse.replace(
        "CDC-15  Warning   Clock enable controlled CDC structure detected",
        "CDC-3   Info      1-bit synchronized with ASYNC_REG property",
        1,
    )
    path.write_text(forward + "Source Clock: l_clk" + reverse, encoding="utf-8")

    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


def test_cdc_detail_rows_are_not_validated_from_the_summary_alone(
    tmp_path: Path,
) -> None:
    _valid_reports(tmp_path)
    path = tmp_path / "cdc-details.rpt"
    text = path.read_text(encoding="utf-8")
    prefix, details = text.split("Source Clock: s_axi_aclk", 1)
    details = details.replace(
        "Clock enable controlled CDC structure detected",
        "Changed CDC detail description",
        1,
    )
    path.write_text(prefix + "Source Clock: s_axi_aclk" + details, encoding="utf-8")

    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            "destination_104[6:0]/D",
            "destination_104/D",
        ),
        (
            "destination_104[6:0]/D",
            "destination_104[5:0]/D",
        ),
    ],
)
def test_cdc6_requires_two_exact_matching_endpoint_ranges(
    tmp_path: Path,
    old: str,
    new: str,
) -> None:
    _valid_reports(tmp_path)
    _replace(tmp_path / "cdc-details.rpt", old, new)

    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


def test_cdc_tables_reject_unknown_or_malformed_rows(tmp_path: Path) -> None:
    _valid_reports(tmp_path)
    summary = tmp_path / "cdc-summary.rpt"
    with summary.open("a", encoding="utf-8") as stream:
        stream.write(
            "Advisory  rogue_clk  l_clk  No Common Primary Clock  "
            "Asynch Clock Groups  1  0  1  0  0\n"
        )
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)

    _valid_reports(tmp_path)
    details = tmp_path / "cdc-details.rpt"
    _replace(
        details,
        "---\n  1  CDC-15",
        "---\nmalformed nonblank CDC table row\n  1  CDC-15",
        count=2,
    )
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


@pytest.mark.parametrize(
    (
        "l_clk_wns",
        "l_clk_endpoints",
        "l_to_axi_endpoints",
        "axi_to_l_endpoints",
        "axi_wns",
        "axi_endpoints",
    ),
    [
        ("9.13", 1001, 18, 113, "3.76", 805),
        ("9.27", 791, 18, 113, "3.68", 805),
        ("0.00", 792, 19, 114, "99.99", 806),
    ],
)
def test_clock_interaction_accepts_clean_dynamic_metrics(
    l_clk_wns: str,
    l_clk_endpoints: int,
    l_to_axi_endpoints: int,
    axi_to_l_endpoints: int,
    axi_wns: str,
    axi_endpoints: int,
) -> None:
    VALIDATOR._validate_clock_interaction(
        _clock_interaction(
            l_clk_wns=l_clk_wns,
            l_clk_endpoints=l_clk_endpoints,
            l_to_axi_endpoints=l_to_axi_endpoints,
            axi_to_l_endpoints=axi_to_l_endpoints,
            axi_wns=axi_wns,
            axi_endpoints=axi_endpoints,
        )
    )


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate", "reordered"])
def test_clock_interaction_row_inventory_and_order_are_exact(mutation: str) -> None:
    lines = _clock_interaction().splitlines()
    row_indices = [
        index
        for index, line in enumerate(lines)
        if line.startswith(("l_clk ", "s_axi_aclk "))
    ]
    assert len(row_indices) == 4
    if mutation == "missing":
        lines.pop(row_indices[2])
    elif mutation == "extra":
        lines.insert(row_indices[-1] + 1, lines[row_indices[-1]])
    elif mutation == "duplicate":
        lines[row_indices[2]] = lines[row_indices[1]]
    else:
        first, second = row_indices[1:3]
        lines[first], lines[second] = lines[second], lines[first]

    with pytest.raises(VALIDATOR.ValidationError):
        VALIDATOR._validate_clock_interaction("\n".join(lines) + "\n")


@pytest.mark.parametrize(
    ("row_index", "start", "end", "value", "left_aligned"),
    [
        (0, 0, 12, "rogue_clk", True),
        (0, 28, 39, "fall - fall", True),
        (0, 41, 48, "NaN", False),
        (0, 41, 48, "-0.01", False),
        (0, 41, 48, "-0.00", False),
        (0, 50, 57, "0.01", False),
        (0, 50, 57, "-0.00", False),
        (0, 59, 70, "1", False),
        (0, 72, 83, "0", False),
        (0, 72, 83, "0001", False),
        (0, 85, 100, "16.27", False),
        (0, 102, 121, "Ignored", True),
        (0, 123, 142, "Asynchronous Groups", True),
        (1, 28, 39, "rise - rise", True),
        (1, 41, 48, "1.00", False),
        (1, 50, 57, "0.00", False),
        (1, 59, 70, "1", False),
        (1, 72, 83, "0", False),
        (1, 85, 100, "10.00", False),
        (1, 102, 121, "Clean", True),
        (1, 123, 142, "Timed", True),
    ],
)
def test_clock_interaction_semantic_mutations_reject(
    row_index: int,
    start: int,
    end: int,
    value: str,
    left_aligned: bool,
) -> None:
    lines = _clock_interaction().splitlines()
    row_indices = [
        index
        for index, line in enumerate(lines)
        if line.startswith(("l_clk ", "s_axi_aclk "))
    ]
    target = row_indices[row_index]
    lines[target] = _replace_fixed_field(
        lines[target], start, end, value, left_aligned=left_aligned
    )

    with pytest.raises(VALIDATOR.ValidationError):
        VALIDATOR._validate_clock_interaction("\n".join(lines) + "\n")


def test_clock_interaction_rejects_shifted_columns_and_noncontiguous_rows() -> None:
    lines = _clock_interaction().splitlines()
    row_indices = [
        index
        for index, line in enumerate(lines)
        if line.startswith(("l_clk ", "s_axi_aclk "))
    ]
    lines[row_indices[0]] = lines[row_indices[0]][:12] + lines[row_indices[0]][13:]
    with pytest.raises(VALIDATOR.ValidationError):
        VALIDATOR._validate_clock_interaction("\n".join(lines) + "\n")

    lines = _clock_interaction().splitlines()
    row_indices = [
        index
        for index, line in enumerate(lines)
        if line.startswith(("l_clk ", "s_axi_aclk "))
    ]
    lines.insert(row_indices[2], "")
    with pytest.raises(VALIDATOR.ValidationError):
        VALIDATOR._validate_clock_interaction("\n".join(lines) + "\n")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("Clock Interaction Report", "Clock Relationship Report"),
        ("Clock Interaction Table", "Clock Relationship Table"),
        ("Inter-Clock", "Inter.Clock"),
        ("From Clock    To Clock", "From Clock    At Clock"),
        (
            "------------  ------------  -----------",
            "-----------   ------------  -----------",
        ),
    ],
)
def test_clock_interaction_title_and_table_headers_are_exact(
    old: str, new: str
) -> None:
    report = _clock_interaction()
    assert report.count(old) == 1
    with pytest.raises(VALIDATOR.ValidationError):
        VALIDATOR._validate_clock_interaction(report.replace(old, new))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("rise - rise     9.13", "rise - rise     9.14"),
        ("0         1001            16.28", "0         1000            16.28"),
        (
            "0           18                   Ignored",
            "0           19                   Ignored",
        ),
        (
            "0          113                   Ignored",
            "0          114                   Ignored",
        ),
    ],
)
def test_clock_interaction_metrics_cross_bind_timing_and_cdc(
    tmp_path: Path, old: str, new: str
) -> None:
    _valid_reports(tmp_path)
    _replace(tmp_path / "clock_interaction.rpt", old, new)
    with pytest.raises(VALIDATOR.ValidationError, match="bind"):
        _validate(tmp_path)


def test_duplicate_clock_interaction_row_rejects(tmp_path: Path) -> None:
    _valid_reports(tmp_path)
    path = tmp_path / "clock_interaction.rpt"
    text = path.read_text(encoding="utf-8")
    row = next(
        line for line in text.splitlines() if line.startswith("l_clk         l_clk")
    )
    path.write_text(text + row + "\n", encoding="utf-8")

    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


def test_clock_tables_reject_unknown_clock_rows(tmp_path: Path) -> None:
    _valid_reports(tmp_path)
    interaction = tmp_path / "clock_interaction.rpt"
    with interaction.open("a", encoding="utf-8") as stream:
        stream.write("rogue_clk l_clk rise - rise 1.00 0.00 0 1 2.00 Clean Timed\n")
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)

    _valid_reports(tmp_path)
    timing = tmp_path / "timing_summary.rpt"
    _replace(
        timing,
        "s_axi_aclk  {0.000 5.000}      10.000          100.000\n",
        "s_axi_aclk  {0.000 5.000}      10.000          100.000\n"
        "rogue_clk   {0.000 1.000}       2.000          500.000\n",
    )
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


def test_timing_rejects_duplicate_methodology_and_spoofed_section(
    tmp_path: Path,
) -> None:
    _valid_reports(tmp_path)
    timing = tmp_path / "timing_summary.rpt"
    _replace(
        timing,
        "LUTAR-1    Warning   LUT drives async reset alert   1\n",
        "LUTAR-1    Warning   LUT drives async reset alert   1\n"
        "LUTAR-1    Warning   LUT drives async reset alert   1\n",
    )
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)

    _valid_reports(tmp_path)
    original = timing.read_text(encoding="utf-8")
    decoy = """| Design Timing Summary
WNS(ns)      TNS(ns)  TNS Failing Endpoints
-------      -------  ---------------------
3.765 0.000 0 1806 0.079 0.000 0 1806 4.500 0.000 0 698
All user specified timing constraints are met.
| Clock Summary
"""
    timing.write_text(
        decoy + original.replace("3.765        0.000", "-1.000        0.000", 1),
        encoding="utf-8",
    )
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


def test_timing18_detail_split_and_check_ordinals_are_exact(tmp_path: Path) -> None:
    _valid_reports(tmp_path)
    methodology = tmp_path / "methodology.rpt"
    _replace(
        methodology,
        "An input delay is missing on synthetic_137",
        "An output delay is missing on synthetic_137",
    )
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


def test_timing_detailed_violation_and_utilization_black_box_reject(
    tmp_path: Path,
) -> None:
    _valid_reports(tmp_path)
    _replace(
        tmp_path / "timing_summary.rpt",
        "Slack (MET) :             3.765ns  (required time - arrival time)",
        "Slack (VIOLATED) :        -1.000ns  (required time - arrival time)",
        count=100,
    )
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)

    _valid_reports(tmp_path)
    with (tmp_path / "timing_summary.rpt").open("a", encoding="utf-8") as stream:
        stream.write("  Slack (VIOLATED) : -1.000ns  (required time - arrival time)\n")
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)

    _valid_reports(tmp_path)
    _replace(
        tmp_path / "timing_summary.rpt",
        "Slack (MET) :             3.765ns",
        "Slack (MET) :             0.080ns",
        count=100,
    )
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)

    _valid_reports(tmp_path)
    _replace(
        tmp_path / "utilization.rpt",
        "| Ref Name | Used |\n+----------+------+\n\n\n10. Instantiated Netlists",
        "| Ref Name | Used |\n+----------+------+\n"
        "| evil_stub | 1 |\n\n\n10. Instantiated Netlists",
    )
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)

    _valid_reports(tmp_path)
    timing = tmp_path / "timing_summary.rpt"
    _replace(
        timing,
        "5. checking no_input_delay (137)",
        "99. checking no_input_delay (137)",
        count=2,
    )
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


@pytest.mark.parametrize(
    ("old", "new", "count"),
    [
        (
            "=== TANDEM AXI ROUTE COMPLETE ===",
            "prefix === TANDEM AXI ROUTE COMPLETE === suffix",
            1,
        ),
        (
            "=== TANDEM AXI ROUTE COMPLETE ===",
            ("=== TANDEM AXI ROUTE COMPLETE ===\n=== TANDEM AXI ROUTE COMPLETE ==="),
            1,
        ),
        (
            "0 Critical Warnings and 0 Errors encountered.",
            "1 Critical Warnings and 0 Errors encountered.",
            2,
        ),
        (
            "0 Critical Warnings and 0 Errors encountered.",
            "zero Critical Warnings and 0 Errors encountered.",
            2,
        ),
        ("SW Build 3671981", "SW Build 3671982", 1),
    ],
)
def test_vivado_log_authority_mutations_reject(
    tmp_path: Path,
    old: str,
    new: str,
    count: int,
) -> None:
    _valid_reports(tmp_path)
    _replace(tmp_path / "vivado.log", old, new, count=count)

    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


def test_vivado_log_anchored_critical_error_and_fatal_reject(tmp_path: Path) -> None:
    for planted in (
        "CRITICAL WARNING: planted",
        "ERROR: planted",
        "FATAL: planted",
    ):
        _valid_reports(tmp_path)
        with (tmp_path / "vivado.log").open("a", encoding="utf-8") as stream:
            stream.write(planted + "\n")
        with pytest.raises(VALIDATOR.ValidationError):
            _validate(tmp_path)

    _valid_reports(tmp_path)
    with (tmp_path / "vivado.log").open("a", encoding="utf-8") as stream:
        stream.write("1 Info, 1 Warning, 1 Critical Warning and 0 Error encountered.\n")
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


def test_unstructured_critical_report_message_rejects(tmp_path: Path) -> None:
    _valid_reports(tmp_path)
    with (tmp_path / "utilization.rpt").open("a", encoding="utf-8") as stream:
        stream.write("CRITICAL WARNING: planted post-route failure\n")

    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


def test_spoofed_good_rows_do_not_mask_bad_scoped_rows(tmp_path: Path) -> None:
    _valid_reports(tmp_path)
    route = tmp_path / "route_status.rpt"
    _replace(
        route,
        "# of nets with routing errors.......... :           0 :",
        "# of nets with routing errors.......... :           1 :",
    )
    with route.open("a", encoding="utf-8") as stream:
        stream.write("# of nets with routing errors.......... :           0 :\n")

    timing = tmp_path / "timing_summary.rpt"
    _replace(
        timing,
        "5. checking no_input_delay (137)",
        "5. checking no_input_delay (136)",
        count=2,
    )
    with timing.open("a", encoding="utf-8") as stream:
        stream.write("5. checking no_input_delay (137)\n")

    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


@pytest.mark.parametrize(
    ("old", "new", "count"),
    [
        (
            "3.765        0.000                      0                 1806",
            "-0.000        0.000                      0                 1806",
            1,
        ),
        (
            "3.765        0.000                      0                 1806",
            "3.765       -0.000                      0                 1806",
            1,
        ),
        (
            "l_clk               9.129        0.000                      0",
            "l_clk               9.129        0.000                      1",
            1,
        ),
        (
            (
                "l_clk               9.129        0.000                      0"
                "                 1001        0.079        0.000"
                "                      0                 1001"
            ),
            (
                "l_clk               9.129        0.000                      0"
                "                    0        0.079        0.000"
                "                      0                 1001"
            ),
            1,
        ),
        (
            (
                "0                 1806        0.079        0.000"
                "                      0                 1806"
            ),
            (
                "0                 1805        0.079        0.000"
                "                      0                 1805"
            ),
            1,
        ),
        (
            "3.765        0.000                      0                 1806",
            "3.766        0.000                      0                 1806",
            1,
        ),
        (
            (
                "l_clk               9.129        0.000                      0"
                "                 1001        0.079        0.000"
                "                      0                 1001"
            ),
            (
                "l_clk               9.129        0.000                      0"
                "                 1001        0.079        0.000"
                "                      0                 1000"
            ),
            1,
        ),
    ],
)
def test_timing_metric_invariant_mutations_reject(
    tmp_path: Path,
    old: str,
    new: str,
    count: int,
) -> None:
    _valid_reports(tmp_path)
    _replace(tmp_path / "timing_summary.rpt", old, new, count=count)
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


def test_timing_rejects_second_total_row_and_noncanonical_zero(tmp_path: Path) -> None:
    _valid_reports(tmp_path)
    timing = tmp_path / "timing_summary.rpt"
    total = (
        "      3.765        0.000                      0                 1806"
        "        0.079        0.000                      0                 1806"
        "        4.500        0.000                       0                   698"
    )
    _replace(timing, total, total + "\n" + total.replace("3.765", "-1.000", 1))
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)

    _valid_reports(tmp_path)
    _replace(
        timing,
        "3.765        0.000                      0                 1806",
        "3.765        0E999                      0                 1806",
    )
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


def test_black_box_section_rejects_decoy_end_marker(tmp_path: Path) -> None:
    _valid_reports(tmp_path)
    utilization = tmp_path / "utilization.rpt"
    _replace(
        utilization,
        "| Ref Name | Used |\n+----------+------+\n\n\n10. Instantiated Netlists",
        "| Ref Name | Used |\n+----------+------+\n"
        "\n10. Instantiated Netlists\n"
        "| evil_stub | 1 |\n\n10. Instantiated Netlists",
    )
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


def test_utilization_rows_cannot_be_spoofed_outside_their_sections(
    tmp_path: Path,
) -> None:
    _valid_reports(tmp_path)
    utilization = tmp_path / "utilization.rpt"
    exact = (
        "| Slice LUTs              |  509 |     0 |          0 |     17600 |  2.89 |"
    )
    _replace(utilization, exact, exact.replace("Slice LUTs", "Slice LUTx"))
    with utilization.open("a", encoding="utf-8") as stream:
        stream.write(exact + "\n")

    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


def test_utilization_real_toc_and_authoritative_body_are_distinct(
    tmp_path: Path,
) -> None:
    _valid_reports(tmp_path)
    utilization = (tmp_path / "utilization.rpt").read_text(encoding="utf-8")

    assert utilization.count("\n1. Slice Logic\n") == 2
    assert utilization.count("\n10. Instantiated Netlists\n") == 2
    assert _validate(tmp_path)["WNS_ns"] == "3.765"


@pytest.mark.parametrize("mutation", ["duplicate-body-heading", "reordered-body"])
def test_utilization_authoritative_body_heading_decoys_reject(
    tmp_path: Path,
    mutation: str,
) -> None:
    _valid_reports(tmp_path)
    utilization = tmp_path / "utilization.rpt"
    text = utilization.read_text(encoding="utf-8")
    slice_heading = "1. Slice Logic\n--------------"
    memory_heading = "3. Memory\n---------"
    dsp_heading = "4. DSP\n------"
    if mutation == "duplicate-body-heading":
        text = text.replace(
            "Utilization Design Information\n",
            f"Utilization Design Information\n\n{slice_heading}\n",
            1,
        )
    else:
        text = text.replace(memory_heading, "BODY-HEADING-SWAP", 1)
        text = text.replace(dsp_heading, memory_heading, 1)
        text = text.replace("BODY-HEADING-SWAP", dsp_heading, 1)
    utilization.write_text(text, encoding="utf-8")

    with pytest.raises(VALIDATOR.ValidationError, match="heading|section order"):
        _validate(tmp_path)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("| Slice LUTs              |  509 |", "| Slice LUTs              |  551 |"),
        ("| Slice LUTs              |  509 |", "| Slice LUTs              |    0 |"),
        (
            "| Slice LUTs              |  509 |     0 |",
            "| Slice LUTs              |  509 |     1 |",
        ),
        (
            "| Slice LUTs              |  509 |     0 |          0 |",
            "| Slice LUTs              |  509 |     0 |          1 |",
        ),
        ("|     17600 |  2.89 |", "|     17601 |  2.89 |"),
        ("|     17600 |  2.89 |", "|     17600 |  2.90 |"),
        ("| Slice                    |  204 |", "| Slice                    |  205 |"),
        ("|      4400 |  4.64 |", "|      4400 |  4.63 |"),
        ("| Block RAM Tile          |    3 |", "| Block RAM Tile          |    0 |"),
        ("|        60 |  5.00 |", "|        60 |  0.00 |"),
        ("| DSPs                    |    2 |", "| DSPs                    |   81 |"),
    ],
)
def test_utilization_capacity_invariant_mutations_reject(old: str, new: str) -> None:
    report = _utilization()
    assert report.count(old) == 1
    with pytest.raises(VALIDATOR.ValidationError):
        VALIDATOR._validate_utilization(report.replace(old, new))


@pytest.mark.parametrize("mutation", ["unknown", "duplicate", "missing"])
def test_route_table_has_an_exact_row_grammar(
    tmp_path: Path,
    mutation: str,
) -> None:
    _valid_reports(tmp_path)
    route = tmp_path / "route_status.rpt"
    text = route.read_text(encoding="utf-8")
    row = "       # of routable nets..................... :        1127 :\n"
    assert text.count(row) == 1
    if mutation == "unknown":
        text = text.replace(
            row,
            row + "       # of unsafe nets....................... :           1 :\n",
        )
    elif mutation == "duplicate":
        text = text.replace(row, row + row)
    else:
        text = text.replace(row, "")
    route.write_text(text, encoding="utf-8")

    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            "# of internally routed nets........ :         349 :",
            "# of internally routed nets........ :         348 :",
        ),
        (
            "# of fully routed nets............. :        1127 :",
            "# of fully routed nets............. :        1126 :",
        ),
        (
            "# of routable nets..................... :        1127 :",
            "# of routable nets..................... :           0 :",
        ),
        (
            "# of logical nets.......................... :        1657 :",
            "# of logical nets.......................... :           0 :",
        ),
    ],
)
def test_route_accounting_and_completion_invariants_reject(old: str, new: str) -> None:
    report = _route()
    assert report.count(old) == 1
    with pytest.raises(VALIDATOR.ValidationError):
        VALIDATOR._validate_route(report.replace(old, new))


def test_missing_symlink_invalid_utf8_and_oversize_reports_reject(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _valid_reports(tmp_path)
    summary = tmp_path / "cdc-summary.rpt"
    summary.unlink()
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)

    _valid_reports(tmp_path)
    real_summary = tmp_path / "real-summary.rpt"
    summary.rename(real_summary)
    summary.symlink_to(real_summary.name)
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)

    summary.unlink()
    summary.write_bytes(b"\xff")
    with pytest.raises(VALIDATOR.ValidationError):
        _validate(tmp_path)

    summary.unlink()
    with summary.open("wb") as stream:
        stream.truncate(VALIDATOR.REPORT_LIMITS["cdc-summary.rpt"] + 1)

    def forbidden_read(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("oversized report was read before its fstat size gate")

    monkeypatch.setattr(VALIDATOR.os, "read", forbidden_read)
    with pytest.raises(VALIDATOR.ValidationError, match="size is outside"):
        _validate(tmp_path)


def test_public_cli_normalizes_malformed_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _valid_reports(tmp_path)
    _replace(
        tmp_path / "route_status.rpt",
        "# of logical nets.......................... :        1657 :",
        "# of logical nets.......................... :        " + "9" * 5000 + " :",
    )

    assert VALIDATOR.main([str(VALIDATOR_PATH), str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("OOC report validation failed:")
    assert "Traceback" not in captured.err


def test_public_cli_normalizes_malformed_cdc_header(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _valid_reports(tmp_path)
    _replace(
        tmp_path / "cdc-details.rpt",
        "ID      Severity  Count  Description",
        "XID      Severity  Count  DescriptionY",
    )

    assert VALIDATOR.main([str(VALIDATOR_PATH), str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("OOC report validation failed:")
    assert "Traceback" not in captured.err
