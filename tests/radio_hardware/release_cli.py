"""Guarded, serial-scoped hardware qualification entry point for a v8 release.

The module intentionally does not deploy firmware.  It opens a fresh local-USB
radio for every steady-state matrix or band-specific transient/modulated cell,
then accepts evidence only after ``Issue46Radio.close()`` has appended verified
mute/selector/DDS cleanup to the durable report.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import statistics
import sys
import time
from builtins import BaseExceptionGroup
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from . import release_campaign as steady_campaign
from .experiment import Issue46Options, Issue46Radio
from .metadata_abi import (
    FLAG_HARDWARE_SAMPLE_COUNTER_VALID,
    FLAG_SAMPLE_SEQUENCE_VALID,
    FLAG_TANDEM_METADATA_VALID,
    TANDEM_UNSAFE_FLAGS,
    TandemEventDirection,
    TandemEventReason,
    TandemState,
)
from .modulated_hardware import (
    DEFAULT_MODULATED_TX2_GAIN_DB,
    MAX_DIAGNOSTIC_IQ_ARTIFACT_BYTES,
    MODE_MANUAL,
    MODE_TANDEM,
    RELEASE_MODULATED_MODES,
    ModulatedHardwareOptions,
    evaluate_modulated_hardware_report,
    modulated_mode_evidence_policy,
    run_modulated_hardware_campaign,
    validate_modulated_hardware_options,
)
from .release_campaign import (
    BandCase,
    PolicyCase,
    ReleaseCampaignConfig,
    build_campaign_report,
    build_release_plan,
    matrix_runner_for_radio_factory,
    run_release_campaign,
)
from .tandem_quality import (
    AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES,
    TandemQualityOptions,
    default_tx_trajectory,
    expected_tandem_gain_table,
    validate_options,
)
from .transient_hardware import (
    TRANSIENT_MODES,
    TransientCaptureOptions,
    run_transient_hardware,
    transient_evidence_policy,
    validate_transient_options,
)
from .transient_quality import (
    StimulusCommand,
    calculate_transient_response,
    reconcile_tandem_events,
)

AGGREGATE_SCHEMA = "plutosdr-fw.tandem-agc-release-hardware.v1"
AGGREGATE_CHECKPOINT = "release-hardware-checkpoint.json"
AGGREGATE_REPORT = "release-hardware-report.json"
DEFAULT_PHASES = ("steady", "transient", "modulated")
BASELINE_POLICY = PolicyCase("baseline", "baseline")
HARNESS_SOURCE_NAMES = (
    "experiment.py",
    "metadata_abi.py",
    "tone_quality.py",
    "tandem_quality.py",
    "release_campaign.py",
    "transient_quality.py",
    "transient_hardware.py",
    "modulated_quality.py",
    "modulated_hardware.py",
    "release_cli.py",
)


class ReleaseCliError(RuntimeError):
    """A configuration, resume, or durable-evidence invariant failed."""


@dataclass(frozen=True)
class ReleaseHardwareOptions:
    serial: str
    firmware_version: str
    firmware_pattern: str
    libiio_source_commit: str
    harness_sources: tuple[tuple[str, str], ...]
    physical_attenuation_db: float
    output_dir: Path
    phases: tuple[str, ...]
    bands: tuple[BandCase, ...]
    policy_set: str
    repeat_cycles: int
    cycle_interval_seconds: float
    soak_deadline_seconds: float
    max_new_steady_runs: int | None
    sample_rate_hz: int
    samples_per_channel: int
    phase_max_seconds: float
    retry_failed: bool
    resume: bool
    plan_only: bool

    @property
    def steady_key(self) -> str:
        return "steady_characterization" if self.policy_set == "full" else "steady_soak"


@dataclass(frozen=True)
class PhaseSpec:
    key: str
    kind: str
    band: BandCase | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "band": asdict(self.band) if self.band is not None else None,
        }


@dataclass(frozen=True)
class ValidatedPhase:
    verdict: str
    cleanup_verified: bool
    summary: Mapping[str, Any]


PhaseExecutor = Callable[[PhaseSpec, Path], Path]
PhaseValidator = Callable[[PhaseSpec, Path, Path], ValidatedPhase]


def _finite_nonnegative(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0.0:
        raise argparse.ArgumentTypeError("value must be finite and nonnegative")
    return parsed


def _finite_positive(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise argparse.ArgumentTypeError("value must be finite and positive")
    return parsed


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def _harness_sources() -> tuple[tuple[str, str], ...]:
    root = Path(__file__).resolve().parent
    return tuple((name, _sha256(root / name)) for name in HARNESS_SOURCE_NAMES)


def _band(value: str) -> BandCase:
    try:
        name, raw_frequency = value.split("=", 1)
        frequency = int(raw_frequency)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("band must be NAME=HZ") from error
    if not name or re.fullmatch(r"[A-Za-z0-9_.-]+", name) is None:
        raise argparse.ArgumentTypeError("band name must be a nonempty safe label")
    return BandCase(name, frequency)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run serial-attested tandem-AGC release qualification; this command "
            "never deploys or flashes firmware"
        )
    )
    parser.add_argument("--authorize-tx2-loopback", action="store_true")
    parser.add_argument("--radio-serial", required=True)
    parser.add_argument(
        "--firmware-version",
        required=True,
        help="literal complete fw_version (converted to an anchored escaped regex)",
    )
    parser.add_argument(
        "--physical-attenuation-db",
        required=True,
        type=_finite_nonnegative,
        help="finite current physical loss; TX backoff is accounted separately",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/radio-hardware/tandem-agc-release"),
    )
    parser.add_argument(
        "--phase",
        action="append",
        choices=DEFAULT_PHASES,
        help="requested phase; repeat to select a subset (default: all)",
    )
    parser.add_argument(
        "--band",
        action="append",
        type=_band,
        help="NAME=HZ; repeat for an explicit band set",
    )
    parser.add_argument(
        "--policy-set",
        choices=("full", "baseline"),
        default="full",
        help=(
            "full = one-factor characterization; baseline = repeatability/soak "
            "without multiplying policy cases"
        ),
    )
    parser.add_argument("--repeat-cycles", type=_positive_integer)
    parser.add_argument("--cycle-interval-seconds", type=_finite_nonnegative)
    parser.add_argument("--soak-deadline-seconds", type=_finite_positive)
    parser.add_argument("--max-new-steady-runs", type=_positive_integer)
    parser.add_argument("--sample-rate-hz", type=_positive_integer, default=2_500_000)
    parser.add_argument("--samples-per-channel", type=_positive_integer, default=65_536)
    parser.add_argument("--phase-max-seconds", type=_finite_positive, default=600.0)
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="explicitly authorize a fresh attempt after a recorded failed phase",
    )
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="print the fully validated plan without importing iio or opening USB",
    )
    return parser


def parse_cli_args(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> ReleaseHardwareOptions:
    parser = build_parser()
    namespace = parser.parse_args(argv)
    environment = os.environ if environ is None else environ
    if not namespace.authorize_tx2_loopback:
        parser.error("--authorize-tx2-loopback is required before any TX mutation")
    serial = namespace.radio_serial.strip()
    firmware = namespace.firmware_version.strip()
    if not serial or serial != namespace.radio_serial:
        parser.error("--radio-serial must be nonempty with no surrounding whitespace")
    if re.fullmatch(r"[A-Za-z0-9_.-]+", serial) is None:
        parser.error("--radio-serial must contain only safe immutable-ID characters")
    if not firmware or firmware != namespace.firmware_version or "\n" in firmware:
        parser.error("--firmware-version must be one exact nonempty line")
    commit = environment.get("PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT", "")
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        parser.error(
            "PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT must contain the manifest-pinned "
            "40-hex host libiio commit"
        )
    requested_phases = tuple(namespace.phase or DEFAULT_PHASES)
    if len(set(requested_phases)) != len(requested_phases):
        parser.error("--phase values cannot be duplicated")
    phases = tuple(phase for phase in DEFAULT_PHASES if phase in requested_phases)
    bands = tuple(namespace.band or steady_campaign.DEFAULT_BANDS)
    if len({band.name for band in bands}) != len(bands):
        parser.error("band names must be unique")
    if len({band.center_frequency_hz for band in bands}) != len(bands):
        parser.error("band frequencies must be unique")
    # Full characterization is intentionally a single cycle by default.  A
    # baseline-only soak spans approximately one hour by default (t=0..3600).
    repeats = namespace.repeat_cycles
    if repeats is None:
        repeats = 1 if namespace.policy_set == "full" else 4
    interval = namespace.cycle_interval_seconds
    if interval is None:
        interval = 0.0 if namespace.policy_set == "full" else 1_200.0
    deadline = namespace.soak_deadline_seconds
    if deadline is None:
        deadline = 14_400.0 if namespace.policy_set == "full" else 5_400.0
    options = ReleaseHardwareOptions(
        serial=serial,
        firmware_version=firmware,
        firmware_pattern=r"\A" + re.escape(firmware) + r"\Z",
        libiio_source_commit=commit,
        harness_sources=_harness_sources(),
        physical_attenuation_db=namespace.physical_attenuation_db,
        # Every invocation owns exactly one immutable serial.  Scope even an
        # explicit base directory so four parallel radios cannot share state.
        output_dir=(namespace.output.resolve() / serial),
        phases=phases,
        bands=bands,
        policy_set=namespace.policy_set,
        repeat_cycles=repeats,
        cycle_interval_seconds=interval,
        soak_deadline_seconds=deadline,
        max_new_steady_runs=namespace.max_new_steady_runs,
        sample_rate_hz=namespace.sample_rate_hz,
        samples_per_channel=namespace.samples_per_channel,
        phase_max_seconds=namespace.phase_max_seconds,
        retry_failed=namespace.retry_failed,
        resume=not namespace.no_resume,
        plan_only=namespace.plan_only,
    )
    validate_release_hardware_options(options)
    return options


def _base_quality(
    options: ReleaseHardwareOptions, *, output_dir: Path, band: BandCase | None = None
) -> TandemQualityOptions:
    quality = TandemQualityOptions(
        tx_gain_trajectory_db=default_tx_trajectory("full"),
        physical_attenuation_db=options.physical_attenuation_db,
        center_frequency_hz=(
            band.center_frequency_hz if band is not None else 915_000_000
        ),
        sample_rate_hz=options.sample_rate_hz,
        samples_per_channel=options.samples_per_channel,
        native_gain_control_modes=AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES,
        max_seconds=options.phase_max_seconds,
        output_dir=output_dir,
        profile="full",
    )
    validate_options(quality)
    return quality


def _steady_inputs(
    options: ReleaseHardwareOptions, work_dir: Path
) -> tuple[ReleaseCampaignConfig, TandemQualityOptions]:
    policies = () if options.policy_set == "full" else (BASELINE_POLICY,)
    config = ReleaseCampaignConfig(
        output_dir=work_dir,
        radio_serials=(options.serial,),
        repeat_cycles=options.repeat_cycles,
        cycle_interval_seconds=options.cycle_interval_seconds,
        soak_deadline_seconds=options.soak_deadline_seconds,
        bands=options.bands,
        policy_cases=policies,
    )
    base = _base_quality(options, output_dir=work_dir / "unused")
    build_release_plan(config, base)
    return config, base


def phase_specs(options: ReleaseHardwareOptions) -> tuple[PhaseSpec, ...]:
    result: list[PhaseSpec] = []
    for phase in options.phases:
        if phase == "steady":
            result.append(PhaseSpec(options.steady_key, "steady"))
        else:
            result.extend(
                PhaseSpec(f"{phase}_{band.name}", phase, band) for band in options.bands
            )
    return tuple(result)


def validate_release_hardware_options(options: ReleaseHardwareOptions) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", options.libiio_source_commit) is None:
        raise ValueError("host libiio commit must be exact 40-hex")
    if tuple(
        name for name, _digest in options.harness_sources
    ) != HARNESS_SOURCE_NAMES or any(
        re.fullmatch(r"[0-9a-f]{64}", digest) is None
        for _name, digest in options.harness_sources
    ):
        raise ValueError("release harness source manifest is incomplete or malformed")
    if re.fullmatch(options.firmware_pattern, options.firmware_version) is None:
        raise ValueError("anchored firmware regex does not match the exact version")
    if options.firmware_pattern != r"\A" + re.escape(options.firmware_version) + r"\Z":
        raise ValueError("firmware regex must be escaped and anchored exactly")
    if not options.phases or any(
        phase not in DEFAULT_PHASES for phase in options.phases
    ):
        raise ValueError("at least one supported phase is required")
    if options.policy_set not in ("full", "baseline"):
        raise ValueError("policy set must be full or baseline")
    if options.repeat_cycles <= 0:
        raise ValueError("repeat cycles must be positive")
    if options.cycle_interval_seconds < 0 or not math.isfinite(
        options.cycle_interval_seconds
    ):
        raise ValueError("cycle interval must be finite and nonnegative")
    if options.soak_deadline_seconds <= 0 or not math.isfinite(
        options.soak_deadline_seconds
    ):
        raise ValueError("soak deadline must be finite and positive")
    if not options.bands:
        raise ValueError("at least one RF band is required")
    if "steady" in options.phases:
        _steady_inputs(options, options.output_dir / "preflight-steady")
    capture = TransientCaptureOptions()
    for band in options.bands:
        quality = _base_quality(
            options, output_dir=options.output_dir / "preflight-transient", band=band
        )
        if "transient" in options.phases:
            validate_transient_options(quality, capture)
        if "modulated" in options.phases:
            validate_modulated_hardware_options(
                ModulatedHardwareOptions(
                    physical_attenuation_db=options.physical_attenuation_db,
                    center_frequency_hz=band.center_frequency_hz,
                    tx2_gain_db=DEFAULT_MODULATED_TX2_GAIN_DB,
                    modes=RELEASE_MODULATED_MODES,
                    max_seconds=options.phase_max_seconds,
                    output_dir=options.output_dir / "preflight-modulated",
                )
            )


def _assert_harness_unchanged(options: ReleaseHardwareOptions) -> None:
    if _harness_sources() != options.harness_sources:
        raise ReleaseCliError("release harness source changed after plan validation")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ReleaseCliError("aggregate JSON cannot contain non-finite values")
        return value
    raise ReleaseCliError(f"aggregate JSON cannot encode {type(value)}")


def _configuration(options: ReleaseHardwareOptions) -> dict[str, Any]:
    return {
        "serial": options.serial,
        "firmware_version": options.firmware_version,
        "firmware_pattern": options.firmware_pattern,
        "libiio_source_commit": options.libiio_source_commit,
        "harness_sources": dict(options.harness_sources),
        "physical_attenuation_db": options.physical_attenuation_db,
        "output_dir": str(options.output_dir),
        "requested_phases": list(options.phases),
        "bands": [asdict(band) for band in options.bands],
        "policy_set": options.policy_set,
        "steady_campaign_kind": (
            "one_factor_characterization"
            if options.policy_set == "full"
            else "baseline_repeatability_soak"
        ),
        "repeat_cycles": options.repeat_cycles,
        "cycle_interval_seconds": options.cycle_interval_seconds,
        "soak_deadline_seconds": options.soak_deadline_seconds,
        "sample_rate_hz": options.sample_rate_hz,
        "samples_per_channel": options.samples_per_channel,
        "autonomous_native_gain_control_modes": list(
            AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES
        ),
        "modulated_modes": list(RELEASE_MODULATED_MODES),
        "modulated_tx2_gain_db": DEFAULT_MODULATED_TX2_GAIN_DB,
        "phase_max_seconds": options.phase_max_seconds,
    }


def _fingerprint(options: ReleaseHardwareOptions, specs: Sequence[PhaseSpec]) -> str:
    payload = {"schema": AGGREGATE_SCHEMA, "configuration": _configuration(options)}
    payload["plan"] = [spec.to_dict() for spec in specs]
    encoded = json.dumps(
        _json_safe(payload), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_json_safe(value), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _new_checkpoint(
    options: ReleaseHardwareOptions, specs: Sequence[PhaseSpec]
) -> dict[str, Any]:
    stamp = time.time_ns()
    return {
        "schema": AGGREGATE_SCHEMA,
        "fingerprint": _fingerprint(options, specs),
        "configuration": _configuration(options),
        "started_unix_ns": stamp,
        "updated_unix_ns": stamp,
        "phases": {
            spec.key: {
                "status": "pending",
                "attempts": 0,
                "spec": spec.to_dict(),
                "history": [],
            }
            for spec in specs
        },
    }


def _aggregate_report(
    checkpoint: Mapping[str, Any], specs: Sequence[PhaseSpec]
) -> dict[str, Any]:
    phases = checkpoint["phases"]
    statuses = [phases[spec.key]["status"] for spec in specs]
    complete = [
        phases[spec.key] for spec in specs if phases[spec.key]["status"] == "complete"
    ]
    all_cleanup = len(complete) == len(specs) and all(
        record.get("cleanup_verified") is True for record in complete
    )
    if any(status in ("failed", "running") for status in statuses):
        verdict = "invalid"
    elif len(complete) != len(specs):
        verdict = "incomplete"
    elif not all_cleanup or any(
        record.get("phase_verdict") != "pass" for record in complete
    ):
        verdict = "fail"
    else:
        verdict = "pass"
    return {
        "schema": AGGREGATE_SCHEMA,
        "fingerprint": checkpoint["fingerprint"],
        "verdict": verdict,
        "all_requested_phases_complete": len(complete) == len(specs),
        "all_cleanup_verified": all_cleanup,
        "configuration": checkpoint["configuration"],
        "plan": [spec.to_dict() for spec in specs],
        "counts": {
            status: statuses.count(status)
            for status in ("pending", "running", "complete", "failed")
        },
        "phases": phases,
        "started_unix_ns": checkpoint["started_unix_ns"],
        "updated_unix_ns": checkpoint["updated_unix_ns"],
    }


def _load_checkpoint(
    path: Path, options: ReleaseHardwareOptions, specs: Sequence[PhaseSpec]
) -> dict[str, Any]:
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    expected_keys = [spec.key for spec in specs]
    if (
        checkpoint.get("schema") != AGGREGATE_SCHEMA
        or checkpoint.get("fingerprint") != _fingerprint(options, specs)
        or list(checkpoint.get("phases", {})) != expected_keys
    ):
        raise ReleaseCliError("aggregate checkpoint differs from the requested plan")
    return checkpoint


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _verify_completed(
    checkpoint: Mapping[str, Any],
    specs: Sequence[PhaseSpec],
    validator: PhaseValidator,
    root: Path,
) -> None:
    for spec in specs:
        record = checkpoint["phases"][spec.key]
        if record["status"] != "complete":
            continue
        report_path = Path(record["report_path"])
        work_dir = Path(record["work_dir"])
        if not _inside(work_dir, root) or not _inside(report_path, work_dir):
            raise ReleaseCliError(f"completed {spec.key} path escapes its attempt")
        if not report_path.is_file() or _sha256(report_path) != record.get(
            "report_sha256"
        ):
            raise ReleaseCliError(f"completed {spec.key} artifact changed")
        validated = validator(spec, report_path, work_dir)
        if (
            validated.verdict != "pass"
            or not validated.cleanup_verified
            or _json_safe(validated.summary) != record.get("summary")
        ):
            raise ReleaseCliError(f"completed {spec.key} evidence no longer validates")


def _run_aggregate_locked(
    options: ReleaseHardwareOptions,
    executor: PhaseExecutor,
    validator: PhaseValidator,
) -> tuple[dict[str, Any], Path]:
    """Execute/resume an aggregate using injected hardware-free boundaries."""

    specs = phase_specs(options)
    root = options.output_dir
    checkpoint_path = root / AGGREGATE_CHECKPOINT
    report_path = root / AGGREGATE_REPORT
    if checkpoint_path.exists():
        if not options.resume:
            raise ReleaseCliError("aggregate checkpoint exists but resume is disabled")
        checkpoint = _load_checkpoint(checkpoint_path, options, specs)
        _verify_completed(checkpoint, specs, validator, root)
    else:
        checkpoint = _new_checkpoint(options, specs)
        _atomic_json(checkpoint_path, checkpoint)

    # A process may have died while a phase owned TX.  Never accept its artifact:
    # retain an audit entry and force a fresh attempt directory.  The subsequent
    # Issue46Radio open acquires the serial lock and mutes before configuration.
    for spec in specs:
        record = checkpoint["phases"][spec.key]
        if record["status"] == "running":
            record["history"].append(
                {
                    "attempt": record["attempts"],
                    "status": "abandoned_untrusted_interrupted_attempt",
                    "work_dir": record.get("work_dir"),
                }
            )
            record["status"] = "pending"
            record["resumable"] = False
        elif record["status"] == "failed" and options.retry_failed:
            record["history"].append(
                {
                    "attempt": record["attempts"],
                    "status": "explicitly_retried_failed_attempt",
                    "work_dir": record.get("work_dir"),
                    "error": record.get("error"),
                }
            )
            record["status"] = "pending"
            record["resumable"] = False
    checkpoint["updated_unix_ns"] = time.time_ns()
    _atomic_json(checkpoint_path, checkpoint)

    for spec in specs:
        record = checkpoint["phases"][spec.key]
        if record["status"] == "complete":
            continue
        if record["status"] == "failed":
            break
        resume_work = record.get("resumable") is True and record.get("work_dir")
        record["attempts"] += 1
        work_dir = (
            Path(record["work_dir"])
            if resume_work
            else root / "artifacts" / spec.key / f"attempt-{record['attempts']:04d}"
        )
        record.update(
            {
                "status": "running",
                "work_dir": str(work_dir.resolve()),
                "started_unix_ns": time.time_ns(),
                "resumable": False,
            }
        )
        checkpoint["updated_unix_ns"] = time.time_ns()
        _atomic_json(checkpoint_path, checkpoint)
        _atomic_json(report_path, _aggregate_report(checkpoint, specs))
        try:
            artifact = Path(executor(spec, work_dir.resolve())).resolve()
            if not artifact.is_file() or not _inside(artifact, work_dir):
                raise ReleaseCliError(
                    f"{spec.key} returned no durable report inside its attempt"
                )
            validated = validator(spec, artifact, work_dir.resolve())
            if validated.verdict == "incomplete" and spec.kind == "steady":
                record.update(
                    {
                        "status": "pending",
                        "resumable": True,
                        "report_path": str(artifact),
                        "report_sha256": _sha256(artifact),
                        "phase_verdict": "incomplete",
                        "cleanup_verified": False,
                        "summary": _json_safe(validated.summary),
                    }
                )
            elif validated.verdict != "pass" or not validated.cleanup_verified:
                raise ReleaseCliError(
                    f"{spec.key} did not prove PASS plus durable cleanup"
                )
            else:
                record.update(
                    {
                        "status": "complete",
                        "completed_unix_ns": time.time_ns(),
                        "report_path": str(artifact),
                        "report_sha256": _sha256(artifact),
                        "phase_verdict": validated.verdict,
                        "cleanup_verified": True,
                        "summary": _json_safe(validated.summary),
                        "resumable": False,
                    }
                )
        except BaseException as error:  # noqa: BLE001 - persist every invalid exit
            record.update(
                {
                    "status": "failed",
                    "completed_unix_ns": time.time_ns(),
                    "error": f"{type(error).__name__}: {error}",
                    "cleanup_verified": False,
                    "resumable": False,
                }
            )
        checkpoint["updated_unix_ns"] = time.time_ns()
        _atomic_json(checkpoint_path, checkpoint)
        _atomic_json(report_path, _aggregate_report(checkpoint, specs))
        if record["status"] == "failed":
            break
        if record["status"] == "pending" and record.get("resumable") is True:
            # An explicit --max-new-steady-runs is an incremental steady-state
            # invocation, not permission to move on to unrelated TX waveforms.
            break
    report = _aggregate_report(checkpoint, specs)
    _atomic_json(report_path, report)
    return report, report_path


def run_aggregate(
    options: ReleaseHardwareOptions,
    executor: PhaseExecutor,
    validator: PhaseValidator,
) -> tuple[dict[str, Any], Path]:
    """Serialize one immutable radio's aggregate state for this invocation."""

    options.output_dir.mkdir(parents=True, exist_ok=True)
    lock_path = options.output_dir / "release-hardware.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ReleaseCliError(
                f"another release invocation owns serial {options.serial}"
            ) from error
        lock.seek(0)
        lock.truncate()
        lock.write(f"pid={os.getpid()} serial={options.serial}\n")
        lock.flush()
        return _run_aggregate_locked(options, executor, validator)


def _issue_options(
    options: ReleaseHardwareOptions,
    quality: TandemQualityOptions,
    *,
    namespace: str,
    tx_gain_db: float | None = None,
) -> Issue46Options:
    return Issue46Options(
        serial=options.serial,
        uri=None,
        allow_non_usb=False,
        firmware_pattern=options.firmware_pattern,
        libiio_source_commit=options.libiio_source_commit,
        attenuation_db=options.physical_attenuation_db,
        tx_gain_db=(quality.strongest_tx_gain_db if tx_gain_db is None else tx_gain_db),
        sample_rate_hz=quality.sample_rate_hz,
        samples_per_channel=quality.samples_per_channel,
        profile="repro",
        sink="ram",
        expected="green",
        output_dir=quality.output_dir,
        max_seconds=quality.max_seconds,
        save_iq=False,
        pn_min_coherence=0.03,
        pn_min_peak_ratio=1.5,
        lock_namespace=namespace,
        center_frequency_hz=quality.center_frequency_hz,
    )


@contextmanager
def _radio_lifecycle(
    iio_module: Any,
    radio_options: Issue46Options,
    radio_factory: Callable[[Any, Issue46Options], Issue46Radio],
) -> Iterator[Issue46Radio]:
    radio = radio_factory(iio_module, radio_options)
    try:
        yield radio
    except BaseException as body_error:
        try:
            radio.close()
        except BaseException as close_error:  # noqa: BLE001
            raise BaseExceptionGroup(
                "release phase and final radio cleanup both failed",
                [body_error, close_error],
            ) from None
        raise
    else:
        radio.close()


def production_executor(
    options: ReleaseHardwareOptions,
    iio_module: Any,
    *,
    radio_factory: Callable[[Any, Issue46Options], Issue46Radio] = Issue46Radio,
) -> PhaseExecutor:
    def execute(spec: PhaseSpec, work_dir: Path) -> Path:
        _assert_harness_unchanged(options)
        if spec.kind == "steady":
            config, base = _steady_inputs(options, work_dir)

            @contextmanager
            def open_radio(
                _serial: str, quality: TandemQualityOptions
            ) -> Iterator[Issue46Radio]:
                with _radio_lifecycle(
                    iio_module,
                    _issue_options(
                        options, quality, namespace="tandem-agc-release-steady"
                    ),
                    radio_factory,
                ) as radio:
                    yield radio

            report, path = run_release_campaign(
                config,
                base,
                matrix_runner_for_radio_factory(open_radio),
                max_new_runs=options.max_new_steady_runs,
            )
            del report
            return path
        assert spec.band is not None
        if spec.kind == "transient":
            quality = _base_quality(options, output_dir=work_dir, band=spec.band)
            with _radio_lifecycle(
                iio_module,
                _issue_options(
                    options, quality, namespace="tandem-agc-release-transient"
                ),
                radio_factory,
            ) as radio:
                _report, path = run_transient_hardware(radio, quality)
            return path
        if spec.kind == "modulated":
            modulated = ModulatedHardwareOptions(
                physical_attenuation_db=options.physical_attenuation_db,
                center_frequency_hz=spec.band.center_frequency_hz,
                tx2_gain_db=DEFAULT_MODULATED_TX2_GAIN_DB,
                modes=RELEASE_MODULATED_MODES,
                max_seconds=options.phase_max_seconds,
                output_dir=work_dir,
            )
            # The modulated signal intentionally uses its deterministic 1.024-MHz
            # sample grid rather than the tone/transient grid.
            radio_quality = replace(
                _base_quality(options, output_dir=work_dir, band=spec.band),
                sample_rate_hz=modulated.sample_rate_hz,
                samples_per_channel=modulated.capture_samples,
            )
            with _radio_lifecycle(
                iio_module,
                _issue_options(
                    options,
                    radio_quality,
                    namespace="tandem-agc-release-modulated",
                    tx_gain_db=modulated.tx2_gain_db,
                ),
                radio_factory,
            ) as radio:
                _report, path = run_modulated_hardware_campaign(radio, modulated)
            return path
        raise AssertionError(f"unsupported phase {spec.kind}")

    return execute


def _cleanup_errors(report: Mapping[str, Any]) -> list[str]:
    cleanup = report.get("cleanup")
    if not isinstance(cleanup, Mapping):
        return ["cleanup is missing"]
    errors = []
    if cleanup.get("verified") is not True or cleanup.get("failures") != []:
        errors.append("cleanup was not verified without failures")
    if cleanup.get("selectors") != [3, 3, 3, 3]:
        errors.append("cleanup selectors are not all ZERO")
    for key in ("tx1_gain_db", "tx2_gain_db"):
        value = cleanup.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) > -80.0
        ):
            errors.append(f"cleanup {key} is not muted below -80 dB")
    dds = cleanup.get("dds")
    if not isinstance(dds, Mapping) or set(dds) != {
        f"altvoltage{index}" for index in range(8)
    }:
        errors.append("cleanup DDS coverage is incomplete")
    else:
        for name, evidence in dds.items():
            if (
                not isinstance(evidence, Mapping)
                or type(evidence.get("present")) is not bool
            ):
                errors.append(f"cleanup {name} is malformed")
            elif evidence["present"] and any(
                evidence.get(attribute) != 0.0 for attribute in ("scale", "raw")
            ):
                errors.append(f"cleanup {name} is not disabled")
    return errors


def _modulated_dma_cleanup_errors(waveforms: Any) -> list[str]:
    if not isinstance(waveforms, list):
        return ["modulated waveforms are missing"]
    errors: list[str] = []
    for index, waveform in enumerate(waveforms):
        if not isinstance(waveform, Mapping):
            errors.append(f"modulated waveform {index} is malformed")
            continue
        case_id = waveform.get("case_id", index)
        cleanup = waveform.get("dma_cleanup")
        if not isinstance(cleanup, Mapping):
            errors.append(f"modulated {case_id} cyclic-DMA cleanup is missing")
            continue
        if cleanup.get("buffer_closed") is not True:
            errors.append(f"modulated {case_id} cyclic-DMA buffer was not closed")
        if cleanup.get("buffer_release_method") not in (
            "explicit_close",
            "reference_release_gc",
        ):
            errors.append(f"modulated {case_id} cyclic-DMA release method is invalid")
        if cleanup.get("failures") != []:
            errors.append(f"modulated {case_id} cyclic-DMA cleanup has failures")
        errors.extend(
            f"modulated {case_id} cyclic-DMA {error}"
            for error in _cleanup_errors({"cleanup": cleanup.get("mute")})
        )
    return errors


def _modulated_iq_convention_errors(runs: Any) -> list[str]:
    if not isinstance(runs, list):
        return ["modulated runs are missing"]
    errors: list[str] = []
    conventions: set[str] = set()
    for index, run in enumerate(runs):
        if not isinstance(run, Mapping):
            errors.append(f"modulated run {index} is malformed")
            continue
        summary = run.get("summary")
        convention = (
            summary.get("iq_convention") if isinstance(summary, Mapping) else None
        )
        if convention not in ("direct", "conjugated"):
            errors.append(
                f"modulated {run.get('mode')}/{run.get('case_id')} IQ convention "
                "is invalid"
            )
        else:
            conventions.add(convention)
    if len(conventions) > 1:
        errors.append("modulated IQ convention changed inside one hardware campaign")
    return errors


def _modulated_gain_errors(runs: Any, expected: ModulatedHardwareOptions) -> list[str]:
    if not isinstance(runs, list):
        return ["modulated runs are missing"]
    errors: list[str] = []
    expected_effective_attenuation = (
        expected.physical_attenuation_db - expected.tx2_gain_db
    )
    for index, run in enumerate(runs):
        if not isinstance(run, Mapping):
            errors.append(f"modulated run {index} is malformed")
            continue
        context = f"modulated {run.get('mode')}/{run.get('case_id')}"
        if run.get("tx2_gain_requested_db") != expected.tx2_gain_db:
            errors.append(f"{context} requested TX2 gain differs from plan")
        if run.get("tx2_gain_readback_db") != expected.tx2_gain_db:
            errors.append(f"{context} TX2 gain readback differs from plan")
        if run.get("effective_attenuation_db") != expected_effective_attenuation:
            errors.append(f"{context} effective attenuation differs from plan")
    return errors


def _modulated_raw_iq_evidence(
    runs: Any,
    *,
    work_dir: Path,
    serial: str,
    capture_samples: int,
) -> tuple[list[str], dict[str, Any] | None]:
    """Verify the bounded desired/blocker diagnostic pair against durable bytes."""

    if not isinstance(runs, list):
        return ["modulated runs are missing"], None
    errors: list[str] = []
    expected_bytes = capture_samples * 8
    if expected_bytes > MAX_DIAGNOSTIC_IQ_ARTIFACT_BYTES:
        errors.append("planned raw-IQ artifact exceeds the 64 KiB bound")
    targets = (
        {
            "purpose": "desired_baseline",
            "case_id": "desired_only",
            "mode": MODE_MANUAL,
            "measurement_index": 0,
            "filename": "desired-only-manual-fixed-frame-0000-rx0-rx1.cs16le",
        },
        {
            "purpose": "first_blocker",
            "case_id": "blocker_00",
            "mode": MODE_MANUAL,
            "measurement_index": 0,
            "filename": "blocker-00-manual-fixed-frame-0000-rx0-rx1.cs16le",
        },
    )
    target_runs: dict[tuple[str, str], list[Mapping[str, Any]]] = {
        (target["case_id"], target["mode"]): [] for target in targets
    }
    candidates: list[tuple[str, str, int, Mapping[str, Any]]] = []
    for run in runs:
        if not isinstance(run, Mapping):
            continue
        key = (run.get("case_id"), run.get("mode"))
        if key in target_runs:
            target_runs[key].append(run)
        measurements = run.get("measurements")
        if not isinstance(measurements, list):
            continue
        for frame_index, frame in enumerate(measurements):
            if isinstance(frame, Mapping) and "raw_iq_provenance" in frame:
                candidates.append(
                    (
                        str(run.get("case_id")),
                        str(run.get("mode")),
                        frame_index,
                        frame,
                    )
                )

    expected_positions = {
        (target["case_id"], target["mode"], target["measurement_index"])
        for target in targets
    }
    observed_positions = {
        (case_id, mode, frame_index)
        for case_id, mode, frame_index, _frame in candidates
    }
    if len(candidates) != 2 or observed_positions != expected_positions:
        errors.append(
            "modulated report must contain exactly two raw-IQ provenance records "
            "on the planned desired/blocker manual frames"
        )

    evidence: dict[str, Any] = {}
    digests: list[str] = []
    expected_paths = {
        (Path(serial) / "diagnostic-iq" / str(target["filename"])).as_posix()
        for target in targets
    }
    root = work_dir.resolve()
    for target in targets:
        purpose = str(target["purpose"])
        key = (str(target["case_id"]), str(target["mode"]))
        matching_runs = target_runs[key]
        if len(matching_runs) != 1:
            errors.append(f"{purpose} raw-IQ target run is missing or duplicated")
            continue
        measurements = matching_runs[0].get("measurements")
        frame_index = int(target["measurement_index"])
        if not isinstance(measurements, list) or len(measurements) <= frame_index:
            errors.append(f"{purpose} raw-IQ target frame is missing")
            continue
        frame = measurements[frame_index]
        if not isinstance(frame, Mapping):
            errors.append(f"{purpose} raw-IQ target frame is malformed")
            continue
        provenance = frame.get("raw_iq_provenance")
        if not isinstance(provenance, Mapping):
            errors.append(f"{purpose} raw-IQ provenance is missing or malformed")
            continue

        if provenance.get("purpose") != purpose:
            errors.append(f"{purpose} raw-IQ purpose differs from plan")
        if provenance.get("case_id") != target["case_id"]:
            errors.append(f"{purpose} raw-IQ case linkage differs from plan")
        if provenance.get("mode") != target["mode"]:
            errors.append(f"{purpose} raw-IQ mode linkage differs from plan")
        if provenance.get("measurement_index") != frame_index:
            errors.append(f"{purpose} raw-IQ frame linkage differs from plan")

        expected_relative_path = (
            Path(serial) / "diagnostic-iq" / str(target["filename"])
        ).as_posix()
        if provenance.get("path") != expected_relative_path:
            errors.append(f"{purpose} raw-IQ artifact path differs from plan")
        byte_count = provenance.get("bytes")
        if type(byte_count) is not int or byte_count != expected_bytes:
            errors.append(f"{purpose} raw-IQ artifact byte count differs from plan")
        if type(byte_count) is int and byte_count > MAX_DIAGNOSTIC_IQ_ARTIFACT_BYTES:
            errors.append(f"{purpose} raw-IQ artifact exceeds the 64 KiB bound")
        digest = provenance.get("sha256")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            errors.append(f"{purpose} raw-IQ artifact SHA-256 is malformed")
        else:
            digests.append(digest)
        if provenance.get("encoding") != "signed-16-bit-little-endian":
            errors.append(f"{purpose} raw-IQ artifact encoding differs from plan")
        if provenance.get("channel_layout") != [
            "rx0_i",
            "rx0_q",
            "rx1_i",
            "rx1_q",
        ]:
            errors.append(f"{purpose} raw-IQ artifact channel layout differs from plan")
        if provenance.get("samples_per_channel") != capture_samples:
            errors.append(f"{purpose} raw-IQ artifact sample count differs from plan")
        if frame.get("sha256") != digest or frame.get("iq_bytes") != expected_bytes:
            errors.append(
                f"{purpose} raw-IQ provenance differs from its measurement frame"
            )

        path_value = provenance.get("path")
        if isinstance(path_value, str):
            candidate_path = work_dir / path_value
            artifact = candidate_path.resolve()
            if artifact != root and root not in artifact.parents:
                errors.append(
                    f"{purpose} raw-IQ artifact escapes the phase work directory"
                )
            elif candidate_path.is_symlink():
                errors.append(f"{purpose} raw-IQ artifact must not be a symlink")
            elif not artifact.is_file():
                errors.append(f"{purpose} raw-IQ artifact is missing")
            else:
                on_disk_bytes = artifact.stat().st_size
                if on_disk_bytes != expected_bytes:
                    errors.append(
                        f"{purpose} raw-IQ artifact on-disk byte count differs"
                    )
                elif on_disk_bytes > MAX_DIAGNOSTIC_IQ_ARTIFACT_BYTES:
                    errors.append(
                        f"{purpose} raw-IQ artifact exceeds the on-disk 64 KiB bound"
                    )
                else:
                    payload = artifact.read_bytes()
                    if (
                        isinstance(digest, str)
                        and hashlib.sha256(payload).hexdigest() != digest
                    ):
                        errors.append(
                            f"{purpose} raw-IQ artifact on-disk SHA-256 differs"
                        )
                temporary = artifact.with_suffix(artifact.suffix + ".tmp")
                if temporary.exists():
                    errors.append(
                        f"{purpose} raw-IQ atomic-write temporary file remains"
                    )
        evidence[purpose] = dict(provenance)

    if len(digests) == 2 and len(set(digests)) != 2:
        errors.append(
            "desired and blocker raw-IQ artifact SHA-256 values are not distinct"
        )

    diagnostic_dir = work_dir / serial / "diagnostic-iq"
    if diagnostic_dir.is_symlink():
        errors.append("raw-IQ diagnostic directory must not be a symlink")
    elif diagnostic_dir.is_dir():
        actual_paths = {
            path.relative_to(work_dir).as_posix()
            for path in diagnostic_dir.rglob("*")
            if path.is_file() or path.is_symlink()
        }
        if actual_paths != expected_paths:
            errors.append("raw-IQ diagnostic directory contents differ from plan")

    return errors, evidence if not errors else None


def _modulated_continuity_errors(runs: Any, capture_samples: int) -> list[str]:
    """Recompute tandem gap evidence from the persisted metadata counters."""

    if not isinstance(runs, list):
        return ["modulated runs are missing"]
    errors: list[str] = []
    uint32_modulus = 1 << 32

    def exact_integer(value: Any, *, minimum: int = 0) -> bool:
        return type(value) is int and value >= minimum

    for run_index, run in enumerate(runs):
        if not isinstance(run, Mapping) or run.get("mode") != MODE_TANDEM:
            continue
        context = f"modulated tandem run {run.get('case_id', run_index)}"
        settling = run.get("settling")
        trace = settling.get("trace") if isinstance(settling, Mapping) else None
        measurements = run.get("measurements")
        if not isinstance(trace, list) or not isinstance(measurements, list):
            errors.append(f"{context} lacks frame evidence")
            continue
        if not trace or not measurements:
            errors.append(f"{context} has empty frame evidence")
            continue
        if settling.get("frames") != len(trace):
            errors.append(f"{context} settling frame count is inconsistent")

        previous_metadata: Mapping[str, Any] | None = None
        cumulative_missing = 0
        cumulative_hidden = 0
        event_hole_count = 0
        last_event_sequence: int | None = None
        unrepresented_since_event = 0
        for frame_index, frame in enumerate((*trace, *measurements)):
            frame_context = f"{context} frame {frame_index}"
            if not isinstance(frame, Mapping):
                errors.append(f"{frame_context} is malformed")
                break
            metadata = frame.get("metadata")
            continuity = frame.get("continuity")
            if not isinstance(metadata, Mapping) or not isinstance(continuity, Mapping):
                errors.append(f"{frame_context} lacks metadata gap evidence")
                break
            buffer_sequence = metadata.get("buffer_sequence")
            sample_sequence = metadata.get("first_sample_sequence")
            samples_per_channel = metadata.get("samples_per_channel")
            transition_count = metadata.get("tandem_transition_count")
            events = metadata.get("gain_events")
            if (
                not exact_integer(buffer_sequence)
                or not exact_integer(sample_sequence)
                or samples_per_channel != capture_samples
                or not exact_integer(transition_count)
                or transition_count >= uint32_modulus
                or not isinstance(events, list)
            ):
                errors.append(f"{frame_context} metadata counters are malformed")
                break
            event_sequences: list[int] = []
            if any(
                not isinstance(event, Mapping)
                or not exact_integer(event.get("event_sequence"))
                or event["event_sequence"] >= uint32_modulus
                for event in events
            ):
                errors.append(f"{frame_context} event sequences are malformed")
                break
            event_sequences.extend(int(event["event_sequence"]) for event in events)
            visible = len(event_sequences)

            if previous_metadata is None:
                buffer_delta: int | None = None
                sample_delta: int | None = None
                transition_delta: int | None = None
                missing = 0
                hidden = 0
                initial_unrepresented = transition_count - visible
                if initial_unrepresented < 0:
                    errors.append(f"{frame_context} has more events than transitions")
                    break
            else:
                buffer_delta = buffer_sequence - int(
                    previous_metadata["buffer_sequence"]
                )
                sample_delta = sample_sequence - int(
                    previous_metadata["first_sample_sequence"]
                )
                if buffer_delta <= 0 or sample_delta != buffer_delta * capture_samples:
                    errors.append(f"{frame_context} frame counters disagree")
                    break
                transition_delta = (
                    transition_count - int(previous_metadata["tandem_transition_count"])
                ) % uint32_modulus
                if transition_delta >= uint32_modulus // 2:
                    errors.append(f"{frame_context} transition counter regressed")
                    break
                missing = buffer_delta - 1
                hidden = transition_delta - visible
                initial_unrepresented = 0
                if hidden < 0 or (missing == 0 and hidden != 0):
                    errors.append(f"{frame_context} hidden transitions are invalid")
                    break
                cumulative_missing += missing
                cumulative_hidden += hidden
                unrepresented_since_event += hidden

            expected_values: dict[str, int | None] = {
                "buffer_delta": buffer_delta,
                "sample_delta": sample_delta,
                "missing_frame_count": missing,
                "transition_count_delta": transition_delta,
                "visible_event_count": visible,
                "hidden_transition_count": hidden,
                "initial_unrepresented_transition_count": initial_unrepresented,
                "cumulative_missing_frame_count": cumulative_missing,
                "cumulative_hidden_transition_count": cumulative_hidden,
            }
            if any(
                (
                    continuity.get(name) is not None
                    if expected is None
                    else type(continuity.get(name)) is not int
                    or continuity.get(name) != expected
                )
                for name, expected in expected_values.items()
            ):
                errors.append(f"{frame_context} gap evidence differs from metadata")
                break

            event_error = False
            for event_sequence in event_sequences:
                if last_event_sequence is not None:
                    delta = (event_sequence - last_event_sequence) % uint32_modulus
                    if delta == 0 or delta >= uint32_modulus // 2:
                        event_error = True
                        break
                    hole = delta - 1
                    if hole != unrepresented_since_event:
                        event_error = True
                        break
                    if hole:
                        event_hole_count += 1
                unrepresented_since_event = 0
                last_event_sequence = event_sequence
            if event_error:
                errors.append(f"{frame_context} event holes do not reconcile")
                break
            if (
                type(continuity.get("cumulative_event_sequence_hole_count")) is not int
                or continuity.get("cumulative_event_sequence_hole_count")
                != event_hole_count
            ):
                errors.append(f"{frame_context} event-hole evidence is inconsistent")
                break
            previous_metadata = metadata
    return errors


def _transient_comparison_errors(modes: Any, comparison: Any) -> list[str]:
    """Reconstruct the shared summary without upgrading ordinal diagnostics."""

    if not isinstance(modes, list) or not isinstance(comparison, list):
        return ["transient comparison cannot be reconstructed"]
    if len(modes) != len(comparison):
        return ["transient comparison count differs from modes"]
    errors: list[str] = []
    quality_fields = (
        "worst_overshoot_db",
        "ringing_peak_to_peak_db",
        "minimum_post_tone_snr_db",
        "maximum_post_clipping_fraction",
        "maximum_phase_excursion_deg",
    )
    for index, (mode, reported) in enumerate(zip(modes, comparison, strict=True)):
        if not isinstance(mode, Mapping) or not isinstance(reported, Mapping):
            errors.append(f"transient comparison entry {index} is malformed")
            continue
        hardware = mode.get("mode") == MODE_TANDEM
        responses = mode.get("responses")
        try:
            summaries: dict[str, dict[str, Any]] = {}
            for direction in ("attack", "release"):
                response = responses[direction]
                summary = {
                    "timing_qualification": response["timing_qualification"],
                    "hardware_latency_qualified": hardware,
                    "transient_observation_scope": response[
                        "transient_observation_scope"
                    ],
                    **{field: response[field] for field in quality_fields},
                }
                if hardware:
                    summary.update(
                        {
                            field: response[field]
                            for field in (
                                "signal_settling_latency_lower_samples",
                                "signal_settling_latency_upper_samples",
                                "signal_settling_latency_lower_seconds",
                                "signal_settling_latency_upper_seconds",
                            )
                        }
                    )
                else:
                    summary.update(
                        {
                            "signal_settling_latency_lower_samples": None,
                            "signal_settling_latency_upper_samples": None,
                            "signal_settling_latency_lower_seconds": None,
                            "signal_settling_latency_upper_seconds": None,
                            "observed_returned_iq_settling_span_lower_axis_units": (
                                response[
                                    "observed_returned_iq_settling_span_lower_axis_units"
                                ]
                            ),
                            "observed_returned_iq_settling_span_upper_axis_units": (
                                response[
                                    "observed_returned_iq_settling_span_upper_axis_units"
                                ]
                            ),
                        }
                    )
                summaries[direction] = summary
            expected = {
                "mode": mode["mode"],
                "timing_basis": mode["timing_basis"],
                "attack": summaries["attack"],
                "release": summaries["release"],
                "gain_evidence": mode["gain_evidence"],
            }
        except (KeyError, TypeError) as error:
            errors.append(
                f"transient comparison entry {index} cannot be reconstructed: {error}"
            )
        else:
            if reported != expected:
                errors.append(
                    f"transient comparison entry {index} differs from recomputation"
                )
    return errors


def _transient_mode_boundary_errors(
    modes: Any, quality: TandemQualityOptions
) -> list[str]:
    """Bind the safe controller and RX state on both sides of every mode."""

    if not isinstance(modes, list):
        return ["transient mode boundary evidence is missing"]
    errors: list[str] = []
    for index, mode in enumerate(modes):
        if not isinstance(mode, Mapping):
            errors.append(f"transient mode {index} boundary evidence is malformed")
            continue
        context = f"transient {mode.get('mode', index)}"
        for status_name in ("tandem_status_before", "tandem_status_after"):
            status = mode.get(status_name)
            if (
                not isinstance(status, Mapping)
                or type(status.get("state")) is not int
                or status.get("state") != int(TandemState.IDLE)
                or type(status.get("fault_flags")) is not int
                or status.get("fault_flags") != 0
                or type(status.get("fifo_level")) is not int
                or status.get("fifo_level") != 0
            ):
                errors.append(f"{context} {status_name} is not safely IDLE")
        final_state = mode.get("final_rx_state")
        gains = (
            final_state.get("gains_db") if isinstance(final_state, Mapping) else None
        )
        if (
            not isinstance(final_state, Mapping)
            or final_state.get("modes") != ["manual", "manual"]
            or not isinstance(gains, list)
            or len(gains) != 2
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or abs(float(value) - quality.manual_gain_db) > 0.1
                for value in gains
            )
        ):
            errors.append(f"{context} final RX state is not restored to manual")
    return errors


def _transient_ordinary_errors(
    modes: Any,
    capture: TransientCaptureOptions,
    quality: TandemQualityOptions,
) -> list[str]:
    """Recompute returned-IQ ordinal evidence for every ordinary mode."""

    if not isinstance(modes, list):
        return ["transient ordinary modes are missing"]
    ordinary_basis = "ordinary_returned_iq_ordinal_axis"
    expected_modes = [mode for mode in TRANSIENT_MODES if mode != MODE_TANDEM]
    ordinary = [
        mode
        for mode in modes
        if isinstance(mode, Mapping) and mode.get("mode") != MODE_TANDEM
    ]
    if [mode.get("mode") for mode in ordinary] != expected_modes:
        return ["transient ordinary mode coverage differs from policy"]
    errors: list[str] = []

    def exact_integer(value: Any, *, minimum: int = 0) -> bool:
        return type(value) is int and value >= minimum

    def finite_number(value: Any) -> bool:
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
        )

    def command_from_report(record: Mapping[str, Any]) -> StimulusCommand:
        return StimulusCommand(
            command_id=record["command_id"],
            requested_level_db=record["requested_level_db"],
            applied_level_db=record["applied_level_db"],
            host_before_ns=record["host_before_ns"],
            host_after_ns=record["host_after_ns"],
            sample_sequence_before=record["sample_sequence_before"],
            sample_sequence_after=record["sample_sequence_after"],
        )

    def ordinal_response(value: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(value)
        lower = result.pop("signal_settling_latency_lower_samples")
        upper = result.pop("signal_settling_latency_upper_samples")
        result.pop("signal_settling_latency_lower_seconds")
        result.pop("signal_settling_latency_upper_seconds")
        result.update(
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
        return result

    for mode in ordinary:
        mode_name = str(mode.get("mode"))
        context = f"transient {mode_name}"
        expected_iio_mode = (
            "manual" if mode_name == MODE_MANUAL else mode_name.removeprefix("native_")
        )
        if mode.get("timing_basis") != ordinary_basis:
            errors.append(f"{context} timing basis is not returned-IQ ordinal")
        if mode.get("metadata_abi") is not None:
            errors.append(f"{context} unexpectedly reports a metadata ABI")
        preconditioning = mode.get("preconditioning")
        trace = (
            preconditioning.get("trace")
            if isinstance(preconditioning, Mapping)
            else None
        )
        baseline = mode.get("baseline_frames")
        attack = mode.get("attack_frames")
        release = mode.get("release_frames")
        if not all(
            isinstance(items, list) and items
            for items in (trace, baseline, attack, release)
        ):
            errors.append(f"{context} frame evidence is missing or empty")
            continue
        assert isinstance(trace, list)
        assert isinstance(baseline, list)
        assert isinstance(attack, list)
        assert isinstance(release, list)
        if any(
            not isinstance(frame, Mapping)
            for frame in (*trace, *baseline, *attack, *release)
        ):
            errors.append(f"{context} frame evidence is malformed")
            continue
        if (
            not isinstance(preconditioning, Mapping)
            or preconditioning.get("frame_count") != len(trace)
            or not max(2, capture.precondition_stable_frames)
            <= len(trace)
            <= capture.max_precondition_frames
        ):
            errors.append(f"{context} precondition frame count is inconsistent")
        expected_baseline = trace[-capture.baseline_frames :]
        if baseline != expected_baseline:
            errors.append(f"{context} baseline is not the retained trace tail")
        if isinstance(preconditioning, Mapping) and preconditioning.get(
            "retained_baseline_frame_indices"
        ) != [frame.get("frame_index") for frame in expected_baseline]:
            errors.append(f"{context} retained baseline indices are inconsistent")
        if len(attack) != capture.response_frames or len(release) != (
            capture.response_frames
        ):
            errors.append(f"{context} response frame count differs from policy")
        if mode.get("acquisition") != {
            "threaded": False,
            "kernel_buffers": 1,
            "queue_capacity_frames": 0,
            "response_tail_frames": 0,
        }:
            errors.append(f"{context} acquisition policy is inconsistent")

        frames_by_section = (
            ("precondition", trace),
            ("attack", attack),
            ("release", release),
        )
        frame_number = 0
        previous_refill_ns: int | None = None
        frame_records_valid = True
        for section, frames in frames_by_section:
            for section_index, frame in enumerate(frames):
                assert isinstance(frame, Mapping)
                frame_context = f"{context} {section} frame {section_index}"
                expected_start = frame_number * capture.frame_samples
                expected_gap_context = (
                    "precondition_observation"
                    if section == "precondition"
                    else (
                        "command_bracket"
                        if section_index == 0
                        else "continuous_response"
                    )
                )
                if (
                    frame.get("frame_index") != frame_number
                    or frame.get("iq_bytes") != capture.frame_samples * 8
                    or not exact_integer(frame.get("refill_monotonic_ns"))
                    or frame.get("timing_basis") != ordinary_basis
                    or frame.get("first_sample_sequence") != expected_start
                    or frame.get("sample_end_exclusive")
                    != expected_start + capture.frame_samples
                    or frame.get("sample_gap_before") is not None
                    or frame.get("physical_sample_continuity_proven") is not False
                    or frame.get("gap_context") != expected_gap_context
                    or frame.get("command_boundary_gap_allowed") is not False
                    or "metadata" in frame
                    or "continuity" in frame
                    or not isinstance(frame.get("sha256"), str)
                    or re.fullmatch(r"[0-9a-f]{64}", frame["sha256"]) is None
                ):
                    errors.append(f"{frame_context} ordinal ledger is inconsistent")
                    frame_records_valid = False
                refill_ns = frame.get("refill_monotonic_ns")
                if (
                    exact_integer(refill_ns)
                    and previous_refill_ns is not None
                    and refill_ns < previous_refill_ns
                ):
                    errors.append(f"{frame_context} refill ledger regressed")
                    frame_records_valid = False
                if exact_integer(refill_ns):
                    previous_refill_ns = refill_ns
                for state_name in ("rx_state_before", "rx_state_after"):
                    state = frame.get(state_name)
                    if (
                        not isinstance(state, Mapping)
                        or state.get("modes") != [expected_iio_mode, expected_iio_mode]
                        or not isinstance(state.get("gains_db"), list)
                        or len(state["gains_db"]) != 2
                        or any(not finite_number(value) for value in state["gains_db"])
                    ):
                        errors.append(f"{frame_context} RX state is inconsistent")
                        frame_records_valid = False
                analysis = frame.get("analysis")
                windows = (
                    analysis.get("windows") if isinstance(analysis, Mapping) else None
                )
                expected_windows = capture.frame_samples // capture.window_samples
                if (
                    not isinstance(analysis, Mapping)
                    or analysis.get("first_sample_sequence") != expected_start
                    or analysis.get("samples_per_channel") != capture.frame_samples
                    or analysis.get("sample_rate_hz") != quality.sample_rate_hz
                    or analysis.get("expected_tone_hz") != quality.tone_hz
                    or not finite_number(analysis.get("selected_tone_hz"))
                    or abs(float(analysis.get("selected_tone_hz", 0)))
                    != abs(quality.tone_hz)
                    or analysis.get("window_samples") != capture.window_samples
                    or analysis.get("stride_samples") != capture.window_samples
                    or analysis.get("window_count") != expected_windows
                    or analysis.get("uncovered_tail_samples") != 0
                    or not isinstance(windows, list)
                    or len(windows) != expected_windows
                ):
                    errors.append(f"{frame_context} analysis ledger is inconsistent")
                    frame_records_valid = False
                else:
                    window_quality: list[bool] = []
                    for window_index, window in enumerate(windows):
                        if not isinstance(window, Mapping):
                            errors.append(
                                f"{frame_context} analysis window is malformed"
                            )
                            frame_records_valid = False
                            break
                        snr = window.get("tone_snr_db")
                        clipping = window.get("clipping_fraction")
                        phase_std = window.get("within_window_phase_std_deg")
                        if (
                            not isinstance(snr, list)
                            or len(snr) != 2
                            or any(not finite_number(value) for value in snr)
                            or not isinstance(clipping, list)
                            or len(clipping) != 2
                            or any(not finite_number(value) for value in clipping)
                            or any(not 0 <= float(value) <= 1 for value in clipping)
                            or not finite_number(phase_std)
                            or float(phase_std) < 0
                        ):
                            errors.append(
                                f"{frame_context} analysis quality values are malformed"
                            )
                            frame_records_valid = False
                            break
                        reasons: list[str] = []
                        for channel in (0, 1):
                            if snr[channel] < quality.thresholds.min_tone_snr_db:
                                reasons.append(f"rx{channel}_tone_snr_low")
                            if (
                                clipping[channel]
                                > quality.thresholds.max_clipping_fraction
                            ):
                                reasons.append(f"rx{channel}_clipping")
                        if phase_std > quality.thresholds.max_phase_std_deg:
                            reasons.append("within_window_phase_unstable")
                        valid = not reasons
                        window_quality.append(valid)
                        if (
                            window.get("window_index") != window_index
                            or window.get("offset_start")
                            != window_index * capture.window_samples
                            or window.get("offset_end_exclusive")
                            != (window_index + 1) * capture.window_samples
                            or window.get("sample_start")
                            != expected_start + window_index * capture.window_samples
                            or window.get("sample_end_exclusive")
                            != expected_start
                            + (window_index + 1) * capture.window_samples
                            or window.get("quality_reasons") != reasons
                            or window.get("quality_valid") is not valid
                        ):
                            errors.append(
                                f"{frame_context} analysis window ledger is inconsistent"
                            )
                            frame_records_valid = False
                    if analysis.get("quality_valid") is not all(window_quality):
                        errors.append(
                            f"{frame_context} analysis quality ledger is inconsistent"
                        )
                        frame_records_valid = False
                frame_number += 1

        if frame_records_valid:
            tolerance = 0.1 if mode_name == MODE_MANUAL else 1.0
            stable_run: list[Mapping[str, Any]] = []
            for trace_index, frame in enumerate(trace):
                assert isinstance(frame, Mapping)
                candidate = [*stable_run, frame]
                stable = True
                for channel in (0, 1):
                    gains = [
                        float(item[state]["gains_db"][channel])
                        for item in candidate
                        for state in ("rx_state_before", "rx_state_after")
                    ]
                    stable &= max(gains) - min(gains) <= tolerance
                stable_run = candidate if stable else [frame]
                if frame.get("precondition_stable_run") != len(stable_run):
                    errors.append(
                        f"{context} precondition stability ledger is inconsistent"
                    )
                    break
                if (
                    trace_index < len(trace) - 1
                    and len(stable_run) >= capture.precondition_stable_frames
                ):
                    errors.append(f"{context} precondition continued after stability")
                    break
            if len(stable_run) < capture.precondition_stable_frames:
                errors.append(f"{context} precondition never established stability")

        commands = mode.get("commands")
        anchor = mode.get("conditioning_anchor")
        if (
            not isinstance(commands, list)
            or len(commands) != 3
            or any(not isinstance(command, Mapping) for command in commands)
            or not isinstance(anchor, Mapping)
        ):
            errors.append(f"{context} commands are missing or malformed")
            continue
        assert all(isinstance(command, Mapping) for command in commands)
        initial, attack_command_record, release_command_record = commands
        command_records_valid = True
        expected_command_ids = ("weak_initial", "strong_attack", "weak_release")
        if tuple(command.get("command_id") for command in commands) != (
            expected_command_ids
        ):
            errors.append(f"{context} command order differs from policy")
            command_records_valid = False
        expected_levels = (
            quality.weakest_tx_gain_db,
            quality.strongest_tx_gain_db,
            quality.weakest_tx_gain_db,
        )
        for command, expected_level in zip(commands, expected_levels, strict=True):
            before = command.get("host_before_ns")
            after = command.get("host_after_ns")
            applied = command.get("applied_level_db")
            effective = (
                quality.physical_attenuation_db - float(applied)
                if finite_number(applied)
                else None
            )
            if (
                not exact_integer(before)
                or not exact_integer(after)
                or not before <= after
                or command.get("host_jitter_ns") != after - before
                or after - before > capture.max_host_jitter_ns
                or not finite_number(command.get("requested_level_db"))
                or float(command["requested_level_db"]) != expected_level
                or not finite_number(applied)
                or abs(float(applied) - expected_level) > capture.readback_tolerance_db
                or command.get("effective_attenuation_db") != effective
            ):
                errors.append(f"{context} command write ledger is inconsistent")
                command_records_valid = False
            if effective is not None and effective < 30.0:
                errors.append(
                    f"{context} command violates the 30 dB effective-attenuation "
                    "boundary"
                )
        attack_lower = baseline[-1].get("sample_end_exclusive")
        attack_upper = attack[0].get("sample_end_exclusive")
        release_lower = attack[-1].get("sample_end_exclusive")
        release_upper = release[0].get("sample_end_exclusive")
        command_bounds = (
            (attack_command_record, attack_lower, attack_upper),
            (release_command_record, release_lower, release_upper),
        )
        bounds_valid = all(
            exact_integer(lower) and exact_integer(upper, minimum=1)
            for _command, lower, upper in command_bounds
        )
        if not bounds_valid or (
            initial.get("sample_sequence_before") is not None
            or initial.get("sample_sequence_after") is not None
            or initial.get("sample_uncertainty") is not None
            or initial.get("timing_role") != "pre_session_conditioning_write"
            or initial.get("sample_timing_basis") is not None
            or initial.get("sample_anchor_policy")
            != "unbounded in sample time; the write predates the open capture session"
            or any(
                command.get("sample_sequence_before") != lower
                or command.get("sample_sequence_after") != upper
                or command.get("sample_uncertainty") != upper - lower
                or not 0 < upper - lower <= capture.max_sample_uncertainty
                or command.get("timing_role")
                != "host_write_positioned_on_returned_iq_ordinal_axis"
                or command.get("sample_timing_basis") != ordinary_basis
                or command.get("sample_anchor_policy")
                != "last returned pre-command IQ ordinal through end of first "
                "returned post-command frame; unobserved hardware intervals excluded"
                or "sample_counter_bracket" in command
                for command, lower, upper in command_bounds
            )
        ):
            errors.append(f"{context} command ordinal bracket is inconsistent")
            command_records_valid = False
        anchor_lower = baseline[0].get("first_sample_sequence")
        anchor_upper = baseline[-1].get("sample_end_exclusive")
        if (
            not exact_integer(anchor_lower)
            or not exact_integer(anchor_upper, minimum=1)
            or anchor.get("command_id") != "weak_conditioning_anchor"
            or anchor.get("requested_level_db") != initial.get("requested_level_db")
            or anchor.get("applied_level_db") != initial.get("applied_level_db")
            or anchor.get("host_before_ns") != initial.get("host_before_ns")
            or anchor.get("host_after_ns") != initial.get("host_after_ns")
            or anchor.get("host_jitter_ns") != initial.get("host_jitter_ns")
            or anchor.get("sample_sequence_before") != anchor_lower
            or anchor.get("sample_sequence_after") != anchor_upper
            or anchor.get("sample_uncertainty") != anchor_upper - anchor_lower
            or anchor.get("timing_role") != "observed_stable_conditioning_interval"
            or anchor.get("sample_timing_basis") != ordinary_basis
            or anchor.get("sample_anchor_policy")
            != "retained stable baseline interval; not the initial write time"
        ):
            errors.append(f"{context} conditioning anchor is inconsistent")
            command_records_valid = False

        if not frame_records_valid or not command_records_valid:
            continue
        for frames, command in (
            (baseline, None),
            (attack, attack_command_record),
            (release, release_command_record),
        ):
            for frame in frames:
                for window in frame["analysis"]["windows"]:
                    lower = (
                        command.get("sample_sequence_before")
                        if command is not None
                        else None
                    )
                    upper = (
                        command.get("sample_sequence_after")
                        if command is not None
                        else None
                    )
                    intersects = bool(
                        command is not None
                        and type(lower) is int
                        and type(upper) is int
                        and window["sample_start"] < upper
                        and window["sample_end_exclusive"] > lower
                    )
                    if not intersects and window.get("quality_valid") is not True:
                        errors.append(
                            f"{context} has a quality-invalid returned-IQ window "
                            "outside a command interval"
                        )
                        break

        responses = mode.get("responses")
        try:
            anchor_command = command_from_report(anchor)
            attack_command = command_from_report(attack_command_record)
            release_command = command_from_report(release_command_record)
            response_kwargs = {
                "sample_rate_hz": quality.sample_rate_hz,
                "baseline_windows": capture.baseline_windows,
                "steady_windows": capture.steady_windows,
                "stable_windows": capture.stable_windows,
                "settling_tolerance_db": capture.settling_tolerance_db,
                "ringing_deadband_db": capture.ringing_deadband_db,
                "max_host_jitter_ns": capture.max_host_jitter_ns,
                "max_sample_uncertainty": capture.max_sample_uncertainty,
            }
            attack_windows = [
                window
                for frame in (*baseline, *attack)
                for window in frame["analysis"]["windows"]
            ]
            release_windows = [
                window
                for frame in (*attack, *release)
                for window in frame["analysis"]["windows"]
            ]
            recomputed_responses = {
                "attack": ordinal_response(
                    calculate_transient_response(
                        attack_windows,
                        previous_command=anchor_command,
                        command=attack_command,
                        **response_kwargs,
                    )
                ),
                "release": ordinal_response(
                    calculate_transient_response(
                        release_windows,
                        previous_command=attack_command,
                        command=release_command,
                        **response_kwargs,
                    )
                ),
            }
        except (KeyError, TypeError, ValueError) as error:
            errors.append(f"{context} responses cannot be recomputed: {error}")
        else:
            if responses != _json_safe(recomputed_responses):
                errors.append(f"{context} responses differ from recomputation")

        gain = mode.get("gain_evidence")
        if mode_name == MODE_MANUAL:
            gain_values: list[list[float]] = [[], []]
            for frame in (*baseline, *attack, *release):
                for state_name in ("rx_state_before", "rx_state_after"):
                    for channel in (0, 1):
                        gain_values[channel].append(
                            float(frame[state_name]["gains_db"][channel])
                        )
            expected_gain = {
                "evidence_valid": True,
                "timing_qualification": "not_applicable_fixed_gain",
                "hardware_latency_qualified": False,
                "expected_gain_db": quality.manual_gain_db,
                "gain_span_db": [max(values) - min(values) for values in gain_values],
                "maximum_readback_error_db": [
                    max(abs(value - quality.manual_gain_db) for value in values)
                    for values in gain_values
                ],
            }
            if any(value > 0.1 for value in expected_gain["gain_span_db"]) or any(
                value > 0.1 for value in expected_gain["maximum_readback_error_db"]
            ):
                errors.append(f"{context} manual RX gain moved outside policy")
        else:

            def gain_at_end(frames: Sequence[Mapping[str, Any]]) -> tuple[float, float]:
                selected = frames[-min(3, len(frames)) :]
                return tuple(
                    float(
                        statistics.median(
                            float(frame["rx_state_after"]["gains_db"][channel])
                            for frame in selected
                        )
                    )
                    for channel in (0, 1)
                )  # type: ignore[return-value]

            weak = gain_at_end(baseline)
            strong = gain_at_end(attack)
            returned = gain_at_end(release)

            def gain_bounds(
                frames: Sequence[Mapping[str, Any]],
                *,
                command: StimulusCommand,
                reference: tuple[float, float],
                sign: int,
            ) -> list[dict[str, Any]]:
                assert command.sample_sequence_before is not None
                assert command.sample_sequence_after is not None
                results = []
                for channel in (0, 1):
                    found = None
                    for frame in frames:
                        before_gain = float(
                            frame["rx_state_before"]["gains_db"][channel]
                        )
                        after_gain = float(frame["rx_state_after"]["gains_db"][channel])
                        evidence = None
                        observed = 0.0
                        if sign * (before_gain - reference[channel]) >= (
                            capture.minimum_native_gain_change_db
                        ):
                            evidence = "pre_refill_readback"
                            observed = before_gain
                        elif sign * (after_gain - reference[channel]) >= (
                            capture.minimum_native_gain_change_db
                        ):
                            evidence = "post_refill_readback"
                            observed = after_gain
                        if evidence is not None:
                            found = {
                                "rx_channel": channel,
                                "evidence": evidence,
                                "observed_gain_db": observed,
                                "returned_iq_observation_span_lower_axis_units": max(
                                    0,
                                    int(frame["first_sample_sequence"])
                                    - command.sample_sequence_after,
                                ),
                                "returned_iq_observation_span_upper_axis_units": max(
                                    0,
                                    int(frame["sample_end_exclusive"])
                                    - command.sample_sequence_before,
                                ),
                                "hardware_latency_qualified": False,
                            }
                            break
                    if found is None:
                        raise ValueError("native gain change is not represented")
                    results.append(found)
                return results

            try:
                attack_bounds = gain_bounds(
                    attack,
                    command=attack_command,
                    reference=weak,
                    sign=-1,
                )
                release_bounds = gain_bounds(
                    release,
                    command=release_command,
                    reference=strong,
                    sign=1,
                )
            except ValueError as error:
                errors.append(f"{context} gain evidence cannot be recomputed: {error}")
                continue
            expected_gain = {
                "evidence_valid": True,
                "timing_qualification": "returned_iq_observation_only",
                "hardware_latency_qualified": False,
                "minimum_required_change_db": capture.minimum_native_gain_change_db,
                "weak_gain_db": list(weak),
                "strong_gain_db": list(strong),
                "returned_weak_gain_db": list(returned),
                "attack_gain_change_db": [
                    strong[index] - weak[index] for index in (0, 1)
                ],
                "release_gain_change_db": [
                    returned[index] - strong[index] for index in (0, 1)
                ],
                "attack_returned_iq_observation_bounds": attack_bounds,
                "release_returned_iq_observation_bounds": release_bounds,
            }
        if gain != expected_gain:
            errors.append(f"{context} gain evidence differs from recomputation")
    return errors


def _transient_continuity_errors(
    modes: Any, capture: TransientCaptureOptions, quality: TandemQualityOptions
) -> list[str]:
    """Recompute transient gap, event, endpoint, and command-bracket evidence."""

    if not isinstance(modes, list):
        return ["transient modes are missing"]
    tandem_modes = [
        mode
        for mode in modes
        if isinstance(mode, Mapping) and mode.get("mode") == MODE_TANDEM
    ]
    if len(tandem_modes) != 1:
        return ["transient tandem mode is missing or duplicated"]
    mode = tandem_modes[0]
    preconditioning = mode.get("preconditioning")
    trace = (
        preconditioning.get("trace") if isinstance(preconditioning, Mapping) else None
    )
    baseline = mode.get("baseline_frames")
    attack = mode.get("attack_frames")
    release = mode.get("release_frames")
    if not all(
        isinstance(items, list) and items
        for items in (trace, baseline, attack, release)
    ):
        return ["transient tandem frame evidence is missing or empty"]
    assert isinstance(trace, list)
    assert isinstance(baseline, list)
    assert isinstance(attack, list)
    assert isinstance(release, list)
    errors: list[str] = []

    def exact_integer(value: Any, *, minimum: int = 0) -> bool:
        return type(value) is int and value >= minimum

    def finite_number(value: Any) -> bool:
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
        )

    if mode.get("timing_basis") != "hardware_sample_counter":
        errors.append("transient tandem mode timing basis is inconsistent")
    if mode.get("metadata_abi") != 2:
        errors.append("transient tandem metadata ABI is inconsistent")
    if any(not isinstance(frame, Mapping) for frame in (*trace, *baseline)):
        return ["transient tandem precondition frame evidence is malformed"]
    if (
        preconditioning.get("frame_count") != len(trace)
        or not capture.precondition_stable_frames + 1
        <= len(trace)
        <= capture.max_precondition_frames
    ):
        errors.append("transient tandem precondition frame count is inconsistent")
    expected_baseline = trace[-capture.baseline_frames :]
    if baseline != expected_baseline:
        errors.append(
            "transient tandem baseline is not the exact retained preconditioning tail"
        )
    expected_baseline_indices = [
        frame.get("frame_index") if isinstance(frame, Mapping) else None
        for frame in expected_baseline
    ]
    if preconditioning.get("retained_baseline_frame_indices") != (
        expected_baseline_indices
    ):
        errors.append(
            "transient tandem retained baseline indices differ from preconditioning"
        )

    commands = mode.get("commands")
    conditioning_anchor = mode.get("conditioning_anchor")
    if (
        not isinstance(commands, list)
        or len(commands) != 3
        or any(not isinstance(command, Mapping) for command in commands)
        or not isinstance(conditioning_anchor, Mapping)
    ):
        errors.append("transient tandem commands or conditioning anchor are missing")
        return errors
    if [command.get("command_id") for command in commands] != [
        "weak_initial",
        "strong_attack",
        "weak_release",
    ]:
        errors.append("transient tandem command order differs from policy")
    initial_command = commands[0]
    by_id = {
        command.get("command_id"): command
        for command in commands
        if isinstance(command, Mapping)
    }
    attack_command = by_id.get("strong_attack")
    release_command = by_id.get("weak_release")
    if not isinstance(attack_command, Mapping) or not isinstance(
        release_command, Mapping
    ):
        errors.append("transient tandem attack/release commands are missing")
        return errors
    for command, expected_level in zip(
        commands,
        (
            quality.weakest_tx_gain_db,
            quality.strongest_tx_gain_db,
            quality.weakest_tx_gain_db,
        ),
        strict=True,
    ):
        before = command.get("host_before_ns")
        after = command.get("host_after_ns")
        applied = command.get("applied_level_db")
        effective = (
            quality.physical_attenuation_db - float(applied)
            if finite_number(applied)
            else None
        )
        if (
            not exact_integer(before)
            or not exact_integer(after)
            or not before <= after
            or command.get("host_jitter_ns") != after - before
            or after - before > capture.max_host_jitter_ns
            or not finite_number(command.get("requested_level_db"))
            or float(command["requested_level_db"]) != expected_level
            or not finite_number(applied)
            or abs(float(applied) - expected_level) > capture.readback_tolerance_db
            or command.get("effective_attenuation_db") != effective
        ):
            errors.append("transient tandem command write ledger is inconsistent")
        if effective is not None and effective < 30.0:
            errors.append(
                "transient tandem command violates the 30 dB "
                "effective-attenuation boundary"
            )
    if (
        initial_command.get("sample_sequence_before") is not None
        or initial_command.get("sample_sequence_after") is not None
        or initial_command.get("sample_uncertainty") is not None
        or initial_command.get("timing_role") != "pre_session_conditioning_write"
        or initial_command.get("sample_timing_basis") is not None
        or initial_command.get("sample_anchor_policy")
        != "unbounded in sample time; the write predates the open capture session"
        or conditioning_anchor.get("requested_level_db")
        != initial_command.get("requested_level_db")
        or conditioning_anchor.get("applied_level_db")
        != initial_command.get("applied_level_db")
        or conditioning_anchor.get("host_before_ns")
        != initial_command.get("host_before_ns")
        or conditioning_anchor.get("host_after_ns")
        != initial_command.get("host_after_ns")
        or conditioning_anchor.get("host_jitter_ns")
        != initial_command.get("host_jitter_ns")
        or conditioning_anchor.get("timing_role")
        != "observed_stable_conditioning_interval"
        or conditioning_anchor.get("sample_timing_basis") != "hardware_sample_counter"
        or conditioning_anchor.get("sample_anchor_policy")
        != "retained stable baseline interval; not the initial write time"
    ):
        errors.append("transient tandem initial command or anchor is inconsistent")

    response_tail = int(
        transient_evidence_policy(capture)["tandem_response_tail_frames"]
    )
    expected_response_frames = capture.response_frames + response_tail
    if len(attack) != expected_response_frames or len(release) != (
        expected_response_frames
    ):
        errors.append("transient tandem response capture count differs from policy")

    acquisition = mode.get("acquisition")
    queue_frames = int(
        transient_evidence_policy(capture)["tandem_capture_queue_frames"]
    )
    consumed_frames = len(trace) + len(attack) + len(release)
    if (
        not isinstance(acquisition, Mapping)
        or acquisition.get("threaded") is not True
        or acquisition.get("kernel_buffers") != 1
        or acquisition.get("queue_capacity_frames") != queue_frames
        or acquisition.get("response_tail_frames") != response_tail
        or acquisition.get("buffer_cancelled_before_join") is not True
        or acquisition.get("consumed_frames") != consumed_frames
        or type(acquisition.get("produced_frames")) is not int
        or acquisition.get("produced_frames") < consumed_frames
        or acquisition.get("produced_frames") > consumed_frames + queue_frames + 1
        or acquisition.get("discarded_tail_frames")
        != acquisition.get("produced_frames") - consumed_frames
    ):
        errors.append("transient tandem acquisition ledger is inconsistent")

    sections = (
        ("precondition", trace),
        ("attack", attack),
        ("release", release),
    )
    previous_metadata: Mapping[str, Any] | None = None
    previous_event: Mapping[str, Any] | None = None
    stream_id: int | None = None
    ownership_epoch: int | None = None
    gain_index_range: tuple[int, int] | None = None
    threshold_provenance: int | None = None
    previous_refill_ns: int | None = None
    cumulative_missing = 0
    frame_number = 0
    visible_response_events: list[Mapping[str, Any]] = []
    uint32_modulus = 1 << 32
    expected_gain_table_id = int(
        expected_tandem_gain_table(quality.center_frequency_hz)
    )
    required_metadata_flags = (
        FLAG_SAMPLE_SEQUENCE_VALID
        | FLAG_HARDWARE_SAMPLE_COUNTER_VALID
        | FLAG_TANDEM_METADATA_VALID
    )
    tandem_stable_run = 0

    for section, frames in sections:
        for section_index, frame in enumerate(frames):
            context = f"transient tandem {section} frame {section_index}"
            if not isinstance(frame, Mapping):
                errors.append(f"{context} is malformed")
                return errors
            if section == "precondition":
                expected_gap_context = "precondition_observation"
            else:
                section_command = (
                    attack_command if section == "attack" else release_command
                )
                start = frame.get("first_sample_sequence")
                end = frame.get("sample_end_exclusive")
                lower = section_command.get("sample_sequence_before")
                upper = section_command.get("sample_sequence_after")
                if not all(type(value) is int for value in (start, end, lower, upper)):
                    errors.append(f"{context} cannot be classified in sample time")
                    return errors
                if end <= lower:
                    expected_gap_context = "precommand_prefetch"
                elif start < upper:
                    expected_gap_context = "command_bracket"
                else:
                    expected_gap_context = "continuous_response"
            if frame.get("frame_index") != frame_number:
                errors.append(f"{context} frame index is not contiguous")
            frame_number += 1
            refill_ns = frame.get("refill_monotonic_ns")
            if (
                frame.get("iq_bytes") != capture.frame_samples * 8
                or not exact_integer(refill_ns)
                or (
                    previous_refill_ns is not None
                    and exact_integer(refill_ns)
                    and refill_ns < previous_refill_ns
                )
                or frame.get("timing_basis") != "hardware_sample_counter"
                or frame.get("physical_sample_continuity_proven") is not True
                or not isinstance(frame.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", frame["sha256"]) is None
            ):
                errors.append(f"{context} capture ledger is inconsistent")
            if exact_integer(refill_ns):
                previous_refill_ns = refill_ns
            if frame.get("gap_context") != expected_gap_context:
                errors.append(f"{context} gap context differs from its phase")
            if frame.get("command_boundary_gap_allowed") is not False:
                errors.append(f"{context} command-boundary policy is inconsistent")

            analysis = frame.get("analysis")
            windows = analysis.get("windows") if isinstance(analysis, Mapping) else None
            expected_window_count = capture.frame_samples // capture.window_samples
            first = frame.get("first_sample_sequence")
            if (
                not isinstance(analysis, Mapping)
                or analysis.get("first_sample_sequence") != first
                or analysis.get("samples_per_channel") != capture.frame_samples
                or analysis.get("sample_rate_hz") != quality.sample_rate_hz
                or analysis.get("expected_tone_hz") != quality.tone_hz
                or not finite_number(analysis.get("selected_tone_hz"))
                or abs(float(analysis.get("selected_tone_hz", 0)))
                != abs(quality.tone_hz)
                or analysis.get("window_samples") != capture.window_samples
                or analysis.get("stride_samples") != capture.window_samples
                or analysis.get("window_count") != expected_window_count
                or analysis.get("uncovered_tail_samples") != 0
                or not isinstance(windows, list)
                or len(windows) != expected_window_count
            ):
                errors.append(f"{context} analysis ledger is inconsistent")
                return errors
            window_quality: list[bool] = []
            for window_index, window in enumerate(windows):
                if not isinstance(window, Mapping) or not exact_integer(first):
                    errors.append(f"{context} analysis window is malformed")
                    return errors
                expected_start = first + window_index * capture.window_samples
                reasons: list[str] = []
                snr = window.get("tone_snr_db")
                clipping = window.get("clipping_fraction")
                phase_std = window.get("within_window_phase_std_deg")
                if (
                    not isinstance(snr, list)
                    or len(snr) != 2
                    or any(not finite_number(value) for value in snr)
                    or not isinstance(clipping, list)
                    or len(clipping) != 2
                    or any(not finite_number(value) for value in clipping)
                    or any(not 0 <= float(value) <= 1 for value in clipping)
                    or not finite_number(phase_std)
                    or float(phase_std) < 0
                ):
                    errors.append(f"{context} analysis quality values are malformed")
                    return errors
                for channel in (0, 1):
                    if snr[channel] < quality.thresholds.min_tone_snr_db:
                        reasons.append(f"rx{channel}_tone_snr_low")
                    if clipping[channel] > quality.thresholds.max_clipping_fraction:
                        reasons.append(f"rx{channel}_clipping")
                if phase_std > quality.thresholds.max_phase_std_deg:
                    reasons.append("within_window_phase_unstable")
                valid = not reasons
                window_quality.append(valid)
                if (
                    window.get("window_index") != window_index
                    or window.get("offset_start")
                    != window_index * capture.window_samples
                    or window.get("offset_end_exclusive")
                    != (window_index + 1) * capture.window_samples
                    or window.get("sample_start") != expected_start
                    or window.get("sample_end_exclusive")
                    != expected_start + capture.window_samples
                    or window.get("quality_reasons") != reasons
                    or window.get("quality_valid") is not valid
                ):
                    errors.append(f"{context} analysis window ledger is inconsistent")
                command = (
                    None
                    if section == "precondition"
                    else attack_command
                    if section == "attack"
                    else release_command
                )
                lower = command.get("sample_sequence_before") if command else None
                upper = command.get("sample_sequence_after") if command else None
                intersects = bool(
                    command is not None
                    and type(lower) is int
                    and type(upper) is int
                    and window["sample_start"] < upper
                    and window["sample_end_exclusive"] > lower
                )
                quality_required = section != "precondition" or frame in baseline
                if quality_required and not intersects and not valid:
                    errors.append(
                        f"{context} has a quality-invalid window outside a command "
                        "interval"
                    )
            if analysis.get("quality_valid") is not all(window_quality):
                errors.append(f"{context} frame quality summary is inconsistent")

            metadata = frame.get("metadata")
            continuity = frame.get("continuity")
            if not isinstance(metadata, Mapping) or not isinstance(continuity, Mapping):
                errors.append(f"{context} lacks metadata gap evidence")
                return errors
            buffer_sequence = metadata.get("buffer_sequence")
            first_sample = metadata.get("first_sample_sequence")
            samples = metadata.get("samples_per_channel")
            transition_count = metadata.get("tandem_transition_count")
            current_stream = metadata.get("stream_id")
            current_epoch = metadata.get("ownership_epoch")
            events = metadata.get("gain_events")
            endpoint = metadata.get("bench_gain_indices")
            index_range = metadata.get("gain_index_range")
            current_provenance = metadata.get("threshold_provenance")
            if (
                not exact_integer(buffer_sequence)
                or not exact_integer(first_sample)
                or samples != capture.frame_samples
                or not exact_integer(transition_count)
                or transition_count >= uint32_modulus
                or not exact_integer(current_stream, minimum=1)
                or not exact_integer(current_epoch, minimum=1)
                or not isinstance(events, list)
                or not isinstance(endpoint, list)
                or len(endpoint) != 2
                or any(not exact_integer(value) for value in endpoint)
                or endpoint[0] != endpoint[1]
                or not isinstance(index_range, list)
                or len(index_range) != 2
                or any(not exact_integer(value) for value in index_range)
                or index_range[0] > index_range[1]
                or not index_range[0] <= endpoint[0] <= index_range[1]
                or not exact_integer(metadata.get("flags"))
                or metadata.get("flags") & TANDEM_UNSAFE_FLAGS
                or metadata.get("flags") & required_metadata_flags
                != required_metadata_flags
                or metadata.get("tandem_state") != int(TandemState.ARMED_AUTO)
                or metadata.get("tandem_state_name") != "armed_auto"
                or metadata.get("gain_table_id") != expected_gain_table_id
                or metadata.get("gain_db_range") != [0, 62]
                or metadata.get("initial_gain_db") != int(quality.manual_gain_db)
                or not exact_integer(current_provenance)
            ):
                errors.append(f"{context} metadata counters or gains are malformed")
                return errors
            if threshold_provenance is None:
                threshold_provenance = int(current_provenance)
            elif current_provenance != threshold_provenance:
                errors.append(f"{context} threshold provenance changed")
            if section == "precondition":
                stable = bool(
                    previous_metadata is not None
                    and not events
                    and transition_count
                    == previous_metadata.get("tandem_transition_count")
                    and endpoint == previous_metadata.get("bench_gain_indices")
                )
                tandem_stable_run = tandem_stable_run + 1 if stable else 0
                if frame.get("precondition_stable_run") != tandem_stable_run:
                    errors.append(
                        f"{context} precondition stability ledger is inconsistent"
                    )
                if (
                    section_index < len(trace) - 1
                    and tandem_stable_run >= capture.precondition_stable_frames
                ):
                    errors.append(
                        "transient tandem precondition continued after stability"
                    )
            if (
                not exact_integer(metadata.get("event_count"))
                or not exact_integer(metadata.get("gain_event_count"))
                or metadata.get("event_count") != len(events)
                or metadata.get("gain_event_count") != len(events)
            ):
                errors.append(f"{context} event count differs from its event array")
            if (
                metadata.get("tandem_fault_flags") != 0
                or metadata.get("observation_overflow_count") != 0
                or metadata.get("event_overflow_count") != 0
            ):
                errors.append(f"{context} reports a fault or metadata overflow")
            if (
                frame.get("first_sample_sequence") != first_sample
                or frame.get("sample_end_exclusive") != first_sample + samples
            ):
                errors.append(f"{context} IQ sample range differs from metadata")

            initial_unrepresented = 0
            if previous_metadata is None:
                stream_id = int(current_stream)
                ownership_epoch = int(current_epoch)
                gain_index_range = (int(index_range[0]), int(index_range[1]))
                buffer_delta: int | None = None
                sample_delta: int | None = None
                transition_delta: int | None = None
                missing = 0
                hidden = 0
                initial_unrepresented = int(transition_count) - len(events)
                if initial_unrepresented < 0:
                    errors.append(f"{context} has more events than transitions")
                    return errors
            else:
                if current_stream != stream_id or current_epoch != ownership_epoch:
                    errors.append(f"{context} stream or ownership changed")
                if tuple(index_range) != gain_index_range:
                    errors.append(f"{context} gain-index range changed")
                buffer_delta = int(buffer_sequence) - int(
                    previous_metadata["buffer_sequence"]
                )
                sample_delta = int(first_sample) - int(
                    previous_metadata["first_sample_sequence"]
                )
                if buffer_delta <= 0 or sample_delta <= 0:
                    errors.append(f"{context} frame counters did not advance")
                    return errors
                if sample_delta != buffer_delta * capture.frame_samples:
                    errors.append(f"{context} buffer/sample deltas disagree")
                    return errors
                missing = buffer_delta - 1
                transition_delta = (
                    int(transition_count)
                    - int(previous_metadata["tandem_transition_count"])
                ) % uint32_modulus
                if transition_delta >= uint32_modulus // 2:
                    errors.append(f"{context} transition counter regressed")
                    return errors
                hidden = transition_delta - len(events)
                if hidden < 0:
                    errors.append(f"{context} has more events than transitions")
                    return errors
                if missing:
                    errors.append(
                        f"{context} has a provider gap under continuous acquisition"
                    )
                elif hidden:
                    errors.append(f"{context} lost adjacent-frame event evidence")
                cumulative_missing += missing

            sample_gap = missing * capture.frame_samples
            expected_continuity = {
                "buffer_delta": buffer_delta,
                "sample_delta": sample_delta,
                "missing_frame_count": missing,
                "sample_gap_before": sample_gap,
                "provider_gap_accepted": False,
                "gap_context": expected_gap_context,
                "command_boundary_gap_allowed": False,
                "transition_count_delta": transition_delta,
                "visible_event_count": len(events),
                "hidden_transition_count": hidden,
                "initial_unrepresented_transition_count": initial_unrepresented,
                "cumulative_missing_frame_count": cumulative_missing,
                "cumulative_hidden_transition_count": 0,
                "cumulative_event_sequence_hole_count": 0,
            }
            if dict(continuity) != expected_continuity:
                errors.append(f"{context} gap evidence differs from metadata")
            if frame.get("sample_gap_before") != sample_gap:
                errors.append(f"{context} sample-gap summary differs from metadata")

            for event_index, event in enumerate(events):
                event_context = f"{context} event {event_index}"
                if not isinstance(event, Mapping):
                    errors.append(f"{event_context} is malformed")
                    return errors
                event_sample = event.get("sample_sequence")
                event_sequence = event.get("event_sequence")
                flags = event.get("flags")
                direction = event.get("direction")
                reason = event.get("reason")
                rx1_gain = event.get("rx1_gain_index")
                rx2_gain = event.get("rx2_gain_index")
                flags_valid = exact_integer(flags) and flags <= 0x3F
                expected_direction = (flags >> 4) & 0x3 if flags_valid else None
                expected_reason = flags & 0xF if flags_valid else None
                try:
                    direction_name = TandemEventDirection(
                        expected_direction
                    ).name.lower()
                    reason_name = TandemEventReason(expected_reason).name.lower()
                except (TypeError, ValueError):
                    direction_name = None
                    reason_name = None
                if (
                    not exact_integer(event_sample)
                    or not exact_integer(event_sequence)
                    or event_sequence >= uint32_modulus
                    or not flags_valid
                    or direction_name is None
                    or reason_name is None
                    or type(direction) is not int
                    or direction != expected_direction
                    or event.get("direction_name") != direction_name
                    or type(reason) is not int
                    or reason != expected_reason
                    or event.get("reason_name") != reason_name
                    or not exact_integer(rx1_gain)
                    or not exact_integer(rx2_gain)
                    or rx1_gain != rx2_gain
                    or not first_sample <= event_sample < first_sample + samples
                    or not index_range[0] <= rx1_gain <= index_range[1]
                ):
                    errors.append(f"{event_context} is malformed")
                    return errors
                step = 1 if direction == 1 else -1
                if previous_event is not None:
                    sequence_delta = (
                        int(event_sequence) - int(previous_event["event_sequence"])
                    ) % uint32_modulus
                    if sequence_delta != 1:
                        errors.append(f"{event_context} sequence is not contiguous")
                    if event_sample < int(previous_event["sample_sequence"]):
                        errors.append(f"{event_context} is not sample ordered")
                    if rx1_gain != int(previous_event["rx1_gain_index"]) + step:
                        errors.append(f"{event_context} is not an exact paired step")
                elif (
                    previous_metadata is not None
                    and rx1_gain
                    != int(previous_metadata["bench_gain_indices"][0]) + step
                ):
                    errors.append(
                        f"{event_context} disagrees with the prior paired endpoint"
                    )
                previous_event = event
                if section in ("attack", "release"):
                    visible_response_events.append(event)
            if events:
                if endpoint != [
                    events[-1].get("rx1_gain_index"),
                    events[-1].get("rx2_gain_index"),
                ]:
                    errors.append(f"{context} endpoint differs from its final event")
            elif previous_metadata is not None and endpoint != previous_metadata.get(
                "bench_gain_indices"
            ):
                errors.append(f"{context} endpoint changed without an event")
            previous_metadata = metadata

    if tandem_stable_run < capture.precondition_stable_frames:
        errors.append("transient tandem precondition never established stability")

    expected_partitions: dict[str, dict[str, int]] = {}
    phase_order = {
        "precommand_prefetch": 0,
        "command_bracket": 1,
        "continuous_response": 2,
    }
    for name, frames, command in (
        ("attack", attack, attack_command),
        ("release", release, release_command),
    ):
        lower = command.get("sample_sequence_before")
        upper = command.get("sample_sequence_after")
        if not exact_integer(lower) or not exact_integer(upper, minimum=1):
            errors.append(
                f"transient tandem {name} response partition cannot be recomputed"
            )
            continue
        contexts: list[str] = []
        fully_post = 0
        for frame in frames:
            assert isinstance(frame, Mapping)
            start = frame.get("first_sample_sequence")
            end = frame.get("sample_end_exclusive")
            if not exact_integer(start) or not exact_integer(end, minimum=1):
                errors.append(
                    f"transient tandem {name} response partition has malformed "
                    "sample bounds"
                )
                contexts = []
                break
            if end <= lower:
                contexts.append("precommand_prefetch")
            elif start < upper:
                contexts.append("command_bracket")
            else:
                contexts.append("continuous_response")
                fully_post += 1
        if not contexts:
            continue
        non_post = len(frames) - fully_post
        if non_post > response_tail:
            errors.append(
                f"transient tandem {name} pre/bracketed prefix exceeds policy"
            )
        if fully_post < capture.response_frames:
            errors.append(
                f"transient tandem {name} lacks the required fully post-command frames"
            )
        if contexts != sorted(contexts, key=phase_order.__getitem__):
            errors.append(
                f"transient tandem {name} response phases are not sample ordered"
            )
        expected_partitions[name] = {
            "precommand_prefetch_frames": contexts.count("precommand_prefetch"),
            "command_bracket_frames": contexts.count("command_bracket"),
            "fully_post_command_frames": fully_post,
            "required_fully_post_command_frames": capture.response_frames,
            "maximum_non_post_command_frames": response_tail,
        }
    if (
        not isinstance(acquisition, Mapping)
        or acquisition.get("response_partitions") != expected_partitions
    ):
        errors.append(
            "transient tandem response partition ledger differs from recomputation"
        )

    anchor_lower = baseline[0].get("first_sample_sequence")
    anchor_upper = baseline[-1].get("sample_end_exclusive")
    if (
        not exact_integer(anchor_lower)
        or not exact_integer(anchor_upper)
        or anchor_upper <= anchor_lower
        or conditioning_anchor.get("command_id") != "weak_conditioning_anchor"
        or conditioning_anchor.get("sample_sequence_before") != anchor_lower
        or conditioning_anchor.get("sample_sequence_after") != anchor_upper
        or conditioning_anchor.get("sample_uncertainty") != anchor_upper - anchor_lower
        or anchor_upper - anchor_lower > capture.max_sample_uncertainty
    ):
        errors.append(
            "transient tandem conditioning anchor differs from the exact retained "
            "baseline interval"
        )
    bracket_plan = (
        (
            "attack",
            attack_command,
            baseline[-1],
        ),
        (
            "release",
            release_command,
            attack[-1],
        ),
    )
    responses = mode.get("responses")
    for name, command, previous_frame in bracket_plan:
        reference = previous_frame.get("sample_end_exclusive")
        bracket = command.get("sample_counter_bracket")
        raw_fields: list[Any] = []
        extended_fields: list[Any] = []
        if isinstance(bracket, Mapping):
            raw_fields = [
                bracket.get("raw_before"),
                bracket.get("raw_post_write_initial"),
                bracket.get("raw_post_write_first_advance"),
                bracket.get("raw_post_write_causal"),
            ]
            extended_fields = [
                bracket.get("extended_before"),
                bracket.get("extended_post_write_initial"),
                bracket.get("extended_post_write_first_advance"),
                bracket.get("extended_after"),
            ]
        if (
            not exact_integer(reference)
            or not isinstance(bracket, Mapping)
            or bracket.get("register_address") != "0x800000b8"
            or bracket.get("counter_width_bits") != 32
            or bracket.get("counter_source")
            != "coherent FPGA RX sample counter low word"
            or bracket.get("extension_reference_sample") != reference
            or any(
                type(value) is not int or not 0 <= value < uint32_modulus
                for value in raw_fields
            )
            or any(not exact_integer(value) for value in extended_fields)
            or any(value >= 1 << 64 for value in extended_fields)
            or any(
                extended & (uint32_modulus - 1) != raw
                for extended, raw in zip(extended_fields, raw_fields, strict=True)
            )
            or not 0 <= extended_fields[1] - extended_fields[0] < uint32_modulus // 2
            or extended_fields[1] - extended_fields[0]
            != (raw_fields[1] - raw_fields[0]) % uint32_modulus
            or not 0 < extended_fields[2] - extended_fields[1] < uint32_modulus // 2
            or extended_fields[2] - extended_fields[1]
            != (raw_fields[2] - raw_fields[1]) % uint32_modulus
            or not 0 < extended_fields[3] - extended_fields[2] < uint32_modulus // 2
            or extended_fields[3] - extended_fields[2]
            != (raw_fields[3] - raw_fields[2]) % uint32_modulus
            or abs(extended_fields[0] - reference) >= uint32_modulus // 2
            or type(bracket.get("post_write_read_count")) is not int
            or bracket.get("post_write_read_count") not in range(3, 10)
            or bracket.get("lower_clamped_to_last_observed_frame_end")
            is not (reference > extended_fields[0])
            or bracket.get("sample_sequence_lower")
            != max(reference, extended_fields[0])
            or bracket.get("sample_sequence_upper") != extended_fields[3]
            or command.get("sample_sequence_before")
            != bracket.get("sample_sequence_lower")
            or command.get("sample_sequence_after")
            != bracket.get("sample_sequence_upper")
            or command.get("sample_uncertainty")
            != command.get("sample_sequence_after")
            - command.get("sample_sequence_before")
            or not exact_integer(command.get("sample_uncertainty"), minimum=1)
            or command.get("sample_uncertainty") > capture.max_sample_uncertainty
            or command.get("timing_role")
            != "host_write_bracketed_by_coherent_fpga_counter"
            or command.get("sample_timing_basis") != "hardware_sample_counter"
            or command.get("sample_anchor_policy")
            != "max(last observed frame end, coherent low32 pre-read) through the "
            "second distinct coherent low32 advance observed after an initial "
            "post-write read"
        ):
            errors.append(f"transient tandem {name} command bracket is inconsistent")
        response = responses.get(name) if isinstance(responses, Mapping) else None
        if (
            not isinstance(response, Mapping)
            or response.get("command_bracket_gap_samples") != 0
        ):
            errors.append(f"transient tandem {name} response gap is inconsistent")

    def command_from_report(record: Mapping[str, Any]) -> StimulusCommand:
        return StimulusCommand(
            command_id=record["command_id"],
            requested_level_db=record["requested_level_db"],
            applied_level_db=record["applied_level_db"],
            host_before_ns=record["host_before_ns"],
            host_after_ns=record["host_after_ns"],
            sample_sequence_before=record["sample_sequence_before"],
            sample_sequence_after=record["sample_sequence_after"],
        )

    try:
        anchor_stimulus = command_from_report(conditioning_anchor)
        attack_stimulus = command_from_report(attack_command)
        release_stimulus = command_from_report(release_command)
        response_kwargs = {
            "sample_rate_hz": quality.sample_rate_hz,
            "baseline_windows": capture.baseline_windows,
            "steady_windows": capture.steady_windows,
            "stable_windows": capture.stable_windows,
            "settling_tolerance_db": capture.settling_tolerance_db,
            "ringing_deadband_db": capture.ringing_deadband_db,
            "max_host_jitter_ns": capture.max_host_jitter_ns,
            "max_sample_uncertainty": capture.max_sample_uncertainty,
        }
        recomputed_responses = {
            "attack": dict(
                calculate_transient_response(
                    [
                        window
                        for frame in (*baseline, *attack)
                        for window in frame["analysis"]["windows"]
                    ],
                    previous_command=anchor_stimulus,
                    command=attack_stimulus,
                    **response_kwargs,
                )
            ),
            "release": dict(
                calculate_transient_response(
                    [
                        window
                        for frame in (*attack, *release)
                        for window in frame["analysis"]["windows"]
                    ],
                    previous_command=attack_stimulus,
                    command=release_stimulus,
                    **response_kwargs,
                )
            ),
        }
        for response in recomputed_responses.values():
            response.update(
                {
                    "timing_qualification": "fpga_sample_counter_bounded",
                    "hardware_latency_qualified": True,
                    "transient_observation_scope": (
                        "continuous_hardware_sample_record"
                    ),
                }
            )
    except (KeyError, TypeError, ValueError) as error:
        errors.append(f"transient tandem responses cannot be recomputed: {error}")
    else:
        if responses != _json_safe(recomputed_responses):
            errors.append("transient tandem responses differ from recomputation")

    try:
        recomputed_gain = _json_safe(
            dict(
                reconcile_tandem_events(
                    (
                        command_from_report(conditioning_anchor),
                        command_from_report(attack_command),
                        command_from_report(release_command),
                    ),
                    visible_response_events,
                    sample_rate_hz=quality.sample_rate_hz,
                    max_host_jitter_ns=capture.max_host_jitter_ns,
                    max_sample_uncertainty=capture.max_sample_uncertainty,
                    max_latency_samples=capture.max_event_latency_samples,
                )
            )
        )
        assert isinstance(recomputed_gain, dict)
        recomputed_gain.update(
            {
                "timing_qualification": "fpga_sample_counter_bounded",
                "hardware_latency_qualified": True,
            }
        )
    except (KeyError, TypeError, ValueError) as error:
        errors.append(f"transient tandem gain evidence cannot be recomputed: {error}")
    else:
        if mode.get("gain_evidence") != recomputed_gain:
            errors.append("transient tandem gain evidence differs from recomputation")
    return errors


def _identity_errors(
    report: Mapping[str, Any], options: ReleaseHardwareOptions
) -> list[str]:
    identity = report.get("identity")
    if not isinstance(identity, Mapping):
        return ["identity is missing"]
    errors = []
    if identity.get("serial") != options.serial:
        errors.append("serial differs from plan")
    if identity.get("libiio_source_commit") != options.libiio_source_commit:
        errors.append("host libiio commit differs from plan")
    attrs = identity.get("context_attrs")
    if (
        not isinstance(attrs, Mapping)
        or attrs.get("fw_version") != options.firmware_version
    ):
        errors.append("firmware version differs from exact plan")
    uri = identity.get("uri")
    if not isinstance(uri, str) or not uri.startswith("usb:"):
        errors.append("radio transport is not dynamically resolved local USB")
    return errors


def _soak_temperature_errors(
    options: ReleaseHardwareOptions, records: Mapping[str, Any]
) -> list[str]:
    if options.policy_set != "baseline":
        return []
    errors = []
    for run_id, record in records.items():
        if record.get("status") != "complete":
            continue
        temperature = record.get("summary", {}).get("temperature")
        if (
            not isinstance(temperature, Mapping)
            or temperature.get("available") is not True
            or type(temperature.get("count")) is not int
            or temperature["count"] <= 0
        ):
            errors.append(f"baseline soak run {run_id} lacks temperature evidence")
    return errors


def production_validator(options: ReleaseHardwareOptions) -> PhaseValidator:
    def validate(spec: PhaseSpec, path: Path, work_dir: Path) -> ValidatedPhase:
        _assert_harness_unchanged(options)
        disk = json.loads(path.read_text(encoding="utf-8"))
        if spec.kind == "steady":
            config, base = _steady_inputs(options, work_dir)
            plan = build_release_plan(config, base)
            checkpoint_path = work_dir / steady_campaign.CHECKPOINT_NAME
            if path != (work_dir / steady_campaign.REPORT_NAME).resolve():
                raise ReleaseCliError("steady report path differs from plan")
            checkpoint = steady_campaign._load_checkpoint(checkpoint_path, plan)
            steady_campaign._verify_completed_artifacts(plan, checkpoint)
            expected = build_campaign_report(plan, checkpoint, config)
            if disk != expected:
                raise ReleaseCliError("steady report differs from its checkpoint")
            identity_failures: list[str] = []
            cleanup_failures: list[str] = []
            complete = 0
            for run, record in zip(plan.runs, checkpoint["runs"].values(), strict=True):
                if record["status"] != "complete":
                    continue
                complete += 1
                child = json.loads(Path(record["report_path"]).read_text())
                identity_failures.extend(_identity_errors(child, options))
                cleanup_failures.extend(_cleanup_errors(child))
                if (
                    child.get("rf", {}).get("center_frequency_hz_requested")
                    != run.band.center_frequency_hz
                ):
                    identity_failures.append("steady RF band differs from plan")
            if identity_failures or cleanup_failures:
                raise ReleaseCliError(
                    "; ".join((*identity_failures, *cleanup_failures))
                )
            temperature_failures = _soak_temperature_errors(options, checkpoint["runs"])
            if temperature_failures:
                raise ReleaseCliError("; ".join(temperature_failures))
            verdict = str(disk.get("verdict"))
            cleanup_verified = verdict == "pass" and complete == len(plan.runs)
            return ValidatedPhase(
                verdict,
                cleanup_verified,
                {
                    "campaign_kind": _configuration(options)["steady_campaign_kind"],
                    "policy_set": options.policy_set,
                    "complete_runs": complete,
                    "planned_runs": len(plan.runs),
                    "temperature": disk.get("temperature"),
                    "repeatability": disk.get("repeatability"),
                },
            )
        expected_schema = {
            "transient": "plutosdr-fw.tandem-agc-transient.v1",
            "modulated": "plutosdr-fw.modulated-hardware.v1",
        }[spec.kind]
        errors = []
        if disk.get("schema") != expected_schema or disk.get("verdict") != "pass":
            errors.append("phase schema or verdict is invalid")
        errors.extend(_identity_errors(disk, options))
        errors.extend(_cleanup_errors(disk))
        assert spec.band is not None
        rf = disk.get("rf")
        if (
            not isinstance(rf, Mapping)
            or rf.get("center_frequency_hz_requested") != spec.band.center_frequency_hz
        ):
            errors.append("phase RF band differs from plan")
        if spec.kind == "transient":
            transient_quality = _base_quality(
                options, output_dir=work_dir, band=spec.band
            )
            center_readback = (
                rf.get("center_frequency_hz_readback")
                if isinstance(rf, Mapping)
                else None
            )
            if (
                not isinstance(rf, Mapping)
                or rf.get("center_frequency_hz_requested")
                != transient_quality.center_frequency_hz
                or rf.get("tone_hz") != transient_quality.tone_hz
                or rf.get("dds_scale") != transient_quality.dds_scale
                or not isinstance(center_readback, Mapping)
                or any(
                    type(center_readback.get(name)) is not int
                    or abs(
                        center_readback[name] - transient_quality.center_frequency_hz
                    )
                    > 2
                    for name in ("rx_lo_hz", "tx_lo_hz")
                )
            ):
                errors.append("transient RF readback differs from plan")
            expected_quality = _json_safe(asdict(transient_quality))
            assert isinstance(expected_quality, dict)
            expected_quality["output_dir"] = str(work_dir)
            expected_capture = TransientCaptureOptions()
            expected_configuration = {
                "quality": expected_quality,
                "transient_capture": _json_safe(asdict(expected_capture)),
                "kernel_buffers": 1,
            }
            if disk.get("configuration") != expected_configuration:
                errors.append("transient configuration differs from plan")
            if disk.get("evidence_policy") != transient_evidence_policy(
                expected_capture
            ):
                errors.append("transient evidence policy differs from plan")
            if disk.get("required_modes") != list(TRANSIENT_MODES) or [
                item.get("mode") for item in disk.get("modes", [])
            ] != list(TRANSIENT_MODES):
                errors.append("transient mode coverage differs from plan")
            mode_records = disk.get("modes", [])
            comparison = disk.get("comparison")
            if (
                not isinstance(comparison, list)
                or len(comparison) != len(TRANSIENT_MODES)
                or [item.get("mode") for item in comparison] != list(TRANSIENT_MODES)
            ):
                errors.append("transient comparison coverage differs from plan")
            for index, mode in enumerate(mode_records):
                if mode.get("verdict") != "pass":
                    errors.append("transient mode verdict is not pass")
                    continue
                gain = mode.get("gain_evidence")
                responses = mode.get("responses")
                if (
                    not isinstance(gain, Mapping)
                    or gain.get("evidence_valid") is not True
                ):
                    errors.append("transient gain evidence is invalid")
                if not isinstance(responses, Mapping) or any(
                    not isinstance(responses.get(direction), Mapping)
                    or responses[direction].get("evidence_valid") is not True
                    for direction in ("attack", "release")
                ):
                    errors.append("transient attack/release response is invalid")
                if (
                    isinstance(comparison, list)
                    and index < len(comparison)
                    and comparison[index].get("gain_evidence") != gain
                ):
                    errors.append("transient comparison changed gain evidence")
            errors.extend(_transient_comparison_errors(mode_records, comparison))
            errors.extend(
                _transient_mode_boundary_errors(mode_records, transient_quality)
            )
            errors.extend(
                _transient_ordinary_errors(
                    mode_records,
                    expected_capture,
                    transient_quality,
                )
            )
            errors.extend(
                _transient_continuity_errors(
                    mode_records,
                    expected_capture,
                    transient_quality,
                )
            )
            summary = {
                "mode_count": len(mode_records),
                "comparison": comparison,
            }
        else:
            expected_options = ModulatedHardwareOptions(
                physical_attenuation_db=options.physical_attenuation_db,
                center_frequency_hz=spec.band.center_frequency_hz,
                tx2_gain_db=DEFAULT_MODULATED_TX2_GAIN_DB,
                modes=RELEASE_MODULATED_MODES,
                max_seconds=options.phase_max_seconds,
                output_dir=work_dir,
            )
            # Durable JSON normalizes dataclass tuples (notably blocker_points)
            # to arrays.  Compare the same JSON-domain representation rather
            # than a Python tuple against the decoded list.
            expected_configuration = _json_safe(asdict(expected_options))
            assert isinstance(expected_configuration, dict)
            expected_configuration["output_dir"] = str(work_dir)
            expected_configuration["minimum_effective_attenuation_db"] = (
                expected_options.minimum_effective_attenuation_db
            )
            if disk.get("configuration") != expected_configuration:
                errors.append("modulated configuration differs from plan")
            if disk.get("mode_evidence_policy") != modulated_mode_evidence_policy():
                errors.append("modulated mode evidence policy differs from plan")
            expected_case_ids = [
                "desired_only",
                *(
                    f"blocker_{index:02d}"
                    for index in range(len(expected_options.blocker_points))
                ),
            ]
            waveforms = disk.get("waveforms")
            if (
                not isinstance(waveforms, list)
                or [item.get("case_id") for item in waveforms] != expected_case_ids
                or [item.get("kind") for item in waveforms]
                != [
                    "desired_only",
                    *("composite_blocker" for _ in expected_case_ids[1:]),
                ]
            ):
                errors.append("modulated waveform cases differ from plan")
            errors.extend(_modulated_dma_cleanup_errors(waveforms))
            runs = disk.get("runs")
            run_records = runs if isinstance(runs, list) else []
            observed = [
                (item.get("case_id"), item.get("mode"))
                for item in run_records
                if isinstance(item, Mapping)
            ]
            expected = [
                (case_id, mode)
                for case_id in expected_case_ids
                for mode in expected_options.modes
            ]
            if observed != expected:
                errors.append("modulated mode/blocker coverage differs from plan")
            errors.extend(_modulated_gain_errors(runs, expected_options))
            errors.extend(_modulated_iq_convention_errors(runs))
            errors.extend(
                _modulated_continuity_errors(runs, expected_options.capture_samples)
            )
            raw_iq_errors, raw_iq_provenance = _modulated_raw_iq_evidence(
                runs,
                work_dir=work_dir,
                serial=options.serial,
                capture_samples=expected_options.capture_samples,
            )
            errors.extend(raw_iq_errors)
            evaluation = disk.get("evaluation")
            if (
                not isinstance(evaluation, Mapping)
                or evaluation.get("valid") is not True
            ):
                errors.append("modulated quality evaluation is invalid")
            else:
                recomputed_evaluation = _json_safe(
                    evaluate_modulated_hardware_report(
                        disk,
                        expected_options.degradation_thresholds,
                        expected_modes=expected_options.modes,
                    )
                )
                if evaluation != recomputed_evaluation:
                    errors.append(
                        "modulated quality evaluation differs from recomputation"
                    )
            summary = {
                "run_count": len(observed),
                "evaluation": evaluation,
                "raw_iq_provenance": raw_iq_provenance,
            }
        if errors:
            raise ReleaseCliError("; ".join(errors))
        return ValidatedPhase("pass", True, summary)

    return validate


def plan_document(options: ReleaseHardwareOptions) -> dict[str, Any]:
    specs = phase_specs(options)
    return {
        "schema": AGGREGATE_SCHEMA,
        "fingerprint": _fingerprint(options, specs),
        "configuration": _configuration(options),
        "plan": [spec.to_dict() for spec in specs],
        "deployment_performed": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    options = parse_cli_args(argv)
    if options.plan_only:
        print(json.dumps(plan_document(options), indent=2, sort_keys=True))
        return 0
    try:
        import iio
    except ImportError as error:
        raise SystemExit(
            "manifest-pinned pylibiio is not importable; use the guarded shell runner"
        ) from error
    report, path = run_aggregate(
        options,
        production_executor(options, iio),
        production_validator(options),
    )
    print(f"aggregate report: {path}")
    print(f"aggregate verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
