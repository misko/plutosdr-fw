"""Hardware-free parser, planning, resume, and aggregate-verdict oracles."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from .metadata_abi import (
    FLAG_HARDWARE_SAMPLE_COUNTER_VALID,
    FLAG_SAMPLE_SEQUENCE_VALID,
    FLAG_TANDEM_METADATA_VALID,
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
    ValidatedPhase,
    _base_quality,
    _json_safe,
    _soak_temperature_errors,
    _steady_inputs,
    parse_cli_args,
    phase_specs,
    plan_document,
    production_validator,
    run_aggregate,
)
from .tandem_quality import AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES
from .transient_hardware import (
    TRANSIENT_MODES,
    TransientCaptureOptions,
    transient_evidence_policy,
)
from .transient_quality import (
    StimulusCommand,
    calculate_transient_response,
    reconcile_tandem_events,
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


def test_production_validator_recomputes_transient_evidence_and_configuration(
    tmp_path: Path,
) -> None:
    options = _parse(tmp_path, "--phase", "transient", "--band", "low=915000000")
    spec = phase_specs(options)[0]
    work_dir = options.output_dir / "work"
    report_path = work_dir / "radio-a" / "tandem-agc-transient-report.json"
    quality = _base_quality(options, output_dir=work_dir, band=spec.band)
    quality_configuration = _json_safe(asdict(quality))
    assert isinstance(quality_configuration, dict)
    quality_configuration["output_dir"] = str(work_dir)
    capture_options = TransientCaptureOptions()
    frame_samples = capture_options.frame_samples
    window_samples = capture_options.window_samples

    def frame_analysis(first_sample: int, *, tone_dbfs: float) -> dict[str, object]:
        windows = [
            {
                "window_index": index,
                "offset_start": index * window_samples,
                "offset_end_exclusive": (index + 1) * window_samples,
                "sample_start": first_sample + index * window_samples,
                "sample_end_exclusive": first_sample + (index + 1) * window_samples,
                "tone_dbfs": [tone_dbfs, tone_dbfs - 0.1],
                "mean_tone_dbfs": tone_dbfs - 0.05,
                "tone_snr_db": [40.0, 39.0],
                "clipping_fraction": [0.0, 0.0],
                "phase_difference_rad": 0.0,
                "phase_difference_deg": 0.0,
                "within_window_phase_std_deg": 0.1,
                "quality_valid": True,
                "quality_reasons": [],
            }
            for index in range(frame_samples // window_samples)
        ]
        return {
            "first_sample_sequence": first_sample,
            "samples_per_channel": frame_samples,
            "sample_rate_hz": quality.sample_rate_hz,
            "expected_tone_hz": quality.tone_hz,
            "selected_tone_hz": quality.tone_hz,
            "window_samples": window_samples,
            "stride_samples": window_samples,
            "window_count": len(windows),
            "uncovered_tail_samples": 0,
            "quality_valid": True,
            "windows": windows,
        }

    def qualified_response(
        frames_before: list[dict[str, object]],
        frames_after: list[dict[str, object]],
        *,
        previous_command: StimulusCommand,
        command: StimulusCommand,
        hardware: bool,
    ) -> dict[str, object]:
        calculated = dict(
            calculate_transient_response(
                [
                    window
                    for frame in (*frames_before, *frames_after)
                    for window in frame["analysis"]["windows"]  # type: ignore[index]
                ],
                previous_command=previous_command,
                command=command,
                sample_rate_hz=quality.sample_rate_hz,
                baseline_windows=capture_options.baseline_windows,
                steady_windows=capture_options.steady_windows,
                stable_windows=capture_options.stable_windows,
                settling_tolerance_db=capture_options.settling_tolerance_db,
                ringing_deadband_db=capture_options.ringing_deadband_db,
                max_host_jitter_ns=capture_options.max_host_jitter_ns,
                max_sample_uncertainty=capture_options.max_sample_uncertainty,
            )
        )
        if hardware:
            calculated.update(
                {
                    "timing_qualification": "fpga_sample_counter_bounded",
                    "hardware_latency_qualified": True,
                    "transient_observation_scope": (
                        "continuous_hardware_sample_record"
                    ),
                }
            )
            return calculated
        lower = calculated.pop("signal_settling_latency_lower_samples")
        upper = calculated.pop("signal_settling_latency_upper_samples")
        calculated.pop("signal_settling_latency_lower_seconds")
        calculated.pop("signal_settling_latency_upper_seconds")
        calculated.update(
            {
                "timing_qualification": "returned_iq_observation_only",
                "hardware_latency_qualified": False,
                "transient_observation_scope": (
                    "returned_iq_windows_with_unobserved_refill_intervals"
                ),
                "observed_returned_iq_settling_span_lower_axis_units": lower,
                "observed_returned_iq_settling_span_upper_axis_units": upper,
            }
        )
        return calculated

    response_tail = int(
        transient_evidence_policy(capture_options)["tandem_response_tail_frames"]
    )
    response_frame_count = capture_options.response_frames + response_tail
    precondition_frame_count = capture_options.precondition_stable_frames + 1
    attack_start = precondition_frame_count
    release_start = attack_start + response_frame_count
    attack_event = {
        "sample_sequence": attack_start * frame_samples + 128,
        "event_sequence": 100,
        "flags": 0x20,
        "direction": 2,
        "direction_name": "decrease",
        "reason": 0,
        "reason_name": "large_lmt_overload",
        "rx1_gain_index": 39,
        "rx2_gain_index": 39,
    }
    release_event = {
        "sample_sequence": release_start * frame_samples + 128,
        "event_sequence": 101,
        "flags": 0x13,
        "direction": 1,
        "direction_name": "increase",
        "reason": 3,
        "reason_name": "both_low_power",
        "rx1_gain_index": 40,
        "rx2_gain_index": 40,
    }

    def tandem_frame(
        frame_index: int,
        sequence: int,
        *,
        buffer_delta: int | None,
        cumulative_missing: int,
        transition_count: int,
        transition_delta: int | None,
        endpoint: int,
        events: list[dict[str, object]],
        gap_context: str,
    ) -> dict[str, object]:
        first = frame_index == 0
        missing = 0 if buffer_delta is None else buffer_delta - 1
        metadata = {
            "stream_id": 9,
            "buffer_sequence": sequence,
            "first_sample_sequence": sequence * frame_samples,
            "samples_per_channel": frame_samples,
            "flags": (
                FLAG_SAMPLE_SEQUENCE_VALID
                | FLAG_HARDWARE_SAMPLE_COUNTER_VALID
                | FLAG_TANDEM_METADATA_VALID
            ),
            "observation_count": 4,
            "ownership_epoch": 5,
            "tandem_state": 3,
            "tandem_state_name": "armed_auto",
            "tandem_fault_flags": 0,
            "tandem_transition_count": transition_count,
            "gain_table_id": 1,
            "threshold_provenance": 123,
            "gain_db_range": [0, 62],
            "initial_gain_db": 40,
            "gain_index_range": [3, 65],
            "bench_gain_indices": [endpoint, endpoint],
            "event_count": len(events),
            "observation_overflow_count": 0,
            "event_overflow_count": 0,
            "temperature_mdeg_c": 35_000,
            "gain_event_count": len(events),
            "gain_events": events,
        }
        return {
            "frame_index": frame_index,
            "iq_bytes": frame_samples * 8,
            "refill_monotonic_ns": 1_000 + frame_index,
            "timing_basis": "hardware_sample_counter",
            "first_sample_sequence": sequence * frame_samples,
            "sample_end_exclusive": (sequence + 1) * frame_samples,
            "sample_gap_before": missing * frame_samples,
            "physical_sample_continuity_proven": True,
            "gap_context": gap_context,
            "command_boundary_gap_allowed": False,
            "sha256": f"{frame_index:064x}",
            "analysis": frame_analysis(
                sequence * frame_samples,
                tone_dbfs=-20.0 if endpoint == 39 else -30.0,
            ),
            "metadata": metadata,
            "continuity": {
                "buffer_delta": buffer_delta,
                "sample_delta": (None if first else buffer_delta * frame_samples),
                "missing_frame_count": missing,
                "sample_gap_before": missing * frame_samples,
                "provider_gap_accepted": False,
                "gap_context": gap_context,
                "command_boundary_gap_allowed": False,
                "transition_count_delta": transition_delta,
                "visible_event_count": len(events),
                "hidden_transition_count": 0,
                "initial_unrepresented_transition_count": 0,
                "cumulative_missing_frame_count": cumulative_missing,
                "cumulative_hidden_transition_count": 0,
                "cumulative_event_sequence_hole_count": 0,
            },
        }

    precondition_frames = [
        tandem_frame(
            frame_index,
            frame_index,
            buffer_delta=None if frame_index == 0 else 1,
            cumulative_missing=0,
            transition_count=0,
            transition_delta=None if frame_index == 0 else 0,
            endpoint=40,
            events=[],
            gap_context="precondition_observation",
        )
        for frame_index in range(precondition_frame_count)
    ]
    for frame_index, frame in enumerate(precondition_frames):
        frame["precondition_stable_run"] = frame_index
    baseline_frame = precondition_frames[-1]
    attack_frames = [
        tandem_frame(
            frame_index,
            frame_index,
            buffer_delta=1,
            cumulative_missing=0,
            transition_count=1,
            transition_delta=1 if frame_index == attack_start else 0,
            endpoint=39,
            events=[attack_event] if frame_index == attack_start else [],
            gap_context=(
                "command_bracket"
                if frame_index == attack_start
                else "continuous_response"
            ),
        )
        for frame_index in range(attack_start, release_start)
    ]
    release_frames = [
        tandem_frame(
            frame_index,
            frame_index,
            buffer_delta=1,
            cumulative_missing=0,
            transition_count=2,
            transition_delta=1 if frame_index == release_start else 0,
            endpoint=40,
            events=[release_event] if frame_index == release_start else [],
            gap_context=(
                "command_bracket"
                if frame_index == release_start
                else "continuous_response"
            ),
        )
        for frame_index in range(release_start, release_start + response_frame_count)
    ]
    anchor_command = StimulusCommand(
        "weak_conditioning_anchor",
        quality.weakest_tx_gain_db,
        quality.weakest_tx_gain_db,
        1_000,
        1_100,
        (attack_start - 1) * frame_samples,
        attack_start * frame_samples,
    )
    attack_command = StimulusCommand(
        "strong_attack",
        quality.strongest_tx_gain_db,
        quality.strongest_tx_gain_db,
        1_200,
        1_300,
        attack_start * frame_samples,
        attack_start * frame_samples + 256,
    )
    release_command = StimulusCommand(
        "weak_release",
        quality.weakest_tx_gain_db,
        quality.weakest_tx_gain_db,
        1_400,
        1_500,
        release_start * frame_samples,
        release_start * frame_samples + 256,
    )

    def counter_timed_record(
        command: StimulusCommand, *, reference: int
    ) -> dict[str, object]:
        assert command.sample_sequence_before is not None
        assert command.sample_sequence_after is not None
        initial = reference + 128
        first_advance = reference + 192
        causal = command.sample_sequence_after
        return {
            **command.as_dict(),
            "effective_attenuation_db": (
                quality.physical_attenuation_db - command.applied_level_db
            ),
            "rx_state_before": None,
            "rx_state_after": None,
            "timing_role": "host_write_bracketed_by_coherent_fpga_counter",
            "sample_timing_basis": "hardware_sample_counter",
            "sample_anchor_policy": (
                "max(last observed frame end, coherent low32 pre-read) through "
                "the second distinct coherent low32 advance observed after an "
                "initial post-write read"
            ),
            "sample_counter_bracket": {
                "register_address": "0x800000b8",
                "counter_width_bits": 32,
                "counter_source": "coherent FPGA RX sample counter low word",
                "extension_reference_sample": reference,
                "raw_before": reference,
                "raw_post_write_initial": initial,
                "raw_post_write_first_advance": first_advance,
                "raw_post_write_causal": causal,
                "extended_before": reference,
                "extended_post_write_initial": initial,
                "extended_post_write_first_advance": first_advance,
                "extended_after": causal,
                "post_write_read_count": 3,
                "lower_clamped_to_last_observed_frame_end": False,
                "sample_sequence_lower": reference,
                "sample_sequence_upper": causal,
            },
        }

    tandem_gain = _json_safe(
        dict(
            reconcile_tandem_events(
                (anchor_command, attack_command, release_command),
                (attack_event, release_event),
                sample_rate_hz=quality.sample_rate_hz,
                max_host_jitter_ns=TransientCaptureOptions().max_host_jitter_ns,
                max_sample_uncertainty=(
                    TransientCaptureOptions().max_sample_uncertainty
                ),
                max_latency_samples=(
                    TransientCaptureOptions().max_event_latency_samples
                ),
            )
        )
    )
    assert isinstance(tandem_gain, dict)
    tandem_gain.update(
        {
            "timing_qualification": "fpga_sample_counter_bounded",
            "hardware_latency_qualified": True,
        }
    )
    tandem_responses = {
        "attack": qualified_response(
            [baseline_frame],
            attack_frames,
            previous_command=anchor_command,
            command=attack_command,
            hardware=True,
        ),
        "release": qualified_response(
            attack_frames,
            release_frames,
            previous_command=attack_command,
            command=release_command,
            hardware=True,
        ),
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

    def ordinary_mode_record(mode: str) -> dict[str, object]:
        iio_mode = "manual" if mode == "manual_fixed" else mode.removeprefix("native_")
        native = mode != "manual_fixed"
        weak_gain = 40.0
        strong_gain = 20.0 if native else weak_gain

        def rx_state(gain: float) -> dict[str, object]:
            return {"modes": [iio_mode, iio_mode], "gains_db": [gain, gain]}

        def frame(
            index: int,
            *,
            phase: str,
            gain: float,
            level: float,
            stable_run: int | None = None,
        ) -> dict[str, object]:
            first = index * frame_samples
            value: dict[str, object] = {
                "frame_index": index,
                "iq_bytes": frame_samples * 8,
                "refill_monotonic_ns": 2_000 + index,
                "timing_basis": "ordinary_returned_iq_ordinal_axis",
                "first_sample_sequence": first,
                "sample_end_exclusive": first + frame_samples,
                "sample_gap_before": None,
                "physical_sample_continuity_proven": False,
                "gap_context": phase,
                "command_boundary_gap_allowed": False,
                "rx_state_before": rx_state(gain),
                "rx_state_after": rx_state(gain),
                "sha256": f"{1_000 + index:064x}",
                "analysis": frame_analysis(first, tone_dbfs=level),
            }
            if stable_run is not None:
                value["precondition_stable_run"] = stable_run
            return value

        trace = [
            frame(
                index,
                phase="precondition_observation",
                gain=weak_gain,
                level=-30.0,
                stable_run=index + 1,
            )
            for index in range(capture_options.precondition_stable_frames)
        ]
        baseline = trace[-capture_options.baseline_frames :]
        attack_begin = len(trace)
        release_begin = attack_begin + capture_options.response_frames
        ordinary_attack = [
            frame(
                index,
                phase=(
                    "command_bracket"
                    if index == attack_begin
                    else "continuous_response"
                ),
                gain=strong_gain,
                level=-20.0,
            )
            for index in range(attack_begin, release_begin)
        ]
        ordinary_release = [
            frame(
                index,
                phase=(
                    "command_bracket"
                    if index == release_begin
                    else "continuous_response"
                ),
                gain=weak_gain,
                level=-30.0,
            )
            for index in range(
                release_begin, release_begin + capture_options.response_frames
            )
        ]
        initial = StimulusCommand(
            "weak_initial",
            quality.weakest_tx_gain_db,
            quality.weakest_tx_gain_db,
            1_000,
            1_100,
            None,
            None,
        )
        anchor = StimulusCommand(
            "weak_conditioning_anchor",
            quality.weakest_tx_gain_db,
            quality.weakest_tx_gain_db,
            1_000,
            1_100,
            int(baseline[0]["first_sample_sequence"]),
            int(baseline[-1]["sample_end_exclusive"]),
        )
        attack_command = StimulusCommand(
            "strong_attack",
            quality.strongest_tx_gain_db,
            quality.strongest_tx_gain_db,
            1_200,
            1_300,
            int(baseline[-1]["sample_end_exclusive"]),
            int(ordinary_attack[0]["sample_end_exclusive"]),
        )
        release_command = StimulusCommand(
            "weak_release",
            quality.weakest_tx_gain_db,
            quality.weakest_tx_gain_db,
            1_400,
            1_500,
            int(ordinary_attack[-1]["sample_end_exclusive"]),
            int(ordinary_release[0]["sample_end_exclusive"]),
        )

        def command_record(command: StimulusCommand) -> dict[str, object]:
            return {
                **command.as_dict(),
                "effective_attenuation_db": (
                    quality.physical_attenuation_db - command.applied_level_db
                ),
                "rx_state_before": rx_state(weak_gain),
                "rx_state_after": rx_state(weak_gain),
                "timing_role": "host_write_positioned_on_returned_iq_ordinal_axis",
                "sample_timing_basis": "ordinary_returned_iq_ordinal_axis",
                "sample_anchor_policy": (
                    "last returned pre-command IQ ordinal through end of first "
                    "returned post-command frame; unobserved hardware intervals "
                    "excluded"
                ),
            }

        mode_responses = {
            "attack": qualified_response(
                baseline,
                ordinary_attack,
                previous_command=anchor,
                command=attack_command,
                hardware=False,
            ),
            "release": qualified_response(
                ordinary_attack,
                ordinary_release,
                previous_command=attack_command,
                command=release_command,
                hardware=False,
            ),
        }
        if native:
            attack_bounds = [
                {
                    "rx_channel": channel,
                    "evidence": "pre_refill_readback",
                    "observed_gain_db": strong_gain,
                    "returned_iq_observation_span_lower_axis_units": 0,
                    "returned_iq_observation_span_upper_axis_units": frame_samples,
                    "hardware_latency_qualified": False,
                }
                for channel in (0, 1)
            ]
            release_bounds = [
                {**bound, "observed_gain_db": weak_gain} for bound in attack_bounds
            ]
            mode_gain: dict[str, object] = {
                "evidence_valid": True,
                "timing_qualification": "returned_iq_observation_only",
                "hardware_latency_qualified": False,
                "minimum_required_change_db": (
                    capture_options.minimum_native_gain_change_db
                ),
                "weak_gain_db": [weak_gain, weak_gain],
                "strong_gain_db": [strong_gain, strong_gain],
                "returned_weak_gain_db": [weak_gain, weak_gain],
                "attack_gain_change_db": [
                    strong_gain - weak_gain,
                    strong_gain - weak_gain,
                ],
                "release_gain_change_db": [
                    weak_gain - strong_gain,
                    weak_gain - strong_gain,
                ],
                "attack_returned_iq_observation_bounds": attack_bounds,
                "release_returned_iq_observation_bounds": release_bounds,
            }
        else:
            mode_gain = {
                "evidence_valid": True,
                "timing_qualification": "not_applicable_fixed_gain",
                "hardware_latency_qualified": False,
                "expected_gain_db": quality.manual_gain_db,
                "gain_span_db": [0.0, 0.0],
                "maximum_readback_error_db": [0.0, 0.0],
            }
        return {
            "mode": mode,
            "timing_basis": "ordinary_returned_iq_ordinal_axis",
            "metadata_abi": None,
            "verdict": "pass",
            "tandem_status_before": {
                "state": 0,
                "fault_flags": 0,
                "fifo_level": 0,
            },
            "tandem_status_after": {
                "state": 0,
                "fault_flags": 0,
                "fifo_level": 0,
            },
            "final_rx_state": {
                "modes": ["manual", "manual"],
                "gains_db": [quality.manual_gain_db, quality.manual_gain_db],
            },
            "gain_evidence": mode_gain,
            "responses": mode_responses,
            "preconditioning": {
                "frame_count": len(trace),
                "trace": trace,
                "retained_baseline_frame_indices": [
                    item["frame_index"] for item in baseline
                ],
            },
            "baseline_frames": baseline,
            "attack_frames": ordinary_attack,
            "release_frames": ordinary_release,
            "acquisition": {
                "threaded": False,
                "kernel_buffers": 1,
                "queue_capacity_frames": 0,
                "response_tail_frames": 0,
            },
            "conditioning_anchor": {
                **anchor.as_dict(),
                "timing_role": "observed_stable_conditioning_interval",
                "sample_timing_basis": "ordinary_returned_iq_ordinal_axis",
                "sample_anchor_policy": (
                    "retained stable baseline interval; not the initial write time"
                ),
            },
            "commands": [
                {
                    **initial.as_dict(),
                    "effective_attenuation_db": (
                        quality.physical_attenuation_db - initial.applied_level_db
                    ),
                    "rx_state_before": rx_state(weak_gain),
                    "rx_state_after": rx_state(weak_gain),
                    "timing_role": "pre_session_conditioning_write",
                    "sample_timing_basis": None,
                    "sample_anchor_policy": (
                        "unbounded in sample time; the write predates the open "
                        "capture session"
                    ),
                },
                command_record(attack_command),
                command_record(release_command),
            ],
        }

    ordinary_records = {
        mode: ordinary_mode_record(mode)
        for mode in TRANSIENT_MODES
        if mode != MODE_TANDEM
    }

    def comparison_entry(record: dict[str, object]) -> dict[str, object]:
        hardware = record["mode"] == MODE_TANDEM
        responses = record["responses"]
        assert isinstance(responses, dict)

        def summarize(response: dict[str, object]) -> dict[str, object]:
            result = {
                key: response[key]
                for key in (
                    "timing_qualification",
                    "transient_observation_scope",
                    "worst_overshoot_db",
                    "ringing_peak_to_peak_db",
                    "minimum_post_tone_snr_db",
                    "maximum_post_clipping_fraction",
                    "maximum_phase_excursion_deg",
                )
            }
            result["hardware_latency_qualified"] = hardware
            if hardware:
                for key in (
                    "signal_settling_latency_lower_samples",
                    "signal_settling_latency_upper_samples",
                    "signal_settling_latency_lower_seconds",
                    "signal_settling_latency_upper_seconds",
                ):
                    result[key] = response[key]
            else:
                for key in (
                    "signal_settling_latency_lower_samples",
                    "signal_settling_latency_upper_samples",
                    "signal_settling_latency_lower_seconds",
                    "signal_settling_latency_upper_seconds",
                ):
                    result[key] = None
                for key in (
                    "observed_returned_iq_settling_span_lower_axis_units",
                    "observed_returned_iq_settling_span_upper_axis_units",
                ):
                    result[key] = response[key]
            return result

        return {
            "mode": record["mode"],
            "timing_basis": record["timing_basis"],
            "attack": summarize(responses["attack"]),
            "release": summarize(responses["release"]),
            "gain_evidence": record["gain_evidence"],
        }

    report = {
        "schema": "plutosdr-fw.tandem-agc-transient.v1",
        "verdict": "pass",
        "identity": {
            "serial": options.serial,
            "uri": "usb:1.2.3",
            "libiio_source_commit": COMMIT,
            "context_attrs": {"fw_version": options.firmware_version},
        },
        "configuration": {
            "quality": quality_configuration,
            "transient_capture": _json_safe(asdict(capture_options)),
            "kernel_buffers": 1,
        },
        "evidence_policy": transient_evidence_policy(capture_options),
        "rf": {
            "center_frequency_hz_requested": 915_000_000,
            "center_frequency_hz_readback": {
                "rx_lo_hz": 915_000_000,
                "tx_lo_hz": 915_000_000,
            },
            "tone_hz": quality.tone_hz,
            "dds_scale": quality.dds_scale,
        },
        "cleanup": cleanup,
        "required_modes": list(TRANSIENT_MODES),
        "modes": [
            (
                {
                    "mode": mode,
                    "timing_basis": "hardware_sample_counter",
                    "metadata_abi": 2,
                    "verdict": "pass",
                    "tandem_status_before": {
                        "state": 0,
                        "fault_flags": 0,
                        "fifo_level": 0,
                    },
                    "tandem_status_after": {
                        "state": 0,
                        "fault_flags": 0,
                        "fifo_level": 0,
                    },
                    "final_rx_state": {
                        "modes": ["manual", "manual"],
                        "gains_db": [
                            quality.manual_gain_db,
                            quality.manual_gain_db,
                        ],
                    },
                    "gain_evidence": tandem_gain,
                    "responses": tandem_responses,
                    "preconditioning": {
                        "frame_count": len(precondition_frames),
                        "trace": precondition_frames,
                        "retained_baseline_frame_indices": [
                            baseline_frame["frame_index"]
                        ],
                    },
                    "baseline_frames": [baseline_frame],
                    "attack_frames": attack_frames,
                    "release_frames": release_frames,
                    "acquisition": {
                        "threaded": True,
                        "kernel_buffers": 1,
                        "queue_capacity_frames": 4,
                        "response_tail_frames": response_tail,
                        "buffer_cancelled_before_join": True,
                        "response_partitions": {
                            direction: {
                                "precommand_prefetch_frames": 0,
                                "command_bracket_frames": 1,
                                "fully_post_command_frames": (response_frame_count - 1),
                                "required_fully_post_command_frames": (
                                    capture_options.response_frames
                                ),
                                "maximum_non_post_command_frames": response_tail,
                            }
                            for direction in ("attack", "release")
                        },
                        "produced_frames": len(precondition_frames)
                        + 2 * response_frame_count,
                        "consumed_frames": len(precondition_frames)
                        + 2 * response_frame_count,
                        "discarded_tail_frames": 0,
                    },
                    "conditioning_anchor": {
                        **anchor_command.as_dict(),
                        "timing_role": "observed_stable_conditioning_interval",
                        "sample_timing_basis": "hardware_sample_counter",
                        "sample_anchor_policy": (
                            "retained stable baseline interval; not the initial "
                            "write time"
                        ),
                    },
                    "commands": [
                        {
                            **StimulusCommand(
                                "weak_initial",
                                quality.weakest_tx_gain_db,
                                quality.weakest_tx_gain_db,
                                1_000,
                                1_100,
                                None,
                                None,
                            ).as_dict(),
                            "effective_attenuation_db": (
                                quality.physical_attenuation_db
                                - quality.weakest_tx_gain_db
                            ),
                            "rx_state_before": None,
                            "rx_state_after": None,
                            "timing_role": "pre_session_conditioning_write",
                            "sample_timing_basis": None,
                            "sample_anchor_policy": (
                                "unbounded in sample time; the write predates "
                                "the open capture session"
                            ),
                        },
                        counter_timed_record(
                            attack_command,
                            reference=attack_start * frame_samples,
                        ),
                        counter_timed_record(
                            release_command,
                            reference=release_start * frame_samples,
                        ),
                    ],
                }
                if mode == MODE_TANDEM
                else ordinary_records[mode]
            )
            for mode in TRANSIENT_MODES
        ],
        "comparison": [],
    }
    report["comparison"] = [comparison_entry(record) for record in report["modes"]]
    report_path.parent.mkdir(parents=True)
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    assert production_validator(options)(spec, report_path, work_dir).verdict == "pass"

    valid_report = json.loads(json.dumps(report))

    def report_mode(document: dict[str, object], name: str) -> dict[str, object]:
        modes = document["modes"]
        assert isinstance(modes, list)
        return next(item for item in modes if item["mode"] == name)

    def report_comparison(document: dict[str, object], name: str) -> dict[str, object]:
        comparison = document["comparison"]
        assert isinstance(comparison, list)
        return next(item for item in comparison if item["mode"] == name)

    def command_from_record(record: dict[str, object]) -> StimulusCommand:
        return StimulusCommand(
            record["command_id"],
            record["requested_level_db"],
            record["applied_level_db"],
            record["host_before_ns"],
            record["host_after_ns"],
            record["sample_sequence_before"],
            record["sample_sequence_after"],
        )

    report = json.loads(json.dumps(valid_report))
    report["rf"].pop("center_frequency_hz_readback")
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="transient RF readback differs"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    report["rf"]["dds_scale"] = quality.dds_scale / 2
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="transient RF readback differs"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    report["rf"]["center_frequency_hz_readback"]["rx_lo_hz"] += 3
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="transient RF readback differs"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    report["rf"]["tone_hz"] += 1
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="transient RF readback differs"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    manual = report_mode(report, "manual_fixed")
    for field in (
        "preconditioning",
        "baseline_frames",
        "attack_frames",
        "release_frames",
        "acquisition",
        "conditioning_anchor",
        "commands",
    ):
        manual.pop(field)
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="frame evidence is missing or empty"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    manual = report_mode(report, "manual_fixed")
    manual["attack_frames"][0].pop("sample_end_exclusive")
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="ordinal ledger is inconsistent"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    manual = report_mode(report, "manual_fixed")
    next(
        command
        for command in manual["commands"]
        if command["command_id"] == "strong_attack"
    ).pop("sample_sequence_after")
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(
        ReleaseCliError, match="command ordinal bracket is inconsistent"
    ):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    manual = report_mode(report, "manual_fixed")
    manual["responses"]["attack"]["worst_overshoot_db"] += 1.0
    report_comparison(report, "manual_fixed").update(comparison_entry(manual))
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="responses differ from recomputation"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    report_comparison(report, "manual_fixed")["attack"][
        "signal_settling_latency_lower_samples"
    ] = 0
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(
        ReleaseCliError, match="comparison entry 0 differs from recomputation"
    ):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    manual = report_mode(report, "manual_fixed")
    moved_frame = manual["attack_frames"][1]
    moved_frame["rx_state_before"]["gains_db"] = [40.25, 40.25]
    moved_frame["rx_state_after"]["gains_db"] = [40.25, 40.25]
    manual["gain_evidence"].update(
        {
            "gain_span_db": [0.25, 0.25],
            "maximum_readback_error_db": [0.25, 0.25],
        }
    )
    report_comparison(report, "manual_fixed").update(comparison_entry(manual))
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="manual RX gain moved outside policy"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    manual = report_mode(report, "manual_fixed")
    manual["attack_frames"][1]["analysis"]["windows"][0]["tone_snr_db"][0] = 0.0
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="analysis window ledger is inconsistent"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    manual = report_mode(report, "manual_fixed")
    manual_attack_command = next(
        command
        for command in manual["commands"]
        if command["command_id"] == "strong_attack"
    )
    manual_release_command = next(
        command
        for command in manual["commands"]
        if command["command_id"] == "weak_release"
    )
    manual_attack_command["applied_level_db"] = -29.8
    manual_attack_command["effective_attenuation_db"] = 29.8
    manual["responses"] = {
        "attack": qualified_response(
            manual["baseline_frames"],
            manual["attack_frames"],
            previous_command=command_from_record(manual["conditioning_anchor"]),
            command=command_from_record(manual_attack_command),
            hardware=False,
        ),
        "release": qualified_response(
            manual["attack_frames"],
            manual["release_frames"],
            previous_command=command_from_record(manual_attack_command),
            command=command_from_record(manual_release_command),
            hardware=False,
        ),
    }
    report_comparison(report, "manual_fixed").update(comparison_entry(manual))
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(
        ReleaseCliError,
        match="manual_fixed command violates the 30 dB effective-attenuation boundary",
    ):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    tandem = report_mode(report, MODE_TANDEM)
    tandem["responses"]["attack"]["worst_overshoot_db"] += 1.0
    report_comparison(report, MODE_TANDEM).update(comparison_entry(tandem))
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(
        ReleaseCliError, match="tandem responses differ from recomputation"
    ):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    manual = report_mode(report, "manual_fixed")
    manual["tandem_status_after"]["fault_flags"] = 1
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="tandem_status_after is not safely IDLE"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    manual = report_mode(report, "manual_fixed")
    manual["final_rx_state"]["gains_db"][0] = quality.manual_gain_db + 0.2
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(
        ReleaseCliError, match="final RX state is not restored to manual"
    ):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    tandem = report_mode(report, MODE_TANDEM)
    tandem["attack_frames"][1]["metadata"]["tandem_state"] = 2
    tandem["attack_frames"][1]["metadata"]["tandem_state_name"] = "armed_manual"
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(
        ReleaseCliError, match="metadata counters or gains are malformed"
    ):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    tandem = report_mode(report, MODE_TANDEM)
    tandem["attack_frames"][1]["metadata"]["ownership_epoch"] = 0
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(
        ReleaseCliError, match="metadata counters or gains are malformed"
    ):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    tandem = report_mode(report, MODE_TANDEM)
    tandem["attack_frames"][1]["metadata"]["flags"] = 0
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(
        ReleaseCliError, match="metadata counters or gains are malformed"
    ):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    tandem = report_mode(report, MODE_TANDEM)
    tandem["attack_frames"][0]["metadata"]["gain_events"][0]["reason_name"] = "peer"
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="event 0 is malformed"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    tandem = report_mode(report, MODE_TANDEM)
    tandem_attack_command = next(
        command
        for command in tandem["commands"]
        if command["command_id"] == "strong_attack"
    )
    tandem_release_command = next(
        command
        for command in tandem["commands"]
        if command["command_id"] == "weak_release"
    )
    tandem_attack_command["applied_level_db"] = -29.8
    tandem_attack_command["effective_attenuation_db"] = 29.8
    tandem["responses"] = {
        "attack": qualified_response(
            tandem["baseline_frames"],
            tandem["attack_frames"],
            previous_command=command_from_record(tandem["conditioning_anchor"]),
            command=command_from_record(tandem_attack_command),
            hardware=True,
        ),
        "release": qualified_response(
            tandem["attack_frames"],
            tandem["release_frames"],
            previous_command=command_from_record(tandem_attack_command),
            command=command_from_record(tandem_release_command),
            hardware=True,
        ),
    }
    tandem_events = [
        event
        for phase in ("attack_frames", "release_frames")
        for frame in tandem[phase]
        for event in frame["metadata"]["gain_events"]
    ]
    tandem_gain = _json_safe(
        dict(
            reconcile_tandem_events(
                (
                    command_from_record(tandem["conditioning_anchor"]),
                    command_from_record(tandem_attack_command),
                    command_from_record(tandem_release_command),
                ),
                tandem_events,
                sample_rate_hz=quality.sample_rate_hz,
                max_host_jitter_ns=capture_options.max_host_jitter_ns,
                max_sample_uncertainty=capture_options.max_sample_uncertainty,
                max_latency_samples=capture_options.max_event_latency_samples,
            )
        )
    )
    tandem_gain.update(
        {
            "timing_qualification": "fpga_sample_counter_bounded",
            "hardware_latency_qualified": True,
        }
    )
    tandem["gain_evidence"] = tandem_gain
    report_comparison(report, MODE_TANDEM).update(comparison_entry(tandem))
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(
        ReleaseCliError,
        match="tandem command violates the 30 dB effective-attenuation boundary",
    ):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    report["evidence_policy"]["tandem_provider_gaps"] = "accept planted gaps"
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="evidence policy differs"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    tandem = next(mode for mode in report["modes"] if mode["mode"] == MODE_TANDEM)
    tandem["acquisition"]["consumed_frames"] -= 1
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="acquisition ledger is inconsistent"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    tandem = next(mode for mode in report["modes"] if mode["mode"] == MODE_TANDEM)
    tandem["acquisition"]["response_partitions"]["attack"][
        "fully_post_command_frames"
    ] -= 1
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="partition ledger differs"):
        production_validator(options)(spec, report_path, work_dir)

    # A self-consistent ledger cannot waive the queue-plus-producer tail bound.
    # Plant five truly prefetched frames followed by one command-bracket frame,
    # move the transition/event into that bracket, and refresh every dependent
    # response/gain/summary field.  Only the independently recomputed six-frame
    # prefix policy should make the report ineligible.
    report = json.loads(json.dumps(valid_report))
    tandem = report_mode(report, MODE_TANDEM)
    forged_attack_frames = tandem["attack_frames"]
    forged_attack_command = next(
        command
        for command in tandem["commands"]
        if command["command_id"] == "strong_attack"
    )
    forged_release_command = next(
        command
        for command in tandem["commands"]
        if command["command_id"] == "weak_release"
    )
    bracket_frame_offset = 5
    forged_lower = forged_attack_frames[bracket_frame_offset]["first_sample_sequence"]
    forged_upper = forged_lower + 256
    forged_attack_command.update(
        {
            "sample_sequence_before": forged_lower,
            "sample_sequence_after": forged_upper,
            "sample_uncertainty": forged_upper - forged_lower,
        }
    )
    forged_bracket = forged_attack_command["sample_counter_bracket"]
    forged_bracket.update(
        {
            "raw_before": forged_lower,
            "raw_post_write_initial": forged_lower + 128,
            "raw_post_write_first_advance": forged_lower + 192,
            "raw_post_write_causal": forged_upper,
            "extended_before": forged_lower,
            "extended_post_write_initial": forged_lower + 128,
            "extended_post_write_first_advance": forged_lower + 192,
            "extended_after": forged_upper,
            "lower_clamped_to_last_observed_frame_end": False,
            "sample_sequence_lower": forged_lower,
            "sample_sequence_upper": forged_upper,
        }
    )
    forged_attack_event = json.loads(
        json.dumps(forged_attack_frames[0]["metadata"]["gain_events"][0])
    )
    forged_attack_event["sample_sequence"] = forged_lower + 128
    for frame_offset, frame in enumerate(forged_attack_frames):
        before_command = frame_offset < bracket_frame_offset
        in_bracket = frame_offset == bracket_frame_offset
        gap_context = (
            "precommand_prefetch"
            if before_command
            else "command_bracket"
            if in_bracket
            else "continuous_response"
        )
        endpoint = 40 if before_command else 39
        events = [forged_attack_event] if in_bracket else []
        transition_count = 0 if before_command else 1
        frame["gap_context"] = gap_context
        frame["continuity"].update(
            {
                "gap_context": gap_context,
                "transition_count_delta": 1 if in_bracket else 0,
                "visible_event_count": len(events),
            }
        )
        frame["metadata"].update(
            {
                "tandem_transition_count": transition_count,
                "bench_gain_indices": [endpoint, endpoint],
                "event_count": len(events),
                "gain_event_count": len(events),
                "gain_events": events,
            }
        )
        frame["analysis"] = frame_analysis(
            frame["first_sample_sequence"],
            tone_dbfs=-30.0 if before_command else -20.0,
        )
    tandem["acquisition"]["response_partitions"]["attack"] = {
        "precommand_prefetch_frames": 5,
        "command_bracket_frames": 1,
        "fully_post_command_frames": 7,
        "required_fully_post_command_frames": capture_options.response_frames,
        "maximum_non_post_command_frames": response_tail,
    }
    forged_anchor = command_from_record(tandem["conditioning_anchor"])
    forged_attack_stimulus = command_from_record(forged_attack_command)
    forged_release_stimulus = command_from_record(forged_release_command)
    tandem["responses"] = {
        "attack": qualified_response(
            tandem["baseline_frames"],
            forged_attack_frames,
            previous_command=forged_anchor,
            command=forged_attack_stimulus,
            hardware=True,
        ),
        "release": qualified_response(
            forged_attack_frames,
            tandem["release_frames"],
            previous_command=forged_attack_stimulus,
            command=forged_release_stimulus,
            hardware=True,
        ),
    }
    forged_response_events = [
        event
        for phase in ("attack_frames", "release_frames")
        for frame in tandem[phase]
        for event in frame["metadata"]["gain_events"]
    ]
    forged_gain = _json_safe(
        dict(
            reconcile_tandem_events(
                (forged_anchor, forged_attack_stimulus, forged_release_stimulus),
                forged_response_events,
                sample_rate_hz=quality.sample_rate_hz,
                max_host_jitter_ns=capture_options.max_host_jitter_ns,
                max_sample_uncertainty=capture_options.max_sample_uncertainty,
                max_latency_samples=capture_options.max_event_latency_samples,
            )
        )
    )
    forged_gain.update(
        {
            "timing_qualification": "fpga_sample_counter_bounded",
            "hardware_latency_qualified": True,
        }
    )
    tandem["gain_evidence"] = forged_gain
    report_comparison(report, MODE_TANDEM).update(comparison_entry(tandem))
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(
        ReleaseCliError,
        match="attack pre/bracketed prefix exceeds policy.*attack lacks the required",
    ) as partition_error:
        production_validator(options)(spec, report_path, work_dir)
    assert "partition ledger differs" not in str(partition_error.value)
    assert "responses differ" not in str(partition_error.value)
    assert "gain evidence differs" not in str(partition_error.value)
    assert "command bracket is inconsistent" not in str(partition_error.value)

    report = json.loads(json.dumps(valid_report))
    tandem = next(mode for mode in report["modes"] if mode["mode"] == MODE_TANDEM)
    attack_counter = next(
        command
        for command in tandem["commands"]
        if command["command_id"] == "strong_attack"
    )["sample_counter_bracket"]
    attack_counter["raw_post_write_causal"] += 1
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="command bracket is inconsistent"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    tandem = next(mode for mode in report["modes"] if mode["mode"] == MODE_TANDEM)
    tandem["attack_frames"][0]["metadata"]["first_sample_sequence"] += 1
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="buffer/sample deltas disagree"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    tandem = next(mode for mode in report["modes"] if mode["mode"] == MODE_TANDEM)
    tandem["attack_frames"][0]["gap_context"] = "continuous_response"
    tandem["attack_frames"][0]["continuity"]["gap_context"] = "continuous_response"
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="gap context differs from its phase"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    tandem = next(mode for mode in report["modes"] if mode["mode"] == MODE_TANDEM)
    tandem["attack_frames"][0]["metadata"]["tandem_transition_count"] = 2
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="lost adjacent-frame event evidence"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    tandem = next(mode for mode in report["modes"] if mode["mode"] == MODE_TANDEM)
    attack_command_record = next(
        command
        for command in tandem["commands"]
        if command["command_id"] == "strong_attack"
    )
    attack_command_record["sample_sequence_after"] -= 1
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="command bracket is inconsistent"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    tandem = next(mode for mode in report["modes"] if mode["mode"] == MODE_TANDEM)
    tandem["baseline_frames"][-1]["sample_end_exclusive"] += 1
    attack_command_record = next(
        command
        for command in tandem["commands"]
        if command["command_id"] == "strong_attack"
    )
    attack_command_record["sample_sequence_before"] += 1
    attack_command_record["sample_uncertainty"] -= 1

    response_events = [
        event
        for phase in ("attack_frames", "release_frames")
        for frame in tandem[phase]
        for event in frame["metadata"]["gain_events"]
    ]
    release_command_record = next(
        command
        for command in tandem["commands"]
        if command["command_id"] == "weak_release"
    )
    forged_gain = _json_safe(
        dict(
            reconcile_tandem_events(
                (
                    command_from_record(tandem["conditioning_anchor"]),
                    command_from_record(attack_command_record),
                    command_from_record(release_command_record),
                ),
                response_events,
                sample_rate_hz=quality.sample_rate_hz,
                max_host_jitter_ns=(TransientCaptureOptions().max_host_jitter_ns),
                max_sample_uncertainty=(
                    TransientCaptureOptions().max_sample_uncertainty
                ),
                max_latency_samples=(
                    TransientCaptureOptions().max_event_latency_samples
                ),
            )
        )
    )
    tandem["gain_evidence"] = forged_gain
    next(item for item in report["comparison"] if item["mode"] == MODE_TANDEM)[
        "gain_evidence"
    ] = forged_gain
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="exact retained preconditioning tail"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    tandem = next(mode for mode in report["modes"] if mode["mode"] == MODE_TANDEM)
    anchor_command_record = tandem["conditioning_anchor"]
    anchor_command_record["sample_sequence_before"] += 1
    anchor_command_record["sample_uncertainty"] -= 1
    attack_command_record = next(
        command
        for command in tandem["commands"]
        if command["command_id"] == "strong_attack"
    )
    release_command_record = next(
        command
        for command in tandem["commands"]
        if command["command_id"] == "weak_release"
    )
    forged_gain = _json_safe(
        dict(
            reconcile_tandem_events(
                (
                    command_from_record(anchor_command_record),
                    command_from_record(attack_command_record),
                    command_from_record(release_command_record),
                ),
                response_events,
                sample_rate_hz=quality.sample_rate_hz,
                max_host_jitter_ns=(TransientCaptureOptions().max_host_jitter_ns),
                max_sample_uncertainty=(
                    TransientCaptureOptions().max_sample_uncertainty
                ),
                max_latency_samples=(
                    TransientCaptureOptions().max_event_latency_samples
                ),
            )
        )
    )
    tandem["gain_evidence"] = forged_gain
    next(item for item in report["comparison"] if item["mode"] == MODE_TANDEM)[
        "gain_evidence"
    ] = forged_gain
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="exact retained baseline interval"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    report["configuration"]["quality"]["sample_rate_hz"] = 1_000_000
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="configuration differs"):
        production_validator(options)(spec, report_path, work_dir)


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
