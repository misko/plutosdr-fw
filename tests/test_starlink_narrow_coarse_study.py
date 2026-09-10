"""Analytic boundaries, source-support integrity and known-signal coordinates."""

from types import SimpleNamespace

import numpy as np
import pytest

from tools import starlink_narrow_coarse_study as study


def test_carrier_support_uses_remaining_cfo_after_correction():
    assert study.coverage(279_687.5)["passband_carrier_count"] == 8
    assert study.coverage(-279_687.5)["passband_carrier_count"] == 8
    assert study.coverage(279_687.6)["status"] == "unobservable_full_pilot_contract"
    assert study.coverage(study.PRIOR)["passband_carrier_count"] == 7
    assert study.coverage(study.PRIOR - study.PRIOR)["passband_carrier_count"] == 8
    assert study.coverage(1_200_000)["stopband_carrier_count"] == 4
    assert not study.coverage(0)["modulated_sidelobes_fully_preserved"]
    with pytest.raises(ValueError):
        study.coverage(float("nan"))


def test_budget_includes_observation_and_full_rate_memory():
    row = study.budget(.080, transport_seconds=.010, command_seconds=.002)
    assert row["earliest_handoff_seconds"] == pytest.approx(.112 + 269 / 15e6)
    assert row["fits_120ms_with_supplied_latencies"]
    assert row["full_60msps_ci16_retrospective_ring_bytes"] > 26_880_000
    assert not row["transport_and_command_measured"]
    assert not study.budget(.100)["fits_120ms_with_supplied_latencies"]
    assert study.budget(0)["full_60msps_ci16_retrospective_ring_bytes"] > 4_800_000
    with pytest.raises(ValueError):
        study.budget(-1)
    with pytest.raises(ValueError):
        study.budget(0, frames_after_handoff=0)


def test_probe_read_is_bounded_and_detects_changed_bytes(tmp_path):
    path = tmp_path / "iq.ci16"
    payload = np.zeros((study.PROBE_SAMPLES + 2 * study.HALO, 2), dtype="<i2").tobytes()
    path.write_bytes(payload)
    item = {"path": str(path), "center_start": 900_600,
            "file_first_canonical_index": 900_000, "probe_sha256": study.sha(payload)}
    values, first, raw = study.read_probe(item)
    assert first == 900_000 and len(raw) == 1_204_800
    assert values.shape == (301_200, 2)
    item["probe_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="bytes changed"):
        study.read_probe(item)
    item["center_start"] += 1
    with pytest.raises(ValueError, match="halos"):
        study.read_probe(item)


@pytest.mark.parametrize("first", (0, 1, 17))
def test_fixed_filter_rejects_startup_and_keeps_true_delay(first):
    count = study.PROBE_SAMPLES + 2 * study.HALO
    indexes = first + np.arange(count)
    phase = 2 * np.pi * (2_812_500 + 285_941.794) * indexes / study.RATE
    samples = np.rint(5000 * np.column_stack((np.cos(phase), np.sin(phase)))).astype(np.int16)
    values, centers, receipt = study.filter_probe(
        samples, first, first + study.HALO, edge="upper", correction_hz=285_941.794)
    assert len(values) == 50_000
    assert centers[0] >= first + study.HALO
    assert np.all((centers + 269) % 6 == 0)
    assert np.max(np.abs(values - np.mean(values))) < 4
    assert abs(np.mean(values)) == pytest.approx(5000, abs=3)
    assert receipt["pre_filter_correction_saturations"] == 0
    assert receipt["ddc_saturations"] == 0


def test_spectrum_does_not_claim_rate_spacing_as_timing_accuracy():
    result = study.spectrum_study()
    assert result["source60_sample_spacing_ns"] == pytest.approx(16.6666667)
    assert result["full_pilot_carrier_residual_bound_hz"] == 279_687.5
    assert result["first_null_main_lobe_residual_bound_hz"] == 45_312.5
    assert not result["timing_accuracy_demonstrated"]
    assert len(result["rows"]) == 8
    assert all(0 < row["pss_energy_after_filter_fraction"] < 1 for row in result["rows"])


def test_high_margin_does_not_admit_an_out_of_coverage_synthetic(monkeypatch):
    monkeypatch.setattr(study, "blind", lambda *args: {
        "best": {"epoch_sample": 0, "tracking_cfo_hz": 0, "margin": .99},
        "total_search_seconds": .01})
    result = study.synthetic(
        {"edge": "upper", "kind": "positive", "injected_cfo_hz": 1_200_000,
         "applied_prefilter_correction_hz": 0},
        {"synthetic_seed": 1, "synthetic_epoch_canonical": 10_003},
        {"templates": SimpleNamespace(qin_edge_pilot_frame=lambda *args: np.zeros(20_000))})
    assert result["classification"] == "unobservable_full_pilot_contract"
    assert result["predeclared_fixture_acceptance_pass"] is None


def test_unadmitted_real_probe_preserves_unknown_observability(monkeypatch):
    monkeypatch.setattr(study, "read_probe", lambda item: (
        np.zeros((301_200, 2), dtype=np.int16), 0, b""))
    monkeypatch.setattr(study, "blind", lambda *args: {
        "best": {"epoch_sample": 0, "tracking_cfo_hz": 0, "margin": .005},
        "total_search_seconds": .01})
    result = study.heldout(
        {"role": "heldout", "center_start": 600, "applied_prefilter_correction_hz": 0,
         "prior_full_original25_source_bounds": [-1000, -1]}, {})
    assert result["classification"] == "no_candidate_coverage_unknown"
    assert not result["calibrated_observability"]
    assert not result["independent_rf_truth"]
