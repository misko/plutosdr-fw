from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import scripts.starlink_pss_m3_execute_v1 as execute_v1
import scripts.starlink_pss_m3_execute_v2 as execute_v2
import scripts.starlink_pss_monitor_probe_v3 as monitor_v3
from tests.test_starlink_pss_m3_execute_v1 import _execute_args, _execution_plan


def _write_base_receipt(arguments: Any, *, outcome: str) -> None:
    execute_v1.probe_v1._write_new_private(
        arguments.output,
        {
            "outcome": outcome,
            "hardware_accessed": True,
            "persistent_write": False,
        },
    )


def test_v2_forces_monitor_v3_and_writes_deterministic_runner_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path, receipt_path, plan = _execution_plan(tmp_path, monkeypatch)
    observed: dict[str, Any] = {}

    def base_execute(arguments: Any, **dependencies: Any) -> dict[str, Any]:
        observed.update(dependencies)
        _write_base_receipt(arguments, outcome="pass")
        return {"verdict": "PASS_FAKE_BASE", "outcome": "pass"}

    result = execute_v2.execute_plan(
        _execute_args(plan_path, receipt_path, plan), base_execute=base_execute
    )

    assert observed == {"monitor_execute": monitor_v3.execute_plan}
    assert result["verdict"] == "PASS_FAKE_BASE"
    assert result["receiver_context_close_contract_active"] is True
    runner_path = execute_v2._runner_path(plan)
    assert runner_path == tmp_path / "execution-receipt-runner-v2.json"
    runner = execute_v1._load(runner_path, label="test v2 runner receipt")
    execute_v2._validate_runner(runner, plan_path=plan_path, plan=plan)
    assert runner["outcome"] == "pass"
    assert runner["execution_receipt"] == execute_v1._identity(
        receipt_path, label="test base receipt"
    )
    assert runner_path.stat().st_mode & 0o777 == 0o600

    monkeypatch.setattr(
        execute_v1,
        "verify_receipt",
        lambda arguments: {"outcome": "pass", "verdict": "PASS_FAKE_VERIFY"},
    )
    verified = execute_v2.verify_receipt(
        SimpleNamespace(plan=plan_path, receipt=receipt_path)
    )
    assert verified["verdict"] == "PASS_FAKE_VERIFY"
    assert len(verified["runner_receipt_sha256"]) == 64


def test_v2_failure_still_binds_failed_base_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path, receipt_path, plan = _execution_plan(tmp_path, monkeypatch)

    def fail(arguments: Any, **dependencies: Any) -> None:
        assert dependencies["monitor_execute"] is monitor_v3.execute_plan
        _write_base_receipt(arguments, outcome="failed")
        raise execute_v1.ProbeError("injected base failure")

    with pytest.raises(execute_v2.ProbeError, match="injected base failure"):
        execute_v2.execute_plan(
            _execute_args(plan_path, receipt_path, plan), base_execute=fail
        )

    runner = execute_v1._load(
        execute_v2._runner_path(plan), label="failed v2 runner receipt"
    )
    assert runner["outcome"] == "failed"
    assert runner["hardware_accessed"] is True
    assert "injected base failure" in runner["error"]


def test_v2_rejects_monitor_override_before_base_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path, receipt_path, plan = _execution_plan(tmp_path, monkeypatch)
    called = False

    def base_execute(arguments: Any, **dependencies: Any) -> None:
        nonlocal called
        called = True

    with pytest.raises(execute_v2.ProbeError, match="cannot be overridden"):
        execute_v2.execute_plan(
            _execute_args(plan_path, receipt_path, plan),
            base_execute=base_execute,
            dependencies={"monitor_execute": object()},
        )
    assert not called


def test_v2_wrong_confirmation_creates_no_runner_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path, receipt_path, plan = _execution_plan(tmp_path, monkeypatch)
    arguments = _execute_args(plan_path, receipt_path, plan)
    arguments.confirm = "yes"

    with pytest.raises(execute_v2.ProbeError, match="confirmation must be exactly"):
        execute_v2.execute_plan(arguments, base_execute=lambda *args, **kwargs: None)

    assert not execute_v2._runner_path(plan).exists()


def test_m3_execution_v2_is_executable() -> None:
    assert Path(execute_v2.__file__).stat().st_mode & 0o111
