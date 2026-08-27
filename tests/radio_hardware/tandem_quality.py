"""Safety-gated manual/native/tandem AGC quality matrix on the TX2 fixture."""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import statistics
import time
from collections.abc import Callable, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field, replace
from itertools import pairwise
from pathlib import Path
from typing import Any

from .experiment import (
    MAX_COMMON_CENTER_FREQUENCY_HZ,
    MIN_COMMON_CENTER_FREQUENCY_HZ,
    NATIVE_FAST_ENTRY_MANUAL_GAIN_DB,
    TX_MUTE_DB,
    EvidenceInvalid,
    Issue46Radio,
)
from .metadata_abi import (
    TANDEM_UNSAFE_FLAGS,
    TandemEventDirection,
    TandemFrameMetadata,
    TandemGainTable,
    TandemMode,
    TandemState,
    build_tandem_request,
    maximum_tandem_events_per_frame,
    parse_tandem_frame_metadata,
)
from .tone_quality import ToneQualityThresholds, analyze_common_tone

MODE_MANUAL = "manual_fixed"
MODE_NATIVE = "native_slow_attack"
MODE_NATIVE_FAST = "native_fast_attack"
MODE_TANDEM = "tandem_auto"
MODES = (MODE_MANUAL, MODE_NATIVE, MODE_TANDEM)
NATIVE_GAIN_CONTROL_MODES = ("slow_attack", "fast_attack", "hybrid")
AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES = ("slow_attack", "fast_attack")
DEFAULT_NATIVE_GAIN_CONTROL_MODES = ("slow_attack",)
MANUAL_TONE_TRACKING_TOLERANCE_DB = 3.0
MANUAL_TONE_RETRACE_TOLERANCE_DB = 3.0
NATIVE_MIN_GAIN_SPAN_DB = 1.0
NATIVE_FAST_MAX_TONE_DBFS = -2.0
_TANDEM_MEASUREMENT_RESTART_LIMIT = 1
_TANDEM_DEFERRED_IQ_LIMIT_BYTES = 32 * 1024 * 1024
_MATRIX_FAILURE_IQ_LIMIT_BYTES = 128 * 1024 * 1024
_MATRIX_FAILURE_IQ_SCHEMA = "plutosdr-fw.tandem-agc-failure-iq.v1"


class _EvidenceInvalidWithDetails(EvidenceInvalid):
    """Evidence rejection carrying JSON-safe durable diagnostic details."""

    def __init__(self, message: str, failure_evidence: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.failure_evidence = dict(failure_evidence)


class _CapturedFrameInvalid(EvidenceInvalid):
    """A rejected capture whose raw bytes remain available until session exit."""

    def __init__(
        self,
        message: str,
        *,
        raw: bytes,
        frame: dict[str, Any],
    ) -> None:
        super().__init__(message)
        self.raw = bytes(raw)
        self.frame = frame


def _artifact_path_error(
    message: str,
    *,
    root: Path,
    path: Path,
    cause: BaseException | None = None,
) -> _EvidenceInvalidWithDetails:
    evidence: dict[str, Any] = {
        "kind": "unsafe_artifact_path",
        "artifact_root": str(root),
        "artifact_path": str(path),
    }
    if cause is not None:
        evidence["cause"] = _exception_text(cause)
    return _EvidenceInvalidWithDetails(message, evidence)


def _open_safe_artifact_parent(root: Path, path: Path) -> tuple[int, str, str]:
    """Open an owned in-root parent without following any in-root symlink."""

    root = Path(os.path.abspath(root))
    path = Path(os.path.abspath(path))
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise _artifact_path_error(
            "artifact path escapes its output root",
            root=root,
            path=path,
            cause=error,
        ) from error
    if relative == Path(".") or relative.name in {"", ".", ".."}:
        raise _artifact_path_error(
            "artifact path does not name a file",
            root=root,
            path=path,
        )

    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root_lstat = root.lstat()
    except OSError as error:
        raise _artifact_path_error(
            "artifact root could not be created safely",
            root=root,
            path=path,
            cause=error,
        ) from error
    if (
        stat.S_ISLNK(root_lstat.st_mode)
        or not stat.S_ISDIR(root_lstat.st_mode)
        or root_lstat.st_uid != os.geteuid()
    ):
        raise _artifact_path_error(
            "artifact root is not an owned real directory",
            root=root,
            path=path,
        )

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_fd = os.open(root, directory_flags)
    except OSError as error:
        raise _artifact_path_error(
            "artifact root could not be opened without following symlinks",
            root=root,
            path=path,
            cause=error,
        ) from error
    try:
        for component in relative.parent.parts:
            if component in {"", ".", ".."}:
                raise _artifact_path_error(
                    "artifact path contains an unsafe directory component",
                    root=root,
                    path=path,
                )
            try:
                child_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            except FileNotFoundError:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=directory_fd)
                    child_fd = os.open(component, directory_flags, dir_fd=directory_fd)
                except OSError as error:
                    raise _artifact_path_error(
                        "artifact directory could not be created safely",
                        root=root,
                        path=path,
                        cause=error,
                    ) from error
            except OSError as error:
                raise _artifact_path_error(
                    "artifact directory is a symlink or special file",
                    root=root,
                    path=path,
                    cause=error,
                ) from error
            child_stat = os.fstat(child_fd)
            if (
                not stat.S_ISDIR(child_stat.st_mode)
                or child_stat.st_uid != os.geteuid()
            ):
                os.close(child_fd)
                raise _artifact_path_error(
                    "artifact directory is not owned by the current user",
                    root=root,
                    path=path,
                )
            os.close(directory_fd)
            directory_fd = child_fd
        return directory_fd, relative.name, relative.as_posix()
    except BaseException:
        os.close(directory_fd)
        raise


def _validate_safe_artifact_destination(root: Path, path: Path) -> str:
    directory_fd, filename, relative_path = _open_safe_artifact_parent(root, path)
    try:
        try:
            destination = os.stat(
                filename,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return relative_path
        if not stat.S_ISREG(destination.st_mode) or destination.st_uid != os.geteuid():
            raise _artifact_path_error(
                "artifact destination is a symlink, special file, or is not owned",
                root=Path(os.path.abspath(root)),
                path=Path(os.path.abspath(path)),
            )
        return relative_path
    finally:
        os.close(directory_fd)


def _safe_atomic_artifact_write(root: Path, path: Path, payload: bytes) -> str:
    """Atomically replace an owned regular artifact without following symlinks."""

    directory_fd, filename, relative_path = _open_safe_artifact_parent(root, path)
    temporary_name: str | None = None
    temporary_fd: int | None = None
    try:
        try:
            destination = os.stat(
                filename,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            destination = None
        if destination is not None and (
            not stat.S_ISREG(destination.st_mode) or destination.st_uid != os.geteuid()
        ):
            raise _artifact_path_error(
                "artifact destination is a symlink, special file, or is not owned",
                root=Path(os.path.abspath(root)),
                path=Path(os.path.abspath(path)),
            )

        open_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        for suffix in range(1_000):
            candidate = f".{filename}.tmp-{os.getpid()}-{suffix}"
            try:
                temporary_fd = os.open(
                    candidate,
                    open_flags,
                    0o600,
                    dir_fd=directory_fd,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if temporary_fd is None or temporary_name is None:
            raise _artifact_path_error(
                "artifact writer could not reserve an owned temporary file",
                root=Path(os.path.abspath(root)),
                path=Path(os.path.abspath(path)),
            )
        temporary_stat = os.fstat(temporary_fd)
        if (
            not stat.S_ISREG(temporary_stat.st_mode)
            or temporary_stat.st_uid != os.geteuid()
        ):
            raise _artifact_path_error(
                "artifact temporary file is not an owned regular file",
                root=Path(os.path.abspath(root)),
                path=Path(os.path.abspath(path)),
            )
        remaining = memoryview(payload)
        while remaining:
            written = os.write(temporary_fd, remaining)
            if written <= 0:
                raise OSError("artifact write made no forward progress")
            remaining = remaining[written:]
        os.fsync(temporary_fd)
        os.close(temporary_fd)
        temporary_fd = None

        # Recheck immediately before the atomic replace.  os.replace itself
        # replaces a directory entry and never follows the destination.
        _validate_safe_artifact_destination(root, path)
        os.replace(
            temporary_name,
            filename,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        temporary_name = None
        os.fsync(directory_fd)
        final_stat = os.stat(
            filename,
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
        if not stat.S_ISREG(final_stat.st_mode) or final_stat.st_uid != os.geteuid():
            raise _artifact_path_error(
                "materialized artifact is not an owned regular file",
                root=Path(os.path.abspath(root)),
                path=Path(os.path.abspath(path)),
            )
        return relative_path
    except _EvidenceInvalidWithDetails:
        raise
    except OSError as error:
        raise _artifact_path_error(
            "artifact could not be written safely",
            root=Path(os.path.abspath(root)),
            path=Path(os.path.abspath(path)),
            cause=error,
        ) from error
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        os.close(directory_fd)


@dataclass
class _TandemContinuity:
    """Chronological AUTO evidence state for one metadata-buffer session."""

    previous: TandemFrameMetadata | None = None
    previous_frame: dict[str, Any] | None = None
    penultimate_frame: dict[str, Any] | None = None
    last_event_sequence: int | None = None
    last_event_sample_sequence: int | None = None
    last_event_gain_index: int | None = None
    unrepresented_since_event: int = 0
    missing_frame_count: int = 0
    hidden_transition_count: int = 0
    event_sequence_hole_count: int = 0
    next_capture_ordinal: int = 0
    last_frame_evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class _DeferredIqWrite:
    path: Path
    raw: bytes
    frame: dict[str, Any]
    path_field: str
    failure_only: bool


@dataclass
class _DeferredTandemWrites:
    """Bound raw-IQ retention until the metadata buffer has closed."""

    maximum_bytes: int = _TANDEM_DEFERRED_IQ_LIMIT_BYTES
    pending: list[_DeferredIqWrite] = field(default_factory=list)
    pending_bytes: int = 0
    report_root: Path | None = None

    def queue(
        self,
        raw: bytes,
        frame: dict[str, Any],
        path: Path,
        *,
        path_field: str,
        failure_only: bool = True,
    ) -> None:
        self.queue_batch(
            (
                _DeferredIqWrite(
                    path=path,
                    raw=raw,
                    frame=frame,
                    path_field=path_field,
                    failure_only=failure_only,
                ),
            )
        )

    def queue_batch(self, writes: Sequence[_DeferredIqWrite]) -> None:
        """Atomically retain a complete logical detail batch or none of it."""

        requested_bytes = sum(len(item.raw) for item in writes)
        if self.pending_bytes + requested_bytes > self.maximum_bytes:
            raise _EvidenceInvalidWithDetails(
                "tandem deferred IQ evidence exceeded its in-memory bound",
                {
                    "kind": "tandem_deferred_iq_bound_exceeded",
                    "maximum_bytes": self.maximum_bytes,
                    "pending_bytes": self.pending_bytes,
                    "requested_bytes": requested_bytes,
                    "requested_items": len(writes),
                    "captured_frames": [item.frame for item in writes],
                },
            )
        prepared = [
            _DeferredIqWrite(
                path=item.path,
                raw=bytes(item.raw),
                frame=item.frame,
                path_field=item.path_field,
                failure_only=item.failure_only,
            )
            for item in writes
        ]
        self.pending.extend(prepared)
        self.pending_bytes += requested_bytes

    def _flush_items(self, items: Sequence[_DeferredIqWrite]) -> None:
        if self.report_root is None:
            raise _EvidenceInvalidWithDetails(
                "tandem artifact writer lacks an output root",
                {"kind": "tandem_artifact_root_missing"},
            )
        for item in items:
            _validate_safe_artifact_destination(self.report_root, item.path)
        materialized: list[tuple[_DeferredIqWrite, str]] = []
        for item in items:
            relative_path = _safe_atomic_artifact_write(
                self.report_root,
                item.path,
                item.raw,
            )
            materialized.append((item, relative_path))
        for item, relative_path in materialized:
            item.frame[item.path_field] = relative_path

    def flush_unconditional(self) -> None:
        unconditional = [item for item in self.pending if not item.failure_only]
        self._flush_items(unconditional)
        self.pending = [item for item in self.pending if item.failure_only]
        self.pending_bytes = sum(len(item.raw) for item in self.pending)

    def flush(self) -> None:
        self._flush_items(self.pending)
        self.discard()

    def discard(self) -> None:
        self.pending.clear()
        self.pending_bytes = 0


@dataclass
class _MatrixFailureIqCapture:
    raw: bytes
    frame: dict[str, Any]
    role: str
    mode: str
    stage: str
    level_index: int | None
    frame_index: int | None
    ordinal: int | None = None


@dataclass
class _MatrixFailureIqLedger:
    """Bound accepted matrix IQ in RAM and materialize it only on failure."""

    output_dir: Path
    planned_accepted_frames: int
    expected_frame_bytes: int
    maximum_bytes: int = _MATRIX_FAILURE_IQ_LIMIT_BYTES
    accepted: list[_MatrixFailureIqCapture] = field(default_factory=list)
    current: _MatrixFailureIqCapture | None = None
    accepted_bytes: int = 0
    next_ordinal: int = 0
    mode: str = "unassigned"
    stage: str = "unassigned"
    level_index: int | None = None
    frame_index: int | None = None
    finalized: bool = False

    def __post_init__(self) -> None:
        self.output_dir = Path(os.path.abspath(self.output_dir))

    @property
    def preflight_bytes(self) -> int:
        return (self.planned_accepted_frames + 1) * self.expected_frame_bytes

    def set_context(
        self,
        *,
        mode: str,
        stage: str,
        level_index: int | None,
        frame_index: int | None,
    ) -> None:
        self.mode = mode
        self.stage = stage
        self.level_index = level_index
        self.frame_index = frame_index

    def observe(self, raw: bytes, frame: dict[str, Any]) -> None:
        """Hold the latest capture as the single possible offending frame."""

        if self.finalized:
            raise RuntimeError("matrix failure-IQ ledger is already finalized")
        payload_bytes = len(raw)
        prior_bytes = len(self.current.raw) if self.current is not None else 0
        projected = self.accepted_bytes - prior_bytes + payload_bytes
        if projected > self.maximum_bytes:
            raise _EvidenceInvalidWithDetails(
                "matrix failure IQ evidence exceeded its in-memory bound",
                {
                    "kind": "matrix_failure_iq_bound_exceeded",
                    "maximum_bytes": self.maximum_bytes,
                    "retained_bytes": self.accepted_bytes,
                    "replaced_current_bytes": prior_bytes,
                    "requested_bytes": payload_bytes,
                    "mode": self.mode,
                    "capture_stage": self.stage,
                    "level_index": self.level_index,
                    "frame_index": self.frame_index,
                    "captured_frame": frame,
                },
            )
        payload = bytes(raw)
        self.accepted_bytes = projected
        self.current = _MatrixFailureIqCapture(
            raw=payload,
            frame=frame,
            role="offending_capture",
            mode=self.mode,
            stage=self.stage,
            level_index=self.level_index,
            frame_index=self.frame_index,
        )

    def accept_current(self) -> None:
        if self.current is None:
            raise RuntimeError("matrix failure-IQ ledger has no current capture")
        self.current.role = "accepted_measurement"
        self.current.ordinal = self.next_ordinal
        self.next_ordinal += 1
        self.accepted.append(self.current)
        self.current = None

    def discard_current(self) -> None:
        if self.current is not None:
            self.accepted_bytes -= len(self.current.raw)
            self.current = None

    def release_accepted_frames(self, frames: Sequence[Mapping[str, Any]]) -> None:
        identities = {id(frame) for frame in frames}
        retained: list[_MatrixFailureIqCapture] = []
        for item in self.accepted:
            if id(item.frame) in identities:
                self.accepted_bytes -= len(item.raw)
            else:
                retained.append(item)
        self.accepted = retained

    def _capture_path(self, item: _MatrixFailureIqCapture) -> Path:
        role = "accepted" if item.role == "accepted_measurement" else "offending"
        ordinal = item.ordinal if item.ordinal is not None else self.next_ordinal
        level = "none" if item.level_index is None else f"{item.level_index:03d}"
        frame = "none" if item.frame_index is None else f"{item.frame_index:03d}"
        return (
            self.output_dir
            / "failure-iq"
            / (f"{role}-{ordinal:04d}-{item.mode}-level{level}-frame{frame}.cs16")
        )

    def flush_failure(self, *, trigger: Mapping[str, Any]) -> dict[str, Any]:
        if self.finalized:
            raise RuntimeError("matrix failure-IQ ledger was finalized twice")
        captures = [*self.accepted]
        if self.current is not None:
            captures.append(self.current)
        capture_paths = [self._capture_path(item) for item in captures]
        manifest_path = self.output_dir / "failure-iq-manifest.json"
        for path in (*capture_paths, manifest_path):
            _validate_safe_artifact_destination(self.output_dir, path)
        entries: list[dict[str, Any]] = []
        materialized: list[tuple[_MatrixFailureIqCapture, str]] = []
        for item, path in zip(captures, capture_paths, strict=True):
            relative_path = _safe_atomic_artifact_write(
                self.output_dir,
                path,
                item.raw,
            )
            materialized.append((item, relative_path))
            entries.append(
                {
                    "ordinal": len(entries),
                    "role": item.role,
                    "mode": item.mode,
                    "capture_stage": item.stage,
                    "level_index": item.level_index,
                    "frame_index": item.frame_index,
                    "relative_path": relative_path,
                    "bytes": len(item.raw),
                    "sha256": hashlib.sha256(item.raw).hexdigest(),
                }
            )
        for item, relative_path in materialized:
            item.frame["failure_iq_path"] = relative_path
        manifest = {
            "schema": _MATRIX_FAILURE_IQ_SCHEMA,
            "maximum_bytes": self.maximum_bytes,
            "tandem_detail_maximum_bytes": _TANDEM_DEFERRED_IQ_LIMIT_BYTES,
            "preflight": {
                "planned_accepted_frames": self.planned_accepted_frames,
                "reserved_offending_frames": 1,
                "expected_frame_bytes": self.expected_frame_bytes,
                "required_bytes": self.preflight_bytes,
            },
            "trigger": dict(trigger),
            "retained_bytes": sum(int(item["bytes"]) for item in entries),
            "entries": entries,
        }
        manifest_payload = (
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        manifest_relative_path = _safe_atomic_artifact_write(
            self.output_dir,
            manifest_path,
            manifest_payload,
        )
        manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest()
        self.finalized = True
        return {
            **manifest,
            "manifest_relative_path": manifest_relative_path,
            "manifest_sha256": manifest_sha256,
        }

    def discard(self) -> None:
        self.accepted.clear()
        self.current = None
        self.accepted_bytes = 0
        self.finalized = True


@dataclass
class _TandemCaptureSession:
    """Mutable execution state shared by priming, settling, and measurement."""

    output_dir: Path
    continuity: _TandemContinuity = field(default_factory=_TandemContinuity)
    deferred: _DeferredTandemWrites = field(default_factory=_DeferredTandemWrites)
    stage: str = "priming_settle"
    level_index: int | None = None
    measurement_attempt: int | None = None
    measurement_frame_index: int | None = None
    minimum_drain_override: int | None = None
    pending_cell: dict[str, Any] | None = None
    cell_capture_trace: list[dict[str, Any]] = field(default_factory=list)
    recovery_settle_trace: list[dict[str, Any]] = field(default_factory=list)
    measurement_attempts: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.deferred.report_root = self.output_dir

    def begin_cell(self, level_index: int, cell: dict[str, Any]) -> None:
        self.stage = "cell_settle"
        self.level_index = level_index
        self.measurement_attempt = None
        self.measurement_frame_index = None
        self.minimum_drain_override = None
        self.pending_cell = cell
        self.cell_capture_trace = []
        self.recovery_settle_trace = []
        self.measurement_attempts = []


_ACTIVE_TANDEM_SESSION: ContextVar[_TandemCaptureSession | None] = ContextVar(
    "tandem_quality_capture_session", default=None
)
_ACTIVE_MATRIX_FAILURE_IQ: ContextVar[_MatrixFailureIqLedger | None] = ContextVar(
    "tandem_quality_matrix_failure_iq", default=None
)


@dataclass(frozen=True)
class TandemQualityOptions:
    """All inputs that materially affect one reproducible matrix."""

    tx_gain_trajectory_db: tuple[float, ...]
    physical_attenuation_db: float
    center_frequency_hz: int = 915_000_000
    sample_rate_hz: int = 2_500_000
    samples_per_channel: int = 65_536
    tone_hz: int = 100_000
    dds_scale: float = 1.0
    manual_gain_db: float = 40.0
    native_gain_control_modes: tuple[str, ...] = DEFAULT_NATIVE_GAIN_CONTROL_MODES
    tandem_low_power_threshold: int = 20
    tandem_large_lmt_overload_threshold: int = 58
    tandem_large_adc_overload_threshold: int = 35
    tandem_small_adc_overload_threshold: int = 34
    tandem_power_measurement_samples: int = 1_024
    tandem_low_power_dwell_periods: int = 3
    tandem_cooldown_periods: int = 16
    kernel_buffers: int = 2
    stable_frames: int = 3
    measurement_frames: int = 3
    max_settle_frames: int = 64
    settle_timeout_seconds: float = 2.5
    max_seconds: float = 180.0
    output_dir: Path = Path("build/radio-hardware/tandem-agc-quality")
    profile: str = "smoke"
    save_iq: bool = False
    thresholds: ToneQualityThresholds = field(default_factory=ToneQualityThresholds)
    native_fast_max_tone_dbfs: float = NATIVE_FAST_MAX_TONE_DBFS

    @property
    def strongest_tx_gain_db(self) -> float:
        return max(self.tx_gain_trajectory_db)

    @property
    def weakest_tx_gain_db(self) -> float:
        return min(self.tx_gain_trajectory_db)

    @property
    def minimum_effective_attenuation_db(self) -> float:
        return self.physical_attenuation_db - self.strongest_tx_gain_db


def native_mode_name(gain_control_mode: str) -> str:
    """Return the stable report-cell name for one native AD9361 mode."""

    if gain_control_mode not in NATIVE_GAIN_CONTROL_MODES:
        raise ValueError(f"unsupported native gain-control mode {gain_control_mode!r}")
    return f"native_{gain_control_mode}"


def native_gain_control_mode(mode: str) -> str | None:
    """Map a report-cell name back to its native IIO gain-control value."""

    prefix = "native_"
    if not mode.startswith(prefix):
        return None
    gain_control_mode = mode[len(prefix) :]
    if gain_control_mode not in NATIVE_GAIN_CONTROL_MODES:
        raise ValueError(f"unsupported native quality mode {mode!r}")
    return gain_control_mode


def tone_quality_thresholds_for_mode(
    options: TandemQualityOptions, mode: str
) -> ToneQualityThresholds:
    """Return the exact amplitude policy for one steady-state comparison mode."""

    if mode in (MODE_MANUAL, MODE_TANDEM):
        return options.thresholds
    native_gain_control_mode(mode)
    if mode == MODE_NATIVE_FAST:
        return replace(
            options.thresholds,
            max_tone_dbfs=options.native_fast_max_tone_dbfs,
        )
    return options.thresholds


def _ordinary_iio_mode(mode: str) -> str:
    if mode == MODE_MANUAL:
        return "manual"
    gain_control_mode = native_gain_control_mode(mode)
    if gain_control_mode is None:
        raise ValueError(f"quality mode {mode!r} is not an ordinary-IIO mode")
    return gain_control_mode


def quality_modes(options: TandemQualityOptions) -> tuple[str, ...]:
    """Return the deterministic mode-cell order for one matrix."""

    return (
        MODE_MANUAL,
        *(native_mode_name(mode) for mode in options.native_gain_control_modes),
        MODE_TANDEM,
    )


def parse_native_gain_control_modes(value: str) -> tuple[str, ...]:
    """Parse a comma-separated, ordered native-mode selection."""

    modes = tuple(item.strip() for item in value.split(","))
    if not modes or any(not mode for mode in modes):
        raise ValueError("native gain-control mode list contains an empty cell")
    if len(set(modes)) != len(modes):
        raise ValueError("native gain-control modes cannot contain duplicates")
    for mode in modes:
        native_mode_name(mode)
    return modes


def expected_tandem_gain_table(center_frequency_hz: int) -> TandemGainTable:
    """Derive the kernel's full-gain-table selection for a common RX/TX LO."""

    if isinstance(center_frequency_hz, bool) or not isinstance(
        center_frequency_hz, int
    ):
        raise TypeError("center frequency must be an integer number of Hz")
    if not (
        MIN_COMMON_CENTER_FREQUENCY_HZ
        <= center_frequency_hz
        <= MAX_COMMON_CENTER_FREQUENCY_HZ
    ):
        raise ValueError(
            "common RX/TX center frequency must be in "
            f"[{MIN_COMMON_CENTER_FREQUENCY_HZ}, "
            f"{MAX_COMMON_CENTER_FREQUENCY_HZ}] Hz"
        )
    if center_frequency_hz <= 1_300_000_000:
        return TandemGainTable.MHZ_200_1300
    if center_frequency_hz <= 4_000_000_000:
        return TandemGainTable.MHZ_1300_4000
    return TandemGainTable.MHZ_4000_6000


def default_tx_trajectory(profile: str) -> tuple[float, ...]:
    """Return a deterministic up/down loudness trajectory."""

    if profile == "smoke":
        return (-61.0, -45.0, -30.0, -45.0, -61.0)
    if profile == "full":
        return (
            -61.0,
            -55.0,
            -50.0,
            -45.0,
            -40.0,
            -35.0,
            -30.0,
            -35.0,
            -40.0,
            -45.0,
            -50.0,
            -55.0,
            -61.0,
        )
    raise ValueError(f"unknown tandem quality profile {profile!r}")


def parse_tx_trajectory(value: str) -> tuple[float, ...]:
    """Parse comma-separated TX hardware gains without accepting ambiguity."""

    try:
        result = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise ValueError("TX trajectory must be comma-separated dB values") from exc
    if not result or any(not math.isfinite(item) for item in result):
        raise ValueError("TX trajectory must contain finite dB values")
    return result


def _select_tandem_priming_gain(
    levels: Sequence[float],
) -> tuple[float, list[float]]:
    """Select and expose the deterministic AUTO-conditioning trajectory rung."""

    distinct_levels = sorted({float(level) for level in levels})
    if not distinct_levels:
        raise ValueError("cannot select a tandem priming gain from an empty trajectory")
    return float(statistics.median(distinct_levels)), distinct_levels


def validate_options(options: TandemQualityOptions) -> None:
    """Reject an unsafe or non-diagnostic experiment before any radio write."""

    expected_tandem_gain_table(options.center_frequency_hz)
    native_modes = options.native_gain_control_modes
    if isinstance(native_modes, (str, bytes)) or not native_modes:
        raise ValueError("native gain-control mode list cannot be empty")
    if len(set(native_modes)) != len(native_modes):
        raise ValueError("native gain-control modes cannot contain duplicates")
    for native_mode in native_modes:
        native_mode_name(native_mode)
    if options.native_fast_max_tone_dbfs != NATIVE_FAST_MAX_TONE_DBFS:
        raise ValueError(
            "native fast-attack maximum tone level must remain exactly -2.0 dBFS"
        )
    levels = options.tx_gain_trajectory_db
    if any(not math.isfinite(level) for level in levels):
        raise ValueError("TX trajectory must contain only finite gains")
    if len(levels) < 3:
        raise ValueError("TX trajectory needs at least weak, strong, and return levels")
    if levels[0] != levels[-1]:
        raise ValueError("TX trajectory must return to its starting level")
    if not TX_MUTE_DB <= min(levels) <= max(levels) <= 0.0:
        raise ValueError("all TX gains must be in [-89.75, 0] dB")
    priming_gain_db, _distinct_levels = _select_tandem_priming_gain(levels)
    if not TX_MUTE_DB <= priming_gain_db <= options.strongest_tx_gain_db:
        raise ValueError("tandem priming gain exceeds the authorized TX trajectory")
    deltas = tuple(current - previous for previous, current in pairwise(levels))
    if not any(delta > 0 for delta in deltas) or not any(delta < 0 for delta in deltas):
        raise ValueError("TX trajectory must contain both rising and falling loudness")
    if not math.isfinite(options.physical_attenuation_db):
        raise ValueError("physical attenuation must be finite")
    if options.physical_attenuation_db < 0:
        raise ValueError("physical attenuation cannot be negative")
    if options.minimum_effective_attenuation_db < 30.0:
        raise ValueError(
            "physical attenuation plus strongest TX backoff must be at least 30 dB"
        )
    if options.sample_rate_hz <= 2 * (abs(options.tone_hz) + 25_000):
        raise ValueError("sample rate does not contain the tone search band")
    if options.samples_per_channel < 8_192:
        raise ValueError("quality frames need at least 8192 samples per channel")
    if not math.isfinite(options.dds_scale) or not 0.0 < options.dds_scale <= 1.0:
        raise ValueError("DDS scale must be in (0, 1]")
    if not math.isfinite(options.manual_gain_db) or not (
        0.0 <= options.manual_gain_db <= 62.0
    ):
        raise ValueError("manual gain must be in [0, 62] dB")
    if options.manual_gain_db != int(options.manual_gain_db):
        raise ValueError("manual gain must be an integer for tandem request parity")
    detector_thresholds = (
        options.tandem_low_power_threshold,
        options.tandem_large_lmt_overload_threshold,
        options.tandem_large_adc_overload_threshold,
        options.tandem_small_adc_overload_threshold,
    )
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in detector_thresholds
    ):
        raise ValueError("tandem detector thresholds must be integers")
    if not 0 <= options.tandem_low_power_threshold <= 0x7F:
        raise ValueError("tandem low-power threshold must be in [0, 127]")
    if not 0 <= options.tandem_large_lmt_overload_threshold <= 0x3F:
        raise ValueError("tandem large-LMT threshold must be in [0, 63]")
    if not (
        0
        <= options.tandem_small_adc_overload_threshold
        <= options.tandem_large_adc_overload_threshold
        <= 0xFF
    ):
        raise ValueError(
            "tandem ADC thresholds must satisfy 0 <= small <= large <= 255"
        )
    timing_values = (
        options.tandem_power_measurement_samples,
        options.tandem_low_power_dwell_periods,
        options.tandem_cooldown_periods,
    )
    if any(
        isinstance(value, bool) or not isinstance(value, int) for value in timing_values
    ):
        raise ValueError("tandem power-window, dwell, and cooldown must be integers")
    if not 1 <= options.tandem_power_measurement_samples <= (1 << 20) - 1:
        raise ValueError("tandem power-measurement samples must be in [1, 1048575]")
    if not 1 <= options.tandem_low_power_dwell_periods <= 0xFF:
        raise ValueError("tandem low-power dwell periods must be in [1, 255]")
    if not 0 <= options.tandem_cooldown_periods <= 0xFF:
        raise ValueError("tandem cooldown periods must be in [0, 255]")
    maximum_events = maximum_tandem_events_per_frame(
        mode=TandemMode.AUTO,
        samples_per_channel=options.samples_per_channel,
        power_measurement_samples=options.tandem_power_measurement_samples,
        cooldown_periods=options.tandem_cooldown_periods,
    )
    if maximum_events > 64:
        raise ValueError(
            "tandem timing can produce "
            f"{maximum_events} events per frame, exceeding metadata capacity 64"
        )
    if options.kernel_buffers <= 0:
        raise ValueError("kernel buffer count must be positive")
    if options.stable_frames < 2 or options.measurement_frames <= 0:
        raise ValueError("stable/measurement frame counts are too small")
    if options.max_settle_frames < options.kernel_buffers + options.stable_frames:
        raise ValueError("settle-frame bound cannot drain and prove stability")
    if not all(
        math.isfinite(value)
        for value in (options.settle_timeout_seconds, options.max_seconds)
    ):
        raise ValueError("experiment deadlines must be finite")
    if options.settle_timeout_seconds <= 0 or options.max_seconds <= 0:
        raise ValueError("experiment deadlines must be positive")


def _exception_text(error: BaseException) -> str:
    number = getattr(error, "errno", None)
    suffix = f" errno={number}" if number is not None else ""
    error_type = (
        "EvidenceInvalid"
        if isinstance(error, EvidenceInvalid)
        else type(error).__name__
    )
    return f"{error_type}{suffix}: {error}"


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _direction(levels: Sequence[float], index: int) -> str:
    if index == 0:
        return "initial"
    if levels[index] > levels[index - 1]:
        return "louder"
    if levels[index] < levels[index - 1]:
        return "quieter"
    return "same"


@dataclass(frozen=True)
class _OrdinaryGainBand:
    """Gain evidence accumulated across a genuinely stable frame window."""

    mode: str
    minimum_db: tuple[float, float]
    maximum_db: tuple[float, float]
    reference_db: tuple[float, float]
    frame_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "minimum_db": list(self.minimum_db),
            "maximum_db": list(self.maximum_db),
            "reference_db": list(self.reference_db),
            "span_db": [
                self.maximum_db[channel] - self.minimum_db[channel]
                for channel in (0, 1)
            ],
            "frame_count": self.frame_count,
        }


def _extend_gain_band(
    states: Sequence[Mapping[str, Sequence[Any]]],
    *,
    expected_mode: str,
    prior: _OrdinaryGainBand | None = None,
) -> _OrdinaryGainBand | None:
    """Extend a stable band, rejecting cumulative drift hidden by pairwise checks."""

    if not states:
        raise ValueError("gain-band extension needs at least one state")
    if prior is not None and prior.mode != expected_mode:
        raise ValueError("gain-band mode differs from the requested mode")

    parsed: list[tuple[float, float]] = []
    for state in states:
        if tuple(state["modes"]) != (expected_mode, expected_mode):
            return None
        gains = tuple(float(value) for value in state["gains_db"])
        if len(gains) != 2 or any(not math.isfinite(value) for value in gains):
            return None
        parsed.append((gains[0], gains[1]))

    minimum = [min(values[channel] for values in parsed) for channel in (0, 1)]
    maximum = [max(values[channel] for values in parsed) for channel in (0, 1)]
    if prior is not None:
        minimum = [
            min(minimum[channel], prior.minimum_db[channel]) for channel in (0, 1)
        ]
        maximum = [
            max(maximum[channel], prior.maximum_db[channel]) for channel in (0, 1)
        ]

    tolerance_db = 0.0 if expected_mode == "manual" else 1.0
    if any(maximum[channel] - minimum[channel] > tolerance_db for channel in (0, 1)):
        return None
    return _OrdinaryGainBand(
        mode=expected_mode,
        minimum_db=(minimum[0], minimum[1]),
        maximum_db=(maximum[0], maximum[1]),
        reference_db=parsed[-1],
        frame_count=(0 if prior is None else prior.frame_count) + 1,
    )


def _event_dict(event: Any) -> dict[str, Any]:
    return {
        **asdict(event),
        "direction": int(event.direction),
        "direction_name": event.direction.name.lower(),
        "reason": int(event.reason),
        "reason_name": event.reason.name.lower(),
    }


def _metadata_dict(metadata: TandemFrameMetadata) -> dict[str, Any]:
    return {
        "stream_id": metadata.stream_id,
        "buffer_sequence": metadata.buffer_sequence,
        "first_sample_sequence": metadata.first_sample_sequence,
        "samples_per_channel": metadata.samples_per_channel,
        "flags": metadata.flags,
        "device_iio_overflow": metadata.device_iio_overflow,
        "observation_count": metadata.observation_count,
        "observation_capacity": metadata.observation_capacity,
        "event_count": metadata.event_count,
        "event_capacity": metadata.event_capacity,
        "observation_overflow_count": metadata.observation_overflow_count,
        "event_overflow_count": metadata.event_overflow_count,
        "ownership_epoch": metadata.ownership_epoch,
        "tandem_state": int(metadata.tandem_state),
        "tandem_state_name": metadata.tandem_state.name.lower(),
        "tandem_transition_count": metadata.tandem_transition_count,
        "gain_table_id": int(metadata.gain_table_id),
        "threshold_provenance": metadata.threshold_provenance,
        "gain_db_range": [metadata.minimum_gain_db, metadata.maximum_gain_db],
        "initial_gain_db": metadata.initial_gain_db,
        "gain_index_range": [
            metadata.minimum_gain_index,
            metadata.maximum_gain_index,
        ],
        "bench_gain_indices": list(metadata.bench_gain_indices),
        "temperature_mdeg_c": metadata.ad9361_temperature_mdeg_c,
        "gain_events": [_event_dict(event) for event in metadata.gain_events],
    }


def _gain_endpoint_is_reachable(
    start: int,
    end: int,
    transitions: int,
    *,
    minimum: int,
    maximum: int,
) -> bool:
    """Return whether exact paired +/-1 steps can join two known endpoints."""

    if transitions < 0 or not minimum <= start <= maximum:
        return False
    if not minimum <= end <= maximum:
        return False
    distance = abs(end - start)
    return distance <= transitions and (transitions - distance) % 2 == 0


def _tandem_continuity_projection(
    metadata: TandemFrameMetadata,
    continuity: _TandemContinuity,
) -> dict[str, int | None]:
    """Project replayable deltas without hiding an ensuing validation failure."""

    previous = continuity.previous
    visible_events = len(metadata.gain_events)
    evidence: dict[str, int | None] = {
        "buffer_delta": None,
        "sample_delta": None,
        "missing_frame_count": 0,
        "transition_count_delta": None,
        "visible_event_count": visible_events,
        "hidden_transition_count": 0,
        "initial_unrepresented_transition_count": 0,
    }
    if previous is None:
        if 0 <= metadata.tandem_transition_count < _UINT32_MODULUS:
            evidence["initial_unrepresented_transition_count"] = (
                metadata.tandem_transition_count - visible_events
            )
        return evidence

    buffer_delta = metadata.buffer_sequence - previous.buffer_sequence
    sample_delta = metadata.first_sample_sequence - previous.first_sample_sequence
    evidence["buffer_delta"] = buffer_delta
    evidence["sample_delta"] = sample_delta
    evidence["missing_frame_count"] = max(0, buffer_delta - 1)
    if (
        0 <= metadata.tandem_transition_count < _UINT32_MODULUS
        and 0 <= previous.tandem_transition_count < _UINT32_MODULUS
    ):
        transition_delta = (
            metadata.tandem_transition_count - previous.tandem_transition_count
        ) % _UINT32_MODULUS
        if transition_delta < _UINT32_HALF_RANGE:
            evidence["transition_count_delta"] = transition_delta
            evidence["hidden_transition_count"] = transition_delta - visible_events
    return evidence


def _validate_tandem_continuity(
    metadata: TandemFrameMetadata,
    frame: dict[str, Any],
    *,
    options: TandemQualityOptions,
    continuity: _TandemContinuity,
) -> None:
    """Reconcile one frame against every earlier frame in this AUTO session."""

    frame["continuity"] = _tandem_continuity_projection(metadata, continuity)
    if metadata.tandem_state is not TandemState.ARMED_AUTO:
        raise EvidenceInvalid("tandem metadata does not prove an AUTO lease")
    if metadata.tandem_fault_flags:
        raise EvidenceInvalid("tandem metadata reports a controller fault")
    if metadata.event_count != len(metadata.gain_events):
        raise EvidenceInvalid("tandem event count differs from decoded events")
    if metadata.rx1_gain_index != metadata.rx2_gain_index:
        raise EvidenceInvalid("tandem endpoint gains are not paired")
    if not 0 <= metadata.tandem_transition_count < _UINT32_MODULUS:
        raise EvidenceInvalid("tandem transition count is outside uint32")
    if (
        metadata.minimum_gain_index > metadata.maximum_gain_index
        or not metadata.minimum_gain_index
        <= metadata.rx1_gain_index
        <= metadata.maximum_gain_index
    ):
        raise EvidenceInvalid("tandem endpoint lies outside its session gain range")

    previous = continuity.previous
    buffer_delta: int | None = None
    sample_delta: int | None = None
    missing_frames = 0
    transition_delta: int | None = None
    hidden_transitions = 0
    initial_unrepresented_transitions = 0
    if previous is not None:
        if metadata.stream_id != previous.stream_id:
            raise EvidenceInvalid("tandem stream changed inside one session")
        if metadata.ownership_epoch != previous.ownership_epoch:
            raise EvidenceInvalid("tandem ownership changed inside one session")
        if metadata.samples_per_channel != previous.samples_per_channel:
            raise EvidenceInvalid("tandem sample count changed inside one session")
        if metadata.gain_table_id is not previous.gain_table_id:
            raise EvidenceInvalid("tandem gain table changed inside one session")
        if metadata.threshold_provenance != previous.threshold_provenance:
            raise EvidenceInvalid(
                "tandem threshold provenance changed inside one session"
            )
        if (
            metadata.minimum_gain_db != previous.minimum_gain_db
            or metadata.maximum_gain_db != previous.maximum_gain_db
            or metadata.initial_gain_db != previous.initial_gain_db
        ):
            raise EvidenceInvalid("tandem gain request changed inside one session")
        if (
            metadata.minimum_gain_index != previous.minimum_gain_index
            or metadata.maximum_gain_index != previous.maximum_gain_index
        ):
            raise EvidenceInvalid("tandem gain-index range changed inside one session")
        buffer_delta = metadata.buffer_sequence - previous.buffer_sequence
        sample_delta = metadata.first_sample_sequence - previous.first_sample_sequence
        if buffer_delta <= 0 or sample_delta <= 0:
            raise EvidenceInvalid("tandem frame counters did not advance")
        if sample_delta % previous.samples_per_channel:
            raise EvidenceInvalid(
                "tandem sample sequence did not advance by whole frames"
            )
        if buffer_delta != sample_delta // previous.samples_per_channel:
            raise EvidenceInvalid("tandem buffer and sample sequence deltas disagree")
        missing_frames = buffer_delta - 1
        transition_delta = _forward_u32_delta(
            metadata.tandem_transition_count,
            previous.tandem_transition_count,
            context="tandem transition count",
        )
        if transition_delta < len(metadata.gain_events):
            raise EvidenceInvalid(
                "tandem frame has more events than its transition-count delta"
            )
        hidden_transitions = transition_delta - len(metadata.gain_events)
        if missing_frames == 0 and hidden_transitions:
            raise EvidenceInvalid(
                "adjacent tandem frames lost transition event evidence"
            )
        maximum_hidden = missing_frames * maximum_tandem_events_per_frame(
            mode=TandemMode.AUTO,
            samples_per_channel=options.samples_per_channel,
            power_measurement_samples=options.tandem_power_measurement_samples,
            cooldown_periods=options.tandem_cooldown_periods,
        )
        if hidden_transitions > maximum_hidden:
            raise EvidenceInvalid(
                "tandem gap contains more hidden transitions than omitted frames "
                "can hold"
            )
    elif metadata.tandem_transition_count < len(metadata.gain_events):
        raise EvidenceInvalid("first tandem frame has more events than transitions")
    else:
        # This is a baseline preceding our first returned IQ frame. It cannot
        # later pay for an event-sequence hole or stimulus response.
        initial_unrepresented_transitions = metadata.tandem_transition_count - len(
            metadata.gain_events
        )

    last_event_sequence = continuity.last_event_sequence
    last_event_sample = continuity.last_event_sample_sequence
    last_event_gain = continuity.last_event_gain_index
    unrepresented_since_event = continuity.unrepresented_since_event
    if previous is not None:
        unrepresented_since_event += hidden_transitions
    frame_start = metadata.first_sample_sequence
    frame_end = frame_start + metadata.samples_per_channel
    event_sequence_holes = 0

    for event_index, event in enumerate(metadata.gain_events):
        context = f"tandem event {event_index}"
        integers = (
            event.sample_sequence,
            event.event_sequence,
            event.flags,
            event.rx1_gain_index,
            event.rx2_gain_index,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) for value in integers
        ):
            raise EvidenceInvalid(f"{context} fields must be integers")
        if not frame_start <= event.sample_sequence < frame_end:
            raise EvidenceInvalid(f"{context} lies outside its IQ frame")
        if not 0 <= event.event_sequence < _UINT32_MODULUS:
            raise EvidenceInvalid(f"{context} sequence is outside uint32")
        if event.rx1_gain_index != event.rx2_gain_index:
            raise EvidenceInvalid(f"{context} endpoint gains are not paired")
        if not (
            metadata.minimum_gain_index
            <= event.rx1_gain_index
            <= metadata.maximum_gain_index
        ):
            raise EvidenceInvalid(f"{context} gain lies outside the session range")
        try:
            direction = event.direction
            _reason = event.reason
        except ValueError as error:
            raise EvidenceInvalid(f"{context} has invalid flags") from error
        if direction not in (
            TandemEventDirection.INCREASE,
            TandemEventDirection.DECREASE,
        ):
            raise EvidenceInvalid(f"{context} has an invalid direction")
        step = 1 if direction is TandemEventDirection.INCREASE else -1
        if last_event_sequence is not None:
            sequence_delta = _forward_u32_delta(
                event.event_sequence,
                last_event_sequence,
                context="tandem event sequence",
            )
            if sequence_delta == 0:
                raise EvidenceInvalid("tandem event sequence did not advance")
            sequence_hole = sequence_delta - 1
            if sequence_hole != unrepresented_since_event:
                raise EvidenceInvalid(
                    "tandem event-sequence hole does not match locally hidden "
                    "transitions"
                )
            if sequence_hole:
                event_sequence_holes += 1
        if last_event_sample is not None and event.sample_sequence < last_event_sample:
            raise EvidenceInvalid("tandem events are not globally sample ordered")

        anchor_gain: int | None = None
        transitions_to_event = 0
        if last_event_gain is not None:
            anchor_gain = last_event_gain
            transitions_to_event = unrepresented_since_event
        elif previous is not None:
            anchor_gain = previous.rx1_gain_index
            transitions_to_event = hidden_transitions
        if anchor_gain is not None:
            gain_before_event = event.rx1_gain_index - step
            if not _gain_endpoint_is_reachable(
                anchor_gain,
                gain_before_event,
                transitions_to_event,
                minimum=metadata.minimum_gain_index,
                maximum=metadata.maximum_gain_index,
            ):
                qualifier = (
                    "exact paired +/-1 endpoint"
                    if transitions_to_event == 0
                    else "gap-accounted paired +/-1 endpoint"
                )
                raise EvidenceInvalid(f"tandem event did not reconcile an {qualifier}")
        unrepresented_since_event = 0
        last_event_gain = event.rx1_gain_index
        last_event_sequence = event.event_sequence
        last_event_sample = event.sample_sequence

    if metadata.gain_events:
        if metadata.bench_gain_indices != (last_event_gain, last_event_gain):
            raise EvidenceInvalid("tandem endpoint differs from its final event")
    elif previous is not None:
        assert transition_delta is not None
        if not _gain_endpoint_is_reachable(
            previous.rx1_gain_index,
            metadata.rx1_gain_index,
            transition_delta,
            minimum=metadata.minimum_gain_index,
            maximum=metadata.maximum_gain_index,
        ):
            raise EvidenceInvalid("tandem endpoint cannot reconcile its transitions")

    evidence = {
        "buffer_delta": buffer_delta,
        "sample_delta": sample_delta,
        "missing_frame_count": missing_frames,
        "transition_count_delta": transition_delta,
        "visible_event_count": len(metadata.gain_events),
        "hidden_transition_count": hidden_transitions,
        "initial_unrepresented_transition_count": (initial_unrepresented_transitions),
        "cumulative_missing_frame_count": (
            continuity.missing_frame_count + missing_frames
        ),
        "cumulative_hidden_transition_count": (
            continuity.hidden_transition_count + hidden_transitions
        ),
        "cumulative_event_sequence_hole_count": (
            continuity.event_sequence_hole_count + event_sequence_holes
        ),
    }
    frame["continuity"] = evidence
    continuity.penultimate_frame = continuity.previous_frame
    continuity.previous_frame = frame
    continuity.previous = metadata
    continuity.last_event_sequence = last_event_sequence
    continuity.last_event_sample_sequence = last_event_sample
    continuity.last_event_gain_index = last_event_gain
    continuity.unrepresented_since_event = unrepresented_since_event
    continuity.missing_frame_count += missing_frames
    continuity.hidden_transition_count += hidden_transitions
    continuity.event_sequence_hole_count += event_sequence_holes
    continuity.last_frame_evidence = evidence


def _tag_tandem_frame(
    frame: dict[str, Any],
    *,
    session: _TandemCaptureSession,
) -> int:
    ordinal = session.continuity.next_capture_ordinal
    session.continuity.next_capture_ordinal += 1
    frame["capture_ordinal"] = ordinal
    frame["capture_stage"] = session.stage
    if session.level_index is not None:
        frame["level_index"] = session.level_index
    if session.measurement_attempt is not None:
        frame["measurement_attempt"] = session.measurement_attempt
    if session.measurement_frame_index is not None:
        frame["measurement_frame_index"] = session.measurement_frame_index
    return ordinal


def _queue_invalid_tandem_capture(
    raw: bytes,
    frame: dict[str, Any],
    *,
    session: _TandemCaptureSession,
    ordinal: int,
) -> None:
    scope = "priming" if session.level_index is None else f"level{session.level_index}"
    path = session.output_dir / (
        f"{MODE_TANDEM}-{scope}-capture{ordinal}-continuity-invalid.cs16"
    )
    session.deferred.queue(
        raw,
        frame,
        path,
        path_field="diagnostic_iq_path",
    )
    if session.level_index is not None:
        session.cell_capture_trace.append(frame)


def _queue_abandoned_tandem_measurements(
    accepted_raw: Sequence[bytes],
    accepted_frames: Sequence[dict[str, Any]],
    *,
    output_dir: Path,
    level_index: int,
    attempt_index: int,
    session: _TandemCaptureSession,
) -> None:
    """Retain every earlier IQ frame when its whole attempt is abandoned."""

    writes = [
        _DeferredIqWrite(
            path=(
                output_dir
                / (
                    f"{MODE_TANDEM}-level{level_index}-attempt{attempt_index}-"
                    f"frame{frame_index}-abandoned.cs16"
                )
            ),
            raw=payload,
            frame=frame,
            path_field="diagnostic_iq_path",
            failure_only=True,
        )
        for frame_index, (payload, frame) in enumerate(
            zip(accepted_raw, accepted_frames, strict=True)
        )
    ]
    session.deferred.queue_batch(writes)


def _queue_transition_tandem_detail(
    accepted_raw: Sequence[bytes],
    accepted_frames: Sequence[dict[str, Any]],
    *,
    offending_raw: bytes,
    offending_frame: dict[str, Any],
    output_dir: Path,
    level_index: int,
    attempt_index: int,
    frame_index: int,
    session: _TandemCaptureSession,
) -> None:
    """Atomically transfer a rejected attempt, including its current frame."""

    writes = [
        _DeferredIqWrite(
            path=(
                output_dir
                / (
                    f"{MODE_TANDEM}-level{level_index}-attempt{attempt_index}-"
                    f"frame{accepted_index}-abandoned.cs16"
                )
            ),
            raw=payload,
            frame=accepted_frame,
            path_field="diagnostic_iq_path",
            failure_only=True,
        )
        for accepted_index, (payload, accepted_frame) in enumerate(
            zip(accepted_raw, accepted_frames, strict=True)
        )
    ]
    writes.append(
        _DeferredIqWrite(
            path=(
                output_dir
                / (
                    f"{MODE_TANDEM}-level{level_index}-attempt{attempt_index}-"
                    f"frame{frame_index}-rejected.cs16"
                )
            ),
            raw=offending_raw,
            frame=offending_frame,
            path_field="diagnostic_iq_path",
            failure_only=True,
        )
    )
    session.deferred.queue_batch(writes)


def _capture_tandem(
    radio: Issue46Radio,
    buffer: Any,
    *,
    options: TandemQualityOptions,
    session: _TandemCaptureSession,
) -> tuple[bytes, TandemFrameMetadata, dict[str, Any]]:
    """Capture and chronologically bind one tandem frame to the active session."""

    matrix_ledger = _ACTIVE_MATRIX_FAILURE_IQ.get()
    if matrix_ledger is not None:
        matrix_ledger.set_context(
            mode=MODE_TANDEM,
            stage=session.stage,
            level_index=session.level_index,
            frame_index=session.measurement_frame_index,
        )
    try:
        raw, parsed, frame = _capture(
            radio,
            buffer,
            options=options,
            metadata=True,
        )
    except _CapturedFrameInvalid as error:
        frame = error.frame
        ordinal = _tag_tandem_frame(frame, session=session)
        frame["continuity_error"] = _exception_text(error)
        _queue_invalid_tandem_capture(
            error.raw,
            frame,
            session=session,
            ordinal=ordinal,
        )
        raise _EvidenceInvalidWithDetails(
            str(error),
            {
                "kind": "tandem_capture_invalid",
                "mode": MODE_TANDEM,
                "level_index": session.level_index,
                "capture_stage": session.stage,
                "prior_frame": session.continuity.previous_frame,
                "current_frame": frame,
                "pending_cell": session.pending_cell,
                "capture_trace": list(session.cell_capture_trace),
            },
        ) from error
    assert parsed is not None
    ordinal = _tag_tandem_frame(frame, session=session)
    prior = session.continuity.previous_frame
    try:
        _validate_tandem_continuity(
            parsed,
            frame,
            options=options,
            continuity=session.continuity,
        )
    except EvidenceInvalid as error:
        frame["continuity_error"] = _exception_text(error)
        _queue_invalid_tandem_capture(
            raw,
            frame,
            session=session,
            ordinal=ordinal,
        )
        raise _EvidenceInvalidWithDetails(
            str(error),
            {
                "kind": "tandem_metadata_continuity_invalid",
                "mode": MODE_TANDEM,
                "level_index": session.level_index,
                "capture_stage": session.stage,
                "prior_frame": prior,
                "current_frame": frame,
                "pending_cell": session.pending_cell,
                "capture_trace": list(session.cell_capture_trace),
            },
        ) from error
    if session.level_index is not None:
        session.cell_capture_trace.append(frame)
    return raw, parsed, frame


def _capture(
    radio: Issue46Radio,
    buffer: Any,
    *,
    options: TandemQualityOptions,
    metadata: bool,
) -> tuple[bytes, TandemFrameMetadata | None, dict[str, Any]]:
    raw, raw_metadata, refill_ns = radio.capture_iq(
        buffer,
        metadata=metadata,
        samples_per_channel=options.samples_per_channel,
    )
    frame: dict[str, Any] = {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "iq_bytes": len(raw),
        "refill_monotonic_ns": refill_ns,
    }
    matrix_ledger = _ACTIVE_MATRIX_FAILURE_IQ.get()
    if matrix_ledger is not None:
        matrix_ledger.observe(raw, frame)
    parsed: TandemFrameMetadata | None = None
    try:
        parsed = (
            raw_metadata
            if isinstance(raw_metadata, TandemFrameMetadata)
            else (
                parse_tandem_frame_metadata(raw_metadata)
                if raw_metadata is not None
                else None
            )
        )
        if metadata and parsed is None:
            raise EvidenceInvalid("tandem capture returned no metadata")
        if parsed is not None:
            if parsed.samples_per_channel != options.samples_per_channel:
                raise EvidenceInvalid("tandem metadata sample count differs from IQ")
            if parsed.iq_payload_bytes != len(raw):
                raise EvidenceInvalid(
                    "tandem metadata IQ byte count differs from payload"
                )
            if parsed.enabled_scan_mask != 0x0F or parsed.channel_count != 2:
                raise EvidenceInvalid(
                    "tandem metadata does not describe dual complex RX"
                )
            unsafe_flags = parsed.flags & TANDEM_UNSAFE_FLAGS
            if unsafe_flags:
                raise EvidenceInvalid(
                    f"tandem metadata reports unsafe flags 0x{unsafe_flags:08x}"
                )
            if parsed.observation_overflow_count or parsed.event_overflow_count:
                raise EvidenceInvalid("tandem metadata record capacity overflowed")
            expected_gain_table = expected_tandem_gain_table(
                options.center_frequency_hz
            )
            if parsed.gain_table_id is not expected_gain_table:
                raise EvidenceInvalid(
                    f"{options.center_frequency_hz} Hz tandem session selected gain "
                    f"table {int(parsed.gain_table_id)}, expected "
                    f"{int(expected_gain_table)}"
                )
            if (
                parsed.minimum_gain_db != 0
                or parsed.maximum_gain_db != 62
                or parsed.initial_gain_db != int(options.manual_gain_db)
            ):
                raise EvidenceInvalid(
                    "tandem metadata differs from requested gain range"
                )
            if parsed.ad9361_temperature_mdeg_c is not None and not (
                -40_000 <= parsed.ad9361_temperature_mdeg_c <= 125_000
            ):
                raise EvidenceInvalid(
                    "AD9361 temperature is outside its physical range"
                )
            frame["metadata"] = _metadata_dict(parsed)
    except Exception as error:
        if isinstance(parsed, TandemFrameMetadata):
            frame.setdefault("metadata", _metadata_dict(parsed))
        raise _CapturedFrameInvalid(
            str(error),
            raw=raw,
            frame=frame,
        ) from error
    return raw, parsed, frame


def _settle_ordinary(
    radio: Issue46Radio,
    buffer: Any,
    *,
    mode: str,
    options: TandemQualityOptions,
) -> tuple[list[dict[str, Any]], _OrdinaryGainBand]:
    expected_mode = _ordinary_iio_mode(mode)
    trace: list[dict[str, Any]] = []
    stable = 0
    stable_band: _OrdinaryGainBand | None = None
    deadline = time.monotonic() + options.settle_timeout_seconds
    minimum_drain = options.kernel_buffers + 1
    for attempt in range(1, options.max_settle_frames + 1):
        matrix_ledger = _ACTIVE_MATRIX_FAILURE_IQ.get()
        if matrix_ledger is not None:
            matrix_ledger.set_context(
                mode=mode,
                stage="cell_settle",
                level_index=matrix_ledger.level_index,
                frame_index=attempt - 1,
            )
        before = radio.read_rx_state()
        _raw, _metadata, frame = _capture(
            radio, buffer, options=options, metadata=False
        )
        after = radio.read_rx_state()
        current_band = _extend_gain_band((before, after), expected_mode=expected_mode)
        if attempt <= minimum_drain or current_band is None:
            stable = 0
            stable_band = None
        else:
            extended = (
                _extend_gain_band(
                    (before, after), expected_mode=expected_mode, prior=stable_band
                )
                if stable_band is not None
                else current_band
            )
            if extended is None:
                # This frame is internally stable but moved outside the prior
                # window. It starts a new candidate window at one frame.
                stable_band = current_band
                stable = 1
            else:
                stable_band = extended
                stable += 1
        trace.append(
            {
                "attempt": attempt,
                "before": before,
                "after": after,
                "stable_run": stable,
                "candidate_gain_band": (
                    stable_band.to_dict() if stable_band is not None else None
                ),
                **frame,
            }
        )
        if stable >= options.stable_frames:
            assert stable_band is not None
            return trace, stable_band
        if time.monotonic() >= deadline:
            break
    raise EvidenceInvalid(
        f"{mode} did not settle in {len(trace)} frames / "
        f"{options.settle_timeout_seconds:.2f} seconds"
    )


def _settle_tandem(
    radio: Issue46Radio,
    buffer: Any,
    *,
    options: TandemQualityOptions,
) -> tuple[list[dict[str, Any]], TandemFrameMetadata]:
    session = _ACTIVE_TANDEM_SESSION.get()
    if session is None:
        session = _TandemCaptureSession(output_dir=options.output_dir)
    trace: list[dict[str, Any]] = []
    stable = 0
    deadline = time.monotonic() + options.settle_timeout_seconds
    minimum_drain = (
        options.kernel_buffers + 1
        if session.minimum_drain_override is None
        else session.minimum_drain_override
    )
    for attempt in range(1, options.max_settle_frames + 1):
        previous = session.continuity.previous
        _raw, parsed, frame = _capture_tandem(
            radio,
            buffer,
            options=options,
            session=session,
        )
        continuity = frame["continuity"]
        is_stable = bool(
            previous is not None
            and parsed.tandem_state is TandemState.ARMED_AUTO
            and not parsed.gain_events
            and parsed.rx1_gain_index == parsed.rx2_gain_index
            and continuity["missing_frame_count"] == 0
            and continuity["transition_count_delta"] == 0
            and parsed.bench_gain_indices == previous.bench_gain_indices
        )
        stable = stable + 1 if attempt > minimum_drain and is_stable else 0
        trace.append({"attempt": attempt, "stable_run": stable, **frame})
        if stable >= options.stable_frames:
            return trace, parsed
        if time.monotonic() >= deadline:
            break
    raise EvidenceInvalid(
        f"{MODE_TANDEM} did not settle in {len(trace)} frames / "
        f"{options.settle_timeout_seconds:.2f} seconds"
    )


def _measure_ordinary(
    radio: Issue46Radio,
    buffer: Any,
    *,
    mode: str,
    options: TandemQualityOptions,
    output_dir: Path,
    level_index: int,
    settled: _OrdinaryGainBand,
) -> list[dict[str, Any]]:
    expected_mode = _ordinary_iio_mode(mode)
    measurements: list[dict[str, Any]] = []
    gain_band = settled
    for frame_index in range(options.measurement_frames):
        matrix_ledger = _ACTIVE_MATRIX_FAILURE_IQ.get()
        if matrix_ledger is not None:
            matrix_ledger.set_context(
                mode=mode,
                stage="measurement",
                level_index=level_index,
                frame_index=frame_index,
            )
        before = radio.read_rx_state()
        raw, _metadata, frame = _capture(radio, buffer, options=options, metadata=False)
        after = radio.read_rx_state()
        extended = _extend_gain_band(
            (before, after), expected_mode=expected_mode, prior=gain_band
        )
        if extended is None:
            raise _EvidenceInvalidWithDetails(
                f"{mode} gain left its settled band during a measurement frame",
                {
                    "kind": "ordinary_gain_left_settled_band",
                    "mode": mode,
                    "expected_iio_mode": expected_mode,
                    "level_index": level_index,
                    "tx2_gain_requested_db": options.tx_gain_trajectory_db[level_index],
                    "frame_index": frame_index,
                    "allowed_cumulative_span_db": (
                        0.0 if expected_mode == "manual" else 1.0
                    ),
                    "settled_gain_band": settled.to_dict(),
                    "cumulative_gain_band_before_frame": gain_band.to_dict(),
                    "rx_state_before": before,
                    "rx_state_after": after,
                    "captured_frame": frame,
                },
            )
        gain_band = extended
        frame["rx_state_before"] = before
        frame["rx_state_after"] = after
        frame["gain_band"] = gain_band.to_dict()
        frame["quality"] = dict(
            analyze_common_tone(
                raw,
                sample_rate_hz=options.sample_rate_hz,
                expected_tone_hz=options.tone_hz,
                thresholds=tone_quality_thresholds_for_mode(options, mode),
            )
        )
        if matrix_ledger is not None:
            matrix_ledger.accept_current()
        if options.save_iq:
            path = output_dir / f"{mode}-level{level_index}-frame{frame_index}.cs16"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            frame["iq_path"] = str(path)
        measurements.append(frame)
    return measurements


def _measure_tandem(
    radio: Issue46Radio,
    buffer: Any,
    *,
    options: TandemQualityOptions,
    output_dir: Path,
    level_index: int,
    settled: TandemFrameMetadata,
) -> list[dict[str, Any]]:
    session = _ACTIVE_TANDEM_SESSION.get()
    matrix_ledger = _ACTIVE_MATRIX_FAILURE_IQ.get()
    owns_session = session is None
    if session is None:
        session = _TandemCaptureSession(output_dir=output_dir)
        session.begin_cell(level_index, {"level_index": level_index})
        session.continuity.previous = settled

    settled_endpoint = settled
    try:
        for attempt_index in range(_TANDEM_MEASUREMENT_RESTART_LIMIT + 1):
            session.stage = "measurement"
            session.measurement_attempt = attempt_index
            session.minimum_drain_override = None
            attempt_measurements: list[dict[str, Any]] = []
            accepted_raw: list[bytes] = []
            transitioned = False
            for frame_index in range(options.measurement_frames):
                session.measurement_frame_index = frame_index
                prior_frame = session.continuity.previous_frame
                try:
                    raw, parsed, frame = _capture_tandem(
                        radio,
                        buffer,
                        options=options,
                        session=session,
                    )
                except BaseException:
                    _queue_abandoned_tandem_measurements(
                        accepted_raw,
                        attempt_measurements,
                        output_dir=output_dir,
                        level_index=level_index,
                        attempt_index=attempt_index,
                        session=session,
                    )
                    if matrix_ledger is not None:
                        matrix_ledger.release_accepted_frames(attempt_measurements)
                    raise
                continuity = frame["continuity"]
                transition_delta = continuity["transition_count_delta"]
                if transition_delta is None:
                    raise EvidenceInvalid(
                        "tandem measurement lacks a settled continuity boundary"
                    )
                if transition_delta > 0:
                    _queue_transition_tandem_detail(
                        accepted_raw,
                        attempt_measurements,
                        offending_raw=raw,
                        offending_frame=frame,
                        output_dir=output_dir,
                        level_index=level_index,
                        attempt_index=attempt_index,
                        frame_index=frame_index,
                        session=session,
                    )
                    if matrix_ledger is not None:
                        matrix_ledger.release_accepted_frames(attempt_measurements)
                    rejection = {
                        "attempt_index": attempt_index,
                        "status": "rejected_transition",
                        "accepted_frames_before_transition": list(attempt_measurements),
                        "prior_frame": prior_frame,
                        "offending_frame": frame,
                        "visible_event_count": continuity["visible_event_count"],
                        "hidden_transition_count": continuity[
                            "hidden_transition_count"
                        ],
                        "transition_count_delta": transition_delta,
                    }
                    session.measurement_attempts.append(rejection)
                    if attempt_index >= _TANDEM_MEASUREMENT_RESTART_LIMIT:
                        raise _EvidenceInvalidWithDetails(
                            "tandem measurement transition recovery was exhausted",
                            {
                                "kind": (
                                    "tandem_measurement_transition_retry_exhausted"
                                ),
                                "mode": MODE_TANDEM,
                                "level_index": level_index,
                                "tx2_gain_requested_db": (
                                    options.tx_gain_trajectory_db[level_index]
                                ),
                                "measurement_attempt": attempt_index,
                                "measurement_frame_index": frame_index,
                                "prior_frame": prior_frame,
                                "current_frame": frame,
                                "pending_cell": session.pending_cell,
                                "measurement_attempts": list(
                                    session.measurement_attempts
                                ),
                                "capture_trace": list(session.cell_capture_trace),
                            },
                        )
                    if matrix_ledger is not None:
                        matrix_ledger.discard_current()

                    session.stage = "measurement_recovery_settle"
                    session.measurement_frame_index = None
                    session.minimum_drain_override = 0
                    recovery_trace, settled_endpoint = _settle_tandem(
                        radio,
                        buffer,
                        options=options,
                    )
                    session.recovery_settle_trace.extend(recovery_trace)
                    if session.pending_cell is not None:
                        settling_record = session.pending_cell.setdefault(
                            "settling",
                            {"frames": 0, "trace": []},
                        )
                        retained_trace = settling_record.setdefault("trace", [])
                        retained_trace.extend(recovery_trace)
                        settling_record["frames"] = len(retained_trace)
                        settling_record["recovery_frames"] = len(
                            session.recovery_settle_trace
                        )
                    rejection["recovery_settling"] = {
                        "frames": len(recovery_trace),
                        "capture_ordinals": [
                            int(item["capture_ordinal"])
                            for item in recovery_trace
                            if "capture_ordinal" in item
                        ],
                    }
                    transitioned = True
                    break

                if parsed.bench_gain_indices != settled_endpoint.bench_gain_indices:
                    raise _EvidenceInvalidWithDetails(
                        "tandem endpoint changed without a transition",
                        {
                            "kind": "tandem_measurement_endpoint_mismatch",
                            "mode": MODE_TANDEM,
                            "level_index": level_index,
                            "measurement_attempt": attempt_index,
                            "measurement_frame_index": frame_index,
                            "prior_frame": prior_frame,
                            "current_frame": frame,
                            "pending_cell": session.pending_cell,
                            "capture_trace": list(session.cell_capture_trace),
                        },
                    )
                frame["quality"] = dict(
                    analyze_common_tone(
                        raw,
                        sample_rate_hz=options.sample_rate_hz,
                        expected_tone_hz=options.tone_hz,
                        thresholds=options.thresholds,
                    )
                )
                if matrix_ledger is not None:
                    matrix_ledger.accept_current()
                attempt_measurements.append(frame)
                accepted_raw.append(raw)

            if transitioned:
                continue

            if session.measurement_attempts:
                session.measurement_attempts.append(
                    {
                        "attempt_index": attempt_index,
                        "status": "accepted",
                        "accepted_capture_ordinals": [
                            int(frame["capture_ordinal"])
                            for frame in attempt_measurements
                            if "capture_ordinal" in frame
                        ],
                    }
                )
            if options.save_iq:
                for frame_index, (raw, frame) in enumerate(
                    zip(accepted_raw, attempt_measurements, strict=True)
                ):
                    path = output_dir / (
                        f"{MODE_TANDEM}-level{level_index}-frame{frame_index}.cs16"
                    )
                    session.deferred.queue(
                        raw,
                        frame,
                        path,
                        path_field="iq_path",
                        failure_only=False,
                    )
            return attempt_measurements
        raise AssertionError("bounded tandem measurement loop did not terminate")
    finally:
        session.measurement_frame_index = None
        session.minimum_drain_override = None
        if owns_session:
            session.deferred.flush()


def summarize_measurements(measurements: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Reduce repeated stable captures without hiding any underlying frame."""

    if not measurements:
        raise ValueError("cannot summarize an empty measurement set")
    qualities = [item["quality"] for item in measurements]

    def med_scalar(name: str) -> float:
        return float(statistics.median(float(item[name]) for item in qualities))

    def med_pair(name: str) -> list[float]:
        return [
            float(statistics.median(float(item[name][channel]) for item in qualities))
            for channel in (0, 1)
        ]

    return {
        "quality_valid": all(bool(item["quality_valid"]) for item in qualities),
        "quality_reasons": sorted(
            {reason for item in qualities for reason in item["quality_reasons"]}
        ),
        "tone_frequency_hz_median": med_scalar("tone_frequency_hz"),
        "tone_frequency_error_hz_median": med_scalar("tone_frequency_error_hz"),
        "tone_dbfs_median": med_pair("tone_dbfs"),
        "rms_dbfs_median": med_pair("rms_dbfs"),
        "dc_dbfs_median": med_pair("dc_dbfs"),
        "tone_snr_db_median": med_pair("tone_snr_db"),
        "clipping_fraction_max": [
            max(float(item["clipping_fraction"][channel]) for item in qualities)
            for channel in (0, 1)
        ],
        "amplitude_imbalance_db_median": med_scalar(
            "amplitude_imbalance_db_rx0_over_rx1"
        ),
        "coherence_median": med_scalar("coherence"),
        "phase_difference_deg_median": med_scalar("phase_difference_deg"),
        "within_capture_phase_std_deg_max": max(
            float(item["within_capture_phase_std_deg"]) for item in qualities
        ),
    }


def _wait_for_idle(
    radio: Issue46Radio, *, timeout_seconds: float = 2.0
) -> dict[str, int]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        status = radio.tandem_status()
        if (
            status["state"] == int(TandemState.IDLE)
            and status["fault_flags"] == 0
            and status["fifo_level"] == 0
        ):
            return status
        if time.monotonic() >= deadline:
            raise EvidenceInvalid(f"tandem controller did not return to IDLE: {status}")
        time.sleep(0.01)


def _augment_tandem_failure(
    error: BaseException,
    session: _TandemCaptureSession,
) -> _EvidenceInvalidWithDetails:
    """Attach the last complete boundary and pending cell to any session failure."""

    details = (
        dict(error.failure_evidence)
        if isinstance(error, _EvidenceInvalidWithDetails)
        else {
            "kind": "tandem_capture_session_invalid",
            "cause": _exception_text(error),
        }
    )
    details.setdefault("mode", MODE_TANDEM)
    details.setdefault("level_index", session.level_index)
    details.setdefault("capture_stage", session.stage)
    details.setdefault("prior_frame", session.continuity.penultimate_frame)
    details.setdefault("current_frame", session.continuity.previous_frame)
    details.setdefault("pending_cell", session.pending_cell)
    details.setdefault("measurement_attempts", list(session.measurement_attempts))
    details.setdefault("capture_trace", list(session.cell_capture_trace))
    if isinstance(error, _EvidenceInvalidWithDetails):
        error.failure_evidence = details
        return error
    return _EvidenceInvalidWithDetails(str(error), details)


def _run_mode(
    radio: Issue46Radio,
    *,
    mode: str,
    options: TandemQualityOptions,
    report: dict[str, Any],
    report_path: Path,
    check_deadline: Callable[[], None],
) -> None:
    matrix_ledger = _ACTIVE_MATRIX_FAILURE_IQ.get()
    if matrix_ledger is not None:
        matrix_ledger.set_context(
            mode=mode,
            stage="mode_setup",
            level_index=None,
            frame_index=None,
        )
    radio.mute_all()
    before = _wait_for_idle(radio)
    radio.configure_rx("manual", manual_gain_db=options.manual_gain_db)
    radio.arm_tx2_tone(tone_hz=options.tone_hz, scale=options.dds_scale)

    metadata = mode == MODE_TANDEM
    request: bytes | None = None
    native_iio_mode = native_gain_control_mode(mode)
    if native_iio_mode is None and mode == MODE_TANDEM:
        request = build_tandem_request(
            mode=TandemMode.AUTO,
            initial_gain_db=int(options.manual_gain_db),
            power_measurement_samples=options.tandem_power_measurement_samples,
            low_power_dwell_periods=options.tandem_low_power_dwell_periods,
            cooldown_periods=options.tandem_cooldown_periods,
            low_power_threshold=options.tandem_low_power_threshold,
            large_lmt_overload_threshold=(options.tandem_large_lmt_overload_threshold),
            large_adc_overload_threshold=(options.tandem_large_adc_overload_threshold),
            small_adc_overload_threshold=(options.tandem_small_adc_overload_threshold),
            samples_per_channel=options.samples_per_channel,
        )
    elif native_iio_mode is None and mode != MODE_MANUAL:
        raise ValueError(f"unknown quality mode {mode!r}")

    first_readback = radio.set_tx2_gain(options.tx_gain_trajectory_db[0])
    native_entry_conditioning: dict[str, Any] | None = None
    if native_iio_mode is not None:
        # Enter autonomous native AGC with the real weakest-rung stimulus
        # already present.  Fast attack may retain its prior lock level and
        # disallow gain increases after lock; entering it while TX2 is still
        # muted therefore makes later cells depend on earlier campaign runs.
        if native_iio_mode == "fast_attack":
            state_before = radio.read_rx_state()
            radio.configure_rx(
                "manual", manual_gain_db=NATIVE_FAST_ENTRY_MANUAL_GAIN_DB
            )
            state_after = radio.read_rx_state()
            native_entry_conditioning = {
                "policy": "weak-stimulus-manual-ceiling-before-fast-attack",
                "stimulus_tx2_gain_db": first_readback,
                "manual_seed_gain_db": NATIVE_FAST_ENTRY_MANUAL_GAIN_DB,
                "rx_state_before": state_before,
                "rx_state_after": state_after,
            }
        radio.configure_rx(native_iio_mode)
    mode_record: dict[str, Any] = {
        "mode": mode,
        "tandem_status_before": before,
        "initial_tx2_readback_db": first_readback,
        "cells": [],
    }
    if native_entry_conditioning is not None:
        mode_record["native_entry_conditioning"] = native_entry_conditioning
    report["modes"].append(mode_record)
    _atomic_json(report_path, report)
    tandem_session = (
        _TandemCaptureSession(output_dir=options.output_dir) if metadata else None
    )
    session_token = (
        _ACTIVE_TANDEM_SESSION.set(tandem_session) if tandem_session else None
    )
    try:
        try:
            with radio.buffer(
                "metadata" if metadata else "ordinary",
                options.kernel_buffers,
                options.samples_per_channel,
                tandem_request=request,
            ) as (buffer, metadata_abi):
                mode_record["metadata_abi"] = metadata_abi
                if metadata:
                    assert tandem_session is not None
                    tandem_session.stage = "priming_settle"
                    check_deadline()
                    priming_gain_db, distinct_levels = _select_tandem_priming_gain(
                        options.tx_gain_trajectory_db
                    )
                    if not (
                        TX_MUTE_DB <= priming_gain_db <= options.strongest_tx_gain_db
                    ):
                        raise EvidenceInvalid(
                            "tandem priming gain exceeds the authorized TX trajectory"
                        )
                    priming_readback = radio.set_tx2_gain(priming_gain_db)
                    priming_effective_attenuation = (
                        options.physical_attenuation_db - priming_readback
                    )
                    if priming_effective_attenuation < 30.0:
                        raise EvidenceInvalid(
                            "tandem priming readback violates the 30 dB effective "
                            "safety boundary"
                        )
                    priming_trace, priming_settled = _settle_tandem(
                        radio, buffer, options=options
                    )
                    priming_metadata = [
                        frame["metadata"]
                        for frame in priming_trace
                        if "metadata" in frame
                    ]
                    priming_events = [
                        event
                        for frame_metadata in priming_metadata
                        for event in frame_metadata["gain_events"]
                    ]
                    priming_reached_max = bool(
                        priming_settled.rx1_gain_index
                        == priming_settled.maximum_gain_index
                        and priming_settled.rx2_gain_index
                        == priming_settled.maximum_gain_index
                    )
                    mode_record["priming"] = {
                        "selection": {
                            "method": "median_of_sorted_distinct_trajectory_gains",
                            "distinct_trajectory_gains_db": distinct_levels,
                            "authorized_strongest_tx2_gain_db": (
                                options.strongest_tx_gain_db
                            ),
                        },
                        "tx2_gain_requested_db": priming_gain_db,
                        "tx2_gain_readback_db": priming_readback,
                        "effective_attenuation_db": priming_effective_attenuation,
                        "quality_gate_applied": False,
                        "settling": {
                            "frames": len(priming_trace),
                            "trace": priming_trace,
                        },
                        "summary": {
                            "event_count": len(priming_events),
                            "increase_event_count": sum(
                                int(event["direction"])
                                == int(TandemEventDirection.INCREASE)
                                for event in priming_events
                            ),
                            "decrease_event_count": sum(
                                int(event["direction"])
                                == int(TandemEventDirection.DECREASE)
                                for event in priming_events
                            ),
                            "final_gain_indices": list(
                                priming_settled.bench_gain_indices
                            ),
                            "maximum_gain_index": priming_settled.maximum_gain_index,
                            "reached_maximum_gain": priming_reached_max,
                        },
                        "final_metadata": _metadata_dict(priming_settled),
                    }
                for index, tx_gain_db in enumerate(options.tx_gain_trajectory_db):
                    check_deadline()
                    if matrix_ledger is not None:
                        matrix_ledger.set_context(
                            mode=mode,
                            stage="cell_setup",
                            level_index=index,
                            frame_index=None,
                        )
                    tx_readback = radio.set_tx2_gain(tx_gain_db)
                    cell: dict[str, Any] = {
                        "level_index": index,
                        "direction": _direction(options.tx_gain_trajectory_db, index),
                        "tx2_gain_requested_db": tx_gain_db,
                        "tx2_gain_readback_db": tx_readback,
                        "effective_attenuation_db": (
                            options.physical_attenuation_db - tx_readback
                        ),
                    }
                    if cell["effective_attenuation_db"] < 30.0:
                        raise EvidenceInvalid(
                            "TX2 readback violates the 30 dB effective safety boundary"
                        )
                    if metadata:
                        assert tandem_session is not None
                        tandem_session.begin_cell(index, cell)
                        settle_trace, settled = _settle_tandem(
                            radio, buffer, options=options
                        )
                        cell["settling"] = {
                            "frames": len(settle_trace),
                            "trace": settle_trace,
                        }
                        measurements = _measure_tandem(
                            radio,
                            buffer,
                            options=options,
                            output_dir=options.output_dir,
                            level_index=index,
                            settled=settled,
                        )
                    else:
                        settle_trace, settled_gain_band = _settle_ordinary(
                            radio, buffer, mode=mode, options=options
                        )
                        measurements = _measure_ordinary(
                            radio,
                            buffer,
                            mode=mode,
                            options=options,
                            output_dir=options.output_dir,
                            level_index=index,
                            settled=settled_gain_band,
                        )
                    if metadata:
                        assert tandem_session is not None
                        if tandem_session.cell_capture_trace:
                            cell["capture_trace"] = list(
                                tandem_session.cell_capture_trace
                            )
                        if tandem_session.measurement_attempts:
                            cell["measurement_attempts"] = list(
                                tandem_session.measurement_attempts
                            )
                    else:
                        cell["settling"] = {
                            "frames": len(settle_trace),
                            "trace": settle_trace,
                        }
                        cell["settling"]["settled_gain_band"] = (
                            settled_gain_band.to_dict()
                        )
                    cell["measurements"] = measurements
                    cell["summary"] = summarize_measurements(measurements)
                    mode_record["cells"].append(cell)
                    if metadata:
                        assert tandem_session is not None
                        tandem_session.pending_cell = None
                    else:
                        _atomic_json(report_path, report)
        except BaseException as error:
            if not metadata:
                raise
            assert tandem_session is not None
            augmented = _augment_tandem_failure(error, tandem_session)
            if augmented is error:
                raise
            raise augmented from error
    finally:
        try:
            radio.mute_all()
        finally:
            if session_token is not None:
                _ACTIVE_TANDEM_SESSION.reset(session_token)
            if tandem_session is not None:
                # Abandoned tandem measurement attempts remain independently
                # authorizing continuity evidence even when recovery succeeds.
                # They are bounded separately and materialized only after this
                # metadata buffer has closed.
                tandem_session.deferred.flush()
    after = _wait_for_idle(radio)
    mode_record["tandem_status_after"] = after
    radio.configure_rx("manual", manual_gain_db=options.manual_gain_db)
    _atomic_json(report_path, report)


def _mode_cells(report: Mapping[str, Any], mode: str) -> list[Mapping[str, Any]]:
    matches = [item for item in report["modes"] if item["mode"] == mode]
    if len(matches) != 1:
        raise EvidenceInvalid(f"report contains {len(matches)} records for {mode}")
    return list(matches[0]["cells"])


def _cell_tandem_frames(cell: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return each captured frame once, preferring the RC21 chronology ledger."""

    capture_trace = cell.get("capture_trace")
    if capture_trace is None:
        return [
            frame
            for section in (cell["settling"]["trace"], cell["measurements"])
            for frame in section
        ]
    if not isinstance(capture_trace, Sequence) or isinstance(
        capture_trace, (str, bytes, bytearray)
    ):
        raise EvidenceInvalid("tandem cell capture_trace is not a sequence")
    frames: list[Mapping[str, Any]] = []
    previous_ordinal: int | None = None
    for item in capture_trace:
        if not isinstance(item, Mapping):
            raise EvidenceInvalid("tandem cell capture_trace contains a non-record")
        ordinal = _required_int(
            item,
            "capture_ordinal",
            context="tandem cell capture trace",
        )
        if previous_ordinal is not None and ordinal <= previous_ordinal:
            raise EvidenceInvalid(
                "tandem cell capture ordinals did not advance chronologically"
            )
        previous_ordinal = ordinal
        frames.append(item)
    return frames


_UINT32_MODULUS = 1 << 32
_UINT32_HALF_RANGE = 1 << 31


def _required_int(value: Mapping[str, Any], name: str, *, context: str) -> int:
    raw = value.get(name)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise EvidenceInvalid(f"{context} lacks integer {name}")
    return raw


def _forward_u32_delta(current: int, previous: int, *, context: str) -> int:
    if not 0 <= current < _UINT32_MODULUS or not 0 <= previous < _UINT32_MODULUS:
        raise EvidenceInvalid(f"{context} is outside uint32")
    delta = (current - previous) % _UINT32_MODULUS
    if delta >= _UINT32_HALF_RANGE:
        raise EvidenceInvalid(f"{context} regressed or advanced ambiguously")
    return delta


def _tandem_stimulus_response(
    cells: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not cells:
        raise EvidenceInvalid("tandem trajectory contains no cells")
    levels = [float(cell["tx2_gain_requested_db"]) for cell in cells]
    if levels[0] != min(levels):
        raise EvidenceInvalid("tandem trajectory must begin at its weakest TX level")

    response: list[dict[str, Any]] = []
    previous_settled: Mapping[str, Any] | None = None
    for index, cell in enumerate(cells):
        frames = [frame["metadata"] for frame in _cell_tandem_frames(cell)]
        if not frames:
            raise EvidenceInvalid(f"tandem cell {index} has no metadata frames")
        cell_events = [event for frame in frames for event in frame["gain_events"]]
        settled = frames[-1]
        settled_endpoint = tuple(settled["bench_gain_indices"])
        settled_gain = int(settled_endpoint[0])
        gain_index_range = tuple(settled.get("gain_index_range", ()))
        if len(gain_index_range) != 2 or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in gain_index_range
        ):
            raise EvidenceInvalid(
                f"tandem cell {index} lacks an integer gain-index range"
            )
        minimum_gain_index, maximum_gain_index = gain_index_range
        if not minimum_gain_index <= settled_gain <= maximum_gain_index:
            raise EvidenceInvalid(
                f"tandem cell {index} endpoint lies outside its gain-index range"
            )

        if index == 0:
            direction = "initial"
            expected = TandemEventDirection.INCREASE
        elif levels[index] > levels[index - 1]:
            direction = "louder"
            expected = TandemEventDirection.DECREASE
        elif levels[index] < levels[index - 1]:
            direction = "quieter"
            expected = TandemEventDirection.INCREASE
        else:
            direction = "same"
            expected = None

        matching_events = (
            []
            if expected is None
            else [
                event
                for event in cell_events
                if int(event["direction"]) == int(expected)
            ]
        )
        settled_delta: int | None = None
        transition_delta: int | None = None
        missing_frames = 0
        hidden_transitions: int | None = None
        evidence_source = "not_applicable"
        direction_proven = False

        if previous_settled is None:
            # Session priming may deliberately enter the trajectory already at
            # maximum gain, so the first weak rung can be a quiet clamp.  This
            # initialization is diagnostic only and never proves the commanded
            # return-leg INCREASE required by the verdict.
            transition_delta = _forward_u32_delta(
                _required_int(
                    settled,
                    "tandem_transition_count",
                    context="tandem initial settled frame",
                ),
                _required_int(
                    frames[0],
                    "tandem_transition_count",
                    context="tandem initial first frame",
                ),
                context="tandem initial transition count",
            )
            if matching_events:
                evidence_source = "explicit_event"
            elif (
                not cell_events
                and transition_delta == 0
                and all(
                    tuple(frame["bench_gain_indices"])
                    == (maximum_gain_index, maximum_gain_index)
                    for frame in frames
                )
            ):
                evidence_source = "clamp"
            else:
                evidence_source = "deadband"
        else:
            previous_endpoint = tuple(previous_settled["bench_gain_indices"])
            previous_gain = int(previous_endpoint[0])
            settled_delta = settled_gain - previous_gain
            transition_delta = _forward_u32_delta(
                _required_int(
                    settled,
                    "tandem_transition_count",
                    context=f"tandem cell {index} settled frame",
                ),
                _required_int(
                    previous_settled,
                    "tandem_transition_count",
                    context=f"tandem cell {index - 1} settled frame",
                ),
                context=f"tandem cell {index} transition count",
            )
            boundary_frames = [previous_settled, *frames]
            for previous_frame, current_frame in pairwise(boundary_frames):
                buffer_delta = _required_int(
                    current_frame,
                    "buffer_sequence",
                    context=f"tandem cell {index} frame",
                ) - _required_int(
                    previous_frame,
                    "buffer_sequence",
                    context=f"tandem cell {index} previous frame",
                )
                if buffer_delta <= 0:
                    raise EvidenceInvalid(
                        f"tandem cell {index} buffer sequence did not advance"
                    )
                missing_frames += buffer_delta - 1
            hidden_transitions = transition_delta - len(cell_events)
            if hidden_transitions < 0:
                raise EvidenceInvalid(
                    f"tandem cell {index} has more visible events than transitions"
                )

            if expected is not None:
                expected_step = 1 if expected is TandemEventDirection.INCREASE else -1
                clamp_index = (
                    maximum_gain_index
                    if expected is TandemEventDirection.INCREASE
                    else minimum_gain_index
                )
                if settled_delta == 0:
                    if transition_delta != 0:
                        raise EvidenceInvalid(
                            f"tandem {direction} TX step changed transition count "
                            "without moving its endpoint"
                        )
                    evidence_source = (
                        "clamp" if settled_gain == clamp_index else "deadband"
                    )
                elif settled_delta * expected_step <= 0:
                    raise EvidenceInvalid(
                        f"tandem {direction} TX step moved the endpoint in the "
                        "wrong direction"
                    )
                else:
                    if abs(settled_delta) > transition_delta:
                        raise EvidenceInvalid(
                            f"tandem {direction} endpoint movement exceeds its "
                            "transition-count delta"
                        )
                    if matching_events:
                        evidence_source = "explicit_event"
                    elif missing_frames > 0 and hidden_transitions > 0:
                        # A provider-accounted gap can prove that the endpoint
                        # is internally possible. It cannot prove which hidden
                        # transition responded to this commanded TX step.
                        evidence_source = "gap_accounted_unproven"
                    else:
                        raise EvidenceInvalid(
                            f"tandem {direction} TX step lacks a matching visible event"
                        )
                    direction_proven = bool(matching_events)
        response.append(
            {
                "level_index": int(cell["level_index"]),
                "direction": direction,
                "tx2_gain_db": levels[index],
                "expected_event_direction": (
                    None if expected is None else expected.name.lower()
                ),
                "matching_event_count": len(matching_events),
                "settled_gain_index": settled_gain,
                "settled_gain_delta": settled_delta,
                "transition_count_delta": transition_delta,
                "missing_frame_count": missing_frames,
                "hidden_transition_count": hidden_transitions,
                "gain_index_range": [minimum_gain_index, maximum_gain_index],
                "evidence_source": evidence_source,
                "direction_proven": direction_proven,
            }
        )
        previous_settled = settled
    return response


def _observed_tandem_evidence(cells: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    metadata_records: list[Mapping[str, Any]] = []
    for cell in cells:
        for frame in _cell_tandem_frames(cell):
            metadata = frame.get("metadata")
            if not isinstance(metadata, Mapping):
                raise EvidenceInvalid("tandem capture lacks frame-associated metadata")
            metadata_records.append(metadata)
    if not metadata_records:
        raise EvidenceInvalid("tandem session contains no metadata frames")

    stream_ids = {
        _required_int(item, "stream_id", context="tandem metadata")
        for item in metadata_records
    }
    ownership_epochs = {
        _required_int(item, "ownership_epoch", context="tandem metadata")
        for item in metadata_records
    }
    if len(stream_ids) != 1:
        raise EvidenceInvalid("tandem stream_id changed inside one buffer session")
    if len(ownership_epochs) != 1:
        raise EvidenceInvalid("tandem ownership epoch changed inside one session")

    events: list[Mapping[str, Any]] = []
    indices: list[int] = []
    missing_frames = 0
    unrepresented_transitions = 0
    event_sequence_holes = 0
    unobserved_events = 0
    verified_gain_steps = 0
    unrepresented_since_event = 0
    previous_metadata: Mapping[str, Any] | None = None
    previous_event: Mapping[str, Any] | None = None

    for frame_index, metadata in enumerate(metadata_records):
        context = f"tandem metadata frame {frame_index}"
        buffer_sequence = _required_int(metadata, "buffer_sequence", context=context)
        first_sample = _required_int(metadata, "first_sample_sequence", context=context)
        sample_count = _required_int(metadata, "samples_per_channel", context=context)
        transition_count = _required_int(
            metadata, "tandem_transition_count", context=context
        )
        endpoint = tuple(metadata.get("bench_gain_indices", ()))
        if (
            buffer_sequence < 0
            or first_sample < 0
            or sample_count <= 0
            or not 0 <= transition_count < _UINT32_MODULUS
        ):
            raise EvidenceInvalid(f"{context} contains an invalid counter")
        if len(endpoint) != 2 or any(
            isinstance(item, bool) or not isinstance(item, int) for item in endpoint
        ):
            raise EvidenceInvalid(f"{context} lacks a paired integer endpoint gain")
        if endpoint[0] != endpoint[1]:
            raise EvidenceInvalid(f"{context} contains a torn endpoint gain")
        indices.extend(int(item) for item in endpoint)

        frame_events = metadata.get("gain_events")
        if not isinstance(frame_events, Sequence) or isinstance(
            frame_events, (str, bytes, bytearray)
        ):
            raise EvidenceInvalid(f"{context} lacks a gain-event sequence")
        if _required_int(metadata, "event_count", context=context) != len(frame_events):
            raise EvidenceInvalid(f"{context} event count differs from its event array")

        transition_delta: int | None = None
        if previous_metadata is None:
            if transition_count < len(frame_events):
                raise EvidenceInvalid(
                    f"{context} has fewer transitions than represented events"
                )
            unrepresented = transition_count - len(frame_events)
        else:
            previous_buffer = _required_int(
                previous_metadata, "buffer_sequence", context="previous tandem frame"
            )
            previous_first = _required_int(
                previous_metadata,
                "first_sample_sequence",
                context="previous tandem frame",
            )
            previous_samples = _required_int(
                previous_metadata,
                "samples_per_channel",
                context="previous tandem frame",
            )
            if sample_count != previous_samples:
                raise EvidenceInvalid("tandem sample count changed inside one session")
            buffer_delta = buffer_sequence - previous_buffer
            sample_delta = first_sample - previous_first
            if buffer_delta <= 0 or sample_delta <= 0:
                raise EvidenceInvalid("tandem frame counters did not advance")
            if sample_delta % previous_samples:
                raise EvidenceInvalid(
                    "tandem sample sequence did not advance by whole frames"
                )
            if buffer_delta != sample_delta // previous_samples:
                raise EvidenceInvalid(
                    "tandem buffer and sample sequence deltas disagree"
                )
            missing_frames += buffer_delta - 1
            previous_transition_count = _required_int(
                previous_metadata,
                "tandem_transition_count",
                context="previous tandem frame",
            )
            transition_delta = _forward_u32_delta(
                transition_count,
                previous_transition_count,
                context="tandem transition count",
            )
            if transition_delta < len(frame_events):
                raise EvidenceInvalid(
                    f"{context} has more events than its transition delta"
                )
            unrepresented = transition_delta - len(frame_events)
            if buffer_delta == 1 and unrepresented:
                raise EvidenceInvalid(
                    "adjacent tandem frames lost transition event evidence"
                )
        unrepresented_transitions += unrepresented
        if previous_metadata is not None:
            # A transition omitted because one or more IQ frames were skipped
            # can explain only the next observed event-sequence hole.  The
            # first-frame transition counter is an independent session
            # baseline and must never become credit for a later hole.
            unrepresented_since_event += unrepresented

        normalized_events: list[Mapping[str, Any]] = []
        for event_index, event in enumerate(frame_events):
            if not isinstance(event, Mapping):
                raise EvidenceInvalid(f"{context} event {event_index} is not a record")
            event_context = f"{context} event {event_index}"
            sample_sequence = _required_int(
                event, "sample_sequence", context=event_context
            )
            event_sequence = _required_int(
                event, "event_sequence", context=event_context
            )
            direction_value = _required_int(event, "direction", context=event_context)
            rx1_gain = _required_int(event, "rx1_gain_index", context=event_context)
            rx2_gain = _required_int(event, "rx2_gain_index", context=event_context)
            if not 0 <= event_sequence < _UINT32_MODULUS:
                raise EvidenceInvalid(f"{event_context} sequence is outside uint32")
            if not first_sample <= sample_sequence < first_sample + sample_count:
                raise EvidenceInvalid(f"{event_context} lies outside its IQ frame")
            if rx1_gain != rx2_gain:
                raise EvidenceInvalid(f"{event_context} contains a torn gain pair")
            try:
                direction = TandemEventDirection(direction_value)
            except ValueError as error:
                raise EvidenceInvalid(
                    f"{event_context} has an invalid direction"
                ) from error

            if previous_event is not None:
                previous_sequence = _required_int(
                    previous_event, "event_sequence", context="previous tandem event"
                )
                sequence_delta = _forward_u32_delta(
                    event_sequence,
                    previous_sequence,
                    context="tandem event sequence",
                )
                if sequence_delta == 0:
                    raise EvidenceInvalid("tandem event sequence did not advance")
                previous_sample = _required_int(
                    previous_event, "sample_sequence", context="previous tandem event"
                )
                if sample_sequence < previous_sample:
                    raise EvidenceInvalid(
                        "tandem events are not globally sample ordered"
                    )
                sequence_hole = sequence_delta - 1
                if sequence_hole != unrepresented_since_event:
                    raise EvidenceInvalid(
                        "tandem event-sequence hole does not match locally "
                        "unrepresented transitions"
                    )
                if sequence_hole:
                    event_sequence_holes += 1
                    unobserved_events += sequence_hole
                else:
                    previous_gain = _required_int(
                        previous_event,
                        "rx1_gain_index",
                        context="previous tandem event",
                    )
                    expected_gain = previous_gain + (
                        1 if direction is TandemEventDirection.INCREASE else -1
                    )
                    if rx1_gain != expected_gain:
                        raise EvidenceInvalid(
                            "consecutive tandem event gain did not take its exact "
                            "+/-1 direction step"
                        )
                    verified_gain_steps += 1
            elif previous_metadata is not None and unrepresented == 0:
                previous_endpoint = tuple(previous_metadata["bench_gain_indices"])
                expected_gain = int(previous_endpoint[0]) + (
                    1 if direction is TandemEventDirection.INCREASE else -1
                )
                if rx1_gain != expected_gain:
                    raise EvidenceInvalid(
                        "first observed tandem event disagrees with the prior endpoint"
                    )
                verified_gain_steps += 1

            # Missing-frame transitions precede every event associated with
            # this returned IQ frame.  Once its first event has consumed (or
            # disproved) that local accounting, none may leak into a later
            # frame interval.
            unrepresented_since_event = 0

            normalized_events.append(event)
            events.append(event)
            indices.extend((rx1_gain, rx2_gain))
            previous_event = event

        if normalized_events:
            final_event = normalized_events[-1]
            final_gain = _required_int(
                final_event, "rx1_gain_index", context="final frame event"
            )
            if endpoint != (final_gain, final_gain):
                raise EvidenceInvalid(
                    f"{context} endpoint gain differs from its final event"
                )
        elif previous_metadata is not None and transition_delta == 0:
            if endpoint != tuple(previous_metadata["bench_gain_indices"]):
                raise EvidenceInvalid(
                    f"{context} endpoint changed without a transition event"
                )
        previous_metadata = metadata

    directions = sorted({int(event["direction"]) for event in events})
    stimulus_response = _tandem_stimulus_response(cells)
    proven_directions = sorted(
        {
            int(TandemEventDirection[item["expected_event_direction"].upper()])
            for item in stimulus_response
            if item["direction_proven"]
            and item["direction"] in ("louder", "quieter")
            and item["expected_event_direction"] is not None
        }
    )
    return {
        "metadata_frames": len(metadata_records),
        "stream_id": next(iter(stream_ids)),
        "event_count": len(events),
        "increase_event_count": sum(
            event["direction"] == int(TandemEventDirection.INCREASE) for event in events
        ),
        "decrease_event_count": sum(
            event["direction"] == int(TandemEventDirection.DECREASE) for event in events
        ),
        "directions": directions,
        "proven_directions": proven_directions,
        "gain_index_min": min(indices),
        "gain_index_max": max(indices),
        "gain_index_span": max(indices) - min(indices),
        "ownership_epochs": sorted(ownership_epochs),
        "missing_frame_count": missing_frames,
        "unrepresented_transition_count": unrepresented_transitions,
        "event_sequence_hole_count": event_sequence_holes,
        "unobserved_event_count": unobserved_events,
        "verified_gain_step_count": verified_gain_steps,
        "stimulus_response": stimulus_response,
    }


def _observed_native_gain_response(
    cells: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Measure independent native-AGC response without pooling the RX channels."""

    if not cells:
        raise EvidenceInvalid("native gain evidence contains no trajectory cells")
    levels = [float(cell["tx2_gain_requested_db"]) for cell in cells]
    weakest = min(levels)
    strongest = max(levels)
    if levels[0] != weakest or levels[-1] != weakest:
        raise EvidenceInvalid(
            "native trajectory must begin and return at its weakest TX level"
        )
    all_gains: list[list[float]] = [[], []]
    weak_gains: list[list[float]] = [[], []]
    strong_gains: list[list[float]] = [[], []]
    cell_medians: list[list[float]] = []
    for cell, level in zip(cells, levels, strict=True):
        cell_gains: list[list[float]] = [[], []]
        for frame in cell["measurements"]:
            gains = tuple(float(value) for value in frame["rx_state_after"]["gains_db"])
            if len(gains) != 2 or any(not math.isfinite(value) for value in gains):
                raise EvidenceInvalid("native gain evidence is malformed")
            for channel in (0, 1):
                cell_gains[channel].append(gains[channel])
                all_gains[channel].append(gains[channel])
                if level == weakest:
                    weak_gains[channel].append(gains[channel])
                if level == strongest:
                    strong_gains[channel].append(gains[channel])
        if any(not values for values in cell_gains):
            raise EvidenceInvalid("native gain evidence contains an empty cell")
        cell_medians.append(
            [float(statistics.median(cell_gains[channel])) for channel in (0, 1)]
        )
    if any(
        not all_gains[channel] or not weak_gains[channel] or not strong_gains[channel]
        for channel in (0, 1)
    ):
        raise EvidenceInvalid("native gain evidence is incomplete")

    weak_medians = [statistics.median(values) for values in weak_gains]
    strong_medians = [statistics.median(values) for values in strong_gains]
    spans = [max(values) - min(values) for values in all_gains]
    initial_weak_medians = cell_medians[0]
    returned_weak_medians = cell_medians[-1]
    return {
        "weakest_tx2_gain_db": weakest,
        "strongest_tx2_gain_db": strongest,
        "weak_gain_db_median": [float(value) for value in weak_medians],
        "strong_gain_db_median": [float(value) for value in strong_medians],
        "weak_minus_strong_gain_db": [
            float(weak_medians[channel] - strong_medians[channel]) for channel in (0, 1)
        ],
        "initial_weak_gain_db_median": initial_weak_medians,
        "returned_weak_gain_db_median": returned_weak_medians,
        "outbound_weak_minus_strong_gain_db": [
            float(initial_weak_medians[channel] - strong_medians[channel])
            for channel in (0, 1)
        ],
        "return_weak_minus_strong_gain_db": [
            float(returned_weak_medians[channel] - strong_medians[channel])
            for channel in (0, 1)
        ],
        "gain_span_db": [float(value) for value in spans],
    }


def _manual_tone_response(cells: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Use fixed RX gain to prove commanded TX2 loudness and return retrace."""

    if not cells:
        raise EvidenceInvalid("manual tone evidence contains no trajectory cells")
    levels = [float(cell["tx2_gain_requested_db"]) for cell in cells]
    tones: list[tuple[float, float]] = []
    for cell in cells:
        values = tuple(float(value) for value in cell["summary"]["tone_dbfs_median"])
        if len(values) != 2 or any(not math.isfinite(value) for value in values):
            raise EvidenceInvalid("manual tone evidence is malformed")
        tones.append((values[0], values[1]))

    reasons: list[str] = []
    steps: list[dict[str, Any]] = []
    for index in range(1, len(cells)):
        requested_delta = levels[index] - levels[index - 1]
        measured_delta = [
            tones[index][channel] - tones[index - 1][channel] for channel in (0, 1)
        ]
        tracking_error = [value - requested_delta for value in measured_delta]
        direction_matches = [
            (
                requested_delta == 0.0
                and abs(measured_delta[channel]) <= MANUAL_TONE_RETRACE_TOLERANCE_DB
            )
            or (requested_delta > 0.0 and measured_delta[channel] > 0.0)
            or (requested_delta < 0.0 and measured_delta[channel] < 0.0)
            for channel in (0, 1)
        ]
        for channel in (0, 1):
            if not direction_matches[channel]:
                reasons.append(f"rx{channel}_step_{index}_wrong_direction")
            if abs(tracking_error[channel]) > MANUAL_TONE_TRACKING_TOLERANCE_DB:
                reasons.append(f"rx{channel}_step_{index}_tracking_error")
        steps.append(
            {
                "to_level_index": index,
                "requested_delta_db": requested_delta,
                "measured_delta_db": measured_delta,
                "tracking_error_db": tracking_error,
                "direction_matches": direction_matches,
            }
        )

    retrace: list[dict[str, Any]] = []
    for level in sorted(set(levels)):
        matching = [
            tone
            for tone, observed in zip(tones, levels, strict=True)
            if observed == level
        ]
        spreads = [
            max(tone[channel] for tone in matching)
            - min(tone[channel] for tone in matching)
            for channel in (0, 1)
        ]
        for channel in (0, 1):
            if spreads[channel] > MANUAL_TONE_RETRACE_TOLERANCE_DB:
                reasons.append(f"rx{channel}_level_{level:g}_retrace_error")
        retrace.append(
            {
                "tx2_gain_db": level,
                "visits": len(matching),
                "tone_spread_db": spreads,
            }
        )

    return {
        "valid": not reasons,
        "reasons": reasons,
        "tracking_tolerance_db": MANUAL_TONE_TRACKING_TOLERANCE_DB,
        "retrace_tolerance_db": MANUAL_TONE_RETRACE_TOLERANCE_DB,
        "steps": steps,
        "retrace": retrace,
    }


def _quality_deltas(
    reference: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    left = reference["summary"]
    right = candidate["summary"]
    return {
        "tone_dbfs_db": [
            float(right["tone_dbfs_median"][index])
            - float(left["tone_dbfs_median"][index])
            for index in (0, 1)
        ],
        "tone_snr_db": [
            float(right["tone_snr_db_median"][index])
            - float(left["tone_snr_db_median"][index])
            for index in (0, 1)
        ],
        "coherence": float(right["coherence_median"]) - float(left["coherence_median"]),
        "phase_stability_deg": float(right["within_capture_phase_std_deg_max"])
        - float(left["within_capture_phase_std_deg_max"]),
    }


def _native_report_modes(report: Mapping[str, Any]) -> tuple[str, ...]:
    modes: list[str] = []
    for record in report["modes"]:
        mode = str(record["mode"])
        if mode in (MODE_MANUAL, MODE_TANDEM):
            continue
        try:
            gain_control_mode = native_gain_control_mode(mode)
        except ValueError as exc:
            raise EvidenceInvalid(str(exc)) from exc
        if gain_control_mode is None:
            raise EvidenceInvalid(f"report contains unknown quality mode {mode!r}")
        modes.append(mode)
    if not modes:
        raise EvidenceInvalid("report contains no native AGC mode")
    if len(set(modes)) != len(modes):
        raise EvidenceInvalid("report contains duplicate native AGC modes")
    return tuple(modes)


def evaluate_matrix(report: Mapping[str, Any]) -> dict[str, Any]:
    """Apply absolute gates and report, but do not invent a relative AGC winner."""

    manual = _mode_cells(report, MODE_MANUAL)
    tandem = _mode_cells(report, MODE_TANDEM)
    native_modes = _native_report_modes(report)
    native_cells = {mode: _mode_cells(report, mode) for mode in native_modes}
    trajectory_lengths = {
        len(manual),
        len(tandem),
        *(len(cells) for cells in native_cells.values()),
    }
    if len(trajectory_lengths) != 1:
        raise EvidenceInvalid("mode trajectories contain different cell counts")
    primary_native_mode = (
        MODE_NATIVE if MODE_NATIVE in native_cells else native_modes[0]
    )
    comparisons = []
    for index, (fixed, paired_agc) in enumerate(zip(manual, tandem, strict=True)):
        ordinary_agc_by_mode = {
            mode: cells[index] for mode, cells in native_cells.items()
        }
        levels = {
            fixed["tx2_gain_requested_db"],
            paired_agc["tx2_gain_requested_db"],
            *(
                ordinary_agc["tx2_gain_requested_db"]
                for ordinary_agc in ordinary_agc_by_mode.values()
            ),
        }
        if len(levels) != 1:
            raise EvidenceInvalid("modes did not execute an identical TX trajectory")
        native_minus_manual_by_mode = {
            mode: _quality_deltas(fixed, ordinary_agc)
            for mode, ordinary_agc in ordinary_agc_by_mode.items()
        }
        tandem_minus_native_by_mode = {
            mode: _quality_deltas(ordinary_agc, paired_agc)
            for mode, ordinary_agc in ordinary_agc_by_mode.items()
        }
        comparisons.append(
            {
                "level_index": index,
                "tx2_gain_db": fixed["tx2_gain_requested_db"],
                "native_reference_mode": primary_native_mode,
                "native_minus_manual": native_minus_manual_by_mode[primary_native_mode],
                "tandem_minus_manual": _quality_deltas(fixed, paired_agc),
                "tandem_minus_native": tandem_minus_native_by_mode[primary_native_mode],
                "native_minus_manual_by_mode": native_minus_manual_by_mode,
                "tandem_minus_native_by_mode": tandem_minus_native_by_mode,
            }
        )

    strongest = max(float(cell["tx2_gain_requested_db"]) for cell in manual)
    manual_reference = [
        cell for cell in manual if float(cell["tx2_gain_requested_db"]) == strongest
    ]
    manual_tone_evidence = _manual_tone_response(manual)
    tandem_evidence = _observed_tandem_evidence(tandem)
    native_gain_evidence_by_mode = {
        mode: _observed_native_gain_response(cells)
        for mode, cells in native_cells.items()
    }
    for native_mode, evidence in native_gain_evidence_by_mode.items():
        return_required = native_mode != MODE_NATIVE_FAST
        evidence["return_response_required"] = return_required
        evidence["return_response_policy"] = (
            "required_autonomous_recovery"
            if return_required
            else "diagnostic_after_fast_attack_gain_lock"
        )
        evidence["return_response_observed_by_rx"] = [
            response > 0.0
            for response in evidence["return_weak_minus_strong_gain_db"]
        ]
    native_gain_evidence = native_gain_evidence_by_mode[primary_native_mode]
    failures: list[str] = []
    if not manual_reference or not all(
        cell["summary"]["quality_valid"] for cell in manual_reference
    ):
        failures.append("manual strongest/reference rung failed the absolute envelope")
    if not manual_tone_evidence["valid"]:
        failures.append(
            "manual fixed-gain tone did not track/retrace the TX2 trajectory: "
            + ", ".join(manual_tone_evidence["reasons"])
        )
    for mode, cells in (*native_cells.items(), (MODE_TANDEM, tandem)):
        failed = [
            int(cell["level_index"])
            for cell in cells
            if not cell["summary"]["quality_valid"]
        ]
        if failed:
            failures.append(f"{mode} failed absolute quality at levels {failed}")
    for native_mode, evidence in native_gain_evidence_by_mode.items():
        narrow_native_channels = [
            channel
            for channel, span in enumerate(evidence["gain_span_db"])
            if span < NATIVE_MIN_GAIN_SPAN_DB
        ]
        if narrow_native_channels:
            failures.append(
                f"{native_mode} gain did not span at least 1 dB on RX channels "
                f"{narrow_native_channels}"
            )
        for leg, evidence_name in (
            ("outbound", "outbound_weak_minus_strong_gain_db"),
            ("return", "return_weak_minus_strong_gain_db"),
        ):
            if native_mode == MODE_NATIVE_FAST and leg == "return":
                continue
            wrong_native_channels = [
                channel
                for channel, response in enumerate(evidence[evidence_name])
                if response <= 0.0
            ]
            if wrong_native_channels:
                failures.append(
                    f"{native_mode} {leg} leg did not keep weak-TX gain higher "
                    "than strongest-TX gain on RX channels "
                    f"{wrong_native_channels}"
                )
    required_directions = {
        int(TandemEventDirection.INCREASE),
        int(TandemEventDirection.DECREASE),
    }
    if set(tandem_evidence["proven_directions"]) != required_directions:
        failures.append(
            "tandem AUTO did not prove a louder-TX decrease and quieter-TX increase"
        )
    if tandem_evidence["gain_index_span"] < 1:
        failures.append("tandem AUTO gain index did not change")
    if len(tandem_evidence["ownership_epochs"]) != 1:
        failures.append("tandem AUTO ownership epoch was not stable")
    return {
        "verdict": "pass" if not failures else "fail",
        "failures": failures,
        "manual_reference_tx2_gain_db": strongest,
        "manual_tone_evidence": manual_tone_evidence,
        "native_modes": list(native_modes),
        "native_reference_mode": primary_native_mode,
        "native_gain_span_db": native_gain_evidence["gain_span_db"],
        "native_gain_evidence": native_gain_evidence,
        "native_gain_evidence_by_mode": native_gain_evidence_by_mode,
        "tandem_evidence": tandem_evidence,
        "comparisons": comparisons,
        "relative_gate_policy": (
            "report numeric deltas; both adaptive modes must independently pass "
            "the common absolute envelope"
            if native_modes == (MODE_NATIVE,)
            else "report numeric deltas; every adaptive mode must independently "
            "pass the common absolute envelope"
        ),
    }


def run_tandem_quality_matrix(
    radio: Issue46Radio, options: TandemQualityOptions
) -> tuple[dict[str, Any], Path]:
    """Execute every configured mode and preserve an atomic evidence report."""

    validate_options(options)
    if radio.options.sample_rate_hz != options.sample_rate_hz:
        raise ValueError("radio and quality sample rates differ")
    if radio.options.samples_per_channel != options.samples_per_channel:
        raise ValueError("radio and quality sample counts differ")
    if abs(radio.options.tx_gain_db - options.strongest_tx_gain_db) > 0.01:
        raise ValueError("radio TX authorization differs from the trajectory ceiling")
    if radio.options.center_frequency_hz != options.center_frequency_hz:
        raise ValueError("radio and quality center frequencies differ")

    planned_failure_iq_frames = (
        len(quality_modes(options))
        * len(options.tx_gain_trajectory_db)
        * options.measurement_frames
    )
    failure_iq_ledger = _MatrixFailureIqLedger(
        output_dir=options.output_dir,
        planned_accepted_frames=planned_failure_iq_frames,
        expected_frame_bytes=options.samples_per_channel * 8,
    )
    if failure_iq_ledger.preflight_bytes > failure_iq_ledger.maximum_bytes:
        raise ValueError(
            "matrix failure-IQ preflight exceeds its 128 MiB bound: "
            f"{failure_iq_ledger.preflight_bytes} > "
            f"{failure_iq_ledger.maximum_bytes} bytes"
        )

    center_frequency_readback = radio.read_center_frequency()
    if any(
        abs(int(value) - options.center_frequency_hz) > 2
        for value in center_frequency_readback.values()
    ):
        raise EvidenceInvalid(
            "live RX/TX LO readback differs from the requested common center "
            f"frequency: {center_frequency_readback}"
        )
    expected_gain_table = expected_tandem_gain_table(options.center_frequency_hz)

    report_path = (
        options.output_dir / radio.options.serial / "tandem-agc-quality-report.json"
    )
    radio._report_path = report_path
    started = time.monotonic()

    def check_deadline() -> None:
        if time.monotonic() - started >= options.max_seconds:
            raise TimeoutError(
                f"tandem quality matrix exceeded {options.max_seconds:.1f} seconds"
            )

    report: dict[str, Any] = {
        "schema": "plutosdr-fw.tandem-agc-quality.v1",
        "started_unix_ns": time.time_ns(),
        "identity": radio.identity,
        "bench_port_mapping": {
            "stimulus": "bench TX2 = AD9361/IIO TX2",
            "receivers": [
                "bench RX0 = AD9361/IIO RX1",
                "bench RX1 = AD9361/IIO RX2",
            ],
        },
        "rf": {
            "center_frequency_hz_requested": options.center_frequency_hz,
            "center_frequency_hz_readback": center_frequency_readback,
            "expected_tandem_gain_table_id": int(expected_gain_table),
            "expected_tandem_gain_table_name": expected_gain_table.name.lower(),
        },
        "configuration": {
            **asdict(options),
            "output_dir": str(options.output_dir),
            "thresholds": asdict(options.thresholds),
            "minimum_effective_attenuation_db": (
                options.minimum_effective_attenuation_db
            ),
        },
        "safety": {
            "physical_attenuation_db": options.physical_attenuation_db,
            "strongest_tx_gain_db": options.strongest_tx_gain_db,
            "minimum_effective_attenuation_db": (
                options.minimum_effective_attenuation_db
            ),
            "required_effective_attenuation_db": 30.0,
            "tx1_policy": "muted below -80 dB for the entire experiment",
        },
        "initial_tandem_status": radio.tandem_status(),
        "modes": [],
        "verdict": "running",
    }
    _atomic_json(report_path, report)
    ledger_token = _ACTIVE_MATRIX_FAILURE_IQ.set(failure_iq_ledger)
    failure_error: BaseException | None = None
    try:
        for mode in quality_modes(options):
            _run_mode(
                radio,
                mode=mode,
                options=options,
                report=report,
                report_path=report_path,
                check_deadline=check_deadline,
            )
            if mode == MODE_MANUAL:
                manual_cells = _mode_cells(report, MODE_MANUAL)
                strongest = options.strongest_tx_gain_db
                reference_cells = [
                    cell
                    for cell in manual_cells
                    if float(cell["tx2_gain_requested_db"]) == strongest
                ]
                preflight_valid = bool(reference_cells) and all(
                    bool(cell["summary"]["quality_valid"]) for cell in reference_cells
                )
                stimulus_evidence = _manual_tone_response(manual_cells)
                preflight_valid = preflight_valid and bool(stimulus_evidence["valid"])
                report["manual_fixture_preflight"] = {
                    "tx2_gain_db": strongest,
                    "valid": preflight_valid,
                    "cell_count": len(reference_cells),
                    "stimulus_evidence": stimulus_evidence,
                }
                _atomic_json(report_path, report)
                if not preflight_valid:
                    raise EvidenceInvalid(
                        "manual fixture preflight did not qualify both tee branches "
                        "and the commanded TX2 trajectory"
                    )
        evaluation = evaluate_matrix(report)
        report["evaluation"] = evaluation
        report["verdict"] = evaluation["verdict"]
    except BaseException as error:
        failure_error = error
        report["verdict"] = "invalid"
        report["fatal_error"] = _exception_text(error)
        if isinstance(error, _EvidenceInvalidWithDetails):
            report["failure_evidence"] = error.failure_evidence
        _atomic_json(report_path, report)
        raise
    finally:
        cleanup_error: BaseException | None = None
        try:
            radio.mute_all()
            report["final_tandem_status"] = _wait_for_idle(radio)
            radio.configure_rx("manual", manual_gain_db=options.manual_gain_db)
            report["final_rx_state"] = radio.read_rx_state()
        except BaseException as error:
            cleanup_error = error
            report["cleanup_error"] = _exception_text(error)
            if failure_error is None:
                report["verdict"] = "invalid"
                report["fatal_error"] = _exception_text(error)
            raise
        finally:
            try:
                if (
                    report.get("verdict") != "pass"
                    or failure_error is not None
                    or cleanup_error is not None
                ):
                    if cleanup_error is not None:
                        trigger = {
                            "kind": "matrix_cleanup_failed",
                            "error": _exception_text(cleanup_error),
                        }
                        if failure_error is not None:
                            trigger["prior_execution_error"] = _exception_text(
                                failure_error
                            )
                    elif failure_error is not None:
                        trigger = {
                            "kind": "matrix_execution_failed",
                            "error": _exception_text(failure_error),
                        }
                    else:
                        evaluation = report.get("evaluation", {})
                        trigger = {
                            "kind": "matrix_evaluation_failed",
                            "failures": (
                                list(evaluation.get("failures", []))
                                if isinstance(evaluation, Mapping)
                                else []
                            ),
                        }
                    iq_evidence = failure_iq_ledger.flush_failure(trigger=trigger)
                    existing = report.get("failure_evidence")
                    failure_evidence = (
                        dict(existing) if isinstance(existing, Mapping) else {}
                    )
                    failure_evidence.setdefault("kind", trigger["kind"])
                    failure_evidence["iq_ledger"] = iq_evidence
                    report["failure_evidence"] = failure_evidence
                else:
                    failure_iq_ledger.discard()
            finally:
                _ACTIVE_MATRIX_FAILURE_IQ.reset(ledger_token)
            report["elapsed_seconds"] = time.monotonic() - started
            report["completed_unix_ns"] = time.time_ns()
            _atomic_json(report_path, report)
    return report, report_path
