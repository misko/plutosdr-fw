from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import scripts.starlink_pss_monitor_probe_v1 as monitor_v1
import scripts.starlink_pss_monitor_probe_v2 as monitor_v2
import scripts.starlink_pss_monitor_probe_v3 as monitor_v3


class FakeContext:
    def __init__(self) -> None:
        self._context = object()
        self.example = "preserved"


class FakeIio:
    def __init__(self, context: FakeContext) -> None:
        self.context = context
        self.uris: list[str] = []

    def Context(self, uri: str) -> FakeContext:
        self.uris.append(uri)
        return self.context


class FakeLinux:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any]] = []

    def _close_iio_context(self, iio_module: Any, context: FakeContext) -> None:
        self.calls.append((iio_module, context))
        context._context = None


def test_deterministic_contract_wraps_context_with_attested_ppu_closer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = FakeContext()
    iio = FakeIio(raw)
    linux = FakeLinux()
    observed: dict[str, Any] = {}

    def inherited(
        plan: Any,
        base: Any,
        handoff: Any,
        backend: Any,
        password: Any,
        iio_module: Any,
        ssh_builder: Any,
        payload: bytes,
    ) -> dict[str, Any]:
        context = iio_module.Context("usb:5.2.5")
        observed["attribute"] = context.example
        context.close()
        observed["closed"] = context._closed
        return {"closed": True}

    monkeypatch.setattr(monitor_v1, "_execute_measurement", inherited)
    before = monitor_v1._execute_measurement
    handoff = SimpleNamespace(ppu=SimpleNamespace(linux=linux))
    with monitor_v3._deterministic_context_contract():
        result = monitor_v1._execute_measurement(
            {}, {}, handoff, object(), object(), iio, object(), b"payload"
        )

    assert result == {"closed": True}
    assert monitor_v1._execute_measurement is before
    assert iio.uris == ["usb:5.2.5"]
    assert linux.calls == [(iio, raw)]
    assert raw._context is None
    assert observed == {"attribute": "preserved", "closed": True}


def test_contract_restores_inherited_function_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def inherited(*args: Any) -> dict[str, Any]:
        raise RuntimeError("injected measurement failure")

    monkeypatch.setattr(monitor_v1, "_execute_measurement", inherited)
    before = monitor_v1._execute_measurement
    handoff = SimpleNamespace(ppu=SimpleNamespace(linux=FakeLinux()))
    with (
        pytest.raises(RuntimeError, match="injected measurement failure"),
        monitor_v3._deterministic_context_contract(),
    ):
        monitor_v1._execute_measurement(
            {},
            {},
            handoff,
            object(),
            object(),
            FakeIio(FakeContext()),
            object(),
            b"",
        )
    assert monitor_v1._execute_measurement is before


def test_suppressed_closer_failure_is_promoted_to_measurement_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingLinux:
        @staticmethod
        def _close_iio_context(iio_module: Any, context: Any) -> None:
            raise OSError("injected close failure")

    def inherited(
        plan: Any,
        base: Any,
        handoff: Any,
        backend: Any,
        password: Any,
        iio_module: Any,
        ssh_builder: Any,
        payload: bytes,
    ) -> dict[str, Any]:
        context = iio_module.Context("usb:5.2.5")
        try:
            context.close()
        except OSError:
            pass
        return {"would_otherwise_pass": True}

    monkeypatch.setattr(monitor_v1, "_execute_measurement", inherited)
    handoff = SimpleNamespace(ppu=SimpleNamespace(linux=FailingLinux()))
    with (
        pytest.raises(monitor_v3.ProbeError, match="not deterministically verified"),
        monitor_v3._deterministic_context_contract(),
    ):
        monitor_v1._execute_measurement(
            {},
            {},
            handoff,
            object(),
            object(),
            FakeIio(FakeContext()),
            object(),
            b"",
        )


def test_v3_execute_delegates_with_context_contract_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = monitor_v1._execute_measurement

    def delegated(args: Any) -> dict[str, Any]:
        assert monitor_v1._execute_measurement is not original
        return {"verdict": "PASS_SCOPED_DELEGATION"}

    monkeypatch.setattr(monitor_v2, "execute_plan", delegated)
    assert monitor_v3.execute_plan(object()) == {"verdict": "PASS_SCOPED_DELEGATION"}
    assert monitor_v1._execute_measurement is original


def test_monitor_v3_preserves_v2_plan_and_receipt_schemas() -> None:
    assert monitor_v3.PLAN_SCHEMA == monitor_v2.PLAN_SCHEMA
    assert monitor_v3.RECEIPT_SCHEMA == monitor_v2.RECEIPT_SCHEMA
    assert monitor_v3.EXPECTED_FIRMWARE == monitor_v2.EXPECTED_FIRMWARE


def test_monitor_v3_is_executable() -> None:
    assert Path(monitor_v3.__file__).stat().st_mode & 0o111
