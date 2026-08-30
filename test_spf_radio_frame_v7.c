#include "spf_radio_frame_v3.h"

#include <assert.h>
#include <string.h>

static spf_radio_frame_v7_args_t base_args(void)
{
	return (spf_radio_frame_v7_args_t){
		.metadata_features = SPF_META_REQUIRED_FEATURES_V7_BASE,
		.stream_id = UINT64_C(0x1122334455667788),
		.buffer_sequence = 9,
		.first_sample_sequence = 1000,
		.samples_per_channel = 1024,
		.iq_payload_bytes = 4096,
		.enabled_scan_mask = UINT32_C(0x03),
		.rx1_gain_db_start = -10,
		.rx2_gain_db_start = -10,
		.rx1_gain_db_end = -10,
		.rx2_gain_db_end = -10,
		.rx1_first_change_sample = SPF_FIRST_CHANGE_UNAVAILABLE,
		.rx2_first_change_sample = SPF_FIRST_CHANGE_UNAVAILABLE,
		.missing_samples_before = UINT64_C(0x0000000200000003),
	};
}

static uint32_t stored_crc(const uint8_t *buffer, size_t header_bytes)
{
	uint32_t value;
	memcpy(&value, buffer + header_bytes - sizeof(value), sizeof(value));
	return value;
}

static void test_no_spi_telemetry(void)
{
	uint8_t buffer[512];
	spf_radio_frame_v7_args_t args = base_args();
	const size_t header_bytes = spf_radio_frame_v7_header_bytes(0, 0);

	assert(header_bytes == sizeof(spf_radio_meta_v3_prefix_t) + sizeof(uint32_t));
	assert(spf_radio_frame_v7_base_build(buffer, sizeof(buffer), &args));
	const spf_radio_meta_v3_prefix_t *header = (const void *)buffer;
	assert(header->version == SPF_GAIN_META_VERSION_V7);
	assert(header->header_bytes == header_bytes);
	assert(header->features == SPF_META_REQUIRED_FEATURES_V7_BASE);
	assert((header->flags & SPF_META_FPGA_GAIN_TIMELINE_VALID) != 0);
	assert((header->flags & SPF_META_START_VALID) != 0);
	assert((header->flags & SPF_META_END_VALID) != 0);
	assert((header->flags & SPF_META_GAIN_READ_FAILED) != 0);
	assert((header->flags & SPF_META_GAIN_OBSERVATIONS_VALID) == 0);
	assert((header->flags & SPF_META_RSSI_READ_FAILED) != 0);
	assert((header->flags & SPF_META_RSSI_START_VALID) == 0);
	assert((header->flags & SPF_META_RSSI_END_VALID) == 0);
	assert(header->gain_observation_count == 0);
	assert(header->gain_observation_capacity == 0);
	assert(header->gain_observation_interval_samples == 0);
	assert(header->rx1_rssi_start_qdb == SPF_RSSI_QDB_INVALID);
	assert(header->rx2_rssi_end_qdb == SPF_RSSI_QDB_INVALID);
	assert(spf_radio_meta_v6_missing_samples_before(header) ==
		args.missing_samples_before);
	assert(stored_crc(buffer, header_bytes) == UINT32_C(0x2b3ab58a));
}

static void test_exact_events_and_optional_rssi(void)
{
	uint8_t buffer[512];
	spf_gain_observation_v3_t observation = {
		.sample_sequence_before = 995,
		.sample_sequence_after = 1010,
		.read_duration_ns = 900,
		.flags = SPF_GAIN_OBSERVATION_VALID |
			SPF_GAIN_OBSERVATION_SAMPLE_INTERVAL_VALID,
		.rx1_gain_index = 40,
		.rx2_gain_index = 40,
		.rx1_gain_db = -10,
		.rx2_gain_db = -10,
	};
	spf_gain_event_v7_t events[2] = {
		{
			.sample_sequence = 1000,
			.event_sequence = UINT32_MAX,
			.flags = UINT16_C(0x13),
			.rx1_gain_index = 40,
			.rx2_gain_index = 40,
		},
		{
			.sample_sequence = 1500,
			.event_sequence = 0,
			.flags = UINT16_C(0x13),
			.rx1_gain_index = 41,
			.rx2_gain_index = 41,
		},
	};
	spf_radio_frame_v7_args_t args = base_args();
	args.gain_observation_interval_samples = 512;
	args.gain_observations = &observation;
	args.gain_observation_count = 1;
	args.gain_observation_capacity = 2;
	args.gain_events = events;
	args.gain_event_count = 2;
	args.gain_event_capacity = 3;
	args.rx1_gain_db_end = -8;
	args.rx2_gain_db_end = -8;
	args.rx1_first_change_sample = 0;
	args.rx2_first_change_sample = 0;
	args.missing_samples_before = 0;
	args.rssi_start = (spf_radio_rssi_v3_t){
		.rx1_qdb = 400,
		.rx2_qdb = 404,
		.valid = true,
		.duration_ns = 100,
	};

	const size_t header_bytes = spf_radio_frame_v7_header_bytes(2, 3);
	assert(header_bytes == sizeof(spf_radio_meta_v3_prefix_t) +
		2 * sizeof(spf_gain_observation_v3_t) +
		3 * sizeof(spf_gain_event_v7_t) + sizeof(uint32_t));
	assert(spf_radio_frame_v7_base_build(buffer, sizeof(buffer), &args));
	const spf_radio_meta_v3_prefix_t *header = (const void *)buffer;
	assert(header->gain_observation_count == 1);
	assert(header->gain_event_count == 2);
	assert(header->rx1_first_change_sample == 0);
	assert(header->rx2_first_change_sample == 0);
	assert((header->flags & SPF_META_GAIN_OBSERVATIONS_VALID) != 0);
	assert((header->flags & SPF_META_GAIN_READ_FAILED) == 0);
	assert((header->flags & SPF_META_FPGA_EVENTS_VALID) != 0);
	assert((header->flags & SPF_META_RX1_CHANGED_IN_BUFFER) != 0);
	assert((header->flags & SPF_META_RX2_CHANGED_IN_BUFFER) != 0);
	assert((header->flags & SPF_META_RSSI_START_VALID) != 0);
	assert((header->flags & SPF_META_RSSI_END_VALID) == 0);
	assert((header->flags & SPF_META_RSSI_READ_FAILED) != 0);
	assert(header->rx1_rssi_start_qdb == 400);
	assert(header->rx1_rssi_end_qdb == SPF_RSSI_QDB_INVALID);
	const size_t event_offset = sizeof(*header) +
		2 * sizeof(spf_gain_observation_v3_t);
	const spf_gain_event_v7_t *wire_events =
		(const spf_gain_event_v7_t *)(buffer + event_offset);
	assert(wire_events[0].event_sequence == UINT32_MAX);
	assert(wire_events[1].event_sequence == 0);
	assert(wire_events[1].rx1_gain_index == 41);
	assert(buffer[event_offset + 2 * sizeof(*wire_events)] == 0);
	assert(stored_crc(buffer, header_bytes) == UINT32_C(0xcd67e933));
}

static void test_invalid_contracts(void)
{
	uint8_t buffer[512];
	spf_radio_frame_v7_args_t args = base_args();
	spf_gain_event_v7_t events[2] = {
		{
			.sample_sequence = 1000,
			.event_sequence = 7,
			.flags = UINT16_C(0x13),
			.rx1_gain_index = 40,
			.rx2_gain_index = 40,
		},
		{
			.sample_sequence = 1100,
			.event_sequence = 8,
			.flags = UINT16_C(0x13),
			.rx1_gain_index = 41,
			.rx2_gain_index = 41,
		},
	};
	spf_gain_observation_v3_t observation = {
		.sample_sequence_before = 995,
		.sample_sequence_after = 1010,
		.flags = SPF_GAIN_OBSERVATION_VALID |
			SPF_GAIN_OBSERVATION_SAMPLE_INTERVAL_VALID,
	};

	args.rx1_gain_db_end = -9;
	assert(!spf_radio_frame_v7_base_build(buffer, sizeof(buffer), &args));
	args.rx1_gain_db_end = -10;
	args.gain_events = events;
	args.gain_event_count = 2;
	args.gain_event_capacity = 2;
	args.rx1_first_change_sample = 1;
	args.rx2_first_change_sample = 1;
	assert(!spf_radio_frame_v7_base_build(buffer, sizeof(buffer), &args));
	args.rx1_first_change_sample = 0;
	args.rx2_first_change_sample = 0;
	assert(spf_radio_frame_v7_base_build(buffer, sizeof(buffer), &args));

	events[1].event_sequence = 9;
	assert(!spf_radio_frame_v7_base_build(buffer, sizeof(buffer), &args));
	events[1].event_sequence = 8;
	events[1].sample_sequence = args.first_sample_sequence +
		args.samples_per_channel;
	assert(!spf_radio_frame_v7_base_build(buffer, sizeof(buffer), &args));
	events[1].sample_sequence = 1100;
	events[1].rx2_gain_index = 42;
	assert(!spf_radio_frame_v7_base_build(buffer, sizeof(buffer), &args));
	events[1].rx2_gain_index = 41;
	events[1].flags |= UINT16_C(0x8000);
	assert(!spf_radio_frame_v7_base_build(buffer, sizeof(buffer), &args));
	events[1].flags = UINT16_C(0x03);
	assert(!spf_radio_frame_v7_base_build(buffer, sizeof(buffer), &args));
	events[1].flags = UINT16_C(0x17);
	assert(!spf_radio_frame_v7_base_build(buffer, sizeof(buffer), &args));
	events[1].flags = UINT16_C(0x13);

	args.gain_event_count = 0;
	args.gain_event_capacity = 0;
	args.gain_events = NULL;
	args.rx1_first_change_sample = SPF_FIRST_CHANGE_UNAVAILABLE;
	args.rx2_first_change_sample = SPF_FIRST_CHANGE_UNAVAILABLE;
	args.gain_observation_interval_samples = 1;
	assert(!spf_radio_frame_v7_base_build(buffer, sizeof(buffer), &args));
	args.gain_observation_interval_samples = 0;
	args.rx1_gain_db_start = SPF_GAIN_DB_INVALID;
	assert(!spf_radio_frame_v7_base_build(buffer, sizeof(buffer), &args));
	args.rx1_gain_db_start = -10;
	args.gain_observation_interval_samples = 512;
	args.gain_observations = &observation;
	args.gain_observation_count = 1;
	args.gain_observation_capacity = 1;
	observation.flags = SPF_GAIN_OBSERVATION_SAMPLE_INTERVAL_VALID;
	assert(!spf_radio_frame_v7_base_build(buffer, sizeof(buffer), &args));
	observation.flags = SPF_GAIN_OBSERVATION_VALID |
		SPF_GAIN_OBSERVATION_SAMPLE_INTERVAL_VALID;
	observation.sample_sequence_before = 2024;
	observation.sample_sequence_after = 2025;
	assert(!spf_radio_frame_v7_base_build(buffer, sizeof(buffer), &args));
	observation.sample_sequence_before = 1010;
	observation.sample_sequence_after = 1009;
	assert(!spf_radio_frame_v7_base_build(buffer, sizeof(buffer), &args));
}

int main(void)
{
	test_no_spi_telemetry();
	test_exact_events_and_optional_rssi();
	test_invalid_contracts();
	return 0;
}
