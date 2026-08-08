#define _POSIX_C_SOURCE 200809L

#include "spf_time_anchor.h"

#include "spf_gain_metadata.h"

#include <iio.h>
#include <string.h>
#include <time.h>

static uint64_t timespec_ns(const struct timespec *value)
{
	return (uint64_t)value->tv_sec * UINT64_C(1000000000) +
		(uint64_t)value->tv_nsec;
}

static uint32_t query_crc(const spf_time_anchor_query_v1_t *query)
{
	spf_time_anchor_query_v1_t copy = *query;
	copy.crc32 = 0;
	return spf_gain_meta_crc32(&copy, sizeof(copy));
}

static uint32_t anchor_crc(const spf_time_anchor_v1_t *anchor)
{
	spf_time_anchor_v1_t copy = *anchor;
	copy.crc32 = 0;
	return spf_gain_meta_crc32(&copy, sizeof(copy));
}

void spf_time_anchor_query_init(
	spf_time_anchor_query_v1_t *query,
	uint64_t request_id)
{
	memset(query, 0, sizeof(*query));
	query->magic = SPF_TIME_ANCHOR_QUERY_MAGIC;
	query->message_bytes = sizeof(*query);
	query->version = SPF_TIME_ANCHOR_VERSION;
	query->request_id = request_id;
	query->crc32 = query_crc(query);
}

bool spf_time_anchor_query_validate(const spf_time_anchor_query_v1_t *query)
{
	return query != NULL && query->magic == SPF_TIME_ANCHOR_QUERY_MAGIC &&
		query->message_bytes == sizeof(*query) &&
		query->version == SPF_TIME_ANCHOR_VERSION &&
		query->request_id != 0 && query->reserved0 == 0 &&
		query->crc32 == query_crc(query);
}

bool spf_time_anchor_validate(const spf_time_anchor_v1_t *anchor)
{
	if (anchor == NULL || anchor->magic != SPF_TIME_ANCHOR_MAGIC ||
		anchor->message_bytes != sizeof(*anchor) ||
		anchor->version != SPF_TIME_ANCHOR_VERSION ||
		(anchor->flags & ~SPF_TIME_ANCHOR_KNOWN_FLAGS) != 0 ||
		anchor->request_id == 0 || anchor->reserved0 != 0 ||
		anchor->reserved1 != 0 || anchor->crc32 != anchor_crc(anchor))
		return false;

	if ((anchor->flags & SPF_TIME_ANCHOR_COUNTER_INTERVAL_VALID) == 0 ||
		(anchor->flags & SPF_TIME_ANCHOR_MONOTONIC_INTERVAL_VALID) == 0 ||
		(anchor->flags & SPF_TIME_ANCHOR_COUNTER_LOW32) == 0)
		return false;
	if ((anchor->sample_counter_before >> 32) != 0 ||
		(anchor->sample_counter_after >> 32) != 0 ||
		anchor->radio_monotonic_after_ns < anchor->radio_monotonic_before_ns)
		return false;

	const uint32_t delta = (uint32_t)anchor->sample_counter_after -
		(uint32_t)anchor->sample_counter_before;
	if (delta >= UINT32_C(0x80000000))
		return false;
	return ((anchor->flags & SPF_TIME_ANCHOR_COUNTER_ADVANCED) != 0) ==
		(delta != 0);
}

bool spf_time_anchor_reader_init(spf_time_anchor_reader_t *reader)
{
	if (reader == NULL)
		return false;
	memset(reader, 0, sizeof(*reader));
	reader->context = iio_create_local_context();
	if (reader->context == NULL)
		return false;
	reader->rx = iio_context_find_device(reader->context, "cf-ad9361-lpc");
	if (reader->rx == NULL)
	{
		spf_time_anchor_reader_destroy(reader);
		return false;
	}
	uint32_t first = 0;
	uint32_t second = 0;
	if (iio_device_reg_read(
			reader->rx, SPF_ADC_SAMPLE_COUNTER_LOW_REG, &first) != 0 ||
		iio_device_reg_read(
			reader->rx, SPF_ADC_SAMPLE_COUNTER_LOW_REG, &second) != 0)
	{
		spf_time_anchor_reader_destroy(reader);
		return false;
	}
	/*
	 * The daemon starts before host-side radio configuration on some images.
	 * A readable but stationary counter is therefore valid at boot. Protocol-v3
	 * RX startup independently proves that the same counter advances before it
	 * accepts a stream, so this does not weaken the stale-HDL capture gate.
	 */
	return true;
}

void spf_time_anchor_reader_destroy(spf_time_anchor_reader_t *reader)
{
	if (reader == NULL)
		return;
	if (reader->context != NULL)
		iio_context_destroy(reader->context);
	memset(reader, 0, sizeof(*reader));
}

bool spf_time_anchor_capture(
	spf_time_anchor_reader_t *reader,
	uint64_t request_id,
	spf_time_anchor_v1_t *anchor)
{
	if (reader == NULL || reader->rx == NULL || anchor == NULL ||
		request_id == 0)
		return false;

	memset(anchor, 0, sizeof(*anchor));
	anchor->magic = SPF_TIME_ANCHOR_MAGIC;
	anchor->message_bytes = sizeof(*anchor);
	anchor->version = SPF_TIME_ANCHOR_VERSION;
	anchor->request_id = request_id;

	struct timespec before;
	struct timespec after;
	uint32_t counter_before = 0;
	uint32_t counter_after = 0;
	if (clock_gettime(CLOCK_MONOTONIC_RAW, &before) != 0 ||
		iio_device_reg_read(
			reader->rx, SPF_ADC_SAMPLE_COUNTER_LOW_REG, &counter_before) != 0 ||
		iio_device_reg_read(
			reader->rx, SPF_ADC_SAMPLE_COUNTER_LOW_REG, &counter_after) != 0 ||
		clock_gettime(CLOCK_MONOTONIC_RAW, &after) != 0)
		return false;

	anchor->radio_monotonic_before_ns = timespec_ns(&before);
	anchor->sample_counter_before = counter_before;
	anchor->sample_counter_after = counter_after;
	anchor->radio_monotonic_after_ns = timespec_ns(&after);
	anchor->flags = SPF_TIME_ANCHOR_COUNTER_INTERVAL_VALID |
		SPF_TIME_ANCHOR_MONOTONIC_INTERVAL_VALID |
		SPF_TIME_ANCHOR_COUNTER_LOW32;
	if ((uint32_t)(counter_after - counter_before) != 0)
		anchor->flags |= SPF_TIME_ANCHOR_COUNTER_ADVANCED;
	anchor->crc32 = anchor_crc(anchor);
	return spf_time_anchor_validate(anchor);
}
