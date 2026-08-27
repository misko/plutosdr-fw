"""Guarded TX2-only modulated-signal hardware quality campaign.

This module deliberately treats a digitally summed desired signal and blocker as
one waveform.  It never assumes a second transmitter or an external generator:
TX1 is held at zero/muted while TX2 cyclic DMA drives the complete stimulus.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
from builtins import BaseExceptionGroup
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .experiment import (
    MAX_COMMON_CENTER_FREQUENCY_HZ,
    MIN_COMMON_CENTER_FREQUENCY_HZ,
    NATIVE_FAST_ENTRY_MANUAL_GAIN_DB,
    TX_MUTE_DB,
    EvidenceInvalid,
    FixtureSafetyError,
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
from .modulated_quality import (
    CompositeQpsk,
    EncodedCS16,
    ModulatedQualityThresholds,
    QpskReference,
    analyze_modulated_capture,
    build_composite_blocker,
    encode_tx2_cs16,
    generate_cyclic_qpsk,
    quantify_blocker_degradation,
    scale_reference_for_tx,
)

MODE_MANUAL = "manual_fixed"
MODE_NATIVE_SLOW = "native_slow_attack"
MODE_NATIVE_FAST = "native_fast_attack"
MODE_NATIVE_HYBRID = "native_hybrid"
MODE_TANDEM = "tandem_auto"
SUPPORTED_MODULATED_MODES = (
    MODE_MANUAL,
    MODE_NATIVE_SLOW,
    MODE_NATIVE_FAST,
    MODE_NATIVE_HYBRID,
    MODE_TANDEM,
)
RELEASE_MODULATED_MODES = (
    MODE_MANUAL,
    MODE_NATIVE_SLOW,
    MODE_NATIVE_FAST,
    MODE_TANDEM,
)
RELEASE_MODULATED_BINDING_MODES = (
    MODE_MANUAL,
    MODE_NATIVE_SLOW,
    MODE_TANDEM,
)
REPORT_ONLY_MODULATED_MODES = frozenset((MODE_NATIVE_FAST,))
# Backward-compatible name for callers that explicitly request every supported
# mode.  Execution and evaluation use ``ModulatedHardwareOptions.modes``.
MODULATED_MODES = SUPPORTED_MODULATED_MODES

DEFAULT_MODULATED_TX2_GAIN_DB = -42.0
TX2_GAIN_READBACK_TOLERANCE_DB = 0.01
MAX_DIAGNOSTIC_IQ_ARTIFACT_BYTES = 64 * 1024

_DIAGNOSTIC_IQ_TARGETS = {
    "desired_only": (
        "desired_baseline",
        "desired-only-manual-fixed-frame-0000-rx0-rx1.cs16le",
    ),
    "blocker_00": (
        "first_blocker",
        "blocker-00-manual-fixed-frame-0000-rx0-rx1.cs16le",
    ),
}

_NATIVE_IIO_MODES = {
    MODE_NATIVE_SLOW: "slow_attack",
    MODE_NATIVE_FAST: "fast_attack",
    MODE_NATIVE_HYBRID: "hybrid",
}


def modulated_mode_evidence_policy() -> dict[str, Any]:
    """Return the durable claim boundary for release and exploratory modes."""

    return {
        "release_default_modes": list(RELEASE_MODULATED_MODES),
        "release_binding_modes": list(RELEASE_MODULATED_BINDING_MODES),
        "native_fast_attack": {
            "classification": "report_only",
            "autonomous_agc_claim": True,
            "release_qualification_claim": False,
            "result_reporting": "observed_pass_fail",
            "evidence_completeness_binding": True,
            "identity_safety_cleanup_binding": True,
            "reason": (
                "independent AD9361 native-fast loops exhibit intermittent "
                "blocker-sensitive lock-state variability across radios and "
                "receive channels"
            ),
        },
        "native_hybrid": {
            "classification": "exploratory_quality_only",
            "autonomous_agc_claim": False,
            "release_qualification_claim": False,
            "ctrl_in2_guarded": False,
            "reason": (
                "hybrid re-arms the external CTRL_IN2 path, whose idle level is "
                "not driven or attested by this fixture"
            ),
        },
    }


@dataclass(frozen=True)
class BlockerPoint:
    """One deterministic in-band composite-blocker condition."""

    offset_hz: float
    power_db: float
    seed: int = 47


@dataclass(frozen=True)
class ModulatedDegradationThresholds:
    """Maximum quality change relative to each mode's desired-only baseline."""

    max_evm_increase_percentage_points: float = 12.0
    max_mer_loss_db: float = 8.0
    max_ser_increase: float = 0.01
    max_ber_increase: float = 0.005
    max_desired_gain_loss_db: float = 3.0


@dataclass(frozen=True)
class ModulatedHardwareOptions:
    """All safety, waveform, capture, and oracle inputs for one campaign."""

    physical_attenuation_db: float
    # The Pluto AD9361 rejects the earlier 1.024-MS/s request with EINVAL in
    # this no-FIR release configuration.  Use the already-qualified 2.5-MS/s
    # clock and preserve the waveform's normalized geometry with eight
    # samples/symbol and the proportionally scaled blocker below.
    sample_rate_hz: int = 2_500_000
    center_frequency_hz: int = 915_000_000
    symbol_count: int = 256
    samples_per_symbol: int = 8
    rolloff: float = 0.25
    span_symbols: int = 10
    desired_seed: int = 46
    capture_samples: int = 8_192
    tx2_gain_db: float = DEFAULT_MODULATED_TX2_GAIN_DB
    tx_peak_fraction: float = 0.80
    tx_headroom_db: float = 1.0
    manual_gain_db: float = 40.0
    modes: tuple[str, ...] = RELEASE_MODULATED_MODES
    blocker_points: tuple[BlockerPoint, ...] = (
        BlockerPoint(offset_hz=390_625.0, power_db=-20.0, seed=47),
    )
    kernel_buffers: int = 16
    stable_frames: int = 3
    measurement_frames: int = 3
    max_settle_frames: int = 64
    settle_timeout_seconds: float = 3.0
    max_seconds: float = 180.0
    cfo_search_hz: float = 8_000.0
    output_dir: Path = Path("build/radio-hardware/modulated-quality")
    tandem_low_power_threshold: int = 20
    tandem_large_lmt_overload_threshold: int = 58
    tandem_large_adc_overload_threshold: int = 35
    tandem_small_adc_overload_threshold: int = 34
    tandem_power_measurement_samples: int = 1_024
    tandem_low_power_dwell_periods: int = 3
    tandem_cooldown_periods: int = 16
    quality_thresholds: ModulatedQualityThresholds = field(
        default_factory=ModulatedQualityThresholds
    )
    degradation_thresholds: ModulatedDegradationThresholds = field(
        default_factory=ModulatedDegradationThresholds
    )

    @property
    def minimum_effective_attenuation_db(self) -> float:
        return self.physical_attenuation_db - self.tx2_gain_db


@dataclass(frozen=True)
class _WaveformCase:
    case_id: str
    kind: str
    composite: CompositeQpsk
    encoded: EncodedCS16
    blocker_seed: int | None


@dataclass
class _TandemContinuity:
    """State needed to reconcile returned frames and provider-accounted gaps."""

    previous: TandemFrameMetadata | None = None
    last_event_sequence: int | None = None
    last_event_sample_sequence: int | None = None
    last_event_gain_index: int | None = None
    unrepresented_since_event: int = 0
    missing_frame_count: int = 0
    hidden_transition_count: int = 0
    event_sequence_hole_count: int = 0
    last_frame_evidence: dict[str, Any] = field(default_factory=dict)


_UINT32_MODULUS = 1 << 32


def _forward_u32_delta(current: int, previous: int, *, context: str) -> int:
    delta = (current - previous) % _UINT32_MODULUS
    if delta >= _UINT32_MODULUS // 2:
        raise EvidenceInvalid(f"{context} regressed ambiguously")
    return delta


def _gain_endpoint_is_reachable(
    start: int,
    end: int,
    transitions: int,
    *,
    minimum: int,
    maximum: int,
) -> bool:
    """Return whether exact paired +/-1 steps can join two known endpoints."""

    if not minimum <= start <= maximum or not minimum <= end <= maximum:
        return False
    distance = abs(end - start)
    return distance <= transitions and (transitions - distance) % 2 == 0


def _finite(name: str, value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{name} must be finite")
    return parsed


def _positive_integer(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _expected_gain_table(center_frequency_hz: int) -> TandemGainTable:
    if isinstance(center_frequency_hz, bool) or not isinstance(
        center_frequency_hz, int
    ):
        raise TypeError("center_frequency_hz must be an integer")
    if not (
        MIN_COMMON_CENTER_FREQUENCY_HZ
        <= center_frequency_hz
        <= MAX_COMMON_CENTER_FREQUENCY_HZ
    ):
        raise ValueError("center_frequency_hz is outside the common AD9361 range")
    if center_frequency_hz <= 1_300_000_000:
        return TandemGainTable.MHZ_200_1300
    if center_frequency_hz <= 4_000_000_000:
        return TandemGainTable.MHZ_1300_4000
    return TandemGainTable.MHZ_4000_6000


def _validate_degradation_thresholds(
    thresholds: ModulatedDegradationThresholds,
) -> None:
    if not isinstance(thresholds, ModulatedDegradationThresholds):
        raise TypeError("degradation_thresholds has the wrong type")
    values = asdict(thresholds)
    for name, value in values.items():
        parsed = _finite(name, value)
        if parsed < 0.0:
            raise ValueError(f"{name} must be nonnegative")


def _prepare_waveforms(
    options: ModulatedHardwareOptions,
) -> tuple[QpskReference, tuple[_WaveformCase, ...]]:
    reference = generate_cyclic_qpsk(
        sample_rate_hz=options.sample_rate_hz,
        symbol_count=options.symbol_count,
        samples_per_symbol=options.samples_per_symbol,
        rolloff=options.rolloff,
        span_symbols=options.span_symbols,
        seed=options.desired_seed,
    )
    cases: list[_WaveformCase] = []
    desired = scale_reference_for_tx(reference, peak_fraction=options.tx_peak_fraction)
    cases.append(
        _WaveformCase(
            case_id="desired_only",
            kind="desired_only",
            composite=desired,
            encoded=encode_tx2_cs16(
                desired.tx_samples, headroom_db=options.tx_headroom_db
            ),
            blocker_seed=None,
        )
    )
    for index, point in enumerate(options.blocker_points):
        composite = build_composite_blocker(
            reference,
            blocker_offset_hz=point.offset_hz,
            blocker_power_db=point.power_db,
            blocker_seed=point.seed,
            peak_fraction=options.tx_peak_fraction,
        )
        cases.append(
            _WaveformCase(
                case_id=f"blocker_{index:02d}",
                kind="composite_blocker",
                composite=composite,
                encoded=encode_tx2_cs16(
                    composite.tx_samples, headroom_db=options.tx_headroom_db
                ),
                blocker_seed=point.seed,
            )
        )
    return reference, tuple(cases)


def validate_modulated_hardware_options(options: ModulatedHardwareOptions) -> None:
    """Fail before touching a radio if the campaign is unsafe or ambiguous."""

    if not isinstance(options, ModulatedHardwareOptions):
        raise TypeError("options must be ModulatedHardwareOptions")
    if not isinstance(options.output_dir, Path):
        raise TypeError("output_dir must be a pathlib.Path")
    if isinstance(options.modes, (str, bytes)) or not isinstance(options.modes, tuple):
        raise TypeError("modes must be a tuple of supported modulated modes")
    if not options.modes:
        raise ValueError("modes cannot be empty")
    if any(not isinstance(mode, str) for mode in options.modes):
        raise TypeError("modes must contain strings")
    if len(set(options.modes)) != len(options.modes):
        raise ValueError("modes cannot contain duplicates")
    unsupported_modes = tuple(
        mode for mode in options.modes if mode not in SUPPORTED_MODULATED_MODES
    )
    if unsupported_modes:
        raise ValueError(f"unsupported modulated modes: {unsupported_modes}")
    if MODE_MANUAL not in options.modes or MODE_TANDEM not in options.modes:
        raise ValueError("modes must include manual_fixed and tandem_auto anchors")
    _expected_gain_table(options.center_frequency_hz)
    if not isinstance(options.quality_thresholds, ModulatedQualityThresholds):
        raise TypeError("quality_thresholds has the wrong type")
    _positive_integer("sample_rate_hz", options.sample_rate_hz)
    if options.sample_rate_hz < 2_500_000:
        raise ValueError(
            "modulated hardware sample_rate_hz must be at least 2500000 "
            "for the release AD9361 no-FIR configuration"
        )
    _positive_integer("capture_samples", options.capture_samples)
    if options.capture_samples < 8_192:
        raise ValueError("capture_samples must satisfy the radio's 8192-sample floor")
    for name in (
        "symbol_count",
        "samples_per_symbol",
        "span_symbols",
        "kernel_buffers",
        "stable_frames",
        "measurement_frames",
        "max_settle_frames",
        "tandem_power_measurement_samples",
        "tandem_low_power_dwell_periods",
    ):
        _positive_integer(name, getattr(options, name))
    if (
        isinstance(options.tandem_cooldown_periods, bool)
        or not isinstance(options.tandem_cooldown_periods, int)
        or options.tandem_cooldown_periods < 0
    ):
        raise ValueError("tandem_cooldown_periods must be a nonnegative integer")
    for name in (
        "physical_attenuation_db",
        "tx2_gain_db",
        "tx_peak_fraction",
        "tx_headroom_db",
        "manual_gain_db",
        "rolloff",
        "settle_timeout_seconds",
        "max_seconds",
        "cfo_search_hz",
    ):
        _finite(name, getattr(options, name))
    if options.physical_attenuation_db < 0.0:
        raise ValueError("physical_attenuation_db cannot be negative")
    if not TX_MUTE_DB <= options.tx2_gain_db <= 0.0:
        raise ValueError("tx2_gain_db must be in [-89.75, 0] dB")
    if options.minimum_effective_attenuation_db < 30.0:
        raise ValueError("physical attenuation plus TX2 backoff must be at least 30 dB")
    if not 0.0 < options.tx_peak_fraction <= 1.0:
        raise ValueError("tx_peak_fraction must be in (0, 1]")
    if not 0.0 <= options.tx_headroom_db <= 60.0:
        raise ValueError("tx_headroom_db must be in [0, 60]")
    if not 0.0 <= options.manual_gain_db <= 62.0:
        raise ValueError("manual_gain_db must be in [0, 62]")
    if options.manual_gain_db != int(options.manual_gain_db):
        raise ValueError("manual_gain_db must be integral for tandem parity")
    if options.stable_frames < 2:
        raise ValueError("stable_frames must be at least two")
    minimum_settle = options.kernel_buffers + 1 + options.stable_frames
    if options.max_settle_frames < minimum_settle:
        raise ValueError(
            "max_settle_frames cannot drain queued buffers and prove stability"
        )
    if options.settle_timeout_seconds <= 0.0 or options.max_seconds <= 0.0:
        raise ValueError("campaign deadlines must be positive")
    if not 0.0 < options.cfo_search_hz < options.sample_rate_hz / 4.0:
        raise ValueError("cfo_search_hz must be positive and below Fs/4")
    if options.cfo_search_hz <= options.quality_thresholds.max_abs_cfo_hz:
        raise ValueError("cfo_search_hz must exceed the absolute CFO gate")
    absolute = options.quality_thresholds
    for name in ("max_evm_percent", "min_mer_db", "max_abs_cfo_hz"):
        _finite(name, getattr(absolute, name))
    if absolute.max_evm_percent <= 0.0 or absolute.max_abs_cfo_hz <= 0.0:
        raise ValueError("absolute EVM and CFO bounds must be positive")
    for name in (
        "max_ser",
        "max_ber",
        "max_clipping_fraction",
        "min_cross_channel_coherence",
        "min_blocker_correlation",
    ):
        value = _finite(name, getattr(absolute, name))
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0, 1]")
    for name in (
        "max_blocker_offset_error_hz",
        "max_blocker_power_error_db",
    ):
        if _finite(name, getattr(absolute, name)) < 0.0:
            raise ValueError(f"{name} must be nonnegative")
    if (
        isinstance(absolute.max_timing_disagreement_samples, bool)
        or not isinstance(absolute.max_timing_disagreement_samples, int)
        or absolute.max_timing_disagreement_samples < 0
    ):
        raise ValueError("timing disagreement gate must be a nonnegative integer")
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
        raise ValueError("tandem ADC thresholds must satisfy small <= large")
    if options.tandem_power_measurement_samples > (1 << 20) - 1:
        raise ValueError("tandem power-measurement samples exceed the ABI limit")
    if options.tandem_low_power_dwell_periods > 0xFF:
        raise ValueError("tandem low-power dwell exceeds the ABI limit")
    if options.tandem_cooldown_periods > 0xFF:
        raise ValueError("tandem cooldown exceeds the ABI limit")
    maximum_events = maximum_tandem_events_per_frame(
        mode=TandemMode.AUTO,
        samples_per_channel=options.capture_samples,
        power_measurement_samples=options.tandem_power_measurement_samples,
        cooldown_periods=options.tandem_cooldown_periods,
    )
    if maximum_events > 64:
        raise ValueError("tandem timing can exceed the metadata event capacity")
    _validate_degradation_thresholds(options.degradation_thresholds)
    if not options.blocker_points:
        raise ValueError("blocker_points must contain at least one composite blocker")
    keys: set[tuple[float, float]] = set()
    for point in options.blocker_points:
        if not isinstance(point, BlockerPoint):
            raise TypeError("blocker_points must contain BlockerPoint values")
        key = (
            _finite("blocker offset", point.offset_hz),
            _finite("blocker power", point.power_db),
        )
        if key in keys:
            raise ValueError("blocker_points contains a duplicate offset/power pair")
        keys.add(key)
        if (
            isinstance(point.seed, bool)
            or not isinstance(point.seed, int)
            or point.seed < 0
        ):
            raise ValueError("blocker seeds must be nonnegative integers")
    reference, cases = _prepare_waveforms(options)
    if options.capture_samples < 2 * reference.cycle_samples:
        raise ValueError("capture_samples must contain at least two waveform cycles")
    if options.capture_samples % reference.cycle_samples:
        raise ValueError("capture_samples must be a whole number of waveform cycles")
    if options.capture_samples * 8 > MAX_DIAGNOSTIC_IQ_ARTIFACT_BYTES:
        raise ValueError("capture_samples exceeds the 64 KiB diagnostic-IQ bound")
    if any(case.encoded.sample_count != reference.cycle_samples for case in cases):
        raise AssertionError("prepared TX2 waveform has the wrong cycle length")


def _exception_text(error: BaseException) -> str:
    number = getattr(error, "errno", None)
    suffix = f" errno={number}" if number is not None else ""
    return f"{type(error).__name__}{suffix}: {error}"


def _atomic_json(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _configuration_dict(options: ModulatedHardwareOptions) -> dict[str, Any]:
    result = asdict(options)
    result["output_dir"] = str(options.output_dir)
    result["minimum_effective_attenuation_db"] = (
        options.minimum_effective_attenuation_db
    )
    return result


def _waveform_dict(case: _WaveformCase, reference: QpskReference) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "kind": case.kind,
        "reference_id": reference.reference_id,
        "cycle_samples": reference.cycle_samples,
        "symbol_count": reference.symbol_count,
        "symbol_rate_hz": reference.symbol_rate_hz,
        "blocker_offset_hz": case.composite.blocker_offset_hz,
        "blocker_power_db": case.composite.blocker_power_db,
        "blocker_seed": case.blocker_seed,
        "composite_applied_scale": case.composite.applied_scale,
        "peak_fraction": case.composite.peak_fraction,
        "tx2_payload_bytes": len(case.encoded.payload),
        "tx2_payload_sha256": hashlib.sha256(case.encoded.payload).hexdigest(),
        "tx2_code_scale": case.encoded.applied_scale,
        "tx2_peak_code": case.encoded.peak_code,
        "tx2_headroom_db": case.encoded.headroom_db,
        "composition": (
            "desired RRC-QPSK and optional RRC-QPSK blocker are summed digitally "
            "before one TX2 CS16 encoding"
        ),
    }


def _wait_for_idle(
    radio: Issue46Radio, *, timeout_seconds: float = 2.0
) -> dict[str, int]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        status = radio.tandem_status()
        if (
            int(status["state"]) == int(TandemState.IDLE)
            and int(status["fault_flags"]) == 0
            and int(status["fifo_level"]) == 0
        ):
            return {name: int(value) for name, value in status.items()}
        if time.monotonic() >= deadline:
            raise EvidenceInvalid(f"tandem controller did not return to IDLE: {status}")
        time.sleep(0.01)


def _metadata_dict(metadata: TandemFrameMetadata) -> dict[str, Any]:
    return {
        "stream_id": metadata.stream_id,
        "buffer_sequence": metadata.buffer_sequence,
        "first_sample_sequence": metadata.first_sample_sequence,
        "samples_per_channel": metadata.samples_per_channel,
        "flags": metadata.flags,
        "observation_count": metadata.observation_count,
        "event_count": metadata.event_count,
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
        "gain_event_count": len(metadata.gain_events),
        "gain_events": [
            {
                "sample_sequence": event.sample_sequence,
                "event_sequence": event.event_sequence,
                "flags": event.flags,
                "direction": int(event.direction),
                "direction_name": event.direction.name.lower(),
                "reason": int(event.reason),
                "reason_name": event.reason.name.lower(),
                "rx1_gain_index": event.rx1_gain_index,
                "rx2_gain_index": event.rx2_gain_index,
            }
            for event in metadata.gain_events
        ],
    }


def _parse_and_validate_metadata(
    raw_metadata: Any,
    *,
    raw_bytes: int,
    options: ModulatedHardwareOptions,
    continuity: _TandemContinuity,
) -> TandemFrameMetadata:
    if raw_metadata is None:
        raise EvidenceInvalid("tandem capture returned no metadata")
    metadata = (
        raw_metadata
        if isinstance(raw_metadata, TandemFrameMetadata)
        else parse_tandem_frame_metadata(bytes(raw_metadata))
    )
    if metadata.samples_per_channel != options.capture_samples:
        raise EvidenceInvalid("tandem metadata sample count differs from IQ")
    if metadata.iq_payload_bytes != raw_bytes:
        raise EvidenceInvalid("tandem metadata IQ byte count differs from payload")
    if metadata.enabled_scan_mask != 0x0F or metadata.channel_count != 2:
        raise EvidenceInvalid("tandem metadata does not describe dual complex RX")
    if metadata.flags & TANDEM_UNSAFE_FLAGS:
        raise EvidenceInvalid("tandem metadata contains unsafe capture flags")
    if metadata.tandem_state is not TandemState.ARMED_AUTO:
        raise EvidenceInvalid("tandem metadata does not prove an AUTO lease")
    if metadata.tandem_fault_flags:
        raise EvidenceInvalid("tandem metadata reports a controller fault")
    if metadata.observation_count > metadata.observation_capacity:
        raise EvidenceInvalid("tandem observation count exceeds capacity")
    if metadata.event_count > metadata.event_capacity:
        raise EvidenceInvalid("tandem event count exceeds capacity")
    if metadata.event_count != len(metadata.gain_events):
        raise EvidenceInvalid("tandem event count differs from decoded events")
    if metadata.observation_overflow_count or metadata.event_overflow_count:
        raise EvidenceInvalid("tandem metadata capacity overflowed")
    if metadata.rx1_gain_index != metadata.rx2_gain_index:
        raise EvidenceInvalid("tandem endpoint gains are not paired")
    if not 0 <= metadata.tandem_transition_count < _UINT32_MODULUS:
        raise EvidenceInvalid("tandem transition count is outside uint32")
    if metadata.gain_table_id is not _expected_gain_table(options.center_frequency_hz):
        raise EvidenceInvalid("tandem metadata selected the wrong gain table")
    if (
        metadata.minimum_gain_db != 0
        or metadata.maximum_gain_db != 62
        or metadata.initial_gain_db != int(options.manual_gain_db)
    ):
        raise EvidenceInvalid("tandem metadata differs from the requested gains")
    if (
        metadata.minimum_gain_index > metadata.maximum_gain_index
        or not metadata.minimum_gain_index
        <= metadata.rx1_gain_index
        <= metadata.maximum_gain_index
    ):
        raise EvidenceInvalid("tandem endpoint lies outside its session gain range")
    temperature = metadata.ad9361_temperature_mdeg_c
    if temperature is not None and not -40_000 <= temperature <= 125_000:
        raise EvidenceInvalid("AD9361 temperature is outside its physical range")
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
        if not missing_frames and hidden_transitions:
            raise EvidenceInvalid(
                "adjacent tandem frames lost transition event evidence"
            )
        maximum_hidden = missing_frames * maximum_tandem_events_per_frame(
            mode=TandemMode.AUTO,
            samples_per_channel=options.capture_samples,
            power_measurement_samples=options.tandem_power_measurement_samples,
            cooldown_periods=options.tandem_cooldown_periods,
        )
        if hidden_transitions > maximum_hidden:
            raise EvidenceInvalid(
                "tandem gap contains more hidden transitions than omitted frames "
                "can hold"
            )
        continuity.missing_frame_count += missing_frames
        continuity.hidden_transition_count += hidden_transitions
        continuity.unrepresented_since_event += hidden_transitions
    elif metadata.tandem_transition_count < len(metadata.gain_events):
        raise EvidenceInvalid("first tandem frame has more events than transitions")
    else:
        # The session may have transitioned before its first returned frame.
        # This is baseline provenance only and must never become credit for a
        # later event-sequence hole.
        initial_unrepresented_transitions = metadata.tandem_transition_count - len(
            metadata.gain_events
        )

    last_event_sequence = continuity.last_event_sequence
    last_event_sample = continuity.last_event_sample_sequence
    last_event_gain = continuity.last_event_gain_index
    unrepresented_since_event = continuity.unrepresented_since_event
    frame_start = metadata.first_sample_sequence
    frame_end = frame_start + metadata.samples_per_channel
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
        if (
            not metadata.minimum_gain_index
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
                raise EvidenceInvalid("tandem event sequence is not contiguous")
            sequence_hole = sequence_delta - 1
            if sequence_hole != unrepresented_since_event:
                raise EvidenceInvalid(
                    "tandem event-sequence hole does not match locally hidden "
                    "transitions"
                )
            if sequence_hole:
                continuity.event_sequence_hole_count += 1
        if last_event_sample is not None and event.sample_sequence < last_event_sample:
            raise EvidenceInvalid("tandem events are not globally sample ordered")
        anchor_gain: int | None = None
        transitions_to_event = 0
        if last_event_gain is not None:
            anchor_gain = last_event_gain
            transitions_to_event = unrepresented_since_event
        elif previous is not None:
            # With no visible event baseline, earlier hidden transitions are
            # already represented by the immediately previous endpoint.
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
            raise EvidenceInvalid("tandem endpoint changed without an event")
    continuity.previous = metadata
    continuity.last_event_sequence = last_event_sequence
    continuity.last_event_sample_sequence = last_event_sample
    continuity.last_event_gain_index = last_event_gain
    continuity.unrepresented_since_event = unrepresented_since_event
    continuity.last_frame_evidence = {
        "buffer_delta": buffer_delta,
        "sample_delta": sample_delta,
        "missing_frame_count": missing_frames,
        "transition_count_delta": transition_delta,
        "visible_event_count": len(metadata.gain_events),
        "hidden_transition_count": hidden_transitions,
        "initial_unrepresented_transition_count": initial_unrepresented_transitions,
        "cumulative_missing_frame_count": continuity.missing_frame_count,
        "cumulative_hidden_transition_count": continuity.hidden_transition_count,
        "cumulative_event_sequence_hole_count": continuity.event_sequence_hole_count,
    }
    return metadata


def _capture(
    radio: Issue46Radio,
    buffer: Any,
    *,
    options: ModulatedHardwareOptions,
    metadata: bool,
    continuity: _TandemContinuity | None = None,
) -> tuple[bytes, TandemFrameMetadata | None, dict[str, Any]]:
    raw, raw_metadata, refill_ns = radio.capture_iq(
        buffer,
        metadata=metadata,
        samples_per_channel=options.capture_samples,
    )
    expected_bytes = options.capture_samples * 8
    if len(raw) != expected_bytes:
        raise EvidenceInvalid(
            f"IQ payload has {len(raw)} bytes, expected {expected_bytes}"
        )
    active_continuity = continuity if continuity is not None else _TandemContinuity()
    parsed = (
        _parse_and_validate_metadata(
            raw_metadata,
            raw_bytes=len(raw),
            options=options,
            continuity=active_continuity,
        )
        if metadata
        else None
    )
    frame: dict[str, Any] = {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "iq_bytes": len(raw),
        "refill_monotonic_ns": int(refill_ns),
    }
    if parsed is not None:
        frame["metadata"] = _metadata_dict(parsed)
        frame["continuity"] = dict(active_continuity.last_frame_evidence)
    return raw, parsed, frame


def _ordinary_state(
    state: Mapping[str, Sequence[Any]], *, expected_mode: str
) -> tuple[float, float]:
    modes = tuple(str(value) for value in state.get("modes", ()))
    if modes != (expected_mode, expected_mode):
        raise EvidenceInvalid(
            f"RX mode readback {modes!r} differs from {expected_mode!r}"
        )
    gains = tuple(float(value) for value in state.get("gains_db", ()))
    if len(gains) != 2 or any(not math.isfinite(value) for value in gains):
        raise EvidenceInvalid("RX gain readback is not a finite pair")
    return gains[0], gains[1]


def _settle_ordinary(
    radio: Issue46Radio,
    buffer: Any,
    *,
    expected_mode: str,
    options: ModulatedHardwareOptions,
    check_deadline: Callable[[], None],
) -> tuple[list[dict[str, Any]], tuple[tuple[float, float], tuple[float, float]]]:
    trace: list[dict[str, Any]] = []
    stable_values: list[tuple[float, float]] = []
    deadline = time.monotonic() + options.settle_timeout_seconds
    minimum_drain = options.kernel_buffers + 1
    tolerance = 0.2 if expected_mode == "manual" else 1.0
    for attempt in range(1, options.max_settle_frames + 1):
        check_deadline()
        before = radio.read_rx_state()
        _raw, _parsed, frame = _capture(radio, buffer, options=options, metadata=False)
        after = radio.read_rx_state()
        gains = (
            _ordinary_state(before, expected_mode=expected_mode),
            _ordinary_state(after, expected_mode=expected_mode),
        )
        stable_values.extend(gains)
        if attempt <= minimum_drain:
            stable_values.clear()
        elif any(
            max(value[channel] for value in stable_values)
            - min(value[channel] for value in stable_values)
            > tolerance
            for channel in (0, 1)
        ):
            stable_values = list(gains)
        stable_run = len(stable_values) // 2
        trace.append(
            {
                "attempt": attempt,
                "rx_state_before": before,
                "rx_state_after": after,
                "stable_run": stable_run,
                **frame,
            }
        )
        if stable_run >= options.stable_frames:
            minimum = tuple(
                min(value[channel] for value in stable_values) for channel in (0, 1)
            )
            maximum = tuple(
                max(value[channel] for value in stable_values) for channel in (0, 1)
            )
            return trace, (minimum, maximum)
        if time.monotonic() >= deadline:
            break
    raise EvidenceInvalid(f"{expected_mode} did not reach a stable gain window")


def _settle_tandem(
    radio: Issue46Radio,
    buffer: Any,
    *,
    options: ModulatedHardwareOptions,
    check_deadline: Callable[[], None],
) -> tuple[list[dict[str, Any]], TandemFrameMetadata, _TandemContinuity]:
    trace: list[dict[str, Any]] = []
    continuity = _TandemContinuity()
    stable = 0
    minimum_drain = options.kernel_buffers + 1
    deadline = time.monotonic() + options.settle_timeout_seconds
    for attempt in range(1, options.max_settle_frames + 1):
        check_deadline()
        previous = continuity.previous
        _raw, parsed, frame = _capture(
            radio,
            buffer,
            options=options,
            metadata=True,
            continuity=continuity,
        )
        assert parsed is not None
        unchanged = bool(
            previous is not None
            and not parsed.gain_events
            and parsed.tandem_transition_count == previous.tandem_transition_count
            and parsed.bench_gain_indices == previous.bench_gain_indices
        )
        stable = stable + 1 if attempt > minimum_drain and unchanged else 0
        trace.append({"attempt": attempt, "stable_run": stable, **frame})
        if stable >= options.stable_frames:
            return trace, parsed, continuity
        if time.monotonic() >= deadline:
            break
    raise EvidenceInvalid("tandem AUTO did not reach an event-free stable endpoint")


def _quality(
    raw: bytes,
    *,
    reference: QpskReference,
    case: _WaveformCase,
    options: ModulatedHardwareOptions,
) -> dict[str, Any]:
    return analyze_modulated_capture(
        raw,
        reference=reference,
        max_cfo_hz=options.cfo_search_hz,
        thresholds=options.quality_thresholds,
        blocker_offset_hz=case.composite.blocker_offset_hz,
        blocker_power_db=case.composite.blocker_power_db,
        blocker_reference=case.composite.blocker_reference,
    )


def summarize_modulated_measurements(
    measurements: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Reduce repeated captures while keeping conservative gate extrema."""

    if not measurements:
        raise ValueError("cannot summarize an empty measurement set")
    qualities = [item["quality"] for item in measurements]
    first = qualities[0]
    if any(item["reference_id"] != first["reference_id"] for item in qualities):
        raise EvidenceInvalid("measurement reference IDs differ")
    iq_convention = first.get("iq_convention")
    if iq_convention not in ("direct", "conjugated"):
        raise EvidenceInvalid("measurement IQ convention is invalid")
    if any(item.get("iq_convention") != iq_convention for item in qualities):
        raise EvidenceInvalid("measurement IQ conventions differ")
    if any(
        item["blocker_offset_hz"] != first["blocker_offset_hz"]
        or item["blocker_power_db"] != first["blocker_power_db"]
        for item in qualities
    ):
        raise EvidenceInvalid("measurement blocker provenance differs")

    def median_pair(name: str) -> list[float]:
        return [
            float(statistics.median(float(item[name][channel]) for item in qualities))
            for channel in (0, 1)
        ]

    blocker_measurements = [item.get("blocker_measurement") for item in qualities]
    blocker_summary: dict[str, Any] | None = None
    if blocker_measurements[0] is not None:
        if not all(isinstance(item, Mapping) for item in blocker_measurements):
            raise EvidenceInvalid("measurement blocker RF evidence is incomplete")
        typed_blockers = [dict(item) for item in blocker_measurements]
        blocker_summary = {
            "detected": all(bool(item["detected"]) for item in typed_blockers),
            "valid": all(bool(item["valid"]) for item in typed_blockers),
            "commanded_signed_offset_hz": float(
                typed_blockers[0]["commanded_signed_offset_hz"]
            ),
            "measured_signed_offset_hz": float(
                statistics.median(
                    float(item["measured_signed_offset_hz"]) for item in typed_blockers
                )
            ),
            "maximum_absolute_offset_error_hz": max(
                abs(float(item["offset_error_hz"])) for item in typed_blockers
            ),
            "commanded_relative_power_db": float(
                typed_blockers[0]["commanded_relative_power_db"]
            ),
            "measured_relative_power_db": float(
                statistics.median(
                    float(item["measured_relative_power_db"]) for item in typed_blockers
                )
            ),
            "maximum_absolute_power_error_db": max(
                abs(float(item["relative_power_error_db"])) for item in typed_blockers
            ),
            "minimum_correlation_per_rx": [
                min(
                    float(item["correlation_per_rx"][channel])
                    for item in typed_blockers
                )
                for channel in (0, 1)
            ],
        }
    elif any(item is not None for item in blocker_measurements):
        raise EvidenceInvalid("baseline unexpectedly mixes blocker RF evidence")

    result = {
        "schema": first["schema"],
        "reference_id": first["reference_id"],
        "measurement_count": len(qualities),
        "iq_convention": iq_convention,
        "blocker_offset_hz": first["blocker_offset_hz"],
        "blocker_power_db": first["blocker_power_db"],
        "quality_valid": all(bool(item["quality_valid"]) for item in qualities),
        "quality_reasons": sorted(
            {reason for item in qualities for reason in item["quality_reasons"]}
        ),
        "evm_percent": median_pair("evm_percent"),
        "mer_db": median_pair("mer_db"),
        "ser": median_pair("ser"),
        "ber": median_pair("ber"),
        "desired_gain_linear": median_pair("desired_gain_linear"),
        "sample_evm_percent": median_pair("sample_evm_percent"),
        "clipping_fraction": [
            max(float(item["clipping_fraction"][channel]) for item in qualities)
            for channel in (0, 1)
        ],
        "cross_channel_coherence": min(
            float(item["cross_channel_coherence"]) for item in qualities
        ),
        "estimated_cfo_hz": float(
            statistics.median(float(item["estimated_cfo_hz"]) for item in qualities)
        ),
        "amplitude_imbalance_db_rx0_over_rx1": float(
            statistics.median(
                float(item["amplitude_imbalance_db_rx0_over_rx1"]) for item in qualities
            )
        ),
        "blocker_measurement": blocker_summary,
    }
    return result


def _measure_ordinary(
    radio: Issue46Radio,
    buffer: Any,
    *,
    expected_mode: str,
    settled_band: tuple[tuple[float, float], tuple[float, float]],
    reference: QpskReference,
    case: _WaveformCase,
    options: ModulatedHardwareOptions,
    check_deadline: Callable[[], None],
) -> list[dict[str, Any]]:
    minimum, maximum = (list(settled_band[0]), list(settled_band[1]))
    tolerance = 0.2 if expected_mode == "manual" else 1.0
    measurements: list[dict[str, Any]] = []
    for frame_index in range(options.measurement_frames):
        check_deadline()
        before = radio.read_rx_state()
        raw, _parsed, frame = _capture(radio, buffer, options=options, metadata=False)
        after = radio.read_rx_state()
        for state in (before, after):
            gains = _ordinary_state(state, expected_mode=expected_mode)
            for channel in (0, 1):
                minimum[channel] = min(minimum[channel], gains[channel])
                maximum[channel] = max(maximum[channel], gains[channel])
        if any(maximum[channel] - minimum[channel] > tolerance for channel in (0, 1)):
            raise EvidenceInvalid("RX gain left its settled measurement window")
        frame["rx_state_before"] = before
        frame["rx_state_after"] = after
        diagnostic_target = _DIAGNOSTIC_IQ_TARGETS.get(case.case_id)
        if (
            diagnostic_target is not None
            and expected_mode == "manual"
            and frame_index == 0
        ):
            purpose, filename = diagnostic_target
            if len(raw) > MAX_DIAGNOSTIC_IQ_ARTIFACT_BYTES:
                raise EvidenceInvalid("diagnostic IQ artifact exceeds the 64 KiB bound")
            artifact_path = (
                options.output_dir / radio.options.serial / "diagnostic-iq" / filename
            )
            _atomic_bytes(artifact_path, raw)
            frame["raw_iq_provenance"] = {
                "purpose": purpose,
                "case_id": case.case_id,
                "mode": MODE_MANUAL,
                "measurement_index": frame_index,
                "path": artifact_path.relative_to(options.output_dir).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "encoding": "signed-16-bit-little-endian",
                "channel_layout": ["rx0_i", "rx0_q", "rx1_i", "rx1_q"],
                "samples_per_channel": options.capture_samples,
            }
        frame["quality"] = _quality(
            raw, reference=reference, case=case, options=options
        )
        measurements.append(frame)
    return measurements


def _measure_tandem(
    radio: Issue46Radio,
    buffer: Any,
    *,
    settled: TandemFrameMetadata,
    continuity: _TandemContinuity,
    reference: QpskReference,
    case: _WaveformCase,
    options: ModulatedHardwareOptions,
    check_deadline: Callable[[], None],
) -> list[dict[str, Any]]:
    measurements: list[dict[str, Any]] = []
    if continuity.previous is not settled:
        raise AssertionError("tandem continuity does not end at the settled frame")
    for _frame_index in range(options.measurement_frames):
        check_deadline()
        previous = continuity.previous
        assert previous is not None
        raw, parsed, frame = _capture(
            radio,
            buffer,
            options=options,
            metadata=True,
            continuity=continuity,
        )
        assert parsed is not None
        if parsed.gain_events:
            raise EvidenceInvalid("tandem changed gain during a measurement frame")
        if parsed.tandem_transition_count != previous.tandem_transition_count:
            raise EvidenceInvalid("tandem transition count changed without an event")
        if parsed.bench_gain_indices != previous.bench_gain_indices:
            raise EvidenceInvalid("tandem endpoint changed during measurement")
        frame["quality"] = _quality(
            raw, reference=reference, case=case, options=options
        )
        measurements.append(frame)
    return measurements


def _run_case_mode(
    radio: Issue46Radio,
    *,
    mode: str,
    reference: QpskReference,
    case: _WaveformCase,
    options: ModulatedHardwareOptions,
    check_deadline: Callable[[], None],
) -> dict[str, Any]:
    check_deadline()
    status_before = _wait_for_idle(radio)
    radio.configure_rx("manual", manual_gain_db=options.manual_gain_db)
    metadata = mode == MODE_TANDEM
    request: bytes | None = None
    preloaded_tx_readback: float | None = None
    native_entry_conditioning: dict[str, Any] | None = None
    if mode in _NATIVE_IIO_MODES:
        expected_mode = _NATIVE_IIO_MODES[mode]
        # Native AGC must see the real waveform before mode entry.  In
        # particular, fast attack can otherwise lock on the muted state.  Seed
        # fast attack at the common manual ceiling so a retained lock cannot
        # strand one RX chain below the weak-signal endpoint.
        preloaded_tx_readback = float(radio.set_tx2_gain(options.tx2_gain_db))
        if (
            not math.isfinite(preloaded_tx_readback)
            or abs(preloaded_tx_readback - options.tx2_gain_db)
            > TX2_GAIN_READBACK_TOLERANCE_DB
        ):
            raise FixtureSafetyError(
                "TX2 gain readback differs from the planned campaign value: "
                f"requested {options.tx2_gain_db:.2f} dB, "
                f"read back {preloaded_tx_readback!r} dB"
            )
        if options.physical_attenuation_db - preloaded_tx_readback < 30.0:
            raise FixtureSafetyError(
                "TX2 readback violates the 30 dB effective safety boundary"
            )
        if expected_mode == "fast_attack":
            state_before = radio.read_rx_state()
            radio.configure_rx(
                "manual", manual_gain_db=NATIVE_FAST_ENTRY_MANUAL_GAIN_DB
            )
            state_after = radio.read_rx_state()
            native_entry_conditioning = {
                "policy": "live-waveform-manual-ceiling-before-fast-attack",
                "stimulus_tx2_gain_db": preloaded_tx_readback,
                "manual_seed_gain_db": NATIVE_FAST_ENTRY_MANUAL_GAIN_DB,
                "rx_state_before": state_before,
                "rx_state_after": state_after,
            }
        radio.configure_rx(expected_mode)
    elif mode == MODE_MANUAL:
        expected_mode = "manual"
    elif mode == MODE_TANDEM:
        expected_mode = "tandem_auto"
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
            samples_per_channel=options.capture_samples,
        )
    else:
        raise ValueError(f"unknown modulated hardware mode {mode!r}")

    record: dict[str, Any] = {
        "case_id": case.case_id,
        "mode": mode,
        "tandem_status_before": status_before,
    }
    if native_entry_conditioning is not None:
        record["native_entry_conditioning"] = native_entry_conditioning
    body_error: BaseException | None = None
    try:
        with radio.buffer(
            "metadata" if metadata else "ordinary",
            options.kernel_buffers,
            options.capture_samples,
            tandem_request=request,
        ) as (buffer, metadata_abi):
            scoped_error: BaseException | None = None
            try:
                record["capture_api"] = "metadata" if metadata else "ordinary"
                record["metadata_abi"] = metadata_abi
                if metadata and metadata_abi != 2:
                    raise EvidenceInvalid(
                        f"tandem capture requires metadata ABI 2, got {metadata_abi}"
                    )
                tx_readback = (
                    float(radio.set_tx2_gain(options.tx2_gain_db))
                    if preloaded_tx_readback is None
                    else preloaded_tx_readback
                )
                if (
                    not math.isfinite(tx_readback)
                    or abs(tx_readback - options.tx2_gain_db)
                    > TX2_GAIN_READBACK_TOLERANCE_DB
                ):
                    raise FixtureSafetyError(
                        "TX2 gain readback differs from the planned campaign value: "
                        f"requested {options.tx2_gain_db:.2f} dB, "
                        f"read back {tx_readback!r} dB"
                    )
                effective_attenuation = options.physical_attenuation_db - tx_readback
                if effective_attenuation < 30.0:
                    raise FixtureSafetyError(
                        "TX2 readback violates the 30 dB effective safety boundary"
                    )
                record["tx2_gain_requested_db"] = options.tx2_gain_db
                record["tx2_gain_readback_db"] = tx_readback
                record["effective_attenuation_db"] = effective_attenuation
                if metadata:
                    settling, settled, continuity = _settle_tandem(
                        radio,
                        buffer,
                        options=options,
                        check_deadline=check_deadline,
                    )
                    measurements = _measure_tandem(
                        radio,
                        buffer,
                        settled=settled,
                        continuity=continuity,
                        reference=reference,
                        case=case,
                        options=options,
                        check_deadline=check_deadline,
                    )
                else:
                    settling, settled_band = _settle_ordinary(
                        radio,
                        buffer,
                        expected_mode=expected_mode,
                        options=options,
                        check_deadline=check_deadline,
                    )
                    measurements = _measure_ordinary(
                        radio,
                        buffer,
                        expected_mode=expected_mode,
                        settled_band=settled_band,
                        reference=reference,
                        case=case,
                        options=options,
                        check_deadline=check_deadline,
                    )
                record["settling"] = {"frames": len(settling), "trace": settling}
                record["measurements"] = measurements
                record["summary"] = summarize_modulated_measurements(measurements)
            except BaseException as error:  # noqa: BLE001 - mute before RX close
                scoped_error = error
            mute_error: BaseException | None = None
            try:
                radio.set_tx2_gain(TX_MUTE_DB)
            except BaseException as error:  # noqa: BLE001 - in-scope mute is mandatory
                mute_error = FixtureSafetyError(
                    f"failed to mute TX2 inside {case.case_id}/{mode} RX scope: "
                    f"{_exception_text(error)}"
                )
            if scoped_error is not None:
                if mute_error is not None:
                    raise BaseExceptionGroup(
                        "modulated mode body and in-scope TX2 mute both failed",
                        [scoped_error, mute_error],
                    )
                raise scoped_error
            if mute_error is not None:
                raise mute_error
    except BaseException as error:  # noqa: BLE001 - preserve shutdown interrupts
        body_error = error
    if body_error is not None:
        raise body_error
    record["tandem_status_after"] = _wait_for_idle(radio)
    return record


def evaluate_modulated_hardware_report(
    report: Mapping[str, Any],
    thresholds: ModulatedDegradationThresholds,
    *,
    expected_modes: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Apply absolute frame gates and per-mode blocker-degradation gates."""

    _validate_degradation_thresholds(thresholds)
    failures: list[str] = []
    configuration = report.get("configuration")
    configured_value = (
        configuration.get("modes") if isinstance(configuration, Mapping) else None
    )
    configured_modes: tuple[str, ...] = ()
    configured_modes_valid = True
    if isinstance(configured_value, (str, bytes)) or not isinstance(
        configured_value, Sequence
    ):
        failures.append("modulated configuration has no valid mode sequence")
        configured_modes_valid = False
    else:
        configured_modes = tuple(configured_value)
        if not configured_modes:
            failures.append("modulated configuration mode sequence is empty")
            configured_modes_valid = False
        elif any(
            not isinstance(mode, str) or mode not in SUPPORTED_MODULATED_MODES
            for mode in configured_modes
        ):
            failures.append("modulated configuration contains an unsupported mode")
            configured_modes_valid = False
        elif len(set(configured_modes)) != len(configured_modes):
            failures.append("modulated configuration contains duplicate modes")
            configured_modes_valid = False
    if expected_modes is None:
        active_modes = configured_modes if configured_modes_valid else ()
    else:
        active_modes = tuple(expected_modes)
        if (
            not active_modes
            or any(
                not isinstance(mode, str) or mode not in SUPPORTED_MODULATED_MODES
                for mode in active_modes
            )
            or len(set(active_modes)) != len(active_modes)
        ):
            raise ValueError("expected_modes must be unique supported modes")
        if configured_modes != active_modes:
            failures.append("modulated configuration modes differ from expectation")
    if report.get("mode_evidence_policy") != modulated_mode_evidence_policy():
        failures.append("modulated mode evidence policy is missing or invalid")
    indexed: dict[str, dict[str, Mapping[str, Any]]] = {
        mode: {} for mode in active_modes
    }
    report_only_failures: list[str] = []
    absolute_quality_failures: dict[str, list[str]] = {
        mode: [] for mode in active_modes
    }
    degradation_failures: dict[str, list[str]] = {
        mode: [] for mode in active_modes
    }
    observed_iq_conventions: set[str] = set()
    for run in report.get("runs", []):
        mode = str(run.get("mode"))
        case_id = str(run.get("case_id"))
        if mode not in indexed:
            failures.append(f"unknown mode record {mode}")
            continue
        if case_id in indexed[mode]:
            failures.append(f"duplicate run {mode}/{case_id}")
            continue
        indexed[mode][case_id] = run
        summary = run.get("summary", {})
        iq_convention = summary.get("iq_convention")
        if iq_convention not in ("direct", "conjugated"):
            failures.append(f"invalid IQ convention for {mode}/{case_id}")
        else:
            observed_iq_conventions.add(str(iq_convention))
        if not bool(summary.get("quality_valid", False)):
            reasons = ",".join(summary.get("quality_reasons", ())) or "invalid"
            message = f"absolute quality failed for {mode}/{case_id}: {reasons}"
            absolute_quality_failures[mode].append(message)
            if mode in REPORT_ONLY_MODULATED_MODES:
                report_only_failures.append(message)
            else:
                failures.append(message)
    if len(observed_iq_conventions) > 1:
        failures.append("modulated runs use mixed IQ conventions")

    blocker_ids = [
        str(item["case_id"])
        for item in report.get("waveforms", [])
        if item.get("kind") == "composite_blocker"
    ]
    degradation_rows: list[dict[str, Any]] = []
    for mode in active_modes:
        runs = indexed[mode]
        baseline_run = runs.get("desired_only")
        if baseline_run is None:
            failures.append(f"missing desired-only baseline for {mode}")
            continue
        baseline = baseline_run["summary"]
        for case_id in blocker_ids:
            blocked_run = runs.get(case_id)
            if blocked_run is None:
                failures.append(f"missing blocker run {mode}/{case_id}")
                continue
            row = quantify_blocker_degradation(baseline, blocked_run["summary"])
            row["mode"] = mode
            row["case_id"] = case_id
            row_failures: list[str] = []
            if (
                float(row["worst_evm_increase_percentage_points"])
                > thresholds.max_evm_increase_percentage_points
            ):
                row_failures.append("evm_degradation")
            if float(row["worst_mer_loss_db"]) > thresholds.max_mer_loss_db:
                row_failures.append("mer_degradation")
            for channel in row["channels"]:
                if float(channel["ser_increase"]) > thresholds.max_ser_increase:
                    row_failures.append(f"{channel['channel']}_ser_degradation")
                if float(channel["ber_increase"]) > thresholds.max_ber_increase:
                    row_failures.append(f"{channel['channel']}_ber_degradation")
                gain_loss = -float(channel["desired_gain_change_db"])
                if gain_loss > thresholds.max_desired_gain_loss_db:
                    row_failures.append(f"{channel['channel']}_gain_degradation")
            row["valid"] = not row_failures
            row["failure_reasons"] = sorted(set(row_failures))
            row["release_gate"] = (
                "report_only" if mode in REPORT_ONLY_MODULATED_MODES else "binding"
            )
            row_messages = [
                f"{mode}/{case_id}: {reason}"
                for reason in row["failure_reasons"]
            ]
            degradation_failures[mode].extend(row_messages)
            if mode in REPORT_ONLY_MODULATED_MODES:
                report_only_failures.extend(row_messages)
            else:
                failures.extend(row_messages)
            degradation_rows.append(row)
    expected_runs = len(active_modes) * (1 + len(blocker_ids))
    if len(report.get("runs", [])) != expected_runs:
        failures.append(
            f"report has {len(report.get('runs', []))} runs, expected {expected_runs}"
        )
    mode_results = []
    for mode in active_modes:
        mode_rows = [row for row in degradation_rows if row["mode"] == mode]
        mode_absolute_valid = not absolute_quality_failures[mode]
        mode_degradation_valid = (
            len(mode_rows) == len(blocker_ids)
            and all(row["valid"] for row in mode_rows)
        )
        mode_failures = [
            *absolute_quality_failures[mode],
            *degradation_failures[mode],
        ]
        mode_results.append(
            {
                "mode": mode,
                "release_gate": (
                    "report_only"
                    if mode in REPORT_ONLY_MODULATED_MODES
                    else "binding"
                ),
                "absolute_quality_valid": mode_absolute_valid,
                "degradation_valid": mode_degradation_valid,
                "observed_valid": (
                    mode_absolute_valid and mode_degradation_valid
                ),
                "failure_reasons": mode_failures,
            }
        )
    binding_rows = [
        row
        for row in degradation_rows
        if row["mode"] not in REPORT_ONLY_MODULATED_MODES
    ]
    expected_binding_rows = sum(
        len(blocker_ids)
        for mode in active_modes
        if mode not in REPORT_ONLY_MODULATED_MODES
    )
    return {
        "valid": not failures,
        "absolute_quality_valid": not any(
            absolute_quality_failures[mode] for mode in active_modes
        ),
        "binding_absolute_quality_valid": not any(
            absolute_quality_failures[mode]
            for mode in active_modes
            if mode not in REPORT_ONLY_MODULATED_MODES
        ),
        "degradation_valid": all(row["valid"] for row in degradation_rows)
        and len(degradation_rows) == len(active_modes) * len(blocker_ids),
        "binding_degradation_valid": all(row["valid"] for row in binding_rows)
        and len(binding_rows) == expected_binding_rows,
        "failure_reasons": failures,
        "report_only_failures": report_only_failures,
        "mode_results": mode_results,
        "degradation": degradation_rows,
    }


def run_modulated_hardware_campaign(
    radio: Issue46Radio, options: ModulatedHardwareOptions
) -> tuple[dict[str, Any], Path]:
    """Run desired-only and composite QPSK on every selected manual/AGC mode."""

    validate_modulated_hardware_options(options)
    reference, cases = _prepare_waveforms(options)
    if radio.options.sample_rate_hz != options.sample_rate_hz:
        raise ValueError("radio and modulated campaign sample rates differ")
    if radio.options.samples_per_channel != options.capture_samples:
        raise ValueError("radio and modulated campaign sample counts differ")
    if abs(float(radio.options.tx_gain_db) - options.tx2_gain_db) > 0.01:
        raise ValueError("radio TX authorization differs from the campaign ceiling")
    if radio.options.center_frequency_hz != options.center_frequency_hz:
        raise ValueError("radio and campaign center frequencies differ")
    center_readback = radio.read_center_frequency()
    if any(
        abs(int(value) - options.center_frequency_hz) > 2
        for value in center_readback.values()
    ):
        raise EvidenceInvalid(
            "live RX/TX LO differs from the requested center frequency"
        )

    report_path = (
        options.output_dir / radio.options.serial / "modulated-hardware-report.json"
    )
    radio._report_path = report_path
    started = time.monotonic()

    def check_deadline() -> None:
        if time.monotonic() - started >= options.max_seconds:
            raise TimeoutError(
                f"modulated campaign exceeded {options.max_seconds:.1f} seconds"
            )

    report: dict[str, Any] = {
        "schema": "plutosdr-fw.modulated-hardware.v1",
        "started_unix_ns": time.time_ns(),
        "identity": radio.identity,
        "configuration": _configuration_dict(options),
        "mode_evidence_policy": modulated_mode_evidence_policy(),
        "bench_port_mapping": {
            "stimulus": "bench TX2 = AD9361/IIO TX2",
            "receivers": [
                "bench RX0 = AD9361/IIO RX1",
                "bench RX1 = AD9361/IIO RX2",
            ],
        },
        "stimulus_topology": {
            "active_transmitters": ["TX2"],
            "tx1": (
                "excluded from the DMA scan, ZERO selectors, and hardware "
                "attenuation mute"
            ),
            "tx2": "one cyclic-DMA CS16 waveform",
            "blocker": "digitally summed into the TX2 waveform before encoding",
            "external_generator_required": False,
            "second_transmitter_required": False,
        },
        "rf": {
            "center_frequency_hz_requested": options.center_frequency_hz,
            "center_frequency_hz_readback": center_readback,
        },
        "safety": {
            "physical_attenuation_db": options.physical_attenuation_db,
            "tx2_gain_ceiling_db": options.tx2_gain_db,
            "minimum_effective_attenuation_db": (
                options.minimum_effective_attenuation_db
            ),
            "required_effective_attenuation_db": 30.0,
        },
        "waveforms": [_waveform_dict(case, reference) for case in cases],
        "runs": [],
        "verdict": "running",
    }
    radio.mute_all()
    _atomic_json(report_path, report)
    body_error: BaseException | None = None
    try:
        for case in cases:
            check_deadline()
            case_record = next(
                item for item in report["waveforms"] if item["case_id"] == case.case_id
            )
            try:
                with radio.cyclic_tx2_waveform(
                    case.encoded.payload, sample_count=case.encoded.sample_count
                ) as dma_evidence:
                    case_record["dma"] = dict(dma_evidence)
                    _atomic_json(report_path, report)
                    for mode in options.modes:
                        run = _run_case_mode(
                            radio,
                            mode=mode,
                            reference=reference,
                            case=case,
                            options=options,
                            check_deadline=check_deadline,
                        )
                        report["runs"].append(run)
                        _atomic_json(report_path, report)
                        if case.case_id == "desired_only" and mode == MODE_MANUAL:
                            summary = run.get("summary")
                            if (
                                not isinstance(summary, Mapping)
                                or summary.get("quality_valid") is not True
                            ):
                                reasons = (
                                    summary.get("quality_reasons", ())
                                    if isinstance(summary, Mapping)
                                    else ()
                                )
                                reason_text = ",".join(str(item) for item in reasons)
                                raise EvidenceInvalid(
                                    "desired-only manual reference preflight failed"
                                    + (f": {reason_text}" if reason_text else "")
                                )
            finally:
                # The cyclic context records this only after its unconditional
                # mute and buffer close.  Persist it even when a mode fails so
                # the invalid report still proves the independent DMA barrier.
                case_record["dma_cleanup"] = dict(
                    getattr(radio, "_last_cyclic_dma_cleanup", {})
                )
                _atomic_json(report_path, report)
            if not bool(case_record["dma_cleanup"].get("buffer_closed", False)):
                raise FixtureSafetyError(
                    "cyclic DMA cleanup did not prove buffer close"
                )
            if case_record["dma_cleanup"].get("failures"):
                raise FixtureSafetyError("cyclic DMA cleanup reported failures")
            _atomic_json(report_path, report)
        report["evaluation"] = evaluate_modulated_hardware_report(
            report,
            options.degradation_thresholds,
            expected_modes=options.modes,
        )
        report["verdict"] = "pass" if report["evaluation"]["valid"] else "fail"
        report["finished_unix_ns"] = time.time_ns()
    except BaseException as error:  # noqa: BLE001 - report every invalid exit
        body_error = error
        report["verdict"] = "invalid"
        report["error"] = _exception_text(error)

    cleanup_error: BaseException | None = None
    try:
        radio.mute_all()
        report["final_mute"] = dict(getattr(radio, "_last_mute_evidence", {}) or {})
    except BaseException as error:  # noqa: BLE001 - final mute is unconditional
        cleanup_error = FixtureSafetyError(
            f"final modulated campaign mute failed: {_exception_text(error)}"
        )
        report["verdict"] = "invalid"
        report["final_mute_error"] = _exception_text(error)
    _atomic_json(report_path, report)
    if body_error is not None:
        if cleanup_error is not None:
            raise BaseExceptionGroup(
                "modulated campaign body and final cleanup both failed",
                [body_error, cleanup_error],
            )
        raise body_error
    if cleanup_error is not None:
        raise cleanup_error
    return report, report_path


def run_serial_modulated_hardware_campaign(
    iio_module: Any,
    radio_options: Any,
    options: ModulatedHardwareOptions,
    *,
    radio_factory: Callable[[Any, Any], Issue46Radio] = Issue46Radio,
) -> tuple[dict[str, Any], Path]:
    """Own one serial-attested radio for the complete campaign lifecycle."""

    # Unsafe campaign inputs must fail without even opening a USB context.
    validate_modulated_hardware_options(options)
    radio = radio_factory(iio_module, radio_options)
    body_error: BaseException | None = None
    result: tuple[dict[str, Any], Path] | None = None
    try:
        result = run_modulated_hardware_campaign(radio, options)
    except BaseException as error:  # noqa: BLE001 - close after every exit
        body_error = error
    close_error: BaseException | None = None
    try:
        radio.close()
    except BaseException as error:  # noqa: BLE001 - preserve close failures too
        close_error = FixtureSafetyError(
            f"radio close failed after modulated campaign: {_exception_text(error)}"
        )
    report_path = (
        result[1] if result is not None else getattr(radio, "_report_path", None)
    )
    durable_report: dict[str, Any] | None = None
    durable_error: BaseException | None = None
    if close_error is None:
        try:
            if not bool(getattr(radio, "cleanup_verified", False)):
                raise FixtureSafetyError(
                    "radio close did not verify the final hardware cleanup"
                )
            if report_path is not None:
                report_path = Path(report_path)
                if not report_path.is_file():
                    raise EvidenceInvalid("post-close evidence report is missing")
                if report_path.with_suffix(report_path.suffix + ".tmp").exists():
                    raise EvidenceInvalid("post-close atomic report temp file remains")
                parsed = json.loads(report_path.read_text(encoding="utf-8"))
                if not isinstance(parsed, dict):
                    raise EvidenceInvalid("post-close report is not a JSON object")
                cleanup = parsed.get("cleanup")
                if not isinstance(cleanup, Mapping) or not bool(
                    cleanup.get("verified", False)
                ):
                    raise FixtureSafetyError(
                        "durable post-close report does not prove cleanup"
                    )
                if cleanup.get("failures") != []:
                    raise FixtureSafetyError(
                        "durable post-close cleanup contains failures"
                    )
                durable_report = parsed
            elif result is not None:
                raise EvidenceInvalid("successful campaign has no durable report path")
        except BaseException as error:  # noqa: BLE001 - durable proof is mandatory
            durable_error = error
    exit_errors = [
        error for error in (body_error, close_error, durable_error) if error is not None
    ]
    if len(exit_errors) > 1:
        raise BaseExceptionGroup(
            "modulated campaign, radio close, or durable cleanup proof failed",
            exit_errors,
        )
    if exit_errors:
        raise exit_errors[0]
    assert result is not None
    assert report_path is not None
    assert durable_report is not None
    return durable_report, report_path


# A descriptive alias for callers that use execute/run terminology interchangeably.
execute_modulated_hardware_campaign = run_modulated_hardware_campaign
