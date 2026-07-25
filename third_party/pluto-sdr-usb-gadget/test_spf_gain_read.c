#include "spf_gain_read.h"
#include "spf_gain_metadata.h"

#include <stdio.h>

static int failure_address = -1;

static int fake_reg_read(
	struct iio_device *device,
	uint32_t address,
	uint32_t *value)
{
	(void)device;
	if ((int)address == failure_address)
		return -1;
	if (address == SPF_AD936X_REG_GAIN_RX1)
		*value = UINT32_C(0xEA); /* mask to 106 */
	else if (address == SPF_AD936X_REG_GAIN_RX2)
		*value = UINT32_C(0xAB); /* mask to 43 */
	else
		return -1;
	return 0;
}

int main(void)
{
	spf_gain_pair_t pair =
		spf_gain_read_pair_with(NULL, fake_reg_read);
	if (!pair.valid || pair.rx1 != 106 || pair.rx2 != 43)
	{
		fprintf(stderr, "valid gain pair mismatch\n");
		return 1;
	}

	failure_address = SPF_AD936X_REG_GAIN_RX1;
	pair = spf_gain_read_pair_with(NULL, fake_reg_read);
	if (pair.valid ||
		pair.rx1 != SPF_GAIN_INDEX_INVALID ||
		pair.rx2 != SPF_GAIN_INDEX_INVALID)
	{
		fprintf(stderr, "RX1 failure did not invalidate pair\n");
		return 1;
	}

	failure_address = SPF_AD936X_REG_GAIN_RX2;
	pair = spf_gain_read_pair_with(NULL, fake_reg_read);
	if (pair.valid ||
		pair.rx1 != SPF_GAIN_INDEX_INVALID ||
		pair.rx2 != SPF_GAIN_INDEX_INVALID)
	{
		fprintf(stderr, "RX2 failure did not invalidate pair\n");
		return 1;
	}
	return 0;
}
