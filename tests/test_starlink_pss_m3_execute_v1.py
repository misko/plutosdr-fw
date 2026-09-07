from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import scripts.starlink_pss_m3_campaign_v1 as campaign
import scripts.starlink_pss_m3_execute_v1 as executor
from scripts.starlink_pss_m3_iio_tx_v1 import DAC_SELECT_ZERO, dac_selector_register
from tests.test_starlink_pss_m3_campaign_v1 import (
    _fixture,
    _monitor_plan,
    _monitor_receipt,
    _records,
)
from tests.test_starlink_pss_m3_iio_tx_v1 import FakeIio
from tests.test_starlink_pss_m3_iio_tx_v1 import _fixture as iio_fixture
from tools.generate_starlink_pss15_cabled_waveform import generate

TRANSMITTER_SERIAL = "test-transmitter-0001"
TRANSMITTER_TOPOLOGY = "3-11"
PPU_COMMIT = "7" * 40


def _campaign(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    waveform_directory = tmp_path / "waveform"
    generate(waveform_directory)
    fixture_path = tmp_path / "fixture.json"
    campaign.probe_v1._write_new_private(fixture_path, _fixture())
    roles = ("positive-a", "negative", "positive-b")
    monitor_paths = {role: tmp_path / f"{role}-monitor-plan.json" for role in roles}
    monitor_receipts = {
        role: tmp_path / f"{role}-monitor-receipt.json" for role in roles
    }
    stimulus_receipts = {role: tmp_path / f"{role}-stimulus.json" for role in roles}
    for index, role in enumerate(roles, 1):
        _monitor_plan(monitor_paths[role], monitor_receipts[role], f"{index}" * 32)
    plan_path = tmp_path / "campaign-plan.json"
    campaign.build_plan(
        SimpleNamespace(
            waveform_evidence=waveform_directory
            / "starlink_pss15_upper_cabled_waveform.json",
            fixture_declaration=fixture_path,
            transmitter_sample_rate_hz=campaign.SAMPLE_RATE_HZ,
            transmitter_lo_hz=1_000_000_000,
            transmitter_hardwaregain_db=-30.0,
            positive_a_monitor_plan=monitor_paths["positive-a"],
            negative_monitor_plan=monitor_paths["negative"],
            positive_b_monitor_plan=monitor_paths["positive-b"],
            positive_a_stimulus_receipt=stimulus_receipts["positive-a"],
            negative_stimulus_receipt=stimulus_receipts["negative"],
            positive_b_stimulus_receipt=stimulus_receipts["positive-b"],
            final_mute_stimulus_receipt=tmp_path / "final-mute.json",
            receipt=tmp_path / "campaign-receipt.json",
            output=plan_path,
        )
    )
    return plan_path, campaign._load(plan_path, label="test campaign plan")


def _execution_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, dict[str, Any]]:
    campaign_path, _base = _campaign(tmp_path)
    repository = tmp_path / "ppu"
    repository.mkdir()
    monkeypatch.setattr(
        executor.probe_v1,
        "_verify_ppu_repository",
        lambda selected, commit: selected,
    )
    monkeypatch.setattr(executor, "_git_source", lambda selected: (PPU_COMMIT, ""))
    monkeypatch.setattr(executor, "ALLOCATED_TRANSMITTER_SERIAL", TRANSMITTER_SERIAL)
    monkeypatch.setattr(
        executor, "ALLOCATED_TRANSMITTER_TOPOLOGY", TRANSMITTER_TOPOLOGY
    )
    monkeypatch.setattr(
        executor,
        "ALLOCATED_TRANSMITTER_NETWORK_INTERFACE",
        "enx001122334455",
    )
    plan_path = tmp_path / "execution-plan.json"
    receipt_path = tmp_path / "execution-receipt.json"
    result = executor.build_plan(
        SimpleNamespace(
            campaign_plan=campaign_path,
            transmitter_topology=TRANSMITTER_TOPOLOGY,
            ppu_repository=repository,
            ppu_commit=PPU_COMMIT,
            receipt=receipt_path,
            output=plan_path,
        )
    )
    assert result["verdict"] == "PASS_OFFLINE_M3_EXECUTION_PLAN_ONLY"
    return (
        plan_path,
        receipt_path,
        executor._load(plan_path, label="test execution plan"),
    )


def _inventory(*, topology: str = TRANSMITTER_TOPOLOGY, plus: bool = True) -> Any:
    return SimpleNamespace(
        serial=TRANSMITTER_SERIAL,
        usb_path=f"/sys/bus/usb/devices/{topology}",
        bus_number=3,
        device_number=14,
        product="PlutoSDR+" if plus else "PlutoSDR",
        confirmed_plus=plus,
        host_network_interfaces=(SimpleNamespace(name="enx001122334455"),),
    )


class ExecutorIio:
    def __init__(self) -> None:
        driver, context, tx, events, buffers = iio_fixture(serial=TRANSMITTER_SERIAL)
        del driver
        self.context = context
        self.tx = tx
        self.events = events
        self.buffers: FakeIio = buffers
        self.uris: list[str] = []

    def Context(self, uri: str) -> Any:
        self.uris.append(uri)
        return self.context

    def Buffer(self, device: Any, samples: int, cyclic: bool) -> Any:
        return self.buffers.Buffer(device, samples, cyclic)


def _execute_args(plan_path: Path, receipt_path: Path, plan: dict[str, Any]) -> Any:
    return SimpleNamespace(
        plan=plan_path,
        ssh_password_file=plan_path.parent / "unused-password",
        receiver_state_root=plan_path.parent / "receiver-state",
        receiver_timeout_s=30.0,
        confirm=plan["confirmation_phrase"],
        output=receipt_path,
    )


def _fake_monitor(arguments: Any) -> dict[str, Any]:
    name = arguments.plan.name
    positive = "negative" not in name
    _monitor_receipt(
        plan_path=arguments.plan,
        receipt_path=arguments.output,
        records=_records(positive=positive),
        started_at=executor._now(),
        completed_at=executor._now(),
    )
    return {"verdict": "PASS_FAKE_MONITOR"}


@contextmanager
def _uncontended_lock(serial: str) -> Iterator[None]:
    assert serial == TRANSMITTER_SERIAL
    yield


def test_execution_plan_binds_exact_radios_fixture_and_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path, receipt_path, plan = _execution_plan(tmp_path, monkeypatch)

    assert plan["receiver_serial"] == campaign.RECEIVER_SERIAL
    assert plan["transmitter_serial"] == TRANSMITTER_SERIAL
    assert plan["transmitter_topology"] == TRANSMITTER_TOPOLOGY
    assert plan["transmitter_network_interface"] == "enx001122334455"
    assert plan["execution_receipt_path"] == str(receipt_path)
    assert plan["confirmation_phrase"] == (
        "EXECUTE CABLED PSS M3 TX test-transmitter-0001 AT 3-11 TO RX "
        f"{campaign.RECEIVER_SERIAL} WITH 40 DB AT 1000000000 HZ"
    )
    executor._validate_plan(plan)
    assert plan_path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    ("devices", "message"),
    (
        ((_inventory(), _inventory()), "uniquely"),
        ((_inventory(topology="3-12"),), "uniquely"),
        ((_inventory(plus=False),), "usable PlutoSDR"),
    ),
)
def test_exact_transmitter_resolution_rejects_ambiguity_or_wrong_hardware(
    devices: tuple[Any, ...], message: str
) -> None:
    with pytest.raises(executor.ProbeError, match=message):
        executor._resolve_transmitter(
            devices,
            serial=TRANSMITTER_SERIAL,
            topology=TRANSMITTER_TOPOLOGY,
            network_interface="enx001122334455",
        )


def test_usb_opener_detection_is_scoped_to_exact_bus_device(tmp_path: Path) -> None:
    own = tmp_path / str(os.getpid()) / "fd"
    other = tmp_path / "4242" / "fd"
    unrelated = tmp_path / "4243" / "fd"
    own.mkdir(parents=True)
    other.mkdir(parents=True)
    unrelated.mkdir(parents=True)
    (own / "1").symlink_to("/dev/bus/usb/003/014")
    (other / "7").symlink_to("/dev/bus/usb/003/014")
    (unrelated / "8").symlink_to("/dev/bus/usb/003/015")

    assert executor._usb_openers(3, 14, proc_root=tmp_path) == [4242]


def test_fake_full_execution_mutes_between_dwells_and_verifies_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path, receipt_path, plan = _execution_plan(tmp_path, monkeypatch)
    iio = ExecutorIio()
    lock_events: list[str] = []
    scans = 0

    def scanner() -> tuple[Any, ...]:
        nonlocal scans
        scans += 1
        return (_inventory(),)

    @contextmanager
    def lock_factory(serial: str) -> Iterator[None]:
        assert serial == TRANSMITTER_SERIAL
        lock_events.append("enter")
        try:
            yield
        finally:
            lock_events.append("exit")

    result = executor.execute_plan(
        _execute_args(plan_path, receipt_path, plan),
        scanner=scanner,
        lock_factory=lock_factory,
        iio_module=iio,
        monitor_execute=_fake_monitor,
        opener_checker=lambda bus, device: [],
    )

    assert result["verdict"] == "PASS_M3_CABLED_TRANSPORT_ONLY"
    assert scans == 2
    assert lock_events == ["enter", "exit"]
    assert iio.uris == ["usb:3.14.5"]
    assert iio.context.closed
    assert iio.tx.reg_read(dac_selector_register(0)) == DAC_SELECT_ZERO
    assert iio.tx.reg_read(dac_selector_register(1)) == DAC_SELECT_ZERO
    assert iio.events[-1] == ("lo-powerdown", "1")

    verified = executor.verify_receipt(
        SimpleNamespace(plan=plan_path, receipt=receipt_path)
    )
    assert verified["verdict"] == "PASS_M3_EXECUTION_RECEIPT_STRUCTURE"
    receipt = executor._load(receipt_path, label="test execution receipt")
    assert receipt["outcome"] == "pass"
    assert receipt["context_close_method"] == "explicit-close"
    assert [item["state"] for item in receipt["actions"]] == [
        "active",
        "muted",
        "active",
        "muted",
    ]


def test_monitor_failure_still_mutes_closes_and_seals_failed_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path, receipt_path, plan = _execution_plan(tmp_path, monkeypatch)
    iio = ExecutorIio()

    def fail_monitor(arguments: Any) -> None:
        raise RuntimeError(f"injected monitor failure for {arguments.plan.name}")

    with pytest.raises(executor.ProbeError, match="injected monitor failure"):
        executor.execute_plan(
            _execute_args(plan_path, receipt_path, plan),
            scanner=lambda: (_inventory(),),
            lock_factory=_uncontended_lock,
            iio_module=iio,
            monitor_execute=fail_monitor,
            opener_checker=lambda bus, device: [],
        )

    receipt = executor._load(receipt_path, label="failed execution receipt")
    assert receipt["outcome"] == "failed"
    assert receipt["transmitter_cleanup_verified"] is True
    assert receipt["context_close_verified"] is True
    assert receipt["receiver_recovery_required"] is True
    assert "injected monitor failure" in receipt["error"]
    assert iio.context.closed
    assert iio.tx.reg_read(dac_selector_register(0)) == DAC_SELECT_ZERO
    assert iio.tx.reg_read(dac_selector_register(1)) == DAC_SELECT_ZERO


def test_wrong_confirmation_fails_before_inventory_or_iio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path, receipt_path, plan = _execution_plan(tmp_path, monkeypatch)
    scans = 0

    def scanner() -> tuple[Any, ...]:
        nonlocal scans
        scans += 1
        return (_inventory(),)

    arguments = _execute_args(plan_path, receipt_path, plan)
    arguments.confirm = "yes"
    with pytest.raises(executor.ProbeError, match="confirmation must be exactly"):
        executor.execute_plan(
            arguments,
            scanner=scanner,
            lock_factory=_uncontended_lock,
            iio_module=object(),
            monitor_execute=_fake_monitor,
        )
    assert scans == 0
    assert not receipt_path.exists()


def test_existing_usb_opener_prevents_iio_context_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path, receipt_path, plan = _execution_plan(tmp_path, monkeypatch)
    iio = ExecutorIio()

    with pytest.raises(executor.ProbeError, match="already open by PIDs"):
        executor.execute_plan(
            _execute_args(plan_path, receipt_path, plan),
            scanner=lambda: (_inventory(),),
            lock_factory=_uncontended_lock,
            iio_module=iio,
            monitor_execute=_fake_monitor,
            opener_checker=lambda bus, device: [4242],
        )

    assert iio.uris == []
    receipt = executor._load(receipt_path, label="USB-owner rejection receipt")
    assert receipt["outcome"] == "failed"
    assert receipt["iio_uri"] is None
    assert receipt["hardware_accessed"] is True


def test_ppu_hardware_import_rejects_module_outside_attested_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = SimpleNamespace(__file__="/tmp/not-the-attested-ppu/module.py")
    monkeypatch.setattr(executor.importlib, "import_module", lambda name: outside)

    with pytest.raises(executor.ProbeError, match="outside the attested checkout"):
        executor._import_ppu_hardware(tmp_path)


def test_m3_execution_orchestrator_is_executable() -> None:
    assert Path(executor.__file__).stat().st_mode & 0o111


def test_m3_executor_is_compiled_for_the_one_reserved_spare() -> None:
    assert executor.ALLOCATED_TRANSMITTER_SERIAL == (
        "1040007c4a94000211000b009186843ef2"
    )
    assert executor.ALLOCATED_TRANSMITTER_TOPOLOGY == "3-11"
    assert executor.ALLOCATED_TRANSMITTER_NETWORK_INTERFACE == "enx00e02297811f"
