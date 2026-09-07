// SPDX-License-Identifier: GPL-2.0-or-later

#define STARLINK_PSS_MONITOR_V3_NO_MAIN
#include "starlink_pss_acqctl_monitor_v3.c"

#define CHECK(condition, message) do { \
	if (!(condition)) { \
		fprintf(stderr, "FAIL: %s\n", message); \
		return 1; \
	} \
} while (0)

struct ddc_mock {
	uint32_t registers[(PSS_MAP_REG_DDC_EMITTED_HI / 4U) + 1U];
};

static int ddc_mock_read(void *context, uint32_t offset, uint32_t *value)
{
	struct ddc_mock *mock = context;

	if (!mock || !value || offset > PSS_MAP_REG_DDC_EMITTED_HI ||
	    (offset & 3U))
		return -1;
	*value = mock->registers[offset / 4U];
	return 0;
}

int main(void)
{
	struct pss_map_info info = {0};
	uint32_t rate = 0U, factor = 0U;
	uint64_t source = 0U;
	struct ddc_mock mock = {0};
	struct pss_map_io io = {.context = &mock, .read32 = ddc_mock_read};
	struct ddc_counters counters = {0};
	(void)run_monitor_v2;
	(void)usage_v2;
	(void)run_monitor_v3;
	(void)usage_v3;

	info.version = PSS_MAP_VERSION_1_1;
	CHECK(monitor_v3_rate(&info, &rate, &factor) && rate == 15U && factor == 1U,
		"15 MS/s was not admitted exactly");
	info.version = PSS_MAP_VERSION_1_2;
	CHECK(monitor_v3_rate(&info, &rate, &factor) && rate == 30U && factor == 2U,
		"30 MS/s was not admitted exactly");
	info.version = PSS_MAP_VERSION_1_4;
	CHECK(monitor_v3_rate(&info, &rate, &factor) && rate == 60U && factor == 4U,
		"60 MS/s was not admitted exactly");
	CHECK(!monitor_v3_rate(NULL, &rate, &factor),
		"missing rate contract was admitted");
	CHECK(project_source_center(UINT64_C(123456), 4U, &source) &&
		source == UINT64_C(493824), "source-center projection is wrong");
	CHECK(!project_source_center(UINT64_MAX, 2U, &source),
		"source-center overflow was admitted");
	CHECK(!project_source_center(1U, 0U, &source),
		"zero decimation factor was admitted");
	CHECK(!project_source_center(1U, 1U, NULL),
		"missing source destination was admitted");
	mock.registers[PSS_MAP_REG_VERSION / 4U] = PSS_MAP_VERSION_1_4;
	mock.registers[PSS_MAP_REG_DDC_ACCEPTED / 4U] = UINT32_C(0x12345678);
	mock.registers[PSS_MAP_REG_DDC_ACCEPTED_HI / 4U] = 1U;
	mock.registers[PSS_MAP_REG_DDC_EMITTED / 4U] = UINT32_C(0x89abcdef);
	mock.registers[PSS_MAP_REG_DDC_EMITTED_HI / 4U] = 2U;
	CHECK(read_ddc_counters(&io, &counters) == 0 &&
		counters.accepted == UINT64_C(0x0000000112345678) &&
		counters.emitted == UINT64_C(0x0000000289abcdef),
		"ABI 1.4 DDC counters did not retain both 32-bit words");
	CHECK(!ddc_counter_saturated(&info, counters.accepted) &&
		ddc_counter_saturated(&info, UINT64_MAX),
		"ABI 1.4 saturation policy is wrong");

	puts("STARLINK_PSS_MONITOR_V3_PASS cases=10");
	return 0;
}
