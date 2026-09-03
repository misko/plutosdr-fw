from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import scripts.starlink_pss_hardware_probe as probe
from scripts.starlink_pss_hardware_probe import (
    ALLOCATED_SERIAL,
    EXPECTED_MODEL,
    PLAN_SCHEMA,
    ProbeError,
    _load_private_json,
    _measure,
    _validate_plan,
    _write_new_private,
    execute_plan,
    verify_receipt,
)
from scripts.starlink_pss_hardware_probe import _identity as actual_identity

REPOSITORY = Path(__file__).resolve().parents[1]


def _identity(path: Path, digest: str) -> dict[str, object]:
    return {"path": str(path.absolute()), "bytes": 100, "sha256": digest * 64}


def _plan(root: Path, *, rate: int = 15, bandwidth: int = 15_000_000) -> dict[str, Any]:
    return {
        "schema": PLAN_SCHEMA,
        "schema_version": 1,
        "plan_id": "1" * 32,
        "created_at": "2026-09-03T20:00:00Z",
        "do_not_merge": True,
        "allowed_operation": "rx-only-candidate-measurement",
        "hardware_accessed": False,
        "persistent_write": False,
        "serial": ALLOCATED_SERIAL,
        "rate_msps": rate,
        "sample_rate_hz": rate * 1_000_000,
        "rf_bandwidth_hz": bandwidth,
        "runtime_target": "ad9363a-1r1t",
        "expected_firmware": (
            f"v0.50-plutoplus-starlink-pss-{rate}m-rx-only-dnm-v2"
        ),
        "ppu_repository": str((root / "ppu").absolute()),
        "ppu_source_commit": "2" * 40,
        "candidate_plan": _identity(root / "candidate.json", "3"),
        "operation_plan": _identity(root / "operation.json", "4"),
        "ram_receipt": _identity(root / "ram-receipt.json", "5"),
        "controller_timeout_ms": 5000,
        "confirmation_phrase": (
            f"RUN STARLINK PSS CANDIDATE {ALLOCATED_SERIAL} {rate} MSPS"
        ),
        "receipt_path": str((root / "probe-receipt.json").absolute()),
    }


@pytest.mark.parametrize(
    ("rate", "bandwidth"), [(15, 15_000_000), (30, 20_000_000), (60, 20_000_000)]
)
def test_plan_policy_accepts_only_staged_ad9363a_rates(
    tmp_path: Path, rate: int, bandwidth: int
) -> None:
    _validate_plan(_plan(tmp_path, rate=rate, bandwidth=bandwidth))


@pytest.mark.parametrize(
    "update",
    [
        {"serial": "f" * 40},
        {"rate_msps": 25, "sample_rate_hz": 25_000_000},
        {"rf_bandwidth_hz": 20_000_001},
        {"persistent_write": True},
        {"confirmation_phrase": "RUN"},
        {"created_at": "2026-09-03T20:00:00+01:00"},
    ],
)
def test_plan_policy_rejects_scope_or_identity_drift(
    tmp_path: Path, update: dict[str, object]
) -> None:
    plan = _plan(tmp_path, rate=30, bandwidth=20_000_000) | update
    with pytest.raises(ProbeError):
        _validate_plan(plan)


def test_private_plan_writer_is_canonical_exclusive_and_mode_0600(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    output = tmp_path / "plan.json"
    plan = _plan(tmp_path)

    identity = _write_new_private(output, plan)

    assert output.stat().st_mode & 0o777 == 0o600
    assert identity["bytes"] == len(output.read_bytes())
    assert _load_private_json(output, label="test plan") == plan
    with pytest.raises(ProbeError, match="existing output"):
        _write_new_private(output, plan)


class FakeAttribute:
    def __init__(self, value: str) -> None:
        self.value = value


class FailingCaptureRateAttribute:
    def __init__(self, context: FakeContext) -> None:
        self.context = context
        self._value = "10000000"

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, requested: str) -> None:
        if requested != "10000000":
            raise OSError("fixture capture write failure")
        if self.context.phy_channel.attrs["sampling_frequency"].value != "10000000":
            raise OSError("capture restored before PHY source")
        self._value = requested


class FakeChannel:
    def __init__(self, identifier: str, **attributes: str) -> None:
        self.id = identifier
        self.attrs = {name: FakeAttribute(value) for name, value in attributes.items()}


class FakeDevice:
    def __init__(self, name: str, channel: FakeChannel) -> None:
        self.name = name
        self.channel = channel

    def find_channel(self, identifier: str, output: bool) -> FakeChannel | None:
        if identifier == self.channel.id and output is False:
            return self.channel
        return None

    def reg_read(self, address: int) -> int:
        assert address == probe.ADC_GP_CONTROL_REG
        return 0


class FakeContext:
    def __init__(self, uri: str, *, rate: int) -> None:
        self.uri = uri
        self.timeout_ms: int | None = None
        self.closed = False
        self.attrs = {
            "hw_serial": ALLOCATED_SERIAL,
            "fw_version": f"v0.50-plutoplus-starlink-pss-{rate}m-rx-only-dnm-v2",
            "hw_model": EXPECTED_MODEL,
        }
        self.phy_channel = FakeChannel(
            "voltage0", sampling_frequency="10000000", rf_bandwidth="9000000"
        )
        self.capture_channel = FakeChannel(
            "voltage0",
            sampling_frequency="10000000",
            sampling_frequency_available=f"{rate * 1_000_000} {rate * 1_000_000 // 8}",
        )
        self.devices = {
            "ad9361-phy": FakeDevice("ad9361-phy", self.phy_channel),
            "cf-ad9361-lpc": FakeDevice("cf-ad9361-lpc", self.capture_channel),
        }

    def set_timeout(self, value: int) -> None:
        self.timeout_ms = value

    def find_device(self, name: str) -> FakeDevice | None:
        return self.devices.get(name)

    def close(self) -> None:
        self.closed = True


class FakeIio:
    def __init__(self, rate: int) -> None:
        self.context = FakeContext("", rate=rate)

    def Context(self, uri: str) -> FakeContext:
        self.context.uri = uri
        return self.context


class FakeRunner:
    def __init__(
        self,
        rate: int,
        *,
        bad_lock_claim: bool = False,
        enabled_after: bool = False,
    ) -> None:
        self.rate = rate
        self.bad_lock_claim = bad_lock_claim
        self.enabled_after = enabled_after
        self.info_count = 0
        self.commands: list[str] = []

    def run(self, argv: tuple[str, ...], *, timeout_s: float) -> str:
        assert timeout_s >= 10
        command = argv[-1]
        self.commands.append(command)
        common = {"serial": ALLOCATED_SERIAL}
        if command.endswith(" info"):
            self.info_count += 1
            value = {
                "schema": "starlink-pss-acqctl.info.v1",
                "claim_scope": "hardware_contract_only",
                "input_rate_msps": self.rate,
                "status": (
                    "0x00000003"
                    if self.enabled_after and self.info_count > 1
                    else "0x00000001"
                ),
            } | common
        elif " candidate " in command:
            value = {
                "schema": "starlink-pss-acqctl.candidate.v1",
                "claim_scope": "candidate_measurement_only",
                "input_rate_msps": self.rate,
                "continuity_ok": True,
                "threshold_decision": None,
                "frame_lock_claim": self.bad_lock_claim,
                "fault_free_epoch": True,
            } | common
        else:
            value = {
                "schema": "starlink-pss-acqctl.snapshot.v1",
                "fault_free_epoch": True,
            } | common
        return json.dumps(value)


def _ssh_builder(
    target: object,
    *,
    ssh_host: str,
    password_path: Path,
    remote_command: str,
) -> tuple[str, ...]:
    assert target is not None
    assert ssh_host == "192.168.2.1"
    assert password_path.is_absolute()
    return ("ssh", remote_command)


def _measurement_handoff(rate: int, runner: FakeRunner) -> tuple[Any, Any, Any]:
    target = SimpleNamespace(bus_number=5, device_number=23)
    operation = SimpleNamespace(target=target, ssh_host="192.168.2.1")
    handoff = SimpleNamespace(operation=operation)
    backend = SimpleNamespace(runner=runner)
    password = SimpleNamespace(path=Path("/private/password").absolute())
    return handoff, backend, password


def test_measurement_configures_exact_rx_path_and_restores_it(tmp_path: Path) -> None:
    rate = 60
    plan = _plan(tmp_path, rate=rate, bandwidth=20_000_000)
    runner = FakeRunner(rate)
    handoff, backend, password = _measurement_handoff(rate, runner)
    iio = FakeIio(rate)

    result = _measure(plan, handoff, backend, password, iio, _ssh_builder)

    assert result["iio_uri"] == "usb:5.23.5"
    assert result["iio_selected"] == {
        "phy_rx_sampling_frequency": 60_000_000,
        "capture_rx_sampling_frequency": 60_000_000,
        "phy_rx_rf_bandwidth": 20_000_000,
    }
    assert result["capture_rates_available_hz"] == (60_000_000, 7_500_000)
    assert result["fpga_decimation_factor"] == 1
    assert result["iio_restore_verified"] is True
    assert iio.context.capture_channel.attrs["sampling_frequency"].value == "10000000"
    assert iio.context.phy_channel.attrs["sampling_frequency"].value == "10000000"
    assert iio.context.phy_channel.attrs["rf_bandwidth"].value == "9000000"
    assert iio.context.closed is True
    assert len(runner.commands) == 5
    assert result["candidate"]["frame_lock_claim"] is False


def test_measurement_rejects_lock_claim_and_still_restores_rx(tmp_path: Path) -> None:
    rate = 15
    plan = _plan(tmp_path, rate=rate, bandwidth=15_000_000)
    runner = FakeRunner(rate, bad_lock_claim=True)
    handoff, backend, password = _measurement_handoff(rate, runner)
    iio = FakeIio(rate)

    with pytest.raises(ProbeError, match="measurement-only contract"):
        _measure(plan, handoff, backend, password, iio, _ssh_builder)

    assert iio.context.capture_channel.attrs["sampling_frequency"].value == "10000000"
    assert iio.context.phy_channel.attrs["rf_bandwidth"].value == "9000000"
    assert iio.context.closed is True


def test_measurement_rejects_engine_left_enabled_and_restores_rx(tmp_path: Path) -> None:
    rate = 30
    plan = _plan(tmp_path, rate=rate, bandwidth=20_000_000)
    runner = FakeRunner(rate, enabled_after=True)
    handoff, backend, password = _measurement_handoff(rate, runner)
    iio = FakeIio(rate)

    with pytest.raises(ProbeError, match="measurement-only contract"):
        _measure(plan, handoff, backend, password, iio, _ssh_builder)

    assert iio.context.capture_channel.attrs["sampling_frequency"].value == "10000000"
    assert iio.context.closed is True


def test_measurement_rejects_fpga_decimation_and_restores_rx(tmp_path: Path) -> None:
    rate = 60
    plan = _plan(tmp_path, rate=rate, bandwidth=20_000_000)
    runner = FakeRunner(rate)
    handoff, backend, password = _measurement_handoff(rate, runner)
    iio = FakeIio(rate)
    iio.context.devices["cf-ad9361-lpc"].reg_read = lambda address: 1

    with pytest.raises(ProbeError, match="factor-one capture path"):
        _measure(plan, handoff, backend, password, iio, _ssh_builder)

    assert iio.context.phy_channel.attrs["sampling_frequency"].value == "10000000"
    assert iio.context.capture_channel.attrs["sampling_frequency"].value == "10000000"
    assert iio.context.closed is True


def test_partial_rate_configuration_restores_phy_before_capture(tmp_path: Path) -> None:
    rate = 60
    plan = _plan(tmp_path, rate=rate, bandwidth=20_000_000)
    runner = FakeRunner(rate)
    handoff, backend, password = _measurement_handoff(rate, runner)
    iio = FakeIio(rate)
    iio.context.capture_channel.attrs["sampling_frequency"] = (
        FailingCaptureRateAttribute(iio.context)
    )

    with pytest.raises(OSError, match="fixture capture write failure"):
        _measure(plan, handoff, backend, password, iio, _ssh_builder)

    assert iio.context.phy_channel.attrs["sampling_frequency"].value == "10000000"
    assert iio.context.capture_channel.attrs["sampling_frequency"].value == "10000000"
    assert iio.context.closed is True


class FakeRuntime:
    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return {"serial": ALLOCATED_SERIAL, "layout": {"kind": "rx-only"}}


class FakeBackend:
    def __init__(self, runner: FakeRunner) -> None:
        self.runner = runner
        self.route_released = False
        self.target_revalidated = False

    @contextmanager
    def transaction_locks(self, target: object, ssh_host: str):
        assert target is not None
        assert ssh_host == "192.168.2.1"
        yield

    def revalidate_target(self, target: object) -> object:
        self.target_revalidated = True
        return target

    def acquire_host_route(self, target: object, ssh_host: str) -> object:
        assert target is not None
        assert ssh_host == "192.168.2.1"
        return SimpleNamespace(destination="192.168.2.1/32")

    def attest_rx_only_runtime_v2(self, target: object, **kwargs: object) -> FakeRuntime:
        assert target is not None
        assert kwargs["runtime_target"] == "ad9363a-1r1t"
        return FakeRuntime()

    def release_host_route(self, route: object) -> None:
        assert route is not None
        self.route_released = True


def _execute_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    bad_lock_claim: bool = False,
) -> tuple[SimpleNamespace, FakeBackend, FakeIio, Path]:
    tmp_path.chmod(0o700)
    for name in ("candidate.json", "operation.json", "ram-receipt.json"):
        _write_new_private(tmp_path / name, {"fixture": name})
    rate = 15
    plan = _plan(tmp_path, rate=rate, bandwidth=15_000_000)
    for label, name in (
        ("candidate_plan", "candidate.json"),
        ("operation_plan", "operation.json"),
        ("ram_receipt", "ram-receipt.json"),
    ):
        plan[label] = actual_identity(tmp_path / name, label=label)
    plan_path = tmp_path / "probe-plan.json"
    _write_new_private(plan_path, plan)
    target = SimpleNamespace(bus_number=5, device_number=23)
    operation = SimpleNamespace(target=target, ssh_host="192.168.2.1")
    runner = FakeRunner(rate, bad_lock_claim=bad_lock_claim)
    backend = FakeBackend(runner)
    iio = FakeIio(rate)
    lifecycle = SimpleNamespace(
        validate_password_file=lambda path: SimpleNamespace(path=path.absolute()),
        ssh_fixed_argv=_ssh_builder,
    )
    linux = SimpleNamespace(
        LinuxRxOnlyReleaseCandidateBackend=lambda **kwargs: backend
    )
    handoff = SimpleNamespace(
        operation=operation,
        candidate=SimpleNamespace(
            artifact_index=SimpleNamespace(path=tmp_path / "candidate-index.json")
        ),
        ppu=SimpleNamespace(lifecycle=lifecycle, linux=linux),
    )
    monkeypatch.setattr(probe, "_load_handoff", lambda **kwargs: handoff)
    monkeypatch.setattr(probe.importlib, "import_module", lambda name: iio)
    output = tmp_path / "probe-receipt.json"
    args = SimpleNamespace(
        plan=plan_path,
        ssh_password_file=(tmp_path.parent / f"{tmp_path.name}.password"),
        state_root=(tmp_path / "state").absolute(),
        timeout_s=45.0,
        confirm=plan["confirmation_phrase"],
        output=output,
    )
    return args, backend, iio, output


def test_execute_writes_pass_receipt_after_route_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, backend, iio, output = _execute_fixture(tmp_path, monkeypatch)

    result = execute_plan(args)

    assert result["verdict"] == "PASS_CANDIDATE_MEASUREMENT_ONLY"
    assert result["frame_lock_claim"] is False
    receipt = _load_private_json(output, label="probe receipt")
    assert receipt["outcome"] == "pass"
    assert receipt["hardware_accessed"] is True
    assert receipt["persistent_write"] is False
    assert receipt["route_release_verified"] is True
    assert receipt["recovery_required"] is True
    assert receipt["measurement"]["iio_restore_verified"] is True
    assert backend.target_revalidated is True
    assert backend.route_released is True
    assert iio.context.closed is True
    verified = verify_receipt(SimpleNamespace(plan=args.plan, receipt=output))
    assert verified["outcome"] == "pass"
    assert verified["frame_lock_claim"] is False


def test_execute_failure_is_receipted_after_restore_and_route_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, backend, iio, output = _execute_fixture(
        tmp_path, monkeypatch, bad_lock_claim=True
    )

    with pytest.raises(ProbeError, match="after writing"):
        execute_plan(args)

    receipt = _load_private_json(output, label="failed probe receipt")
    assert receipt["outcome"] == "failed"
    assert receipt["measurement"] is None
    assert receipt["route_release_verified"] is True
    assert "measurement-only contract" in receipt["error"]
    assert backend.route_released is True
    assert iio.context.phy_channel.attrs["sampling_frequency"].value == "10000000"
    assert iio.context.closed is True
    verified = verify_receipt(SimpleNamespace(plan=args.plan, receipt=output))
    assert verified["outcome"] == "failed"


def test_hardware_probe_source_manifest_is_dnm_offline_and_byte_exact() -> None:
    manifest_path = (
        REPOSITORY / "manifests/starlink-pss-hardware-probe-dnm-v1-source.yaml"
    )
    values = {
        key.strip(): value.strip().strip('"')
        for line in manifest_path.read_text().splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }
    assert values["schema"] == "plutosdr-fw.starlink-pss-hardware-probe-source"
    assert values["schema_version"] == "1"
    assert values["do_not_merge"] == "true"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    assert values["hardware_qualified"] == "false"
    assert values["allocated_radio_serial"] == ALLOCATED_SERIAL
    assert values["ppu_source_commit"] == (
        "5790a39705e9e598ef048ec773e0227cf9ac1808"
    )
    for prefix in ("probe_script", "probe_test", "controller_readme", "plan"):
        member = REPOSITORY / values[f"{prefix}_path"]
        assert member.is_file()
        assert hashlib.sha256(member.read_bytes()).hexdigest() == values[
            f"{prefix}_sha256"
        ]
