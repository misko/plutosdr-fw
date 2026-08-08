#include "spf_ip_protocol.h"

#include <spf/spf_radio_frame_v3.h>

#include <assert.h>
#include <stdlib.h>
#include <string.h>

int main(void)
{
	spf_gain_observation_v3_t observation = {
		.sample_sequence_before = 1000000,
		.sample_sequence_after = 1014000,
		.read_duration_ns = 490000,
		.flags = SPF_GAIN_OBSERVATION_VALID |
			SPF_GAIN_OBSERVATION_SAMPLE_INTERVAL_VALID,
		.rx1_gain_index = 42,
		.rx2_gain_index = 43,
		.rx1_gain_db = 20,
		.rx2_gain_db = 21,
	};
	spf_radio_frame_v3_args_t args = {
		.metadata_features = SPF_META_REQUIRED_FEATURES_V3,
		.stream_id = 44,
		.buffer_sequence = 0,
		.first_sample_sequence = 1000000,
		.samples_per_channel = 16384,
		.iq_payload_bytes = 16384 * 8,
		.enabled_scan_mask = 0x0f,
		.gain_observation_interval_samples = 16384,
		.gain_observations = &observation,
		.gain_observation_count = 1,
		.gain_observation_capacity = 1,
		.rssi_start = {
			.rx1_qdb = 400,
			.rx2_qdb = 404,
			.valid = true,
		},
		.rssi_end = {
			.rx1_qdb = 400,
			.rx2_qdb = 404,
			.valid = true,
		},
	};
	const size_t header_bytes = spf_radio_frame_v3_header_bytes(1, 0);
	const size_t frame_bytes = header_bytes + args.iq_payload_bytes;
	uint8_t *frame = calloc(1, frame_bytes);
	assert(frame != NULL);
	assert(spf_radio_frame_v3_build(frame, header_bytes, &args));
	for (size_t index = header_bytes; index < frame_bytes; ++index)
		frame[index] = (uint8_t)(index % 251);

	const size_t fragment_count = spf_ip_fragment_count(frame_bytes, 1472);
	assert(fragment_count > 1);
	spf_ip_fragment_v1_t *headers =
		calloc(fragment_count, sizeof(*headers));
	assert(headers != NULL);
	assert(spf_ip_fragment_plan(headers,
		fragment_count,
		frame,
		frame_bytes,
		args.stream_id,
		args.buffer_sequence,
		1472));
	assert(headers[0].frame_crc32 == spf_ip_crc32(frame, frame_bytes));
	assert(headers[0].stream_id == args.stream_id);
	assert(headers[0].frame_sequence == args.buffer_sequence);
	assert(headers[fragment_count - 1].fragment_offset +
		headers[fragment_count - 1].fragment_bytes == frame_bytes);

	free(headers);
	free(frame);
	return 0;
}
