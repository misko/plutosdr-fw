// SPDX-License-Identifier: GPL-2.0-or-later

#define STARLINK_PSS_MONITOR_V3_NO_MAIN
#include "starlink_pss_acqctl_monitor_v3.c"

#define CHECK(condition, message) do { \
	if (!(condition)) { \
		fprintf(stderr, "FAIL: %s\n", message); \
		return 1; \
	} \
} while (0)

int main(void)
{
	struct pss_map_info info = {0};
	uint32_t rate = 0U, factor = 0U;
	uint64_t source = 0U;
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
	info.version = PSS_MAP_VERSION_1_3;
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

	puts("STARLINK_PSS_MONITOR_V3_PASS cases=8");
	return 0;
}
