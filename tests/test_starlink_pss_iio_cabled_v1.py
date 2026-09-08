from __future__ import annotations

import pytest

import scripts.starlink_pss_iio_cabled_v1 as runner
from scripts.starlink_pss_iio_cabled_v1 import (
    RATE_PROFILES,
    _analyze,
    _future_center,
    _receiver_uri,
    _tx_state_is_safe,
)


@pytest.mark.parametrize("rate_msps", [30, 60])
def test_rate_profile_scales_every_source_sample_quantity(rate_msps: int) -> None:
    profile = RATE_PROFILES[rate_msps]

    assert profile.rate_hz == rate_msps * 1_000_000
    assert profile.period_samples == profile.rate_hz // 750
    assert profile.aperture_samples == rate_msps * 2
    assert profile.host_lead_samples == profile.rate_hz // 5
    assert profile.bandwidth_hz == 20_000_000
    assert f"pss{rate_msps}" in profile.coefficient_path.name
    assert f"pss{rate_msps}" in profile.waveform_path.name
    assert profile.waveform_bytes == profile.period_samples * 4
    assert profile.request_prefix & 0x80000000


def test_future_center_honors_rate_specific_host_lead() -> None:
    profile = RATE_PROFILES[30]
    anchor = 8_192
    current = 1_000_000

    center = _future_center(
        anchor,
        current,
        profile.period_samples,
        host_lead_samples=profile.host_lead_samples,
    )

    assert center >= current + profile.host_lead_samples
    assert (center - anchor) % profile.period_samples == 0
    assert center - profile.period_samples < current + profile.host_lead_samples


def test_ethernet_receiver_uri_is_fixed_and_does_not_discover_peers() -> None:
    assert _receiver_uri("ethernet") == "ip:192.168.1.17"


def test_receiver_uri_rejects_unknown_transport() -> None:
    with pytest.raises(
        runner.QualificationError, match="unsupported receiver transport"
    ):
        _receiver_uri("network")


def test_fine_analysis_uses_selected_rate_period_and_aperture() -> None:
    profile = RATE_PROFILES[30]
    results = [
        {
            "ordinal": ordinal,
            "winner_timestamp": 5_000_000 + ordinal * profile.period_samples,
            "winner_lag": ordinal % 3 - 1,
            "correlation_real": 2,
            "correlation_imag": 0,
            "sample_energy": 2,
            "coefficient_energy": 2,
        }
        for ordinal in range(16)
    ]

    analysis = _analyze(
        results,
        period_samples=profile.period_samples,
        aperture_samples=profile.aperture_samples,
    )

    assert analysis["fitted_period_source_samples"] == profile.period_samples
    assert analysis["relative_clock_error_ppm"] == 0
    assert analysis["residual_max_abs_source_samples"] == 0
    assert analysis["aperture_edge_hits"] == 0
    assert analysis["normalized_score_median"] == 1


def _safe_tx_state() -> dict[str, object]:
    return {
        "serial": runner.TX_SERIAL,
        "dac_selectors": [3, 3],
        "dds_raw": [0, 0, 0, 0],
        "dds_scale": [0.0, 0.0, 0.0, 0.0],
        "tx_hardwaregain_db": -89.75,
        "tx_lo_powerdown": 1,
    }


@pytest.mark.parametrize(
    ("field", "unsafe"),
    [
        ("serial", "peer-radio"),
        ("dac_selectors", [0, 0]),
        ("dds_raw", [1, 0, 0, 0]),
        ("dds_scale", [0.01, 0.0, 0.0, 0.0]),
        ("tx_hardwaregain_db", -79.75),
        ("tx_lo_powerdown", 0),
    ],
)
def test_tx_state_requires_every_independent_mute_barrier(
    field: str, unsafe: object
) -> None:
    state = _safe_tx_state()

    assert _tx_state_is_safe(state, expected_serial=runner.TX_SERIAL)
    state[field] = unsafe
    assert not _tx_state_is_safe(state, expected_serial=runner.TX_SERIAL)


def test_independent_final_mute_uses_two_fresh_contexts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contexts = [object(), object()]
    opened: list[tuple[str, object]] = []
    released: list[object] = []

    def open_context(uri: str) -> object:
        context = contexts[len(opened)]
        opened.append((uri, context))
        return context

    class Finalizer:
        def __init__(self, _iio: object, context: object, *, expected_serial: str):
            assert context is contexts[0]
            assert expected_serial == runner.TX_SERIAL

        def close(self) -> dict[str, bool]:
            released.append(contexts[0])
            return {"verified": True}

    class VerificationContext:
        def set_timeout(self, timeout_ms: int) -> None:
            assert timeout_ms == 5_000

    contexts[1] = VerificationContext()
    monkeypatch.setattr(runner.iio, "Context", open_context)
    monkeypatch.setattr(runner, "PhaseContinuousSingleTx", Finalizer)
    monkeypatch.setattr(
        runner,
        "_read_tx_safe_state",
        lambda context, *, expected_serial: {**_safe_tx_state(), "verified": True},
    )
    monkeypatch.setattr(
        runner,
        "close_iio_context",
        lambda _iio, context: (released.append(context), "released")[1],
    )

    result = runner._independent_final_tx_mute("usb:3.81.5")

    assert opened == [("usb:3.81.5", contexts[0]), ("usb:3.81.5", contexts[1])]
    assert released == [contexts[0], contexts[1]]
    assert result["verified"] is True
    assert result["independent_reopen"]["dac_selectors"] == [3, 3]
