"""Safety-gated manual/native/tandem AGC quality matrix on the TX2 fixture."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any, Optional

from .experiment import (
    MAX_COMMON_CENTER_FREQUENCY_HZ,
    MIN_COMMON_CENTER_FREQUENCY_HZ,
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
MODE_TANDEM = "tandem_auto"
MODES = (MODE_MANUAL, MODE_NATIVE, MODE_TANDEM)
NATIVE_GAIN_CONTROL_MODES = ("slow_attack", "fast_attack", "hybrid")
DEFAULT_NATIVE_GAIN_CONTROL_MODES = ("slow_attack",)
MANUAL_TONE_TRACKING_TOLERANCE_DB = 3.0
MANUAL_TONE_RETRACE_TOLERANCE_DB = 3.0
NATIVE_MIN_GAIN_SPAN_DB = 1.0


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
    return f"{type(error).__name__}{suffix}: {error}"


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
    prior: Optional[_OrdinaryGainBand] = None,
) -> Optional[_OrdinaryGainBand]:
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


def _capture(
    radio: Issue46Radio,
    buffer: Any,
    *,
    options: TandemQualityOptions,
    metadata: bool,
) -> tuple[bytes, Optional[TandemFrameMetadata], dict[str, Any]]:
    raw, raw_metadata, refill_ns = radio.capture_iq(
        buffer,
        metadata=metadata,
        samples_per_channel=options.samples_per_channel,
    )
    parsed = (
        parse_tandem_frame_metadata(raw_metadata) if raw_metadata is not None else None
    )
    if parsed is not None:
        if parsed.samples_per_channel != options.samples_per_channel:
            raise EvidenceInvalid("tandem metadata sample count differs from IQ")
        if parsed.iq_payload_bytes != len(raw):
            raise EvidenceInvalid("tandem metadata IQ byte count differs from payload")
        if parsed.enabled_scan_mask != 0x0F or parsed.channel_count != 2:
            raise EvidenceInvalid("tandem metadata does not describe dual complex RX")
        unsafe_flags = parsed.flags & TANDEM_UNSAFE_FLAGS
        if unsafe_flags:
            raise EvidenceInvalid(
                f"tandem metadata reports unsafe flags 0x{unsafe_flags:08x}"
            )
        if parsed.observation_overflow_count or parsed.event_overflow_count:
            raise EvidenceInvalid("tandem metadata record capacity overflowed")
        expected_gain_table = expected_tandem_gain_table(options.center_frequency_hz)
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
            raise EvidenceInvalid("tandem metadata differs from requested gain range")
        if parsed.ad9361_temperature_mdeg_c is not None and not (
            -40_000 <= parsed.ad9361_temperature_mdeg_c <= 125_000
        ):
            raise EvidenceInvalid("AD9361 temperature is outside its physical range")
    frame = {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "iq_bytes": len(raw),
        "refill_monotonic_ns": refill_ns,
    }
    if parsed is not None:
        frame["metadata"] = _metadata_dict(parsed)
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
    stable_band: Optional[_OrdinaryGainBand] = None
    deadline = time.monotonic() + options.settle_timeout_seconds
    minimum_drain = options.kernel_buffers + 1
    for attempt in range(1, options.max_settle_frames + 1):
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
    trace: list[dict[str, Any]] = []
    stable = 0
    previous: Optional[TandemFrameMetadata] = None
    ownership_epoch: Optional[int] = None
    deadline = time.monotonic() + options.settle_timeout_seconds
    minimum_drain = options.kernel_buffers + 1
    for attempt in range(1, options.max_settle_frames + 1):
        _raw, parsed, frame = _capture(radio, buffer, options=options, metadata=True)
        assert parsed is not None
        if ownership_epoch is None:
            ownership_epoch = parsed.ownership_epoch
        if parsed.ownership_epoch != ownership_epoch:
            raise EvidenceInvalid("tandem ownership epoch changed inside one session")
        is_stable = bool(
            parsed.tandem_state is TandemState.ARMED_AUTO
            and not parsed.gain_events
            and parsed.rx1_gain_index == parsed.rx2_gain_index
            and (
                previous is None
                or parsed.tandem_transition_count == previous.tandem_transition_count
            )
            and (
                previous is None
                or parsed.bench_gain_indices == previous.bench_gain_indices
            )
        )
        stable = stable + 1 if attempt > minimum_drain and is_stable else 0
        trace.append({"attempt": attempt, "stable_run": stable, **frame})
        previous = parsed
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
        before = radio.read_rx_state()
        raw, _metadata, frame = _capture(radio, buffer, options=options, metadata=False)
        after = radio.read_rx_state()
        extended = _extend_gain_band(
            (before, after), expected_mode=expected_mode, prior=gain_band
        )
        if extended is None:
            raise EvidenceInvalid(
                f"{mode} gain left its settled band during a measurement frame"
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
                thresholds=options.thresholds,
            )
        )
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
    measurements: list[dict[str, Any]] = []
    previous = settled
    for frame_index in range(options.measurement_frames):
        raw, parsed, frame = _capture(radio, buffer, options=options, metadata=True)
        assert parsed is not None
        if parsed.tandem_state is not TandemState.ARMED_AUTO:
            raise EvidenceInvalid("tandem left AUTO during a measurement frame")
        if parsed.ownership_epoch != previous.ownership_epoch:
            raise EvidenceInvalid("tandem ownership changed during measurement")
        if parsed.gain_events:
            raise EvidenceInvalid("tandem changed gain during a measurement frame")
        if parsed.tandem_transition_count != previous.tandem_transition_count:
            raise EvidenceInvalid("tandem transition count changed without an event")
        if parsed.bench_gain_indices != previous.bench_gain_indices:
            raise EvidenceInvalid("tandem endpoint gain changed without an event")
        frame["quality"] = dict(
            analyze_common_tone(
                raw,
                sample_rate_hz=options.sample_rate_hz,
                expected_tone_hz=options.tone_hz,
                thresholds=options.thresholds,
            )
        )
        if options.save_iq:
            path = (
                output_dir / f"{MODE_TANDEM}-level{level_index}-frame{frame_index}.cs16"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            frame["iq_path"] = str(path)
        measurements.append(frame)
        previous = parsed
    return measurements


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


def _run_mode(
    radio: Issue46Radio,
    *,
    mode: str,
    options: TandemQualityOptions,
    report: dict[str, Any],
    report_path: Path,
    check_deadline: Callable[[], None],
) -> None:
    radio.mute_all()
    before = _wait_for_idle(radio)
    radio.configure_rx("manual", manual_gain_db=options.manual_gain_db)
    radio.arm_tx2_tone(tone_hz=options.tone_hz, scale=options.dds_scale)

    metadata = mode == MODE_TANDEM
    request: Optional[bytes] = None
    native_iio_mode = native_gain_control_mode(mode)
    if native_iio_mode is not None:
        radio.configure_rx(native_iio_mode)
    elif mode == MODE_TANDEM:
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
    elif mode != MODE_MANUAL:
        raise ValueError(f"unknown quality mode {mode!r}")

    first_readback = radio.set_tx2_gain(options.tx_gain_trajectory_db[0])
    mode_record: dict[str, Any] = {
        "mode": mode,
        "tandem_status_before": before,
        "initial_tx2_readback_db": first_readback,
        "cells": [],
    }
    report["modes"].append(mode_record)
    _atomic_json(report_path, report)
    try:
        with radio.buffer(
            "metadata" if metadata else "ordinary",
            options.kernel_buffers,
            options.samples_per_channel,
            tandem_request=request,
        ) as (buffer, metadata_abi):
            mode_record["metadata_abi"] = metadata_abi
            if metadata:
                check_deadline()
                priming_gain_db, distinct_levels = _select_tandem_priming_gain(
                    options.tx_gain_trajectory_db
                )
                if not TX_MUTE_DB <= priming_gain_db <= options.strongest_tx_gain_db:
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
                    frame["metadata"] for frame in priming_trace if "metadata" in frame
                ]
                priming_events = [
                    event
                    for frame_metadata in priming_metadata
                    for event in frame_metadata["gain_events"]
                ]
                priming_reached_max = bool(
                    priming_settled.rx1_gain_index == priming_settled.maximum_gain_index
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
                        "final_gain_indices": list(priming_settled.bench_gain_indices),
                        "maximum_gain_index": priming_settled.maximum_gain_index,
                        "reached_maximum_gain": priming_reached_max,
                    },
                    "final_metadata": _metadata_dict(priming_settled),
                }
                _atomic_json(report_path, report)
            for index, tx_gain_db in enumerate(options.tx_gain_trajectory_db):
                check_deadline()
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
                    settle_trace, settled = _settle_tandem(
                        radio, buffer, options=options
                    )
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
                cell["settling"] = {
                    "frames": len(settle_trace),
                    "trace": settle_trace,
                }
                if not metadata:
                    cell["settling"]["settled_gain_band"] = settled_gain_band.to_dict()
                cell["measurements"] = measurements
                cell["summary"] = summarize_measurements(measurements)
                mode_record["cells"].append(cell)
                _atomic_json(report_path, report)
    finally:
        radio.mute_all()
    after = _wait_for_idle(radio)
    mode_record["tandem_status_after"] = after
    radio.configure_rx("manual", manual_gain_db=options.manual_gain_db)
    _atomic_json(report_path, report)


def _mode_cells(report: Mapping[str, Any], mode: str) -> list[Mapping[str, Any]]:
    matches = [item for item in report["modes"] if item["mode"] == mode]
    if len(matches) != 1:
        raise EvidenceInvalid(f"report contains {len(matches)} records for {mode}")
    return list(matches[0]["cells"])


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
        frames = [
            frame["metadata"]
            for section in (cell["settling"]["trace"], cell["measurements"])
            for frame in section
        ]
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
                        evidence_source = "gap_accounted_endpoint"
                    else:
                        raise EvidenceInvalid(
                            f"tandem {direction} TX step lacks a matching visible "
                            "event or a gap-accounted hidden transition"
                        )
                    direction_proven = True
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
        for section in (cell["settling"]["trace"], cell["measurements"]):
            for frame in section:
                metadata = frame.get("metadata")
                if not isinstance(metadata, Mapping):
                    raise EvidenceInvalid(
                        "tandem capture lacks frame-associated metadata"
                    )
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
        report["verdict"] = "invalid"
        report["fatal_error"] = _exception_text(error)
        _atomic_json(report_path, report)
        raise
    finally:
        radio.mute_all()
        report["final_tandem_status"] = _wait_for_idle(radio)
        radio.configure_rx("manual", manual_gain_db=options.manual_gain_db)
        report["final_rx_state"] = radio.read_rx_state()
        report["elapsed_seconds"] = time.monotonic() - started
        report["completed_unix_ns"] = time.time_ns()
        _atomic_json(report_path, report)
    return report, report_path
