"""Synthetic goldens and planted failures for transient AGC measurements."""

from __future__ import annotations

import json
import math
from dataclasses import replace

import pytest

from .metadata_abi import TandemGainEvent
from .transient_quality import (
    StimulusCommand,
    TransientEvidenceError,
    analyze_immediate_dual_rx,
    calculate_transient_response,
    reconcile_tandem_events,
    timestamp_stimulus_command,
)


def _command(
    command_id: str,
    level_db: float,
    *,
    host_before_ns: int,
    host_after_ns: int,
    sample_before: int | None,
    sample_after: int | None,
) -> StimulusCommand:
    return StimulusCommand(
        command_id=command_id,
        requested_level_db=level_db,
        applied_level_db=level_db,
        host_before_ns=host_before_ns,
        host_after_ns=host_after_ns,
        sample_sequence_before=sample_before,
        sample_sequence_after=sample_after,
    )


def _dual_tone_windows(
    amplitudes: list[tuple[float, float]],
    *,
    window_samples: int = 1_024,
    sample_rate_hz: int = 1_000_000,
    tone_hz: float = 100_000.0,
    phases: tuple[float, float] = (0.4, -0.2),
    noise_sigma: float = 1.5,
    seed: int = 24,
) -> bytes:
    np = pytest.importorskip("numpy")
    sample_count = len(amplitudes) * window_samples
    indexes = np.arange(sample_count, dtype=np.float64)
    carrier = np.exp(2j * np.pi * tone_hz * indexes / sample_rate_hz)
    rng = np.random.default_rng(seed)
    signal = np.empty((2, sample_count), dtype=np.complex128)
    for channel in range(2):
        envelope = np.concatenate(
            [np.full(window_samples, pair[channel]) for pair in amplitudes]
        )
        noise = noise_sigma * (
            rng.normal(size=sample_count) + 1j * rng.normal(size=sample_count)
        )
        signal[channel] = envelope * np.exp(1j * phases[channel]) * carrier + noise
    words = np.empty((sample_count, 4), dtype="<i2")
    words[:, 0] = np.rint(signal[0].real).astype("<i2")
    words[:, 1] = np.rint(signal[0].imag).astype("<i2")
    words[:, 2] = np.rint(signal[1].real).astype("<i2")
    words[:, 3] = np.rint(signal[1].imag).astype("<i2")
    return words.tobytes()


def test_timestamp_command_brackets_callback_and_hardware_readback() -> None:
    clocks = iter((1_000_000, 1_120_000))
    samples = iter((50_000, 50_180))
    writes: list[float] = []

    def apply(level: float) -> float:
        writes.append(level)
        return level + 0.05

    command = timestamp_stimulus_command(
        "louder",
        -30.0,
        apply=apply,
        clock_ns=lambda: next(clocks),
        sample_sequence=lambda: next(samples),
        max_host_jitter_ns=200_000,
        max_sample_uncertainty=200,
        readback_tolerance_db=0.1,
    )

    assert writes == [-30.0]
    assert command.host_jitter_ns == 120_000
    assert command.sample_uncertainty == 180
    assert command.applied_level_db == pytest.approx(-29.95)
    assert command.as_dict()["sample_sequence_before"] == 50_000
    json.dumps(command.as_dict(), allow_nan=False)


@pytest.mark.parametrize(
    ("clock_values", "sample_values", "readback", "message"),
    [
        ((0, 6_000_001), (10, 11), -30.0, "host jitter"),
        ((2, 1), (10, 11), -30.0, "clock moved backward"),
        ((0, 1), (12, 11), -30.0, "sample sequence moved backward"),
        ((0, 1), (10, 11), -29.0, "readback differs"),
        ((0, 1), (10, 11), math.nan, "finite number"),
    ],
)
def test_timestamp_command_fails_closed_on_uncertain_or_invalid_evidence(
    clock_values: tuple[int, int],
    sample_values: tuple[int, int],
    readback: float,
    message: str,
) -> None:
    clocks = iter(clock_values)
    samples = iter(sample_values)
    with pytest.raises(TransientEvidenceError, match=message):
        timestamp_stimulus_command(
            "step",
            -30.0,
            apply=lambda _level: readback,
            clock_ns=lambda: next(clocks),
            sample_sequence=lambda: next(samples),
            max_host_jitter_ns=5_000_000,
            max_sample_uncertainty=100,
        )


def test_immediate_windows_recover_level_snr_clipping_and_phase() -> None:
    raw = _dual_tone_windows(
        [(200.0, 160.0), (200.0, 160.0), (800.0, 640.0), (800.0, 640.0)]
    )
    result = analyze_immediate_dual_rx(
        raw,
        first_sample_sequence=90_000,
        sample_rate_hz=1_000_000,
        expected_tone_hz=100_000.0,
        window_samples=1_024,
    )

    assert result["window_count"] == 4
    assert result["uncovered_tail_samples"] == 0
    assert result["selected_tone_hz"] == 100_000.0
    windows = result["windows"]
    assert windows[0]["sample_start"] == 90_000
    assert windows[-1]["sample_end_exclusive"] == 94_096
    assert windows[0]["tone_dbfs"] == pytest.approx(
        [
            20.0 * math.log10(200.0 / 2_048.0),
            20.0 * math.log10(160.0 / 2_048.0),
        ],
        abs=0.15,
    )
    assert windows[2]["tone_dbfs"] == pytest.approx(
        [
            20.0 * math.log10(800.0 / 2_048.0),
            20.0 * math.log10(640.0 / 2_048.0),
        ],
        abs=0.15,
    )
    assert min(min(window["tone_snr_db"]) for window in windows) > 35.0
    assert all(window["clipping_fraction"] == [0.0, 0.0] for window in windows)
    assert all(
        window["phase_difference_deg"] == pytest.approx(math.degrees(0.6), abs=0.2)
        for window in windows
    )
    assert result["quality_valid"]
    json.dumps(result, allow_nan=False)


def test_immediate_windows_localize_clipping_without_discarding_first_samples() -> None:
    np = pytest.importorskip("numpy")
    raw = bytearray(_dual_tone_windows([(400.0, 400.0)] * 3))
    words = np.frombuffer(raw, dtype="<i2").reshape((-1, 4))
    words[1_024:2_048:32, 2] = 2_047
    result = analyze_immediate_dual_rx(
        raw,
        first_sample_sequence=1_000,
        sample_rate_hz=1_000_000,
        expected_tone_hz=100_000.0,
        window_samples=1_024,
    )

    assert result["windows"][0]["offset_start"] == 0
    assert result["windows"][0]["clipping_fraction"] == [0.0, 0.0]
    assert result["windows"][1]["clipping_fraction"][1] > 0.0
    assert "rx1_clipping" in result["windows"][1]["quality_reasons"]
    assert not result["quality_valid"]


@pytest.mark.parametrize(
    ("value", "options", "message"),
    [
        (b"", {}, "contains no samples|empty"),
        (
            [[complex(math.nan, 0.0)] * 64, [0j] * 64],
            {"window_samples": 64},
            "non-finite",
        ),
        ([[0j] * 32, [0j] * 32], {}, "shorter than one analysis window"),
    ],
)
def test_immediate_analyzer_rejects_missing_or_nonfinite_iq(
    value: object, options: dict[str, int], message: str
) -> None:
    with pytest.raises((TransientEvidenceError, ValueError), match=message):
        analyze_immediate_dual_rx(
            value,
            first_sample_sequence=0,
            sample_rate_hz=1_000_000,
            expected_tone_hz=100_000.0,
            **options,
        )


def _trajectory_commands() -> list[StimulusCommand]:
    return [
        _command(
            "baseline",
            -60.0,
            host_before_ns=0,
            host_after_ns=100,
            sample_before=100,
            sample_after=110,
        ),
        _command(
            "louder",
            -30.0,
            host_before_ns=1_000,
            host_after_ns=1_100,
            sample_before=200,
            sample_after=210,
        ),
        _command(
            "quieter",
            -60.0,
            host_before_ns=2_000,
            host_after_ns=2_100,
            sample_before=400,
            sample_after=410,
        ),
    ]


def _paired_event(
    sample: int, sequence: int, direction: int, gain: int
) -> dict[str, int]:
    return {
        "sample_sequence": sample,
        "event_sequence": sequence,
        "direction": direction,
        "rx1_gain_index": gain,
        "rx2_gain_index": gain,
    }


def test_reconcile_tandem_events_produces_attack_and_release_bounds() -> None:
    result = reconcile_tandem_events(
        _trajectory_commands(),
        [
            _paired_event(230, 7, 2, 64),
            _paired_event(430, 8, 1, 65),
        ],
        sample_rate_hz=1_000,
        max_sample_uncertainty=20,
    )

    attack, release = result["transitions"]
    assert attack["response_kind"] == "attack"
    assert attack["expected_event_direction"] == "decrease"
    assert attack["latency_lower_samples"] == 20
    assert attack["latency_upper_samples"] == 30
    assert attack["latency_lower_seconds"] == pytest.approx(0.020)
    assert attack["latency_upper_seconds"] == pytest.approx(0.030)
    assert release["response_kind"] == "release"
    assert release["expected_event_direction"] == "increase"
    assert release["latency_lower_samples"] == 20
    assert release["latency_upper_samples"] == 30
    assert result["unassigned_event_count"] == 0
    json.dumps(result, allow_nan=False)


def test_event_inside_bounded_command_write_has_zero_latency_lower_bound() -> None:
    result = reconcile_tandem_events(
        _trajectory_commands(),
        [
            _paired_event(205, 12, 2, 64),
            _paired_event(430, 13, 1, 65),
        ],
        sample_rate_hz=1_000,
        max_sample_uncertainty=20,
    )
    attack = result["transitions"][0]
    assert attack["event_within_command_bracket"]
    assert attack["latency_lower_samples"] == 0
    assert attack["latency_upper_samples"] == 5


def test_reconciliation_accepts_strict_metadata_event_objects() -> None:
    result = reconcile_tandem_events(
        _trajectory_commands(),
        [
            TandemGainEvent(230, 0xFFFFFFFF, 2 << 4, 64, 64),
            TandemGainEvent(430, 0, 1 << 4, 65, 65),
        ],
        sample_rate_hz=1_000,
        max_sample_uncertainty=20,
    )
    assert [
        transition["expected_event_direction"] for transition in result["transitions"]
    ] == ["decrease", "increase"]


@pytest.mark.parametrize(
    ("commands", "events", "message"),
    [
        (
            _trajectory_commands(),
            [_paired_event(230, 7, 2, 64)],
            "lacks a paired release",
        ),
        (
            _trajectory_commands(),
            [
                _paired_event(230, 7, 2, 64),
                _paired_event(430, 9, 1, 65),
            ],
            "missing evidence",
        ),
        (
            _trajectory_commands(),
            [
                _paired_event(230, 7, 2, 64),
                {
                    **_paired_event(430, 8, 1, 65),
                    "rx2_gain_index": 66,
                },
            ],
            "torn gain pair",
        ),
        (
            _trajectory_commands(),
            [
                _paired_event(230, 7, 2, 64),
                _paired_event(430, 8, 1, 66),
            ],
            r"exact \+/-1 step",
        ),
        (
            [
                _trajectory_commands()[0],
                _command(
                    "louder",
                    -30.0,
                    host_before_ns=1_000,
                    host_after_ns=6_001_001,
                    sample_before=200,
                    sample_after=210,
                ),
            ],
            [_paired_event(230, 7, 2, 64)],
            "host jitter",
        ),
        (
            [
                _trajectory_commands()[0],
                _command(
                    "louder",
                    -30.0,
                    host_before_ns=1_000,
                    host_after_ns=1_100,
                    sample_before=None,
                    sample_after=None,
                ),
            ],
            [_paired_event(230, 7, 2, 64)],
            "lacks sample-sequence bounds",
        ),
    ],
)
def test_reconciliation_fails_closed_on_missing_or_ambiguous_evidence(
    commands: list[StimulusCommand],
    events: list[dict[str, int]],
    message: str,
) -> None:
    with pytest.raises(TransientEvidenceError, match=message):
        reconcile_tandem_events(
            commands,
            events,
            sample_rate_hz=1_000,
            max_sample_uncertainty=20,
        )


def _quality_window(
    start: int,
    level: float,
    *,
    phase_deg: float = -179.0,
) -> dict[str, object]:
    return {
        "sample_start": start,
        "sample_end_exclusive": start + 10,
        "tone_dbfs": [level, level - 0.2],
        "tone_snr_db": [30.0, 29.0],
        "clipping_fraction": [0.0, 0.0],
        "phase_difference_deg": phase_deg,
    }


def _response_fixture() -> tuple[
    StimulusCommand, StimulusCommand, list[dict[str, object]]
]:
    previous = _command(
        "baseline",
        -60.0,
        host_before_ns=0,
        host_after_ns=10,
        sample_before=10,
        sample_after=20,
    )
    command = _command(
        "louder",
        -30.0,
        host_before_ns=100,
        host_after_ns=200,
        sample_before=50,
        sample_after=55,
    )
    levels = [-30.0] * 5 + [-12.0, -10.0, -16.0, -14.0, -15.0, -15.0, -15.0]
    windows = [
        _quality_window(
            index * 10,
            level,
            phase_deg=179.0 if index < 5 else -179.0,
        )
        for index, level in enumerate(levels)
    ]
    return previous, command, windows


def test_transient_response_calculates_settling_overshoot_and_ringing() -> None:
    previous, command, windows = _response_fixture()
    result = calculate_transient_response(
        windows,
        previous_command=previous,
        command=command,
        sample_rate_hz=1_000,
        settling_tolerance_db=0.2,
        ringing_deadband_db=0.25,
    )

    assert result["response_kind"] == "attack"
    assert result["baseline_tone_dbfs"] == pytest.approx([-30.0, -30.2])
    assert result["steady_tone_dbfs"] == pytest.approx([-15.0, -15.2])
    assert result["worst_overshoot_db"] == pytest.approx(5.0)
    assert result["opposite_excursion_db"] == pytest.approx([1.0, 1.0])
    assert result["ringing_crossings"] == [2, 2]
    assert result["ringing_excursions_after_stable"] == 0
    assert result["ringing_peak_to_peak_db"] == pytest.approx([0.0, 0.0])
    assert result["signal_settling_latency_lower_samples"] == 35
    assert result["signal_settling_latency_upper_samples"] == 50
    assert result["maximum_phase_excursion_deg"] == pytest.approx(2.0)
    assert result["command_intersecting_window_count"] == 1
    json.dumps(result, allow_nan=False)


def test_release_step_uses_the_same_directionally_symmetric_metrics() -> None:
    previous, command, windows = _response_fixture()
    previous = replace(
        previous,
        requested_level_db=-30.0,
        applied_level_db=-30.0,
    )
    command = replace(
        command,
        requested_level_db=-60.0,
        applied_level_db=-60.0,
    )
    inverted = []
    for window in windows:
        copy = dict(window)
        copy["tone_dbfs"] = [
            -45.0 - (float(value) + 30.0) for value in window["tone_dbfs"]
        ]
        inverted.append(copy)
    result = calculate_transient_response(
        inverted,
        previous_command=previous,
        command=command,
        sample_rate_hz=1_000,
        settling_tolerance_db=0.2,
    )
    assert result["response_kind"] == "release"
    assert result["worst_overshoot_db"] == pytest.approx(5.0)


def test_transient_response_rejects_gaps_and_missing_steady_state() -> None:
    previous, command, windows = _response_fixture()
    with pytest.raises(TransientEvidenceError, match="gap, overlap"):
        calculate_transient_response(
            windows[:6] + windows[7:],
            previous_command=previous,
            command=command,
            sample_rate_hz=1_000,
        )

    unstable = [dict(window) for window in windows]
    for index, window in enumerate(unstable[-6:]):
        window["tone_dbfs"] = [-10.0 if index % 2 else -20.0] * 2
    with pytest.raises(TransientEvidenceError, match="stable window run"):
        calculate_transient_response(
            unstable,
            previous_command=previous,
            command=command,
            sample_rate_hz=1_000,
            settling_tolerance_db=0.1,
        )
