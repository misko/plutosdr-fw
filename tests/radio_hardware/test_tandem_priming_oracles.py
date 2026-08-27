"""Offline lifecycle oracles for deterministic tandem AUTO priming."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from . import tandem_quality
from .tandem_quality import (
    MODE_TANDEM,
    TandemQualityOptions,
    _run_mode,
    default_tx_trajectory,
    validate_options,
)


class _FakeRadio:
    def __init__(self) -> None:
        self.operations: list[tuple[object, ...]] = []
        self.current_tx2_gain_db = -89.75
        self.rx_mode = "manual"
        self.rx_gain_db = 40.0

    def mute_all(self) -> None:
        self.operations.append(("mute_all",))

    def configure_rx(self, mode: str, *, manual_gain_db: float | None = None) -> None:
        self.rx_mode = mode
        if manual_gain_db is not None:
            self.rx_gain_db = float(manual_gain_db)
        self.operations.append(("configure_rx", mode, manual_gain_db))

    def read_rx_state(self) -> dict[str, list[object]]:
        return {
            "modes": [self.rx_mode, self.rx_mode],
            "gains_db": [self.rx_gain_db, self.rx_gain_db],
        }

    def arm_tx2_tone(self, *, tone_hz: int, scale: float) -> None:
        self.operations.append(("arm_tx2_tone", tone_hz, scale))

    def set_tx2_gain(self, gain_db: float) -> float:
        self.current_tx2_gain_db = float(gain_db)
        self.operations.append(("set_tx2_gain", self.current_tx2_gain_db))
        return self.current_tx2_gain_db

    def buffer(
        self,
        layout: str,
        kernel_buffers: int,
        samples_per_channel: int,
        *,
        tandem_request: bytes | None,
    ):
        @contextmanager
        def opened():
            self.operations.append(
                (
                    "buffer_enter",
                    layout,
                    kernel_buffers,
                    samples_per_channel,
                    tandem_request is not None,
                )
            )
            try:
                yield object(), 2
            finally:
                self.operations.append(("buffer_exit",))

        return opened()


@pytest.mark.parametrize("profile", ["smoke", "full"])
def test_tandem_mode_primes_at_distinct_level_median_before_measurement(
    monkeypatch: pytest.MonkeyPatch, tmp_path, profile: str
) -> None:
    trajectory = default_tx_trajectory(profile)
    options = TandemQualityOptions(
        tx_gain_trajectory_db=trajectory,
        physical_attenuation_db=0.0,
        output_dir=tmp_path,
    )
    validate_options(options)
    radio = _FakeRadio()
    settled = SimpleNamespace(
        rx1_gain_index=65,
        rx2_gain_index=65,
        maximum_gain_index=65,
        bench_gain_indices=(65, 65),
    )
    settled_at: list[float] = []
    measured_at: list[tuple[int, float]] = []
    deadline_checks: list[None] = []

    monkeypatch.setattr(
        tandem_quality,
        "_wait_for_idle",
        lambda _radio: {"state": 0, "fault_flags": 0, "fifo_level": 0},
    )
    monkeypatch.setattr(tandem_quality, "_atomic_json", lambda *_args: None)
    monkeypatch.setattr(
        tandem_quality,
        "_metadata_dict",
        lambda metadata: {
            "bench_gain_indices": list(metadata.bench_gain_indices),
            "maximum_gain_index": metadata.maximum_gain_index,
        },
    )

    def fake_settle(_radio, _buffer, *, options):
        del options
        settled_at.append(radio.current_tx2_gain_db)
        return (
            [
                {
                    "metadata": {
                        "gain_events": [
                            {
                                "direction": int(
                                    tandem_quality.TandemEventDirection.INCREASE
                                )
                            }
                        ]
                    }
                }
            ],
            settled,
        )

    def fake_measure(
        _radio,
        _buffer,
        *,
        options,
        output_dir,
        level_index,
        settled,
    ):
        del options, output_dir, settled
        measured_at.append((level_index, radio.current_tx2_gain_db))
        return [{"quality": {"quality_valid": True}}]

    monkeypatch.setattr(tandem_quality, "_settle_tandem", fake_settle)
    monkeypatch.setattr(tandem_quality, "_measure_tandem", fake_measure)
    monkeypatch.setattr(
        tandem_quality,
        "summarize_measurements",
        lambda _measurements: {"quality_valid": True},
    )

    report: dict[str, object] = {"modes": []}
    _run_mode(
        radio,
        mode=MODE_TANDEM,
        options=options,
        report=report,
        report_path=tmp_path / "report.json",
        check_deadline=lambda: deadline_checks.append(None),
    )

    mode_record = report["modes"][0]
    priming = mode_record["priming"]
    assert priming["selection"] == {
        "method": "median_of_sorted_distinct_trajectory_gains",
        "distinct_trajectory_gains_db": sorted(set(trajectory)),
        "authorized_strongest_tx2_gain_db": -30.0,
    }
    assert priming["tx2_gain_requested_db"] == -45.0
    assert priming["tx2_gain_readback_db"] == -45.0
    assert priming["effective_attenuation_db"] == 45.0
    assert priming["quality_gate_applied"] is False
    assert priming["summary"]["reached_maximum_gain"] is True
    assert priming["final_metadata"] == {
        "bench_gain_indices": [65, 65],
        "maximum_gain_index": 65,
    }

    commanded_gains = [
        operation[1] for operation in radio.operations if operation[0] == "set_tx2_gain"
    ]
    assert commanded_gains == [-61.0, -45.0, *trajectory]
    buffer_enter = next(
        index
        for index, operation in enumerate(radio.operations)
        if operation[0] == "buffer_enter"
    )
    prime_command = next(
        index
        for index, operation in enumerate(radio.operations)
        if operation == ("set_tx2_gain", -45.0) and index > buffer_enter
    )
    assert buffer_enter < prime_command
    assert settled_at == [-45.0, *trajectory]
    assert measured_at == list(enumerate(trajectory))
    assert len(deadline_checks) == len(trajectory) + 1


def test_tandem_priming_maximum_is_diagnostic_not_a_fixture_requirement(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    trajectory = default_tx_trajectory("smoke")
    options = TandemQualityOptions(
        tx_gain_trajectory_db=trajectory,
        physical_attenuation_db=0.0,
        output_dir=tmp_path,
    )
    radio = _FakeRadio()
    settled = SimpleNamespace(
        rx1_gain_index=58,
        rx2_gain_index=58,
        maximum_gain_index=65,
        bench_gain_indices=(58, 58),
    )

    monkeypatch.setattr(
        tandem_quality,
        "_wait_for_idle",
        lambda _radio: {"state": 0, "fault_flags": 0, "fifo_level": 0},
    )
    monkeypatch.setattr(tandem_quality, "_atomic_json", lambda *_args: None)
    monkeypatch.setattr(
        tandem_quality,
        "_metadata_dict",
        lambda metadata: {
            "bench_gain_indices": list(metadata.bench_gain_indices),
            "maximum_gain_index": metadata.maximum_gain_index,
        },
    )
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
        "summarize_measurements",
        lambda _measurements: {"quality_valid": True},
    )

    report: dict[str, object] = {"modes": []}
    _run_mode(
        radio,
        mode=MODE_TANDEM,
        options=options,
        report=report,
        report_path=tmp_path / "report.json",
        check_deadline=lambda: None,
    )

    summary = report["modes"][0]["priming"]["summary"]
    assert summary["final_gain_indices"] == [58, 58]
    assert summary["reached_maximum_gain"] is False
