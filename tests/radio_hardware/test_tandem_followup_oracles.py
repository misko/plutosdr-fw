"""Planted offline oracles for RF-band, native-mode, and AUTO-timing coverage."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from . import tandem_quality
from .experiment import EvidenceInvalid, FixtureSafetyError, Issue46Radio
from .metadata_abi import TandemGainTable, TandemState
from .tandem_quality import (
    DEFAULT_NATIVE_GAIN_CONTROL_MODES,
    MODE_MANUAL,
    MODE_NATIVE,
    MODE_TANDEM,
    MODES,
    TandemQualityOptions,
    _capture,
    _run_mode,
    evaluate_matrix,
    expected_tandem_gain_table,
    native_mode_name,
    parse_native_gain_control_modes,
    quality_modes,
    run_tandem_quality_matrix,
    validate_options,
)
from .test_tandem_matrix_oracles import _passing_report
from .test_tandem_priming_oracles import _FakeRadio


def _options(**overrides) -> TandemQualityOptions:
    return TandemQualityOptions(
        tx_gain_trajectory_db=(-60.0, -30.0, -60.0),
        physical_attenuation_db=0.0,
        **overrides,
    )


@pytest.mark.parametrize(
    ("center_frequency_hz", "expected"),
    [
        (70_000_000, TandemGainTable.MHZ_200_1300),
        (915_000_000, TandemGainTable.MHZ_200_1300),
        (1_300_000_000, TandemGainTable.MHZ_200_1300),
        (1_300_000_001, TandemGainTable.MHZ_1300_4000),
        (2_450_000_000, TandemGainTable.MHZ_1300_4000),
        (4_000_000_000, TandemGainTable.MHZ_1300_4000),
        (4_000_000_001, TandemGainTable.MHZ_4000_6000),
        (5_800_000_000, TandemGainTable.MHZ_4000_6000),
        (6_000_000_000, TandemGainTable.MHZ_4000_6000),
    ],
)
def test_gain_table_derivation_matches_kernel_boundaries(
    center_frequency_hz: int, expected: TandemGainTable
) -> None:
    assert expected_tandem_gain_table(center_frequency_hz) is expected


@pytest.mark.parametrize(
    "center_frequency_hz",
    [True, 70_000_000.0, 69_999_999, 6_000_000_001],
)
def test_invalid_common_center_frequency_is_rejected_before_hardware(
    center_frequency_hz: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="center frequency"):
        validate_options(_options(center_frequency_hz=center_frequency_hz))  # type: ignore[arg-type]


class _Attribute:
    def __init__(self, value: object, *, readback_offset: int = 0) -> None:
        self._value = str(value)
        self.readback_offset = readback_offset

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, requested: object) -> None:
        self._value = str(int(requested) + self.readback_offset)


def _frequency_radio(*, tx_readback_offset: int = 0) -> Issue46Radio:
    radio = Issue46Radio.__new__(Issue46Radio)
    channels = {
        "altvoltage0": SimpleNamespace(
            id="altvoltage0", attrs={"frequency": _Attribute(915_000_000)}
        ),
        "altvoltage1": SimpleNamespace(
            id="altvoltage1",
            attrs={
                "frequency": _Attribute(915_000_000, readback_offset=tx_readback_offset)
            },
        ),
    }
    radio._phy_channel = lambda name, output: channels[name]  # type: ignore[method-assign]
    return radio


def test_common_center_frequency_programs_and_reads_back_both_los() -> None:
    radio = _frequency_radio()

    readback = radio._configure_center_frequency(2_450_000_000)

    assert readback == {"rx_lo_hz": 2_450_000_000, "tx_lo_hz": 2_450_000_000}
    assert radio.read_center_frequency() == readback


def test_common_center_frequency_rejects_a_planted_lo_readback_mismatch() -> None:
    radio = _frequency_radio(tx_readback_offset=10)

    with pytest.raises(FixtureSafetyError, match="readback"):
        radio._configure_center_frequency(5_800_000_000)


def _parsed_metadata(gain_table: TandemGainTable, samples: int) -> SimpleNamespace:
    return SimpleNamespace(
        samples_per_channel=samples,
        iq_payload_bytes=samples * 8,
        enabled_scan_mask=0x0F,
        channel_count=2,
        flags=0,
        device_iio_overflow=False,
        observation_count=1,
        observation_capacity=64,
        event_count=0,
        event_capacity=64,
        observation_overflow_count=0,
        event_overflow_count=0,
        stream_id=1,
        buffer_sequence=1,
        first_sample_sequence=1,
        ownership_epoch=1,
        tandem_state=TandemState.ARMED_AUTO,
        tandem_transition_count=0,
        gain_table_id=gain_table,
        threshold_provenance=0,
        minimum_gain_db=0,
        maximum_gain_db=62,
        initial_gain_db=40,
        minimum_gain_index=3,
        maximum_gain_index=65,
        bench_gain_indices=(40, 40),
        ad9361_temperature_mdeg_c=35_000,
        gain_events=(),
    )


@pytest.mark.parametrize(
    ("center_frequency_hz", "gain_table"),
    [
        (915_000_000, TandemGainTable.MHZ_200_1300),
        (2_450_000_000, TandemGainTable.MHZ_1300_4000),
        (5_800_000_000, TandemGainTable.MHZ_4000_6000),
    ],
)
def test_capture_accepts_the_expected_gain_table_readback(
    monkeypatch: pytest.MonkeyPatch,
    center_frequency_hz: int,
    gain_table: TandemGainTable,
) -> None:
    options = _options(
        center_frequency_hz=center_frequency_hz, samples_per_channel=8192
    )
    raw = bytes(options.samples_per_channel * 8)
    radio = SimpleNamespace(
        capture_iq=lambda *_args, **_kwargs: (raw, b"metadata", 123)
    )
    monkeypatch.setattr(
        tandem_quality,
        "parse_tandem_frame_metadata",
        lambda _raw: _parsed_metadata(gain_table, options.samples_per_channel),
    )

    _payload, parsed, frame = _capture(radio, object(), options=options, metadata=True)

    assert parsed is not None
    assert frame["metadata"]["gain_table_id"] == int(gain_table)


def test_capture_rejects_a_planted_wrong_gain_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options = _options(center_frequency_hz=2_450_000_000, samples_per_channel=8192)
    raw = bytes(options.samples_per_channel * 8)
    radio = SimpleNamespace(
        capture_iq=lambda *_args, **_kwargs: (raw, b"metadata", 123)
    )
    monkeypatch.setattr(
        tandem_quality,
        "parse_tandem_frame_metadata",
        lambda _raw: _parsed_metadata(
            TandemGainTable.MHZ_200_1300, options.samples_per_channel
        ),
    )

    with pytest.raises(EvidenceInvalid, match="selected gain table 1, expected 2"):
        _capture(radio, object(), options=options, metadata=True)


def test_legacy_defaults_preserve_the_original_three_mode_matrix() -> None:
    options = _options()

    assert options.center_frequency_hz == 915_000_000
    assert options.native_gain_control_modes == DEFAULT_NATIVE_GAIN_CONTROL_MODES
    assert options.tandem_power_measurement_samples == 1_024
    assert options.tandem_low_power_dwell_periods == 3
    assert options.tandem_cooldown_periods == 16
    assert quality_modes(options) == MODES


def test_native_mode_parser_preserves_requested_order() -> None:
    selected = parse_native_gain_control_modes("hybrid,slow_attack,fast_attack")

    assert selected == ("hybrid", "slow_attack", "fast_attack")
    assert quality_modes(_options(native_gain_control_modes=selected)) == (
        MODE_MANUAL,
        "native_hybrid",
        MODE_NATIVE,
        "native_fast_attack",
        MODE_TANDEM,
    )


@pytest.mark.parametrize(
    "selection",
    [
        "",
        "slow_attack,",
        "slow_attack,,hybrid",
        "slow_attack,slow_attack",
        "slow_attack,unsupported",
    ],
)
def test_native_mode_parser_rejects_empty_duplicate_or_unknown_cells(
    selection: str,
) -> None:
    with pytest.raises(ValueError):
        parse_native_gain_control_modes(selection)


@pytest.mark.parametrize("iio_mode", ["slow_attack", "fast_attack", "hybrid"])
def test_run_mode_programs_each_selected_native_iio_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path, iio_mode: str
) -> None:
    radio = _FakeRadio()
    band = SimpleNamespace(to_dict=lambda: {"mode": iio_mode})
    monkeypatch.setattr(
        tandem_quality,
        "_wait_for_idle",
        lambda _radio: {"state": 0, "fault_flags": 0, "fifo_level": 0},
    )
    monkeypatch.setattr(tandem_quality, "_atomic_json", lambda *_args: None)
    monkeypatch.setattr(
        tandem_quality,
        "_settle_ordinary",
        lambda *_args, **_kwargs: ([], band),
    )
    monkeypatch.setattr(
        tandem_quality,
        "_measure_ordinary",
        lambda *_args, **_kwargs: [{"quality": {"quality_valid": True}}],
    )
    monkeypatch.setattr(
        tandem_quality,
        "summarize_measurements",
        lambda _measurements: {"quality_valid": True},
    )

    _run_mode(
        radio,
        mode=native_mode_name(iio_mode),
        options=_options(output_dir=tmp_path),
        report={"modes": []},
        report_path=tmp_path / "report.json",
        check_deadline=lambda: None,
    )

    configured = [
        operation[1] for operation in radio.operations if operation[0] == "configure_rx"
    ]
    assert configured == ["manual", iio_mode, "manual"]


def test_multi_native_evaluator_reports_every_mode_and_keeps_legacy_reference() -> None:
    report = _passing_report()
    slow = report["modes"][1]
    tandem = report["modes"].pop()
    for iio_mode in ("fast_attack", "hybrid"):
        record = copy.deepcopy(slow)
        record["mode"] = native_mode_name(iio_mode)
        report["modes"].append(record)
    report["modes"].append(tandem)

    evaluation = evaluate_matrix(report)

    assert evaluation["verdict"] == "pass"
    assert evaluation["native_modes"] == [
        MODE_NATIVE,
        "native_fast_attack",
        "native_hybrid",
    ]
    assert evaluation["native_reference_mode"] == MODE_NATIVE
    assert set(evaluation["native_gain_evidence_by_mode"]) == set(
        evaluation["native_modes"]
    )
    assert (
        evaluation["native_gain_evidence"]
        == evaluation["native_gain_evidence_by_mode"][MODE_NATIVE]
    )
    for comparison in evaluation["comparisons"]:
        assert comparison["native_reference_mode"] == MODE_NATIVE
        assert set(comparison["native_minus_manual_by_mode"]) == set(
            evaluation["native_modes"]
        )
        assert (
            comparison["native_minus_manual"]
            == comparison["native_minus_manual_by_mode"][MODE_NATIVE]
        )


@pytest.mark.parametrize("failed_mode", ["native_fast_attack", "native_hybrid"])
def test_one_bad_extra_native_cell_cannot_hide_behind_slow_attack(
    failed_mode: str,
) -> None:
    report = _passing_report()
    slow = report["modes"][1]
    tandem = report["modes"].pop()
    for iio_mode in ("fast_attack", "hybrid"):
        record = copy.deepcopy(slow)
        record["mode"] = native_mode_name(iio_mode)
        report["modes"].append(record)
    report["modes"].append(tandem)
    failed_record = next(
        item for item in report["modes"] if item["mode"] == failed_mode
    )
    failed_record["cells"][1]["summary"]["quality_valid"] = False

    evaluation = evaluate_matrix(report)

    assert evaluation["verdict"] == "fail"
    assert any(failed_mode in failure for failure in evaluation["failures"])


@pytest.mark.parametrize(
    "overrides",
    [
        {"tandem_power_measurement_samples": True},
        {"tandem_power_measurement_samples": 0},
        {"tandem_power_measurement_samples": 1 << 20},
        {"tandem_low_power_dwell_periods": 0},
        {"tandem_low_power_dwell_periods": 256},
        {"tandem_cooldown_periods": -1},
        {"tandem_cooldown_periods": 256},
        {
            "samples_per_channel": 8192,
            "tandem_power_measurement_samples": 1,
            "tandem_cooldown_periods": 0,
        },
    ],
)
def test_invalid_or_capacity_unsafe_auto_timing_is_rejected_before_hardware(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        validate_options(_options(**overrides))  # type: ignore[arg-type]


def test_event_capacity_boundary_and_full_wire_timing_ranges_are_accepted() -> None:
    options = _options(
        samples_per_channel=8192,
        tandem_power_measurement_samples=128,
        tandem_low_power_dwell_periods=255,
        tandem_cooldown_periods=0,
    )

    validate_options(options)
    validate_options(
        replace(
            options,
            tandem_power_measurement_samples=(1 << 20) - 1,
            tandem_cooldown_periods=255,
        )
    )


def test_quality_runner_forwards_configured_auto_timing_exactly(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    radio = _FakeRadio()
    request_kwargs: dict[str, object] = {}
    settled = SimpleNamespace(
        rx1_gain_index=50,
        rx2_gain_index=50,
        maximum_gain_index=65,
        bench_gain_indices=(50, 50),
    )

    def fake_request(**kwargs) -> bytes:
        request_kwargs.update(kwargs)
        return b"request"

    monkeypatch.setattr(tandem_quality, "build_tandem_request", fake_request)
    monkeypatch.setattr(
        tandem_quality,
        "_wait_for_idle",
        lambda _radio: {"state": 0, "fault_flags": 0, "fifo_level": 0},
    )
    monkeypatch.setattr(tandem_quality, "_atomic_json", lambda *_args: None)
    monkeypatch.setattr(
        tandem_quality,
        "_settle_tandem",
        lambda *_args, **_kwargs: ([{"metadata": {"gain_events": []}}], settled),
    )
    monkeypatch.setattr(
        tandem_quality,
        "_measure_tandem",
        lambda *_args, **_kwargs: [{"quality": {"quality_valid": True}}],
    )
    monkeypatch.setattr(
        tandem_quality,
        "_metadata_dict",
        lambda metadata: {"bench_gain_indices": list(metadata.bench_gain_indices)},
    )
    monkeypatch.setattr(
        tandem_quality,
        "summarize_measurements",
        lambda _measurements: {"quality_valid": True},
    )
    options = _options(
        output_dir=tmp_path,
        tandem_power_measurement_samples=2_048,
        tandem_low_power_dwell_periods=7,
        tandem_cooldown_periods=11,
    )

    _run_mode(
        radio,
        mode=MODE_TANDEM,
        options=options,
        report={"modes": []},
        report_path=tmp_path / "report.json",
        check_deadline=lambda: None,
    )

    assert request_kwargs["power_measurement_samples"] == 2_048
    assert request_kwargs["low_power_dwell_periods"] == 7
    assert request_kwargs["cooldown_periods"] == 11
    assert request_kwargs["samples_per_channel"] == options.samples_per_channel


class _MatrixRadio:
    def __init__(self, options: TandemQualityOptions, *, readback_offset: int = 0):
        self.options = SimpleNamespace(
            serial="offline-radio",
            sample_rate_hz=options.sample_rate_hz,
            samples_per_channel=options.samples_per_channel,
            tx_gain_db=options.strongest_tx_gain_db,
            center_frequency_hz=options.center_frequency_hz,
        )
        self.identity = {"serial": "offline-radio"}
        self.readback_offset = readback_offset
        self._report_path = None

    def read_center_frequency(self) -> dict[str, int]:
        return {
            "rx_lo_hz": self.options.center_frequency_hz,
            "tx_lo_hz": self.options.center_frequency_hz + self.readback_offset,
        }

    @staticmethod
    def tandem_status() -> dict[str, int]:
        return {"state": 0, "fault_flags": 0, "fifo_level": 0}

    @staticmethod
    def mute_all() -> None:
        pass

    @staticmethod
    def configure_rx(mode: str, *, manual_gain_db: float | None = None) -> None:
        del mode, manual_gain_db

    @staticmethod
    def read_rx_state() -> dict[str, list[object]]:
        return {"modes": ["manual", "manual"], "gains_db": [40.0, 40.0]}


def test_full_runner_records_rf_attestation_and_every_native_cell(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    selected = ("slow_attack", "fast_attack", "hybrid")
    options = _options(
        output_dir=tmp_path,
        center_frequency_hz=2_450_000_000,
        native_gain_control_modes=selected,
        tandem_power_measurement_samples=2_048,
        tandem_low_power_dwell_periods=7,
        tandem_cooldown_periods=11,
    )
    template = _passing_report()
    records = {item["mode"]: item for item in template["modes"]}

    def fake_run_mode(_radio, *, mode, report, **_kwargs) -> None:
        if mode in (MODE_MANUAL, MODE_TANDEM):
            record = copy.deepcopy(records[mode])
        else:
            record = copy.deepcopy(records[MODE_NATIVE])
            record["mode"] = mode
        report["modes"].append(record)

    monkeypatch.setattr(tandem_quality, "_run_mode", fake_run_mode)

    report, path = run_tandem_quality_matrix(_MatrixRadio(options), options)

    assert path.exists()
    assert report["verdict"] == "pass"
    assert [item["mode"] for item in report["modes"]] == [
        MODE_MANUAL,
        MODE_NATIVE,
        "native_fast_attack",
        "native_hybrid",
        MODE_TANDEM,
    ]
    assert report["rf"] == {
        "center_frequency_hz_requested": 2_450_000_000,
        "center_frequency_hz_readback": {
            "rx_lo_hz": 2_450_000_000,
            "tx_lo_hz": 2_450_000_000,
        },
        "expected_tandem_gain_table_id": 2,
        "expected_tandem_gain_table_name": "mhz_1300_4000",
    }
    assert report["configuration"]["tandem_power_measurement_samples"] == 2_048
    assert report["configuration"]["tandem_low_power_dwell_periods"] == 7
    assert report["configuration"]["tandem_cooldown_periods"] == 11


def test_full_runner_persists_structured_gain_band_failure_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    options = _options(output_dir=tmp_path)
    manual = copy.deepcopy(_passing_report()["modes"][0])
    failure_evidence = {
        "kind": "ordinary_gain_left_settled_band",
        "mode": MODE_NATIVE,
        "expected_iio_mode": "slow_attack",
        "level_index": 1,
        "tx2_gain_requested_db": -30.0,
        "frame_index": 2,
        "allowed_cumulative_span_db": 1.0,
        "settled_gain_band": {"planted": "settled"},
        "cumulative_gain_band_before_frame": {"planted": "prior"},
        "rx_state_before": {"planted": "before"},
        "rx_state_after": {"planted": "after"},
        "captured_frame": {"planted": "frame"},
    }

    def fake_run_mode(_radio, *, mode, report, **_kwargs) -> None:
        if mode == MODE_MANUAL:
            report["modes"].append(copy.deepcopy(manual))
            return
        raise tandem_quality._EvidenceInvalidWithDetails(
            f"{mode} gain left its settled band during a measurement frame",
            failure_evidence,
        )

    monkeypatch.setattr(tandem_quality, "_run_mode", fake_run_mode)

    with pytest.raises(EvidenceInvalid, match="left its settled band"):
        run_tandem_quality_matrix(_MatrixRadio(options), options)

    report_path = tmp_path / "offline-radio" / "tandem-agc-quality-report.json"
    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted["verdict"] == "invalid"
    assert persisted["fatal_error"].startswith("EvidenceInvalid:")
    assert persisted["failure_evidence"] == failure_evidence


def test_full_runner_rejects_a_planted_live_lo_drift_before_transmit(tmp_path) -> None:
    options = _options(output_dir=tmp_path, center_frequency_hz=5_800_000_000)

    with pytest.raises(EvidenceInvalid, match="live RX/TX LO readback"):
        run_tandem_quality_matrix(_MatrixRadio(options, readback_offset=10), options)
