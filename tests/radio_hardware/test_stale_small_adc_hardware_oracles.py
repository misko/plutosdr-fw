import copy
import hashlib
import json
import pathlib
from types import SimpleNamespace

import pytest

from . import stale_small_adc_hardware as stale
from .candidate_binding import REQUIRED_EVIDENCE_ROLES

SERIAL = "test-radio-17"
FIRMWARE = "v0.41-plutoplus-spf-tandem-agc-v8-test"
KERNEL = "5.15.0-test"
MODEL = "Analog Devices PlutoSDR Rev.C (Z7010-AD9361)"
LIBIIO_COMMIT = "7" * 40
LIBIIO_TAG = "tandem-test/libiio-v1"


def _source_provenance(root: pathlib.Path) -> dict[str, str]:
    paths = {
        "release_driver": root / "linux/drivers/iio/adc/adi_tandem_agc.c",
        "release_uapi": root / "linux/include/uapi/linux/adi_tandem_agc.h",
        "metadata_abi": root / "tests/radio_hardware/metadata_abi.py",
    }
    result: dict[str, str] = {}
    for role, path in paths.items():
        result[f"{role}_path"] = str(path)
        result[f"{role}_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _audit() -> dict:
    root = pathlib.Path(stale.__file__).resolve().parents[2]
    return stale.audit_release_interfaces(_source_provenance(root))


def _candidate(tmp_path: pathlib.Path) -> dict:
    root = tmp_path / "candidate"
    source = root / "source/test-source.yaml"
    artifact_index = root / "candidate-index.json"
    receipt = root / "deploy/ram-boot-receipt.json"
    dfu = root / "artifact/test.dfu"
    return {
        "attestation": "exact candidate test fixture",
        "source_commit": "a" * 40,
        "source_manifest": {
            "path": str(source),
            "relative_path": "source/test-source.yaml",
            "committed_relative_path": "manifests/test-source.yaml",
            "bytes": 1,
            "sha256": "1" * 64,
            "values": {
                "libiio_0_25_source": LIBIIO_COMMIT,
                "libiio_0_25_ref": f"refs/tags/{LIBIIO_TAG}",
            },
        },
        "build_run_id": 10,
        "build_run_attempt": 1,
        "artifact_index_path": str(artifact_index),
        "artifact_index_bytes": 100,
        "artifact_index_sha256": "2" * 64,
        "artifact_index": {"harness": {"files": []}},
        "evidence_member_count": len(REQUIRED_EVIDENCE_ROLES),
        "evidence_members_verified": True,
        "dfu_path": str(dfu),
        "dfu_bytes": 17,
        "dfu_sha256": "3" * 64,
        "fit_bytes": 1,
        "fit_sha256": "4" * 64,
        "deployment_receipt_path": str(receipt),
        "deployment_receipt_bytes": 100,
        "deployment_receipt_sha256": "5" * 64,
        "deployment_receipt": {},
        "serial": SERIAL,
        "firmware_version": FIRMWARE,
        "firmware_pattern": rf"\A{FIRMWARE.replace('.', '[.]')}\Z",
        "kernel_version": KERNEL,
        "hardware_model": MODEL,
    }


def _host(tmp_path: pathlib.Path) -> dict:
    source = tmp_path / "libiio-source"
    build = tmp_path / "libiio-build"
    library = build / "libiio.so.0.25"
    return {
        "source_commit": LIBIIO_COMMIT,
        "protected_source_tag": LIBIIO_TAG,
        "source_directory": str(source),
        "build_directory": str(build),
        "mapped_shared_objects": [str(library)],
        "mapped_shared_object": str(library),
        "mapped_shared_object_sha256": "6" * 64,
        "runner_shared_object_sha256": "6" * 64,
        "pylibiio_file": str(source / "bindings/python/iio.py"),
    }


def _public_iio() -> dict:
    values = {
        "abi_version": 1,
        "fault_flags": 0,
        "features": 7,
        "fifo_depth": 256,
        "fifo_level": 0,
        "fpga_abi": 1,
        "fpga_identity": 0x54414732,
        "overflow_count": 0,
        "ownership_epoch": 0,
        "rx1_gain_index": 43,
        "rx2_gain_index": 43,
        "state": 0,
        "transition_count": 0,
    }
    return {
        "attribute_names": list(stale.EXPECTED_IIO_ATTRIBUTES),
        "attribute_values": values,
    }


def _mute() -> dict:
    return {
        "verified": True,
        "tx1_gain_db": -89.75,
        "tx2_gain_db": -89.75,
        "selectors": [stale.lifecycle.DAC_SELECT_ZERO] * 4,
        "dds": {
            f"altvoltage{index}": {"present": True, "raw": 0.0, "scale": 0.0}
            for index in range(8)
        },
        "failures": [],
    }


def _idle() -> dict:
    return {
        "state": 0,
        "fault_flags": 0,
        "overflow_count": 0,
        "fifo_level": 0,
        "ownership_epoch": 0,
        "transition_count": 0,
        "rx1_gain_index": 43,
        "rx2_gain_index": 43,
    }


def _report(tmp_path: pathlib.Path) -> dict:
    output_parent = tmp_path / "hardware/stale-latch" / SERIAL
    output_parent.mkdir(parents=True, mode=0o700)
    output_parent.chmod(0o700)
    output = output_parent / stale.REPORT_FILENAME
    parent = output_parent.stat()
    candidate = _candidate(tmp_path)
    return {
        "schema": stale.SCHEMA,
        "schema_version": stale.SCHEMA_VERSION,
        "verdict": "BLOCKED",
        "phase_status": stale.PHASE_STATUS,
        "release_claim": stale.RELEASE_CLAIM,
        "release_pass_eligible": False,
        "hardware_qualified": False,
        "started_unix_ns": 100,
        "completed_unix_ns": 200,
        "candidate_lineage": candidate,
        "host_libiio": _host(tmp_path),
        "runner_provenance": {"fixture": "committed"},
        "interface_audit": _audit(),
        "observation": {
            "mode": "read-only-interface-inventory",
            "serial": SERIAL,
            "uri": "usb:3.17.5",
            "firmware_version": FIRMWARE,
            "context_attrs": {
                "hw_model": MODEL,
                "hw_serial": SERIAL,
                "fw_version": FIRMWARE,
                "ad9361-phy,model": "ad9361",
                "local,kernel": KERNEL,
                "iio,buffer-metadata": "2",
                "uri": "usb:3.17.5",
            },
            "public_iio": _public_iio(),
            "session_opened": False,
            "metadata_buffer_opened": False,
            "tx_stimulus_enabled": False,
        },
        "output_preflight": {
            "verified": True,
            "absolute_report_path": str(output),
            "absolute_temporary_path": str(output.with_suffix(".json.tmp")),
            "report_existed_before_context": False,
            "temporary_existed_before_context": False,
            "output_parent_device": parent.st_dev,
            "output_parent_inode": parent.st_ino,
        },
        "cleanup": {
            "verified": True,
            "context_closed": True,
            "lock_released": True,
            "tx_mute": _mute(),
            "tandem_status": _idle(),
            "errors": [],
        },
        "operator_action": (
            "Optional diagnostic only: add/review the missing release-image interfaces "
            "before attempting direct hardware observation of the internal stale-latch FSM."
        ),
    }


def _trace() -> dict:
    return {
        "schema": stale.TRACE_SCHEMA,
        "schema_version": stale.TRACE_SCHEMA_VERSION,
        "serial": SERIAL,
        "artifact_index_sha256": "2" * 64,
        "deployment_receipt_sha256": "5" * 64,
        "ownership_epoch": 9,
        "events": [
            {
                "sample_sequence": 100,
                "event_sequence": 40,
                "direction": "decrease",
                "reason": "small_adc_inhibit",
                "rx1_gain_index": 42,
                "rx2_gain_index": 42,
            },
            {
                "sample_sequence": 200,
                "event_sequence": 41,
                "direction": "decrease",
                "reason": "large_adc_overload",
                "rx1_gain_index": 41,
                "rx2_gain_index": 41,
            },
            {
                "sample_sequence": 300,
                "event_sequence": 42,
                "direction": "decrease",
                "reason": "small_adc_inhibit",
                "rx1_gain_index": 40,
                "rx2_gain_index": 40,
            },
        ],
        "status_samples": [
            {
                "state": "ARMED_AUTO",
                "ownership_epoch": 9,
                "fault_flags": 0,
                "fifo_level": 0,
                "overflow_count": 0,
                "transition_count": transition,
                "rx1_gain_index": 43 - transition,
                "rx2_gain_index": 43 - transition,
            }
            for transition in range(4)
        ],
        "cleanup": {
            "context_closed": True,
            "tx_muted": True,
            "dds_disabled": True,
            "dac_selectors_zero": True,
            "tandem_state": "IDLE",
            "fifo_level": 0,
        },
    }


def _set_path(value, path, replacement):
    current = value
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = replacement


def test_release_source_audit_proves_concrete_missing_interfaces():
    audit = _audit()
    assert audit["verdict"] == "blocked"
    assert audit["qualification_possible"] is False
    assert audit["public_iio"]["attributes"] == list(stale.EXPECTED_IIO_ATTRIBUTES)
    assert audit["session_abi"]["ioctls"] == list(stale.EXPECTED_IOCTLS)
    assert audit["session_abi"]["same_epoch_mode_control"] is False
    assert audit["metadata_abi"]["detector_state_fields"] == []
    assert [item["id"] for item in audit["missing_interfaces"]] == [
        item["id"] for item in stale.MISSING_INTERFACES
    ]


@pytest.mark.parametrize(
    ("target", "old", "new"),
    [
        ("driver", "IIO_DEVICE_ATTR(_name, 0444,", "IIO_DEVICE_ATTR(_name, 0644,"),
        ("driver", ".attrs = &tandem_attr_group,", ".debugfs_reg_access = injected,"),
        (
            "driver",
            "static TANDEM_ATTR_RO(state, TANDEM_ATTR_STATE);",
            "static TANDEM_ATTR_RO(detector_state, TANDEM_ATTR_STATE);",
        ),
        (
            "uapi",
            "#define ADI_TANDEM_AGC_IOC_RELEASE \\" + "\n"
            "\t_IO(ADI_TANDEM_AGC_IOC_MAGIC, 0x03)",
            "#define ADI_TANDEM_AGC_IOC_SET_MODE _IO('T', 4)",
        ),
        ("uapi", "\t__u32 mode;", "\t__u32 diagnostic_mode;"),
    ],
)
def test_release_source_audit_fails_closed_on_interface_change(
    tmp_path, target, old, new
):
    root = pathlib.Path(stale.__file__).resolve().parents[2]
    paths = {
        "driver": tmp_path / "adi_tandem_agc.c",
        "uapi": tmp_path / "adi_tandem_agc.h",
        "metadata": tmp_path / "metadata_abi.py",
    }
    source_paths = {
        "driver": root / "linux/drivers/iio/adc/adi_tandem_agc.c",
        "uapi": root / "linux/include/uapi/linux/adi_tandem_agc.h",
        "metadata": root / "tests/radio_hardware/metadata_abi.py",
    }
    for role, path in paths.items():
        text = source_paths[role].read_text()
        if role == target:
            assert old in text
            text = text.replace(old, new, 1)
        path.write_text(text)
    provenance = {
        "release_driver_path": str(paths["driver"]),
        "release_driver_sha256": hashlib.sha256(
            paths["driver"].read_bytes()
        ).hexdigest(),
        "release_uapi_path": str(paths["uapi"]),
        "release_uapi_sha256": hashlib.sha256(paths["uapi"].read_bytes()).hexdigest(),
        "metadata_abi_path": str(paths["metadata"]),
        "metadata_abi_sha256": hashlib.sha256(
            paths["metadata"].read_bytes()
        ).hexdigest(),
    }
    with pytest.raises(stale.StaleLatchQualificationError, match="changed|read-only"):
        stale.audit_release_interfaces(provenance)


def test_public_trace_can_only_produce_blocked_observable_claims():
    assessment = stale.assess_public_trace(_trace())
    assert assessment == {
        "verdict": "blocked",
        "qualification_possible": False,
        "serial": SERIAL,
        "ownership_epoch": 9,
        "event_count": 3,
        "small_adc_inhibit_event_count": 2,
        "paired_event_indexes": True,
        "event_sequence_contiguous": True,
        "status_indexes_paired": True,
        "status_transition_monotonic": True,
        "cleanup_verified": True,
        "observable_claims": [
            "accepted SMALL_ADC_INHIBIT reason/count when present",
            "paired post-change indexes and contiguous event order",
            "monotonic public transition/status snapshots",
            "final public cleanup",
        ],
        "unprovable_claims": [item["id"] for item in stale.MISSING_INTERFACES],
    }


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("schema_version",), True),
        (("artifact_index_sha256",), "x" * 64),
        (("events", 0, "direction"), "increase"),
        (("events", 0, "rx2_gain_index"), 41),
        (("events", 1, "event_sequence"), 50),
        (("events", 1, "sample_sequence"), 99),
        (("status_samples", 1, "ownership_epoch"), 10),
        (("status_samples", 2, "transition_count"), 0),
        (("status_samples", 2, "rx2_gain_index"), 99),
        (("status_samples", 2, "fault_flags"), True),
        (("cleanup", "context_closed"), False),
        (("cleanup", "context_closed"), 1),
        (("cleanup", "fifo_level"), 1),
    ],
)
def test_public_trace_rejects_planted_failures(path, replacement):
    trace = _trace()
    _set_path(trace, path, replacement)
    with pytest.raises(stale.StaleLatchQualificationError):
        stale.assess_public_trace(trace)


def test_public_trace_rejects_missing_or_extra_critical_field():
    missing = _trace()
    del missing["deployment_receipt_sha256"]
    extra = _trace()
    extra["hardware_qualified"] = True
    for planted in (missing, extra):
        with pytest.raises(stale.StaleLatchQualificationError, match="keys"):
            stale.assess_public_trace(planted)


def test_blocked_report_structure_accepts_exact_nonauthorizing_evidence(tmp_path):
    stale._validate_report_structure(_report(tmp_path))


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("schema_version",), True),
        (("verdict",), "PASS"),
        (("phase_status",), "qualified"),
        (("release_claim",), "RC28 qualified"),
        (("release_pass_eligible",), True),
        (("hardware_qualified",), True),
        (("candidate_lineage", "serial"), "other-radio"),
        (("candidate_lineage", "firmware_version"), "wrong-firmware"),
        (("host_libiio", "runner_shared_object_sha256"), "0" * 64),
        (("interface_audit", "qualification_possible"), True),
        (("interface_audit", "public_iio", "all_attributes_read_only"), False),
        (("interface_audit", "public_iio", "arbitrary_register_access"), True),
        (("interface_audit", "session_abi", "same_epoch_mode_control"), True),
        (("interface_audit", "session_abi", "detector_injection"), True),
        (("interface_audit", "metadata_abi", "detector_state_fields"), ["small"]),
        (("observation", "session_opened"), True),
        (("observation", "metadata_buffer_opened"), True),
        (("observation", "tx_stimulus_enabled"), True),
        (("observation", "context_attrs", "local,kernel"), "wrong-kernel"),
        (("observation", "public_iio", "extra"), True),
        (("observation", "public_iio", "attribute_values", "fault_flags"), 1),
        (("cleanup", "verified"), False),
        (("cleanup", "context_closed"), False),
        (("cleanup", "lock_released"), False),
        (("cleanup", "errors"), ["failure"]),
        (("cleanup", "tx_mute", "tx1_gain_db"), -10.0),
        (("cleanup", "tx_mute", "selectors"), [0, 0, 0, 1]),
        (("cleanup", "tx_mute", "dds", "altvoltage0", "raw"), 1.0),
        (("cleanup", "tandem_status", "state"), 3),
        (("cleanup", "tandem_status", "fifo_level"), 1),
        (("operator_action",), "promote RC28"),
    ],
)
def test_blocked_report_rejects_planted_authority_identity_and_cleanup_failures(
    tmp_path, path, replacement
):
    report = _report(tmp_path)
    _set_path(report, path, replacement)
    with pytest.raises(stale.StaleLatchQualificationError):
        stale._validate_report_structure(report)


def test_blocked_report_requires_every_interface_gap(tmp_path):
    report = _report(tmp_path)
    report["interface_audit"]["missing_interfaces"].pop()
    with pytest.raises(stale.StaleLatchQualificationError, match="gap"):
        stale._validate_report_structure(report)


def test_blocked_report_rejects_missing_and_extra_top_level_fields(tmp_path):
    missing = _report(tmp_path / "missing")
    del missing["operator_action"]
    extra = _report(tmp_path / "extra")
    extra["hardware_pass"] = True
    for report in (missing, extra):
        with pytest.raises(stale.StaleLatchQualificationError, match="keys"):
            stale._validate_report_structure(report)


def test_durable_validator_reattests_candidate_host_harness_and_audit(
    tmp_path, monkeypatch
):
    report = _report(tmp_path)
    candidate = report["candidate_lineage"]
    provenance = report["runner_provenance"]
    host = report["host_libiio"]
    audit = report["interface_audit"]
    monkeypatch.setattr(stale, "_attest_stale_runner_provenance", lambda: provenance)
    monkeypatch.setattr(stale, "_attest_candidate_inputs", lambda **_kwargs: candidate)
    monkeypatch.setattr(stale, "_reattest_host_libiio", lambda: host)
    monkeypatch.setattr(stale, "audit_release_interfaces", lambda _value: audit)
    stale.validate_durable_blocked_report(report)

    for field in (
        "artifact_index_sha256",
        "deployment_receipt_sha256",
        "dfu_sha256",
    ):
        planted = {**candidate, field: "0" * 64}
        monkeypatch.setattr(
            stale,
            "_attest_candidate_inputs",
            lambda planted=planted, **_kwargs: planted,
        )
        with pytest.raises(stale.StaleLatchQualificationError, match="candidate"):
            stale.validate_durable_blocked_report(report)


def test_stale_harness_requires_every_observer_source_and_exact_digest():
    provenance = {}
    files = []
    for index, relative in enumerate(stale.STALE_HARNESS_PATHS, 1):
        digest = f"{index:x}" * 64
        field = stale.PROVENANCE_FIELDS[relative]
        provenance[f"{field}_sha256"] = digest
        files.append({"path": relative, "sha256": digest})
    candidate = {"artifact_index": {"harness": {"files": files}}}
    stale._bind_stale_harness(candidate, provenance)

    missing = copy.deepcopy(candidate)
    missing["artifact_index"]["harness"]["files"].pop()
    with pytest.raises(stale.StaleLatchQualificationError, match="omits"):
        stale._bind_stale_harness(missing, provenance)
    changed = copy.deepcopy(candidate)
    changed["artifact_index"]["harness"]["files"][0]["sha256"] = "0" * 64
    with pytest.raises(stale.StaleLatchQualificationError, match="does not bind"):
        stale._bind_stale_harness(changed, provenance)
    duplicate = copy.deepcopy(candidate)
    duplicate["artifact_index"]["harness"]["files"].append(
        copy.deepcopy(duplicate["artifact_index"]["harness"]["files"][0])
    )
    with pytest.raises(stale.StaleLatchQualificationError, match="duplicated"):
        stale._bind_stale_harness(duplicate, provenance)


def test_main_refuses_hardware_without_explicit_flag(tmp_path):
    arguments = [
        "--serial",
        SERIAL,
        "--output",
        str((tmp_path / stale.REPORT_FILENAME).absolute()),
        "--source-manifest",
        str((tmp_path / "source.yaml").absolute()),
        "--artifact-index",
        str((tmp_path / "candidate-index.json").absolute()),
        "--deployment-receipt",
        str((tmp_path / "receipt.json").absolute()),
        "--candidate-dfu",
        str((tmp_path / "candidate.dfu").absolute()),
    ]
    with pytest.raises(SystemExit, match="explicit --hardware"):
        stale.main(arguments)


def test_relative_candidate_path_fails_before_context(tmp_path):
    calls = []
    fake_iio = SimpleNamespace(Context=lambda _uri: calls.append(True))
    with pytest.raises(stale.StaleLatchQualificationError, match="source manifest"):
        stale.run_hardware_observer(
            fake_iio,
            serial=SERIAL,
            output_path=(tmp_path / stale.REPORT_FILENAME).absolute(),
            source_manifest_path=pathlib.Path("source.yaml"),
            artifact_index_path=(tmp_path / "candidate-index.json").absolute(),
            deployment_receipt_path=(tmp_path / "receipt.json").absolute(),
            candidate_dfu_path=(tmp_path / "candidate.dfu").absolute(),
        )
    assert calls == []


def _stub_hardware_run(tmp_path, monkeypatch, *, inventory_error=None):
    candidate = _candidate(tmp_path)
    provenance = {"fixture": "committed"}
    host = _host(tmp_path)
    audit = _audit()
    monkeypatch.setattr(stale, "_attest_stale_runner_provenance", lambda: provenance)
    monkeypatch.setattr(stale, "_attest_candidate_inputs", lambda **_kwargs: candidate)
    monkeypatch.setattr(stale, "audit_release_interfaces", lambda _value: audit)
    monkeypatch.setattr(
        stale, "_host_libiio_for_candidate", lambda _module, _candidate: host
    )
    monkeypatch.setattr(stale, "_reattest_host_libiio", lambda: host)
    monkeypatch.setattr(
        stale,
        "_identity_for_candidate",
        lambda _context, **_kwargs: {
            "context_attrs": {
                "hw_model": MODEL,
                "hw_serial": SERIAL,
                "fw_version": FIRMWARE,
                "ad9361-phy,model": "ad9361",
                "local,kernel": KERNEL,
                "iio,buffer-metadata": "2",
                "uri": "usb:3.17.5",
            }
        },
    )
    monkeypatch.setattr(
        stale.lifecycle, "_resolve_uri", lambda _module, _serial: "usb:3.17.5"
    )
    lock_path = tmp_path / "radio.lock"
    monkeypatch.setattr(
        stale.lifecycle,
        "_open_lock",
        lambda _serial: lock_path.open("w+", encoding="utf-8"),
    )
    mute_calls = []
    idle_calls = []
    monkeypatch.setattr(
        stale.lifecycle,
        "_force_mute",
        lambda _phy, _tx: mute_calls.append(True) or _mute(),
    )
    monkeypatch.setattr(
        stale.lifecycle,
        "_wait_idle",
        lambda _tandem, **_kwargs: idle_calls.append(True) or _idle(),
    )
    if inventory_error is None:
        monkeypatch.setattr(
            stale, "_inventory_public_iio", lambda _tandem: _public_iio()
        )
    else:
        monkeypatch.setattr(
            stale,
            "_inventory_public_iio",
            lambda _tandem: (_ for _ in ()).throw(inventory_error),
        )

    closed = []
    monkeypatch.setattr(
        stale.lifecycle, "close_iio_object", lambda _context: closed.append(True)
    )

    devices = {
        "ad9361-phy": object(),
        "cf-ad9361-dds-core-lpc": object(),
        "tandem-agc": object(),
    }

    class Context:
        def set_timeout(self, _timeout):
            return None

        def find_device(self, name):
            return devices.get(name)

    fake_iio = SimpleNamespace(Context=lambda _uri: Context())
    output = (tmp_path / "output" / stale.REPORT_FILENAME).absolute()
    return fake_iio, output, mute_calls, idle_calls, closed


def test_fake_hardware_observer_persists_only_durable_blocked_report(
    tmp_path, monkeypatch
):
    fake_iio, output, mute_calls, idle_calls, closed = _stub_hardware_run(
        tmp_path, monkeypatch
    )
    report = stale.run_hardware_observer(
        fake_iio,
        serial=SERIAL,
        output_path=output,
        source_manifest_path=(tmp_path / "source.yaml").absolute(),
        artifact_index_path=(tmp_path / "candidate-index.json").absolute(),
        deployment_receipt_path=(tmp_path / "receipt.json").absolute(),
        candidate_dfu_path=(tmp_path / "candidate.dfu").absolute(),
    )
    assert report["verdict"] == "BLOCKED"
    assert report["release_pass_eligible"] is False
    assert report["hardware_qualified"] is False
    assert report["observation"]["session_opened"] is False
    assert report["observation"]["tx_stimulus_enabled"] is False
    assert mute_calls == [True, True]
    assert idle_calls == [True, True]
    assert closed == [True]
    assert stat_mode(output) == 0o600
    assert json.loads(output.read_text()) == report


def stat_mode(path: pathlib.Path) -> int:
    return path.stat().st_mode & 0o777


def test_observer_failure_still_runs_independent_mute_idle_close_and_unlock(
    tmp_path, monkeypatch
):
    fake_iio, output, mute_calls, idle_calls, closed = _stub_hardware_run(
        tmp_path,
        monkeypatch,
        inventory_error=stale.StaleLatchQualificationError("planted inventory failure"),
    )
    with pytest.raises(stale.StaleLatchQualificationError, match="planted"):
        stale.run_hardware_observer(
            fake_iio,
            serial=SERIAL,
            output_path=output,
            source_manifest_path=(tmp_path / "source.yaml").absolute(),
            artifact_index_path=(tmp_path / "candidate-index.json").absolute(),
            deployment_receipt_path=(tmp_path / "receipt.json").absolute(),
            candidate_dfu_path=(tmp_path / "candidate.dfu").absolute(),
        )
    assert mute_calls == [True, True]
    assert idle_calls == [True, True]
    assert closed == [True]
    assert not output.exists()


def test_candidate_failure_occurs_before_context_factory(tmp_path, monkeypatch):
    monkeypatch.setattr(
        stale, "_attest_stale_runner_provenance", lambda: {"fixture": "committed"}
    )
    monkeypatch.setattr(
        stale,
        "_attest_candidate_inputs",
        lambda **_kwargs: (_ for _ in ()).throw(
            stale.StaleLatchQualificationError("planted candidate failure")
        ),
    )
    context_calls = []
    fake_iio = SimpleNamespace(Context=lambda _uri: context_calls.append(True))
    with pytest.raises(stale.StaleLatchQualificationError, match="candidate"):
        stale.run_hardware_observer(
            fake_iio,
            serial=SERIAL,
            output_path=(tmp_path / "out" / stale.REPORT_FILENAME).absolute(),
            source_manifest_path=(tmp_path / "source.yaml").absolute(),
            artifact_index_path=(tmp_path / "candidate-index.json").absolute(),
            deployment_receipt_path=(tmp_path / "receipt.json").absolute(),
            candidate_dfu_path=(tmp_path / "candidate.dfu").absolute(),
        )
    assert context_calls == []
