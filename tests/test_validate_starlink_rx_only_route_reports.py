from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "ci" / "validate_starlink_rx_only_route_reports.py"
MONITOR = "i_system_wrapper/system_i/starlink_pss_candidate_monitor/inst/i_event_cdc"


def _detail_row(
    number: int, rule: str, severity: str, source: str, destination: str
) -> str:
    return (
        f"{number:4d}  {rule:<7} {severity:<8} reviewed  0  False Path  "
        f"{source}  {destination}"
    )


def _cdc_report() -> str:
    rows = [
        _detail_row(
            1,
            "CDC-1",
            "Critical",
            "i_system_wrapper/system_i/cpack_timestamp/inst/overflow_sync/"
            "input_reg_reg[0]/C",
            "i_system_wrapper/system_i/cpack_timestamp/inst/overflow_sync/"
            "output_reg_reg[0]/D",
        ),
        _detail_row(
            2,
            "CDC-4",
            "Critical",
            "i_system_wrapper/system_i/cpack_timestamp/inst/timestamp_cpu_sync/"
            "input_reg_reg[31:0]/C",
            "i_system_wrapper/system_i/cpack_timestamp/inst/timestamp_cpu_sync/"
            "output_reg_reg[31:0]/D",
        ),
    ]
    rows.extend(
        _detail_row(
            index + 3,
            "CDC-15",
            "Warning",
            f"{MONITOR}/mailbox_metric_num_reg[{index}]/C",
            f"{MONITOR}/snapshot_metric_num_reg[{index}]/D",
        )
        for index in range(293)
    )
    rows.extend(
        (
            _detail_row(
                296,
                "CDC-3",
                "Info",
                f"{MONITOR}/request_toggle_reg/C",
                f"{MONITOR}/request_sync_1_reg/D",
            ),
            _detail_row(
                297,
                "CDC-3",
                "Info",
                f"{MONITOR}/acknowledge_toggle_reg/C",
                f"{MONITOR}/acknowledge_sync_1_reg/D",
            ),
        )
    )
    return (
        "CDC Report\n\n"
        "CDC-1 Critical 1 reviewed\n"
        "CDC-3 Info 2 reviewed\n"
        "CDC-4 Critical 1 reviewed\n"
        "CDC-15 Warning 293 reviewed\n\n"
        + "\n".join(rows)
        + "\n"
    )


def _bus_skew_report(met: int = 3, violated: int = 0) -> str:
    return "Bus Skew Report\n" + "".join(
        f"Constraint {index}\nSlack (MET)\n" for index in range(met)
    ) + "".join(
        f"Constraint violated-{index}\nSlack (VIOLATED)\n" for index in range(violated)
    )


def _run(tmp_path: Path, cdc: str, bus: str) -> subprocess.CompletedProcess[str]:
    cdc_path = tmp_path / "cdc.rpt"
    bus_path = tmp_path / "bus-skew.rpt"
    cdc_path.write_text(cdc, encoding="utf-8")
    bus_path.write_text(bus, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--cdc-report",
            str(cdc_path),
            "--bus-skew-report",
            str(bus_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_exact_reviewed_route_inventory_passes(tmp_path: Path) -> None:
    result = _run(tmp_path, _cdc_report(), _bus_skew_report())

    assert result.returncode == 0, result.stderr
    assert "PASS exact RX-only routed CDC" in result.stdout


@pytest.mark.parametrize("met", [0, 2, 4])
def test_bus_skew_inventory_is_exact(tmp_path: Path, met: int) -> None:
    result = _run(tmp_path, _cdc_report(), _bus_skew_report(met=met))

    assert result.returncode == 1
    assert "expected exactly 3 met constraints" in result.stderr


def test_bus_skew_violation_is_rejected(tmp_path: Path) -> None:
    result = _run(tmp_path, _cdc_report(), _bus_skew_report(violated=1))

    assert result.returncode == 1
    assert "violated constraints" in result.stderr


@pytest.mark.parametrize(
    ("needle", "replacement", "message"),
    [
        (
            f"{MONITOR}/mailbox_metric_num_reg[0]/C",
            f"{MONITOR}/unreviewed_payload_source_reg[0]/C",
            "do not exactly cover",
        ),
        (
            f"{MONITOR}/snapshot_metric_num_reg[0]/D",
            f"{MONITOR}/unreviewed_destination_reg[0]/D",
            "do not exactly cover",
        ),
        (
            f"{MONITOR}/request_toggle_reg/C",
            f"{MONITOR}/unreviewed_request_source_reg/C",
            "do not exactly cover",
        ),
        (
            f"{MONITOR}/request_sync_1_reg/D",
            f"{MONITOR}/unreviewed_sync_reg/D",
            "do not exactly cover",
        ),
    ],
)
def test_monitor_inventory_changes_fail_closed(
    tmp_path: Path, needle: str, replacement: str, message: str
) -> None:
    mutated = _cdc_report().replace(needle, replacement, 1)
    result = _run(tmp_path, mutated, _bus_skew_report())

    assert result.returncode == 1
    assert message in result.stderr


@pytest.mark.parametrize(
    ("needle", "message"),
    [
        ("mailbox_metric_num_reg[0]", "CDC-15 inventory differs"),
        ("request_toggle_reg", "CDC-3 inventory differs"),
    ],
)
def test_missing_monitor_row_is_rejected(
    tmp_path: Path, needle: str, message: str
) -> None:
    rows = _cdc_report().splitlines()
    mutated = "\n".join(row for row in rows if needle not in row) + "\n"
    result = _run(tmp_path, mutated, _bus_skew_report())

    assert result.returncode == 1
    assert message in result.stderr


@pytest.mark.parametrize(
    ("needle", "message"),
    [
        ("mailbox_metric_num_reg[0]", "CDC-15 inventory differs"),
        ("request_toggle_reg", "CDC-3 inventory differs"),
    ],
)
def test_extra_monitor_row_is_rejected(
    tmp_path: Path, needle: str, message: str
) -> None:
    rows = _cdc_report().splitlines()
    reviewed_row = next(row for row in rows if needle in row)
    mutated = _cdc_report() + reviewed_row + "\n"
    result = _run(tmp_path, mutated, _bus_skew_report())

    assert result.returncode == 1
    assert message in result.stderr


def test_monitor_critical_row_is_rejected(tmp_path: Path) -> None:
    original = _detail_row(
        3,
        "CDC-15",
        "Warning",
        f"{MONITOR}/mailbox_metric_num_reg[0]/C",
        f"{MONITOR}/snapshot_metric_num_reg[0]/D",
    )
    critical = _detail_row(
        3,
        "CDC-1",
        "Critical",
        f"{MONITOR}/unexpected_source_reg/C",
        f"{MONITOR}/unexpected_destination_reg/D",
    )
    mutated = _cdc_report().replace(original, critical, 1)
    result = _run(tmp_path, mutated, _bus_skew_report())

    assert result.returncode == 1
    assert "monitor contributes Critical" in result.stderr


def test_additional_noncritical_monitor_row_is_rejected(tmp_path: Path) -> None:
    extra = _detail_row(
        298,
        "CDC-2",
        "Warning",
        f"{MONITOR}/unexpected_source_reg/C",
        f"{MONITOR}/unexpected_destination_reg/D",
    )
    result = _run(tmp_path, _cdc_report() + extra + "\n", _bus_skew_report())

    assert result.returncode == 1
    assert "monitor routed CDC inventory differs" in result.stderr


def test_noninherited_critical_row_is_rejected(tmp_path: Path) -> None:
    mutated = _cdc_report().replace(
        "cpack_timestamp/inst/overflow_sync/", "unreviewed_block/", 2
    )
    result = _run(tmp_path, mutated, _bus_skew_report())

    assert result.returncode == 1
    assert "lacks the one reviewed overflow" in result.stderr


def test_additional_nonmonitor_critical_row_is_rejected(tmp_path: Path) -> None:
    extra = _detail_row(
        298,
        "CDC-1",
        "Critical",
        "i_system_wrapper/system_i/axi_ad9361/unreviewed_source_reg/C",
        "i_system_wrapper/system_i/rx_fir_decimator/unreviewed_sync_reg/D",
    )
    result = _run(tmp_path, _cdc_report() + extra + "\n", _bus_skew_report())

    assert result.returncode == 1
    assert "differs from the two reviewed crossings: got 3" in result.stderr
