#ifndef SPF_GAIN_METADATA_H
#define SPF_GAIN_METADATA_H

#include <stddef.h>
#include <stdint.h>

#define SPF_GAIN_META_MAGIC UINT32_C(0x314D4753)
#define SPF_GAIN_META_VERSION UINT16_C(1)
#define SPF_GAIN_META_HEADER_BYTES UINT16_C(80)
#define SPF_GAIN_INDEX_INVALID UINT8_C(0xFF)
#define SPF_FIRST_CHANGE_UNAVAILABLE UINT32_MAX

#define SPF_META_FEATURE_GAIN_ENDPOINT_SNAPSHOTS (UINT32_C(1) << 0)
#define SPF_META_FEATURE_HEADER_CRC32            (UINT32_C(1) << 1)
#define SPF_META_FEATURE_SAMPLE_SEQUENCE         (UINT32_C(1) << 2)
#define SPF_META_FEATURE_FPGA_GAIN_EVENTS        (UINT32_C(1) << 3)

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
#pragma pack(pop)

_Static_assert(sizeof(spf_gain_meta_v1_t) == SPF_GAIN_META_HEADER_BYTES,
	"SPF gain metadata v1 must be 80 bytes");
_Static_assert(offsetof(spf_gain_meta_v1_t, stream_id) == 16,
	"unexpected stream_id offset");
_Static_assert(offsetof(spf_gain_meta_v1_t, rx1_gain_start) == 55,
	"unexpected gain offset");
_Static_assert(offsetof(spf_gain_meta_v1_t, header_crc32) == 76,
	"unexpected CRC offset");

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
