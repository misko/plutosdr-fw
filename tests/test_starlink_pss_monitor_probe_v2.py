from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

import scripts.starlink_pss_monitor_probe_v1 as monitor_v1
import scripts.starlink_pss_monitor_probe_v2 as monitor_v2
from tests.test_starlink_pss_monitor_probe_v1 import _plan, _records


def _v2_plan() -> dict[str, object]:
    plan = _plan()
    plan["schema"] = monitor_v2.PLAN_SCHEMA
    plan["expected_firmware"] = monitor_v2.EXPECTED_FIRMWARE
    return plan


def test_v2_plan_and_records_are_bound_to_v7() -> None:
    plan = _v2_plan()
    monitor_v2._validate_plan(plan)
    result = monitor_v2._validate_monitor_records(_records(), plan)

    assert result["summary"]["maps_copied"] == 12
    invalid = deepcopy(plan)
    invalid["expected_firmware"] = monitor_v1.EXPECTED_FIRMWARE
    with pytest.raises(monitor_v2.ProbeError, match="violate"):
        monitor_v2._validate_plan(invalid)


def test_v2_scoping_restores_historical_v1_contract() -> None:
    before = (
        monitor_v1.PLAN_SCHEMA,
        monitor_v1.RECEIPT_SCHEMA,
        monitor_v1.EXPECTED_FIRMWARE,
        monitor_v1._ad9361_v6_contract,
    )
    with monitor_v2._v7_monitor_contract():
        assert monitor_v1.PLAN_SCHEMA == monitor_v2.PLAN_SCHEMA
        assert monitor_v1.RECEIPT_SCHEMA == monitor_v2.RECEIPT_SCHEMA
        assert monitor_v1.EXPECTED_FIRMWARE == monitor_v2.EXPECTED_FIRMWARE
        assert monitor_v1._ad9361_v6_contract == (
            monitor_v2.probe_v9._ad9361_v7_acquisition_injection_contract
        )
    assert (
        monitor_v1.PLAN_SCHEMA,
        monitor_v1.RECEIPT_SCHEMA,
        monitor_v1.EXPECTED_FIRMWARE,
        monitor_v1._ad9361_v6_contract,
    ) == before


def test_v2_monitor_script_is_executable() -> None:
    assert Path(monitor_v2.__file__).stat().st_mode & 0o111
