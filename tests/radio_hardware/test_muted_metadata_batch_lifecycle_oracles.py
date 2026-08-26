import copy
import errno
import fcntl
import hashlib
import json
import pathlib
import re
import struct
import subprocess
import zlib
from dataclasses import replace
from types import SimpleNamespace

import pytest

from . import muted_metadata_batch_lifecycle as lifecycle
from .candidate_binding import REQUIRED_EVIDENCE_ROLES
from .lifecycle_test_support import build_lifecycle_v5_archive
from .metadata_abi import (
    FEATURE_HARDWARE_SAMPLE_COUNTER,
    FLAG_SAMPLE_SEQUENCE_VALID,
    GAIN_EVENT_BYTES,
    GAIN_OBSERVATION_BYTES,
    METADATA_MAGIC,
    TANDEM_V5_EXTENSION,
    V5_PREFIX_BYTES,
    TandemFrameMetadata,
    TandemGainTable,
    TandemState,
)
from .muted_metadata_batch_lifecycle import (
    BATCH_FRAMES,
    CENTER_FREQUENCY_HZ,
    EXACT_HOLD_METADATA_FLAGS,
    EXACT_METADATA_FEATURES,
    EXPECTED_BATCH_CACHE_BYTES,
    FRAME_SAMPLES,
    HOLD_GAIN_DB,
    RAW_METADATA_BYTES,
    RF_BANDWIDTH_HZ,
    RX_SCAN_FORMAT,
    SAMPLE_RATE_HZ,
    QualificationError,
    _atomic_json,
    _attest_mapped_libiio,
    _attest_runner_provenance,
    _close_resources_and_persist,
    _configure_dual_complex_rx_scan,
    _frame_evidence,
    _reread_exact_report,
    validate_archived_pass_report,
    validate_durable_pass_report,
    validate_full_drain_frames,
)
from .pluto_plus_candidate_test_support import (
    build_utility_deployment_bundle,
    identity,
    write_private,
)

EXACT_LIBIIO_COMMIT = "70739d25ec1fa7b95d9069bd26a3e4192fdb3851"
EXACT_LIBIIO_TAG = "tandem-agc-v8-rc3-source/libiio-v1"
TEST_SERIAL = "1040007c4a94000211000b009186843ef2"
EXPECTED_FIRMWARE_VERSION = "v0.41-plutoplus-spf-tandem-agc-v8-rc4"
EXPECTED_FIRMWARE_PATTERN = rf"\A{re.escape(EXPECTED_FIRMWARE_VERSION)}\Z"
EXPECTED_KERNEL_VERSION = "5.15.0-g77a1f2352162"
EXPECTED_HARDWARE_MODEL = "Analog Devices PlutoSDR Rev.C (Z7010-AD9361)"
_REAL_ATTEST_CANDIDATE_BINDING = lifecycle._attest_candidate_binding


@pytest.fixture(autouse=True)
def _attested_in_progress_runner_tree(monkeypatch, tmp_path):
    """Model committed runner and protected libiio provenance without host paths."""

    monkeypatch.setenv("PLUTOSDR_FW_LIBIIO_SOURCE_REF", f"refs/tags/{EXACT_LIBIIO_TAG}")
    monkeypatch.setenv("PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT", EXACT_LIBIIO_COMMIT)

    def semantic(index_path: pathlib.Path, *, expected_stage: str):
        value = json.loads(index_path.read_text())
        normalized = lifecycle.validate_artifact_index(value)
        assert normalized["stage"] == expected_stage
        return normalized

    monkeypatch.setattr(lifecycle, "verify_artifact_index_semantics", semantic)

    repository = pathlib.Path(lifecycle.__file__).resolve().parents[2]
    original = lifecycle._git_bytes
    protected = {
        "tests/radio_hardware/muted_metadata_batch_lifecycle.py",
        "scripts/run_muted_metadata_batch_lifecycle_hardware.sh",
        "tests/radio_hardware/metadata_abi.py",
        "tests/radio_hardware/candidate_binding.py",
        "tests/radio_hardware/pluto_plus_candidate.py",
    }

    def fake_git(observed_repository, *arguments):
        observed_repository = pathlib.Path(observed_repository)
        if observed_repository == repository:
            if arguments == ("status", "--porcelain", "--untracked-files=no"):
                return b""
            if arguments and arguments[0] == "show":
                relative = arguments[1].split(":", 1)[1]
                if relative in protected:
                    return (repository / relative).read_bytes()
        if (
            observed_repository.name == "attested-fixture-libiio-source"
            and observed_repository.is_relative_to(tmp_path)
        ):
            if arguments in {
                ("rev-parse", "HEAD"),
                (
                    "rev-parse",
                    f"refs/tags/{EXACT_LIBIIO_TAG}^{{commit}}",
                ),
            }:
                return f"{EXACT_LIBIIO_COMMIT}\n".encode()
            if arguments == ("status", "--porcelain", "--untracked-files=no"):
                return b""
            if arguments == (
                "show",
                f"{EXACT_LIBIIO_COMMIT}:bindings/python/iio.py",
            ):
                return (observed_repository / "bindings/python/iio.py").read_bytes()
        return original(observed_repository, *arguments)

    monkeypatch.setattr(lifecycle, "_git_bytes", fake_git)

    def fake_candidate_binding(
        *,
        source_manifest_path,
        artifact_index_path,
        deployment_receipt_path,
        candidate_dfu_path,
        serial,
        runner_provenance,
        semantic_verify=False,
    ):
        del semantic_verify
        source_manifest_path = pathlib.Path(source_manifest_path).absolute()
        artifact_index_path = pathlib.Path(artifact_index_path).absolute()
        deployment_receipt_path = pathlib.Path(deployment_receipt_path).absolute()
        candidate_dfu_path = pathlib.Path(candidate_dfu_path).absolute()
        return {
            "attestation": (
                "exact committed source manifest, candidate index, DFU/FIT bytes, "
                "harness blobs, and serial-scoped RAM receipt verified before radio "
                "context"
            ),
            "source_commit": str(
                runner_provenance.get("host_runner_repository_commit", "a" * 40)
            ),
            "source_manifest": {
                "path": str(source_manifest_path),
                "relative_path": "manifests/tandem-agc-test-source.yaml",
                "committed_relative_path": ("manifests/tandem-agc-test-source.yaml"),
                "bytes": 1,
                "sha256": "1" * 64,
                "values": {
                    "libiio_0_25_source": EXACT_LIBIIO_COMMIT,
                    "libiio_0_25_ref": f"refs/tags/{EXACT_LIBIIO_TAG}",
                },
            },
            "build_run_id": 1,
            "build_run_attempt": 1,
            "artifact_index_path": str(artifact_index_path),
            "artifact_index_bytes": 1,
            "artifact_index_sha256": "2" * 64,
            "artifact_index": {},
            "evidence_member_count": len(REQUIRED_EVIDENCE_ROLES),
            "evidence_members_verified": True,
            "dfu_path": str(candidate_dfu_path),
            "dfu_bytes": 17,
            "dfu_sha256": "3" * 64,
            "fit_bytes": 1,
            "fit_sha256": "4" * 64,
            "deployment_receipt_path": str(deployment_receipt_path),
            "deployment_receipt_bytes": 1,
            "deployment_receipt_sha256": "5" * 64,
            "deployment_receipt": {},
            "serial": serial,
            "firmware_version": EXPECTED_FIRMWARE_VERSION,
            "firmware_pattern": EXPECTED_FIRMWARE_PATTERN,
            "kernel_version": EXPECTED_KERNEL_VERSION,
            "hardware_model": EXPECTED_HARDWARE_MODEL,
        }

    monkeypatch.setattr(lifecycle, "_attest_candidate_binding", fake_candidate_binding)


def _run_hardware(iio_module, **kwargs):
    receipt_path = pathlib.Path(kwargs.pop("ram_boot_receipt_path")).absolute()
    output_path = pathlib.Path(kwargs["output_path"]).absolute()
    return lifecycle.run_hardware(
        iio_module,
        source_manifest_path=output_path.parent
        / "manifests/tandem-agc-test-source.yaml",
        artifact_index_path=output_path.parent / "candidate-index.json",
        deployment_receipt_path=receipt_path,
        candidate_dfu_path=output_path.parent / "candidate.dfu",
        **kwargs,
    )


def _preflight(*args, **kwargs):
    kwargs.setdefault("firmware_version", EXPECTED_FIRMWARE_VERSION)
    kwargs.setdefault("kernel_version", EXPECTED_KERNEL_VERSION)
    kwargs.setdefault("hardware_model", EXPECTED_HARDWARE_MODEL)
    return lifecycle._preflight(*args, **kwargs)


def _stub_runner_provenance(monkeypatch):
    monkeypatch.setattr(
        lifecycle,
        "_attest_runner_provenance",
        lambda: {
            "host_runner_repository_commit": "a" * 40,
            "host_runner_repository": str(
                pathlib.Path(lifecycle.__file__).resolve().parents[2]
            ),
        },
    )


def _hold_status(epoch=11):
    return {
        "state": int(TandemState.ARMED_HOLD),
        "fault_flags": 0,
        "overflow_count": 0,
        "fifo_level": 0,
        "ownership_epoch": epoch,
        "transition_count": 0,
        "rx1_gain_index": 43,
        "rx2_gain_index": 43,
    }


def _idle_status(endpoint=43):
    return {
        "state": int(TandemState.IDLE),
        "fault_flags": 0,
        "overflow_count": 0,
        "fifo_level": 0,
        "ownership_epoch": 0,
        "transition_count": 0,
        "rx1_gain_index": endpoint,
        "rx2_gain_index": endpoint,
    }


def _mute():
    return {
        "verified": True,
        "tx1_gain_db": -89.75,
        "tx2_gain_db": -89.75,
        "selectors": [3, 3, 3, 3],
        "dds": {
            f"altvoltage{index}": {
                "present": True,
                "raw": 0.0,
                "scale": 0.0,
            }
            for index in range(8)
        },
        "failures": [],
    }


def _rx():
    return {"modes": ["manual", "manual"], "gains_db": [40.0, 40.0]}


def _boot_rx():
    return {"modes": ["slow_attack", "slow_attack"], "gains_db": [71.0, 71.0]}


def _rf(*, normalized=True):
    lo = CENTER_FREQUENCY_HZ if normalized else 2_400_000_000
    tx_lo = CENTER_FREQUENCY_HZ if normalized else 2_450_000_000
    rate = SAMPLE_RATE_HZ if normalized else 30_720_000
    bandwidth = RF_BANDWIDTH_HZ if normalized else 18_000_000
    return {
        "rx_lo_hz": lo,
        "tx_lo_hz": tx_lo,
        "channels": {
            role: {
                "sampling_frequency_hz": rate,
                "rf_bandwidth_hz": bandwidth,
            }
            for role in ("rx0", "rx1", "tx0", "tx1")
        },
    }


def _scan_evidence():
    return {
        "enabled_channel_ids": [
            "voltage0",
            "voltage1",
            "voltage2",
            "voltage3",
        ],
        "enabled_scan_mask": 0x0F,
        "sample_size_bytes": 8,
        "layout": [
            {
                "id": f"voltage{index}",
                "index": index,
                "format": dict(RX_SCAN_FORMAT),
            }
            for index in range(4)
        ],
    }


class _Attribute:
    def __init__(self, value, *, label, writes, readback_offset=0):
        self._value = str(value)
        self.label = label
        self.writes = writes
        self.readback_offset = readback_offset

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, requested):
        self.writes.append((self.label, str(requested)))
        try:
            self._value = str(float(requested) + self.readback_offset)
        except ValueError:
            self._value = str(requested)


class _Channel:
    def __init__(self, channel_id, output, attrs):
        self.id = channel_id
        self.output = output
        self.attrs = attrs


class _Device:
    def __init__(self, device_id, channels, *, writes, registers=None):
        self.id = device_id
        self.channels = channels
        self.attrs = {}
        self.writes = writes
        self.registers = dict(registers or {})

    def find_channel(self, channel_id, output):
        return next(
            (
                channel
                for channel in self.channels
                if channel.id == channel_id and channel.output is output
            ),
            None,
        )

    def reg_read(self, address):
        return self.registers.get(address, 0)

    def reg_write(self, address, value):
        self.writes.append((f"register:{address:#x}", str(value)))
        self.registers[address] = value


def _attr(value, label, writes, *, readback_offset=0):
    return _Attribute(
        value, label=label, writes=writes, readback_offset=readback_offset
    )


def _hardware_state(*, tx_gain=-80.0, tx_lo_readback_offset=0):
    writes = []
    phy_channels = []
    for index in (0, 1):
        phy_channels.append(
            _Channel(
                f"voltage{index}",
                False,
                {
                    "gain_control_mode": _attr(
                        "slow_attack", f"rx{index}:gain_control_mode", writes
                    ),
                    "hardwaregain": _attr(71.0, f"rx{index}:hardwaregain", writes),
                    "sampling_frequency": _attr(
                        30_720_000, f"rx{index}:sampling_frequency", writes
                    ),
                    "rf_bandwidth": _attr(
                        18_000_000, f"rx{index}:rf_bandwidth", writes
                    ),
                },
            )
        )
        phy_channels.append(
            _Channel(
                f"voltage{index}",
                True,
                {
                    "hardwaregain": _attr(tx_gain, f"tx{index}:hardwaregain", writes),
                    "sampling_frequency": _attr(
                        30_720_000, f"tx{index}:sampling_frequency", writes
                    ),
                    "rf_bandwidth": _attr(
                        18_000_000, f"tx{index}:rf_bandwidth", writes
                    ),
                },
            )
        )
    phy_channels.extend(
        [
            _Channel(
                "altvoltage0",
                True,
                {"frequency": _attr(2_400_000_000, "rx_lo:frequency", writes)},
            ),
            _Channel(
                "altvoltage1",
                True,
                {
                    "frequency": _attr(
                        2_450_000_000,
                        "tx_lo:frequency",
                        writes,
                        readback_offset=tx_lo_readback_offset,
                    )
                },
            ),
        ]
    )
    phy = _Device("ad9361-phy", phy_channels, writes=writes)
    dds_channels = [
        _Channel(
            f"altvoltage{index}",
            True,
            {
                "raw": _attr(0, f"dds{index}:raw", writes),
                "scale": _attr(0, f"dds{index}:scale", writes),
            },
        )
        for index in range(8)
    ]
    registers = {lifecycle._selector_address(index): 3 for index in range(4)} | {
        lifecycle._legacy_address(index): 0 for index in range(4)
    }
    tx = _Device("dds", dds_channels, writes=writes, registers=registers)
    tandem = SimpleNamespace(
        id="tandem-agc",
        attrs={
            name: SimpleNamespace(value=str(value))
            for name, value in _idle_status(65).items()
        },
    )
    context = SimpleNamespace(
        attrs={
            "hw_model": EXPECTED_HARDWARE_MODEL,
            "hw_serial": TEST_SERIAL,
            "fw_version": EXPECTED_FIRMWARE_VERSION,
            "ad9361-phy,model": "ad9361",
            "local,kernel": EXPECTED_KERNEL_VERSION,
            "uri": "usb:3.21.5",
            "iio,buffer-metadata": "2",
        }
    )
    return context, phy, tx, tandem, writes


def test_safe_preflight_accepts_cold_rc4_rx_rf_without_writes():
    context, phy, tx, tandem, writes = _hardware_state()
    result = _preflight(
        context,
        phy,
        tx,
        tandem,
        serial=TEST_SERIAL,
        uri="usb:3.21.5",
        firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
    )
    assert result["rx_state"] == _boot_rx()
    assert result["rf_state"] == _rf(normalized=False)
    assert result["configuration_write_count"] == 0
    assert result["metadata_buffer_open_count"] == 0
    assert writes == []


def test_safe_preflight_rejects_unmuted_tx_without_writes():
    context, phy, tx, tandem, writes = _hardware_state(tx_gain=-70.0)
    with pytest.raises(QualificationError, match="already muted"):
        _preflight(
            context,
            phy,
            tx,
            tandem,
            serial=TEST_SERIAL,
            uri="usb:3.21.5",
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
        )
    assert writes == []


@pytest.mark.parametrize("gain", [float("nan"), float("inf")])
def test_safe_preflight_rejects_nonfinite_mute_without_writes(gain):
    context, phy, tx, tandem, writes = _hardware_state(tx_gain=gain)
    with pytest.raises(QualificationError, match="already muted"):
        _preflight(
            context,
            phy,
            tx,
            tandem,
            serial=TEST_SERIAL,
            uri="usb:3.21.5",
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
        )
    assert writes == []


def test_safe_preflight_rejects_nonfinite_dds_without_writes():
    context, phy, tx, tandem, writes = _hardware_state()
    tx.find_channel("altvoltage0", True).attrs["scale"]._value = "nan"
    with pytest.raises(QualificationError, match="already muted"):
        _preflight(
            context,
            phy,
            tx,
            tandem,
            serial=TEST_SERIAL,
            uri="usb:3.21.5",
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
        )
    assert writes == []


def test_force_mute_rejects_nonfinite_write_readback_before_normalization():
    context, phy, tx, tandem, writes = _hardware_state()
    preflight = _preflight(
        context,
        phy,
        tx,
        tandem,
        serial=TEST_SERIAL,
        uri="usb:3.21.5",
        firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
    )
    phy.find_channel("voltage0", True).attrs["hardwaregain"].readback_offset = float(
        "nan"
    )
    with pytest.raises(QualificationError, match="finite|muted|readback"):
        lifecycle._normalize_before_hold(phy, tx, tandem, preflight=preflight)
    assert not any("frequency" in label for label, _ in writes)


def test_normalization_is_ordered_after_mute_and_before_any_buffer():
    context, phy, tx, tandem, writes = _hardware_state()
    preflight = _preflight(
        context,
        phy,
        tx,
        tandem,
        serial=TEST_SERIAL,
        uri="usb:3.21.5",
        firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
    )
    result = lifecycle._normalize_before_hold(phy, tx, tandem, preflight=preflight)
    assert result["metadata_buffer_open_count_before"] == 0
    assert result["metadata_buffer_open_count_after"] == 0
    assert [
        (item["target"], item["attribute"], item["requested"])
        for item in result["operations"]
    ] == [item[:3] for item in lifecycle._normalization_operation_contract()]
    first_lo_write = writes.index(("rx_lo:frequency", str(CENTER_FREQUENCY_HZ)))
    assert all(
        any(label == expected for label, _ in writes[:first_lo_write])
        for expected in ("tx0:hardwaregain", "tx1:hardwaregain", "dds0:raw")
    )
    assert result["rf_state_after"] == _rf()
    assert result["rx_state_after"] == _rx()


def test_normalization_rejects_missing_tx_lo_readback():
    context, phy, tx, tandem, _writes = _hardware_state(tx_lo_readback_offset=3)
    preflight = _preflight(
        context,
        phy,
        tx,
        tandem,
        serial=TEST_SERIAL,
        uri="usb:3.21.5",
        firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
    )
    with pytest.raises(QualificationError, match="readback"):
        lifecycle._normalize_before_hold(phy, tx, tandem, preflight=preflight)


def test_normalization_refuses_to_write_before_safe_preflight():
    _context, phy, tx, tandem, writes = _hardware_state()
    with pytest.raises(QualificationError, match="safe preflight"):
        lifecycle._normalize_before_hold(phy, tx, tandem, preflight={"verdict": "FAIL"})
    assert writes == []


def test_cleanup_unknown_identity_is_read_only():
    _context, phy, tx, tandem, writes = _hardware_state(tx_gain=-70.0)
    report = {"cleanup": {"verified": False}}
    errors = []
    lifecycle._cleanup_live_state(
        report,
        phy=phy,
        tx=tx,
        tandem=tandem,
        identity_verified=False,
        safe_preflight_completed=False,
        cleanup_errors=errors,
    )
    assert writes == []
    assert report["cleanup"]["preflight_failed_without_writes"] is True


def test_cleanup_exact_identity_unmuted_is_mute_only():
    _context, phy, tx, tandem, writes = _hardware_state(tx_gain=-70.0)
    report = {"cleanup": {"verified": False}}
    errors = []
    lifecycle._cleanup_live_state(
        report,
        phy=phy,
        tx=tx,
        tandem=tandem,
        identity_verified=True,
        safe_preflight_completed=False,
        cleanup_errors=errors,
    )
    assert errors == []
    assert report["cleanup"]["verified"] is True
    assert not any("gain_control_mode" in label for label, _ in writes)
    assert writes[0][0] == "tx0:hardwaregain"


def test_cleanup_idle_failure_forbids_manual40(monkeypatch):
    _context, phy, tx, tandem, writes = _hardware_state()
    report = {"cleanup": {"verified": False}}
    errors = []

    def reject_idle(*_args, **_kwargs):
        raise QualificationError("planted non-IDLE")

    monkeypatch.setattr(lifecycle, "_wait_idle", reject_idle)
    lifecycle._cleanup_live_state(
        report,
        phy=phy,
        tx=tx,
        tandem=tandem,
        identity_verified=True,
        safe_preflight_completed=True,
        cleanup_errors=errors,
    )
    assert len(errors) == 2
    assert not any("gain_control_mode" in label for label, _ in writes)


class _ScanChannel:
    def __init__(
        self,
        channel_id,
        index,
        *,
        format_overrides=None,
        initially_enabled=False,
        sticky_enabled=False,
    ):
        self.id = channel_id
        self.index = index
        self.scan_element = True
        self._enabled = initially_enabled
        self._sticky_enabled = sticky_enabled
        data_format = dict(RX_SCAN_FORMAT)
        data_format.update(format_overrides or {})
        self.data_format = SimpleNamespace(**data_format)

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, value):
        if self._sticky_enabled and not value:
            self._enabled = True
        else:
            self._enabled = value


class _ScanRx:
    def __init__(
        self,
        channel_ids=None,
        indexes=None,
        *,
        format_overrides=None,
        sample_size_override=None,
        sticky_extra=False,
    ):
        if channel_ids is None:
            channel_ids = [f"voltage{index}" for index in range(4)]
        if indexes is None:
            indexes = list(range(len(channel_ids)))
        self.channels = [
            _ScanChannel(
                channel_id,
                index,
                format_overrides=(format_overrides if ordinal == 2 else None),
            )
            for ordinal, (channel_id, index) in enumerate(zip(channel_ids, indexes))
        ]
        if sticky_extra:
            self.channels.append(
                _ScanChannel(
                    "voltage4",
                    4,
                    initially_enabled=True,
                    sticky_enabled=True,
                )
            )
        self._sample_size_override = sample_size_override

    @property
    def sample_size(self):
        if self._sample_size_override is not None:
            return self._sample_size_override
        return 2 * sum(channel.enabled for channel in self.channels)


def test_real_four_scalar_rx_scan_shape_is_attested():
    rx = _ScanRx()
    evidence = _configure_dual_complex_rx_scan(rx)
    assert evidence == _scan_evidence()
    assert [lane["format"]["bits"] for lane in evidence["layout"]] == [12] * 4
    assert all(channel.enabled for channel in rx.channels)


@pytest.mark.parametrize(
    ("rx", "message"),
    [
        (_ScanRx(channel_ids=["voltage0", "voltage1"]), "lacks channels"),
        (_ScanRx(indexes=[0, 1, 3, 2]), "scan index"),
        (_ScanRx(format_overrides={"is_signed": False}), "scan format"),
        (_ScanRx(format_overrides={"is_be": True}), "scan format"),
        (_ScanRx(format_overrides={"bits": 16}), "scan format"),
        (_ScanRx(format_overrides={"length": 12}), "scan format"),
        (_ScanRx(format_overrides={"shift": 1}), "scan format"),
        (_ScanRx(format_overrides={"repeat": 2}), "scan format"),
        (_ScanRx(sticky_extra=True), "enabled scan readback"),
        (_ScanRx(sample_size_override=6), "sample size is 6"),
    ],
)
def test_rx_scan_rejects_two_lane_reordered_or_non_signed_le16_12_shape(rx, message):
    with pytest.raises(QualificationError, match=message):
        _configure_dual_complex_rx_scan(rx)


@pytest.mark.parametrize(
    ("rx", "message"),
    [
        (_ScanRx(indexes=[0, "1", 2, 3]), "index is not an exact integer"),
        (_ScanRx(indexes=[False, 1, 2, 3]), "index is not an exact integer"),
        (
            _ScanRx(format_overrides={"length": "16"}),
            "length is not an exact integer",
        ),
        (
            _ScanRx(format_overrides={"bits": 12.0}),
            "bits is not an exact integer",
        ),
        (
            _ScanRx(format_overrides={"shift": False}),
            "shift is not an exact integer",
        ),
        (
            _ScanRx(format_overrides={"repeat": 1.0}),
            "repeat is not an exact integer",
        ),
        (
            _ScanRx(format_overrides={"is_signed": 1}),
            "is_signed is not an exact boolean",
        ),
        (
            _ScanRx(format_overrides={"is_be": 0}),
            "is_be is not an exact boolean",
        ),
        (_ScanRx(sample_size_override=8.0), "sample size is not an exact integer"),
    ],
)
def test_rx_scan_rejects_coercible_noncanonical_types(rx, message):
    with pytest.raises(QualificationError, match=message):
        _configure_dual_complex_rx_scan(rx)


@pytest.mark.parametrize(
    ("attribute", "message"),
    [("index", "does not expose its scan index"), ("data_format", "scan format")],
)
def test_rx_scan_fails_closed_when_shape_property_is_absent(attribute, message):
    rx = _ScanRx()
    delattr(rx.channels[0], attribute)
    with pytest.raises(QualificationError, match=message):
        _configure_dual_complex_rx_scan(rx)


def _frames():
    base = TandemFrameMetadata(
        version=5,
        header_bytes=3_256,
        features=EXACT_METADATA_FEATURES,
        flags=EXACT_HOLD_METADATA_FLAGS,
        stream_id=7,
        buffer_sequence=0,
        first_sample_sequence=123_456,
        samples_per_channel=FRAME_SAMPLES,
        iq_payload_bytes=FRAME_SAMPLES * 8,
        enabled_scan_mask=0x0F,
        sample_format=1,
        channel_count=2,
        observation_count=4,
        observation_capacity=64,
        event_count=0,
        event_capacity=64,
        observation_overflow_count=0,
        event_overflow_count=0,
        ownership_epoch=11,
        tandem_state=TandemState.ARMED_HOLD,
        tandem_fault_flags=0,
        tandem_transition_count=0,
        gain_table_id=TandemGainTable.MHZ_200_1300,
        threshold_provenance=lifecycle.EXPECTED_THRESHOLD_PROVENANCE,
        minimum_gain_db=0,
        maximum_gain_db=62,
        initial_gain_db=40,
        minimum_gain_index=3,
        maximum_gain_index=65,
        rx1_gain_index=43,
        rx2_gain_index=43,
        ad9361_temperature_mdeg_c=35_000,
        gain_events=(),
    )
    return [
        replace(
            base,
            buffer_sequence=index,
            first_sample_sequence=base.first_sample_sequence + index * FRAME_SAMPLES,
        )
        for index in range(BATCH_FRAMES)
    ]


_GAIN_OBSERVATION = struct.Struct("<QQIHBBbbHI")


def _hold_observation(sample_before, sample_after):
    return (
        sample_before,
        sample_after,
        1_000,
        0x0003,
        43,
        43,
        HOLD_GAIN_DB,
        HOLD_GAIN_DB,
        0,
        0,
    )


def _metadata_wire(metadata, *, observations=None):
    payload = bytearray(RAW_METADATA_BYTES)
    struct.pack_into(
        "<IHHIIQQQIIIHB",
        payload,
        0,
        METADATA_MAGIC,
        5,
        RAW_METADATA_BYTES,
        metadata.features,
        metadata.flags,
        metadata.stream_id,
        metadata.buffer_sequence,
        metadata.first_sample_sequence,
        metadata.samples_per_channel,
        metadata.iq_payload_bytes,
        metadata.enabled_scan_mask,
        metadata.sample_format,
        metadata.channel_count,
    )
    struct.pack_into("<bbbbB", payload, 55, *(HOLD_GAIN_DB,) * 4, 0)
    struct.pack_into("<IIII", payload, 60, 1_000, 1_000, 0xFFFFFFFF, 0xFFFFFFFF)
    struct.pack_into("<HHHH", payload, 76, 100, 100, 100, 100)
    struct.pack_into("<III", payload, 84, 1_000, 1_000, FRAME_SAMPLES // 4)
    struct.pack_into(
        "<HHHHHHII",
        payload,
        96,
        metadata.observation_count,
        metadata.observation_capacity,
        GAIN_OBSERVATION_BYTES,
        metadata.event_count,
        metadata.event_capacity,
        GAIN_EVENT_BYTES,
        metadata.observation_overflow_count,
        metadata.event_overflow_count,
    )
    TANDEM_V5_EXTENSION.pack_into(
        payload,
        124,
        metadata.ownership_epoch,
        int(metadata.tandem_state),
        metadata.tandem_fault_flags,
        metadata.tandem_transition_count,
        int(metadata.gain_table_id),
        metadata.threshold_provenance,
        metadata.minimum_gain_db,
        metadata.maximum_gain_db,
        metadata.initial_gain_db,
        metadata.minimum_gain_index,
        metadata.maximum_gain_index,
        metadata.rx1_gain_index,
        metadata.rx2_gain_index,
        (
            lifecycle.TEMPERATURE_INVALID_SENTINEL
            if metadata.ad9361_temperature_mdeg_c is None
            else metadata.ad9361_temperature_mdeg_c
        ),
        0,
        0,
        0,
    )
    if observations is None:
        observations = [
            (
                metadata.first_sample_sequence + index * (FRAME_SAMPLES // 4),
                metadata.first_sample_sequence + index * (FRAME_SAMPLES // 4) + 1,
                1_000,
                0x0003,
                metadata.rx1_gain_index,
                metadata.rx2_gain_index,
                HOLD_GAIN_DB,
                HOLD_GAIN_DB,
                0,
                0,
            )
            for index in range(metadata.observation_count)
        ]
    assert len(observations) == metadata.observation_count
    for index, observation in enumerate(observations):
        _GAIN_OBSERVATION.pack_into(
            payload,
            V5_PREFIX_BYTES + index * GAIN_OBSERVATION_BYTES,
            *observation,
        )
    struct.pack_into("<I", payload, len(payload) - 4, 0)
    struct.pack_into("<I", payload, len(payload) - 4, zlib.crc32(payload) & 0xFFFFFFFF)
    return bytes(payload)


class _IntegrationState:
    def __init__(self, tandem, *, phy, writes):
        self.tandem = tandem
        self.phy = phy
        self.writes = writes
        self.active_buffer = None
        self.open_count = 0
        self.close_count = 0
        self.kernel_buffer_counts = []
        self.buffers = []
        self.flip_tx_on_close = set()
        self.temperature_overrides = {}

    def set_status(self, status):
        for name, value in status.items():
            self.tandem.attrs[name].value = str(value)


class _IntegrationRx(_ScanRx):
    def __init__(self, state):
        super().__init__()
        self.id = "cf-ad9361-lpc"
        self.state = state

    def set_kernel_buffers_count(self, count):
        self.state.kernel_buffer_counts.append(count)


class _IntegrationMetadataBuffer:
    _iq = b"\x00" * lifecycle.EXPECTED_IQ_BYTES

    def __init__(
        self,
        device,
        samples_per_channel,
        request,
        *,
        metadata_capacity,
        batch_frames,
    ):
        state = device.state
        if state.active_buffer is not None:
            raise OSError(errno.EBUSY, "planted active metadata owner")
        if (
            samples_per_channel != FRAME_SAMPLES
            or request != lifecycle._hold_request()
            or metadata_capacity != lifecycle.METADATA_CAPACITY
            or batch_frames != BATCH_FRAMES
        ):
            raise AssertionError("integration MetadataBuffer request changed")
        state.open_count += 1
        self.state = state
        self.session_ordinal = state.open_count
        self.batch_frames = batch_frames
        self.batch_cache_bytes = EXPECTED_BATCH_CACHE_BYTES
        self.stream_id = 6 + self.session_ordinal
        self.ownership_epoch = 10 + self.session_ordinal
        self.first_sample = (123_456, 9_000_000, 18_000_000)[self.session_ordinal - 1]
        self.refill_count = 0
        self.cancelled = False
        self.closed = False
        state.active_buffer = self
        state.buffers.append(self)
        state.writes.append((f"buffer{self.session_ordinal}:open", ""))
        state.set_status(_hold_status(self.ownership_epoch))

    def refill(self):
        if self.cancelled or self.closed:
            raise OSError(errno.EBADF, "planted poisoned metadata buffer")
        if self.refill_count >= self.batch_frames:
            raise OSError(errno.ENODATA, "planted batch exhausted")
        metadata = replace(
            _frames()[0],
            stream_id=self.stream_id,
            ownership_epoch=self.ownership_epoch,
            buffer_sequence=self.refill_count,
            first_sample_sequence=(
                self.first_sample + self.refill_count * FRAME_SAMPLES
            ),
            ad9361_temperature_mdeg_c=self.state.temperature_overrides.get(
                (self.session_ordinal, self.refill_count),
                None
                if self.session_ordinal == 2 and self.refill_count == 0
                else 35_000,
            ),
        )
        self.refill_count += 1
        return _metadata_wire(metadata)

    def read(self):
        if self.refill_count == 0 or self.closed:
            raise OSError(errno.EBADF, "planted read without refill")
        return self._iq

    def cancel(self):
        if self.closed:
            raise OSError(errno.EBADF, "planted cancel after close")
        self.cancelled = True

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.state.close_count += 1
        self.state.writes.append((f"buffer{self.session_ordinal}:close", ""))
        if self.session_ordinal in self.state.flip_tx_on_close:
            for index in (0, 1):
                channel = self.state.phy.find_channel(f"voltage{index}", True)
                channel.attrs["hardwaregain"]._value = "-70.0"
        if self.state.active_buffer is self:
            self.state.active_buffer = None
            self.state.set_status(_idle_status())


class _IntegrationContext:
    def __init__(self, attrs, devices):
        self.attrs = attrs
        self.devices = devices
        self.closed = False
        self.timeout_ms = None

    def set_timeout(self, timeout_ms):
        self.timeout_ms = timeout_ms

    def find_device(self, device_id):
        return self.devices.get(device_id)

    def close(self):
        self.closed = True


class _IntegrationIio:
    MetadataBuffer = _IntegrationMetadataBuffer

    def __init__(self, context, pylibiio_path):
        self._context = context
        self.__file__ = str(pylibiio_path)

    def scan_contexts(self):
        return {"usb:3.21.5": ("R18 offline integration " + TEST_SERIAL)}

    def Context(self, uri):
        if uri != "usb:3.21.5":
            raise AssertionError(f"unexpected integration URI {uri}")
        return self._context


def _normalization():
    operations = []
    clock = 1_100
    for ordinal, (target, attribute, requested, tolerance) in enumerate(
        lifecycle._normalization_operation_contract()
    ):
        operations.append(
            {
                "ordinal": ordinal,
                "target": target,
                "attribute": attribute,
                "requested": requested,
                "readback": requested
                if isinstance(requested, str)
                else float(requested),
                "tolerance": tolerance,
                "host_before_ns": clock,
                "host_after_ns": clock + 1,
            }
        )
        clock += 10
    return {
        "verified": True,
        "policy": (
            "safe preflight, complete mute barrier, then RF/RX normalization; "
            "zero metadata buffers until every readback passes"
        ),
        "started_monotonic_ns": 1_050,
        "mute_barrier_completed_monotonic_ns": 1_075,
        "completed_monotonic_ns": 1_300,
        "metadata_buffer_open_count_before": 0,
        "metadata_buffer_open_count_after": 0,
        "mute_barrier": _mute(),
        "tandem_status_before": _idle_status(65),
        "operations": operations,
        "rf_state_after": _rf(),
        "rx_state_after": _rx(),
        "mute_after": _mute(),
        "tandem_status_after": _idle_status(65),
        "expected_gain_table": {
            "selection_basis": "common RX/TX LO at or below 1300000000 Hz",
            "center_frequency_hz": CENTER_FREQUENCY_HZ,
            "gain_table_id": 1,
            "gain_table_name": "mhz_200_1300",
            "hold_frame_attestation_required": True,
        },
    }


def test_exact_event_free_hold_batch_passes():
    result = validate_full_drain_frames(
        _frames(),
        status_after_open=_hold_status(),
        status_before_close=_hold_status(),
    )
    assert result["verified"] is True
    assert result["frame_count"] == 64
    assert result["sample_gaps"] == 0
    assert result["gain_events"] == 0


@pytest.mark.parametrize(
    ("index", "change"),
    [
        (12, {"buffer_sequence": 13}),
        (12, {"first_sample_sequence": 123_456 + 13 * FRAME_SAMPLES}),
        (12, {"ownership_epoch": 99}),
        (12, {"tandem_state": TandemState.ARMED_AUTO}),
        (12, {"tandem_fault_flags": 1}),
        (12, {"event_overflow_count": 1}),
        (12, {"rx2_gain_index": 10}),
        (12, {"features": FEATURE_HARDWARE_SAMPLE_COUNTER}),
        (12, {"flags": FLAG_SAMPLE_SEQUENCE_VALID}),
        (12, {"gain_table_id": TandemGainTable.MHZ_1300_4000}),
        (12, {"minimum_gain_db": 1}),
        (12, {"initial_gain_db": 39}),
        (12, {"maximum_gain_index": 64}),
    ],
)
def test_continuity_oracle_rejects_corruption(index, change):
    frames = _frames()
    frames[index] = replace(frames[index], **change)
    with pytest.raises(QualificationError):
        validate_full_drain_frames(
            frames,
            status_after_open=_hold_status(),
            status_before_close=_hold_status(),
        )


def test_continuity_oracle_requires_exactly_64_frames():
    with pytest.raises(QualificationError, match="63 frames"):
        validate_full_drain_frames(
            _frames()[:-1],
            status_after_open=_hold_status(),
            status_before_close=_hold_status(),
        )


def test_full_drain_accepts_only_a_leading_temperature_omission_prefix():
    frames = _frames()
    for ordinal in range(3):
        frames[ordinal] = replace(frames[ordinal], ad9361_temperature_mdeg_c=None)
    result = validate_full_drain_frames(
        frames,
        status_after_open=_hold_status(),
        status_before_close=_hold_status(),
    )
    assert result["verified"] is True


def test_full_drain_rejects_all_invalid_sentinels():
    frames = [replace(frame, ad9361_temperature_mdeg_c=None) for frame in _frames()]
    with pytest.raises(QualificationError, match="no valid sample"):
        validate_full_drain_frames(
            frames,
            status_after_open=_hold_status(),
            status_before_close=_hold_status(),
        )


def test_full_drain_rejects_temperature_omission_after_first_valid():
    frames = _frames()
    frames[4] = replace(frames[4], ad9361_temperature_mdeg_c=None)
    with pytest.raises(QualificationError, match="after the first valid"):
        validate_full_drain_frames(
            frames,
            status_after_open=_hold_status(),
            status_before_close=_hold_status(),
        )


@pytest.mark.parametrize(
    "value",
    [
        True,
        35_000.0,
        lifecycle.MINIMUM_TEMPERATURE_MDEG_C - 1,
        lifecycle.MAXIMUM_TEMPERATURE_MDEG_C + 1,
    ],
)
def test_temperature_samples_reject_types_and_values_outside_producer_range(value):
    with pytest.raises(QualificationError, match="exact integer"):
        lifecycle._validate_temperature_sample(value, role="full_drain", ordinal=0)
    with pytest.raises(QualificationError, match="cancel_first frame 0"):
        lifecycle._validate_temperature_sample(value, role="cancel_first", ordinal=0)


def test_cancel_first_accepts_exact_invalid_sentinel_representation():
    lifecycle._validate_temperature_sample(None, role="cancel_first", ordinal=0)


def _valid_report(tmp_path):
    frames = _frames()
    full_wires = [_metadata_wire(metadata) for metadata in frames]
    frame_records = [
        _frame_evidence(
            index,
            metadata,
            duration_ns=index + 1,
            returned_iq_sha256_in_process="a" * 64,
            metadata_sha256=hashlib.sha256(full_wires[index]).hexdigest(),
        )
        for index, metadata in enumerate(frames)
    ]
    cancel_metadata = replace(
        frames[0],
        stream_id=8,
        ownership_epoch=12,
        first_sample_sequence=9_000_000,
    )
    cancel_record = _frame_evidence(
        0,
        cancel_metadata,
        duration_ns=10,
        returned_iq_sha256_in_process="c" * 64,
        metadata_sha256=hashlib.sha256(_metadata_wire(cancel_metadata)).hexdigest(),
    )
    serial = TEST_SERIAL
    firmware = EXPECTED_FIRMWARE_VERSION
    final_status = _idle_status()
    cleanup = _mute()
    cleanup.update(
        {
            "started_monotonic_ns": 1_810,
            "mute_completed_monotonic_ns": 1_820,
            "idle_verified_monotonic_ns": 1_830,
            "rx_completed_monotonic_ns": 1_840,
            "final_idle_verified_monotonic_ns": 1_850,
            "rf_readback_completed_monotonic_ns": 1_860,
            "operation_order": [
                "force_mute",
                "verify_idle",
                "configure_manual40",
                "verify_final_idle",
                "read_final_rf",
            ],
            "tandem_status": final_status,
            "rx_state": _rx(),
            "rf_state": _rf(),
            "errors": [],
        }
    )
    repository = pathlib.Path(lifecycle.__file__).resolve().parents[2]
    commit = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    def blob_sha(relative):
        return hashlib.sha256((repository / relative).read_bytes()).hexdigest()

    module_relative = "tests/radio_hardware/muted_metadata_batch_lifecycle.py"
    shell_relative = "scripts/run_muted_metadata_batch_lifecycle_hardware.sh"
    abi_relative = "tests/radio_hardware/metadata_abi.py"
    candidate_binding_relative = "tests/radio_hardware/candidate_binding.py"
    module_sha = blob_sha(module_relative)
    shell_sha = blob_sha(shell_relative)
    abi_sha = blob_sha(abi_relative)
    candidate_binding_sha = blob_sha(candidate_binding_relative)
    output_path = tmp_path / lifecycle.REPORT_FILENAME
    output_preflight = lifecycle._prepare_fresh_output_path(output_path)
    captures = [
        *(("full_drain", index, payload) for index, payload in enumerate(full_wires)),
        ("cancel_first", 0, _metadata_wire(cancel_metadata)),
    ]
    metadata_artifacts = lifecycle._new_metadata_artifact_manifest(captures)
    lifecycle._write_metadata_artifacts(output_path, captures, metadata_artifacts)
    libiio_source = (tmp_path / "attested-fixture-libiio-source").resolve()
    pylibiio = libiio_source / "bindings/python/iio.py"
    pylibiio.parent.mkdir(parents=True, exist_ok=True)
    pylibiio.write_bytes(b"attested fixture pylibiio")
    libiio_build = tmp_path / "libiio-build"
    libiio_build.mkdir()
    library = libiio_build / "libiio.so.0.25"
    library.write_bytes(b"attested fixture libiio")
    library_sha = hashlib.sha256(library.read_bytes()).hexdigest()
    (libiio_build / "CMakeCache.txt").write_text(
        f"CMAKE_HOME_DIRECTORY:INTERNAL={libiio_source}\n", encoding="utf-8"
    )
    runner_provenance = {
        "host_runner_repository_commit": commit,
        "host_runner_repository": str(repository),
        "python_module_path": str(repository / module_relative),
        "python_module_sha256": module_sha,
        "python_module_head_blob_sha256": module_sha,
        "shell_runner_path": str(repository / shell_relative),
        "shell_runner_sha256": shell_sha,
        "shell_runner_head_blob_sha256": shell_sha,
        "metadata_abi_path": str(repository / abi_relative),
        "metadata_abi_sha256": abi_sha,
        "metadata_abi_head_blob_sha256": abi_sha,
        "candidate_binding_path": str(repository / candidate_binding_relative),
        "candidate_binding_sha256": candidate_binding_sha,
        "candidate_binding_head_blob_sha256": candidate_binding_sha,
    }
    device_lineage = lifecycle._attest_candidate_binding(
        source_manifest_path=tmp_path / "manifests/tandem-agc-test-source.yaml",
        artifact_index_path=tmp_path / "candidate-index.json",
        deployment_receipt_path=tmp_path / "ram-boot-receipt.json",
        candidate_dfu_path=tmp_path / "candidate.dfu",
        serial=serial,
        runner_provenance=runner_provenance,
    )
    preflight = {
        "verdict": "GO",
        "serial": serial,
        "uri": "usb:3.17.5",
        "firmware_version": firmware,
        "context_attrs": {
            "hw_serial": serial,
            "fw_version": firmware,
            "hw_model": EXPECTED_HARDWARE_MODEL,
            "ad9361-phy,model": "ad9361",
            "local,kernel": EXPECTED_KERNEL_VERSION,
            "iio,buffer-metadata": "2",
            "uri": "usb:3.17.5",
        },
        "mute": _mute(),
        "rx_state": _boot_rx(),
        "rf_state": _rf(normalized=False),
        "tandem_status": _idle_status(65),
        "started_monotonic_ns": 900,
        "completed_monotonic_ns": 1_000,
        "configuration_write_count": 0,
        "metadata_buffer_open_count": 0,
    }
    return {
        "schema": lifecycle.SCHEMA,
        "verdict": "PASS",
        "release_claim": "none; muted host-transport lifecycle qualification only",
        "release_pass_eligible": False,
        "hardware_qualified": False,
        "started_unix_ns": 1,
        "completed_unix_ns": 2,
        "host_libiio": {
            "source_commit": EXACT_LIBIIO_COMMIT,
            "protected_source_tag": EXACT_LIBIIO_TAG,
            "source_directory": str(libiio_source),
            "build_directory": str(libiio_build),
            "mapped_shared_objects": [str(library)],
            "mapped_shared_object": str(library),
            "mapped_shared_object_sha256": library_sha,
            "runner_shared_object_sha256": library_sha,
            "pylibiio_file": str(libiio_source / "bindings/python/iio.py"),
        },
        "runner_provenance": runner_provenance,
        "expected_device_firmware_lineage": device_lineage,
        "device_firmware_provenance": (
            lifecycle._observed_device_firmware_provenance(
                device_lineage, preflight=preflight
            )
        ),
        "output_preflight": output_preflight,
        "configuration": {
            "serial": serial,
            "firmware_pattern": EXPECTED_FIRMWARE_PATTERN,
            "firmware_version": EXPECTED_FIRMWARE_VERSION,
            "kernel_version": EXPECTED_KERNEL_VERSION,
            "hardware_model": EXPECTED_HARDWARE_MODEL,
            "tx_policy": "fully muted; no DDS/DMA enable and no TX gain increase",
            "normalization_policy": (
                "under verified mute with zero buffers: common LO, all PHY rates "
                "and bandwidths, then RX manual 40"
            ),
            "iq_evidence_policy": lifecycle.IQ_EVIDENCE_POLICY,
            "temperature_policy": lifecycle.TEMPERATURE_POLICY,
            "temperature_producer_policy": lifecycle.TEMPERATURE_PRODUCER_POLICY,
            "temperature_qualification_policy": (
                lifecycle.TEMPERATURE_QUALIFICATION_POLICY
            ),
            "temperature_producer_range_mdeg_c": [
                lifecycle.MINIMUM_TEMPERATURE_MDEG_C,
                lifecycle.MAXIMUM_TEMPERATURE_MDEG_C,
            ],
            "temperature_invalid_sentinel": lifecycle.TEMPERATURE_INVALID_SENTINEL,
            "temperature_policy_predecessor": (
                lifecycle._temperature_policy_predecessor()
            ),
            "observation_retention_policy": (lifecycle.OBSERVATION_RETENTION_POLICY),
            "observation_retention_policy_predecessor": (
                lifecycle._observation_retention_policy_predecessor()
            ),
            "failure_artifact_policy": lifecycle.FAILURE_ARTIFACT_POLICY,
            "center_frequency_hz": CENTER_FREQUENCY_HZ,
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "rf_bandwidth_hz": RF_BANDWIDTH_HZ,
            "expected_gain_table_id": 1,
            "expected_gain_table_name": "mhz_200_1300",
            "tandem_mode": "hold",
            "hold_gain_db": 40,
            "frame_samples_per_channel": FRAME_SAMPLES,
            "kernel_buffers": 8,
            "batch_frames": 64,
            "metadata_capacity_bytes": 64 * 1024,
            "expected_batch_cache_bytes": EXPECTED_BATCH_CACHE_BYTES,
        },
        "preflight": preflight,
        "normalization": _normalization(),
        "rx_scan": _scan_evidence(),
        "full_drain": {
            "kernel_buffers": 8,
            "batch_frames": 64,
            "metadata_capacity_bytes": 64 * 1024,
            "batch_cache_bound_bytes": EXPECTED_BATCH_CACHE_BYTES,
            "expected_batch_cache_bytes": EXPECTED_BATCH_CACHE_BYTES,
            "normalization_completed_monotonic_ns": 1_300,
            "first_buffer_open_requested_monotonic_ns": 1_400,
            "status_after_open": _hold_status(11),
            "status_before_close": _hold_status(11),
            "close_method": "explicit_normal_close",
            "close_completed_monotonic_ns": 1_500,
            "frames": frame_records,
            "continuity": {
                "verified": True,
                "frame_count": 64,
                "stream_id": 7,
                "ownership_epoch": 11,
                "buffer_sequence_range": [0, 63],
                "sample_sequence_range": [
                    123_456,
                    123_456 + 64 * FRAME_SAMPLES,
                ],
                "sample_gaps": 0,
                "gain_events": 0,
                "faults": 0,
                "overflows": 0,
            },
            "status_after_close": _idle_status(),
        },
        "post_full_drain_barrier": {
            "verified": True,
            "policy": (
                "force mute, verify closed HOLD IDLE, then read RX without writes"
            ),
            "started_monotonic_ns": 1_510,
            "mute_completed_monotonic_ns": 1_520,
            "idle_verified_monotonic_ns": 1_530,
            "completed_monotonic_ns": 1_540,
            "metadata_buffer_open_count": 0,
            "operation_order": ["force_mute", "verify_idle", "read_rx_state"],
            "mute": _mute(),
            "tandem_status": _idle_status(),
            "rx_state": _rx(),
        },
        "cancel_lifecycle": {
            "verified": True,
            "kernel_buffers": 8,
            "batch_frames": 64,
            "old_buffer_open_requested_monotonic_ns": 1_600,
            "operation_order": [
                "first_cached_frame_returned",
                "old_buffer_cancel",
                "second_open_ebusy",
                "old_refill_ebadf",
                "old_buffer_close",
                "mute_after_old_close",
                "verify_old_close_idle",
                "fresh_buffer_open",
                "fresh_buffer_close",
            ],
            "status_after_old_open": _hold_status(12),
            "first_returned_cached_frame": cancel_record,
            "second_open_error": {
                "type": "OSError",
                "errno": 16,
                "message": "busy",
            },
            "poison_refill_error": {
                "type": "OSError",
                "errno": 9,
                "message": "bad fd",
            },
            "old_buffer_close_completed_monotonic_ns": 1_700,
            "mute_after_old_close_started_monotonic_ns": 1_710,
            "mute_after_old_close": _mute(),
            "mute_after_old_close_completed_monotonic_ns": 1_720,
            "old_close_idle_verified_monotonic_ns": 1_730,
            "status_after_old_close": _idle_status(),
            "fresh_buffer_open_requested_monotonic_ns": 1_740,
            "status_after_fresh_open": _hold_status(13),
            "status_after_fresh_close": final_status,
            "fresh_buffer_close_completed_monotonic_ns": 1_800,
        },
        "temperature_evidence": lifecycle._temperature_evidence(
            [frame.ad9361_temperature_mdeg_c for frame in frames],
            cancel_metadata.ad9361_temperature_mdeg_c,
        ),
        "metadata_artifacts": metadata_artifacts,
        "final_tandem_status": final_status,
        "final_rx_state": _rx(),
        "final_rf_state": _rf(),
        "cleanup": cleanup,
    }


def test_durable_report_validator_accepts_frame_derived_pass(tmp_path):
    validate_durable_pass_report(_valid_report(tmp_path))


def _archived_raw_metadata(report):
    report_path = pathlib.Path(report["output_preflight"]["absolute_report_path"])
    return {
        entry["relative_path"]: (
            report_path.parent / entry["relative_path"]
        ).read_bytes()
        for entry in report["metadata_artifacts"]["entries"]
    }


def test_archive_validator_accepts_exact_v5_without_live_paths(tmp_path, monkeypatch):
    report = _valid_report(tmp_path)
    raw_metadata = _archived_raw_metadata(report)

    def reject_live_access(*_args, **_kwargs):
        raise AssertionError("archive validation attempted live provenance access")

    monkeypatch.setattr(lifecycle, "_git_bytes", reject_live_access)
    monkeypatch.setattr(lifecycle, "_attest_candidate_binding", reject_live_access)
    monkeypatch.setattr(
        lifecycle, "_read_bounded_owned_regular_file", reject_live_access
    )
    monkeypatch.setattr(
        lifecycle, "_sha256_bounded_owned_regular_file", reject_live_access
    )
    monkeypatch.setattr(lifecycle, "_require_nonsymlink_path", reject_live_access)

    validate_archived_pass_report(report, raw_metadata=raw_metadata)


def test_pure_archive_builder_emits_current_valid_v5(tmp_path, monkeypatch):
    baseline = _valid_report(tmp_path / "baseline")
    lineage = baseline["expected_device_firmware_lineage"]
    runner = baseline["runner_provenance"]
    host = baseline["host_libiio"]
    configuration = baseline["configuration"]

    def reject_live_access(*_args, **_kwargs):
        raise AssertionError("pure lifecycle fixture attempted live access")

    monkeypatch.setattr(lifecycle, "_git_bytes", reject_live_access)
    monkeypatch.setattr(lifecycle, "_attest_candidate_binding", reject_live_access)
    report, raw_metadata = build_lifecycle_v5_archive(
        report_path=(tmp_path / "archive" / lifecycle.REPORT_FILENAME),
        lineage=lineage,
        runner_provenance=runner,
        serial=configuration["serial"],
        runtime={
            "uri": "usb:test-fixture",
            "firmware_version": configuration["firmware_version"],
            "kernel_version": configuration["kernel_version"],
            "hardware_model": configuration["hardware_model"],
            "libiio_source_commit": host["source_commit"],
            "libiio_source_ref": f"refs/tags/{host['protected_source_tag']}",
            "libiio_sha256": host["mapped_shared_object_sha256"],
        },
    )

    assert report["schema"] == lifecycle.SCHEMA
    assert report["expected_device_firmware_lineage"] == lineage
    assert report["runner_provenance"] == runner
    assert len(raw_metadata) == lifecycle.RAW_METADATA_FILE_COUNT


@pytest.mark.parametrize(
    "report",
    [
        {
            "schema": "plutosdr-fw.muted-metadata-batch-lifecycle.v4",
            "verdict": "PASS",
        },
        {
            "schema": lifecycle.SCHEMA,
            "verdict": "PASS",
            "release_claim": "none; muted host-transport lifecycle qualification only",
            "release_pass_eligible": False,
            "hardware_qualified": False,
        },
    ],
    ids=("predecessor-v4", "minimal-v5"),
)
def test_archive_validator_rejects_old_and_minimal_reports(report):
    with pytest.raises(QualificationError):
        validate_archived_pass_report(report, raw_metadata={})


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("configuration", "hold_gain_db"), 39),
        (("full_drain", "frames", 7, "buffer_sequence"), 6),
        (("cancel_lifecycle", "second_open_error", "errno"), errno.EIO),
        (("cleanup", "verified"), False),
    ],
)
def test_archive_validator_rejects_altered_v5_semantics(tmp_path, path, value):
    report = _valid_report(tmp_path)
    raw_metadata = _archived_raw_metadata(report)
    target = report
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value

    with pytest.raises(QualificationError):
        validate_archived_pass_report(report, raw_metadata=raw_metadata)


@pytest.mark.parametrize("plant", ["missing", "extra", "changed"])
def test_archive_validator_rejects_altered_raw_metadata_inventory(tmp_path, plant):
    report = _valid_report(tmp_path)
    raw_metadata = _archived_raw_metadata(report)
    first = next(iter(raw_metadata))
    if plant == "missing":
        raw_metadata.pop(first)
    elif plant == "extra":
        raw_metadata["raw-metadata/unexpected.metadata.bin"] = b"x" * RAW_METADATA_BYTES
    else:
        payload = bytearray(raw_metadata[first])
        payload[0] ^= 0xFF
        raw_metadata[first] = bytes(payload)

    with pytest.raises(QualificationError):
        validate_archived_pass_report(report, raw_metadata=raw_metadata)


def test_durable_report_accepts_new_boundary_observation_between_snapshots(tmp_path):
    report = _valid_report(tmp_path)
    first, second = _frames()[:2]
    first = replace(first, observation_count=2)
    second = replace(second, observation_count=3)
    first_start = first.first_sample_sequence
    second_start = second.first_sample_sequence
    first_observations = [
        _hold_observation(first_start + 12_000, first_start + 12_001),
        _hold_observation(first_start + 29_308, first_start + 62_727),
    ]
    second_observations = [
        # This sample was appended after frame 0's metadata snapshot. It
        # legitimately straddles frame 1 without having appeared in frame 0.
        _hold_observation(second_start - 2_149, second_start + 2_061),
        _hold_observation(second_start + 15_389, second_start + 15_390),
        _hold_observation(second_start + 32_642, second_start + 32_643),
    ]
    _replace_full_metadata_payload(
        report,
        0,
        first,
        _metadata_wire(first, observations=first_observations),
    )
    _replace_full_metadata_payload(
        report,
        1,
        second,
        _metadata_wire(second, observations=second_observations),
    )
    validate_durable_pass_report(report)


def test_durable_report_rejects_missing_previously_retained_observation(tmp_path):
    report = _valid_report(tmp_path)
    first, second = _frames()[:2]
    first = replace(first, observation_count=2)
    second = replace(second, observation_count=2)
    first_start = first.first_sample_sequence
    second_start = second.first_sample_sequence
    first_observations = [
        _hold_observation(first_start + 1_000, first_start + 1_001),
        _hold_observation(second_start - 20_000, second_start + 100),
    ]
    second_observations = [
        _hold_observation(second_start + 1_000, second_start + 1_001),
        _hold_observation(second_start + 18_000, second_start + 18_001),
    ]
    _replace_full_metadata_payload(
        report,
        0,
        first,
        _metadata_wire(first, observations=first_observations),
    )
    _replace_full_metadata_payload(
        report,
        1,
        second,
        _metadata_wire(second, observations=second_observations),
    )
    with pytest.raises(QualificationError, match="observation retention"):
        validate_durable_pass_report(report)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("host_libiio", "runner_shared_object_sha256"), "0" * 64),
        (("host_libiio", "protected_source_tag"), "wrong-tag"),
        (("release_pass_eligible",), True),
        (("release_pass_eligible",), 0),
        (("hardware_qualified",), True),
        (("hardware_qualified",), 0),
        (("expected_device_firmware_lineage", "source_commit"), "0" * 40),
        (
            ("expected_device_firmware_lineage", "source_manifest", "sha256"),
            "0" * 64,
        ),
        (("expected_device_firmware_lineage", "build_run_id"), True),
        (("expected_device_firmware_lineage", "build_run_attempt"), 1.0),
        (("expected_device_firmware_lineage", "artifact_index_sha256"), "0" * 64),
        (("expected_device_firmware_lineage", "dfu_sha256"), "0" * 64),
        (("expected_device_firmware_lineage", "fit_sha256"), "0" * 64),
        (("expected_device_firmware_lineage", "fit_bytes"), 12_783_050),
        (
            ("expected_device_firmware_lineage", "deployment_receipt_sha256"),
            "0" * 64,
        ),
        (("expected_device_firmware_lineage", "serial"), "another-radio"),
        (
            ("expected_device_firmware_lineage", "firmware_version"),
            "v0.41-wrong-candidate",
        ),
        (("configuration", "serial"), "another-radio"),
        (("configuration", "iq_evidence_policy"), "IQ independently retained"),
        (("configuration", "temperature_policy"), "accept arbitrary nulls"),
        (("configuration", "temperature_invalid_sentinel"), 0),
        (("configuration", "failure_artifact_policy"), "promote partial failures"),
        (
            ("configuration", "temperature_policy_predecessor", "failed_report_sha256"),
            "0" * 64,
        ),
        (("configuration", "observation_retention_policy"), "require equality"),
        (
            (
                "configuration",
                "observation_retention_policy_predecessor",
                "failed_report_sha256",
            ),
            "0" * 64,
        ),
        (("configuration", "center_frequency_hz"), 914_999_999),
        (("preflight", "context_attrs", "local,kernel"), "5.15.0-wrong"),
        (("preflight", "configuration_write_count"), True),
        (("preflight", "metadata_buffer_open_count"), 1),
        (("preflight", "mute", "dds", "altvoltage0", "raw"), 0),
        (("normalization", "started_monotonic_ns"), 999),
        (("normalization", "metadata_buffer_open_count_after"), 1),
        (("normalization", "operations", 0, "readback"), 915_000_003.0),
        (("normalization", "operations", 0, "ordinal"), False),
        (("normalization", "expected_gain_table", "gain_table_id"), 2),
        (("full_drain", "first_buffer_open_requested_monotonic_ns"), 1_299),
        (("full_drain", "close_completed_monotonic_ns"), 9_999),
        (("post_full_drain_barrier", "started_monotonic_ns"), 1_499),
        (("post_full_drain_barrier", "operation_order"), []),
        (("post_full_drain_barrier", "mute", "tx1_gain_db"), -81.0),
        (("runner_provenance", "python_module_sha256"), "0" * 64),
        (("runner_provenance", "shell_runner_sha256"), "0" * 64),
        (("runner_provenance", "metadata_abi_sha256"), "0" * 64),
        (("runner_provenance", "metadata_abi_path"), "/tmp/metadata_abi.py"),
        (("temperature_evidence", "verified"), 1),
        (("temperature_evidence", "producer_semantics"), "startup only"),
        (("temperature_evidence", "qualification_acceptance"), "any omission"),
        (("temperature_evidence", "raw_invalid_sentinel"), 0),
        (
            ("temperature_evidence", "full_drain", "first_valid_ordinal"),
            1,
        ),
        (("temperature_evidence", "full_drain", "leading_omission_count"), 1),
        (("temperature_evidence", "cancel_first", "producer_omitted"), True),
        (("temperature_evidence", "actual_omission_count"), 1),
        (("rx_scan", "enabled_channel_ids"), ["voltage0", "voltage1"]),
        (("rx_scan", "enabled_scan_mask"), 0x03),
        (("rx_scan", "enabled_scan_mask"), 15.0),
        (("rx_scan", "sample_size_bytes"), 6),
        (("rx_scan", "sample_size_bytes"), 8.0),
        (("rx_scan", "layout", 0, "index"), False),
        (("rx_scan", "layout", 1, "index"), 1.0),
        (("rx_scan", "layout", 2, "index"), 3),
        (("rx_scan", "layout", 2, "format", "is_signed"), False),
        (("rx_scan", "layout", 2, "format", "is_signed"), 1),
        (("rx_scan", "layout", 2, "format", "is_be"), 0),
        (("rx_scan", "layout", 2, "format", "length"), 12),
        (("rx_scan", "layout", 2, "format", "length"), 16.0),
        (("rx_scan", "layout", 2, "format", "bits"), 16),
        (("rx_scan", "layout", 2, "format", "bits"), 12.0),
        (("rx_scan", "layout", 2, "format", "shift"), 1),
        (("rx_scan", "layout", 2, "format", "shift"), False),
        (("rx_scan", "layout", 2, "format", "repeat"), 2),
        (("rx_scan", "layout", 2, "format", "repeat"), 1.0),
        (
            ("rx_scan",),
            {**_scan_evidence(), "unexpected": True},
        ),
        (
            ("rx_scan", "layout", 0),
            {**_scan_evidence()["layout"][0], "unexpected": True},
        ),
        (
            ("rx_scan", "layout", 0, "format"),
            {**RX_SCAN_FORMAT, "unexpected": True},
        ),
        (("full_drain", "batch_cache_bound_bytes"), EXPECTED_BATCH_CACHE_BYTES - 1),
        (("full_drain", "frames", 7, "ownership_epoch"), 99),
        (("full_drain", "frames", 7, "features"), FEATURE_HARDWARE_SAMPLE_COUNTER),
        (("full_drain", "frames", 7, "threshold_provenance"), 1),
        (("full_drain", "frames", 7, "metadata_bytes"), 3_256.0),
        (("full_drain", "continuity", "frame_count"), 63),
        (("cancel_lifecycle", "status_after_old_open", "ownership_epoch"), 14),
        (("cancel_lifecycle", "old_buffer_open_requested_monotonic_ns"), 1_539),
        (("cancel_lifecycle", "old_buffer_close_completed_monotonic_ns"), 1_900),
        (("cancel_lifecycle", "mute_after_old_close", "tx1_gain_db"), -81.0),
        (("cancel_lifecycle", "fresh_buffer_open_requested_monotonic_ns"), 1_729),
        (("cancel_lifecycle", "second_open_error", "errno"), 5),
        (("cancel_lifecycle", "operation_order"), []),
        (("cleanup", "verified"), False),
        (("cleanup", "tx1_gain_db"), -81.0),
        (("cleanup", "started_monotonic_ns"), 1_799),
        (("cleanup", "operation_order"), []),
        (("final_rf_state", "rx_lo_hz"), 2_400_000_000),
    ],
)
def test_planted_false_pass_is_rejected(tmp_path, path, value):
    report = copy.deepcopy(_valid_report(tmp_path))
    target = report
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    with pytest.raises(QualificationError):
        validate_durable_pass_report(report)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 10**4000])
def test_hostile_numeric_is_a_domain_failure(tmp_path, value):
    report = _valid_report(tmp_path)
    report["cleanup"]["dds"]["altvoltage0"]["raw"] = value
    with pytest.raises(QualificationError):
        validate_durable_pass_report(report)


def test_in_process_iq_digest_is_explicitly_not_durable_revalidated(tmp_path):
    report = _valid_report(tmp_path)
    report["full_drain"]["frames"][0]["returned_iq_sha256_in_process"] = "b" * 64
    validate_durable_pass_report(report)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 10**4000])
def test_hostile_extra_context_attribute_is_a_domain_failure(tmp_path, value):
    report = _valid_report(tmp_path)
    report["preflight"]["context_attrs"]["planted"] = value
    with pytest.raises(QualificationError):
        validate_durable_pass_report(report)


@pytest.mark.parametrize("encoded", ['"\\ud800"', '"\\udfff"'])
def test_lone_surrogate_json_string_is_a_domain_failure(tmp_path, encoded):
    report = _valid_report(tmp_path)
    report["preflight"]["context_attrs"]["planted"] = json.loads(encoded)
    with pytest.raises(QualificationError, match="Unicode"):
        validate_durable_pass_report(report)


def test_embedded_nul_provenance_path_is_a_domain_failure(tmp_path):
    report = _valid_report(tmp_path)
    report["host_libiio"]["source_directory"] = json.loads('"/tmp/a\\u0000b"')
    with pytest.raises(QualificationError, match="NUL"):
        validate_durable_pass_report(report)


@pytest.mark.parametrize(
    "path",
    [
        ("started_unix_ns",),
        ("normalization", "operations", 0, "host_before_ns"),
        ("full_drain", "frames", 0, "refill_duration_ns"),
    ],
)
def test_huge_integer_timestamps_and_durations_are_domain_failures(tmp_path, path):
    report = _valid_report(tmp_path)
    target = report
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = 10**4000
    with pytest.raises(QualificationError):
        validate_durable_pass_report(report)


def test_fresh_output_rejects_ancestor_and_leaf_symlinks(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    ancestor = tmp_path / "ancestor"
    ancestor.symlink_to(target, target_is_directory=True)
    with pytest.raises(QualificationError, match="symlink"):
        lifecycle._prepare_fresh_output_path(ancestor / "result.json")
    leaf = tmp_path / "leaf.json"
    leaf.symlink_to(target / "redirected.json")
    with pytest.raises(QualificationError, match="symlink"):
        lifecycle._prepare_fresh_output_path(leaf)


def test_durable_validator_rejects_nonprivate_raw_metadata_directory(tmp_path):
    report = _valid_report(tmp_path)
    report_path = pathlib.Path(report["output_preflight"]["absolute_report_path"])
    artifact_directory = report_path.parent / lifecycle.RAW_METADATA_DIRECTORY
    artifact_directory.chmod(0o755)
    with pytest.raises(QualificationError, match="directory"):
        validate_durable_pass_report(report)


@pytest.mark.parametrize(
    "prefix",
    [lifecycle.RAW_METADATA_STAGING_PREFIX, lifecycle.RAW_METADATA_ABORTED_PREFIX],
)
def test_reserved_metadata_transaction_residue_is_rejected(tmp_path, prefix):
    fresh_parent = tmp_path / "fresh"
    fresh_parent.mkdir(mode=0o700)
    (fresh_parent / f"{prefix}planted").mkdir(mode=0o700)
    with pytest.raises(QualificationError, match="preflight"):
        lifecycle._prepare_fresh_output_path(fresh_parent / lifecycle.REPORT_FILENAME)

    report = _valid_report(tmp_path / "durable")
    report_path = pathlib.Path(report["output_preflight"]["absolute_report_path"])
    (report_path.parent / f"{prefix}planted").mkdir(mode=0o700)
    with pytest.raises(QualificationError, match="staging residue"):
        validate_durable_pass_report(report)


def test_overlong_durable_output_component_is_a_domain_failure(tmp_path):
    report = _valid_report(tmp_path)
    report_path = pathlib.Path("/") / ("x" * 300) / "result.json"
    preflight = report["output_preflight"]
    preflight["absolute_report_path"] = str(report_path)
    preflight["absolute_temporary_path"] = str(report_path.with_suffix(".json.tmp"))
    preflight["absolute_raw_metadata_directory"] = str(
        report_path.parent / lifecycle.RAW_METADATA_DIRECTORY
    )
    with pytest.raises(QualificationError):
        validate_durable_pass_report(report)


@pytest.mark.parametrize("plant", ["build", "library"])
def test_overlong_durable_host_path_is_a_domain_failure(tmp_path, plant):
    report = _valid_report(tmp_path)
    host = report["host_libiio"]
    if plant == "build":
        build = pathlib.Path("/tmp") / ("x" * 300) / "build"
        library = build / "libiio.so.0.25"
        host["build_directory"] = str(build)
    else:
        library = pathlib.Path(host["build_directory"]) / ("x" * 300) / "libiio.so.0.25"
    host["mapped_shared_object"] = str(library)
    host["mapped_shared_objects"] = [str(library)]
    with pytest.raises(QualificationError):
        validate_durable_pass_report(report)


def test_existing_lock_is_nofollow_regular_and_forced_private(tmp_path, monkeypatch):
    lock_path = tmp_path / "radio.lock"
    lock_path.write_text("stale\n", encoding="utf-8")
    lock_path.chmod(0o664)
    monkeypatch.setattr(lifecycle, "_lock_path", lambda _serial: lock_path)
    lock = lifecycle._open_lock(TEST_SERIAL)
    lock.close()
    assert lock_path.stat().st_mode & 0o777 == 0o600
    lock_path.unlink()
    target = tmp_path / "target"
    target.write_text("not a lock\n", encoding="utf-8")
    lock_path.symlink_to(target.name)
    with pytest.raises(QualificationError):
        lifecycle._open_lock(TEST_SERIAL)


@pytest.mark.parametrize(
    "plant", ["delete", "extra", "temporary", "symlink", "oversized"]
)
def test_metadata_inventory_mutation_is_rejected(tmp_path, monkeypatch, plant):
    report = _valid_report(tmp_path)
    report_path = pathlib.Path(report["output_preflight"]["absolute_report_path"])
    directory = report_path.parent / lifecycle.RAW_METADATA_DIRECTORY
    victim = directory / "full-frame-0000.metadata.bin"
    if plant == "delete":
        victim.unlink()
    elif plant == "extra":
        (directory / "extra.metadata.bin").write_bytes(b"x")
    elif plant == "temporary":
        (directory / "full-frame-0000.metadata.bin.tmp").write_bytes(b"x")
    else:
        if plant == "symlink":
            target = directory / "full-frame-0001.metadata.bin"
            victim.unlink()
            victim.symlink_to(target.name)
        else:
            victim.write_bytes(b"x" * (RAW_METADATA_BYTES + 1))
            victim_identity = (victim.stat().st_dev, victim.stat().st_ino)
            original_read = lifecycle.os.read

            def forbid_unbounded_read(descriptor, size):
                observed = lifecycle.os.fstat(descriptor)
                if (observed.st_dev, observed.st_ino) == victim_identity:
                    raise AssertionError("oversized metadata must fail before read")
                return original_read(descriptor, size)

            monkeypatch.setattr(lifecycle.os, "read", forbid_unbounded_read)
    with pytest.raises(QualificationError):
        validate_durable_pass_report(report)


def _refresh_first_metadata_artifact(report, payload):
    report_path = pathlib.Path(report["output_preflight"]["absolute_report_path"])
    entry = report["metadata_artifacts"]["entries"][0]
    path = report_path.parent / entry["relative_path"]
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    entry["sha256"] = digest
    report["full_drain"]["frames"][0]["metadata_sha256"] = digest
    report["metadata_artifacts"]["manifest_sha256"] = (
        lifecycle._metadata_manifest_digest(report["metadata_artifacts"]["entries"])
    )


def _replace_full_metadata_artifact(report, ordinal, metadata):
    payload = _metadata_wire(metadata)
    _replace_full_metadata_payload(report, ordinal, metadata, payload)


def _replace_full_metadata_payload(report, ordinal, metadata, payload):
    report_path = pathlib.Path(report["output_preflight"]["absolute_report_path"])
    entry = report["metadata_artifacts"]["entries"][ordinal]
    path = report_path.parent / entry["relative_path"]
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    entry["sha256"] = digest
    report["full_drain"]["frames"][ordinal] = _frame_evidence(
        ordinal,
        metadata,
        duration_ns=ordinal + 1,
        returned_iq_sha256_in_process="a" * 64,
        metadata_sha256=digest,
    )
    report["metadata_artifacts"]["manifest_sha256"] = (
        lifecycle._metadata_manifest_digest(report["metadata_artifacts"]["entries"])
    )


def _refresh_temperature_evidence(report):
    report["temperature_evidence"] = lifecycle._temperature_evidence(
        [
            frame["ad9361_temperature_mdeg_c"]
            for frame in report["full_drain"]["frames"]
        ],
        report["cancel_lifecycle"]["first_returned_cached_frame"][
            "ad9361_temperature_mdeg_c"
        ],
    )


def _replace_cancel_metadata_artifact(report, metadata):
    payload = _metadata_wire(metadata)
    report_path = pathlib.Path(report["output_preflight"]["absolute_report_path"])
    entry = report["metadata_artifacts"]["entries"][-1]
    path = report_path.parent / entry["relative_path"]
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    entry["sha256"] = digest
    report["cancel_lifecycle"]["first_returned_cached_frame"] = _frame_evidence(
        0,
        metadata,
        duration_ns=10,
        returned_iq_sha256_in_process="c" * 64,
        metadata_sha256=digest,
    )
    report["metadata_artifacts"]["manifest_sha256"] = (
        lifecycle._metadata_manifest_digest(report["metadata_artifacts"]["entries"])
    )


def test_durable_report_accepts_multi_frame_leading_temperature_sentinels(tmp_path):
    report = _valid_report(tmp_path)
    base_frames = _frames()
    for ordinal in range(3):
        _replace_full_metadata_artifact(
            report,
            ordinal,
            replace(base_frames[ordinal], ad9361_temperature_mdeg_c=None),
        )
    _refresh_temperature_evidence(report)
    validate_durable_pass_report(report)
    evidence = report["temperature_evidence"]["full_drain"]
    assert evidence["leading_omission_count"] == 3
    assert evidence["first_valid_ordinal"] == 3
    assert evidence["omitted_ordinals"] == [0, 1, 2]


def test_durable_report_accepts_and_reparses_cancel_first_sentinel(tmp_path):
    report = _valid_report(tmp_path)
    cancel = replace(
        _frames()[0],
        stream_id=8,
        ownership_epoch=12,
        first_sample_sequence=9_000_000,
        ad9361_temperature_mdeg_c=None,
    )
    _replace_cancel_metadata_artifact(report, cancel)
    _refresh_temperature_evidence(report)
    validate_durable_pass_report(report)
    entry = report["metadata_artifacts"]["entries"][-1]
    report_path = pathlib.Path(report["output_preflight"]["absolute_report_path"])
    parsed = lifecycle.parse_tandem_frame_metadata(
        (report_path.parent / entry["relative_path"]).read_bytes()
    )
    assert parsed.ad9361_temperature_mdeg_c is None
    assert report["temperature_evidence"]["cancel_first"] == {
        "frame_count": 1,
        "ordinal": 0,
        "producer_omitted": True,
        "omitted_ordinals": [0],
        "valid_temperature_count": 0,
        "temperature_mdeg_c": None,
    }
    assert report["release_pass_eligible"] is False
    assert report["hardware_qualified"] is False
    assert report["schema"] == lifecycle.SCHEMA


def test_durable_report_rejects_all_full_drain_temperature_sentinels(tmp_path):
    report = _valid_report(tmp_path)
    for ordinal, frame in enumerate(_frames()):
        _replace_full_metadata_artifact(
            report,
            ordinal,
            replace(frame, ad9361_temperature_mdeg_c=None),
        )
    with pytest.raises(QualificationError, match="no valid sample"):
        validate_durable_pass_report(report)


def test_durable_report_rejects_temperature_sentinel_after_valid_sample(tmp_path):
    report = _valid_report(tmp_path)
    _replace_full_metadata_artifact(
        report,
        7,
        replace(_frames()[7], ad9361_temperature_mdeg_c=None),
    )
    with pytest.raises(QualificationError, match="after the first valid"):
        validate_durable_pass_report(report)


@pytest.mark.parametrize(
    "value",
    [
        lifecycle.MINIMUM_TEMPERATURE_MDEG_C - 1,
        lifecycle.MAXIMUM_TEMPERATURE_MDEG_C + 1,
    ],
)
def test_durable_report_rejects_cancel_temperature_outside_producer_range(
    tmp_path, value
):
    report = _valid_report(tmp_path)
    cancel = replace(
        _frames()[0],
        stream_id=8,
        ownership_epoch=12,
        first_sample_sequence=9_000_000,
        ad9361_temperature_mdeg_c=value,
    )
    _replace_cancel_metadata_artifact(report, cancel)
    with pytest.raises(QualificationError, match="cancel_first frame 0"):
        validate_durable_pass_report(report)


def test_v5_validator_rejects_v4_schema_and_temperature_authority_promotion(tmp_path):
    report = _valid_report(tmp_path)
    report["schema"] = lifecycle.PREDECESSOR_SCHEMA
    with pytest.raises(QualificationError, match="schema"):
        validate_durable_pass_report(report)
    report["schema"] = lifecycle.SCHEMA
    report["release_pass_eligible"] = True
    with pytest.raises(QualificationError, match="release authority"):
        validate_durable_pass_report(report)


@pytest.mark.parametrize("role", ["full_drain", "cancel_first"])
def test_missing_temperature_field_is_a_clean_schema_rejection(tmp_path, role):
    report = _valid_report(tmp_path)
    frame = (
        report["full_drain"]["frames"][0]
        if role == "full_drain"
        else report["cancel_lifecycle"]["first_returned_cached_frame"]
    )
    del frame["ad9361_temperature_mdeg_c"]
    with pytest.raises(QualificationError, match="frame evidence fields"):
        validate_durable_pass_report(report)


@pytest.mark.parametrize(
    ("stream_id", "first_sample_sequence"),
    [
        (7, 9_000_000),
        (8, 123_456),
    ],
)
def test_cancel_session_must_follow_full_stream(
    tmp_path, stream_id, first_sample_sequence
):
    report = _valid_report(tmp_path)
    cancel_metadata = replace(
        _frames()[0],
        stream_id=stream_id,
        ownership_epoch=12,
        first_sample_sequence=first_sample_sequence,
    )
    _replace_cancel_metadata_artifact(report, cancel_metadata)
    with pytest.raises(QualificationError, match="cancel session"):
        validate_durable_pass_report(report)


@pytest.mark.parametrize(
    "plant",
    [
        "nonmax_index",
        "short_cadence",
        "unknown_flag",
        "bad_magic",
        "bad_crc",
        "bad_header",
        "invalid_temperature",
    ],
)
def test_synchronized_raw_metadata_mutation_is_rejected(tmp_path, plant):
    report = _valid_report(tmp_path)
    report_path = pathlib.Path(report["output_preflight"]["absolute_report_path"])
    path = (
        report_path.parent / report["metadata_artifacts"]["entries"][0]["relative_path"]
    )
    payload = bytearray(path.read_bytes())
    if plant == "nonmax_index":
        payload[V5_PREFIX_BYTES + 22] = 44
        payload[V5_PREFIX_BYTES + 23] = 44
    elif plant == "short_cadence":
        first_sample = report["full_drain"]["frames"][0]["first_sample_sequence"]
        struct.pack_into(
            "<QQ",
            payload,
            V5_PREFIX_BYTES + GAIN_OBSERVATION_BYTES,
            first_sample + 1,
            first_sample + 2,
        )
    elif plant == "unknown_flag":
        flags = struct.unpack_from("<I", payload, 12)[0] | (1 << 31)
        struct.pack_into("<I", payload, 12, flags)
        report["full_drain"]["frames"][0]["flags"] = flags
    elif plant == "bad_magic":
        struct.pack_into("<I", payload, 0, 0)
    elif plant == "bad_crc":
        payload[200] ^= 1
    elif plant == "invalid_temperature":
        struct.pack_into("<i", payload, 164, 150_000)
        report["full_drain"]["frames"][0]["ad9361_temperature_mdeg_c"] = 150_000
    else:
        struct.pack_into("<H", payload, 6, RAW_METADATA_BYTES - 1)
    if plant != "bad_crc":
        struct.pack_into("<I", payload, len(payload) - 4, 0)
        struct.pack_into(
            "<I", payload, len(payload) - 4, zlib.crc32(payload) & 0xFFFFFFFF
        )
    _refresh_first_metadata_artifact(report, bytes(payload))
    with pytest.raises(QualificationError):
        validate_durable_pass_report(report)


def test_atomic_report_must_reread_exact_before_pass(tmp_path):
    report = _valid_report(tmp_path)
    path = tmp_path / "result.json"
    identity = _atomic_json(path, report)
    assert _reread_exact_report(path, report) == report
    changed = json.loads(path.read_text())
    changed["full_drain"]["continuity"]["frame_count"] = 63
    _atomic_json(
        path,
        changed,
        replace_existing=True,
        expected_existing_identity=identity,
    )
    with pytest.raises(QualificationError):
        _reread_exact_report(path, report)


def test_atomic_fail_report_reread_rejects_int_float_alias(tmp_path):
    path = tmp_path / "failure.json"
    expected = {"verdict": "FAIL", "error": {"errno": 5}}
    identity = _atomic_json(path, expected)
    changed = {"verdict": "FAIL", "error": {"errno": 5.0}}
    _atomic_json(
        path,
        changed,
        replace_existing=True,
        expected_existing_identity=identity,
    )
    with pytest.raises(QualificationError, match="bytes|size"):
        _reread_exact_report(path, expected)


def test_oversized_report_is_rejected_before_read(tmp_path, monkeypatch):
    path = tmp_path / "failure.json"
    expected = {"verdict": "FAIL", "error": {"errno": 5}}
    path.write_bytes(lifecycle._json_payload(expected) + b"x")
    victim_identity = (path.stat().st_dev, path.stat().st_ino)
    original_read = lifecycle.os.read

    def forbid_unbounded_read(descriptor, size):
        observed = lifecycle.os.fstat(descriptor)
        if (observed.st_dev, observed.st_ino) == victim_identity:
            raise AssertionError("oversized report must fail before read")
        return original_read(descriptor, size)

    monkeypatch.setattr(lifecycle.os, "read", forbid_unbounded_read)
    with pytest.raises(QualificationError, match="size"):
        _reread_exact_report(path, expected)


def test_first_report_promotion_never_clobbers_raced_target(tmp_path, monkeypatch):
    output = tmp_path / "result.json"
    lock_path = tmp_path / "radio.lock"
    lock = lock_path.open("a+", encoding="utf-8")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    original_open = lifecycle.os.open

    planted = False

    def plant_target_before_open(path, flags, *args, **kwargs):
        nonlocal planted
        if pathlib.Path(path) == output and flags & lifecycle.os.O_EXCL and not planted:
            planted = True
            output.write_bytes(b"external winner")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(lifecycle.os, "open", plant_target_before_open)
    durable, error = _close_resources_and_persist(
        {
            "schema": lifecycle.SCHEMA,
            "verdict": "FAIL",
            "started_unix_ns": 1,
            "cleanup": _mute(),
        },
        output_path=output,
        context=None,
        lock=lock,
        lock_acquired=True,
        cleanup_errors=[],
        primary_error=None,
    )
    assert durable["verdict"] == "FAIL"
    assert isinstance(error, QualificationError)
    assert output.read_bytes() == b"external winner"
    assert not output.with_suffix(".json.tmp").exists()
    with lock_path.open("a+", encoding="utf-8") as reopened:
        fcntl.flock(reopened, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(reopened, fcntl.LOCK_UN)


def test_owned_report_rewrite_never_clobbers_swapped_path(tmp_path, monkeypatch):
    output = tmp_path / "result.json"
    identity = _atomic_json(output, {"verdict": "assembling"})
    original_ftruncate = lifecycle.os.ftruncate
    swapped = False

    def swap_before_owned_write(descriptor, length):
        nonlocal swapped
        if not swapped:
            swapped = True
            output.unlink()
            output.write_bytes(b"external swapped report")
        return original_ftruncate(descriptor, length)

    monkeypatch.setattr(lifecycle.os, "ftruncate", swap_before_owned_write)
    with pytest.raises(lifecycle._AtomicPromotionError, match="replaced"):
        _atomic_json(
            output,
            {"verdict": "FAIL"},
            replace_existing=True,
            expected_existing_identity=identity,
        )
    assert output.read_bytes() == b"external swapped report"


def test_metadata_promotion_never_clobbers_raced_target(tmp_path, monkeypatch):
    target = tmp_path / "frame.metadata.bin"
    original_open = lifecycle.os.open
    planted = False

    def plant_target_before_open(path, flags, *args, **kwargs):
        nonlocal planted
        if pathlib.Path(path) == target and flags & lifecycle.os.O_EXCL and not planted:
            planted = True
            target.write_bytes(b"external sidecar")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(lifecycle.os, "open", plant_target_before_open)
    with pytest.raises(QualificationError, match="not fresh"):
        lifecycle._atomic_bytes(target, b"owned payload")
    assert target.read_bytes() == b"external sidecar"
    assert not target.with_suffix(".bin.tmp").exists()


def test_artifact_directory_claim_fsync_failure_leaves_no_raw_namespace(
    tmp_path, monkeypatch
):
    output = tmp_path / lifecycle.REPORT_FILENAME
    lifecycle._prepare_fresh_output_path(output)
    frames = _frames()
    captures = [
        *(
            ("full_drain", ordinal, _metadata_wire(frame))
            for ordinal, frame in enumerate(frames)
        ),
        (
            "cancel_first",
            0,
            _metadata_wire(
                replace(
                    frames[0],
                    stream_id=8,
                    ownership_epoch=12,
                    first_sample_sequence=9_000_000,
                )
            ),
        ),
    ]
    manifest = lifecycle._new_metadata_artifact_manifest(captures)
    original_fsync = lifecycle.os.fsync
    planted = False

    def fail_first_fsync(descriptor):
        nonlocal planted
        if not planted:
            planted = True
            raise OSError(errno.EIO, "planted claim fsync failure")
        return original_fsync(descriptor)

    monkeypatch.setattr(lifecycle.os, "fsync", fail_first_fsync)
    with pytest.raises(lifecycle._ArtifactDirectoryClaimError):
        lifecycle._write_metadata_artifacts(output, captures, manifest)
    assert not (output.parent / lifecycle.RAW_METADATA_DIRECTORY).exists()
    residues = [
        path
        for path in output.parent.iterdir()
        if path.name.startswith(lifecycle.RAW_METADATA_ABORTED_PREFIX)
    ]
    assert len(residues) == 1
    assert list(residues[0].iterdir()) == []
    assert lifecycle.stat.S_IMODE(residues[0].stat().st_mode) == 0o700
    assert not any(
        path.name.startswith(lifecycle.RAW_METADATA_STAGING_PREFIX)
        for path in output.parent.iterdir()
    )


def test_mapped_library_sha_is_computed_in_hardware_process(tmp_path, monkeypatch):
    source = tmp_path / "libiio-source"
    build = tmp_path / "libiio-build"
    source.mkdir()
    build.mkdir()
    library = build / "libiio.so.0.25"
    library.write_bytes(b"exact mapped library bytes")
    (build / "CMakeCache.txt").write_text(
        f"CMAKE_HOME_DIRECTORY:INTERNAL={source}\n", encoding="utf-8"
    )
    digest = hashlib.sha256(library.read_bytes()).hexdigest()
    monkeypatch.setattr(lifecycle, "_mapped_libiio", lambda: [str(library)])
    monkeypatch.setenv("PLUTOSDR_FW_LIBIIO_PATH", str(library))
    monkeypatch.setenv("PLUTOSDR_FW_LIBIIO_BUILD", str(build))
    monkeypatch.setenv("PLUTOSDR_FW_LIBIIO_SOURCE", str(source))
    monkeypatch.setenv("PLUTOSDR_FW_LIBIIO_SHA256", digest)
    evidence = _attest_mapped_libiio()
    assert evidence["mapped_shared_object_sha256"] == digest
    assert evidence["runner_shared_object_sha256"] == digest


def test_wrong_pylibiio_fails_before_context_factory(tmp_path, monkeypatch):
    _stub_runner_provenance(monkeypatch)
    source = (tmp_path / "attested-fixture-libiio-source").resolve()
    pylibiio = source / "bindings/python/iio.py"
    pylibiio.parent.mkdir(parents=True)
    pylibiio.write_bytes(b"attested fixture pylibiio")
    build = tmp_path / "build"
    build.mkdir()
    library = build / "libiio.so.0.25"
    library.write_bytes(b"mapped")
    called = []

    def context_factory(_uri):
        called.append(True)
        raise AssertionError("context must not open")

    fake_iio = SimpleNamespace(
        __file__=str(tmp_path / "forged-iio.py"), Context=context_factory
    )
    monkeypatch.setattr(
        lifecycle,
        "_attest_mapped_libiio",
        lambda: {
            "source_commit": EXACT_LIBIIO_COMMIT,
            "protected_source_tag": EXACT_LIBIIO_TAG,
            "source_directory": str(source),
            "build_directory": str(build),
            "mapped_shared_objects": [str(library)],
            "mapped_shared_object": str(library),
            "mapped_shared_object_sha256": hashlib.sha256(
                library.read_bytes()
            ).hexdigest(),
            "runner_shared_object_sha256": hashlib.sha256(
                library.read_bytes()
            ).hexdigest(),
        },
    )
    monkeypatch.setenv("PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT", EXACT_LIBIIO_COMMIT)
    monkeypatch.setenv("PLUTOSDR_FW_LIBIIO_SHA256", "a" * 64)
    output = tmp_path / "private" / lifecycle.REPORT_FILENAME
    with pytest.raises(QualificationError, match="pylibiio"):
        _run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
            output_path=output,
            ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
        )
    assert called == []


def test_v5_runner_rejects_legacy_report_filename_before_context(tmp_path):
    called = []
    output = tmp_path / "muted-metadata-batch-lifecycle-v4.json"
    fake_iio = SimpleNamespace(Context=lambda _uri: called.append(True))
    with pytest.raises(QualificationError, match="v5 output filename"):
        _run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
            output_path=output,
            ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
        )
    assert called == []
    assert not output.exists()
    assert not output.parent.joinpath(lifecycle.RAW_METADATA_DIRECTORY).exists()


def test_candidate_runner_rejects_relative_identity_path_before_context(tmp_path):
    called = []
    fake_iio = SimpleNamespace(Context=lambda _uri: called.append(True))
    with pytest.raises(QualificationError, match="source manifest path.*absolute"):
        lifecycle.run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            output_path=tmp_path / lifecycle.REPORT_FILENAME,
            source_manifest_path=pathlib.Path("source/candidate.yaml"),
            artifact_index_path=tmp_path / "candidate-index.json",
            deployment_receipt_path=tmp_path / "deployment-receipt.json",
            candidate_dfu_path=tmp_path / "candidate.dfu",
        )
    assert called == []


def _write_candidate_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    path.write_bytes(payload)
    return payload


def _candidate_binding_files(
    tmp_path, *, serial=TEST_SERIAL, stage="candidate-pre-hardware"
):
    repository = pathlib.Path(lifecycle.__file__).resolve().parents[2]
    commit = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    root = tmp_path / "candidate"
    source_member = "source/tandem-agc-v8-rc4-source.yaml"
    source_path = root / source_member
    source_path.parent.mkdir(parents=True)
    source_payload = (
        repository / "manifests/tandem-agc-v8-rc4-source.yaml"
    ).read_bytes()
    source_path.write_bytes(source_payload)
    dfu_path = root / "artifact/firmware.dfu"
    dfu_path.parent.mkdir(parents=True)
    fit_payload = b"candidate-fit"
    dfu_payload = fit_payload + b"D" * 16
    dfu_path.write_bytes(dfu_payload)

    evidence_members = []
    for index, role in enumerate(REQUIRED_EVIDENCE_ROLES, 1):
        path = root / f"evidence/{role}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = f"{role}:{index}\n".encode()
        path.write_bytes(payload)
        evidence_members.append(
            {
                "role": role,
                "path": path.relative_to(root).as_posix(),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )

    harness_files = []
    for relative in lifecycle.CANDIDATE_HARNESS_PATHS:
        harness_files.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(
                    (repository / relative).read_bytes()
                ).hexdigest(),
            }
        )
    artifact_index = {
        "schema": "plutosdr-fw.tandem-release-evidence",
        "schema_version": 1,
        "stage": stage,
        "release": {
            "firmware_version": EXPECTED_FIRMWARE_VERSION,
            "kernel_version": EXPECTED_KERNEL_VERSION,
            "hardware_model": EXPECTED_HARDWARE_MODEL,
            "metadata_abi": "frame-metadata-v5",
            "tandem_agc": "request-v2",
        },
        "source": {
            "commit": commit,
            "manifest_path": source_member,
            "manifest_sha256": hashlib.sha256(source_payload).hexdigest(),
        },
        "build": {"run_id": 1234, "run_attempt": 1},
        "artifact": {
            "dfu_path": dfu_path.relative_to(root).as_posix(),
            "dfu_bytes": len(dfu_payload),
            "dfu_sha256": hashlib.sha256(dfu_payload).hexdigest(),
            "fit_bytes": len(fit_payload),
            "fit_sha256": hashlib.sha256(fit_payload).hexdigest(),
        },
        "harness": {"files": harness_files},
        "evidence": {"members": evidence_members},
    }
    index_path = root / (
        "candidate-index.json"
        if stage == "candidate-pre-hardware"
        else "final-artifact-index.json"
    )
    index_payload = _write_candidate_json(index_path, artifact_index)
    receipt = {
        "schema": "plutosdr-fw.tandem-ram-boot-receipt",
        "schema_version": 4,
        "verdict": "pass",
        "boot_mode": "ram-only",
        "artifact_index_sha256": hashlib.sha256(index_payload).hexdigest(),
        "radio": {"serial": serial},
        "artifact": {"dfu_sha256": artifact_index["artifact"]["dfu_sha256"]},
        "runtime": {
            "firmware_version": EXPECTED_FIRMWARE_VERSION,
            "hardware_model": EXPECTED_HARDWARE_MODEL,
        },
        "boot": {"pre_id": "boot-before", "post_id": "boot-after"},
        "persistent_flash": {
            "partition": "/dev/mtdblock3",
            "mtd_name": "qspi-linux",
            "bytes": 32 * 1024 * 1024,
            "pre_sha256": "7" * 64,
            "post_sha256": "7" * 64,
            "unchanged": True,
        },
        "safety": {
            "final_tx_muted": True,
            "final_dds_disabled": True,
            "final_dac_selectors_zero": True,
            "final_tandem_state": "IDLE",
            "final_fifo_level": 0,
            "final_fault_flags": 0,
        },
        "timestamps": {"started_unix_ns": 100, "completed_unix_ns": 200},
        "topology": {
            "usb_port": "3-8",
            "pre_sysfs_path": "/sys/bus/usb/devices/3-8",
            "dfu_sysfs_path": "/sys/bus/usb/devices/3-8",
            "post_sysfs_path": "/sys/bus/usb/devices/3-8",
            "network_interface": "enx001122334455",
        },
        "host_route": {
            "destination": "192.168.2.1/32",
            "interface": "enx001122334455",
            "source": "192.168.2.10",
            "release_verified": True,
        },
        "commands": [
            {
                "phase": "request-ram-mode",
                "argv": [
                    "sshpass",
                    "-f",
                    "/private/ssh-password",
                    "ssh",
                    "-F",
                    "/dev/null",
                    "-B",
                    "enx001122334455",
                    "-o",
                    "BatchMode=no",
                    "-o",
                    "NumberOfPasswordPrompts=1",
                    "-o",
                    "PreferredAuthentications=password",
                    "-o",
                    "PasswordAuthentication=yes",
                    "-o",
                    "PubkeyAuthentication=no",
                    "-o",
                    "KbdInteractiveAuthentication=no",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-o",
                    "GlobalKnownHostsFile=/dev/null",
                    "-o",
                    "CheckHostIP=no",
                    "-o",
                    "UpdateHostKeys=no",
                    "root@192.168.2.1",
                    "/usr/sbin/device_reboot ram",
                ],
            },
            {
                "phase": "download-firmware-to-ram",
                "argv": [
                    "dfu-util",
                    "-d",
                    "0456:b673,0456:b674",
                    "-p",
                    "3-8",
                    "-a",
                    "firmware.dfu",
                    "-D",
                    "/proc/self/fd/9",
                ],
            },
            {
                "phase": "detach-into-downloaded-image",
                "argv": [
                    "dfu-util",
                    "-d",
                    "0456:b673,0456:b674",
                    "-p",
                    "3-8",
                    "-a",
                    "firmware.dfu",
                    "-e",
                ],
            },
        ],
    }
    legacy_receipt_path = root / "deployment-receipt.json"
    _write_candidate_json(legacy_receipt_path, receipt)
    utility = build_utility_deployment_bundle(
        root=root,
        artifact_index_path=index_path,
        artifact_index=artifact_index,
        artifact_index_payload=index_payload,
        serial=serial,
        expected_current_firmware="v0.41-plutoplus-spf-tandem-agc-v8-rc3",
    )
    receipt_path = utility["receipt"]
    provenance = {
        "host_runner_repository_commit": commit,
        "host_runner_repository": str(repository),
        "python_module_sha256": harness_files[3]["sha256"],
        "shell_runner_sha256": harness_files[0]["sha256"],
        "metadata_abi_sha256": harness_files[2]["sha256"],
        "candidate_binding_sha256": harness_files[1]["sha256"],
    }
    return {
        "source_manifest_path": source_path,
        "artifact_index_path": index_path,
        "deployment_receipt_path": receipt_path,
        "candidate_dfu_path": dfu_path,
        "serial": serial,
        "runner_provenance": provenance,
    }


def test_candidate_lineage_binds_arbitrary_serial_and_exact_inputs(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        lifecycle, "_attest_candidate_binding", _REAL_ATTEST_CANDIDATE_BINDING
    )
    inputs = _candidate_binding_files(tmp_path, serial="R17-serial")
    result = _REAL_ATTEST_CANDIDATE_BINDING(**inputs)
    assert result["serial"] == "R17-serial"
    assert result["firmware_version"] == EXPECTED_FIRMWARE_VERSION
    assert result["evidence_member_count"] == len(REQUIRED_EVIDENCE_ROLES)
    assert result["evidence_members_verified"] is True
    assert (
        result["artifact_index_sha256"]
        == hashlib.sha256(inputs["artifact_index_path"].read_bytes()).hexdigest()
    )
    assert (
        result["deployment_receipt_sha256"]
        == hashlib.sha256(inputs["deployment_receipt_path"].read_bytes()).hexdigest()
    )


def test_final_artifact_stage_is_accepted_for_full_final_campaign(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        lifecycle, "_attest_candidate_binding", _REAL_ATTEST_CANDIDATE_BINDING
    )
    inputs = _candidate_binding_files(tmp_path, stage="final-pre-confirmation")
    result = _REAL_ATTEST_CANDIDATE_BINDING(**inputs)

    assert result["artifact_index"]["stage"] == "final-pre-confirmation"


@pytest.mark.parametrize(
    "plant",
    [
        "receipt",
        "index-receipt-binding",
        "artifact",
        "manifest",
        "source-lock",
        "harness",
        "serial",
        "evidence",
    ],
)
def test_candidate_lineage_rejects_planted_identity_or_byte_failure(
    tmp_path, monkeypatch, plant
):
    monkeypatch.setattr(
        lifecycle, "_attest_candidate_binding", _REAL_ATTEST_CANDIDATE_BINDING
    )
    inputs = _candidate_binding_files(tmp_path)
    index_path = inputs["artifact_index_path"]
    receipt_path = inputs["deployment_receipt_path"]
    index = json.loads(index_path.read_text())
    receipt = json.loads(receipt_path.read_text())

    def rewrite_index():
        payload = _write_candidate_json(index_path, index)
        candidate_path = receipt_path.parent / "release-candidate-plan.json"
        operation_path = receipt_path.parent / "operation-plan.json"
        candidate = json.loads(candidate_path.read_text())
        candidate["artifact_index"] = {
            "path": str(index_path.absolute()),
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        write_private(candidate_path, candidate)
        operation = json.loads(operation_path.read_text())
        operation["candidate_plan"] = identity(candidate_path, candidate)
        write_private(operation_path, operation)
        receipt["candidate_plan"] = identity(candidate_path, candidate)
        receipt["operation_plan"] = identity(operation_path, operation)
        write_private(receipt_path, receipt)

    if plant == "receipt":
        receipt["post_runtime"]["safe_state"]["tx_gain_db"][0] = 0.0
        write_private(receipt_path, receipt)
    elif plant == "index-receipt-binding":
        index["build"]["run_attempt"] = 2
        _write_candidate_json(index_path, index)
    elif plant == "artifact":
        inputs["candidate_dfu_path"].write_bytes(
            inputs["candidate_dfu_path"].read_bytes() + b"x"
        )
    elif plant == "manifest":
        inputs["source_manifest_path"].write_bytes(
            inputs["source_manifest_path"].read_bytes() + b"\n# planted\n"
        )
    elif plant == "source-lock":
        index["source"]["commit"] = "0" * 40
        rewrite_index()
    elif plant == "harness":
        index["harness"]["files"][0]["sha256"] = "0" * 64
        rewrite_index()
    elif plant == "serial":
        inputs["serial"] = "different-serial"
    else:
        member = (
            inputs["artifact_index_path"].parent
            / index["evidence"]["members"][0]["path"]
        )
        member.write_bytes(member.read_bytes() + b"x")

    with pytest.raises(
        QualificationError, match="candidate|receipt|DFU|manifest|harness|evidence"
    ):
        _REAL_ATTEST_CANDIDATE_BINDING(**inputs)


def test_wrong_protected_libiio_tag_fails_before_context_factory(tmp_path, monkeypatch):
    _stub_runner_provenance(monkeypatch)
    source = (tmp_path / "attested-fixture-libiio-source").resolve()
    pylibiio = source / "bindings/python/iio.py"
    pylibiio.parent.mkdir(parents=True)
    pylibiio.write_bytes(b"attested fixture pylibiio")
    build = tmp_path / "build"
    build.mkdir()
    library = build / "libiio.so.0.25"
    library.write_bytes(b"mapped")
    called = []

    def context_factory(_uri):
        called.append(True)
        raise AssertionError("context must not open")

    fake_iio = SimpleNamespace(
        __file__=str(source / "bindings/python/iio.py"), Context=context_factory
    )
    digest = hashlib.sha256(library.read_bytes()).hexdigest()
    monkeypatch.setattr(
        lifecycle,
        "_attest_mapped_libiio",
        lambda: {
            "source_commit": EXACT_LIBIIO_COMMIT,
            "protected_source_tag": EXACT_LIBIIO_TAG,
            "source_directory": str(source),
            "build_directory": str(build),
            "mapped_shared_objects": [str(library)],
            "mapped_shared_object": str(library),
            "mapped_shared_object_sha256": digest,
            "runner_shared_object_sha256": digest,
        },
    )

    def wrong_tag_git(_repository, *arguments):
        if arguments == ("rev-parse", "HEAD"):
            return f"{EXACT_LIBIIO_COMMIT}\n".encode()
        if arguments == (
            "rev-parse",
            f"refs/tags/{EXACT_LIBIIO_TAG}^{{commit}}",
        ):
            return ("0" * 40 + "\n").encode()
        if arguments == ("status", "--porcelain", "--untracked-files=no"):
            return b""
        raise AssertionError(arguments)

    monkeypatch.setattr(lifecycle, "_git_bytes", wrong_tag_git)
    monkeypatch.setenv("PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT", EXACT_LIBIIO_COMMIT)
    monkeypatch.setenv("PLUTOSDR_FW_LIBIIO_SHA256", digest)
    output = tmp_path / "private" / lifecycle.REPORT_FILENAME
    with pytest.raises(QualificationError, match="source graph"):
        _run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
            output_path=output,
            ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
        )
    assert called == []


def _set_integration_runner_environment(monkeypatch):
    repository = pathlib.Path(lifecycle.__file__).resolve().parents[2]
    commit = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    paths = {
        "MODULE": repository / "tests/radio_hardware/muted_metadata_batch_lifecycle.py",
        "SHELL": repository / "scripts/run_muted_metadata_batch_lifecycle_hardware.sh",
        "METADATA_ABI": repository / "tests/radio_hardware/metadata_abi.py",
        "CANDIDATE_BINDING": (repository / "tests/radio_hardware/candidate_binding.py"),
    }
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_COMMIT", commit)
    for role, path in paths.items():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        monkeypatch.setenv(f"PLUTOSDR_FW_RUNNER_{role}_SHA256", digest)
        monkeypatch.setenv(f"PLUTOSDR_FW_RUNNER_{role}_HEAD_SHA256", digest)
        if role != "MODULE":
            monkeypatch.setenv(f"PLUTOSDR_FW_RUNNER_{role}_PATH", str(path))


def test_tracked_dirty_runner_tree_fails_before_context_factory(tmp_path, monkeypatch):
    _set_integration_runner_environment(monkeypatch)
    monkeypatch.setenv("PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT", EXACT_LIBIIO_COMMIT)
    monkeypatch.setenv("PLUTOSDR_FW_LIBIIO_SHA256", "a" * 64)
    monkeypatch.setattr(
        lifecycle,
        "_attest_host_libiio",
        lambda _module: {
            "source_commit": EXACT_LIBIIO_COMMIT,
            "protected_source_tag": EXACT_LIBIIO_TAG,
        },
    )
    original_git = lifecycle._git_bytes

    def dirty_runner_tree(repository, *arguments):
        if arguments == ("status", "--porcelain", "--untracked-files=no"):
            return b" M README.md\n"
        return original_git(repository, *arguments)

    monkeypatch.setattr(lifecycle, "_git_bytes", dirty_runner_tree)
    context_calls = []
    fake_iio = SimpleNamespace(
        Context=lambda _uri: context_calls.append(True), scan_contexts=dict
    )
    output = tmp_path / "evidence" / lifecycle.REPORT_FILENAME
    with pytest.raises(QualificationError, match="tracked changes"):
        _run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
            output_path=output,
            ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
        )
    assert context_calls == []


def _integration_run_components(tmp_path, monkeypatch):
    source = (tmp_path / "attested-fixture-libiio-source").resolve()
    pylibiio = source / "bindings/python/iio.py"
    pylibiio.parent.mkdir(parents=True)
    pylibiio.write_bytes(b"attested fixture pylibiio")
    build = tmp_path / "libiio-build"
    build.mkdir()
    library = build / "libiio.so.0.25"
    library.write_bytes(b"exact end-to-end fixture libiio")
    library_sha = hashlib.sha256(library.read_bytes()).hexdigest()
    (build / "CMakeCache.txt").write_text(
        f"CMAKE_HOME_DIRECTORY:INTERNAL={source}\n", encoding="utf-8"
    )
    host_libiio = {
        "source_commit": EXACT_LIBIIO_COMMIT,
        "protected_source_tag": EXACT_LIBIIO_TAG,
        "source_directory": str(source),
        "build_directory": str(build),
        "mapped_shared_objects": [str(library)],
        "mapped_shared_object": str(library),
        "mapped_shared_object_sha256": library_sha,
        "runner_shared_object_sha256": library_sha,
        "pylibiio_file": str(source / "bindings/python/iio.py"),
    }
    monkeypatch.setattr(
        lifecycle, "_attest_host_libiio", lambda _iio_module: host_libiio
    )
    monkeypatch.setenv("PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT", EXACT_LIBIIO_COMMIT)
    monkeypatch.setenv("PLUTOSDR_FW_LIBIIO_SHA256", library_sha)
    _set_integration_runner_environment(monkeypatch)

    context_record, phy, tx, tandem, writes = _hardware_state()
    state = _IntegrationState(tandem, phy=phy, writes=writes)
    rx = _IntegrationRx(state)
    context = _IntegrationContext(
        context_record.attrs,
        {
            "ad9361-phy": phy,
            "cf-ad9361-lpc": rx,
            "cf-ad9361-dds-core-lpc": tx,
            "tandem-agc": tandem,
        },
    )
    fake_iio = _IntegrationIio(context, source / "bindings/python/iio.py")
    lock_path = tmp_path / "radio.lock"
    monkeypatch.setattr(lifecycle, "_lock_path", lambda _serial: lock_path)
    output = tmp_path / "evidence" / lifecycle.REPORT_FILENAME
    return fake_iio, context, state, output, lock_path


def test_run_hardware_fake_end_to_end_persists_closed_valid_pass(tmp_path, monkeypatch):
    fake_iio, context, state, output, lock_path = _integration_run_components(
        tmp_path, monkeypatch
    )

    report = _run_hardware(
        fake_iio,
        serial=TEST_SERIAL,
        firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
        output_path=output,
        ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
    )

    assert report == json.loads(output.read_text(encoding="utf-8"))
    validate_durable_pass_report(report)
    assert report["verdict"] == "PASS"
    assert report["release_pass_eligible"] is False
    assert report["hardware_qualified"] is False
    assert report["schema"] == lifecycle.SCHEMA
    assert output.name == lifecycle.REPORT_FILENAME
    assert (
        report["cancel_lifecycle"]["first_returned_cached_frame"][
            "ad9361_temperature_mdeg_c"
        ]
        is None
    )
    assert report["temperature_evidence"]["cancel_first"]["producer_omitted"] is True
    assert context.closed is True
    assert context.timeout_ms == 10_000
    assert state.active_buffer is None
    assert state.open_count == state.close_count == 3
    assert all(buffer.closed for buffer in state.buffers)
    assert state.kernel_buffer_counts == [8, 8]
    artifact_directory = output.parent / lifecycle.RAW_METADATA_DIRECTORY
    assert len(list(artifact_directory.iterdir())) == lifecycle.RAW_METADATA_FILE_COUNT
    with lock_path.open("r+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_UN)


def test_cancel_temperature_failure_is_typed_non_authorizing_and_promotes_no_raw(
    tmp_path, monkeypatch
):
    fake_iio, context, state, output, lock_path = _integration_run_components(
        tmp_path, monkeypatch
    )
    state.temperature_overrides[(2, 0)] = lifecycle.MAXIMUM_TEMPERATURE_MDEG_C + 1

    with pytest.raises(QualificationError, match="cancel_first frame 0"):
        _run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
            output_path=output,
            ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
        )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema"] == lifecycle.SCHEMA
    assert report["verdict"] == "FAIL"
    assert report["release_pass_eligible"] is False
    assert report["hardware_qualified"] is False
    assert "cancel_first frame 0" in report["error"]["message"]
    assert "metadata_artifacts" not in report
    assert "temperature_evidence" not in report
    assert not (output.parent / lifecycle.RAW_METADATA_DIRECTORY).exists()
    assert context.closed is True
    assert state.active_buffer is None
    with lock_path.open("r+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_UN)


def test_close_drift_is_remuted_before_rx_write_or_next_buffer_open(
    tmp_path, monkeypatch
):
    fake_iio, context, state, output, _lock_path = _integration_run_components(
        tmp_path, monkeypatch
    )
    state.flip_tx_on_close = {1, 2, 3}

    report = _run_hardware(
        fake_iio,
        serial=TEST_SERIAL,
        firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
        output_path=output,
        ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
    )

    assert report["verdict"] == "PASS"
    labels = [label for label, _value in state.writes]
    for session, next_boundary in ((1, "buffer2:open"), (2, "buffer3:open")):
        close_index = labels.index(f"buffer{session}:close")
        boundary_index = labels.index(next_boundary, close_index + 1)
        mute_index = labels.index("tx0:hardwaregain", close_index + 1)
        assert close_index < mute_index < boundary_index
        assert not any(
            label.startswith("rx") for label in labels[close_index + 1 : mute_index]
        )
    final_close = labels.index("buffer3:close")
    final_mute = labels.index("tx0:hardwaregain", final_close + 1)
    final_rx_write = next(
        index
        for index in range(final_close + 1, len(labels))
        if labels[index].startswith("rx")
    )
    assert final_close < final_mute < final_rx_write
    assert context.closed is True


def test_second_sidecar_failure_rolls_back_pass_namespace(tmp_path, monkeypatch):
    fake_iio, context, state, output, _lock_path = _integration_run_components(
        tmp_path, monkeypatch
    )
    original_atomic_bytes = lifecycle._atomic_bytes
    calls = 0

    def fail_second_sidecar(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError(errno.EIO, "planted second sidecar failure")
        return original_atomic_bytes(*args, **kwargs)

    monkeypatch.setattr(lifecycle, "_atomic_bytes", fail_second_sidecar)
    monkeypatch.setattr(
        lifecycle.os,
        "unlink",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("rollback must not unlink raceable child names")
        ),
    )
    with pytest.raises(OSError, match="second sidecar"):
        _run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
            output_path=output,
            ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
        )
    report = json.loads(output.read_bytes())
    assert report["verdict"] == "FAIL"
    assert "metadata_artifacts" not in report
    assert not (output.parent / lifecycle.RAW_METADATA_DIRECTORY).exists()
    residues = [
        path
        for path in output.parent.iterdir()
        if path.name.startswith(lifecycle.RAW_METADATA_ABORTED_PREFIX)
    ]
    assert len(residues) == 1
    assert [path.name for path in residues[0].iterdir()] == [
        "full-frame-0000.metadata.bin"
    ]
    assert context.closed is True
    assert state.active_buffer is None


def test_staging_directory_swap_after_preopen_stat_is_rejected(tmp_path, monkeypatch):
    fake_iio, context, state, output, _lock_path = _integration_run_components(
        tmp_path, monkeypatch
    )
    original_open = lifecycle.os.open
    swapped = False
    external_directory = None
    moved_owned_directory = output.parent / "created-staging-moved"

    def swap_staging_before_open(path, flags, *args, **kwargs):
        nonlocal external_directory, swapped
        if (
            not swapped
            and isinstance(path, str)
            and path.startswith(lifecycle.RAW_METADATA_STAGING_PREFIX)
            and flags & getattr(lifecycle.os, "O_DIRECTORY", 0)
        ):
            swapped = True
            external_directory = output.parent / path
            external_directory.rename(moved_owned_directory)
            external_directory.mkdir(mode=0o700)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(lifecycle.os, "open", swap_staging_before_open)
    with pytest.raises(QualificationError, match="staging claim"):
        _run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
            output_path=output,
            ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
        )
    assert external_directory is not None
    assert list(external_directory.iterdir()) == []
    assert list(moved_owned_directory.iterdir()) == []
    assert not (output.parent / lifecycle.RAW_METADATA_DIRECTORY).exists()
    assert json.loads(output.read_bytes())["verdict"] == "FAIL"
    assert context.closed is True
    assert state.active_buffer is None


def test_final_metadata_directory_promotion_never_clobbers_raced_namespace(
    tmp_path, monkeypatch
):
    fake_iio, context, state, output, _lock_path = _integration_run_components(
        tmp_path, monkeypatch
    )
    original_rename = lifecycle._rename_noreplace_at
    planted = b"external canonical raw namespace"
    raced = False

    def race_canonical_before_promotion(old_fd, old_name, new_fd, new_name):
        nonlocal raced
        if (
            not raced
            and old_name.startswith(lifecycle.RAW_METADATA_STAGING_PREFIX)
            and new_name == lifecycle.RAW_METADATA_DIRECTORY
        ):
            raced = True
            canonical = output.parent / lifecycle.RAW_METADATA_DIRECTORY
            canonical.mkdir(mode=0o700)
            (canonical / "external.bin").write_bytes(planted)
        return original_rename(old_fd, old_name, new_fd, new_name)

    monkeypatch.setattr(
        lifecycle, "_rename_noreplace_at", race_canonical_before_promotion
    )
    with pytest.raises(QualificationError, match="raced or reused"):
        _run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
            output_path=output,
            ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
        )
    canonical = output.parent / lifecycle.RAW_METADATA_DIRECTORY
    assert [path.name for path in canonical.iterdir()] == ["external.bin"]
    assert (canonical / "external.bin").read_bytes() == planted
    assert json.loads(output.read_bytes())["verdict"] == "FAIL"
    residues = [
        path
        for path in output.parent.iterdir()
        if path.name.startswith(lifecycle.RAW_METADATA_ABORTED_PREFIX)
    ]
    assert len(residues) == 1
    assert len(list(residues[0].iterdir())) == lifecycle.RAW_METADATA_FILE_COUNT
    assert not any(
        path.name.startswith(lifecycle.RAW_METADATA_STAGING_PREFIX)
        for path in output.parent.iterdir()
    )
    assert context.closed is True
    assert state.active_buffer is None


def test_final_report_swap_preserves_external_and_rolls_back_sidecars(
    tmp_path, monkeypatch
):
    fake_iio, context, state, output, _lock_path = _integration_run_components(
        tmp_path, monkeypatch
    )
    original_atomic_json = lifecycle._atomic_json
    planted = b"external final-report winner"
    swapped = False

    def swap_before_final_rewrite(path, report, **kwargs):
        nonlocal swapped
        if (
            not swapped
            and report.get("verdict") == "PASS"
            and kwargs.get("replace_existing") is True
        ):
            swapped = True
            output.unlink()
            output.write_bytes(planted)
        return original_atomic_json(path, report, **kwargs)

    monkeypatch.setattr(lifecycle, "_atomic_json", swap_before_final_rewrite)
    with pytest.raises(QualificationError, match="rewrite changed|without replacing"):
        _run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
            output_path=output,
            ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
        )
    assert output.read_bytes() == planted
    assert not (output.parent / lifecycle.RAW_METADATA_DIRECTORY).exists()
    assert context.closed is True
    assert state.active_buffer is None


def test_late_completed_raw_directory_move_demotes_durable_pass(tmp_path, monkeypatch):
    fake_iio, context, state, output, _lock_path = _integration_run_components(
        tmp_path, monkeypatch
    )
    original_verify = lifecycle._verify_claimed_output_namespace
    moved = output.parent / "raw-metadata-moved-after-pass-reread"
    planted = False

    def move_raw_during_final_verify(*args, **kwargs):
        nonlocal planted
        if not planted and kwargs.get("require_raw_absent") is False:
            planted = True
            (output.parent / lifecycle.RAW_METADATA_DIRECTORY).rename(moved)
        return original_verify(*args, **kwargs)

    monkeypatch.setattr(
        lifecycle, "_verify_claimed_output_namespace", move_raw_during_final_verify
    )
    with pytest.raises(QualificationError, match="metadata artifact ownership"):
        _run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
            output_path=output,
            ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
        )
    durable = json.loads(output.read_bytes())
    assert durable["verdict"] == "FAIL"
    assert "metadata_artifacts" not in durable
    assert not (output.parent / lifecycle.RAW_METADATA_DIRECTORY).exists()
    assert len(list(moved.iterdir())) == lifecycle.RAW_METADATA_FILE_COUNT
    assert context.closed is True
    assert state.active_buffer is None


@pytest.mark.parametrize("target", ["raw", "parent"])
def test_evidence_directory_descriptor_close_failure_demotes_pass(
    tmp_path, monkeypatch, target
):
    fake_iio, context, state, output, _lock_path = _integration_run_components(
        tmp_path, monkeypatch
    )
    original_close = lifecycle.os.close
    planted = False

    def fail_selected_directory_close(descriptor):
        nonlocal planted
        selected_path = (
            output.parent / lifecycle.RAW_METADATA_DIRECTORY
            if target == "raw"
            else output.parent
        )
        try:
            descriptor_stat = lifecycle.os.fstat(descriptor)
            selected_stat = selected_path.stat(follow_symlinks=False)
            selected = (descriptor_stat.st_dev, descriptor_stat.st_ino) == (
                selected_stat.st_dev,
                selected_stat.st_ino,
            )
        except OSError:
            selected = False
        if not planted and selected and output.exists():
            planted = True
            original_close(descriptor)
            raise OSError(errno.EIO, f"planted {target} descriptor close failure")
        return original_close(descriptor)

    monkeypatch.setattr(lifecycle.os, "close", fail_selected_directory_close)
    with pytest.raises((OSError, QualificationError), match="descriptor"):
        _run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
            output_path=output,
            ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
        )
    durable = json.loads(output.read_bytes())
    assert durable["verdict"] == "FAIL"
    assert "metadata_artifacts" not in durable
    assert not (output.parent / lifecycle.RAW_METADATA_DIRECTORY).exists()
    residues = [
        path
        for path in output.parent.iterdir()
        if path.name.startswith(lifecycle.RAW_METADATA_ABORTED_PREFIX)
    ]
    assert len(residues) == 1
    assert len(list(residues[0].iterdir())) == lifecycle.RAW_METADATA_FILE_COUNT
    assert context.closed is True
    assert state.active_buffer is None


@pytest.mark.parametrize("plant", ["cleanup", "context-close"])
def test_post_capture_failure_promotes_no_metadata_artifacts(
    tmp_path, monkeypatch, plant
):
    fake_iio, context, state, output, _lock_path = _integration_run_components(
        tmp_path, monkeypatch
    )
    if plant == "cleanup":
        original_cleanup = lifecycle._cleanup_live_state

        def fail_cleanup(*args, **kwargs):
            original_cleanup(*args, **kwargs)
            kwargs["cleanup_errors"].append(
                lifecycle._error_record(OSError(errno.EIO, "planted cleanup failure"))
            )

        monkeypatch.setattr(lifecycle, "_cleanup_live_state", fail_cleanup)
    else:
        original_close = lifecycle.close_iio_object

        def fail_context_close(value):
            if value is context:
                context.close()
                raise OSError(errno.EIO, "planted context close failure")
            return original_close(value)

        monkeypatch.setattr(lifecycle, "close_iio_object", fail_context_close)
    with pytest.raises(QualificationError, match="cleanup"):
        _run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
            output_path=output,
            ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
        )
    report = json.loads(output.read_bytes())
    assert report["verdict"] == "FAIL"
    assert "metadata_artifacts" not in report
    assert not (output.parent / lifecycle.RAW_METADATA_DIRECTORY).exists()
    assert context.closed is True
    assert state.active_buffer is None


def test_output_parent_replacement_cannot_receive_report_or_sidecars(
    tmp_path, monkeypatch
):
    fake_iio, context, state, output, _lock_path = _integration_run_components(
        tmp_path, monkeypatch
    )
    original_verify = lifecycle._verify_claimed_output_namespace
    calls = 0
    original_parent = output.parent
    moved_parent = output.parent.with_name(output.parent.name + "-moved")

    def replace_parent_before_final_verify(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            original_parent.rename(moved_parent)
            original_parent.mkdir(mode=0o700)
        return original_verify(*args, **kwargs)

    monkeypatch.setattr(
        lifecycle,
        "_verify_claimed_output_namespace",
        replace_parent_before_final_verify,
    )
    with pytest.raises(QualificationError, match="parent pathname"):
        _run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
            output_path=output,
            ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
        )
    assert not output.exists()
    assert not (original_parent / lifecycle.RAW_METADATA_DIRECTORY).exists()
    moved_report = moved_parent / lifecycle.REPORT_FILENAME
    assert json.loads(moved_report.read_bytes())["verdict"] == "FAIL"
    assert context.closed is True
    assert state.active_buffer is None


@pytest.mark.parametrize("plant", ["report", "sidecar"])
def test_post_context_freshness_race_never_overwrites_evidence(
    tmp_path, monkeypatch, plant
):
    fake_iio, context, state, output, _lock_path = _integration_run_components(
        tmp_path, monkeypatch
    )
    original_writer = lifecycle._write_metadata_artifacts
    planted_path = output
    planted_bytes = b"external post-context evidence"

    def plant_before_first_sidecar(*args, **kwargs):
        nonlocal planted_path
        if plant == "report":
            output.unlink()
        else:
            directory = output.parent / lifecycle.RAW_METADATA_DIRECTORY
            directory.mkdir()
            planted_path = directory / "full-frame-0000.metadata.bin"
        planted_path.write_bytes(planted_bytes)
        return original_writer(*args, **kwargs)

    monkeypatch.setattr(
        lifecycle, "_write_metadata_artifacts", plant_before_first_sidecar
    )
    with pytest.raises(QualificationError, match="owned|raced|claim"):
        _run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
            output_path=output,
            ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
        )
    assert planted_path.read_bytes() == planted_bytes
    assert context.closed is True
    assert state.active_buffer is None
    assert state.open_count == state.close_count == 3
    if plant == "sidecar":
        assert json.loads(output.read_text(encoding="utf-8"))["verdict"] == "FAIL"
        assert list((output.parent / lifecycle.RAW_METADATA_DIRECTORY).iterdir()) == [
            planted_path
        ]
    else:
        assert not (output.parent / lifecycle.RAW_METADATA_DIRECTORY).exists()


def _stub_precontext_provenance(monkeypatch):
    monkeypatch.setenv("PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT", EXACT_LIBIIO_COMMIT)
    monkeypatch.setenv("PLUTOSDR_FW_LIBIIO_SHA256", "a" * 64)
    monkeypatch.setattr(
        lifecycle,
        "_attest_host_libiio",
        lambda _module: {
            "source_commit": EXACT_LIBIIO_COMMIT,
            "protected_source_tag": EXACT_LIBIIO_TAG,
        },
    )
    monkeypatch.setattr(
        lifecycle,
        "_attest_runner_provenance",
        lambda: {
            "host_runner_repository_commit": "a" * 40,
            "host_runner_repository": str(
                pathlib.Path(lifecycle.__file__).resolve().parents[2]
            ),
        },
    )


def test_report_namespace_is_claimed_before_context_factory(tmp_path, monkeypatch):
    _stub_precontext_provenance(monkeypatch)
    output = tmp_path / "evidence" / lifecycle.REPORT_FILENAME
    lock_path = tmp_path / "radio.lock"
    context_calls = []
    fake_iio = SimpleNamespace(
        Context=lambda _uri: context_calls.append(True), scan_contexts=dict
    )
    monkeypatch.setattr(lifecycle, "_open_lock", lambda _serial: lock_path.open("a+"))
    original_atomic = lifecycle._atomic_json
    planted = False

    def race_report_claim(path, report, **kwargs):
        nonlocal planted
        if not planted:
            planted = True
            output.write_bytes(b"external winner")
        return original_atomic(path, report, **kwargs)

    monkeypatch.setattr(lifecycle, "_atomic_json", race_report_claim)
    with pytest.raises(QualificationError, match="without replacing"):
        _run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
            output_path=output,
            ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
        )
    assert output.read_bytes() == b"external winner"
    assert context_calls == []
    assert not (output.parent / lifecycle.RAW_METADATA_DIRECTORY).exists()


def test_receipt_attestation_failure_precedes_context_factory(tmp_path, monkeypatch):
    _stub_precontext_provenance(monkeypatch)
    context_calls = []
    fake_iio = SimpleNamespace(
        Context=lambda _uri: context_calls.append(True), scan_contexts=dict
    )
    monkeypatch.setattr(
        lifecycle,
        "_attest_candidate_binding",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            QualificationError("planted malformed RAM receipt")
        ),
    )
    output = tmp_path / "evidence" / lifecycle.REPORT_FILENAME
    with pytest.raises(QualificationError, match="malformed RAM receipt"):
        _run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
            output_path=output,
            ram_boot_receipt_path=tmp_path / "missing-receipt.json",
        )
    assert context_calls == []
    assert not output.exists()


def test_post_lock_freshness_recheck_preserves_existing_winner_evidence(
    tmp_path, monkeypatch
):
    _stub_precontext_provenance(monkeypatch)
    output = tmp_path / "evidence" / lifecycle.REPORT_FILENAME
    lock_path = tmp_path / "radio.lock"
    context_calls = []
    fake_iio = SimpleNamespace(
        Context=lambda _uri: context_calls.append(True),
        scan_contexts=dict,
    )

    def open_after_winner_promotion(_serial):
        output.write_bytes(b"immutable winner evidence")
        return lock_path.open("a+", encoding="utf-8")

    monkeypatch.setattr(lifecycle, "_open_lock", open_after_winner_promotion)
    with pytest.raises(QualificationError, match="fresh"):
        _run_hardware(
            fake_iio,
            serial=TEST_SERIAL,
            firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
            output_path=output,
            ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
        )
    assert output.read_bytes() == b"immutable winner evidence"
    assert context_calls == []
    assert not (output.parent / lifecycle.RAW_METADATA_DIRECTORY).exists()


def test_lock_loser_never_writes_requested_evidence(tmp_path, monkeypatch):
    _stub_precontext_provenance(monkeypatch)
    output = tmp_path / "evidence" / lifecycle.REPORT_FILENAME
    lock_path = tmp_path / "radio.lock"
    lock_path.touch()
    winner_lock = lock_path.open("r+", encoding="utf-8")
    fcntl.flock(winner_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    context_calls = []
    fake_iio = SimpleNamespace(
        Context=lambda _uri: context_calls.append(True),
        scan_contexts=dict,
    )
    monkeypatch.setattr(
        lifecycle,
        "_open_lock",
        lambda _serial: lock_path.open("r+", encoding="utf-8"),
    )
    try:
        with pytest.raises(QualificationError, match="lock is held"):
            _run_hardware(
                fake_iio,
                serial=TEST_SERIAL,
                firmware_pattern=EXPECTED_FIRMWARE_PATTERN,
                output_path=output,
                ram_boot_receipt_path=tmp_path / "ram-boot-receipt.json",
            )
    finally:
        fcntl.flock(winner_lock, fcntl.LOCK_UN)
        winner_lock.close()
    assert not output.exists()
    assert not output.with_suffix(".json.tmp").exists()
    assert not (output.parent / lifecycle.RAW_METADATA_DIRECTORY).exists()
    assert context_calls == []


def test_runner_source_sha_is_computed_in_hardware_process(tmp_path, monkeypatch):
    module_path = lifecycle.pathlib.Path(lifecycle.__file__).resolve()
    repository = module_path.parents[2]
    shell = repository / "scripts/run_muted_metadata_batch_lifecycle_hardware.sh"
    metadata_abi_path = module_path.parent / "metadata_abi.py"
    candidate_binding_path = module_path.parent / "candidate_binding.py"
    module_sha = hashlib.sha256(module_path.read_bytes()).hexdigest()
    shell_sha = hashlib.sha256(shell.read_bytes()).hexdigest()
    metadata_abi_sha = hashlib.sha256(metadata_abi_path.read_bytes()).hexdigest()
    candidate_binding_sha = hashlib.sha256(
        candidate_binding_path.read_bytes()
    ).hexdigest()
    commit = "a" * 40
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_COMMIT", commit)
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_MODULE_SHA256", module_sha)
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_MODULE_HEAD_SHA256", module_sha)
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_SHELL_SHA256", shell_sha)
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_SHELL_HEAD_SHA256", shell_sha)
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_SHELL_PATH", str(shell))
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_METADATA_ABI_SHA256", metadata_abi_sha)
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_METADATA_ABI_HEAD_SHA256", metadata_abi_sha)
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_METADATA_ABI_PATH", str(metadata_abi_path))
    monkeypatch.setenv(
        "PLUTOSDR_FW_RUNNER_CANDIDATE_BINDING_SHA256", candidate_binding_sha
    )
    monkeypatch.setenv(
        "PLUTOSDR_FW_RUNNER_CANDIDATE_BINDING_HEAD_SHA256", candidate_binding_sha
    )
    monkeypatch.setenv(
        "PLUTOSDR_FW_RUNNER_CANDIDATE_BINDING_PATH", str(candidate_binding_path)
    )

    def fake_git(_repository, *arguments):
        if arguments == ("rev-parse", "HEAD"):
            return f"{commit}\n".encode()
        if arguments == ("status", "--porcelain", "--untracked-files=no"):
            return b""
        if arguments[0] == "show":
            relative = arguments[1].split(":", 1)[1]
            return (repository / relative).read_bytes()
        raise AssertionError(arguments)

    monkeypatch.setattr(lifecycle, "_git_bytes", fake_git)
    evidence = _attest_runner_provenance()
    assert evidence["python_module_sha256"] == module_sha
    assert evidence["shell_runner_sha256"] == shell_sha
    assert evidence["metadata_abi_sha256"] == metadata_abi_sha
    assert evidence["candidate_binding_sha256"] == candidate_binding_sha


def test_runner_rejects_metadata_abi_mutation(tmp_path, monkeypatch):
    module_path = lifecycle.pathlib.Path(lifecycle.__file__).resolve()
    repository = module_path.parents[2]
    shell = repository / "scripts/run_muted_metadata_batch_lifecycle_hardware.sh"
    metadata_abi_path = module_path.parent / "metadata_abi.py"
    candidate_binding_path = module_path.parent / "candidate_binding.py"
    commit = "a" * 40
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_COMMIT", commit)
    monkeypatch.setenv(
        "PLUTOSDR_FW_RUNNER_MODULE_SHA256",
        hashlib.sha256(module_path.read_bytes()).hexdigest(),
    )
    monkeypatch.setenv(
        "PLUTOSDR_FW_RUNNER_MODULE_HEAD_SHA256",
        hashlib.sha256(module_path.read_bytes()).hexdigest(),
    )
    monkeypatch.setenv(
        "PLUTOSDR_FW_RUNNER_SHELL_SHA256",
        hashlib.sha256(shell.read_bytes()).hexdigest(),
    )
    monkeypatch.setenv(
        "PLUTOSDR_FW_RUNNER_SHELL_HEAD_SHA256",
        hashlib.sha256(shell.read_bytes()).hexdigest(),
    )
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_SHELL_PATH", str(shell))
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_METADATA_ABI_SHA256", "0" * 64)
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_METADATA_ABI_HEAD_SHA256", "0" * 64)
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_METADATA_ABI_PATH", str(metadata_abi_path))
    candidate_binding_sha = hashlib.sha256(
        candidate_binding_path.read_bytes()
    ).hexdigest()
    monkeypatch.setenv(
        "PLUTOSDR_FW_RUNNER_CANDIDATE_BINDING_SHA256", candidate_binding_sha
    )
    monkeypatch.setenv(
        "PLUTOSDR_FW_RUNNER_CANDIDATE_BINDING_HEAD_SHA256", candidate_binding_sha
    )
    monkeypatch.setenv(
        "PLUTOSDR_FW_RUNNER_CANDIDATE_BINDING_PATH", str(candidate_binding_path)
    )

    def fake_git(_repository, *arguments):
        if arguments == ("rev-parse", "HEAD"):
            return f"{commit}\n".encode()
        if arguments == ("status", "--porcelain", "--untracked-files=no"):
            return b""
        if arguments[0] == "show":
            relative = arguments[1].split(":", 1)[1]
            return (repository / relative).read_bytes()
        raise AssertionError(arguments)

    monkeypatch.setattr(lifecycle, "_git_bytes", fake_git)
    with pytest.raises(QualificationError, match="SHA-256|commit blob"):
        _attest_runner_provenance()


def test_context_close_failure_still_unlocks_and_persists_failure(tmp_path):
    class PlantedCloseFailure:
        def close(self):
            raise OSError(5, "planted context close failure")

    lock_path = tmp_path / "radio.lock"
    lock = lock_path.open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    output = tmp_path / "durable.json"
    report = {
        "schema": "plutosdr-fw.muted-metadata-batch-lifecycle.v1",
        "verdict": "FAIL",
        "started_unix_ns": 1,
        "cleanup": _mute(),
        "final_rx_state": _rx(),
        "final_tandem_status": _idle_status(),
    }
    durable, error = _close_resources_and_persist(
        report,
        output_path=output,
        context=PlantedCloseFailure(),
        lock=lock,
        lock_acquired=True,
        cleanup_errors=[],
        primary_error=None,
    )
    assert isinstance(error, QualificationError)
    assert durable == json.loads(output.read_text())
    assert durable["verdict"] == "FAIL"
    assert durable["cleanup"]["verified"] is False
    assert durable["cleanup"]["errors"][0]["errno"] == 5
    reopened = lock_path.open("a+")
    try:
        fcntl.flock(reopened, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        fcntl.flock(reopened, fcntl.LOCK_UN)
        reopened.close()


def test_report_promotion_failure_still_closes_context_and_unlocks(
    tmp_path, monkeypatch
):
    class ClosableContext:
        closed = False

        def close(self):
            self.closed = True

    context = ClosableContext()
    lock_path = tmp_path / "radio.lock"
    lock = lock_path.open("a+", encoding="utf-8")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    output = tmp_path / "durable.json"

    def reject_promotion(_path, _report, **_kwargs):
        raise OSError(errno.EIO, "planted report promotion failure")

    monkeypatch.setattr(lifecycle, "_atomic_json", reject_promotion)
    durable, error = _close_resources_and_persist(
        {
            "schema": lifecycle.SCHEMA,
            "verdict": "FAIL",
            "started_unix_ns": 1,
            "cleanup": _mute(),
        },
        output_path=output,
        context=context,
        lock=lock,
        lock_acquired=True,
        cleanup_errors=[],
        primary_error=None,
    )
    assert durable["verdict"] == "FAIL"
    assert isinstance(error, OSError)
    assert context.closed is True
    assert not output.exists()
    with lock_path.open("a+", encoding="utf-8") as reopened:
        fcntl.flock(reopened, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(reopened, fcntl.LOCK_UN)
