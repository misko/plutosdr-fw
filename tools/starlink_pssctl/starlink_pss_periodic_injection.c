// SPDX-License-Identifier: GPL-2.0-or-later
#define _POSIX_C_SOURCE 200809L

#include "starlink_pss_periodic_injection.h"

#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#define POLL_INTERVAL_NS 1000000L

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

static int injection_read32(const struct pss_injection_io *io,
	uint32_t offset, uint32_t *value, char *error, size_t error_size)
{
	if (!io || !io->read32 || !value)
		return fail(error, error_size, "invalid injection read arguments");
	if (offset > PSS_INJECTION_REG_LAST_OFFSET_HI || (offset & 3U))
		return fail(error, error_size,
			"invalid injection read offset 0x%08" PRIx32, offset);
	if (io->read32(io->context, offset, value) < 0)
		return fail(error, error_size,
			"injection read 0x%02" PRIx32 " failed", offset);
	return 0;
}

static int injection_write32(const struct pss_injection_io *io,
	uint32_t offset, uint32_t value, char *error, size_t error_size)
{
	if (!io || !io->write32)
		return fail(error, error_size, "invalid injection write arguments");
	if (offset > PSS_INJECTION_REG_LAST_OFFSET_HI || (offset & 3U))
		return fail(error, error_size,
			"invalid injection write offset 0x%08" PRIx32, offset);
	if (io->write32(io->context, offset, value) < 0)
		return fail(error, error_size,
			"injection write 0x%02" PRIx32 " failed", offset);
	return 0;
}

static uint64_t combine_u64(uint32_t low, uint32_t high)
{
	return (uint64_t)low | ((uint64_t)high << 32);
}

static int monotonic_milliseconds(uint64_t *milliseconds)
{
	struct timespec value;

	if (!milliseconds || clock_gettime(CLOCK_MONOTONIC, &value) < 0)
		return -1;
	*milliseconds = (uint64_t)value.tv_sec * UINT64_C(1000) +
		(uint64_t)value.tv_nsec / UINT64_C(1000000);
	return 0;
}

static void poll_pause(void)
{
	const struct timespec delay = {.tv_nsec = POLL_INTERVAL_NS};

	nanosleep(&delay, NULL);
}

bool pss_injection_state_fault_free(const struct pss_injection_state *state)
{
	return state && !(state->status & ~PSS_INJECTION_STATUS_KNOWN_MASK) &&
		!(state->status & PSS_INJECTION_STATUS_FAULT_MASK);
}

int pss_injection_read_state(const struct pss_injection_io *io,
	struct pss_injection_state *state, char *error, size_t error_size)
{
	if (!state)
		return fail(error, error_size, "missing injection-state destination");
	memset(state, 0, sizeof(*state));
	if (injection_read32(io, PSS_INJECTION_REG_STATUS, &state->status,
			error, error_size) < 0 ||
	    injection_read32(io, PSS_INJECTION_REG_LAST_GENERATION,
			&state->last_completed_generation, error, error_size) < 0 ||
	    injection_read32(io, PSS_INJECTION_REG_LAST_REPETITIONS,
			&state->last_completed_repetitions, error, error_size) < 0)
		return -1;
	if (state->status & ~PSS_INJECTION_STATUS_KNOWN_MASK)
		return fail(error, error_size,
			"injection status has unknown bits 0x%08" PRIx32,
			state->status & ~PSS_INJECTION_STATUS_KNOWN_MASK);
	state->fixture_count = (state->status >> 8) & UINT32_C(0xff);
	return 0;
}

int pss_injection_require_contract(const struct pss_injection_io *io,
	struct pss_injection_info *info, char *error, size_t error_size)
{
	struct pss_injection_info local;
	uint32_t offset_low, offset_high;

	memset(&local, 0, sizeof(local));
	if (injection_read32(io, PSS_INJECTION_REG_IDENTIFICATION,
			&local.identification, error, error_size) < 0 ||
	    injection_read32(io, PSS_INJECTION_REG_VERSION, &local.version,
			error, error_size) < 0 ||
	    injection_read32(io, PSS_INJECTION_REG_CAPABILITIES,
			&local.capabilities, error, error_size) < 0 ||
	    injection_read32(io, PSS_INJECTION_REG_GEOMETRY, &local.geometry,
			error, error_size) < 0 ||
	    injection_read32(io, PSS_INJECTION_REG_PERIOD, &local.period_samples,
			error, error_size) < 0 ||
	    injection_read32(io, PSS_INJECTION_REG_LAST_OFFSET_LO, &offset_low,
			error, error_size) < 0 ||
	    injection_read32(io, PSS_INJECTION_REG_LAST_OFFSET_HI, &offset_high,
			error, error_size) < 0)
		return -1;
	local.last_sample_offset = combine_u64(offset_low, offset_high);
	if (local.identification != PSS_INJECTION_IDENTIFICATION ||
	    local.version != PSS_INJECTION_VERSION ||
	    local.capabilities != PSS_INJECTION_CAPABILITIES ||
	    local.geometry != PSS_INJECTION_GEOMETRY ||
	    local.period_samples != PSS_INJECTION_PERIOD_SAMPLES ||
	    local.last_sample_offset != PSS_INJECTION_LAST_SAMPLE_OFFSET)
		return fail(error, error_size,
			"injection contract mismatch id=0x%08" PRIx32
			" version=0x%08" PRIx32 " capabilities=0x%08" PRIx32
			" geometry=0x%08" PRIx32 " period=%" PRIu32
			" last_offset=%" PRIu64,
			local.identification, local.version, local.capabilities,
			local.geometry, local.period_samples,
			local.last_sample_offset);
	if (info)
		*info = local;
	return 0;
}

int pss_injection_read_current_index(const struct pss_injection_io *io,
	uint64_t *current_index, char *error, size_t error_size)
{
	uint32_t low, high;

	if (!current_index)
		return fail(error, error_size, "missing current-index destination");
	if (injection_read32(io, PSS_INJECTION_REG_CURRENT_INDEX_LO, &low,
			error, error_size) < 0 ||
	    injection_read32(io, PSS_INJECTION_REG_CURRENT_INDEX_HI, &high,
			error, error_size) < 0)
		return -1;
	*current_index = combine_u64(low, high);
	return 0;
}

static int wait_for_status(const struct pss_injection_io *io,
	uint32_t set_mask, uint32_t clear_mask, unsigned int timeout_ms,
	struct pss_injection_state *result, char *error, size_t error_size)
{
	struct pss_injection_state state;
	uint64_t started, now;

	if (!timeout_ms)
		return fail(error, error_size, "injection timeout must be nonzero");
	if (monotonic_milliseconds(&started) < 0)
		return fail(error, error_size, "cannot read monotonic clock");
	for (;;) {
		if (pss_injection_read_state(io, &state, error, error_size) < 0)
			return -1;
		if (!pss_injection_state_fault_free(&state))
			return fail(error, error_size,
				"injection entered fault state 0x%08" PRIx32,
				state.status);
		if ((state.status & set_mask) == set_mask &&
		    !(state.status & clear_mask)) {
			if (result)
				*result = state;
			return 0;
		}
		if (monotonic_milliseconds(&now) < 0)
			return fail(error, error_size, "cannot read monotonic clock");
		if (now - started >= timeout_ms)
			return fail(error, error_size,
				"injection status wait timed out at 0x%08" PRIx32,
				state.status);
		poll_pause();
	}
}

static int wait_for_fixture_count(const struct pss_injection_io *io,
	uint32_t expected_count, unsigned int timeout_ms,
	struct pss_injection_state *result, char *error, size_t error_size)
{
	struct pss_injection_state state;
	uint64_t started, now;

	if (!timeout_ms || expected_count > UINT32_C(0xff))
		return fail(error, error_size, "invalid injection fixture-count wait");
	if (monotonic_milliseconds(&started) < 0)
		return fail(error, error_size, "cannot read monotonic clock");
	for (;;) {
		if (pss_injection_read_state(io, &state, error, error_size) < 0)
			return -1;
		if (!pss_injection_state_fault_free(&state))
			return fail(error, error_size,
				"injection entered fault state 0x%08" PRIx32,
				state.status);
		if (state.fixture_count == expected_count) {
			if (result)
				*result = state;
			return 0;
		}
		if (monotonic_milliseconds(&now) < 0)
			return fail(error, error_size, "cannot read monotonic clock");
		if (now - started >= timeout_ms)
			return fail(error, error_size,
				"injection fixture-count wait timed out at %" PRIu32,
				state.fixture_count);
		poll_pause();
	}
}

int pss_injection_load_fixture(const struct pss_injection_io *io,
	const uint32_t *packed_qi_words, size_t word_count, uint32_t generation,
	unsigned int timeout_ms, char *error, size_t error_size)
{
	struct pss_injection_state state;
	size_t index;

	if (!packed_qi_words || word_count != PSS_INJECTION_FIXTURE_SAMPLES)
		return fail(error, error_size,
			"injection fixture must contain exactly %u packed QI words",
			PSS_INJECTION_FIXTURE_SAMPLES);
	if (!generation)
		return fail(error, error_size, "injection generation must be nonzero");
	if (pss_injection_require_contract(io, NULL, error, error_size) < 0 ||
	    pss_injection_read_state(io, &state, error, error_size) < 0)
		return -1;
	if (state.status & (PSS_INJECTION_STATUS_INFLIGHT |
			PSS_INJECTION_STATUS_ACTIVE | PSS_INJECTION_STATUS_ARM_PENDING))
		return fail(error, error_size,
			"cannot replace an armed injection fixture");
	if (injection_write32(io, PSS_INJECTION_REG_CONTROL, 1U,
			error, error_size) < 0 ||
	    wait_for_status(io, 0U, PSS_INJECTION_STATUS_KNOWN_MASK,
			timeout_ms, NULL, error, error_size) < 0 ||
	    injection_write32(io, PSS_INJECTION_REG_GENERATION, generation,
			error, error_size) < 0)
		return -1;
	for (index = 0; index < word_count; ++index) {
		if (injection_write32(io, PSS_INJECTION_REG_FIXTURE_DATA,
				packed_qi_words[index], error, error_size) < 0)
			return -1;
	}
	if (wait_for_fixture_count(io, PSS_INJECTION_FIXTURE_SAMPLES,
			timeout_ms, &state, error, error_size) < 0)
		return -1;
	if (state.fixture_count != PSS_INJECTION_FIXTURE_SAMPLES)
		return fail(error, error_size,
			"injection fixture count is %" PRIu32 ", expected %u",
			state.fixture_count, PSS_INJECTION_FIXTURE_SAMPLES);
	if (injection_write32(io, PSS_INJECTION_REG_CONTROL, 2U,
			error, error_size) < 0 ||
	    wait_for_status(io, PSS_INJECTION_STATUS_FIXTURE_VALID,
			PSS_INJECTION_STATUS_FAULT_MASK, timeout_ms,
			&state, error, error_size) < 0)
		return -1;
	if (state.fixture_count != PSS_INJECTION_FIXTURE_SAMPLES)
		return fail(error, error_size,
			"sealed injection fixture count changed to %" PRIu32,
			state.fixture_count);
	return 0;
}

int pss_injection_arm(const struct pss_injection_io *io, uint64_t start_index,
	unsigned int timeout_ms, char *error, size_t error_size)
{
	struct pss_injection_state state;
	uint64_t current_index;

	if (start_index > UINT64_MAX - PSS_INJECTION_LAST_SAMPLE_OFFSET)
		return fail(error, error_size, "injection interval overflows 64 bits");
	if (pss_injection_require_contract(io, NULL, error, error_size) < 0 ||
	    pss_injection_read_current_index(io, &current_index,
			error, error_size) < 0)
		return -1;
	if (start_index < current_index ||
	    start_index - current_index < PSS_INJECTION_MINIMUM_ARM_LEAD)
		return fail(error, error_size,
			"injection start lacks required lead: current=%" PRIu64
			" start=%" PRIu64, current_index, start_index);
	if (injection_write32(io, PSS_INJECTION_REG_START_INDEX_LO,
			(uint32_t)start_index, error, error_size) < 0 ||
	    injection_write32(io, PSS_INJECTION_REG_START_INDEX_HI,
			(uint32_t)(start_index >> 32), error, error_size) < 0 ||
	    wait_for_status(io, PSS_INJECTION_STATUS_ARM_READY,
			PSS_INJECTION_STATUS_FAULT_MASK, timeout_ms,
			&state, error, error_size) < 0 ||
	    injection_write32(io, PSS_INJECTION_REG_CONTROL, 4U,
			error, error_size) < 0 ||
	    wait_for_status(io, PSS_INJECTION_STATUS_INFLIGHT,
			PSS_INJECTION_STATUS_FAULT_MASK,
			timeout_ms, NULL, error, error_size) < 0)
		return -1;
	return 0;
}

int pss_injection_wait_complete(const struct pss_injection_io *io,
	uint32_t generation, unsigned int timeout_ms,
	struct pss_injection_state *final_state, char *error, size_t error_size)
{
	struct pss_injection_state state;

	if (!generation)
		return fail(error, error_size, "expected generation must be nonzero");
	if (wait_for_status(io, PSS_INJECTION_STATUS_COMPLETED,
			PSS_INJECTION_STATUS_INFLIGHT |
			PSS_INJECTION_STATUS_ACTIVE |
			PSS_INJECTION_STATUS_ARM_PENDING |
			PSS_INJECTION_STATUS_FAULT_MASK,
			timeout_ms, &state, error, error_size) < 0)
		return -1;
	if (state.last_completed_generation != generation ||
	    state.last_completed_repetitions != PSS_INJECTION_REPETITIONS)
		return fail(error, error_size,
			"injection completion mismatch generation=%" PRIu32
			" repetitions=%" PRIu32,
			state.last_completed_generation,
			state.last_completed_repetitions);
	if (final_state)
		*final_state = state;
	return 0;
}
