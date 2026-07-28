#include "spf_gain_read.h"
#include "spf_gain_metadata.h"

#include <stdio.h>

static int failure_address = -1;
static uint32_t fake_rx1 = UINT32_C(0xEA);
static uint32_t fake_rx2 = UINT32_C(0xAB);

static int fake_reg_read(
	struct iio_device *device,
	uint32_t address,
	uint32_t *value)
{
	(void)device;
	if ((int)address == failure_address)
		return -1;
	if (address == SPF_AD936X_REG_GAIN_RX1)
		*value = fake_rx1;
	else if (address == SPF_AD936X_REG_GAIN_RX2)
		*value = fake_rx2;
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

	failure_address = -1;
	const char table_text[] =
		"<gaintable AD9361 type=FULL dest=3 start=4000000000 end=6000000000>\n"
		"-10, 0x00, 0x00, 0x00\n"
		"-10, 0x00, 0x00, 0x00\n"
		"-9, 0x00, 0x00, 0x00\n"
		"20, 0x00, 0x00, 0x00\n"
		"</gaintable>\n";
	spf_gain_table_t table;
	if (!spf_gain_table_parse(
			table_text,
			sizeof(table_text) - 1,
			UINT64_C(5766000000),
			&table) ||
		table.entry_count != 4 ||
		table.db_by_index[0] != -10 ||
		table.db_by_index[3] != 20)
	{
		fprintf(stderr, "valid gain table did not parse\n");
		return 1;
	}

	fake_rx1 = 1;
	fake_rx2 = 3;
	pair = spf_gain_read_db_pair_with(NULL, &table, fake_reg_read);
	if (!pair.valid ||
		pair.rx1 != 1 ||
		pair.rx2 != 3 ||
		pair.rx1_db != -10 ||
		pair.rx2_db != 20)
	{
		fprintf(stderr, "gain dB lookup mismatch\n");
		return 1;
	}

	if (spf_gain_table_parse(
			table_text,
			sizeof(table_text) - 1,
			UINT64_C(2400000000),
			&table))
	{
		fprintf(stderr, "out-of-range LO unexpectedly accepted\n");
		return 1;
	}
	return 0;
}
