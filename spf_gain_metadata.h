#ifndef SPF_GAIN_METADATA_H
#define SPF_GAIN_METADATA_H

#include <stddef.h>
#include <stdint.h>

#define SPF_GAIN_META_MAGIC UINT32_C(0x314D4753)
#define SPF_GAIN_META_VERSION_V1 UINT16_C(1)
#define SPF_GAIN_META_VERSION_V2 UINT16_C(2)
#define SPF_GAIN_META_VERSION_V3 UINT16_C(3)
#define SPF_GAIN_META_VERSION_V6 UINT16_C(6)
#define SPF_GAIN_META_VERSION_V7 UINT16_C(7)
#define SPF_GAIN_META_VERSION SPF_GAIN_META_VERSION_V1
#define SPF_GAIN_META_HEADER_BYTES_V1 UINT16_C(80)
#define SPF_GAIN_META_HEADER_BYTES_V2 UINT16_C(96)
#define SPF_GAIN_META_HEADER_BYTES SPF_GAIN_META_HEADER_BYTES_V1
#define SPF_GAIN_INDEX_INVALID UINT8_C(0xFF)
#define SPF_GAIN_DB_INVALID INT8_MIN
#define SPF_RSSI_QDB_INVALID UINT16_MAX
#define SPF_FIRST_CHANGE_UNAVAILABLE UINT32_MAX

#define SPF_META_FEATURE_GAIN_ENDPOINT_SNAPSHOTS (UINT32_C(1) << 0)
#define SPF_META_FEATURE_HEADER_CRC32            (UINT32_C(1) << 1)
#define SPF_META_FEATURE_SAMPLE_SEQUENCE         (UINT32_C(1) << 2)
#define SPF_META_FEATURE_FPGA_GAIN_EVENTS        (UINT32_C(1) << 3)
#define SPF_META_FEATURE_GAIN_DB_ENDPOINTS        (UINT32_C(1) << 4)
#define SPF_META_FEATURE_RSSI_ENDPOINT_SNAPSHOTS  (UINT32_C(1) << 5)
#define SPF_META_FEATURE_GAIN_OBSERVATION_SERIES   (UINT32_C(1) << 6)
#define SPF_META_FEATURE_HARDWARE_SAMPLE_COUNTER   (UINT32_C(1) << 7)
#define SPF_META_FEATURE_CANONICAL_RX_LAYOUT       (UINT32_C(1) << 10)
#define SPF_META_FEATURE_EXACT_GAP_ACCOUNTING      (UINT32_C(1) << 11)
#define SPF_META_FEATURE_FPGA_GAIN_TIMELINE         (UINT32_C(1) << 12)

#define SPF_META_REQUIRED_FEATURES_V1 ( \
	SPF_META_FEATURE_GAIN_ENDPOINT_SNAPSHOTS | \
	SPF_META_FEATURE_HEADER_CRC32 | \
	SPF_META_FEATURE_SAMPLE_SEQUENCE)
#define SPF_META_REQUIRED_FEATURES_V2 ( \
	SPF_META_REQUIRED_FEATURES_V1 | \
	SPF_META_FEATURE_GAIN_DB_ENDPOINTS | \
	SPF_META_FEATURE_RSSI_ENDPOINT_SNAPSHOTS)
#define SPF_META_REQUIRED_FEATURES_V3 ( \
	SPF_META_REQUIRED_FEATURES_V2 | \
	SPF_META_FEATURE_GAIN_OBSERVATION_SERIES | \
	SPF_META_FEATURE_HARDWARE_SAMPLE_COUNTER)
#define SPF_META_REQUIRED_FEATURES_V6_BASE ( \
	SPF_META_REQUIRED_FEATURES_V3 | \
	SPF_META_FEATURE_CANONICAL_RX_LAYOUT | \
	SPF_META_FEATURE_EXACT_GAP_ACCOUNTING)
#define SPF_META_REQUIRED_FEATURES_V7_BASE ( \
	SPF_META_REQUIRED_FEATURES_V6_BASE | \
	SPF_META_FEATURE_FPGA_GAIN_TIMELINE)

#define SPF_META_START_VALID                 (UINT32_C(1) << 0)
#define SPF_META_END_VALID                   (UINT32_C(1) << 1)
#define SPF_META_RX1_ENDPOINT_CHANGED        (UINT32_C(1) << 2)
#define SPF_META_RX2_ENDPOINT_CHANGED        (UINT32_C(1) << 3)
#define SPF_META_SAMPLE_SEQUENCE_VALID       (UINT32_C(1) << 4)
#define SPF_META_FPGA_EVENTS_VALID           (UINT32_C(1) << 5)
#define SPF_META_RX1_CHANGED_IN_BUFFER       (UINT32_C(1) << 6)
#define SPF_META_RX2_CHANGED_IN_BUFFER       (UINT32_C(1) << 7)
#define SPF_META_RX1_LOCKED_AT_END           (UINT32_C(1) << 8)
#define SPF_META_RX2_LOCKED_AT_END           (UINT32_C(1) << 9)
#define SPF_META_GAIN_FULL_TABLE_MODE        (UINT32_C(1) << 10)
#define SPF_META_DEVICE_IIO_OVERFLOW         (UINT32_C(1) << 11)
#define SPF_META_GAIN_READ_FAILED            (UINT32_C(1) << 12)
#define SPF_META_FPGA_EVENT_OVERFLOW         (UINT32_C(1) << 13)
#define SPF_META_DUMMY_GAINS                  (UINT32_C(1) << 14)
#define SPF_META_RSSI_START_VALID             (UINT32_C(1) << 15)
#define SPF_META_RSSI_END_VALID               (UINT32_C(1) << 16)
#define SPF_META_RSSI_READ_FAILED             (UINT32_C(1) << 17)
#define SPF_META_GAIN_DB_VALUES               (UINT32_C(1) << 18)
#define SPF_META_GAIN_OBSERVATIONS_VALID       (UINT32_C(1) << 19)
#define SPF_META_GAIN_OBSERVATION_OVERFLOW     (UINT32_C(1) << 20)
#define SPF_META_HARDWARE_SAMPLE_COUNTER_VALID (UINT32_C(1) << 21)
#define SPF_META_SAMPLE_GAP_BEFORE              (UINT32_C(1) << 23)
#define SPF_META_FPGA_GAIN_TIMELINE_VALID        (UINT32_C(1) << 24)

#define SPF_GAIN_OBSERVATION_VALID                 (UINT16_C(1) << 0)
#define SPF_GAIN_OBSERVATION_SAMPLE_INTERVAL_VALID (UINT16_C(1) << 1)

#define SPF_GAIN_EVENT_RX1_CHANGED (UINT16_C(1) << 0)
#define SPF_GAIN_EVENT_RX2_CHANGED (UINT16_C(1) << 1)
#define SPF_GAIN_EVENT_RX1_LOCKED  (UINT16_C(1) << 2)
#define SPF_GAIN_EVENT_RX2_LOCKED  (UINT16_C(1) << 3)

#define SPF_GAIN_OBSERVATION_BYTES UINT16_C(32)
#define SPF_GAIN_EVENT_BYTES UINT16_C(16)
#define SPF_RADIO_META_V3_PREFIX_BYTES UINT16_C(124)
#define SPF_MAX_GAIN_OBSERVATIONS UINT16_C(256)
#define SPF_MAX_GAIN_EVENTS UINT16_C(256)

#define SPF_SAMPLE_FORMAT_CS16_LE_TIME_INTERLEAVED UINT16_C(1)

#if defined(__BYTE_ORDER__) && (__BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__)
#error "SPF direct-USB protocol v1 requires a little-endian target"
#endif

#pragma pack(push, 1)
typedef struct
{
	uint32_t magic;
	uint16_t version;
	uint16_t header_bytes;
	uint32_t features;
	uint32_t flags;
	uint64_t stream_id;
	uint64_t buffer_sequence;
	uint64_t first_sample_sequence;
	uint32_t samples_per_channel;
	uint32_t iq_payload_bytes;
	uint32_t enabled_scan_mask;
	uint16_t sample_format;
	uint8_t channel_count;
	uint8_t rx1_gain_start;
	uint8_t rx2_gain_start;
	uint8_t rx1_gain_end;
	uint8_t rx2_gain_end;
	uint8_t reserved0;
	uint32_t gain_start_read_duration_ns;
	uint32_t gain_end_read_duration_ns;
	uint32_t rx1_first_change_sample;
	uint32_t rx2_first_change_sample;
	uint32_t header_crc32;
} spf_gain_meta_v1_t;

typedef struct
{
	uint32_t magic;
	uint16_t version;
	uint16_t header_bytes;
	uint32_t features;
	uint32_t flags;
	uint64_t stream_id;
	uint64_t buffer_sequence;
	uint64_t first_sample_sequence;
	uint32_t samples_per_channel;
	uint32_t iq_payload_bytes;
	uint32_t enabled_scan_mask;
	uint16_t sample_format;
	uint8_t channel_count;
	int8_t rx1_gain_db_start;
	int8_t rx2_gain_db_start;
	int8_t rx1_gain_db_end;
	int8_t rx2_gain_db_end;
	uint8_t reserved0;
	uint32_t gain_start_read_duration_ns;
	uint32_t gain_end_read_duration_ns;
	uint32_t rx1_first_change_sample;
	uint32_t rx2_first_change_sample;
	uint16_t rx1_rssi_start_qdb;
	uint16_t rx2_rssi_start_qdb;
	uint16_t rx1_rssi_end_qdb;
	uint16_t rx2_rssi_end_qdb;
	uint32_t rssi_start_read_duration_ns;
	uint32_t rssi_end_read_duration_ns;
	uint32_t header_crc32;
} spf_radio_meta_v2_t;

typedef struct
{
	uint64_t sample_sequence_before;
	uint64_t sample_sequence_after;
	uint32_t read_duration_ns;
	uint16_t flags;
	uint8_t rx1_gain_index;
	uint8_t rx2_gain_index;
	int8_t rx1_gain_db;
	int8_t rx2_gain_db;
	uint16_t reserved0;
	uint32_t reserved1;
} spf_gain_observation_v3_t;

typedef struct
{
	uint64_t sample_sequence;
	uint16_t flags;
	uint16_t reserved0;
	uint32_t reserved1;
} spf_gain_event_v3_t;

/*
 * The v3 CRC is the final uint32_t at header_bytes - 4, after the fixed-size
 * observation and event capacity arrays.  It is intentionally not part of
 * this prefix so negotiated capacities retain one fixed USB transfer size.
 */
typedef struct
{
	uint32_t magic;
	uint16_t version;
	uint16_t header_bytes;
	uint32_t features;
	uint32_t flags;
	uint64_t stream_id;
	uint64_t buffer_sequence;
	uint64_t first_sample_sequence;
	uint32_t samples_per_channel;
	uint32_t iq_payload_bytes;
	uint32_t enabled_scan_mask;
	uint16_t sample_format;
	uint8_t channel_count;
	int8_t rx1_gain_db_start;
	int8_t rx2_gain_db_start;
	int8_t rx1_gain_db_end;
	int8_t rx2_gain_db_end;
	uint8_t reserved0;
	uint32_t gain_start_read_duration_ns;
	uint32_t gain_end_read_duration_ns;
	uint32_t rx1_first_change_sample;
	uint32_t rx2_first_change_sample;
	uint16_t rx1_rssi_start_qdb;
	uint16_t rx2_rssi_start_qdb;
	uint16_t rx1_rssi_end_qdb;
	uint16_t rx2_rssi_end_qdb;
	uint32_t rssi_start_read_duration_ns;
	uint32_t rssi_end_read_duration_ns;
	uint32_t gain_observation_interval_samples;
	uint16_t gain_observation_count;
	uint16_t gain_observation_capacity;
	uint16_t gain_observation_bytes;
	uint16_t gain_event_count;
	uint16_t gain_event_capacity;
	uint16_t gain_event_bytes;
	uint32_t gain_observation_overflow_count;
	uint32_t gain_event_overflow_count;
	uint32_t reserved1;
	uint32_t reserved2;
} spf_radio_meta_v3_prefix_t;
#pragma pack(pop)

_Static_assert(sizeof(spf_gain_meta_v1_t) == SPF_GAIN_META_HEADER_BYTES,
	"SPF gain metadata v1 must be 80 bytes");
_Static_assert(offsetof(spf_gain_meta_v1_t, stream_id) == 16,
	"unexpected stream_id offset");
_Static_assert(offsetof(spf_gain_meta_v1_t, rx1_gain_start) == 55,
	"unexpected gain offset");
_Static_assert(offsetof(spf_gain_meta_v1_t, header_crc32) == 76,
	"unexpected CRC offset");
_Static_assert(sizeof(spf_radio_meta_v2_t) == SPF_GAIN_META_HEADER_BYTES_V2,
	"SPF radio metadata v2 must be 96 bytes");
_Static_assert(offsetof(spf_radio_meta_v2_t, stream_id) == 16,
	"unexpected v2 stream_id offset");
_Static_assert(offsetof(spf_radio_meta_v2_t, rx1_gain_db_start) == 55,
	"unexpected v2 gain offset");
_Static_assert(offsetof(spf_radio_meta_v2_t, rx1_rssi_start_qdb) == 76,
	"unexpected v2 RSSI offset");
_Static_assert(offsetof(spf_radio_meta_v2_t, header_crc32) == 92,
	"unexpected v2 CRC offset");
_Static_assert(sizeof(spf_gain_observation_v3_t) == SPF_GAIN_OBSERVATION_BYTES,
	"SPF v3 gain observation must be 32 bytes");
_Static_assert(sizeof(spf_gain_event_v3_t) == SPF_GAIN_EVENT_BYTES,
	"SPF v3 gain event must be 16 bytes");
_Static_assert(sizeof(spf_radio_meta_v3_prefix_t) ==
	SPF_RADIO_META_V3_PREFIX_BYTES,
	"SPF radio metadata v3 prefix must be 124 bytes");
_Static_assert(offsetof(spf_radio_meta_v3_prefix_t,
	gain_observation_interval_samples) == 92,
	"unexpected v3 extension offset");
_Static_assert(offsetof(spf_radio_meta_v3_prefix_t, reserved1) == 116,
	"unexpected v3 reserved-word offset");

/* V6 assigns the two V3 reserved words to one little-endian exact gap count. */
static inline uint64_t spf_radio_meta_v6_missing_samples_before(
	const spf_radio_meta_v3_prefix_t *header)
{
	return (uint64_t)header->reserved1 |
		((uint64_t)header->reserved2 << 32);
}

/*
 * CRC-32/ISO-HDLC (the zlib.crc32 variant). Call this with header_crc32 set to
 * zero and len == header_bytes.
 */
static inline uint32_t spf_gain_meta_crc32(const void *data, size_t len)
{
	const uint8_t *bytes = (const uint8_t *)data;
	uint32_t crc = UINT32_C(0xFFFFFFFF);

	for (size_t i = 0; i < len; ++i)
	{
		crc ^= bytes[i];
		for (unsigned int bit = 0; bit < 8; ++bit)
		{
			const uint32_t mask = (uint32_t)-(int32_t)(crc & 1U);
			crc = (crc >> 1) ^ (UINT32_C(0xEDB88320) & mask);
		}
	}

	return crc ^ UINT32_C(0xFFFFFFFF);
}

#endif
