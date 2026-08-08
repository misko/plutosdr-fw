#include "spf_radio_frame_v3.h"

#include <limits.h>
#include <string.h>

size_t spf_radio_frame_v3_header_bytes(
	uint16_t gain_observation_capacity,
	uint16_t gain_event_capacity)
{
	if (gain_observation_capacity == 0 ||
		gain_observation_capacity > SPF_MAX_GAIN_OBSERVATIONS ||
		gain_event_capacity > SPF_MAX_GAIN_EVENTS)
		return 0;
	const size_t bytes = sizeof(spf_radio_meta_v3_prefix_t) +
		(size_t)gain_observation_capacity * sizeof(spf_gain_observation_v3_t) +
		(size_t)gain_event_capacity * sizeof(spf_gain_event_v3_t) +
		sizeof(uint32_t);
	return bytes <= UINT16_MAX ? bytes : 0;
}

bool spf_radio_frame_v3_build(
	void *destination,
	size_t destination_bytes,
	const spf_radio_frame_v3_args_t *args)
{
	if (destination == NULL || args == NULL || args->stream_id == 0 ||
		args->samples_per_channel == 0 ||
		args->iq_payload_bytes != args->samples_per_channel * UINT32_C(8) ||
		args->enabled_scan_mask != UINT32_C(0x0f) ||
		(args->metadata_features & SPF_META_REQUIRED_FEATURES_V3) !=
			SPF_META_REQUIRED_FEATURES_V3 ||
		args->gain_observation_interval_samples == 0 ||
		args->gain_observation_count == 0 ||
		args->gain_observation_count > args->gain_observation_capacity ||
		args->gain_observations == NULL ||
		args->gain_event_count > args->gain_event_capacity ||
		(args->gain_event_count != 0 && args->gain_events == NULL))
		return false;

	const size_t header_bytes = spf_radio_frame_v3_header_bytes(
		args->gain_observation_capacity,
		args->gain_event_capacity);
	if (header_bytes == 0 || destination_bytes < header_bytes)
		return false;

	const spf_gain_observation_v3_t *first = &args->gain_observations[0];
	const spf_gain_observation_v3_t *last =
		&args->gain_observations[args->gain_observation_count - 1];
	const bool first_valid =
		(first->flags & SPF_GAIN_OBSERVATION_VALID) != 0;
	const bool last_valid =
		(last->flags & SPF_GAIN_OBSERVATION_VALID) != 0;
	uint32_t flags = SPF_META_SAMPLE_SEQUENCE_VALID |
		SPF_META_HARDWARE_SAMPLE_COUNTER_VALID |
		SPF_META_GAIN_OBSERVATIONS_VALID |
		SPF_META_GAIN_DB_VALUES |
		SPF_META_GAIN_FULL_TABLE_MODE;
	if (first_valid)
		flags |= SPF_META_START_VALID;
	if (last_valid)
		flags |= SPF_META_END_VALID;
	if (!first_valid || !last_valid)
		flags |= SPF_META_GAIN_READ_FAILED;
	if (first_valid && last_valid)
	{
		if (first->rx1_gain_index != last->rx1_gain_index)
			flags |= SPF_META_RX1_ENDPOINT_CHANGED;
		if (first->rx2_gain_index != last->rx2_gain_index)
			flags |= SPF_META_RX2_ENDPOINT_CHANGED;
	}
	if (args->rssi_start.valid)
		flags |= SPF_META_RSSI_START_VALID;
	if (args->rssi_end.valid)
		flags |= SPF_META_RSSI_END_VALID;
	if (!args->rssi_start.valid || !args->rssi_end.valid)
		flags |= SPF_META_RSSI_READ_FAILED;
	if (args->gain_observation_overflow_count != 0)
		flags |= SPF_META_GAIN_OBSERVATION_OVERFLOW;
	if (args->gain_event_count != 0)
		flags |= SPF_META_FPGA_EVENTS_VALID;
	if (args->gain_event_overflow_count != 0)
		flags |= SPF_META_FPGA_EVENT_OVERFLOW;
	if (args->device_iio_overflow)
		flags |= SPF_META_DEVICE_IIO_OVERFLOW;

	memset(destination, 0, header_bytes);
	spf_radio_meta_v3_prefix_t *header =
		(spf_radio_meta_v3_prefix_t *)destination;
	header->magic = SPF_GAIN_META_MAGIC;
	header->version = SPF_GAIN_META_VERSION_V3;
	header->header_bytes = (uint16_t)header_bytes;
	header->features = args->metadata_features;
	header->flags = flags;
	header->stream_id = args->stream_id;
	header->buffer_sequence = args->buffer_sequence;
	header->first_sample_sequence = args->first_sample_sequence;
	header->samples_per_channel = args->samples_per_channel;
	header->iq_payload_bytes = args->iq_payload_bytes;
	header->enabled_scan_mask = args->enabled_scan_mask;
	header->sample_format = SPF_SAMPLE_FORMAT_CS16_LE_TIME_INTERLEAVED;
	header->channel_count = 2;
	header->rx1_gain_db_start = first->rx1_gain_db;
	header->rx2_gain_db_start = first->rx2_gain_db;
	header->rx1_gain_db_end = last->rx1_gain_db;
	header->rx2_gain_db_end = last->rx2_gain_db;
	header->gain_start_read_duration_ns = first->read_duration_ns;
	header->gain_end_read_duration_ns = last->read_duration_ns;
	header->rx1_first_change_sample = SPF_FIRST_CHANGE_UNAVAILABLE;
	header->rx2_first_change_sample = SPF_FIRST_CHANGE_UNAVAILABLE;
	header->rx1_rssi_start_qdb = args->rssi_start.rx1_qdb;
	header->rx2_rssi_start_qdb = args->rssi_start.rx2_qdb;
	header->rx1_rssi_end_qdb = args->rssi_end.rx1_qdb;
	header->rx2_rssi_end_qdb = args->rssi_end.rx2_qdb;
	header->rssi_start_read_duration_ns = args->rssi_start.duration_ns;
	header->rssi_end_read_duration_ns = args->rssi_end.duration_ns;
	header->gain_observation_interval_samples =
		args->gain_observation_interval_samples;
	header->gain_observation_count = args->gain_observation_count;
	header->gain_observation_capacity = args->gain_observation_capacity;
	header->gain_observation_bytes = SPF_GAIN_OBSERVATION_BYTES;
	header->gain_event_count = args->gain_event_count;
	header->gain_event_capacity = args->gain_event_capacity;
	header->gain_event_bytes = SPF_GAIN_EVENT_BYTES;
	header->gain_observation_overflow_count =
		args->gain_observation_overflow_count;
	header->gain_event_overflow_count = args->gain_event_overflow_count;

	uint8_t *cursor = (uint8_t *)destination + sizeof(*header);
	memcpy(cursor,
		args->gain_observations,
		(size_t)args->gain_observation_count * sizeof(*args->gain_observations));
	cursor += (size_t)args->gain_observation_capacity *
		sizeof(*args->gain_observations);
	if (args->gain_event_count != 0)
		memcpy(cursor,
			args->gain_events,
			(size_t)args->gain_event_count * sizeof(*args->gain_events));
	uint32_t *crc = (uint32_t *)((uint8_t *)destination +
		header_bytes - sizeof(uint32_t));
	*crc = spf_gain_meta_crc32(destination, header_bytes);
	return true;
}
