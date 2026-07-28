#include "spf_rssi_read.h"
#include "spf_gain_metadata.h"

#include <stdio.h>
#include <string.h>

static ssize_t fake_attr_read(
	const struct iio_channel *channel,
	const char *attribute,
	char *destination,
	size_t destination_bytes)
{
	if (strcmp(attribute, SPF_RSSI_ATTR) != 0)
		return -1;
	const char *value = channel == (const struct iio_channel *)1
		? "111.25 dB\n"
		: "87.50 dB\n";
	size_t bytes = strlen(value);
	if (bytes + 1 > destination_bytes)
		return -1;
	memcpy(destination, value, bytes + 1);
	return (ssize_t)bytes;
}

int main(void)
{
	uint16_t qdb = 0;
	if (!spf_rssi_parse_qdb("111.25 dB\n", &qdb) || qdb != 445)
	{
		fprintf(stderr, "RSSI quarter-dB parse mismatch\n");
		return 1;
	}
	if (spf_rssi_parse_qdb("-12.00 dB\n", &qdb) ||
		spf_rssi_parse_qdb("12.10 dB\n", &qdb) ||
		spf_rssi_parse_qdb("12.00 dBm\n", &qdb))
	{
		fprintf(stderr, "invalid RSSI text unexpectedly accepted\n");
		return 1;
	}

	spf_rssi_pair_t pair = spf_rssi_read_pair_with(
		(const struct iio_channel *)1,
		(const struct iio_channel *)2,
		fake_attr_read);
	if (!pair.valid || pair.rx1_qdb != 445 || pair.rx2_qdb != 350)
	{
		fprintf(stderr, "RSSI pair mismatch\n");
		return 1;
	}

	pair = spf_rssi_read_pair_with(
		NULL,
		(const struct iio_channel *)2,
		fake_attr_read);
	if (pair.valid ||
		pair.rx1_qdb != SPF_RSSI_QDB_INVALID ||
		pair.rx2_qdb != SPF_RSSI_QDB_INVALID)
	{
		fprintf(stderr, "RSSI failure did not invalidate pair\n");
		return 1;
	}
	return 0;
}
