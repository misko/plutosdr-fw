"""Guarded observer for the release-image stale-small-ADC qualification gap.

The current release ABI can report accepted gain events, including reason
``SMALL_ADC_INHIBIT``, but it cannot expose or inject the detector state that
caused the decision, expose the stale-latch episode state, switch HOLD/AUTO
inside one ownership epoch, or count the physical paired pulse independently
of decision acceptance.  Consequently this entry point can only publish a
candidate-bound, nonauthorizing ``BLOCKED`` interface observation.  It must
never emit a hardware-qualification PASS.

The hardware path performs no acquisition and enables no transmitter.  It
opens the exact serial only after validating the candidate index, DFU, source
manifest, deployment receipt, and committed harness.  Its only writes are the
same independent fail-closed TX/DDS/DAC mute barriers used by the lifecycle
qualification.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import math
import os
import pathlib
import re
import stat
import sys
import time
from collections.abc import Mapping, Sequence
from typing import Any

from . import muted_metadata_batch_lifecycle as lifecycle
from .metadata_abi import TandemEventReason, TandemState

SCHEMA = "plutosdr-fw.stale-small-adc-hardware.v1"
SCHEMA_VERSION = 1
REPORT_FILENAME = "stale-latch-report.json"
TRACE_SCHEMA = "plutosdr-fw.stale-small-adc-public-trace.v1"
TRACE_SCHEMA_VERSION = 1
RELEASE_CLAIM = (
    "none; read-only interface observation cannot qualify stale-small-ADC recovery"
)
PHASE_STATUS = "blocked-missing-release-interface"
MAXIMUM_SOURCE_BYTES = 2 * 1024 * 1024

EXPECTED_IIO_ATTRIBUTES = (
    "abi_version",
    "fault_flags",
    "features",
    "fifo_depth",
    "fifo_level",
    "fpga_abi",
    "fpga_identity",
    "overflow_count",
    "ownership_epoch",
    "rx1_gain_index",
    "rx2_gain_index",
    "state",
    "transition_count",
)
EXPECTED_IOCTLS = ("ACQUIRE", "GET_CAPS", "GET_STATUS", "RELEASE")
EXPECTED_REQUEST_FIELDS = (
    "magic",
    "version",
    "size",
    "required_features",
    "mode",
    "observation_capacity",
    "event_capacity",
    "minimum_gain_db",
    "maximum_gain_db",
    "initial_gain_db",
    "power_measurement_samples",
    "low_power_dwell_periods",
    "cooldown_periods",
    "pulse_high_cycles",
    "pulse_low_cycles",
    "detector_blanking_cycles",
    "low_power_threshold",
    "large_lmt_overload_threshold",
    "large_adc_overload_threshold",
    "small_adc_overload_threshold",
    "overflow_policy",
    "sync_fault_policy",
    "reserved",
)
EXPECTED_STATUS_FIELDS = (
    "version",
    "size",
    "state",
    "ownership_epoch",
    "fault_flags",
    "fifo_level",
    "overflow_count",
    "transition_count",
    "minimum_gain_db",
    "maximum_gain_db",
    "initial_gain_db",
    "minimum_gain_index",
    "maximum_gain_index",
    "rx1_gain_index",
    "rx2_gain_index",
    "gain_table_id",
    "threshold_provenance",
    "reserved",
)
EXPECTED_EVENT_FIELDS = (
    "sample_sequence",
    "event_sequence",
    "flags",
    "rx1_gain_index",
    "rx2_gain_index",
)
GAIN_OBSERVATION_FIELDS = (
    "sample_before",
    "sample_after",
    "read_duration_ns",
    "flags",
    "rx1_gain_index",
    "rx2_gain_index",
    "rx1_gain_db",
    "rx2_gain_db",
    "reserved0",
    "reserved1",
)
MISSING_INTERFACES = (
    {
        "id": "detector-snapshot",
        "required_evidence": (
            "sample-aligned current low-power, small-ADC, large-ADC, and "
            "large-LMT detector bits before every candidate decision"
        ),
        "current_gap": (
            "IIO status and metadata gain observations contain no detector bits"
        ),
    },
    {
        "id": "stale-episode-state",
        "required_evidence": (
            "latched small-ADC state, one-clear budget, recurrence state, and "
            "neutral-dwell re-arm state"
        ),
        "current_gap": "neither status nor metadata exposes the stale episode FSM",
    },
    {
        "id": "same-epoch-mode-control",
        "required_evidence": (
            "guarded HOLD-to-AUTO transitions without closing the owning session"
        ),
        "current_gap": (
            "mode is immutable in ACQUIRE and close/reacquire starts a new epoch"
        ),
    },
    {
        "id": "deterministic-detector-fixture",
        "required_evidence": (
            "an exact-release-image mechanism or sample-aligned fixture marker "
            "that deterministically creates each required detector combination"
        ),
        "current_gap": (
            "the release ABI has no detector injection/capture command or fixture marker"
        ),
    },
    {
        "id": "physical-pulse-accounting",
        "required_evidence": (
            "a physical paired CTRL_IN pulse count/trace independent of accepted "
            "event and transition counters"
        ),
        "current_gap": "the public ABI exposes accepted transitions/events only",
    },
)

STALE_HARNESS_PATHS = (
    "linux/drivers/iio/adc/adi_tandem_agc.c",
    "linux/include/uapi/linux/adi_tandem_agc.h",
    "scripts/run_stale_small_adc_hardware.sh",
    "tests/radio_hardware/stale_small_adc_hardware.py",
)
PROVENANCE_ENV = {
    STALE_HARNESS_PATHS[0]: "RELEASE_DRIVER",
    STALE_HARNESS_PATHS[1]: "RELEASE_UAPI",
    STALE_HARNESS_PATHS[2]: "STALE_SHELL",
    STALE_HARNESS_PATHS[3]: "STALE_MODULE",
}
PROVENANCE_FIELDS = {
    STALE_HARNESS_PATHS[0]: "release_driver",
    STALE_HARNESS_PATHS[1]: "release_uapi",
    STALE_HARNESS_PATHS[2]: "stale_shell",
    STALE_HARNESS_PATHS[3]: "stale_module",
}


class StaleLatchQualificationError(RuntimeError):
    """The observer cannot produce trustworthy, nonauthorizing evidence."""


def _fail(message: str) -> None:
    raise StaleLatchQualificationError(message)


def _mapping(value: object, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
        _fail(f"{name} must be a string-keyed object")
    return value


def _sequence(value: object, *, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail(f"{name} must be an array")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, name: str) -> None:
    observed = set(value)
    if observed != expected:
        _fail(
            f"{name} keys changed: missing={sorted(expected - observed)} "
            f"extra={sorted(observed - expected)}"
        )


def _integer(
    value: object, *, name: str, minimum: int = 0, maximum: int = (1 << 63) - 1
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(f"{name} must be an exact integer in [{minimum}, {maximum}]")
    return value


def _sha256(value: object, *, name: str) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _fail(f"{name} must be a lowercase SHA-256")
    return value


def _absolute_path(value: object, *, name: str) -> pathlib.Path:
    if type(value) is not str or not value:
        _fail(f"{name} must be a nonempty absolute path")
    path = pathlib.Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path) != value:
        _fail(f"{name} must be an absolute normalized path")
    return path


def _read_source(path: pathlib.Path, *, name: str) -> tuple[bytes, str]:
    try:
        payload = lifecycle._read_bounded_owned_regular_file(
            path, maximum_bytes=MAXIMUM_SOURCE_BYTES, name=name
        )
        return payload, payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise StaleLatchQualificationError(f"{name} is not UTF-8") from error
    except lifecycle.QualificationError as error:
        raise StaleLatchQualificationError(str(error)) from error


def _struct_fields(text: str, structure: str) -> tuple[str, ...]:
    match = re.search(
        rf"struct\s+{re.escape(structure)}\s*\{{(?P<body>.*?)\}};",
        text,
        re.DOTALL,
    )
    if match is None:
        _fail(f"release UAPI omits {structure}")
    fields = tuple(
        re.findall(r"__(?:u|s)\d+\s+([a-zA-Z0-9_]+)(?:\[[^\]]+\])?\s*;", match["body"])
    )
    if not fields:
        _fail(f"release UAPI {structure} has no fields")
    return fields


def _attest_stale_runner_provenance() -> dict[str, str]:
    """Extend the clean A1.1 runner proof with the blocked-observer sources."""

    try:
        result = dict(lifecycle._attest_runner_provenance())
    except lifecycle.QualificationError as error:
        raise StaleLatchQualificationError(str(error)) from error
    repository = pathlib.Path(result["host_runner_repository"])
    commit = result["host_runner_repository_commit"]
    for relative, env_role in PROVENANCE_ENV.items():
        field = PROVENANCE_FIELDS[relative]
        expected_path = repository / relative
        path_text = os.environ.get(f"PLUTOSDR_FW_{env_role}_PATH", "")
        observed_sha = os.environ.get(f"PLUTOSDR_FW_{env_role}_SHA256", "")
        head_sha = os.environ.get(f"PLUTOSDR_FW_{env_role}_HEAD_SHA256", "")
        path = pathlib.Path(path_text) if path_text else pathlib.Path()
        if (
            not path_text
            or not path.is_absolute()
            or ".." in path.parts
            or path != expected_path
        ):
            _fail(f"{field} provenance path is absent or unexpected")
        _sha256(observed_sha, name=f"{field} live SHA-256")
        _sha256(head_sha, name=f"{field} commit SHA-256")
        live_sha = lifecycle._sha256_bounded_owned_regular_file(
            path,
            maximum_bytes=MAXIMUM_SOURCE_BYTES,
            name=f"{field} live source",
        )
        committed_sha = hashlib.sha256(
            lifecycle._git_bytes(repository, "show", f"{commit}:{relative}")
        ).hexdigest()
        if not (live_sha == committed_sha == observed_sha == head_sha):
            _fail(f"{field} does not match its committed candidate harness blob")
        result[f"{field}_path"] = str(path)
        result[f"{field}_sha256"] = live_sha
        result[f"{field}_head_blob_sha256"] = committed_sha
    return result


def _bind_stale_harness(
    candidate: Mapping[str, Any], provenance: Mapping[str, Any]
) -> None:
    artifact_index = _mapping(
        candidate.get("artifact_index"), name="candidate artifact index"
    )
    harness = _mapping(artifact_index.get("harness"), name="candidate harness")
    files = _sequence(harness.get("files"), name="candidate harness files")
    indexed: dict[str, str] = {}
    for item in files:
        entry = _mapping(item, name="candidate harness file")
        if set(entry) != {"path", "sha256"}:
            _fail("candidate harness file keys changed")
        path = entry["path"]
        if type(path) is not str or not path or path in indexed:
            _fail("candidate harness path is invalid or duplicated")
        indexed[path] = _sha256(entry["sha256"], name=f"candidate harness {path}")
    if not set(STALE_HARNESS_PATHS).issubset(indexed):
        _fail("candidate harness omits stale-small-ADC observer sources")
    for relative in STALE_HARNESS_PATHS:
        field = PROVENANCE_FIELDS[relative]
        if indexed[relative] != provenance.get(f"{field}_sha256"):
            _fail(f"candidate harness does not bind {relative}")


def _attest_candidate_inputs(
    *,
    source_manifest_path: pathlib.Path,
    artifact_index_path: pathlib.Path,
    deployment_receipt_path: pathlib.Path,
    candidate_dfu_path: pathlib.Path,
    serial: str,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        candidate = lifecycle._attest_candidate_binding(
            source_manifest_path=source_manifest_path,
            artifact_index_path=artifact_index_path,
            deployment_receipt_path=deployment_receipt_path,
            candidate_dfu_path=candidate_dfu_path,
            serial=serial,
            runner_provenance=provenance,
        )
    except lifecycle.QualificationError as error:
        raise StaleLatchQualificationError(str(error)) from error
    _bind_stale_harness(candidate, provenance)
    return candidate


def audit_release_interfaces(provenance: Mapping[str, Any]) -> dict[str, Any]:
    """Derive the exact public-interface gap from committed release sources."""

    driver_path = _absolute_path(
        provenance.get("release_driver_path"), name="release driver path"
    )
    uapi_path = _absolute_path(
        provenance.get("release_uapi_path"), name="release UAPI path"
    )
    metadata_path = _absolute_path(
        provenance.get("metadata_abi_path"), name="metadata ABI path"
    )
    driver_payload, driver = _read_source(driver_path, name="release tandem driver")
    uapi_payload, uapi = _read_source(uapi_path, name="release tandem UAPI")
    metadata_payload, _metadata = _read_source(
        metadata_path, name="release metadata ABI adapter"
    )
    hashes = {
        "driver": hashlib.sha256(driver_payload).hexdigest(),
        "uapi": hashlib.sha256(uapi_payload).hexdigest(),
        "metadata": hashlib.sha256(metadata_payload).hexdigest(),
    }
    for role, field in (
        ("driver", "release_driver_sha256"),
        ("uapi", "release_uapi_sha256"),
        ("metadata", "metadata_abi_sha256"),
    ):
        if hashes[role] != provenance.get(field):
            _fail(f"release {role} source changed during interface audit")

    attributes = tuple(
        sorted(set(re.findall(r"static\s+TANDEM_ATTR_RO\(([^,]+),", driver)))
    )
    ioctls = tuple(
        name
        for name in sorted(
            set(re.findall(r"#define\s+ADI_TANDEM_AGC_IOC_([A-Z_]+)\b", uapi))
        )
        if name != "MAGIC"
    )
    request_fields = _struct_fields(uapi, "adi_tandem_agc_request_v1")
    status_fields = _struct_fields(uapi, "adi_tandem_agc_status")
    event_fields = _struct_fields(uapi, "adi_tandem_agc_event")
    if attributes != EXPECTED_IIO_ATTRIBUTES:
        _fail("release tandem IIO attribute surface changed and needs review")
    if ioctls != EXPECTED_IOCTLS:
        _fail("release tandem ioctl surface changed and needs review")
    if request_fields != EXPECTED_REQUEST_FIELDS:
        _fail("release tandem request fields changed and need review")
    if status_fields != EXPECTED_STATUS_FIELDS:
        _fail("release tandem status fields changed and need review")
    if event_fields != EXPECTED_EVENT_FIELDS:
        _fail("release tandem event fields changed and need review")
    if (
        re.search(
            r"#define\s+TANDEM_ATTR_RO\(_name,\s*_address\)\s*\\\s*\n"
            r"\s*IIO_DEVICE_ATTR\(_name,\s*0444,",
            driver,
        )
        is None
        or "debugfs_reg_access" in driver
    ):
        _fail("release tandem IIO device is not an exact read-only surface")
    if int(TandemEventReason.SMALL_ADC_INHIBIT) != 2:
        _fail("metadata SMALL_ADC_INHIBIT reason changed")

    return {
        "verdict": "blocked",
        "qualification_possible": False,
        "source": {
            "driver_path": str(driver_path),
            "driver_sha256": hashes["driver"],
            "uapi_path": str(uapi_path),
            "uapi_sha256": hashes["uapi"],
            "metadata_abi_path": str(metadata_path),
            "metadata_abi_sha256": hashes["metadata"],
        },
        "public_iio": {
            "attributes": list(attributes),
            "all_attributes_read_only": True,
            "arbitrary_register_access": False,
        },
        "session_abi": {
            "ioctls": list(ioctls),
            "request_fields": list(request_fields),
            "status_fields": list(status_fields),
            "event_fields": list(event_fields),
            "mode_selected_only_at_acquire": True,
            "same_epoch_mode_control": False,
            "detector_injection": False,
        },
        "metadata_abi": {
            "small_adc_inhibit_reason": int(TandemEventReason.SMALL_ADC_INHIBIT),
            "gain_observation_fields": list(GAIN_OBSERVATION_FIELDS),
            "detector_state_fields": [],
            "stale_episode_fields": [],
        },
        "supported_observations": [
            "accepted event sample/event sequence, direction, reason, and paired indexes",
            "state, ownership epoch, faults, FIFO, paired indexes, transitions, and overflow",
            "post-close TX mute, DDS disable, selector ZERO, tandem IDLE, and FIFO drain",
        ],
        "missing_interfaces": [dict(item) for item in MISSING_INTERFACES],
    }


def assess_public_trace(value: object) -> dict[str, Any]:
    """Validate what an exact public event/status trace can and cannot prove.

    This analyzer deliberately returns a blocked assessment even for a perfect
    trace.  Accepted event reasons prove the controller's selected reason, but
    the absent detector/episode/mode/pulse interfaces prevent the A1.2 claim.
    """

    try:
        lifecycle._validate_strict_json_domain(value)
    except lifecycle.QualificationError as error:
        raise StaleLatchQualificationError(str(error)) from error
    trace = _mapping(value, name="public trace")
    _exact_keys(
        trace,
        {
            "schema",
            "schema_version",
            "serial",
            "artifact_index_sha256",
            "deployment_receipt_sha256",
            "ownership_epoch",
            "events",
            "status_samples",
            "cleanup",
        },
        name="public trace",
    )
    if (
        trace.get("schema") != TRACE_SCHEMA
        or type(trace.get("schema_version")) is not int
        or trace.get("schema_version") != TRACE_SCHEMA_VERSION
    ):
        _fail("public trace schema/version changed")
    serial = trace.get("serial")
    if type(serial) is not str or re.fullmatch(r"[A-Za-z0-9_.:-]+", serial) is None:
        _fail("public trace serial is invalid")
    _sha256(trace.get("artifact_index_sha256"), name="trace artifact-index SHA-256")
    _sha256(
        trace.get("deployment_receipt_sha256"),
        name="trace deployment-receipt SHA-256",
    )
    epoch = _integer(trace.get("ownership_epoch"), name="trace epoch", minimum=1)

    events = _sequence(trace.get("events"), name="public trace events")
    parsed_events: list[dict[str, Any]] = []
    previous_sample = -1
    previous_sequence: int | None = None
    for index, raw_event in enumerate(events):
        event = _mapping(raw_event, name=f"public event {index}")
        _exact_keys(
            event,
            {
                "sample_sequence",
                "event_sequence",
                "direction",
                "reason",
                "rx1_gain_index",
                "rx2_gain_index",
            },
            name=f"public event {index}",
        )
        sample = _integer(
            event.get("sample_sequence"), name=f"event {index} sample sequence"
        )
        sequence = _integer(
            event.get("event_sequence"),
            name=f"event {index} event sequence",
            maximum=0xFFFFFFFF,
        )
        direction = event.get("direction")
        reason = event.get("reason")
        rx1 = _integer(
            event.get("rx1_gain_index"),
            name=f"event {index} RX1 index",
            maximum=0x7F,
        )
        rx2 = _integer(
            event.get("rx2_gain_index"),
            name=f"event {index} RX2 index",
            maximum=0x7F,
        )
        if direction not in {"increase", "decrease"}:
            _fail(f"public event {index} direction is invalid")
        if reason not in {
            "large_lmt_overload",
            "large_adc_overload",
            "small_adc_inhibit",
            "both_low_power",
            "peer",
            "clamped",
            "initial",
        }:
            _fail(f"public event {index} reason is invalid")
        if rx1 != rx2 or sample < previous_sample:
            _fail(f"public event {index} is torn or not sample ordered")
        if (
            previous_sequence is not None
            and sequence != (previous_sequence + 1) & 0xFFFFFFFF
        ):
            _fail(f"public event {index} sequence has a hole")
        if reason == "small_adc_inhibit" and direction != "decrease":
            _fail("SMALL_ADC_INHIBIT event is not a decrease")
        previous_sample = sample
        previous_sequence = sequence
        parsed_events.append(dict(event))

    statuses = _sequence(trace.get("status_samples"), name="public status samples")
    if not statuses:
        _fail("public trace has no status samples")
    previous_transitions: int | None = None
    for index, raw_status in enumerate(statuses):
        status = _mapping(raw_status, name=f"public status {index}")
        _exact_keys(
            status,
            {
                "state",
                "ownership_epoch",
                "fault_flags",
                "fifo_level",
                "overflow_count",
                "transition_count",
                "rx1_gain_index",
                "rx2_gain_index",
            },
            name=f"public status {index}",
        )
        state = status.get("state")
        if state not in {"ARMED_AUTO", "ARMED_HOLD", "FAULTED"}:
            _fail(f"public status {index} state is invalid")
        if (
            _integer(
                status.get("ownership_epoch"), name=f"status {index} epoch", minimum=1
            )
            != epoch
        ):
            _fail(f"public status {index} epoch changed")
        transitions = _integer(
            status.get("transition_count"), name=f"status {index} transitions"
        )
        rx1 = _integer(
            status.get("rx1_gain_index"),
            name=f"status {index} RX1 index",
            maximum=0x7F,
        )
        rx2 = _integer(
            status.get("rx2_gain_index"),
            name=f"status {index} RX2 index",
            maximum=0x7F,
        )
        if rx1 != rx2 or (
            previous_transitions is not None and transitions < previous_transitions
        ):
            _fail(f"public status {index} is torn or regresses")
        _integer(status.get("fault_flags"), name=f"status {index} faults")
        _integer(status.get("fifo_level"), name=f"status {index} FIFO level")
        _integer(status.get("overflow_count"), name=f"status {index} overflows")
        previous_transitions = transitions

    cleanup = _mapping(trace.get("cleanup"), name="public trace cleanup")
    expected_cleanup = {
        "context_closed": True,
        "tx_muted": True,
        "dds_disabled": True,
        "dac_selectors_zero": True,
        "tandem_state": "IDLE",
        "fifo_level": 0,
    }
    if (
        set(cleanup) != set(expected_cleanup)
        or any(
            cleanup.get(key) is not True
            for key in (
                "context_closed",
                "tx_muted",
                "dds_disabled",
                "dac_selectors_zero",
            )
        )
        or cleanup.get("tandem_state") != "IDLE"
        or type(cleanup.get("fifo_level")) is not int
        or cleanup.get("fifo_level") != 0
    ):
        _fail("public trace cleanup is not exact and safe")

    small_events = [
        event for event in parsed_events if event["reason"] == "small_adc_inhibit"
    ]
    return {
        "verdict": "blocked",
        "qualification_possible": False,
        "serial": serial,
        "ownership_epoch": epoch,
        "event_count": len(parsed_events),
        "small_adc_inhibit_event_count": len(small_events),
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
        "unprovable_claims": [item["id"] for item in MISSING_INTERFACES],
    }


def _inventory_public_iio(tandem: Any) -> dict[str, Any]:
    names = tuple(sorted(str(name) for name in tandem.attrs))
    if names != EXPECTED_IIO_ATTRIBUTES:
        _fail(f"live tandem IIO attributes changed: {names}")
    values: dict[str, int] = {}
    for name in names:
        try:
            values[name] = int(str(tandem.attrs[name].value))
        except (KeyError, TypeError, ValueError) as error:
            raise StaleLatchQualificationError(
                f"live tandem IIO attribute {name} is not an integer"
            ) from error
    exact = {
        "abi_version": 1,
        "features": 7,
        "fpga_abi": 1,
        "fpga_identity": 0x54414732,
        "state": int(TandemState.IDLE),
        "ownership_epoch": 0,
        "fault_flags": 0,
        "fifo_level": 0,
        "overflow_count": 0,
        "transition_count": 0,
    }
    if any(values.get(name) != expected for name, expected in exact.items()):
        _fail(f"live tandem IIO interface is not clean release IDLE: {values}")
    if (
        values["fifo_depth"] <= 0
        or values["rx1_gain_index"] != values["rx2_gain_index"]
        or not 0 <= values["rx1_gain_index"] <= 0x7F
    ):
        _fail(f"live tandem IIO capacity/index evidence is invalid: {values}")
    return {"attribute_names": list(names), "attribute_values": values}


def _prepare_output(path: pathlib.Path) -> dict[str, Any]:
    if not path.is_absolute() or ".." in path.parts or path.name != REPORT_FILENAME:
        _fail(f"output must be an absolute normalized {REPORT_FILENAME!r} path")
    try:
        lifecycle._require_nonsymlink_path(path, include_leaf=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        lifecycle._require_nonsymlink_path(temporary, include_leaf=True)
        if path.exists() or temporary.exists():
            _fail("stale-latch report and temporary path must be fresh")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent = path.parent.stat(follow_symlinks=False)
    except OSError as error:
        raise StaleLatchQualificationError("output path cannot be prepared") from error
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.getuid()
        or stat.S_IMODE(parent.st_mode) != 0o700
    ):
        _fail("stale-latch output parent must be owned private mode 0700")
    return {
        "verified": True,
        "absolute_report_path": str(path),
        "absolute_temporary_path": str(temporary),
        "report_existed_before_context": False,
        "temporary_existed_before_context": False,
        "output_parent_device": parent.st_dev,
        "output_parent_inode": parent.st_ino,
    }


def _validate_output(value: object) -> pathlib.Path:
    output = _mapping(value, name="output preflight")
    _exact_keys(
        output,
        {
            "verified",
            "absolute_report_path",
            "absolute_temporary_path",
            "report_existed_before_context",
            "temporary_existed_before_context",
            "output_parent_device",
            "output_parent_inode",
        },
        name="output preflight",
    )
    path = _absolute_path(output.get("absolute_report_path"), name="report path")
    temporary = _absolute_path(
        output.get("absolute_temporary_path"), name="report temporary path"
    )
    if (
        path.name != REPORT_FILENAME
        or temporary != path.with_suffix(path.suffix + ".tmp")
        or output.get("verified") is not True
        or output.get("report_existed_before_context") is not False
        or output.get("temporary_existed_before_context") is not False
    ):
        _fail("output preflight semantics changed")
    parent = path.parent.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_dev
        != _integer(output.get("output_parent_device"), name="output parent device")
        or parent.st_ino
        != _integer(output.get("output_parent_inode"), name="output parent inode")
        or parent.st_uid != os.getuid()
        or stat.S_IMODE(parent.st_mode) != 0o700
    ):
        _fail("durable output parent identity changed")
    return path


def _validate_report_structure(value: object) -> None:
    """Reject any mutation that could make the blocked observer authorize RC8."""

    try:
        lifecycle._validate_strict_json_domain(value)
    except lifecycle.QualificationError as error:
        raise StaleLatchQualificationError(str(error)) from error
    report = _mapping(value, name="stale-latch report")
    _exact_keys(
        report,
        {
            "schema",
            "schema_version",
            "verdict",
            "phase_status",
            "release_claim",
            "release_pass_eligible",
            "hardware_qualified",
            "started_unix_ns",
            "completed_unix_ns",
            "candidate_lineage",
            "host_libiio",
            "runner_provenance",
            "interface_audit",
            "observation",
            "output_preflight",
            "cleanup",
            "operator_action",
        },
        name="stale-latch report",
    )
    if (
        report.get("schema") != SCHEMA
        or type(report.get("schema_version")) is not int
        or report.get("schema_version") != SCHEMA_VERSION
        or report.get("verdict") != "BLOCKED"
        or report.get("phase_status") != PHASE_STATUS
        or report.get("release_claim") != RELEASE_CLAIM
        or report.get("release_pass_eligible") is not False
        or report.get("hardware_qualified") is not False
    ):
        _fail("stale-latch report gained authority or changed identity")
    started = _integer(report.get("started_unix_ns"), name="report start", minimum=1)
    _integer(
        report.get("completed_unix_ns"),
        name="report completion",
        minimum=started,
    )

    candidate = _mapping(report.get("candidate_lineage"), name="candidate lineage")
    for name in (
        "artifact_index_sha256",
        "deployment_receipt_sha256",
        "dfu_sha256",
    ):
        _sha256(candidate.get(name), name=f"candidate {name}")
    serial = candidate.get("serial")
    firmware_version = candidate.get("firmware_version")
    kernel_version = candidate.get("kernel_version")
    hardware_model = candidate.get("hardware_model")
    if (
        type(serial) is not str
        or not serial
        or type(firmware_version) is not str
        or not firmware_version
        or type(kernel_version) is not str
        or not kernel_version
        or type(hardware_model) is not str
        or not hardware_model
    ):
        _fail("candidate serial/version binding is incomplete")
    _absolute_path(
        candidate.get("artifact_index_path"), name="candidate artifact-index path"
    )
    _absolute_path(
        candidate.get("deployment_receipt_path"),
        name="candidate deployment-receipt path",
    )
    _absolute_path(candidate.get("dfu_path"), name="candidate DFU path")
    source_manifest = _mapping(
        candidate.get("source_manifest"), name="candidate source manifest"
    )
    _absolute_path(source_manifest.get("path"), name="candidate source-manifest path")
    source_values = _mapping(
        source_manifest.get("values"), name="candidate source-manifest values"
    )
    libiio_commit = source_values.get("libiio_0_25_source")
    libiio_ref = source_values.get("libiio_0_25_ref")
    if (
        type(libiio_commit) is not str
        or re.fullmatch(r"[0-9a-f]{40}", libiio_commit) is None
        or type(libiio_ref) is not str
        or not libiio_ref.startswith("refs/tags/")
    ):
        _fail("candidate source manifest has no exact host-libiio identity")

    host = _mapping(report.get("host_libiio"), name="host libiio")
    _exact_keys(
        host,
        {
            "source_commit",
            "protected_source_tag",
            "source_directory",
            "build_directory",
            "mapped_shared_objects",
            "mapped_shared_object",
            "mapped_shared_object_sha256",
            "runner_shared_object_sha256",
            "pylibiio_file",
        },
        name="host libiio",
    )
    mapped_sha = _sha256(
        host.get("mapped_shared_object_sha256"), name="mapped libiio SHA-256"
    )
    if (
        host.get("source_commit") != libiio_commit
        or host.get("protected_source_tag") != libiio_ref.removeprefix("refs/tags/")
        or host.get("runner_shared_object_sha256") != mapped_sha
        or host.get("mapped_shared_objects") != [host.get("mapped_shared_object")]
    ):
        _fail("host libiio does not bind the candidate source")
    for name in (
        "source_directory",
        "build_directory",
        "mapped_shared_object",
        "pylibiio_file",
    ):
        _absolute_path(host.get(name), name=f"host libiio {name}")

    audit = _mapping(report.get("interface_audit"), name="interface audit")
    if (
        audit.get("verdict") != "blocked"
        or audit.get("qualification_possible") is not False
        or _sequence(audit.get("missing_interfaces"), name="missing interfaces")
        != list(MISSING_INTERFACES)
    ):
        _fail("interface audit no longer proves every release-interface gap")
    public_iio = _mapping(audit.get("public_iio"), name="public IIO audit")
    session_abi = _mapping(audit.get("session_abi"), name="session ABI audit")
    metadata_abi = _mapping(audit.get("metadata_abi"), name="metadata ABI audit")
    if (
        public_iio.get("attributes") != list(EXPECTED_IIO_ATTRIBUTES)
        or public_iio.get("all_attributes_read_only") is not True
        or public_iio.get("arbitrary_register_access") is not False
        or session_abi.get("ioctls") != list(EXPECTED_IOCTLS)
        or session_abi.get("same_epoch_mode_control") is not False
        or session_abi.get("detector_injection") is not False
        or metadata_abi.get("small_adc_inhibit_reason") != 2
        or metadata_abi.get("detector_state_fields") != []
        or metadata_abi.get("stale_episode_fields") != []
    ):
        _fail("interface audit capabilities changed")

    observation = _mapping(report.get("observation"), name="hardware observation")
    _exact_keys(
        observation,
        {
            "mode",
            "serial",
            "uri",
            "firmware_version",
            "context_attrs",
            "public_iio",
            "session_opened",
            "metadata_buffer_opened",
            "tx_stimulus_enabled",
        },
        name="hardware observation",
    )
    if (
        observation.get("mode") != "read-only-interface-inventory"
        or observation.get("serial") != serial
        or observation.get("firmware_version") != firmware_version
        or not str(observation.get("uri", "")).startswith("usb:")
        or observation.get("session_opened") is not False
        or observation.get("metadata_buffer_opened") is not False
        or observation.get("tx_stimulus_enabled") is not False
    ):
        _fail("observer performed or claimed an unsafe/authorizing operation")
    live_iio = _mapping(observation.get("public_iio"), name="live public IIO")
    _exact_keys(
        live_iio,
        {"attribute_names", "attribute_values"},
        name="live public IIO",
    )
    if live_iio.get("attribute_names") != list(EXPECTED_IIO_ATTRIBUTES):
        _fail("live public IIO inventory changed")
    values = _mapping(live_iio.get("attribute_values"), name="live IIO values")
    if set(values) != set(EXPECTED_IIO_ATTRIBUTES):
        _fail("live public IIO value set changed")
    exact_live = {
        "abi_version": 1,
        "features": 7,
        "fpga_abi": 1,
        "fpga_identity": 0x54414732,
        "state": int(TandemState.IDLE),
        "ownership_epoch": 0,
        "fault_flags": 0,
        "fifo_level": 0,
        "overflow_count": 0,
        "transition_count": 0,
    }
    if (
        any(type(value) is not int for value in values.values())
        or any(values.get(name) != expected for name, expected in exact_live.items())
        or values.get("fifo_depth", 0) <= 0
        or values.get("rx1_gain_index") != values.get("rx2_gain_index")
        or not 0 <= values.get("rx1_gain_index", -1) <= 0x7F
    ):
        _fail("live public IIO values are not clean release IDLE")
    context_attrs = _mapping(
        observation.get("context_attrs"), name="observed context attributes"
    )
    expected_context = {
        "hw_model": hardware_model,
        "hw_serial": serial,
        "fw_version": firmware_version,
        "ad9361-phy,model": "ad9361",
        "local,kernel": kernel_version,
        "iio,buffer-metadata": "2",
    }
    if any(
        context_attrs.get(name) != expected
        for name, expected in expected_context.items()
    ):
        _fail("observed context attributes do not bind the candidate")

    cleanup = _mapping(report.get("cleanup"), name="observer cleanup")
    _exact_keys(
        cleanup,
        {
            "verified",
            "context_closed",
            "lock_released",
            "tx_mute",
            "tandem_status",
            "errors",
        },
        name="observer cleanup",
    )
    if (
        cleanup.get("verified") is not True
        or cleanup.get("context_closed") is not True
        or cleanup.get("lock_released") is not True
        or cleanup.get("errors") != []
    ):
        _fail("observer cleanup is incomplete")
    mute = _mapping(cleanup.get("tx_mute"), name="cleanup TX mute")
    tandem = _mapping(cleanup.get("tandem_status"), name="cleanup tandem status")
    if (
        set(mute)
        != {
            "verified",
            "tx1_gain_db",
            "tx2_gain_db",
            "selectors",
            "dds",
            "failures",
        }
        or mute.get("verified") is not True
        or mute.get("failures") != []
        or type(mute.get("tx1_gain_db")) not in {int, float}
        or type(mute.get("tx2_gain_db")) not in {int, float}
        or not math.isfinite(float(mute["tx1_gain_db"]))
        or not math.isfinite(float(mute["tx2_gain_db"]))
        or float(mute["tx1_gain_db"]) > -80.0
        or float(mute["tx2_gain_db"]) > -80.0
        or mute.get("selectors") != [lifecycle.DAC_SELECT_ZERO] * 4
        or tandem.get("state") != int(TandemState.IDLE)
        or tandem.get("ownership_epoch") != 0
        or tandem.get("fault_flags") != 0
        or tandem.get("fifo_level") != 0
        or tandem.get("overflow_count") != 0
        or tandem.get("transition_count") != 0
    ):
        _fail("observer cleanup does not prove muted clean IDLE")
    dds = _mapping(mute.get("dds"), name="cleanup DDS state")
    if set(dds) != {f"altvoltage{index}" for index in range(8)}:
        _fail("observer cleanup DDS inventory changed")
    for name, raw_channel in dds.items():
        channel = _mapping(raw_channel, name=f"cleanup DDS {name}")
        if (
            set(channel) != {"present", "raw", "scale"}
            or channel.get("present") is not True
            or type(channel.get("raw")) not in {int, float}
            or type(channel.get("scale")) not in {int, float}
            or float(channel["raw"]) != 0.0
            or float(channel["scale"]) != 0.0
        ):
            _fail(f"observer cleanup DDS {name} is not disabled")
    if set(tandem) != set(lifecycle._STATUS_NAMES):
        _fail("observer cleanup tandem status fields changed")
    if (
        any(type(value) is not int for value in tandem.values())
        or tandem.get("rx1_gain_index") != tandem.get("rx2_gain_index")
        or not 0 <= tandem.get("rx1_gain_index", -1) <= 0x7F
    ):
        _fail("observer cleanup tandem indexes are invalid")
    _validate_output(report.get("output_preflight"))
    if report.get("operator_action") != (
        "Optional diagnostic only: add/review the missing release-image interfaces "
        "before attempting direct hardware observation of the internal stale-latch FSM."
    ):
        _fail("operator action changed")


def validate_durable_blocked_report(value: object) -> None:
    """Reopen every external binding and validate a durable BLOCKED report."""

    _validate_report_structure(value)
    report = _mapping(value, name="stale-latch report")
    observed_provenance = _mapping(
        report.get("runner_provenance"), name="runner provenance"
    )
    expected_provenance = _attest_stale_runner_provenance()
    if not lifecycle._json_identical(dict(observed_provenance), expected_provenance):
        _fail("durable stale observer provenance changed")
    candidate = _mapping(report.get("candidate_lineage"), name="candidate lineage")
    source_manifest = _mapping(
        candidate.get("source_manifest"), name="candidate source manifest"
    )
    expected_candidate = _attest_candidate_inputs(
        source_manifest_path=_absolute_path(
            source_manifest.get("path"), name="candidate source-manifest path"
        ),
        artifact_index_path=_absolute_path(
            candidate.get("artifact_index_path"), name="candidate artifact-index path"
        ),
        deployment_receipt_path=_absolute_path(
            candidate.get("deployment_receipt_path"),
            name="candidate deployment-receipt path",
        ),
        candidate_dfu_path=_absolute_path(
            candidate.get("dfu_path"), name="candidate DFU path"
        ),
        serial=str(candidate.get("serial", "")),
        provenance=expected_provenance,
    )
    if not lifecycle._json_identical(dict(candidate), expected_candidate):
        _fail("durable candidate lineage changed")
    expected_host = _reattest_host_libiio()
    if not lifecycle._json_identical(
        dict(_mapping(report.get("host_libiio"), name="host libiio")),
        expected_host,
    ):
        _fail("durable host libiio changed")
    expected_audit = audit_release_interfaces(expected_provenance)
    if not lifecycle._json_identical(
        dict(_mapping(report.get("interface_audit"), name="interface audit")),
        expected_audit,
    ):
        _fail("durable release-interface audit changed")


def _host_libiio_for_candidate(
    iio_module: Any, candidate: Mapping[str, Any]
) -> dict[str, Any]:
    source_manifest = _mapping(
        candidate.get("source_manifest"), name="candidate source manifest"
    )
    values = _mapping(source_manifest.get("values"), name="source manifest values")
    expected_commit = str(values.get("libiio_0_25_source", ""))
    expected_ref = str(values.get("libiio_0_25_ref", ""))
    try:
        observed = lifecycle._attest_host_libiio(iio_module)
    except lifecycle.QualificationError as error:
        raise StaleLatchQualificationError(str(error)) from error
    if observed.get("source_commit") != expected_commit or observed.get(
        "protected_source_tag"
    ) != expected_ref.removeprefix("refs/tags/"):
        _fail("host libiio does not match the candidate source manifest")
    return observed


def _reattest_host_libiio() -> dict[str, Any]:
    import iio

    try:
        return lifecycle._attest_host_libiio(iio)
    except lifecycle.QualificationError as error:
        raise StaleLatchQualificationError(str(error)) from error


def _identity_for_candidate(
    context: Any, *, serial: str, uri: str, candidate: Mapping[str, Any]
) -> dict[str, Any]:
    try:
        return lifecycle._attest_identity(
            context,
            serial=serial,
            uri=uri,
            firmware_pattern=str(candidate["firmware_pattern"]),
            firmware_version=str(candidate["firmware_version"]),
            kernel_version=str(candidate["kernel_version"]),
            hardware_model=str(candidate["hardware_model"]),
        )
    except lifecycle.QualificationError as error:
        raise StaleLatchQualificationError(str(error)) from error


def run_hardware_observer(
    iio_module: Any,
    *,
    serial: str,
    output_path: pathlib.Path,
    source_manifest_path: pathlib.Path,
    artifact_index_path: pathlib.Path,
    deployment_receipt_path: pathlib.Path,
    candidate_dfu_path: pathlib.Path,
) -> dict[str, Any]:
    """Inventory the blocked release interface without opening a tandem session."""

    paths = {
        "output": output_path,
        "source manifest": source_manifest_path,
        "artifact index": artifact_index_path,
        "deployment receipt": deployment_receipt_path,
        "candidate DFU": candidate_dfu_path,
    }
    for name, path in paths.items():
        if not path.is_absolute() or ".." in path.parts:
            _fail(f"{name} path must be absolute and normalized")
    if not serial or re.fullmatch(r"[A-Za-z0-9_.:-]+", serial) is None:
        _fail("serial is not a canonical explicit identifier")
    output_preflight = _prepare_output(output_path)
    provenance = _attest_stale_runner_provenance()
    candidate = _attest_candidate_inputs(
        source_manifest_path=source_manifest_path,
        artifact_index_path=artifact_index_path,
        deployment_receipt_path=deployment_receipt_path,
        candidate_dfu_path=candidate_dfu_path,
        serial=serial,
        provenance=provenance,
    )
    interface_audit = audit_release_interfaces(provenance)
    host_libiio = _host_libiio_for_candidate(iio_module, candidate)
    started_ns = time.time_ns()

    lock: Any = None
    lock_acquired = False
    context: Any = None
    phy: Any = None
    tx: Any = None
    tandem: Any = None
    observation: dict[str, Any] | None = None
    cleanup_errors: list[str] = []
    cleanup_mute: dict[str, Any] | None = None
    cleanup_tandem: dict[str, Any] | None = None
    primary_error: BaseException | None = None
    try:
        lock = lifecycle._open_lock(serial)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock_acquired = True
        except BlockingIOError as error:
            raise StaleLatchQualificationError(
                "serial-scoped hardware lock is already held"
            ) from error
        uri = lifecycle._resolve_uri(iio_module, serial)
        context = iio_module.Context(uri)
        context.set_timeout(10_000)
        phy = context.find_device("ad9361-phy")
        tx = context.find_device("cf-ad9361-dds-core-lpc")
        tandem = context.find_device("tandem-agc")
        if any(device is None for device in (phy, tx, tandem)):
            _fail("required PHY/TX/tandem device is absent")
        identity = _identity_for_candidate(
            context, serial=serial, uri=uri, candidate=candidate
        )
        lifecycle._force_mute(phy, tx)
        lifecycle._wait_idle(tandem, label="stale observer preflight")
        public_iio = _inventory_public_iio(tandem)
        observation = {
            "mode": "read-only-interface-inventory",
            "serial": serial,
            "uri": uri,
            "firmware_version": candidate["firmware_version"],
            "context_attrs": identity["context_attrs"],
            "public_iio": public_iio,
            "session_opened": False,
            "metadata_buffer_opened": False,
            "tx_stimulus_enabled": False,
        }
    except BaseException as error:  # noqa: BLE001 - cleanup must follow any exit
        primary_error = error
    finally:
        if phy is not None and tx is not None:
            try:
                cleanup_mute = lifecycle._force_mute(phy, tx)
            except BaseException as error:  # noqa: BLE001 - independent mute path
                cleanup_errors.append(f"final mute: {error}")
        if tandem is not None:
            try:
                cleanup_tandem = lifecycle._wait_idle(
                    tandem, label="stale observer cleanup"
                )
            except BaseException as error:  # noqa: BLE001 - independent IDLE path
                cleanup_errors.append(f"final tandem IDLE: {error}")
        if context is not None:
            try:
                lifecycle.close_iio_object(context)
            except BaseException as error:  # noqa: BLE001 - cleanup is best effort
                cleanup_errors.append(f"context close: {error}")
            context = None
        if lock is not None:
            if lock_acquired:
                try:
                    fcntl.flock(lock, fcntl.LOCK_UN)
                except BaseException as error:  # noqa: BLE001 - release unconditionally
                    cleanup_errors.append(f"lock release: {error}")
            try:
                lock.close()
            except BaseException as error:  # noqa: BLE001 - close unconditionally
                cleanup_errors.append(f"lock close: {error}")
            lock = None

    if primary_error is not None:
        if cleanup_errors:
            raise StaleLatchQualificationError(
                f"{primary_error}; cleanup also failed: {'; '.join(cleanup_errors)}"
            ) from primary_error
        raise primary_error.with_traceback(primary_error.__traceback__)
    if (
        cleanup_errors
        or observation is None
        or cleanup_mute is None
        or cleanup_tandem is None
    ):
        _fail(f"observer cleanup failed: {'; '.join(cleanup_errors)}")

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "verdict": "BLOCKED",
        "phase_status": PHASE_STATUS,
        "release_claim": RELEASE_CLAIM,
        "release_pass_eligible": False,
        "hardware_qualified": False,
        "started_unix_ns": started_ns,
        "completed_unix_ns": time.time_ns(),
        "candidate_lineage": candidate,
        "host_libiio": host_libiio,
        "runner_provenance": provenance,
        "interface_audit": interface_audit,
        "observation": observation,
        "output_preflight": output_preflight,
        "cleanup": {
            "verified": True,
            "context_closed": True,
            "lock_released": True,
            "tx_mute": cleanup_mute,
            "tandem_status": cleanup_tandem,
            "errors": [],
        },
        "operator_action": (
            "Optional diagnostic only: add/review the missing release-image interfaces "
            "before attempting direct hardware observation of the internal stale-latch FSM."
        ),
    }
    _validate_report_structure(report)
    try:
        lifecycle._atomic_json(output_path, report)
        durable = lifecycle._reread_exact_report(output_path, report)
    except lifecycle.QualificationError as error:
        raise StaleLatchQualificationError(str(error)) from error
    validate_durable_blocked_report(durable)
    return durable


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hardware", action="store_true")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--source-manifest", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-index", type=pathlib.Path, required=True)
    parser.add_argument("--deployment-receipt", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-dfu", type=pathlib.Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.hardware:
        raise SystemExit("refusing hardware access without explicit --hardware")
    import iio

    try:
        report = run_hardware_observer(
            iio,
            serial=args.serial,
            output_path=args.output,
            source_manifest_path=args.source_manifest,
            artifact_index_path=args.artifact_index,
            deployment_receipt_path=args.deployment_receipt,
            candidate_dfu_path=args.candidate_dfu,
        )
    except BaseException as error:  # noqa: BLE001 - CLI reports fail closed
        print(f"FAIL: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    artifact = args.output.absolute()
    print(f"BLOCKED: {artifact}")
    print(f"SHA256: {hashlib.sha256(artifact.read_bytes()).hexdigest()}")
    print("Optional diagnostic only; this report does not gate RC8")
    if report.get("hardware_qualified") is not False:
        raise AssertionError("blocked observer gained hardware authority")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
