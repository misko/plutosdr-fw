from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.starlink_pss_m3_iio_tx_v1 import (
    DAC_SELECT_DMA,
    DAC_SELECT_ZERO,
    TX_MUTE_DB,
    SingleTxCyclicIio,
    TxSafetyError,
    close_iio_context,
    dac_selector_register,
    load_exact_payload,
)


class FakeAttr:
    def __init__(
        self, label: str, value: object, events: list[tuple[str, str]]
    ) -> None:
        self.label = label
        self._value = str(value)
        self.events = events

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, value: object) -> None:
        self._value = str(value)
        self.events.append((self.label, self._value))


class FakeFormat:
    length = 16
    bits = 16
    shift = 0
    is_signed = True
    is_be = False
    repeat = 1


class FakeChannel:
    def __init__(
        self,
        identifier: str,
        *,
        output: bool,
        index: int = 0,
        scan_element: bool = False,
        enabled: bool = False,
        attrs: dict[str, FakeAttr] | None = None,
    ) -> None:
        self.id = identifier
        self.output = output
        self.index = index
        self.scan_element = scan_element
        self.enabled = enabled
        self.attrs = attrs or {}
        self.data_format = FakeFormat()


class FakeDevice:
    def __init__(self, channels: list[FakeChannel]) -> None:
        self.channels = channels
        self.registers: dict[int, int] = {}
        self.kernel_buffers: int | None = None

    def find_channel(self, name: str, output: bool) -> FakeChannel | None:
        return next(
            (
                channel
                for channel in self.channels
                if channel.id == name and channel.output is output
            ),
            None,
        )

    def reg_read(self, address: int) -> int:
        return self.registers.get(address, 0)

    def reg_write(self, address: int, value: int) -> None:
        self.registers[address] = value

    @property
    def sample_size(self) -> int:
        return sum(
            2 for channel in self.channels if channel.scan_element and channel.enabled
        )

    def set_kernel_buffers_count(self, count: int) -> None:
        self.kernel_buffers = count


class FakeContext:
    def __init__(self, serial: str, phy: FakeDevice, tx: FakeDevice) -> None:
        self.attrs = {"hw_serial": serial}
        self.devices = {
            "ad9361-phy": phy,
            "cf-ad9361-dds-core-lpc": tx,
        }
        self.timeout_ms: int | None = None
        self.closed = False

    def find_device(self, name: str) -> FakeDevice | None:
        return self.devices.get(name)

    def set_timeout(self, timeout_ms: int) -> None:
        self.timeout_ms = timeout_ms

    def close(self) -> None:
        self.closed = True


class FakeBuffer:
    def __init__(
        self, device: FakeDevice, samples: int, cyclic: bool, *, fail_push: bool
    ) -> None:
        assert device.sample_size == 4
        assert cyclic is True
        self.payload = bytes(samples * device.sample_size)
        self.closed = False
        self.pushed = False
        self.fail_push = fail_push

    def __len__(self) -> int:
        return len(self.payload)

    def write(self, payload: bytearray) -> int:
        self.payload = bytes(payload)
        return len(payload)

    def read(self) -> bytes:
        return self.payload

    def push(self) -> None:
        if self.fail_push:
            raise OSError("injected push failure")
        self.pushed = True

    def close(self) -> None:
        self.closed = True


class FakeLegacyBuffer(FakeBuffer):
    close = None

    def cancel(self) -> None:
        self.closed = True


class FakeIio:
    def __init__(self, *, fail_push: bool = False, legacy_buffer: bool = False) -> None:
        self.fail_push = fail_push
        self.legacy_buffer = legacy_buffer
        self.buffers: list[FakeBuffer] = []

    def Buffer(self, device: FakeDevice, samples: int, cyclic: bool) -> FakeBuffer:
        buffer_type = FakeLegacyBuffer if self.legacy_buffer else FakeBuffer
        buffer = buffer_type(device, samples, cyclic, fail_push=self.fail_push)
        self.buffers.append(buffer)
        return buffer


class FakeLegacyContext(FakeContext):
    close = None

    def __init__(self, serial: str, phy: FakeDevice, tx: FakeDevice) -> None:
        super().__init__(serial, phy, tx)
        self._context = object()


class FakeLegacyIio(FakeIio):
    def __init__(self) -> None:
        super().__init__()
        self.destroyed: list[object] = []

    def _destroy(self, native: object) -> None:
        self.destroyed.append(native)


def _fixture(
    *,
    serial: str = "test-transmitter-0001",
    fail_push: bool = False,
    legacy_buffer: bool = False,
) -> tuple[SingleTxCyclicIio, FakeContext, FakeDevice, list[tuple[str, str]], FakeIio]:
    events: list[tuple[str, str]] = []
    phy_tx = FakeChannel(
        "voltage0",
        output=True,
        attrs={
            "hardwaregain": FakeAttr("gain", -10, events),
            "sampling_frequency": FakeAttr("sample-rate", 30_720_000, events),
            "rf_bandwidth": FakeAttr("bandwidth", 18_000_000, events),
        },
    )
    tx_lo = FakeChannel(
        "altvoltage1",
        output=True,
        attrs={
            "frequency": FakeAttr("lo-frequency", 2_400_000_000, events),
            "powerdown": FakeAttr("lo-powerdown", 0, events),
        },
    )
    phy = FakeDevice([phy_tx, tx_lo])
    tx_i = FakeChannel(
        "voltage0", output=True, index=0, scan_element=True, enabled=False
    )
    tx_q = FakeChannel(
        "voltage1", output=True, index=1, scan_element=True, enabled=False
    )
    dds = FakeChannel(
        "altvoltage0",
        output=True,
        attrs={
            "scale": FakeAttr("dds-scale", 1, events),
            "raw": FakeAttr("dds-raw", 1, events),
        },
    )
    tx = FakeDevice([tx_i, tx_q, dds])
    context = FakeContext(serial, phy, tx)
    iio = FakeIio(fail_push=fail_push, legacy_buffer=legacy_buffer)
    driver = SingleTxCyclicIio(iio, context, expected_serial=serial)
    return driver, context, tx, events, iio


def test_cyclic_tx_enables_gain_last_and_mutes_every_barrier() -> None:
    driver, context, tx, events, iio = _fixture()
    configured = driver.configure(
        sample_rate_hz=15_000_000,
        rf_bandwidth_hz=15_000_000,
        tx_lo_hz=1_000_000_000,
    )
    payload = bytes(range(100)) * 800
    active = driver.start(payload, gain_db=-30.0)

    assert context.timeout_ms == 5_000
    assert configured["sample_rate_hz"] == 15_000_000
    assert active["payload_sha256"] == hashlib.sha256(payload).hexdigest()
    assert active["selectors"] == (DAC_SELECT_DMA, DAC_SELECT_DMA)
    assert active["tx_lo_powerdown"] == 0
    assert active["tx_hardwaregain_db"] == -30.0
    assert driver.active
    assert tx.kernel_buffers == 1
    assert iio.buffers[-1].pushed
    assert events[-2:] == [("lo-powerdown", "0"), ("gain", "-30.0")]

    muted = driver.mute()
    assert muted["verified"] is True
    assert muted["tx_hardwaregain_db"] == TX_MUTE_DB
    assert muted["tx_lo_powerdown"] == 1
    assert tx.reg_read(dac_selector_register(0)) == DAC_SELECT_ZERO
    assert tx.reg_read(dac_selector_register(1)) == DAC_SELECT_ZERO
    assert iio.buffers[-1].closed
    assert not driver.active
    assert all(not channel.enabled for channel in tx.channels if channel.scan_element)

    closed = driver.close()
    assert closed["verified"] is True
    assert context.closed


def test_failed_buffer_push_runs_unconditional_mute_cleanup() -> None:
    driver, _context, tx, events, iio = _fixture(fail_push=True)
    driver.configure(
        sample_rate_hz=15_000_000,
        rf_bandwidth_hz=15_000_000,
        tx_lo_hz=1_000_000_000,
    )

    with pytest.raises(OSError, match="push failure"):
        driver.start(bytes(80_000), gain_db=-30.0)

    assert not driver.active
    assert iio.buffers[-1].closed
    assert tx.reg_read(dac_selector_register(0)) == DAC_SELECT_ZERO
    assert tx.reg_read(dac_selector_register(1)) == DAC_SELECT_ZERO
    assert events[-2] == ("dds-raw", "0.0")
    assert events[-1] == ("lo-powerdown", "1")


def test_installed_libiio_cancel_fallback_is_synchronously_invoked() -> None:
    driver, _context, _tx, _events, iio = _fixture(legacy_buffer=True)
    driver.configure(
        sample_rate_hz=15_000_000,
        rf_bandwidth_hz=15_000_000,
        tx_lo_hz=1_000_000_000,
    )
    driver.start(bytes(80_000), gain_db=-30.0)

    muted = driver.mute()

    assert muted["buffer_release"] == "cancel-reference-release-gc"
    assert iio.buffers[-1].closed


def test_legacy_libiio_context_is_destroyed_once_and_wrapper_is_cleared() -> None:
    driver, context, _tx, _events, _iio = _fixture()
    legacy_context = FakeLegacyContext(
        driver.expected_serial,
        context.devices["ad9361-phy"],
        context.devices["cf-ad9361-dds-core-lpc"],
    )
    legacy_iio = FakeLegacyIio()
    native = legacy_context._context

    assert close_iio_context(legacy_iio, legacy_context) == "legacy-native-destroy"
    assert legacy_context._context is None
    assert legacy_iio.destroyed == [native]


def test_wrong_serial_is_rejected_before_any_write() -> None:
    driver, context, _tx, events, iio = _fixture()
    assert driver.expected_serial == "test-transmitter-0001"
    with pytest.raises(TxSafetyError, match="differs"):
        SingleTxCyclicIio(iio, context, expected_serial="some-other-radio")
    assert events == []


def test_unexpected_scan_format_fails_closed() -> None:
    driver, _context, tx, _events, iio = _fixture()
    tx.find_channel("voltage1", True).data_format.bits = 12  # type: ignore[union-attr]
    driver.configure(
        sample_rate_hz=15_000_000,
        rf_bandwidth_hz=15_000_000,
        tx_lo_hz=1_000_000_000,
    )

    with pytest.raises(TxSafetyError, match="scan format"):
        driver.start(bytes(80_000), gain_db=-30.0)

    assert not driver.active
    assert not iio.buffers
    assert tx.reg_read(dac_selector_register(0)) == DAC_SELECT_ZERO
    assert tx.reg_read(dac_selector_register(1)) == DAC_SELECT_ZERO


def test_exact_payload_loader_rejects_mode_or_digest_changes(tmp_path: Path) -> None:
    path = tmp_path / "waveform.bin"
    payload = b"\x00\x01\x02\x03" * 20_000
    path.write_bytes(payload)
    path.chmod(0o600)
    digest = hashlib.sha256(payload).hexdigest()

    assert (
        load_exact_payload(path, expected_bytes=len(payload), expected_sha256=digest)
        == payload
    )
    path.chmod(0o644)
    with pytest.raises(TxSafetyError, match="mode-0600"):
        load_exact_payload(path, expected_bytes=len(payload), expected_sha256=digest)


def test_iio_tx_source_has_no_standalone_hardware_entrypoint() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "scripts/starlink_pss_m3_iio_tx_v1.py"
    )
    text = source.read_text(encoding="utf-8")
    assert "if __name__ ==" not in text
    assert "argparse" not in text
