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

import scripts.starlink_pss_native_iio_live_campaign_v2 as runner


def _map(generation: int) -> PssPhaseMap:
    return PssPhaseMap(
        PSS_MAP_VERSIONS[30],
        generation,
        100_000 + (generation - 1) * PSS_MAP_CANONICAL_SPAN,
        tuple([100] * 20_000),
    )


def test_frequency_plan_uses_a_guarded_below_band_receiver_noise_control() -> None:
    geometry = runner._validate_frequency_plan(1_937_500_000)

    assert geometry["control_if_hz"] == 850_000_000
    assert geometry["control_rf_hz"] == 10_600_000_000
    assert geometry["control_upper_rf_hz"] == 10_610_000_000
    assert geometry["starlink_lower_rf_hz"] == 10_700_000_000
    assert geometry["control_guard_hz"] == 90_000_000
    with pytest.raises(TypeError, match="on-channel IF"):
        runner._validate_frequency_plan(True)


def test_deployment_binding_rejects_old_or_unqualified_profiles(
    tmp_path: Path,
) -> None:
    expected = runner.EXPECTED_DEPLOYMENTS[30]
    first_key_hash = "4" * 64
    receipt = {
        "schema_version": 2,
        "transport": "lan_ssh_frm",
        "outcome": "success",
        "error": None,
        "returned_serial": runner.RX_SERIAL,
        "returned_phy": "ad9361",
        "returned_firmware": expected["firmware"],
        "plan": {
            "host": "192.168.1.17",
            "target_serial": runner.RX_SERIAL,
            "expected_firmware": expected["firmware"],
            "mutation_profile_id": expected["profile"],
            "image_sha256": expected["image_sha256"],
            "fit_sha256": expected["fit_sha256"],
            "expected_metadata_abi": 3,
            "expected_tandem_agc": False,
            "return_iio_layout": "detector-only-1r1t-v1",
        },
        "read_only_return_attestation": {
            "serial": runner.RX_SERIAL,
            "firmware": expected["firmware"],
            "fit_sha256": expected["fit_sha256"],
            "root_marker_present": "1",
            "rx_dma_dt_state": "disabled",
            "dds_present": "0",
            "dds_dt_state": "disabled",
            "tx_dma_dt_state": "disabled",
            "tandem_present": "0",
            "tandem_dt_state": "disabled",
            "tx_lo_powerdown": "1",
            "boot_id": "11111111-1111-4111-8111-111111111111",
            "qspi_sha256": "3" * 64,
        },
        "host_key_rotation": {"replacement_known_hosts_sha256": first_key_hash},
    }
    path = tmp_path / "deployment.json"
    path.write_text(json.dumps(receipt))
    assert runner._validate_deployment(path, rate_msps=30) == receipt

    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("replacement key\n")
    final_key_hash = hashlib.sha256(known_hosts.read_bytes()).hexdigest()
    reboot = {
        "schema_version": 2,
        "outcome": "success",
        "error": None,
        "dispatch_error": None,
        "plan": {
            "schema_version": 3,
            "serial": runner.RX_SERIAL,
            "ssh_host": "192.168.1.17",
            "known_hosts_sha256": first_key_hash,
        },
        "before": {
            "serial": runner.RX_SERIAL,
            "firmware": expected["firmware"],
            "boot_id": "11111111-1111-4111-8111-111111111111",
            "capabilities": {
                "phy_model": "ad9361",
                "rx_scan_channels": [],
                "tandem_agc": False,
                "detector_only": True,
            },
        },
        "after": {
            "serial": runner.RX_SERIAL,
            "firmware": expected["firmware"],
            "boot_id": "22222222-2222-4222-8222-222222222222",
            "capabilities": {
                "phy_model": "ad9361",
                "rx_scan_channels": [],
                "tandem_agc": False,
                "detector_only": True,
            },
        },
        "host_key_rotation": {
            "previous_known_hosts_sha256": first_key_hash,
            "replacement_known_hosts_sha256": final_key_hash,
        },
    }
    reboot_path = tmp_path / "reboot.json"
    reboot_path.write_text(json.dumps(reboot))
    binding = runner._deployment_binding(
        path,
        known_hosts,
        rate_msps=30,
        reboot_receipts=[reboot_path],
    )
    assert binding["current_boot_id"] == "22222222-2222-4222-8222-222222222222"
    assert len(binding["reboots"]) == 1

    receipt["plan"]["mutation_profile_id"] = "nearby-off-slice-v1"
    path.write_text(json.dumps(receipt))
    with pytest.raises(runner.QualificationError, match="deployment receipt"):
        runner._validate_deployment(path, rate_msps=30)


def test_corrected_campaign_uses_one_epoch_ten_map_discards_and_replays(
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
            "maps_delivered": Attribute(47),
            "chunks_delivered": Attribute(9_400),
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
    coefficient.write_bytes(b"one exact coefficient fixture")
    profile = runner.RateProfile(
        rate_msps=30,
        firmware=runner.EXPECTED_DEPLOYMENTS[30]["firmware"],
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

    client = Client()
    monkeypatch.setattr(runner, "acquire_radio_lock", locked)
    monkeypatch.setattr(
        runner,
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
    monkeypatch.setattr(runner, "_write_number", lambda _c, _n, value, _t: value)
    monkeypatch.setattr(runner, "analyze_phase_maps", analyze)
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

    receipt = runner.run(
        tmp_path / "campaign",
        profile=profile,
        on_if_hz=1_937_500_000,
        deployment_receipt=tmp_path / "unused-deployment.json",
        known_hosts_file=tmp_path / "unused-known-hosts",
        reboot_receipts=[],
        firmware_source_commit="a" * 40,
        ppu_source_commit="b" * 40,
        role_duration_seconds=1.0,
    )

    assert receipt["outcome"] == "pass"
    assert receipt["role_order"] == list(runner.ROLES)
    assert receipt["transmitter_opened"] is False
    assert receipt["pss_detected"] is False
    assert client.open_count == 1
    assert client.generation == 47
    assert receipt["stream"]["complete_maps"] == 47
    assert receipt["stream"]["transition_discard_maps"] == 20
    assert [value["complete_maps"] for value in receipt["roles"].values()] == [9, 9, 9]
    assert [value["discarded_map_count"] for value in receipt["transitions"]] == [
        10,
        10,
    ]
    assert receipt["roles"]["below_band_control"]["requested_lo_hz"] == 850_000_000

    analysis = runner.replay(
        receipt_path=Path(receipt["receipt"]),
        output=tmp_path / "campaign" / "replay-analysis.json",
    )
    assert analysis["outcome"] == "pass"
    assert analysis["pss_detected"] is False

    tampered = json.loads(Path(receipt["receipt"]).read_text())
    tampered["transitions"][0]["discarded_map_count"] = 5
    Path(receipt["receipt"]).write_text(json.dumps(tampered))
    with pytest.raises(runner.QualificationError, match="retune contract"):
        runner.replay(
            receipt_path=Path(receipt["receipt"]),
            output=tmp_path / "campaign" / "must-not-pass.json",
        )
    assert not (tmp_path / "campaign" / "must-not-pass.json").exists()
    assert events[-2:] == ["context_close", "lock_exit"]


def test_invalid_arguments_create_no_output(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="role duration"):
        runner.run(
            tmp_path / "must-not-exist",
            profile=runner.RATE_PROFILES[30],
            on_if_hz=1_937_500_000,
            deployment_receipt=tmp_path / "none",
            known_hosts_file=tmp_path / "none",
            reboot_receipts=[],
            firmware_source_commit="a" * 40,
            ppu_source_commit="b" * 40,
            role_duration_seconds=0.5,
        )
    assert not (tmp_path / "must-not-exist").exists()
