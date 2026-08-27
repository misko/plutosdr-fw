#include "spf_radio_frame_v3.h"

#include <assert.h>
#include <string.h>

static spf_radio_frame_v3_args_t valid_args(
	spf_gain_observation_v3_t *observations)
{
	const spf_radio_frame_v3_args_t args = {
		.metadata_features = SPF_META_REQUIRED_FEATURES_V6_BASE,
		.stream_id = UINT64_C(0x1122334455667788),
		.buffer_sequence = 9,
		.first_sample_sequence = UINT64_C(0x1234567800000020),
		.samples_per_channel = 1024,
		.iq_payload_bytes = 4096,
		.enabled_scan_mask = UINT32_C(0x03),
		.gain_observation_interval_samples = 512,
		.gain_observations = observations,
		.gain_observation_count = 1,
		.gain_observation_capacity = 1,
		.gain_event_capacity = 0,
	};
	return args;
}

static void test_v6_layout_and_exact_gap(void)
{
	uint8_t buffer[512];
	spf_gain_observation_v3_t observation = {
		.sample_sequence_before = UINT64_C(0x1234567800000000),
		.sample_sequence_after = UINT64_C(0x1234567800000010),
		.flags = SPF_GAIN_OBSERVATION_VALID |
			SPF_GAIN_OBSERVATION_SAMPLE_INTERVAL_VALID,
		.rx1_gain_db = 12,
		.rx2_gain_db = 12,
	};
	spf_radio_frame_v3_args_t args = valid_args(&observation);
	const uint64_t gap = UINT64_C(0x0000000200000003);

	assert(spf_radio_frame_v6_base_build(buffer, sizeof(buffer), &args, gap));
	const spf_radio_meta_v3_prefix_t *header = (const void *)buffer;
	assert(header->version == SPF_GAIN_META_VERSION_V6);
	assert(header->enabled_scan_mask == UINT32_C(0x03));
	assert(header->channel_count == 1);
	assert(header->iq_payload_bytes == 4096);
	assert(header->flags & SPF_META_SAMPLE_GAP_BEFORE);
	assert(spf_radio_meta_v6_missing_samples_before(header) == gap);
	assert(*(const uint32_t *)(buffer + header->header_bytes - 4) ==
		UINT32_C(0x2a157032));

	args.enabled_scan_mask = UINT32_C(0x0c);
	assert(spf_radio_frame_v6_base_build(buffer, sizeof(buffer), &args, 0));
	header = (const void *)buffer;
	assert(header->channel_count == 1);
	assert(!(header->flags & SPF_META_SAMPLE_GAP_BEFORE));
	assert(spf_radio_meta_v6_missing_samples_before(header) == 0);

	args.enabled_scan_mask = UINT32_C(0x0f);
	args.iq_payload_bytes = 8192;
	assert(spf_radio_frame_v6_base_build(buffer, sizeof(buffer), &args, 0));
	header = (const void *)buffer;
	assert(header->channel_count == 2);

	args.enabled_scan_mask = UINT32_C(0x05);
	assert(!spf_radio_frame_v6_base_build(buffer, sizeof(buffer), &args, 0));
	args.enabled_scan_mask = UINT32_C(0x03);
	args.iq_payload_bytes = 4096;
	args.samples_per_channel = 1023;
	assert(!spf_radio_frame_v6_base_build(buffer, sizeof(buffer), &args, 0));
}

int main(void)
{
	test_v6_layout_and_exact_gap();
	uint8_t buffer[512];
	spf_gain_observation_v3_t observations[2] = {
		{
			.sample_sequence_before = 1000,
			.sample_sequence_after = 1100,
			.read_duration_ns = 490000,
			.flags = SPF_GAIN_OBSERVATION_VALID |
				SPF_GAIN_OBSERVATION_SAMPLE_INTERVAL_VALID,
			.rx1_gain_index = 42,
			.rx2_gain_index = 43,
			.rx1_gain_db = 20,
			.rx2_gain_db = 21,
		},
		{
			.sample_sequence_before = 1600,
			.sample_sequence_after = 1700,
			.read_duration_ns = 500000,
			.flags = SPF_GAIN_OBSERVATION_VALID |
				SPF_GAIN_OBSERVATION_SAMPLE_INTERVAL_VALID,
			.rx1_gain_index = 44,
			.rx2_gain_index = 43,
			.rx1_gain_db = 22,
			.rx2_gain_db = 21,
		},
	};
	spf_radio_frame_v3_args_t args = {
		.metadata_features = SPF_META_REQUIRED_FEATURES_V3,
		.stream_id = 7,
		.buffer_sequence = 3,
		.first_sample_sequence = 1000,
		.samples_per_channel = 1024,
		.iq_payload_bytes = 8192,
		.enabled_scan_mask = 0x0f,
		.gain_observation_interval_samples = 512,
		.gain_observations = observations,
		.gain_observation_count = 2,
		.gain_observation_capacity = 4,
		.gain_observation_overflow_count = 1,
		.gain_event_capacity = 0,
		.rssi_start = {
			.rx1_qdb = 400,
			.rx2_qdb = 404,
			.valid = true,
			.duration_ns = 100,
		},
		.rssi_end = {
			.rx1_qdb = 408,
			.rx2_qdb = 412,
			.valid = true,
			.duration_ns = 110,
		},
	};
	const size_t header_bytes = spf_radio_frame_v3_header_bytes(4, 0);
	assert(header_bytes == sizeof(spf_radio_meta_v3_prefix_t) +
		4 * sizeof(spf_gain_observation_v3_t) + sizeof(uint32_t));
	assert(spf_radio_frame_v3_build(buffer, sizeof(buffer), &args));
	const spf_radio_meta_v3_prefix_t *header =
		(const spf_radio_meta_v3_prefix_t *)buffer;
	assert(header->header_bytes == header_bytes);
	assert(header->stream_id == 7);
	assert(header->buffer_sequence == 3);
	assert(header->gain_observation_count == 2);
	assert((header->flags & SPF_META_RX1_ENDPOINT_CHANGED) != 0);
	assert((header->flags & SPF_META_RX2_ENDPOINT_CHANGED) == 0);
	assert((header->flags & SPF_META_GAIN_OBSERVATION_OVERFLOW) != 0);
	const uint32_t stored_crc = *(const uint32_t *)(buffer + header_bytes - 4);
	/* Golden value emitted by Python RadioMetadataV3.pack for this fixture. */
	assert(stored_crc == UINT32_C(0x341a79b7));
	uint8_t copy[sizeof(buffer)];
	memcpy(copy, buffer, header_bytes);
	*(uint32_t *)(copy + header_bytes - 4) = 0;
	assert(stored_crc == spf_gain_meta_crc32(copy, header_bytes));

	args.stream_id = 0;
	assert(!spf_radio_frame_v3_build(buffer, sizeof(buffer), &args));
	args.stream_id = 7;
	args.gain_observation_count = 0;
	assert(!spf_radio_frame_v3_build(buffer, sizeof(buffer), &args));
	return 0;
}
