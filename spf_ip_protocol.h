#ifndef SPF_IP_PROTOCOL_H
#define SPF_IP_PROTOCOL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define SPF_IP_CONTROL_MAGIC UINT32_C(0x31434953) /* little-endian "SIC1" */
#define SPF_IP_CONTROL_VERSION UINT16_C(1)
#define SPF_IP_FRAGMENT_MAGIC UINT32_C(0x31504953) /* little-endian "SIP1" */
#define SPF_IP_FRAGMENT_VERSION UINT16_C(1)

#define SPF_IP_CONTROL_FLAG_FINITE_RX (UINT32_C(1) << 0)
#define SPF_IP_CONTROL_FLAG_IDEMPOTENT_REQUESTS (UINT32_C(1) << 1)
#define SPF_IP_CONTROL_FLAG_TIME_ANCHOR (UINT32_C(1) << 2)
#define SPF_IP_CONTROL_KNOWN_FLAGS \
	(SPF_IP_CONTROL_FLAG_FINITE_RX | SPF_IP_CONTROL_FLAG_IDEMPOTENT_REQUESTS | \
	 SPF_IP_CONTROL_FLAG_TIME_ANCHOR)

#define SPF_IP_FRAGMENT_FLAG_FIRST (UINT32_C(1) << 0)
#define SPF_IP_FRAGMENT_FLAG_LAST (UINT32_C(1) << 1)
#define SPF_IP_FRAGMENT_KNOWN_FLAGS \
	(SPF_IP_FRAGMENT_FLAG_FIRST | SPF_IP_FRAGMENT_FLAG_LAST)

#define SPF_METADATA_FEATURE_GAIN_ENDPOINTS (UINT64_C(1) << 0)
#define SPF_METADATA_FEATURE_HEADER_CRC32 (UINT64_C(1) << 1)
#define SPF_METADATA_FEATURE_SAMPLE_SEQUENCE (UINT64_C(1) << 2)
#define SPF_METADATA_FEATURE_FPGA_EVENTS (UINT64_C(1) << 3)
#define SPF_METADATA_FEATURE_GAIN_DB_ENDPOINTS (UINT64_C(1) << 4)
#define SPF_METADATA_FEATURE_RSSI_ENDPOINTS (UINT64_C(1) << 5)
#define SPF_METADATA_FEATURE_GAIN_OBSERVATIONS (UINT64_C(1) << 6)
#define SPF_METADATA_FEATURE_HARDWARE_SAMPLE_COUNTER (UINT64_C(1) << 7)
#define SPF_METADATA_KNOWN_FEATURES UINT64_C(0xff)

#define SPF_IP_MAX_DATAGRAM_BYTES UINT32_C(65507)
#define SPF_IP_MAX_FRAME_BYTES UINT32_C(16777216)
#define SPF_IP_MAX_FRAGMENT_COUNT UINT32_C(65536)
#define SPF_IP_MAX_SAMPLES_PER_CHANNEL UINT32_C(524288)
#define SPF_IP_MAX_FINITE_FRAMES UINT32_C(16)
#define SPF_IP_MAX_GAIN_OBSERVATIONS UINT16_C(256)
#define SPF_IP_MAX_GAIN_EVENTS UINT16_C(256)

typedef enum
{
	SPF_IP_CONTROL_QUERY_CAPABILITIES = 1,
	SPF_IP_CONTROL_CAPABILITIES = 2,
	SPF_IP_CONTROL_START_RX = 3,
	SPF_IP_CONTROL_STARTED = 4,
	SPF_IP_CONTROL_STOP_RX = 5,
	SPF_IP_CONTROL_STOPPED = 6,
	SPF_IP_CONTROL_ERROR = 7,
} spf_ip_control_type_t;

typedef enum
{
	SPF_IP_CONTROL_DATAGRAM_DROP = 0,
	SPF_IP_CONTROL_DATAGRAM_LEGACY,
	SPF_IP_CONTROL_DATAGRAM_V3,
	SPF_IP_CONTROL_DATAGRAM_TIME_ANCHOR,
} spf_ip_control_datagram_kind_t;

#pragma pack(push, 1)
typedef struct
{
	uint32_t magic;
	uint16_t version;
	uint16_t message_type;
	uint32_t message_bytes;
	uint64_t request_id;
	int32_t status;
	uint32_t flags;
	uint16_t protocol_min;
	uint16_t protocol_max;
	uint64_t features;
	uint32_t max_samples_per_channel;
	uint32_t max_finite_frames;
	uint32_t enabled_scan_mask;
	uint32_t samples_per_channel;
	uint32_t frame_count;
	uint32_t gain_observation_interval_samples;
	uint16_t gain_observation_capacity;
	uint16_t gain_event_capacity;
	uint16_t data_port;
	uint16_t max_datagram_bytes;
	uint64_t stream_id;
} spf_ip_control_v1_t;

typedef struct
{
	uint32_t magic;
	uint16_t version;
	uint16_t header_bytes;
	uint32_t flags;
	uint64_t stream_id;
	uint64_t frame_sequence;
	uint32_t frame_bytes;
	uint32_t frame_crc32;
	uint32_t fragment_index;
	uint32_t fragment_count;
	uint32_t fragment_offset;
	uint32_t fragment_bytes;
} spf_ip_fragment_v1_t;
#pragma pack(pop)

_Static_assert(sizeof(spf_ip_control_v1_t) == 80,
	"direct-IP control v1 must remain 80 bytes");
_Static_assert(sizeof(spf_ip_fragment_v1_t) == 52,
	"direct-IP fragment v1 must remain 52 bytes");

void spf_ip_control_init_query(spf_ip_control_v1_t *message,
	uint64_t request_id);
void spf_ip_control_init_capabilities(spf_ip_control_v1_t *message,
	uint64_t request_id);
void spf_ip_control_init_error(spf_ip_control_v1_t *message,
	uint64_t request_id,
	int32_t status);
void spf_ip_control_init_reply(spf_ip_control_v1_t *reply,
	const spf_ip_control_v1_t *request,
	spf_ip_control_type_t reply_type,
	uint64_t stream_id);
bool spf_ip_control_validate(const spf_ip_control_v1_t *message);
spf_ip_control_datagram_kind_t spf_ip_control_datagram_classify(
	const void *datagram,
	size_t datagram_bytes,
	uint32_t legacy_magic,
	size_t legacy_header_bytes,
	uint32_t time_anchor_magic);
bool spf_ip_fragment_validate(const spf_ip_fragment_v1_t *header,
	size_t datagram_bytes);
uint32_t spf_ip_crc32(const void *data, size_t bytes);
size_t spf_ip_fragment_count(size_t frame_bytes, size_t max_datagram_bytes);
bool spf_ip_fragment_plan(
	spf_ip_fragment_v1_t *headers,
	size_t header_capacity,
	const void *frame,
	size_t frame_bytes,
	uint64_t stream_id,
	uint64_t frame_sequence,
	size_t max_datagram_bytes);

#endif
