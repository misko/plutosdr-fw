"""Offline transport oracles for guarded transient hardware execution."""

from __future__ import annotations

import errno
import hashlib
import json
import re
import struct
import threading
import zlib
from builtins import BaseExceptionGroup
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from . import transient_hardware as transient_hardware_module
from .experiment import EvidenceInvalid, Issue46Radio
from .metadata_abi import (
    FEATURE_AD9361_TEMPERATURE,
    FEATURE_FPGA_GAIN_EVENTS,
    FEATURE_HARDWARE_SAMPLE_COUNTER,
    FEATURE_TANDEM_METADATA,
    FLAG_HARDWARE_SAMPLE_COUNTER_VALID,
    FLAG_SAMPLE_SEQUENCE_VALID,
    FLAG_TANDEM_METADATA_VALID,
    GAIN_EVENT_BYTES,
    GAIN_OBSERVATION_BYTES,
    METADATA_MAGIC,
    TANDEM_GAIN_EVENT,
    TANDEM_V5_EXTENSION,
    V5_PREFIX_BYTES,
    TandemEventDirection,
    TandemGainEvent,
    TandemGainTable,
    TandemState,
    parse_tandem_frame_metadata,
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


def _tone_raw(
    *,
    samples: int,
    amplitude: float,
    seed: int,
    alternating_amplitudes: tuple[float, float] | None = None,
) -> bytes:
    np = pytest.importorskip("numpy")
    indexes = np.arange(samples, dtype=np.float64)
    carrier = np.exp(2j * np.pi * 100_000.0 * indexes / 1_000_000)
    rng = np.random.default_rng(seed)
    signal = []
    amplitudes: Any = amplitude
    if alternating_amplitudes is not None:
        amplitudes = np.where(
            (indexes.astype(np.int64) // 1_024) % 2 == 0,
            alternating_amplitudes[0],
            alternating_amplitudes[1],
        )
    for channel, phase in enumerate((0.3, -0.2)):
        noise = rng.normal(size=samples) + 1j * rng.normal(size=samples)
        signal.append(
            amplitudes
            * (1.0 - 0.05 * channel)
            * carrier
            * np.exp(1j * phase)
            + noise
        )
    matrix = np.asarray(signal)
    words = np.empty((samples, 4), dtype="<i2")
    words[:, 0] = np.rint(matrix[0].real).astype("<i2")
    words[:, 1] = np.rint(matrix[0].imag).astype("<i2")
    words[:, 2] = np.rint(matrix[1].real).astype("<i2")
    words[:, 3] = np.rint(matrix[1].imag).astype("<i2")
    return words.tobytes()


def _metadata_wire(metadata: Any) -> bytes:
    header_bytes = V5_PREFIX_BYTES + 64 * (
        GAIN_OBSERVATION_BYTES + GAIN_EVENT_BYTES
    ) + 4
    payload = bytearray(header_bytes)
    struct.pack_into(
        "<IHHIIQQQIIIHB",
        payload,
        0,
        METADATA_MAGIC,
        5,
        header_bytes,
        metadata.features,
        metadata.flags,
        metadata.stream_id,
        metadata.buffer_sequence,
        metadata.first_sample_sequence,
        metadata.samples_per_channel,
        metadata.iq_payload_bytes,
        metadata.enabled_scan_mask,
        metadata.sample_format,
        metadata.channel_count,
    )
    struct.pack_into(
        "<HHHHHHII",
        payload,
        96,
        metadata.observation_count,
        metadata.observation_capacity,
        GAIN_OBSERVATION_BYTES,
        metadata.event_count,
        metadata.event_capacity,
        GAIN_EVENT_BYTES,
        metadata.observation_overflow_count,
        metadata.event_overflow_count,
    )
    TANDEM_V5_EXTENSION.pack_into(
        payload,
        124,
        metadata.ownership_epoch,
        int(metadata.tandem_state),
        metadata.tandem_fault_flags,
        metadata.tandem_transition_count,
        int(metadata.gain_table_id),
        metadata.threshold_provenance,
        metadata.minimum_gain_db,
        metadata.maximum_gain_db,
        metadata.initial_gain_db,
        metadata.minimum_gain_index,
        metadata.maximum_gain_index,
        metadata.rx1_gain_index,
        metadata.rx2_gain_index,
        (
            -(1 << 31)
            if metadata.ad9361_temperature_mdeg_c is None
            else metadata.ad9361_temperature_mdeg_c
        ),
        0,
        0,
        0,
    )
    event_offset = V5_PREFIX_BYTES + 64 * GAIN_OBSERVATION_BYTES
    for index, event in enumerate(metadata.gain_events):
        TANDEM_GAIN_EVENT.pack_into(
            payload,
            event_offset + index * GAIN_EVENT_BYTES,
            event.sample_sequence,
            event.event_sequence,
            event.flags,
            event.rx1_gain_index,
            event.rx2_gain_index,
        )
    struct.pack_into("<I", payload, len(payload) - 4, 0)
    struct.pack_into(
        "<I", payload, len(payload) - 4, zlib.crc32(payload) & 0xFFFFFFFF
    )
    return bytes(payload)


class _FakeRadio:
    def __init__(self, output_dir: Path) -> None:
        self.options = SimpleNamespace(
            serial="FAKE-TRANSIENT",
            sample_rate_hz=1_000_000,
            samples_per_channel=65_536,
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
        self.metadata_session_closed = False
        self.buffer_open = False
        self.metadata_by_token: dict[bytes, Any] = {}
        self.metadata_capture_count = 0
        self.metadata_sample = 100_000
        self.metadata_buffer_sequence = 40
        self.metadata_transition_count = 0
        self.metadata_event_sequence = 70
        self.metadata_gain_index = 65
        self.metadata_previous_level = -60.0
        self.sample_counter_low32 = self.metadata_sample
        self.sample_counter_step = 128
        self.last_counter_read = self.sample_counter_low32
        self.post_write_counter_reads_remaining = 0
        self.exact_command_writes: list[tuple[float, int]] = []
        self.tx1_attestation_count = 0
        self.release_post_attested = threading.Event()
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
        self.metadata_flags_override: int | None = None
        self.metadata_features_override: int | None = None
        self.metadata_observation_count_override: int | None = None
        self.metadata_threshold_provenance_override: int | None = None
        self.metadata_temperature_overrides: dict[int, int | None] = {}
        self.metadata_amplitude_overrides: dict[int, float] = {}
        self.metadata_alternating_amplitude_capture_indices: set[int] = set()
        self.plant_too_close_event_pair = False
        self.planted_suffix_event_capture_index: int | None = None
        self.preclose_transition_delta = 0
        self.preclose_endpoint_delta = 0
        self.post_close_transition_delta = 0
        self.post_close_endpoint_delta = 0
        self.deferred_readback_override: float | None = None
        self.fail_first_metadata_capture = False
        self.fail_completed_tandem_wrapper_mute = False
        self.completed_tandem_manual_configured = False
        self.fail_next_capture_with_mute_error = False
        self.mute_failures_remaining = 0
        self.cancel_failures_remaining = 0
        self.buffer_cancelled = threading.Event()
        self.block_metadata_refill = False
        self.block_metadata_refill_at_count: int | None = None
        self.blocked_refill_waiting = threading.Event()
        self.buffer_cancel_calls = 0
        self.mute_while_buffer_open_count = 0
        self.cleanup_verified = False
        self.closed = False

    def mute_all(self) -> None:
        if self.buffer_open:
            self.mute_while_buffer_open_count += 1
        self.tx_gain_db = -89.75
        self.operations.append(("mute_all",))
        if (
            self.fail_completed_tandem_wrapper_mute
            and self.completed_tandem_manual_configured
        ):
            self.fail_completed_tandem_wrapper_mute = False
            raise RuntimeError("planted tandem wrapper mute failure")
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

    def write_tx2_gain_exact(self, gain_db: float) -> None:
        self.tx_gain_db = float(gain_db)
        self.exact_command_writes.append((self.tx_gain_db, self.last_counter_read))
        self.sample_counter_low32 = self.last_counter_read + 4_096
        self.post_write_counter_reads_remaining = 3
        if self.tx_gain_db > -45.0:
            self.attack_command_applied.set()
        self.operations.append(("write_tx2_gain_exact", self.tx_gain_db))

    def read_tx2_gain(self) -> float:
        self.operations.append(("read_tx2_gain",))
        return (
            self.tx_gain_db
            if self.deferred_readback_override is None
            else self.deferred_readback_override
        )

    def attest_tx1_muted(self) -> float:
        self.tx1_attestation_count += 1
        self.operations.append(("attest_tx1_muted", self.tx1_attestation_count))
        if self.tx1_attestation_count >= 4:
            self.release_post_attested.set()
        return -89.75

    def configure_rx(self, mode: str, *, manual_gain_db: float | None = None) -> None:
        self.mode = mode
        if mode == "manual":
            assert manual_gain_db is not None
            self.rx_gain_db = float(manual_gain_db)
        else:
            self.rx_gain_db = 20.0 if self.tx_gain_db > -45.0 else 40.0
        if mode == "manual" and self.metadata_session_closed:
            self.completed_tandem_manual_configured = True
        self.operations.append(("configure_rx", mode, manual_gain_db))

    def read_rx_state(self) -> dict[str, list[Any]]:
        return {
            "modes": [self.mode, self.mode],
            "gains_db": [self.rx_gain_db, self.rx_gain_db],
        }

    def read_center_frequency(self) -> dict[str, int]:
        return {"rx_lo_hz": 915_000_000, "tx_lo_hz": 915_000_000}

    def tandem_status(self) -> dict[str, int]:
        transition_count = self.metadata_transition_count
        gain_index = self.metadata_gain_index
        if self.metadata_open and self.metadata_capture_count >= 64:
            transition_count = (
                transition_count + self.preclose_transition_delta
            ) % (1 << 32)
            gain_index += self.preclose_endpoint_delta
        elif self.metadata_session_closed:
            transition_count = (
                transition_count
                + self.preclose_transition_delta
                + self.post_close_transition_delta
            ) % (1 << 32)
            gain_index += self.preclose_endpoint_delta + self.post_close_endpoint_delta
        return {
            "state": int(TandemState.ARMED_AUTO) if self.metadata_open else 0,
            "fault_flags": 0,
            "overflow_count": 0,
            "fifo_level": 0,
            "ownership_epoch": 5 if self.metadata_open else 0,
            "transition_count": transition_count,
            "rx1_gain_index": gain_index,
            "rx2_gain_index": gain_index,
        }

    def buffer(
        self,
        api: str,
        kernel_buffers: int,
        samples_per_channel: int,
        *,
        tandem_request: bytes | None,
        batch_frames: int = 1,
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
                    batch_frames,
                )
            )
            self.metadata_open = api == "metadata"
            if self.metadata_open:
                self.metadata_session_closed = False
                self.completed_tandem_manual_configured = False
            self.buffer_open = True
            self.buffer_cancelled.clear()
            if self.metadata_open:
                self.metadata_previous_level = self.tx_gain_db
                self.metadata_capture_count = 0
                self.metadata_buffer_sequence = 0
                self.metadata_transition_count = 0
                self.metadata_gain_index = 65
            try:
                yield (
                    SimpleNamespace(
                        cancel=self.cancel_buffer,
                        batch_frames=batch_frames,
                        batch_cache_bytes=(
                            batch_frames
                            * (samples_per_channel * 8 + 64 * 1_024 + 16)
                        ),
                    ),
                    (2 if self.metadata_open else None),
                )
            finally:
                if self.metadata_open:
                    self.metadata_session_closed = True
                self.metadata_open = False
                self.buffer_open = False
                self.operations.append(("buffer_exit", api))

        return opened()

    def cancel_buffer(self) -> None:
        self.buffer_cancel_calls += 1
        self.operations.append(("buffer_cancel",))
        self.buffer_cancelled.set()
        if self.cancel_failures_remaining:
            self.cancel_failures_remaining -= 1
            raise RuntimeError("planted buffer cancel failure")

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
        command = next(
            (
                (level, sample)
                for level, sample in self.exact_command_writes
                if first_sample <= sample + 16_384 < first_sample + samples
            ),
            None,
        )
        if command is not None:
            level, command_sample = command
            louder = level > -45.0
            quieter = not louder
            if quieter and self.omit_release_event:
                command = None
        if command is not None:
            direction = (
                TandemEventDirection.DECREASE
                if louder
                else TandemEventDirection.INCREASE
            )
            self.metadata_gain_index += -1 if louder else 1
            self.metadata_transition_count += 1
            event = TandemGainEvent(
                sample_sequence=command_sample + 16_384,
                event_sequence=self.metadata_event_sequence,
                flags=int(direction) << 4,
                rx1_gain_index=self.metadata_gain_index,
                rx2_gain_index=self.metadata_gain_index,
            )
            self.metadata_event_sequence += 1
            events = (event,)
            if self.plant_too_close_event_pair and louder:
                self.metadata_gain_index -= 1
                self.metadata_transition_count += 1
                second = TandemGainEvent(
                    sample_sequence=event.sample_sequence + 1,
                    event_sequence=self.metadata_event_sequence,
                    flags=int(direction) << 4,
                    rx1_gain_index=self.metadata_gain_index,
                    rx2_gain_index=self.metadata_gain_index,
                )
                self.metadata_event_sequence += 1
                events = (event, second)

        if self.planted_suffix_event_capture_index == self.metadata_capture_count:
            self.metadata_gain_index -= 1
            self.metadata_transition_count += 1
            event = TandemGainEvent(
                sample_sequence=first_sample + samples // 2,
                event_sequence=self.metadata_event_sequence,
                flags=int(TandemEventDirection.DECREASE) << 4,
                rx1_gain_index=self.metadata_gain_index,
                rx2_gain_index=self.metadata_gain_index,
            )
            self.metadata_event_sequence += 1
            events = (*events, event)

        metadata = SimpleNamespace(
            version=5,
            header_bytes=3_256,
            features=(
                (
                    FEATURE_FPGA_GAIN_EVENTS
                    | FEATURE_HARDWARE_SAMPLE_COUNTER
                    | FEATURE_TANDEM_METADATA
                    | FEATURE_AD9361_TEMPERATURE
                    | 0x77
                )
                if self.metadata_features_override is None
                else self.metadata_features_override
            ),
            samples_per_channel=samples,
            iq_payload_bytes=samples * 8,
            enabled_scan_mask=0x0F,
            channel_count=2,
            flags=(
                (
                    FLAG_SAMPLE_SEQUENCE_VALID
                    | FLAG_HARDWARE_SAMPLE_COUNTER_VALID
                    | FLAG_TANDEM_METADATA_VALID
                )
                if self.metadata_flags_override is None
                else self.metadata_flags_override
            ),
            sample_format=1,
            observation_count=(
                4
                if self.metadata_observation_count_override is None
                else self.metadata_observation_count_override
            ),
            observation_capacity=64,
            observation_overflow_count=0,
            event_capacity=64,
            event_overflow_count=0,
            tandem_state=TandemState.ARMED_AUTO,
            tandem_fault_flags=0,
            gain_table_id=TandemGainTable.MHZ_200_1300,
            minimum_gain_db=0,
            maximum_gain_db=62,
            initial_gain_db=62,
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
            threshold_provenance=(
                572_733_972
                if self.metadata_threshold_provenance_override is None
                else self.metadata_threshold_provenance_override
            ),
            ad9361_temperature_mdeg_c=self.metadata_temperature_overrides.get(
                self.metadata_capture_count, 35_000
            ),
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
        if metadata and (
            self.block_metadata_refill
            or self.block_metadata_refill_at_count == self.metadata_capture_count
        ):
            self.blocked_refill_waiting.set()
            if not self.buffer_cancelled.wait(timeout=2.0):
                raise EvidenceInvalid("planted refill was not cancelled")
            raise OSError(errno.EBADF, "planted cancelled refill")
        if metadata and self.fail_first_metadata_capture:
            self.fail_first_metadata_capture = False
            raise EvidenceInvalid("planted first metadata refill failure")
        if metadata and self.metadata_capture_count == 0:
            self.blocked_refill_waiting.set()
            if not self.release_post_attested.wait(timeout=2.0):
                if self.buffer_cancelled.is_set():
                    raise OSError(errno.EBADF, "planted cancelled refill")
                raise EvidenceInvalid("planted release bracket never completed")
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
        amplitude = (
            self.metadata_amplitude_overrides.get(self.metadata_capture_count, 400.0)
            if metadata
            else (400.0 if adaptive else (600.0 if self.tx_gain_db > -45.0 else 160.0))
        )
        raw = _tone_raw(
            samples=samples_per_channel,
            amplitude=amplitude,
            seed=(1 if metadata else len(self.operations)),
            alternating_amplitudes=(300.0, 500.0)
            if metadata
            and self.metadata_capture_count
            in self.metadata_alternating_amplitude_capture_indices
            else None,
        )
        if not metadata:
            return raw, None, 1_000 + len(self.operations)
        parsed = self._metadata(samples=samples_per_channel)
        wire = _metadata_wire(parsed)
        self.metadata_by_token[wire] = parsed
        return raw, wire, 1_000_000_000 + self.metadata_capture_count

    def read_rx_sample_counter_low32(self) -> int:
        if self.scripted_counter_reads:
            value = self.scripted_counter_reads.pop(0)
            self.counter_reads.append((threading.current_thread().name, value))
            return value
        if self.freeze_sample_counter:
            value = self.sample_counter_low32 % (1 << 32)
            self.counter_reads.append((threading.current_thread().name, value))
            return value
        current = self.sample_counter_low32
        value = current % (1 << 32)
        self.counter_reads.append((threading.current_thread().name, value))
        self.last_counter_read = value
        if self.post_write_counter_reads_remaining:
            self.sample_counter_low32 = current + 4_096
            self.post_write_counter_reads_remaining -= 1
        else:
            self.sample_counter_low32 = current + 65_536
        return value

    def parse_metadata(self, token: bytes) -> Any:
        return parse_tandem_frame_metadata(token)

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
        samples_per_channel=65_536,
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
        "weak_stimulus_tx_gain_db": -60.0,
        "strong_stimulus_tx_gain_db": -30.0,
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
    report_writer: Any | None = None,
) -> tuple[dict[str, Any], Path]:
    selected_clocks = clocks or _Clocks()
    kwargs: dict[str, Any] = {}
    if report_writer is not None:
        kwargs["report_writer"] = report_writer
    return run_transient_hardware(
        radio,
        quality,
        capture=capture or _capture_options(),
        clock_ns=selected_clocks.clock_ns,
        monotonic=selected_clocks.monotonic,
        wall_clock_ns=selected_clocks.wall_clock_ns,
        sleep=lambda _seconds: None,
        metadata_parser=radio.parse_metadata,
        **kwargs,
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
    assert (
        report["configuration"]["transient_capture"]["weak_stimulus_tx_gain_db"]
        == -60.0
    )
    assert report["evidence_policy"]["stimulus"] == {
        "weak_tx_gain_db": -60.0,
        "strong_tx_gain_db": -30.0,
        "step_db": 30.0,
        "quality_policy": (
            "explicit trajectory rungs require prior same-band steady "
            "qualification; retain the 10 dB returned-IQ tone-SNR gate"
        ),
    }
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
    assert persisted["schema"] == "plutosdr-fw.tandem-agc-transient.v2"

    buffer_entries = [item for item in radio.operations if item[0] == "buffer_enter"]
    assert [item[1] for item in buffer_entries] == [
        "ordinary",
        "ordinary",
        "ordinary",
        "metadata",
    ]
    assert all(item[2:4] == (1, 1_024) for item in buffer_entries[:-1])
    assert buffer_entries[-1][2:4] == (8, 65_536)
    assert buffer_entries[-1][4]
    assert all(not item[4] for item in buffer_entries[:-1])
    assert [item[5] for item in buffer_entries] == [1, 1, 1, 64]


def test_tandem_batch_schedule_partition_and_exact_command_contract(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    report, _path = _run_fake(radio, _quality(tmp_path))
    tandem = next(mode for mode in report["modes"] if mode["mode"] == "tandem_auto")
    acquisition = tandem["acquisition"]

    assert report["configuration"]["tandem_transport"] == {
        "provider_frame_samples": 65_536,
        "kernel_buffers": 8,
        "batch_frames": 64,
        "queue_capacity_frames": 4,
        "metadata_abi": 2,
    }
    assert acquisition["post_open_s0_raw"] == 100_000
    assert acquisition["targets"] == {
        "strong_attack": {
            "offset_frames": 16,
            "offset_samples": 16 * 65_536,
            "target_raw": 100_000 + 16 * 65_536,
        },
        "weak_release": {
            "offset_frames": 40,
            "offset_samples": 40 * 65_536,
            "target_raw": 100_000 + 40 * 65_536,
        },
    }
    plan = acquisition["schedule_plan"]
    assert acquisition["schedule_frozen_before_worker_start"] is True
    assert [
        plan["s0_read_host_after_ns"],
        plan["targets_frozen_host_ns"],
        plan["worker_start_requested_ns"],
        plan["worker_start_returned_ns"],
    ] == sorted(
        [
            plan["s0_read_host_after_ns"],
            plan["targets_frozen_host_ns"],
            plan["worker_start_requested_ns"],
            plan["worker_start_returned_ns"],
        ]
    )
    assert [(item["command_id"], item["requested_level_db"]) for item in plan["commands"]] == [
        ("strong_attack", -30.0),
        ("weak_release", -60.0),
    ]

    assert len(tandem["batch_frames"]) == 64
    assert [frame["frame_index"] for frame in tandem["batch_frames"]] == list(
        range(64)
    )
    assert [
        frame["metadata"]["buffer_sequence"] for frame in tandem["batch_frames"]
    ] == list(range(64))
    assert all(
        frame["metadata"]["features"] == 1_023
        and frame["metadata"]["initial_gain_db"] == 62
        and frame["metadata"]["iq_payload_bytes"] == 524_288
        and frame["metadata"]["enabled_scan_mask"] == 0x0F
        for frame in tandem["batch_frames"]
    )
    groups = tandem["partition"]["groups"]
    assert [groups[name]["count"] for name in tandem["partition"]["phase_order"]] == [
        16,
        1,
        23,
        1,
        23,
    ]
    assert all(
        groups[name]["count"] >= 8
        for name in (
            "fully_pre_attack",
            "fully_post_attack_pre_release",
            "fully_post_release",
        )
    )

    for command_id in ("strong_attack", "weak_release"):
        diagnostics = acquisition["schedule_diagnostics"][command_id]
        assert diagnostics["qualified"] is True
        assert diagnostics["write_ack"] == {
            **diagnostics["write_ack"],
            "operation": "one_exact_tx2_hardwaregain_write",
            "attempt_count": 1,
            "acknowledged": True,
            "error": None,
        }
        assert diagnostics["deferred_tx2_readback"] == {
            **diagnostics["deferred_tx2_readback"],
            "operation": "one_exact_tx2_hardwaregain_read",
            "attempt_count": 1,
            "passed": True,
            "error": None,
        }
        assert diagnostics["tx1_mute_assurance"]["pre"]["passed"] is True
        assert diagnostics["tx1_mute_assurance"]["post"]["passed"] is True
        assert diagnostics["raw_bracket"]["post_write_read_count"] == 3
        assert diagnostics["raw_bracket"]["causal_uncertainty_samples"] <= 16_384
        assert diagnostics["target"]["overshoot_samples"] <= 16_384
        assert all(
            item["first_refill_in_flight"] is True
            for item in diagnostics["worker_in_flight_observations"]
        )
    assert [item[0] for item in radio.operations].count("write_tx2_gain_exact") == 2
    assert [item[0] for item in radio.operations].count("read_tx2_gain") == 2
    assert [item[0] for item in radio.operations].count("attest_tx1_muted") == 4


def test_tandem_mandatory_sidecar_inventory_is_exact_and_reparseable(
    tmp_path: Path,
) -> None:
    report, _path = _run_fake(_FakeRadio(tmp_path), _quality(tmp_path))
    tandem = next(mode for mode in report["modes"] if mode["mode"] == "tandem_auto")
    manifest = tandem["acquisition"]["artifact_manifest"]

    assert manifest["path_root"] == "quality.output_dir"
    assert manifest["relative_directory"] == (
        "FAKE-TRANSIENT/transient-iq/tandem_auto/batch"
    )
    assert manifest["frame_count"] == 64
    assert manifest["file_count"] == 128
    assert manifest["iq_total_bytes"] == 64 * 524_288
    assert manifest["raw_metadata_total_bytes"] == 64 * 3_256
    assert manifest["completed_iq_files"] == 64
    assert manifest["completed_raw_metadata_files"] == 64
    assert manifest["write_complete"] is True
    assert len(manifest["entries"]) == 64

    observed_paths: set[str] = set()
    for index, frame in enumerate(tandem["batch_frames"]):
        iq_relative = frame["iq_path"]
        metadata_relative = frame["raw_metadata_path"]
        assert iq_relative == (
            f"FAKE-TRANSIENT/transient-iq/tandem_auto/batch/frame-{index:04d}.cs16"
        )
        assert metadata_relative == (
            "FAKE-TRANSIENT/transient-iq/tandem_auto/batch/"
            f"frame-{index:04d}.metadata.bin"
        )
        assert not Path(iq_relative).is_absolute()
        assert not Path(metadata_relative).is_absolute()
        assert observed_paths.isdisjoint({iq_relative, metadata_relative})
        observed_paths.update((iq_relative, metadata_relative))
        iq = (tmp_path / iq_relative).read_bytes()
        raw_metadata = (tmp_path / metadata_relative).read_bytes()
        assert len(iq) == 524_288
        assert hashlib.sha256(iq).hexdigest() == frame["sha256"]
        assert len(raw_metadata) == 3_256
        assert hashlib.sha256(raw_metadata).hexdigest() == (
            frame["raw_metadata_sha256"]
        )
        parsed = parse_tandem_frame_metadata(raw_metadata)
        assert parsed.buffer_sequence == index
        assert parsed.first_sample_sequence == frame["first_sample_sequence"]
        assert parsed.iq_payload_bytes == len(iq)
    assert len(observed_paths) == 128


def test_tandem_partial_sidecar_failure_retains_predeclared_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_write = transient_hardware_module._atomic_bytes
    failed = False

    def fail_first_metadata_sidecar(path: Path, value: bytes) -> None:
        nonlocal failed
        if path.name.endswith(".metadata.bin") and not failed:
            failed = True
            path.with_suffix(path.suffix + ".tmp").write_bytes(b"partial")
            raise OSError(errno.ENOSPC, "planted metadata sidecar failure")
        real_write(path, value)

    monkeypatch.setattr(
        transient_hardware_module, "_atomic_bytes", fail_first_metadata_sidecar
    )
    radio = _FakeRadio(tmp_path)
    with pytest.raises(OSError, match="planted metadata sidecar failure"):
        _run_fake(radio, _quality(tmp_path))

    persisted = json.loads(
        (
            tmp_path / radio.options.serial / "tandem-agc-transient-report.json"
        ).read_text(encoding="utf-8")
    )
    failure = persisted["failure_evidence"]
    manifest = failure["acquisition"]["artifact_manifest"]
    assert len(failure["batch_frames"]) == 64
    assert manifest["frame_count"] == 64
    assert manifest["file_count"] == 128
    assert manifest["completed_iq_files"] == 1
    assert manifest["completed_raw_metadata_files"] == 0
    assert manifest["write_complete"] is False
    assert failure["batch_frames"][0]["artifact_write_status"] == {
        "iq_write_completed": True,
        "raw_metadata_write_completed": False,
    }
    assert (
        tmp_path / failure["batch_frames"][0]["iq_path"]
    ).is_file()
    assert not (
        tmp_path / failure["batch_frames"][0]["raw_metadata_path"]
    ).exists()
    assert (
        tmp_path
        / (failure["batch_frames"][0]["raw_metadata_path"] + ".tmp")
    ).read_bytes() == b"partial"


def test_tandem_sidecar_symlink_is_rejected_before_any_sidecar_write(
    tmp_path: Path,
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    serial_iq = tmp_path / "FAKE-TRANSIENT" / "transient-iq"
    serial_iq.mkdir(parents=True)
    (serial_iq / "tandem_auto").symlink_to(external, target_is_directory=True)
    radio = _FakeRadio(tmp_path)

    with pytest.raises(EvidenceInvalid, match="contains a symlink"):
        _run_fake(radio, _quality(tmp_path))

    assert list(external.iterdir()) == []
    assert radio.operations == []
    assert not (
        tmp_path / radio.options.serial / "tandem-agc-transient-report.json"
    ).exists()


def test_transient_serial_symlink_preflight_precedes_radio_factory(
    tmp_path: Path,
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    (tmp_path / "FAKE-TRANSIENT").symlink_to(external, target_is_directory=True)
    opened = False

    def factory(_iio: Any, _options: Any) -> _FakeRadio:
        nonlocal opened
        opened = True
        return _FakeRadio(tmp_path)

    with pytest.raises(EvidenceInvalid, match="contains a symlink"):
        run_serial_transient_hardware(
            object(),
            SimpleNamespace(serial="FAKE-TRANSIENT"),
            _quality(tmp_path),
            capture=_capture_options(),
            radio_factory=factory,
        )

    assert opened is False
    assert list(external.iterdir()) == []


def test_transient_report_temporary_symlink_preflight_precedes_radio_io(
    tmp_path: Path,
) -> None:
    serial_directory = tmp_path / "FAKE-TRANSIENT"
    serial_directory.mkdir()
    external = tmp_path / "external-report"
    external.write_text("untouched", encoding="utf-8")
    report_temporary = serial_directory / "tandem-agc-transient-report.json.tmp"
    report_temporary.symlink_to(external)
    radio = _FakeRadio(tmp_path)

    with pytest.raises(EvidenceInvalid, match="temporary path is a symlink"):
        _run_fake(radio, _quality(tmp_path))

    assert radio.operations == []
    assert external.read_text(encoding="utf-8") == "untouched"


def test_tandem_unplanned_sidecar_preflight_precedes_radio_io(
    tmp_path: Path,
) -> None:
    batch_directory = (
        tmp_path / "FAKE-TRANSIENT" / "transient-iq" / "tandem_auto" / "batch"
    )
    batch_directory.mkdir(parents=True)
    (batch_directory / "stale-frame.tmp").write_bytes(b"stale")
    radio = _FakeRadio(tmp_path)

    with pytest.raises(EvidenceInvalid, match="unplanned artifact"):
        _run_fake(radio, _quality(tmp_path))

    assert radio.operations == []
    assert (batch_directory / "stale-frame.tmp").read_bytes() == b"stale"


def test_tandem_deleted_sidecar_demotes_durable_pass_to_invalid(
    tmp_path: Path,
) -> None:
    deleted = False

    def delete_after_pass_write(path: Path, value: dict[str, Any]) -> None:
        nonlocal deleted
        transient_hardware_module._atomic_json(path, value)
        if value.get("verdict") == "pass" and not deleted:
            deleted = True
            (
                tmp_path
                / "FAKE-TRANSIENT"
                / "transient-iq"
                / "tandem_auto"
                / "batch"
                / "frame-0000.cs16"
            ).unlink()

    radio = _FakeRadio(tmp_path)
    with pytest.raises(EvidenceInvalid, match="exact 128-file inventory"):
        _run_fake(
            radio,
            _quality(tmp_path),
            report_writer=delete_after_pass_write,
        )

    persisted = json.loads(
        (
            tmp_path / radio.options.serial / "tandem-agc-transient-report.json"
        ).read_text(encoding="utf-8")
    )
    assert deleted is True
    assert persisted["verdict"] == "invalid"
    assert "exact 128-file inventory" in persisted["fatal_error"]


@pytest.mark.parametrize(
    ("attribute", "value", "message"),
    (
        ("metadata_flags_override", 0, "does not mark the FPGA counter valid"),
        (
            "metadata_flags_override",
            (1 << 31)
            | FLAG_SAMPLE_SEQUENCE_VALID
            | FLAG_HARDWARE_SAMPLE_COUNTER_VALID
            | FLAG_TANDEM_METADATA_VALID,
            "unrecognized flags",
        ),
        (
            "metadata_features_override",
            1_023 & ~FEATURE_TANDEM_METADATA,
            "lacks required tandem-v5 features",
        ),
        (
            "metadata_features_override",
            (1 << 31) | 1_023,
            "wire provenance changed",
        ),
        (
            "metadata_observation_count_override",
            0,
            "observation count exceeds the overlap-safe bound",
        ),
        (
            "metadata_threshold_provenance_override",
            0,
            "threshold provenance differs from its request",
        ),
    ),
)
def test_tandem_metadata_flags_features_and_physics_are_live_gates(
    tmp_path: Path, attribute: str, value: int, message: str
) -> None:
    radio = _FakeRadio(tmp_path)
    setattr(radio, attribute, value)

    with pytest.raises(Exception, match=message):
        _run_fake(radio, _quality(tmp_path))

    persisted = json.loads(
        (
            tmp_path / radio.options.serial / "tandem-agc-transient-report.json"
        ).read_text(encoding="utf-8")
    )
    physics = persisted["failure_evidence"]["acquisition"][
        "metadata_physics_policy"
    ]
    assert physics == {
        "protocol_version": 5,
        "header_bytes": 3_256,
        "required_features": 904,
        "required_flags": (
            FLAG_SAMPLE_SEQUENCE_VALID
            | FLAG_HARDWARE_SAMPLE_COUNTER_VALID
            | FLAG_TANDEM_METADATA_VALID
        ),
        "sample_format": 1,
        "observation_capacity": 64,
        "event_capacity": 64,
        "maximum_observations_per_frame": 5,
        "maximum_events_per_frame": 4,
        "minimum_event_spacing_samples": 17_408,
    }


def test_tandem_temperature_allows_only_a_leading_startup_omission(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.metadata_temperature_overrides = {0: None, 1: None}

    report, _path = _run_fake(radio, _quality(tmp_path))

    tandem = next(mode for mode in report["modes"] if mode["mode"] == "tandem_auto")
    temperatures = [
        frame["metadata"]["temperature_mdeg_c"]
        for frame in tandem["batch_frames"]
    ]
    assert temperatures[:3] == [None, None, 35_000]
    assert temperatures.count(None) == 2


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({2: None}, "became unavailable after its first valid sample"),
        (
            {index: None for index in range(64)},
            "lacks one complete valid temperature session",
        ),
        ({0: 125_001}, "outside provider provenance"),
        ({0: -40_001}, "outside provider provenance"),
    ),
)
def test_tandem_temperature_rejects_late_missing_all_missing_and_out_of_range(
    tmp_path: Path,
    overrides: dict[int, int | None],
    message: str,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.metadata_temperature_overrides = overrides

    with pytest.raises(EvidenceInvalid, match=message):
        _run_fake(radio, _quality(tmp_path))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("flags", 0, "lacks required valid flags"),
        ("features", 1_023 & ~FEATURE_TANDEM_METADATA, "wire provenance changed"),
    ),
)
def test_tandem_runtime_required_mask_gate_rejects_parser_substitution(
    tmp_path: Path, field: str, value: int, message: str
) -> None:
    radio = _FakeRadio(tmp_path)
    metadata = radio._metadata(samples=65_536)
    setattr(metadata, field, value)
    capture = replace(_capture_options(), frame_samples=65_536, window_samples=1_024)

    with pytest.raises(EvidenceInvalid, match=message):
        transient_hardware_module._validate_tandem_metadata(
            metadata,
            raw_bytes=524_288,
            quality=_quality(tmp_path),
            capture=capture,
            state=transient_hardware_module._CaptureState(),
            gap_context="continuous_acquisition_unclassified",
            expected_initial_gain_db=62,
        )


def test_tandem_metadata_rejects_gain_events_inside_cooldown_spacing(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.plant_too_close_event_pair = True

    with pytest.raises(EvidenceInvalid, match="violate cooldown spacing"):
        _run_fake(radio, _quality(tmp_path))


@pytest.mark.parametrize("plant", ("rf", "within_frame_rf", "event"))
def test_tandem_stable_suffix_requires_rf_and_event_stability(
    tmp_path: Path, plant: str
) -> None:
    radio = _FakeRadio(tmp_path)
    if plant == "rf":
        radio.metadata_amplitude_overrides[63] = 800.0
        expected = "stable suffix exceeds its RF tolerance"
    elif plant == "within_frame_rf":
        radio.metadata_alternating_amplitude_capture_indices.add(63)
        expected = "stable suffix exceeds its RF tolerance"
    else:
        radio.planted_suffix_event_capture_index = 56
        expected = "eight-frame suffix is not event/endpoint stable"

    with pytest.raises(EvidenceInvalid, match=expected):
        _run_fake(radio, _quality(tmp_path))


@pytest.mark.parametrize(
    ("phase", "endpoint"),
    (
        ("fully_post_attack_pre_release", 65),
        ("fully_post_release", 64),
    ),
)
def test_tandem_stable_suffix_requires_commanded_endpoint_directions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    endpoint: int,
) -> None:
    original = transient_hardware_module._stable_tandem_partition_suffix

    def planted_suffix(*args: object, **kwargs: object) -> dict[str, Any]:
        result = original(*args, **kwargs)
        if kwargs["label"] == phase:
            result["bench_gain_indices"] = [endpoint, endpoint]
        return result

    monkeypatch.setattr(
        transient_hardware_module,
        "_stable_tandem_partition_suffix",
        planted_suffix,
    )
    with pytest.raises(
        EvidenceInvalid,
        match="stable endpoints do not prove the commanded attack decrease",
    ):
        _run_fake(_FakeRadio(tmp_path), _quality(tmp_path))


def test_tandem_close_counter_ledger_preserves_bounded_forward_deltas(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.preclose_transition_delta = 2
    radio.post_close_transition_delta = 2
    report, _path = _run_fake(radio, _quality(tmp_path))
    tandem = next(mode for mode in report["modes"] if mode["mode"] == "tandem_auto")
    ledger = tandem["acquisition"]["close_counter_ledger"]

    assert ledger["last_frame_to_pre_close_forward_delta"] == 2
    assert ledger["transition_count_forward_delta"] == 2
    assert ledger["maximum_forward_delta"] == 64
    assert ledger["pre_endpoint"] == [65, 65]
    assert ledger["post_endpoint"] == [65, 65]
    assert ledger["exact_retired_tail_count_claim"] is None


@pytest.mark.parametrize(
    ("transition_delta", "endpoint_delta", "message"),
    (
        (65, 1, "exceed the FIFO retirement bound"),
        (0, -1, "endpoint movement disagrees with transition count"),
    ),
)
def test_tandem_close_counter_ledger_rejects_reset_or_endpoint_substitution(
    tmp_path: Path, transition_delta: int, endpoint_delta: int, message: str
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.post_close_transition_delta = transition_delta
    radio.post_close_endpoint_delta = endpoint_delta

    with pytest.raises(EvidenceInvalid, match=message):
        _run_fake(radio, _quality(tmp_path))


def test_tandem_deferred_readback_failure_preserves_progressive_schedule(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.deferred_readback_override = -40.0

    with pytest.raises(EvidenceInvalid, match="deferred TX2 readback differs"):
        _run_fake(radio, _quality(tmp_path))

    persisted = json.loads(
        (
            tmp_path / radio.options.serial / "tandem-agc-transient-report.json"
        ).read_text(encoding="utf-8")
    )
    failure = persisted["failure_evidence"]
    diagnostics = failure["acquisition"]["schedule_diagnostics"]
    assert failure["verdict"] == "invalid"
    assert diagnostics["strong_attack"]["status"] == "failed"
    assert diagnostics["strong_attack"]["write_ack"]["attempt_count"] == 1
    assert diagnostics["strong_attack"]["write_ack"]["acknowledged"] is True
    assert diagnostics["strong_attack"]["deferred_tx2_readback"] == {
        **diagnostics["strong_attack"]["deferred_tx2_readback"],
        "attempt_count": 1,
        "observed_level_db": -40.0,
        "passed": False,
    }
    assert failure["acquisition"]["shutdown"]["cancel_called"] is True
    assert failure["acquisition"]["buffer_close_completed"] is False


def test_tandem_first_refill_failure_is_delivered_once_and_cancelled(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.fail_first_metadata_capture = True

    with pytest.raises(EvidenceInvalid, match="planted first metadata refill failure"):
        _run_fake(radio, _quality(tmp_path))

    assert radio.buffer_cancel_calls == 1
    assert not any(
        thread.name == "tandem-transient-batch-acquisition"
        for thread in threading.enumerate()
    )
    metadata_enter = max(
        index
        for index, operation in enumerate(radio.operations)
        if operation[:2] == ("buffer_enter", "metadata")
    )
    mute = radio.operations.index(("mute_all",), metadata_enter + 1)
    cancel = radio.operations.index(("buffer_cancel",), mute + 1)
    close = radio.operations.index(("buffer_exit", "metadata"), cancel + 1)
    assert metadata_enter < mute < cancel < close


def test_tandem_final_wrapper_mute_failure_preserves_full_invalid_mode(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.fail_completed_tandem_wrapper_mute = True

    with pytest.raises(RuntimeError, match="planted tandem wrapper mute failure"):
        _run_fake(radio, _quality(tmp_path))

    persisted = json.loads(
        (
            tmp_path / radio.options.serial / "tandem-agc-transient-report.json"
        ).read_text(encoding="utf-8")
    )
    failure = persisted["failure_evidence"]
    assert persisted["verdict"] == "invalid"
    assert failure["mode"] == "tandem_auto"
    assert failure["verdict"] == "invalid"
    assert len(failure["batch_frames"]) == 64
    assert failure["acquisition"]["artifact_manifest"]["write_complete"] is True
    assert "planted tandem wrapper mute failure" in failure["fatal_error"]
    assert failure["cleanup_request_error"] == failure["fatal_error"]
    assert persisted["modes"][-1] == failure


def test_tandem_memory_ledger_measures_and_gates_finished_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, _path = _run_fake(_FakeRadio(tmp_path), _quality(tmp_path))
    tandem = next(mode for mode in report["modes"] if mode["mode"] == "tandem_auto")
    ledger = tandem["acquisition"]["memory_ledger"]
    assert ledger["parsed_evidence_reservation_bytes"] == 8_388_608
    assert ledger["post_close_fft_workspace_bytes"] == 8_388_608
    assert ledger["capture_phase_envelope_bytes"] == 89_261_056
    assert ledger["post_close_materialization_envelope_bytes"] == 54_525_952
    assert ledger["maximum_phase_envelope_bytes"] == 89_261_056
    assert ledger["aggregate_resident_bytes"] == 89_261_056
    assert ledger["maximum_aggregate_bytes"] == 100_663_296
    assert type(ledger["measured_finished_mode_and_parsed_metadata_bytes"]) is int
    live_measured = ledger["measured_finished_mode_and_parsed_metadata_bytes"]
    canonical_bytes = ledger["canonical_evidence_projection_bytes"]
    assert type(canonical_bytes) is int
    assert 0 < canonical_bytes <= live_measured <= 8_388_608
    assert ledger["measured_evidence_within_reservation"] is True
    assert ledger["canonical_evidence_projection_method"] == (
        "canonical-json-v1: finished tandem mode with attestation value fields "
        "replaced by fixed sentinels plus 64 normalized reparsed metadata records"
    )
    reparsed = [
        parse_tandem_frame_metadata(
            (tmp_path / frame["raw_metadata_path"]).read_bytes()
        )
        for frame in tandem["batch_frames"]
    ]
    canonical = transient_hardware_module._canonical_tandem_evidence_bytes(
        tandem, reparsed
    )
    assert len(canonical) == canonical_bytes
    assert hashlib.sha256(canonical).hexdigest() == (
        ledger["canonical_evidence_projection_sha256"]
    )
    substituted_live_diagnostic = json.loads(json.dumps(tandem))
    substituted_live_diagnostic["acquisition"]["memory_ledger"][
        "measured_finished_mode_and_parsed_metadata_bytes"
    ] = 1
    assert transient_hardware_module._canonical_tandem_evidence_bytes(
        substituted_live_diagnostic, reparsed
    ) == canonical
    assert canonical_bytes > 1

    fake_frames = [
        transient_hardware_module._DeferredFrame(
            record={}, raw=b"", metadata=SimpleNamespace()
        )
        for _ in range(64)
    ]
    substituted = {
        "acquisition": {
            "memory_ledger": {"parsed_evidence_reservation_bytes": 8_388_608.0}
        }
    }
    with pytest.raises(EvidenceInvalid, match="reservation was substituted"):
        transient_hardware_module._attest_tandem_evidence_reservation(
            substituted, fake_frames
        )

    overbound = {
        "acquisition": {
            "memory_ledger": {
                "parsed_evidence_reservation_bytes": 8_388_608,
                "canonical_evidence_projection_method": ledger[
                    "canonical_evidence_projection_method"
                ],
            }
        }
    }
    monkeypatch.setattr(
        transient_hardware_module,
        "_canonical_tandem_evidence_bytes",
        lambda _record, _metadata: b"{}",
    )
    monkeypatch.setattr(
        transient_hardware_module,
        "_recursive_resident_bytes",
        lambda _value: 8_388_609,
    )
    with pytest.raises(EvidenceInvalid, match="violate the retained evidence"):
        transient_hardware_module._attest_tandem_evidence_reservation(
            overbound, fake_frames
        )


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
            for bound in gain["attack_returned_iq_observation_bounds"]
        )
        assert gain["hardware_latency_qualified"] is False

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
        if mode["mode"] == "tandem_auto":
            assert initial["timing_role"] == "pre_session_weak_conditioning_write"
            assert initial["sample_anchor_policy"] == (
                "unbounded in hardware sample time; write predates AUTO62 "
                "batch ownership"
            )
        else:
            assert initial["timing_role"] == "pre_session_conditioning_write"

        anchor = mode["conditioning_anchor"]
        if mode["mode"] == "tandem_auto":
            assert anchor["timing_role"] == "exact_retained_pre_attack_tail"
            assert anchor["sample_anchor_policy"].startswith(
                "exact final 8192 samples"
            )
            assert anchor["sample_uncertainty"] == 8_192
        else:
            assert anchor["timing_role"] == "observed_stable_conditioning_interval"
            assert "not the initial write time" in anchor["sample_anchor_policy"]
            assert anchor["sample_uncertainty"] == 1_024

        for command_id in ("strong_attack", "weak_release"):
            command = commands[command_id]
            assert command["sample_uncertainty"] > 0
            if mode["mode"] == "tandem_auto":
                assert command["sample_uncertainty"] <= 16_384
                assert (
                    command["timing_role"]
                    == "s0_targeted_one_write_bracketed_by_coherent_fpga_counter"
                )
                assert command["sample_counter_bracket"]["command_interval"] == "[A,C)"
            else:
                assert command["sample_uncertainty"] == 1_024
                assert command["timing_role"] == (
                    "host_write_positioned_on_returned_iq_ordinal_axis"
                )
        if mode["mode"] != "tandem_auto":
            assert mode["timing_basis"] == "ordinary_returned_iq_ordinal_axis"
            for response in mode["responses"].values():
                assert response["hardware_latency_qualified"] is False
                assert response["timing_qualification"] == (
                    "returned_iq_observation_only"
                )
                assert not any(
                    key.startswith("signal_settling_latency_") for key in response
                )
            comparison = next(
                item for item in report["comparison"] if item["mode"] == mode["mode"]
            )
            assert comparison["attack"]["signal_settling_latency_lower_samples"] is None
            assert comparison["attack"]["signal_settling_latency_lower_seconds"] is None


def test_tandem_command_bracket_rejects_even_a_matched_metadata_gap(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.sample_gap_capture_index = 3
    with pytest.raises(EvidenceInvalid, match="provider gap is forbidden") as raised:
        _run_fake(radio, _quality(tmp_path))
    assert "buffer 2->4" in str(raised.value)
    assert "sample 231072->362144" in str(raised.value)
    assert "hidden transitions 0" in str(raised.value)


def test_runner_rejects_excessive_command_sample_uncertainty_and_checkpoints(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.sample_counter_step = 1_024
    with pytest.raises(EvidenceInvalid, match=r"uncertainty 12288 exceeds 1024"):
        _run_fake(
            radio,
            _quality(tmp_path),
            capture=_capture_options(max_sample_uncertainty=1_024),
        )

    report_path = tmp_path / radio.options.serial / "tandem-agc-transient-report.json"
    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted["verdict"] == "invalid"
    assert "uncertainty 12288 exceeds 1024" in persisted["fatal_error"]
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
    assert "sample delta 131072" in persisted["fatal_error"]
    assert "expected 65536" in persisted["fatal_error"]


def test_tandem_provider_gap_cannot_hide_transient_event_timing(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.sample_gap_capture_index = 3
    radio.hidden_transition_capture_index = 3
    with pytest.raises(EvidenceInvalid, match="provider gap is forbidden") as raised:
        _run_fake(radio, _quality(tmp_path))
    evidence = re.search(
        r"transition delta (\d+), visible events (\d+), hidden transitions (\d+)",
        str(raised.value),
    )
    assert evidence is not None
    transition_delta, visible_events, hidden_transitions = map(int, evidence.groups())
    assert visible_events in (0, 1)
    assert hidden_transitions == 1
    assert transition_delta == visible_events + hidden_transitions


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
    assert set(radio.metadata_capture_thread_names) == {
        "tandem-transient-batch-acquisition"
    }
    assert {thread for thread, _value in radio.counter_reads} == {"MainThread"}
    acquisition = tandem["acquisition"]
    assert acquisition["transport"] == "single_metadata_batch"
    assert acquisition["kernel_buffers"] == 8
    assert acquisition["initiating_batch_refill_calls"] == 1
    assert acquisition["cached_replay_refill_calls"] == 63
    assert acquisition["produced_frames"] == 64
    assert acquisition["consumed_frames"] == 64
    assert (
        attack["sample_counter_bracket"]["raw_c_causal_advance"]
        != attack["sample_counter_bracket"]["raw_b_first_advance"]
    )
    assert all(
        frame["continuity"]["buffer_delta"] in (None, 1)
        and frame["continuity"]["provider_gap_accepted"] is False
        for frame in tandem["batch_frames"]
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

    ordinary_frames = [
        frame
        for mode in report["modes"]
        if mode["mode"] != "tandem_auto"
        for frame in (
            mode["preconditioning"]["trace"]
            + mode["attack_frames"]
            + mode["release_frames"]
        )
    ]
    tandem = next(mode for mode in report["modes"] if mode["mode"] == "tandem_auto")
    tandem_frames = tandem["batch_frames"]
    assert analyzed == len(ordinary_frames) + len(tandem_frames) + 2
    assert written == len(ordinary_frames) + 2 * len(tandem_frames)
    assert all(
        len(frame["sha256"]) == 64
        and frame["analysis"]["samples_per_channel"] == 1_024
        and Path(frame["iq_path"]).is_file()
        for frame in ordinary_frames
    )
    assert all(
        len(frame["sha256"]) == 64
        and frame["analysis"]["samples_per_channel"] == 65_536
        and (tmp_path / frame["iq_path"]).is_file()
        and (tmp_path / frame["raw_metadata_path"]).is_file()
        for frame in tandem_frames
    )


def test_tandem_counter_bracket_requires_post_write_cdc_advance(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.freeze_sample_counter = True
    with pytest.raises(EvidenceInvalid, match="target-poll read budget"):
        _run_fake(radio, _quality(tmp_path))


def test_tandem_counter_bracket_rejects_an_empty_sample_interval(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.scripted_counter_reads = [900, 950, 975, 1_000]
    with pytest.raises(EvidenceInvalid, match="bracket is empty"):
        transient_hardware_module._timestamp_tandem_command(
            radio,
            "planted_empty_bracket",
            -30.0,
            last_observed_frame_end=1_000,
            clock_ns=_Clocks().clock_ns,
            max_host_jitter_ns=1_000,
            max_sample_uncertainty=16_384,
            readback_tolerance_db=0.25,
        )


def test_tandem_response_partition_accepts_only_the_bounded_producer_prefix() -> None:
    frame_samples = 1_024
    frames = [
        {
            "first_sample_sequence": index * frame_samples,
            "sample_end_exclusive": (index + 1) * frame_samples,
        }
        for index in range(7)
    ]
    accepted = transient_hardware_module._response_partition(
        frames,
        transient_hardware_module.StimulusCommand(
            "bounded_prefix",
            -30.0,
            -30.0,
            1_000,
            1_100,
            2 * frame_samples,
            5 * frame_samples,
        ),
        required_fully_post_frames=2,
    )
    assert accepted == {
        "precommand_prefetch_frames": 2,
        "command_bracket_frames": 3,
        "fully_post_command_frames": 2,
        "required_fully_post_command_frames": 2,
        "maximum_non_post_command_frames": 5,
    }

    with pytest.raises(EvidenceInvalid, match="exceeding the 5-frame producer"):
        transient_hardware_module._response_partition(
            frames,
            transient_hardware_module.StimulusCommand(
                "oversized_prefix",
                -30.0,
                -30.0,
                1_000,
                1_100,
                2 * frame_samples,
                6 * frame_samples,
            ),
            required_fully_post_frames=2,
        )


def test_blocked_tandem_refill_is_muted_cancelled_and_joined_before_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(transient_hardware_module, "_CAPTURE_THREAD_WAIT_SECONDS", 0.05)
    radio = _FakeRadio(tmp_path)
    radio.block_metadata_refill = True

    with pytest.raises(EvidenceInvalid, match="returned no cached frame before timeout"):
        _run_fake(radio, _quality(tmp_path))

    assert radio.blocked_refill_waiting.is_set()
    assert radio.buffer_cancel_calls == 1
    assert radio.mute_while_buffer_open_count >= 1
    assert not any(
        thread.name == "tandem-transient-batch-acquisition"
        for thread in threading.enumerate()
    )
    metadata_enter = max(
        index
        for index, operation in enumerate(radio.operations)
        if operation[:2] == ("buffer_enter", "metadata")
    )
    emergency_mute = radio.operations.index(("mute_all",), metadata_enter + 1)
    cancel = radio.operations.index(("buffer_cancel",), emergency_mute + 1)
    metadata_exit = radio.operations.index(("buffer_exit", "metadata"), cancel + 1)
    assert emergency_mute < cancel < metadata_exit


def test_successful_tandem_shutdown_replays_full_batch_without_cancel_before_close(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    report, _path = _run_fake(radio, _quality(tmp_path))
    tandem = next(mode for mode in report["modes"] if mode["mode"] == "tandem_auto")

    assert report["verdict"] == "pass"
    assert radio.buffer_cancel_calls == 0
    assert tandem["acquisition"]["batch_cache_fully_replayed"] is True
    assert tandem["acquisition"]["shutdown"] == {
        "events": tandem["acquisition"]["shutdown"]["events"],
        "worker_in_flight_before_shutdown": False,
        "cancel_required": False,
        "cancel_called": False,
        "cancel_succeeded": None,
        "worker_stopped": True,
        "batch_fully_consumed": True,
        "shutdown_path": "normal_close_after_full_cache_replay",
    }
    assert [
        event["event"] for event in tandem["acquisition"]["shutdown"]["events"]
    ] == [
        "prejoin_mute_start",
        "prejoin_mute_complete",
        "worker_stop_start",
        "worker_stop_complete",
    ]
    assert not any(
        thread.name == "tandem-transient-batch-acquisition"
        for thread in threading.enumerate()
    )


def test_tandem_cancel_failure_is_preserved_with_acquisition_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(transient_hardware_module, "_CAPTURE_THREAD_WAIT_SECONDS", 0.05)
    radio = _FakeRadio(tmp_path)
    radio.block_metadata_refill = True
    radio.cancel_failures_remaining = 1

    with pytest.raises(BaseExceptionGroup) as raised:
        _run_fake(radio, _quality(tmp_path))

    def leaves(error: BaseException) -> list[BaseException]:
        if isinstance(error, BaseExceptionGroup):
            return [child for item in error.exceptions for child in leaves(item)]
        return [error]

    messages = [str(error) for error in leaves(raised.value)]
    assert any("returned no cached frame before timeout" in message for message in messages)
    assert any("planted buffer cancel failure" in message for message in messages)
    assert radio.mute_while_buffer_open_count >= 1
    assert not any(
        thread.name == "tandem-transient-batch-acquisition"
        for thread in threading.enumerate()
    )


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


def test_iio_buffer_close_failure_cannot_mask_body_failure() -> None:
    class ClosingBuffer:
        def close(self) -> None:
            raise RuntimeError("planted synchronous close failure")

    fake_radio = SimpleNamespace(
        rx=SimpleNamespace(set_kernel_buffers_count=lambda _count: None),
        iio=SimpleNamespace(Buffer=lambda *_args: ClosingBuffer()),
    )

    with (
        pytest.raises(BaseExceptionGroup) as raised,
        Issue46Radio.buffer(
            fake_radio,
            "ordinary",
            1,
            1_024,
        ),
    ):
        raise EvidenceInvalid("planted buffer body failure")

    messages = [str(error) for error in raised.value.exceptions]
    assert any("planted buffer body failure" in message for message in messages)
    assert any("planted synchronous close failure" in message for message in messages)


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


def test_transient_stimulus_requires_distinct_configured_rungs(tmp_path: Path) -> None:
    quality = _quality(tmp_path)
    with pytest.raises(ValueError, match="configured quality-trajectory rungs"):
        validate_transient_options(
            quality,
            _capture_options(weak_stimulus_tx_gain_db=-55.0),
        )
    with pytest.raises(ValueError, match="weak stimulus must be below"):
        validate_transient_options(
            quality,
            _capture_options(weak_stimulus_tx_gain_db=-30.0),
        )


def test_release_default_uses_the_characterized_minus_45_db_weak_rung() -> None:
    capture = TransientCaptureOptions()
    assert capture.weak_stimulus_tx_gain_db == -45.0
    assert capture.strong_stimulus_tx_gain_db == -30.0
    assert capture.strong_stimulus_tx_gain_db - capture.weak_stimulus_tx_gain_db == 15.0
