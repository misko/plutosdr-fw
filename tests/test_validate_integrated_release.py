"""Planted-failure tests for the fail-closed integrated release gate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import stat
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_integrated_release.py"
POLICY_PATH = ROOT / "manifests" / "tandem-agc-v8-integrated-waivers.json"
COMMIT = "1" * 40


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_integrated_release", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_module()


def _write(path: Path, payload: bytes | str) -> None:
    if isinstance(payload, str):
        payload = payload.encode()
    path.write_bytes(payload)
    path.chmod(0o644)


def _write_dcp(path: Path) -> None:
    identities = [
        '<BUILD_NUMBER Name="3671981"/>',
        '<FULL_BUILD Name="SW Build 3671981 on Fri Oct 14 04:59:54 MDT 2022"/>',
        '<PRODUCT Name="Vivado v2022.2 (64-bit)"/>',
        '<Part Name="xc7z010clg400-1"/>',
        '<Top Name="system_top"/>',
        '<DisableAutoIOBuffers Name="0"/>',
        '<OutOfContext Name="0"/>',
        '<HDPlatform Name="0"/>',
    ]
    files = [
        f'<File Type="{file_type}" Name="{name}" ModTime="1"/>'
        for name, file_type in VALIDATOR.DCP_FILES.items()
    ]
    files.append('<File Type="HWDEF" Name="system_top.hwdef" ModTime="1"/>')
    xml = (
        '<?xml version="1.0"?>\n<Checkpoint Version="19" Minor="0">\n'
        + "\n".join(identities + files)
        + "\n</Checkpoint>\n"
    )
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in (("dcp.xml", xml), *VALIDATOR.DCP_FILES.items()):
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, payload)
    path.chmod(0o644)


def _header(
    command: str, *, state: str | None = None, device: str = "7z010-clg400"
) -> str:
    lines = [
        "Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.",
        "-" * 100,
        (
            "| Tool Version : Vivado v.2022.2 (lin64) Build 3671981 "
            "Fri Oct 14 04:59:54 MDT 2022"
        ),
        "| Date         : ignored",
        "| Host         : ignored",
        f"| Command      : {command}",
        "| Design       : system_top",
        f"| Device       : {device}",
        "| Speed File   : -1  PRODUCTION 1.12 2019-11-22",
    ]
    if state is not None:
        lines.append(f"| Design State : {state}")
    lines.extend(["-" * 100, ""])
    return "\n".join(lines)


def _timing(policy: dict[str, object]) -> str:
    checks = policy["check_timing"]
    assert isinstance(checks, list)
    toc = [
        f"{index}. checking {entry['check']} ({entry['count']})"
        for index, entry in enumerate(checks, 1)
    ]
    body = [
        f"{index}. checking {entry['check']} ({entry['count']})\n{'-' * 20}"
        for index, entry in enumerate(checks, 1)
    ]
    return (
        _header("report_timing_summary -report_unconstrained")
        + "Timing Summary Report\n\ncheck_timing report\n\nTable of Contents\n"
        + "\n".join(toc)
        + "\n\n"
        + "\n\n".join(body)
        + "\n\n| Design Timing Summary\n| ---------------------\n"
        + "    WNS(ns) TNS(ns) TNS Failing Endpoints TNS Total Endpoints WHS(ns) THS(ns) THS Failing Endpoints THS Total Endpoints WPWS(ns) TPWS(ns) TPWS Failing Endpoints TPWS Total Endpoints\n"
        + "    ------- ------- --------------------- ------------------- ------- ------- --------------------- ------------------- -------- -------- ---------------------- --------------------\n"
        + "      0.603 0.000 0 53788 0.017 0.000 0 53628 0.264 0.000 0 25303\n\n"
        + "All user specified timing constraints are met.\n"
    )


def _utilization(policy: dict[str, object]) -> str:
    entries = policy["utilization"]
    assert isinstance(entries, list)
    sections: list[str] = []
    for section_name in dict.fromkeys(entry["section"] for entry in entries):
        rows = []
        for entry in entries:
            if entry["section"] != section_name:
                continue
            used = {
                "Slice LUTs": 13502,
                "Slice Registers": 23120,
                "Block RAM Tile": 8,
                "DSPs": 74,
                "Bonded IOB": 53,
                "BUFGCTRL": 3,
            }[entry["resource"]]
            percent = 100.0 * used / entry["available"]
            rows.append(
                f"| {entry['resource']} | {used} | 0 | 0 | "
                f"{entry['available']} | {percent:.2f} |"
            )
        sections.append(
            f"{section_name}\n{'-' * len(section_name)}\n\n"
            "+--- fixture table ---+\n" + "\n".join(rows) + "\n"
        )
    return (
        _header("report_utilization", state="Routed", device="xc7z010clg400-1")
        + "Utilization Design Information\n\nTable of Contents\n-----------------\n"
        + "\n".join(entry["section"] for entry in entries)
        + "\n\n"
        + "\n".join(sections)
    )


def _rule_report(policy: dict[str, object], key: str) -> str:
    entries = policy[key]
    assert isinstance(entries, list)
    title = "Report DRC" if key == "drc" else "Report Methodology"
    rows = "\n".join(
        f"| {entry['rule']} | {entry['severity']} | reviewed | {entry['count']} |"
        for entry in entries
    )
    details = []
    for entry in entries:
        for index in range(1, entry["count"] + 1):
            details.append(
                f"{entry['rule']}#{index} {entry['severity']}\nReviewed fixture detail\nRelated violations: <none>"
            )
    return (
        _header(f"report_{key}", state="Fully Routed", device="xc7z010clg400-1")
        + f"{title}\n\nTable of Contents\n-----------------\n1. REPORT SUMMARY\n2. REPORT DETAILS\n\n"
        + "1. REPORT SUMMARY\n-----------------\n"
        + f"             Violations found: {sum(entry['count'] for entry in entries)}\n"
        + rows
        + "\n\n2. REPORT DETAILS\n-----------------\n"
        + "\n\n".join(details)
        + "\n"
    )


def _cdc(policy: dict[str, object]) -> str:
    cdc = policy["cdc"]
    assert isinstance(cdc, dict)
    entries = cdc["summary"]
    critical_paths = {entry["rule"]: entry for entry in cdc["critical_paths"]}
    summary = "\n".join(
        f"{entry['rule']}  {entry['severity']}  {entry['count']}  reviewed"
        for entry in entries
    )
    details = []
    row = 0
    for entry in entries:
        for index in range(entry["count"]):
            row += 1
            critical = critical_paths.get(entry["rule"])
            source = (
                critical["source"]
                if critical is not None
                else f"source/{entry['rule']}/{index}"
            )
            destination = (
                critical["destination"]
                if critical is not None
                else f"destination/{entry['rule']}/{index}"
            )
            details.append(
                f"{row}  {entry['rule']}  {entry['severity']}  reviewed crossing  0  False_Path  {source}  {destination}"
            )
    return (
        _header("report_cdc -details")
        + "CDC Report\n\nID Severity Count Description\n"
        + summary
        + "\n\nRow ID Severity Description Depth Exception Source Destination\n"
        + "\n".join(details)
        + "\n"
    )


def _bus(policy: dict[str, object]) -> str:
    bus = policy["bus_skew"]
    assert isinstance(bus, dict)
    blocks = []
    for index, scope in enumerate(bus["constraints"], 1):
        blocks.append(
            f"Id: {index}\n"
            f"set_bus_skew -from [get_cells {{{scope}/src}}] -to [get_cells {{{scope}/dest}}] {bus['requirement_ns']:.3f}\n"
            f"Requirement: {bus['requirement_ns']:.3f}ns\n"
            f"Endpoints: {bus['endpoints']}\n\n"
            f"Slack (MET) :             {8.0 + index / 10:.3f}ns  (requirement - actual skew)\n"
        )
    return _header("report_bus_skew") + "Bus Skew Report\n\n" + "\n".join(blocks)


def _fixture(root: Path) -> argparse.Namespace:
    policy = json.loads(POLICY_PATH.read_text())
    paths = {
        "source_manifest": root / "source.yaml",
        "waiver_inventory": root / "waivers.json",
        "routed_dcp": root / "system_top_routed.dcp",
        "utilization_report": root / "utilization.rpt",
        "timing_report": root / "timing.rpt",
        "route_status_report": root / "route.rpt",
        "drc_report": root / "drc.rpt",
        "methodology_report": root / "methodology.rpt",
        "cdc_report": root / "cdc.rpt",
        "bus_skew_report": root / "bus-skew.rpt",
        "output": root / "verdict.json",
    }
    _write(paths["source_manifest"], "schema: plutosdr-fw.source-manifest\n")
    _write(paths["waiver_inventory"], POLICY_PATH.read_bytes())
    _write_dcp(paths["routed_dcp"])
    _write(paths["utilization_report"], _utilization(policy))
    _write(paths["timing_report"], _timing(policy))
    _write(
        paths["route_status_report"],
        _header(
            "report_route_status",
            state="Fully Routed",
            device="xc7z010clg400-1",
        )
        + """Design Route Status
 : # nets :
 # of logical nets.......................... : 100 :
 # of nets not needing routing.............. : 40 :
 # of routable nets......................... : 60 :
 # of fully routed nets..................... : 60 :
 # of nets with routing errors.............. : 0 :
""",
    )
    _write(paths["drc_report"], _rule_report(policy, "drc"))
    _write(paths["methodology_report"], _rule_report(policy, "methodology"))
    _write(paths["cdc_report"], _cdc(policy))
    _write(paths["bus_skew_report"], _bus(policy))
    return argparse.Namespace(source_commit=COMMIT, **paths)


def _replace(path: Path, old: bytes | str, new: bytes | str) -> None:
    payload = path.read_bytes()
    if isinstance(old, str):
        old = old.encode()
    if isinstance(new, str):
        new = new.encode()
    assert old in payload
    _write(path, payload.replace(old, new, 1))


def test_valid_integrated_evidence_emits_exact_release_verdict(tmp_path: Path) -> None:
    args = _fixture(tmp_path)
    verdict = VALIDATOR.run(args)
    assert json.loads(args.output.read_text()) == verdict
    validated_inputs = [
        {
            "role": role,
            "path": getattr(args, attribute).name,
            "bytes": len(getattr(args, attribute).read_bytes()),
            "sha256": hashlib.sha256(getattr(args, attribute).read_bytes()).hexdigest(),
        }
        for role, attribute in VALIDATOR.VALIDATED_INPUTS
    ]
    assert verdict == {
        "schema": VALIDATOR.VERDICT_SCHEMA,
        "verdict": "PASS",
        "source_commit": COMMIT,
        "source_manifest_sha256": hashlib.sha256(
            args.source_manifest.read_bytes()
        ).hexdigest(),
        "routed_dcp_sha256": hashlib.sha256(args.routed_dcp.read_bytes()).hexdigest(),
        "waiver_inventory_sha256": hashlib.sha256(
            args.waiver_inventory.read_bytes()
        ).hexdigest(),
        "validated_inputs": validated_inputs,
        "firmware_release_eligible": True,
    }


def test_policy_records_reviewed_rc6_dsp_and_cdc_inventory() -> None:
    policy = json.loads(POLICY_PATH.read_text())
    dsp = next(entry for entry in policy["utilization"] if entry["resource"] == "DSPs")
    assert dsp == {
        "section": "4. DSP",
        "resource": "DSPs",
        "available": 80,
        "max_used": 74,
        "max_utilization_percent": 92.5,
        "rationale": (
            "The reviewed tandem pwr_div and evt_seq DSP48 mappings raise use to "
            "seventy-four blocks while reserving the remaining six blocks for "
            "placement margin."
        ),
    }
    cdc15 = next(
        entry for entry in policy["cdc"]["summary"] if entry["rule"] == "CDC-15"
    )
    assert cdc15 == {
        "rule": "CDC-15",
        "severity": "Warning",
        "count": 2085,
        "rationale": (
            "The exact inventory covers inherited ADI clock-enable controlled "
            "false-path crossings plus the added coherent tandem "
            "fault[3]/F_ILLEGAL snapshot crossing."
        ),
    }


@pytest.mark.parametrize(
    ("used", "percent", "accepted"),
    ((73, "91.25", True), (75, "93.75", False)),
)
def test_dsp_guardrail_accepts_headroom_and_rejects_excess(
    tmp_path: Path, used: int, percent: str, accepted: bool
) -> None:
    args = _fixture(tmp_path)
    _replace(
        args.utilization_report,
        "| DSPs | 74 | 0 | 0 | 80 | 92.50 |",
        f"| DSPs | {used} | 0 | 0 | 80 | {percent} |",
    )
    if accepted:
        assert VALIDATOR.run(args)["verdict"] == "PASS"
        assert args.output.exists()
    else:
        with pytest.raises(VALIDATOR.ValidationError, match="guardrail exceeded"):
            VALIDATOR.run(args)
        assert not args.output.exists()


@pytest.mark.parametrize("count", (2084, 2086))
def test_cdc15_old_and_extra_counts_are_rejected(tmp_path: Path, count: int) -> None:
    args = _fixture(tmp_path)
    _replace(
        args.cdc_report,
        "CDC-15  Warning  2085  reviewed",
        f"CDC-15  Warning  {count}  reviewed",
    )
    with pytest.raises(VALIDATOR.ValidationError, match="CDC summary"):
        VALIDATOR.run(args)
    assert not args.output.exists()


@pytest.mark.parametrize(
    ("field", "old", "new"),
    (
        (
            "utilization_report",
            "| Design State : Routed\n",
            "| Design State : Fully Routed\n",
        ),
        ("route_status_report", "| Design State : Fully Routed\n", ""),
        (
            "drc_report",
            "| Design State : Fully Routed\n",
            "| Design State : Fully Routed\n| Design State : Fully Routed\n",
        ),
        (
            "methodology_report",
            "| Design State : Fully Routed\n",
            "| Design State : Routed\n",
        ),
        (
            "timing_report",
            "| Speed File   : -1  PRODUCTION 1.12 2019-11-22\n",
            (
                "| Speed File   : -1  PRODUCTION 1.12 2019-11-22\n"
                "| Design State : Fully Routed\n"
            ),
        ),
        (
            "cdc_report",
            "| Speed File   : -1  PRODUCTION 1.12 2019-11-22\n",
            (
                "| Speed File   : -1  PRODUCTION 1.12 2019-11-22\n"
                "| Design State : Fully Routed\n"
            ),
        ),
        (
            "bus_skew_report",
            "| Speed File   : -1  PRODUCTION 1.12 2019-11-22\n",
            (
                "| Speed File   : -1  PRODUCTION 1.12 2019-11-22\n"
                "| Design State : Fully Routed\n"
            ),
        ),
    ),
)
def test_report_state_contract_is_exact(
    tmp_path: Path, field: str, old: str, new: str
) -> None:
    args = _fixture(tmp_path)
    _replace(getattr(args, field), old, new)
    with pytest.raises(VALIDATOR.ValidationError, match="design state"):
        VALIDATOR.run(args)
    assert not args.output.exists()


@pytest.mark.parametrize(
    ("field", "old", "new"),
    (
        (
            "route_status_report",
            "# of fully routed nets..................... : 60 :",
            "# of fully routed nets..................... : 59 :",
        ),
        (
            "route_status_report",
            "# of nets with routing errors.............. : 0 :",
            "# of nets with routing errors.............. : 1 :",
        ),
        (
            "route_status_report",
            "| Device       : xc7z010clg400-1",
            "| Device       : xc7z020clg400-1",
        ),
        ("timing_report", "0.603 0.000 0 53788", "-0.001 0.001 1 53788"),
        ("timing_report", "checking no_clock (0)", "checking no_clock (1)"),
        (
            "utilization_report",
            "| Slice LUTs | 13502 | 0 | 0 | 17600 | 76.72 |",
            "| Slice LUTs | 13502 | 0 | 0 | 17599 | 76.72 |",
        ),
        (
            "drc_report",
            "| CHECK-3 | Warning | reviewed | 1 |",
            "| NEW-1 | Critical | reviewed | 1 |",
        ),
        ("methodology_report", "| TIMING-9 | Warning", "| TIMING-9 | Critical"),
        ("cdc_report", "CDC-1  Critical  1", "CDC-1  Critical  2"),
        (
            "cdc_report",
            "cpack_timestamp/inst/overflow_sync/output_reg_reg[0]/D",
            "unreviewed/output/D",
        ),
        ("bus_skew_report", "Slack (MET)", "Slack (VIOLATED)"),
        ("bus_skew_report", "cpack_timestamp/inst/fifo", "unknown_timestamp/inst/fifo"),
        ("timing_report", "Vivado v.2022.2", "Vivado v.2023.1"),
    ),
)
def test_planted_report_failures_are_rejected(
    tmp_path: Path, field: str, old: str, new: str
) -> None:
    args = _fixture(tmp_path)
    _replace(getattr(args, field), old, new)
    with pytest.raises(VALIDATOR.ValidationError):
        VALIDATOR.run(args)
    assert not args.output.exists()


def test_non_checkpoint_and_existing_output_are_rejected(tmp_path: Path) -> None:
    args = _fixture(tmp_path)
    _write(args.routed_dcp, b"not-a-checkpoint")
    with pytest.raises(VALIDATOR.ValidationError, match="ZIP checkpoint"):
        VALIDATOR.run(args)

    args = _fixture(tmp_path)
    _write(args.output, "preexisting\n")
    with pytest.raises(VALIDATOR.ValidationError, match="must be absent"):
        VALIDATOR.run(args)


def test_duplicate_policy_key_is_rejected(tmp_path: Path) -> None:
    args = _fixture(tmp_path)
    _replace(
        args.waiver_inventory,
        b'{\n  "schema":',
        b'{\n  "schema_version": 1,\n  "schema":',
    )
    with pytest.raises(VALIDATOR.ValidationError, match="duplicate key"):
        VALIDATOR.run(args)


def test_symlink_report_is_rejected(tmp_path: Path) -> None:
    args = _fixture(tmp_path)
    target = args.route_status_report
    moved = tmp_path / "route-target.rpt"
    target.rename(moved)
    target.symlink_to(moved)
    with pytest.raises(VALIDATOR.ValidationError, match="non-symlink"):
        VALIDATOR.run(args)


def test_rc5_through_rc20_and_final_packaging_cannot_bypass_integrated_gate() -> None:
    package = (ROOT / "scripts" / "ci" / "package_main_firmware.sh").read_text()
    assert (
        package.count(
            "tandem-agc-v8-rc5-source.yaml | tandem-agc-v8-rc6-source.yaml | "
            "tandem-agc-v8-rc7-source.yaml | tandem-agc-v8-rc8-source.yaml | "
            "tandem-agc-v8-rc9-source.yaml | tandem-agc-v8-rc10-source.yaml | "
            "tandem-agc-v8-rc11-source.yaml | "
            "tandem-agc-v8-rc12-source.yaml | "
            "tandem-agc-v8-rc13-source.yaml | "
            "tandem-agc-v8-rc14-source.yaml | "
            "tandem-agc-v8-rc15-source.yaml | "
            "tandem-agc-v8-rc16-source.yaml | "
            "tandem-agc-v8-rc17-source.yaml | "
            "tandem-agc-v8-rc18-source.yaml | "
            "tandem-agc-v8-rc19-source.yaml | "
            "tandem-agc-v8-rc20-source.yaml | "
            "tandem-agc-v8-source.yaml"
        )
        == 1
    )
    assert package.count("python3 scripts/validate_integrated_release.py") == 1
    assert (
        'INTEGRATED_WAIVERS="${ROOT}/manifests/tandem-agc-v8-integrated-waivers.json"'
    ) in package
    assert "open_checkpoint {$routed_dcp}" in package
    for command in (
        "report_route_status",
        "report_drc",
        "report_methodology",
        "report_utilization",
        "report_timing_summary",
        "report_cdc -details",
        "report_bus_skew",
    ):
        assert command in package
    assert "report_route_status -return_string" in package
    assert "get_property TOP [current_design]" in package
    assert "checkpoint is not fully routed" in package
    for argument in (
        "--source-commit",
        "--source-manifest",
        "--waiver-inventory",
        "--routed-dcp",
        "--utilization-report",
        "--timing-report",
        "--route-status-report",
        "--drc-report",
        "--methodology-report",
        "--cdc-report",
        "--bus-skew-report",
        "--output",
    ):
        assert package.count(argument) == 1
