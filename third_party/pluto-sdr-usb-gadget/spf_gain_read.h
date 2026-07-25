#ifndef SPF_GAIN_READ_H
#define SPF_GAIN_READ_H

#include <stdbool.h>
#include <stdint.h>

#include <iio.h>

#define SPF_AD936X_REG_GAIN_RX1 UINT32_C(0x2B0)
#define SPF_AD936X_REG_GAIN_RX2 UINT32_C(0x2B5)
#define SPF_AD936X_GAIN_MASK UINT32_C(0x7F)
#define SPF_AD936X_SPLIT_GAIN_ATTR "adi,split-gain-table-mode-enable"

typedef struct
{
	uint8_t rx1;
	uint8_t rx2;
	bool valid;
	uint32_t duration_ns;
} spf_gain_pair_t;

typedef int (*spf_gain_reg_read_fn)(
	struct iio_device *device,
	uint32_t address,
	uint32_t *value);

spf_gain_pair_t spf_gain_read_pair(struct iio_device *phy);

spf_gain_pair_t spf_gain_read_pair_with(
	struct iio_device *phy,
	spf_gain_reg_read_fn reg_read);

bool spf_gain_is_full_table_mode(struct iio_device *phy);

#endif
