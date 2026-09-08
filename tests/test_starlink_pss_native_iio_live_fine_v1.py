from __future__ import annotations

import hashlib
import json
import struct
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pluto_plus.hardware.pss_iio import (
    PSS_PACKET_HEADER,
    PSS_PACKET_MAGIC,
    PssFinePacket,
)

import scripts.starlink_pss_native_iio_live_fine_v1 as runner


def _analysis(
    *, score: float, residual: float, period: float, edge_hits: int = 0
) -> dict[str, Any]:
    return {
        "normalized_score_median": score,
        "residual_max_abs_source_samples": residual,
        "fitted_period_source_samples": period,
        "aperture_edge_hits": edge_hits,
    }


def _blocks(
    *, matched_a: dict[str, Any], mismatch: dict[str, Any], matched_b: dict[str, Any]
) -> dict[str, Any]:
    return {
        "matched_a": {"analysis": matched_a},
        "energy_matched_mismatch": {"analysis": mismatch},
        "matched_b": {"analysis": matched_b},
    }


def test_fine_policy_requires_two_matched_tracks_around_the_same_rf_control() -> None:
    profile = runner.RATE_PROFILES[30]
    blocks = _blocks(
        matched_a=_analysis(score=0.40, residual=0.5, period=40_000.04),
        mismatch=_analysis(score=0.04, residual=20.0, period=40_001.0),
        matched_b=_analysis(score=0.35, residual=0.6, period=40_000.05),
    )

    result = runner.evaluate_bracket(blocks, profile=profile)
    assert result["qualified"] is True
    assert result["matched_to_mismatch_median_ratio"] == pytest.approx(8.75)

    blocks["energy_matched_mismatch"]["analysis"] = _analysis(
        score=0.30, residual=20.0, period=40_001.0
    )
    assert runner.evaluate_bracket(blocks, profile=profile)["qualified"] is False


def test_latest_passing_coarse_window_seeds_fine_timing() -> None:
    point = {
        "coarse_windows": [
            {
                "peak_to_median": 1.0,
                "robust_z": 7.0,
                "candidate_start_index_source_center": 10,
                "estimated_frame_period_source_samples": 40_000.0,
            },
            {
                "peak_to_median": 1.2,
                "robust_z": 7.0,
                "candidate_start_index_source_center": 20,
                "estimated_frame_period_source_samples": 40_000.25,
            },
            {
                "peak_to_median": 1.3,
                "robust_z": 8.0,
                "candidate_start_index_source_center": 30,
                "estimated_frame_period_source_samples": 40_000.125,
            },
        ]
    }

    assert runner._last_passing_anchor(point) == (30.0, 40_000.125)


def _fine_packet_document() -> dict[str, Any]:
    center = 1_000_000
    lag = -7
    winner = center + lag
    words = [0] * 26
    words[0] = PSS_PACKET_MAGIC
    words[1] = PSS_PACKET_HEADER
    words[2] = runner.REQUEST_BASE
    words[3:7] = [center & 0xFFFFFFFF, center >> 32] * 2
    words[7] = lag & 0xFFFFFFFF
    words[8:10] = [winner & 0xFFFFFFFF, winner >> 32]
    words[10] = runner._generation(0, 0)
    words[11:19] = [20_000, 0, 0, 0, 100_000, 0, runner.COEFFICIENT_ENERGY, 0]
    packet = PssFinePacket.decode(struct.pack("<26I", *words), rate_msps=30)
    return runner.cabled._packet_document(packet, 0)


def test_fine_packet_replay_is_bound_to_its_exact_abi_words() -> None:
    document = _fine_packet_document()
    packet = runner._decode_packet(document, rate_msps=30)
    assert packet.request_id == runner.REQUEST_BASE
    assert packet.lag == -7

    document["winner_timestamp"] += 1
    with pytest.raises(runner.QualificationError, match="encoded words"):
        runner._decode_packet(document, rate_msps=30)


def test_three_brackets_use_sealed_generations_and_matched_control_matched_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = runner.RATE_PROFILES[30]
    calls: list[dict[str, Any]] = []

    def block(_client: object, **values: Any) -> dict[str, Any]:
        calls.append(values)
        matched = values["role"] != "energy_matched_mismatch"
        period = 40_000.04 if matched else 40_001.0
        score = 0.4 if matched else 0.04
        results = [
            {"winner_timestamp": values["anchor"] + (ordinal + 1) * values["period"]}
            for ordinal in range(runner.RESULTS_PER_BLOCK)
        ]
        return {
            "role": values["role"],
            "results": results,
            "analysis": _analysis(
                score=score,
                residual=0.5 if matched else 20.0,
                period=period,
            ),
        }

    monkeypatch.setattr(runner, "_run_block", block)
    brackets, evaluation = runner._run_brackets(
        object(), profile=profile, anchor=1_000_000.0, period=40_000.0
    )

    assert evaluation["qualified"] is True
    assert evaluation["qualifying_bracket_ordinals"] == [1, 2, 3]
    assert [value["role"] for value in calls] == list(runner.BRACKET_ROLES) * 3
    assert [value["generation"] for value in calls] == [
        runner._generation(bracket, role) for bracket in range(3) for role in range(3)
    ]
    assert [value["request_base"] for value in calls] == [
        runner._request_base(bracket, role) for bracket in range(3) for role in range(3)
    ]
    assert len(brackets) == 3


def _compact_map(generation: int) -> dict[str, int]:
    start = 100_000 + (generation - 1) * runner.v3.MAP_SPAN
    return {
        "generation": generation,
        "canonical_start_index": start,
        "source_start_index": start * 2,
        "peak_bin": 0,
        "peak_score": 100,
    }


def _valid_negative_point(ordinal: int, offset_hz: int) -> dict[str, Any]:
    first_discard_generation = (ordinal - 1) * runner.v3.MAPS_PER_POINT + 1
    discarded = [
        _compact_map(first_discard_generation + index)
        for index in range(runner.v3.RETUNE_DISCARD_MAPS)
    ]
    first_generation = first_discard_generation + runner.v3.RETUNE_DISCARD_MAPS
    retained = [
        _compact_map(first_generation + index)
        for index in range(runner.v3.POINT_MAP_COUNT)
    ]
    windows: list[dict[str, Any]] = []
    for index in range(runner.v3.POINT_WINDOW_COUNT):
        reference = retained[index]
        newest = retained[index + 2]
        candidate = reference["canonical_start_index"] + 1_000
        windows.append(
            {
                "phase_bin": 1_000,
                "drift_bins_per_64_frames": 0,
                "combined_score": 100,
                "combined_median": 100.0,
                "median_absolute_deviation": 10.0,
                "peak_to_median": 1.0,
                "robust_z": 1.0,
                "candidate_start_index_canonical": candidate,
                "candidate_start_index_source_center": candidate * 2,
                "estimated_frame_period_canonical_samples": 20_000.0,
                "estimated_frame_period_source_samples": 40_000.0,
                "reference_generation": reference["generation"],
                "newest_generation": newest["generation"],
                "reference_start_index_canonical": reference["canonical_start_index"],
                "newest_start_index_canonical": newest["canonical_start_index"],
            }
        )
    return {
        "role": runner.TRIGGER_ROLE,
        "ordinal": ordinal,
        "offset_hz": offset_hz,
        "base_if_hz": 1_937_500_000,
        "requested_lo_hz": 1_937_500_000 + offset_hz,
        "readback_lo_hz": 1_937_500_000 + offset_hz,
        "started_at": "2026-09-08T00:00:00+00:00",
        "completed_at": "2026-09-08T00:00:01+00:00",
        "retained_elapsed_seconds": 1.0,
        "settle_seconds": runner.v3.RETUNE_SETTLE_SECONDS,
        "discarded_map_count": runner.v3.RETUNE_DISCARD_MAPS,
        "discarded_maps": discarded,
        "complete_maps": runner.v3.POINT_MAP_COUNT,
        "coarse_window_count": runner.v3.POINT_WINDOW_COUNT,
        "coarse_windows": windows,
        "first_maps": retained[:8],
        "last_maps": retained[-8:],
        "metrics": runner.v3.trajectory_metrics(windows),
    }


class _Attribute:
    def __init__(self, value: int):
        self.value = str(value)


def test_no_trigger_run_consumes_one_complete_scan_and_restores_rx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_active = False
    coefficient = tmp_path / "matched.mem"
    coefficient.write_bytes(b"exact matched fixture")
    control = tmp_path / "control.mem"
    control.write_bytes(b"exact control fixture")
    control_evidence = tmp_path / "control.json"
    control_evidence.write_text('{"fixture":true}\n')
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
    tracker = SimpleNamespace(
        attrs={
            "schedule_submitted": _Attribute(0),
            "packets_delivered": _Attribute(0),
            "buffer_push_failures": _Attribute(0),
            "packet_validation_failures": _Attribute(0),
            "fault_flags": _Attribute(0),
            "active_coefficient_generation": _Attribute(0),
        }
    )
    phase_map = SimpleNamespace(
        attrs={
            "maps_delivered": _Attribute(0),
            "chunks_delivered": _Attribute(0),
            "buffer_push_failures": _Attribute(0),
            "fault_flags": _Attribute(0),
        }
    )

    class Client:
        context = object()

        def __init__(self) -> None:
            self.tracker = tracker
            self.phase_map = phase_map
            self.open_count = 0

        def load_coefficient_file(self, _path: Path, *, generation: int) -> None:
            tracker.attrs["active_coefficient_generation"].value = str(generation)

        def open_maps(self, **_kwargs: Any) -> None:
            self.open_count += 1

        def close_maps(self) -> None:
            pass

        def close_fine(self) -> None:
            pass

        def close(self) -> None:
            assert lock_active

    class Stream:
        def __init__(self, _client: object, *, rate_msps: int) -> None:
            assert rate_msps == 30
            self.count = 0
            self.digest = hashlib.sha256()

    client = Client()

    def capture(
        _client: object, stream: Stream, *, ordinal: int, offset_hz: int, **_kwargs: Any
    ) -> dict[str, Any]:
        stream.count += runner.v3.MAPS_PER_POINT
        phase_map.attrs["maps_delivered"].value = str(stream.count)
        phase_map.attrs["chunks_delivered"].value = str(
            stream.count * runner.PSS_MAP_CHUNKS
        )
        return _valid_negative_point(ordinal, offset_hz)

    @contextmanager
    def locked(serial: str) -> Any:
        nonlocal lock_active
        assert serial == runner.RX_SERIAL
        lock_active = True
        try:
            yield
        finally:
            lock_active = False

    original = {
        "phy_rate": 30_720_000,
        "adc_rate": 30_720_000,
        "bandwidth": 18_000_000,
        "gain_mode": "slow_attack",
        "lo": 2_400_000_000,
        "lo_powerdown": 0,
    }
    selected = {
        "phy_rate": 30_000_000,
        "adc_rate": 30_000_000,
        "bandwidth": 20_000_000,
        "gain_mode": "slow_attack",
        "lo": 1_937_500_000,
        "lo_powerdown": 0,
    }
    monkeypatch.setattr(runner, "acquire_radio_lock", locked)
    monkeypatch.setattr(
        runner.v2,
        "_deployment_binding",
        lambda *_a, **_k: {
            "receipt": {
                "path": "/evidence/deployment.json",
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
    monkeypatch.setattr(
        runner,
        "_load_control_evidence",
        lambda: {"mask": {"construction": "exact-test-control"}},
    )
    monkeypatch.setattr(runner, "CONTROL_PATH", control)
    monkeypatch.setattr(
        runner, "CONTROL_SHA256", hashlib.sha256(control.read_bytes()).hexdigest()
    )
    monkeypatch.setattr(runner, "CONTROL_EVIDENCE_PATH", control_evidence)
    monkeypatch.setattr(runner.PssIioClient, "connect", lambda *_a, **_k: client)
    monkeypatch.setattr(runner, "_configure_rx", lambda *_a, **_k: (original, selected))
    monkeypatch.setattr(runner, "_restore_rx", lambda *_a, **_k: original)
    monkeypatch.setattr(runner.v2, "ContinuousMapStream", Stream)
    monkeypatch.setattr(runner.v3, "_capture_point", capture)
    monkeypatch.setitem(runner.RATE_PROFILES, 30, profile)

    receipt = runner.run(
        tmp_path / "run",
        profile=profile,
        on_if_hz=1_937_500_000,
        deployment_receipt=tmp_path / "deployment.json",
        known_hosts_file=tmp_path / "known_hosts",
        reboot_receipts=[],
        firmware_source_commit="a" * 40,
        ppu_source_commit="b" * 40,
    )

    assert receipt["outcome"] == "pass"
    assert receipt["pss_detected"] is False
    assert receipt["fine_timing_qualified"] is False
    assert receipt["stream"]["complete_maps"] == runner.v3.EXPECTED_TOTAL_MAPS // 3
    assert client.open_count == 1
    assert receipt["cleanup"]["rx_restored"] == original

    analysis = runner.replay(
        receipt_path=Path(receipt["receipt"]),
        output=tmp_path / "run" / "replay-analysis.json",
    )
    assert analysis["outcome"] == "pass"
    assert analysis["pss_detected"] is False

    tampered = json.loads(Path(receipt["receipt"]).read_text())
    tampered["stream"]["fine_packets"] = 1
    Path(receipt["receipt"]).write_text(json.dumps(tampered))
    with pytest.raises(runner.QualificationError, match="stream accounting"):
        runner.replay(
            receipt_path=Path(receipt["receipt"]),
            output=tmp_path / "run" / "must-not-pass.json",
        )
