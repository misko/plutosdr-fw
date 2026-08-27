"""Offline goldens for the tandem request and metadata-v5 wire contract."""

from __future__ import annotations

import struct
import zlib

import pytest

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
    TANDEM_REQUEST,
    TANDEM_REQUEST_MAGIC,
    TANDEM_TEMPERATURE_INVALID,
    TANDEM_V5_EXTENSION,
    V5_PREFIX_BYTES,
    MetadataProtocolError,
    TandemEventDirection,
    TandemEventReason,
    TandemGainTable,
    TandemMode,
    TandemState,
    build_hold_request,
    build_tandem_request,
    maximum_tandem_events_per_frame,
    parse_tandem_frame_metadata,
)

FRAME_START = 1_000
FRAME_SAMPLES = 256
OBSERVATION_CAPACITY = 1
EVENT_CAPACITY = 3
EVENT_OFFSET = V5_PREFIX_BYTES + OBSERVATION_CAPACITY * GAIN_OBSERVATION_BYTES


def _crc(payload: bytearray) -> bytes:
    struct.pack_into("<I", payload, len(payload) - 4, 0)
    struct.pack_into("<I", payload, len(payload) - 4, zlib.crc32(payload) & 0xFFFFFFFF)
    return bytes(payload)


def _tandem_payload(*, temperature_mdeg_c: int = 41_250) -> bytes:
    header_bytes = (
        V5_PREFIX_BYTES
        + OBSERVATION_CAPACITY * GAIN_OBSERVATION_BYTES
        + EVENT_CAPACITY * GAIN_EVENT_BYTES
        + 4
    )
    payload = bytearray(header_bytes)
    features = (
        FEATURE_FPGA_GAIN_EVENTS
        | FEATURE_HARDWARE_SAMPLE_COUNTER
        | FEATURE_TANDEM_METADATA
        | FEATURE_AD9361_TEMPERATURE
    )
    flags = (
        FLAG_SAMPLE_SEQUENCE_VALID
        | FLAG_HARDWARE_SAMPLE_COUNTER_VALID
        | FLAG_TANDEM_METADATA_VALID
    )
    struct.pack_into(
        "<IHHIIQQQIIIHB",
        payload,
        0,
        METADATA_MAGIC,
        5,
        header_bytes,
        features,
        flags,
        7,
        11,
        FRAME_START,
        FRAME_SAMPLES,
        FRAME_SAMPLES * 8,
        0x0F,
        1,
        2,
    )
    struct.pack_into(
        "<HHHHHHII",
        payload,
        96,
        0,
        OBSERVATION_CAPACITY,
        GAIN_OBSERVATION_BYTES,
        2,
        EVENT_CAPACITY,
        GAIN_EVENT_BYTES,
        0,
        0,
    )
    TANDEM_V5_EXTENSION.pack_into(
        payload,
        124,
        9,
        int(TandemState.ARMED_AUTO),
        0,
        23,
        int(TandemGainTable.MHZ_200_1300),
        0x1234,
        0,
        62,
        30,
        1,
        70,
        40,
        40,
        temperature_mdeg_c,
        0,
        0,
        0,
    )
    TANDEM_GAIN_EVENT.pack_into(
        payload,
        EVENT_OFFSET,
        FRAME_START + 50,
        17,
        (int(TandemEventDirection.INCREASE) << 4)
        | int(TandemEventReason.BOTH_LOW_POWER),
        41,
        41,
    )
    TANDEM_GAIN_EVENT.pack_into(
        payload,
        EVENT_OFFSET + GAIN_EVENT_BYTES,
        FRAME_START + 100,
        18,
        (int(TandemEventDirection.DECREASE) << 4)
        | int(TandemEventReason.LARGE_ADC_OVERLOAD),
        40,
        40,
    )
    return _crc(payload)


def test_general_request_builder_preserves_the_hold_wire_golden() -> None:
    legacy = build_hold_request(
        observation_capacity=12,
        event_capacity=13,
        gain_db=27,
    )
    generalized = build_tandem_request(
        mode=TandemMode.HOLD,
        observation_capacity=12,
        event_capacity=13,
        initial_gain_db=27,
    )

    assert legacy == generalized
    values = TANDEM_REQUEST.unpack(legacy)
    assert len(legacy) == 104
    assert values[:5] == (TANDEM_REQUEST_MAGIC, 1, 104, 0x7, 0)
    assert set(legacy[72:]) == {0}


def test_auto_request_is_capacity_bounded_and_exact() -> None:
    assert (
        maximum_tandem_events_per_frame(
            mode=TandemMode.AUTO,
            samples_per_channel=65_536,
            power_measurement_samples=1_024,
            cooldown_periods=16,
        )
        == 4
    )
    request = build_tandem_request(
        mode=TandemMode.AUTO,
        event_capacity=4,
        initial_gain_db=30,
        cooldown_periods=16,
        samples_per_channel=65_536,
    )
    values = TANDEM_REQUEST.unpack(request)
    assert values[4] == int(TandemMode.AUTO)
    assert values[6] == 4
    assert values[7:10] == (0, 62, 30)
    assert values[10:13] == (1_024, 3, 16)

    with pytest.raises(ValueError, match="cannot cover 4"):
        build_tandem_request(
            mode=TandemMode.AUTO,
            event_capacity=3,
            cooldown_periods=16,
            samples_per_channel=65_536,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mode": 9},
        {"mode": TandemMode.AUTO, "minimum_gain_db": 31, "initial_gain_db": 30},
        {"mode": TandemMode.AUTO, "pulse_high_cycles": 3},
        {"mode": TandemMode.AUTO, "large_adc_overload_threshold": 256},
    ],
)
def test_request_builder_rejects_values_the_kernel_cannot_accept(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        build_tandem_request(**kwargs)


def test_tandem_v5_parser_returns_strict_provenance_and_events() -> None:
    metadata = parse_tandem_frame_metadata(_tandem_payload())

    assert metadata.first_sample_sequence == FRAME_START
    assert metadata.tandem_state is TandemState.ARMED_AUTO
    assert metadata.ownership_epoch == 9
    assert metadata.gain_table_id is TandemGainTable.MHZ_200_1300
    assert metadata.bench_gain_indices == (40, 40)
    assert metadata.ad9361_temperature_mdeg_c == 41_250
    assert len(metadata.gain_events) == 2
    assert metadata.gain_events[0].direction is TandemEventDirection.INCREASE
    assert metadata.gain_events[0].reason is TandemEventReason.BOTH_LOW_POWER
    assert metadata.gain_events[1].direction is TandemEventDirection.DECREASE
    assert metadata.gain_events[1].reason is TandemEventReason.LARGE_ADC_OVERLOAD

    invalid_temperature = parse_tandem_frame_metadata(
        _tandem_payload(temperature_mdeg_c=TANDEM_TEMPERATURE_INVALID)
    )
    assert invalid_temperature.ad9361_temperature_mdeg_c is None


def test_tandem_v5_parser_rejects_bad_crc_and_missing_contract_bits() -> None:
    corrupt = bytearray(_tandem_payload())
    corrupt[40] ^= 1
    with pytest.raises(MetadataProtocolError, match="CRC"):
        parse_tandem_frame_metadata(bytes(corrupt))

    missing_feature = bytearray(_tandem_payload())
    features = struct.unpack_from("<I", missing_feature, 8)[0]
    struct.pack_into("<I", missing_feature, 8, features & ~FEATURE_TANDEM_METADATA)
    with pytest.raises(MetadataProtocolError, match="features"):
        parse_tandem_frame_metadata(_crc(missing_feature))

    missing_flag = bytearray(_tandem_payload())
    flags = struct.unpack_from("<I", missing_flag, 12)[0]
    struct.pack_into("<I", missing_flag, 12, flags & ~FLAG_TANDEM_METADATA_VALID)
    with pytest.raises(MetadataProtocolError, match="provenance valid"):
        parse_tandem_frame_metadata(_crc(missing_flag))


@pytest.mark.parametrize(
    ("offset", "fmt", "value", "match"),
    [
        (124, "<I", 0, "ownership epoch"),
        (128, "<I", int(TandemState.IDLE), "not armed"),
        (132, "<I", 1, "fault flags"),
        (140, "<I", 99, "state or gain table"),
        (148, "<i", 31, "gain-dB provenance"),
        (160, "<B", 71, "gain-index provenance"),
        (163, "<B", 41, "endpoint gains"),
        (168, "<I", 1, "reserved fields"),
    ],
)
def test_tandem_v5_parser_rejects_invalid_session_provenance(
    offset: int, fmt: str, value: int, match: str
) -> None:
    payload = bytearray(_tandem_payload())
    struct.pack_into(fmt, payload, offset, value)
    with pytest.raises(MetadataProtocolError, match=match):
        parse_tandem_frame_metadata(_crc(payload))


@pytest.mark.parametrize(
    ("relative_offset", "fmt", "value", "match"),
    [
        (15, "<B", 42, "torn gain pair"),
        (12, "<H", 0x40, "unknown flag"),
        (12, "<H", 0x03, "invalid direction"),
        (12, "<H", 0x17, "invalid direction or reason"),
        (0, "<Q", FRAME_START + FRAME_SAMPLES, "outside its IQ frame"),
        (GAIN_EVENT_BYTES + 8, "<I", 99, "sequence has a hole"),
        (GAIN_EVENT_BYTES, "<Q", FRAME_START + 1, "not sample ordered"),
        (2 * GAIN_EVENT_BYTES, "<B", 1, "unused tandem"),
    ],
)
def test_tandem_v5_parser_rejects_malformed_or_stale_events(
    relative_offset: int, fmt: str, value: int, match: str
) -> None:
    payload = bytearray(_tandem_payload())
    struct.pack_into(fmt, payload, EVENT_OFFSET + relative_offset, value)
    with pytest.raises(MetadataProtocolError, match=match):
        parse_tandem_frame_metadata(_crc(payload))
