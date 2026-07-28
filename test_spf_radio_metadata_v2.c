#include "spf_gain_metadata.h"

#include <stdio.h>
#include <string.h>

static const uint8_t golden[SPF_GAIN_META_HEADER_BYTES_V2] = {
	0x53, 0x47, 0x4d, 0x31, 0x02, 0x00, 0x60, 0x00,
	0x37, 0x00, 0x00, 0x00, 0x17, 0x84, 0x05, 0x00,
	0xf0, 0xde, 0xbc, 0x9a, 0x78, 0x56, 0x34, 0x12,
	0x07, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
	0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
	0x08, 0x00, 0x00, 0x00, 0x40, 0x00, 0x00, 0x00,
	0x0f, 0x00, 0x00, 0x00, 0x01, 0x00, 0x02, 0x2a,
	0x2b, 0x29, 0x2b, 0x00, 0xb0, 0x04, 0x00, 0x00,
	0x14, 0x05, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff,
	0xff, 0xff, 0xff, 0xff, 0x91, 0x01, 0x92, 0x01,
	0x93, 0x01, 0x94, 0x01, 0x78, 0x05, 0x00, 0x00,
	0xdc, 0x05, 0x00, 0x00, 0x6f, 0xf4, 0x6d, 0xc7
};

int main(void)
{
	spf_radio_meta_v2_t header = {
		.magic = SPF_GAIN_META_MAGIC,
		.version = SPF_GAIN_META_VERSION_V2,
		.header_bytes = SPF_GAIN_META_HEADER_BYTES_V2,
		.features =
			SPF_META_FEATURE_GAIN_ENDPOINT_SNAPSHOTS |
			SPF_META_FEATURE_HEADER_CRC32 |
			SPF_META_FEATURE_SAMPLE_SEQUENCE |
			SPF_META_FEATURE_GAIN_DB_ENDPOINTS |
			SPF_META_FEATURE_RSSI_ENDPOINT_SNAPSHOTS,
		.flags =
			SPF_META_START_VALID |
			SPF_META_END_VALID |
			SPF_META_RX1_ENDPOINT_CHANGED |
			SPF_META_SAMPLE_SEQUENCE_VALID |
			SPF_META_GAIN_FULL_TABLE_MODE |
			SPF_META_RSSI_START_VALID |
			SPF_META_RSSI_END_VALID |
			SPF_META_GAIN_DB_VALUES,
		.stream_id = UINT64_C(0x123456789ABCDEF0),
		.buffer_sequence = 7,
		.first_sample_sequence = 1024,
		.samples_per_channel = 8,
		.iq_payload_bytes = 64,
		.enabled_scan_mask = 0x0F,
		.sample_format = SPF_SAMPLE_FORMAT_CS16_LE_TIME_INTERLEAVED,
		.channel_count = 2,
		.rx1_gain_db_start = 42,
		.rx2_gain_db_start = 43,
		.rx1_gain_db_end = 41,
		.rx2_gain_db_end = 43,
		.gain_start_read_duration_ns = 1200,
		.gain_end_read_duration_ns = 1300,
		.rx1_first_change_sample = SPF_FIRST_CHANGE_UNAVAILABLE,
		.rx2_first_change_sample = SPF_FIRST_CHANGE_UNAVAILABLE,
		.rx1_rssi_start_qdb = 401,
		.rx2_rssi_start_qdb = 402,
		.rx1_rssi_end_qdb = 403,
		.rx2_rssi_end_qdb = 404,
		.rssi_start_read_duration_ns = 1400,
		.rssi_end_read_duration_ns = 1500,
	};

	header.header_crc32 = spf_gain_meta_crc32(&header, sizeof(header));
	if (memcmp(&header, golden, sizeof(header)) != 0)
	{
		const uint8_t *actual = (const uint8_t *)&header;
		fprintf(stderr, "golden v2 metadata mismatch\nactual: ");
		for (size_t i = 0; i < sizeof(header); ++i)
			fprintf(stderr, "%02x", actual[i]);
		fprintf(stderr, "\n");
		return 1;
	}

	return 0;
}
