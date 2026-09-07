// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef STARLINK_PSS_M2_QUALIFICATION_H
#define STARLINK_PSS_M2_QUALIFICATION_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "starlink_pss_acquisition.h"
#include "starlink_pss_periodic_injection.h"

#define PSS_M2_TEMPLATE_OFFSET 32U
#define PSS_M2_WARMUP_SAMPLES UINT64_C(20000)
#define PSS_M2_TARGET_SAFETY_LEAD UINT64_C(500000)

struct pss_m2_case_plan {
	uint32_t requested_phase;
	uint32_t injection_delta;
	uint64_t injection_start;
	uint64_t target_map_start;
};

struct pss_m2_map_result {
	uint32_t requested_phase;
	uint32_t actual_peak_phase;
	uint16_t actual_peak_value;
	uint16_t actual_runner_up_value;
	uint32_t mismatch_count;
	uint32_t first_mismatch_phase;
	uint16_t first_mismatch_expected;
	uint16_t first_mismatch_actual;
	bool unique_peak;
	bool timing_qualified;
	bool exact;
};

int pss_m2_plan_case(uint64_t current_index, uint64_t latest_map_start,
	uint32_t requested_phase, struct pss_m2_case_plan *plan,
	char *error, size_t error_size);
int pss_m2_build_expected_map(const uint8_t *period_scores,
	size_t score_count, const struct pss_m2_case_plan *plan,
	uint16_t *expected_map, size_t map_words,
	char *error, size_t error_size);
int pss_m2_check_map(const uint16_t *actual_map, size_t actual_words,
	const uint16_t *expected_map, size_t expected_words,
	uint32_t requested_phase, struct pss_m2_map_result *result,
	char *error, size_t error_size);

#endif
