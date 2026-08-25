import copy
import fcntl
import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from . import muted_metadata_batch_lifecycle as lifecycle
from .metadata_abi import (
    FEATURE_AD9361_TEMPERATURE,
    FEATURE_FPGA_GAIN_EVENTS,
    FEATURE_HARDWARE_SAMPLE_COUNTER,
    FEATURE_TANDEM_METADATA,
    FLAG_HARDWARE_SAMPLE_COUNTER_VALID,
    FLAG_SAMPLE_SEQUENCE_VALID,
    FLAG_TANDEM_METADATA_VALID,
    TandemFrameMetadata,
    TandemGainTable,
    TandemState,
)
from .muted_metadata_batch_lifecycle import (
    BATCH_FRAMES,
    EXACT_LIBIIO_COMMIT,
    EXPECTED_BATCH_CACHE_BYTES,
    FRAME_SAMPLES,
    RX_SCAN_FORMAT,
    QualificationError,
    _atomic_json,
    _attest_mapped_libiio,
    _attest_runner_provenance,
    _close_resources_and_persist,
    _configure_dual_complex_rx_scan,
    _frame_evidence,
    _reread_exact_report,
    validate_durable_pass_report,
    validate_full_drain_frames,
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
    assert _configure_dual_complex_rx_scan(rx) == _scan_evidence()
    assert all(channel.enabled for channel in rx.channels)


@pytest.mark.parametrize(
    ("rx", "message"),
    [
        (_ScanRx(channel_ids=["voltage0", "voltage1"]), "lacks channels"),
        (_ScanRx(indexes=[0, 1, 3, 2]), "scan index"),
        (_ScanRx(format_overrides={"is_signed": False}), "scan format"),
        (_ScanRx(format_overrides={"is_be": True}), "scan format"),
        (_ScanRx(format_overrides={"bits": 12}), "scan format"),
        (_ScanRx(format_overrides={"length": 12}), "scan format"),
        (_ScanRx(format_overrides={"shift": 1}), "scan format"),
        (_ScanRx(format_overrides={"repeat": 2}), "scan format"),
        (_ScanRx(sticky_extra=True), "enabled scan readback"),
        (_ScanRx(sample_size_override=6), "sample size is 6"),
    ],
)
def test_rx_scan_rejects_two_lane_reordered_or_non_cs16_shape(rx, message):
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
            _ScanRx(format_overrides={"bits": 16.0}),
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
        features=(
            FEATURE_AD9361_TEMPERATURE
            | FEATURE_FPGA_GAIN_EVENTS
            | FEATURE_HARDWARE_SAMPLE_COUNTER
            | FEATURE_TANDEM_METADATA
        ),
        flags=(
            FLAG_HARDWARE_SAMPLE_COUNTER_VALID
            | FLAG_SAMPLE_SEQUENCE_VALID
            | FLAG_TANDEM_METADATA_VALID
        ),
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
        threshold_provenance=572_733_972,
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


def _valid_report():
    frames = _frames()
    frame_records = [
        _frame_evidence(
            index,
            metadata,
            duration_ns=index + 1,
            iq_sha256="a" * 64,
            metadata_sha256="b" * 64,
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
        iq_sha256="c" * 64,
        metadata_sha256="d" * 64,
    )
    serial = "1040007c4a94000211000b009186843ef2"
    firmware = "v0.41-plutoplus-spf-tandem-agc-v8-rc2"
    final_status = _idle_status()
    cleanup = _mute()
    cleanup.update(
        {
            "tandem_status": final_status,
            "rx_state": _rx(),
            "errors": [],
        }
    )
    return {
        "schema": "plutosdr-fw.muted-metadata-batch-lifecycle.v1",
        "verdict": "PASS",
        "release_claim": "none; muted host-transport lifecycle qualification only",
        "started_unix_ns": 1,
        "completed_unix_ns": 2,
        "host_libiio": {
            "source_commit": EXACT_LIBIIO_COMMIT,
            "source_directory": "/src/libiio",
            "build_directory": "/tmp/libiio-build",
            "mapped_shared_objects": ["/tmp/libiio-build/libiio.so.0.25"],
            "mapped_shared_object": "/tmp/libiio-build/libiio.so.0.25",
            "mapped_shared_object_sha256": "e" * 64,
            "runner_shared_object_sha256": "e" * 64,
            "pylibiio_file": "/src/libiio/bindings/python/iio.py",
        },
        "runner_provenance": {
            "firmware_repo_commit": "f" * 40,
            "python_module_path": "/src/plutosdr-fw/tests/radio_hardware/muted_metadata_batch_lifecycle.py",
            "python_module_sha256": "1" * 64,
            "python_module_head_blob_sha256": "1" * 64,
            "shell_runner_path": "/src/plutosdr-fw/scripts/run_muted_metadata_batch_lifecycle_hardware.sh",
            "shell_runner_sha256": "2" * 64,
            "shell_runner_head_blob_sha256": "2" * 64,
            "metadata_abi_path": "/src/plutosdr-fw/tests/radio_hardware/metadata_abi.py",
            "metadata_abi_sha256": "3" * 64,
            "metadata_abi_head_blob_sha256": "3" * 64,
        },
        "configuration": {
            "serial": serial,
            "firmware_pattern": r"v0[.]41-plutoplus-spf-tandem-agc-v8-rc2",
            "tx_policy": "fully muted; no DDS/DMA enable and no TX gain increase",
            "tandem_mode": "hold",
            "hold_gain_db": 40,
            "frame_samples_per_channel": FRAME_SAMPLES,
            "kernel_buffers": 8,
            "batch_frames": 64,
            "metadata_capacity_bytes": 64 * 1024,
            "expected_batch_cache_bytes": EXPECTED_BATCH_CACHE_BYTES,
        },
        "preflight": {
            "verdict": "GO",
            "serial": serial,
            "uri": "usb:3.17.5",
            "firmware_version": firmware,
            "context_attrs": {
                "hw_serial": serial,
                "fw_version": firmware,
                "iio,buffer-metadata": "2",
            },
            "mute": _mute(),
            "rx_state": _rx(),
            "tandem_status": _idle_status(65),
        },
        "forced_mute_before": _mute(),
        "rx_manual_before": _rx(),
        "rx_scan": _scan_evidence(),
        "full_drain": {
            "kernel_buffers": 8,
            "batch_frames": 64,
            "metadata_capacity_bytes": 64 * 1024,
            "batch_cache_bound_bytes": EXPECTED_BATCH_CACHE_BYTES,
            "expected_batch_cache_bytes": EXPECTED_BATCH_CACHE_BYTES,
            "status_after_open": _hold_status(11),
            "status_before_close": _hold_status(11),
            "close_method": "explicit_normal_close",
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
        "rx_after_full_drain": _rx(),
        "mute_after_full_drain": _mute(),
        "cancel_lifecycle": {
            "verified": True,
            "kernel_buffers": 8,
            "batch_frames": 64,
            "operation_order": [
                "first_cached_frame_returned",
                "old_buffer_cancel",
                "second_open_ebusy",
                "old_refill_ebadf",
                "old_buffer_close",
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
            "status_after_old_close": _idle_status(),
            "status_after_fresh_open": _hold_status(13),
            "status_after_fresh_close": final_status,
        },
        "final_tandem_status": final_status,
        "final_rx_state": _rx(),
        "cleanup": cleanup,
    }


def test_durable_report_validator_accepts_frame_derived_pass():
    validate_durable_pass_report(_valid_report())


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("host_libiio", "runner_shared_object_sha256"), "0" * 64),
        (("runner_provenance", "python_module_sha256"), "0" * 64),
        (("runner_provenance", "shell_runner_sha256"), "0" * 64),
        (("runner_provenance", "metadata_abi_sha256"), "0" * 64),
        (("runner_provenance", "metadata_abi_path"), "/tmp/metadata_abi.py"),
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
        (("rx_scan", "layout", 2, "format", "bits"), 16.0),
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
        (("full_drain", "continuity", "frame_count"), 63),
        (("cancel_lifecycle", "second_open_error", "errno"), 5),
        (("cancel_lifecycle", "operation_order"), []),
        (("cleanup", "verified"), False),
    ],
)
def test_planted_false_pass_is_rejected(path, value):
    report = copy.deepcopy(_valid_report())
    target = report
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    with pytest.raises(QualificationError):
        validate_durable_pass_report(report)


def test_atomic_report_must_reread_exact_before_pass(tmp_path):
    report = _valid_report()
    path = tmp_path / "result.json"
    _atomic_json(path, report)
    assert _reread_exact_report(path, report) == report
    changed = json.loads(path.read_text())
    changed["full_drain"]["continuity"]["frame_count"] = 63
    _atomic_json(path, changed)
    with pytest.raises(QualificationError):
        _reread_exact_report(path, report)


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


def test_runner_source_sha_is_computed_in_hardware_process(tmp_path, monkeypatch):
    module_path = lifecycle.pathlib.Path(lifecycle.__file__).resolve()
    shell = tmp_path / "runner.sh"
    shell.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    metadata_abi_path = module_path.parent / "metadata_abi.py"
    module_sha = hashlib.sha256(module_path.read_bytes()).hexdigest()
    shell_sha = hashlib.sha256(shell.read_bytes()).hexdigest()
    metadata_abi_sha = hashlib.sha256(metadata_abi_path.read_bytes()).hexdigest()
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_COMMIT", "a" * 40)
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_MODULE_SHA256", module_sha)
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_MODULE_HEAD_SHA256", module_sha)
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_SHELL_SHA256", shell_sha)
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_SHELL_HEAD_SHA256", shell_sha)
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_SHELL_PATH", str(shell))
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_METADATA_ABI_SHA256", metadata_abi_sha)
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_METADATA_ABI_HEAD_SHA256", metadata_abi_sha)
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_METADATA_ABI_PATH", str(metadata_abi_path))
    evidence = _attest_runner_provenance()
    assert evidence["python_module_sha256"] == module_sha
    assert evidence["shell_runner_sha256"] == shell_sha
    assert evidence["metadata_abi_sha256"] == metadata_abi_sha


def test_runner_rejects_metadata_abi_mutation(tmp_path, monkeypatch):
    module_path = lifecycle.pathlib.Path(lifecycle.__file__).resolve()
    shell = tmp_path / "runner.sh"
    shell.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    metadata_abi_path = module_path.parent / "metadata_abi.py"
    monkeypatch.setenv("PLUTOSDR_FW_RUNNER_COMMIT", "a" * 40)
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
    with pytest.raises(QualificationError, match="SHA-256"):
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
