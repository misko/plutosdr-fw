#ifndef SPF_GAIN_READ_H
#define SPF_GAIN_READ_H

#include <stdbool.h>
#include <stdint.h>

#include <iio.h>

#define SPF_AD936X_REG_GAIN_RX1 UINT32_C(0x2B0)
#define SPF_AD936X_REG_GAIN_RX2 UINT32_C(0x2B5)
#define SPF_AD936X_GAIN_MASK UINT32_C(0x7F)
#define SPF_AD936X_SPLIT_GAIN_ATTR "adi,split-gain-table-mode-enable"
#define SPF_AD936X_DIGITAL_GAIN_ATTR "adi,gc-dig-gain-enable"
#define SPF_AD936X_GAIN_TABLE_ATTR "gain_table_config"
#define SPF_GAIN_TABLE_MAX_ENTRIES UINT32_C(128)

typedef struct
{
	uint8_t rx1;
	uint8_t rx2;
	int8_t rx1_db;
	int8_t rx2_db;
	bool valid;
	uint32_t duration_ns;
} spf_gain_pair_t;

typedef struct
{
	int8_t db_by_index[SPF_GAIN_TABLE_MAX_ENTRIES];
	uint32_t entry_count;
	uint64_t start_frequency_hz;
	uint64_t end_frequency_hz;
	uint32_t fnv1a32;
	bool valid;
} spf_gain_table_t;

typedef int (*spf_gain_reg_read_fn)(
	struct iio_device *device,
	uint32_t address,
	uint32_t *value);

spf_gain_pair_t spf_gain_read_pair(struct iio_device *phy);

spf_gain_pair_t spf_gain_read_pair_with(
	struct iio_device *phy,
	spf_gain_reg_read_fn reg_read);

spf_gain_pair_t spf_gain_read_db_pair(
	struct iio_device *phy,
	const spf_gain_table_t *table);

spf_gain_pair_t spf_gain_read_db_pair_with(
	struct iio_device *phy,
	const spf_gain_table_t *table,
	spf_gain_reg_read_fn reg_read);

bool spf_gain_table_parse(
	const char *text,
	size_t text_bytes,
	uint64_t lo_hz,
	spf_gain_table_t *table);

bool spf_gain_table_load(
	struct iio_device *phy,
	spf_gain_table_t *table);

bool spf_gain_is_full_table_mode(struct iio_device *phy);
bool spf_gain_is_digital_gain_disabled(struct iio_device *phy);

#endif
