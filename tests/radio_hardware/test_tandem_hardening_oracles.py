"""Focused offline regressions for tandem-quality verdict hardening."""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from .experiment import EvidenceInvalid
from .metadata_abi import (
    FLAG_DEVICE_IIO_OVERFLOW,
    FLAG_DUMMY_GAINS,
    FLAG_FPGA_EVENT_OVERFLOW,
    FLAG_GAIN_OBSERVATION_OVERFLOW,
    FLAG_GAIN_READ_FAILED,
    FLAG_RSSI_READ_FAILED,
)
from .tandem_quality import (
    MODE_NATIVE,
    TandemQualityOptions,
    _capture,
    _extend_gain_band,
    _measure_ordinary,
    evaluate_matrix,
)
from .test_tandem_matrix_oracles import _passing_report


def _state(mode: str, rx0: float, rx1: float) -> dict[str, list[object]]:
    return {"modes": [mode, mode], "gains_db": [rx0, rx1]}


def test_stable_gain_band_rejects_cumulative_pairwise_drift() -> None:
    first = _extend_gain_band(
        (_state("slow_attack", 10.0, 20.0),) * 2,
        expected_mode="slow_attack",
    )
    assert first is not None
    second = _extend_gain_band(
        (_state("slow_attack", 11.0, 21.0),) * 2,
        expected_mode="slow_attack",
        prior=first,
    )
    assert second is not None
    assert second.to_dict()["span_db"] == [1.0, 1.0]

    # Every individual move is only 1 dB, but the whole candidate window has
    # crept by 2 dB and therefore cannot count as three stable frames.
    assert (
        _extend_gain_band(
            (_state("slow_attack", 12.0, 22.0),) * 2,
            expected_mode="slow_attack",
            prior=second,
        )
        is None
    )


def test_manual_gain_band_is_exact() -> None:
    settled = _extend_gain_band(
        (_state("manual", 30.0, 30.0),) * 2, expected_mode="manual"
    )
    assert settled is not None
    assert (
        _extend_gain_band(
            (_state("manual", 30.001, 30.0),) * 2,
            expected_mode="manual",
            prior=settled,
        )
        is None
    )


def test_first_measurement_gain_jump_is_compared_with_settled_band(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    settled = _extend_gain_band(
        (_state("slow_attack", 30.0, 30.0),) * 2,
        expected_mode="slow_attack",
    )
    assert settled is not None

    class JumpingRadio:
        @staticmethod
        def read_rx_state() -> dict[str, list[object]]:
            return _state("slow_attack", 32.0, 32.0)

    monkeypatch.setattr(
        "tests.radio_hardware.tandem_quality._capture",
        lambda *_args, **_kwargs: (b"", None, {}),
    )
    options = TandemQualityOptions(
        tx_gain_trajectory_db=(-60.0, -30.0, -60.0),
        physical_attenuation_db=0.0,
        measurement_frames=1,
    )
    with pytest.raises(EvidenceInvalid, match="left its settled band") as caught:
        _measure_ordinary(
            JumpingRadio(),
            object(),
            mode=MODE_NATIVE,
            options=options,
            output_dir=tmp_path,
            level_index=0,
            settled=settled,
        )
    assert caught.value.failure_evidence == {
        "kind": "ordinary_gain_left_settled_band",
        "mode": MODE_NATIVE,
        "expected_iio_mode": "slow_attack",
        "level_index": 0,
        "tx2_gain_requested_db": -60.0,
        "frame_index": 0,
        "allowed_cumulative_span_db": 1.0,
        "settled_gain_band": settled.to_dict(),
        "cumulative_gain_band_before_frame": settled.to_dict(),
        "rx_state_before": _state("slow_attack", 32.0, 32.0),
        "rx_state_after": _state("slow_attack", 32.0, 32.0),
        "captured_frame": {},
    }


@pytest.mark.parametrize(
    "unsafe_flag",
    [
        FLAG_DEVICE_IIO_OVERFLOW,
        FLAG_GAIN_READ_FAILED,
        FLAG_FPGA_EVENT_OVERFLOW,
        FLAG_DUMMY_GAINS,
        FLAG_RSSI_READ_FAILED,
        FLAG_GAIN_OBSERVATION_OVERFLOW,
    ],
)
def test_capture_rejects_every_unsafe_tandem_metadata_flag(
    monkeypatch: pytest.MonkeyPatch, unsafe_flag: int
) -> None:
    samples = 8_192
    raw = bytes(samples * 8)
    parsed = SimpleNamespace(
        samples_per_channel=samples,
        iq_payload_bytes=len(raw),
        enabled_scan_mask=0x0F,
        channel_count=2,
        flags=unsafe_flag,
    )

    class FakeRadio:
        @staticmethod
        def capture_iq(*_args, **_kwargs):
            return raw, b"metadata", 1

    monkeypatch.setattr(
        "tests.radio_hardware.tandem_quality.parse_tandem_frame_metadata",
        lambda _payload: parsed,
    )
    options = TandemQualityOptions(
        tx_gain_trajectory_db=(-60.0, -30.0, -60.0),
        physical_attenuation_db=0.0,
        samples_per_channel=samples,
    )
    with pytest.raises(EvidenceInvalid, match="unsafe flags"):
        _capture(FakeRadio(), object(), options=options, metadata=True)


def test_native_fixed_cross_channel_offset_cannot_fake_gain_response() -> None:
    report = copy.deepcopy(_passing_report())
    for cell in report["modes"][1]["cells"]:
        for frame in cell["measurements"]:
            frame["rx_state_after"]["gains_db"] = [30.0, 29.0]

    evaluation = evaluate_matrix(report)
    assert evaluation["verdict"] == "fail"
    assert evaluation["native_gain_span_db"] == [0.0, 0.0]
    assert any("RX channels [0, 1]" in failure for failure in evaluation["failures"])


def test_native_gain_motion_in_the_wrong_direction_cannot_pass() -> None:
    report = copy.deepcopy(_passing_report())
    for cell in report["modes"][1]["cells"]:
        gain = 20.0 if cell["tx2_gain_requested_db"] == -60.0 else 40.0
        for frame in cell["measurements"]:
            frame["rx_state_after"]["gains_db"] = [gain, gain + 1.0]

    evaluation = evaluate_matrix(report)
    assert evaluation["native_gain_span_db"] == [20.0, 20.0]
    assert evaluation["verdict"] == "fail"
    assert any("outbound leg" in failure for failure in evaluation["failures"])
    assert any("return leg" in failure for failure in evaluation["failures"])


def test_manual_fixed_gain_tone_must_track_and_retrace_tx2() -> None:
    report = copy.deepcopy(_passing_report())
    for cell in report["modes"][0]["cells"]:
        cell["summary"]["tone_dbfs_median"] = [-25.0, -25.2]

    evaluation = evaluate_matrix(report)
    assert evaluation["verdict"] == "fail"
    assert not evaluation["manual_tone_evidence"]["valid"]
    assert any(
        "manual fixed-gain tone" in failure for failure in evaluation["failures"]
    )
