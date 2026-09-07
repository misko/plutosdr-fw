from __future__ import annotations

from pathlib import Path
from typing import Any

import scripts.starlink_pss_m3_execute_v1 as execute_v1
import scripts.starlink_pss_m3_execute_v3 as execute_v3
import scripts.starlink_pss_m3_iio_tx_v2 as tx_v2
from tests.test_starlink_pss_m3_execute_v1 import _execute_args, _execution_plan


def test_v3_scopes_stable_tx_driver_and_binds_both_runner_receipts(
    tmp_path: Path, monkeypatch: Any
) -> None:
    plan_path, receipt_path, plan = _execution_plan(tmp_path, monkeypatch)
    original = execute_v1.SingleTxCyclicIio

    def base_execute(arguments: Any, **dependencies: Any) -> dict[str, Any]:
        assert execute_v1.SingleTxCyclicIio is tx_v2.SingleTxCyclicIio
        assert "monitor_execute" in dependencies
        execute_v1.probe_v1._write_new_private(
            arguments.output,
            {"outcome": "pass", "hardware_accessed": True, "persistent_write": False},
        )
        return {"verdict": "PASS_FAKE_BASE", "outcome": "pass"}

    result = execute_v3.execute_plan(
        _execute_args(plan_path, receipt_path, plan), base_execute=base_execute
    )

    assert execute_v1.SingleTxCyclicIio is original
    assert result["stable_tx_channel_identity_contract_active"] is True
    runner_path = execute_v3._runner_path(plan)
    runner = execute_v1._load(runner_path, label="test v3 runner")
    execute_v3._validate_runner(runner, plan_path=plan_path, plan=plan)
    assert runner["outcome"] == "pass"
    assert runner["module_binding_restored"] is True
    assert runner["transmitter_driver_source"] == execute_v3._source_identity(
        tx_v2, label="test v2 transmitter driver"
    )
