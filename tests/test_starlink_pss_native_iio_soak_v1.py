from __future__ import annotations

import hashlib
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

import scripts.starlink_pss_native_iio_soak_v1 as runner
from scripts.starlink_pss_iio_cabled_v1 import QualificationError
from scripts.starlink_pss_native_iio_soak_v1 import (
    _minimum_complete_maps,
    _record_map,
    _validate_transition,
)


def _map(generation: int, start_index: int, *, rate_msps: int = 30) -> PssPhaseMap:
    bins = [0] * 20_000
    bins[1234] = generation
    return PssPhaseMap(
        PSS_MAP_VERSIONS[rate_msps], generation, start_index, tuple(bins)
    )


def test_minimum_complete_maps_allows_only_two_boundary_maps() -> None:
    assert _minimum_complete_maps(120.0) == 1404
    assert _minimum_complete_maps(1.0) == 9
    with pytest.raises(ValueError, match="finite and positive"):
        _minimum_complete_maps(0.0)


def test_transition_requires_generation_index_and_abi_continuity() -> None:
    previous = _map(10, 5_000_000)
    current = _map(11, 5_000_000 + PSS_MAP_CANONICAL_SPAN)
    _validate_transition(previous, current)

    with pytest.raises(QualificationError, match="generation"):
        _validate_transition(previous, _map(12, current.start_index))
    with pytest.raises(QualificationError, match="start index"):
        _validate_transition(previous, _map(11, current.start_index + 1))
    with pytest.raises(QualificationError, match="ABI"):
        _validate_transition(previous, _map(11, current.start_index, rate_msps=60))


def test_record_map_hashes_full_identity_and_scales_source_index() -> None:
    phase_map = _map(7, 2_560_000)
    digest = hashlib.sha256()

    record = _record_map(phase_map, digest=digest, rate_msps=30)

    assert record == {
        "generation": 7,
        "canonical_start_index": 2_560_000,
        "source_start_index": 5_120_000,
        "peak_bin": 1234,
        "peak_score": 7,
    }
    assert digest.hexdigest() != hashlib.sha256().hexdigest()


def test_run_holds_rx_lock_through_restore_and_context_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    lock_active = False

    @contextmanager
    def locked(_serial: str) -> Any:
        nonlocal lock_active
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

    maps = tuple(_map(index + 1, index * PSS_MAP_CANONICAL_SPAN) for index in range(9))
    phase_map = SimpleNamespace(
        attrs={
            "maps_delivered": Attribute(9),
            "chunks_delivered": Attribute(1800),
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

    class Client:
        def __init__(self) -> None:
            self.phase_map = phase_map
            self.tracker = tracker
            self.reads = 0

        def load_coefficient_file(self, *_args: Any, **_kwargs: Any) -> None:
            assert lock_active

        def open_maps(self, **_kwargs: Any) -> None:
            assert lock_active
            events.append("map_open")

        def read_maps(self, _reassembler: object) -> tuple[PssPhaseMap, ...]:
            assert lock_active
            self.reads += 1
            assert self.reads == 1
            return maps

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
        firmware="test-firmware",
        bandwidth_hz=20_000_000,
        period_samples=40_000,
        aperture_samples=60,
        host_lead_samples=6_000_000,
        coefficient_generation=23,
        coefficient_path=coefficient,
        coefficient_sha256=hashlib.sha256(coefficient.read_bytes()).hexdigest(),
        waveform_path=tmp_path / "unused-waveform.bin",
        waveform_sha256="0" * 64,
        waveform_bytes=0,
    )

    @dataclass
    class Coarse:
        marker: str = "last-three"

    clock = iter((0.0, 0.0, 1.1, 1.2))
    monkeypatch.setattr(runner, "acquire_radio_lock", locked)
    monkeypatch.setattr(runner, "_receiver_uri", lambda _transport: "ip:192.0.2.1")
    monkeypatch.setattr(
        runner.PssIioClient,
        "connect",
        lambda *_args, **_kwargs: client,
    )
    configured_lo: list[int] = []

    def configure(*_args: Any, **kwargs: Any) -> tuple[dict[str, int], dict[str, int]]:
        configured_lo.append(kwargs["lo_hz"])
        return {"before": 1}, {"selected": 1}

    monkeypatch.setattr(runner, "_configure_rx", configure)

    def restore(*_args: Any) -> dict[str, bool]:
        assert lock_active
        events.append("restore")
        return {"verified": True}

    monkeypatch.setattr(runner, "_restore_rx", restore)
    monkeypatch.setattr(
        runner, "analyze_phase_maps", lambda *_args, **_kwargs: Coarse()
    )
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(clock))

    receipt = runner.run(
        tmp_path / "receipt",
        profile=profile,
        receiver_transport="ethernet",
        duration_seconds=1.0,
        rx_lo_hz=1_937_500_000,
    )

    assert receipt["outcome"] == "pass"
    assert receipt["transmitter_opened"] is False
    assert receipt["receiver"]["requested_lo_hz"] == 1_937_500_000
    assert configured_lo == [1_937_500_000]
    assert events[-3:] == ["restore", "context_close", "lock_exit"]
    assert not lock_active


@pytest.mark.parametrize("rx_lo_hz", [True, 69_999_999, 6_000_000_001])
def test_run_rejects_invalid_rx_lo_before_creating_output(
    tmp_path: Path, rx_lo_hz: Any
) -> None:
    with pytest.raises(ValueError, match="RX LO"):
        runner.run(
            tmp_path / "must-not-exist",
            profile=runner.RATE_PROFILES[30],
            receiver_transport="ethernet",
            duration_seconds=1.0,
            rx_lo_hz=rx_lo_hz,
        )
    assert not (tmp_path / "must-not-exist").exists()
