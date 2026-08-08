#include "spf_ip_protocol.h"

#include <assert.h>
#include <string.h>

static void test_query_golden_vector(void)
{
	static const uint8_t expected[80] = {
		0x53, 0x49, 0x43, 0x31, 0x01, 0x00, 0x01, 0x00,
		0x50, 0x00, 0x00, 0x00, 0x08, 0x07, 0x06, 0x05,
		0x04, 0x03, 0x02, 0x01,
	};
	spf_ip_control_v1_t query;
	spf_ip_control_init_query(&query, UINT64_C(0x0102030405060708));
	assert(spf_ip_control_validate(&query));
	assert(memcmp(&query, expected, sizeof(expected)) == 0);
	query.data_port = 1;
	assert(!spf_ip_control_validate(&query));
}

static void test_v3_start_and_started(void)
{
	spf_ip_control_v1_t start = {0};
	start.magic = SPF_IP_CONTROL_MAGIC;
	start.version = SPF_IP_CONTROL_VERSION;
	start.message_type = SPF_IP_CONTROL_START_RX;
	start.message_bytes = sizeof(start);
	start.request_id = 100;
	start.protocol_min = 3;
	start.protocol_max = 3;
	start.features = SPF_METADATA_FEATURE_GAIN_ENDPOINTS |
		SPF_METADATA_FEATURE_HEADER_CRC32 |
		SPF_METADATA_FEATURE_GAIN_OBSERVATIONS |
		SPF_METADATA_FEATURE_HARDWARE_SAMPLE_COUNTER;
	start.enabled_scan_mask = 0x0f;
	start.samples_per_channel = 524288;
	start.frame_count = 4;
	start.gain_observation_interval_samples = 32768;
	start.gain_observation_capacity = 32;
	start.data_port = 40000;
	start.max_datagram_bytes = 1472;
	assert(spf_ip_control_validate(&start));
	start.message_type = SPF_IP_CONTROL_STARTED;
	assert(!spf_ip_control_validate(&start));
	start.stream_id = UINT64_C(0x1122334455667788);
	assert(spf_ip_control_validate(&start));
	start.data_port = 0;
	assert(!spf_ip_control_validate(&start));
}

static void test_fragment_and_crc(void)
{
	static const uint8_t payload[] = "complete inner frame";
	spf_ip_fragment_v1_t header = {0};
	header.magic = SPF_IP_FRAGMENT_MAGIC;
	header.version = SPF_IP_FRAGMENT_VERSION;
	header.header_bytes = sizeof(header);
	header.flags = SPF_IP_FRAGMENT_FLAG_FIRST | SPF_IP_FRAGMENT_FLAG_LAST;
	header.stream_id = 7;
	header.frame_sequence = 11;
	header.frame_bytes = sizeof(payload) - 1;
	header.frame_crc32 = spf_ip_crc32(payload, sizeof(payload) - 1);
	header.fragment_count = 1;
	header.fragment_bytes = sizeof(payload) - 1;
	assert(header.frame_crc32 == UINT32_C(0x27d7afdf));
	assert(spf_ip_fragment_validate(&header, sizeof(header) + sizeof(payload) - 1));
	header.fragment_index = 1;
	assert(!spf_ip_fragment_validate(&header, sizeof(header) + sizeof(payload) - 1));
}

int main(void)
{
	test_query_golden_vector();
	test_v3_start_and_started();
	test_fragment_and_crc();
	return 0;
}
