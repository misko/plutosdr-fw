"""Fail-closed single-TX libiio primitive for the cabled M3 campaign.

This module has no command-line entry point and cannot select a radio.  The M3
executor must first validate the sealed physical fixture and acquire PPU's
exact serial lock, then pass an already-open exact-USB IIO context here.
"""

from __future__ import annotations

import gc
import hashlib
import math
import os
import stat
from pathlib import Path
from typing import Any

PHY_DEVICE = "ad9361-phy"
TX_DEVICE = "cf-ad9361-dds-core-lpc"
TX_MUTE_DB = -89.75
MAXIMUM_ACTIVE_GAIN_DB = -10.0
MINIMUM_LO_HZ = 70_000_000
MAXIMUM_LO_HZ = 6_000_000_000
DAC_SELECT_DMA = 0x2
DAC_SELECT_ZERO = 0x3


def dac_selector_register(channel: int) -> int:
    return 0x0418 + channel * 0x40


def dac_legacy_control_register(channel: int) -> int:
    return 0x0414 + channel * 0x40


class TxSafetyError(RuntimeError):
    """The transmitter state could not be proven safe or exact."""


def close_iio_context(iio_module: Any, context: Any) -> str:
    """Release modern or legacy pylibiio contexts without double-destroying."""

    close = getattr(context, "close", None)
    if callable(close):
        close()
        return "explicit-close"
    native = getattr(context, "_context", None)
    destroy = getattr(iio_module, "_destroy", None)
    if native is None or not callable(destroy):
        raise TxSafetyError("pylibiio context has no deterministic close operation")
    # Clear the wrapper first so its eventual __del__ cannot double-destroy the
    # native context if the ctypes destroy call itself raises.
    context._context = None
    destroy(native)
    return "legacy-native-destroy"


def _stat_identity(state: os.stat_result) -> tuple[int, ...]:
    return (
        state.st_dev,
        state.st_ino,
        state.st_mode,
        state.st_uid,
        state.st_nlink,
        state.st_size,
        state.st_mtime_ns,
        state.st_ctime_ns,
    )


def _first_number(value: Any) -> float:
    try:
        parsed = float(str(value).strip().split()[0])
    except (IndexError, TypeError, ValueError) as error:
        raise TxSafetyError(f"numeric IIO readback is invalid: {value!r}") from error
    if not math.isfinite(parsed):
        raise TxSafetyError("numeric IIO readback is not finite")
    return parsed


class SingleTxCyclicIio:
    """Own and fail-safe one 1R1T DMA transmitter on an exact IIO context."""

    def __init__(self, iio_module: Any, context: Any, *, expected_serial: str) -> None:
        self.iio = iio_module
        self.context = context
        self.expected_serial = expected_serial
        self.phy = self._required_device(PHY_DEVICE)
        self.tx = self._required_device(TX_DEVICE)
        self.phy_tx = self._required_channel(self.phy, "voltage0", True)
        self.tx_lo = self._required_channel(self.phy, "altvoltage1", True)
        self._buffer: Any = None
        self._scan_originals: list[tuple[Any, bool]] = []
        self._configured: dict[str, Any] | None = None
        self._active: dict[str, Any] | None = None
        self._closed = False
        self._attest_identity()

    def _required_device(self, name: str) -> Any:
        device = self.context.find_device(name)
        if device is None:
            raise TxSafetyError(f"IIO context lacks required device {name!r}")
        return device

    @staticmethod
    def _required_channel(device: Any, name: str, output: bool) -> Any:
        channel = device.find_channel(name, output)
        if channel is None:
            raise TxSafetyError(f"IIO device lacks required channel {name!r}")
        return channel

    @staticmethod
    def _read_attr(owner: Any, name: str) -> str:
        attrs = getattr(owner, "attrs", {})
        if name not in attrs:
            raise TxSafetyError(f"IIO object lacks required attribute {name!r}")
        return str(attrs[name].value)

    @classmethod
    def _write_numeric(
        cls, owner: Any, name: str, value: float, *, tolerance: float
    ) -> float:
        if not math.isfinite(float(value)) or tolerance < 0:
            raise TxSafetyError(f"{name} request or tolerance is invalid")
        attrs = getattr(owner, "attrs", {})
        if name not in attrs:
            raise TxSafetyError(f"IIO object lacks required attribute {name!r}")
        attrs[name].value = str(value)
        observed = _first_number(attrs[name].value)
        if abs(observed - float(value)) > tolerance:
            raise TxSafetyError(
                f"{name} readback {observed} differs from request {value}"
            )
        return observed

    def _attest_identity(self) -> None:
        attrs = {str(key): str(value) for key, value in self.context.attrs.items()}
        serial = attrs.get(
            "hw_serial", attrs.get("usb,serial", attrs.get("serial", ""))
        )
        if serial != self.expected_serial:
            raise TxSafetyError(
                f"IIO serial {serial!r} differs from {self.expected_serial!r}"
            )
        setter = getattr(self.context, "set_timeout", None)
        if not callable(setter):
            raise TxSafetyError("IIO context cannot set a bounded timeout")
        setter(5_000)
        gain_channels = tuple(
            channel
            for channel in self.phy.channels
            if bool(getattr(channel, "output", False))
            and getattr(channel, "id", "") == "voltage0"
            and "hardwaregain" in getattr(channel, "attrs", {})
        )
        if gain_channels != (self.phy_tx,):
            raise TxSafetyError(
                "runtime is not an exact single-TX hardware-gain layout"
            )
        if "powerdown" not in getattr(self.tx_lo, "attrs", {}):
            raise TxSafetyError("TX LO lacks a powerdown control")

    def _write_selector(self, lane: int, selector: int) -> int:
        legacy_address = dac_legacy_control_register(lane)
        legacy = int(self.tx.reg_read(legacy_address))
        self.tx.reg_write(legacy_address, legacy & ~1)
        address = dac_selector_register(lane)
        self.tx.reg_write(address, selector)
        observed = int(self.tx.reg_read(address)) & 0xF
        if observed != selector:
            raise TxSafetyError(
                f"DAC lane {lane} selector readback {observed} != {selector}"
            )
        return observed

    def _mute_dds(self) -> dict[str, dict[str, float | bool]]:
        evidence: dict[str, dict[str, float | bool]] = {}
        for channel in self.tx.channels:
            identifier = str(getattr(channel, "id", ""))
            if not bool(getattr(channel, "output", False)) or not identifier.startswith(
                "altvoltage"
            ):
                continue
            attrs = getattr(channel, "attrs", {})
            values: dict[str, float | bool] = {"present": True}
            for name in ("scale", "raw"):
                if name in attrs:
                    values[name] = self._write_numeric(
                        channel, name, 0.0, tolerance=1e-9
                    )
            evidence[identifier] = values
        return evidence

    def _close_buffer(self) -> str:
        buffer = self._buffer
        self._buffer = None
        if buffer is None:
            return "not-active"
        close = getattr(buffer, "close", None)
        if callable(close):
            close()
            method = "explicit-close"
        else:
            cancel = getattr(buffer, "cancel", None)
            if callable(cancel):
                cancel()
                method = "cancel-reference-release-gc"
            else:
                method = "reference-release-gc"
        buffer = None
        gc.collect()
        return method

    def _restore_scan(self) -> None:
        errors: list[str] = []
        for channel, enabled in self._scan_originals:
            try:
                channel.enabled = enabled
            except Exception as error:  # noqa: BLE001 - restore every channel
                errors.append(f"{getattr(channel, 'id', '?')}: {error}")
        self._scan_originals.clear()
        if errors:
            raise TxSafetyError("TX scan restoration failed: " + "; ".join(errors))

    def mute(self) -> dict[str, Any]:
        """Attempt every mute barrier and prove the resulting safe state."""

        if self._closed:
            raise TxSafetyError("IIO transmitter is already closed")

        failures: list[str] = []
        evidence: dict[str, Any] = {}

        def attempt(label: str, action: Any) -> None:
            try:
                evidence[label] = action()
            except Exception as error:  # noqa: BLE001 - every barrier is attempted
                failures.append(f"{label}: {error}")

        attempt(
            "tx_hardwaregain_db",
            lambda: self._write_numeric(
                self.phy_tx, "hardwaregain", TX_MUTE_DB, tolerance=0.26
            ),
        )
        attempt("selector_i", lambda: self._write_selector(0, DAC_SELECT_ZERO))
        attempt("selector_q", lambda: self._write_selector(1, DAC_SELECT_ZERO))
        attempt("dds", self._mute_dds)
        attempt(
            "tx_lo_powerdown",
            lambda: round(
                self._write_numeric(self.tx_lo, "powerdown", 1, tolerance=1e-9)
            ),
        )
        attempt("buffer_release", self._close_buffer)
        attempt("scan_restore", lambda: (self._restore_scan(), True)[1])
        self._active = None
        evidence["verified"] = not failures
        evidence["failures"] = failures
        if failures:
            raise TxSafetyError("; ".join(failures))
        if (
            evidence["tx_hardwaregain_db"] > -80.0
            or evidence["selector_i"] != DAC_SELECT_ZERO
            or evidence["selector_q"] != DAC_SELECT_ZERO
            or evidence["tx_lo_powerdown"] != 1
            or self._buffer is not None
        ):
            raise TxSafetyError("TX mute readbacks do not prove a safe state")
        return evidence

    def configure(
        self,
        *,
        sample_rate_hz: int,
        rf_bandwidth_hz: int,
        tx_lo_hz: int,
    ) -> dict[str, Any]:
        """Configure clocks and LO while all independent TX barriers are muted."""

        if self._closed:
            raise TxSafetyError("IIO transmitter is already closed")

        if (
            isinstance(sample_rate_hz, bool)
            or not isinstance(sample_rate_hz, int)
            or sample_rate_hz <= 0
            or isinstance(rf_bandwidth_hz, bool)
            or not isinstance(rf_bandwidth_hz, int)
            or not 200_000 <= rf_bandwidth_hz <= 20_000_000
            or isinstance(tx_lo_hz, bool)
            or not isinstance(tx_lo_hz, int)
            or not MINIMUM_LO_HZ <= tx_lo_hz <= MAXIMUM_LO_HZ
        ):
            raise TxSafetyError("TX clock, bandwidth, or LO request is out of range")
        mute = self.mute()
        sample_rate = round(
            self._write_numeric(
                self.phy_tx,
                "sampling_frequency",
                sample_rate_hz,
                tolerance=max(2.0, sample_rate_hz * 100e-6),
            )
        )
        bandwidth = round(
            self._write_numeric(
                self.phy_tx, "rf_bandwidth", rf_bandwidth_hz, tolerance=2.0
            )
        )
        lo = round(
            self._write_numeric(self.tx_lo, "frequency", tx_lo_hz, tolerance=2.0)
        )
        if round(_first_number(self._read_attr(self.tx_lo, "powerdown"))) != 1:
            raise TxSafetyError("TX LO left powered while configuring the fixture")
        self._configured = {
            "sample_rate_hz": sample_rate,
            "rf_bandwidth_hz": bandwidth,
            "tx_lo_hz": lo,
            "mute_before_configuration": mute,
        }
        return dict(self._configured)

    def _enable_exact_iq_scan(self) -> list[dict[str, Any]]:
        if self._scan_originals:
            raise TxSafetyError("TX scan ownership is already active")
        expected = {"voltage0": 0, "voltage1": 1}
        found: dict[str, Any] = {}
        for channel in self.tx.channels:
            if not bool(getattr(channel, "scan_element", False)):
                continue
            self._scan_originals.append((channel, bool(channel.enabled)))
            identifier = str(channel.id)
            channel.enabled = identifier in expected
            if identifier in expected:
                if identifier in found:
                    raise TxSafetyError(f"duplicate TX scan channel {identifier!r}")
                found[identifier] = channel
        if set(found) != set(expected):
            raise TxSafetyError(f"TX scan layout differs from {sorted(expected)}")
        layout: list[dict[str, Any]] = []
        for identifier, index in expected.items():
            channel = found[identifier]
            data_format = channel.data_format
            observed = {
                "id": identifier,
                "index": int(channel.index),
                "length": int(data_format.length),
                "bits": int(data_format.bits),
                "shift": int(data_format.shift),
                "is_signed": bool(data_format.is_signed),
                "is_be": bool(data_format.is_be),
                "repeat": int(data_format.repeat),
            }
            if observed != {
                "id": identifier,
                "index": index,
                "length": 16,
                "bits": 16,
                "shift": 0,
                "is_signed": True,
                "is_be": False,
                "repeat": 1,
            }:
                raise TxSafetyError(f"TX scan format is unexpected: {observed}")
            layout.append(observed)
        if int(self.tx.sample_size) != 4:
            raise TxSafetyError(
                f"single-TX scan size is {self.tx.sample_size}, expected 4"
            )
        return layout

    def start(self, payload: bytes, *, gain_db: float) -> dict[str, Any]:
        """Start exact cyclic DMA, enabling hardware gain as the final write."""

        if self._closed:
            raise TxSafetyError("IIO transmitter is already closed")
        if self._configured is None:
            raise TxSafetyError("TX must be configured before cyclic DMA starts")
        if self._buffer is not None or self._active is not None:
            raise TxSafetyError("cyclic TX is already active")
        if (
            isinstance(gain_db, bool)
            or not isinstance(gain_db, (int, float))
            or not math.isfinite(gain_db)
            or not TX_MUTE_DB <= gain_db <= MAXIMUM_ACTIVE_GAIN_DB
        ):
            raise TxSafetyError("active TX gain is outside the cabled safety range")
        try:
            immutable = bytes(payload)
        except (TypeError, ValueError) as error:
            raise TxSafetyError("cyclic TX payload is not bytes-like") from error
        if not immutable or len(immutable) % 4:
            raise TxSafetyError("cyclic TX payload is not complete CI16 IQ")
        sample_count = len(immutable) // 4
        try:
            if self.mute()["verified"] is not True:
                raise TxSafetyError("TX was not muted before cyclic setup")
            scan_layout = self._enable_exact_iq_scan()
            set_kernel_buffers = getattr(self.tx, "set_kernel_buffers_count", None)
            if callable(set_kernel_buffers):
                set_kernel_buffers(1)
            buffer = self.iio.Buffer(self.tx, sample_count, True)
            self._buffer = buffer
            if len(buffer) != len(immutable):
                raise TxSafetyError(
                    f"cyclic buffer has {len(buffer)} bytes, expected {len(immutable)}"
                )
            written = int(buffer.write(bytearray(immutable)))
            if written != len(immutable):
                raise TxSafetyError(
                    f"cyclic write accepted {written} bytes, expected {len(immutable)}"
                )
            read = getattr(buffer, "read", None)
            if not callable(read) or bytes(read()) != immutable:
                raise TxSafetyError("cyclic buffer payload readback differs")
            buffer.push()
            selectors = (
                self._write_selector(0, DAC_SELECT_DMA),
                self._write_selector(1, DAC_SELECT_DMA),
            )
            lo_powerdown = round(
                self._write_numeric(self.tx_lo, "powerdown", 0, tolerance=1e-9)
            )
            gain = self._write_numeric(
                self.phy_tx, "hardwaregain", gain_db, tolerance=0.26
            )
            self._active = {
                "sample_count": sample_count,
                "payload_bytes": len(immutable),
                "payload_sha256": hashlib.sha256(immutable).hexdigest(),
                "cyclic": True,
                "scan_layout": scan_layout,
                "buffer_readback_verified": True,
                "selectors": selectors,
                "tx_lo_powerdown": lo_powerdown,
                "tx_hardwaregain_db": gain,
                "configuration": self._configured,
            }
            return dict(self._active)
        except BaseException as body_error:
            try:
                self.mute()
            except Exception as cleanup_error:  # noqa: BLE001 - preserve cleanup
                raise TxSafetyError(
                    "cyclic TX setup failed and fail-safe mute also failed: "
                    f"setup={body_error}; mute={cleanup_error}"
                ) from body_error
            raise

    @property
    def active(self) -> bool:
        return self._active is not None and self._buffer is not None

    def close(self) -> dict[str, Any]:
        if self._closed:
            raise TxSafetyError("IIO transmitter was already closed")
        mute_error: BaseException | None = None
        evidence: dict[str, Any] = {}
        try:
            evidence = self.mute()
        except BaseException as error:  # noqa: BLE001 - context must still close
            mute_error = error
        try:
            method = close_iio_context(self.iio, self.context)
            self._closed = True
        except BaseException as close_error:
            if mute_error is not None:
                raise TxSafetyError(
                    f"final mute failed ({mute_error}); context close failed ({close_error})"
                ) from mute_error
            raise
        if mute_error is not None:
            raise TxSafetyError(
                f"final mute failed before context close ({mute_error})"
            ) from mute_error
        evidence["context_release"] = method
        return evidence


def load_exact_payload(
    path: Path, *, expected_bytes: int, expected_sha256: str
) -> bytes:
    """Load one mode-0600 waveform and verify its exact byte identity."""

    selected = path.absolute()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        before = selected.lstat()
        descriptor = os.open(selected, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_size != expected_bytes
            or _stat_identity(opened) != _stat_identity(before)
        ):
            raise TxSafetyError("TX waveform is not one exact mode-0600 regular file")
        chunks: list[bytes] = []
        remaining = expected_bytes
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1 << 20))
            if not chunk:
                raise TxSafetyError("TX waveform was truncated while reading")
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if (
            os.read(descriptor, 1)
            or _stat_identity(os.fstat(descriptor)) != _stat_identity(opened)
            or hashlib.sha256(payload).hexdigest() != expected_sha256
        ):
            raise TxSafetyError(
                "TX waveform changed or differs from its sealed identity"
            )
        return payload
    except OSError as error:
        raise TxSafetyError(f"TX waveform cannot be opened safely: {error}") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
