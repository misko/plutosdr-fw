"""Deterministic, resumable release-campaign orchestration for tandem quality."""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, ContextManager

from .tandem_quality import (
    NATIVE_GAIN_CONTROL_MODES,
    TandemQualityOptions,
    default_tx_trajectory,
    expected_tandem_gain_table,
    quality_modes,
    run_tandem_quality_matrix,
    validate_options,
)

CAMPAIGN_SCHEMA = "plutosdr-fw.tandem-agc-release-campaign.v1"
CHECKPOINT_NAME = "campaign-checkpoint.json"
REPORT_NAME = "campaign-report.json"


class CampaignConfigurationError(ValueError):
    """The requested plan cannot be resumed or is not a controlled campaign."""


@dataclass(frozen=True)
class BandCase:
    name: str
    center_frequency_hz: int


DEFAULT_BANDS = (
    BandCase("low-915mhz", 915_000_000),
    BandCase("mid-2450mhz", 2_450_000_000),
    BandCase("high-5800mhz", 5_800_000_000),
)


@dataclass(frozen=True)
class PolicyCase:
    name: str
    factor: str
    overrides: tuple[tuple[str, int], ...] = ()

    def kwargs(self) -> dict[str, int]:
        return dict(self.overrides)


_FACTOR_FIELDS = {
    "baseline": frozenset(),
    "low_power_threshold": frozenset({"tandem_low_power_threshold"}),
    "large_lmt_threshold": frozenset({"tandem_large_lmt_overload_threshold"}),
    "adc_thresholds": frozenset(
        {
            "tandem_large_adc_overload_threshold",
            "tandem_small_adc_overload_threshold",
        }
    ),
    "low_power_dwell": frozenset({"tandem_low_power_dwell_periods"}),
    "cooldown": frozenset({"tandem_cooldown_periods"}),
}


@dataclass(frozen=True)
class ClassificationLimits:
    snr_regression_db: float = 1.0
    coherence_regression: float = 0.001
    phase_regression_deg: float = 1.0
    frequency_regression_hz: float = 50.0


@dataclass(frozen=True)
class RepeatabilityLimits:
    snr_drop_db: float = 2.0
    coherence_drop: float = 0.002
    phase_increase_deg: float = 2.0
    frequency_increase_hz: float = 100.0
    temperature_span_c: float = 20.0


@dataclass(frozen=True)
class ReleaseCampaignConfig:
    output_dir: Path
    radio_serials: tuple[str, ...]
    repeat_cycles: int = 1
    cycle_interval_seconds: float = 0.0
    soak_deadline_seconds: float = 3_600.0
    bands: tuple[BandCase, ...] = DEFAULT_BANDS
    policy_cases: tuple[PolicyCase, ...] = ()
    classification_limits: ClassificationLimits = field(
        default_factory=ClassificationLimits
    )
    repeatability_limits: RepeatabilityLimits = field(
        default_factory=RepeatabilityLimits
    )


@dataclass(frozen=True)
class CampaignRun:
    ordinal: int
    run_id: str
    fingerprint: str
    serial: str
    cycle: int
    band: BandCase
    policy: PolicyCase
    options: TandemQualityOptions

    @property
    def expected_report_path(self) -> Path:
        return self.options.output_dir / self.serial / "tandem-agc-quality-report.json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "run_id": self.run_id,
            "fingerprint": self.fingerprint,
            "serial": self.serial,
            "cycle": self.cycle,
            "band": _json_safe(self.band),
            "policy": _json_safe(self.policy),
            "expected_report_path": str(self.expected_report_path),
        }


@dataclass(frozen=True)
class CampaignPlan:
    fingerprint: str
    runs: tuple[CampaignRun, ...]
    policy_cases: tuple[PolicyCase, ...]


RunMatrix = Callable[
    [CampaignRun, TandemQualityOptions], tuple[Mapping[str, Any], Path]
]


def _json_safe(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CampaignConfigurationError(
                "campaign JSON cannot contain non-finite values"
            )
        return value
    raise CampaignConfigurationError(f"campaign value is not JSON-safe: {type(value)}")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _json_safe(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(_json_safe(value), indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]", "-", value).strip("-.")
    if not slug:
        raise CampaignConfigurationError(f"invalid empty campaign label from {value!r}")
    return slug


def default_policy_cases(base: TandemQualityOptions) -> tuple[PolicyCase, ...]:
    """Return baseline plus one deterministic alternate for each policy factor."""

    def shifted(value: int, delta: int, minimum: int, maximum: int) -> int:
        candidate = value + delta
        return candidate if candidate <= maximum else max(minimum, value - delta)

    low = shifted(base.tandem_low_power_threshold, 4, 0, 127)
    lmt = shifted(base.tandem_large_lmt_overload_threshold, 4, 0, 63)
    adc_delta = 2 if base.tandem_large_adc_overload_threshold <= 253 else -2
    large_adc = base.tandem_large_adc_overload_threshold + adc_delta
    small_adc = base.tandem_small_adc_overload_threshold + adc_delta
    dwell = shifted(base.tandem_low_power_dwell_periods, 1, 1, 255)
    cooldown = shifted(base.tandem_cooldown_periods, 8, 0, 255)
    return (
        PolicyCase("baseline", "baseline"),
        PolicyCase(
            f"low-power-{low}",
            "low_power_threshold",
            (("tandem_low_power_threshold", low),),
        ),
        PolicyCase(
            f"large-lmt-{lmt}",
            "large_lmt_threshold",
            (("tandem_large_lmt_overload_threshold", lmt),),
        ),
        PolicyCase(
            f"adc-{large_adc}-{small_adc}",
            "adc_thresholds",
            (
                ("tandem_large_adc_overload_threshold", large_adc),
                ("tandem_small_adc_overload_threshold", small_adc),
            ),
        ),
        PolicyCase(
            f"dwell-{dwell}",
            "low_power_dwell",
            (("tandem_low_power_dwell_periods", dwell),),
        ),
        PolicyCase(
            f"cooldown-{cooldown}",
            "cooldown",
            (("tandem_cooldown_periods", cooldown),),
        ),
    )


def _validate_config(config: ReleaseCampaignConfig) -> None:
    if not config.radio_serials or len(set(config.radio_serials)) != len(
        config.radio_serials
    ):
        raise CampaignConfigurationError("radio serials must be nonempty and unique")
    if config.repeat_cycles <= 0:
        raise CampaignConfigurationError("repeat_cycles must be positive")
    for value, label, allow_zero in (
        (config.cycle_interval_seconds, "cycle interval", True),
        (config.soak_deadline_seconds, "soak deadline", False),
    ):
        if not math.isfinite(value) or value < 0 or (not allow_zero and value == 0):
            raise CampaignConfigurationError(f"{label} must be finite and positive")
    if not config.bands or len({band.name for band in config.bands}) != len(
        config.bands
    ):
        raise CampaignConfigurationError("band names must be nonempty and unique")
    for band in config.bands:
        _slug(band.name)
        expected_tandem_gain_table(band.center_frequency_hz)


def _validate_policy_cases(
    cases: Sequence[PolicyCase], base: TandemQualityOptions
) -> None:
    if not cases or cases[0] != PolicyCase("baseline", "baseline"):
        raise CampaignConfigurationError(
            "the first policy case must be the empty baseline"
        )
    if len({case.name for case in cases}) != len(cases):
        raise CampaignConfigurationError("policy case names must be unique")
    for case in cases:
        _slug(case.name)
        if case.factor not in _FACTOR_FIELDS:
            raise CampaignConfigurationError(f"unknown policy factor {case.factor!r}")
        keys = [key for key, _value in case.overrides]
        if (
            len(set(keys)) != len(keys)
            or frozenset(keys) != _FACTOR_FIELDS[case.factor]
        ):
            raise CampaignConfigurationError(
                f"policy {case.name!r} does not change exactly its declared factor"
            )
        changed = replace(base, **case.kwargs())
        if case.factor != "baseline" and changed == base:
            raise CampaignConfigurationError(
                f"policy {case.name!r} does not change baseline"
            )
        validate_options(changed)


def _options_payload(options: TandemQualityOptions) -> dict[str, Any]:
    value = _json_safe(options)
    assert isinstance(value, dict)
    value.pop("output_dir", None)
    return value


def build_release_plan(
    config: ReleaseCampaignConfig, base_options: TandemQualityOptions
) -> CampaignPlan:
    """Build the exact full-profile, all-native campaign without touching hardware."""

    _validate_config(config)
    release_base = replace(
        base_options,
        profile="full",
        tx_gain_trajectory_db=default_tx_trajectory("full"),
        native_gain_control_modes=NATIVE_GAIN_CONTROL_MODES,
    )
    validate_options(release_base)
    cases = config.policy_cases or default_policy_cases(release_base)
    _validate_policy_cases(cases, release_base)
    plan_payload = {
        "schema": CAMPAIGN_SCHEMA,
        "output_dir": str(config.output_dir.resolve()),
        "radio_serials": config.radio_serials,
        "repeat_cycles": config.repeat_cycles,
        "cycle_interval_seconds": config.cycle_interval_seconds,
        "soak_deadline_seconds": config.soak_deadline_seconds,
        "bands": config.bands,
        "policy_cases": cases,
        "classification_limits": config.classification_limits,
        "repeatability_limits": config.repeatability_limits,
        "base_options": _options_payload(release_base),
    }
    campaign_fingerprint = _fingerprint(plan_payload)
    runs: list[CampaignRun] = []
    for cycle in range(config.repeat_cycles):
        for serial in config.radio_serials:
            for band in config.bands:
                for policy in cases:
                    candidate = replace(
                        release_base,
                        center_frequency_hz=band.center_frequency_hz,
                        **policy.kwargs(),
                    )
                    validate_options(candidate)
                    run_payload = {
                        "campaign_fingerprint": campaign_fingerprint,
                        "cycle": cycle,
                        "serial": serial,
                        "band": band,
                        "policy": policy,
                        "options": _options_payload(candidate),
                    }
                    run_fingerprint = _fingerprint(run_payload)
                    run_id = (
                        f"c{cycle:03d}-{_slug(serial)[:40]}-{_slug(band.name)}-"
                        f"{_slug(policy.name)}-{run_fingerprint[:12]}"
                    )
                    options = replace(
                        candidate,
                        output_dir=config.output_dir.resolve() / "runs" / run_id,
                    )
                    runs.append(
                        CampaignRun(
                            ordinal=len(runs),
                            run_id=run_id,
                            fingerprint=run_fingerprint,
                            serial=serial,
                            cycle=cycle,
                            band=band,
                            policy=policy,
                            options=options,
                        )
                    )
    return CampaignPlan(campaign_fingerprint, tuple(runs), tuple(cases))


def matrix_runner_for_radio_factory(
    radio_factory: Callable[[str, TandemQualityOptions], ContextManager[Any]],
    matrix_callback: Callable[
        [Any, TandemQualityOptions], tuple[dict[str, Any], Path]
    ] = run_tandem_quality_matrix,
) -> RunMatrix:
    """Adapt fresh radios, returning JSON after the radio's cleanup has closed."""

    def run(spec: CampaignRun, options: TandemQualityOptions):
        with radio_factory(spec.serial, options) as radio:
            _in_memory_report, report_path = matrix_callback(radio, options)
        report_path = Path(report_path)
        if report_path.resolve() != spec.expected_report_path.resolve():
            raise ValueError(
                "matrix callback returned a report path outside its planned artifact"
            )
        # Issue46Radio.close() appends independently verified cleanup evidence to
        # the durable report, so the in-memory object intentionally predates it.
        durable_report = json.loads(report_path.read_text(encoding="utf-8"))
        return durable_report, report_path

    return run


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk_temperatures(value: Any) -> list[float]:
    values: list[float] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if (
                key == "temperature_mdeg_c"
                and isinstance(item, (int, float))
                and not isinstance(item, bool)
            ):
                number = float(item)
                if math.isfinite(number):
                    values.append(number / 1000.0)
            else:
                values.extend(_walk_temperatures(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(_walk_temperatures(item))
    return values


def _temperature_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    values = _walk_temperatures(report)
    if not values:
        return {"available": False, "count": 0}
    return {
        "available": True,
        "count": len(values),
        "minimum_c": min(values),
        "median_c": statistics.median(values),
        "maximum_c": max(values),
        "span_c": max(values) - min(values),
    }


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} is not finite")
    return result


def _tandem_quality_summary(report: Mapping[str, Any]) -> dict[str, float]:
    records = [
        record
        for record in report.get("modes", [])
        if record.get("mode") == "tandem_auto"
    ]
    if len(records) != 1 or not records[0].get("cells"):
        raise ValueError("report has no unique tandem quality trajectory")
    snr: list[float] = []
    coherence: list[float] = []
    phase: list[float] = []
    frequency: list[float] = []
    clipping: list[float] = []
    for cell in records[0]["cells"]:
        summary = cell["summary"]
        snr.extend(
            _number(value, "tone SNR") for value in summary["tone_snr_db_median"]
        )
        coherence.append(_number(summary["coherence_median"], "coherence"))
        phase.append(_number(summary["within_capture_phase_std_deg_max"], "phase"))
        frequency.append(
            abs(_number(summary["tone_frequency_error_hz_median"], "frequency"))
        )
        clipping.extend(
            _number(value, "clipping") for value in summary["clipping_fraction_max"]
        )
    return {
        "minimum_snr_db": min(snr),
        "minimum_coherence": min(coherence),
        "maximum_phase_std_deg": max(phase),
        "maximum_abs_frequency_error_hz": max(frequency),
        "maximum_clipping_fraction": max(clipping),
    }


def _cleanup_reasons(report: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if report.get("verdict") != "pass" or "fatal_error" in report:
        reasons.append("matrix did not finish with PASS")
    status = report.get("final_tandem_status", {})
    if not isinstance(status, Mapping):
        reasons.append("final tandem status is missing or malformed")
    else:
        for key, expected in (
            ("state", 0),
            ("fault_flags", 0),
            ("fifo_level", 0),
            ("overflow_count", 0),
        ):
            if status.get(key) != expected:
                reasons.append(f"final tandem {key} != {expected}")
    rx = report.get("final_rx_state", {})
    if not isinstance(rx, Mapping) or rx.get("modes") != ["manual", "manual"]:
        reasons.append("final RX modes are not both manual")
    cleanup = report.get("cleanup")
    if not isinstance(cleanup, Mapping):
        reasons.append("cleanup attestation is missing or malformed")
        return reasons
    if cleanup.get("verified") is not True:
        reasons.append("cleanup verified is not true")
    failures = cleanup.get("failures")
    if not isinstance(failures, list) or failures:
        reasons.append("cleanup failures are missing, malformed, or nonempty")
    for key in ("tx1_gain_db", "tx2_gain_db"):
        value = cleanup.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value > -80.0
        ):
            reasons.append(f"cleanup {key} is not a finite mute gain <= -80 dB")
    selectors = cleanup.get("selectors")
    if (
        not isinstance(selectors, list)
        or len(selectors) != 4
        or any(type(value) is not int or value != 3 for value in selectors)
    ):
        reasons.append("cleanup selectors are not exactly four ZERO=3 readbacks")
    dds = cleanup.get("dds")
    expected_dds = {f"altvoltage{index}" for index in range(8)}
    if not isinstance(dds, Mapping) or set(dds) != expected_dds:
        reasons.append("cleanup DDS evidence does not cover altvoltage0..7")
    else:
        for name in sorted(dds):
            item = dds[name]
            if not isinstance(item, Mapping) or type(item.get("present")) is not bool:
                reasons.append(f"cleanup DDS {name} evidence is malformed")
                continue
            if not item["present"]:
                continue
            for attribute in ("scale", "raw"):
                value = item.get(attribute)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value != 0.0
                ):
                    reasons.append(
                        f"cleanup DDS {name} {attribute} is not exactly zero"
                    )
    return reasons


def _validate_matrix_report(
    spec: CampaignRun, returned: Mapping[str, Any], path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_path = spec.expected_report_path.resolve()
    if path.resolve() != expected_path or not expected_path.is_file():
        raise ValueError(f"matrix report path is not the planned artifact: {path}")
    disk = json.loads(expected_path.read_text(encoding="utf-8"))
    if _json_safe(returned) != disk:
        raise ValueError("returned matrix report differs from its durable JSON")
    if disk.get("schema") != "plutosdr-fw.tandem-agc-quality.v1":
        raise ValueError("matrix report schema is missing or unsupported")
    if disk.get("identity", {}).get("serial") != spec.serial:
        raise ValueError("matrix report serial differs from planned radio")
    configuration = disk.get("configuration", {})
    if not isinstance(configuration, Mapping):
        raise ValueError("matrix configuration is missing or malformed")
    expected_configuration = _options_payload(spec.options)
    allowed_derived = {"output_dir", "minimum_effective_attenuation_db"}
    if set(configuration) != set(expected_configuration) | allowed_derived:
        raise ValueError("matrix configuration fields differ from plan")
    for key, expected in expected_configuration.items():
        if configuration.get(key) != expected:
            raise ValueError(f"matrix configuration {key} differs from plan")
    output_dir = configuration.get("output_dir")
    if (
        not isinstance(output_dir, str)
        or Path(output_dir).resolve() != spec.options.output_dir.resolve()
    ):
        raise ValueError("matrix configuration output_dir differs from plan")
    if (
        configuration.get("minimum_effective_attenuation_db")
        != spec.options.minimum_effective_attenuation_db
    ):
        raise ValueError("matrix minimum effective attenuation differs from plan")

    modes = disk.get("modes")
    if not isinstance(modes, list) or [record.get("mode") for record in modes] != list(
        quality_modes(spec.options)
    ):
        raise ValueError("matrix mode cells differ from plan")
    trajectory = list(spec.options.tx_gain_trajectory_db)
    for record in modes:
        cells = record.get("cells") if isinstance(record, Mapping) else None
        if not isinstance(cells, list) or len(cells) != len(trajectory):
            raise ValueError("matrix mode does not contain the full planned trajectory")
        for index, (cell, expected_gain) in enumerate(zip(cells, trajectory)):
            if not isinstance(cell, Mapping):
                raise ValueError("matrix trajectory cell is malformed")
            if (
                cell.get("level_index") != index
                or cell.get("tx2_gain_requested_db") != expected_gain
            ):
                raise ValueError("matrix trajectory order or gain differs from plan")
            measurements = cell.get("measurements")
            if (
                not isinstance(measurements, list)
                or len(measurements) != spec.options.measurement_frames
            ):
                raise ValueError("matrix cell measurement count differs from plan")
            summary = cell.get("summary")
            if (
                not isinstance(summary, Mapping)
                or type(summary.get("quality_valid")) is not bool
            ):
                raise ValueError("matrix cell quality summary is malformed")
            measurement_validity = []
            for measurement in measurements:
                quality = (
                    measurement.get("quality")
                    if isinstance(measurement, Mapping)
                    else None
                )
                if (
                    not isinstance(quality, Mapping)
                    or type(quality.get("quality_valid")) is not bool
                ):
                    raise ValueError("matrix measurement quality is malformed")
                measurement_validity.append(quality["quality_valid"])
            if summary["quality_valid"] != all(measurement_validity):
                raise ValueError("matrix cell quality validity is inconsistent")
            adaptive = record["mode"] != "manual_fixed"
            strongest_manual = expected_gain == spec.options.strongest_tx_gain_db
            if (adaptive or strongest_manual) and not summary["quality_valid"]:
                raise ValueError("required matrix cell is not quality-valid")

    preflight = disk.get("manual_fixture_preflight")
    expected_reference_cells = trajectory.count(spec.options.strongest_tx_gain_db)
    if (
        not isinstance(preflight, Mapping)
        or preflight.get("valid") is not True
        or preflight.get("tx2_gain_db") != spec.options.strongest_tx_gain_db
        or preflight.get("cell_count") != expected_reference_cells
        or not isinstance(preflight.get("stimulus_evidence"), Mapping)
        or preflight["stimulus_evidence"].get("valid") is not True
    ):
        raise ValueError("manual fixture preflight is missing or invalid")
    evaluation = disk.get("evaluation")
    expected_native_modes = list(quality_modes(spec.options)[1:-1])
    if (
        not isinstance(evaluation, Mapping)
        or evaluation.get("verdict") != "pass"
        or evaluation.get("failures") != []
        or evaluation.get("native_modes") != expected_native_modes
        or not isinstance(evaluation.get("manual_tone_evidence"), Mapping)
        or evaluation["manual_tone_evidence"].get("valid") is not True
    ):
        raise ValueError("matrix evaluation is missing or invalid")

    rf = disk.get("rf", {})
    expected_table = expected_tandem_gain_table(spec.options.center_frequency_hz)
    expected_readback = {
        "rx_lo_hz": spec.options.center_frequency_hz,
        "tx_lo_hz": spec.options.center_frequency_hz,
    }
    if (
        not isinstance(rf, Mapping)
        or rf.get("center_frequency_hz_requested") != spec.options.center_frequency_hz
        or rf.get("center_frequency_hz_readback") != expected_readback
        or rf.get("expected_tandem_gain_table_id") != int(expected_table)
        or rf.get("expected_tandem_gain_table_name") != expected_table.name.lower()
    ):
        raise ValueError("matrix gain-table attestation differs from plan")
    cleanup_reasons = _cleanup_reasons(disk)
    if cleanup_reasons:
        raise ValueError("; ".join(cleanup_reasons))
    final_rx_state = disk["final_rx_state"]
    if final_rx_state.get("gains_db") != [
        spec.options.manual_gain_db,
        spec.options.manual_gain_db,
    ]:
        raise ValueError("final RX gains differ from planned manual cleanup state")
    summary = {
        "quality": _tandem_quality_summary(disk),
        "temperature": _temperature_summary(disk),
        "cleanup_valid": True,
    }
    return disk, summary


def _classify(
    baseline: Mapping[str, float],
    candidate: Mapping[str, float],
    limits: ClassificationLimits,
) -> dict[str, Any]:
    deltas = {
        "minimum_snr_db": candidate["minimum_snr_db"] - baseline["minimum_snr_db"],
        "minimum_coherence": candidate["minimum_coherence"]
        - baseline["minimum_coherence"],
        "maximum_phase_std_deg": candidate["maximum_phase_std_deg"]
        - baseline["maximum_phase_std_deg"],
        "maximum_abs_frequency_error_hz": candidate["maximum_abs_frequency_error_hz"]
        - baseline["maximum_abs_frequency_error_hz"],
    }
    regressions = []
    if deltas["minimum_snr_db"] < -limits.snr_regression_db:
        regressions.append("SNR regression")
    if deltas["minimum_coherence"] < -limits.coherence_regression:
        regressions.append("coherence regression")
    if deltas["maximum_phase_std_deg"] > limits.phase_regression_deg:
        regressions.append("phase regression")
    if deltas["maximum_abs_frequency_error_hz"] > limits.frequency_regression_hz:
        regressions.append("frequency regression")
    improvements = bool(
        deltas["minimum_snr_db"] > limits.snr_regression_db
        or deltas["minimum_coherence"] > limits.coherence_regression
        or deltas["maximum_phase_std_deg"] < -limits.phase_regression_deg
        or deltas["maximum_abs_frequency_error_hz"] < -limits.frequency_regression_hz
    )
    classification = (
        "degraded" if regressions else "improved" if improvements else "equivalent"
    )
    return {"classification": classification, "deltas": deltas, "reasons": regressions}


def _repeatability(
    plan: CampaignPlan, records: Mapping[str, Any], config: ReleaseCampaignConfig
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[tuple[int, Mapping[str, Any]]]] = {}
    by_id = {run.run_id: run for run in plan.runs}
    for run_id, record in records.items():
        if record["status"] != "complete":
            continue
        run = by_id[run_id]
        groups.setdefault((run.serial, run.band.name, run.policy.name), []).append(
            (run.cycle, record)
        )
    output = []
    limits = config.repeatability_limits
    for (serial, band, policy), items in sorted(groups.items()):
        items.sort(key=lambda item: item[0])
        qualities = [item[1]["summary"]["quality"] for item in items]
        first = qualities[0]
        failures = []
        if len(items) != config.repeat_cycles:
            failures.append("missing repeat cycles")
        snr_drop = first["minimum_snr_db"] - min(
            item["minimum_snr_db"] for item in qualities
        )
        coherence_drop = first["minimum_coherence"] - min(
            item["minimum_coherence"] for item in qualities
        )
        phase_increase = (
            max(item["maximum_phase_std_deg"] for item in qualities)
            - first["maximum_phase_std_deg"]
        )
        frequency_increase = (
            max(item["maximum_abs_frequency_error_hz"] for item in qualities)
            - first["maximum_abs_frequency_error_hz"]
        )
        temperatures = [
            item[1]["summary"]["temperature"]["median_c"]
            for item in items
            if item[1]["summary"]["temperature"].get("available")
        ]
        temperature_span = (
            max(temperatures) - min(temperatures) if temperatures else None
        )
        for condition, message in (
            (snr_drop > limits.snr_drop_db, "SNR drift"),
            (coherence_drop > limits.coherence_drop, "coherence drift"),
            (phase_increase > limits.phase_increase_deg, "phase drift"),
            (frequency_increase > limits.frequency_increase_hz, "frequency drift"),
            (
                temperature_span is not None
                and temperature_span > limits.temperature_span_c,
                "temperature span",
            ),
        ):
            if condition:
                failures.append(message)
        output.append(
            {
                "serial": serial,
                "band": band,
                "policy": policy,
                "cycles": [cycle for cycle, _record in items],
                "verdict": "pass" if not failures else "fail",
                "failures": failures,
                "snr_drop_db": snr_drop,
                "coherence_drop": coherence_drop,
                "phase_increase_deg": phase_increase,
                "frequency_increase_hz": frequency_increase,
                "temperature_span_c": temperature_span,
            }
        )
    return output


def build_campaign_report(
    plan: CampaignPlan, checkpoint: Mapping[str, Any], config: ReleaseCampaignConfig
) -> dict[str, Any]:
    records = checkpoint["runs"]
    by_id = {run.run_id: run for run in plan.runs}
    baselines: dict[tuple[str, str, int], Mapping[str, Any]] = {}
    for run_id, record in records.items():
        run = by_id[run_id]
        if record["status"] == "complete" and run.policy.factor == "baseline":
            baselines[(run.serial, run.band.name, run.cycle)] = record
    classifications = []
    for run in plan.runs:
        record = records[run.run_id]
        if run.policy.factor == "baseline":
            classification: dict[str, Any] = {"classification": "baseline"}
        elif record["status"] != "complete":
            classification = {
                "classification": "unavailable",
                "reasons": ["run incomplete"],
            }
        else:
            baseline = baselines.get((run.serial, run.band.name, run.cycle))
            if baseline is None:
                classification = {
                    "classification": "unavailable",
                    "reasons": ["baseline incomplete"],
                }
            else:
                classification = _classify(
                    baseline["summary"]["quality"],
                    record["summary"]["quality"],
                    config.classification_limits,
                )
                base_temp = baseline["summary"]["temperature"]
                candidate_temp = record["summary"]["temperature"]
                classification["temperature_median_delta_c"] = (
                    candidate_temp["median_c"] - base_temp["median_c"]
                    if base_temp.get("available") and candidate_temp.get("available")
                    else None
                )
        classifications.append({**run.to_dict(), **classification})
    repeatability = _repeatability(plan, records, config)
    statuses = [record["status"] for record in records.values()]
    degraded = any(item["classification"] == "degraded" for item in classifications)
    drift_failed = any(item["verdict"] == "fail" for item in repeatability)
    if any(status in ("failed", "running") for status in statuses):
        verdict = "invalid"
    elif any(status == "pending" for status in statuses) or checkpoint.get(
        "deadline_exceeded"
    ):
        verdict = "incomplete"
    elif degraded or drift_failed:
        verdict = "fail"
    else:
        verdict = "pass"
    temperatures = [
        record["summary"]["temperature"]["median_c"]
        for record in records.values()
        if record["status"] == "complete"
        and record["summary"]["temperature"].get("available")
    ]
    report = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign_fingerprint": plan.fingerprint,
        "verdict": verdict,
        "reason": checkpoint.get("reason"),
        "counts": {
            status: statuses.count(status)
            for status in ("pending", "running", "complete", "failed")
        },
        "plan": [run.to_dict() for run in plan.runs],
        "runs": records,
        "policy_classifications": classifications,
        "repeatability": repeatability,
        "temperature": (
            {
                "available": True,
                "minimum_median_c": min(temperatures),
                "maximum_median_c": max(temperatures),
                "span_c": max(temperatures) - min(temperatures),
            }
            if temperatures
            else {"available": False}
        ),
        "started_unix_ns": checkpoint["started_unix_ns"],
        "updated_unix_ns": checkpoint["updated_unix_ns"],
    }
    _canonical_bytes(report)
    return report


def _new_checkpoint(plan: CampaignPlan, now: float) -> dict[str, Any]:
    stamp = int(now * 1_000_000_000)
    return {
        "schema": CAMPAIGN_SCHEMA,
        "campaign_fingerprint": plan.fingerprint,
        "started_unix_ns": stamp,
        "updated_unix_ns": stamp,
        "deadline_exceeded": False,
        "reason": None,
        "runs": {
            run.run_id: {"status": "pending", "attempts": 0, "spec": run.to_dict()}
            for run in plan.runs
        },
    }


def _load_checkpoint(path: Path, plan: CampaignPlan) -> dict[str, Any]:
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    if (
        checkpoint.get("schema") != CAMPAIGN_SCHEMA
        or checkpoint.get("campaign_fingerprint") != plan.fingerprint
    ):
        raise CampaignConfigurationError(
            "checkpoint does not match this campaign configuration"
        )
    if list(checkpoint.get("runs", {})) != [run.run_id for run in plan.runs]:
        raise CampaignConfigurationError(
            "checkpoint run plan differs from deterministic plan"
        )
    return checkpoint


def _verify_completed_artifacts(
    plan: CampaignPlan, checkpoint: Mapping[str, Any]
) -> None:
    by_id = {run.run_id: run for run in plan.runs}
    for run_id, record in checkpoint["runs"].items():
        if record["status"] != "complete":
            continue
        path = Path(record["report_path"])
        if not path.is_file() or _sha256(path) != record["report_sha256"]:
            raise CampaignConfigurationError(f"completed artifact changed for {run_id}")
        disk = json.loads(path.read_text(encoding="utf-8"))
        validated, recomputed_summary = _validate_matrix_report(
            by_id[run_id], disk, path
        )
        if record.get("matrix_verdict") != validated.get("verdict"):
            raise CampaignConfigurationError(
                f"checkpoint matrix verdict changed for {run_id}"
            )
        if _json_safe(record.get("summary")) != recomputed_summary:
            raise CampaignConfigurationError(
                f"checkpoint derived summary changed for {run_id}"
            )


def run_release_campaign(
    config: ReleaseCampaignConfig,
    base_options: TandemQualityOptions,
    run_matrix: RunMatrix,
    *,
    resume: bool = True,
    max_new_runs: int | None = None,
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], Path]:
    """Execute or resume a campaign, atomically preserving every decision."""

    plan = build_release_plan(config, base_options)
    root = config.output_dir.resolve()
    checkpoint_path = root / CHECKPOINT_NAME
    report_path = root / REPORT_NAME
    if checkpoint_path.exists():
        if not resume:
            raise CampaignConfigurationError("checkpoint exists but resume is disabled")
        checkpoint = _load_checkpoint(checkpoint_path, plan)
        _verify_completed_artifacts(plan, checkpoint)
    else:
        checkpoint = _new_checkpoint(plan, now())
        _atomic_json(checkpoint_path, checkpoint)
    blocked = [
        run_id
        for run_id, record in checkpoint["runs"].items()
        if record["status"] in ("running", "failed")
    ]
    if blocked:
        checkpoint["reason"] = f"fail-closed resume blocker: {blocked[0]}"
        checkpoint["updated_unix_ns"] = int(now() * 1_000_000_000)
        _atomic_json(checkpoint_path, checkpoint)
        report = build_campaign_report(plan, checkpoint, config)
        _atomic_json(report_path, report)
        return report, report_path
    started = checkpoint["started_unix_ns"] / 1_000_000_000
    deadline = started + config.soak_deadline_seconds
    executed = 0
    for spec in plan.runs:
        record = checkpoint["runs"][spec.run_id]
        if record["status"] == "complete":
            continue
        if max_new_runs is not None and executed >= max_new_runs:
            checkpoint["reason"] = "invocation run limit reached"
            break
        cycle_start = started + spec.cycle * config.cycle_interval_seconds
        current = now()
        if current < cycle_start:
            if cycle_start >= deadline:
                checkpoint["deadline_exceeded"] = True
                checkpoint["reason"] = "soak deadline precedes next cycle"
                break
            sleep(cycle_start - current)
            current = now()
        if current >= deadline:
            checkpoint["deadline_exceeded"] = True
            checkpoint["reason"] = "soak deadline exceeded"
            break
        record["status"] = "running"
        record["attempts"] += 1
        record["started_unix_ns"] = int(current * 1_000_000_000)
        checkpoint["updated_unix_ns"] = record["started_unix_ns"]
        checkpoint["reason"] = None
        _atomic_json(checkpoint_path, checkpoint)
        try:
            returned, returned_path = run_matrix(spec, spec.options)
            disk, summary = _validate_matrix_report(spec, returned, Path(returned_path))
            record.update(
                {
                    "status": "complete",
                    "completed_unix_ns": int(now() * 1_000_000_000),
                    "report_path": str(spec.expected_report_path.resolve()),
                    "report_sha256": _sha256(spec.expected_report_path),
                    "matrix_verdict": disk["verdict"],
                    "summary": summary,
                }
            )
        except Exception as error:
            record.update(
                {
                    "status": "failed",
                    "completed_unix_ns": int(now() * 1_000_000_000),
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            checkpoint["reason"] = f"run failed: {spec.run_id}"
        executed += 1
        checkpoint["updated_unix_ns"] = int(now() * 1_000_000_000)
        _atomic_json(checkpoint_path, checkpoint)
        report = build_campaign_report(plan, checkpoint, config)
        _atomic_json(report_path, report)
        if record["status"] == "failed":
            return report, report_path
    checkpoint["updated_unix_ns"] = int(now() * 1_000_000_000)
    _atomic_json(checkpoint_path, checkpoint)
    report = build_campaign_report(plan, checkpoint, config)
    _atomic_json(report_path, report)
    return report, report_path
