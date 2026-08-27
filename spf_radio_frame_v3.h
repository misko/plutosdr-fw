#ifndef SPF_RADIO_FRAME_V3_H
#define SPF_RADIO_FRAME_V3_H

#include "spf_gain_metadata.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct
{
	uint16_t rx1_qdb;
	uint16_t rx2_qdb;
	bool valid;
	uint32_t duration_ns;
} spf_radio_rssi_v3_t;

typedef struct
{
	uint32_t metadata_features;
	uint64_t stream_id;
	uint64_t buffer_sequence;
	uint64_t first_sample_sequence;
	uint32_t samples_per_channel;
	uint32_t iq_payload_bytes;
	uint32_t enabled_scan_mask;
	uint32_t gain_observation_interval_samples;
	const spf_gain_observation_v3_t *gain_observations;
	uint16_t gain_observation_count;
	uint16_t gain_observation_capacity;
	uint32_t gain_observation_overflow_count;
	const spf_gain_event_v3_t *gain_events;
	uint16_t gain_event_count;
	uint16_t gain_event_capacity;
	uint32_t gain_event_overflow_count;
	spf_radio_rssi_v3_t rssi_start;
	spf_radio_rssi_v3_t rssi_end;
	bool device_iio_overflow;
} spf_radio_frame_v3_args_t;

size_t spf_radio_frame_v3_header_bytes(
	uint16_t gain_observation_capacity,
	uint16_t gain_event_capacity);

/*
 * Serialize only the metadata header. IQ begins at destination+header_bytes
 * and remains the transport adapter's responsibility.
 */
bool spf_radio_frame_v3_build(
	void *destination,
	size_t destination_bytes,
	const spf_radio_frame_v3_args_t *args);

/*
 * Build the common V6 base. The caller may insert a reviewed extension before
 * the variable observation/event arrays and must then recompute the CRC.
 * V3 remains strict dual-RX; V6 admits only complete RX0, RX1, or dual layouts.
 */
bool spf_radio_frame_v6_base_build(
	void *destination,
	size_t destination_bytes,
	const spf_radio_frame_v3_args_t *args,
	uint64_t missing_samples_before);

#endif
