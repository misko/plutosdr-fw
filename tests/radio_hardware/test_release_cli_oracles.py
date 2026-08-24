"""Hardware-free parser, planning, resume, and aggregate-verdict oracles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .release_campaign import build_release_plan
from .release_cli import (
    AGGREGATE_CHECKPOINT,
    PhaseSpec,
    ReleaseCliError,
    ValidatedPhase,
    _steady_inputs,
    parse_cli_args,
    phase_specs,
    plan_document,
    run_aggregate,
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
    assert plan_document(options)["deployment_performed"] is False


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
