"""Offline planted oracles for deterministic tandem release campaigns."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

import pytest

from .release_campaign import (
    BandCase,
    CampaignConfigurationError,
    PolicyCase,
    ReleaseCampaignConfig,
    build_release_plan,
    matrix_runner_for_radio_factory,
    run_release_campaign,
)
from .tandem_quality import (
    NATIVE_GAIN_CONTROL_MODES,
    TandemQualityOptions,
    expected_tandem_gain_table,
    quality_modes,
)

BASELINE = PolicyCase("baseline", "baseline")
LOW_POLICY = PolicyCase(
    "low-power-24",
    "low_power_threshold",
    (("tandem_low_power_threshold", 24),),
)


def _base(tmp_path: Path) -> TandemQualityOptions:
    return TandemQualityOptions(
        tx_gain_trajectory_db=(-61.0, -45.0, -30.0, -45.0, -61.0),
        physical_attenuation_db=0.0,
        output_dir=tmp_path / "unused",
    )


def _config(
    tmp_path: Path,
    *,
    cycles: int = 1,
    policies: tuple[PolicyCase, ...] = (BASELINE, LOW_POLICY),
    interval: float = 0.0,
    deadline: float = 100.0,
) -> ReleaseCampaignConfig:
    return ReleaseCampaignConfig(
        output_dir=tmp_path / "campaign",
        radio_serials=("radio-a",),
        repeat_cycles=cycles,
        cycle_interval_seconds=interval,
        soak_deadline_seconds=deadline,
        bands=(BandCase("mid", 2_450_000_000),),
        policy_cases=policies,
    )


def _safe_cleanup():
    return {
        "verified": True,
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
        "failures": [],
    }


def _matrix_report(spec, *, snr: float = 20.0, temperature_c: float = 35.0):
    summary = {
        "quality_valid": True,
        "tone_snr_db_median": [snr, snr + 0.2],
        "coherence_median": 0.9995,
        "within_capture_phase_std_deg_max": 0.2,
        "tone_frequency_error_hz_median": 10.0,
        "clipping_fraction_max": [0.0, 0.0],
    }
    mode_records = []
    for mode in quality_modes(spec.options):
        cells = []
        for level_index, tx_gain_db in enumerate(spec.options.tx_gain_trajectory_db):
            measurements = [
                {
                    "quality": {"quality_valid": True},
                    "metadata": {"temperature_mdeg_c": round(temperature_c * 1000)},
                }
                for _index in range(spec.options.measurement_frames)
            ]
            cells.append(
                {
                    "level_index": level_index,
                    "tx2_gain_requested_db": tx_gain_db,
                    "tx2_gain_readback_db": tx_gain_db,
                    "summary": dict(summary),
                    "measurements": measurements,
                }
            )
        mode_records.append({"mode": mode, "cells": cells})
    options = spec.options
    configuration = asdict(options)
    configuration["output_dir"] = str(options.output_dir)
    configuration["minimum_effective_attenuation_db"] = (
        options.minimum_effective_attenuation_db
    )
    return {
        "schema": "plutosdr-fw.tandem-agc-quality.v1",
        "identity": {"serial": spec.serial},
        "configuration": configuration,
        "rf": {
            "center_frequency_hz_requested": options.center_frequency_hz,
            "center_frequency_hz_readback": {
                "rx_lo_hz": options.center_frequency_hz,
                "tx_lo_hz": options.center_frequency_hz,
            },
            "expected_tandem_gain_table_id": int(
                expected_tandem_gain_table(options.center_frequency_hz)
            ),
            "expected_tandem_gain_table_name": expected_tandem_gain_table(
                options.center_frequency_hz
            ).name.lower(),
        },
        "modes": mode_records,
        "manual_fixture_preflight": {
            "tx2_gain_db": options.strongest_tx_gain_db,
            "valid": True,
            "cell_count": options.tx_gain_trajectory_db.count(
                options.strongest_tx_gain_db
            ),
            "stimulus_evidence": {"valid": True, "reasons": []},
        },
        "evaluation": {
            "verdict": "pass",
            "failures": [],
            "native_modes": list(quality_modes(options)[1:-1]),
            "manual_tone_evidence": {"valid": True, "reasons": []},
        },
        "verdict": "pass",
        "final_tandem_status": {
            "state": 0,
            "fault_flags": 0,
            "fifo_level": 0,
            "overflow_count": 0,
        },
        "final_rx_state": {
            "modes": ["manual", "manual"],
            "gains_db": [options.manual_gain_db, options.manual_gain_db],
        },
        "cleanup": _safe_cleanup(),
    }


def _write_report(spec, report):
    path = spec.expected_report_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
    return report, path


def test_default_plan_is_full_all_native_all_band_all_radio_and_deterministic(
    tmp_path: Path,
) -> None:
    config = ReleaseCampaignConfig(
        output_dir=tmp_path / "campaign",
        radio_serials=("radio-a", "radio-b"),
        repeat_cycles=2,
    )

    first = build_release_plan(config, _base(tmp_path))
    second = build_release_plan(config, _base(tmp_path))

    assert first.fingerprint == second.fingerprint
    assert [run.run_id for run in first.runs] == [run.run_id for run in second.runs]
    assert len(first.runs) == 2 * 2 * 3 * 11
    assert {run.band.center_frequency_hz for run in first.runs} == {
        915_000_000,
        2_450_000_000,
        5_800_000_000,
    }
    assert {run.options.profile for run in first.runs} == {"full"}
    assert {run.options.native_gain_control_modes for run in first.runs} == {
        NATIVE_GAIN_CONTROL_MODES
    }
    assert len({run.options.output_dir for run in first.runs}) == len(first.runs)


def test_default_policy_cases_change_exactly_one_declared_factor(
    tmp_path: Path,
) -> None:
    plan = build_release_plan(
        ReleaseCampaignConfig(
            output_dir=tmp_path / "campaign", radio_serials=("radio-a",)
        ),
        _base(tmp_path),
    )

    expected = {
        "baseline": set(),
        "low_power_threshold": {"tandem_low_power_threshold"},
        "large_lmt_threshold": {"tandem_large_lmt_overload_threshold"},
        "adc_thresholds": {
            "tandem_large_adc_overload_threshold",
            "tandem_small_adc_overload_threshold",
        },
        "low_power_dwell": {"tandem_low_power_dwell_periods"},
        "cooldown": {"tandem_cooldown_periods"},
    }
    assert {
        case.factor: {key for key, _value in case.overrides}
        for case in plan.policy_cases
    } == expected
    assert len(plan.policy_cases) == 11
    assert {
        factor: sum(case.factor == factor for case in plan.policy_cases)
        for factor in expected
    } == {
        "baseline": 1,
        "low_power_threshold": 2,
        "large_lmt_threshold": 2,
        "adc_thresholds": 2,
        "low_power_dwell": 2,
        "cooldown": 2,
    }


@pytest.mark.parametrize(
    "bad_policy",
    [
        PolicyCase("not-baseline", "baseline"),
        PolicyCase(
            "mixed",
            "cooldown",
            (
                ("tandem_cooldown_periods", 24),
                ("tandem_low_power_dwell_periods", 4),
            ),
        ),
    ],
)
def test_noncontrolled_policy_plan_is_rejected(
    tmp_path: Path, bad_policy: PolicyCase
) -> None:
    with pytest.raises(CampaignConfigurationError):
        build_release_plan(_config(tmp_path, policies=(bad_policy,)), _base(tmp_path))


def test_campaign_checkpoint_resume_skips_verified_completed_run(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    calls: list[str] = []

    def callback(spec, _options):
        calls.append(spec.run_id)
        return _write_report(spec, _matrix_report(spec))

    partial, _path = run_release_campaign(
        config, _base(tmp_path), callback, max_new_runs=1
    )
    assert partial["verdict"] == "incomplete"
    assert partial["counts"] == {
        "pending": 1,
        "running": 0,
        "complete": 1,
        "failed": 0,
    }

    complete, path = run_release_campaign(config, _base(tmp_path), callback)

    assert complete["verdict"] == "pass"
    assert len(calls) == 2
    assert path.is_file()
    assert not list(config.output_dir.rglob("*.tmp"))
    json.dumps(complete, allow_nan=False)


def test_campaign_resume_is_independent_of_canonical_json_key_order(
    tmp_path: Path,
) -> None:
    config = ReleaseCampaignConfig(
        output_dir=tmp_path / "campaign",
        radio_serials=("radio-a",),
        bands=(
            BandCase("z-low", 915_000_000),
            BandCase("a-mid", 2_450_000_000),
        ),
        policy_cases=(BASELINE,),
    )
    plan = build_release_plan(config, _base(tmp_path))
    planned_ids = [run.run_id for run in plan.runs]
    calls: list[str] = []

    def callback(spec, _options):
        calls.append(spec.run_id)
        return _write_report(spec, _matrix_report(spec))

    partial, _path = run_release_campaign(
        config, _base(tmp_path), callback, max_new_runs=1
    )
    assert partial["verdict"] == "incomplete"
    durable = json.loads(
        (config.output_dir / "campaign-checkpoint.json").read_text(encoding="utf-8")
    )
    assert list(durable["runs"]) == sorted(planned_ids)
    assert list(durable["runs"]) != planned_ids

    complete, _path = run_release_campaign(config, _base(tmp_path), callback)

    assert complete["verdict"] == "pass"
    assert calls == planned_ids
    assert list(complete["runs"]) == planned_ids


def test_resume_rejects_tampered_completed_artifact(tmp_path: Path) -> None:
    config = _config(tmp_path)

    def callback(spec, _options):
        return _write_report(spec, _matrix_report(spec))

    run_release_campaign(config, _base(tmp_path), callback, max_new_runs=1)
    plan = build_release_plan(config, _base(tmp_path))
    plan.runs[0].expected_report_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(CampaignConfigurationError, match="artifact changed"):
        run_release_campaign(config, _base(tmp_path), callback)


def test_resume_rejects_tampered_checkpoint_summary(tmp_path: Path) -> None:
    config = _config(tmp_path)

    def callback(spec, _options):
        return _write_report(spec, _matrix_report(spec))

    run_release_campaign(config, _base(tmp_path), callback, max_new_runs=1)
    checkpoint_path = config.output_dir / "campaign-checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    completed = next(
        record
        for record in checkpoint["runs"].values()
        if record["status"] == "complete"
    )
    completed["summary"]["quality"]["minimum_snr_db"] = 9_999.0
    checkpoint_path.write_text(
        json.dumps(checkpoint, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(CampaignConfigurationError, match="derived summary changed"):
        run_release_campaign(config, _base(tmp_path), callback)


def test_skeletal_matrix_report_stops_fail_closed(tmp_path: Path) -> None:
    config = _config(tmp_path)

    def callback(spec, _options):
        skeletal = {
            "schema": "plutosdr-fw.tandem-agc-quality.v1",
            "identity": {"serial": spec.serial},
            "verdict": "pass",
            "cleanup": _safe_cleanup(),
        }
        return _write_report(spec, skeletal)

    aggregate, _path = run_release_campaign(config, _base(tmp_path), callback)

    assert aggregate["verdict"] == "invalid"
    failed = next(
        record for record in aggregate["runs"].values() if record["status"] == "failed"
    )
    assert "configuration" in failed["error"]


def test_manual_weak_quality_failure_is_allowed_when_evaluation_passes(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, policies=(BASELINE,))

    def callback(spec, _options):
        report = _matrix_report(spec)
        weak_cell = report["modes"][0]["cells"][0]
        weak_cell["measurements"][0]["quality"]["quality_valid"] = False
        weak_cell["summary"]["quality_valid"] = False
        return _write_report(spec, report)

    aggregate, _path = run_release_campaign(config, _base(tmp_path), callback)

    assert aggregate["verdict"] == "pass"


def test_cleanup_failure_is_recorded_and_stops_fail_closed(tmp_path: Path) -> None:
    config = _config(tmp_path)

    def callback(spec, _options):
        report = _matrix_report(spec)
        report["final_tandem_status"]["fault_flags"] = 1
        return _write_report(spec, report)

    aggregate, _path = run_release_campaign(config, _base(tmp_path), callback)

    assert aggregate["verdict"] == "invalid"
    assert aggregate["counts"]["failed"] == 1
    assert aggregate["counts"]["pending"] == 1
    failed = next(
        record for record in aggregate["runs"].values() if record["status"] == "failed"
    )
    assert "fault_flags" in failed["error"]


def test_missing_cleanup_attestation_stops_fail_closed(tmp_path: Path) -> None:
    config = _config(tmp_path)

    def callback(spec, _options):
        report = _matrix_report(spec)
        report.pop("cleanup")
        return _write_report(spec, report)

    aggregate, _path = run_release_campaign(config, _base(tmp_path), callback)

    assert aggregate["verdict"] == "invalid"
    failed = next(
        record for record in aggregate["runs"].values() if record["status"] == "failed"
    )
    assert "cleanup attestation is missing" in failed["error"]


def test_malformed_cleanup_attestation_stops_fail_closed(tmp_path: Path) -> None:
    config = _config(tmp_path)

    def callback(spec, _options):
        report = _matrix_report(spec)
        report["cleanup"] = []
        return _write_report(spec, report)

    aggregate, _path = run_release_campaign(config, _base(tmp_path), callback)

    assert aggregate["verdict"] == "invalid"
    failed = next(
        record for record in aggregate["runs"].values() if record["status"] == "failed"
    )
    assert "cleanup attestation is missing" in failed["error"]


def test_false_cleanup_attestation_stops_fail_closed(tmp_path: Path) -> None:
    config = _config(tmp_path)

    def callback(spec, _options):
        report = _matrix_report(spec)
        report["cleanup"]["verified"] = False
        return _write_report(spec, report)

    aggregate, _path = run_release_campaign(config, _base(tmp_path), callback)

    assert aggregate["verdict"] == "invalid"
    failed = next(
        record for record in aggregate["runs"].values() if record["status"] == "failed"
    )
    assert "cleanup verified is not true" in failed["error"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda cleanup: cleanup.update(tx1_gain_db=-79.9), "tx1_gain"),
        (lambda cleanup: cleanup.update(selectors=[3, 3, 3, 2]), "selectors"),
        (
            lambda cleanup: cleanup["dds"]["altvoltage0"].update(scale=0.1),
            "DDS altvoltage0 scale",
        ),
        (lambda cleanup: cleanup["failures"].append("planted"), "failures"),
    ],
)
def test_unsafe_cleanup_evidence_stops_fail_closed(
    tmp_path: Path, mutation, message: str
) -> None:
    config = _config(tmp_path)

    def callback(spec, _options):
        report = _matrix_report(spec)
        mutation(report["cleanup"])
        return _write_report(spec, report)

    aggregate, _path = run_release_campaign(config, _base(tmp_path), callback)

    assert aggregate["verdict"] == "invalid"
    failed = next(
        record for record in aggregate["runs"].values() if record["status"] == "failed"
    )
    assert message.lower() in failed["error"].lower()


def test_policy_regression_is_classified_and_fails_aggregate(tmp_path: Path) -> None:
    config = _config(tmp_path)

    def callback(spec, _options):
        snr = 20.0 if spec.policy.factor == "baseline" else 18.0
        return _write_report(spec, _matrix_report(spec, snr=snr))

    aggregate, _path = run_release_campaign(config, _base(tmp_path), callback)

    assert aggregate["verdict"] == "fail"
    candidate = next(
        item
        for item in aggregate["policy_classifications"]
        if item["policy"]["factor"] != "baseline"
    )
    assert candidate["classification"] == "degraded"
    assert candidate["deltas"]["minimum_snr_db"] == pytest.approx(-2.0)


def test_repeat_cycle_temperature_and_quality_drift_are_summarized(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, cycles=2, policies=(BASELINE,))

    def callback(spec, _options):
        return _write_report(
            spec,
            _matrix_report(
                spec,
                snr=20.0 - 3.0 * spec.cycle,
                temperature_c=35.0 + 2.0 * spec.cycle,
            ),
        )

    aggregate, _path = run_release_campaign(config, _base(tmp_path), callback)

    assert aggregate["verdict"] == "fail"
    assert aggregate["temperature"]["span_c"] == pytest.approx(2.0)
    drift = aggregate["repeatability"][0]
    assert drift["cycles"] == [0, 1]
    assert drift["snr_drop_db"] == pytest.approx(3.0)
    assert drift["verdict"] == "fail"


class _Clock:
    def __init__(self) -> None:
        self.value = 1_000.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


def test_soak_deadline_leaves_later_cycle_incomplete_without_sleeping_past_it(
    tmp_path: Path,
) -> None:
    config = _config(
        tmp_path,
        cycles=2,
        policies=(BASELINE,),
        interval=10.0,
        deadline=5.0,
    )
    clock = _Clock()
    calls = 0

    def callback(spec, _options):
        nonlocal calls
        calls += 1
        return _write_report(spec, _matrix_report(spec))

    aggregate, _path = run_release_campaign(
        config,
        _base(tmp_path),
        callback,
        now=clock.now,
        sleep=clock.sleep,
    )

    assert calls == 1
    assert clock.sleeps == []
    assert aggregate["verdict"] == "incomplete"
    assert aggregate["reason"] == "soak deadline precedes next cycle"


def test_radio_factory_adapter_opens_fresh_radio_for_matrix(tmp_path: Path) -> None:
    config = _config(tmp_path, policies=(BASELINE,))
    plan = build_release_plan(config, _base(tmp_path))
    opened: list[tuple[str, int]] = []

    @contextmanager
    def factory(serial, options):
        opened.append((serial, options.center_frequency_hz))
        yield object()

    def matrix(_radio, options):
        spec = plan.runs[0]
        assert options == spec.options
        return _write_report(spec, _matrix_report(spec))

    runner = matrix_runner_for_radio_factory(factory, matrix)
    returned, path = runner(plan.runs[0], plan.runs[0].options)

    assert returned["verdict"] == "pass"
    assert path == plan.runs[0].expected_report_path
    assert opened == [("radio-a", 2_450_000_000)]


def test_radio_factory_adapter_reloads_close_time_cleanup(tmp_path: Path) -> None:
    config = _config(tmp_path, policies=(BASELINE,))
    plan = build_release_plan(config, _base(tmp_path))
    spec = plan.runs[0]

    @contextmanager
    def factory(_serial, _options):
        yield object()
        durable = json.loads(spec.expected_report_path.read_text(encoding="utf-8"))
        durable["cleanup"] = _safe_cleanup()
        spec.expected_report_path.write_text(
            json.dumps(durable, sort_keys=True) + "\n", encoding="utf-8"
        )

    def matrix(_radio, _options):
        return _write_report(spec, _matrix_report(spec))

    runner = matrix_runner_for_radio_factory(factory, matrix)
    aggregate, _path = run_release_campaign(config, _base(tmp_path), runner)

    assert aggregate["verdict"] == "pass"
    assert aggregate["runs"][spec.run_id]["status"] == "complete"


def test_radio_factory_adapter_does_not_hide_close_time_tampering(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, policies=(BASELINE,))
    plan = build_release_plan(config, _base(tmp_path))
    spec = plan.runs[0]

    @contextmanager
    def factory(_serial, _options):
        yield object()
        durable = json.loads(spec.expected_report_path.read_text(encoding="utf-8"))
        durable["identity"]["serial"] = "different-radio"
        spec.expected_report_path.write_text(
            json.dumps(durable, sort_keys=True) + "\n", encoding="utf-8"
        )

    def matrix(_radio, _options):
        return _write_report(spec, _matrix_report(spec))

    runner = matrix_runner_for_radio_factory(factory, matrix)
    aggregate, _path = run_release_campaign(config, _base(tmp_path), runner)

    assert aggregate["verdict"] == "invalid"
    failed = aggregate["runs"][spec.run_id]
    assert failed["status"] == "failed"
    assert "serial differs" in failed["error"]
