#ifndef SPF_RSSI_READ_H
#define SPF_RSSI_READ_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <iio.h>

#define SPF_RSSI_ATTR "rssi"
#define SPF_RSSI_QDB_MAX UINT16_C(511)

typedef struct
{
	uint16_t rx1_qdb;
	uint16_t rx2_qdb;
	bool valid;
	uint32_t duration_ns;
} spf_rssi_pair_t;

typedef ssize_t (*spf_rssi_attr_read_fn)(
	const struct iio_channel *channel,
	const char *attribute,
	char *destination,
	size_t destination_bytes);

spf_rssi_pair_t spf_rssi_read_pair(struct iio_device *phy);

spf_rssi_pair_t spf_rssi_read_pair_with(
	const struct iio_channel *rx1,
	const struct iio_channel *rx2,
	spf_rssi_attr_read_fn attr_read);

bool spf_rssi_parse_qdb(
	const char *text,
	uint16_t *qdb);

#endif
