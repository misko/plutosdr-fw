#ifndef SPF_TIME_ANCHOR_H
#define SPF_TIME_ANCHOR_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

struct iio_context;
struct iio_device;

#define SPF_TIME_ANCHOR_QUERY_MAGIC UINT32_C(0x31515453) /* "STQ1" */
#define SPF_TIME_ANCHOR_MAGIC UINT32_C(0x31415453) /* "STA1" */
#define SPF_TIME_ANCHOR_VERSION UINT16_C(1)

#define SPF_TIME_ANCHOR_COUNTER_INTERVAL_VALID (UINT32_C(1) << 0)
#define SPF_TIME_ANCHOR_MONOTONIC_INTERVAL_VALID (UINT32_C(1) << 1)
#define SPF_TIME_ANCHOR_COUNTER_LOW32 (UINT32_C(1) << 2)
#define SPF_TIME_ANCHOR_COUNTER_ADVANCED (UINT32_C(1) << 3)
#define SPF_TIME_ANCHOR_KNOWN_FLAGS \
	(SPF_TIME_ANCHOR_COUNTER_INTERVAL_VALID | \
	 SPF_TIME_ANCHOR_MONOTONIC_INTERVAL_VALID | \
	 SPF_TIME_ANCHOR_COUNTER_LOW32 | \
	 SPF_TIME_ANCHOR_COUNTER_ADVANCED)

#define SPF_ADC_SAMPLE_COUNTER_LOW_REG UINT32_C(0x800000B8)

#pragma pack(push, 1)
typedef struct
{
	uint32_t magic;
	uint16_t message_bytes;
	uint16_t version;
	uint64_t request_id;
	uint32_t reserved0;
	uint32_t crc32;
} spf_time_anchor_query_v1_t;

/*
 * This response is byte-for-byte identical over FunctionFS USB control and
 * direct-IP UDP control. The host brackets the exchange with its own
 * monotonic clock. The radio fields describe the smaller interval in which
 * the coherent FPGA counter was observed.
 *
 * Only the coherent low 32 counter bits are CPU-visible. Consumers extend
 * both values near an inline 64-bit frame counter; COUNTER_LOW32 makes that
 * limitation explicit and prevents accidental use as an absolute counter.
 */
typedef struct
{
	uint32_t magic;
	uint16_t message_bytes;
	uint16_t version;
	uint32_t flags;
	uint32_t reserved0;
	uint64_t request_id;
	uint64_t radio_monotonic_before_ns;
	uint64_t sample_counter_before;
	uint64_t sample_counter_after;
	uint64_t radio_monotonic_after_ns;
	uint32_t reserved1;
	uint32_t crc32;
} spf_time_anchor_v1_t;
#pragma pack(pop)

_Static_assert(sizeof(spf_time_anchor_query_v1_t) == 24,
	"time-anchor query must remain 24 bytes");
_Static_assert(sizeof(spf_time_anchor_v1_t) == 64,
	"time-anchor response must remain 64 bytes");

typedef struct
{
	struct iio_context *context;
	struct iio_device *rx;
} spf_time_anchor_reader_t;

void spf_time_anchor_query_init(
	spf_time_anchor_query_v1_t *query,
	uint64_t request_id);
bool spf_time_anchor_query_validate(const spf_time_anchor_query_v1_t *query);
bool spf_time_anchor_validate(const spf_time_anchor_v1_t *anchor);

bool spf_time_anchor_reader_init(spf_time_anchor_reader_t *reader);
void spf_time_anchor_reader_destroy(spf_time_anchor_reader_t *reader);
bool spf_time_anchor_capture(
	spf_time_anchor_reader_t *reader,
	uint64_t request_id,
	spf_time_anchor_v1_t *anchor);

#endif
