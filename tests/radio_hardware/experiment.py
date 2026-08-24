"""Guarded TX2 fixture and bounded issue-46 refill experiment."""

from __future__ import annotations

import errno
import fcntl
import gc
import hashlib
import json
import math
import os
import random
import re
import time
from builtins import BaseExceptionGroup
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

from .continuity import (
    BoundaryVerdict,
    agree_dual_rx,
    counter_transition,
    evaluate_boundary,
    pn_transition,
)
from .metadata_abi import (
    FrameMetadata,
    build_hold_request,
    close_iio_object,
    create_metadata_buffer,
    parse_frame_metadata,
)
from .pnxx import (
    P15_SAMPLE_PERIOD,
    PnPhaseEstimate,
    analyze_tone,
    estimate_p15_phase,
)

RX_DEVICE = "cf-ad9361-lpc"
TX_DEVICE = "cf-ad9361-dds-core-lpc"
PHY_DEVICE = "ad9361-phy"

TX_MUTE_DB = -89.75
DAC_SYNC_REGISTER = 0x0044
DAC_SELECT_DDS = 0x0
DAC_SELECT_DMA = 0x2
DAC_SELECT_ZERO = 0x3
DAC_SELECT_PNXX = 0x9
MIN_COMMON_CENTER_FREQUENCY_HZ = 70_000_000
MAX_COMMON_CENTER_FREQUENCY_HZ = 6_000_000_000


def DAC_SELECTOR_REGISTER(channel: int) -> int:
    return 0x0418 + channel * 0x40


def DAC_LEGACY_CONTROL_REGISTER(channel: int) -> int:
    return 0x0414 + channel * 0x40


class FixtureSafetyError(RuntimeError):
    """The physical fixture or its fail-safe state was not proven."""


class EvidenceInvalid(RuntimeError):
    """A run completed without evidence strong enough for RED or GREEN."""


@dataclass(frozen=True)
class Issue46Options:
    serial: str
    uri: Optional[str]
    allow_non_usb: bool
    firmware_pattern: str
    libiio_source_commit: str
    attenuation_db: float
    tx_gain_db: float
    sample_rate_hz: int
    samples_per_channel: int
    profile: str
    sink: str
    expected: str
    output_dir: Path
    max_seconds: float
    save_iq: bool
    pn_min_coherence: float
    pn_min_peak_ratio: float
    seed: int = 46
    lock_namespace: str = "issue46"
    center_frequency_hz: int = 915_000_000

    @property
    def refill_period_seconds(self) -> float:
        return self.samples_per_channel / self.sample_rate_hz


@dataclass(frozen=True)
class CellPlan:
    api: str
    kernel_buffers: int
    pause_factor: float
    repeat: int
    sink: str

    @property
    def key(self) -> str:
        pause = str(self.pause_factor).replace(".", "p")
        return f"{self.api}-k{self.kernel_buffers}-p{pause}-r{self.repeat}-{self.sink}"


@dataclass(frozen=True)
class CaptureFrame:
    ordinal: int
    sha256: str
    bytes: int
    refill_monotonic_ns: int
    rx0_pn: PnPhaseEstimate
    rx1_pn: PnPhaseEstimate
    metadata: Optional[FrameMetadata]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        return result


def _first_number(value: Any) -> float:
    return float(str(value).strip().split()[0])


def _exception_text(error: BaseException) -> str:
    number = getattr(error, "errno", None)
    suffix = f" errno={number}" if number is not None else ""
    return f"{type(error).__name__}{suffix}: {error}"


def _radio_lock_path(serial: str) -> Path:
    """Return the one process lock shared by every suite for this radio."""

    safe_serial = re.sub(r"[^A-Za-z0-9_.-]", "_", serial)
    return Path(f"/tmp/plutosdr-fw-radio-{safe_serial}.lock")


def resolve_radio_uri(iio_module: Any, serial: str, explicit_uri: Optional[str]) -> str:
    """Resolve dynamic USB bus/device coordinates by immutable radio serial."""

    if explicit_uri:
        return explicit_uri
    contexts = iio_module.scan_contexts()
    matches = [
        uri
        for uri, description in contexts.items()
        if uri.startswith("usb:") and serial in str(description)
    ]
    if len(matches) != 1:
        raise FixtureSafetyError(
            "expected exactly one USB IIO context for serial "
            f"{serial!r}; found {matches}"
        )
    return matches[0]


class Issue46Radio:
    """One locked radio whose cleanup always leaves both transmitters muted."""

    def __init__(self, iio_module: Any, options: Issue46Options):
        self.iio = iio_module
        self.options = options
        self.uri = resolve_radio_uri(iio_module, options.serial, options.uri)
        if not self.uri.startswith("usb:") and not options.allow_non_usb:
            raise FixtureSafetyError(
                "issue-46 hardware defaults to local USB; pass --allow-non-usb "
                "only for an intentional transport comparison"
            )
        safe_namespace = re.sub(r"[^A-Za-z0-9_.-]", "_", options.lock_namespace)
        self._lock_path = _radio_lock_path(options.serial)
        self._lock = self._lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._lock.seek(0)
            holder = self._lock.read().strip() or "holder details unavailable"
            self._lock.close()
            raise FixtureSafetyError(
                f"another process holds the radio lock for {options.serial}: {holder}"
            ) from exc
        self._lock.seek(0)
        self._lock.truncate()
        self._lock.write(f"pid={os.getpid()} suite={safe_namespace} uri={self.uri}\n")
        self._lock.flush()

        self.context: Any = None
        self.phy: Any = None
        self.rx: Any = None
        self.tx: Any = None
        self.identity: dict[str, Any] = {}
        self.initial_registers: dict[str, int] = {}
        self.tone_qualification: Optional[dict[str, Any]] = None
        self.cleanup_verified = False
        self._last_mute_evidence: Optional[dict[str, Any]] = None
        self._report_path: Optional[Path] = None
        self._pnxx_armed = False
        self._pnxx_sync_count = 0
        try:
            self._open_and_attest()
            self._mute_everything()
            self._configure_fixed_radio()
        except BaseException:
            try:
                self.close()
            except BaseException:
                pass
            raise

    def _open_and_attest(self) -> None:
        self.context = self.iio.Context(self.uri)
        set_timeout = getattr(self.context, "set_timeout", None)
        if not callable(set_timeout):
            raise FixtureSafetyError("selected libiio context cannot install a timeout")
        set_timeout(5_000)
        self.phy = self.context.find_device(PHY_DEVICE)
        self.rx = self.context.find_device(RX_DEVICE)
        self.tx = self.context.find_device(TX_DEVICE)
        if any(device is None for device in (self.phy, self.rx, self.tx)):
            raise FixtureSafetyError(
                "radio lacks the required AD9361 PHY/RX/TX devices"
            )

        attrs = {str(key): str(value) for key, value in self.context.attrs.items()}
        observed_serial = attrs.get("hw_serial", attrs.get("serial", ""))
        if observed_serial != self.options.serial:
            raise FixtureSafetyError(
                f"opened serial {observed_serial!r}, expected {self.options.serial!r}"
            )
        firmware = attrs.get("fw_version", "")
        if re.search(self.options.firmware_pattern, firmware) is None:
            raise FixtureSafetyError(
                f"radio fw_version {firmware!r} does not match "
                f"{self.options.firmware_pattern!r}"
            )
        if re.fullmatch(r"[0-9a-f]{40}", self.options.libiio_source_commit) is None:
            raise FixtureSafetyError(
                "host libiio source commit was not attested by the runner"
            )
        if getattr(self.iio, "MetadataBuffer", None) is None:
            raise FixtureSafetyError("host libiio binding lacks MetadataBuffer")

        self.identity = {
            "serial": observed_serial,
            "uri": self.uri,
            "context_name": str(self.context.name),
            "context_description": str(self.context.description),
            "context_version": list(self.context.version),
            "context_attrs": attrs,
            "pylibiio_file": str(getattr(self.iio, "__file__", "")),
            "libiio_source_commit": self.options.libiio_source_commit,
        }
        for channel in range(4):
            self.initial_registers[f"selector_{channel}"] = int(
                self.tx.reg_read(DAC_SELECTOR_REGISTER(channel))
            )
            self.initial_registers[f"legacy_{channel}"] = int(
                self.tx.reg_read(DAC_LEGACY_CONTROL_REGISTER(channel))
            )

    def _channel(self, device: Any, name: str, output: bool) -> Any:
        channel = device.find_channel(name, output)
        if channel is None:
            raise FixtureSafetyError(
                f"{device.id} lacks channel {name!r}, output={output}"
            )
        return channel

    @staticmethod
    def _read_attr(owner: Any, name: str) -> str:
        if name not in owner.attrs:
            raise FixtureSafetyError(f"{getattr(owner, 'id', owner)!r} lacks {name}")
        return str(owner.attrs[name].value)

    @classmethod
    def _write_attr(cls, owner: Any, name: str, value: Any) -> str:
        if name not in owner.attrs:
            raise FixtureSafetyError(f"{getattr(owner, 'id', owner)!r} lacks {name}")
        owner.attrs[name].value = str(value)
        return cls._read_attr(owner, name)

    @classmethod
    def _write_numeric(
        cls, owner: Any, name: str, value: float, *, tolerance: float = 1.0
    ) -> float:
        if not math.isfinite(float(value)) or not math.isfinite(float(tolerance)):
            raise FixtureSafetyError(f"{name} request and tolerance must be finite")
        observed = _first_number(cls._write_attr(owner, name, value))
        if not math.isfinite(observed):
            raise FixtureSafetyError(f"{name} returned a non-finite readback")
        if abs(observed - float(value)) > tolerance:
            raise FixtureSafetyError(
                f"{name} readback {observed} differs from requested {value}"
            )
        return observed

    def _phy_channel(self, name: str, output: bool) -> Any:
        return self._channel(self.phy, name, output)

    def _set_tx_gains(self, tx1_db: float, tx2_db: float) -> None:
        self._write_numeric(
            self._phy_channel("voltage0", True),
            "hardwaregain",
            tx1_db,
            tolerance=0.26,
        )
        self._write_numeric(
            self._phy_channel("voltage1", True),
            "hardwaregain",
            tx2_db,
            tolerance=0.26,
        )

    def _mute_dds(self) -> None:
        for index in range(8):
            channel = self.tx.find_channel(f"altvoltage{index}", True)
            if channel is None:
                continue
            if "scale" in channel.attrs:
                self._write_numeric(channel, "scale", 0.0, tolerance=1e-9)
            if "raw" in channel.attrs:
                self._write_numeric(channel, "raw", 0.0, tolerance=1e-9)

    def _write_selector(self, channel: int, selector: int) -> None:
        legacy_address = DAC_LEGACY_CONTROL_REGISTER(channel)
        legacy = int(self.tx.reg_read(legacy_address))
        self.tx.reg_write(legacy_address, legacy & ~1)
        self.tx.reg_write(DAC_SELECTOR_REGISTER(channel), selector)
        observed = int(self.tx.reg_read(DAC_SELECTOR_REGISTER(channel))) & 0xF
        if observed != selector:
            raise FixtureSafetyError(
                f"DAC channel {channel} selector readback {observed} != {selector}"
            )

    def _best_effort_mute(self) -> tuple[dict[str, Any], list[str]]:
        """Attempt and verify every independent mute path before reporting errors."""

        failures: list[str] = []
        tx_gains: list[Optional[float]] = [None, None]
        selector_readbacks: list[Optional[int]] = [None] * 4
        dds_channels: dict[int, Any] = {}
        dds_readbacks: dict[str, dict[str, Any]] = {}

        def record_failure(label: str, error: BaseException | str) -> None:
            detail = error if isinstance(error, str) else _exception_text(error)
            failures.append(f"{label}: {detail}")

        # A failure on one attenuator must never prevent attempting the other.
        for index in (0, 1):
            try:
                self._write_numeric(
                    self._phy_channel(f"voltage{index}", True),
                    "hardwaregain",
                    TX_MUTE_DB,
                    tolerance=0.26,
                )
            except BaseException as error:
                record_failure(f"TX{index + 1} gain mute", error)

        # Likewise, attempt every attribute on every DDS channel independently.
        for index in range(8):
            name = f"altvoltage{index}"
            dds_readbacks[name] = {"present": False}
            try:
                channel = self.tx.find_channel(name, True)
            except BaseException as error:
                record_failure(f"DDS {name} lookup", error)
                continue
            if channel is None:
                continue
            dds_channels[index] = channel
            dds_readbacks[name] = {"present": True}
            for attribute in ("scale", "raw"):
                if attribute not in channel.attrs:
                    continue
                try:
                    self._write_numeric(channel, attribute, 0.0, tolerance=1e-9)
                except BaseException as error:
                    record_failure(f"DDS {name} {attribute} mute", error)

        # ZERO is the final independent safety barrier for each logical DAC lane.
        for channel in range(4):
            try:
                self._write_selector(channel, DAC_SELECT_ZERO)
            except BaseException as error:
                record_failure(f"selector {channel} mute", error)

        # Verify every path even when its write already failed; the readback is
        # useful evidence and may prove that a failed transport write still landed.
        for index in (0, 1):
            try:
                observed = _first_number(
                    self._read_attr(
                        self._phy_channel(f"voltage{index}", True),
                        "hardwaregain",
                    )
                )
                tx_gains[index] = observed
                if observed > -80.0:
                    record_failure(
                        f"TX{index + 1} gain verification",
                        f"readback {observed} dB is above -80 dB",
                    )
            except BaseException as error:
                record_failure(f"TX{index + 1} gain verification", error)

        for index, channel in dds_channels.items():
            name = f"altvoltage{index}"
            for attribute in ("scale", "raw"):
                if attribute not in channel.attrs:
                    continue
                try:
                    observed = _first_number(self._read_attr(channel, attribute))
                    dds_readbacks[name][attribute] = observed
                    if abs(observed) > 1e-9:
                        record_failure(
                            f"DDS {name} {attribute} verification",
                            f"readback {observed} is not zero",
                        )
                except BaseException as error:
                    record_failure(f"DDS {name} {attribute} verification", error)

        for channel in range(4):
            try:
                observed = int(self.tx.reg_read(DAC_SELECTOR_REGISTER(channel))) & 0xF
                selector_readbacks[channel] = observed
                if observed != DAC_SELECT_ZERO:
                    record_failure(
                        f"selector {channel} verification",
                        f"readback {observed} is not ZERO",
                    )
            except BaseException as error:
                record_failure(f"selector {channel} verification", error)

        evidence = {
            "verified": not failures,
            "tx1_gain_db": tx_gains[0],
            "tx2_gain_db": tx_gains[1],
            "selectors": selector_readbacks,
            "dds": dds_readbacks,
            "failures": list(failures),
        }
        self._last_mute_evidence = evidence
        return evidence, failures

    def _mute_everything(self) -> None:
        _evidence, failures = self._best_effort_mute()
        if failures:
            raise FixtureSafetyError("; ".join(failures))

    def _configure_fixed_radio(self) -> None:
        if not math.isfinite(self.options.attenuation_db) or not math.isfinite(
            self.options.tx_gain_db
        ):
            raise FixtureSafetyError("attenuation and TX gain must be finite")
        effective_attenuation_db = self.options.attenuation_db - self.options.tx_gain_db
        if effective_attenuation_db < 30.0:
            raise FixtureSafetyError(
                "physical TX2-to-each-RX attenuation plus TX backoff must be "
                f">= 30 dB; observed {effective_attenuation_db:.2f} dB"
            )
        if not TX_MUTE_DB <= self.options.tx_gain_db <= 0.0:
            raise FixtureSafetyError("TX2 hardware gain must be in [-89.75, 0] dB")
        if self.options.sample_rate_hz <= 0 or self.options.samples_per_channel <= 0:
            raise FixtureSafetyError("sample rate and buffer length must be positive")
        if self.options.sample_rate_hz <= 250_000:
            raise FixtureSafetyError(
                "sample rate must keep the 100 kHz preflight in band"
            )
        if self.options.samples_per_channel < 8_192:
            raise FixtureSafetyError(
                "issue-46 buffers must contain at least 8192 samples"
            )
        center_frequency_hz = self.options.center_frequency_hz
        if isinstance(center_frequency_hz, bool) or not isinstance(
            center_frequency_hz, int
        ):
            raise FixtureSafetyError("center frequency must be an integer number of Hz")
        if not (
            MIN_COMMON_CENTER_FREQUENCY_HZ
            <= center_frequency_hz
            <= MAX_COMMON_CENTER_FREQUENCY_HZ
        ):
            raise FixtureSafetyError(
                "common RX/TX center frequency must be in "
                f"[{MIN_COMMON_CENTER_FREQUENCY_HZ}, "
                f"{MAX_COMMON_CENTER_FREQUENCY_HZ}] Hz"
            )

        rx0 = self._phy_channel("voltage0", False)
        rx1 = self._phy_channel("voltage1", False)
        tx0 = self._phy_channel("voltage0", True)
        tx1 = self._phy_channel("voltage1", True)
        for channel in (rx0, rx1, tx0, tx1):
            self._write_numeric(
                channel,
                "sampling_frequency",
                self.options.sample_rate_hz,
                tolerance=max(2.0, self.options.sample_rate_hz * 100e-6),
            )
            self._write_numeric(channel, "rf_bandwidth", 1_500_000, tolerance=2.0)
        for channel in (rx0, rx1):
            self._write_attr(channel, "gain_control_mode", "manual")
            self._write_numeric(channel, "hardwaregain", 20.0, tolerance=0.1)
        self._configure_center_frequency(center_frequency_hz)
        if "calib_mode" in self.phy.attrs:
            self._write_attr(self.phy, "calib_mode", "tx_quad")

        enabled_ids = {"voltage0", "voltage1", "voltage2", "voltage3"}
        for channel in self.rx.channels:
            if channel.scan_element:
                channel.enabled = channel.id in enabled_ids
        if int(self.rx.sample_size) != 8:
            raise FixtureSafetyError(
                f"dual-RX scan size is {self.rx.sample_size}, expected 8 bytes/sample"
            )

    def _configure_center_frequency(self, center_frequency_hz: int) -> dict[str, int]:
        """Tune the common RX/TX LO and return exact numeric readbacks."""

        self._write_numeric(
            self._phy_channel("altvoltage0", True),
            "frequency",
            center_frequency_hz,
            tolerance=2.0,
        )
        self._write_numeric(
            self._phy_channel("altvoltage1", True),
            "frequency",
            center_frequency_hz,
            tolerance=2.0,
        )
        return self.read_center_frequency()

    def read_center_frequency(self) -> dict[str, int]:
        """Return live RX/TX LO readbacks without changing radio state."""

        return {
            "rx_lo_hz": round(
                _first_number(
                    self._read_attr(self._phy_channel("altvoltage0", True), "frequency")
                )
            ),
            "tx_lo_hz": round(
                _first_number(
                    self._read_attr(self._phy_channel("altvoltage1", True), "frequency")
                )
            ),
        }

    def _pulse_sync(self) -> None:
        self.tx.reg_write(DAC_SYNC_REGISTER, 1)
        deadline = time.monotonic() + 1.0
        while int(self.tx.reg_read(DAC_SYNC_REGISTER)) & 1:
            if time.monotonic() >= deadline:
                raise FixtureSafetyError("DAC sync pulse did not self-clear")
            time.sleep(0.001)

    def _configure_tone_dds(self, tone_hz: int, scale: float) -> None:
        self._mute_dds()
        settings = ((4, 0), (6, 270_000))
        for index, phase in settings:
            channel = self._channel(self.tx, f"altvoltage{index}", True)
            # The HDL DDS phase accumulator quantizes its IIO frequency
            # readback. Keep that known quantization separate from the much
            # stricter measured-RF frequency gate in the tone oracle.
            dds_bin_hz = self.options.sample_rate_hz / 65_536
            self._write_numeric(
                channel, "frequency", tone_hz, tolerance=max(2.0, dds_bin_hz)
            )
            if "phase" in channel.attrs:
                self._write_numeric(channel, "phase", phase, tolerance=1.0)
            self._write_numeric(
                channel, "scale", scale, tolerance=max(1e-6, 1.0 / 32_768)
            )
            if "raw" in channel.attrs:
                self._write_numeric(channel, "raw", 1.0, tolerance=1e-9)

    @contextmanager
    def buffer(
        self,
        api: str,
        kernel_buffers: int,
        samples_per_channel: int,
        *,
        tandem_request: Optional[bytes] = None,
    ) -> Iterator[tuple[Any, Optional[int]]]:
        if kernel_buffers <= 0:
            raise ValueError("kernel buffer count must be positive")
        self.rx.set_kernel_buffers_count(kernel_buffers)
        value = None
        metadata_abi: Optional[int] = None
        try:
            if api == "ordinary":
                value = self.iio.Buffer(self.rx, samples_per_channel, False)
            elif api == "metadata":
                value, metadata_abi = create_metadata_buffer(
                    self.iio,
                    self.rx,
                    samples_per_channel,
                    tandem_request=(
                        tandem_request
                        if tandem_request is not None
                        else build_hold_request(gain_db=20)
                    ),
                )
            else:
                raise ValueError(f"unknown capture API {api!r}")
            yield value, metadata_abi
        finally:
            close_iio_object(value)
            value = None
            gc.collect()

    def mute_all(self) -> None:
        """Force the fixture into its verified non-transmitting configuration."""

        self._mute_everything()

    def arm_tx2_tone(self, *, tone_hz: int, scale: float) -> None:
        """Route one DDS tone to physical TX2 while both transmitters stay muted."""

        if not 0.0 < scale <= 1.0:
            raise FixtureSafetyError("DDS tone scale must be in (0, 1]")
        self._mute_everything()
        self._write_selector(0, DAC_SELECT_ZERO)
        self._write_selector(1, DAC_SELECT_ZERO)
        self._write_selector(2, DAC_SELECT_DDS)
        self._write_selector(3, DAC_SELECT_DDS)
        self._configure_tone_dds(tone_hz, scale)
        self._pulse_sync()

    @contextmanager
    def cyclic_tx2_waveform(
        self,
        tx2_cs16: bytes | bytearray | memoryview,
        *,
        sample_count: int,
    ) -> Iterator[dict[str, Any]]:
        """Route one verified cyclic-DMA waveform to TX2 and zeros to TX1.

        The caller receives control while both hardware attenuators remain
        muted.  It may then use :meth:`set_tx2_gain`, whose existing fixture
        authorization bounds still apply.  Every exit path attempts the three
        independent mute barriers before synchronously closing the DMA buffer.
        """

        # A malformed caller must not be able to leave a previously active RF
        # path transmitting merely because validation returns early.
        self.mute_all()
        if isinstance(sample_count, bool) or not isinstance(sample_count, int):
            raise FixtureSafetyError("cyclic TX sample_count must be an integer")
        if sample_count <= 0:
            raise FixtureSafetyError("cyclic TX sample_count must be positive")
        try:
            tx2_payload = bytes(tx2_cs16)
        except (TypeError, ValueError) as exc:
            raise FixtureSafetyError("TX2 cyclic payload must be bytes-like") from exc
        expected_tx2_bytes = sample_count * 4
        if len(tx2_payload) != expected_tx2_bytes:
            raise FixtureSafetyError(
                f"TX2 cyclic payload has {len(tx2_payload)} bytes, expected "
                f"{expected_tx2_bytes}"
            )

        buffer: Any = None
        buffer_closed = False
        buffer_release_method = "not_created"
        body_error: BaseException | None = None
        channel_states: list[tuple[Any, bool]] = []
        evidence: dict[str, Any] = {
            "sample_count": sample_count,
            "tx2_payload_bytes": len(tx2_payload),
            "tx2_payload_sha256": hashlib.sha256(tx2_payload).hexdigest(),
            "cyclic": True,
            "tx1_source": "excluded from DMA scan and ZERO selector",
            "tx2_source": "cyclic DMA",
        }
        try:
            # Keep the DMA scan scoped to the physical TX2 I/Q pair.  Enabling
            # both complex transmitters makes each 64-bit DMA beat one
            # four-lane scan; on Pluto's time-multiplexed 2T interface the TX2
            # pair then updates on only one of two physical phases.  The 0x0c
            # scan instead packs two successive TX2 IQ samples per beat, which
            # util_upack2 emits on successive DAC read events at the requested
            # per-channel sample cadence.  TX1 remains independently blocked
            # by its hardware attenuator and both ZERO selectors.
            enabled_ids = {"voltage2", "voltage3"}
            scan_channels: dict[str, Any] = {}
            for channel in self.tx.channels:
                if channel.scan_element:
                    channel_states.append((channel, bool(channel.enabled)))
                    if channel.id in enabled_ids:
                        if channel.id in scan_channels:
                            raise FixtureSafetyError(
                                f"duplicate TX scan channel {channel.id!r}"
                            )
                        scan_channels[channel.id] = channel
                    channel.enabled = channel.id in enabled_ids
            if set(scan_channels) != enabled_ids:
                missing = sorted(enabled_ids - set(scan_channels))
                raise FixtureSafetyError(f"TX scan layout lacks channels {missing}")
            scan_layout: list[dict[str, Any]] = []
            for expected_index, channel_id in (
                (2, "voltage2"),
                (3, "voltage3"),
            ):
                channel = scan_channels[channel_id]
                observed_index = int(channel.index)
                if observed_index != expected_index:
                    raise FixtureSafetyError(
                        f"TX {channel_id} scan index {observed_index}, expected "
                        f"{expected_index}"
                    )
                data_format = channel.data_format
                observed_format = {
                    "length": int(data_format.length),
                    "bits": int(data_format.bits),
                    "shift": int(data_format.shift),
                    "is_signed": bool(data_format.is_signed),
                    "is_be": bool(data_format.is_be),
                    "repeat": int(data_format.repeat),
                }
                expected_format = {
                    "length": 16,
                    "bits": 16,
                    "shift": 0,
                    "is_signed": True,
                    "is_be": False,
                    "repeat": 1,
                }
                if observed_format != expected_format:
                    raise FixtureSafetyError(
                        f"TX {channel_id} scan format {observed_format}, expected "
                        f"{expected_format}"
                    )
                scan_layout.append(
                    {"id": channel_id, "index": observed_index, **observed_format}
                )
            sample_size = int(self.tx.sample_size)
            if sample_size != 4:
                raise FixtureSafetyError(
                    f"TX2-only scan size is {sample_size}, expected 4 bytes/sample"
                )

            expected_buffer_bytes = sample_count * sample_size
            buffer = self.iio.Buffer(self.tx, sample_count, True)
            if len(buffer) != expected_buffer_bytes:
                raise FixtureSafetyError(
                    f"cyclic DMA buffer has {len(buffer)} bytes, expected "
                    f"{expected_buffer_bytes}"
                )
            # pylibiio's Buffer.write() obtains a ctypes view with
            # ``from_buffer`` and therefore requires writable host storage.
            # Keep the immutable payload above for hashing/comparison, but
            # hand the transport an exact mutable copy.
            writable_payload = bytearray(tx2_payload)
            written = int(buffer.write(writable_payload))
            if written != expected_buffer_bytes:
                raise FixtureSafetyError(
                    f"cyclic DMA write accepted {written} bytes, expected "
                    f"{expected_buffer_bytes}"
                )
            read_buffer = getattr(buffer, "read", None)
            if not callable(read_buffer):
                raise FixtureSafetyError(
                    "cyclic DMA output buffer cannot provide payload readback"
                )
            try:
                readback = bytes(read_buffer())
            except BaseException as error:  # noqa: BLE001 - fail closed on any ABI error
                raise FixtureSafetyError(
                    "cyclic DMA output buffer readback failed"
                ) from error
            if readback != tx2_payload:
                raise FixtureSafetyError(
                    "cyclic DMA buffer readback differs from payload"
                )
            buffer.push()

            self._write_selector(0, DAC_SELECT_ZERO)
            self._write_selector(1, DAC_SELECT_ZERO)
            self._write_selector(2, DAC_SELECT_DMA)
            self._write_selector(3, DAC_SELECT_DMA)
            tx_gains = [
                _first_number(
                    self._read_attr(
                        self._phy_channel(f"voltage{index}", True), "hardwaregain"
                    )
                )
                for index in (0, 1)
            ]
            if any(gain > -80.0 for gain in tx_gains):
                raise FixtureSafetyError(
                    f"TX gain readbacks {tx_gains} dB are above the mute limit"
                )
            evidence.update(
                {
                    "scan_sample_size": sample_size,
                    "enabled_scan_mask": 0x0C,
                    "scan_layout": scan_layout,
                    "buffer_bytes": expected_buffer_bytes,
                    "write_bytes": written,
                    "buffer_payload_layout": ["tx2_i", "tx2_q"],
                    "buffer_payload_sha256": hashlib.sha256(tx2_payload).hexdigest(),
                    "tx1_gain_db": tx_gains[0],
                    "tx2_gain_db": tx_gains[1],
                    "selectors": [
                        DAC_SELECT_ZERO,
                        DAC_SELECT_ZERO,
                        DAC_SELECT_DMA,
                        DAC_SELECT_DMA,
                    ],
                }
            )
            yield evidence
        except BaseException as error:  # noqa: BLE001 - preserve every body exit
            body_error = error
            raise
        finally:
            cleanup_failures: list[str] = []
            try:
                cleanup, mute_failures = self._best_effort_mute()
                cleanup_failures.extend(mute_failures)
            except BaseException as error:  # noqa: BLE001 - mute is unconditional
                cleanup = {"verified": False, "failures": []}
                cleanup_failures.append(
                    f"cyclic DMA mute routine: {_exception_text(error)}"
                )
            try:
                buffer_value = buffer
                buffer = None
                buffer_release_method = (
                    "not_created"
                    if buffer_value is None
                    else (
                        "explicit_close"
                        if callable(getattr(buffer_value, "close", None))
                        else "reference_release_gc"
                    )
                )
                try:
                    close_iio_object(buffer_value)
                finally:
                    buffer_value = None
                    gc.collect()
                buffer_closed = True
            except BaseException as error:  # noqa: BLE001 - report close failures
                cleanup_failures.append(
                    f"cyclic DMA buffer close: {_exception_text(error)}"
                )
            for channel, was_enabled in channel_states:
                try:
                    channel.enabled = was_enabled
                except BaseException as error:  # noqa: BLE001 - restore every channel
                    cleanup_failures.append(
                        f"cyclic DMA scan restore: {_exception_text(error)}"
                    )
            self._last_cyclic_dma_cleanup = {
                "mute": cleanup,
                "buffer_closed": buffer_closed,
                "buffer_release_method": buffer_release_method,
                "failures": cleanup_failures,
            }
            if cleanup_failures:
                cleanup_error = FixtureSafetyError("; ".join(cleanup_failures))
                if body_error is None:
                    raise cleanup_error
                raise BaseExceptionGroup(
                    "cyclic DMA body and cleanup both failed",
                    [body_error, cleanup_error],
                ) from None

    def set_tx2_gain(self, gain_db: float) -> float:
        """Set TX2 only, bounded by the strongest gain attested at construction."""

        if not TX_MUTE_DB <= gain_db <= self.options.tx_gain_db:
            raise FixtureSafetyError(
                f"TX2 gain {gain_db} dB is outside the authorized "
                f"[{TX_MUTE_DB}, {self.options.tx_gain_db}] dB range"
            )
        self._set_tx_gains(TX_MUTE_DB, gain_db)
        return _first_number(
            self._read_attr(self._phy_channel("voltage1", True), "hardwaregain")
        )

    def configure_rx(
        self, mode: str, *, manual_gain_db: Optional[float] = None
    ) -> None:
        """Apply one identical receive mode to both physical receive ports."""

        channels = tuple(
            self._phy_channel(f"voltage{index}", False) for index in (0, 1)
        )
        for channel in channels:
            self._write_attr(channel, "gain_control_mode", mode)
        if manual_gain_db is not None:
            if mode != "manual":
                raise ValueError("manual_gain_db is valid only in manual mode")
            for channel in channels:
                self._write_numeric(
                    channel, "hardwaregain", manual_gain_db, tolerance=0.1
                )
        observed = tuple(
            self._read_attr(channel, "gain_control_mode") for channel in channels
        )
        if observed != (mode, mode):
            raise FixtureSafetyError(
                f"RX gain-control readback {observed!r} differs from {mode!r}"
            )

    def read_rx_state(self) -> dict[str, list[Any]]:
        """Return JSON-safe mode and gain readbacks for both receivers."""

        channels = tuple(
            self._phy_channel(f"voltage{index}", False) for index in (0, 1)
        )
        return {
            "modes": [
                self._read_attr(channel, "gain_control_mode") for channel in channels
            ],
            "gains_db": [
                _first_number(self._read_attr(channel, "hardwaregain"))
                for channel in channels
            ],
        }

    def tandem_status(self) -> dict[str, int]:
        """Read the controller state without changing tandem ownership."""

        tandem = self.context.find_device("tandem-agc")
        if tandem is None:
            raise FixtureSafetyError("radio lacks the tandem-agc device")
        names = (
            "state",
            "fault_flags",
            "overflow_count",
            "fifo_level",
            "ownership_epoch",
            "transition_count",
            "rx1_gain_index",
            "rx2_gain_index",
        )
        return {name: int(self._read_attr(tandem, name)) for name in names}

    def capture_iq(
        self, buffer: Any, *, metadata: bool, samples_per_channel: int
    ) -> tuple[bytes, Optional[bytes], int]:
        """Refill once and return the matching dual-RX IQ and optional metadata."""

        raw_metadata = self._refill(buffer, metadata=metadata)
        refill_monotonic_ns = time.monotonic_ns()
        raw = bytes(buffer.read())
        expected_bytes = samples_per_channel * 8
        if len(raw) != expected_bytes:
            raise EvidenceInvalid(
                f"IQ payload has {len(raw)} bytes, expected {expected_bytes}"
            )
        return raw, raw_metadata, refill_monotonic_ns

    @staticmethod
    def _refill(buffer: Any, *, metadata: bool) -> Optional[bytes]:
        for attempt in range(65):
            try:
                result = buffer.refill()
                if not metadata:
                    return None
                value = (
                    result if result is not None else getattr(buffer, "metadata", None)
                )
                if value is None:
                    raise EvidenceInvalid("metadata refill returned no metadata")
                return bytes(value)
            except OSError as error:
                if error.errno != errno.EAGAIN or attempt == 64:
                    raise
        raise AssertionError("refill retry loop did not terminate")

    def qualify_tone(self) -> dict[str, Any]:
        if self.tone_qualification is not None:
            return self.tone_qualification
        tone_hz = 100_000
        try:
            self._mute_everything()
            self._write_selector(0, DAC_SELECT_ZERO)
            self._write_selector(1, DAC_SELECT_ZERO)
            self._write_selector(2, DAC_SELECT_DDS)
            self._write_selector(3, DAC_SELECT_DDS)
            self._configure_tone_dds(tone_hz, 0.20)
            self._pulse_sync()
            self._set_tx_gains(TX_MUTE_DB, self.options.tx_gain_db)
            time.sleep(0.1)
            tone_samples = min(self.options.samples_per_channel, 65_536)
            with self.buffer("ordinary", 2, tone_samples) as (buffer, _):
                self._refill(buffer, metadata=False)
                self._refill(buffer, metadata=False)
                raw = bytes(buffer.read())
            result = dict(
                analyze_tone(
                    raw,
                    sample_rate_hz=self.options.sample_rate_hz,
                    tone_hz=tone_hz,
                )
            )
            result.update(
                {
                    "tone_hz": tone_hz,
                    "dds_scale": 0.20,
                    "tx2_gain_db": self.options.tx_gain_db,
                    "attenuation_db": self.options.attenuation_db,
                }
            )
            if not result["valid"]:
                raise FixtureSafetyError(
                    f"DDS tone did not qualify both tee branches: {json.dumps(result)}"
                )
            self.tone_qualification = result
            return result
        finally:
            self._mute_everything()

    def arm_pnxx(self) -> None:
        if self._pnxx_armed:
            return
        if self.tone_qualification is None:
            self.qualify_tone()
        self._mute_everything()
        self._write_selector(0, DAC_SELECT_ZERO)
        self._write_selector(1, DAC_SELECT_ZERO)
        self._write_selector(2, DAC_SELECT_PNXX)
        self._write_selector(3, DAC_SELECT_PNXX)
        self._pulse_sync()
        self._pnxx_sync_count += 1
        self._set_tx_gains(TX_MUTE_DB, self.options.tx_gain_db)
        time.sleep(0.1)
        self._pnxx_armed = True

    def capture_frame(
        self,
        buffer: Any,
        *,
        api: str,
        ordinal: int,
        iq_path: Optional[Path] = None,
    ) -> tuple[CaptureFrame, bytes]:
        raw_metadata = self._refill(buffer, metadata=api == "metadata")
        refill_time = time.monotonic_ns()
        raw = bytes(buffer.read())
        expected_bytes = self.options.samples_per_channel * 8
        if len(raw) != expected_bytes:
            raise EvidenceInvalid(
                f"IQ payload has {len(raw)} bytes, expected {expected_bytes}"
            )
        if iq_path is not None:
            iq_path.write_bytes(raw)

        phases = tuple(
            estimate_p15_phase(raw, rx_channel=channel) for channel in (0, 1)
        )
        for channel, phase in enumerate(phases):
            if phase.coherence < self.options.pn_min_coherence:
                raise EvidenceInvalid(
                    f"RX{channel} PN coherence {phase.coherence:.4f} is below "
                    f"{self.options.pn_min_coherence:.4f}"
                )
            if phase.peak_ratio < self.options.pn_min_peak_ratio:
                raise EvidenceInvalid(
                    f"RX{channel} PN peak ratio {phase.peak_ratio:.3f} is below "
                    f"{self.options.pn_min_peak_ratio:.3f}"
                )

        metadata = (
            parse_frame_metadata(raw_metadata) if raw_metadata is not None else None
        )
        if metadata is not None:
            if metadata.samples_per_channel != self.options.samples_per_channel:
                raise EvidenceInvalid("metadata sample count differs from IIO buffer")
            if metadata.iq_payload_bytes != expected_bytes:
                raise EvidenceInvalid("metadata IQ byte count differs from IIO payload")
            if metadata.enabled_scan_mask != 0x0F or metadata.channel_count != 2:
                raise EvidenceInvalid("metadata does not describe dual complex RX")
        return (
            CaptureFrame(
                ordinal=ordinal,
                sha256=hashlib.sha256(raw).hexdigest(),
                bytes=len(raw),
                refill_monotonic_ns=refill_time,
                rx0_pn=phases[0],
                rx1_pn=phases[1],
                metadata=metadata,
            ),
            raw,
        )

    def close(self) -> None:
        if self.context is None:
            if not self._lock.closed:
                self._lock.close()
            return
        errors: list[str] = []
        try:
            try:
                cleanup, errors = self._best_effort_mute()
            except BaseException as error:
                cleanup = {
                    "verified": False,
                    "tx1_gain_db": None,
                    "tx2_gain_db": None,
                    "selectors": [None] * 4,
                    "dds": {},
                    "failures": [f"mute routine: {_exception_text(error)}"],
                }
                errors = list(cleanup["failures"])
            self.cleanup_verified = bool(cleanup["verified"])
            if self._report_path is not None and self._report_path.exists():
                try:
                    report = json.loads(self._report_path.read_text(encoding="utf-8"))
                    report["cleanup"] = cleanup
                    _atomic_json(self._report_path, report)
                except BaseException as error:
                    errors.append(f"cleanup report: {_exception_text(error)}")
        finally:
            context, self.context = self.context, None
            self.phy = self.rx = self.tx = None
            try:
                close_iio_object(context)
            finally:
                del context
                gc.collect()
                if not self._lock.closed:
                    self._lock.close()
        if errors:
            raise FixtureSafetyError("; ".join(errors))


def experiment_matrix(options: Issue46Options) -> list[CellPlan]:
    if options.profile == "smoke":
        kernel_counts = (1, 2)
        pauses = (0.0, 1.0, 4.0)
        repeats = 1
    elif options.profile == "repro":
        kernel_counts = (1, 2, 4)
        pauses = (0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0)
        repeats = 5
    else:
        raise ValueError(f"unknown issue-46 profile {options.profile!r}")
    sinks: Sequence[str] = (
        ("ram", "sync") if options.sink == "both" else (options.sink,)
    )
    matrix = [
        CellPlan(api, kernel, pause, repeat, sink)
        for repeat in range(repeats)
        for kernel in kernel_counts
        for pause in pauses
        for api in ("ordinary", "metadata")
        for sink in sinks
    ]
    random.Random(options.seed).shuffle(matrix)
    return matrix


def _boundary_record(
    *,
    plan: CellPlan,
    previous: CaptureFrame,
    current: Optional[CaptureFrame],
    capacity_safe: bool,
    refill_error: Optional[str] = None,
) -> dict[str, Any]:
    counter = None
    pn = None
    if current is not None:
        rx0 = pn_transition(
            previous.rx0_pn.phase,
            current.rx0_pn.phase,
            previous.metadata.samples_per_channel
            if previous.metadata is not None
            else previous.bytes // 8,
            period=P15_SAMPLE_PERIOD,
        )
        rx1 = pn_transition(
            previous.rx1_pn.phase,
            current.rx1_pn.phase,
            previous.metadata.samples_per_channel
            if previous.metadata is not None
            else previous.bytes // 8,
            period=P15_SAMPLE_PERIOD,
        )
        pn = agree_dual_rx((rx0, rx1))
        if previous.metadata is not None and current.metadata is not None:
            counter = counter_transition(previous.metadata, current.metadata)
    overflow = bool(
        current and current.metadata and current.metadata.device_iio_overflow
    )
    verdict: BoundaryVerdict = evaluate_boundary(
        api=plan.api,
        capacity_safe=capacity_safe,
        pn=pn,
        counter=counter,
        overflow_flag=overflow,
        refill_error=refill_error,
    )
    return {
        "previous_ordinal": previous.ordinal,
        "current_ordinal": current.ordinal if current is not None else None,
        "capacity_safe": capacity_safe,
        "refill_error": refill_error,
        "pn": asdict(pn) if pn is not None else None,
        "counter": asdict(counter) if counter is not None else None,
        "overflow_flag": overflow,
        "verdict": asdict(verdict),
    }


def _run_cell(
    radio: Issue46Radio,
    plan: CellPlan,
    *,
    output_dir: Path,
) -> dict[str, Any]:
    frames: list[CaptureFrame] = []
    boundaries: list[dict[str, Any]] = []
    held_ram: list[bytes] = []
    sink_file = None
    cell_dir = output_dir / "iq" / plan.key
    if radio.options.save_iq:
        cell_dir.mkdir(parents=True, exist_ok=True)
    if plan.sink == "sync":
        sink_path = output_dir / "sink" / f"{plan.key}.ci16"
        sink_path.parent.mkdir(parents=True, exist_ok=True)
        sink_file = sink_path.open("wb")
    metadata_abi: Optional[int] = None
    error_after_pause: Optional[str] = None
    try:

        def consume(raw: bytes) -> None:
            if plan.sink == "ram":
                held_ram.append(raw)
            elif sink_file is not None:
                sink_file.write(raw)
                sink_file.flush()
                os.fsync(sink_file.fileno())

        with radio.buffer(
            plan.api, plan.kernel_buffers, radio.options.samples_per_channel
        ) as (buffer, metadata_abi):
            for ordinal in range(2):
                iq_path = (
                    cell_dir / f"frame-{ordinal:02d}.ci16"
                    if radio.options.save_iq
                    else None
                )
                frame, raw = radio.capture_frame(
                    buffer, api=plan.api, ordinal=ordinal, iq_path=iq_path
                )
                consume(raw)
                frames.append(frame)
                if ordinal:
                    boundaries.append(
                        _boundary_record(
                            plan=plan,
                            previous=frames[-2],
                            current=frame,
                            capacity_safe=True,
                        )
                    )

            time.sleep(plan.pause_factor * radio.options.refill_period_seconds)
            for post_index in range(plan.kernel_buffers + 3):
                ordinal = len(frames)
                iq_path = (
                    cell_dir / f"frame-{ordinal:02d}.ci16"
                    if radio.options.save_iq
                    else None
                )
                try:
                    frame, raw = radio.capture_frame(
                        buffer, api=plan.api, ordinal=ordinal, iq_path=iq_path
                    )
                except OSError as error:
                    error_after_pause = _exception_text(error)
                    boundaries.append(
                        _boundary_record(
                            plan=plan,
                            previous=frames[-1],
                            current=None,
                            capacity_safe=(
                                post_index > 0
                                or plan.pause_factor <= max(0, plan.kernel_buffers - 1)
                            ),
                            refill_error=error_after_pause,
                        )
                    )
                    break
                consume(raw)
                frames.append(frame)
                boundaries.append(
                    _boundary_record(
                        plan=plan,
                        previous=frames[-2],
                        current=frame,
                        capacity_safe=(
                            post_index > 0
                            or plan.pause_factor <= max(0, plan.kernel_buffers - 1)
                        ),
                    )
                )
    finally:
        if sink_file is not None:
            sink_file.close()
    return {
        "plan": asdict(plan),
        "metadata_abi": metadata_abi,
        "frames": [frame.to_dict() for frame in frames],
        "boundaries": boundaries,
        "refill_error": error_after_pause,
        "verdict": (
            "red"
            if any(item["verdict"]["verdict"] == "red" for item in boundaries)
            else "green"
        ),
    }


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def run_experiment(radio: Issue46Radio) -> tuple[dict[str, Any], Path]:
    """Run the randomized A/B matrix and preserve evidence after every cell."""

    options = radio.options
    radio.arm_pnxx()
    if radio._pnxx_sync_count != 1:
        raise EvidenceInvalid("PNXX must have exactly one DAC sync seed")
    output_dir = options.output_dir
    report_path = output_dir / "issue-46-report.json"
    radio._report_path = report_path
    matrix = experiment_matrix(options)
    started = time.monotonic()
    report: dict[str, Any] = {
        "schema": "plutosdr-fw.issue-46-refill-continuity.v1",
        "started_unix_ns": time.time_ns(),
        "identity": radio.identity,
        "initial_dac_registers": radio.initial_registers,
        "tone_qualification": radio.tone_qualification,
        "configuration": {
            **asdict(options),
            "output_dir": str(options.output_dir),
            "refill_period_seconds": options.refill_period_seconds,
            "pn_phase_period": P15_SAMPLE_PERIOD,
        },
        "matrix": [asdict(item) for item in matrix],
        "cells": [],
        "verdict": "running",
    }
    _atomic_json(report_path, report)
    try:
        for index, plan in enumerate(matrix):
            if time.monotonic() - started >= options.max_seconds:
                raise TimeoutError(
                    f"issue-46 experiment exceeded {options.max_seconds:.1f} seconds"
                )
            cell = _run_cell(radio, plan, output_dir=output_dir)
            cell["matrix_index"] = index
            report["cells"].append(cell)
            _atomic_json(report_path, report)
        report["verdict"] = (
            "red"
            if any(cell["verdict"] == "red" for cell in report["cells"])
            else "green"
        )
    except BaseException as error:
        report["verdict"] = "invalid"
        report["fatal_error"] = _exception_text(error)
        _atomic_json(report_path, report)
        raise
    report["elapsed_seconds"] = time.monotonic() - started
    report["completed_unix_ns"] = time.time_ns()
    _atomic_json(report_path, report)
    return report, report_path
