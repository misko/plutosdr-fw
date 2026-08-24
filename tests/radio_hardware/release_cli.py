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
    validate_options,
)
from .transient_hardware import (
    TRANSIENT_MODES,
    TransientCaptureOptions,
    run_transient_hardware,
    validate_transient_options,
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
            expected_quality = _json_safe(asdict(transient_quality))
            assert isinstance(expected_quality, dict)
            expected_quality["output_dir"] = str(work_dir)
            expected_configuration = {
                "quality": expected_quality,
                "transient_capture": _json_safe(asdict(TransientCaptureOptions())),
                "kernel_buffers": 1,
            }
            if disk.get("configuration") != expected_configuration:
                errors.append("transient configuration differs from plan")
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
