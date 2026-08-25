"""Hardware-free parser, planning, resume, and aggregate-verdict oracles."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest

from .metadata_abi import (
    TandemEventDirection,
    TandemGainEvent,
    parse_tandem_frame_metadata,
)
from .modulated_hardware import (
    DEFAULT_MODULATED_TX2_GAIN_DB,
    MODE_NATIVE_HYBRID,
    MODE_TANDEM,
    RELEASE_MODULATED_MODES,
    ModulatedHardwareOptions,
    evaluate_modulated_hardware_report,
    modulated_mode_evidence_policy,
)
from .release_campaign import build_release_plan
from .release_cli import (
    AGGREGATE_CHECKPOINT,
    PhaseSpec,
    ReleaseCliError,
    ReleaseHardwareOptions,
    ValidatedPhase,
    _base_quality,
    _release_canonical_tandem_evidence_bytes,
    _release_tandem_metadata_dict,
    _soak_temperature_errors,
    _steady_inputs,
    _tandem_batch_stable_suffix,
    parse_cli_args,
    phase_specs,
    plan_document,
    production_validator,
    run_aggregate,
)
from .tandem_quality import AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES
from .test_transient_hardware_oracles import (
    _FakeRadio,
    _metadata_wire,
    _run_fake,
    _tone_raw,
)
from .transient_hardware import (
    TRANSIENT_MODES,
    TransientCaptureOptions,
)

COMMIT = "6" * 40


def _arguments(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "--authorize-tx2-loopback",
        "--radio-serial",
        "radio-a",
        "--firmware-version",
        "v0.41-plutoplus-spf-tandem-agc-v8",
        "--physical-attenuation-db",
        "0",
        "--output",
        str(tmp_path / "release"),
        *extra,
    ]


def _parse(tmp_path: Path, *extra: str):
    return parse_cli_args(
        _arguments(tmp_path, *extra),
        environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
    )


def test_parser_requires_explicit_authorization_and_env_pinned_libiio(
    tmp_path: Path,
) -> None:
    arguments = _arguments(tmp_path)
    arguments.remove("--authorize-tx2-loopback")
    with pytest.raises(SystemExit):
        parse_cli_args(arguments, environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT})
    with pytest.raises(SystemExit):
        parse_cli_args(_arguments(tmp_path), environ={})


def test_parser_anchors_literal_firmware_and_scopes_output_by_serial(
    tmp_path: Path,
) -> None:
    options = _parse(tmp_path, "--plan-only")

    assert options.firmware_pattern == (r"\Av0\.41\-plutoplus\-spf\-tandem\-agc\-v8\Z")
    assert options.output_dir == (tmp_path / "release" / "radio-a").resolve()
    assert set(dict(options.harness_sources)) >= {
        "release_cli.py",
        "release_campaign.py",
        "transient_hardware.py",
        "modulated_hardware.py",
    }
    assert all(len(digest) == 64 for _name, digest in options.harness_sources)
    plan = plan_document(options)
    assert plan["deployment_performed"] is False
    assert plan["configuration"]["modulated_tx2_gain_db"] == -42.0
    assert plan["configuration"]["autonomous_native_gain_control_modes"] == [
        "slow_attack",
        "fast_attack",
    ]
    assert plan["configuration"]["modulated_modes"] == list(RELEASE_MODULATED_MODES)
    assert MODE_NATIVE_HYBRID not in plan["configuration"]["modulated_modes"]


def test_plan_fingerprint_binds_release_harness_source_manifest(
    tmp_path: Path,
) -> None:
    options = _parse(tmp_path, "--plan-only")
    planted_sources = (
        *options.harness_sources[:-1],
        (options.harness_sources[-1][0], "0" * 64),
    )

    assert (
        plan_document(options)["fingerprint"]
        != plan_document(replace(options, harness_sources=planted_sources))[
            "fingerprint"
        ]
    )


def test_parser_rejects_serial_path_traversal_before_output_join(
    tmp_path: Path,
) -> None:
    arguments = _arguments(tmp_path)
    arguments[arguments.index("radio-a")] = "../radio-a"
    with pytest.raises(SystemExit):
        parse_cli_args(
            arguments,
            environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
        )


def test_parser_rejects_precreated_serial_output_symlink(tmp_path: Path) -> None:
    base = tmp_path / "release"
    outside = tmp_path / "outside"
    base.mkdir()
    outside.mkdir()
    (base / "radio-a").symlink_to(outside, target_is_directory=True)

    with pytest.raises(SystemExit):
        _parse(tmp_path, "--phase", "transient", "--band", "low=915000000")


def test_aggregate_rechecks_serial_symlink_swap_before_executor(
    tmp_path: Path,
) -> None:
    options = _parse(tmp_path, "--phase", "transient", "--band", "low=915000000")
    outside = tmp_path / "outside"
    outside.mkdir()
    options.output_dir.parent.mkdir(parents=True, exist_ok=True)
    options.output_dir.symlink_to(outside, target_is_directory=True)
    calls: list[tuple[str, str]] = []
    execute, validate = _fake_boundaries(calls)

    with pytest.raises(ReleaseCliError, match="symlink"):
        run_aggregate(options, execute, validate)
    assert calls == []


def test_aggregate_rejects_precreated_attempt_symlink_before_executor(
    tmp_path: Path,
) -> None:
    options = _parse(tmp_path, "--phase", "transient", "--band", "low=915000000")
    spec = phase_specs(options)[0]
    attempt = options.output_dir / "artifacts" / spec.key / "attempt-0001"
    outside = tmp_path / "outside-attempt"
    attempt.parent.mkdir(parents=True, exist_ok=True)
    outside.mkdir()
    attempt.symlink_to(outside, target_is_directory=True)
    calls: list[tuple[str, str]] = []
    execute, validate = _fake_boundaries(calls)

    with pytest.raises(ReleaseCliError, match="symlink"):
        run_aggregate(options, execute, validate)
    assert calls == []


def test_characterization_and_baseline_soak_are_distinct_plans(
    tmp_path: Path,
) -> None:
    characterization = _parse(tmp_path / "characterization", "--phase", "steady")
    soak = _parse(tmp_path / "soak", "--phase", "steady", "--policy-set", "baseline")

    assert phase_specs(characterization)[0].key == "steady_characterization"
    assert characterization.repeat_cycles == 1
    assert phase_specs(soak)[0].key == "steady_soak"
    assert soak.repeat_cycles == 4
    assert soak.cycle_interval_seconds == 1_200.0
    full_config, full_base = _steady_inputs(
        characterization, characterization.output_dir / "work"
    )
    soak_config, soak_base = _steady_inputs(soak, soak.output_dir / "work")
    full_factors = {
        policy.factor
        for policy in build_release_plan(full_config, full_base).policy_cases
    }
    assert full_factors == {
        "baseline",
        "low_power_threshold",
        "large_lmt_threshold",
        "adc_thresholds",
        "low_power_dwell",
        "cooldown",
    }
    assert build_release_plan(soak_config, soak_base).policy_cases == (
        soak_config.policy_cases
    )
    assert soak_config.policy_cases[0].factor == "baseline"
    assert full_base.native_gain_control_modes == AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES
    assert soak_base.native_gain_control_modes == AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES


def _fake_boundaries(calls: list[tuple[str, str]]):
    def execute(spec: PhaseSpec, work_dir: Path) -> Path:
        calls.append((spec.key, work_dir.name))
        path = work_dir / "fake-report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"key": spec.key, "verdict": "pass", "cleanup": True}) + "\n",
            encoding="utf-8",
        )
        return path

    def validate(spec: PhaseSpec, path: Path, _work_dir: Path) -> ValidatedPhase:
        report = json.loads(path.read_text(encoding="utf-8"))
        return ValidatedPhase(
            str(report["verdict"]),
            report.get("cleanup") is True,
            {"key": spec.key},
        )

    return execute, validate


def test_fake_aggregate_requires_every_requested_phase_and_cleanup(
    tmp_path: Path,
) -> None:
    options = _parse(
        tmp_path,
        "--phase",
        "transient",
        "--band",
        "low=915000000",
        "--band",
        "high=5800000000",
    )
    calls: list[tuple[str, str]] = []
    execute, validate = _fake_boundaries(calls)

    report, report_path = run_aggregate(options, execute, validate)

    assert report_path.is_file()
    assert report["verdict"] == "pass"
    assert report["all_requested_phases_complete"] is True
    assert report["all_cleanup_verified"] is True
    assert [key for key, _attempt in calls] == [
        "transient_low",
        "transient_high",
    ]


def test_resume_revalidates_hash_and_never_reruns_completed_artifact(
    tmp_path: Path,
) -> None:
    options = _parse(tmp_path, "--phase", "transient", "--band", "low=915000000")
    calls: list[tuple[str, str]] = []
    execute, validate = _fake_boundaries(calls)
    first, _path = run_aggregate(options, execute, validate)
    artifact = Path(first["phases"]["transient_low"]["report_path"])
    artifact.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ReleaseCliError, match="artifact changed"):
        run_aggregate(options, execute, validate)
    assert len(calls) == 1


def test_interrupted_artifact_is_abandoned_and_fresh_attempt_is_used(
    tmp_path: Path,
) -> None:
    options = _parse(tmp_path, "--phase", "transient", "--band", "low=915000000")
    specs = phase_specs(options)
    calls: list[tuple[str, str]] = []
    execute, validate = _fake_boundaries(calls)
    # Plant a valid new checkpoint, then model power loss after the running mark.
    from .release_cli import _atomic_json, _new_checkpoint

    checkpoint = _new_checkpoint(options, specs)
    record = checkpoint["phases"]["transient_low"]
    record.update(
        {
            "status": "running",
            "attempts": 1,
            "work_dir": str(options.output_dir / "artifacts" / "old"),
        }
    )
    _atomic_json(options.output_dir / AGGREGATE_CHECKPOINT, checkpoint)

    report, _path = run_aggregate(options, execute, validate)

    assert report["verdict"] == "pass"
    assert calls == [("transient_low", "attempt-0002")]
    history = report["phases"]["transient_low"]["history"]
    assert history[0]["status"] == "abandoned_untrusted_interrupted_attempt"


def test_incomplete_steady_stops_before_other_phase(tmp_path: Path) -> None:
    options = _parse(
        tmp_path,
        "--phase",
        "steady",
        "--phase",
        "transient",
        "--band",
        "low=915000000",
    )
    calls: list[str] = []

    def execute(spec: PhaseSpec, work_dir: Path) -> Path:
        calls.append(spec.key)
        path = work_dir / "fake-report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"kind": spec.kind}) + "\n", encoding="utf-8")
        return path

    def validate(spec: PhaseSpec, _path: Path, _work_dir: Path) -> ValidatedPhase:
        if spec.kind == "steady":
            return ValidatedPhase("incomplete", False, {"complete_runs": 1})
        return ValidatedPhase("pass", True, {})

    report, _path = run_aggregate(options, execute, validate)

    assert report["verdict"] == "incomplete"
    assert calls == ["steady_characterization"]
    assert report["phases"]["transient_low"]["status"] == "pending"


def test_cleanup_failure_cannot_produce_aggregate_pass(tmp_path: Path) -> None:
    options = _parse(tmp_path, "--phase", "modulated", "--band", "low=915000000")
    calls: list[tuple[str, str]] = []
    execute, _validate = _fake_boundaries(calls)

    def missing_cleanup(
        _spec: PhaseSpec, _path: Path, _work_dir: Path
    ) -> ValidatedPhase:
        return ValidatedPhase("pass", False, {})

    report, _path = run_aggregate(options, execute, missing_cleanup)

    assert report["verdict"] == "invalid"
    assert report["all_cleanup_verified"] is False
    assert report["phases"]["modulated_low"]["status"] == "failed"


def test_production_validator_compares_modulated_configuration_in_json_domain(
    tmp_path: Path,
) -> None:
    options = _parse(tmp_path, "--phase", "modulated", "--band", "low=915000000")
    spec = phase_specs(options)[0]
    work_dir = options.output_dir / "work"
    report_path = work_dir / "radio-a" / "modulated-hardware-report.json"
    modulated = ModulatedHardwareOptions(
        physical_attenuation_db=0.0,
        center_frequency_hz=915_000_000,
        tx2_gain_db=DEFAULT_MODULATED_TX2_GAIN_DB,
        max_seconds=options.phase_max_seconds,
        output_dir=work_dir,
    )
    configuration = json.loads(
        json.dumps(
            {
                **asdict(modulated),
                "output_dir": str(work_dir),
                "minimum_effective_attenuation_db": (
                    modulated.minimum_effective_attenuation_db
                ),
            },
            default=str,
        )
    )
    case_ids = [
        "desired_only",
        *(f"blocker_{index:02d}" for index in range(len(modulated.blocker_points))),
    ]
    desired_payload = (bytes(range(256)) * 256)[: modulated.capture_samples * 8]
    blocker_payload = bytes(value ^ 0xA5 for value in desired_payload)
    raw_by_case: dict[str, dict[str, object]] = {}
    for purpose, case_id, filename, payload in (
        (
            "desired_baseline",
            "desired_only",
            "desired-only-manual-fixed-frame-0000-rx0-rx1.cs16le",
            desired_payload,
        ),
        (
            "first_blocker",
            "blocker_00",
            "blocker-00-manual-fixed-frame-0000-rx0-rx1.cs16le",
            blocker_payload,
        ),
    ):
        digest = hashlib.sha256(payload).hexdigest()
        relative_path = Path(options.serial) / "diagnostic-iq" / filename
        path = work_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        raw_by_case[case_id] = {
            "payload": payload,
            "sha256": digest,
            "path": path,
            "provenance": {
                "purpose": purpose,
                "case_id": case_id,
                "mode": "manual_fixed",
                "measurement_index": 0,
                "path": relative_path.as_posix(),
                "sha256": digest,
                "bytes": len(payload),
                "encoding": "signed-16-bit-little-endian",
                "channel_layout": ["rx0_i", "rx0_q", "rx1_i", "rx1_q"],
                "samples_per_channel": modulated.capture_samples,
            },
        }

    def quality_summary(case_id: str) -> dict[str, object]:
        blocked = case_id != "desired_only"
        return {
            "schema": "plutosdr-fw.modulated-quality.v1",
            "reference_id": "reference-46",
            "iq_convention": "direct",
            "quality_valid": True,
            "quality_reasons": [],
            "evm_percent": [2.0, 2.0],
            "mer_db": [34.0, 34.0],
            "ser": [0.0, 0.0],
            "ber": [0.0, 0.0],
            "desired_gain_linear": [1.0, 1.0],
            "blocker_offset_hz": 320_000.0 if blocked else None,
            "blocker_power_db": -20.0 if blocked else None,
        }

    cleanup = {
        "verified": True,
        "failures": [],
        "tx1_gain_db": -89.75,
        "tx2_gain_db": -89.75,
        "selectors": [3, 3, 3, 3],
        "dds": {
            f"altvoltage{index}": {"present": True, "scale": 0.0, "raw": 0.0}
            for index in range(8)
        },
    }

    def tandem_frame(sequence: int) -> dict[str, object]:
        first = sequence == 0
        return {
            "metadata": {
                "buffer_sequence": sequence,
                "first_sample_sequence": sequence * modulated.capture_samples,
                "samples_per_channel": modulated.capture_samples,
                "tandem_transition_count": 0,
                "gain_events": [],
            },
            "continuity": {
                "buffer_delta": None if first else 1,
                "sample_delta": None if first else modulated.capture_samples,
                "missing_frame_count": 0,
                "transition_count_delta": None if first else 0,
                "visible_event_count": 0,
                "hidden_transition_count": 0,
                "initial_unrepresented_transition_count": 0,
                "cumulative_missing_frame_count": 0,
                "cumulative_hidden_transition_count": 0,
                "cumulative_event_sequence_hole_count": 0,
            },
        }

    def raw_measurements(case_id: str) -> list[dict[str, object]]:
        artifact = raw_by_case[case_id]
        payload = artifact["payload"]
        assert isinstance(payload, bytes)
        return [
            {
                "sha256": artifact["sha256"],
                "iq_bytes": len(payload),
                "raw_iq_provenance": artifact["provenance"],
            }
        ]

    report = {
        "schema": "plutosdr-fw.modulated-hardware.v1",
        "verdict": "pass",
        "identity": {
            "serial": options.serial,
            "uri": "usb:1.2.3",
            "libiio_source_commit": COMMIT,
            "context_attrs": {"fw_version": options.firmware_version},
        },
        "configuration": configuration,
        "mode_evidence_policy": modulated_mode_evidence_policy(),
        "rf": {"center_frequency_hz_requested": 915_000_000},
        "cleanup": cleanup,
        "waveforms": [
            {
                "case_id": case_id,
                "kind": (
                    "desired_only" if case_id == "desired_only" else "composite_blocker"
                ),
                "dma_cleanup": {
                    "mute": cleanup,
                    "buffer_closed": True,
                    "buffer_release_method": "explicit_close",
                    "failures": [],
                },
            }
            for case_id in case_ids
        ],
        "runs": [
            {
                "case_id": case_id,
                "mode": mode,
                "tx2_gain_requested_db": DEFAULT_MODULATED_TX2_GAIN_DB,
                "tx2_gain_readback_db": DEFAULT_MODULATED_TX2_GAIN_DB,
                "effective_attenuation_db": (
                    modulated.minimum_effective_attenuation_db
                ),
                "summary": quality_summary(case_id),
                **(
                    {
                        "settling": {"frames": 1, "trace": [tandem_frame(0)]},
                        "measurements": [tandem_frame(1)],
                    }
                    if mode == MODE_TANDEM
                    else (
                        {"measurements": raw_measurements(case_id)}
                        if case_id in raw_by_case and mode == "manual_fixed"
                        else {}
                    )
                ),
            }
            for case_id in case_ids
            for mode in modulated.modes
        ],
    }
    report["evaluation"] = evaluate_modulated_hardware_report(
        report,
        modulated.degradation_thresholds,
        expected_modes=modulated.modes,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")

    validated = production_validator(options)(spec, report_path, work_dir)

    assert validated.verdict == "pass"
    assert validated.cleanup_verified is True
    expected_raw_summary: dict[str, object] = {}
    for artifact in raw_by_case.values():
        provenance = artifact["provenance"]
        assert isinstance(provenance, dict)
        expected_raw_summary[str(provenance["purpose"])] = provenance
    assert validated.summary["raw_iq_provenance"] == expected_raw_summary

    def raw_frame(document: dict[str, object], case_id: str) -> dict[str, object]:
        runs = document["runs"]
        assert isinstance(runs, list)
        run = next(
            item
            for item in runs
            if item["case_id"] == case_id and item["mode"] == "manual_fixed"
        )
        return run["measurements"][0]

    valid_report = json.loads(json.dumps(report))
    assert modulated.modes == RELEASE_MODULATED_MODES
    assert MODE_NATIVE_HYBRID not in {run["mode"] for run in valid_report["runs"]}
    report["evaluation"]["degradation_valid"] = False
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="differs from recomputation"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    report["mode_evidence_policy"]["native_hybrid"]["release_qualification_claim"] = (
        True
    )
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="mode evidence policy differs"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    planted_hybrid = dict(report["runs"][0])
    planted_hybrid["mode"] = MODE_NATIVE_HYBRID
    report["runs"].append(planted_hybrid)
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="mode/blocker coverage differs"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    report["runs"][-1]["summary"]["iq_convention"] = "conjugated"
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="IQ convention changed"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    tandem_run = next(run for run in report["runs"] if run["mode"] == MODE_TANDEM)
    tandem_run["measurements"][0]["continuity"]["sample_delta"] += 1
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="gap evidence differs from metadata"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    report["waveforms"][0]["dma_cleanup"]["mute"]["verified"] = False
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="cyclic-DMA cleanup was not verified"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    report["runs"][0]["tx2_gain_readback_db"] = -41.75
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="TX2 gain readback differs from plan"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    target_frame = raw_frame(report, "blocker_00")
    target_frame["raw_iq_provenance"]["path"] = "../../escaped.cs16le"
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="escapes the phase work directory"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    report["runs"][1]["measurements"] = [dict(raw_measurements("desired_only")[0])]
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="exactly two raw-IQ provenance"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    raw_frame(report, "blocker_00").pop("raw_iq_provenance")
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="exactly two raw-IQ provenance"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    raw_frame(report, "blocker_00")["raw_iq_provenance"]["channel_layout"] = [
        "rx1_i",
        "rx1_q",
        "rx0_i",
        "rx0_q",
    ]
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="channel layout differs from plan"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    raw_frame(report, "blocker_00")["raw_iq_provenance"]["measurement_index"] = 1
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="frame linkage differs from plan"):
        production_validator(options)(spec, report_path, work_dir)

    report_path.write_text(json.dumps(valid_report) + "\n", encoding="utf-8")
    desired_path = raw_by_case["desired_only"]["path"]
    desired_payload = raw_by_case["desired_only"]["payload"]
    assert isinstance(desired_path, Path)
    assert isinstance(desired_payload, bytes)
    blocker_path = raw_by_case["blocker_00"]["path"]
    blocker_payload = raw_by_case["blocker_00"]["payload"]
    assert isinstance(blocker_path, Path)
    assert isinstance(blocker_payload, bytes)

    report = json.loads(json.dumps(valid_report))
    desired_digest = hashlib.sha256(desired_payload).hexdigest()
    blocker_frame = raw_frame(report, "blocker_00")
    blocker_frame["sha256"] = desired_digest
    blocker_frame["raw_iq_provenance"]["sha256"] = desired_digest
    blocker_path.write_bytes(desired_payload)
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="SHA-256 values are not distinct"):
        production_validator(options)(spec, report_path, work_dir)

    blocker_path.write_bytes(blocker_payload)
    report_path.write_text(json.dumps(valid_report) + "\n", encoding="utf-8")
    stale_path = blocker_path.parent / "stale-frame.cs16le"
    stale_path.write_bytes(b"stale")
    with pytest.raises(ReleaseCliError, match="directory contents differ from plan"):
        production_validator(options)(spec, report_path, work_dir)
    stale_path.unlink()

    desired_path.write_bytes(desired_payload[:-1])
    with pytest.raises(ReleaseCliError, match="on-disk byte count differs"):
        production_validator(options)(spec, report_path, work_dir)

    desired_path.write_bytes(desired_payload)
    blocker_path.write_bytes(blocker_payload[:-1] + b"X")
    with pytest.raises(ReleaseCliError, match="on-disk SHA-256 differs"):
        production_validator(options)(spec, report_path, work_dir)

    blocker_path.unlink()
    with pytest.raises(ReleaseCliError, match="raw-IQ artifact is missing"):
        production_validator(options)(spec, report_path, work_dir)


def _generated_v2_transient_fixture(
    tmp_path: Path,
) -> tuple[ReleaseHardwareOptions, PhaseSpec, Path, Path, dict[str, Any]]:
    options = _parse(
        tmp_path,
        "--phase",
        "transient",
        "--band",
        "low=915000000",
        "--sample-rate-hz",
        "1000000",
    )
    spec = phase_specs(options)[0]
    work_dir = tmp_path / "transient-phase-work"
    quality = _base_quality(options, output_dir=work_dir, band=spec.band)

    class ReleaseFakeRadio(_FakeRadio):
        def capture_iq(
            self, buffer: object, *, metadata: bool, samples_per_channel: int
        ) -> tuple[bytes, bytes | None, int]:
            if metadata:
                return super().capture_iq(
                    buffer,
                    metadata=True,
                    samples_per_channel=samples_per_channel,
                )
            raw = _tone_raw(
                samples=samples_per_channel,
                amplitude=1_200.0,
                seed=len(self.operations),
            )
            return raw, None, 1_000 + len(self.operations)

    radio = ReleaseFakeRadio(work_dir)
    radio.options.serial = options.serial
    radio.options.sample_rate_hz = quality.sample_rate_hz
    radio.options.center_frequency_hz = quality.center_frequency_hz
    radio.identity = {
        "serial": options.serial,
        "uri": "usb:1.2.3",
        "libiio_source_commit": options.libiio_source_commit,
        "context_attrs": {"fw_version": options.firmware_version},
    }
    report, report_path = _run_fake(
        radio,
        quality,
        capture=TransientCaptureOptions(),
    )
    report["cleanup"] = {
        "verified": True,
        "failures": [],
        "tx1_gain_db": -89.75,
        "tx2_gain_db": -89.75,
        "selectors": [3, 3, 3, 3],
        "dds": {
            f"altvoltage{index}": {
                "present": True,
                "scale": 0.0,
                "raw": 0.0,
            }
            for index in range(8)
        },
    }
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return options, spec, work_dir, report_path.resolve(), report


def _tandem_mode(report: dict[str, Any]) -> dict[str, Any]:
    modes = report["modes"]
    assert isinstance(modes, list)
    return next(mode for mode in modes if mode["mode"] == MODE_TANDEM)


def _refresh_tandem_manifest_digest(tandem: dict[str, Any]) -> None:
    manifest = tandem["acquisition"]["artifact_manifest"]
    encoded = json.dumps(
        manifest["entries"],
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    manifest["entries_canonical_json_sha256"] = hashlib.sha256(encoded).hexdigest()


def _refresh_tandem_projection_claim(report: dict[str, Any], work_dir: Path) -> None:
    tandem = _tandem_mode(report)
    parsed = [
        parse_tandem_frame_metadata(
            (work_dir / frame["raw_metadata_path"]).read_bytes()
        )
        for frame in tandem["batch_frames"]
    ]
    canonical = _release_canonical_tandem_evidence_bytes(tandem, parsed)
    ledger = tandem["acquisition"]["memory_ledger"]
    ledger["canonical_evidence_projection_bytes"] = len(canonical)
    ledger["canonical_evidence_projection_sha256"] = hashlib.sha256(
        canonical
    ).hexdigest()


def _rewrite_tandem_metadata_sidecar(
    report: dict[str, Any],
    work_dir: Path,
    *,
    frame_index: int,
    metadata: Any,
) -> None:
    tandem = _tandem_mode(report)
    frame = tandem["batch_frames"][frame_index]
    payload = _metadata_wire(metadata)
    parsed = parse_tandem_frame_metadata(payload)
    path = work_dir / frame["raw_metadata_path"]
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    updated = {
        "raw_metadata_bytes": len(payload),
        "raw_metadata_sha256": digest,
        "metadata": _release_tandem_metadata_dict(parsed),
    }
    frame.update(updated)
    for key in ("attack_frames", "release_frames"):
        for retained in tandem[key]:
            if retained["frame_index"] == frame_index:
                retained.update(updated)
    manifest = tandem["acquisition"]["artifact_manifest"]
    entry = manifest["entries"][frame_index]
    entry["raw_metadata_bytes"] = len(payload)
    entry["raw_metadata_sha256"] = digest
    manifest["raw_metadata_total_bytes"] = sum(
        item["raw_metadata_bytes"] for item in manifest["entries"]
    )
    _refresh_tandem_manifest_digest(tandem)


def _rewrite_tandem_temperatures(
    report: dict[str, Any],
    work_dir: Path,
    temperatures: dict[int, int | None],
) -> None:
    tandem = _tandem_mode(report)
    for frame_index, temperature in temperatures.items():
        frame = tandem["batch_frames"][frame_index]
        parsed = parse_tandem_frame_metadata(
            (work_dir / frame["raw_metadata_path"]).read_bytes()
        )
        _rewrite_tandem_metadata_sidecar(
            report,
            work_dir,
            frame_index=frame_index,
            metadata=replace(parsed, ad9361_temperature_mdeg_c=temperature),
        )
    _refresh_tandem_projection_claim(report, work_dir)


def _plant_tandem_directional_undo(
    report: dict[str, Any], work_dir: Path, *, response: str
) -> None:
    """Add one wire-valid unassigned event that undoes a commanded response."""

    tandem = _tandem_mode(report)
    frames = tandem["batch_frames"]
    parsed = [
        parse_tandem_frame_metadata(
            (work_dir / frame["raw_metadata_path"]).read_bytes()
        )
        for frame in frames
    ]
    if response == "attack":
        planted_index = 17
        direction = TandemEventDirection.INCREASE
        event_sequence = parsed[16].gain_events[-1].event_sequence + 1
    elif response == "release":
        planted_index = 41
        direction = TandemEventDirection.DECREASE
        event_sequence = parsed[40].gain_events[-1].event_sequence + 1
    else:
        raise AssertionError(f"unknown response {response!r}")

    planted_endpoint_delta = 1 if direction == TandemEventDirection.INCREASE else -1
    planted_event = TandemGainEvent(
        sample_sequence=parsed[planted_index].first_sample_sequence + 1_024,
        event_sequence=event_sequence,
        flags=int(direction) << 4,
        rx1_gain_index=(parsed[planted_index].rx1_gain_index + planted_endpoint_delta),
        rx2_gain_index=(parsed[planted_index].rx2_gain_index + planted_endpoint_delta),
    )
    for frame_index in range(planted_index, len(frames)):
        metadata = parsed[frame_index]
        gain_events = metadata.gain_events
        event_count = metadata.event_count
        transition_delta = 1
        endpoint_delta = 1 if response == "attack" else -1
        if frame_index == planted_index:
            gain_events = (planted_event,)
            event_count = 1
        elif response == "attack" and frame_index == 40:
            pre_release_decrease = TandemGainEvent(
                sample_sequence=metadata.first_sample_sequence + 1_024,
                event_sequence=event_sequence + 1,
                flags=int(TandemEventDirection.DECREASE) << 4,
                rx1_gain_index=metadata.rx1_gain_index - 1,
                rx2_gain_index=metadata.rx2_gain_index - 1,
            )
            gain_events = (
                pre_release_decrease,
                *(
                    replace(event, event_sequence=event.event_sequence + 2)
                    for event in metadata.gain_events
                ),
            )
            event_count = 2
            transition_delta = 2
            endpoint_delta = 0
        elif response == "attack" and frame_index > 40:
            transition_delta = 2
            endpoint_delta = 0
        updated = replace(
            metadata,
            event_count=event_count,
            tandem_transition_count=(
                metadata.tandem_transition_count + transition_delta
            ),
            rx1_gain_index=metadata.rx1_gain_index + endpoint_delta,
            rx2_gain_index=metadata.rx2_gain_index + endpoint_delta,
            gain_events=gain_events,
        )
        _rewrite_tandem_metadata_sidecar(
            report,
            work_dir,
            frame_index=frame_index,
            metadata=updated,
        )

    previous_transition_count: int | None = None
    for frame in frames:
        metadata = frame["metadata"]
        current_transition_count = metadata["tandem_transition_count"]
        if previous_transition_count is not None:
            frame["continuity"]["transition_count_delta"] = (
                current_transition_count - previous_transition_count
            ) % (1 << 32)
            frame["continuity"]["visible_event_count"] = len(metadata["gain_events"])
        previous_transition_count = current_transition_count
    for key in ("attack_frames", "release_frames"):
        for retained in tandem[key]:
            retained["continuity"] = json.loads(
                json.dumps(frames[retained["frame_index"]]["continuity"])
            )

    groups = tandem["partition"]["groups"]
    tandem["partition"]["stable_suffixes"] = {
        phase: _tandem_batch_stable_suffix(
            frames,
            groups[phase]["frame_indices"],
            tolerance_db=1.0,
        )
        for phase in (
            "fully_post_attack_pre_release",
            "fully_post_release",
        )
    }

    gain = tandem["gain_evidence"]
    planted_event_count = 2 if response == "attack" else 1
    gain["event_count"] += planted_event_count
    gain["unassigned_event_count"] += planted_event_count
    if response == "attack":
        gain["transitions"][1]["event"]["event_sequence"] += 2
    comparison = next(
        item for item in report["comparison"] if item["mode"] == MODE_TANDEM
    )
    comparison["gain_evidence"] = json.loads(json.dumps(gain))

    last_metadata = frames[-1]["metadata"]
    endpoint = last_metadata["bench_gain_indices"]
    transition_count = last_metadata["tandem_transition_count"]
    acquisition = tandem["acquisition"]
    for status_key in ("pre_close_tandem_status", "post_close_tandem_status"):
        acquisition[status_key].update(
            {
                "transition_count": transition_count,
                "rx1_gain_index": endpoint[0],
                "rx2_gain_index": endpoint[1],
            }
        )
    tandem["tandem_status_after"] = json.loads(
        json.dumps(acquisition["post_close_tandem_status"])
    )
    close = acquisition["close_counter_ledger"]
    close.update(
        {
            "last_frame_transition_count": transition_count,
            "pre_transition_count": transition_count,
            "post_transition_count": transition_count,
            "last_frame_to_pre_close_forward_delta": 0,
            "transition_count_forward_delta": 0,
            "pre_endpoint": endpoint,
            "post_endpoint": endpoint,
        }
    )
    _refresh_tandem_projection_claim(report, work_dir)


def _plant_schedule_candidate(
    report: dict[str, Any], *, command_id: str, after_b: bool
) -> None:
    schedule = _tandem_mode(report)["acquisition"]["schedule_diagnostics"][command_id]
    reads = schedule["counter_reads"]
    role = "raw_c_causal_advance" if after_b else "raw_b_first_advance"
    insert_at = next(index for index, item in enumerate(reads) if item["role"] == role)
    candidate = dict(reads[insert_at])
    candidate["role"] = "post_write_advance_candidate"
    candidate["host_after_ns"] = candidate["host_before_ns"]
    reads.insert(insert_at, candidate)
    for ordinal, item in enumerate(reads):
        item["ordinal"] = ordinal
    schedule["raw_bracket"]["post_write_read_count"] += 1


def test_runtime_generated_v2_transient_passes_production_validator(
    tmp_path: Path,
) -> None:
    options, spec, work_dir, report_path, _report = _generated_v2_transient_fixture(
        tmp_path
    )

    validated = production_validator(options)(spec, report_path, work_dir)

    assert validated.verdict == "pass"
    assert validated.cleanup_verified is True
    assert validated.summary["mode_count"] == len(TRANSIENT_MODES)


def test_production_validator_accepts_only_leading_temperature_omissions(
    tmp_path: Path,
) -> None:
    options, spec, work_dir, report_path, report = _generated_v2_transient_fixture(
        tmp_path / "leading-temperature-omission"
    )
    _rewrite_tandem_temperatures(report, work_dir, {0: None, 1: None})
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")

    validated = production_validator(options)(spec, report_path, work_dir)

    assert validated.cleanup_verified is True


@pytest.mark.parametrize(
    "temperatures",
    (
        {2: None},
        {index: None for index in range(64)},
        {0: 125_001},
        {0: -40_001},
    ),
)
def test_production_validator_rejects_invalid_temperature_sessions(
    tmp_path: Path, temperatures: dict[int, int | None]
) -> None:
    options, spec, work_dir, report_path, report = _generated_v2_transient_fixture(
        tmp_path / f"invalid-temperature-{len(temperatures)}-{next(iter(temperatures))}"
    )
    _rewrite_tandem_temperatures(report, work_dir, temperatures)
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")

    with pytest.raises(ReleaseCliError):
        production_validator(options)(spec, report_path, work_dir)


def test_release_validator_recomputes_whole_window_stable_suffix(
    tmp_path: Path,
) -> None:
    _options, _spec, _work_dir, _report_path, report = _generated_v2_transient_fixture(
        tmp_path
    )
    tandem = _tandem_mode(report)
    frames = tandem["batch_frames"]
    partition = tandem["partition"]
    assert isinstance(frames, list)
    assert isinstance(partition, dict)
    indices = partition["groups"]["fully_post_release"]["frame_indices"]
    for frame_index in indices[-8:]:
        windows = frames[frame_index]["analysis"]["windows"]
        for window_index, window in enumerate(windows):
            level = -20.0 if window_index % 2 == 0 else -40.0
            window["tone_dbfs"] = [level, level]

    with pytest.raises(ValueError, match="exceeds its RF tolerance"):
        _tandem_batch_stable_suffix(frames, indices, tolerance_db=1.0)


@pytest.mark.parametrize("response", ("attack", "release"))
def test_production_validator_rejects_self_consistent_directional_undo(
    tmp_path: Path, response: str
) -> None:
    options, spec, work_dir, report_path, report = _generated_v2_transient_fixture(
        tmp_path
    )
    _plant_tandem_directional_undo(report, work_dir, response=response)
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")

    with pytest.raises(ReleaseCliError) as raised:
        production_validator(options)(spec, report_path, work_dir)
    assert str(raised.value) == (
        "transient tandem stable endpoints do not prove the commanded "
        "attack decrease and release increase"
    )


def test_production_validator_rejects_planted_v2_contract_mutations(
    tmp_path: Path,
) -> None:
    options, spec, work_dir, report_path, valid_report = (
        _generated_v2_transient_fixture(tmp_path)
    )
    validate = production_validator(options)

    def target(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        acquisition = tandem["acquisition"]
        planted = (acquisition["targets"]["strong_attack"]["target_raw"] + 1) % (
            1 << 32
        )
        acquisition["targets"]["strong_attack"]["target_raw"] = planted
        acquisition["schedule_diagnostics"]["strong_attack"]["target"]["target_raw"] = (
            planted
        )
        acquisition["schedule_plan"]["commands"][0]["target_raw"] = planted

    def frozen_chronology(report: dict[str, Any]) -> None:
        plan = _tandem_mode(report)["acquisition"]["schedule_plan"]
        plan["targets_frozen_host_ns"] = plan["worker_start_requested_ns"] + 1

    def worker_start_chronology(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        plan = tandem["acquisition"]["schedule_plan"]
        attack = tandem["commands"][1]
        plan["worker_start_returned_ns"] = attack["host_after_ns"] + 1

    def tx1_pre_chronology(report: dict[str, Any]) -> None:
        schedule = _tandem_mode(report)["acquisition"]["schedule_diagnostics"][
            "strong_attack"
        ]
        raw_a = next(
            item
            for item in schedule["counter_reads"]
            if item["role"] == "raw_a_prewrite"
        )
        schedule["tx1_mute_assurance"]["pre"].update(
            {
                "host_before_ns": raw_a["host_after_ns"],
                "host_after_ns": raw_a["host_after_ns"],
            }
        )

    def refill_completion(report: dict[str, Any]) -> None:
        acquisition = _tandem_mode(report)["acquisition"]
        acquisition["initiating_refill_completion_monotonic_ns"] += 12_345

    def shutdown_chronology(report: dict[str, Any]) -> None:
        events = _tandem_mode(report)["acquisition"]["shutdown"]["events"]
        for index, event in enumerate(events):
            event["monotonic_ns"] = index

    def readback(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        acquisition = tandem["acquisition"]
        schedule = acquisition["schedule_diagnostics"]["weak_release"]
        command = tandem["commands"][2]
        unbound = acquisition["unbound_commands"]["weak_release"]
        observed = command["requested_level_db"] + 0.5
        schedule["deferred_tx2_readback"].update(
            {"observed_level_db": observed, "passed": False}
        )
        schedule["applied_level_db"] = observed
        command["applied_level_db"] = observed
        unbound["applied_level_db"] = observed
        effective = report["safety"]["physical_attenuation_db"] - observed
        command["effective_attenuation_db"] = effective
        unbound["effective_attenuation_db"] = effective

    def tx1(report: dict[str, Any]) -> None:
        assurance = _tandem_mode(report)["acquisition"]["schedule_diagnostics"][
            "strong_attack"
        ]["tx1_mute_assurance"]["post"]
        assurance.update({"observed_level_db": -70.0, "passed": False})

    def malformed_post_count(report: dict[str, Any]) -> None:
        schedule = _tandem_mode(report)["acquisition"]["schedule_diagnostics"][
            "strong_attack"
        ]
        schedule["raw_bracket"]["post_write_read_count"] = "3"

    def malformed_counter_read(report: dict[str, Any]) -> None:
        schedule = _tandem_mode(report)["acquisition"]["schedule_diagnostics"][
            "weak_release"
        ]
        schedule["counter_reads"][-1] = None

    def malformed_poll_observation(report: dict[str, Any]) -> None:
        schedule = _tandem_mode(report)["acquisition"]["schedule_diagnostics"][
            "strong_attack"
        ]
        schedule["target"]["poll_observations"][-2] = None

    def cache(report: dict[str, Any]) -> None:
        acquisition = _tandem_mode(report)["acquisition"]
        acquisition["configured_batch_cache_bytes"] += 1

    def refill(report: dict[str, Any]) -> None:
        acquisition = _tandem_mode(report)["acquisition"]
        acquisition["cached_replay_refill_calls"] = 62

    def measured_memory(report: dict[str, Any]) -> None:
        ledger = _tandem_mode(report)["acquisition"]["memory_ledger"]
        ledger["measured_finished_mode_and_parsed_metadata_bytes"] = 1

    def canonical_bytes(report: dict[str, Any]) -> None:
        ledger = _tandem_mode(report)["acquisition"]["memory_ledger"]
        ledger["canonical_evidence_projection_bytes"] += 1

    def canonical_sha(report: dict[str, Any]) -> None:
        ledger = _tandem_mode(report)["acquisition"]["memory_ledger"]
        ledger["canonical_evidence_projection_sha256"] = "0" * 64

    def canonical_method(report: dict[str, Any]) -> None:
        ledger = _tandem_mode(report)["acquisition"]["memory_ledger"]
        ledger["canonical_evidence_projection_method"] += ":planted"

    def canonicalized_target(report: dict[str, Any]) -> None:
        target(report)
        _refresh_tandem_projection_claim(report, work_dir)

    def phase_memory(report: dict[str, Any]) -> None:
        ledger = _tandem_mode(report)["acquisition"]["memory_ledger"]
        ledger["post_close_fft_workspace_bytes"] = 4_194_304
        ledger["post_close_materialization_envelope_bytes"] -= 4_194_304

    def partition(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        tandem["partition"]["phase_by_frame"][0] = "attack_bracket"
        tandem["batch_frames"][0]["batch_phase"] = "attack_bracket"

    def quality(report: dict[str, Any]) -> None:
        window = _tandem_mode(report)["batch_frames"][0]["analysis"]["windows"][0]
        window["quality_valid"] = False
        window["quality_reasons"] = ["planted_invalid_window"]

    def frame_unknown_field(report: dict[str, Any]) -> None:
        _tandem_mode(report)["batch_frames"][0]["fatal_error"] = (
            "planted preserved failure"
        )

    def analysis_unknown_field(report: dict[str, Any]) -> None:
        _tandem_mode(report)["batch_frames"][0]["analysis"]["fatal_error"] = (
            "planted preserved failure"
        )

    def continuity_unknown_field(report: dict[str, Any]) -> None:
        _tandem_mode(report)["batch_frames"][0]["continuity"]["fatal_error"] = (
            "planted preserved failure"
        )

    def metadata_unknown_field(report: dict[str, Any]) -> None:
        _tandem_mode(report)["batch_frames"][0]["metadata"]["fatal_error"] = (
            "planted preserved failure"
        )

    def metadata_numeric_type(report: dict[str, Any]) -> None:
        _tandem_mode(report)["batch_frames"][0]["metadata"]["version"] = 5.0

    def analysis_numeric_type(report: dict[str, Any]) -> None:
        _tandem_mode(report)["batch_frames"][0]["analysis"]["windows"][0][
            "window_index"
        ] = 0.0

    def malformed_final_event(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        frame = next(
            frame
            for frame in tandem["batch_frames"]
            if frame["metadata"]["gain_events"]
        )
        frame["metadata"]["gain_events"][-1] = None

    def malformed_frame_index(report: dict[str, Any]) -> None:
        _tandem_mode(report)["batch_frames"][0]["frame_index"] = "bad"

    def escaped_anchor_path(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        anchor_index = tandem["conditioning_anchor"]["source"]["source_frame_index"]
        tandem["batch_frames"][anchor_index]["iq_path"] = "/dev/zero"

    def escaped_release_anchor_path(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        release_source = tandem["response_observations"]["release"]["baseline_anchor"]
        tandem["batch_frames"][release_source["source_frame_index"]]["iq_path"] = (
            "../../outside"
        )

    def gain(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        tandem["gain_evidence"]["evidence_valid"] = False
        comparison = next(
            item for item in report["comparison"] if item["mode"] == MODE_TANDEM
        )
        comparison["gain_evidence"] = tandem["gain_evidence"]

    def response(report: dict[str, Any]) -> None:
        _tandem_mode(report)["responses"]["attack"]["evidence_valid"] = False

    def close_counter(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        acquisition = tandem["acquisition"]
        ledger = acquisition["close_counter_ledger"]
        post = (ledger["pre_transition_count"] + 65) % (1 << 32)
        ledger["post_transition_count"] = post
        ledger["transition_count_forward_delta"] = 65
        acquisition["post_close_tandem_status"]["transition_count"] = post
        tandem["tandem_status_after"]["transition_count"] = post

    def cancel(report: dict[str, Any]) -> None:
        shutdown = _tandem_mode(report)["acquisition"]["shutdown"]
        shutdown.update(
            {
                "cancel_required": True,
                "cancel_called": True,
                "cancel_succeeded": True,
                "shutdown_path": "cancel_after_full_cache_replay",
            }
        )

    def status(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        acquisition = tandem["acquisition"]
        acquisition["post_close_tandem_status"]["fifo_level"] = 1
        acquisition["close_counter_ledger"]["post_fifo_level"] = 1
        tandem["tandem_status_after"]["fifo_level"] = 1

    def configuration(report: dict[str, Any]) -> None:
        report["configuration"]["tandem_transport"]["queue_capacity_frames"] = 3
        _tandem_mode(report)["acquisition"]["queue_capacity_frames"] = 3
        report["evidence_policy"]["tandem_capture_queue_frames"] = 3

    def evidence_policy(report: dict[str, Any]) -> None:
        report["evidence_policy"]["tandem_aggregate_resident_bytes"] -= 1

    def metadata_request(report: dict[str, Any]) -> None:
        _tandem_mode(report)["metadata_request"]["decoded"]["initial_gain_db"] = 61

    def artifact_completion(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        frame = tandem["batch_frames"][0]
        frame["artifact_write_status"]["iq_write_completed"] = False
        manifest = tandem["acquisition"]["artifact_manifest"]
        manifest["entries"][0]["write_status"]["iq_write_completed"] = False
        manifest["completed_iq_files"] = 63
        manifest["write_complete"] = False
        _refresh_tandem_manifest_digest(tandem)

    def malformed_modes(report: dict[str, Any]) -> None:
        report["modes"] = [None]

    def malformed_comparison(report: dict[str, Any]) -> None:
        report["comparison"] = [None]

    def contradictory_failure(report: dict[str, Any]) -> None:
        report["failure_evidence"] = _tandem_mode(report)

    def fatal_error(report: dict[str, Any]) -> None:
        report["fatal_error"] = "planted contradictory PASS error"

    def cleanup_request_error(report: dict[str, Any]) -> None:
        report["cleanup_request_error"] = "planted contradictory cleanup error"

    def bench_mapping(report: dict[str, Any]) -> None:
        report["bench_port_mapping"]["stimulus"] = "bench TX1"

    def cleanup_unknown_field(report: dict[str, Any]) -> None:
        report["cleanup"]["fatal_error"] = "planted preserved failure"

    def final_rx_state_unknown_field(report: dict[str, Any]) -> None:
        _tandem_mode(report)["final_rx_state"]["fatal_error"] = (
            "planted restore failure"
        )

    mutations = [
        ("frozen target", target),
        ("pre-start chronology", frozen_chronology),
        ("worker-start chronology", worker_start_chronology),
        ("TX1-pre chronology", tx1_pre_chronology),
        ("initiating refill completion", refill_completion),
        ("shutdown chronology", shutdown_chronology),
        (
            "candidate before B",
            lambda report: _plant_schedule_candidate(
                report, command_id="strong_attack", after_b=False
            ),
        ),
        (
            "candidate after B",
            lambda report: _plant_schedule_candidate(
                report, command_id="weak_release", after_b=True
            ),
        ),
        ("deferred readback", readback),
        ("TX1 attestation", tx1),
        ("malformed post-write count", malformed_post_count),
        ("malformed counter read", malformed_counter_read),
        ("malformed poll observation", malformed_poll_observation),
        ("batch cache", cache),
        ("full replay", refill),
        ("claimed memory", measured_memory),
        ("canonical bytes", canonical_bytes),
        ("canonical SHA", canonical_sha),
        ("canonical method", canonical_method),
        ("self-consistent canonical target", canonicalized_target),
        ("phase memory", phase_memory),
        ("partition", partition),
        ("window quality", quality),
        ("frame unknown field", frame_unknown_field),
        ("analysis unknown field", analysis_unknown_field),
        ("continuity unknown field", continuity_unknown_field),
        ("metadata unknown field", metadata_unknown_field),
        ("metadata numeric type", metadata_numeric_type),
        ("analysis numeric type", analysis_numeric_type),
        ("malformed final event", malformed_final_event),
        ("malformed frame index", malformed_frame_index),
        ("escaped anchor path", escaped_anchor_path),
        ("escaped release anchor path", escaped_release_anchor_path),
        ("gain evidence", gain),
        ("response evidence", response),
        ("close counter", close_counter),
        ("successful cancel", cancel),
        ("post-close status", status),
        ("transport configuration", configuration),
        ("evidence policy", evidence_policy),
        ("metadata request", metadata_request),
        ("artifact completion", artifact_completion),
        ("malformed modes", malformed_modes),
        ("malformed comparison", malformed_comparison),
        ("contradictory failure evidence", contradictory_failure),
        ("failure-only fatal error", fatal_error),
        ("failure-only cleanup error", cleanup_request_error),
        ("bench mapping", bench_mapping),
        ("cleanup unknown field", cleanup_unknown_field),
        ("final RX state unknown field", final_rx_state_unknown_field),
    ]
    for label, mutate in mutations:
        planted = json.loads(json.dumps(valid_report))
        mutate(planted)
        if label not in {
            "canonical bytes",
            "canonical SHA",
            "malformed modes",
        }:
            _refresh_tandem_projection_claim(planted, work_dir)
        report_path.write_text(json.dumps(planted) + "\n", encoding="utf-8")
        try:
            validate(spec, report_path, work_dir)
        except ReleaseCliError:
            pass
        else:
            pytest.fail(f"planted {label} mutation was accepted")


def test_production_validator_stats_exact_sidecar_sizes_before_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    options, spec, work_dir, report_path, valid_report = (
        _generated_v2_transient_fixture(tmp_path)
    )
    frame = _tandem_mode(valid_report)["batch_frames"][0]
    paths = {
        (work_dir / frame["iq_path"]).resolve(),
        (work_dir / frame["raw_metadata_path"]).resolve(),
    }
    for path in paths:
        path.write_bytes(path.read_bytes() + b"\x00")

    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(path: Path) -> bytes:
        if path.resolve() in paths:
            raise AssertionError("oversized sidecar was read before its size gate")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    with pytest.raises(ReleaseCliError):
        production_validator(options)(spec, report_path, work_dir)


def test_production_validator_reparses_self_consistent_metadata_physics_mutations(
    tmp_path: Path,
) -> None:
    options, spec, work_dir, report_path, valid_report = (
        _generated_v2_transient_fixture(tmp_path)
    )
    validate = production_validator(options)
    frame_index = 18
    valid_frame = _tandem_mode(valid_report)["batch_frames"][frame_index]
    metadata_path = work_dir / valid_frame["raw_metadata_path"]
    original_payload = metadata_path.read_bytes()
    original = parse_tandem_frame_metadata(original_payload)

    prior_events = [
        event
        for frame in _tandem_mode(valid_report)["batch_frames"][:frame_index]
        for event in frame["metadata"]["gain_events"]
    ]
    first_event_sequence = (
        (prior_events[-1]["event_sequence"] + 1) % (1 << 32) if prior_events else 1
    )

    def events(count: int, *, spacing: int) -> tuple[TandemGainEvent, ...]:
        endpoint = original.rx1_gain_index
        planted: list[TandemGainEvent] = []
        for index in range(count):
            direction = (
                TandemEventDirection.DECREASE
                if index % 2 == 0
                else TandemEventDirection.INCREASE
            )
            endpoint += -1 if direction == TandemEventDirection.DECREASE else 1
            planted.append(
                TandemGainEvent(
                    sample_sequence=(
                        original.first_sample_sequence + 1_024 + index * spacing
                    ),
                    event_sequence=(first_event_sequence + index) % (1 << 32),
                    flags=int(direction) << 4,
                    rx1_gain_index=endpoint,
                    rx2_gain_index=endpoint,
                )
            )
        return tuple(planted)

    five_events = events(5, spacing=10_000)
    too_close_events = events(2, spacing=1)
    mutations = (
        ("six observations", replace(original, observation_count=6)),
        (
            "five visible events",
            replace(
                original,
                event_count=5,
                tandem_transition_count=original.tandem_transition_count + 5,
                rx1_gain_index=five_events[-1].rx1_gain_index,
                rx2_gain_index=five_events[-1].rx2_gain_index,
                gain_events=five_events,
            ),
        ),
        (
            "too-close events",
            replace(
                original,
                event_count=2,
                tandem_transition_count=original.tandem_transition_count + 2,
                rx1_gain_index=too_close_events[-1].rx1_gain_index,
                rx2_gain_index=too_close_events[-1].rx2_gain_index,
                gain_events=too_close_events,
            ),
        ),
    )
    for label, metadata in mutations:
        planted = json.loads(json.dumps(valid_report))
        _rewrite_tandem_metadata_sidecar(
            planted,
            work_dir,
            frame_index=frame_index,
            metadata=metadata,
        )
        _refresh_tandem_projection_claim(planted, work_dir)
        report_path.write_text(json.dumps(planted) + "\n", encoding="utf-8")
        try:
            validate(spec, report_path, work_dir)
        except ReleaseCliError:
            pass
        else:
            pytest.fail(f"planted {label} mutation was accepted")
        metadata_path.write_bytes(original_payload)


def test_production_validator_rejects_nonfinite_and_overflowed_json_numbers(
    tmp_path: Path,
) -> None:
    options, spec, work_dir, report_path, valid_report = (
        _generated_v2_transient_fixture(tmp_path)
    )
    validate = production_validator(options)
    planted = json.loads(json.dumps(valid_report))
    _tandem_mode(planted)["batch_frames"][0]["iq_bytes"] = float("nan")
    report_path.write_text(json.dumps(planted) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="strict finite JSON"):
        validate(spec, report_path, work_dir)

    encoded = json.dumps(valid_report)
    assert '"iq_bytes": 524288' in encoded
    report_path.write_text(
        encoded.replace('"iq_bytes": 524288', '"iq_bytes": 1e999', 1) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ReleaseCliError, match="strict finite JSON"):
        validate(spec, report_path, work_dir)


def test_production_validator_rejects_float_overflowing_json_integers_cleanly(
    tmp_path: Path,
) -> None:
    options, spec, work_dir, report_path, valid_report = (
        _generated_v2_transient_fixture(tmp_path)
    )
    validate = production_validator(options)
    huge = 10**4000

    def elapsed(report: dict[str, Any]) -> None:
        report["elapsed_seconds"] = huge

    def cleanup_gain(report: dict[str, Any]) -> None:
        report["cleanup"]["tx1_gain_db"] = huge

    def ordinary_final_gain(report: dict[str, Any]) -> None:
        ordinary = next(mode for mode in report["modes"] if mode["mode"] != MODE_TANDEM)
        ordinary["final_rx_state"]["gains_db"][0] = huge

    def ordinary_analysis(report: dict[str, Any]) -> None:
        ordinary = next(mode for mode in report["modes"] if mode["mode"] != MODE_TANDEM)
        ordinary["baseline_frames"][0]["analysis"]["selected_tone_hz"] = huge

    def tandem_suffix(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        indices = tandem["partition"]["groups"]["fully_post_release"]["frame_indices"]
        tandem["batch_frames"][indices[-1]]["analysis"]["windows"][0]["tone_dbfs"][
            0
        ] = huge

    def tandem_readback(report: dict[str, Any]) -> None:
        schedule = _tandem_mode(report)["acquisition"]["schedule_diagnostics"][
            "strong_attack"
        ]
        schedule["deferred_tx2_readback"]["observed_level_db"] = huge

    mutations = (
        ("elapsed", elapsed, False),
        ("cleanup gain", cleanup_gain, False),
        ("ordinary final gain", ordinary_final_gain, False),
        ("ordinary analysis", ordinary_analysis, False),
        ("tandem suffix", tandem_suffix, True),
        ("tandem readback", tandem_readback, True),
    )
    for label, mutate, refresh_projection in mutations:
        planted = json.loads(json.dumps(valid_report))
        mutate(planted)
        if refresh_projection:
            _refresh_tandem_projection_claim(planted, work_dir)
        report_path.write_text(json.dumps(planted) + "\n", encoding="utf-8")
        try:
            validate(spec, report_path, work_dir)
        except ReleaseCliError:
            pass
        else:
            pytest.fail(f"float-overflowing {label} JSON integer was accepted")


def test_baseline_soak_requires_temperature_evidence(tmp_path: Path) -> None:
    soak = _parse(
        tmp_path,
        "--phase",
        "steady",
        "--policy-set",
        "baseline",
    )
    records = {
        "run-a": {
            "status": "complete",
            "summary": {"temperature": {"available": False, "count": 0}},
        }
    }

    assert _soak_temperature_errors(soak, records) == [
        "baseline soak run run-a lacks temperature evidence"
    ]
    records["run-a"]["summary"]["temperature"] = {
        "available": True,
        "count": 3,
        "median_c": 35.0,
    }
    assert _soak_temperature_errors(soak, records) == []
