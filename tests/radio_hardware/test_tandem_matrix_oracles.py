"""Offline goldens for matrix planning, comparison, and verdict semantics."""

from __future__ import annotations

import copy

import pytest

from .experiment import EvidenceInvalid
from .metadata_abi import TandemEventDirection
from .tandem_quality import (
    MODE_MANUAL,
    MODE_NATIVE,
    MODE_TANDEM,
    TandemQualityOptions,
    _observed_tandem_evidence,
    default_tx_trajectory,
    evaluate_matrix,
    parse_tx_trajectory,
    validate_options,
)


def test_safe_default_trajectory_is_bidirectional_and_returns_weak() -> None:
    levels = default_tx_trajectory("smoke")
    options = TandemQualityOptions(
        tx_gain_trajectory_db=levels, physical_attenuation_db=0.0
    )
    validate_options(options)
    assert levels == (-61.0, -45.0, -30.0, -45.0, -61.0)
    assert options.minimum_effective_attenuation_db == 30.0
    assert parse_tx_trajectory("-61, -45,-30,-45,-61") == levels


@pytest.mark.parametrize(
    ("levels", "attenuation", "message"),
    [
        ((-60.0, -45.0, -20.0, -60.0), 0.0, "at least 30"),
        ((-60.0, -45.0, -30.0), 0.0, "return"),
        ((-60.0, -55.0, 1.0, -60.0), 30.0, r"\[-89.75"),
        ((-60.0, -60.0, -60.0), 30.0, "rising and falling"),
    ],
)
def test_unsafe_or_non_diagnostic_trajectory_is_rejected(
    levels: tuple[float, ...], attenuation: float, message: str
) -> None:
    options = TandemQualityOptions(
        tx_gain_trajectory_db=levels, physical_attenuation_db=attenuation
    )
    with pytest.raises(ValueError, match=message):
        validate_options(options)


def _summary(valid: bool = True, *, tone_dbfs: float = -25.0) -> dict[str, object]:
    return {
        "quality_valid": valid,
        "tone_dbfs_median": [tone_dbfs, tone_dbfs - 0.2],
        "tone_snr_db_median": [30.0, 29.0],
        "coherence_median": 0.999,
        "within_capture_phase_std_deg_max": 0.2,
    }


def _ordinary_cell(
    index: int,
    level: float,
    *,
    valid: bool = True,
    gain: float = 30.0,
    tone_dbfs: float = -25.0,
) -> dict:
    return {
        "level_index": index,
        "tx2_gain_requested_db": level,
        "summary": _summary(valid, tone_dbfs=tone_dbfs),
        "measurements": [{"rx_state_after": {"gains_db": [gain, gain - 0.5]}}],
        "settling": {"trace": []},
    }


def _tandem_cell(index: int, level: float) -> dict:
    direction = (
        TandemEventDirection.DECREASE if index == 1 else TandemEventDirection.INCREASE
    )
    gain = 50 if index == 1 else 51
    samples_per_channel = 1_024
    settling_buffer = index * 2
    settling_first_sample = 10_000 + settling_buffer * samples_per_channel
    event = {
        "sample_sequence": settling_first_sample + 100,
        "event_sequence": index + 1,
        "direction": int(direction),
        "rx1_gain_index": gain,
        "rx2_gain_index": gain,
    }
    metadata = {
        "stream_id": 99,
        "buffer_sequence": settling_buffer,
        "first_sample_sequence": settling_first_sample,
        "samples_per_channel": samples_per_channel,
        "event_count": 1,
        "gain_events": [event],
        "bench_gain_indices": [gain, gain],
        "gain_index_range": [0, 70],
        "ownership_epoch": 7,
        "tandem_transition_count": index + 1,
    }
    measurement_metadata = {
        **metadata,
        "buffer_sequence": settling_buffer + 1,
        "first_sample_sequence": settling_first_sample + samples_per_channel,
        "event_count": 0,
        "gain_events": [],
    }
    return {
        "level_index": index,
        "tx2_gain_requested_db": level,
        "summary": _summary(),
        "measurements": [{"metadata": measurement_metadata}],
        "settling": {"trace": [{"metadata": metadata}]},
    }


def _passing_report() -> dict:
    levels = (-60.0, -30.0, -60.0)
    return {
        "modes": [
            {
                "mode": MODE_MANUAL,
                "cells": [
                    _ordinary_cell(index, level, tone_dbfs=level + 5.0)
                    for index, level in enumerate(levels)
                ],
            },
            {
                "mode": MODE_NATIVE,
                "cells": [
                    _ordinary_cell(
                        index,
                        level,
                        gain=55.0 if level == min(levels) else 25.0,
                    )
                    for index, level in enumerate(levels)
                ],
            },
            {
                "mode": MODE_TANDEM,
                "cells": [
                    _tandem_cell(index, level) for index, level in enumerate(levels)
                ],
            },
        ]
    }


def _provider_gap_report() -> dict:
    """Model the accepted/rejected-buffer pattern observed on the USB probe."""

    levels = (-61.0, -45.0, -30.0, -45.0, -61.0)
    samples = 1_024
    first_sample_base = 10_000
    template = _tandem_cell(0, levels[0])["settling"]["trace"][0]["metadata"]

    def metadata(
        buffer_sequence: int,
        transition_count: int,
        gain: int,
        *,
        event_sequence: int | None = None,
    ) -> dict:
        result = copy.deepcopy(template)
        first_sample = first_sample_base + buffer_sequence * samples
        events = []
        if event_sequence is not None:
            events.append(
                {
                    "sample_sequence": first_sample + 100,
                    "event_sequence": event_sequence,
                    "direction": int(TandemEventDirection.INCREASE),
                    "rx1_gain_index": gain,
                    "rx2_gain_index": gain,
                }
            )
        result.update(
            {
                "buffer_sequence": buffer_sequence,
                "first_sample_sequence": first_sample,
                "samples_per_channel": samples,
                "event_count": len(events),
                "gain_events": events,
                "bench_gain_indices": [gain, gain],
                "gain_index_range": [0, 65],
                "tandem_transition_count": transition_count,
            }
        )
        return result

    def cell(
        index: int,
        settling: list[dict],
        measurement: dict,
    ) -> dict:
        return {
            "level_index": index,
            "tx2_gain_requested_db": levels[index],
            "summary": _summary(),
            "settling": {"trace": [{"metadata": item} for item in settling]},
            "measurements": [{"metadata": measurement}],
        }

    tandem = [
        cell(0, [metadata(25, 13, 65, event_sequence=13)], metadata(26, 13, 65)),
        cell(1, [metadata(27, 13, 65)], metadata(28, 13, 65)),
        cell(2, [metadata(31, 15, 63)], metadata(32, 15, 63)),
        cell(
            3,
            [
                metadata(33, 16, 64, event_sequence=16),
                metadata(35, 17, 65),
            ],
            metadata(36, 17, 65),
        ),
        cell(4, [metadata(37, 17, 65)], metadata(38, 17, 65)),
    ]
    return {
        "modes": [
            {
                "mode": MODE_MANUAL,
                "cells": [
                    _ordinary_cell(index, level, tone_dbfs=level + 5.0)
                    for index, level in enumerate(levels)
                ],
            },
            {
                "mode": MODE_NATIVE,
                "cells": [
                    _ordinary_cell(
                        index,
                        level,
                        gain=55.0 if level == min(levels) else 25.0,
                    )
                    for index, level in enumerate(levels)
                ],
            },
            {"mode": MODE_TANDEM, "cells": tandem},
        ]
    }


def test_matrix_verdict_requires_absolute_quality_and_bidirectional_control() -> None:
    evaluation = evaluate_matrix(_passing_report())
    assert evaluation["verdict"] == "pass"
    assert evaluation["failures"] == []
    assert len(evaluation["comparisons"]) == 3
    assert evaluation["tandem_evidence"]["gain_index_span"] == 1

    failed = _passing_report()
    failed["modes"][1]["cells"][0]["summary"]["quality_valid"] = False
    evaluation = evaluate_matrix(failed)
    assert evaluation["verdict"] == "fail"
    assert any("native_slow_attack" in item for item in evaluation["failures"])


def test_provider_gap_uses_endpoint_accounting_and_allows_deadband_and_clamp() -> None:
    evaluation = evaluate_matrix(_provider_gap_report())

    assert evaluation["verdict"] == "pass"
    tandem = evaluation["tandem_evidence"]
    assert tandem["directions"] == [int(TandemEventDirection.INCREASE)]
    assert tandem["proven_directions"] == [
        int(TandemEventDirection.INCREASE),
        int(TandemEventDirection.DECREASE),
    ]
    response = tandem["stimulus_response"]
    assert [item["evidence_source"] for item in response] == [
        "explicit_event",
        "deadband",
        "gap_accounted_endpoint",
        "explicit_event",
        "clamp",
    ]
    assert response[2]["settled_gain_delta"] == -2
    assert response[2]["transition_count_delta"] == 2
    assert response[2]["missing_frame_count"] == 2
    assert response[2]["hidden_transition_count"] == 2
    assert response[3]["settled_gain_delta"] == 2
    assert response[3]["transition_count_delta"] == 2
    assert response[3]["hidden_transition_count"] == 1


def test_primed_initial_weak_clamp_needs_no_visible_increase() -> None:
    report = _provider_gap_report()
    first = report["modes"][2]["cells"][0]["settling"]["trace"][0]["metadata"]
    first["event_count"] = 0
    first["gain_events"] = []

    evaluation = evaluate_matrix(report)

    assert evaluation["verdict"] == "pass"
    initial = evaluation["tandem_evidence"]["stimulus_response"][0]
    assert initial["evidence_source"] == "clamp"
    assert not initial["direction_proven"]


@pytest.mark.parametrize(
    ("gain", "message"),
    [
        (65, "changed transition count without moving"),
        (66, "wrong direction"),
        (62, "movement exceeds"),
    ],
)
def test_provider_gap_rejects_static_wrong_or_impossible_endpoint_movement(
    gain: int, message: str
) -> None:
    report = _provider_gap_report()
    cell = report["modes"][2]["cells"][2]
    for section in (cell["settling"]["trace"], cell["measurements"]):
        for frame in section:
            frame["metadata"]["bench_gain_indices"] = [gain, gain]
            if gain > 65:
                frame["metadata"]["gain_index_range"] = [0, 70]

    with pytest.raises(EvidenceInvalid, match=message):
        evaluate_matrix(report)


def test_wholly_deadband_trajectory_does_not_prove_both_directions() -> None:
    report = _provider_gap_report()
    for cell in report["modes"][2]["cells"][1:]:
        for section in (cell["settling"]["trace"], cell["measurements"]):
            for frame in section:
                metadata = frame["metadata"]
                metadata["event_count"] = 0
                metadata["gain_events"] = []
                metadata["tandem_transition_count"] = 13
                metadata["bench_gain_indices"] = [65, 65]

    evaluation = evaluate_matrix(report)

    assert evaluation["verdict"] == "fail"
    assert evaluation["tandem_evidence"]["proven_directions"] == []
    assert any("louder-TX decrease" in reason for reason in evaluation["failures"])


def test_initial_increase_cannot_substitute_for_quieter_return_response() -> None:
    report = _passing_report()
    returned_weak = report["modes"][2]["cells"][-1]
    for section in (returned_weak["settling"]["trace"], returned_weak["measurements"]):
        for frame in section:
            metadata = frame["metadata"]
            metadata["event_count"] = 0
            metadata["gain_events"] = []
            metadata["tandem_transition_count"] = 2
            metadata["bench_gain_indices"] = [50, 50]

    evaluation = evaluate_matrix(report)

    assert evaluation["verdict"] == "fail"
    assert evaluation["tandem_evidence"]["proven_directions"] == [
        int(TandemEventDirection.DECREASE)
    ]
    assert not evaluation["tandem_evidence"]["stimulus_response"][-1][
        "direction_proven"
    ]
    assert any("quieter-TX increase" in reason for reason in evaluation["failures"])


def test_native_gain_response_requires_recovery_on_returned_weak_level() -> None:
    report = _passing_report()
    returned_weak = report["modes"][1]["cells"][-1]
    returned_weak["measurements"][0]["rx_state_after"]["gains_db"] = [25.0, 24.5]

    evaluation = evaluate_matrix(report)

    assert evaluation["verdict"] == "fail"
    native = evaluation["native_gain_evidence"]
    assert native["outbound_weak_minus_strong_gain_db"] == [30.0, 30.0]
    assert native["return_weak_minus_strong_gain_db"] == [0.0, 0.0]
    assert any("return leg" in reason for reason in evaluation["failures"])


@pytest.mark.parametrize(
    ("first_sequence", "transition_count", "first_gain"),
    [
        pytest.param(3, 6, 48, id="first-session-seq3-through6-count6"),
        pytest.param(4, 8, 57, id="persisted-count-seq4-through7-count8"),
    ],
)
def test_first_hardware_frame_accepts_independent_counter_baselines(
    first_sequence: int, transition_count: int, first_gain: int
) -> None:
    report = _passing_report()
    cell = report["modes"][2]["cells"][0]
    settling = cell["settling"]["trace"][0]["metadata"]
    first_sample = settling["first_sample_sequence"]
    settling["gain_events"] = [
        {
            "sample_sequence": first_sample + 100 + offset * 100,
            "event_sequence": sequence,
            "direction": int(TandemEventDirection.INCREASE),
            "rx1_gain_index": gain,
            "rx2_gain_index": gain,
        }
        for offset, (sequence, gain) in enumerate(
            zip(
                range(first_sequence, first_sequence + 4),
                range(first_gain, first_gain + 4),
                strict=True,
            )
        )
    ]
    settling["event_count"] = 4
    settling["tandem_transition_count"] = transition_count
    final_gain = first_gain + 3
    settling["bench_gain_indices"] = [final_gain, final_gain]
    measurement = cell["measurements"][0]["metadata"]
    measurement["tandem_transition_count"] = transition_count
    measurement["bench_gain_indices"] = [final_gain, final_gain]

    evidence = _observed_tandem_evidence([cell])

    assert evidence["event_count"] == 4
    assert evidence["unrepresented_transition_count"] == transition_count - 4
    assert evidence["verified_gain_step_count"] == 3


def test_matrix_rejects_mismatched_level_trajectory_as_invalid_evidence() -> None:
    report = copy.deepcopy(_passing_report())
    report["modes"][2]["cells"][1]["tx2_gain_requested_db"] = -31.0
    with pytest.raises(Exception, match="identical TX trajectory"):
        evaluate_matrix(report)


def _tandem_frames(report: dict) -> list[dict]:
    cells = report["modes"][2]["cells"]
    return [
        frame["metadata"]
        for cell in cells
        for section in (cell["settling"]["trace"], cell["measurements"])
        for frame in section
    ]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("stream_id", 100, "stream_id changed"),
        ("ownership_epoch", 8, "ownership epoch changed"),
    ],
)
def test_tandem_evidence_requires_one_stream_and_epoch(
    field: str, value: int, message: str
) -> None:
    report = _passing_report()
    _tandem_frames(report)[2][field] = value

    with pytest.raises(EvidenceInvalid, match=message):
        evaluate_matrix(report)


def test_tandem_evidence_requires_matching_forward_frame_counters() -> None:
    report = _passing_report()
    _tandem_frames(report)[2]["buffer_sequence"] += 1

    with pytest.raises(EvidenceInvalid, match="buffer and sample sequence"):
        evaluate_matrix(report)


def test_adjacent_tandem_frames_cannot_hide_a_transition() -> None:
    report = _passing_report()
    _tandem_frames(report)[2]["tandem_transition_count"] += 1

    with pytest.raises(EvidenceInvalid, match="lost transition event evidence"):
        evaluate_matrix(report)


def test_tandem_event_sequence_and_exact_direction_step_are_required() -> None:
    report = _passing_report()
    second_event = _tandem_frames(report)[2]["gain_events"][0]
    second_event["event_sequence"] = 1
    with pytest.raises(EvidenceInvalid, match="event sequence did not advance"):
        evaluate_matrix(report)

    report = _passing_report()
    second_frame = _tandem_frames(report)[2]
    second_frame["gain_events"][0]["rx1_gain_index"] = 51
    second_frame["gain_events"][0]["rx2_gain_index"] = 51
    second_frame["bench_gain_indices"] = [51, 51]
    with pytest.raises(EvidenceInvalid, match=r"exact \+/-1 direction step"):
        evaluate_matrix(report)


def test_tandem_events_must_correlate_with_each_tx_level_transition() -> None:
    report = _passing_report()
    frames = _tandem_frames(report)
    for frame_index, gain in ((2, 52), (4, 53)):
        event = frames[frame_index]["gain_events"][0]
        event["direction"] = int(TandemEventDirection.INCREASE)
        event["rx1_gain_index"] = gain
        event["rx2_gain_index"] = gain
        frames[frame_index]["bench_gain_indices"] = [gain, gain]
        frames[frame_index + 1]["bench_gain_indices"] = [gain, gain]

    with pytest.raises(EvidenceInvalid, match="louder TX step"):
        evaluate_matrix(report)


def test_tandem_events_are_globally_sample_ordered() -> None:
    report = _passing_report()
    first_frame = _tandem_frames(report)[0]
    first_event = first_frame["gain_events"][0]
    first_frame["gain_events"].append(
        {
            **first_event,
            "sample_sequence": first_event["sample_sequence"] - 1,
            "event_sequence": 2,
            "direction": int(TandemEventDirection.DECREASE),
            "rx1_gain_index": 50,
            "rx2_gain_index": 50,
        }
    )
    first_frame["event_count"] = 2
    first_frame["tandem_transition_count"] = 2
    first_frame["bench_gain_indices"] = [50, 50]

    with pytest.raises(EvidenceInvalid, match="globally sample ordered"):
        evaluate_matrix(report)


def test_accounted_frame_gap_can_explain_unobserved_transition() -> None:
    report = _passing_report()
    cells = report["modes"][2]["cells"][:2]
    second_settle = cells[1]["settling"]["trace"][0]["metadata"]
    second_measurement = cells[1]["measurements"][0]["metadata"]
    samples = second_settle["samples_per_channel"]
    second_settle["buffer_sequence"] += 1
    second_settle["first_sample_sequence"] += samples
    second_settle["gain_events"][0]["sample_sequence"] += samples
    second_settle["tandem_transition_count"] = 3
    second_settle["gain_events"][0]["event_sequence"] = 3
    second_measurement["buffer_sequence"] += 1
    second_measurement["first_sample_sequence"] += samples
    second_measurement["tandem_transition_count"] = 3

    evidence = _observed_tandem_evidence(cells)

    assert evidence["missing_frame_count"] == 1
    assert evidence["unrepresented_transition_count"] == 1
    assert evidence["event_sequence_hole_count"] == 1
    assert evidence["unobserved_event_count"] == 1


def test_first_frame_transition_baseline_cannot_pay_a_later_event_hole() -> None:
    report = _passing_report()
    frames = _tandem_frames(report)
    for frame in frames:
        frame["tandem_transition_count"] += 1
    frames[2]["gain_events"][0]["event_sequence"] = 3
    frames[4]["gain_events"][0]["event_sequence"] = 4

    with pytest.raises(EvidenceInvalid, match="locally unrepresented transitions"):
        evaluate_matrix(report)
