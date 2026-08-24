"""Fake-only safety and execution goldens for modulated hardware support."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from builtins import BaseExceptionGroup
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from .experiment import (
    DAC_SELECT_DMA,
    DAC_SELECT_ZERO,
    TX_MUTE_DB,
    EvidenceInvalid,
    FixtureSafetyError,
    Issue46Options,
    Issue46Radio,
)
from .metadata_abi import (
    TandemEventDirection,
    TandemFrameMetadata,
    TandemGainEvent,
    TandemGainTable,
    TandemState,
)
from .modulated_hardware import (
    MODE_MANUAL,
    MODE_NATIVE_FAST,
    MODE_TANDEM,
    MODULATED_MODES,
    BlockerPoint,
    ModulatedDegradationThresholds,
    ModulatedHardwareOptions,
    _parse_and_validate_metadata,
    _TandemContinuity,
    evaluate_modulated_hardware_report,
    run_modulated_hardware_campaign,
    run_serial_modulated_hardware_campaign,
    validate_modulated_hardware_options,
)
from .modulated_quality import ModulatedQualityThresholds, decode_tx2_cs16


class _ScanChannel:
    def __init__(
        self,
        channel_id: str,
        enabled: bool,
        *,
        index: int,
        format_overrides: dict[str, Any] | None = None,
    ):
        self.id = channel_id
        self.scan_element = True
        self.enabled = enabled
        self.index = index
        scan_format = {
            "length": 16,
            "bits": 16,
            "shift": 0,
            "is_signed": True,
            "is_be": False,
            "repeat": 1,
        }
        scan_format.update(format_overrides or {})
        self.data_format = SimpleNamespace(**scan_format)


class _OutputBuffer:
    def __init__(
        self,
        samples: int,
        *,
        readable: bool = True,
        short_write: bool = False,
        fail_close: bool = False,
    ):
        self.payload = bytes(samples * 8)
        self.readable = readable
        self.short_write = short_write
        self.fail_close = fail_close
        self.pushed = False
        self.closed = False

    def __len__(self) -> int:
        return len(self.payload)

    def write(self, payload: bytes | bytearray) -> int:
        self.payload = bytes(payload)
        return len(self.payload) - int(self.short_write)

    def read(self) -> bytes:
        if not self.readable:
            raise OSError("planted output readback failure")
        return self.payload

    def push(self) -> None:
        self.pushed = True

    def close(self) -> None:
        self.closed = True
        if self.fail_close:
            raise OSError("planted output close failure")


def _dma_context_radio(
    *,
    readable: bool = True,
    short_write: bool = False,
    fail_close: bool = False,
    scan_indexes: tuple[int, int, int, int] = (0, 1, 2, 3),
    format_overrides: dict[str, Any] | None = None,
) -> tuple[Issue46Radio, _OutputBuffer, list[int], list[_ScanChannel]]:
    radio = Issue46Radio.__new__(Issue46Radio)
    channels = [
        _ScanChannel(
            f"voltage{index}",
            enabled=bool(index % 2),
            index=scan_indexes[index],
            format_overrides=(format_overrides if index == 0 else None),
        )
        for index in range(4)
    ]
    radio.tx = SimpleNamespace(channels=channels, sample_size=8)
    output = _OutputBuffer(
        4,
        readable=readable,
        short_write=short_write,
        fail_close=fail_close,
    )
    radio.iio = SimpleNamespace(Buffer=lambda _device, _samples, _cyclic: output)
    selectors: list[int] = []
    mute_calls: list[str] = []
    radio.mute_all = lambda: mute_calls.append("entry")
    radio._write_selector = lambda _channel, selector: selectors.append(selector)
    hardwaregain = SimpleNamespace(value=str(TX_MUTE_DB))
    tx1 = SimpleNamespace(attrs={"hardwaregain": hardwaregain})
    radio._phy_channel = lambda _name, _output: tx1

    def best_effort_mute() -> tuple[dict[str, Any], list[str]]:
        mute_calls.append("exit")
        return {"verified": True}, []

    radio._best_effort_mute = best_effort_mute
    radio._test_mute_calls = mute_calls
    return radio, output, selectors, channels


def _group_members(error: BaseException) -> list[BaseException]:
    nested = getattr(error, "exceptions", None)
    if nested is None:
        return [error]
    return [member for item in nested for member in _group_members(item)]


def test_cyclic_dma_interleaves_zero_tx1_and_verified_tx2() -> None:
    radio, output, selectors, channels = _dma_context_radio()
    original_states = [channel.enabled for channel in channels]
    tx2 = bytes.fromhex("01000200 fdff0400 0500faff 07000800")

    with radio.cyclic_tx2_waveform(tx2, sample_count=4) as evidence:
        assert evidence["selectors"] == [
            DAC_SELECT_ZERO,
            DAC_SELECT_ZERO,
            DAC_SELECT_DMA,
            DAC_SELECT_DMA,
        ]
        assert output.pushed
        for index in range(4):
            assert output.payload[index * 8 : index * 8 + 4] == bytes(4)
            assert (
                output.payload[index * 8 + 4 : index * 8 + 8]
                == tx2[index * 4 : index * 4 + 4]
            )

    assert selectors == [
        DAC_SELECT_ZERO,
        DAC_SELECT_ZERO,
        DAC_SELECT_DMA,
        DAC_SELECT_DMA,
    ]
    assert output.closed
    assert radio._test_mute_calls == ["entry", "exit"]
    assert [channel.enabled for channel in channels] == original_states
    assert radio._last_cyclic_dma_cleanup["buffer_closed"]
    assert radio._last_cyclic_dma_cleanup["failures"] == []


@pytest.mark.parametrize(
    ("radio_kwargs", "message"),
    [
        ({"short_write": True}, "write accepted"),
        ({"readable": False}, "readback failed"),
    ],
)
def test_cyclic_dma_fails_closed_on_unverified_payload(
    radio_kwargs: dict[str, bool], message: str
) -> None:
    radio, output, _selectors, channels = _dma_context_radio(**radio_kwargs)
    original_states = [channel.enabled for channel in channels]
    with (
        pytest.raises(FixtureSafetyError, match=message),
        radio.cyclic_tx2_waveform(bytes(16), sample_count=4),
    ):
        pytest.fail("unsafe cyclic context yielded")
    assert output.closed
    assert radio._test_mute_calls == ["entry", "exit"]
    assert [channel.enabled for channel in channels] == original_states


def test_cyclic_dma_preserves_body_and_cleanup_failures() -> None:
    radio, output, _selectors, _channels = _dma_context_radio(fail_close=True)
    with (
        pytest.raises(BaseExceptionGroup) as caught,
        radio.cyclic_tx2_waveform(bytes(16), sample_count=4),
    ):
        raise RuntimeError("planted campaign body failure")
    members = _group_members(caught.value)
    assert any(isinstance(item, RuntimeError) for item in members)
    assert any(
        isinstance(item, FixtureSafetyError) and "buffer close" in str(item)
        for item in members
    )
    assert output.closed
    assert radio._test_mute_calls == ["entry", "exit"]
    assert not radio._last_cyclic_dma_cleanup["buffer_closed"]


def test_cyclic_dma_rejects_output_buffer_without_readback() -> None:
    radio, output, _selectors, _channels = _dma_context_radio()
    output.read = None  # type: ignore[method-assign]
    with (
        pytest.raises(FixtureSafetyError, match="cannot provide payload readback"),
        radio.cyclic_tx2_waveform(bytes(16), sample_count=4),
    ):
        pytest.fail("unverified output buffer yielded")
    assert output.closed
    assert radio._test_mute_calls == ["entry", "exit"]


@pytest.mark.parametrize(
    ("radio_kwargs", "message"),
    [
        ({"scan_indexes": (1, 0, 2, 3)}, "scan index"),
        ({"format_overrides": {"is_be": True}}, "scan format"),
        ({"format_overrides": {"bits": 12}}, "scan format"),
    ],
)
def test_cyclic_dma_rejects_reordered_or_non_cs16_scan_layout(
    radio_kwargs: dict[str, Any], message: str
) -> None:
    radio, _output, _selectors, channels = _dma_context_radio(**radio_kwargs)
    original_states = [channel.enabled for channel in channels]
    with (
        pytest.raises(FixtureSafetyError, match=message),
        radio.cyclic_tx2_waveform(bytes(16), sample_count=4),
    ):
        pytest.fail("unattested scan layout yielded")
    assert radio._test_mute_calls == ["entry", "exit"]
    assert [channel.enabled for channel in channels] == original_states


class _FakeCampaignRadio:
    def __init__(
        self,
        options: ModulatedHardwareOptions,
        *,
        clip: tuple[str, str] | None = None,
        noisy: tuple[str, str, float] | None = None,
        unpaired_tandem: bool = False,
        fail_mute_call: int | None = None,
        metadata_abi: int = 2,
        cleanup_verified_on_close: bool = True,
        cleanup_failures: tuple[str, ...] = (),
        tx_gain_readback_offset_db: float = 0.0,
    ):
        self.options = SimpleNamespace(
            serial="fake-usb-radio",
            sample_rate_hz=options.sample_rate_hz,
            samples_per_channel=options.capture_samples,
            tx_gain_db=options.tx2_gain_db,
            center_frequency_hz=options.center_frequency_hz,
        )
        self.identity = {
            "serial": self.options.serial,
            "uri": "usb:fake",
            "firmware": "fake-offline-only",
        }
        self.clip = clip
        self.noisy = noisy
        self.unpaired_tandem = unpaired_tandem
        self.fail_mute_call = fail_mute_call
        self.metadata_abi = metadata_abi
        self.cleanup_verified_on_close = cleanup_verified_on_close
        self.cleanup_failures = cleanup_failures
        self.tx_gain_readback_offset_db = tx_gain_readback_offset_db
        self.active: Any = None
        self.active_case = ""
        self.mode = "manual"
        self.in_metadata = False
        self.in_buffer = False
        self.case_count = 0
        self.buffer_sequence = 0
        self.stream_id = 0
        self.capture_count = 0
        self.waveform_entries = 0
        self.mute_count = 0
        self.close_count = 0
        self.tx_gain_log: list[float] = []
        self.tx_mutes_inside_buffer: list[bool] = []
        self.cleanup_verified = False
        self._last_mute_evidence: dict[str, Any] = {}
        self._last_cyclic_dma_cleanup: dict[str, Any] = {}
        self._report_path: Path | None = None

    def read_center_frequency(self) -> dict[str, int]:
        return {
            "rx_lo_hz": self.options.center_frequency_hz,
            "tx_lo_hz": self.options.center_frequency_hz,
        }

    def mute_all(self) -> None:
        self.mute_count += 1
        if self.mute_count == self.fail_mute_call:
            raise OSError("planted final mute failure")
        self._last_mute_evidence = {"verified": True, "tx1_gain_db": TX_MUTE_DB}

    @contextmanager
    def cyclic_tx2_waveform(self, payload: bytes, *, sample_count: int):
        decoded = decode_tx2_cs16(payload)
        assert decoded.size == sample_count
        self.active = decoded
        self.active_case = "desired_only" if self.case_count == 0 else "blocker_00"
        self.case_count += 1
        self.waveform_entries += 1
        try:
            yield {
                "sample_count": sample_count,
                "cyclic": True,
                "tx1_source": "zero samples and ZERO selector",
                "tx2_source": "cyclic DMA",
            }
        finally:
            self.active = None
            self._last_cyclic_dma_cleanup = {
                "mute": {"verified": True},
                "buffer_closed": True,
                "failures": [],
            }

    def configure_rx(self, mode: str, *, manual_gain_db: float | None = None) -> None:
        del manual_gain_db
        self.mode = mode

    def read_rx_state(self) -> dict[str, list[Any]]:
        gains = {
            "manual": 40.0,
            "slow_attack": 32.0,
            "fast_attack": 31.0,
            "hybrid": 30.0,
        }
        return {"modes": [self.mode, self.mode], "gains_db": [gains[self.mode]] * 2}

    def set_tx2_gain(self, gain_db: float) -> float:
        self.tx_gain_log.append(float(gain_db))
        if gain_db == TX_MUTE_DB:
            self.tx_mutes_inside_buffer.append(self.in_buffer)
        if gain_db == TX_MUTE_DB:
            return float(gain_db)
        return float(gain_db) + self.tx_gain_readback_offset_db

    @contextmanager
    def buffer(
        self,
        api: str,
        kernel_buffers: int,
        samples_per_channel: int,
        *,
        tandem_request: bytes | None = None,
    ):
        del kernel_buffers, samples_per_channel
        assert (api == "metadata") == (tandem_request is not None)
        self.in_buffer = True
        self.in_metadata = api == "metadata"
        if self.in_metadata:
            self.stream_id += 1
            self.buffer_sequence = 0
        try:
            yield object(), self.metadata_abi if self.in_metadata else None
        finally:
            self.in_metadata = False
            self.in_buffer = False

    def _fake_metadata(self, samples: int, raw_bytes: int) -> TandemFrameMetadata:
        sequence = self.buffer_sequence
        self.buffer_sequence += 1
        return TandemFrameMetadata(
            version=5,
            header_bytes=0,
            features=0,
            flags=0,
            stream_id=self.stream_id,
            buffer_sequence=sequence,
            first_sample_sequence=sequence * samples,
            samples_per_channel=samples,
            iq_payload_bytes=raw_bytes,
            enabled_scan_mask=0x0F,
            sample_format=0,
            channel_count=2,
            observation_count=0,
            observation_capacity=64,
            event_count=0,
            event_capacity=64,
            observation_overflow_count=0,
            event_overflow_count=0,
            ownership_epoch=700 + self.stream_id,
            tandem_state=TandemState.ARMED_AUTO,
            tandem_fault_flags=0,
            tandem_transition_count=11,
            gain_table_id=TandemGainTable.MHZ_200_1300,
            threshold_provenance=0,
            minimum_gain_db=0,
            maximum_gain_db=62,
            initial_gain_db=40,
            minimum_gain_index=0,
            maximum_gain_index=62,
            rx1_gain_index=35,
            rx2_gain_index=36 if self.unpaired_tandem else 35,
            ad9361_temperature_mdeg_c=35_000,
            gain_events=(),
        )

    def capture_iq(
        self, _buffer: Any, *, metadata: bool, samples_per_channel: int
    ) -> tuple[bytes, TandemFrameMetadata | None, int]:
        np = pytest.importorskip("numpy")
        assert self.active is not None
        repeats = math.ceil(samples_per_channel / self.active.size)
        source = np.tile(self.active, repeats)[:samples_per_channel]
        source = source * (600.0 / 32_767.0)
        channels = np.stack((source * np.exp(0.2j), 0.82 * source * np.exp(-0.35j)))
        mode_name = (
            MODE_TANDEM
            if metadata
            else {
                "manual": "manual_fixed",
                "slow_attack": "native_slow_attack",
                "fast_attack": "native_fast_attack",
                "hybrid": "native_hybrid",
            }[self.mode]
        )
        if self.noisy is not None and self.noisy[:2] == (
            self.active_case,
            mode_name,
        ):
            rng = np.random.default_rng(1000 + self.capture_count)
            sigma = self.noisy[2]
            channels += sigma * (
                rng.normal(size=channels.shape) + 1j * rng.normal(size=channels.shape)
            )
        words = np.empty((samples_per_channel, 4), dtype="<i2")
        words[:, 0] = np.rint(channels[0].real).astype("<i2")
        words[:, 1] = np.rint(channels[0].imag).astype("<i2")
        words[:, 2] = np.rint(channels[1].real).astype("<i2")
        words[:, 3] = np.rint(channels[1].imag).astype("<i2")
        if self.clip == (self.active_case, mode_name):
            words[::16, 0] = 2_047
        raw = words.tobytes()
        self.capture_count += 1
        parsed = (
            self._fake_metadata(samples_per_channel, len(raw)) if metadata else None
        )
        return raw, parsed, self.capture_count

    def tandem_status(self) -> dict[str, int]:
        return {
            "state": int(TandemState.IDLE),
            "fault_flags": 0,
            "overflow_count": 0,
            "fifo_level": 0,
            "ownership_epoch": self.stream_id,
            "transition_count": 11,
            "rx1_gain_index": 35,
            "rx2_gain_index": 35,
        }

    def close(self) -> None:
        self.close_count += 1
        self.cleanup_verified = self.cleanup_verified_on_close
        if self._report_path is not None and self._report_path.exists():
            report = json.loads(self._report_path.read_text(encoding="utf-8"))
            report["cleanup"] = {
                "verified": self.cleanup_verified,
                "tx1_gain_db": TX_MUTE_DB,
                "tx2_gain_db": TX_MUTE_DB,
                "failures": (
                    list(self.cleanup_failures)
                    if self.cleanup_verified
                    else ["planted cleanup gap"]
                ),
            }
            temporary = self._report_path.with_suffix(self._report_path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self._report_path)


def _campaign_options(output_dir: Path) -> ModulatedHardwareOptions:
    return ModulatedHardwareOptions(
        physical_attenuation_db=0.0,
        sample_rate_hz=1_024_000,
        symbol_count=64,
        samples_per_symbol=4,
        capture_samples=8_192,
        blocker_points=(BlockerPoint(320_000.0, -20.0, 47),),
        kernel_buffers=1,
        stable_frames=2,
        measurement_frames=1,
        max_settle_frames=5,
        settle_timeout_seconds=2.0,
        max_seconds=30.0,
        tandem_power_measurement_samples=128,
        tandem_cooldown_periods=3,
        output_dir=output_dir,
    )


def _metadata_with_event(
    base: TandemFrameMetadata,
    *,
    buffer_sequence: int,
    transition_count: int,
    event_sequence: int,
    direction: TandemEventDirection,
    gain: int,
    rx2_gain: int | None = None,
) -> TandemFrameMetadata:
    samples = base.samples_per_channel
    event = TandemGainEvent(
        sample_sequence=buffer_sequence * samples + 10,
        event_sequence=event_sequence,
        flags=(int(direction) << 4) | 4,
        rx1_gain_index=gain,
        rx2_gain_index=gain if rx2_gain is None else rx2_gain,
    )
    return replace(
        base,
        buffer_sequence=buffer_sequence,
        first_sample_sequence=buffer_sequence * samples,
        tandem_transition_count=transition_count,
        event_count=1,
        rx1_gain_index=gain,
        rx2_gain_index=gain,
        gain_events=(event,),
    )


def test_adjacent_tandem_metadata_reconciles_every_event_and_endpoint(
    tmp_path: Path,
) -> None:
    options = _campaign_options(tmp_path)
    radio = _FakeCampaignRadio(options)
    base = radio._fake_metadata(options.capture_samples, options.capture_samples * 8)
    continuity = _TandemContinuity()
    _parse_and_validate_metadata(
        base,
        raw_bytes=options.capture_samples * 8,
        options=options,
        continuity=continuity,
    )
    increased = _metadata_with_event(
        base,
        buffer_sequence=1,
        transition_count=12,
        event_sequence=100,
        direction=TandemEventDirection.INCREASE,
        gain=36,
    )
    _parse_and_validate_metadata(
        increased,
        raw_bytes=options.capture_samples * 8,
        options=options,
        continuity=continuity,
    )
    decreased = _metadata_with_event(
        base,
        buffer_sequence=2,
        transition_count=13,
        event_sequence=101,
        direction=TandemEventDirection.DECREASE,
        gain=35,
    )
    parsed = _parse_and_validate_metadata(
        decreased,
        raw_bytes=options.capture_samples * 8,
        options=options,
        continuity=continuity,
    )
    assert parsed.bench_gain_indices == (35, 35)


def test_provider_skipped_frames_are_gap_accounted_without_losing_events(
    tmp_path: Path,
) -> None:
    """Mirror real MetadataBuffer sequence jumps from device-side USB drops."""

    options = _campaign_options(tmp_path)
    radio = _FakeCampaignRadio(options)
    base = radio._fake_metadata(options.capture_samples, options.capture_samples * 8)
    continuity = _TandemContinuity()
    _parse_and_validate_metadata(
        base,
        raw_bytes=options.capture_samples * 8,
        options=options,
        continuity=continuity,
    )
    first_visible = _metadata_with_event(
        base,
        buffer_sequence=1,
        transition_count=12,
        event_sequence=100,
        direction=TandemEventDirection.INCREASE,
        gain=36,
    )
    _parse_and_validate_metadata(
        first_visible,
        raw_bytes=options.capture_samples * 8,
        options=options,
        continuity=continuity,
    )
    # The provider increments both counters for every device refill.  Frames 2
    # and 3 were not delivered over USB; their two transitions cancel at the
    # endpoint and are intentionally absent from frame 4's event array.
    after_gap = replace(
        first_visible,
        buffer_sequence=4,
        first_sample_sequence=4 * options.capture_samples,
        tandem_transition_count=14,
        event_count=0,
        gain_events=(),
    )
    _parse_and_validate_metadata(
        after_gap,
        raw_bytes=options.capture_samples * 8,
        options=options,
        continuity=continuity,
    )
    assert continuity.last_frame_evidence == {
        "buffer_delta": 3,
        "sample_delta": 3 * options.capture_samples,
        "missing_frame_count": 2,
        "transition_count_delta": 2,
        "visible_event_count": 0,
        "hidden_transition_count": 2,
        "initial_unrepresented_transition_count": 0,
        "cumulative_missing_frame_count": 2,
        "cumulative_hidden_transition_count": 2,
        "cumulative_event_sequence_hole_count": 0,
    }
    recovered = _metadata_with_event(
        base,
        buffer_sequence=5,
        transition_count=15,
        event_sequence=103,
        direction=TandemEventDirection.INCREASE,
        gain=37,
    )
    parsed = _parse_and_validate_metadata(
        recovered,
        raw_bytes=options.capture_samples * 8,
        options=options,
        continuity=continuity,
    )
    assert parsed.bench_gain_indices == (37, 37)
    assert continuity.missing_frame_count == 2
    assert continuity.hidden_transition_count == 2
    assert continuity.event_sequence_hole_count == 1
    assert continuity.unrepresented_since_event == 0


def test_provider_gap_requires_matching_buffer_and_sample_deltas(
    tmp_path: Path,
) -> None:
    options = _campaign_options(tmp_path)
    radio = _FakeCampaignRadio(options)
    base = radio._fake_metadata(options.capture_samples, options.capture_samples * 8)
    continuity = _TandemContinuity()
    _parse_and_validate_metadata(
        base,
        raw_bytes=options.capture_samples * 8,
        options=options,
        continuity=continuity,
    )
    mismatched = replace(
        base,
        buffer_sequence=3,
        first_sample_sequence=2 * options.capture_samples,
    )
    with pytest.raises(EvidenceInvalid, match="deltas disagree"):
        _parse_and_validate_metadata(
            mismatched,
            raw_bytes=options.capture_samples * 8,
            options=options,
            continuity=continuity,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("hidden_transition", "lost transition event"),
        ("event_sequence", "event sequence is not contiguous"),
        ("wrong_step", r"exact paired \+/-1 endpoint"),
        ("torn_event", "event 0 endpoint gains are not paired"),
    ],
)
def test_adjacent_tandem_metadata_rejects_incomplete_transition_proof(
    tmp_path: Path, mutation: str, message: str
) -> None:
    options = _campaign_options(tmp_path)
    radio = _FakeCampaignRadio(options)
    base = radio._fake_metadata(options.capture_samples, options.capture_samples * 8)
    continuity = _TandemContinuity()
    _parse_and_validate_metadata(
        base,
        raw_bytes=options.capture_samples * 8,
        options=options,
        continuity=continuity,
    )
    first = _metadata_with_event(
        base,
        buffer_sequence=1,
        transition_count=12,
        event_sequence=100,
        direction=TandemEventDirection.INCREASE,
        gain=36,
    )
    if mutation == "hidden_transition":
        candidate = replace(
            first,
            event_count=0,
            gain_events=(),
            rx1_gain_index=35,
            rx2_gain_index=35,
        )
    else:
        _parse_and_validate_metadata(
            first,
            raw_bytes=options.capture_samples * 8,
            options=options,
            continuity=continuity,
        )
        candidate = _metadata_with_event(
            base,
            buffer_sequence=2,
            transition_count=13,
            event_sequence=100 if mutation == "event_sequence" else 101,
            direction=TandemEventDirection.INCREASE,
            gain=38 if mutation == "wrong_step" else 37,
            rx2_gain=36 if mutation == "torn_event" else None,
        )
    with pytest.raises(EvidenceInvalid, match=message):
        _parse_and_validate_metadata(
            candidate,
            raw_bytes=options.capture_samples * 8,
            options=options,
            continuity=continuity,
        )


def test_fake_radio_runs_all_modes_and_blocker_oracles_atomically(
    tmp_path: Path,
) -> None:
    options = _campaign_options(tmp_path)
    radio = _FakeCampaignRadio(options)
    report, path = run_modulated_hardware_campaign(radio, options)

    assert report["verdict"] == "pass", report.get("evaluation")
    assert path.exists()
    assert not path.with_suffix(path.suffix + ".tmp").exists()
    assert len(report["runs"]) == 2 * len(MODULATED_MODES)
    assert {run["mode"] for run in report["runs"]} == set(MODULATED_MODES)
    assert all(run["summary"]["quality_valid"] for run in report["runs"])
    assert report["evaluation"]["degradation_valid"]
    assert report["stimulus_topology"]["active_transmitters"] == ["TX2"]
    assert not report["stimulus_topology"]["external_generator_required"]
    assert not report["stimulus_topology"]["second_transmitter_required"]
    assert radio.waveform_entries == 2
    assert radio.mute_count >= 2
    assert radio.tx_gain_log.count(TX_MUTE_DB) == len(report["runs"])
    assert radio.tx_mutes_inside_buffer == [True] * len(report["runs"])
    tandem_runs = [run for run in report["runs"] if run["mode"] == MODE_TANDEM]
    assert tandem_runs
    assert all(run["metadata_abi"] == 2 for run in tandem_runs)
    blocker_runs = [run for run in report["runs"] if run["case_id"] == "blocker_00"]
    assert all(run["summary"]["blocker_measurement"]["valid"] for run in blocker_runs)

    provenance_frames = [
        (run, measurement)
        for run in report["runs"]
        for measurement in run["measurements"]
        if "raw_iq_provenance" in measurement
    ]
    assert len(provenance_frames) == 1
    raw_run, raw_frame = provenance_frames[0]
    assert (raw_run["case_id"], raw_run["mode"]) == (
        "desired_only",
        "manual_fixed",
    )
    provenance = raw_frame["raw_iq_provenance"]
    artifact = options.output_dir / provenance["path"]
    payload = artifact.read_bytes()
    assert provenance["bytes"] == options.capture_samples * 8 == len(payload)
    assert provenance["sha256"] == raw_frame["sha256"]
    assert provenance["sha256"] == hashlib.sha256(payload).hexdigest()
    assert provenance["channel_layout"] == ["rx0_i", "rx0_q", "rx1_i", "rx1_q"]
    assert not artifact.with_suffix(artifact.suffix + ".tmp").exists()


def test_evaluator_rejects_missing_invalid_or_mixed_iq_conventions(
    tmp_path: Path,
) -> None:
    options = _campaign_options(tmp_path)
    report, _path = run_modulated_hardware_campaign(
        _FakeCampaignRadio(options), options
    )
    original = report["runs"][0]["summary"]["iq_convention"]
    mutations = (
        ("missing", None, "invalid IQ convention"),
        ("invalid", "swapped", "invalid IQ convention"),
        (
            "mixed",
            "conjugated" if original == "direct" else "direct",
            "mixed IQ conventions",
        ),
    )
    for mutation, value, expected_reason in mutations:
        planted = copy.deepcopy(report)
        summary = planted["runs"][0]["summary"]
        if mutation == "missing":
            summary.pop("iq_convention")
        else:
            summary["iq_convention"] = value
        evaluation = evaluate_modulated_hardware_report(
            planted, options.degradation_thresholds
        )
        assert not evaluation["valid"]
        assert any(
            expected_reason in reason for reason in evaluation["failure_reasons"]
        )


def test_campaign_accepts_real_issue46_options_contract(tmp_path: Path) -> None:
    options = _campaign_options(tmp_path)
    radio = _FakeCampaignRadio(options)
    radio.options = Issue46Options(
        serial="fake-usb-radio",
        uri="usb:fake",
        allow_non_usb=False,
        firmware_pattern=r"fake",
        libiio_source_commit="a" * 40,
        attenuation_db=options.physical_attenuation_db,
        tx_gain_db=options.tx2_gain_db,
        sample_rate_hz=options.sample_rate_hz,
        samples_per_channel=options.capture_samples,
        profile="modulated-offline",
        sink="hash",
        expected="pass",
        output_dir=tmp_path,
        max_seconds=options.max_seconds,
        save_iq=False,
        pn_min_coherence=0.9,
        pn_min_peak_ratio=1.1,
        center_frequency_hz=options.center_frequency_hz,
    )
    report, _path = run_modulated_hardware_campaign(radio, options)
    assert report["verdict"] == "pass"
    assert len(report["runs"]) == 2 * len(MODULATED_MODES)


def test_tandem_refuses_legacy_metadata_abi_before_unmuting(tmp_path: Path) -> None:
    options = _campaign_options(tmp_path)
    radio = _FakeCampaignRadio(options, metadata_abi=1)
    with pytest.raises(EvidenceInvalid, match="requires metadata ABI 2"):
        run_modulated_hardware_campaign(radio, options)
    # Manual plus three native cells ran, but the tandem cell never unmuted.
    assert radio.tx_gain_log.count(options.tx2_gain_db) == 4
    assert radio.tx_mutes_inside_buffer == [True] * 5


def test_campaign_rejects_tx_gain_readback_that_differs_from_plan(
    tmp_path: Path,
) -> None:
    options = _campaign_options(tmp_path)
    radio = _FakeCampaignRadio(options, tx_gain_readback_offset_db=0.25)
    with pytest.raises(FixtureSafetyError, match="readback differs from the planned"):
        run_modulated_hardware_campaign(radio, options)
    assert radio.tx_gain_log[0] == options.tx2_gain_db
    assert radio.tx_mutes_inside_buffer == [True]


def test_planted_clipping_returns_fail_report_not_false_green(tmp_path: Path) -> None:
    options = _campaign_options(tmp_path)
    radio = _FakeCampaignRadio(options, clip=("desired_only", MODE_NATIVE_FAST))
    report, _path = run_modulated_hardware_campaign(radio, options)
    assert report["verdict"] == "fail"
    assert any(
        "absolute quality failed" in reason
        and MODE_NATIVE_FAST in reason
        and "clipping" in reason
        for reason in report["evaluation"]["failure_reasons"]
    )
    assert radio.mute_count >= 2


def test_invalid_manual_reference_fails_closed_before_adaptive_tx(
    tmp_path: Path,
) -> None:
    options = _campaign_options(tmp_path)
    radio = _FakeCampaignRadio(options, clip=("desired_only", MODE_MANUAL))

    with pytest.raises(
        EvidenceInvalid, match="desired-only manual reference preflight failed"
    ):
        run_modulated_hardware_campaign(radio, options)

    # The manual cell muted TX2 before returning its invalid result.  No native
    # AGC, tandem, or blocker cell was subsequently allowed to energize TX2.
    assert radio.tx_gain_log.count(options.tx2_gain_db) == 1
    assert radio.tx_mutes_inside_buffer == [True]
    assert radio.waveform_entries == 1

    report_path = (
        options.output_dir / radio.options.serial / "modulated-hardware-report.json"
    )
    durable = json.loads(report_path.read_text(encoding="utf-8"))
    assert durable["verdict"] == "invalid"
    assert "desired-only manual reference preflight failed" in durable["error"]
    assert [(run["case_id"], run["mode"]) for run in durable["runs"]] == [
        ("desired_only", MODE_MANUAL)
    ]
    manual = durable["runs"][0]
    assert manual["summary"]["quality_valid"] is False

    provenance = manual["measurements"][0]["raw_iq_provenance"]
    artifact = options.output_dir / provenance["path"]
    payload = artifact.read_bytes()
    assert provenance["bytes"] == len(payload) == options.capture_samples * 8
    assert provenance["sha256"] == hashlib.sha256(payload).hexdigest()

    dma_cleanup = durable["waveforms"][0]["dma_cleanup"]
    assert dma_cleanup["buffer_closed"] is True
    assert dma_cleanup["failures"] == []
    assert durable["final_mute"]["verified"] is True


def test_planted_blocker_degradation_fails_relative_gate(tmp_path: Path) -> None:
    quality = ModulatedQualityThresholds(
        max_evm_percent=80.0,
        min_mer_db=0.0,
        max_ser=1.0,
        max_ber=1.0,
        max_clipping_fraction=0.0,
        min_cross_channel_coherence=0.0,
        max_timing_disagreement_samples=0,
        max_abs_cfo_hz=5_000.0,
    )
    degradation = ModulatedDegradationThresholds(
        max_evm_increase_percentage_points=1.0,
        max_mer_loss_db=1.0,
        max_ser_increase=1.0,
        max_ber_increase=1.0,
        max_desired_gain_loss_db=20.0,
    )
    options = replace(
        _campaign_options(tmp_path),
        quality_thresholds=quality,
        degradation_thresholds=degradation,
    )
    radio = _FakeCampaignRadio(options, noisy=("blocker_00", MODE_NATIVE_FAST, 35.0))
    report, _path = run_modulated_hardware_campaign(radio, options)
    assert report["verdict"] == "fail"
    row = next(
        item
        for item in report["evaluation"]["degradation"]
        if item["mode"] == MODE_NATIVE_FAST
    )
    assert not row["valid"]
    assert "evm_degradation" in row["failure_reasons"]


def test_serial_lifecycle_closes_after_invalid_tandem_evidence(tmp_path: Path) -> None:
    options = _campaign_options(tmp_path)
    radio = _FakeCampaignRadio(options, unpaired_tandem=True)
    with pytest.raises(EvidenceInvalid, match="not paired"):
        run_serial_modulated_hardware_campaign(
            object(), object(), options, radio_factory=lambda _iio, _options: radio
        )
    assert radio.close_count == 1
    assert radio.mute_count >= 2
    report_path = tmp_path / "fake-usb-radio" / "modulated-hardware-report.json"
    assert report_path.exists()
    durable = json.loads(report_path.read_text(encoding="utf-8"))
    assert durable["verdict"] == "invalid"
    # The planted mode failure happens inside the cyclic TX scope.  Its report
    # must still retain the barrier evidence produced during context unwind.
    dma_cleanup = durable["waveforms"][0]["dma_cleanup"]
    assert dma_cleanup["buffer_closed"] is True
    assert dma_cleanup["failures"] == []


def test_serial_lifecycle_closes_and_reports_final_mute_failure(tmp_path: Path) -> None:
    options = _campaign_options(tmp_path)
    radio = _FakeCampaignRadio(options, fail_mute_call=2)
    with pytest.raises(FixtureSafetyError, match="final modulated campaign mute"):
        run_serial_modulated_hardware_campaign(
            object(), object(), options, radio_factory=lambda _iio, _options: radio
        )
    assert radio.close_count == 1
    report_path = tmp_path / "fake-usb-radio" / "modulated-hardware-report.json"
    report_text = report_path.read_text(encoding="utf-8")
    assert '"verdict": "invalid"' in report_text
    assert "planted final mute failure" in report_text


def test_serial_wrapper_returns_durable_post_close_cleanup(tmp_path: Path) -> None:
    options = _campaign_options(tmp_path)
    radio = _FakeCampaignRadio(options)
    report, report_path = run_serial_modulated_hardware_campaign(
        object(), object(), options, radio_factory=lambda _iio, _options: radio
    )
    assert radio.close_count == 1
    assert radio.cleanup_verified
    assert report["cleanup"]["verified"]
    assert report == json.loads(report_path.read_text(encoding="utf-8"))


def test_serial_wrapper_rejects_unverified_durable_cleanup(tmp_path: Path) -> None:
    options = _campaign_options(tmp_path)
    radio = _FakeCampaignRadio(options, cleanup_verified_on_close=False)
    with pytest.raises(FixtureSafetyError, match="did not verify"):
        run_serial_modulated_hardware_campaign(
            object(), object(), options, radio_factory=lambda _iio, _options: radio
        )
    assert radio.close_count == 1


def test_serial_wrapper_rejects_verified_cleanup_with_failures(tmp_path: Path) -> None:
    options = _campaign_options(tmp_path)
    radio = _FakeCampaignRadio(
        options, cleanup_failures=("planted durable cleanup failure",)
    )
    with pytest.raises(FixtureSafetyError, match="contains failures"):
        run_serial_modulated_hardware_campaign(
            object(), object(), options, radio_factory=lambda _iio, _options: radio
        )
    assert radio.close_count == 1


@pytest.mark.parametrize(
    "options",
    [
        ModulatedHardwareOptions(physical_attenuation_db=0.0, tx2_gain_db=-29.0),
        ModulatedHardwareOptions(physical_attenuation_db=0.0, capture_samples=4_097),
        ModulatedHardwareOptions(
            physical_attenuation_db=0.0,
            blocker_points=(
                BlockerPoint(320_000.0, -20.0, 47),
                BlockerPoint(320_000.0, -20.0, 48),
            ),
        ),
    ],
)
def test_invalid_or_unsafe_campaigns_fail_before_radio_io(
    options: ModulatedHardwareOptions,
) -> None:
    with pytest.raises(ValueError):
        validate_modulated_hardware_options(options)


def test_serial_wrapper_validates_before_constructing_radio(tmp_path: Path) -> None:
    constructed = False

    def factory(_iio: Any, _options: Any) -> Any:
        nonlocal constructed
        constructed = True
        raise AssertionError("unsafe options opened a radio")

    options = replace(_campaign_options(tmp_path), tx2_gain_db=-29.0)
    with pytest.raises(ValueError, match="at least 30 dB"):
        run_serial_modulated_hardware_campaign(
            object(), object(), options, radio_factory=factory
        )
    assert not constructed
