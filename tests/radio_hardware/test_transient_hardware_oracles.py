"""Offline transport oracles for guarded transient hardware execution."""

from __future__ import annotations

import json
import threading
from builtins import BaseExceptionGroup
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from . import transient_hardware as transient_hardware_module
from .experiment import EvidenceInvalid
from .metadata_abi import (
    TandemEventDirection,
    TandemGainEvent,
    TandemGainTable,
    TandemState,
)
from .tandem_quality import (
    AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES,
    TandemQualityOptions,
    native_mode_name,
)
from .transient_hardware import (
    TRANSIENT_MODES,
    TransientCaptureOptions,
    run_serial_transient_hardware,
    run_transient_hardware,
    validate_transient_options,
)


class _Clocks:
    def __init__(self, *, host_step_ns: int = 100) -> None:
        self.host_ns = 1_000
        self.host_step_ns = host_step_ns
        self.seconds_value = 0.0
        self.wall_ns = 5_000

    def clock_ns(self) -> int:
        value = self.host_ns
        self.host_ns += self.host_step_ns
        return value

    def monotonic(self) -> float:
        self.seconds_value += 0.000_001
        return self.seconds_value

    def wall_clock_ns(self) -> int:
        self.wall_ns += 1_000
        return self.wall_ns


def _tone_raw(*, samples: int, amplitude: float, seed: int) -> bytes:
    np = pytest.importorskip("numpy")
    indexes = np.arange(samples, dtype=np.float64)
    carrier = np.exp(2j * np.pi * 100_000.0 * indexes / 1_000_000)
    rng = np.random.default_rng(seed)
    signal = []
    for channel, phase in enumerate((0.3, -0.2)):
        noise = rng.normal(size=samples) + 1j * rng.normal(size=samples)
        signal.append(
            amplitude * (1.0 - 0.05 * channel) * carrier * np.exp(1j * phase) + noise
        )
    matrix = np.asarray(signal)
    words = np.empty((samples, 4), dtype="<i2")
    words[:, 0] = np.rint(matrix[0].real).astype("<i2")
    words[:, 1] = np.rint(matrix[0].imag).astype("<i2")
    words[:, 2] = np.rint(matrix[1].real).astype("<i2")
    words[:, 3] = np.rint(matrix[1].imag).astype("<i2")
    return words.tobytes()


class _FakeRadio:
    def __init__(self, output_dir: Path) -> None:
        self.options = SimpleNamespace(
            serial="FAKE-TRANSIENT",
            sample_rate_hz=1_000_000,
            samples_per_channel=8_192,
            tx_gain_db=-30.0,
            center_frequency_hz=915_000_000,
            output_dir=output_dir,
        )
        self.identity = {"serial": self.options.serial, "fw_version": "fake-v8"}
        self._report_path: Path | None = None
        self.operations: list[tuple[Any, ...]] = []
        self.mode = "manual"
        self.rx_gain_db = 40.0
        self.tx_gain_db = -89.75
        self.metadata_open = False
        self.buffer_open = False
        self.metadata_by_token: dict[bytes, Any] = {}
        self.metadata_capture_count = 0
        self.metadata_sample = 100_000
        self.metadata_buffer_sequence = 40
        self.metadata_transition_count = 0
        self.metadata_event_sequence = 70
        self.metadata_gain_index = 40
        self.metadata_previous_level = -60.0
        self.sample_counter_low32 = self.metadata_sample
        self.sample_counter_step = 128
        self.freeze_sample_counter = False
        self.scripted_counter_reads: list[int] = []
        self.counter_reads: list[tuple[str, int]] = []
        self.capture_thread_names: list[str] = []
        self.metadata_capture_thread_names: list[str] = []
        self.coordinate_attack_capture = False
        self.attack_capture_waiting = threading.Event()
        self.attack_command_applied = threading.Event()
        self.sample_gap_capture_index: int | None = None
        self.sample_gap_frames = 1
        self.buffer_gap_frames_override: int | None = None
        self.hidden_transition_capture_index: int | None = None
        self.omit_release_event = False
        self.fail_next_capture_with_mute_error = False
        self.mute_failures_remaining = 0
        self.cleanup_verified = False
        self.closed = False

    def mute_all(self) -> None:
        self.tx_gain_db = -89.75
        self.operations.append(("mute_all",))
        if self.mute_failures_remaining:
            self.mute_failures_remaining -= 1
            raise RuntimeError("planted mute failure")

    def arm_tx2_tone(self, *, tone_hz: int, scale: float) -> None:
        self.operations.append(("arm_tx2_tone", tone_hz, scale))

    def set_tx2_gain(self, gain_db: float) -> float:
        self.tx_gain_db = float(gain_db)
        if (
            self.coordinate_attack_capture
            and self.metadata_open
            and self.tx_gain_db > -45.0
        ):
            self.attack_command_applied.set()
        if not self.metadata_open and self.mode != "manual":
            self.rx_gain_db = 20.0 if self.tx_gain_db > -45.0 else 40.0
        self.operations.append(("set_tx2_gain", self.tx_gain_db))
        return self.tx_gain_db

    def configure_rx(self, mode: str, *, manual_gain_db: float | None = None) -> None:
        self.mode = mode
        if mode == "manual":
            assert manual_gain_db is not None
            self.rx_gain_db = float(manual_gain_db)
        else:
            self.rx_gain_db = 20.0 if self.tx_gain_db > -45.0 else 40.0
        self.operations.append(("configure_rx", mode, manual_gain_db))

    def read_rx_state(self) -> dict[str, list[Any]]:
        return {
            "modes": [self.mode, self.mode],
            "gains_db": [self.rx_gain_db, self.rx_gain_db],
        }

    def read_center_frequency(self) -> dict[str, int]:
        return {"rx_lo_hz": 915_000_000, "tx_lo_hz": 915_000_000}

    def tandem_status(self) -> dict[str, int]:
        return {"state": 0, "fault_flags": 0, "fifo_level": 0}

    def buffer(
        self,
        api: str,
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
                    api,
                    kernel_buffers,
                    samples_per_channel,
                    tandem_request is not None,
                )
            )
            self.metadata_open = api == "metadata"
            self.buffer_open = True
            if self.metadata_open:
                self.metadata_previous_level = self.tx_gain_db
            try:
                yield object(), 2 if self.metadata_open else None
            finally:
                self.metadata_open = False
                self.buffer_open = False
                self.operations.append(("buffer_exit", api))

        return opened()

    def _metadata(self, *, samples: int) -> Any:
        events: tuple[TandemGainEvent, ...] = ()
        first_sample = self.metadata_sample
        buffer_sequence = self.metadata_buffer_sequence
        if self.sample_gap_capture_index == self.metadata_capture_count:
            first_sample += samples * self.sample_gap_frames
            buffer_sequence += (
                self.sample_gap_frames
                if self.buffer_gap_frames_override is None
                else self.buffer_gap_frames_override
            )
        if self.hidden_transition_capture_index == self.metadata_capture_count:
            self.metadata_gain_index -= 1
            self.metadata_transition_count += 1
            self.metadata_event_sequence += 1
        louder = self.tx_gain_db > self.metadata_previous_level
        quieter = self.tx_gain_db < self.metadata_previous_level
        emit = louder or (quieter and not self.omit_release_event)
        if emit:
            direction = (
                TandemEventDirection.DECREASE
                if louder
                else TandemEventDirection.INCREASE
            )
            self.metadata_gain_index += -1 if louder else 1
            self.metadata_transition_count += 1
            event = TandemGainEvent(
                sample_sequence=first_sample + 128,
                event_sequence=self.metadata_event_sequence,
                flags=int(direction) << 4,
                rx1_gain_index=self.metadata_gain_index,
                rx2_gain_index=self.metadata_gain_index,
            )
            self.metadata_event_sequence += 1
            events = (event,)
            self.metadata_previous_level = self.tx_gain_db

        metadata = SimpleNamespace(
            samples_per_channel=samples,
            iq_payload_bytes=samples * 8,
            enabled_scan_mask=0x0F,
            channel_count=2,
            flags=0,
            observation_count=4,
            observation_overflow_count=0,
            event_overflow_count=0,
            tandem_state=TandemState.ARMED_AUTO,
            tandem_fault_flags=0,
            gain_table_id=TandemGainTable.MHZ_200_1300,
            minimum_gain_db=0,
            maximum_gain_db=62,
            initial_gain_db=40,
            minimum_gain_index=3,
            maximum_gain_index=65,
            rx1_gain_index=self.metadata_gain_index,
            rx2_gain_index=self.metadata_gain_index,
            bench_gain_indices=(self.metadata_gain_index, self.metadata_gain_index),
            first_sample_sequence=first_sample,
            buffer_sequence=buffer_sequence,
            stream_id=9,
            ownership_epoch=5,
            tandem_transition_count=self.metadata_transition_count,
            threshold_provenance=123,
            ad9361_temperature_mdeg_c=35_000,
            event_count=len(events),
            gain_events=events,
        )
        self.metadata_sample = first_sample + samples
        self.metadata_buffer_sequence = buffer_sequence + 1
        self.metadata_capture_count += 1
        return metadata

    def capture_iq(
        self, _buffer: Any, *, metadata: bool, samples_per_channel: int
    ) -> tuple[bytes, bytes | None, int]:
        self.capture_thread_names.append(threading.current_thread().name)
        if metadata:
            self.metadata_capture_thread_names.append(threading.current_thread().name)
        if (
            metadata
            and self.coordinate_attack_capture
            and self.metadata_capture_count == 3
        ):
            self.attack_capture_waiting.set()
            if not self.attack_command_applied.wait(timeout=2.0):
                raise EvidenceInvalid("planted concurrent command never arrived")
        if self.fail_next_capture_with_mute_error:
            self.fail_next_capture_with_mute_error = False
            self.mute_failures_remaining = 1
            raise EvidenceInvalid("planted capture failure")
        adaptive = self.mode != "manual" or metadata
        amplitude = 400.0 if adaptive else (600.0 if self.tx_gain_db > -45.0 else 160.0)
        raw = _tone_raw(
            samples=samples_per_channel,
            amplitude=amplitude,
            seed=len(self.operations) + self.metadata_capture_count,
        )
        if not metadata:
            return raw, None, 1_000 + len(self.operations)
        parsed = self._metadata(samples=samples_per_channel)
        token = f"metadata-{self.metadata_capture_count}".encode()
        self.metadata_by_token[token] = parsed
        return raw, token, 1_000 + len(self.operations)

    def read_rx_sample_counter_low32(self) -> int:
        if self.scripted_counter_reads:
            value = self.scripted_counter_reads.pop(0)
            self.counter_reads.append((threading.current_thread().name, value))
            return value
        if self.freeze_sample_counter:
            value = self.sample_counter_low32 % (1 << 32)
            self.counter_reads.append((threading.current_thread().name, value))
            return value
        current = max(self.sample_counter_low32, self.metadata_sample)
        value = current % (1 << 32)
        self.counter_reads.append((threading.current_thread().name, value))
        self.sample_counter_low32 = current + self.sample_counter_step
        return value

    def parse_metadata(self, token: bytes) -> Any:
        return self.metadata_by_token[token]

    def close(self) -> None:
        self.closed = True
        self.cleanup_verified = True
        if self._report_path is not None and self._report_path.is_file():
            report = json.loads(self._report_path.read_text(encoding="utf-8"))
            report["cleanup"] = {"verified": True, "failures": []}
            self._report_path.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )


def _quality(output_dir: Path) -> TandemQualityOptions:
    return TandemQualityOptions(
        tx_gain_trajectory_db=(-60.0, -30.0, -60.0),
        physical_attenuation_db=0.0,
        sample_rate_hz=1_000_000,
        samples_per_channel=8_192,
        tone_hz=100_000,
        manual_gain_db=40.0,
        native_gain_control_modes=AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES,
        stable_frames=2,
        measurement_frames=1,
        max_settle_frames=4,
        max_seconds=30.0,
        output_dir=output_dir,
    )


def _capture_options(**overrides: Any) -> TransientCaptureOptions:
    values = {
        "frame_samples": 1_024,
        "window_samples": 256,
        "response_frames": 2,
        "baseline_frames": 1,
        "precondition_stable_frames": 2,
        "max_precondition_frames": 5,
        "baseline_windows": 2,
        "steady_windows": 2,
        "stable_windows": 2,
        "max_host_jitter_ns": 1_000,
        "minimum_native_gain_change_db": 1.0,
    }
    values.update(overrides)
    return TransientCaptureOptions(**values)


def _run_fake(
    radio: _FakeRadio,
    quality: TandemQualityOptions,
    *,
    clocks: _Clocks | None = None,
    capture: TransientCaptureOptions | None = None,
) -> tuple[dict[str, Any], Path]:
    selected_clocks = clocks or _Clocks()
    return run_transient_hardware(
        radio,
        quality,
        capture=capture or _capture_options(),
        clock_ns=selected_clocks.clock_ns,
        monotonic=selected_clocks.monotonic,
        wall_clock_ns=selected_clocks.wall_clock_ns,
        sleep=lambda _seconds: None,
        metadata_parser=radio.parse_metadata,
    )


def test_fake_transport_executes_every_mode_and_writes_atomic_report(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    report, report_path = _run_fake(radio, _quality(tmp_path))

    assert report["verdict"] == "pass"
    assert [mode["mode"] for mode in report["modes"]] == list(TRANSIENT_MODES)
    assert TRANSIENT_MODES == (
        "manual_fixed",
        *(native_mode_name(mode) for mode in AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES),
        "tandem_auto",
    )
    assert "native_hybrid" not in TRANSIENT_MODES
    assert report["trajectory_db"] == [-60.0, -30.0, -60.0]
    assert report["cleanup"] == {
        "verified": False,
        "status": "pending_radio_lifecycle_close",
        "owner": "Issue46Radio.close",
    }
    assert radio._report_path == report_path
    assert not radio.closed
    assert not report_path.with_suffix(".json.tmp").exists()
    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted["verdict"] == "pass"

    buffer_entries = [item for item in radio.operations if item[0] == "buffer_enter"]
    assert [item[1] for item in buffer_entries] == [
        "ordinary",
        "ordinary",
        "ordinary",
        "metadata",
    ]
    assert all(item[2:4] == (1, 1_024) for item in buffer_entries)
    assert buffer_entries[-1][4]
    assert all(not item[4] for item in buffer_entries[:-1])


def test_serial_wrapper_closes_and_reloads_durable_cleanup_proof(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    clocks = _Clocks()
    opened: list[Any] = []

    def factory(iio_module: Any, radio_options: Any) -> _FakeRadio:
        opened.append((iio_module, radio_options))
        return radio

    report, report_path = run_serial_transient_hardware(
        object(),
        radio.options,
        _quality(tmp_path),
        capture=_capture_options(),
        radio_factory=factory,
        clock_ns=clocks.clock_ns,
        monotonic=clocks.monotonic,
        wall_clock_ns=clocks.wall_clock_ns,
        sleep=lambda _seconds: None,
        metadata_parser=radio.parse_metadata,
    )

    assert len(opened) == 1
    assert radio.closed
    assert radio.cleanup_verified
    assert report["cleanup"] == {"verified": True, "failures": []}
    assert report == json.loads(report_path.read_text(encoding="utf-8"))
    assert not report_path.with_suffix(".json.tmp").exists()


def test_serial_wrapper_rejects_missing_durable_cleanup_proof(tmp_path: Path) -> None:
    radio = _FakeRadio(tmp_path)
    clocks = _Clocks()

    def close_without_durable_proof() -> None:
        radio.closed = True
        radio.cleanup_verified = True

    radio.close = close_without_durable_proof  # type: ignore[method-assign]
    with pytest.raises(Exception, match="does not prove cleanup"):
        run_serial_transient_hardware(
            object(),
            radio.options,
            _quality(tmp_path),
            capture=_capture_options(),
            radio_factory=lambda _iio, _options: radio,
            clock_ns=clocks.clock_ns,
            monotonic=clocks.monotonic,
            wall_clock_ns=clocks.wall_clock_ns,
            sleep=lambda _seconds: None,
            metadata_parser=radio.parse_metadata,
        )


def test_serial_wrapper_validates_before_opening_radio(tmp_path: Path) -> None:
    opened = False

    def factory(_iio: Any, _options: Any) -> _FakeRadio:
        nonlocal opened
        opened = True
        return _FakeRadio(tmp_path)

    with pytest.raises(ValueError, match="windows must divide"):
        run_serial_transient_hardware(
            object(),
            SimpleNamespace(),
            _quality(tmp_path),
            capture=_capture_options(window_samples=300),
            radio_factory=factory,
        )
    assert not opened


def test_transient_rejects_non_autonomous_native_set_before_radio_io(
    tmp_path: Path,
) -> None:
    quality = replace(
        _quality(tmp_path),
        native_gain_control_modes=("slow_attack", "fast_attack", "hybrid"),
    )

    with pytest.raises(ValueError, match="autonomous native-mode set"):
        validate_transient_options(quality, _capture_options())


def test_report_retains_immediate_iq_gain_and_tandem_event_evidence(
    tmp_path: Path,
) -> None:
    report, _path = _run_fake(_FakeRadio(tmp_path), _quality(tmp_path))
    modes = {mode["mode"]: mode for mode in report["modes"]}

    manual = modes["manual_fixed"]
    assert manual["attack_frames"][0]["analysis"]["windows"][0]["offset_start"] == 0
    assert manual["gain_evidence"]["gain_span_db"] == [0.0, 0.0]
    assert manual["responses"]["attack"]["steady_change_db"][0] > 10.0

    for native_mode in (
        "native_slow_attack",
        "native_fast_attack",
    ):
        gain = modes[native_mode]["gain_evidence"]
        assert all(value < 0 for value in gain["attack_gain_change_db"])
        assert all(value > 0 for value in gain["release_gain_change_db"])
        assert all(
            bound["evidence"] == "pre_refill_readback"
            for bound in gain["attack_latency_bounds"]
        )

    tandem = modes["tandem_auto"]
    assert tandem["timing_basis"] == "hardware_sample_counter"
    assert [
        transition["response_kind"]
        for transition in tandem["gain_evidence"]["transitions"]
    ] == ["attack", "release"]
    assert all(
        frame["metadata"]["first_sample_sequence"] == frame["first_sample_sequence"]
        for frame in tandem["attack_frames"] + tandem["release_frames"]
    )
    assert report["comparison"][0]["attack"]["maximum_post_clipping_fraction"] == 0.0


def test_host_writes_have_bounded_sample_intervals_and_initial_is_unanchored(
    tmp_path: Path,
) -> None:
    report, _path = _run_fake(_FakeRadio(tmp_path), _quality(tmp_path))
    for mode in report["modes"]:
        commands = {item["command_id"]: item for item in mode["commands"]}
        initial = commands["weak_initial"]
        assert initial["sample_sequence_before"] is None
        assert initial["sample_sequence_after"] is None
        assert initial["timing_role"] == "pre_session_conditioning_write"

        anchor = mode["conditioning_anchor"]
        assert anchor["timing_role"] == "observed_stable_conditioning_interval"
        assert "not the initial write time" in anchor["sample_anchor_policy"]
        assert anchor["sample_uncertainty"] == 1_024

        for command_id in ("strong_attack", "weak_release"):
            command = commands[command_id]
            assert command["sample_uncertainty"] > 0
            if mode["mode"] == "tandem_auto":
                assert command["sample_uncertainty"] == 256
                assert (
                    command["timing_role"]
                    == "host_write_bracketed_by_coherent_fpga_counter"
                )
                assert command["sample_counter_bracket"]["post_write_read_count"] == 2
            else:
                assert command["sample_uncertainty"] == 1_024
                assert command["timing_role"] == "host_write_bracketed_by_observed_iq"
        if mode["mode"] != "tandem_auto":
            assert mode["timing_basis"].startswith("ordinary_session_local_")


def test_tandem_command_bracket_rejects_even_a_matched_metadata_gap(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.sample_gap_capture_index = 3
    with pytest.raises(EvidenceInvalid, match="provider gap is forbidden") as raised:
        _run_fake(radio, _quality(tmp_path))
    assert "buffer 42->44" in str(raised.value)
    assert "sample 102048->104096" in str(raised.value)
    assert "hidden transitions 0" in str(raised.value)


def test_runner_rejects_excessive_command_sample_uncertainty_and_checkpoints(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.sample_counter_step = 1_024
    with pytest.raises(EvidenceInvalid, match=r"uncertainty 2048 exceeds 1024"):
        _run_fake(
            radio,
            _quality(tmp_path),
            capture=_capture_options(max_sample_uncertainty=1_024),
        )

    report_path = tmp_path / radio.options.serial / "tandem-agc-transient-report.json"
    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted["verdict"] == "invalid"
    assert "uncertainty 2048 exceeds 1024" in persisted["fatal_error"]
    assert radio.operations[-1] == ("mute_all",)


def test_tandem_sample_gap_outside_a_command_boundary_remains_fatal(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.sample_gap_capture_index = 4
    with pytest.raises(EvidenceInvalid, match="provider gap is forbidden"):
        _run_fake(radio, _quality(tmp_path))


def test_zero_transition_precondition_gap_is_fatal_under_continuous_acquisition(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.sample_gap_capture_index = 1
    with pytest.raises(EvidenceInvalid, match="provider gap is forbidden") as raised:
        _run_fake(radio, _quality(tmp_path))
    assert "transition delta 0" in str(raised.value)
    assert "hidden transitions 0" in str(raised.value)


def test_tandem_provider_gap_requires_matching_buffer_and_sample_deltas(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.sample_gap_capture_index = 3
    radio.buffer_gap_frames_override = 0
    with pytest.raises(EvidenceInvalid, match="buffer/sample deltas disagree"):
        _run_fake(radio, _quality(tmp_path))

    persisted = json.loads(
        (
            tmp_path / radio.options.serial / "tandem-agc-transient-report.json"
        ).read_text(encoding="utf-8")
    )
    assert "buffer delta 1" in persisted["fatal_error"]
    assert "sample delta 2048" in persisted["fatal_error"]


def test_tandem_provider_gap_cannot_hide_transient_event_timing(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.sample_gap_capture_index = 3
    radio.hidden_transition_capture_index = 3
    with pytest.raises(EvidenceInvalid, match="provider gap is forbidden") as raised:
        _run_fake(radio, _quality(tmp_path))
    assert "transition delta 2" in str(raised.value)
    assert "visible events 1" in str(raised.value)
    assert "hidden transitions 1" in str(raised.value)


def test_runner_fails_closed_when_tandem_release_event_is_missing(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.omit_release_event = True
    with pytest.raises(Exception, match="release|endpoint changed"):
        _run_fake(radio, _quality(tmp_path))

    persisted = json.loads(
        (
            tmp_path / radio.options.serial / "tandem-agc-transient-report.json"
        ).read_text(encoding="utf-8")
    )
    assert persisted["verdict"] == "invalid"


def test_tandem_refills_run_continuously_while_counter_timed_command_executes(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.coordinate_attack_capture = True

    report, _path = _run_fake(radio, _quality(tmp_path))
    tandem = next(mode for mode in report["modes"] if mode["mode"] == "tandem_auto")
    attack = next(
        command
        for command in tandem["commands"]
        if command["command_id"] == "strong_attack"
    )

    assert radio.attack_capture_waiting.is_set()
    assert radio.attack_command_applied.is_set()
    assert set(radio.metadata_capture_thread_names) == {"tandem-transient-acquisition"}
    assert {thread for thread, _value in radio.counter_reads} == {"MainThread"}
    assert tandem["acquisition"]["threaded"] is True
    assert tandem["acquisition"]["kernel_buffers"] == 1
    assert tandem["acquisition"]["consumed_frames"] == (
        len(tandem["preconditioning"]["trace"])
        + len(tandem["attack_frames"])
        + len(tandem["release_frames"])
    )
    assert (
        attack["sample_counter_bracket"]["raw_post_write_advanced"]
        != (attack["sample_counter_bracket"]["raw_post_write_initial"])
    )
    assert all(
        frame["continuity"]["buffer_delta"] in (None, 1)
        and frame["continuity"]["provider_gap_accepted"] is False
        for frame in (
            tandem["preconditioning"]["trace"]
            + tandem["attack_frames"]
            + tandem["release_frames"]
        )
    )


def test_iq_analysis_hashing_and_artifact_writes_wait_for_buffer_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    radio = _FakeRadio(tmp_path)
    analyzed = 0
    written = 0
    real_analyze = transient_hardware_module.analyze_immediate_dual_rx
    real_write = transient_hardware_module._atomic_bytes

    def checked_analyze(*args: Any, **kwargs: Any) -> Any:
        nonlocal analyzed
        assert not radio.buffer_open
        analyzed += 1
        return real_analyze(*args, **kwargs)

    def checked_write(path: Path, value: bytes) -> None:
        nonlocal written
        assert not radio.buffer_open
        written += 1
        real_write(path, value)

    monkeypatch.setattr(
        transient_hardware_module, "analyze_immediate_dual_rx", checked_analyze
    )
    monkeypatch.setattr(transient_hardware_module, "_atomic_bytes", checked_write)
    report, _path = _run_fake(
        radio,
        replace(_quality(tmp_path), save_iq=True),
    )

    unique_frames = [
        frame
        for mode in report["modes"]
        for frame in (
            mode["preconditioning"]["trace"]
            + mode["attack_frames"]
            + mode["release_frames"]
        )
    ]
    assert analyzed == len(unique_frames)
    assert written == len(unique_frames)
    assert all(
        len(frame["sha256"]) == 64
        and frame["analysis"]["samples_per_channel"] == 1_024
        and Path(frame["iq_path"]).is_file()
        for frame in unique_frames
    )


def test_tandem_counter_bracket_requires_post_write_cdc_advance(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.freeze_sample_counter = True
    with pytest.raises(EvidenceInvalid, match="post-write FPGA counter advance"):
        _run_fake(radio, _quality(tmp_path))


def test_low32_extension_accepts_wrap_and_rejects_half_range_ambiguity() -> None:
    modulus = 1 << 32
    assert (
        transient_hardware_module._extend_low32_near(0x20, reference=modulus - 0x10)
        == modulus + 0x20
    )
    with pytest.raises(EvidenceInvalid, match="extension is ambiguous"):
        transient_hardware_module._extend_low32_near(0x80000000, reference=0)


def test_runner_rejects_host_write_jitter_and_still_requests_mute(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    clocks = _Clocks(host_step_ns=1_001)
    with pytest.raises(Exception, match="host jitter"):
        _run_fake(radio, _quality(tmp_path), clocks=clocks)

    assert not any(item[0] == "buffer_enter" for item in radio.operations)
    assert radio.operations[-1] == ("mute_all",)


def test_runner_preserves_body_and_fail_safe_mute_errors(tmp_path: Path) -> None:
    radio = _FakeRadio(tmp_path)
    radio.fail_next_capture_with_mute_error = True
    with pytest.raises(BaseExceptionGroup) as raised:
        _run_fake(radio, _quality(tmp_path))

    def leaves(error: BaseException) -> list[BaseException]:
        if isinstance(error, BaseExceptionGroup):
            return [child for item in error.exceptions for child in leaves(item)]
        return [error]

    messages = [str(error) for error in leaves(raised.value)]
    assert any("planted capture failure" in message for message in messages)
    assert any("planted mute failure" in message for message in messages)
    persisted = json.loads(
        (
            tmp_path / radio.options.serial / "tandem-agc-transient-report.json"
        ).read_text(encoding="utf-8")
    )
    assert persisted["verdict"] == "invalid"
    assert "ExceptionGroup" in persisted["fatal_error"]


def test_static_capture_validation_happens_before_any_radio_operation(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    invalid = _capture_options(window_samples=300)
    with pytest.raises(ValueError, match="windows must divide"):
        _run_fake(radio, _quality(tmp_path), capture=invalid)
    assert radio.operations == []


def test_capture_options_prove_enough_pre_and_post_windows(tmp_path: Path) -> None:
    quality = _quality(tmp_path)
    with pytest.raises(ValueError, match="baseline captures"):
        validate_transient_options(
            quality,
            _capture_options(baseline_windows=5),
        )
    with pytest.raises(ValueError, match="steady windows"):
        validate_transient_options(
            quality,
            _capture_options(response_frames=1, stable_windows=5),
        )
    with pytest.raises(ValueError, match="must cover the retained baseline anchor"):
        validate_transient_options(
            quality,
            _capture_options(max_sample_uncertainty=1_023),
        )
    with pytest.raises(ValueError, match="must be integers"):
        validate_transient_options(
            quality,
            _capture_options(max_event_latency_samples=None),
        )
    with pytest.raises(ValueError, match="deferred IQ bytes"):
        validate_transient_options(
            quality,
            _capture_options(max_precondition_frames=10_000),
        )
