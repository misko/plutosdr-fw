"""Small, self-contained adapters for the two issue-46 metadata ABIs.

The v0.38 metadata-v5 firmware returns radio metadata v3 and uses the original
``MetadataBuffer(device, samples, capacity)`` constructor.  Tandem RC2 returns
metadata v5 and requires a 104-byte session request.  Nothing in this module
imports SPF; the wire contract is intentionally checked here at the firmware
boundary.
"""

from __future__ import annotations

import enum
import inspect
import struct
import zlib
from dataclasses import dataclass
from typing import Any, Optional

METADATA_MAGIC = 0x314D4753
VERSION_V3 = 3
VERSION_V5 = 5

FEATURE_HARDWARE_SAMPLE_COUNTER = 1 << 7
FEATURE_FPGA_GAIN_EVENTS = 1 << 3
FEATURE_TANDEM_METADATA = 1 << 8
FEATURE_AD9361_TEMPERATURE = 1 << 9
FLAG_SAMPLE_SEQUENCE_VALID = 1 << 4
FLAG_DEVICE_IIO_OVERFLOW = 1 << 11
FLAG_GAIN_READ_FAILED = 1 << 12
FLAG_FPGA_EVENT_OVERFLOW = 1 << 13
FLAG_DUMMY_GAINS = 1 << 14
FLAG_RSSI_READ_FAILED = 1 << 17
FLAG_GAIN_OBSERVATION_OVERFLOW = 1 << 20
FLAG_HARDWARE_SAMPLE_COUNTER_VALID = 1 << 21
FLAG_TANDEM_METADATA_VALID = 1 << 22
TANDEM_UNSAFE_FLAGS = (
    FLAG_DEVICE_IIO_OVERFLOW
    | FLAG_GAIN_READ_FAILED
    | FLAG_FPGA_EVENT_OVERFLOW
    | FLAG_DUMMY_GAINS
    | FLAG_RSSI_READ_FAILED
    | FLAG_GAIN_OBSERVATION_OVERFLOW
)

V3_PREFIX_BYTES = 124
V5_EXTENSION_BYTES = 56
V5_PREFIX_BYTES = V3_PREFIX_BYTES + V5_EXTENSION_BYTES
GAIN_OBSERVATION_BYTES = 32
GAIN_EVENT_BYTES = 16

TANDEM_REQUEST_MAGIC = 0x54465053
TANDEM_ABI_VERSION = 1
TANDEM_REQUIRED_FEATURES = 0x7
TANDEM_POLICY_FAIL_SESSION = 0
TANDEM_REQUEST = struct.Struct("<IHHIIIIiiiIIIIII4BII8I")
TANDEM_V5_EXTENSION = struct.Struct("<IIIIIIiiiBBBBi3I")
TANDEM_GAIN_EVENT = struct.Struct("<QIHBB")
assert TANDEM_REQUEST.size == 104
assert TANDEM_V5_EXTENSION.size == V5_EXTENSION_BYTES
assert TANDEM_GAIN_EVENT.size == GAIN_EVENT_BYTES

TANDEM_TEMPERATURE_INVALID = -(1 << 31)


class TandemMode(enum.IntEnum):
    HOLD = 0
    AUTO = 1


class TandemState(enum.IntEnum):
    IDLE = 0
    VALIDATING = 1
    ARMED_HOLD = 2
    ARMED_AUTO = 3
    FAULTED = 4
    RESTORING = 5


class TandemGainTable(enum.IntEnum):
    MHZ_200_1300 = 1
    MHZ_1300_4000 = 2
    MHZ_4000_6000 = 3


class TandemEventDirection(enum.IntEnum):
    INCREASE = 1
    DECREASE = 2


class TandemEventReason(enum.IntEnum):
    LARGE_LMT_OVERLOAD = 0
    LARGE_ADC_OVERLOAD = 1
    SMALL_ADC_INHIBIT = 2
    BOTH_LOW_POWER = 3
    PEER = 4
    CLAMPED = 5
    INITIAL = 6


class MetadataProtocolError(ValueError):
    """Metadata could not prove its own wire-level validity."""


@dataclass(frozen=True)
class FrameMetadata:
    version: int
    header_bytes: int
    features: int
    flags: int
    stream_id: int
    buffer_sequence: int
    first_sample_sequence: int
    samples_per_channel: int
    iq_payload_bytes: int
    enabled_scan_mask: int
    sample_format: int
    channel_count: int
    observation_count: int
    observation_capacity: int
    event_count: int
    event_capacity: int
    observation_overflow_count: int
    event_overflow_count: int

    @property
    def device_iio_overflow(self) -> bool:
        return bool(self.flags & FLAG_DEVICE_IIO_OVERFLOW)


@dataclass(frozen=True)
class TandemGainEvent:
    sample_sequence: int
    event_sequence: int
    flags: int
    rx1_gain_index: int
    rx2_gain_index: int

    @property
    def direction(self) -> TandemEventDirection:
        return TandemEventDirection((self.flags >> 4) & 0x3)

    @property
    def reason(self) -> TandemEventReason:
        return TandemEventReason(self.flags & 0xF)


@dataclass(frozen=True)
class TandemFrameMetadata(FrameMetadata):
    ownership_epoch: int
    tandem_state: TandemState
    tandem_fault_flags: int
    tandem_transition_count: int
    gain_table_id: TandemGainTable
    threshold_provenance: int
    minimum_gain_db: int
    maximum_gain_db: int
    initial_gain_db: int
    minimum_gain_index: int
    maximum_gain_index: int
    rx1_gain_index: int
    rx2_gain_index: int
    ad9361_temperature_mdeg_c: Optional[int]
    gain_events: tuple[TandemGainEvent, ...]

    @property
    def bench_gain_indices(self) -> tuple[int, int]:
        """Return gains in the bench's RX0/RX1 naming order."""

        return self.rx1_gain_index, self.rx2_gain_index


def _unpack_from(fmt: str, payload: bytes, offset: int) -> tuple[Any, ...]:
    try:
        return struct.unpack_from(fmt, payload, offset)
    except struct.error as exc:
        raise MetadataProtocolError("metadata record is truncated") from exc


def parse_frame_metadata(payload: bytes) -> FrameMetadata:
    """Validate and decode the counter-bearing fields shared by v3 and v5."""

    payload = bytes(payload)
    if len(payload) < V3_PREFIX_BYTES + 4:
        raise MetadataProtocolError("metadata record is shorter than a v3 header")

    magic, version, header_bytes, features, flags = _unpack_from("<IHHII", payload, 0)
    if magic != METADATA_MAGIC:
        raise MetadataProtocolError(f"unexpected metadata magic 0x{magic:08x}")
    if version not in (VERSION_V3, VERSION_V5):
        raise MetadataProtocolError(f"unsupported metadata version {version}")
    if header_bytes != len(payload):
        raise MetadataProtocolError(
            f"metadata length {len(payload)} differs from header_bytes {header_bytes}"
        )

    minimum_prefix = V5_PREFIX_BYTES if version == VERSION_V5 else V3_PREFIX_BYTES
    if header_bytes < minimum_prefix + 4:
        raise MetadataProtocolError(
            "metadata header is shorter than its version prefix"
        )

    received_crc = _unpack_from("<I", payload, header_bytes - 4)[0]
    crc_input = bytearray(payload)
    struct.pack_into("<I", crc_input, header_bytes - 4, 0)
    calculated_crc = zlib.crc32(crc_input) & 0xFFFFFFFF
    if received_crc != calculated_crc:
        raise MetadataProtocolError(
            f"metadata CRC mismatch: got 0x{received_crc:08x}, "
            f"calculated 0x{calculated_crc:08x}"
        )

    required_features = FEATURE_HARDWARE_SAMPLE_COUNTER
    required_flags = FLAG_SAMPLE_SEQUENCE_VALID | FLAG_HARDWARE_SAMPLE_COUNTER_VALID
    if features & required_features != required_features:
        raise MetadataProtocolError("metadata lacks the FPGA sample-counter feature")
    if flags & required_flags != required_flags:
        raise MetadataProtocolError("metadata does not mark the FPGA counter valid")

    stream_id, buffer_sequence, first_sample_sequence = _unpack_from(
        "<QQQ", payload, 16
    )
    samples_per_channel, iq_payload_bytes, enabled_scan_mask = _unpack_from(
        "<III", payload, 40
    )
    sample_format, channel_count = _unpack_from("<HB", payload, 52)
    (
        observation_count,
        observation_capacity,
        observation_bytes,
        event_count,
        event_capacity,
        event_bytes,
    ) = _unpack_from("<HHHHHH", payload, 96)
    observation_overflow_count, event_overflow_count = _unpack_from("<II", payload, 108)

    if observation_count > observation_capacity:
        raise MetadataProtocolError("observation count exceeds its capacity")
    if event_count > event_capacity:
        raise MetadataProtocolError("event count exceeds its capacity")
    if observation_bytes != GAIN_OBSERVATION_BYTES:
        raise MetadataProtocolError("unexpected gain-observation record size")
    if event_bytes != GAIN_EVENT_BYTES:
        raise MetadataProtocolError("unexpected gain-event record size")

    expected_bytes = (
        minimum_prefix
        + observation_capacity * GAIN_OBSERVATION_BYTES
        + event_capacity * GAIN_EVENT_BYTES
        + 4
    )
    if header_bytes != expected_bytes:
        raise MetadataProtocolError(
            f"metadata capacity layout requires {expected_bytes} bytes, "
            f"not {header_bytes}"
        )
    if not stream_id:
        raise MetadataProtocolError("metadata stream_id must be nonzero")
    if not samples_per_channel:
        raise MetadataProtocolError("metadata sample count must be nonzero")

    return FrameMetadata(
        version=version,
        header_bytes=header_bytes,
        features=features,
        flags=flags,
        stream_id=stream_id,
        buffer_sequence=buffer_sequence,
        first_sample_sequence=first_sample_sequence,
        samples_per_channel=samples_per_channel,
        iq_payload_bytes=iq_payload_bytes,
        enabled_scan_mask=enabled_scan_mask,
        sample_format=sample_format,
        channel_count=channel_count,
        observation_count=observation_count,
        observation_capacity=observation_capacity,
        event_count=event_count,
        event_capacity=event_capacity,
        observation_overflow_count=observation_overflow_count,
        event_overflow_count=event_overflow_count,
    )


def _parse_tandem_gain_event(
    payload: bytes,
    *,
    frame_start: int,
    frame_end: int,
    minimum_gain_index: int,
    maximum_gain_index: int,
) -> TandemGainEvent:
    if len(payload) != TANDEM_GAIN_EVENT.size:
        raise MetadataProtocolError("tandem gain-event record has the wrong size")
    event = TandemGainEvent(*TANDEM_GAIN_EVENT.unpack(payload))
    if event.flags & 0xFFC0:
        raise MetadataProtocolError("tandem gain event has unknown flag bits")
    try:
        _ = event.direction
        _ = event.reason
    except ValueError as exc:
        raise MetadataProtocolError(
            "tandem gain event has an invalid direction or reason"
        ) from exc
    if event.rx1_gain_index != event.rx2_gain_index:
        raise MetadataProtocolError("tandem gain event contains a torn gain pair")
    if not minimum_gain_index <= event.rx1_gain_index <= maximum_gain_index:
        raise MetadataProtocolError(
            "tandem gain event is outside the session gain range"
        )
    if not frame_start <= event.sample_sequence < frame_end:
        raise MetadataProtocolError("tandem gain event lies outside its IQ frame")
    return event


def parse_tandem_frame_metadata(payload: bytes) -> TandemFrameMetadata:
    """Strictly validate tandem metadata v5 and its frame-associated events."""

    payload = bytes(payload)
    base = parse_frame_metadata(payload)
    if base.version != VERSION_V5:
        raise MetadataProtocolError("tandem metadata requires protocol version 5")
    required_features = (
        FEATURE_FPGA_GAIN_EVENTS
        | FEATURE_HARDWARE_SAMPLE_COUNTER
        | FEATURE_TANDEM_METADATA
        | FEATURE_AD9361_TEMPERATURE
    )
    if base.features & required_features != required_features:
        raise MetadataProtocolError("metadata lacks required tandem-v5 features")
    if not base.flags & FLAG_TANDEM_METADATA_VALID:
        raise MetadataProtocolError("metadata does not mark tandem provenance valid")

    try:
        extension = TANDEM_V5_EXTENSION.unpack_from(payload, V3_PREFIX_BYTES)
    except struct.error as exc:
        raise MetadataProtocolError("tandem-v5 extension is truncated") from exc
    if any(extension[-3:]):
        raise MetadataProtocolError("tandem-v5 reserved fields must be zero")
    (
        ownership_epoch,
        state,
        fault_flags,
        transition_count,
        gain_table_id,
        threshold_provenance,
        minimum_gain_db,
        maximum_gain_db,
        initial_gain_db,
        minimum_gain_index,
        maximum_gain_index,
        rx1_gain_index,
        rx2_gain_index,
        temperature_mdeg_c,
        *_reserved,
    ) = extension

    if not ownership_epoch:
        raise MetadataProtocolError("tandem ownership epoch must be nonzero")
    if fault_flags:
        raise MetadataProtocolError(
            f"tandem metadata reports fault flags 0x{fault_flags:08x}"
        )
    try:
        parsed_state = TandemState(state)
        parsed_gain_table = TandemGainTable(gain_table_id)
    except ValueError as exc:
        raise MetadataProtocolError("tandem state or gain table is unknown") from exc
    if parsed_state not in (TandemState.ARMED_HOLD, TandemState.ARMED_AUTO):
        raise MetadataProtocolError("tandem lease is not armed")
    if not 0 <= minimum_gain_db <= initial_gain_db <= maximum_gain_db <= 62:
        raise MetadataProtocolError("tandem gain-dB provenance is invalid")
    if not minimum_gain_index <= maximum_gain_index <= 0x7F:
        raise MetadataProtocolError("tandem gain-index provenance is invalid")
    if rx1_gain_index != rx2_gain_index:
        raise MetadataProtocolError("tandem endpoint gains are not paired")
    if not minimum_gain_index <= rx1_gain_index <= maximum_gain_index:
        raise MetadataProtocolError("tandem endpoint gain is outside the session range")

    arrays_offset = V5_PREFIX_BYTES
    event_offset = arrays_offset + base.observation_capacity * GAIN_OBSERVATION_BYTES
    events: list[TandemGainEvent] = []
    frame_end = base.first_sample_sequence + base.samples_per_channel
    for index in range(base.event_count):
        offset = event_offset + index * GAIN_EVENT_BYTES
        event = _parse_tandem_gain_event(
            payload[offset : offset + GAIN_EVENT_BYTES],
            frame_start=base.first_sample_sequence,
            frame_end=frame_end,
            minimum_gain_index=minimum_gain_index,
            maximum_gain_index=maximum_gain_index,
        )
        if events:
            expected_sequence = (events[-1].event_sequence + 1) & 0xFFFFFFFF
            if event.event_sequence != expected_sequence:
                raise MetadataProtocolError("tandem gain-event sequence has a hole")
            if event.sample_sequence < events[-1].sample_sequence:
                raise MetadataProtocolError("tandem gain events are not sample ordered")
        events.append(event)
    unused_start = event_offset + base.event_count * GAIN_EVENT_BYTES
    unused_end = event_offset + base.event_capacity * GAIN_EVENT_BYTES
    if any(payload[unused_start:unused_end]):
        raise MetadataProtocolError("unused tandem gain-event records must be zero")

    return TandemFrameMetadata(
        **vars(base),
        ownership_epoch=ownership_epoch,
        tandem_state=parsed_state,
        tandem_fault_flags=fault_flags,
        tandem_transition_count=transition_count,
        gain_table_id=parsed_gain_table,
        threshold_provenance=threshold_provenance,
        minimum_gain_db=minimum_gain_db,
        maximum_gain_db=maximum_gain_db,
        initial_gain_db=initial_gain_db,
        minimum_gain_index=minimum_gain_index,
        maximum_gain_index=maximum_gain_index,
        rx1_gain_index=rx1_gain_index,
        rx2_gain_index=rx2_gain_index,
        ad9361_temperature_mdeg_c=(
            None
            if temperature_mdeg_c == TANDEM_TEMPERATURE_INVALID
            else temperature_mdeg_c
        ),
        gain_events=tuple(events),
    )


def maximum_tandem_events_per_frame(
    *,
    mode: TandemMode | int,
    samples_per_channel: int,
    power_measurement_samples: int,
    cooldown_periods: int,
) -> int:
    """Return the conservative number of AUTO transitions one frame can hold."""

    try:
        parsed_mode = TandemMode(mode)
    except ValueError as exc:
        raise ValueError(f"unknown tandem mode {mode!r}") from exc
    if not isinstance(samples_per_channel, int) or samples_per_channel <= 0:
        raise ValueError("samples_per_channel must be a positive integer")
    if not isinstance(power_measurement_samples, int) or power_measurement_samples <= 0:
        raise ValueError("power_measurement_samples must be a positive integer")
    if not isinstance(cooldown_periods, int) or cooldown_periods < 0:
        raise ValueError("cooldown_periods must be a nonnegative integer")
    if parsed_mode is TandemMode.HOLD:
        return 0
    minimum_transition_samples = power_measurement_samples * (cooldown_periods + 1)
    return 1 + (samples_per_channel - 1) // minimum_transition_samples


def build_tandem_request(
    *,
    mode: TandemMode | int,
    observation_capacity: int = 64,
    event_capacity: int = 64,
    minimum_gain_db: int = 0,
    maximum_gain_db: int = 62,
    initial_gain_db: int = 20,
    power_measurement_samples: int = 1024,
    low_power_dwell_periods: int = 3,
    cooldown_periods: int = 2,
    pulse_high_cycles: int = 4,
    pulse_low_cycles: int = 4,
    detector_blanking_cycles: int = 8,
    low_power_threshold: int = 20,
    large_lmt_overload_threshold: int = 58,
    large_adc_overload_threshold: int = 49,
    small_adc_overload_threshold: int = 48,
    samples_per_channel: Optional[int] = None,
) -> bytes:
    """Build the exact fail-closed ABI-v1 HOLD or AUTO session request.

    ``samples_per_channel`` is optional because the wire request is independent
    of buffer length.  Supplying it for AUTO additionally proves that the
    requested event capacity covers the worst-case transition count.
    """

    try:
        parsed_mode = TandemMode(mode)
    except ValueError as exc:
        raise ValueError(f"unknown tandem mode {mode!r}") from exc
    if not 1 <= observation_capacity <= 64:
        raise ValueError("observation_capacity must be in [1, 64]")
    if not 1 <= event_capacity <= 64:
        raise ValueError("event_capacity must be in [1, 64]")
    if not 0 <= minimum_gain_db <= initial_gain_db <= maximum_gain_db <= 62:
        raise ValueError("tandem gains must be ordered within [0, 62] dB")
    if not 1 <= power_measurement_samples <= (1 << 20) - 1:
        raise ValueError("power_measurement_samples must be in [1, 1048575]")
    if not 1 <= low_power_dwell_periods <= 0xFF:
        raise ValueError("low_power_dwell_periods must be in [1, 255]")
    if not 0 <= cooldown_periods <= 0xFF:
        raise ValueError("cooldown_periods must be in [0, 255]")
    if not 4 <= pulse_high_cycles <= 0xFF:
        raise ValueError("pulse_high_cycles must be in [4, 255]")
    if not 4 <= pulse_low_cycles <= 0xFF:
        raise ValueError("pulse_low_cycles must be in [4, 255]")
    if not 0 <= detector_blanking_cycles <= 0xFFFF:
        raise ValueError("detector_blanking_cycles must be in [0, 65535]")
    thresholds = (
        low_power_threshold,
        large_lmt_overload_threshold,
        large_adc_overload_threshold,
        small_adc_overload_threshold,
    )
    if any(
        isinstance(value, bool) or not isinstance(value, int) for value in thresholds
    ):
        raise ValueError("tandem detector thresholds must be integers")
    if not 0 <= low_power_threshold <= 0x7F:
        raise ValueError("low-power threshold must be in [0, 127]")
    if not 0 <= large_lmt_overload_threshold <= 0x3F:
        raise ValueError("large-LMT threshold must be in [0, 63]")
    if not 0 <= small_adc_overload_threshold <= large_adc_overload_threshold <= 0xFF:
        raise ValueError("ADC thresholds must satisfy 0 <= small <= large <= 255")
    if samples_per_channel is not None:
        maximum_events = maximum_tandem_events_per_frame(
            mode=parsed_mode,
            samples_per_channel=samples_per_channel,
            power_measurement_samples=power_measurement_samples,
            cooldown_periods=cooldown_periods,
        )
        if maximum_events > event_capacity:
            raise ValueError(
                f"event_capacity {event_capacity} cannot cover {maximum_events} "
                "worst-case AUTO transitions"
            )
    return TANDEM_REQUEST.pack(
        TANDEM_REQUEST_MAGIC,
        TANDEM_ABI_VERSION,
        TANDEM_REQUEST.size,
        TANDEM_REQUIRED_FEATURES,
        int(parsed_mode),
        observation_capacity,
        event_capacity,
        minimum_gain_db,
        maximum_gain_db,
        initial_gain_db,
        power_measurement_samples,
        low_power_dwell_periods,
        cooldown_periods,
        pulse_high_cycles,
        pulse_low_cycles,
        detector_blanking_cycles,
        *thresholds,
        TANDEM_POLICY_FAIL_SESSION,
        TANDEM_POLICY_FAIL_SESSION,
        *([0] * 8),
    )


def build_hold_request(
    *, observation_capacity: int = 64, event_capacity: int = 64, gain_db: int = 20
) -> bytes:
    """Build RC2's legacy HOLD request used by the continuity experiment."""

    return build_tandem_request(
        mode=TandemMode.HOLD,
        observation_capacity=observation_capacity,
        event_capacity=event_capacity,
        initial_gain_db=gain_db,
    )


def metadata_buffer_abi(metadata_buffer_type: type[Any]) -> int:
    """Return 1 for v0.38's constructor and 2 for RC2's request ABI."""

    try:
        parameters = inspect.signature(metadata_buffer_type.__init__).parameters
    except (TypeError, ValueError) as exc:
        raise RuntimeError("cannot inspect libiio MetadataBuffer constructor") from exc
    return 2 if "request" in parameters else 1


def create_metadata_buffer(
    iio_module: Any,
    device: Any,
    samples_per_channel: int,
    *,
    metadata_capacity: int = 64 * 1024,
    tandem_request: Optional[bytes] = None,
    batch_frames: int = 1,
) -> tuple[Any, int]:
    """Open either metadata ABI without silently falling back to ordinary IIO."""

    if isinstance(batch_frames, bool) or not isinstance(batch_frames, int):
        raise TypeError("metadata batch frame count must be an integer")
    if not 1 <= batch_frames <= 64:
        raise ValueError("metadata batch frame count must be in [1, 64]")
    buffer_type = getattr(iio_module, "MetadataBuffer", None)
    if buffer_type is None:
        raise RuntimeError(
            "installed pylibiio has no MetadataBuffer; use the manifest-pinned runtime"
        )
    abi = metadata_buffer_abi(buffer_type)
    if abi == 2:
        request = tandem_request if tandem_request is not None else build_hold_request()
        return (
            buffer_type(
                device,
                samples_per_channel,
                request,
                metadata_capacity=metadata_capacity,
                batch_frames=batch_frames,
            ),
            abi,
        )
    if batch_frames != 1:
        raise RuntimeError(
            "metadata batching requires request ABI 2 and cannot use the legacy ABI"
        )
    return (
        buffer_type(
            device,
            samples_per_channel,
            metadata_capacity=metadata_capacity,
        ),
        abi,
    )


def close_iio_object(value: Any) -> None:
    """Synchronously close patched bindings and tolerate the legacy ABI."""

    if value is None:
        return
    close = getattr(value, "close", None)
    if callable(close):
        close()
