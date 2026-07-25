#define _POSIX_C_SOURCE 200809L

#include "spf_gain_read.h"
#include "spf_gain_metadata.h"

#include <limits.h>
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
