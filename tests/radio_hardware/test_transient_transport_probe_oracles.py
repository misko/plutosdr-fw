"""Offline acceptance and rejection oracles for the weak transport probe."""

from __future__ import annotations

import copy
import errno
import json
import threading
from builtins import BaseExceptionGroup
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from . import transient_transport_probe as probe_module
from .experiment import EvidenceInvalid, FixtureSafetyError
from .metadata_abi import (
    FEATURE_AD9361_TEMPERATURE,
    FEATURE_FPGA_GAIN_EVENTS,
    FEATURE_HARDWARE_SAMPLE_COUNTER,
    FEATURE_TANDEM_METADATA,
    FLAG_HARDWARE_SAMPLE_COUNTER_VALID,
    FLAG_SAMPLE_SEQUENCE_VALID,
    FLAG_TANDEM_METADATA_VALID,
    TANDEM_REQUEST,
    TandemEventDirection,
    TandemEventReason,
    TandemGainEvent,
    TandemGainTable,
    TandemMode,
    TandemState,
)
from .tandem_quality import TandemQualityOptions
from .transient_transport_probe import (
    PROBE_PENDING_VERDICT,
    PROBE_THREAD_NAME,
    TransientTransportProbeOptions,
    run_serial_transient_transport_probe,
    run_transient_transport_probe,
    validate_transient_transport_probe_report,
)

_REQUIRED_FEATURES = (
    FEATURE_AD9361_TEMPERATURE
    | FEATURE_FPGA_GAIN_EVENTS
    | FEATURE_HARDWARE_SAMPLE_COUNTER
    | FEATURE_TANDEM_METADATA
)
_REQUIRED_FLAGS = (
    FLAG_SAMPLE_SEQUENCE_VALID
    | FLAG_HARDWARE_SAMPLE_COUNTER_VALID
    | FLAG_TANDEM_METADATA_VALID
)


def _tone_raw(
    samples: int, *, rx0_amplitude: float = 600.0, rx1_amplitude: float = 570.0
) -> bytes:
    np = pytest.importorskip("numpy")
    indexes = np.arange(samples, dtype=np.float64)
    carrier = np.exp(2j * np.pi * 100_000.0 * indexes / 2_500_000.0)
    words = np.empty((samples, 4), dtype="<i2")
    words[:, 0] = np.rint(rx0_amplitude * carrier.real).astype("<i2")
    words[:, 1] = np.rint(rx0_amplitude * carrier.imag).astype("<i2")
    words[:, 2] = np.rint(rx1_amplitude * carrier.real).astype("<i2")
    words[:, 3] = np.rint(rx1_amplitude * carrier.imag).astype("<i2")
    return words.tobytes()


class _Clock:
    def __init__(self) -> None:
        self.value = 10_000

    def __call__(self) -> int:
        self.value += 100
        return self.value


class _FakeBuffer:
    def __init__(self, radio: _FakeProbeRadio) -> None:
        self.radio = radio

    def cancel(self) -> None:
        self.radio.operations.append(("buffer_cancel",))
        self.radio.cancel_calls += 1
        self.radio.cancelled.set()
        if self.radio.cancel_failures:
            self.radio.cancel_failures -= 1
            raise RuntimeError("planted cancel failure")


class _FakeProbeRadio:
    def __init__(self, output_dir: Path) -> None:
        self.options = SimpleNamespace(
            serial="FAKE-TRANSPORT-PROBE",
            sample_rate_hz=2_500_000,
            samples_per_channel=65_536,
            tx_gain_db=-45.0,
            center_frequency_hz=915_000_000,
            attenuation_db=0.0,
            output_dir=output_dir,
        )
        self.identity = {
            "serial": self.options.serial,
            "fw_version": "fake-rc2",
            "libiio_source_commit": "1" * 40,
        }
        self._report_path: Path | None = None
        self.operations: list[tuple[Any, ...]] = []
        self.mode = "manual"
        self.rx_gain_db = 40.0
        self.tx_gain_db = -89.75
        self.buffer_open = False
        self.cancelled = threading.Event()
        self.blocked_refill = threading.Event()
        self.cancel_calls = 0
        self.mute_failures = 0
        self.buffer_mute_failures = 0
        self.cancel_failures = 0
        self.buffer_close_failures = 0
        self.hold_open_failures = 0
        self.hold_close_failures = 0
        self.hold_fifo_after_clear = 0
        self.hold_fifo_after_close: int | None = None
        self.hold_active = False
        self.close_failures = 0
        self.cleanup_verified = False
        self.capture_count = 0
        self.capture_attempts = 0
        self.startup_eagain_attempts = 0
        self.startup_eagain_remaining = 0
        self.block_capture_at: int | None = None
        self.worker_error_at: int | None = None
        self.gap_at: int | None = None
        self.buffer_gap_frames = 1
        self.sample_gap_frames = 1
        self.hidden_transition_at: int | None = None
        self.visible_event_at: set[int] = set()
        self.bad_event_sequence_at: int | None = None
        self.bad_event_step_at: int | None = None
        self.bad_event_range_at: int | None = None
        self.bad_event_sample_at: int | None = None
        self.bad_event_flags_at: int | None = None
        self.regressed_event_samples_at: int | None = None
        self.dense_events_at: int | None = None
        self.dense_event_count = 2
        self.dense_event_spacing_samples = 1
        self.stream_change_at: int | None = None
        self.zero_epoch_at: int | None = None
        self.missing_feature_at: int | None = None
        self.missing_valid_flag_at: int | None = None
        self.unsafe_flag_at: int | None = None
        self.overflow_at: int | None = None
        self.excess_observations_at: int | None = None
        self.bad_sample_format_at: int | None = None
        self.bad_threshold_provenance_at: int | None = None
        self.bad_initial_gain_at: int | None = None
        self.auto_initial_endpoint_offset = 0
        self.nonmax_endpoint_without_event_at: int | None = None
        self.first_unrepresented_transitions = 0
        self.readback_offset_db = 0.0
        self.first_sample = 10_000_000
        self.buffer_sequence = 0
        self.transition_count = 0
        self.event_sequence = 100
        self.gain_index = 40
        self.fifo_level = 0
        self.auto_request_initial_gain_db: int | None = None
        self.hold_request_initial_gain_db: int | None = None
        self.sample_counter = self.first_sample
        self.refill_ns = 1_000_000
        self.metadata_by_token: dict[bytes, Any] = {}
        self.capture_thread_names: list[str] = []
        self.raw = _tone_raw(self.options.samples_per_channel)
        self.closed = False

    def _mute_evidence(self) -> dict[str, Any]:
        return {
            "verified": True,
            "tx1_gain_db": -89.75,
            "tx2_gain_db": -89.75,
            "selectors": [3, 3, 3, 3],
            "dds": {
                f"altvoltage{index}": {
                    "present": True,
                    "raw": 0.0,
                    "scale": 0.0,
                }
                for index in range(8)
            },
            "failures": [],
        }

    def mute_all(self) -> dict[str, Any]:
        self.operations.append(("mute", self.buffer_open))
        self.tx_gain_db = -89.75
        if self.mute_failures:
            self.mute_failures -= 1
            raise RuntimeError("planted mute failure")
        if self.buffer_open and self.buffer_mute_failures:
            self.buffer_mute_failures -= 1
            raise RuntimeError("planted mute failure")
        return self._mute_evidence()

    def arm_tx2_tone(self, *, tone_hz: int, scale: float) -> None:
        self.operations.append(("arm_tone", tone_hz, scale))

    def set_tx2_gain(self, gain_db: float) -> float:
        if gain_db > self.options.tx_gain_db:
            raise FixtureSafetyError("planted radio rejected strong TX")
        self.tx_gain_db = float(gain_db)
        self.operations.append(("set_tx2_gain", self.tx_gain_db))
        return self.tx_gain_db + self.readback_offset_db

    def configure_rx(self, mode: str, *, manual_gain_db: float | None = None) -> None:
        self.mode = mode
        if manual_gain_db is not None:
            self.rx_gain_db = float(manual_gain_db)
        self.operations.append(("configure_rx", mode, manual_gain_db))

    def read_rx_state(self) -> dict[str, list[Any]]:
        return {
            "modes": [self.mode, self.mode],
            "gains_db": [self.rx_gain_db, self.rx_gain_db],
        }

    def read_center_frequency(self) -> dict[str, int]:
        return {"rx_lo_hz": 915_000_000, "tx_lo_hz": 915_000_000}

    def tandem_status(self) -> dict[str, int]:
        return {
            "state": int(
                TandemState.ARMED_HOLD if self.hold_active else TandemState.IDLE
            ),
            "fault_flags": 0,
            "overflow_count": 0,
            "fifo_level": self.fifo_level,
            "ownership_epoch": 7 if self.hold_active else 0,
            "transition_count": self.transition_count,
            "rx1_gain_index": self.gain_index,
            "rx2_gain_index": self.gain_index,
        }

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
            assert api == "metadata"
            assert samples_per_channel == 65_536
            assert (
                tandem_request is not None
                and len(tandem_request) == TANDEM_REQUEST.size
            )
            unpacked_request = TANDEM_REQUEST.unpack(tandem_request)
            request_mode = TandemMode(unpacked_request[4])
            request_initial_gain_db = int(unpacked_request[9])
            is_hold = request_mode is TandemMode.HOLD
            if is_hold:
                self.hold_request_initial_gain_db = request_initial_gain_db
            else:
                self.auto_request_initial_gain_db = request_initial_gain_db
            assert kernel_buffers == (1 if is_hold else 2)
            operation_prefix = "hold_buffer" if is_hold else "buffer"
            self.operations.append((f"{operation_prefix}_enter", api, kernel_buffers))
            if is_hold and self.hold_open_failures:
                self.hold_open_failures -= 1
                raise RuntimeError("planted HOLD FIFO clear open failure")
            self.buffer_open = True
            self.cancelled.clear()
            if is_hold:
                self.hold_active = True
                self.fifo_level = self.hold_fifo_after_clear
                self.transition_count = 0
                self.event_sequence = 0
            else:
                self.gain_index = 65 + self.auto_initial_endpoint_offset
                self.transition_count = 0
                self.event_sequence = 0
            body_error: BaseException | None = None
            try:
                yield _FakeBuffer(self), 2
            except BaseException as error:  # noqa: BLE001
                body_error = error
            close_error: BaseException | None = None
            self.buffer_open = False
            self.hold_active = False
            if is_hold and self.hold_fifo_after_close is not None:
                self.fifo_level = self.hold_fifo_after_close
            self.operations.append((f"{operation_prefix}_close",))
            if is_hold and self.hold_close_failures:
                self.hold_close_failures -= 1
                close_error = RuntimeError("planted HOLD FIFO clear close failure")
            elif not is_hold and self.buffer_close_failures:
                self.buffer_close_failures -= 1
                close_error = RuntimeError("planted buffer close failure")
            if body_error is not None and close_error is not None:
                raise BaseExceptionGroup(
                    "planted buffer body and close failure", [body_error, close_error]
                )
            if body_error is not None:
                raise body_error.with_traceback(body_error.__traceback__)
            if close_error is not None:
                raise close_error

        return opened()

    def _metadata(self, samples: int) -> Any:
        index = self.capture_count
        first_sample = self.first_sample
        buffer_sequence = self.buffer_sequence
        if self.gap_at == index:
            first_sample += samples * self.sample_gap_frames
            buffer_sequence += self.buffer_gap_frames

        events: tuple[TandemGainEvent, ...] = ()
        if self.dense_events_at == index:
            built_events = []
            for event_index in range(self.dense_event_count):
                direction = (
                    TandemEventDirection.DECREASE
                    if event_index % 2 == 0
                    else TandemEventDirection.INCREASE
                )
                reason = (
                    TandemEventReason.BOTH_LOW_POWER
                    if direction is TandemEventDirection.INCREASE
                    else TandemEventReason.LARGE_ADC_OVERLOAD
                )
                self.gain_index += (
                    1 if direction is TandemEventDirection.INCREASE else -1
                )
                built_events.append(
                    TandemGainEvent(
                        sample_sequence=(
                            first_sample
                            + 1
                            + event_index * self.dense_event_spacing_samples
                        ),
                        event_sequence=self.event_sequence + event_index,
                        flags=(int(direction) << 4) | int(reason),
                        rx1_gain_index=self.gain_index,
                        rx2_gain_index=self.gain_index,
                    )
                )
            events = tuple(built_events)
            self.transition_count += self.dense_event_count
            self.event_sequence += self.dense_event_count
        elif self.regressed_event_samples_at == index:
            direction = TandemEventDirection.DECREASE
            event_flags = (int(direction) << 4) | int(
                TandemEventReason.LARGE_ADC_OVERLOAD
            )
            events = (
                TandemGainEvent(
                    sample_sequence=first_sample + 512,
                    event_sequence=self.event_sequence,
                    flags=event_flags,
                    rx1_gain_index=self.gain_index - 1,
                    rx2_gain_index=self.gain_index - 1,
                ),
                TandemGainEvent(
                    sample_sequence=first_sample + 256,
                    event_sequence=self.event_sequence + 1,
                    flags=event_flags,
                    rx1_gain_index=self.gain_index - 2,
                    rx2_gain_index=self.gain_index - 2,
                ),
            )
            self.gain_index -= 2
            self.transition_count += 2
            self.event_sequence += 2
        elif index in self.visible_event_at:
            direction = TandemEventDirection.DECREASE
            next_gain = self.gain_index - 1
            if self.bad_event_step_at == index:
                next_gain -= 1
            event_sequence = self.event_sequence
            if self.bad_event_sequence_at == index:
                event_sequence += 1
            event_sample = first_sample + 256
            if self.bad_event_sample_at == index:
                event_sample = first_sample + samples
            flags = (int(direction) << 4) | int(TandemEventReason.LARGE_ADC_OVERLOAD)
            if self.bad_event_flags_at == index:
                flags |= 1 << 8
            event_gain = next_gain
            if self.bad_event_range_at == index:
                event_gain = 66
            events = (
                TandemGainEvent(
                    sample_sequence=event_sample,
                    event_sequence=event_sequence,
                    flags=flags,
                    rx1_gain_index=event_gain,
                    rx2_gain_index=event_gain,
                ),
            )
            self.gain_index = event_gain
            self.transition_count += 1
            self.event_sequence += 1
        if self.hidden_transition_at == index:
            self.gain_index -= 1
            self.transition_count += 1
        if self.nonmax_endpoint_without_event_at == index:
            self.gain_index = 64

        features = _REQUIRED_FEATURES
        flags = _REQUIRED_FLAGS
        stream_id = 9
        ownership_epoch = 5
        observation_overflow = 0
        observation_count = 4
        if self.missing_feature_at == index:
            features &= ~FEATURE_TANDEM_METADATA
        if self.missing_valid_flag_at == index:
            flags &= ~FLAG_TANDEM_METADATA_VALID
        if self.unsafe_flag_at == index:
            flags |= 1 << 11
        if self.stream_change_at == index:
            stream_id += 1
        if self.zero_epoch_at == index:
            ownership_epoch = 0
        if self.overflow_at == index:
            observation_overflow = 1
        if self.excess_observations_at == index:
            observation_count = 6
        sample_format = 0 if self.bad_sample_format_at == index else 1
        threshold_provenance = (
            1 if self.bad_threshold_provenance_at == index else 572_733_972
        )
        transition_count = self.transition_count
        if index == 0:
            transition_count += self.first_unrepresented_transitions

        metadata = SimpleNamespace(
            version=5,
            header_bytes=3_256,
            features=features,
            flags=flags,
            stream_id=stream_id,
            buffer_sequence=buffer_sequence,
            first_sample_sequence=first_sample,
            samples_per_channel=samples,
            iq_payload_bytes=samples * 8,
            enabled_scan_mask=0x0F,
            sample_format=sample_format,
            channel_count=2,
            observation_count=observation_count,
            observation_capacity=64,
            event_count=len(events),
            event_capacity=64,
            observation_overflow_count=observation_overflow,
            event_overflow_count=0,
            ownership_epoch=ownership_epoch,
            tandem_state=TandemState.ARMED_AUTO,
            tandem_fault_flags=0,
            tandem_transition_count=transition_count,
            gain_table_id=TandemGainTable.MHZ_200_1300,
            threshold_provenance=threshold_provenance,
            minimum_gain_db=0,
            maximum_gain_db=62,
            initial_gain_db=(
                40
                if self.bad_initial_gain_at == index
                else self.auto_request_initial_gain_db
            ),
            minimum_gain_index=3,
            maximum_gain_index=65,
            rx1_gain_index=self.gain_index,
            rx2_gain_index=self.gain_index,
            bench_gain_indices=(self.gain_index, self.gain_index),
            ad9361_temperature_mdeg_c=35_000,
            gain_events=events,
        )
        self.first_sample = first_sample + samples
        self.buffer_sequence = buffer_sequence + 1
        self.capture_count += 1
        return metadata

    def capture_iq(
        self, _buffer: Any, *, metadata: bool, samples_per_channel: int
    ) -> tuple[bytes, bytes | None, int]:
        assert metadata is True
        self.capture_thread_names.append(threading.current_thread().name)
        self.capture_attempts += 1
        for attempt in range(65):
            if not self.startup_eagain_remaining:
                break
            self.startup_eagain_remaining -= 1
            self.startup_eagain_attempts += 1
            if attempt == 64:
                raise OSError(errno.EAGAIN, "planted bounded startup EAGAIN")
        if self.block_capture_at == self.capture_count:
            self.blocked_refill.set()
            if not self.cancelled.wait(timeout=2.0):
                raise EvidenceInvalid("planted blocked refill was not cancelled")
            raise OSError(errno.EBADF, "planted cancelled refill")
        if self.worker_error_at == self.capture_count:
            raise EvidenceInvalid("planted acquisition worker failure")
        parsed = self._metadata(samples_per_channel)
        token = f"metadata-{self.capture_count}".encode()
        self.metadata_by_token[token] = parsed
        self.refill_ns += 1_000_000
        return self.raw, token, self.refill_ns

    def parse_metadata(self, token: bytes) -> Any:
        return self.metadata_by_token[token]

    def read_rx_sample_counter_low32(self) -> int:
        current = max(self.sample_counter, self.first_sample)
        self.sample_counter = current + 256
        return current % (1 << 32)

    def close(self) -> None:
        self.closed = True
        self.cleanup_verified = self.close_failures == 0
        cleanup = {
            **self._mute_evidence(),
            "verified": self.cleanup_verified,
        }
        if self._report_path is not None and self._report_path.is_file():
            report = json.loads(self._report_path.read_text(encoding="utf-8"))
            report["cleanup"] = cleanup
            self._report_path.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if self.close_failures:
            self.close_failures -= 1
            raise RuntimeError("planted radio close failure")


def _quality(output_dir: Path) -> TandemQualityOptions:
    return TandemQualityOptions(
        tx_gain_trajectory_db=(-61.0, -45.0, -30.0, -45.0, -61.0),
        physical_attenuation_db=0.0,
        sample_rate_hz=2_500_000,
        samples_per_channel=65_536,
        max_seconds=30.0,
        output_dir=output_dir,
    )


def _run_fake(
    radio: _FakeProbeRadio,
    quality: TandemQualityOptions,
) -> tuple[dict[str, Any], Path]:
    return run_transient_transport_probe(
        radio,
        quality,
        clock_ns=_Clock(),
        metadata_parser=radio.parse_metadata,
    )


def _failure_report(radio: _FakeProbeRadio) -> dict[str, Any]:
    assert radio._report_path is not None and radio._report_path.is_file()
    return json.loads(radio._report_path.read_text(encoding="utf-8"))


def _forge_mid_session_event_excursion(
    report: dict[str, Any], *, spacing_samples: int
) -> dict[str, Any]:
    forged = copy.deepcopy(report)
    frames = forged["frames"]
    event_frame_index = 10
    event_frame = frames[event_frame_index]
    first_sample = event_frame["first_sample_sequence"]
    directions = (
        TandemEventDirection.DECREASE,
        TandemEventDirection.INCREASE,
    )
    reasons = (
        TandemEventReason.LARGE_ADC_OVERLOAD,
        TandemEventReason.BOTH_LOW_POWER,
    )
    gains = (64, 65)
    events = []
    for index, (direction, reason, gain) in enumerate(
        zip(directions, reasons, gains, strict=True)
    ):
        events.append(
            {
                "sample_sequence": first_sample + 256 + index * spacing_samples,
                "event_sequence": index,
                "flags": (int(direction) << 4) | int(reason),
                "direction": int(direction),
                "direction_name": direction.name.lower(),
                "reason": int(reason),
                "reason_name": reason.name.lower(),
                "rx1_gain_index": gain,
                "rx2_gain_index": gain,
            }
        )
    for index, frame in enumerate(frames[event_frame_index:], start=event_frame_index):
        frame["metadata"].update(
            tandem_transition_count=2,
            event_count=2 if index == event_frame_index else 0,
            gain_events=events if index == event_frame_index else [],
        )
        frame["continuity"].update(
            transition_count_delta=2 if index == event_frame_index else 0,
            visible_event_count=2 if index == event_frame_index else 0,
        )
    for name in ("initial_stable_suffix", "final_stable_suffix"):
        forged[name]["transition_count"] = 2
    return forged


def test_probe_accepts_exact_weak_continuous_transport(tmp_path: Path) -> None:
    radio = _FakeProbeRadio(tmp_path)
    radio.block_capture_at = 40
    radio.startup_eagain_remaining = 3
    report, path = _run_fake(radio, _quality(tmp_path))

    assert path.is_file()
    assert report["verdict"] == PROBE_PENDING_VERDICT
    assert report["release_pass_eligible"] is False
    assert radio.auto_request_initial_gain_db == 62
    assert report["configuration"]["probe"]["auto_initial_gain_db"] == 62
    assert report["metadata_request"]["decoded"]["initial_gain_db"] == 62
    assert report["evidence_policy"]["auto_initial_gain_db"] == 62
    assert all(frame["metadata"]["initial_gain_db"] == 62 for frame in report["frames"])
    assert all(
        frame["metadata"]["tandem_transition_count"] == 0
        and frame["metadata"]["event_count"] == 0
        and frame["metadata"]["bench_gain_indices"]
        == [frame["metadata"]["gain_index_range"][1]] * 2
        for frame in report["frames"]
    )
    assert report["stale_fifo_normalization"]["action"] == "not_required"
    assert report["stale_fifo_normalization"]["stale_fifo_events"] == 0
    assert report["stale_fifo_normalization"]["hold_session"] is None
    assert not any(
        operation[0] == "hold_buffer_enter" for operation in radio.operations
    )
    assert len(report["frames"]) == 40
    assert report["frames"][31]["probe_phase"] == "uncontended_continuity"
    assert report["command_contention"]["command"]["requested_level_db"] == -45.0
    assert report["command_contention"]["partition"]["fully_post_command_frames"] >= 2
    assert report["conditioning_anchor_candidate"]["sample_count"] == 8_192
    assert report["conditioning_anchor_candidate"]["byte_count"] == 65_536
    assert len(report["conditioning_anchor_candidate"]["tail_sha256"]) == 64
    assert radio.blocked_refill.is_set()
    assert radio.cancel_calls == 1
    assert radio.startup_eagain_attempts == 3
    assert set(radio.capture_thread_names) == {PROBE_THREAD_NAME}
    assert all(
        operation[1] <= -45.0
        for operation in radio.operations
        if operation[0] == "set_tx2_gain"
    )
    cancel_index = radio.operations.index(("buffer_cancel",))
    close_index = radio.operations.index(("buffer_close",))
    assert any(
        operation == ("mute", True) for operation in radio.operations[:cancel_index]
    )
    assert cancel_index < close_index
    assert not any(thread.name == PROBE_THREAD_NAME for thread in threading.enumerate())
    validate_transient_transport_probe_report(report, _quality(tmp_path))


def test_probe_clears_stale_fifo_in_muted_hold_before_tx(tmp_path: Path) -> None:
    radio = _FakeProbeRadio(tmp_path)
    radio.fifo_level = 8
    report, _path = _run_fake(radio, _quality(tmp_path))

    normalization = report["stale_fifo_normalization"]
    assert normalization["stale_fifo_events"] == 8
    assert normalization["action"] == "muted_hold_session_acquire_clear"
    hold = normalization["hold_session"]
    assert hold["metadata_request"]["decoded"]["mode"] == int(TandemMode.HOLD)
    assert hold["metadata_request"]["decoded"]["initial_gain_db"] == 40
    assert report["metadata_request"]["decoded"]["initial_gain_db"] == 62
    assert hold["metadata_abi"] == 2
    assert hold["refill_count"] == 0
    assert hold["opened"] is True and hold["closed"] is True
    assert hold["status_while_open"]["state"] == int(TandemState.ARMED_HOLD)
    assert hold["status_while_open"]["ownership_epoch"] > 0
    assert hold["status_while_open"]["fifo_level"] == 0
    assert normalization["status_after"]["state"] == int(TandemState.IDLE)
    assert normalization["status_after"]["ownership_epoch"] == 0
    assert normalization["status_after"]["fifo_level"] == 0
    assert normalization["rx_state_before"] == normalization["rx_state_after"]

    mute_index = radio.operations.index(("mute", False))
    hold_enter = radio.operations.index(("hold_buffer_enter", "metadata", 1))
    hold_close = radio.operations.index(("hold_buffer_close",))
    arm_index = next(
        index
        for index, operation in enumerate(radio.operations)
        if operation[0] == "arm_tone"
    )
    tx_index = next(
        index
        for index, operation in enumerate(radio.operations)
        if operation[0] == "set_tx2_gain"
    )
    assert mute_index < hold_enter < hold_close < arm_index < tx_index
    validate_transient_transport_probe_report(report, _quality(tmp_path))


def test_probe_fifo_clear_open_failure_never_arms_tx(tmp_path: Path) -> None:
    radio = _FakeProbeRadio(tmp_path)
    radio.fifo_level = 8
    radio.hold_open_failures = 1

    with pytest.raises(BaseException, match="HOLD FIFO clear open failure"):
        _run_fake(radio, _quality(tmp_path))

    assert not any(
        operation[0] in {"arm_tone", "set_tx2_gain"} for operation in radio.operations
    )
    hold_enter = radio.operations.index(("hold_buffer_enter", "metadata", 1))
    assert any(
        operation == ("mute", False) for operation in radio.operations[:hold_enter]
    )
    assert any(
        operation == ("mute", False) for operation in radio.operations[hold_enter + 1 :]
    )
    assert _failure_report(radio)["verdict"] == "invalid"


def test_probe_rejects_impossible_stale_fifo_level_before_tx(
    tmp_path: Path,
) -> None:
    radio = _FakeProbeRadio(tmp_path)
    radio.fifo_level = 65

    with pytest.raises(BaseException, match="FIFO level is invalid"):
        _run_fake(radio, _quality(tmp_path))

    assert not any(
        operation[0] in {"hold_buffer_enter", "arm_tone", "set_tx2_gain"}
        for operation in radio.operations
    )
    assert _failure_report(radio)["verdict"] == "invalid"


def test_probe_rejects_fifo_remaining_after_hold_close_before_tx(
    tmp_path: Path,
) -> None:
    radio = _FakeProbeRadio(tmp_path)
    radio.fifo_level = 8
    radio.hold_fifo_after_close = 8

    with pytest.raises(BaseException, match="FIFO remains nonempty"):
        _run_fake(radio, _quality(tmp_path))

    assert not any(
        operation[0] in {"arm_tone", "set_tx2_gain"} for operation in radio.operations
    )
    hold_close = radio.operations.index(("hold_buffer_close",))
    assert any(
        operation == ("mute", False) for operation in radio.operations[hold_close + 1 :]
    )
    assert _failure_report(radio)["verdict"] == "invalid"


def test_probe_hold_close_failure_is_muted_and_never_arms_tx(tmp_path: Path) -> None:
    radio = _FakeProbeRadio(tmp_path)
    radio.fifo_level = 8
    radio.hold_close_failures = 1

    with pytest.raises(BaseException, match="HOLD FIFO clear close failure"):
        _run_fake(radio, _quality(tmp_path))

    assert not any(
        operation[0] in {"arm_tone", "set_tx2_gain"} for operation in radio.operations
    )
    hold_close = radio.operations.index(("hold_buffer_close",))
    assert any(
        operation == ("mute", False) for operation in radio.operations[hold_close + 1 :]
    )
    assert _failure_report(radio)["verdict"] == "invalid"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        (lambda radio: setattr(radio, "gap_at", 39), "provider gap"),
        (
            lambda radio: (
                setattr(radio, "gap_at", 20),
                setattr(radio, "buffer_gap_frames", 2),
                setattr(radio, "sample_gap_frames", 1),
            ),
            "buffer/sample deltas disagree",
        ),
        (lambda radio: setattr(radio, "hidden_transition_at", 12), "lost gain-event"),
        (
            lambda radio: setattr(radio, "first_unrepresented_transitions", 1),
            "unrepresented prior transitions",
        ),
        (
            lambda radio: radio.visible_event_at.add(0),
            "represented startup transition",
        ),
        (
            lambda radio: setattr(radio, "auto_initial_endpoint_offset", -1),
            "maximum-gain endpoint",
        ),
        (lambda radio: setattr(radio, "stream_change_at", 8), "stream or ownership"),
        (lambda radio: setattr(radio, "zero_epoch_at", 8), "stream or ownership"),
        (lambda radio: setattr(radio, "missing_feature_at", 8), "required features"),
        (lambda radio: setattr(radio, "missing_valid_flag_at", 8), "valid flags"),
        (lambda radio: setattr(radio, "unsafe_flag_at", 8), "unsafe"),
        (lambda radio: setattr(radio, "overflow_at", 8), "overflow"),
        (
            lambda radio: setattr(radio, "excess_observations_at", 8),
            "provider overlap bound",
        ),
        (
            lambda radio: setattr(radio, "bad_sample_format_at", 8),
            "wire/request provenance",
        ),
        (
            lambda radio: setattr(radio, "bad_threshold_provenance_at", 8),
            "wire/request provenance",
        ),
        (
            lambda radio: setattr(radio, "bad_initial_gain_at", 8),
            "differs from its request",
        ),
        (lambda radio: setattr(radio, "worker_error_at", 31), "worker failure"),
        (lambda radio: setattr(radio, "readback_offset_db", 0.5), "readback"),
    ),
)
def test_probe_rejects_runtime_evidence_mutations(
    tmp_path: Path,
    mutation: Any,
    expected: str,
) -> None:
    radio = _FakeProbeRadio(tmp_path)
    mutation(radio)
    with pytest.raises(BaseException, match=expected):
        _run_fake(radio, _quality(tmp_path))
    report = _failure_report(radio)
    assert report["verdict"] == "invalid"
    assert report["release_pass_eligible"] is False
    assert not any(thread.name == PROBE_THREAD_NAME for thread in threading.enumerate())


@pytest.mark.parametrize(
    ("frame_index", "visible_event", "expected", "expected_tx_writes"),
    (
        (10, True, "AUTO session contains a gain transition", 1),
        (32, True, "AUTO session contains a gain transition", 2),
        (10, False, "endpoint changed without a visible event", 1),
        (32, False, "endpoint changed without a visible event", 2),
    ),
)
def test_probe_rejects_nonstable_mid_and_command_phase_gain_state(
    tmp_path: Path,
    frame_index: int,
    visible_event: bool,
    expected: str,
    expected_tx_writes: int,
) -> None:
    radio = _FakeProbeRadio(tmp_path)
    if visible_event:
        radio.visible_event_at.add(frame_index)
    else:
        radio.nonmax_endpoint_without_event_at = frame_index

    with pytest.raises(BaseException, match=expected):
        _run_fake(radio, _quality(tmp_path))

    tx_writes = [
        operation for operation in radio.operations if operation[0] == "set_tx2_gain"
    ]
    assert len(tx_writes) == expected_tx_writes
    assert _failure_report(radio)["verdict"] == "invalid"


def test_probe_requires_all_32_frames_before_control_reassertion(
    tmp_path: Path,
) -> None:
    radio = _FakeProbeRadio(tmp_path)
    radio.worker_error_at = 31

    with pytest.raises(BaseException, match="worker failure"):
        _run_fake(radio, _quality(tmp_path))

    tx_writes = [
        operation for operation in radio.operations if operation[0] == "set_tx2_gain"
    ]
    assert tx_writes == [("set_tx2_gain", -45.0)]
    report = _failure_report(radio)
    assert report["verdict"] == "invalid"
    assert "command_contention" not in report


def test_probe_max_gain_start_keeps_first_frame_transition_gate_fatal(
    tmp_path: Path,
) -> None:
    radio = _FakeProbeRadio(tmp_path)
    radio.first_unrepresented_transitions = 2

    with pytest.raises(BaseException, match="unrepresented prior transitions"):
        _run_fake(radio, _quality(tmp_path))

    assert radio.auto_request_initial_gain_db == 62
    assert [
        operation for operation in radio.operations if operation[0] == "set_tx2_gain"
    ] == [("set_tx2_gain", -45.0)]
    failure = _failure_report(radio)
    assert failure["frames"] == []
    assert "unrepresented prior transitions" in failure["fatal_error"]
    assert "command_contention" not in failure


def test_probe_fails_closed_after_bounded_startup_eagain_retries(
    tmp_path: Path,
) -> None:
    radio = _FakeProbeRadio(tmp_path)
    radio.startup_eagain_remaining = 65

    with pytest.raises(BaseException, match="bounded startup EAGAIN"):
        _run_fake(radio, _quality(tmp_path))

    assert radio.startup_eagain_attempts == 65
    assert radio.capture_count == 0
    assert [
        operation for operation in radio.operations if operation[0] == "set_tx2_gain"
    ] == [("set_tx2_gain", -45.0)]
    assert _failure_report(radio)["verdict"] == "invalid"


@pytest.mark.parametrize(
    "field",
    (
        "bad_event_sequence_at",
        "bad_event_step_at",
        "bad_event_range_at",
        "bad_event_sample_at",
        "bad_event_flags_at",
    ),
)
def test_probe_rejects_corrupt_visible_events(tmp_path: Path, field: str) -> None:
    radio = _FakeProbeRadio(tmp_path)
    radio.visible_event_at.update({9, 10} if field == "bad_event_sequence_at" else {10})
    setattr(radio, field, 10)
    with pytest.raises((EvidenceInvalid, ValueError, BaseExceptionGroup)):
        _run_fake(radio, _quality(tmp_path))
    assert _failure_report(radio)["verdict"] == "invalid"


def test_probe_rejects_regressing_event_sample_order(tmp_path: Path) -> None:
    radio = _FakeProbeRadio(tmp_path)
    radio.regressed_event_samples_at = 10

    with pytest.raises(BaseException, match="sample ordered|samples regressed"):
        _run_fake(radio, _quality(tmp_path))

    assert _failure_report(radio)["verdict"] == "invalid"


@pytest.mark.parametrize(
    ("event_count", "spacing", "expected"),
    (
        (5, 1, "physics bound"),
        (2, 1, "cooldown spacing"),
    ),
)
def test_probe_rejects_physically_impossible_event_density(
    tmp_path: Path,
    event_count: int,
    spacing: int,
    expected: str,
) -> None:
    radio = _FakeProbeRadio(tmp_path)
    radio.dense_events_at = 10
    radio.dense_event_count = event_count
    radio.dense_event_spacing_samples = spacing

    with pytest.raises(BaseException, match=expected):
        _run_fake(radio, _quality(tmp_path))

    assert _failure_report(radio)["verdict"] == "invalid"


def test_report_validator_rejects_forged_event_cooldown_spacing(
    tmp_path: Path,
) -> None:
    radio = _FakeProbeRadio(tmp_path)
    report, _path = _run_fake(radio, _quality(tmp_path))
    forged = _forge_mid_session_event_excursion(report, spacing_samples=1)
    with pytest.raises(EvidenceInvalid, match="cooldown spacing"):
        validate_transient_transport_probe_report(forged, _quality(tmp_path))


def test_report_validator_rejects_self_consistent_visible_event_excursion(
    tmp_path: Path,
) -> None:
    radio = _FakeProbeRadio(tmp_path)
    report, _path = _run_fake(radio, _quality(tmp_path))
    forged = _forge_mid_session_event_excursion(report, spacing_samples=17_408)

    with pytest.raises(
        EvidenceInvalid, match="AUTO session contains a gain transition"
    ):
        validate_transient_transport_probe_report(forged, _quality(tmp_path))


def test_report_validator_rejects_self_consistent_nonmax_stable_suffix(
    tmp_path: Path,
) -> None:
    radio = _FakeProbeRadio(tmp_path)
    report, _path = _run_fake(radio, _quality(tmp_path))
    forged = copy.deepcopy(report)
    frames = forged["frames"]
    direction = TandemEventDirection.DECREASE
    reason = TandemEventReason.LARGE_ADC_OVERLOAD
    event_frame = frames[1]
    event_sample = event_frame["first_sample_sequence"] + 256
    event = {
        "sample_sequence": event_sample,
        "event_sequence": 0,
        "flags": (int(direction) << 4) | int(reason),
        "direction": int(direction),
        "direction_name": direction.name.lower(),
        "reason": int(reason),
        "reason_name": reason.name.lower(),
        "rx1_gain_index": 64,
        "rx2_gain_index": 64,
    }
    for index, frame in enumerate(frames[1:], start=1):
        metadata = frame["metadata"]
        metadata.update(
            tandem_transition_count=1,
            rx1_gain_index=64,
            rx2_gain_index=64,
            bench_gain_indices=[64, 64],
            event_count=1 if index == 1 else 0,
            gain_events=[event] if index == 1 else [],
        )
        frame["continuity"].update(
            transition_count_delta=1 if index == 1 else 0,
            visible_event_count=1 if index == 1 else 0,
        )
    for name in ("initial_stable_suffix", "final_stable_suffix"):
        forged[name].update(
            transition_count=1,
            bench_gain_indices=[64, 64],
        )

    with pytest.raises(EvidenceInvalid, match="maximum-gain endpoint"):
        validate_transient_transport_probe_report(forged, _quality(tmp_path))


def test_probe_rejects_tone_below_configured_level_gate(tmp_path: Path) -> None:
    radio = _FakeProbeRadio(tmp_path)
    radio.raw = _tone_raw(
        radio.options.samples_per_channel,
        rx0_amplitude=100.0,
        rx1_amplitude=95.0,
    )
    quality = _quality(tmp_path)
    quality = replace(
        quality,
        thresholds=replace(quality.thresholds, min_tone_dbfs=-20.0),
    )

    with pytest.raises(BaseException, match="tone_too_weak"):
        _run_fake(radio, quality)

    report = _failure_report(radio)
    assert report["verdict"] == "invalid"
    assert len(report["frames"]) == 40
    assert radio.operations.index(("buffer_cancel",)) < radio.operations.index(
        ("buffer_close",)
    )


def test_probe_groups_acquisition_mute_cancel_and_close_failures(
    tmp_path: Path,
) -> None:
    radio = _FakeProbeRadio(tmp_path)
    radio.worker_error_at = 5
    radio.buffer_mute_failures = 1
    radio.cancel_failures = 1
    radio.buffer_close_failures = 1

    with pytest.raises(BaseExceptionGroup) as caught:
        _run_fake(radio, _quality(tmp_path))

    rendered = repr(caught.value)
    assert "worker failure" in rendered
    assert "mute failure" in rendered
    assert "cancel failure" in rendered
    assert "buffer close failure" in rendered
    failure = _failure_report(radio)
    assert failure["verdict"] == "invalid"
    assert all(
        detail in failure["fatal_error"]
        for detail in (
            "worker failure",
            "mute failure",
            "cancel failure",
            "buffer close failure",
        )
    )


def test_probe_worker_error_after_final_frame_is_not_discarded(tmp_path: Path) -> None:
    radio = _FakeProbeRadio(tmp_path)
    radio.worker_error_at = 40
    with pytest.raises(BaseException, match="worker failure"):
        _run_fake(radio, _quality(tmp_path))
    assert _failure_report(radio)["verdict"] == "invalid"


def test_probe_radio_authorization_forbids_strong_write(tmp_path: Path) -> None:
    radio = _FakeProbeRadio(tmp_path)
    with pytest.raises(FixtureSafetyError, match="strong TX"):
        radio.set_tx2_gain(-30.0)


def test_serial_probe_persists_verified_cleanup(tmp_path: Path) -> None:
    radio = _FakeProbeRadio(tmp_path)
    report, _path = run_serial_transient_transport_probe(
        object(),
        radio.options,
        _quality(tmp_path),
        radio_factory=lambda _iio, _options: radio,
        clock_ns=_Clock(),
        metadata_parser=radio.parse_metadata,
    )
    assert report["cleanup"]["verified"] is True
    assert report["cleanup"]["selectors"] == [3, 3, 3, 3]
    assert radio.closed is True


def test_serial_close_failure_invalidates_durable_qualification(tmp_path: Path) -> None:
    radio = _FakeProbeRadio(tmp_path)
    radio.close_failures = 1
    with pytest.raises(FixtureSafetyError, match="radio close failed"):
        run_serial_transient_transport_probe(
            object(),
            radio.options,
            _quality(tmp_path),
            radio_factory=lambda _iio, _options: radio,
            clock_ns=_Clock(),
            metadata_parser=radio.parse_metadata,
        )
    report = _failure_report(radio)
    assert report["verdict"] == "invalid"
    assert report["release_pass_eligible"] is False
    assert report["cleanup"]["verified"] is False


def test_report_validator_rejects_planted_mutations(tmp_path: Path) -> None:
    radio = _FakeProbeRadio(tmp_path)
    report, _path = _run_fake(radio, _quality(tmp_path))
    mutations = []

    def mutated(apply: Any) -> dict[str, Any]:
        value = copy.deepcopy(report)
        apply(value)
        return value

    mutations.extend(
        (
            mutated(lambda value: value.update(release_pass_eligible=True)),
            mutated(lambda value: value["frames"].pop()),
            mutated(
                lambda value: value["frames"][12]["continuity"].update(buffer_delta=2)
            ),
            mutated(
                lambda value: value["frames"][12]["metadata"].update(
                    tandem_transition_count=1
                )
            ),
            mutated(
                lambda value: value["frames"][12]["metadata"].update(sample_format=0)
            ),
            mutated(
                lambda value: value["frames"][12]["metadata"].update(
                    threshold_provenance=0
                )
            ),
            mutated(
                lambda value: value["frames"][12]["metadata"].update(initial_gain_db=40)
            ),
            mutated(
                lambda value: value["frames"][0]["metadata"].update(
                    bench_gain_indices=[64, 64]
                )
            ),
            mutated(
                lambda value: value["metadata_request"]["decoded"].update(
                    initial_gain_db=40
                )
            ),
            mutated(
                lambda value: value["evidence_policy"].update(auto_initial_gain_db=40)
            ),
            mutated(lambda value: value["frames"][12].update(sample_gap_before=None)),
            mutated(
                lambda value: value["conditioning_anchor_candidate"].update(
                    byte_count=1
                )
            ),
            mutated(
                lambda value: value["command_contention"]["command"][
                    "sample_counter_bracket"
                ].update(raw_post_write_causal=-1)
            ),
            mutated(
                lambda value: value["command_contention"]["command"].update(
                    sample_anchor_policy="forged"
                )
            ),
            mutated(
                lambda value: value["safety"].update(strong_tx_write_permitted=True)
            ),
            mutated(lambda value: value["acquisition"].update(discarded_tail_frames=6)),
            mutated(
                lambda value: value["weak_signal_quality"]["conditioning_anchor"][
                    "analysis"
                ]["windows"][0]["tone_dbfs"].__setitem__(0, -90.0)
            ),
            mutated(
                lambda value: value["weak_signal_quality"]["final_stable_suffix"][0][
                    "analysis"
                ]["windows"][0]["clipping_fraction"].__setitem__(0, -1.0)
            ),
            mutated(
                lambda value: value["weak_signal_quality"]["final_stable_suffix"][
                    0
                ].update(source_frame_sha256="0" * 64)
            ),
        )
    )
    for forged in mutations:
        with pytest.raises(EvidenceInvalid):
            validate_transient_transport_probe_report(forged, _quality(tmp_path))


def test_report_validator_binds_stale_fifo_hold_normalization(tmp_path: Path) -> None:
    radio = _FakeProbeRadio(tmp_path)
    radio.fifo_level = 8
    report, _path = _run_fake(radio, _quality(tmp_path))

    mutations = []
    for mutation in (
        lambda value: value["stale_fifo_normalization"]["hold_session"].update(
            refill_count=1
        ),
        lambda value: value["stale_fifo_normalization"]["hold_session"][
            "metadata_request"
        ]["decoded"].update(mode=int(TandemMode.AUTO)),
        lambda value: value["stale_fifo_normalization"]["hold_session"][
            "metadata_request"
        ]["decoded"].update(initial_gain_db=62),
        lambda value: value["stale_fifo_normalization"]["hold_session"][
            "status_while_open"
        ].update(ownership_epoch=0),
        lambda value: value["stale_fifo_normalization"]["mute_evidence_before"].update(
            tx2_gain_db=-70.0
        ),
        lambda value: value["stale_fifo_normalization"]["rx_state_after"][
            "gains_db"
        ].__setitem__(0, 39.0),
        lambda value: (
            value["stale_fifo_normalization"]["status_before"].update(fifo_level=65),
            value["stale_fifo_normalization"].update(stale_fifo_events=65),
        ),
    ):
        forged = copy.deepcopy(report)
        mutation(forged)
        mutations.append(forged)

    for forged in mutations:
        with pytest.raises((EvidenceInvalid, FixtureSafetyError)):
            validate_transient_transport_probe_report(forged, _quality(tmp_path))


def test_cleanup_validator_rejects_unsafe_durable_readbacks(tmp_path: Path) -> None:
    radio = _FakeProbeRadio(tmp_path)
    report, _path = run_serial_transient_transport_probe(
        object(),
        radio.options,
        _quality(tmp_path),
        radio_factory=lambda _iio, _options: radio,
        clock_ns=_Clock(),
        metadata_parser=radio.parse_metadata,
    )
    forged = copy.deepcopy(report)
    forged["cleanup"]["selectors"][0] = 0
    with pytest.raises(FixtureSafetyError):
        validate_transient_transport_probe_report(
            forged, _quality(tmp_path), require_cleanup=True
        )


def test_report_write_failure_never_starts_rf(tmp_path: Path) -> None:
    radio = _FakeProbeRadio(tmp_path)

    def fail_write(_path: Path, _report: Any) -> None:
        raise OSError("planted report write failure")

    with pytest.raises(BaseException) as caught:
        run_transient_transport_probe(
            radio,
            _quality(tmp_path),
            clock_ns=_Clock(),
            metadata_parser=radio.parse_metadata,
            report_writer=fail_write,
        )
    assert "report write failure" in repr(caught.value)
    assert not any(operation[0] == "arm_tone" for operation in radio.operations)


def test_probe_setup_failure_mutes_and_cancels_before_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    radio = _FakeProbeRadio(tmp_path)

    class FailingPump:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("planted pump construction failure")

    monkeypatch.setattr(probe_module, "_TandemCapturePump", FailingPump)
    with pytest.raises(BaseException, match="pump construction failure"):
        _run_fake(radio, _quality(tmp_path))
    cancel_index = radio.operations.index(("buffer_cancel",))
    close_index = radio.operations.index(("buffer_close",))
    assert any(
        operation == ("mute", True) for operation in radio.operations[:cancel_index]
    )
    assert cancel_index < close_index


def test_probe_start_failure_mutes_and_cancels_before_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    radio = _FakeProbeRadio(tmp_path)
    base_pump = probe_module._TandemCapturePump

    class FailingStartPump(base_pump):
        def start(self) -> None:
            raise RuntimeError("planted pump start failure")

    monkeypatch.setattr(probe_module, "_TandemCapturePump", FailingStartPump)
    with pytest.raises(BaseException, match="pump start failure"):
        _run_fake(radio, _quality(tmp_path))

    assert [
        operation for operation in radio.operations if operation[0] == "set_tx2_gain"
    ] == [("set_tx2_gain", -45.0)]
    cancel_index = radio.operations.index(("buffer_cancel",))
    close_index = radio.operations.index(("buffer_close",))
    assert any(
        operation == ("mute", True) for operation in radio.operations[:cancel_index]
    )
    assert cancel_index < close_index


def test_probe_binds_command_prefix_to_live_pump_queue_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    radio = _FakeProbeRadio(tmp_path)
    base_pump = probe_module._TandemCapturePump

    class WrongQueueCapacityPump(base_pump):
        @property
        def queue_capacity_frames(self) -> int:
            return 3

    monkeypatch.setattr(probe_module, "_TandemCapturePump", WrongQueueCapacityPump)
    with pytest.raises(BaseException, match="command prefix differs"):
        _run_fake(radio, _quality(tmp_path))

    assert [
        operation for operation in radio.operations if operation[0] == "set_tx2_gain"
    ] == [("set_tx2_gain", -45.0)]
    cancel_index = radio.operations.index(("buffer_cancel",))
    close_index = radio.operations.index(("buffer_close",))
    assert any(
        operation == ("mute", True) for operation in radio.operations[:cancel_index]
    )
    assert cancel_index < close_index
    assert not any(thread.name == PROBE_THREAD_NAME for thread in threading.enumerate())


def test_probe_options_are_not_relaxable(tmp_path: Path) -> None:
    radio = _FakeProbeRadio(tmp_path)
    relaxed = TransientTransportProbeOptions(continuity_frames=31)
    with pytest.raises(ValueError, match="frozen"):
        run_transient_transport_probe(radio, _quality(tmp_path), probe=relaxed)
    unstable_start = TransientTransportProbeOptions(auto_initial_gain_db=40)
    with pytest.raises(ValueError, match="frozen"):
        run_transient_transport_probe(radio, _quality(tmp_path), probe=unstable_start)
    noninteger_start = TransientTransportProbeOptions(auto_initial_gain_db=62.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="exact integer"):
        run_transient_transport_probe(radio, _quality(tmp_path), probe=noninteger_start)
    assert radio.operations == []
