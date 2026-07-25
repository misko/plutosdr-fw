#define _POSIX_C_SOURCE 200809L

#include "spf_gain_read.h"
#include "spf_gain_metadata.h"

#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static uint32_t elapsed_ns(
	const struct timespec *before,
	const struct timespec *after)
{
	uint64_t elapsed =
		(uint64_t)(after->tv_sec - before->tv_sec) * UINT64_C(1000000000);
	if (after->tv_nsec >= before->tv_nsec)
		elapsed += (uint64_t)(after->tv_nsec - before->tv_nsec);
	else
		elapsed -= (uint64_t)(before->tv_nsec - after->tv_nsec);
	return elapsed > UINT32_MAX ? UINT32_MAX : (uint32_t)elapsed;
}

spf_gain_pair_t spf_gain_read_pair(struct iio_device *phy)
{
	return spf_gain_read_pair_with(phy, iio_device_reg_read);
}

spf_gain_pair_t spf_gain_read_pair_with(
	struct iio_device *phy,
	spf_gain_reg_read_fn reg_read)
{
	spf_gain_pair_t result = {
		.rx1 = SPF_GAIN_INDEX_INVALID,
		.rx2 = SPF_GAIN_INDEX_INVALID,
		.rx1_db = SPF_GAIN_DB_INVALID,
		.rx2_db = SPF_GAIN_DB_INVALID,
		.valid = false,
		.duration_ns = 0,
	};
	struct timespec before = {0, 0};
	struct timespec after = {0, 0};
	uint32_t rx1_raw = 0;
	uint32_t rx2_raw = 0;

	clock_gettime(CLOCK_MONOTONIC_RAW, &before);
	int rc1 = reg_read(phy, SPF_AD936X_REG_GAIN_RX1, &rx1_raw);
	int rc2 = reg_read(phy, SPF_AD936X_REG_GAIN_RX2, &rx2_raw);
	clock_gettime(CLOCK_MONOTONIC_RAW, &after);
	result.duration_ns = elapsed_ns(&before, &after);

	if (rc1 == 0 && rc2 == 0)
	{
		result.rx1 = (uint8_t)(rx1_raw & SPF_AD936X_GAIN_MASK);
		result.rx2 = (uint8_t)(rx2_raw & SPF_AD936X_GAIN_MASK);
		result.valid = true;
	}
	return result;
}

spf_gain_pair_t spf_gain_read_db_pair(
	struct iio_device *phy,
	const spf_gain_table_t *table)
{
	return spf_gain_read_db_pair_with(phy, table, iio_device_reg_read);
}

spf_gain_pair_t spf_gain_read_db_pair_with(
	struct iio_device *phy,
	const spf_gain_table_t *table,
	spf_gain_reg_read_fn reg_read)
{
	spf_gain_pair_t result = spf_gain_read_pair_with(phy, reg_read);
	if (!result.valid ||
		!table ||
		!table->valid ||
		result.rx1 >= table->entry_count ||
		result.rx2 >= table->entry_count)
	{
		result.valid = false;
		result.rx1_db = SPF_GAIN_DB_INVALID;
		result.rx2_db = SPF_GAIN_DB_INVALID;
		return result;
	}

	result.rx1_db = table->db_by_index[result.rx1];
	result.rx2_db = table->db_by_index[result.rx2];
	return result;
}

static uint32_t fnv1a32(const char *data, size_t bytes)
{
	uint32_t hash = UINT32_C(2166136261);
	for (size_t idx = 0; idx < bytes; ++idx)
	{
		hash ^= (uint8_t)data[idx];
		hash *= UINT32_C(16777619);
	}
	return hash;
}

bool spf_gain_table_parse(
	const char *text,
	size_t text_bytes,
	uint64_t lo_hz,
	spf_gain_table_t *table)
{
	if (!text || !table || text_bytes == 0 || text_bytes > 4096)
		return false;

	memset(table, 0, sizeof(*table));
	char copy[4097];
	memcpy(copy, text, text_bytes);
	copy[text_bytes] = '\0';

	unsigned int model = 0;
	unsigned int destination = 0;
	unsigned long long start_hz = 0;
	unsigned long long end_hz = 0;
	char mode[16] = {0};
	if (sscanf(
			copy,
			"<gaintable AD%u type=%15s dest=%u start=%llu end=%llu>",
			&model,
			mode,
			&destination,
			&start_hz,
			&end_hz) != 5 ||
		model != 9361 ||
		strcmp(mode, "FULL") != 0 ||
		destination != 3 ||
		start_hz >= end_hz ||
		!((uint64_t)start_hz < lo_hz && lo_hz <= (uint64_t)end_hz))
	{
		return false;
	}

	char *save = NULL;
	char *line = strtok_r(copy, "\n", &save);
	bool footer_seen = false;
	int previous_db = INT_MIN;
	while ((line = strtok_r(NULL, "\n", &save)) != NULL)
	{
		if (strcmp(line, "</gaintable>") == 0)
		{
			footer_seen = true;
			break;
		}

		int gain_db = 0;
		unsigned int byte0 = 0;
		unsigned int byte1 = 0;
		unsigned int byte2 = 0;
		if (sscanf(
				line,
				" %d, 0x%x, 0x%x, 0x%x",
				&gain_db,
				&byte0,
				&byte1,
				&byte2) != 4 ||
			table->entry_count >= SPF_GAIN_TABLE_MAX_ENTRIES ||
			gain_db < INT8_MIN + 1 ||
			gain_db > INT8_MAX ||
			gain_db < previous_db ||
			byte0 > UINT8_MAX ||
			byte1 > UINT8_MAX ||
			byte2 > UINT8_MAX)
		{
			memset(table, 0, sizeof(*table));
			return false;
		}
		table->db_by_index[table->entry_count++] = (int8_t)gain_db;
		previous_db = gain_db;
	}

	if (!footer_seen || table->entry_count == 0)
	{
		memset(table, 0, sizeof(*table));
		return false;
	}

	table->start_frequency_hz = (uint64_t)start_hz;
	table->end_frequency_hz = (uint64_t)end_hz;
	table->fnv1a32 = fnv1a32(text, text_bytes);
	table->valid = true;
	return true;
}

bool spf_gain_table_load(
	struct iio_device *phy,
	spf_gain_table_t *table)
{
	char text[4097];
	ssize_t bytes = iio_device_attr_read(
		phy,
		SPF_AD936X_GAIN_TABLE_ATTR,
		text,
		sizeof(text) - 1);
	if (bytes <= 0 || bytes >= (ssize_t)sizeof(text))
		return false;
	text[bytes] = '\0';

	struct iio_channel *rx_lo =
		iio_device_find_channel(phy, "altvoltage0", true);
	long long lo_hz = 0;
	if (!rx_lo ||
		iio_channel_attr_read_longlong(rx_lo, "frequency", &lo_hz) < 0 ||
		lo_hz <= 0)
	{
		return false;
	}

	return spf_gain_table_parse(text, (size_t)bytes, (uint64_t)lo_hz, table);
}

bool spf_gain_is_full_table_mode(struct iio_device *phy)
{
	bool split_table = false;
	return
		iio_device_debug_attr_read_bool(
			phy,
			SPF_AD936X_SPLIT_GAIN_ATTR,
			&split_table) == 0 &&
		!split_table;
}

bool spf_gain_is_digital_gain_disabled(struct iio_device *phy)
{
	bool digital_gain = true;
	return
		iio_device_debug_attr_read_bool(
			phy,
			SPF_AD936X_DIGITAL_GAIN_ATTR,
			&digital_gain) == 0 &&
		!digital_gain;
}
