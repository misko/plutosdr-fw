"""Hardware-free parser, planning, resume, and aggregate-verdict oracles."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from .modulated_hardware import (
    MODE_TANDEM,
    MODULATED_MODES,
    ModulatedHardwareOptions,
    evaluate_modulated_hardware_report,
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
from .transient_hardware import TRANSIENT_MODES, TransientCaptureOptions

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
    assert plan_document(options)["deployment_performed"] is False


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
        tx2_gain_db=-30.0,
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
                "summary": quality_summary(case_id),
                **(
                    {
                        "settling": {"frames": 1, "trace": [tandem_frame(0)]},
                        "measurements": [tandem_frame(1)],
                    }
                    if mode == MODE_TANDEM
                    else {}
                ),
            }
            for case_id in case_ids
            for mode in MODULATED_MODES
        ],
    }
    report["evaluation"] = evaluate_modulated_hardware_report(
        report, modulated.degradation_thresholds
    )
    report_path.parent.mkdir(parents=True)
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")

    validated = production_validator(options)(spec, report_path, work_dir)

    assert validated.verdict == "pass"
    assert validated.cleanup_verified is True

    valid_report = json.loads(json.dumps(report))
    report["evaluation"]["degradation_valid"] = False
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="differs from recomputation"):
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


def test_production_validator_rejects_transient_configuration_substitution(
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
    gain = {"evidence_valid": True}
    responses = {
        "attack": {"evidence_valid": True},
        "release": {"evidence_valid": True},
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
            "transient_capture": _json_safe(asdict(TransientCaptureOptions())),
            "kernel_buffers": 1,
        },
        "rf": {"center_frequency_hz_requested": 915_000_000},
        "cleanup": cleanup,
        "required_modes": list(TRANSIENT_MODES),
        "modes": [
            {
                "mode": mode,
                "verdict": "pass",
                "gain_evidence": gain,
                "responses": responses,
            }
            for mode in TRANSIENT_MODES
        ],
        "comparison": [
            {"mode": mode, "gain_evidence": gain} for mode in TRANSIENT_MODES
        ],
    }
    report_path.parent.mkdir(parents=True)
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    assert production_validator(options)(spec, report_path, work_dir).verdict == "pass"

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
