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

import scripts.starlink_pss_native_iio_live_campaign_v3 as runner

ZERO_BINS = tuple([100] * 20_000)


def _map(generation: int) -> PssPhaseMap:
    return PssPhaseMap(
        PSS_MAP_VERSIONS[30],
        generation,
        100_000 + (generation - 1) * PSS_MAP_CANONICAL_SPAN,
        ZERO_BINS,
    )


def _point(offset_hz: int, *, positive: bool, median: float) -> dict[str, Any]:
    return {
        "offset_hz": offset_hz,
        "requested_lo_hz": 1_937_500_000 + offset_hz,
        "metrics": {
            "classification": "positive_track" if positive else "negative_control",
            "pass_fraction": 1.0 if positive else 0.0,
            "longest_consecutive_track_windows": 32 if positive else 0,
            "median_peak_to_median": median,
        },
    }


def test_scan_geometry_is_interleaved_and_control_remains_below_band() -> None:
    geometry = runner._scan_geometry(1_937_500_000)

    assert runner.OFFSET_ORDER_HZ[:5] == (0, 100_000, -100_000, 200_000, -200_000)
    assert len(runner.OFFSET_ORDER_HZ) == 25
    assert geometry["control_scan_upper_rf_hz"] == 10_611_200_000
    assert geometry["control_scan_clearance_hz"] == 88_800_000
    assert runner.EXPECTED_TOTAL_MAPS == 3_300


def test_campaign_requires_repeatable_positive_roles_and_a_clean_control() -> None:
    def role(positive: bool, median: float) -> dict[str, Any]:
        return {
            "points": [
                _point(offset, positive=positive and offset == 0, median=median)
                for offset in runner.OFFSET_ORDER_HZ
            ]
        }

    roles = {
        "on_channel_a": role(True, 1.30),
        "below_band_control": role(False, 1.00),
        "on_channel_b": role(True, 1.25),
    }
    result = runner.campaign_evaluation(roles)
    assert result["qualified"] is True
    assert result["positive_to_control_median_ratio"] == 1.25

    roles["below_band_control"] = role(True, 1.00)
    result = runner.campaign_evaluation(roles)
    assert result["qualified"] is False
    assert result["gates"]["below_band_control_has_no_passing_points"] is False


def test_source_checkout_attestation_rejects_a_mistyped_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit = "a" * 40
    responses: dict[tuple[str, ...], str] = {
        ("remote", "get-url", "origin"): "git@github.com:misko/pluto-plus-utils.git\n",
        ("rev-parse", "--show-toplevel"): f"{tmp_path}\n",
        ("status", "--porcelain=v1", "--untracked-files=all"): "",
    }

    def invoke(command: tuple[str, ...], **_kwargs: Any) -> SimpleNamespace:
        assert command[:3] == ("git", "-C", str(tmp_path))
        if command[3:5] == ("rev-parse", "--verify"):
            return SimpleNamespace(stdout=f"{commit}\n")
        return SimpleNamespace(stdout=responses[command[3:]])

    monkeypatch.setattr(runner.v2.subprocess, "run", invoke)
    runner.v2._verify_source_checkout(
        tmp_path,
        commit,
        label="PPU source",
        expected_origin_suffix="/misko/pluto-plus-utils",
    )

    with pytest.raises(runner.QualificationError, match="exact clean source"):
        runner.v2._verify_source_checkout(
            tmp_path,
            "b" * 40,
            label="PPU source",
            expected_origin_suffix="/misko/pluto-plus-utils",
        )


def test_scanned_campaign_uses_one_epoch_and_replays(
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
            "maps_delivered": Attribute(runner.EXPECTED_TOTAL_MAPS),
            "chunks_delivered": Attribute(
                runner.EXPECTED_TOTAL_MAPS * runner.PSS_MAP_CHUNKS
            ),
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

        def read_maps(self, _reassembler: object) -> tuple[PssPhaseMap, ...]:
            assert lock_active
            self.generation += 1
            return (_map(self.generation),)

        def close_maps(self) -> None:
            assert lock_active

        def close(self) -> None:
            assert lock_active
            events.append("context_close")

    coefficient = tmp_path / "coefficient.mem"
    coefficient.write_bytes(b"one exact scanned coefficient fixture")
    profile = runner.RateProfile(
        rate_msps=30,
        firmware=runner.v2.EXPECTED_DEPLOYMENTS[30]["firmware"],
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

    current_lo = {"value": 0}

    def analyze(maps: tuple[PssPhaseMap, ...], **_kwargs: Any) -> Coarse:
        reference = maps[0]
        candidate = reference.start_index + 1_000
        positive = current_lo["value"] == 1_937_500_000
        return Coarse(
            phase_bin=1_000,
            drift_bins_per_64_frames=0,
            combined_score=400 if positive else 100,
            combined_median=300.0,
            median_absolute_deviation=20.0,
            peak_to_median=1.25 if positive else 1.0,
            robust_z=7.0 if positive else 1.0,
            candidate_start_index_canonical=candidate,
            candidate_start_index_source_center=candidate * 2,
            estimated_frame_period_canonical_samples=20_000.0,
            estimated_frame_period_source_samples=40_000.0,
            reference_generation=reference.generation,
            newest_generation=maps[-1].generation,
            reference_start_index_canonical=reference.start_index,
            newest_start_index_canonical=maps[-1].start_index,
        )

    clock_value = 0.0

    def clock() -> float:
        nonlocal clock_value
        clock_value += 0.01
        return clock_value

    client = Client()
    monkeypatch.setattr(runner, "acquire_radio_lock", locked)
    monkeypatch.setattr(
        runner.v2,
        "_deployment_binding",
        lambda *args, **kwargs: {
            "receipt": {
                "path": "/evidence/deploy.json",
                "bytes": 1,
                "sha256": "1" * 64,
            },
            "boot_id": "11111111-1111-4111-8111-111111111111",
            "qspi_sha256": "2" * 64,
            "known_hosts": {
                "path": "/evidence/known_hosts",
                "bytes": 1,
                "sha256": "3" * 64,
            },
            "reboots": [],
            "current_boot_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    monkeypatch.setattr(runner.v2, "_verify_source_checkout", lambda *_a, **_k: None)
    monkeypatch.setattr(runner.PssIioClient, "connect", lambda *_a, **_k: client)
    monkeypatch.setattr(
        runner,
        "_configure_rx",
        lambda *_a, **_k: (
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

    def write_number(_channel: object, _name: str, value: int, _tolerance: int) -> int:
        current_lo["value"] = value
        return value

    monkeypatch.setattr(runner, "_write_number", write_number)
    monkeypatch.setattr(runner.v2, "analyze_phase_maps", analyze)
    monkeypatch.setattr(runner.time, "monotonic", clock)
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        runner,
        "_restore_rx",
        lambda *_args: {
            "phy_rate": 30_720_000,
            "adc_rate": 30_720_000,
            "bandwidth": 18_000_000,
            "gain_mode": "slow_attack",
            "lo": 2_400_000_000,
            "lo_powerdown": 0,
        },
    )
    monkeypatch.setitem(runner.RATE_PROFILES, 30, profile)

    receipt = runner.run(
        tmp_path / "campaign",
        profile=profile,
        on_if_hz=1_937_500_000,
        deployment_receipt=tmp_path / "unused-deployment.json",
        known_hosts_file=tmp_path / "unused-known-hosts",
        reboot_receipts=[],
        firmware_source_commit="a" * 40,
        ppu_source_commit="b" * 40,
    )

    assert receipt["outcome"] == "pass"
    assert receipt["pss_detected"] is True
    assert receipt["transmitter_opened"] is False
    assert client.open_count == 1
    assert client.generation == runner.EXPECTED_TOTAL_MAPS
    assert receipt["stream"]["complete_maps"] == runner.EXPECTED_TOTAL_MAPS
    assert all(
        len(value["points"]) == len(runner.OFFSET_ORDER_HZ)
        for value in receipt["roles"].values()
    )
    assert (
        receipt["roles"]["below_band_control"]["analysis"]["passing_point_count"] == 0
    )

    analysis = runner.replay(
        receipt_path=Path(receipt["receipt"]),
        output=tmp_path / "campaign" / "replay-analysis.json",
    )
    assert analysis["outcome"] == "pass"
    assert analysis["pss_detected"] is True

    tampered = json.loads(Path(receipt["receipt"]).read_text())
    tampered["roles"]["on_channel_a"]["points"][0]["discarded_maps"][0] = None
    Path(receipt["receipt"]).write_text(json.dumps(tampered))
    with pytest.raises(runner.QualificationError, match="violates its contract"):
        runner.replay(
            receipt_path=Path(receipt["receipt"]),
            output=tmp_path / "campaign" / "must-not-pass.json",
        )
    assert not (tmp_path / "campaign" / "must-not-pass.json").exists()
    assert events[-2:] == ["context_close", "lock_exit"]
