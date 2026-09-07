// SPDX-License-Identifier: GPL-2.0-or-later
#include "starlink_pss_m2_qualification.h"

#include <stdio.h>
#include <string.h>

#define ERROR_SIZE 256U

static unsigned int failures;

#define CHECK(condition, message) \
	do { \
		if (!(condition)) { \
			fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, message); \
			failures++; \
		} \
	} while (0)

static void test_edge_phase_plans(void)
{
	const uint64_t tile =
		(uint64_t)PSS_MAP_PHASE_BINS * PSS_MAP_TILE_FRAMES;
	const uint64_t current = UINT64_C(2280000);
	const uint64_t latest = UINT64_C(1000000);
	const uint32_t phases[] = {0U, 1U, 32U, 129U, 10000U, 19999U};
	char error[ERROR_SIZE] = {0};
	size_t index;

	for (index = 0; index < sizeof(phases) / sizeof(phases[0]); ++index) {
		struct pss_m2_case_plan plan;
		uint32_t expected_delta =
			(PSS_M2_TEMPLATE_OFFSET + PSS_MAP_PHASE_BINS - phases[index]) %
			PSS_MAP_PHASE_BINS;

		CHECK(pss_m2_plan_case(current, latest, phases[index], &plan,
			error, sizeof(error)) == 0, error);
		CHECK(plan.injection_delta == expected_delta, "wrong injection delta");
		CHECK(plan.target_map_start > latest, "target map is not future");
		CHECK((plan.target_map_start - latest) % tile == 0U,
			"target lost acquisition-map boundary");
		CHECK(plan.injection_start + PSS_M2_WARMUP_SAMPLES +
			expected_delta == plan.target_map_start,
			"injection start does not map to target");
		CHECK(plan.target_map_start - plan.injection_start >=
			PSS_M2_WARMUP_SAMPLES,
			"target lacks a complete deterministic warm-up period");
		CHECK(plan.injection_start >= current + PSS_M2_TARGET_SAFETY_LEAD,
			"target lacks host scheduling safety lead");
	}
}

static void test_expected_map_and_exact_check(void)
{
	uint8_t scores[PSS_MAP_PHASE_BINS] = {0};
	uint16_t expected[PSS_MAP_PHASE_BINS];
	uint16_t actual[PSS_MAP_PHASE_BINS];
	struct pss_m2_case_plan plan = {
		.requested_phase = 19999U,
		.injection_delta = 33U,
		.injection_start = UINT64_C(10000000),
		.target_map_start = UINT64_C(10020033),
	};
	struct pss_m2_map_result result;
	char error[ERROR_SIZE] = {0};

	scores[PSS_M2_TEMPLATE_OFFSET] = 255U;
	scores[PSS_M2_TEMPLATE_OFFSET + 1U] = 116U;
	CHECK(pss_m2_build_expected_map(scores, PSS_MAP_PHASE_BINS, &plan,
		expected, PSS_MAP_PHASE_BINS, error, sizeof(error)) == 0, error);
	memcpy(actual, expected, sizeof(actual));
	CHECK(expected[19999U] == 16320U, "wrapped expected peak changed");
	CHECK(pss_m2_check_map(actual, PSS_MAP_PHASE_BINS,
		expected, PSS_MAP_PHASE_BINS, 19999U, &result,
		error, sizeof(error)) == 0, error);
	CHECK(result.exact && result.unique_peak &&
		result.actual_peak_phase == 19999U &&
		result.actual_peak_value == 16320U &&
		result.actual_runner_up_value == 7424U,
		"exact wrapped map did not qualify");
	actual[7]++;
	CHECK(pss_m2_check_map(actual, PSS_MAP_PHASE_BINS,
		expected, PSS_MAP_PHASE_BINS, 19999U, &result,
		error, sizeof(error)) == 0, error);
	CHECK(!result.exact && result.mismatch_count == 1U &&
		result.first_mismatch_phase == 7U,
		"one-word mismatch was not rejected exactly");
}

static void test_invalid_inputs(void)
{
	struct pss_m2_case_plan plan;
	char error[ERROR_SIZE] = {0};

	CHECK(pss_m2_plan_case(0U, 0U, PSS_MAP_PHASE_BINS, &plan,
		error, sizeof(error)) < 0, "out-of-range phase was accepted");
	CHECK(pss_m2_plan_case(UINT64_MAX, 0U, 0U, &plan,
		error, sizeof(error)) < 0, "overflowing current index was accepted");
}

int main(void)
{
	test_edge_phase_plans();
	test_expected_map_and_exact_check();
	test_invalid_inputs();
	if (failures) {
		fprintf(stderr, "PSS_M2_QUALIFICATION_TEST_FAIL failures=%u\n", failures);
		return 1;
	}
	printf("PSS_M2_QUALIFICATION_TEST_PASS phases=6 bins=%u tile_frames=%u\n",
		PSS_MAP_PHASE_BINS, PSS_MAP_TILE_FRAMES);
	return 0;
}
