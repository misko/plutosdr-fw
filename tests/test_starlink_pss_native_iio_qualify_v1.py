from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import scripts.starlink_pss_native_iio_qualify_v1 as qualify


def _windows(*, positive: bool, count: int = 1_402) -> list[dict[str, Any]]:
    first_start = 100_000
    result = []
    for ordinal in range(count):
        passed = positive or ordinal == 17
        drift = 4 if positive else 0
        phase = (
            (1_000 + ordinal * drift) % qualify.FRAME_SAMPLES
            if positive
            else ordinal * 997 % 20_000
        )
        reference = first_start + ordinal * qualify.MAP_SPAN
        period = qualify.FRAME_SAMPLES + drift / 64
        result.append(
            {
                "phase_bin": phase,
                "drift_bins_per_64_frames": drift,
                "combined_score": 600 if passed else 330,
                "combined_median": 300.0,
                "median_absolute_deviation": 20.0,
                "peak_to_median": 2.0 if passed else 1.1,
                "robust_z": 10.0 if passed else 4.0,
                "candidate_start_index_canonical": reference + phase,
                "candidate_start_index_source_center": (reference + phase) * 2,
                "estimated_frame_period_canonical_samples": period,
                "estimated_frame_period_source_samples": period * 2,
                "reference_generation": ordinal + 1,
                "newest_generation": ordinal + 3,
                "reference_start_index_canonical": reference,
                "newest_start_index_canonical": reference + 2 * qualify.MAP_SPAN,
            }
        )
    return result


def _run_receipt(coefficient: Path, *, positive: bool, lo_hz: int) -> dict[str, Any]:
    windows = _windows(positive=positive)
    map_count = len(windows) + 2
    before = {
        "phy_rate": 30_720_000,
        "adc_rate": 30_720_000,
        "bandwidth": 18_000_000,
        "gain_mode": "slow_attack",
        "lo": 2_400_000_000,
        "lo_powerdown": 0,
    }
    return {
        "schema": qualify.RUN_SCHEMA,
        "outcome": "pass",
        "persistent_write": False,
        "transmitter_opened": False,
        "rate_msps": 30,
        "sample_rate_hz": 30_000_000,
        "requested_duration_seconds": 120.0,
        "coefficient": {
            "path": str(coefficient),
            "sha256": hashlib.sha256(coefficient.read_bytes()).hexdigest(),
            "generation": 23,
        },
        "receiver": {
            "serial": qualify.RECEIVER_SERIAL,
            "transport": "ethernet",
            "uri": "ip:192.168.1.17",
            "firmware": qualify.EXPECTED_FIRMWARE[30],
            "requested_lo_hz": lo_hz,
            "original": before,
            "selected": {
                "phy_rate": 30_000_000,
                "adc_rate": 30_000_000,
                "bandwidth": 20_000_000,
                "gain_mode": "slow_attack",
                "lo": lo_hz,
                "lo_powerdown": 0,
            },
        },
        "stream": {
            "elapsed_seconds": 120.01,
            "complete_maps": map_count,
            "coarse_window_count": len(windows),
            "coarse_windows": windows,
            "first_maps": [
                {
                    "generation": 1,
                    "canonical_start_index": 100_000,
                }
            ],
            "counters": {
                "maps_delivered": map_count,
                "chunks_delivered": map_count * qualify.MAP_CHUNKS,
                "map_buffer_push_failures": 0,
                "map_fault_flags": 0,
                "tracker_buffer_push_failures": 0,
                "tracker_packet_validation_failures": 0,
                "tracker_fault_flags": 0,
            },
            "map_digest_sha256": "a" * 64,
            "logical_map_bytes": map_count * qualify.FRAME_SAMPLES * 2,
            "transport_bytes": map_count * qualify.MAP_CHUNKS * 256,
        },
        "gates": {
            "duration_met": True,
            "minimum_map_count_met": True,
            "coarse_window_count_exact": True,
        },
        "cleanup": {"verified": True, "errors": [], "rx_restored": before},
    }


def _write(path: Path, value: dict[str, Any]) -> Path:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return path


def test_trajectory_metrics_separates_track_from_isolated_noise() -> None:
    positive = qualify.trajectory_metrics(_windows(positive=True, count=40))
    negative = qualify.trajectory_metrics(_windows(positive=False, count=40))

    assert positive["classification"] == "positive_track"
    assert positive["passing_windows"] == 40
    assert positive["longest_consecutive_track_windows"] == 40
    assert negative["classification"] == "negative_control"
    assert negative["passing_windows"] == 1
    assert negative["longest_consecutive_track_windows"] == 1


def test_short_trajectory_is_ambiguous() -> None:
    metrics = qualify.trajectory_metrics(_windows(positive=False, count=7))
    assert metrics["classification"] == "ambiguous"
    assert metrics["minimum_window_count_met"] is False


def test_campaign_evaluation_requires_duration_geometry_and_all_three_roles() -> None:
    positive = qualify.trajectory_metrics(_windows(positive=True, count=40))
    negative = qualify.trajectory_metrics(_windows(positive=False, count=40))
    roles = {
        "on_channel_a": {
            "metrics": positive,
            "requested_lo_hz": 1_937_500_000,
            "requested_duration_seconds": 120.0,
            "elapsed_seconds": 120.01,
        },
        "off_slice_control": {
            "metrics": negative,
            "requested_lo_hz": 1_887_500_000,
            "requested_duration_seconds": 120.0,
            "elapsed_seconds": 120.02,
        },
        "on_channel_b": {
            "metrics": positive,
            "requested_lo_hz": 1_937_500_000,
            "requested_duration_seconds": 120.0,
            "elapsed_seconds": 120.03,
        },
    }

    result = qualify.campaign_evaluation(roles)

    assert result["qualified"] is True
    assert result["off_slice_separation_hz"] == 50_000_000
    roles["on_channel_b"]["requested_duration_seconds"] = 1.0
    assert qualify.campaign_evaluation(roles)["qualified"] is False


def test_role_analysis_replays_complete_receipt(
    tmp_path: Path,
) -> None:
    coefficient = tmp_path / "coeff.mem"
    coefficient.write_bytes(b"exact coefficient")
    receipt_path = _write(
        tmp_path / "run.json",
        _run_receipt(coefficient, positive=False, lo_hz=1_887_500_000),
    )

    result = qualify.analyze_role(
        role="off_slice_control",
        receipt_path=receipt_path,
        output=tmp_path / "analysis.json",
    )

    assert result["outcome"] == "pass"
    assert result["metrics"]["classification"] == "negative_control"
    assert result["pss_detected"] is False
    assert (tmp_path / "analysis.json").stat().st_mode & 0o777 == 0o600


def test_role_analysis_rejects_trajectory_discontinuity(tmp_path: Path) -> None:
    coefficient = tmp_path / "coeff.mem"
    coefficient.write_bytes(b"exact coefficient")
    receipt = _run_receipt(coefficient, positive=False, lo_hz=1_887_500_000)
    receipt["stream"]["coarse_windows"][91]["reference_generation"] += 1

    with pytest.raises(qualify.QualificationError, match="timing identity"):
        qualify.analyze_role(
            role="off_slice_control",
            receipt_path=_write(tmp_path / "run.json", receipt),
            output=tmp_path / "analysis.json",
        )
    assert not (tmp_path / "analysis.json").exists()


def test_campaign_requires_positive_control_positive_and_frequency_separation(
    tmp_path: Path,
) -> None:
    coefficient = tmp_path / "coeff.mem"
    coefficient.write_bytes(b"exact coefficient")
    role_paths = []
    for role, positive, lo_hz in (
        ("on_channel_a", True, 1_937_500_000),
        ("off_slice_control", False, 1_887_500_000),
        ("on_channel_b", True, 1_937_500_000),
    ):
        receipt = _write(
            tmp_path / f"{role}-run.json",
            _run_receipt(coefficient, positive=positive, lo_hz=lo_hz),
        )
        analysis = tmp_path / f"{role}-analysis.json"
        qualify.analyze_role(role=role, receipt_path=receipt, output=analysis)
        role_paths.append(analysis)

    result = qualify.qualify_campaign(
        on_a=role_paths[0],
        control=role_paths[1],
        on_b=role_paths[2],
        output=tmp_path / "campaign.json",
    )

    assert result["outcome"] == "pass"
    assert result["pss_detected"] is True
    assert result["timing_trajectory_qualified"] is True
    assert result["sss_detected"] is False
    assert result["frame_lock_claim"] is False


def test_campaign_rejects_changed_source_after_role_analysis(tmp_path: Path) -> None:
    coefficient = tmp_path / "coeff.mem"
    coefficient.write_bytes(b"exact coefficient")
    receipt_path = _write(
        tmp_path / "run.json",
        _run_receipt(coefficient, positive=True, lo_hz=1_937_500_000),
    )
    analysis_path = tmp_path / "analysis.json"
    qualify.analyze_role(
        role="on_channel_a", receipt_path=receipt_path, output=analysis_path
    )
    receipt_path.write_text(receipt_path.read_text() + "\n")

    with pytest.raises(qualify.QualificationError, match="changed"):
        qualify._validate_role_analysis(analysis_path, expected_role="on_channel_a")
