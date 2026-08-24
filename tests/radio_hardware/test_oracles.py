"""Offline goldens for issue 46; safe on public PR runners."""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

import pytest

from .continuity import (
    ContinuityError,
    ContinuityKind,
    agree_dual_rx,
    counter_transition,
    evaluate_boundary,
    pn_transition,
)
from .experiment import (
    DAC_LEGACY_CONTROL_REGISTER,
    DAC_SELECT_ZERO,
    DAC_SELECTOR_REGISTER,
    FixtureSafetyError,
    Issue46Options,
    Issue46Radio,
    _radio_lock_path,
    experiment_matrix,
)
from .metadata_abi import (
    FEATURE_HARDWARE_SAMPLE_COUNTER,
    FLAG_DEVICE_IIO_OVERFLOW,
    FLAG_HARDWARE_SAMPLE_COUNTER_VALID,
    FLAG_SAMPLE_SEQUENCE_VALID,
    GAIN_EVENT_BYTES,
    GAIN_OBSERVATION_BYTES,
    METADATA_MAGIC,
    TANDEM_REQUEST_MAGIC,
    V3_PREFIX_BYTES,
    V5_PREFIX_BYTES,
    FrameMetadata,
    MetadataProtocolError,
    build_hold_request,
    metadata_buffer_abi,
    parse_frame_metadata,
)
from .pnxx import (
    P15_SAMPLE_PERIOD,
    P15_TAPS,
    P15_UPDATE_PERIOD,
    P20_TAPS,
    P20_UPDATE_PERIOD,
    PNXX_JOINT_SAMPLE_PERIOD,
    estimate_p15_phase,
    p15_period,
    pn_samples,
    pn_step,
    verify_rtl_contract,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class _FakeAttr:
    def __init__(self, value: float, *, fail_write: bool = False):
        self._value = str(value)
        self.fail_write = fail_write
        self.write_attempts = 0

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, value: str) -> None:
        self.write_attempts += 1
        if self.fail_write:
            raise OSError("planted attribute write failure")
        self._value = str(value)


class _FakeChannel:
    def __init__(self, **attrs: _FakeAttr):
        self.attrs = attrs


class _FakePhy:
    id = "ad9361-phy"

    def __init__(self, *, fail_tx1: bool = False):
        self.channels = {
            "voltage0": _FakeChannel(hardwaregain=_FakeAttr(0.0, fail_write=fail_tx1)),
            "voltage1": _FakeChannel(hardwaregain=_FakeAttr(0.0)),
        }

    def find_channel(self, name: str, output: bool) -> _FakeChannel | None:
        assert output
        return self.channels.get(name)


class _FakeTx:
    id = "cf-ad9361-dds-core-lpc"

    def __init__(self, *, fail_dds0: bool = False, fail_selector0: bool = False):
        self.channels = {
            f"altvoltage{index}": _FakeChannel(
                scale=_FakeAttr(1.0, fail_write=fail_dds0 and index == 0),
                raw=_FakeAttr(1.0),
            )
            for index in range(8)
        }
        self.registers = {
            **{DAC_LEGACY_CONTROL_REGISTER(index): 1 for index in range(4)},
            **{DAC_SELECTOR_REGISTER(index): 9 for index in range(4)},
        }
        self.fail_selector0 = fail_selector0
        self.selector_write_attempts = [0] * 4

    def find_channel(self, name: str, output: bool) -> _FakeChannel | None:
        assert output
        return self.channels.get(name)

    def reg_read(self, address: int) -> int:
        return self.registers[address]

    def reg_write(self, address: int, value: int) -> None:
        for index in range(4):
            if address == DAC_SELECTOR_REGISTER(index):
                self.selector_write_attempts[index] += 1
                if self.fail_selector0 and index == 0:
                    raise OSError("planted selector write failure")
        self.registers[address] = value


class _FakeClosable:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _fake_radio(
    *,
    fail_tx1: bool = False,
    fail_dds0: bool = False,
    fail_selector0: bool = False,
) -> Issue46Radio:
    radio = Issue46Radio.__new__(Issue46Radio)
    radio.phy = _FakePhy(fail_tx1=fail_tx1)
    radio.tx = _FakeTx(fail_dds0=fail_dds0, fail_selector0=fail_selector0)
    radio._last_mute_evidence = None
    return radio


def test_all_suites_share_one_canonical_serial_lock() -> None:
    assert _radio_lock_path("same/serial") == Path(
        "/tmp/plutosdr-fw-radio-same_serial.lock"
    )


def test_best_effort_mute_verifies_every_independent_path() -> None:
    radio = _fake_radio()
    evidence, failures = radio._best_effort_mute()
    assert failures == []
    assert evidence["verified"]
    assert evidence["tx1_gain_db"] == pytest.approx(-89.75)
    assert evidence["tx2_gain_db"] == pytest.approx(-89.75)
    assert evidence["selectors"] == [DAC_SELECT_ZERO] * 4
    assert all(
        item["scale"] == 0.0 and item["raw"] == 0.0 for item in evidence["dds"].values()
    )


def test_best_effort_mute_continues_after_independent_failures() -> None:
    radio = _fake_radio(fail_tx1=True, fail_dds0=True, fail_selector0=True)
    with pytest.raises(FixtureSafetyError) as caught:
        radio._mute_everything()
    assert "TX1 gain mute" in str(caught.value)
    assert "DDS altvoltage0 scale mute" in str(caught.value)
    assert "selector 0 mute" in str(caught.value)
    assert radio.phy.channels["voltage1"].attrs["hardwaregain"].write_attempts == 1
    assert radio.tx.channels["altvoltage7"].attrs["scale"].write_attempts == 1
    assert radio.tx.channels["altvoltage7"].attrs["raw"].write_attempts == 1
    assert radio.tx.selector_write_attempts == [1, 1, 1, 1]
    assert radio._last_mute_evidence is not None
    assert not radio._last_mute_evidence["verified"]


def test_close_releases_context_and_lock_after_mute_failure() -> None:
    radio = _fake_radio(fail_tx1=True)
    context = _FakeClosable()
    lock = _FakeClosable()
    radio.context = context
    radio.rx = object()
    radio._lock = lock
    radio._report_path = None
    radio.cleanup_verified = False
    with pytest.raises(FixtureSafetyError, match="TX1 gain mute"):
        radio.close()
    assert context.closed
    assert lock.closed
    assert radio.context is None
    assert radio.phy is None
    assert radio.tx is None
    assert not radio.cleanup_verified


def _metadata_payload(
    *,
    version: int,
    first_sample: int = 1_000,
    samples: int = 256,
    buffer_sequence: int = 2,
    flags: int = 0,
) -> bytes:
    prefix = V5_PREFIX_BYTES if version == 5 else V3_PREFIX_BYTES
    observation_capacity = 2
    event_capacity = 1
    size = (
        prefix
        + observation_capacity * GAIN_OBSERVATION_BYTES
        + event_capacity * GAIN_EVENT_BYTES
        + 4
    )
    payload = bytearray(size)
    flags |= FLAG_SAMPLE_SEQUENCE_VALID | FLAG_HARDWARE_SAMPLE_COUNTER_VALID
    struct.pack_into(
        "<IHHIIQQQIIIHB",
        payload,
        0,
        METADATA_MAGIC,
        version,
        size,
        FEATURE_HARDWARE_SAMPLE_COUNTER,
        flags,
        7,
        buffer_sequence,
        first_sample,
        samples,
        samples * 8,
        0x0F,
        1,
        2,
    )
    struct.pack_into(
        "<HHHHHHII",
        payload,
        96,
        1,
        observation_capacity,
        GAIN_OBSERVATION_BYTES,
        0,
        event_capacity,
        GAIN_EVENT_BYTES,
        0,
        0,
    )
    struct.pack_into("<I", payload, size - 4, 0)
    struct.pack_into("<I", payload, size - 4, zlib.crc32(payload) & 0xFFFFFFFF)
    return bytes(payload)


@pytest.mark.parametrize("version", [3, 5])
def test_metadata_parser_accepts_counter_goldens(version: int) -> None:
    parsed = parse_frame_metadata(_metadata_payload(version=version))
    assert parsed.version == version
    assert parsed.first_sample_sequence == 1_000
    assert parsed.samples_per_channel == 256
    assert parsed.iq_payload_bytes == 2_048
    assert not parsed.device_iio_overflow


def test_metadata_parser_rejects_crc_and_counter_downgrade() -> None:
    corrupt = bytearray(_metadata_payload(version=3))
    corrupt[32] ^= 1
    with pytest.raises(MetadataProtocolError, match="CRC"):
        parse_frame_metadata(bytes(corrupt))

    missing_flag = bytearray(_metadata_payload(version=3))
    flags = struct.unpack_from("<I", missing_flag, 12)[0]
    struct.pack_into(
        "<I", missing_flag, 12, flags & ~FLAG_HARDWARE_SAMPLE_COUNTER_VALID
    )
    struct.pack_into("<I", missing_flag, len(missing_flag) - 4, 0)
    struct.pack_into(
        "<I", missing_flag, len(missing_flag) - 4, zlib.crc32(missing_flag) & 0xFFFFFFFF
    )
    with pytest.raises(MetadataProtocolError, match="counter valid"):
        parse_frame_metadata(bytes(missing_flag))


def test_tandem_request_has_stable_104_byte_wire_layout() -> None:
    request = build_hold_request(gain_db=20)
    assert len(request) == 104
    assert struct.unpack_from("<I", request)[0] == TANDEM_REQUEST_MAGIC
    assert struct.unpack_from("<H", request, 6)[0] == len(request)
    assert set(request[72:]) == {0}


def test_metadata_constructor_abi_detection() -> None:
    class LegacyMetadataBuffer:
        def __init__(self, device, samples_count, metadata_capacity=64 * 1024):
            pass

    class RequestMetadataBuffer:
        def __init__(self, device, samples_count, request, metadata_capacity=64 * 1024):
            pass

    assert metadata_buffer_abi(LegacyMetadataBuffer) == 1
    assert metadata_buffer_abi(RequestMetadataBuffer) == 2


def _frame(first: int, *, flags: int = 0, buffer_sequence: int = 2) -> FrameMetadata:
    return parse_frame_metadata(
        _metadata_payload(
            version=5,
            first_sample=first,
            flags=flags,
            buffer_sequence=buffer_sequence,
        )
    )


def test_planted_deletion_is_red_until_metadata_is_explicit() -> None:
    previous = _frame(1_000)
    deleted = 768
    current = _frame(1_000 + 256 + deleted, buffer_sequence=6)
    counter = counter_transition(previous, current)
    assert counter.kind is ContinuityKind.GAP
    assert counter.missing_samples == deleted

    rx0 = pn_transition(10, 10 + 256 + deleted, 256, period=P15_SAMPLE_PERIOD)
    rx1 = pn_transition(1_234, 1_234 + 256 + deleted, 256, period=P15_SAMPLE_PERIOD)
    pn = agree_dual_rx((rx0, rx1))

    result = evaluate_boundary(
        api="metadata",
        capacity_safe=False,
        pn=pn,
        counter=counter,
        overflow_flag=False,
    )
    assert result.verdict == "red"
    assert result.classification == "metadata_unflagged_gap"

    explicit_current = _frame(
        1_000 + 256 + deleted,
        flags=FLAG_DEVICE_IIO_OVERFLOW,
        buffer_sequence=6,
    )
    result = evaluate_boundary(
        api="metadata",
        capacity_safe=False,
        pn=pn,
        counter=counter_transition(previous, explicit_current),
        overflow_flag=explicit_current.device_iio_overflow,
    )
    assert result.verdict == "green"
    assert result.classification == "explicit_segmented_gap"


def test_ordinary_resumption_with_planted_deletion_is_red() -> None:
    pn = pn_transition(50, 50 + 256 + 9, 256, period=P15_SAMPLE_PERIOD)
    result = evaluate_boundary(
        api="ordinary",
        capacity_safe=False,
        pn=pn,
        counter=None,
        overflow_flag=False,
    )
    assert result.verdict == "red"
    assert result.classification == "ordinary_unrepresented_gap"


def test_counter_and_pn_disagreement_is_invalid_evidence() -> None:
    previous = _frame(1_000)
    current = _frame(1_000 + 256 + 256, buffer_sequence=4)
    pn = pn_transition(10, 10 + 256 + 512, 256, period=P15_SAMPLE_PERIOD)
    with pytest.raises(ContinuityError, match="disagree"):
        evaluate_boundary(
            api="metadata",
            capacity_safe=False,
            pn=pn,
            counter=counter_transition(previous, current),
            overflow_flag=True,
        )


def test_metadata_buffer_sequence_must_follow_the_fpga_counter() -> None:
    previous = _frame(1_000)
    current = parse_frame_metadata(
        _metadata_payload(
            version=5,
            first_sample=1_000 + 2 * 256,
            buffer_sequence=previous.buffer_sequence + 1,
        )
    )
    with pytest.raises(ContinuityError, match="buffer_sequence"):
        counter_transition(previous, current)


def test_visible_saturation_failure_is_green_but_premature_failure_is_red() -> None:
    outside = evaluate_boundary(
        api="ordinary",
        capacity_safe=False,
        pn=None,
        counter=None,
        overflow_flag=False,
        refill_error="EOVERFLOW",
    )
    inside = evaluate_boundary(
        api="ordinary",
        capacity_safe=True,
        pn=None,
        counter=None,
        overflow_flag=False,
        refill_error="EIO",
    )
    assert outside.classification == "explicit_failure"
    assert outside.verdict == "green"
    assert inside.classification == "premature_failure"
    assert inside.verdict == "red"


def test_oracle_matches_every_p15_and_p20_rtl_equation() -> None:
    verify_rtl_contract(
        REPOSITORY_ROOT / "hdl/library/axi_ad9361/axi_ad9361_tx_channel.v"
    )


def test_pn_periods_and_seeded_golden_words() -> None:
    assert pn_step(0xFFFFFF, P15_TAPS) == 0x000200
    assert pn_step(0xFFFFFF, P20_TAPS) == 0x1C71C8
    assert tuple(pn_samples(P15_TAPS, 12)) == (
        -1,
        -1,
        0,
        512,
        192,
        40,
        15,
        2,
        512,
        -832,
        680,
        255,
    )
    state = pn_step(0xFFFFFF, P15_TAPS)
    initial_state = state
    for _ in range(P15_UPDATE_PERIOD):
        state = pn_step(state, P15_TAPS)
    assert state == initial_state
    state = pn_step(0xFFFFFF, P20_TAPS)
    initial_state = state
    for _ in range(P20_UPDATE_PERIOD):
        state = pn_step(state, P20_TAPS)
    assert state == initial_state
    assert (
        math.lcm(P15_UPDATE_PERIOD * 2, P20_UPDATE_PERIOD * 2)
        == PNXX_JOINT_SAMPLE_PERIOD
    )


def test_fft_phase_oracle_finds_a_planted_p15_phase() -> None:
    np = pytest.importorskip("numpy")
    phase = 12_345
    count = 4_096
    reference = np.asarray(p15_period(), dtype=np.float64)
    indexes = (phase + np.arange(count)) % P15_SAMPLE_PERIOD
    rng = np.random.default_rng(46)
    source = reference[indexes] + 1j * rng.normal(0.0, 900.0, count)
    rx0 = source * (0.7 + 0.2j)
    rx1 = source * (-0.3 + 0.8j)
    words = np.empty((count, 4), dtype="<i2")
    words[:, 0] = np.rint(rx0.real).astype("<i2")
    words[:, 1] = np.rint(rx0.imag).astype("<i2")
    words[:, 2] = np.rint(rx1.real).astype("<i2")
    words[:, 3] = np.rint(rx1.imag).astype("<i2")

    first = estimate_p15_phase(words.tobytes(), rx_channel=0)
    second = estimate_p15_phase(words.tobytes(), rx_channel=1)
    assert first.phase == phase
    assert second.phase == phase
    assert first.coherence > 0.1
    assert second.coherence > 0.1


def test_repro_matrix_is_the_pinned_randomized_ab_design(tmp_path: Path) -> None:
    options = Issue46Options(
        serial="serial",
        uri=None,
        allow_non_usb=False,
        firmware_pattern="rc2",
        libiio_source_commit="0" * 40,
        attenuation_db=30.0,
        tx_gain_db=-20.0,
        sample_rate_hz=2_500_000,
        samples_per_channel=262_144,
        profile="repro",
        sink="ram",
        expected="green",
        output_dir=tmp_path,
        max_seconds=600.0,
        save_iq=False,
        pn_min_coherence=0.03,
        pn_min_peak_ratio=1.5,
    )
    matrix = experiment_matrix(options)
    assert len(matrix) == 2 * 3 * 7 * 5
    assert {item.api for item in matrix} == {"ordinary", "metadata"}
    assert {item.kernel_buffers for item in matrix} == {1, 2, 4}
    assert {item.pause_factor for item in matrix} == {
        0.0,
        0.5,
        1.0,
        2.0,
        4.0,
        8.0,
        16.0,
    }
    assert options.refill_period_seconds == pytest.approx(0.1048576)
    assert matrix == experiment_matrix(options)
