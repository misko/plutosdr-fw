"""Weak-only qualification probe for tandem transient metadata transport.

This module deliberately does not run a gain transient.  It asks the current
metadata provider to return one exact, gap-free 65,536-sample sequence while
the tandem controller is in AUTO at the already-qualified -45 dB TX2 rung.  A
same-level TX2 write then exercises control/data contention without increasing
RF power.  The resulting artifact can qualify the transport design for a later
transient attempt, but can never be a firmware-release PASS by itself.
"""

from __future__ import annotations

import errno
import hashlib
import json
import math
import os
import queue
import re
import statistics
import struct
import subprocess
import threading
import time
from builtins import BaseExceptionGroup
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from .experiment import EvidenceInvalid, FixtureSafetyError, Issue46Radio
from .metadata_abi import (
    FEATURE_AD9361_TEMPERATURE,
    FEATURE_FPGA_GAIN_EVENTS,
    FEATURE_HARDWARE_SAMPLE_COUNTER,
    FEATURE_TANDEM_METADATA,
    FLAG_HARDWARE_SAMPLE_COUNTER_VALID,
    FLAG_SAMPLE_SEQUENCE_VALID,
    FLAG_TANDEM_METADATA_VALID,
    TANDEM_REQUEST,
    TANDEM_UNSAFE_FLAGS,
    TandemEventDirection,
    TandemEventReason,
    TandemFrameMetadata,
    TandemMode,
    TandemState,
    build_tandem_request,
    maximum_tandem_events_per_frame,
    parse_tandem_frame_metadata,
)
from .tandem_quality import (
    MODE_TANDEM,
    TandemQualityOptions,
    expected_tandem_gain_table,
    validate_options,
)
from .transient_hardware import (
    TransientCaptureOptions,
    TransientRadioTransport,
    _capture_frame,
    _CaptureState,
    _check_effective_attenuation,
    _DeferredFrame,
    _exception_text,
    _extend_low32_near,
    _rx_state,
    _strict_low32_counter,
    _wait_for_idle,
)
from .transient_quality import (
    StimulusCommand,
    analyze_immediate_dual_rx,
    timestamp_stimulus_command,
)

PROBE_SCHEMA = "plutosdr-fw.tandem-agc-transient-transport-probe.v2"
PROBE_VERDICT = "qualified_transport"
PROBE_PENDING_VERDICT = "qualified_transport_pending_cleanup"
PROBE_THREAD_NAME = "tandem-transient-transport-probe-acquisition"
PROBE_EXACT_SERIAL = "1040007c4a94000211000b009186843ef2"
PROBE_EXACT_FIRMWARE_VERSION = "v0.41-plutoplus-spf-tandem-agc-v8-rc2"
PROBE_EXACT_FIRMWARE_PATTERN = (
    r"^v0[.]41-plutoplus-spf-tandem-agc-v8-rc2$"
)
PROBE_EXACT_LIBIIO_COMMIT = "70739d25ec1fa7b95d9069bd26a3e4192fdb3851"
PROBE_EXACT_LIBIIO_TAG = "tandem-agc-v8-rc3-source/libiio-v1"
PROBE_EXACT_LIBIIO_REF = f"refs/tags/{PROBE_EXACT_LIBIIO_TAG}"

_PROBE_MANIFEST_PATH = "manifests/tandem-agc-v8-rc3-source.yaml"
_PROBE_LOCAL_RUNTIME_DEPENDENCIES = (
    "pytest.ini",
    "scripts/run_tandem_agc_quality_hardware.sh",
    _PROBE_MANIFEST_PATH,
    "tests/__init__.py",
    "tests/radio_hardware/__init__.py",
    "tests/radio_hardware/conftest.py",
    "tests/radio_hardware/continuity.py",
    "tests/radio_hardware/experiment.py",
    "tests/radio_hardware/metadata_abi.py",
    "tests/radio_hardware/pnxx.py",
    "tests/radio_hardware/requirements.txt",
    "tests/radio_hardware/tandem_quality.py",
    "tests/radio_hardware/test_transient_transport_probe.py",
    "tests/radio_hardware/tone_quality.py",
    "tests/radio_hardware/transient_hardware.py",
    "tests/radio_hardware/transient_quality.py",
    "tests/radio_hardware/transient_transport_probe.py",
)

_PROBE_WEAK_GAIN_DB = -45.0
_PROBE_AUTO_INITIAL_GAIN_DB = 62
_PROBE_FRAME_SAMPLES = 65_536
_PROBE_KERNEL_BUFFERS = 8
_PROBE_BATCH_FRAMES = 64
_PROBE_COMMAND_TARGET_FRAMES = 40
_PROBE_FULLY_PRE_COMMAND_FRAMES = 32
_PROBE_FULLY_POST_COMMAND_FRAMES = 8
_PROBE_STABLE_FRAMES = 3
_PROBE_ANCHOR_SAMPLES = 8_192
_PROBE_WINDOW_SAMPLES = 1_024
_PROBE_QUEUE_FRAMES = 4
_PROBE_METADATA_CAPACITY_BYTES = 64 * 1024
_PROBE_SIZE_T_BYTES = 8
_PROBE_MAX_PYTHON_RAW_BYTES = 32 * 1024 * 1024
_PROBE_MAX_CORE_BATCH_BYTES = 64 * 1024 * 1024
_PROBE_MAX_AGGREGATE_BYTES = (
    _PROBE_MAX_PYTHON_RAW_BYTES + _PROBE_MAX_CORE_BATCH_BYTES
)
_PROBE_TARGET_COARSE_GUARD_SAMPLES = 65_536
_PROBE_TARGET_FINE_SLEEP_SAMPLES = 4_096
_PROBE_TARGET_MAX_POLL_READS = 64
_PROBE_WORKER_WAIT_SECONDS = 6.0
_PROBE_REQUIRED_METADATA_FEATURES = (
    FEATURE_AD9361_TEMPERATURE
    | FEATURE_FPGA_GAIN_EVENTS
    | FEATURE_HARDWARE_SAMPLE_COUNTER
    | FEATURE_TANDEM_METADATA
)
_PROBE_REQUIRED_METADATA_FLAGS = (
    FLAG_SAMPLE_SEQUENCE_VALID
    | FLAG_HARDWARE_SAMPLE_COUNTER_VALID
    | FLAG_TANDEM_METADATA_VALID
)
_PROBE_METADATA_HEADER_BYTES = 180 + 64 * 32 + 64 * 16 + 4
_PROBE_RAW_SCHEDULE_FIELDS = frozenset(
    {
        "register_address",
        "counter_width_bits",
        "counter_source",
        "post_open_baseline_raw",
        "target_offset_frames",
        "target_offset_samples",
        "target_raw",
        "last_below_raw",
        "raw_a_prewrite",
        "raw_post_write_initial",
        "raw_b_first_advance",
        "raw_c_causal_advance",
        "target_poll_read_count",
        "target_poll_policy",
        "target_coarse_guard_samples",
        "target_fine_sleep_samples",
        "target_max_poll_reads",
        "target_poll_observations",
        "target_total_requested_sleep_samples",
        "post_write_read_count",
        "target_overshoot_samples",
        "causal_uncertainty_samples",
        "worker_in_flight_at_command",
    }
)


@dataclass(frozen=True)
class TransientTransportProbeOptions:
    """Frozen safety and evidence bounds for the qualification-only probe."""

    weak_stimulus_tx_gain_db: float = _PROBE_WEAK_GAIN_DB
    auto_initial_gain_db: int = _PROBE_AUTO_INITIAL_GAIN_DB
    frame_samples: int = _PROBE_FRAME_SAMPLES
    kernel_buffers: int = _PROBE_KERNEL_BUFFERS
    batch_frames: int = _PROBE_BATCH_FRAMES
    command_target_frames: int = _PROBE_COMMAND_TARGET_FRAMES
    fully_pre_command_frames: int = _PROBE_FULLY_PRE_COMMAND_FRAMES
    fully_post_command_frames: int = _PROBE_FULLY_POST_COMMAND_FRAMES
    stable_frames: int = _PROBE_STABLE_FRAMES
    anchor_samples: int = _PROBE_ANCHOR_SAMPLES
    window_samples: int = _PROBE_WINDOW_SAMPLES
    max_host_jitter_ns: int = 50_000_000
    max_command_sample_uncertainty: int = 16_384
    readback_tolerance_db: float = 0.25
    maximum_retained_raw_bytes: int = _PROBE_MAX_PYTHON_RAW_BYTES
    maximum_core_batch_bytes: int = _PROBE_MAX_CORE_BATCH_BYTES
    maximum_aggregate_bytes: int = _PROBE_MAX_AGGREGATE_BYTES

    @property
    def target_sample_offset(self) -> int:
        return self.command_target_frames * self.frame_samples

    @property
    def retained_frames(self) -> int:
        return self.batch_frames

    @property
    def maximum_python_raw_frames(self) -> int:
        # The retained list, worker queue, and producer own disjoint frames
        # from the same one-batch budget; they never duplicate raw IQ bytes.
        return self.batch_frames

    @property
    def maximum_python_raw_bytes(self) -> int:
        return self.maximum_python_raw_frames * self.frame_samples * 8

    @property
    def core_batch_cache_bytes(self) -> int:
        per_frame = (
            self.frame_samples * 8
            + _PROBE_METADATA_CAPACITY_BYTES
            + 2 * _PROBE_SIZE_T_BYTES
        )
        return self.batch_frames * per_frame

    @property
    def aggregate_resident_bytes(self) -> int:
        iq_frame_bytes = self.frame_samples * 8
        return sum(
            (
                self.core_batch_cache_bytes,
                iq_frame_bytes,  # ordinary libiio C buffer
                self.maximum_python_raw_bytes,
                iq_frame_bytes,  # transient Buffer.read() bytearray
                _PROBE_METADATA_CAPACITY_BYTES,  # ctypes refill scratch
                _PROBE_METADATA_CAPACITY_BYTES,  # returned metadata bytes
                self.batch_frames
                * _PROBE_METADATA_CAPACITY_BYTES,  # parsed-evidence reservation
                self.kernel_buffers * iq_frame_bytes,  # device K8 DMA reservation
            )
        )


_DEFAULT_PROBE_OPTIONS = TransientTransportProbeOptions()


class _ProbeBatchCaptureWorker:
    """Drain exactly one configured metadata batch on one acquisition thread."""

    def __init__(
        self,
        acquire: Callable[[], _DeferredFrame],
        *,
        batch_frames: int,
        thread_name: str,
    ) -> None:
        self._acquire = acquire
        self._batch_frames = batch_frames
        self._queue: queue.Queue[_DeferredFrame | BaseException] = queue.Queue(
            maxsize=_PROBE_QUEUE_FRAMES
        )
        self._stop = threading.Event()
        self._first_refill_started = threading.Event()
        self._first_refill_completed = threading.Event()
        self._finished = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=thread_name,
            daemon=True,
        )
        self._terminal_error: BaseException | None = None
        self._started = False
        self.produced_frames = 0
        self.consumed_frames = 0
        self.discarded_tail_frames = 0

    @property
    def queue_capacity_frames(self) -> int:
        return self._queue.maxsize

    @property
    def first_refill_in_flight(self) -> bool:
        return self._first_refill_started.is_set() and not (
            self._first_refill_completed.is_set()
        )

    @property
    def is_alive(self) -> bool:
        return self._thread.is_alive()

    @property
    def finished(self) -> bool:
        return self._finished.is_set()

    def start(self) -> None:
        self._thread.start()
        self._started = True
        if not self._first_refill_started.wait(_PROBE_WORKER_WAIT_SECONDS):
            raise EvidenceInvalid(
                "transport probe acquisition worker did not initiate its batch refill"
            )

    def _offer(self, item: _DeferredFrame | BaseException) -> bool:
        while not self._stop.is_set():
            try:
                self._queue.put(item, timeout=0.05)
                return True
            except queue.Full:
                continue
        return False

    def _run(self) -> None:
        try:
            for index in range(self._batch_frames):
                if self._stop.is_set():
                    return
                if index == 0:
                    self._first_refill_started.set()
                try:
                    frame = self._acquire()
                finally:
                    if index == 0:
                        self._first_refill_completed.set()
                self.produced_frames += 1
                if not self._offer(frame):
                    self.discarded_tail_frames += 1
                    return
        except BaseException as error:  # noqa: BLE001 - cross-thread propagation
            if not (
                self._stop.is_set()
                and isinstance(error, OSError)
                and error.errno == errno.EBADF
            ):
                self._terminal_error = error
                self._offer(error)
        finally:
            self._finished.set()

    def require_first_refill_in_flight(self) -> None:
        if self.first_refill_in_flight:
            return
        if self._terminal_error is not None:
            error = self._terminal_error
            self._terminal_error = None
            try:
                queued = self._queue.get_nowait()
            except queue.Empty:
                queued = None
            if queued is not None and queued is not error:
                self._queue.put_nowait(queued)
            raise error.with_traceback(error.__traceback__)
        raise EvidenceInvalid(
            "transport probe full metadata batch completed before the "
            "predeclared command target"
        )

    def take(self) -> _DeferredFrame:
        try:
            item = self._queue.get(timeout=_PROBE_WORKER_WAIT_SECONDS)
        except queue.Empty as exc:
            raise EvidenceInvalid(
                "transport probe acquisition worker returned no cached frame"
            ) from exc
        if isinstance(item, BaseException):
            self._terminal_error = None
            raise item.with_traceback(item.__traceback__)
        self.consumed_frames += 1
        return item

    def request_stop(self) -> None:
        self._stop.set()

    def stop(self) -> None:
        self.request_stop()
        if not self._started:
            return
        self._thread.join(timeout=_PROBE_WORKER_WAIT_SECONDS)
        if self._thread.is_alive():
            raise EvidenceInvalid("transport probe acquisition worker did not stop")
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, BaseException):
                self._terminal_error = None
                raise item.with_traceback(item.__traceback__)
            self.discarded_tail_frames += 1
        if self._terminal_error is not None:
            error = self._terminal_error
            self._terminal_error = None
            raise error.with_traceback(error.__traceback__)


def _durable_exception_text(error: BaseException) -> str:
    """Render every nested failure leaf into the durable invalid artifact."""

    rendered: list[str] = []

    def visit(current: BaseException, path: str) -> None:
        rendered.append(f"{path}: {_exception_text(current)}")
        if isinstance(current, BaseExceptionGroup):
            for index, child in enumerate(current.exceptions):
                visit(child, f"{path}.{index}")

    visit(error, "root")
    return " | ".join(rendered)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_bytes(repository: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ("git", "-C", str(repository), *arguments),
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = (
            error.stderr.decode("utf-8", errors="replace").strip()
            if isinstance(error, subprocess.CalledProcessError)
            else str(error)
        )
        raise EvidenceInvalid(
            f"transport probe provenance git {' '.join(arguments)} failed: {detail}"
        ) from error
    return completed.stdout


def _git_text(repository: Path, *arguments: str) -> str:
    return _git_bytes(repository, *arguments).decode("utf-8").strip()


def _manifest_source_identity(raw: bytes) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in raw.decode("utf-8").splitlines():
        key, separator, value = line.partition(":")
        if separator and key in {"libiio_0_25_source", "libiio_0_25_ref"}:
            values[key] = value.strip()
    expected = {
        "libiio_0_25_source": PROBE_EXACT_LIBIIO_COMMIT,
        "libiio_0_25_ref": PROBE_EXACT_LIBIIO_REF,
    }
    if values != expected:
        raise EvidenceInvalid(
            f"transport probe source manifest libiio identity is {values}, "
            f"expected {expected}"
        )
    return values


def _firmware_repository() -> Path:
    return Path(__file__).resolve().parents[2]


def _attest_firmware_runner(repository: Path | None = None) -> dict[str, Any]:
    repository = (
        _firmware_repository() if repository is None else repository.resolve()
    )
    commit = _git_text(repository, "rev-parse", "HEAD")
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise EvidenceInvalid("transport probe runner commit is not exact SHA-1")

    dependencies = []
    manifest_blob: bytes | None = None
    for relative_path in _PROBE_LOCAL_RUNTIME_DEPENDENCIES:
        absolute_path = (repository / relative_path).resolve()
        if not absolute_path.is_file():
            raise EvidenceInvalid(
                f"transport probe runtime dependency is absent: {relative_path}"
            )
        committed = _git_bytes(repository, "show", f"{commit}:{relative_path}")
        observed_sha256 = _sha256_file(absolute_path)
        commit_blob_sha256 = hashlib.sha256(committed).hexdigest()
        if observed_sha256 != commit_blob_sha256:
            raise EvidenceInvalid(
                f"transport probe runtime dependency differs from {commit}: "
                f"{relative_path}"
            )
        if relative_path == _PROBE_MANIFEST_PATH:
            manifest_blob = committed
        dependencies.append(
            {
                "relative_path": relative_path,
                "absolute_path": str(absolute_path),
                "observed_sha256": observed_sha256,
                "commit_blob_sha256": commit_blob_sha256,
            }
        )
    if manifest_blob is None:
        raise EvidenceInvalid("transport probe source manifest was not attested")
    manifest_identity = _manifest_source_identity(manifest_blob)
    return {
        "repository": str(repository),
        "commit": commit,
        "local_dependencies": dependencies,
        "manifest_relative_path": _PROBE_MANIFEST_PATH,
        "manifest_libiio_identity": manifest_identity,
    }


def _cmake_source_directory(cache: Path) -> Path:
    if not cache.is_file():
        raise EvidenceInvalid(f"transport probe CMake cache is absent: {cache}")
    prefix = "CMAKE_HOME_DIRECTORY:INTERNAL="
    values = [
        line[len(prefix) :]
        for line in cache.read_text(encoding="utf-8").splitlines()
        if line.startswith(prefix)
    ]
    if len(values) != 1:
        raise EvidenceInvalid("transport probe CMake source identity is ambiguous")
    return Path(values[0]).resolve()


def _attest_host_libiio(iio_module: Any) -> dict[str, Any]:
    environment_commit = os.environ.get("PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT", "")
    if environment_commit != PROBE_EXACT_LIBIIO_COMMIT:
        raise EvidenceInvalid(
            "transport probe launcher did not attest exact protected libiio "
            f"{PROBE_EXACT_LIBIIO_COMMIT}"
        )

    pylibiio = Path(str(getattr(iio_module, "__file__", ""))).resolve()
    if not pylibiio.is_file() or pylibiio.parts[-3:] != (
        "bindings",
        "python",
        "iio.py",
    ):
        raise EvidenceInvalid(
            f"transport probe pylibiio path is not source-backed: {pylibiio}"
        )
    source = pylibiio.parents[2]
    source_head = _git_text(source, "rev-parse", "HEAD")
    protected_tag_commit = _git_text(
        source, "rev-parse", f"{PROBE_EXACT_LIBIIO_REF}^{{commit}}"
    )
    if source_head != PROBE_EXACT_LIBIIO_COMMIT or (
        protected_tag_commit != PROBE_EXACT_LIBIIO_COMMIT
    ):
        raise EvidenceInvalid(
            "transport probe libiio HEAD/protected tag does not resolve to the "
            "exact qualified commit"
        )
    if _git_text(source, "status", "--porcelain", "--untracked-files=no"):
        raise EvidenceInvalid("transport probe libiio source has tracked changes")

    mapped = sorted(
        {
            str(Path(line.rsplit(maxsplit=1)[-1]).resolve())
            for line in Path("/proc/self/maps").read_text(encoding="utf-8").splitlines()
            if "/libiio.so" in line.rsplit(maxsplit=1)[-1]
        }
    )
    if len(mapped) != 1:
        raise EvidenceInvalid(
            f"transport probe mapped libiio set is not unique: {mapped}"
        )
    mapped_shared_object = Path(mapped[0])
    build = mapped_shared_object.parent.resolve()
    if not mapped_shared_object.is_file() or not mapped_shared_object.is_relative_to(
        build
    ):
        raise EvidenceInvalid("transport probe mapped libiio path is invalid")
    cmake_cache = build / "CMakeCache.txt"
    cmake_source = _cmake_source_directory(cmake_cache)
    if cmake_source != source:
        raise EvidenceInvalid(
            "transport probe mapped libiio build belongs to another source tree"
        )

    pylibiio_commit_blob = _git_bytes(
        source, "show", f"{PROBE_EXACT_LIBIIO_COMMIT}:bindings/python/iio.py"
    )
    pylibiio_sha256 = _sha256_file(pylibiio)
    pylibiio_commit_blob_sha256 = hashlib.sha256(pylibiio_commit_blob).hexdigest()
    if pylibiio_sha256 != pylibiio_commit_blob_sha256:
        raise EvidenceInvalid(
            "transport probe pylibiio differs from the exact protected commit"
        )
    return {
        "source_commit": PROBE_EXACT_LIBIIO_COMMIT,
        "protected_source_tag": PROBE_EXACT_LIBIIO_TAG,
        "protected_source_ref": PROBE_EXACT_LIBIIO_REF,
        "source_directory": str(source),
        "source_head_commit": source_head,
        "protected_tag_commit": protected_tag_commit,
        "source_tracked_clean": True,
        "build_directory": str(build),
        "cmake_cache_path": str(cmake_cache.resolve()),
        "cmake_source_directory": str(cmake_source),
        "mapped_shared_objects": mapped,
        "mapped_shared_object": str(mapped_shared_object),
        "mapped_shared_object_sha256": _sha256_file(mapped_shared_object),
        "pylibiio_path": str(pylibiio),
        "pylibiio_sha256": pylibiio_sha256,
        "pylibiio_commit_blob_sha256": pylibiio_commit_blob_sha256,
    }


def _attest_runtime_provenance(iio_module: Any) -> dict[str, Any]:
    return {
        "host_libiio": _attest_host_libiio(iio_module),
        "firmware_runner": _attest_firmware_runner(),
    }


def validate_transient_transport_probe_options(
    quality: TandemQualityOptions, probe: TransientTransportProbeOptions
) -> None:
    """Reject every weakening or ambiguity before a radio object is opened."""

    validate_options(quality)
    if type(probe.auto_initial_gain_db) is not int:
        raise TypeError("transport probe AUTO initial gain must be an exact integer")
    exact = {
        "weak_stimulus_tx_gain_db": (
            probe.weak_stimulus_tx_gain_db,
            _PROBE_WEAK_GAIN_DB,
        ),
        "auto_initial_gain_db": (
            probe.auto_initial_gain_db,
            _PROBE_AUTO_INITIAL_GAIN_DB,
        ),
        "frame_samples": (probe.frame_samples, _PROBE_FRAME_SAMPLES),
        "kernel_buffers": (probe.kernel_buffers, _PROBE_KERNEL_BUFFERS),
        "batch_frames": (probe.batch_frames, _PROBE_BATCH_FRAMES),
        "command_target_frames": (
            probe.command_target_frames,
            _PROBE_COMMAND_TARGET_FRAMES,
        ),
        "fully_pre_command_frames": (
            probe.fully_pre_command_frames,
            _PROBE_FULLY_PRE_COMMAND_FRAMES,
        ),
        "fully_post_command_frames": (
            probe.fully_post_command_frames,
            _PROBE_FULLY_POST_COMMAND_FRAMES,
        ),
        "stable_frames": (probe.stable_frames, _PROBE_STABLE_FRAMES),
        "anchor_samples": (probe.anchor_samples, _PROBE_ANCHOR_SAMPLES),
        "window_samples": (probe.window_samples, _PROBE_WINDOW_SAMPLES),
        "maximum_retained_raw_bytes": (
            probe.maximum_retained_raw_bytes,
            _PROBE_MAX_PYTHON_RAW_BYTES,
        ),
        "maximum_core_batch_bytes": (
            probe.maximum_core_batch_bytes,
            _PROBE_MAX_CORE_BATCH_BYTES,
        ),
        "maximum_aggregate_bytes": (
            probe.maximum_aggregate_bytes,
            _PROBE_MAX_AGGREGATE_BYTES,
        ),
    }
    for name, (actual, expected) in exact.items():
        if actual != expected:
            raise ValueError(
                f"transport probe {name} is frozen at {expected!r}, got {actual!r}"
            )
    if isinstance(probe.max_host_jitter_ns, bool) or not isinstance(
        probe.max_host_jitter_ns, int
    ):
        raise TypeError("transport probe host-jitter bound must be an integer")
    if not 0 < probe.max_host_jitter_ns <= 50_000_000:
        raise ValueError("transport probe host-jitter bound must be in (0, 50000000]")
    if isinstance(probe.max_command_sample_uncertainty, bool) or not isinstance(
        probe.max_command_sample_uncertainty, int
    ):
        raise TypeError("transport probe sample-uncertainty bound must be an integer")
    if not probe.anchor_samples <= probe.max_command_sample_uncertainty <= 16_384:
        raise ValueError(
            "transport probe sample uncertainty must cover the 8192-sample "
            "anchor without exceeding 16384 samples"
        )
    if (
        isinstance(probe.readback_tolerance_db, bool)
        or not isinstance(probe.readback_tolerance_db, (int, float))
        or not math.isfinite(float(probe.readback_tolerance_db))
        or not 0 <= probe.readback_tolerance_db <= 0.25
    ):
        raise ValueError("transport probe readback tolerance must be in [0, 0.25] dB")
    if probe.weak_stimulus_tx_gain_db not in quality.tx_gain_trajectory_db:
        raise ValueError(
            "transport probe weak stimulus must be a configured quality rung"
        )
    if quality.samples_per_channel != probe.frame_samples:
        raise ValueError(
            "transport probe requires an exact 65536-sample quality configuration"
        )
    if quality.physical_attenuation_db - probe.weak_stimulus_tx_gain_db < 30.0:
        raise ValueError("transport probe weak stimulus violates 30 dB attenuation")
    if struct.calcsize("P") != _PROBE_SIZE_T_BYTES:
        raise ValueError("transport probe requires an exact 64-bit host size_t")
    if probe.maximum_python_raw_bytes > probe.maximum_retained_raw_bytes:
        raise ValueError("transport probe bounded Python IQ retention exceeds 32 MiB")
    if probe.core_batch_cache_bytes > probe.maximum_core_batch_bytes:
        raise ValueError("transport probe libiio batch cache exceeds 64 MiB")
    if probe.aggregate_resident_bytes > probe.maximum_aggregate_bytes:
        raise ValueError("transport probe aggregate capture memory exceeds 96 MiB")


def _validate_probe_radio_options(
    options: Any,
    quality: TandemQualityOptions,
    probe: TransientTransportProbeOptions,
) -> None:
    if type(getattr(options, "serial", None)) is not str or (
        options.serial != PROBE_EXACT_SERIAL
    ):
        raise ValueError("transport probe is authorized only for exact R18 serial")
    if type(getattr(options, "firmware_pattern", None)) is not str or (
        options.firmware_pattern != PROBE_EXACT_FIRMWARE_PATTERN
    ):
        raise ValueError("transport probe firmware pattern is not exact anchored RC2")
    if type(getattr(options, "libiio_source_commit", None)) is not str or (
        options.libiio_source_commit != PROBE_EXACT_LIBIIO_COMMIT
    ):
        raise ValueError("transport probe radio options do not bind exact host libiio")
    if getattr(options, "uri", None) is not None or (
        getattr(options, "allow_non_usb", None) is not False
    ):
        raise ValueError("transport probe requires unique serial-resolved local USB")
    if getattr(options, "sample_rate_hz", None) != quality.sample_rate_hz:
        raise ValueError("radio and transport-probe sample rates differ")
    if getattr(options, "samples_per_channel", None) != probe.frame_samples:
        raise ValueError("radio buffer authorization differs from transport probe")
    if float(getattr(options, "tx_gain_db", math.nan)) != (
        probe.weak_stimulus_tx_gain_db
    ):
        raise ValueError("radio TX ceiling must equal the -45 dB probe level")
    if getattr(options, "center_frequency_hz", None) != quality.center_frequency_hz:
        raise ValueError("radio and transport-probe center frequencies differ")
    if float(getattr(options, "attenuation_db", math.nan)) != (
        quality.physical_attenuation_db
    ):
        raise ValueError("radio and transport-probe attenuation declarations differ")
    try:
        radio_output = Path(options.output_dir).resolve()
    except (AttributeError, TypeError) as error:
        raise ValueError("transport probe radio output directory is invalid") from error
    if radio_output != quality.output_dir.resolve():
        raise ValueError("radio and transport-probe output directories differ")


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _quality_configuration(quality: TandemQualityOptions) -> dict[str, Any]:
    result = asdict(quality)
    result["output_dir"] = str(quality.output_dir)
    result["thresholds"] = asdict(quality.thresholds)
    return result


_REQUEST_FIELD_NAMES = (
    "magic",
    "abi_version",
    "request_bytes",
    "required_features",
    "mode",
    "observation_capacity",
    "event_capacity",
    "minimum_gain_db",
    "maximum_gain_db",
    "initial_gain_db",
    "power_measurement_samples",
    "low_power_dwell_periods",
    "cooldown_periods",
    "pulse_high_cycles",
    "pulse_low_cycles",
    "detector_blanking_cycles",
    "low_power_threshold",
    "large_lmt_overload_threshold",
    "large_adc_overload_threshold",
    "small_adc_overload_threshold",
    "observation_overflow_policy",
    "event_overflow_policy",
    "reserved_0",
    "reserved_1",
    "reserved_2",
    "reserved_3",
    "reserved_4",
    "reserved_5",
    "reserved_6",
    "reserved_7",
)


def _request_evidence(request: bytes) -> dict[str, Any]:
    unpacked = TANDEM_REQUEST.unpack(request)
    decoded = dict(zip(_REQUEST_FIELD_NAMES, unpacked, strict=True))
    return {
        "wire_bytes": len(request),
        "wire_hex": request.hex(),
        "sha256": hashlib.sha256(request).hexdigest(),
        "decoded": decoded,
    }


def _expected_threshold_provenance(quality: TandemQualityOptions) -> int:
    return (
        quality.tandem_low_power_threshold
        | quality.tandem_large_lmt_overload_threshold << 8
        | quality.tandem_large_adc_overload_threshold << 16
        | quality.tandem_small_adc_overload_threshold << 24
    )


def _full_metadata_dict(metadata: TandemFrameMetadata) -> dict[str, Any]:
    events = []
    for event in metadata.gain_events:
        events.append(
            {
                "sample_sequence": int(event.sample_sequence),
                "event_sequence": int(event.event_sequence),
                "flags": int(event.flags),
                "direction": int(event.direction),
                "direction_name": event.direction.name.lower(),
                "reason": int(event.reason),
                "reason_name": event.reason.name.lower(),
                "rx1_gain_index": int(event.rx1_gain_index),
                "rx2_gain_index": int(event.rx2_gain_index),
            }
        )
    return {
        "version": metadata.version,
        "header_bytes": metadata.header_bytes,
        "features": metadata.features,
        "flags": metadata.flags,
        "stream_id": metadata.stream_id,
        "buffer_sequence": metadata.buffer_sequence,
        "first_sample_sequence": metadata.first_sample_sequence,
        "samples_per_channel": metadata.samples_per_channel,
        "iq_payload_bytes": metadata.iq_payload_bytes,
        "enabled_scan_mask": metadata.enabled_scan_mask,
        "sample_format": metadata.sample_format,
        "channel_count": metadata.channel_count,
        "observation_count": metadata.observation_count,
        "observation_capacity": metadata.observation_capacity,
        "event_count": metadata.event_count,
        "event_capacity": metadata.event_capacity,
        "observation_overflow_count": metadata.observation_overflow_count,
        "event_overflow_count": metadata.event_overflow_count,
        "ownership_epoch": metadata.ownership_epoch,
        "tandem_state": int(metadata.tandem_state),
        "tandem_state_name": metadata.tandem_state.name.lower(),
        "tandem_fault_flags": metadata.tandem_fault_flags,
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
        "gain_events": events,
    }


def _capture_adapter(probe: TransientTransportProbeOptions) -> TransientCaptureOptions:
    return TransientCaptureOptions(
        weak_stimulus_tx_gain_db=probe.weak_stimulus_tx_gain_db,
        frame_samples=probe.frame_samples,
        window_samples=probe.window_samples,
        max_host_jitter_ns=probe.max_host_jitter_ns,
        max_sample_uncertainty=probe.max_command_sample_uncertainty,
        readback_tolerance_db=probe.readback_tolerance_db,
    )


def _probe_auto_request(
    quality: TandemQualityOptions, probe: TransientTransportProbeOptions
) -> bytes:
    """Build the probe-only AUTO request at its stable maximum-gain clamp.

    The weak -45 dB stimulus needs no downward response on the qualified R18
    fixture.  Starting AUTO at the request maximum prevents the controller's
    expected low-power increases from preceding the first provider frame.  A
    real startup transition remains disqualifying; this only changes the
    explicit initial condition.
    """

    return build_tandem_request(
        mode=TandemMode.AUTO,
        initial_gain_db=probe.auto_initial_gain_db,
        power_measurement_samples=quality.tandem_power_measurement_samples,
        low_power_dwell_periods=quality.tandem_low_power_dwell_periods,
        cooldown_periods=quality.tandem_cooldown_periods,
        low_power_threshold=quality.tandem_low_power_threshold,
        large_lmt_overload_threshold=quality.tandem_large_lmt_overload_threshold,
        large_adc_overload_threshold=quality.tandem_large_adc_overload_threshold,
        small_adc_overload_threshold=quality.tandem_small_adc_overload_threshold,
        samples_per_channel=probe.frame_samples,
    )


def _validate_probe_metadata(
    metadata: TandemFrameMetadata,
    *,
    frame_index: int,
    quality: TandemQualityOptions,
    probe: TransientTransportProbeOptions,
    session_provenance: dict[str, Any],
    event_timing_state: dict[str, int],
    previous_refill_ns: int | None,
    refill_ns: int,
) -> None:
    if metadata.version != 5:
        raise EvidenceInvalid("transport probe requires metadata protocol v5")
    if metadata.header_bytes != _PROBE_METADATA_HEADER_BYTES:
        raise EvidenceInvalid("transport probe metadata has an unexpected layout")
    if metadata.features & _PROBE_REQUIRED_METADATA_FEATURES != (
        _PROBE_REQUIRED_METADATA_FEATURES
    ):
        raise EvidenceInvalid("transport probe metadata lacks required features")
    if metadata.flags & _PROBE_REQUIRED_METADATA_FLAGS != (
        _PROBE_REQUIRED_METADATA_FLAGS
    ):
        raise EvidenceInvalid("transport probe metadata lacks required valid flags")
    if metadata.flags & TANDEM_UNSAFE_FLAGS:
        raise EvidenceInvalid("transport probe metadata carries an unsafe flag")
    if metadata.stream_id <= 0 or metadata.ownership_epoch <= 0:
        raise EvidenceInvalid("transport probe stream and ownership must be nonzero")
    if frame_index == 0 and metadata.buffer_sequence != 0:
        raise EvidenceInvalid(
            "transport probe first accepted provider buffer sequence is not zero"
        )
    if frame_index == 0 and metadata.tandem_transition_count != len(
        metadata.gain_events
    ):
        raise EvidenceInvalid(
            "transport probe first frame has unrepresented prior transitions: "
            f"buffer_sequence={metadata.buffer_sequence}, "
            f"first_sample_sequence={metadata.first_sample_sequence}, "
            f"transition_count={metadata.tandem_transition_count}, "
            f"visible_events={len(metadata.gain_events)}, "
            f"endpoint={metadata.bench_gain_indices}"
        )
    if frame_index == 0 and (
        metadata.tandem_transition_count != 0 or metadata.gain_events
    ):
        raise EvidenceInvalid(
            "transport probe first frame contains a represented startup transition: "
            f"buffer_sequence={metadata.buffer_sequence}, "
            f"first_sample_sequence={metadata.first_sample_sequence}, "
            f"transition_count={metadata.tandem_transition_count}, "
            f"visible_events={len(metadata.gain_events)}, "
            f"endpoint={metadata.bench_gain_indices}"
        )
    if metadata.observation_capacity != 64 or metadata.event_capacity != 64:
        raise EvidenceInvalid("transport probe metadata capacity differs from request")
    if not 0 <= metadata.observation_count <= metadata.observation_capacity:
        raise EvidenceInvalid("transport probe observation count exceeds capacity")
    provider_observation_interval = probe.frame_samples // 4
    overlap_safe_observations = probe.frame_samples // provider_observation_interval + 1
    if metadata.observation_count > overlap_safe_observations:
        raise EvidenceInvalid(
            "transport probe observation count exceeds the provider overlap bound"
        )
    if metadata.event_count != len(metadata.gain_events):
        raise EvidenceInvalid("transport probe event count differs from event ledger")
    if not 0 <= metadata.event_count <= metadata.event_capacity:
        raise EvidenceInvalid("transport probe event count exceeds capacity")
    if metadata.tandem_fault_flags:
        raise EvidenceInvalid("transport probe metadata carries tandem fault flags")
    if metadata.tandem_state is not TandemState.ARMED_AUTO:
        raise EvidenceInvalid("transport probe controller left tandem AUTO")
    if metadata.gain_table_id is not expected_tandem_gain_table(
        quality.center_frequency_hz
    ):
        raise EvidenceInvalid("transport probe selected the wrong gain table")
    if (
        metadata.minimum_gain_db != 0
        or metadata.maximum_gain_db != 62
        or metadata.initial_gain_db != probe.auto_initial_gain_db
    ):
        raise EvidenceInvalid("transport probe metadata differs from its AUTO request")
    if frame_index == 0 and metadata.bench_gain_indices != (
        metadata.maximum_gain_index,
        metadata.maximum_gain_index,
    ):
        raise EvidenceInvalid(
            "transport probe first frame is not at the maximum-gain endpoint"
        )
    if metadata.sample_format != 1 or metadata.threshold_provenance != (
        _expected_threshold_provenance(quality)
    ):
        raise EvidenceInvalid("transport probe wire/request provenance is invalid")
    for event in metadata.gain_events:
        expected_flags = (int(event.direction) << 4) | int(event.reason)
        if event.flags != expected_flags or event.flags & ~0x3F:
            raise EvidenceInvalid("transport probe event flags are inconsistent")
    if previous_refill_ns is not None and refill_ns < previous_refill_ns:
        raise EvidenceInvalid("transport probe refill completion clock regressed")
    maximum_events = maximum_tandem_events_per_frame(
        mode=TandemMode.AUTO,
        samples_per_channel=probe.frame_samples,
        power_measurement_samples=quality.tandem_power_measurement_samples,
        cooldown_periods=quality.tandem_cooldown_periods,
    )
    if maximum_events > metadata.event_capacity:
        raise EvidenceInvalid("transport probe event capacity proof failed")
    if metadata.event_count > maximum_events:
        raise EvidenceInvalid(
            "transport probe event count exceeds its configured physics bound"
        )
    minimum_event_spacing = quality.tandem_power_measurement_samples * (
        quality.tandem_cooldown_periods + 1
    )
    prior_event_sample = event_timing_state.get("last_event_sample")
    for event in metadata.gain_events:
        if (
            prior_event_sample is not None
            and event.sample_sequence - prior_event_sample < minimum_event_spacing
        ):
            raise EvidenceInvalid(
                "transport probe gain events violate the configured cooldown spacing"
            )
        prior_event_sample = event.sample_sequence
    if prior_event_sample is not None:
        event_timing_state["last_event_sample"] = prior_event_sample
    current_provenance = {
        "features": metadata.features,
        "sample_format": metadata.sample_format,
        "threshold_provenance": metadata.threshold_provenance,
        "gain_index_range": (
            metadata.minimum_gain_index,
            metadata.maximum_gain_index,
        ),
    }
    if not session_provenance:
        session_provenance.update(current_provenance)
    elif current_provenance != session_provenance:
        raise EvidenceInvalid("transport probe metadata provenance changed in session")
    if metadata.tandem_transition_count != 0 or metadata.gain_events:
        raise EvidenceInvalid(
            "transport probe AUTO session contains a gain transition: "
            f"frame={frame_index}, "
            f"transition_count={metadata.tandem_transition_count}, "
            f"visible_events={len(metadata.gain_events)}"
        )
    if metadata.bench_gain_indices != (
        metadata.maximum_gain_index,
        metadata.maximum_gain_index,
    ):
        raise EvidenceInvalid(
            f"transport probe frame {frame_index} is not at the maximum-gain endpoint"
        )


def _stable_suffix(
    frames: Sequence[_DeferredFrame], *, count: int, label: str
) -> dict[str, Any]:
    if len(frames) < count:
        raise EvidenceInvalid(f"transport probe {label} lacks {count} stable frames")
    suffix = frames[-count:]
    metadata = [frame.metadata for frame in suffix]
    if any(item is None for item in metadata):
        raise EvidenceInvalid(f"transport probe {label} lacks tandem metadata")
    typed = [item for item in metadata if item is not None]
    transition_counts = {item.tandem_transition_count for item in typed}
    endpoints = {item.bench_gain_indices for item in typed}
    if any(item.gain_events for item in typed):
        raise EvidenceInvalid(f"transport probe {label} contains a gain event")
    if any(
        item.bench_gain_indices != (item.maximum_gain_index, item.maximum_gain_index)
        for item in typed
    ):
        raise EvidenceInvalid(
            f"transport probe {label} is not at the maximum-gain endpoint"
        )
    if len(transition_counts) != 1 or len(endpoints) != 1:
        raise EvidenceInvalid(f"transport probe {label} endpoint is not stable")
    return {
        "frame_indices": [int(frame.record["frame_index"]) for frame in suffix],
        "transition_count": typed[-1].tandem_transition_count,
        "bench_gain_indices": list(typed[-1].bench_gain_indices),
        "event_count": 0,
    }


def _schedule_batched_command(
    radio: TransientRadioTransport,
    worker: _ProbeBatchCaptureWorker,
    probe: TransientTransportProbeOptions,
    *,
    post_open_baseline_raw: int,
    check_deadline: Callable[[], None],
    clock_ns: Callable[[], int],
    sleep: Callable[[float], None],
    sample_rate_hz: int,
) -> tuple[StimulusCommand, dict[str, Any]]:
    """Issue the weak write at a predeclared B8 target during batch drain."""

    target_delta = probe.target_sample_offset
    if not 0 < target_delta < (1 << 31):
        raise EvidenceInvalid("transport probe command target is ambiguous in low32")
    target_raw = (post_open_baseline_raw + target_delta) % (1 << 32)
    last_below_raw: int | None = None
    poll_read_count = 0
    poll_observations: list[dict[str, Any]] = []
    total_requested_sleep_samples = 0
    for _ in range(_PROBE_TARGET_MAX_POLL_READS):
        check_deadline()
        worker.require_first_refill_in_flight()
        current = _strict_low32_counter(radio.read_rx_sample_counter_low32())
        poll_read_count += 1
        advance = (current - post_open_baseline_raw) % (1 << 32)
        if advance >= 1 << 31:
            raise EvidenceInvalid(
                "transport probe command target polling crossed an ambiguous wrap"
            )
        remaining = target_delta - advance
        if remaining > 0:
            last_below_raw = current
            if remaining > _PROBE_TARGET_COARSE_GUARD_SAMPLES:
                phase = "coarse_sleep"
                sleep_samples = remaining - _PROBE_TARGET_COARSE_GUARD_SAMPLES
            elif remaining > 2 * _PROBE_TARGET_FINE_SLEEP_SAMPLES:
                phase = "fine_sleep"
                sleep_samples = _PROBE_TARGET_FINE_SLEEP_SAMPLES
            else:
                phase = "tail_poll"
                sleep_samples = 0
            poll_observations.append(
                {
                    "raw": current,
                    "advance_samples": advance,
                    "remaining_samples": remaining,
                    "phase": phase,
                    "requested_sleep_samples": sleep_samples,
                }
            )
            if sleep_samples:
                total_requested_sleep_samples += sleep_samples
                sleep(sleep_samples / sample_rate_hz)
                check_deadline()
            continue
        target_overshoot = advance - target_delta
        if target_overshoot > probe.max_command_sample_uncertainty:
            raise EvidenceInvalid(
                "transport probe command target overshoot "
                f"{target_overshoot} exceeds {probe.max_command_sample_uncertainty} "
                "samples"
            )
        raw_a = current
        poll_observations.append(
            {
                "raw": current,
                "advance_samples": advance,
                "remaining_samples": 0,
                "phase": "target_reached",
                "requested_sleep_samples": 0,
            }
        )
        break
    else:
        raise EvidenceInvalid(
            "transport probe command target exceeded its 64-read polling budget"
        )
    if last_below_raw is None:
        raise EvidenceInvalid("transport probe command target lacks a last-below read")
    worker.require_first_refill_in_flight()
    command = timestamp_stimulus_command(
        "weak_control_reassertion",
        probe.weak_stimulus_tx_gain_db,
        apply=radio.set_tx2_gain,
        clock_ns=clock_ns,
        max_host_jitter_ns=probe.max_host_jitter_ns,
        readback_tolerance_db=probe.readback_tolerance_db,
    )

    raw_initial = _strict_low32_counter(radio.read_rx_sample_counter_low32())
    raw_b: int | None = None
    raw_c: int | None = None
    post_write_read_count = 1
    for _ in range(8):
        current = _strict_low32_counter(radio.read_rx_sample_counter_low32())
        post_write_read_count += 1
        if raw_b is None:
            if current != raw_initial:
                raw_b = current
        elif current != raw_b:
            raw_c = current
            break
    else:
        raise EvidenceInvalid(
            "transport probe command did not observe causal B and C counter advances"
        )
    assert raw_b is not None
    assert raw_c is not None
    initial_delta = (raw_initial - raw_a) % (1 << 32)
    b_delta = (raw_b - raw_initial) % (1 << 32)
    c_delta = (raw_c - raw_b) % (1 << 32)
    if initial_delta >= 1 << 31 or not all(
        0 < value < 1 << 31 for value in (b_delta, c_delta)
    ):
        raise EvidenceInvalid(
            "transport probe command A-to-B-to-C bracket is ambiguous"
        )
    causal_uncertainty = initial_delta + b_delta + c_delta
    if not 0 < causal_uncertainty <= probe.max_command_sample_uncertainty:
        raise EvidenceInvalid(
            "transport probe command causal uncertainty "
            f"{causal_uncertainty} exceeds {probe.max_command_sample_uncertainty} "
            "samples"
        )
    return command, {
        "register_address": "0x800000b8",
        "counter_width_bits": 32,
        "counter_source": "coherent FPGA RX sample counter low word",
        "post_open_baseline_raw": post_open_baseline_raw,
        "target_offset_frames": probe.command_target_frames,
        "target_offset_samples": target_delta,
        "target_raw": target_raw,
        "last_below_raw": last_below_raw,
        "raw_a_prewrite": raw_a,
        "raw_post_write_initial": raw_initial,
        "raw_b_first_advance": raw_b,
        "raw_c_causal_advance": raw_c,
        "target_poll_read_count": poll_read_count,
        "target_poll_policy": (
            "counter-adaptive coarse guard, 4096-sample fine sleeps, bounded tail polls"
        ),
        "target_coarse_guard_samples": _PROBE_TARGET_COARSE_GUARD_SAMPLES,
        "target_fine_sleep_samples": _PROBE_TARGET_FINE_SLEEP_SAMPLES,
        "target_max_poll_reads": _PROBE_TARGET_MAX_POLL_READS,
        "target_poll_observations": poll_observations,
        "target_total_requested_sleep_samples": total_requested_sleep_samples,
        "post_write_read_count": post_write_read_count,
        "target_overshoot_samples": target_overshoot,
        "causal_uncertainty_samples": causal_uncertainty,
        "worker_in_flight_at_command": True,
    }


def _validate_batch_host_chronology(
    *,
    initial_host_after_ns: int,
    command_host_before_ns: int,
    command_host_after_ns: int,
    initiating_refill_completion_ns: int,
) -> None:
    """Bind the command to the initiating refill in one monotonic clock domain."""

    values = {
        "initial host completion": initial_host_after_ns,
        "command host start": command_host_before_ns,
        "command host completion": command_host_after_ns,
        "initiating refill completion": initiating_refill_completion_ns,
    }
    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise EvidenceInvalid(
                f"transport probe {name} is not a nonnegative monotonic timestamp"
            )
    if initial_host_after_ns > command_host_before_ns:
        raise EvidenceInvalid(
            "transport probe same-level command predates initial conditioning"
        )
    if command_host_after_ns > initiating_refill_completion_ns:
        raise EvidenceInvalid(
            "transport probe same-level command did not complete while the "
            "initiating metadata batch refill was in flight"
        )


def _bind_batch_counter_schedule(
    frames: Sequence[_DeferredFrame],
    command: StimulusCommand,
    raw: Mapping[str, Any],
    probe: TransientTransportProbeOptions,
) -> tuple[StimulusCommand, dict[str, Any]]:
    """Extend the low32 schedule only after the exact batch is available."""

    if len(frames) != probe.batch_frames:
        raise EvidenceInvalid("transport probe cannot bind an incomplete batch")
    first_start = int(frames[0].record["first_sample_sequence"])
    last_end = int(frames[-1].record["sample_end_exclusive"])
    raw_s0 = _strict_low32_counter(raw.get("post_open_baseline_raw"))
    s0 = _extend_low32_near(raw_s0, reference=first_start)
    target = s0 + probe.target_sample_offset
    if not s0 < target:
        raise EvidenceInvalid("transport probe post-open target does not follow S0")
    if not first_start <= target < last_end:
        raise EvidenceInvalid("transport probe predeclared target is outside the batch")

    raw_p = _strict_low32_counter(raw.get("last_below_raw"))
    raw_a = _strict_low32_counter(raw.get("raw_a_prewrite"))
    raw_initial = _strict_low32_counter(raw.get("raw_post_write_initial"))
    raw_b = _strict_low32_counter(raw.get("raw_b_first_advance"))
    raw_c = _strict_low32_counter(raw.get("raw_c_causal_advance"))
    p_delta = (raw_p - raw_s0) % (1 << 32)
    a_delta = (raw_a - raw_s0) % (1 << 32)
    initial_delta = (raw_initial - raw_a) % (1 << 32)
    b_delta = (raw_b - raw_initial) % (1 << 32)
    c_delta = (raw_c - raw_b) % (1 << 32)
    if any(value >= 1 << 31 for value in (p_delta, a_delta, initial_delta)) or any(
        not 0 < value < 1 << 31 for value in (b_delta, c_delta)
    ):
        raise EvidenceInvalid("transport probe batch counter extension is ambiguous")
    extended_p = s0 + p_delta
    extended_a = s0 + a_delta
    extended_initial = extended_a + initial_delta
    extended_b = extended_initial + b_delta
    extended_c = extended_b + c_delta
    target_error = extended_a - target
    causal_uncertainty = extended_c - extended_a
    if not extended_p < target <= extended_a:
        raise EvidenceInvalid("transport probe last-below/target/A ordering is invalid")
    if not 0 < extended_a - extended_p < 1 << 31:
        raise EvidenceInvalid("transport probe last-below to A advance is ambiguous")
    if not 0 <= target_error <= probe.max_command_sample_uncertainty:
        raise EvidenceInvalid("transport probe posthoc target error exceeds policy")
    if not 0 < causal_uncertainty <= probe.max_command_sample_uncertainty:
        raise EvidenceInvalid("transport probe posthoc A-to-C bracket exceeds policy")
    if (
        raw.get("target_raw") != target % (1 << 32)
        or raw.get("target_offset_frames") != probe.command_target_frames
        or raw.get("target_offset_samples") != probe.target_sample_offset
        or raw.get("target_overshoot_samples") != target_error
        or raw.get("causal_uncertainty_samples") != causal_uncertainty
        or raw.get("worker_in_flight_at_command") is not True
    ):
        raise EvidenceInvalid("transport probe raw and extended schedule disagree")
    bracketed = StimulusCommand(
        command_id=command.command_id,
        requested_level_db=command.requested_level_db,
        applied_level_db=command.applied_level_db,
        host_before_ns=command.host_before_ns,
        host_after_ns=command.host_after_ns,
        sample_sequence_before=extended_a,
        sample_sequence_after=extended_c,
    )
    return bracketed, {
        **dict(raw),
        "first_batch_sample": first_start,
        "last_batch_sample_exclusive": last_end,
        "post_open_baseline_sample": s0,
        "target_sample": target,
        "last_below_sample": extended_p,
        "a_prewrite_sample": extended_a,
        "post_write_initial_sample": extended_initial,
        "b_first_advance_sample": extended_b,
        "c_causal_advance_sample": extended_c,
        "command_interval": "[A,C)",
    }


def _probe_command_partition(
    frames: Sequence[_DeferredFrame],
    command: StimulusCommand,
    *,
    required_fully_pre_frames: int,
    required_fully_post_frames: int,
) -> dict[str, Any]:
    lower = command.sample_sequence_before
    upper = command.sample_sequence_after
    if lower is None or upper is None:
        raise EvidenceInvalid("transport probe command lacks a hardware bracket")
    contexts: list[str] = []
    for frame in frames:
        start = int(frame.record["first_sample_sequence"])
        end = int(frame.record["sample_end_exclusive"])
        if end <= lower:
            context = "fully_pre_command"
        elif start < upper and end > lower:
            context = "command_bracket"
        else:
            context = "fully_post_command"
        frame.record["probe_phase"] = context
        contexts.append(context)
    order = {
        "fully_pre_command": 0,
        "command_bracket": 1,
        "fully_post_command": 2,
    }
    if contexts != sorted(contexts, key=order.__getitem__):
        raise EvidenceInvalid("transport probe command frames are not sample ordered")
    fully_pre = contexts.count("fully_pre_command")
    fully_post = contexts.count("fully_post_command")
    if fully_pre < required_fully_pre_frames:
        raise EvidenceInvalid(
            f"transport probe retained {fully_pre} fully pre-command frames; "
            f"requires {required_fully_pre_frames}"
        )
    if fully_post < required_fully_post_frames:
        raise EvidenceInvalid(
            f"transport probe retained {fully_post} fully post-command frames; "
            f"requires {required_fully_post_frames}"
        )
    return {
        "frame_indices": [int(frame.record["frame_index"]) for frame in frames],
        "phase_by_frame": contexts,
        "fully_pre_command_frames": fully_pre,
        "required_fully_pre_command_frames": required_fully_pre_frames,
        "command_bracket_frames": contexts.count("command_bracket"),
        "fully_post_command_frames": fully_post,
        "required_fully_post_command_frames": required_fully_post_frames,
    }


def _command_record(
    command: StimulusCommand,
    *,
    effective_attenuation_db: float,
    counter_bracket: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        **command.as_dict(),
        "effective_attenuation_db": effective_attenuation_db,
        "timing_role": "same_level_write_bracketed_by_coherent_fpga_counter",
        "sample_timing_basis": "hardware_sample_counter",
        "sample_anchor_policy": (
            "post-open S0 plus a frozen 40-frame target; command interval is the "
            "coherent causal counter bracket [A,C) while the first batch refill runs"
        ),
        "sample_counter_bracket": dict(counter_bracket),
    }


def _initial_command_record(
    command: StimulusCommand, *, effective_attenuation_db: float
) -> dict[str, Any]:
    return {
        **command.as_dict(),
        "effective_attenuation_db": effective_attenuation_db,
        "timing_role": "pre_session_weak_conditioning_write",
        "sample_timing_basis": None,
        "sample_anchor_policy": (
            "unbounded in hardware sample time; the write predates the AUTO session"
        ),
    }


def _materialize_frames(frames: Sequence[_DeferredFrame]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for frame in frames:
        record = frame.record
        record["sha256"] = hashlib.sha256(frame.raw).hexdigest()
        if frame.metadata is None:
            raise EvidenceInvalid("transport probe frame lacks tandem metadata")
        record["metadata"] = _full_metadata_dict(frame.metadata)
        records.append(record)
    return records


def _analyze_quality_tail(
    frame: _DeferredFrame,
    *,
    quality: TandemQualityOptions,
    probe: TransientTransportProbeOptions,
) -> dict[str, Any]:
    byte_count = probe.anchor_samples * 8
    byte_offset = len(frame.raw) - byte_count
    tail = frame.raw[byte_offset:]
    frame_end = int(frame.record["sample_end_exclusive"])
    first_sample = frame_end - probe.anchor_samples
    analysis = dict(
        analyze_immediate_dual_rx(
            tail,
            first_sample_sequence=first_sample,
            sample_rate_hz=quality.sample_rate_hz,
            expected_tone_hz=quality.tone_hz,
            window_samples=probe.window_samples,
            min_tone_snr_db=quality.thresholds.min_tone_snr_db,
            max_clipping_fraction=quality.thresholds.max_clipping_fraction,
            max_phase_std_deg=quality.thresholds.max_phase_std_deg,
        )
    )
    for raw_window in analysis.get("windows", []):
        window = dict(raw_window)
        tone_snr = [float(value) for value in window.get("tone_snr_db", [])]
        tone_levels = [float(value) for value in window.get("tone_dbfs", [])]
        clipping = [float(value) for value in window.get("clipping_fraction", [])]
        if not (len(tone_snr) == len(tone_levels) == len(clipping) == 2):
            raise EvidenceInvalid(
                "transport probe weak-signal tail lacks dual-RX quality evidence"
            )
        reasons: list[str] = []
        for channel in (0, 1):
            if tone_snr[channel] < quality.thresholds.min_tone_snr_db:
                reasons.append(f"rx{channel}_tone_snr_low")
            if tone_levels[channel] < quality.thresholds.min_tone_dbfs:
                reasons.append(f"rx{channel}_tone_too_weak")
            if tone_levels[channel] > quality.thresholds.max_tone_dbfs:
                reasons.append(f"rx{channel}_tone_too_strong")
            if clipping[channel] > quality.thresholds.max_clipping_fraction:
                reasons.append(f"rx{channel}_clipping")
        if (
            float(window.get("within_window_phase_std_deg", math.inf))
            > quality.thresholds.max_phase_std_deg
        ):
            reasons.append("within_window_phase_unstable")
        window["quality_reasons"] = reasons
        window["quality_valid"] = not reasons
        raw_window.clear()
        raw_window.update(window)
    analysis["quality_valid"] = all(
        bool(window.get("quality_valid")) for window in analysis.get("windows", [])
    )
    if analysis.get("quality_valid") is not True:
        reasons = [
            reason
            for window in analysis.get("windows", [])
            for reason in window.get("quality_reasons", [])
        ]
        raise EvidenceInvalid(
            f"transport probe weak-signal tail failed RF quality gates: {reasons!r}"
        )
    return {
        "frame_index": int(frame.record["frame_index"]),
        "sample_sequence_before": first_sample,
        "sample_sequence_after": frame_end,
        "sample_offset_in_frame": probe.frame_samples - probe.anchor_samples,
        "sample_count": probe.anchor_samples,
        "byte_offset_in_iq_payload": byte_offset,
        "byte_count": byte_count,
        "source_frame_sha256": hashlib.sha256(frame.raw).hexdigest(),
        "tail_sha256": hashlib.sha256(tail).hexdigest(),
        "analysis": analysis,
    }


def _materialize_weak_signal_quality(
    frames: Sequence[_DeferredFrame],
    *,
    quality: TandemQualityOptions,
    probe: TransientTransportProbeOptions,
) -> dict[str, Any]:
    if len(frames) != probe.retained_frames:
        raise EvidenceInvalid(
            "transport probe cannot analyze an incomplete frame ledger"
        )
    conditioning = _analyze_quality_tail(
        frames[probe.fully_pre_command_frames - 1], quality=quality, probe=probe
    )
    final = [
        _analyze_quality_tail(frame, quality=quality, probe=probe)
        for frame in frames[-probe.stable_frames :]
    ]
    return {
        "timing_scope": "post-buffer analysis of returned weak-IQ tails",
        "quality_required": True,
        "conditioning_anchor": conditioning,
        "final_stable_suffix": final,
    }


def _bind_anchor_artifact(
    report: dict[str, Any],
    frames: Sequence[_DeferredFrame],
    probe: TransientTransportProbeOptions,
) -> None:
    if len(frames) < probe.fully_pre_command_frames:
        return
    frame = frames[probe.fully_pre_command_frames - 1]
    byte_count = probe.anchor_samples * 8
    byte_offset = len(frame.raw) - byte_count
    tail = frame.raw[byte_offset:]
    anchor = report.get("conditioning_anchor_candidate")
    if not isinstance(anchor, dict):
        return
    anchor.update(
        {
            "sample_offset_in_frame": probe.frame_samples - probe.anchor_samples,
            "sample_count": probe.anchor_samples,
            "byte_offset_in_iq_payload": byte_offset,
            "byte_count": byte_count,
            "source_frame_sha256": hashlib.sha256(frame.raw).hexdigest(),
            "tail_sha256": hashlib.sha256(tail).hexdigest(),
        }
    )


def _report_memory_policy(probe: TransientTransportProbeOptions) -> dict[str, Any]:
    iq_bytes_per_frame = probe.frame_samples * 8
    ledger_bytes_per_frame = 2 * _PROBE_SIZE_T_BYTES
    core_bytes_per_frame = (
        iq_bytes_per_frame + _PROBE_METADATA_CAPACITY_BYTES + ledger_bytes_per_frame
    )
    return {
        "core_cache": {
            "batch_frames": probe.batch_frames,
            "iq_bytes_per_frame": iq_bytes_per_frame,
            "metadata_capacity_bytes_per_frame": _PROBE_METADATA_CAPACITY_BYTES,
            "size_t_bytes": _PROBE_SIZE_T_BYTES,
            "size_ledger_bytes_per_frame": ledger_bytes_per_frame,
            "bytes_per_frame": core_bytes_per_frame,
            "configured_batch_cache_bytes": probe.core_batch_cache_bytes,
            "formula": (
                "batch_frames * (samples_per_channel * 8 + "
                "metadata_capacity + 2 * sizeof(size_t))"
            ),
            "cap_bytes": probe.maximum_core_batch_bytes,
            "within_cap": probe.core_batch_cache_bytes
            <= probe.maximum_core_batch_bytes,
            "allocation_lifetime": (
                "full configured cache remains allocated through final cached replay"
            ),
        },
        "python_raw": {
            "retained_frame_count": probe.retained_frames,
            "queue_capacity_frames": _PROBE_QUEUE_FRAMES,
            "producer_held_frame_bound": 1,
            "maximum_unique_raw_frames": probe.maximum_python_raw_frames,
            "bytes_per_frame": iq_bytes_per_frame,
            "maximum_bytes": probe.maximum_python_raw_bytes,
            "cap_bytes": probe.maximum_retained_raw_bytes,
            "within_cap": probe.maximum_python_raw_bytes
            <= probe.maximum_retained_raw_bytes,
            "ownership_proof": (
                "retained, queue, and producer partitions own disjoint frames from "
                "the frozen one-batch budget"
            ),
        },
        "ordinary_core_buffer": {
            "bytes": iq_bytes_per_frame,
            "scope": "libiio destination buffer outside the retained batch cache",
        },
        "python_read_temporary": {
            "bytes": iq_bytes_per_frame,
            "scope": "transient Buffer.read() bytearray while bytes are materialized",
        },
        "metadata_reservations": {
            "ctypes_refill_scratch_bytes": _PROBE_METADATA_CAPACITY_BYTES,
            "returned_metadata_bytes_bound": _PROBE_METADATA_CAPACITY_BYTES,
            "parsed_evidence_bytes_bound": (
                probe.batch_frames * _PROBE_METADATA_CAPACITY_BYTES
            ),
            "parsed_evidence_policy": (
                "reserve one full metadata-capacity budget per retained frame"
            ),
        },
        "device_kernel_dma": {
            "kernel_buffers": probe.kernel_buffers,
            "bytes_per_buffer": iq_bytes_per_frame,
            "reserved_bytes": probe.kernel_buffers * iq_bytes_per_frame,
        },
        "aggregate": {
            "conservative_capture_upper_bound_bytes": probe.aggregate_resident_bytes,
            "cap_bytes": probe.maximum_aggregate_bytes,
            "within_cap": probe.aggregate_resident_bytes
            <= probe.maximum_aggregate_bytes,
            "formula": (
                "retained C cache + ordinary C buffer + Python raw + transient "
                "read bytearray + metadata scratch/result/parsed reservations + K8 DMA"
            ),
            "scope": (
                "capture-path byte reservoirs; Python allocator and report-object "
                "overhead are covered by conservative metadata reservations"
            ),
        },
    }


def _qualification_scope() -> str:
    return (
        "weak-only tandem AUTO metadata transport continuity and same-level "
        "control/data contention; no commanded loudness step or intentionally "
        "induced gain transient"
    )


def _evidence_policy(probe: TransientTransportProbeOptions) -> dict[str, Any]:
    return {
        "provider_gaps": "forbidden",
        "hidden_transitions": "forbidden",
        "first_provider_buffer_sequence": 0,
        "first_frame_unrepresented_transitions": 0,
        "auto_initial_gain_db": probe.auto_initial_gain_db,
        "auto_initial_gain_policy": (
            "start at the maximum-gain clamp so the weak-only session has no "
            "expected startup increase; any observed startup transition remains fatal"
        ),
        "all_returned_frame_gain_state": (
            "transition_count=0, event_count=0, and paired maximum_gain_index "
            "for every retained frame"
        ),
        "metadata_batch_frames": probe.batch_frames,
        "metadata_batch_policy": (
            "one full C batch is initiated by the acquisition thread; all returned "
            "frames are cached replays from that batch"
        ),
        "command_target": (
            "post-open coherent S0 + 40 * 65536 samples while first refill is in flight"
        ),
        "maximum_target_overshoot_samples": probe.max_command_sample_uncertainty,
        "maximum_a_to_c_uncertainty_samples": probe.max_command_sample_uncertainty,
        "target_poll_pacing": {
            "coarse_guard_samples": _PROBE_TARGET_COARSE_GUARD_SAMPLES,
            "fine_sleep_samples": _PROBE_TARGET_FINE_SLEEP_SAMPLES,
            "maximum_poll_reads": _PROBE_TARGET_MAX_POLL_READS,
            "policy": (
                "sleep to the guard band, pace within it, then use bounded tail reads"
            ),
        },
        "required_fully_pre_command_frames": probe.fully_pre_command_frames,
        "required_fully_post_command_frames": probe.fully_post_command_frames,
        "final_stable_frames": probe.stable_frames,
        "batch_failure_policy": (
            "partial batch failures free the cache, poison, and core-cancel before "
            "return; future refill is EBADF and explicit cleanup cancel is idempotent"
        ),
        "release_claim": "never eligible",
    }


def _safety_policy(
    quality: TandemQualityOptions, probe: TransientTransportProbeOptions
) -> dict[str, Any]:
    return {
        "physical_attenuation_db": quality.physical_attenuation_db,
        "authorized_tx2_gain_ceiling_db": probe.weak_stimulus_tx_gain_db,
        "minimum_effective_attenuation_db": (
            quality.physical_attenuation_db - probe.weak_stimulus_tx_gain_db
        ),
        "required_effective_attenuation_db": 30.0,
        "strong_tx_write_permitted": False,
        "tx1_policy": "muted below -80 dB throughout",
    }


def _capacity_policy(
    quality: TandemQualityOptions, probe: TransientTransportProbeOptions
) -> dict[str, Any]:
    maximum_events = maximum_tandem_events_per_frame(
        mode=TandemMode.AUTO,
        samples_per_channel=probe.frame_samples,
        power_measurement_samples=quality.tandem_power_measurement_samples,
        cooldown_periods=quality.tandem_cooldown_periods,
    )
    nominal_observations = (
        probe.frame_samples // quality.tandem_power_measurement_samples
    )
    # Provider metadata samples four gain observations per returned frame,
    # independent of the controller's detector-window configuration.
    provider_observation_interval = probe.frame_samples // 4
    nominal_stored_observations = probe.frame_samples // provider_observation_interval
    overlap_safe_observations = nominal_stored_observations + 1
    return {
        "maximum_gain_events_per_frame": maximum_events,
        "event_capacity": 64,
        "event_capacity_safe": maximum_events <= 64,
        "controller_measurement_periods_per_frame": nominal_observations,
        "provider_observation_interval_samples": provider_observation_interval,
        "nominal_stored_observations_per_frame": nominal_stored_observations,
        "overlap_safe_stored_observations_per_frame": overlap_safe_observations,
        "nominal_k8_initial_sampler_demand": (
            nominal_stored_observations * (probe.kernel_buffers + 1)
        ),
        "overlap_safe_k8_initial_sampler_demand": (
            overlap_safe_observations * (probe.kernel_buffers + 1)
        ),
        "observation_ring_capacity": 1_024,
        "observation_capacity_safe": (
            overlap_safe_observations * (probe.kernel_buffers + 1) <= 1_024
        ),
    }


_FIFO_NORMALIZATION_POLICY = (
    "while fully muted, an ABI-2 HOLD MetadataBuffer open/close may normalize only "
    "a stale FIFO on an otherwise safe unowned IDLE controller; construction "
    "synchronously acquires and clears the session, no refill or TX write occurs"
)
_TANDEM_STATUS_FIELDS = {
    "state",
    "fault_flags",
    "overflow_count",
    "fifo_level",
    "ownership_epoch",
    "transition_count",
    "rx1_gain_index",
    "rx2_gain_index",
}


def _safe_unowned_idle_status(
    status: Mapping[str, Any], *, require_empty_fifo: bool, label: str
) -> dict[str, int]:
    if set(status) != _TANDEM_STATUS_FIELDS:
        raise EvidenceInvalid(f"transport probe {label} status fields are incomplete")
    normalized: dict[str, int] = {}
    for name, value in status.items():
        if type(value) is not int:
            raise EvidenceInvalid(
                f"transport probe {label} {name} is not an exact integer"
            )
        normalized[name] = value
    required = {
        "state": int(TandemState.IDLE),
        "fault_flags": 0,
        "overflow_count": 0,
        "ownership_epoch": 0,
    }
    for name, expected in required.items():
        if normalized.get(name) != expected:
            raise EvidenceInvalid(
                f"transport probe {label} {name} is {normalized.get(name)!r}, "
                f"expected {expected}"
            )
    fifo_level = normalized.get("fifo_level")
    if fifo_level is None or not 0 <= fifo_level <= 64:
        raise EvidenceInvalid(f"transport probe {label} FIFO level is invalid")
    if require_empty_fifo and fifo_level != 0:
        raise EvidenceInvalid(
            f"transport probe {label} FIFO remains nonempty at {fifo_level}"
        )
    return normalized


def _safe_completed_weak_session_status(
    status: Mapping[str, Any], *, label: str, require_zero_transitions: bool = True
) -> dict[str, int]:
    """Require complete post-close ownership and optional success invariants."""

    normalized = _safe_unowned_idle_status(
        status, require_empty_fifo=True, label=label
    )
    if require_zero_transitions and normalized["transition_count"] != 0:
        raise EvidenceInvalid(
            f"transport probe {label} transition count is "
            f"{normalized['transition_count']}, expected 0"
        )
    rx1 = normalized["rx1_gain_index"]
    rx2 = normalized["rx2_gain_index"]
    if rx1 != rx2 or not 0 <= rx1 <= 0x7F:
        raise EvidenceInvalid(
            f"transport probe {label} endpoint is not a paired 7-bit gain index"
        )
    return normalized


def _safe_owned_hold_status(status: Mapping[str, Any], *, label: str) -> dict[str, int]:
    if set(status) != _TANDEM_STATUS_FIELDS:
        raise EvidenceInvalid(f"transport probe {label} status fields are incomplete")
    normalized: dict[str, int] = {}
    for name, value in status.items():
        if type(value) is not int:
            raise EvidenceInvalid(
                f"transport probe {label} {name} is not an exact integer"
            )
        normalized[name] = value
    if (
        normalized["state"] != int(TandemState.ARMED_HOLD)
        or normalized["ownership_epoch"] <= 0
        or normalized["fault_flags"] != 0
        or normalized["overflow_count"] != 0
        or normalized["fifo_level"] != 0
        or normalized["transition_count"] != 0
        or normalized["rx1_gain_index"] != normalized["rx2_gain_index"]
    ):
        raise EvidenceInvalid(f"transport probe {label} is not a safe owned HOLD")
    return normalized


def _manual_gain_state(
    radio: TransientRadioTransport,
    quality: TandemQualityOptions,
    *,
    label: str,
) -> dict[str, Any]:
    state = _rx_state(radio, expected_mode="manual")
    gains = [float(value) for value in state["gains_db"]]
    if any(abs(value - quality.manual_gain_db) > 0.1 for value in gains):
        raise EvidenceInvalid(
            f"transport probe {label} RX gains differ from configured manual gain"
        )
    return state


def _hold_normalization_request(
    quality: TandemQualityOptions, probe: TransientTransportProbeOptions
) -> bytes:
    return build_tandem_request(
        mode=TandemMode.HOLD,
        initial_gain_db=int(quality.manual_gain_db),
        power_measurement_samples=quality.tandem_power_measurement_samples,
        low_power_dwell_periods=quality.tandem_low_power_dwell_periods,
        cooldown_periods=quality.tandem_cooldown_periods,
        low_power_threshold=quality.tandem_low_power_threshold,
        large_lmt_overload_threshold=quality.tandem_large_lmt_overload_threshold,
        large_adc_overload_threshold=quality.tandem_large_adc_overload_threshold,
        small_adc_overload_threshold=quality.tandem_small_adc_overload_threshold,
        samples_per_channel=probe.frame_samples,
    )


def _normalize_stale_fifo(
    radio: TransientRadioTransport,
    quality: TandemQualityOptions,
    probe: TransientTransportProbeOptions,
    evidence: dict[str, Any],
    *,
    mute_evidence: Mapping[str, Any] | None,
    check_deadline: Callable[[], None],
) -> dict[str, int]:
    """Clear only a stale FIFO, under mute, through one bounded HOLD session."""

    _validate_verified_mute_evidence(
        mute_evidence, label="pre-normalization mute evidence"
    )
    rx_before = _manual_gain_state(radio, quality, label="pre-normalization")
    before = _safe_unowned_idle_status(
        radio.tandem_status(),
        require_empty_fifo=False,
        label="pre-normalization status",
    )
    fifo_level = before["fifo_level"]
    evidence.update(
        {
            "policy": _FIFO_NORMALIZATION_POLICY,
            "mute_evidence_before": dict(mute_evidence or {}),
            "rx_state_before": rx_before,
            "status_before": before,
            "stale_fifo_events": fifo_level,
        }
    )
    if fifo_level == 0:
        after = _safe_unowned_idle_status(
            radio.tandem_status(),
            require_empty_fifo=True,
            label="no-op normalization status",
        )
        if after != before:
            raise EvidenceInvalid(
                "transport probe no-op FIFO normalization status changed"
            )
        rx_after = _manual_gain_state(radio, quality, label="post-no-op normalization")
        if rx_after != rx_before:
            raise EvidenceInvalid(
                "transport probe no-op FIFO normalization changed RX state"
            )
        evidence.update(
            {
                "action": "not_required",
                "hold_session": None,
                "status_after": after,
                "rx_state_after": rx_after,
            }
        )
        return after

    request = _hold_normalization_request(quality, probe)
    hold_session = {
        "mode": "hold",
        "kernel_buffers": 1,
        "samples_per_channel": probe.frame_samples,
        "refill_count": 0,
        "metadata_request": _request_evidence(request),
        "metadata_abi": None,
        "opened": False,
        "closed": False,
        "status_while_open": None,
        "tx_policy": "fully muted before and throughout normalization",
    }
    evidence.update(
        {
            "action": "muted_hold_session_acquire_clear",
            "hold_session": hold_session,
        }
    )
    check_deadline()
    with radio.buffer(
        "metadata",
        1,
        probe.frame_samples,
        tandem_request=request,
    ) as (_buffer, metadata_abi):
        hold_session["opened"] = True
        hold_session["metadata_abi"] = metadata_abi
        if metadata_abi != 2:
            raise EvidenceInvalid(
                "transport probe FIFO normalization requires metadata ABI 2"
            )
        hold_session["status_while_open"] = _safe_owned_hold_status(
            radio.tandem_status(), label="in-session HOLD status"
        )
    hold_session["closed"] = True
    check_deadline()
    after = _safe_unowned_idle_status(
        radio.tandem_status(),
        require_empty_fifo=True,
        label="post-normalization status",
    )
    active_status = hold_session["status_while_open"]
    assert isinstance(active_status, Mapping)
    for field in ("transition_count", "rx1_gain_index", "rx2_gain_index"):
        if after[field] != active_status[field]:
            raise EvidenceInvalid(
                "transport probe HOLD normalization changed event/gain state on close"
            )
    rx_after = _manual_gain_state(radio, quality, label="post-HOLD normalization")
    if rx_after != rx_before:
        raise EvidenceInvalid("transport probe HOLD normalization did not restore RX")
    evidence["status_after"] = after
    evidence["rx_state_after"] = rx_after
    return after


def _run_probe_body(
    radio: TransientRadioTransport,
    quality: TandemQualityOptions,
    probe: TransientTransportProbeOptions,
    report: dict[str, Any],
    retained: list[_DeferredFrame],
    *,
    check_deadline: Callable[[], None],
    clock_ns: Callable[[], int],
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    metadata_parser: Callable[[bytes], TandemFrameMetadata],
) -> None:
    mute_evidence = radio.mute_all()
    radio.configure_rx("manual", manual_gain_db=quality.manual_gain_db)
    fifo_normalization: dict[str, Any] = {}
    report["stale_fifo_normalization"] = fifo_normalization
    status_before = _normalize_stale_fifo(
        radio,
        quality,
        probe,
        fifo_normalization,
        mute_evidence=mute_evidence,
        check_deadline=check_deadline,
    )
    report["tandem_status_before"] = status_before
    radio.arm_tx2_tone(tone_hz=quality.tone_hz, scale=quality.dds_scale)

    initial = timestamp_stimulus_command(
        "weak_initial",
        probe.weak_stimulus_tx_gain_db,
        apply=radio.set_tx2_gain,
        clock_ns=clock_ns,
        max_host_jitter_ns=probe.max_host_jitter_ns,
        readback_tolerance_db=probe.readback_tolerance_db,
    )
    initial_effective = _check_effective_attenuation(quality, initial)
    report["weak_conditioning_command"] = _initial_command_record(
        initial, effective_attenuation_db=initial_effective
    )

    capture = _capture_adapter(probe)
    request = _probe_auto_request(quality, probe)
    report["metadata_request"] = _request_evidence(request)
    state = _CaptureState()
    metadata_abi: int | None = None
    worker: _ProbeBatchCaptureWorker | None = None
    previous_refill_ns: int | None = None
    session_provenance: dict[str, Any] = {}
    event_timing_state: dict[str, int] = {}
    initial_stability: Mapping[str, Any] | None = None
    final_stability: Mapping[str, Any] | None = None

    session_error: BaseException | None = None
    try:
        with radio.buffer(
            "metadata",
            probe.kernel_buffers,
            probe.frame_samples,
            tandem_request=request,
            batch_frames=probe.batch_frames,
        ) as (buffer, metadata_abi):
            cancel_capture = getattr(buffer, "cancel", None)
            configured_batch_frames = getattr(buffer, "batch_frames", None)
            configured_batch_cache_bytes = getattr(buffer, "batch_cache_bytes", None)
            setup_valid = (
                metadata_abi == 2
                and callable(cancel_capture)
                and type(configured_batch_frames) is int
                and configured_batch_frames == probe.batch_frames
                and type(configured_batch_cache_bytes) is int
                and configured_batch_cache_bytes == probe.core_batch_cache_bytes
            )
            if not setup_valid:
                setup_error = EvidenceInvalid(
                    "transport probe requires metadata ABI 2, batch64 cache "
                    "attestation, and thread-safe cancel"
                )
                mute_error: BaseException | None = None
                try:
                    radio.mute_all()
                except BaseException as error:  # noqa: BLE001
                    mute_error = error
                cancel_error: BaseException | None = None
                if callable(cancel_capture):
                    try:
                        cancel_capture()
                    except BaseException as error:  # noqa: BLE001
                        cancel_error = error
                setup_errors = [
                    error
                    for error in (setup_error, mute_error, cancel_error)
                    if error is not None
                ]
                if len(setup_errors) > 1:
                    raise BaseExceptionGroup(
                        "transport probe setup, pre-close mute, or cancel failed",
                        setup_errors,
                    )
                raise setup_error

            report["acquisition"].update(
                {
                    "metadata_abi": metadata_abi,
                    "configured_batch_frames": configured_batch_frames,
                    "configured_batch_cache_bytes": configured_batch_cache_bytes,
                    "batch_cache_attested": True,
                }
            )
            post_open_baseline_raw = _strict_low32_counter(
                radio.read_rx_sample_counter_low32()
            )
            report["acquisition"]["post_open_baseline_raw"] = (
                post_open_baseline_raw
            )

            def acquire_one() -> _DeferredFrame:
                nonlocal previous_refill_ns
                frame = _capture_frame(
                    radio,
                    buffer,
                    mode=MODE_TANDEM,
                    expected_iio_mode="manual",
                    quality=quality,
                    capture=capture,
                    state=state,
                    metadata_parser=metadata_parser,
                    gap_context="continuous_acquisition_unclassified",
                    expected_tandem_initial_gain_db=probe.auto_initial_gain_db,
                )
                assert frame.metadata is not None
                refill_ns = int(frame.record["refill_monotonic_ns"])
                _validate_probe_metadata(
                    frame.metadata,
                    frame_index=int(frame.record["frame_index"]),
                    quality=quality,
                    probe=probe,
                    session_provenance=session_provenance,
                    event_timing_state=event_timing_state,
                    previous_refill_ns=previous_refill_ns,
                    refill_ns=refill_ns,
                )
                previous_refill_ns = refill_ns
                return frame

            acquisition_error: BaseException | None = None
            try:
                worker = _ProbeBatchCaptureWorker(
                    acquire_one,
                    batch_frames=probe.batch_frames,
                    thread_name=PROBE_THREAD_NAME,
                )
                if worker.queue_capacity_frames != _PROBE_QUEUE_FRAMES:
                    raise EvidenceInvalid(
                        "transport probe worker queue differs from the exact "
                        "Python memory ledger"
                    )
                worker.start()
                report["acquisition"]["worker_started"] = True
                unbound_command, raw_schedule = _schedule_batched_command(
                    radio,
                    worker,
                    probe,
                    post_open_baseline_raw=post_open_baseline_raw,
                    check_deadline=check_deadline,
                    clock_ns=clock_ns,
                    sleep=sleep,
                    sample_rate_hz=quality.sample_rate_hz,
                )
                command_effective = _check_effective_attenuation(
                    quality, unbound_command
                )
                report["acquisition"].update(
                    {
                        "worker_in_flight_at_command": True,
                        "prebind_unbound_command": {
                            **unbound_command.as_dict(),
                            "effective_attenuation_db": command_effective,
                        },
                        "prebind_raw_counter_schedule": dict(raw_schedule),
                    }
                )
                for _ in range(probe.batch_frames):
                    check_deadline()
                    frame = worker.take()
                    retained.append(frame)
                initiating_refill_completion_ns = int(
                    retained[0].record["refill_monotonic_ns"]
                )
                report["acquisition"].update(
                    {
                        "single_core_batch_initiated": True,
                        "initiating_batch_refill_calls": 1,
                        "public_refill_calls": probe.batch_frames,
                        "cached_replay_refill_calls": probe.batch_frames - 1,
                        "batch_cache_fully_replayed": True,
                        "initiating_refill_completion_monotonic_ns": (
                            initiating_refill_completion_ns
                        ),
                    }
                )
                _validate_batch_host_chronology(
                    initial_host_after_ns=initial.host_after_ns,
                    command_host_before_ns=unbound_command.host_before_ns,
                    command_host_after_ns=unbound_command.host_after_ns,
                    initiating_refill_completion_ns=(
                        initiating_refill_completion_ns
                    ),
                )
                command, counter_bracket = _bind_batch_counter_schedule(
                    retained, unbound_command, raw_schedule, probe
                )
                command_partition = _probe_command_partition(
                    retained,
                    command,
                    required_fully_pre_frames=probe.fully_pre_command_frames,
                    required_fully_post_frames=probe.fully_post_command_frames,
                )
                fully_pre = [
                    frame
                    for frame in retained
                    if frame.record.get("probe_phase") == "fully_pre_command"
                ]
                fully_post = [
                    frame
                    for frame in retained
                    if frame.record.get("probe_phase") == "fully_post_command"
                ]
                qualification_prefix = fully_pre[: probe.fully_pre_command_frames]
                initial_stability = _stable_suffix(
                    qualification_prefix,
                    count=probe.stable_frames,
                    label="fully pre-command qualification suffix",
                )
                anchor_frame = qualification_prefix[-1]
                anchor_end = int(anchor_frame.record["sample_end_exclusive"])
                report["conditioning_anchor_candidate"] = {
                    "frame_index": int(anchor_frame.record["frame_index"]),
                    "sample_sequence_before": anchor_end - probe.anchor_samples,
                    "sample_sequence_after": anchor_end,
                    "sample_uncertainty": probe.anchor_samples,
                    "timing_basis": "hardware_sample_counter",
                    "role": "stable_tail_candidate_for_future_transient",
                    "release_latency_evidence": False,
                }
                final_stability = _stable_suffix(
                    fully_post,
                    count=probe.stable_frames,
                    label="fully post-command final suffix",
                )
                report["command_contention"] = {
                    "command": _command_record(
                        command,
                        effective_attenuation_db=command_effective,
                        counter_bracket=counter_bracket,
                    ),
                    "partition": dict(command_partition),
                    "command_timing_qualified": True,
                    "gain_transient_exercised": False,
                }
            except BaseException as error:  # noqa: BLE001
                acquisition_error = error

            # Required ordering on success and every failure: remove RF first,
            # cancel a failed/in-flight batch, then join before close.  A fully
            # replayed successful batch closes normally to exercise RELEASE.
            prejoin_mute_error: BaseException | None = None
            try:
                radio.mute_all()
            except BaseException as error:  # noqa: BLE001
                prejoin_mute_error = error
            worker_in_flight_before_shutdown = bool(
                worker is not None and worker.first_refill_in_flight
            )
            cancel_required = acquisition_error is not None or (
                worker_in_flight_before_shutdown
            )
            if worker is not None:
                worker.request_stop()
            cancel_error: BaseException | None = None
            cancel_called = False
            if cancel_required:
                cancel_called = True
                try:
                    cancel_capture()
                except BaseException as error:  # noqa: BLE001
                    cancel_error = error
            stop_error: BaseException | None = None
            if worker is not None:
                try:
                    worker.stop()
                except BaseException as error:  # noqa: BLE001
                    stop_error = error
                report["acquisition"].update(
                    {
                        "produced_frames": worker.produced_frames,
                        "consumed_frames": worker.consumed_frames,
                        "discarded_tail_frames": worker.discarded_tail_frames,
                    }
                )
            report["acquisition"].update(
                {
                    "worker_in_flight_before_shutdown": (
                        worker_in_flight_before_shutdown
                    ),
                    "cancel_required": cancel_required,
                    "cancel_called": cancel_called,
                    "cancel_succeeded": (
                        cancel_error is None if cancel_called else None
                    ),
                    "shutdown_path": (
                        "cancel_failed_or_in_flight_batch"
                        if cancel_required
                        else "normal_close_after_full_cache_replay"
                    ),
                    "worker_stopped_before_buffer_close": stop_error is None,
                }
            )
            errors = [
                error
                for error in (
                    acquisition_error,
                    prejoin_mute_error,
                    cancel_error,
                    stop_error,
                )
                if error is not None
            ]
            if len(errors) > 1:
                raise BaseExceptionGroup(
                    "transport acquisition, emergency mute, buffer cancel, or "
                    "worker shutdown failed",
                    errors,
                )
            if errors:
                error = errors[0]
                raise error.with_traceback(error.__traceback__)
        report["acquisition"]["buffer_close_completed"] = True
    except BaseException as error:  # noqa: BLE001
        session_error = error

    post_session_errors: list[BaseException] = []
    try:
        radio.mute_all()
    except BaseException as error:  # noqa: BLE001
        post_session_errors.append(error)
    try:
        status_after = _safe_completed_weak_session_status(
            _wait_for_idle(radio, monotonic=monotonic, sleep=sleep),
            label="post-session status",
            require_zero_transitions=session_error is None,
        )
        report["tandem_status_after"] = status_after
    except BaseException as error:  # noqa: BLE001
        post_session_errors.append(error)
    try:
        radio.configure_rx("manual", manual_gain_db=quality.manual_gain_db)
        report["final_rx_state"] = _rx_state(radio, expected_mode="manual")
    except BaseException as error:  # noqa: BLE001
        post_session_errors.append(error)

    report["metadata_abi"] = metadata_abi
    if initial_stability is not None:
        report["initial_stable_suffix"] = dict(initial_stability)
    if final_stability is not None:
        report["final_stable_suffix"] = dict(final_stability)
    all_errors = [
        error for error in ([session_error] + post_session_errors) if error is not None
    ]
    if len(all_errors) > 1:
        raise BaseExceptionGroup(
            "transport probe session or post-session restoration failed", all_errors
        )
    if all_errors:
        error = all_errors[0]
        raise error.with_traceback(error.__traceback__)


def _refill_cadence(
    frames: Sequence[Mapping[str, Any]], sample_rate_hz: int
) -> dict[str, Any]:
    values = [int(frame["refill_monotonic_ns"]) for frame in frames]
    deltas = [current - previous for previous, current in pairwise(values)]
    ordered = sorted(deltas)
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    frame_period_ns = _PROBE_FRAME_SAMPLES * 1_000_000_000 / sample_rate_hz
    return {
        "adjacent_refill_completion_delta_ns": deltas,
        "median_refill_completion_delta_ns": statistics.median(deltas),
        "p95_refill_completion_delta_ns": ordered[p95_index],
        "maximum_refill_completion_delta_ns": max(deltas),
        "nominal_hardware_frame_period_ns": frame_period_ns,
        "timing_scope": "host refill completion cadence; not capture latency",
    }


def _required_mapping(value: Any, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceInvalid(f"transport probe report lacks object {name}")
    return value


def _required_list(value: Any, *, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise EvidenceInvalid(f"transport probe report lacks list {name}")
    return value


def _required_int(value: Any, *, name: str, minimum: int | None = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceInvalid(f"transport probe report {name} is not an integer")
    if minimum is not None and value < minimum:
        raise EvidenceInvalid(
            f"transport probe report {name} must be at least {minimum}"
        )
    return value


def _required_number(value: Any, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceInvalid(f"transport probe report {name} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EvidenceInvalid(f"transport probe report {name} is not finite")
    return result


def _json_domain(value: Any) -> Any:
    return json.loads(json.dumps(value, allow_nan=False))


def _required_sha256(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise EvidenceInvalid(f"transport probe report {name} is not SHA-256")
    return value


def _validate_firmware_runner_provenance(value: Any) -> dict[str, Any]:
    record = _required_mapping(value, name="firmware runner provenance")
    expected_fields = {
        "repository",
        "commit",
        "local_dependencies",
        "manifest_relative_path",
        "manifest_libiio_identity",
    }
    if set(record) != expected_fields:
        raise EvidenceInvalid("transport probe firmware provenance fields changed")

    repository_value = record.get("repository")
    if not isinstance(repository_value, str):
        raise EvidenceInvalid("transport probe firmware repository path is invalid")
    repository = Path(repository_value)
    if not repository.is_absolute() or not repository.is_dir():
        raise EvidenceInvalid("transport probe firmware repository is not absolute")
    repository = repository.resolve()
    if str(repository) != repository_value:
        raise EvidenceInvalid("transport probe firmware repository is not canonical")
    if repository != _firmware_repository():
        raise EvidenceInvalid("transport probe firmware repository path changed")
    commit = record.get("commit")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise EvidenceInvalid("transport probe firmware commit is not exact SHA-1")
    if _git_text(repository, "rev-parse", f"{commit}^{{commit}}") != commit:
        raise EvidenceInvalid("transport probe firmware commit cannot be resolved")
    if _git_text(repository, "rev-parse", "HEAD") != commit:
        raise EvidenceInvalid("transport probe firmware runner HEAD changed")

    dependencies = _required_list(
        record.get("local_dependencies"), name="local runtime dependencies"
    )
    if len(dependencies) != len(_PROBE_LOCAL_RUNTIME_DEPENDENCIES):
        raise EvidenceInvalid("transport probe local dependency inventory changed")
    manifest_blob: bytes | None = None
    for expected_path, dependency_value in zip(
        _PROBE_LOCAL_RUNTIME_DEPENDENCIES, dependencies, strict=True
    ):
        dependency = _required_mapping(
            dependency_value, name=f"runtime dependency {expected_path}"
        )
        if set(dependency) != {
            "relative_path",
            "absolute_path",
            "observed_sha256",
            "commit_blob_sha256",
        }:
            raise EvidenceInvalid(
                f"transport probe runtime dependency {expected_path} fields changed"
            )
        absolute = (repository / expected_path).resolve()
        if (
            dependency.get("relative_path") != expected_path
            or dependency.get("absolute_path") != str(absolute)
        ):
            raise EvidenceInvalid(
                f"transport probe runtime dependency {expected_path} path changed"
            )
        committed = _git_bytes(repository, "show", f"{commit}:{expected_path}")
        expected_sha256 = hashlib.sha256(committed).hexdigest()
        observed_sha256 = _required_sha256(
            dependency.get("observed_sha256"),
            name=f"runtime dependency {expected_path} observed digest",
        )
        commit_blob_sha256 = _required_sha256(
            dependency.get("commit_blob_sha256"),
            name=f"runtime dependency {expected_path} commit digest",
        )
        if observed_sha256 != expected_sha256 or commit_blob_sha256 != expected_sha256:
            raise EvidenceInvalid(
                f"transport probe runtime dependency {expected_path} digest changed"
            )
        try:
            current_sha256 = _sha256_file(absolute)
        except OSError as error:
            raise EvidenceInvalid(
                f"transport probe runtime dependency {expected_path} cannot be "
                f"reread: {error}"
            ) from error
        if current_sha256 != expected_sha256:
            raise EvidenceInvalid(
                f"transport probe runtime dependency {expected_path} no longer "
                "matches the runner commit"
            )
        if expected_path == _PROBE_MANIFEST_PATH:
            manifest_blob = committed

    if record.get("manifest_relative_path") != _PROBE_MANIFEST_PATH:
        raise EvidenceInvalid("transport probe source manifest path changed")
    if manifest_blob is None:
        raise EvidenceInvalid("transport probe source manifest blob is absent")
    manifest_identity = _manifest_source_identity(manifest_blob)
    if record.get("manifest_libiio_identity") != manifest_identity:
        raise EvidenceInvalid("transport probe source manifest identity changed")
    return dict(record)


def _validate_host_libiio_provenance(value: Any) -> dict[str, Any]:
    record = _required_mapping(value, name="host libiio provenance")
    expected_fields = {
        "source_commit",
        "protected_source_tag",
        "protected_source_ref",
        "source_directory",
        "source_head_commit",
        "protected_tag_commit",
        "source_tracked_clean",
        "build_directory",
        "cmake_cache_path",
        "cmake_source_directory",
        "mapped_shared_objects",
        "mapped_shared_object",
        "mapped_shared_object_sha256",
        "pylibiio_path",
        "pylibiio_sha256",
        "pylibiio_commit_blob_sha256",
    }
    if set(record) != expected_fields:
        raise EvidenceInvalid("transport probe host libiio provenance fields changed")
    exact = {
        "source_commit": PROBE_EXACT_LIBIIO_COMMIT,
        "protected_source_tag": PROBE_EXACT_LIBIIO_TAG,
        "protected_source_ref": PROBE_EXACT_LIBIIO_REF,
        "source_head_commit": PROBE_EXACT_LIBIIO_COMMIT,
        "protected_tag_commit": PROBE_EXACT_LIBIIO_COMMIT,
        "source_tracked_clean": True,
    }
    if record.get("source_tracked_clean") is not True or any(
        record.get(field) != expected
        for field, expected in exact.items()
        if field != "source_tracked_clean"
    ):
        raise EvidenceInvalid("transport probe protected libiio identity changed")

    path_fields = (
        "source_directory",
        "build_directory",
        "cmake_cache_path",
        "cmake_source_directory",
        "mapped_shared_object",
        "pylibiio_path",
    )
    paths: dict[str, Path] = {}
    for field in path_fields:
        raw_path = record.get(field)
        if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
            raise EvidenceInvalid(
                f"transport probe host libiio {field} is not an absolute path"
            )
        paths[field] = Path(raw_path).resolve()
        if str(paths[field]) != raw_path:
            raise EvidenceInvalid(
                f"transport probe host libiio {field} is not canonical"
            )
    if (
        paths["cmake_source_directory"] != paths["source_directory"]
        or paths["cmake_cache_path"] != paths["build_directory"] / "CMakeCache.txt"
        or paths["mapped_shared_object"].parent != paths["build_directory"]
        or paths["pylibiio_path"]
        != paths["source_directory"] / "bindings/python/iio.py"
    ):
        raise EvidenceInvalid("transport probe host libiio paths are not cross-bound")
    if _cmake_source_directory(paths["cmake_cache_path"]) != paths[
        "source_directory"
    ]:
        raise EvidenceInvalid("transport probe durable CMake source changed")

    source = paths["source_directory"]
    source_head = _git_text(source, "rev-parse", "HEAD")
    protected_tag_commit = _git_text(
        source, "rev-parse", f"{PROBE_EXACT_LIBIIO_REF}^{{commit}}"
    )
    if (
        source_head != PROBE_EXACT_LIBIIO_COMMIT
        or protected_tag_commit != PROBE_EXACT_LIBIIO_COMMIT
        or source_head != record.get("source_head_commit")
        or protected_tag_commit != record.get("protected_tag_commit")
    ):
        raise EvidenceInvalid("transport probe durable libiio source identity changed")
    if _git_text(source, "status", "--porcelain", "--untracked-files=no"):
        raise EvidenceInvalid("transport probe durable libiio source is not clean")

    mapped = _required_list(
        record.get("mapped_shared_objects"), name="mapped libiio objects"
    )
    if mapped != [str(paths["mapped_shared_object"])]:
        raise EvidenceInvalid("transport probe mapped libiio inventory changed")
    mapped_sha256 = _required_sha256(
        record.get("mapped_shared_object_sha256"), name="mapped libiio digest"
    )
    pylibiio_sha256 = _required_sha256(
        record.get("pylibiio_sha256"), name="pylibiio digest"
    )
    pylibiio_commit_sha256 = _required_sha256(
        record.get("pylibiio_commit_blob_sha256"),
        name="pylibiio commit digest",
    )
    try:
        recomputed_mapped_sha256 = _sha256_file(paths["mapped_shared_object"])
        recomputed_pylibiio_sha256 = _sha256_file(paths["pylibiio_path"])
        protected_pylibiio_sha256 = hashlib.sha256(
            _git_bytes(
                source,
                "show",
                f"{PROBE_EXACT_LIBIIO_COMMIT}:bindings/python/iio.py",
            )
        ).hexdigest()
    except OSError as error:
        raise EvidenceInvalid(
            f"transport probe host provenance file cannot be reread: {error}"
        ) from error
    if mapped_sha256 != recomputed_mapped_sha256:
        raise EvidenceInvalid("transport probe mapped libiio digest changed")
    if not (
        pylibiio_sha256
        == pylibiio_commit_sha256
        == recomputed_pylibiio_sha256
        == protected_pylibiio_sha256
    ):
        raise EvidenceInvalid("transport probe pylibiio digest changed")
    return dict(record)


def _validate_runtime_provenance(value: Any) -> dict[str, Any]:
    record = _required_mapping(value, name="runtime provenance")
    if set(record) != {"host_libiio", "firmware_runner"}:
        raise EvidenceInvalid("transport probe runtime provenance fields changed")
    return {
        "host_libiio": _validate_host_libiio_provenance(
            record.get("host_libiio")
        ),
        "firmware_runner": _validate_firmware_runner_provenance(
            record.get("firmware_runner")
        ),
    }


def _validate_probe_identity(
    value: Any, *, runtime_provenance: Mapping[str, Any]
) -> dict[str, Any]:
    identity = _required_mapping(value, name="radio identity")
    if set(identity) != {
        "serial",
        "uri",
        "context_name",
        "context_description",
        "context_version",
        "context_attrs",
        "pylibiio_file",
        "libiio_source_commit",
    }:
        raise EvidenceInvalid("transport probe radio identity fields changed")
    uri = identity.get("uri")
    if not isinstance(uri, str) or not uri.startswith("usb:"):
        raise EvidenceInvalid("transport probe radio URI is not local USB")
    description = identity.get("context_description")
    if not isinstance(description, str) or not description:
        raise EvidenceInvalid("transport probe context description is empty")
    version = _required_list(identity.get("context_version"), name="context version")
    host = _required_mapping(
        runtime_provenance.get("host_libiio"), name="host libiio provenance"
    )
    attrs = _required_mapping(identity.get("context_attrs"), name="context attrs")
    pylibiio_file = identity.get("pylibiio_file")
    if (
        identity.get("serial") != PROBE_EXACT_SERIAL
        or identity.get("context_name") != "usb"
        or len(version) != 3
        or _required_int(version[0], name="context version major") != 0
        or _required_int(version[1], name="context version minor") != 25
        or type(version[2]) is not str
        or version[2] != "v0.25"
        or attrs.get("hw_serial") != PROBE_EXACT_SERIAL
        or attrs.get("usb,serial") != PROBE_EXACT_SERIAL
        or attrs.get("fw_version") != PROBE_EXACT_FIRMWARE_VERSION
        or attrs.get("iio,buffer-metadata") != "2"
        or attrs.get("uri") != uri
        or identity.get("libiio_source_commit") != PROBE_EXACT_LIBIIO_COMMIT
        or type(pylibiio_file) is not str
        or pylibiio_file != host.get("pylibiio_path")
    ):
        raise EvidenceInvalid(
            "transport probe radio/firmware/host identity is not exact R18 RC2"
        )
    return dict(identity)


def _validate_report_unowned_idle_status(
    value: Any, *, name: str, require_empty_fifo: bool
) -> dict[str, int]:
    status = _required_mapping(value, name=name)
    if set(status) != _TANDEM_STATUS_FIELDS:
        raise EvidenceInvalid(f"transport probe {name} status fields changed")
    parsed = {
        field: _required_int(status.get(field), name=f"{name} {field}")
        for field in _TANDEM_STATUS_FIELDS
    }
    required = {
        "state": int(TandemState.IDLE),
        "fault_flags": 0,
        "overflow_count": 0,
        "ownership_epoch": 0,
    }
    if any(parsed[field] != expected for field, expected in required.items()):
        raise EvidenceInvalid(f"transport probe {name} is not safely unowned IDLE")
    if parsed["fifo_level"] > 64:
        raise EvidenceInvalid(f"transport probe {name} FIFO exceeds capacity")
    if require_empty_fifo and parsed["fifo_level"] != 0:
        raise EvidenceInvalid(f"transport probe {name} FIFO is not empty")
    return parsed


def _validate_report_owned_hold_status(value: Any, *, name: str) -> dict[str, int]:
    status = _required_mapping(value, name=name)
    if set(status) != _TANDEM_STATUS_FIELDS:
        raise EvidenceInvalid(f"transport probe {name} status fields changed")
    parsed = {
        field: _required_int(status.get(field), name=f"{name} {field}")
        for field in _TANDEM_STATUS_FIELDS
    }
    if (
        parsed["state"] != int(TandemState.ARMED_HOLD)
        or parsed["ownership_epoch"] <= 0
        or parsed["fault_flags"] != 0
        or parsed["overflow_count"] != 0
        or parsed["fifo_level"] != 0
        or parsed["transition_count"] != 0
        or parsed["rx1_gain_index"] != parsed["rx2_gain_index"]
    ):
        raise EvidenceInvalid(f"transport probe {name} is not safe owned HOLD")
    return parsed


def _validate_manual_rx_report(
    value: Any, *, quality: TandemQualityOptions, name: str
) -> dict[str, Any]:
    state = _required_mapping(value, name=name)
    if set(state) != {"modes", "gains_db"} or state.get("modes") != [
        "manual",
        "manual",
    ]:
        raise EvidenceInvalid(f"transport probe {name} RX mode is not manual")
    gains = _required_list(state.get("gains_db"), name=f"{name} RX gains")
    if len(gains) != 2 or any(
        abs(_required_number(gain, name=f"{name} RX gain") - quality.manual_gain_db)
        > 0.1
        for gain in gains
    ):
        raise EvidenceInvalid(f"transport probe {name} RX gain is invalid")
    return {"modes": ["manual", "manual"], "gains_db": list(gains)}


def _validate_fifo_normalization_report(
    value: Any,
    *,
    quality: TandemQualityOptions,
    probe: TransientTransportProbeOptions,
) -> dict[str, int]:
    record = _required_mapping(value, name="stale_fifo_normalization")
    if set(record) != {
        "policy",
        "mute_evidence_before",
        "rx_state_before",
        "status_before",
        "stale_fifo_events",
        "action",
        "hold_session",
        "status_after",
        "rx_state_after",
    }:
        raise EvidenceInvalid("transport probe FIFO-normalization ledger changed")
    if record.get("policy") != _FIFO_NORMALIZATION_POLICY:
        raise EvidenceInvalid("transport probe FIFO-normalization policy changed")
    _validate_verified_mute_evidence(
        record.get("mute_evidence_before"), label="pre-normalization mute evidence"
    )
    rx_before = _validate_manual_rx_report(
        record.get("rx_state_before"),
        quality=quality,
        name="pre-normalization",
    )
    before = _validate_report_unowned_idle_status(
        record.get("status_before"),
        name="pre-normalization status",
        require_empty_fifo=False,
    )
    if record.get("stale_fifo_events") != before["fifo_level"]:
        raise EvidenceInvalid("transport probe stale-FIFO event count changed")
    after = _validate_report_unowned_idle_status(
        record.get("status_after"),
        name="post-normalization status",
        require_empty_fifo=True,
    )
    rx_after = _validate_manual_rx_report(
        record.get("rx_state_after"),
        quality=quality,
        name="post-normalization",
    )
    if rx_after != rx_before:
        raise EvidenceInvalid("transport probe FIFO normalization changed RX state")
    if before["fifo_level"] == 0:
        if (
            record.get("action") != "not_required"
            or record.get("hold_session") is not None
            or after != before
        ):
            raise EvidenceInvalid("transport probe forged a no-op FIFO normalization")
        return after

    hold_session = _required_mapping(record.get("hold_session"), name="HOLD session")
    active_status = _validate_report_owned_hold_status(
        hold_session.get("status_while_open"), name="in-session HOLD status"
    )
    if any(
        after[field] != active_status[field]
        for field in ("transition_count", "rx1_gain_index", "rx2_gain_index")
    ):
        raise EvidenceInvalid(
            "transport probe HOLD close changed transition or endpoint state"
        )
    expected_hold_session = {
        "mode": "hold",
        "kernel_buffers": 1,
        "samples_per_channel": probe.frame_samples,
        "refill_count": 0,
        "metadata_request": _request_evidence(
            _hold_normalization_request(quality, probe)
        ),
        "metadata_abi": 2,
        "opened": True,
        "closed": True,
        "status_while_open": active_status,
        "tx_policy": "fully muted before and throughout normalization",
    }
    if record.get("action") != "muted_hold_session_acquire_clear" or record.get(
        "hold_session"
    ) != _json_domain(expected_hold_session):
        raise EvidenceInvalid("transport probe HOLD FIFO normalization changed")
    return after


def _validate_verified_mute_evidence(value: Any, *, label: str) -> None:
    cleanup = _required_mapping(value, name=label)
    if cleanup.get("verified") is not True or cleanup.get("failures") != []:
        raise FixtureSafetyError(f"transport probe {label} is invalid")
    for name in ("tx1_gain_db", "tx2_gain_db"):
        if _required_number(cleanup.get(name), name=f"cleanup {name}") > -80.0:
            raise FixtureSafetyError(f"transport probe {label} {name} is not muted")
    selectors = _required_list(cleanup.get("selectors"), name="cleanup selectors")
    if selectors != [3, 3, 3, 3]:
        raise FixtureSafetyError(f"transport probe {label} selectors are not ZERO")
    dds = _required_mapping(cleanup.get("dds"), name="cleanup DDS")
    expected_names = {f"altvoltage{index}" for index in range(8)}
    if set(dds) != expected_names:
        raise FixtureSafetyError(f"transport probe {label} DDS inventory is incomplete")
    for name in sorted(expected_names):
        channel = _required_mapping(dds.get(name), name=f"cleanup DDS {name}")
        if channel.get("present") is not True:
            raise FixtureSafetyError(f"transport probe {label} DDS {name} is absent")
        for attribute in ("raw", "scale"):
            if (
                _required_number(
                    channel.get(attribute), name=f"cleanup DDS {name} {attribute}"
                )
                != 0.0
            ):
                raise FixtureSafetyError(
                    f"transport probe {label} DDS {name} {attribute} is nonzero"
                )


def _validate_cleanup_evidence(value: Any) -> None:
    _validate_verified_mute_evidence(value, label="durable cleanup")


def _validate_stable_report_suffix(
    frames: Sequence[Mapping[str, Any]],
    reported: Any,
    *,
    count: int,
    name: str,
) -> None:
    if len(frames) < count:
        raise EvidenceInvalid(f"transport probe report {name} is too short")
    suffix = list(frames[-count:])
    metadata = [
        _required_mapping(frame.get("metadata"), name=f"{name} metadata")
        for frame in suffix
    ]
    if any(
        _required_list(item.get("gain_events"), name="gain_events") for item in metadata
    ):
        raise EvidenceInvalid(f"transport probe report {name} contains events")
    transitions = {
        _required_int(item.get("tandem_transition_count"), name="transition_count")
        for item in metadata
    }
    endpoints = {
        tuple(_required_list(item.get("bench_gain_indices"), name="endpoint"))
        for item in metadata
    }
    if len(transitions) != 1 or len(endpoints) != 1:
        raise EvidenceInvalid(f"transport probe report {name} is not stable")
    for item in metadata:
        gain_range = _required_list(item.get("gain_index_range"), name="gain range")
        endpoint = _required_list(item.get("bench_gain_indices"), name="endpoint")
        if len(gain_range) != 2 or endpoint != [gain_range[1], gain_range[1]]:
            raise EvidenceInvalid(
                f"transport probe report {name} is not at the maximum-gain endpoint"
            )
    expected = {
        "frame_indices": [
            _required_int(frame.get("frame_index"), name="frame_index")
            for frame in suffix
        ],
        "transition_count": next(iter(transitions)),
        "bench_gain_indices": list(next(iter(endpoints))),
        "event_count": 0,
    }
    if reported != expected:
        raise EvidenceInvalid(f"transport probe report {name} ledger is inconsistent")


def _validate_quality_tail_report(
    value: Any,
    *,
    frame: Mapping[str, Any],
    quality: TandemQualityOptions,
    probe: TransientTransportProbeOptions,
    name: str,
) -> None:
    record = _required_mapping(value, name=name)
    frame_index = _required_int(frame.get("frame_index"), name=f"{name} frame_index")
    frame_end = _required_int(
        frame.get("sample_end_exclusive"), name=f"{name} frame end"
    )
    first_sample = frame_end - probe.anchor_samples
    expected_geometry = {
        "frame_index": frame_index,
        "sample_sequence_before": first_sample,
        "sample_sequence_after": frame_end,
        "sample_offset_in_frame": probe.frame_samples - probe.anchor_samples,
        "sample_count": probe.anchor_samples,
        "byte_offset_in_iq_payload": ((probe.frame_samples - probe.anchor_samples) * 8),
        "byte_count": probe.anchor_samples * 8,
        "source_frame_sha256": frame.get("sha256"),
    }
    if any(record.get(key) != expected for key, expected in expected_geometry.items()):
        raise EvidenceInvalid(f"transport probe {name} geometry changed")
    digest = record.get("tail_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise EvidenceInvalid(f"transport probe {name} lacks a tail digest")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise EvidenceInvalid(f"transport probe {name} digest is invalid") from exc
    analysis = _required_mapping(record.get("analysis"), name=f"{name} analysis")
    expected_analysis = {
        "first_sample_sequence": first_sample,
        "samples_per_channel": probe.anchor_samples,
        "sample_rate_hz": quality.sample_rate_hz,
        "expected_tone_hz": float(quality.tone_hz),
        "window_samples": probe.window_samples,
        "stride_samples": probe.window_samples,
        "window_count": probe.anchor_samples // probe.window_samples,
        "uncovered_tail_samples": 0,
        "quality_valid": True,
    }
    if any(
        analysis.get(key) != expected for key, expected in expected_analysis.items()
    ):
        raise EvidenceInvalid(f"transport probe {name} analysis geometry changed")
    selected_tone = _required_number(
        analysis.get("selected_tone_hz"), name=f"{name} selected tone"
    )
    if abs(selected_tone) != abs(float(quality.tone_hz)):
        raise EvidenceInvalid(f"transport probe {name} selected the wrong tone")
    windows = _required_list(analysis.get("windows"), name=f"{name} windows")
    if len(windows) != probe.anchor_samples // probe.window_samples:
        raise EvidenceInvalid(f"transport probe {name} window count changed")
    for index, raw_window in enumerate(windows):
        window = _required_mapping(raw_window, name=f"{name} window {index}")
        offset = index * probe.window_samples
        if (
            window.get("window_index") != index
            or window.get("offset_start") != offset
            or window.get("offset_end_exclusive") != offset + probe.window_samples
            or window.get("sample_start") != first_sample + offset
            or window.get("sample_end_exclusive")
            != first_sample + offset + probe.window_samples
        ):
            raise EvidenceInvalid(f"transport probe {name} window geometry changed")
        tone_snr = _required_list(window.get("tone_snr_db"), name=f"{name} tone SNR")
        tone_levels = _required_list(window.get("tone_dbfs"), name=f"{name} tone level")
        clipping = _required_list(
            window.get("clipping_fraction"), name=f"{name} clipping"
        )
        if len(tone_snr) != 2 or len(tone_levels) != 2 or len(clipping) != 2:
            raise EvidenceInvalid(f"transport probe {name} lacks dual-RX quality")
        reasons: list[str] = []
        for channel in (0, 1):
            if (
                _required_number(tone_snr[channel], name=f"{name} RX{channel} tone SNR")
                < quality.thresholds.min_tone_snr_db
            ):
                reasons.append(f"rx{channel}_tone_snr_low")
            tone_level = _required_number(
                tone_levels[channel], name=f"{name} RX{channel} tone level"
            )
            if tone_level < quality.thresholds.min_tone_dbfs:
                reasons.append(f"rx{channel}_tone_too_weak")
            if tone_level > quality.thresholds.max_tone_dbfs:
                reasons.append(f"rx{channel}_tone_too_strong")
            clipping_value = _required_number(
                clipping[channel], name=f"{name} RX{channel} clipping"
            )
            if not 0 <= clipping_value <= 1:
                raise EvidenceInvalid(
                    f"transport probe {name} RX{channel} clipping is impossible"
                )
            if clipping_value > quality.thresholds.max_clipping_fraction:
                reasons.append(f"rx{channel}_clipping")
        phase_std = _required_number(
            window.get("within_window_phase_std_deg"),
            name=f"{name} phase standard deviation",
        )
        if phase_std < 0:
            raise EvidenceInvalid(
                f"transport probe {name} phase standard deviation is negative"
            )
        if phase_std > quality.thresholds.max_phase_std_deg:
            reasons.append("within_window_phase_unstable")
        if window.get("quality_reasons") != reasons or window.get(
            "quality_valid"
        ) is not (not reasons):
            raise EvidenceInvalid(f"transport probe {name} quality verdict changed")
        if reasons:
            raise EvidenceInvalid(f"transport probe {name} failed RF quality gates")


def _validate_command_report(
    value: Any,
    *,
    quality: TandemQualityOptions,
    probe: TransientTransportProbeOptions,
    last_qualified_frame_end: int,
    first_batch_sample: int,
    last_batch_sample_exclusive: int,
) -> StimulusCommand:
    command = _required_mapping(value, name="command_contention.command")
    if set(command) != {
        "command_id",
        "requested_level_db",
        "applied_level_db",
        "host_before_ns",
        "host_after_ns",
        "host_jitter_ns",
        "sample_sequence_before",
        "sample_sequence_after",
        "sample_uncertainty",
        "effective_attenuation_db",
        "timing_role",
        "sample_timing_basis",
        "sample_anchor_policy",
        "sample_counter_bracket",
    }:
        raise EvidenceInvalid("transport probe command fields changed")
    if command.get("command_id") != "weak_control_reassertion":
        raise EvidenceInvalid("transport probe command identity changed")
    requested = _required_number(
        command.get("requested_level_db"), name="command requested level"
    )
    applied = _required_number(
        command.get("applied_level_db"), name="command applied level"
    )
    if requested != probe.weak_stimulus_tx_gain_db or abs(applied - requested) > (
        probe.readback_tolerance_db
    ):
        raise EvidenceInvalid("transport probe command is not the guarded weak level")
    effective = _required_number(
        command.get("effective_attenuation_db"), name="command attenuation"
    )
    if effective != quality.physical_attenuation_db - applied or effective < 30.0:
        raise EvidenceInvalid("transport probe command attenuation is invalid")
    host_before = _required_int(command.get("host_before_ns"), name="host_before_ns")
    host_after = _required_int(command.get("host_after_ns"), name="host_after_ns")
    host_jitter = _required_int(command.get("host_jitter_ns"), name="host_jitter_ns")
    if host_after - host_before != host_jitter or not (
        0 <= host_jitter <= probe.max_host_jitter_ns
    ):
        raise EvidenceInvalid("transport probe command host bracket is invalid")
    lower = _required_int(
        command.get("sample_sequence_before"), name="command sample lower"
    )
    upper = _required_int(
        command.get("sample_sequence_after"), name="command sample upper"
    )
    uncertainty = _required_int(
        command.get("sample_uncertainty"), name="command sample uncertainty"
    )
    if upper - lower != uncertainty or not (
        0 < uncertainty <= probe.max_command_sample_uncertainty
    ):
        raise EvidenceInvalid("transport probe command sample bracket is invalid")
    if lower < last_qualified_frame_end:
        raise EvidenceInvalid("transport probe command predates its 32-frame gate")
    if (
        command.get("timing_role")
        != ("same_level_write_bracketed_by_coherent_fpga_counter")
        or command.get("sample_timing_basis") != "hardware_sample_counter"
        or command.get("sample_anchor_policy")
        != (
            "post-open S0 plus a frozen 40-frame target; command interval is the "
            "coherent causal counter bracket [A,C) while the first batch refill runs"
        )
    ):
        raise EvidenceInvalid("transport probe command timing role is invalid")

    bracket = _required_mapping(
        command.get("sample_counter_bracket"), name="sample_counter_bracket"
    )
    expected_bracket_fields = {
        "register_address",
        "counter_width_bits",
        "counter_source",
        "post_open_baseline_raw",
        "target_offset_frames",
        "target_offset_samples",
        "target_raw",
        "last_below_raw",
        "raw_a_prewrite",
        "raw_post_write_initial",
        "raw_b_first_advance",
        "raw_c_causal_advance",
        "target_poll_read_count",
        "target_poll_policy",
        "target_coarse_guard_samples",
        "target_fine_sleep_samples",
        "target_max_poll_reads",
        "target_poll_observations",
        "target_total_requested_sleep_samples",
        "post_write_read_count",
        "target_overshoot_samples",
        "causal_uncertainty_samples",
        "worker_in_flight_at_command",
        "first_batch_sample",
        "last_batch_sample_exclusive",
        "post_open_baseline_sample",
        "target_sample",
        "last_below_sample",
        "a_prewrite_sample",
        "post_write_initial_sample",
        "b_first_advance_sample",
        "c_causal_advance_sample",
        "command_interval",
    }
    if set(bracket) != expected_bracket_fields:
        raise EvidenceInvalid("transport probe command bracket fields changed")
    raw_s0 = _required_int(
        bracket.get("post_open_baseline_raw"), name="counter raw S0"
    )
    raw_target = _required_int(bracket.get("target_raw"), name="counter raw target")
    raw_p = _required_int(
        bracket.get("last_below_raw"), name="counter raw last-below"
    )
    raw_a = _required_int(bracket.get("raw_a_prewrite"), name="counter raw A")
    raw_initial = _required_int(
        bracket.get("raw_post_write_initial"), name="counter raw_initial"
    )
    raw_b = _required_int(
        bracket.get("raw_b_first_advance"), name="counter raw B"
    )
    raw_c = _required_int(
        bracket.get("raw_c_causal_advance"), name="counter raw C"
    )
    if any(
        not 0 <= value < 1 << 32
        for value in (raw_s0, raw_target, raw_p, raw_a, raw_initial, raw_b, raw_c)
    ):
        raise EvidenceInvalid("transport probe raw command counter exceeds uint32")
    p_delta = (raw_p - raw_s0) % (1 << 32)
    a_delta = (raw_a - raw_s0) % (1 << 32)
    initial_delta = (raw_initial - raw_a) % (1 << 32)
    b_delta = (raw_b - raw_initial) % (1 << 32)
    c_delta = (raw_c - raw_b) % (1 << 32)
    if initial_delta >= 1 << 31 or not all(
        0 < delta < 1 << 31 for delta in (b_delta, c_delta)
    ):
        raise EvidenceInvalid("transport probe command counter advances are ambiguous")
    s0 = _required_int(
        bracket.get("post_open_baseline_sample"), name="extended S0"
    )
    target = _required_int(bracket.get("target_sample"), name="extended target")
    extended_p = _required_int(
        bracket.get("last_below_sample"), name="extended last-below"
    )
    extended_a = _required_int(
        bracket.get("a_prewrite_sample"), name="extended A"
    )
    extended_initial = _required_int(
        bracket.get("post_write_initial_sample"), name="extended initial"
    )
    extended_b = _required_int(
        bracket.get("b_first_advance_sample"), name="extended B"
    )
    extended_c = _required_int(
        bracket.get("c_causal_advance_sample"), name="extended C"
    )
    target_offset = probe.target_sample_offset
    target_error = extended_a - target
    causal_uncertainty = extended_c - extended_a
    if (
        s0 & ((1 << 32) - 1) != raw_s0
        or target & ((1 << 32) - 1) != raw_target
        or extended_p & ((1 << 32) - 1) != raw_p
        or extended_a & ((1 << 32) - 1) != raw_a
        or extended_initial & ((1 << 32) - 1) != raw_initial
        or extended_b & ((1 << 32) - 1) != raw_b
        or extended_c & ((1 << 32) - 1) != raw_c
        or not all(
            0 <= item < 1 << 64
            for item in (
                s0,
                target,
                extended_p,
                extended_a,
                extended_initial,
                extended_b,
                extended_c,
                lower,
                upper,
            )
        )
        or extended_p != s0 + p_delta
        or extended_a != s0 + a_delta
        or extended_initial != extended_a + initial_delta
        or extended_b != extended_initial + b_delta
        or extended_c != extended_b + c_delta
        or target != s0 + target_offset
        or lower != extended_a
        or upper != extended_c
        or lower < last_qualified_frame_end
        or not s0 < target
        or not first_batch_sample <= target < last_batch_sample_exclusive
        or not extended_p < target <= extended_a < extended_c
        or not 0 < extended_a - extended_p < 1 << 31
        or not 0 <= target_error <= probe.max_command_sample_uncertainty
        or not 0 < causal_uncertainty <= probe.max_command_sample_uncertainty
        or bracket.get("first_batch_sample") != first_batch_sample
        or bracket.get("last_batch_sample_exclusive")
        != last_batch_sample_exclusive
        or bracket.get("target_offset_frames") != probe.command_target_frames
        or bracket.get("target_offset_samples") != target_offset
        or bracket.get("target_overshoot_samples") != target_error
        or bracket.get("causal_uncertainty_samples") != causal_uncertainty
        or bracket.get("worker_in_flight_at_command") is not True
        or bracket.get("command_interval") != "[A,C)"
        or bracket.get("register_address") != "0x800000b8"
        or bracket.get("counter_width_bits") != 32
        or bracket.get("counter_source") != "coherent FPGA RX sample counter low word"
    ):
        raise EvidenceInvalid("transport probe command counter ledger is inconsistent")
    target_reads = _required_int(
        bracket.get("target_poll_read_count"), name="target_poll_read_count"
    )
    post_reads = _required_int(
        bracket.get("post_write_read_count"), name="post_write_read_count"
    )
    poll_observations = _required_list(
        bracket.get("target_poll_observations"), name="target_poll_observations"
    )
    if (
        bracket.get("target_poll_policy")
        != (
            "counter-adaptive coarse guard, 4096-sample fine sleeps, bounded "
            "tail polls"
        )
        or bracket.get("target_coarse_guard_samples")
        != _PROBE_TARGET_COARSE_GUARD_SAMPLES
        or bracket.get("target_fine_sleep_samples")
        != _PROBE_TARGET_FINE_SLEEP_SAMPLES
        or bracket.get("target_max_poll_reads") != _PROBE_TARGET_MAX_POLL_READS
        or not 2 <= target_reads == len(poll_observations) <= (
            _PROBE_TARGET_MAX_POLL_READS
        )
        or not 3 <= post_reads <= 9
    ):
        raise EvidenceInvalid("transport probe command read count is outside policy")
    prior_advance = -1
    expected_total_sleep = 0
    for index, raw_observation in enumerate(poll_observations):
        observation = _required_mapping(
            raw_observation, name=f"target poll observation {index}"
        )
        if set(observation) != {
            "raw",
            "advance_samples",
            "remaining_samples",
            "phase",
            "requested_sleep_samples",
        }:
            raise EvidenceInvalid("transport probe target poll fields changed")
        observed_raw = _required_int(observation.get("raw"), name="poll raw")
        advance = _required_int(
            observation.get("advance_samples"), name="poll advance"
        )
        remaining = _required_int(
            observation.get("remaining_samples"), name="poll remaining"
        )
        sleep_samples = _required_int(
            observation.get("requested_sleep_samples"), name="poll sleep"
        )
        if (
            not 0 <= observed_raw < 1 << 32
            or observed_raw != (raw_s0 + advance) % (1 << 32)
            or not prior_advance <= advance < 1 << 31
            or sleep_samples < 0
        ):
            raise EvidenceInvalid("transport probe target poll counter is invalid")
        prior_advance = advance
        if index == len(poll_observations) - 1:
            expected = {
                "remaining": 0,
                "phase": "target_reached",
                "sleep": 0,
            }
            if advance != a_delta:
                raise EvidenceInvalid("transport probe target poll does not end at A")
        else:
            expected_remaining = target_offset - advance
            if expected_remaining <= 0:
                raise EvidenceInvalid("transport probe target poll passed T early")
            if expected_remaining > _PROBE_TARGET_COARSE_GUARD_SAMPLES:
                expected_phase = "coarse_sleep"
                expected_sleep = (
                    expected_remaining - _PROBE_TARGET_COARSE_GUARD_SAMPLES
                )
            elif expected_remaining > 2 * _PROBE_TARGET_FINE_SLEEP_SAMPLES:
                expected_phase = "fine_sleep"
                expected_sleep = _PROBE_TARGET_FINE_SLEEP_SAMPLES
            else:
                expected_phase = "tail_poll"
                expected_sleep = 0
            expected = {
                "remaining": expected_remaining,
                "phase": expected_phase,
                "sleep": expected_sleep,
            }
            expected_total_sleep += expected_sleep
        if (
            remaining != expected["remaining"]
            or observation.get("phase") != expected["phase"]
            or sleep_samples != expected["sleep"]
        ):
            raise EvidenceInvalid("transport probe target poll pacing is inconsistent")
    if (
        poll_observations[-2].get("raw") != raw_p
        or bracket.get("target_total_requested_sleep_samples")
        != expected_total_sleep
    ):
        raise EvidenceInvalid("transport probe target sleep ledger is inconsistent")
    return StimulusCommand(
        command_id="weak_control_reassertion",
        requested_level_db=requested,
        applied_level_db=applied,
        host_before_ns=host_before,
        host_after_ns=host_after,
        sample_sequence_before=lower,
        sample_sequence_after=upper,
    )


def _validate_transient_transport_probe_report_impl(
    report: Mapping[str, Any],
    quality: TandemQualityOptions,
    probe: TransientTransportProbeOptions,
    *,
    require_cleanup: bool,
) -> None:
    if report.get("schema") != PROBE_SCHEMA:
        raise EvidenceInvalid("transport probe report schema is invalid")
    expected_verdict = PROBE_VERDICT if require_cleanup else PROBE_PENDING_VERDICT
    if report.get("verdict") != expected_verdict:
        raise EvidenceInvalid("transport probe report is not qualified")
    if report.get("release_pass_eligible") is not False:
        raise EvidenceInvalid("transport probe report is release-pass eligible")
    if "fatal_error" in report or report.get("iq_artifacts_saved") is not False:
        raise EvidenceInvalid("transport probe qualified report carries invalid state")
    runtime_provenance = _validate_runtime_provenance(
        report.get("runtime_provenance")
    )
    _validate_probe_identity(
        report.get("identity"), runtime_provenance=runtime_provenance
    )
    if report.get("qualification_scope") != _qualification_scope():
        raise EvidenceInvalid("transport probe qualification scope changed")
    if report.get("safety") != _json_domain(_safety_policy(quality, probe)):
        raise EvidenceInvalid("transport probe safety policy changed")
    if report.get("evidence_policy") != _json_domain(_evidence_policy(probe)):
        raise EvidenceInvalid("transport probe evidence policy changed")
    normalized_status_after = _validate_fifo_normalization_report(
        report.get("stale_fifo_normalization"), quality=quality, probe=probe
    )

    configuration = _required_mapping(report.get("configuration"), name="configuration")
    if configuration.get("probe") != _json_domain(asdict(probe)):
        raise EvidenceInvalid("transport probe report configuration changed")
    if configuration.get("quality") != _json_domain(_quality_configuration(quality)):
        raise EvidenceInvalid("transport probe quality configuration changed")
    rf = _required_mapping(report.get("rf"), name="rf")
    expected_rf = {
        "center_frequency_hz_requested": quality.center_frequency_hz,
        "center_frequency_hz_readback": {
            "rx_lo_hz": quality.center_frequency_hz,
            "tx_lo_hz": quality.center_frequency_hz,
        },
        "sample_rate_hz": quality.sample_rate_hz,
        "tone_hz": quality.tone_hz,
        "dds_scale": quality.dds_scale,
        "weak_tx2_gain_db": probe.weak_stimulus_tx_gain_db,
    }
    if set(rf) != set(expected_rf):
        raise EvidenceInvalid("transport probe RF ledger has unexpected fields")
    readback = _required_mapping(
        rf.get("center_frequency_hz_readback"), name="LO readback"
    )
    for key, expected in expected_rf.items():
        if key == "center_frequency_hz_readback":
            if set(readback) != {"rx_lo_hz", "tx_lo_hz"} or any(
                abs(
                    _required_int(readback.get(name), name=name)
                    - quality.center_frequency_hz
                )
                > 2
                for name in ("rx_lo_hz", "tx_lo_hz")
            ):
                raise EvidenceInvalid("transport probe LO readback is invalid")
        elif rf.get(key) != expected:
            raise EvidenceInvalid(f"transport probe RF field {key} changed")

    expected_request = _request_evidence(_probe_auto_request(quality, probe))
    if report.get("metadata_request") != _json_domain(expected_request):
        raise EvidenceInvalid("transport probe AUTO request evidence changed")
    if report.get("metadata_abi") != 2:
        raise EvidenceInvalid("transport probe report lacks metadata ABI 2")
    if report.get("capacity_policy") != _json_domain(_capacity_policy(quality, probe)):
        raise EvidenceInvalid("transport probe capacity proof changed")
    if report.get("memory_policy") != _json_domain(_report_memory_policy(probe)):
        raise EvidenceInvalid("transport probe memory proof changed")

    frames = _required_list(report.get("frames"), name="frames")
    if len(frames) != probe.retained_frames:
        raise EvidenceInvalid(
            f"transport probe report retained {len(frames)} frames, "
            f"requires {probe.retained_frames}"
        )
    prior_metadata: Mapping[str, Any] | None = None
    prior_refill: int | None = None
    prior_event: Mapping[str, Any] | None = None
    stream_id: int | None = None
    ownership_epoch: int | None = None
    provenance: tuple[Any, ...] | None = None
    maximum_events = maximum_tandem_events_per_frame(
        mode=TandemMode.AUTO,
        samples_per_channel=probe.frame_samples,
        power_measurement_samples=quality.tandem_power_measurement_samples,
        cooldown_periods=quality.tandem_cooldown_periods,
    )
    minimum_event_spacing = quality.tandem_power_measurement_samples * (
        quality.tandem_cooldown_periods + 1
    )
    maximum_observations = int(
        _capacity_policy(quality, probe)["overlap_safe_stored_observations_per_frame"]
    )
    for index, raw_frame in enumerate(frames):
        frame = _required_mapping(raw_frame, name=f"frame {index}")
        if _required_int(frame.get("frame_index"), name="frame_index") != index:
            raise EvidenceInvalid("transport probe frame indices are not exact")
        if frame.get("timing_basis") != "hardware_sample_counter":
            raise EvidenceInvalid("transport probe frame timing basis changed")
        if frame.get("physical_sample_continuity_proven") is not True:
            raise EvidenceInvalid("transport probe frame continuity is not proven")
        if (
            frame.get("sample_gap_before") != 0
            or frame.get("gap_context") != "continuous_acquisition_unclassified"
            or frame.get("command_boundary_gap_allowed") is not False
        ):
            raise EvidenceInvalid("transport probe top-level gap ledger changed")
        if _required_int(frame.get("iq_bytes"), name="iq_bytes") != (
            probe.frame_samples * 8
        ):
            raise EvidenceInvalid("transport probe frame IQ byte count changed")
        digest = frame.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise EvidenceInvalid("transport probe frame lacks a SHA-256 digest")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise EvidenceInvalid(
                "transport probe frame digest is not hexadecimal"
            ) from exc
        refill = _required_int(
            frame.get("refill_monotonic_ns"), name="refill_monotonic_ns"
        )
        if prior_refill is not None and refill < prior_refill:
            raise EvidenceInvalid("transport probe refill ledger regressed")
        prior_refill = refill
        metadata = _required_mapping(frame.get("metadata"), name="metadata")
        if _required_int(metadata.get("version"), name="metadata version") != 5:
            raise EvidenceInvalid("transport probe metadata version changed")
        if _required_int(metadata.get("header_bytes"), name="header_bytes") != (
            _PROBE_METADATA_HEADER_BYTES
        ):
            raise EvidenceInvalid("transport probe metadata layout changed")
        features = _required_int(metadata.get("features"), name="features")
        flags = _required_int(metadata.get("flags"), name="flags")
        if features & _PROBE_REQUIRED_METADATA_FEATURES != (
            _PROBE_REQUIRED_METADATA_FEATURES
        ) or flags & _PROBE_REQUIRED_METADATA_FLAGS != (_PROBE_REQUIRED_METADATA_FLAGS):
            raise EvidenceInvalid("transport probe required metadata bits are absent")
        if flags & TANDEM_UNSAFE_FLAGS:
            raise EvidenceInvalid("transport probe metadata has unsafe flags")
        current_stream = _required_int(
            metadata.get("stream_id"), name="stream_id", minimum=1
        )
        current_epoch = _required_int(
            metadata.get("ownership_epoch"), name="ownership_epoch", minimum=1
        )
        if stream_id is None:
            stream_id, ownership_epoch = current_stream, current_epoch
        elif (current_stream, current_epoch) != (stream_id, ownership_epoch):
            raise EvidenceInvalid("transport probe stream or ownership changed")
        buffer_sequence = _required_int(
            metadata.get("buffer_sequence"), name="buffer_sequence"
        )
        first_sample = _required_int(
            metadata.get("first_sample_sequence"), name="first_sample_sequence"
        )
        if first_sample + probe.frame_samples > 1 << 64:
            raise EvidenceInvalid("transport probe frame exceeds uint64 sample time")
        if index == 0 and buffer_sequence != 0:
            raise EvidenceInvalid("transport probe first buffer is not sequence zero")
        if (
            current_stream >= 1 << 64
            or buffer_sequence >= 1 << 64
            or current_epoch >= 1 << 32
        ):
            raise EvidenceInvalid("transport probe stream counters exceed wire range")
        if (
            frame.get("first_sample_sequence") != first_sample
            or frame.get("sample_end_exclusive") != first_sample + probe.frame_samples
        ):
            raise EvidenceInvalid("transport probe frame/sample ledger disagrees")
        if (
            metadata.get("samples_per_channel") != probe.frame_samples
            or metadata.get("iq_payload_bytes") != probe.frame_samples * 8
        ):
            raise EvidenceInvalid("transport probe metadata payload geometry changed")
        if (
            metadata.get("enabled_scan_mask") != 0x0F
            or metadata.get("channel_count") != 2
        ):
            raise EvidenceInvalid("transport probe metadata is not dual complex RX")
        observation_count = _required_int(
            metadata.get("observation_count"), name="observation_count"
        )
        event_count = _required_int(metadata.get("event_count"), name="event_count")
        if (
            metadata.get("observation_capacity") != 64
            or metadata.get("event_capacity") != 64
        ):
            raise EvidenceInvalid("transport probe metadata capacity changed")
        if not 0 <= observation_count <= 64 or not 0 <= event_count <= 64:
            raise EvidenceInvalid("transport probe metadata count exceeds capacity")
        if observation_count > maximum_observations:
            raise EvidenceInvalid(
                "transport probe observation count exceeds the provider overlap bound"
            )
        if event_count > maximum_events:
            raise EvidenceInvalid(
                "transport probe event count exceeds its configured physics bound"
            )
        if (
            metadata.get("observation_overflow_count") != 0
            or metadata.get("event_overflow_count") != 0
        ):
            raise EvidenceInvalid("transport probe metadata overflowed")
        if (
            metadata.get("tandem_state") != int(TandemState.ARMED_AUTO)
            or metadata.get("tandem_state_name") != "armed_auto"
        ):
            raise EvidenceInvalid("transport probe tandem state changed")
        if metadata.get("tandem_fault_flags") != 0:
            raise EvidenceInvalid("transport probe tandem metadata faulted")
        if metadata.get("gain_table_id") != int(
            expected_tandem_gain_table(quality.center_frequency_hz)
        ):
            raise EvidenceInvalid("transport probe gain table changed")
        if (
            metadata.get("gain_db_range") != [0, 62]
            or metadata.get("initial_gain_db") != probe.auto_initial_gain_db
        ):
            raise EvidenceInvalid("transport probe request provenance changed")
        if metadata.get("sample_format") != 1 or metadata.get(
            "threshold_provenance"
        ) != _expected_threshold_provenance(quality):
            raise EvidenceInvalid("transport probe wire/request provenance changed")
        gain_range = _required_list(
            metadata.get("gain_index_range"), name="gain_index_range"
        )
        endpoint = _required_list(
            metadata.get("bench_gain_indices"), name="bench_gain_indices"
        )
        if len(gain_range) != 2 or len(endpoint) != 2:
            raise EvidenceInvalid("transport probe gain geometry is invalid")
        minimum_gain = _required_int(gain_range[0], name="minimum_gain_index")
        maximum_gain = _required_int(gain_range[1], name="maximum_gain_index")
        endpoint_pair = (
            _required_int(endpoint[0], name="rx1_gain_index"),
            _required_int(endpoint[1], name="rx2_gain_index"),
        )
        if endpoint_pair[0] != endpoint_pair[1] or not (
            minimum_gain <= endpoint_pair[0] <= maximum_gain
        ):
            raise EvidenceInvalid("transport probe endpoint is invalid")
        if endpoint_pair != (
            maximum_gain,
            maximum_gain,
        ):
            raise EvidenceInvalid(
                f"transport probe frame {index} is not at the maximum-gain endpoint"
            )
        current_provenance = (
            features,
            metadata.get("sample_format"),
            metadata.get("threshold_provenance"),
            tuple(gain_range),
        )
        if provenance is None:
            provenance = current_provenance
        elif current_provenance != provenance:
            raise EvidenceInvalid("transport probe provenance changed in session")

        events = _required_list(metadata.get("gain_events"), name="gain_events")
        if event_count != len(events):
            raise EvidenceInvalid("transport probe event count disagrees with ledger")
        for raw_event in events:
            event = _required_mapping(raw_event, name="gain event")
            event_flags = _required_int(event.get("flags"), name="event flags")
            direction = _required_int(event.get("direction"), name="event direction")
            reason = _required_int(event.get("reason"), name="event reason")
            try:
                parsed_direction = TandemEventDirection(direction)
                parsed_reason = TandemEventReason(reason)
            except ValueError as exc:
                raise EvidenceInvalid("transport probe event enum is invalid") from exc
            if (
                event_flags != (direction << 4) | reason
                or event_flags & ~0x3F
                or event.get("direction_name") != parsed_direction.name.lower()
                or event.get("reason_name") != parsed_reason.name.lower()
            ):
                raise EvidenceInvalid("transport probe event flags/names disagree")
            event_sample = _required_int(
                event.get("sample_sequence"), name="event sample_sequence"
            )
            event_sequence = _required_int(
                event.get("event_sequence"), name="event_sequence"
            )
            if event_sequence >= 1 << 32:
                raise EvidenceInvalid("transport probe event sequence exceeds uint32")
            rx1 = _required_int(event.get("rx1_gain_index"), name="event rx1 gain")
            rx2 = _required_int(event.get("rx2_gain_index"), name="event rx2 gain")
            if rx1 != rx2 or not minimum_gain <= rx1 <= maximum_gain:
                raise EvidenceInvalid("transport probe event gain is invalid")
            if not first_sample <= event_sample < first_sample + probe.frame_samples:
                raise EvidenceInvalid("transport probe event is outside its frame")
            if prior_event is not None:
                prior_sequence = _required_int(
                    prior_event.get("event_sequence"), name="prior event sequence"
                )
                if (event_sequence - prior_sequence) % (1 << 32) != 1:
                    raise EvidenceInvalid("transport probe event sequence has a hole")
                prior_event_sample = _required_int(
                    prior_event.get("sample_sequence"), name="prior event sample"
                )
                if event_sample < prior_event_sample:
                    raise EvidenceInvalid("transport probe event samples regressed")
                if event_sample - prior_event_sample < minimum_event_spacing:
                    raise EvidenceInvalid(
                        "transport probe gain events violate cooldown spacing"
                    )
                prior_gain = _required_int(
                    prior_event.get("rx1_gain_index"), name="prior event gain"
                )
                expected_gain = prior_gain + (
                    1 if parsed_direction is TandemEventDirection.INCREASE else -1
                )
                if rx1 != expected_gain:
                    raise EvidenceInvalid("transport probe event step is not exact")
            elif prior_metadata is not None:
                prior_endpoint = _required_list(
                    prior_metadata.get("bench_gain_indices"), name="prior endpoint"
                )
                expected_gain = _required_int(
                    prior_endpoint[0], name="prior endpoint gain"
                ) + (1 if parsed_direction is TandemEventDirection.INCREASE else -1)
                if rx1 != expected_gain:
                    raise EvidenceInvalid("transport probe first event step is invalid")
            prior_event = event
        if events:
            last_event = _required_mapping(events[-1], name="last event")
            if endpoint_pair != (
                last_event.get("rx1_gain_index"),
                last_event.get("rx2_gain_index"),
            ):
                raise EvidenceInvalid(
                    "transport probe endpoint differs from last event"
                )
        elif prior_metadata is not None and endpoint != prior_metadata.get(
            "bench_gain_indices"
        ):
            raise EvidenceInvalid("transport probe endpoint changed without event")

        transition_count = _required_int(
            metadata.get("tandem_transition_count"), name="transition_count"
        )
        if transition_count >= 1 << 32:
            raise EvidenceInvalid("transport probe transition count exceeds uint32")
        continuity = _required_mapping(frame.get("continuity"), name="continuity")
        if prior_metadata is None:
            if transition_count != event_count:
                raise EvidenceInvalid(
                    "transport probe first frame has unrepresented transitions"
                )
            if transition_count != 0 or event_count != 0:
                raise EvidenceInvalid(
                    "transport probe first frame contains a represented startup "
                    "transition"
                )
            expected_continuity = {
                "buffer_delta": None,
                "sample_delta": None,
                "transition_count_delta": None,
                "initial_unrepresented_transition_count": transition_count
                - event_count,
            }
        else:
            prior_buffer = _required_int(
                prior_metadata.get("buffer_sequence"), name="prior buffer_sequence"
            )
            prior_sample = _required_int(
                prior_metadata.get("first_sample_sequence"), name="prior sample"
            )
            prior_transition = _required_int(
                prior_metadata.get("tandem_transition_count"), name="prior transition"
            )
            transition_delta = (transition_count - prior_transition) % (1 << 32)
            if (
                buffer_sequence - prior_buffer != 1
                or first_sample - prior_sample != probe.frame_samples
                or transition_delta != event_count
            ):
                raise EvidenceInvalid("transport probe has a gap or hidden transition")
            expected_continuity = {
                "buffer_delta": 1,
                "sample_delta": probe.frame_samples,
                "transition_count_delta": transition_delta,
                "initial_unrepresented_transition_count": 0,
            }
            if transition_count != 0 or event_count != 0:
                raise EvidenceInvalid(
                    "transport probe AUTO session contains a gain transition"
                )
        for key, expected in expected_continuity.items():
            if continuity.get(key) != expected:
                raise EvidenceInvalid(
                    f"transport probe continuity field {key} is inconsistent"
                )
        exact_zero = {
            "missing_frame_count": 0,
            "sample_gap_before": 0,
            "hidden_transition_count": 0,
            "cumulative_missing_frame_count": 0,
            "cumulative_hidden_transition_count": 0,
            "cumulative_event_sequence_hole_count": 0,
        }
        if any(continuity.get(key) != expected for key, expected in exact_zero.items()):
            raise EvidenceInvalid("transport probe continuity counters are nonzero")
        if (
            continuity.get("visible_event_count") != event_count
            or continuity.get("provider_gap_accepted") is not False
            or continuity.get("command_boundary_gap_allowed") is not False
        ):
            raise EvidenceInvalid("transport probe event/gap ledger is inconsistent")
        prior_metadata = metadata

    initial_frames = frames[: probe.fully_pre_command_frames]
    _validate_stable_report_suffix(
        initial_frames,
        report.get("initial_stable_suffix"),
        count=probe.stable_frames,
        name="initial_stable_suffix",
    )
    anchor_frame = _required_mapping(initial_frames[-1], name="anchor frame")
    anchor_end = _required_int(
        anchor_frame.get("sample_end_exclusive"), name="anchor frame end"
    )
    anchor_digest = anchor_frame.get("sha256")
    tail_digest_value = _required_mapping(
        report.get("conditioning_anchor_candidate"),
        name="conditioning_anchor_candidate",
    ).get("tail_sha256")
    if not isinstance(tail_digest_value, str) or len(tail_digest_value) != 64:
        raise EvidenceInvalid("transport probe anchor lacks a tail SHA-256")
    try:
        int(tail_digest_value, 16)
    except ValueError as exc:
        raise EvidenceInvalid("transport probe anchor tail digest is invalid") from exc
    expected_anchor = {
        "frame_index": probe.fully_pre_command_frames - 1,
        "sample_sequence_before": anchor_end - probe.anchor_samples,
        "sample_sequence_after": anchor_end,
        "sample_uncertainty": probe.anchor_samples,
        "sample_offset_in_frame": probe.frame_samples - probe.anchor_samples,
        "sample_count": probe.anchor_samples,
        "byte_offset_in_iq_payload": ((probe.frame_samples - probe.anchor_samples) * 8),
        "byte_count": probe.anchor_samples * 8,
        "source_frame_sha256": anchor_digest,
        "tail_sha256": tail_digest_value,
        "timing_basis": "hardware_sample_counter",
        "role": "stable_tail_candidate_for_future_transient",
        "release_latency_evidence": False,
    }
    if report.get("conditioning_anchor_candidate") != expected_anchor:
        raise EvidenceInvalid("transport probe conditioning anchor changed")

    contention = _required_mapping(
        report.get("command_contention"), name="command_contention"
    )
    if (
        contention.get("command_timing_qualified") is not True
        or contention.get("gain_transient_exercised") is not False
    ):
        raise EvidenceInvalid("transport probe contention scope is invalid")
    command = _validate_command_report(
        contention.get("command"),
        quality=quality,
        probe=probe,
        last_qualified_frame_end=anchor_end,
        first_batch_sample=_required_int(
            frames[0].get("first_sample_sequence"), name="first batch sample"
        ),
        last_batch_sample_exclusive=_required_int(
            frames[-1].get("sample_end_exclusive"), name="last batch sample"
        ),
    )
    assert command.sample_sequence_before is not None
    assert command.sample_sequence_after is not None
    contexts: list[str] = []
    for raw_frame in frames:
        frame = _required_mapping(raw_frame, name="command frame")
        start = _required_int(
            frame.get("first_sample_sequence"), name="command frame start"
        )
        end = _required_int(frame.get("sample_end_exclusive"), name="command frame end")
        if end <= command.sample_sequence_before:
            context = "fully_pre_command"
        elif start < command.sample_sequence_after and end > (
            command.sample_sequence_before
        ):
            context = "command_bracket"
        else:
            context = "fully_post_command"
        if frame.get("probe_phase") != context:
            raise EvidenceInvalid(
                "transport probe command phase ledger is inconsistent"
            )
        contexts.append(context)
    order = {
        "fully_pre_command": 0,
        "command_bracket": 1,
        "fully_post_command": 2,
    }
    if contexts != sorted(contexts, key=order.__getitem__):
        raise EvidenceInvalid("transport probe command phases are not ordered")
    fully_pre = contexts.count("fully_pre_command")
    fully_post = contexts.count("fully_post_command")
    expected_partition = {
        "frame_indices": list(range(probe.retained_frames)),
        "phase_by_frame": contexts,
        "fully_pre_command_frames": fully_pre,
        "required_fully_pre_command_frames": probe.fully_pre_command_frames,
        "command_bracket_frames": contexts.count("command_bracket"),
        "fully_post_command_frames": fully_post,
        "required_fully_post_command_frames": probe.fully_post_command_frames,
    }
    if fully_pre < probe.fully_pre_command_frames or fully_post < (
        probe.fully_post_command_frames
    ) or contexts[: probe.fully_pre_command_frames] != [
        "fully_pre_command"
    ] * probe.fully_pre_command_frames:
        raise EvidenceInvalid("transport probe command partition is insufficient")
    if contention.get("partition") != expected_partition:
        raise EvidenceInvalid("transport probe command partition ledger changed")
    final_frames = [
        frame
        for frame, context in zip(frames, contexts, strict=True)
        if context == "fully_post_command"
    ]
    _validate_stable_report_suffix(
        final_frames,
        report.get("final_stable_suffix"),
        count=probe.stable_frames,
        name="final_stable_suffix",
    )
    weak_quality = _required_mapping(
        report.get("weak_signal_quality"), name="weak_signal_quality"
    )
    if (
        weak_quality.get("timing_scope")
        != "post-buffer analysis of returned weak-IQ tails"
        or weak_quality.get("quality_required") is not True
    ):
        raise EvidenceInvalid("transport probe weak-signal quality scope changed")
    conditioning_quality = weak_quality.get("conditioning_anchor")
    _validate_quality_tail_report(
        conditioning_quality,
        frame=initial_frames[-1],
        quality=quality,
        probe=probe,
        name="conditioning quality tail",
    )
    if (
        _required_mapping(conditioning_quality, name="conditioning quality tail").get(
            "tail_sha256"
        )
        != tail_digest_value
    ):
        raise EvidenceInvalid("transport probe anchor quality digest changed")
    final_quality = _required_list(
        weak_quality.get("final_stable_suffix"), name="final quality suffix"
    )
    if len(final_quality) != probe.stable_frames:
        raise EvidenceInvalid("transport probe final quality suffix is incomplete")
    for value, frame in zip(final_quality, frames[-probe.stable_frames :], strict=True):
        _validate_quality_tail_report(
            value,
            frame=frame,
            quality=quality,
            probe=probe,
            name="final quality tail",
        )

    initial_command = _required_mapping(
        report.get("weak_conditioning_command"), name="weak_conditioning_command"
    )
    if (
        initial_command.get("command_id") != "weak_initial"
        or initial_command.get("sample_sequence_before") is not None
        or initial_command.get("sample_sequence_after") is not None
        or initial_command.get("sample_uncertainty") is not None
    ):
        raise EvidenceInvalid("transport probe conditioning command is invalid")
    if (
        initial_command.get("timing_role") != "pre_session_weak_conditioning_write"
        or initial_command.get("sample_timing_basis") is not None
        or initial_command.get("sample_anchor_policy")
        != ("unbounded in hardware sample time; the write predates the AUTO session")
    ):
        raise EvidenceInvalid("transport probe conditioning timing role changed")
    initial_requested = _required_number(
        initial_command.get("requested_level_db"), name="initial requested level"
    )
    initial_applied = _required_number(
        initial_command.get("applied_level_db"), name="initial applied level"
    )
    if (
        initial_requested != probe.weak_stimulus_tx_gain_db
        or abs(initial_applied - initial_requested) > probe.readback_tolerance_db
    ):
        raise EvidenceInvalid("transport probe conditioning level changed")
    initial_effective = _required_number(
        initial_command.get("effective_attenuation_db"), name="initial attenuation"
    )
    if initial_effective != quality.physical_attenuation_db - initial_applied or (
        initial_effective < 30.0
    ):
        raise EvidenceInvalid("transport probe conditioning attenuation is invalid")
    initial_host_before = _required_int(
        initial_command.get("host_before_ns"), name="initial host_before_ns"
    )
    initial_host_after = _required_int(
        initial_command.get("host_after_ns"), name="initial host_after_ns"
    )
    initial_host_jitter = _required_int(
        initial_command.get("host_jitter_ns"), name="initial host_jitter_ns"
    )
    if initial_host_after - initial_host_before != initial_host_jitter or not (
        0 <= initial_host_jitter <= probe.max_host_jitter_ns
    ):
        raise EvidenceInvalid("transport probe conditioning host bracket is invalid")

    acquisition = _required_mapping(report.get("acquisition"), name="acquisition")
    expected_acquisition_fields = {
        "threaded",
        "thread_name",
        "kernel_buffers",
        "queue_capacity_frames",
        "required_consumed_frames",
        "partial_batch_failure_contract",
        "worker_started",
        "produced_frames",
        "consumed_frames",
        "discarded_tail_frames",
        "single_core_batch_initiated",
        "initiating_batch_refill_calls",
        "public_refill_calls",
        "cached_replay_refill_calls",
        "batch_cache_fully_replayed",
        "initiating_refill_completion_monotonic_ns",
        "worker_in_flight_at_command",
        "worker_in_flight_before_shutdown",
        "cancel_required",
        "cancel_called",
        "cancel_succeeded",
        "shutdown_path",
        "worker_stopped_before_buffer_close",
        "buffer_close_completed",
        "metadata_abi",
        "configured_batch_frames",
        "configured_batch_cache_bytes",
        "batch_cache_attested",
        "post_open_baseline_raw",
        "prebind_unbound_command",
        "prebind_raw_counter_schedule",
    }
    if set(acquisition) != expected_acquisition_fields:
        raise EvidenceInvalid("transport probe acquisition fields changed")
    produced = _required_int(acquisition.get("produced_frames"), name="produced_frames")
    consumed = _required_int(acquisition.get("consumed_frames"), name="consumed_frames")
    discarded = _required_int(
        acquisition.get("discarded_tail_frames"), name="discarded_tail_frames"
    )
    post_open_raw = _required_int(
        acquisition.get("post_open_baseline_raw"), name="post_open_baseline_raw"
    )
    initiating_refill_completion_ns = _required_int(
        acquisition.get("initiating_refill_completion_monotonic_ns"),
        name="initiating_refill_completion_monotonic_ns",
    )
    frame_zero_refill_completion_ns = _required_int(
        _required_mapping(frames[0], name="frame zero").get("refill_monotonic_ns"),
        name="frame zero refill_monotonic_ns",
    )
    _validate_batch_host_chronology(
        initial_host_after_ns=initial_host_after,
        command_host_before_ns=command.host_before_ns,
        command_host_after_ns=command.host_after_ns,
        initiating_refill_completion_ns=initiating_refill_completion_ns,
    )
    command_bracket = _required_mapping(
        _required_mapping(
            report.get("command_contention"), name="command_contention"
        ).get("command"),
        name="command_contention.command",
    ).get("sample_counter_bracket")
    unbound_command = _required_mapping(
        acquisition.get("prebind_unbound_command"),
        name="prebind unbound command",
    )
    raw_schedule = _required_mapping(
        acquisition.get("prebind_raw_counter_schedule"),
        name="prebind raw counter schedule",
    )
    bound_command = _required_mapping(
        _required_mapping(
            report.get("command_contention"), name="command_contention"
        ).get("command"),
        name="command_contention.command",
    )
    expected_unbound_fields = {
        "command_id",
        "requested_level_db",
        "applied_level_db",
        "host_before_ns",
        "host_after_ns",
        "host_jitter_ns",
        "sample_sequence_before",
        "sample_sequence_after",
        "sample_uncertainty",
        "effective_attenuation_db",
    }
    bound_fields = expected_unbound_fields - {
        "sample_sequence_before",
        "sample_sequence_after",
        "sample_uncertainty",
    }
    if (
        acquisition.get("threaded") is not True
        or acquisition.get("worker_started") is not True
        or acquisition.get("thread_name") != PROBE_THREAD_NAME
        or acquisition.get("kernel_buffers") != probe.kernel_buffers
        or acquisition.get("metadata_abi") != 2
        or acquisition.get("configured_batch_frames") != probe.batch_frames
        or acquisition.get("configured_batch_cache_bytes")
        != probe.core_batch_cache_bytes
        or acquisition.get("batch_cache_attested") is not True
        or not 0 <= post_open_raw < 1 << 32
        or not isinstance(command_bracket, Mapping)
        or command_bracket.get("post_open_baseline_raw") != post_open_raw
        or set(unbound_command) != expected_unbound_fields
        or unbound_command.get("sample_sequence_before") is not None
        or unbound_command.get("sample_sequence_after") is not None
        or unbound_command.get("sample_uncertainty") is not None
        or any(
            unbound_command.get(field) != bound_command.get(field)
            for field in bound_fields
        )
        or set(raw_schedule) != _PROBE_RAW_SCHEDULE_FIELDS
        or any(
            raw_schedule.get(field) != command_bracket.get(field)
            for field in _PROBE_RAW_SCHEDULE_FIELDS
        )
        or acquisition.get("queue_capacity_frames") != _PROBE_QUEUE_FRAMES
        or acquisition.get("required_consumed_frames") != probe.retained_frames
        or produced != probe.batch_frames
        or consumed != probe.batch_frames
        or discarded != 0
        or acquisition.get("single_core_batch_initiated") is not True
        or acquisition.get("initiating_batch_refill_calls") != 1
        or acquisition.get("public_refill_calls") != probe.batch_frames
        or acquisition.get("cached_replay_refill_calls") != probe.batch_frames - 1
        or acquisition.get("batch_cache_fully_replayed") is not True
        or initiating_refill_completion_ns != frame_zero_refill_completion_ns
        or acquisition.get("worker_in_flight_at_command") is not True
        or acquisition.get("worker_in_flight_before_shutdown") is not False
        or acquisition.get("cancel_required") is not False
        or acquisition.get("cancel_called") is not False
        or acquisition.get("cancel_succeeded") is not None
        or acquisition.get("shutdown_path")
        != "normal_close_after_full_cache_replay"
        or acquisition.get("worker_stopped_before_buffer_close") is not True
        or acquisition.get("buffer_close_completed") is not True
        or acquisition.get("partial_batch_failure_contract")
        != (
            "initiating refill fails after core cache free/poison/core cancel; future "
            "refill is EBADF; explicit cleanup cancel is idempotent and precedes "
            "join/close; a fresh session may recover"
        )
    ):
        raise EvidenceInvalid("transport probe acquisition ledger is invalid")
    if report.get("tandem_status_before") != _json_domain(normalized_status_after):
        raise EvidenceInvalid(
            "transport probe initial status differs from FIFO normalization"
        )
    _validate_report_unowned_idle_status(
        report.get("tandem_status_before"),
        name="pre-session status",
        require_empty_fifo=True,
    )
    _safe_completed_weak_session_status(
        _required_mapping(
            report.get("tandem_status_after"), name="post-session status"
        ),
        label="post-session status",
    )
    final_rx = _required_mapping(report.get("final_rx_state"), name="final_rx_state")
    if final_rx.get("modes") != ["manual", "manual"]:
        raise EvidenceInvalid("transport probe final RX mode is not manual")
    gains = _required_list(final_rx.get("gains_db"), name="final RX gains")
    if len(gains) != 2 or any(
        abs(_required_number(value, name="final RX gain") - quality.manual_gain_db)
        > 0.1
        for value in gains
    ):
        raise EvidenceInvalid("transport probe final RX gains are invalid")
    expected_cadence = _refill_cadence(frames, quality.sample_rate_hz)
    if report.get("refill_cadence") != _json_domain(expected_cadence):
        raise EvidenceInvalid("transport probe refill cadence ledger changed")
    if require_cleanup:
        _validate_cleanup_evidence(report.get("cleanup"))


def validate_transient_transport_probe_report(
    report: Mapping[str, Any],
    quality: TandemQualityOptions,
    *,
    probe: TransientTransportProbeOptions = _DEFAULT_PROBE_OPTIONS,
    require_cleanup: bool = False,
) -> None:
    """Independently recheck a probe artifact in its serialized JSON domain."""

    validate_transient_transport_probe_options(quality, probe)
    try:
        _validate_transient_transport_probe_report_impl(
            _json_domain(report), quality, probe, require_cleanup=require_cleanup
        )
    except (EvidenceInvalid, FixtureSafetyError):
        raise
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise EvidenceInvalid(
            "transport probe report is malformed: " + _exception_text(error)
        ) from error


def run_transient_transport_probe(
    radio: Issue46Radio | TransientRadioTransport,
    quality: TandemQualityOptions,
    *,
    probe: TransientTransportProbeOptions = _DEFAULT_PROBE_OPTIONS,
    clock_ns: Callable[[], int] = time.monotonic_ns,
    monotonic: Callable[[], float] = time.monotonic,
    wall_clock_ns: Callable[[], int] = time.time_ns,
    sleep: Callable[[float], None] = time.sleep,
    metadata_parser: Callable[
        [bytes], TandemFrameMetadata
    ] = parse_tandem_frame_metadata,
    report_writer: Callable[[Path, Mapping[str, Any]], None] = _atomic_json,
    runtime_provenance: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], Path]:
    """Run the weak-only transport qualification and preserve a durable artifact."""

    validate_transient_transport_probe_options(quality, probe)
    if runtime_provenance is None:
        iio_module = getattr(radio, "iio", None)
        if iio_module is None:
            raise EvidenceInvalid(
                "transport probe lacks an IIO module for runtime attestation"
            )
        runtime_provenance = _attest_runtime_provenance(iio_module)
    attested_runtime = _validate_runtime_provenance(runtime_provenance)
    _validate_probe_radio_options(radio.options, quality, probe)
    _validate_probe_identity(
        radio.identity, runtime_provenance=attested_runtime
    )

    center_frequency = {
        key: int(value) for key, value in radio.read_center_frequency().items()
    }
    expected_frequency = quality.center_frequency_hz
    if set(center_frequency) != {"rx_lo_hz", "tx_lo_hz"} or any(
        abs(value - expected_frequency) > 2 for value in center_frequency.values()
    ):
        raise EvidenceInvalid(
            "live RX/TX LO differs from transport-probe configuration"
        )

    serial = str(radio.options.serial)
    if str(radio.identity.get("serial", "")) != serial:
        raise EvidenceInvalid(
            "transport probe radio identity differs from authorization"
        )
    report_path = (
        quality.output_dir / serial / "tandem-agc-transient-transport-probe.json"
    )
    if report_path.exists():
        raise EvidenceInvalid(
            f"transport probe refuses to overwrite existing artifact: {report_path}"
        )
    radio._report_path = report_path
    started = monotonic()

    def check_deadline() -> None:
        if monotonic() - started >= quality.max_seconds:
            raise TimeoutError(
                "tandem transient transport probe exceeded "
                f"{quality.max_seconds:.1f} seconds"
            )

    report: dict[str, Any] = {
        "schema": PROBE_SCHEMA,
        "started_unix_ns": wall_clock_ns(),
        "identity": dict(radio.identity),
        "runtime_provenance": attested_runtime,
        "release_pass_eligible": False,
        "qualification_scope": _qualification_scope(),
        "rf": {
            "center_frequency_hz_requested": expected_frequency,
            "center_frequency_hz_readback": center_frequency,
            "sample_rate_hz": quality.sample_rate_hz,
            "tone_hz": quality.tone_hz,
            "dds_scale": quality.dds_scale,
            "weak_tx2_gain_db": probe.weak_stimulus_tx_gain_db,
        },
        "configuration": {
            "quality": _quality_configuration(quality),
            "probe": asdict(probe),
        },
        "safety": _safety_policy(quality, probe),
        "evidence_policy": _evidence_policy(probe),
        "capacity_policy": _capacity_policy(quality, probe),
        "memory_policy": _report_memory_policy(probe),
        "acquisition": {
            "threaded": True,
            "thread_name": PROBE_THREAD_NAME,
            "kernel_buffers": probe.kernel_buffers,
            "queue_capacity_frames": _PROBE_QUEUE_FRAMES,
            "required_consumed_frames": probe.retained_frames,
            "partial_batch_failure_contract": (
                "initiating refill fails after core cache free/poison/core cancel; "
                "future refill is EBADF; explicit cleanup cancel is idempotent and "
                "precedes join/close; a fresh session may recover"
            ),
            "worker_started": False,
            "produced_frames": 0,
            "consumed_frames": 0,
            "discarded_tail_frames": 0,
            "single_core_batch_initiated": False,
            "initiating_batch_refill_calls": 0,
            "public_refill_calls": 0,
            "cached_replay_refill_calls": 0,
            "batch_cache_fully_replayed": False,
            "initiating_refill_completion_monotonic_ns": None,
            "prebind_unbound_command": None,
            "prebind_raw_counter_schedule": None,
            "worker_in_flight_at_command": False,
            "worker_in_flight_before_shutdown": False,
            "cancel_required": False,
            "cancel_called": False,
            "cancel_succeeded": None,
            "shutdown_path": "pending",
            "worker_stopped_before_buffer_close": False,
            "buffer_close_completed": False,
        },
        "frames": [],
        "iq_artifacts_saved": False,
        "cleanup": {
            "verified": False,
            "status": "pending_radio_lifecycle_close",
            "owner": "Issue46Radio.close",
        },
        "verdict": "running",
    }

    initial_report_error: BaseException | None = None
    try:
        report_writer(report_path, report)
    except BaseException as error:  # noqa: BLE001
        initial_report_error = error

    retained: list[_DeferredFrame] = []
    campaign_error: BaseException | None = initial_report_error
    if campaign_error is None:
        try:
            _run_probe_body(
                radio,
                quality,
                probe,
                report,
                retained,
                check_deadline=check_deadline,
                clock_ns=clock_ns,
                monotonic=monotonic,
                sleep=sleep,
                metadata_parser=metadata_parser,
            )
        except BaseException as error:  # noqa: BLE001
            campaign_error = error

    materialize_error: BaseException | None = None
    try:
        report["frames"] = _materialize_frames(retained)
        _bind_anchor_artifact(report, retained, probe)
        if len(retained) == probe.retained_frames:
            report["weak_signal_quality"] = _materialize_weak_signal_quality(
                retained, quality=quality, probe=probe
            )
        if len(report["frames"]) >= 2:
            report["refill_cadence"] = _refill_cadence(
                report["frames"], quality.sample_rate_hz
            )
    except BaseException as error:  # noqa: BLE001
        materialize_error = error

    final_mute_error: BaseException | None = None
    try:
        radio.mute_all()
    except BaseException as error:  # noqa: BLE001
        final_mute_error = error

    pre_report_errors = [
        error
        for error in (campaign_error, materialize_error, final_mute_error)
        if error is not None
    ]
    if not pre_report_errors:
        report["verdict"] = PROBE_PENDING_VERDICT
        try:
            validate_transient_transport_probe_report(
                report, quality, probe=probe, require_cleanup=False
            )
        except BaseException as error:  # noqa: BLE001
            pre_report_errors.append(error)
    if pre_report_errors:
        report["verdict"] = "invalid"
        report["fatal_error"] = _durable_exception_text(
            pre_report_errors[0]
            if len(pre_report_errors) == 1
            else BaseExceptionGroup("transport probe failures", pre_report_errors)
        )
    report["elapsed_seconds"] = monotonic() - started
    report["completed_unix_ns"] = wall_clock_ns()

    report_error: BaseException | None = None
    try:
        report_writer(report_path, report)
    except BaseException as error:  # noqa: BLE001
        report_error = error

    errors = [*pre_report_errors, *([report_error] if report_error is not None else [])]
    if len(errors) > 1:
        raise BaseExceptionGroup(
            "transport probe or its fail-closed exit handling failed", errors
        )
    if errors:
        error = errors[0]
        raise error.with_traceback(error.__traceback__)
    return report, report_path


def run_serial_transient_transport_probe(
    iio_module: Any,
    radio_options: Any,
    quality: TandemQualityOptions,
    *,
    probe: TransientTransportProbeOptions = _DEFAULT_PROBE_OPTIONS,
    radio_factory: Callable[[Any, Any], Issue46Radio] = Issue46Radio,
    clock_ns: Callable[[], int] = time.monotonic_ns,
    monotonic: Callable[[], float] = time.monotonic,
    wall_clock_ns: Callable[[], int] = time.time_ns,
    sleep: Callable[[float], None] = time.sleep,
    metadata_parser: Callable[
        [bytes], TandemFrameMetadata
    ] = parse_tandem_frame_metadata,
    report_writer: Callable[[Path, Mapping[str, Any]], None] = _atomic_json,
    runtime_provenance: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], Path]:
    """Own one radio and require durable close-time cleanup evidence."""

    validate_transient_transport_probe_options(quality, probe)
    if runtime_provenance is None:
        runtime_provenance = _attest_runtime_provenance(iio_module)
    attested_runtime = _validate_runtime_provenance(runtime_provenance)
    _validate_probe_radio_options(radio_options, quality, probe)
    report_path = (
        quality.output_dir
        / PROBE_EXACT_SERIAL
        / "tandem-agc-transient-transport-probe.json"
    )
    if report_path.exists():
        raise EvidenceInvalid(
            f"transport probe refuses to overwrite existing artifact: {report_path}"
        )
    radio = radio_factory(iio_module, radio_options)
    body_error: BaseException | None = None
    result: tuple[dict[str, Any], Path] | None = None
    try:
        result = run_transient_transport_probe(
            radio,
            quality,
            probe=probe,
            clock_ns=clock_ns,
            monotonic=monotonic,
            wall_clock_ns=wall_clock_ns,
            sleep=sleep,
            metadata_parser=metadata_parser,
            report_writer=report_writer,
            runtime_provenance=attested_runtime,
        )
    except BaseException as error:  # noqa: BLE001
        body_error = error

    close_error: BaseException | None = None
    try:
        radio.close()
    except BaseException as error:  # noqa: BLE001
        close_error = FixtureSafetyError(
            "radio close failed after transport probe: " + _exception_text(error)
        )

    report_path_value = (
        result[1] if result is not None else getattr(radio, "_report_path", None)
    )
    report_path = Path(report_path_value) if report_path_value is not None else None
    close_invalidation_error: BaseException | None = None
    if close_error is not None and report_path is not None and report_path.is_file():
        try:
            parsed_failure = json.loads(report_path.read_text(encoding="utf-8"))
            if not isinstance(parsed_failure, dict):
                raise EvidenceInvalid(
                    "close-failed transport-probe report is not a JSON object"
                )
            parsed_failure["verdict"] = "invalid"
            parsed_failure["release_pass_eligible"] = False
            parsed_failure["fatal_error"] = _durable_exception_text(close_error)
            prior_cleanup = parsed_failure.get("cleanup")
            cleanup_failure = (
                dict(prior_cleanup) if isinstance(prior_cleanup, Mapping) else {}
            )
            failures = cleanup_failure.get("failures")
            cleanup_failure["failures"] = [
                *(failures if isinstance(failures, list) else []),
                _exception_text(close_error),
            ]
            cleanup_failure["verified"] = False
            parsed_failure["cleanup"] = cleanup_failure
            report_writer(report_path, parsed_failure)
        except BaseException as error:  # noqa: BLE001
            close_invalidation_error = error
    durable_report: dict[str, Any] | None = None
    durable_error: BaseException | None = None
    if close_error is None and body_error is None:
        try:
            if not bool(getattr(radio, "cleanup_verified", False)):
                raise FixtureSafetyError(
                    "radio close did not verify final transport-probe cleanup"
                )
            if report_path is None or not report_path.is_file():
                raise EvidenceInvalid("post-close transport-probe report is missing")
            if report_path.with_suffix(report_path.suffix + ".tmp").exists():
                raise EvidenceInvalid("transport-probe atomic report temp remains")
            parsed = json.loads(report_path.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict):
                raise EvidenceInvalid(
                    "post-close transport-probe report is not an object"
                )
            _validate_cleanup_evidence(parsed.get("cleanup"))
            if parsed.get("schema") != PROBE_SCHEMA:
                raise EvidenceInvalid("durable transport-probe schema changed")
            if parsed.get("verdict") != PROBE_PENDING_VERDICT:
                raise EvidenceInvalid(
                    "durable transport probe lacks its pending-cleanup verdict"
                )
            if parsed.get("release_pass_eligible") is not False:
                raise EvidenceInvalid(
                    "transport probe was mislabelled release eligible"
                )
            if parsed.get("identity") != _json_domain(dict(radio.identity)):
                raise EvidenceInvalid("durable transport-probe identity changed")
            parsed["verdict"] = PROBE_VERDICT
            validate_transient_transport_probe_report(
                parsed, quality, probe=probe, require_cleanup=True
            )
            report_writer(report_path, parsed)
            if report_path.with_suffix(report_path.suffix + ".tmp").exists():
                raise EvidenceInvalid(
                    "transport-probe promotion left an atomic report temp"
                )
            promoted = json.loads(report_path.read_text(encoding="utf-8"))
            if not isinstance(promoted, dict):
                raise EvidenceInvalid(
                    "promoted transport-probe report is not a JSON object"
                )
            if promoted.get("identity") != _json_domain(dict(radio.identity)):
                raise EvidenceInvalid("promoted transport-probe identity changed")
            validate_transient_transport_probe_report(
                promoted, quality, probe=probe, require_cleanup=True
            )
            durable_report = promoted
        except BaseException as error:  # noqa: BLE001
            durable_error = error

    errors = [
        error
        for error in (
            body_error,
            close_error,
            close_invalidation_error,
            durable_error,
        )
        if error is not None
    ]
    if len(errors) > 1:
        raise BaseExceptionGroup(
            "transport probe, radio close, or durable cleanup proof failed", errors
        )
    if errors:
        error = errors[0]
        raise error.with_traceback(error.__traceback__)
    assert result is not None
    assert report_path is not None
    assert durable_report is not None
    return durable_report, report_path


__all__ = [
    "PROBE_PENDING_VERDICT",
    "PROBE_SCHEMA",
    "PROBE_VERDICT",
    "TransientTransportProbeOptions",
    "run_serial_transient_transport_probe",
    "run_transient_transport_probe",
    "validate_transient_transport_probe_options",
    "validate_transient_transport_probe_report",
]
