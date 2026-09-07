// SPDX-License-Identifier: GPL-2.0-or-later
#include "starlink_pss_m2_qualification.h"

#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

static int fail(char *error, size_t error_size, const char *format, ...)
{
	va_list arguments;

	if (error && error_size) {
		va_start(arguments, format);
		vsnprintf(error, error_size, format, arguments);
		va_end(arguments);
	}
	return -1;
}

int pss_m2_plan_case(uint64_t current_index, uint64_t latest_map_start,
	uint32_t requested_phase, struct pss_m2_case_plan *plan,
	char *error, size_t error_size)
{
	const uint64_t tile_samples =
		(uint64_t)PSS_MAP_PHASE_BINS * PSS_MAP_TILE_FRAMES;
	uint64_t target, minimum_start, injection_lead;
	uint32_t delta;

	if (!plan)
		return fail(error, error_size, "missing M2 case-plan destination");
	if (requested_phase >= PSS_MAP_PHASE_BINS)
		return fail(error, error_size,
			"M2 requested phase %" PRIu32 " is out of range",
			requested_phase);
	if (current_index > UINT64_MAX - PSS_M2_TARGET_SAFETY_LEAD)
		return fail(error, error_size, "M2 current index cannot accept safety lead");
	minimum_start = current_index + PSS_M2_TARGET_SAFETY_LEAD;
	delta = (PSS_M2_TEMPLATE_OFFSET + PSS_MAP_PHASE_BINS -
		requested_phase) % PSS_MAP_PHASE_BINS;
	injection_lead = PSS_M2_WARMUP_SAMPLES + delta;
	if (latest_map_start > UINT64_MAX - tile_samples)
		return fail(error, error_size, "M2 next target-map start overflows");
	target = latest_map_start + tile_samples;
	for (;;) {
		if (target >= injection_lead &&
		    target - injection_lead >= minimum_start)
			break;
		if (target > UINT64_MAX - tile_samples)
			return fail(error, error_size,
				"M2 cannot find a future target-map boundary");
		target += tile_samples;
	}
	if (target - injection_lead >
	    UINT64_MAX - PSS_INJECTION_LAST_SAMPLE_OFFSET)
		return fail(error, error_size, "M2 injection interval overflows");
	plan->requested_phase = requested_phase;
	plan->injection_delta = delta;
	plan->injection_start = target - injection_lead;
	plan->target_map_start = target;
	return 0;
}

int pss_m2_build_expected_map(const uint8_t *period_scores,
	size_t score_count, const struct pss_m2_case_plan *plan,
	uint16_t *expected_map, size_t map_words,
	char *error, size_t error_size)
{
	size_t phase;

	if (!period_scores || score_count != PSS_MAP_PHASE_BINS || !plan ||
	    !expected_map || map_words != PSS_MAP_PHASE_BINS)
		return fail(error, error_size, "invalid M2 expected-map geometry");
	if (plan->requested_phase >= PSS_MAP_PHASE_BINS ||
	    plan->injection_delta >= PSS_MAP_PHASE_BINS ||
	    plan->injection_start > UINT64_MAX - PSS_M2_WARMUP_SAMPLES -
		plan->injection_delta ||
	    plan->injection_start + PSS_M2_WARMUP_SAMPLES +
		plan->injection_delta != plan->target_map_start)
		return fail(error, error_size, "invalid M2 case-plan relationship");
	for (phase = 0; phase < PSS_MAP_PHASE_BINS; ++phase) {
		size_t profile_index =
			(phase + plan->injection_delta) % PSS_MAP_PHASE_BINS;

		expected_map[phase] =
			(uint16_t)((uint16_t)period_scores[profile_index] *
				PSS_MAP_TILE_FRAMES);
	}
	return 0;
}

int pss_m2_check_map(const uint16_t *actual_map, size_t actual_words,
	const uint16_t *expected_map, size_t expected_words,
	uint32_t requested_phase, struct pss_m2_map_result *result,
	char *error, size_t error_size)
{
	uint16_t peak = 0U, runner = 0U, expected_peak, expected_runner = 0U;
	uint32_t peak_phase = 0U, peak_count = 0U;
	size_t phase;

	if (!actual_map || actual_words != PSS_MAP_PHASE_BINS || !expected_map ||
	    expected_words != PSS_MAP_PHASE_BINS || !result ||
	    requested_phase >= PSS_MAP_PHASE_BINS)
		return fail(error, error_size, "invalid M2 map-check geometry");
	memset(result, 0, sizeof(*result));
	result->requested_phase = requested_phase;
	result->first_mismatch_phase = UINT32_MAX;
	expected_peak = expected_map[requested_phase];
	if (!expected_peak)
		return fail(error, error_size, "M2 expected timing peak is zero");
	for (phase = 0; phase < PSS_MAP_PHASE_BINS; ++phase) {
		uint16_t value = actual_map[phase];
		uint16_t expected = expected_map[phase];

		if (phase != requested_phase) {
			if (expected >= expected_peak)
				return fail(error, error_size,
					"M2 expected timing peak is not unique");
			if (expected > expected_runner)
				expected_runner = expected;
		}

		if (value > peak) {
			runner = peak;
			peak = value;
			peak_phase = (uint32_t)phase;
			peak_count = 1U;
		} else if (value == peak) {
			peak_count++;
		} else if (value > runner) {
			runner = value;
		}
		if (value != expected_map[phase]) {
			if (!result->mismatch_count) {
				result->first_mismatch_phase = (uint32_t)phase;
				result->first_mismatch_expected = expected_map[phase];
				result->first_mismatch_actual = value;
			}
			result->mismatch_count++;
		}
	}
	result->actual_peak_phase = peak_phase;
	result->actual_peak_value = peak;
	result->actual_runner_up_value = runner;
	result->unique_peak = peak_count == 1U;
	result->timing_qualified = result->unique_peak &&
		peak_phase == requested_phase && peak == expected_peak &&
		runner == expected_runner;
	result->exact = !result->mismatch_count && result->timing_qualified;
	return 0;
}
