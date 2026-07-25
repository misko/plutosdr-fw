#define _POSIX_C_SOURCE 200809L

#include "spf_rssi_read.h"
#include "spf_gain_metadata.h"

#include <stdio.h>
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

bool spf_rssi_parse_qdb(
	const char *text,
	uint16_t *qdb)
{
	if (!text || !qdb)
		return false;

	double db = 0.0;
	char unit[3] = {0};
	char extra = '\0';
	if (sscanf(text, " %lf %2s %c", &db, unit, &extra) != 2 ||
		strcmp(unit, "dB") != 0 ||
		db < 0.0 ||
		db > 127.75)
	{
		return false;
	}

	double scaled = db * 4.0;
	uint16_t rounded = (uint16_t)(scaled + 0.5);
	double error = scaled - (double)rounded;
	if (error < -0.001 || error > 0.001 || rounded > SPF_RSSI_QDB_MAX)
		return false;
	*qdb = rounded;
	return true;
}

spf_rssi_pair_t spf_rssi_read_pair(struct iio_device *phy)
{
	const struct iio_channel *rx1 =
		iio_device_find_channel(phy, "voltage0", false);
	const struct iio_channel *rx2 =
		iio_device_find_channel(phy, "voltage1", false);
	return spf_rssi_read_pair_with(rx1, rx2, iio_channel_attr_read);
}

spf_rssi_pair_t spf_rssi_read_pair_with(
	const struct iio_channel *rx1,
	const struct iio_channel *rx2,
	spf_rssi_attr_read_fn attr_read)
{
	spf_rssi_pair_t result = {
		.rx1_qdb = SPF_RSSI_QDB_INVALID,
		.rx2_qdb = SPF_RSSI_QDB_INVALID,
		.valid = false,
		.duration_ns = 0,
	};
	char rx1_text[32] = {0};
	char rx2_text[32] = {0};
	struct timespec before = {0, 0};
	struct timespec after = {0, 0};

	clock_gettime(CLOCK_MONOTONIC_RAW, &before);
	ssize_t rc1 = rx1 && attr_read
		? attr_read(rx1, SPF_RSSI_ATTR, rx1_text, sizeof(rx1_text))
		: -1;
	ssize_t rc2 = rx2 && attr_read
		? attr_read(rx2, SPF_RSSI_ATTR, rx2_text, sizeof(rx2_text))
		: -1;
	clock_gettime(CLOCK_MONOTONIC_RAW, &after);
	result.duration_ns = elapsed_ns(&before, &after);

	if (rc1 > 0 &&
		rc1 < (ssize_t)sizeof(rx1_text) &&
		rc2 > 0 &&
		rc2 < (ssize_t)sizeof(rx2_text) &&
		spf_rssi_parse_qdb(rx1_text, &result.rx1_qdb) &&
		spf_rssi_parse_qdb(rx2_text, &result.rx2_qdb))
	{
		result.valid = true;
	}
	else
	{
		result.rx1_qdb = SPF_RSSI_QDB_INVALID;
		result.rx2_qdb = SPF_RSSI_QDB_INVALID;
	}
	return result;
}
