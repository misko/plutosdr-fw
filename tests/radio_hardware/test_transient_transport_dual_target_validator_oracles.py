"""Adversarial offline oracles for the durable dual-target v4 validator."""

from __future__ import annotations

import copy
import hashlib
import json
import struct
import zlib
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from .experiment import EvidenceInvalid
from .metadata_abi import GAIN_OBSERVATION_BYTES, V3_PREFIX_BYTES, V5_PREFIX_BYTES
from .test_transient_transport_probe_oracles import (
    _alternating_window_tone_raw,
    _DualTargetFakeRadio,
    _protected_libiio_source_fixture,  # noqa: F401
    _quality,
    _run_dual_target_fake,
)
from .transient_quality import analyze_immediate_dual_rx
from .transient_transport_dual_target_validator import validate_dual_target_report
from .transient_transport_probe import TransientTransportProbeOptions

_SERIAL = "1040007c4a94000211000b009186843ef2"
_PROJECTION_SCHEMA = "plutosdr-fw.tandem-evidence-projection.v1"
_OBSERVATION = struct.Struct("<QQIHBBbbHI")


@pytest.fixture()
def valid_pending(
    tmp_path: Path,
) -> tuple[dict[str, Any], Any, TransientTransportProbeOptions, Path]:
    quality = _quality(tmp_path)
    probe = TransientTransportProbeOptions()
    report, _path = _run_dual_target_fake(_DualTargetFakeRadio(tmp_path), quality)
    validate_dual_target_report(
        report,
        quality,
        probe,
        phase_root=tmp_path,
        require_cleanup=False,
    )
    return report, quality, probe, tmp_path


def _validate(report: dict[str, Any], quality: Any, probe: Any, root: Path) -> None:
    validate_dual_target_report(
        report,
        quality,
        probe,
        phase_root=root,
        require_cleanup=False,
    )


def _refresh_manifest(report: dict[str, Any]) -> None:
    mode = report["mode_evidence"]
    frames = mode["batch_frames"]
    entries = [
        {
            "frame_index": index,
            "iq_path": frame["iq_path"],
            "iq_bytes": frame["iq_bytes"],
            "iq_sha256": frame["sha256"],
            "raw_metadata_path": frame["raw_metadata_path"],
            "raw_metadata_bytes": frame["raw_metadata_bytes"],
            "raw_metadata_sha256": frame["raw_metadata_sha256"],
            "write_status": frame["artifact_write_status"],
        }
        for index, frame in enumerate(frames)
    ]
    encoded = json.dumps(
        entries, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    manifest = mode["acquisition"]["artifact_manifest"]
    manifest.update(
        {
            "relative_directory": str(frames[0]["iq_path"]).rsplit("/", 1)[0],
            "entries": entries,
            "entries_canonical_json_sha256": hashlib.sha256(encoded).hexdigest(),
        }
    )


def _refresh_canonical(report: dict[str, Any]) -> None:
    mode = report["mode_evidence"]
    projection_mode = copy.deepcopy(mode)
    ledger = projection_mode["acquisition"]["memory_ledger"]
    ledger.update(
        {
            "measured_finished_mode_and_parsed_metadata_bytes": 0,
            "measured_evidence_within_reservation": True,
            "canonical_evidence_projection_bytes": 0,
            "canonical_evidence_projection_sha256": "0" * 64,
        }
    )
    projection = {
        "schema": _PROJECTION_SCHEMA,
        "mode": projection_mode,
        "reparsed_metadata": [
            copy.deepcopy(frame["metadata"]) for frame in mode["batch_frames"]
        ],
    }
    encoded = json.dumps(
        projection, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    live_ledger = mode["acquisition"]["memory_ledger"]
    live_ledger["canonical_evidence_projection_bytes"] = len(encoded)
    live_ledger["canonical_evidence_projection_sha256"] = hashlib.sha256(
        encoded
    ).hexdigest()


def _refresh_report(report: dict[str, Any]) -> None:
    _refresh_manifest(report)
    _refresh_canonical(report)


def _rewrite_crc(payload: bytearray) -> None:
    struct.pack_into("<I", payload, len(payload) - 4, 0)
    struct.pack_into("<I", payload, len(payload) - 4, zlib.crc32(payload) & 0xFFFFFFFF)


def _rewrite_observation(
    payload: bytearray, slot: int, transform: Callable[[list[int]], None]
) -> None:
    offset = V5_PREFIX_BYTES + slot * GAIN_OBSERVATION_BYTES
    values = list(_OBSERVATION.unpack_from(payload, offset))
    transform(values)
    _OBSERVATION.pack_into(payload, offset, *values)


def _rewrite_temperature(
    report: dict[str, Any], root: Path, *, frame_index: int, value: int | None
) -> None:
    frame = report["mode_evidence"]["batch_frames"][frame_index]
    path = root / frame["raw_metadata_path"]
    payload = bytearray(path.read_bytes())
    struct.pack_into(
        "<i", payload, V3_PREFIX_BYTES + 40, -(1 << 31) if value is None else value
    )
    _rewrite_crc(payload)
    path.write_bytes(payload)
    frame["raw_metadata_sha256"] = hashlib.sha256(payload).hexdigest()
    frame["metadata"]["temperature_mdeg_c"] = value
    _refresh_report(report)


def _reject_raw_mutation(
    base: dict[str, Any],
    quality: Any,
    probe: Any,
    root: Path,
    mutate: Callable[[bytearray, dict[str, Any]], None],
) -> None:
    report = copy.deepcopy(base)
    frame = report["mode_evidence"]["batch_frames"][0]
    path = root / frame["raw_metadata_path"]
    original = path.read_bytes()
    try:
        payload = bytearray(original)
        mutate(payload, frame)
        _rewrite_crc(payload)
        path.write_bytes(payload)
        frame["raw_metadata_sha256"] = hashlib.sha256(payload).hexdigest()
        _refresh_report(report)
        with pytest.raises(EvidenceInvalid):
            _validate(report, quality, probe, root)
    finally:
        path.write_bytes(original)


def _reject_report_mutations(
    base: dict[str, Any],
    quality: Any,
    probe: Any,
    root: Path,
    mutations: tuple[Callable[[dict[str, Any]], None], ...],
    *,
    refresh_canonical: bool = True,
) -> None:
    for mutate in mutations:
        report = copy.deepcopy(base)
        mutate(report)
        if refresh_canonical:
            _refresh_canonical(report)
        with pytest.raises(EvidenceInvalid):
            _validate(report, quality, probe, root)


def test_generated_pending_report_is_durably_valid(
    valid_pending: tuple[dict[str, Any], Any, TransientTransportProbeOptions, Path],
) -> None:
    report, quality, probe, root = valid_pending
    _validate(report, quality, probe, root)


def test_dual_target_validator_accepts_only_leading_temperature_omissions(
    valid_pending: tuple[dict[str, Any], Any, TransientTransportProbeOptions, Path],
) -> None:
    base, quality, probe, root = valid_pending
    report = copy.deepcopy(base)
    paths = [
        root / report["mode_evidence"]["batch_frames"][index]["raw_metadata_path"]
        for index in (0, 1, 3)
    ]
    originals = [path.read_bytes() for path in paths]
    try:
        _rewrite_temperature(report, root, frame_index=0, value=None)
        _rewrite_temperature(report, root, frame_index=1, value=None)
        _validate(report, quality, probe, root)

        _rewrite_temperature(report, root, frame_index=3, value=None)
        with pytest.raises(EvidenceInvalid):
            _validate(report, quality, probe, root)
    finally:
        for path, payload in zip(paths, originals, strict=True):
            path.write_bytes(payload)


def test_self_consistent_raw_observation_prefix_and_mask_mutations_are_rejected(
    valid_pending: tuple[dict[str, Any], Any, TransientTransportProbeOptions, Path],
) -> None:
    report, quality, probe, root = valid_pending

    def nonmaximum(payload: bytearray, _frame: dict[str, Any]) -> None:
        def change(values: list[int]) -> None:
            values[4:8] = [64, 64, 61, 61]

        _rewrite_observation(payload, 0, change)

    def observation_flags(payload: bytearray, _frame: dict[str, Any]) -> None:
        _rewrite_observation(payload, 0, lambda values: values.__setitem__(3, 0x0007))

    def compressed_cadence(payload: bytearray, frame: dict[str, Any]) -> None:
        start = frame["first_sample_sequence"]
        for slot in range(4):

            def change(values: list[int], *, sample: int = start + slot) -> None:
                values[0], values[1] = sample, sample + 1

            _rewrite_observation(payload, slot, change)

    def out_of_frame(payload: bytearray, frame: dict[str, Any]) -> None:
        end = frame["sample_end_exclusive"]

        def change(values: list[int]) -> None:
            values[0], values[1] = end, end + 1

        _rewrite_observation(payload, 0, change)

    def nonzero_unused(payload: bytearray, _frame: dict[str, Any]) -> None:
        payload[V5_PREFIX_BYTES + 4 * GAIN_OBSERVATION_BYTES] = 1

    def unknown_feature(payload: bytearray, frame: dict[str, Any]) -> None:
        features = struct.unpack_from("<I", payload, 8)[0] | (1 << 31)
        struct.pack_into("<I", payload, 8, features)
        frame["metadata"]["features"] = features

    def unknown_flag(payload: bytearray, frame: dict[str, Any]) -> None:
        flags = struct.unpack_from("<I", payload, 12)[0] | (1 << 31)
        struct.pack_into("<I", payload, 12, flags)
        frame["metadata"]["flags"] = flags

    def first_change(payload: bytearray, _frame: dict[str, Any]) -> None:
        struct.pack_into("<II", payload, 68, 0, 0)

    def prefix_reserved(payload: bytearray, _frame: dict[str, Any]) -> None:
        payload[59] = 1

    def prefix_reserved_tail(payload: bytearray, _frame: dict[str, Any]) -> None:
        struct.pack_into("<II", payload, 116, 1, 1)

    def invalid_rssi(payload: bytearray, _frame: dict[str, Any]) -> None:
        struct.pack_into("<H", payload, 76, 0xFFFF)

    def provider_interval(payload: bytearray, _frame: dict[str, Any]) -> None:
        struct.pack_into("<I", payload, 92, 1)

    mutations = (
        nonmaximum,
        observation_flags,
        compressed_cadence,
        out_of_frame,
        nonzero_unused,
        unknown_feature,
        unknown_flag,
        first_change,
        prefix_reserved,
        prefix_reserved_tail,
        invalid_rssi,
        provider_interval,
    )
    for mutate in mutations:
        _reject_raw_mutation(report, quality, probe, root, mutate)


def test_global_observation_cadence_spans_adjacent_frames(
    valid_pending: tuple[dict[str, Any], Any, TransientTransportProbeOptions, Path],
) -> None:
    base, quality, probe, root = valid_pending
    report = copy.deepcopy(base)
    frames = report["mode_evidence"]["batch_frames"][:2]
    paths = [root / frame["raw_metadata_path"] for frame in frames]
    originals = [path.read_bytes() for path in paths]
    try:
        boundary = frames[0]["sample_end_exclusive"]
        samples = ((boundary - 1, boundary - 1), (boundary, boundary + 1))
        for frame, path, original, (sample_before, sample_after) in zip(
            frames, paths, originals, samples, strict=True
        ):
            payload = bytearray(original)
            struct.pack_into("<H", payload, 96, 1)
            payload[
                V5_PREFIX_BYTES + GAIN_OBSERVATION_BYTES : V5_PREFIX_BYTES
                + 4 * GAIN_OBSERVATION_BYTES
            ] = b"\0" * (3 * GAIN_OBSERVATION_BYTES)

            def change(
                values: list[int],
                *,
                before: int = sample_before,
                after: int = sample_after,
            ) -> None:
                values[0], values[1] = before, after

            _rewrite_observation(payload, 0, change)
            _rewrite_crc(payload)
            path.write_bytes(payload)
            frame["raw_metadata_sha256"] = hashlib.sha256(payload).hexdigest()
            frame["metadata"]["observation_count"] = 1
        _refresh_report(report)
        with pytest.raises(EvidenceInvalid):
            _validate(report, quality, probe, root)
    finally:
        for path, original in zip(paths, originals, strict=True):
            path.write_bytes(original)


def test_self_consistent_target_schedule_and_chronology_mutations_are_rejected(
    valid_pending: tuple[dict[str, Any], Any, TransientTransportProbeOptions, Path],
) -> None:
    report, quality, probe, root = valid_pending
    command_id = "weak_reassertion_16f"

    def coordinated_target(value: dict[str, Any]) -> None:
        mode = value["mode_evidence"]
        acquisition = mode["acquisition"]
        forged = acquisition["targets"][command_id]["target_raw"] + 1
        acquisition["targets"][command_id]["target_raw"] = forged
        acquisition["schedule_plan"]["commands"][0]["target_raw"] = forged
        acquisition["schedule_diagnostics"][command_id]["target"]["target_raw"] = forged
        mode["commands"][1]["sample_counter_bracket"]["target_raw"] = forged

    def candidate_role(value: dict[str, Any]) -> None:
        reads = value["mode_evidence"]["acquisition"]["schedule_diagnostics"][
            command_id
        ]["counter_reads"]
        initial = next(
            item for item in reads if item["role"] == "raw_post_write_initial"
        )
        initial["role"] = "post_write_advance_candidate"

    def write_attempt_bool(value: dict[str, Any]) -> None:
        value["mode_evidence"]["acquisition"]["schedule_diagnostics"][command_id][
            "write_ack"
        ]["attempt_count"] = True

    def readback_attempt_bool(value: dict[str, Any]) -> None:
        value["mode_evidence"]["acquisition"]["schedule_diagnostics"][command_id][
            "deferred_tx2_readback"
        ]["attempt_count"] = True

    def tx1_attempt_bool(value: dict[str, Any]) -> None:
        value["mode_evidence"]["acquisition"]["schedule_diagnostics"][command_id][
            "tx1_mute_assurance"
        ]["pre"]["attempt_count"] = True

    def forged_attenuation(value: dict[str, Any]) -> None:
        mode = value["mode_evidence"]
        mode["commands"][1]["effective_attenuation_db"] = 99.0
        mode["acquisition"]["unbound_commands"][command_id][
            "effective_attenuation_db"
        ] = 99.0

    def late_worker_return(value: dict[str, Any]) -> None:
        mode = value["mode_evidence"]
        first_pre = mode["acquisition"]["schedule_diagnostics"][command_id][
            "tx1_mute_assurance"
        ]["pre"]["host_before_ns"]
        mode["acquisition"]["schedule_plan"]["worker_start_returned_ns"] = first_pre + 1

    def cross_command_overlap(value: dict[str, Any]) -> None:
        diagnostics = value["mode_evidence"]["acquisition"]["schedule_diagnostics"]
        first_post = diagnostics[command_id]["tx1_mute_assurance"]["post"]
        second_pre = diagnostics["weak_reassertion_40f"]["tx1_mute_assurance"]["pre"]
        second_pre["host_before_ns"] = first_post["host_before_ns"]
        second_pre["host_after_ns"] = first_post["host_after_ns"]

    def detached_completion(value: dict[str, Any]) -> None:
        value["mode_evidence"]["acquisition"][
            "initiating_refill_completion_monotonic_ns"
        ] += 1

    def early_shutdown(value: dict[str, Any]) -> None:
        events = value["mode_evidence"]["acquisition"]["shutdown"]["events"]
        for index, event in enumerate(events):
            event["monotonic_ns"] = index

    def worker_bool(value: dict[str, Any]) -> None:
        value["mode_evidence"]["acquisition"]["schedule_diagnostics"][command_id][
            "raw_bracket"
        ]["worker_in_flight_at_command"] = 1

    _reject_report_mutations(
        report,
        quality,
        probe,
        root,
        (
            coordinated_target,
            candidate_role,
            write_attempt_bool,
            readback_attempt_bool,
            tx1_attempt_bool,
            forged_attenuation,
            late_worker_return,
            cross_command_overlap,
            detached_completion,
            early_shutdown,
            worker_bool,
        ),
    )


def test_schema_type_memory_partition_and_lifecycle_mutations_are_rejected(
    valid_pending: tuple[dict[str, Any], Any, TransientTransportProbeOptions, Path],
) -> None:
    report, quality, probe, root = valid_pending

    def top_failure(value: dict[str, Any]) -> None:
        value["failure_evidence"] = {"planted": True}

    def mode_failure(value: dict[str, Any]) -> None:
        value["mode_evidence"]["fatal_error"] = "planted"

    def frame_failure(value: dict[str, Any]) -> None:
        value["mode_evidence"]["batch_frames"][0]["fatal_error"] = "planted"

    def final_state_failure(value: dict[str, Any]) -> None:
        value["mode_evidence"]["final_rx_state"]["fatal_error"] = "planted"

    def bool_clock(value: dict[str, Any]) -> None:
        value["started_unix_ns"] = True

    def bool_configuration(value: dict[str, Any]) -> None:
        value["configuration"]["probe"]["frame_samples"] = True

    def huge_elapsed(value: dict[str, Any]) -> None:
        value["elapsed_seconds"] = 10**4000

    def integer_elapsed(value: dict[str, Any]) -> None:
        value["elapsed_seconds"] = 0

    def infinite_elapsed(value: dict[str, Any]) -> None:
        value["elapsed_seconds"] = float("inf")

    def huge_nested(value: dict[str, Any]) -> None:
        value["mode_evidence"]["commands"][1]["host_jitter_ns"] = 10**4000

    def measured_one(value: dict[str, Any]) -> None:
        value["mode_evidence"]["acquisition"]["memory_ledger"][
            "measured_finished_mode_and_parsed_metadata_bytes"
        ] = 1

    def memory_method(value: dict[str, Any]) -> None:
        value["mode_evidence"]["acquisition"]["memory_ledger"][
            "canonical_evidence_projection_method"
        ] = "planted"

    def memory_bool(value: dict[str, Any]) -> None:
        value["mode_evidence"]["acquisition"]["memory_ledger"][
            "aggregate_resident_bytes"
        ] = True

    def phase_substitution(value: dict[str, Any]) -> None:
        value["mode_evidence"]["batch_frames"][0]["batch_phase"] = (
            "fully_between_commands"
        )
        value["mode_evidence"]["batch_frames"][0]["gap_context"] = (
            "fully_between_commands"
        )

    def partition_count(value: dict[str, Any]) -> None:
        value["mode_evidence"]["partition"]["groups"]["fully_pre_first"]["count"] -= 1

    def anchor_extra(value: dict[str, Any]) -> None:
        value["mode_evidence"]["conditioning_anchor"]["source"]["fatal_error"] = (
            "planted"
        )

    def analysis_extra(value: dict[str, Any]) -> None:
        value["mode_evidence"]["batch_frames"][0]["analysis"]["fatal_error"] = "planted"

    def cancel_success(value: dict[str, Any]) -> None:
        shutdown = value["mode_evidence"]["acquisition"]["shutdown"]
        shutdown["cancel_required"] = True
        shutdown["cancel_called"] = True
        shutdown["cancel_succeeded"] = True

    def post_fifo(value: dict[str, Any]) -> None:
        value["mode_evidence"]["acquisition"]["post_close_tandem_status"][
            "fifo_level"
        ] = 1
        value["mode_evidence"]["tandem_status_after"]["fifo_level"] = 1

    def close_policy(value: dict[str, Any]) -> None:
        value["mode_evidence"]["acquisition"]["close_counter_ledger"]["policy"] = (
            "claim an exact retired tail"
        )

    def release_claim(value: dict[str, Any]) -> None:
        value["mode_evidence"]["release_pass_eligible"] = True
        value["release_pass_eligible"] = True

    _reject_report_mutations(
        report,
        quality,
        probe,
        root,
        (
            top_failure,
            mode_failure,
            frame_failure,
            final_state_failure,
            bool_clock,
            bool_configuration,
            huge_elapsed,
            integer_elapsed,
            infinite_elapsed,
            huge_nested,
            measured_one,
            memory_method,
            memory_bool,
            phase_substitution,
            partition_count,
            anchor_extra,
            analysis_extra,
            cancel_success,
            post_fifo,
            close_policy,
            release_claim,
        ),
    )

    forged = copy.deepcopy(report)
    forged["mode_evidence"]["acquisition"]["memory_ledger"][
        "canonical_evidence_projection_sha256"
    ] = "0" * 64
    with pytest.raises(EvidenceInvalid):
        _validate(forged, quality, probe, root)


def test_self_consistent_raw_iq_suffix_oscillation_is_rejected(
    valid_pending: tuple[dict[str, Any], Any, TransientTransportProbeOptions, Path],
) -> None:
    base, quality, probe, root = valid_pending
    report = copy.deepcopy(base)
    frame = report["mode_evidence"]["batch_frames"][-1]
    path = root / frame["iq_path"]
    original = path.read_bytes()
    try:
        planted = _alternating_window_tone_raw(65_536)
        path.write_bytes(planted)
        frame["sha256"] = hashlib.sha256(planted).hexdigest()
        frame["analysis"] = dict(
            analyze_immediate_dual_rx(
                planted,
                first_sample_sequence=frame["first_sample_sequence"],
                sample_rate_hz=quality.sample_rate_hz,
                expected_tone_hz=quality.tone_hz,
                window_samples=1_024,
                min_tone_snr_db=quality.thresholds.min_tone_snr_db,
                max_clipping_fraction=quality.thresholds.max_clipping_fraction,
                max_phase_std_deg=quality.thresholds.max_phase_std_deg,
            )
        )
        _refresh_report(report)
        with pytest.raises(EvidenceInvalid):
            _validate(report, quality, probe, root)
    finally:
        path.write_bytes(original)


def test_sidecar_inventory_size_symlink_and_containment_mutations_are_rejected(
    valid_pending: tuple[dict[str, Any], Any, TransientTransportProbeOptions, Path],
) -> None:
    base, quality, probe, root = valid_pending

    escaped = copy.deepcopy(base)
    escaped_frame = escaped["mode_evidence"]["batch_frames"][0]
    escaped_frame["iq_path"] = "../../outside.cs16"
    _refresh_report(escaped)
    with pytest.raises(EvidenceInvalid):
        _validate(escaped, quality, probe, root)

    metadata_relative = base["mode_evidence"]["batch_frames"][0]["raw_metadata_path"]
    metadata_path = root / metadata_relative
    backup = root / "saved-frame-0000-metadata.bin"
    metadata_path.rename(backup)
    try:
        metadata_path.symlink_to(backup)
        with pytest.raises(EvidenceInvalid):
            _validate(base, quality, probe, root)
    finally:
        metadata_path.unlink(missing_ok=True)
        backup.rename(metadata_path)

    original_metadata = metadata_path.read_bytes()
    try:
        metadata_path.write_bytes(original_metadata + b"\0")
        with pytest.raises(EvidenceInvalid):
            _validate(base, quality, probe, root)
    finally:
        metadata_path.write_bytes(original_metadata)

    inventory = metadata_path.parent
    extra = inventory / "planted.tmp"
    try:
        extra.write_bytes(b"planted")
        with pytest.raises(EvidenceInvalid):
            _validate(base, quality, probe, root)
    finally:
        extra.unlink(missing_ok=True)

    serial_root = root / _SERIAL
    relocated = root / f"{_SERIAL}.real"
    serial_root.rename(relocated)
    try:
        serial_root.symlink_to(relocated.name, target_is_directory=True)
        with pytest.raises(EvidenceInvalid):
            _validate(base, quality, probe, root)
    finally:
        serial_root.unlink(missing_ok=True)
        relocated.rename(serial_root)

    alias = root.parent / f"{root.name}-alias"
    try:
        alias.symlink_to(root, target_is_directory=True)
        forged = copy.deepcopy(base)
        forged["configuration"]["quality"]["output_dir"] = str(alias)
        alias_quality = replace(quality, output_dir=alias)
        with pytest.raises(EvidenceInvalid):
            _validate(forged, alias_quality, probe, alias)
    finally:
        alias.unlink(missing_ok=True)


def test_protected_repo_blob_cmake_and_pylibiio_mutations_are_rejected(
    valid_pending: tuple[dict[str, Any], Any, TransientTransportProbeOptions, Path],
) -> None:
    base, quality, probe, root = valid_pending

    nonexistent = copy.deepcopy(base)
    nonexistent["runtime_provenance"]["firmware_runner"]["commit"] = "1" * 40
    with pytest.raises(EvidenceInvalid):
        _validate(nonexistent, quality, probe, root)

    dependency_forgery = copy.deepcopy(base)
    dependency = dependency_forgery["runtime_provenance"]["firmware_runner"][
        "local_dependencies"
    ][0]
    dependency_path = Path(dependency["absolute_path"])
    original_dependency = dependency_path.read_bytes()
    try:
        planted = original_dependency + b"planted"
        dependency_path.write_bytes(planted)
        digest = hashlib.sha256(planted).hexdigest()
        dependency["observed_sha256"] = digest
        dependency["commit_blob_sha256"] = digest
        with pytest.raises(EvidenceInvalid):
            _validate(dependency_forgery, quality, probe, root)
    finally:
        dependency_path.write_bytes(original_dependency)

    host = base["runtime_provenance"]["host_libiio"]
    cmake_path = Path(host["cmake_cache_path"])
    original_cmake = cmake_path.read_bytes()
    try:
        cmake_path.write_text(
            "CMAKE_HOME_DIRECTORY:INTERNAL=/planted/source\n", encoding="utf-8"
        )
        with pytest.raises(EvidenceInvalid):
            _validate(base, quality, probe, root)
    finally:
        cmake_path.write_bytes(original_cmake)

    pylibiio_forgery = copy.deepcopy(base)
    forged_host = pylibiio_forgery["runtime_provenance"]["host_libiio"]
    pylibiio_path = Path(forged_host["pylibiio_path"])
    original_pylibiio = pylibiio_path.read_bytes()
    try:
        planted = original_pylibiio + b"# planted\n"
        pylibiio_path.write_bytes(planted)
        digest = hashlib.sha256(planted).hexdigest()
        forged_host["pylibiio_sha256"] = digest
        forged_host["pylibiio_commit_blob_sha256"] = digest
        with pytest.raises(EvidenceInvalid):
            _validate(pylibiio_forgery, quality, probe, root)
    finally:
        pylibiio_path.write_bytes(original_pylibiio)

    substituted_tag = copy.deepcopy(base)
    substituted_tag["runtime_provenance"]["host_libiio"]["protected_tag_commit"] = (
        "2" * 40
    )
    with pytest.raises(EvidenceInvalid):
        _validate(substituted_tag, quality, probe, root)
