from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pluto_plus.hardware.pss_iio import (
    PSS_MAP_CANONICAL_SPAN,
    PSS_MAP_VERSIONS,
    PssPhaseMap,
)

import scripts.starlink_pss_native_iio_live_campaign_v1 as runner
import scripts.starlink_pss_native_iio_qualify_v1 as qualifier


def _map(generation: int) -> PssPhaseMap:
    bins = tuple([100] * 20_000)
    return PssPhaseMap(
        PSS_MAP_VERSIONS[30],
        generation,
        100_000 + (generation - 1) * PSS_MAP_CANONICAL_SPAN,
        bins,
    )


def test_frequency_plan_rejects_invalid_or_overlapping_slice() -> None:
    runner._validate_frequency_plan(1_937_500_000, 1_887_500_000)
    with pytest.raises(ValueError, match="off-slice"):
        runner._validate_frequency_plan(1_937_500_000, 1_927_500_000)
    with pytest.raises(ValueError, match="on-channel"):
        runner._validate_frequency_plan(True, 1_887_500_000)


def test_campaign_uses_one_map_epoch_and_holds_lock_through_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    lock_active = False

    @contextmanager
    def locked(serial: str) -> Any:
        nonlocal lock_active
        assert serial == runner.RX_SERIAL
        lock_active = True
        events.append("lock_enter")
        try:
            yield
        finally:
            assert "context_close" in events
            events.append("lock_exit")
            lock_active = False

    class Attribute:
        def __init__(self, value: int):
            self.value = str(value)

    phase_device = SimpleNamespace(
        attrs={
            "maps_delivered": Attribute(37),
            "chunks_delivered": Attribute(7_400),
            "buffer_push_failures": Attribute(0),
            "fault_flags": Attribute(0),
        }
    )
    tracker = SimpleNamespace(
        attrs={
            "active_coefficient_generation": Attribute(23),
            "buffer_push_failures": Attribute(0),
            "packet_validation_failures": Attribute(0),
            "fault_flags": Attribute(0),
        }
    )
    phy = object()

    class Context:
        def find_device(self, name: str) -> object | None:
            return phy if name == "ad9361-phy" else None

    class Client:
        def __init__(self) -> None:
            self.context = Context()
            self.phase_map = phase_device
            self.tracker = tracker
            self.generation = 0
            self.open_count = 0

        def load_coefficient_file(self, *_args: Any, **_kwargs: Any) -> None:
            assert lock_active

        def open_maps(self, **_kwargs: Any) -> None:
            assert lock_active
            self.open_count += 1
            events.append("map_open")

        def read_maps(self, _reassembler: object) -> tuple[PssPhaseMap, ...]:
            assert lock_active
            self.generation += 1
            return (_map(self.generation),)

        def close_maps(self) -> None:
            assert lock_active
            events.append("map_close")

        def close(self) -> None:
            assert lock_active
            events.append("context_close")

    client = Client()
    coefficient = tmp_path / "coefficient.mem"
    coefficient.write_bytes(b"one exact coefficient fixture")
    profile = runner.RateProfile(
        rate_msps=30,
        firmware=qualifier.EXPECTED_FIRMWARE[30],
        bandwidth_hz=20_000_000,
        period_samples=40_000,
        aperture_samples=60,
        host_lead_samples=6_000_000,
        coefficient_generation=23,
        coefficient_path=coefficient,
        coefficient_sha256=hashlib.sha256(coefficient.read_bytes()).hexdigest(),
        waveform_path=tmp_path / "unused.bin",
        waveform_sha256="0" * 64,
        waveform_bytes=0,
    )

    @dataclass
    class Coarse:
        phase_bin: int
        drift_bins_per_64_frames: int
        combined_score: int
        combined_median: float
        median_absolute_deviation: float
        peak_to_median: float
        robust_z: float
        candidate_start_index_canonical: int
        candidate_start_index_source_center: int
        estimated_frame_period_canonical_samples: float
        estimated_frame_period_source_samples: float
        reference_generation: int
        newest_generation: int
        reference_start_index_canonical: int
        newest_start_index_canonical: int

    def analyze(maps: tuple[PssPhaseMap, ...], **_kwargs: Any) -> Coarse:
        reference = maps[0]
        candidate = reference.start_index + 1_000
        return Coarse(
            phase_bin=1_000,
            drift_bins_per_64_frames=0,
            combined_score=330,
            combined_median=300.0,
            median_absolute_deviation=20.0,
            peak_to_median=1.1,
            robust_z=4.0,
            candidate_start_index_canonical=candidate,
            candidate_start_index_source_center=candidate * 2,
            estimated_frame_period_canonical_samples=20_000.0,
            estimated_frame_period_source_samples=40_000.0,
            reference_generation=reference.generation,
            newest_generation=maps[-1].generation,
            reference_start_index_canonical=reference.start_index,
            newest_start_index_canonical=maps[-1].start_index,
        )

    clock_value = -0.11

    def clock() -> float:
        nonlocal clock_value
        clock_value += 0.11
        return clock_value

    monkeypatch.setattr(runner, "acquire_radio_lock", locked)
    monkeypatch.setattr(
        runner.PssIioClient, "connect", lambda *_args, **_kwargs: client
    )
    monkeypatch.setattr(
        runner,
        "_configure_rx",
        lambda *_args, **_kwargs: (
            {
                "phy_rate": 30_720_000,
                "adc_rate": 30_720_000,
                "bandwidth": 18_000_000,
                "gain_mode": "slow_attack",
                "lo": 2_400_000_000,
                "lo_powerdown": 0,
            },
            {
                "phy_rate": 30_000_000,
                "adc_rate": 30_000_000,
                "bandwidth": 20_000_000,
                "gain_mode": "slow_attack",
                "lo": 1_937_500_000,
                "lo_powerdown": 0,
            },
        ),
    )
    monkeypatch.setattr(runner, "_required_channel", lambda *_args: object())
    monkeypatch.setattr(
        runner, "_write_number", lambda _channel, _name, value, _tolerance: value
    )
    monkeypatch.setattr(runner, "analyze_phase_maps", analyze)
    monkeypatch.setattr(runner.time, "monotonic", clock)
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)

    def restore(*_args: Any) -> dict[str, Any]:
        assert lock_active
        events.append("restore")
        return {
            "phy_rate": 30_720_000,
            "adc_rate": 30_720_000,
            "bandwidth": 18_000_000,
            "gain_mode": "slow_attack",
            "lo": 2_400_000_000,
            "lo_powerdown": 0,
        }

    monkeypatch.setattr(runner, "_restore_rx", restore)

    receipt = runner.run(
        tmp_path / "campaign",
        profile=profile,
        on_lo_hz=1_937_500_000,
        off_lo_hz=1_887_500_000,
        role_duration_seconds=1.0,
    )

    assert receipt["outcome"] == "pass"
    assert receipt["transmitter_opened"] is False
    assert receipt["pss_detected"] is False
    assert client.open_count == 1
    assert client.generation == 37
    assert receipt["stream"]["complete_maps"] == 37
    assert receipt["stream"]["transition_discard_maps"] == 10
    assert [value["complete_maps"] for value in receipt["roles"].values()] == [9, 9, 9]
    assert [value["discarded_map_count"] for value in receipt["transitions"]] == [5, 5]
    assert receipt["evaluation"]["gates"]["duration_qualified"] is False
    replay = qualifier.replay_campaign_run(
        receipt_path=Path(receipt["receipt"]),
        output=tmp_path / "campaign" / "replay-analysis.json",
    )
    assert replay["outcome"] == "pass"
    assert replay["pss_detected"] is False
    assert replay["evaluation"]["gates"]["duration_qualified"] is False
    receipt_path = Path(receipt["receipt"])
    tampered = json.loads(receipt_path.read_text())
    tampered["pss_detected"] = True
    receipt_path.write_text(json.dumps(tampered, indent=2, sort_keys=True) + "\n")
    with pytest.raises(qualifier.QualificationError, match="claims differ"):
        qualifier.replay_campaign_run(
            receipt_path=receipt_path,
            output=tmp_path / "campaign" / "must-not-pass.json",
        )
    assert not (tmp_path / "campaign" / "must-not-pass.json").exists()
    tampered["pss_detected"] = False
    del tampered["gates"]["single_map_epoch_exact"]
    receipt_path.write_text(json.dumps(tampered, indent=2, sort_keys=True) + "\n")
    with pytest.raises(qualifier.QualificationError, match="root contract"):
        qualifier.replay_campaign_run(
            receipt_path=receipt_path,
            output=tmp_path / "campaign" / "must-not-omit-gate.json",
        )
    assert not (tmp_path / "campaign" / "must-not-omit-gate.json").exists()
    assert events[-3:] == ["restore", "context_close", "lock_exit"]
    assert not lock_active


def test_invalid_campaign_arguments_do_not_create_output(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="role duration"):
        runner.run(
            tmp_path / "must-not-exist",
            profile=runner.RATE_PROFILES[30],
            on_lo_hz=1_937_500_000,
            off_lo_hz=1_887_500_000,
            role_duration_seconds=0.5,
        )
    assert not (tmp_path / "must-not-exist").exists()
