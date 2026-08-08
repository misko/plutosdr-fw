#include "spf_time_anchor.h"

#include "spf_gain_metadata.h"

#include <assert.h>
#include <string.h>

int main(void)
{
	static const uint8_t query_golden[24] = {
		0x53, 0x54, 0x51, 0x31, 0x18, 0x00, 0x01, 0x00,
		0x08, 0x07, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01,
		0x00, 0x00, 0x00, 0x00, 0x05, 0x5b, 0x31, 0x87,
	};
	spf_time_anchor_query_v1_t query;
	spf_time_anchor_query_init(&query, UINT64_C(0x0102030405060708));
	assert(spf_time_anchor_query_validate(&query));
	assert(memcmp(&query, query_golden, sizeof(query)) == 0);
	query.reserved0 = 1;
	assert(!spf_time_anchor_query_validate(&query));

	spf_time_anchor_v1_t anchor;
	memset(&anchor, 0, sizeof(anchor));
	anchor.magic = SPF_TIME_ANCHOR_MAGIC;
	anchor.message_bytes = sizeof(anchor);
	anchor.version = SPF_TIME_ANCHOR_VERSION;
	anchor.flags = SPF_TIME_ANCHOR_COUNTER_INTERVAL_VALID |
		SPF_TIME_ANCHOR_MONOTONIC_INTERVAL_VALID |
		SPF_TIME_ANCHOR_COUNTER_LOW32 |
		SPF_TIME_ANCHOR_COUNTER_ADVANCED;
	anchor.request_id = 7;
	anchor.radio_monotonic_before_ns = 1000;
	anchor.sample_counter_before = UINT32_C(0xFFFFFFF0);
	anchor.sample_counter_after = UINT32_C(0x00000010);
	anchor.radio_monotonic_after_ns = 2000;
	anchor.crc32 = spf_gain_meta_crc32(&anchor, sizeof(anchor));
	assert(spf_time_anchor_validate(&anchor));
	static const uint8_t anchor_golden[64] = {
		0x53, 0x54, 0x41, 0x31, 0x40, 0x00, 0x01, 0x00,
		0x0f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
		0x07, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
		0xe8, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
		0xf0, 0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x00,
		0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
		0xd0, 0x07, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
		0x00, 0x00, 0x00, 0x00, 0x40, 0xdf, 0x4b, 0x9e,
	};
	assert(memcmp(&anchor, anchor_golden, sizeof(anchor)) == 0);
	anchor.sample_counter_before |= UINT64_C(1) << 32;
	assert(!spf_time_anchor_validate(&anchor));
	return 0;
}
