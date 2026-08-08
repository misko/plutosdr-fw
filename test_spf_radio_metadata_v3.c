#include "spf_gain_metadata.h"

#include <assert.h>
#include <stdlib.h>
#include <string.h>

int main(void)
{
	const uint16_t observation_capacity = 2;
	const size_t header_bytes = sizeof(spf_radio_meta_v3_prefix_t) +
		observation_capacity * sizeof(spf_gain_observation_v3_t) +
		sizeof(uint32_t);
	assert(header_bytes == 192);
	uint8_t *wire = calloc(1, header_bytes);
	assert(wire);
	spf_radio_meta_v3_prefix_t *header =
		(spf_radio_meta_v3_prefix_t *)wire;
	header->magic = SPF_GAIN_META_MAGIC;
	header->version = SPF_GAIN_META_VERSION_V3;
	header->header_bytes = (uint16_t)header_bytes;
	header->features = SPF_META_REQUIRED_FEATURES_V3;
	header->flags = SPF_META_START_VALID |
		SPF_META_END_VALID |
		SPF_META_SAMPLE_SEQUENCE_VALID |
		SPF_META_GAIN_FULL_TABLE_MODE |
		SPF_META_GAIN_DB_VALUES |
		SPF_META_GAIN_OBSERVATIONS_VALID |
		SPF_META_HARDWARE_SAMPLE_COUNTER_VALID;
	header->stream_id = UINT64_C(0x123456789ABCDEF0);
	header->first_sample_sequence = UINT64_C(0x100000020);
	header->samples_per_channel = 32768;
	header->iq_payload_bytes = 32768 * 8;
	header->enabled_scan_mask = UINT32_C(0x0F);
	header->sample_format = SPF_SAMPLE_FORMAT_CS16_LE_TIME_INTERLEAVED;
	header->channel_count = 2;
	header->rx1_gain_db_start = 20;
	header->rx2_gain_db_start = 21;
	header->rx1_gain_db_end = 20;
	header->rx2_gain_db_end = 21;
	header->rx1_first_change_sample = SPF_FIRST_CHANGE_UNAVAILABLE;
	header->rx2_first_change_sample = SPF_FIRST_CHANGE_UNAVAILABLE;
	header->gain_observation_interval_samples = 32768;
	header->gain_observation_count = 1;
	header->gain_observation_capacity = observation_capacity;
	header->gain_observation_bytes = SPF_GAIN_OBSERVATION_BYTES;
	header->gain_event_bytes = SPF_GAIN_EVENT_BYTES;

	spf_gain_observation_v3_t *observation =
		(spf_gain_observation_v3_t *)(wire + sizeof(*header));
	observation->sample_sequence_before = UINT64_C(0x100000000);
	observation->sample_sequence_after = UINT64_C(0x100003A98);
	observation->read_duration_ns = 500000;
	observation->flags = SPF_GAIN_OBSERVATION_VALID |
		SPF_GAIN_OBSERVATION_SAMPLE_INTERVAL_VALID;
	observation->rx1_gain_index = 42;
	observation->rx2_gain_index = 43;
	observation->rx1_gain_db = 20;
	observation->rx2_gain_db = 21;

	uint32_t *crc = (uint32_t *)(wire + header_bytes - sizeof(uint32_t));
	*crc = spf_gain_meta_crc32(wire, header_bytes);
	const uint32_t expected_crc = *crc;
	*crc = 0;
	assert(spf_gain_meta_crc32(wire, header_bytes) == expected_crc);
	*crc = expected_crc;
	wire[sizeof(*header) + 1] ^= 1;
	*crc = 0;
	assert(spf_gain_meta_crc32(wire, header_bytes) != expected_crc);
	free(wire);
	return 0;
}
