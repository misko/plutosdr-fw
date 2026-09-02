// SPDX-License-Identifier: GPL-2.0-or-later
#define _POSIX_C_SOURCE 200809L

#include "starlink_pss_hw.h"

#include <errno.h>
#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define PSS_PACKET_MAGIC UINT32_C(0x31535350)
#define PSS_PACKET_HEADER UINT32_C(0x1a010001)
#define PSS_MINIMUM_HOST_LEAD UINT64_C(65536)

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

static int read32(const struct pss_io *io, uint32_t offset, uint32_t *value,
	char *error, size_t error_size)
{
	if (!io || !io->read32 || !value)
		return fail(error, error_size, "invalid MMIO read arguments");
	if (offset > PSS_MMIO_SPAN - sizeof(*value) || (offset & 3U))
		return fail(error, error_size, "invalid MMIO read offset 0x%08" PRIx32,
			offset);
	if (io->read32(io->context, offset, value) < 0)
		return fail(error, error_size, "MMIO read 0x%02" PRIx32 " failed",
			offset);
	return 0;
}

static int write32(const struct pss_io *io, uint32_t offset, uint32_t value,
	char *error, size_t error_size)
{
	if (!io || !io->write32)
		return fail(error, error_size, "invalid MMIO write arguments");
	if (offset > PSS_MMIO_SPAN - sizeof(value) || (offset & 3U))
		return fail(error, error_size, "invalid MMIO write offset 0x%08" PRIx32,
			offset);
	if (io->write32(io->context, offset, value) < 0)
		return fail(error, error_size, "MMIO write 0x%02" PRIx32 " failed",
			offset);
	return 0;
}

static uint64_t monotonic_milliseconds(void)
{
	struct timespec value;

	if (clock_gettime(CLOCK_MONOTONIC, &value) < 0)
		return 0;
	return (uint64_t)value.tv_sec * 1000U + (uint64_t)value.tv_nsec / 1000000U;
}

static void poll_delay(void)
{
	struct timespec delay = {.tv_sec = 0, .tv_nsec = 100000L};

	while (nanosleep(&delay, &delay) < 0 && errno == EINTR)
		;
}

static uint64_t combine_u64(uint32_t low, uint32_t high)
{
	return (uint64_t)low | (uint64_t)high << 32;
}

static int64_t combine_s48(uint32_t low, uint32_t high)
{
	uint64_t value = (uint64_t)low | ((uint64_t)high & UINT64_C(0xffff)) << 32;

	if (value & (UINT64_C(1) << 47))
		value |= ~((UINT64_C(1) << 48) - 1U);
	return (int64_t)value;
}

static uint32_t counter_delta(uint32_t before, uint32_t after)
{
	if (before == UINT32_MAX)
		return after == UINT32_MAX ? 0U : UINT32_MAX;
	return after - before;
}

int pss_read_info(const struct pss_io *io, struct pss_info *info,
	char *error, size_t error_size)
{
	if (!info)
		return fail(error, error_size, "missing info destination");
	memset(info, 0, sizeof(*info));
	if (read32(io, PSS_REG_IDENTIFICATION, &info->identification,
			error, error_size) < 0 ||
	    read32(io, PSS_REG_VERSION, &info->version, error, error_size) < 0 ||
	    read32(io, PSS_REG_RATE_MSPS, &info->rate_msps, error, error_size) < 0 ||
	    read32(io, PSS_REG_GEOMETRY, &info->geometry, error, error_size) < 0 ||
	    read32(io, PSS_REG_CAPABILITIES, &info->capabilities,
			error, error_size) < 0 ||
	    read32(io, PSS_REG_STATUS, &info->status, error, error_size) < 0 ||
	    read32(io, PSS_REG_ACTIVE_COEFFICIENT_GENERATION,
			&info->active_generation, error, error_size) < 0)
		return -1;
	return 0;
}

int pss_require_contract(const struct pss_io *io, struct pss_info *info,
	char *error, size_t error_size)
{
	struct pss_info local;
	struct pss_info *destination = info ? info : &local;

	if (pss_read_info(io, destination, error, error_size) < 0)
		return -1;
	if (destination->identification != PSS_IDENTIFICATION)
		return fail(error, error_size,
			"wrong hardware ID: expected 0x%08" PRIx32 ", got 0x%08" PRIx32,
			PSS_IDENTIFICATION, destination->identification);
	if (destination->version != PSS_VERSION)
		return fail(error, error_size,
			"wrong ABI version: expected 0x%08" PRIx32 ", got 0x%08" PRIx32,
			PSS_VERSION, destination->version);
	if (destination->rate_msps != PSS_RATE_MSPS)
		return fail(error, error_size,
			"wrong rate: expected %" PRIu32 " MS/s, got %" PRIu32,
			PSS_RATE_MSPS, destination->rate_msps);
	if (destination->geometry != PSS_GEOMETRY)
		return fail(error, error_size,
			"wrong geometry: expected 0x%08" PRIx32 ", got 0x%08" PRIx32,
			PSS_GEOMETRY, destination->geometry);
	if (destination->capabilities != PSS_CAPABILITIES)
		return fail(error, error_size,
			"wrong capabilities: expected 0x%08" PRIx32 ", got 0x%08" PRIx32,
			PSS_CAPABILITIES, destination->capabilities);
	if (!(destination->status & PSS_STATUS_RESET_RELEASED))
		return fail(error, error_size, "tracker reset is not released");
	return 0;
}

int pss_read_current_index(const struct pss_io *io, uint64_t *index,
	char *error, size_t error_size)
{
	uint32_t low, high;

	if (!index)
		return fail(error, error_size, "missing current-index destination");
	if (read32(io, PSS_REG_CURRENT_INDEX_LO, &low, error, error_size) < 0 ||
	    read32(io, PSS_REG_CURRENT_INDEX_HI, &high, error, error_size) < 0)
		return -1;
	*index = combine_u64(low, high);
	return 0;
}

static int read_ci16_file(const char *path, struct pss_ci16 *values,
	unsigned int expected_count, const char *kind,
	char *error, size_t error_size)
{
	FILE *input;
	char line[128];
	unsigned int count = 0;

	if (!path || !values || !kind)
		return fail(error, error_size, "missing CI16 file input or destination");
	input = fopen(path, "r");
	if (!input)
		return fail(error, error_size, "cannot open %s: %s", path,
			strerror(errno));
	while (fgets(line, sizeof(line), input)) {
		char *end;
		unsigned long word;

		if (strchr(line, '\n') == NULL && !feof(input)) {
			fclose(input);
			return fail(error, error_size, "%s: overlong line", path);
		}
		errno = 0;
		word = strtoul(line, &end, 16);
		while (*end == ' ' || *end == '\t' || *end == '\r' || *end == '\n')
			++end;
		if (errno || end == line || *end != '\0' || word > UINT32_MAX) {
			fclose(input);
			return fail(error, error_size, "%s: invalid CI16 word on line %u",
				path, count + 1U);
		}
		if (count >= expected_count) {
			fclose(input);
			return fail(error, error_size,
				"%s: expected exactly %u %s words", path, expected_count, kind);
		}
		/* Fixture files are I in bits 31:16 and Q in bits 15:0. */
		values[count].i = (int16_t)(uint16_t)(word >> 16);
		values[count].q = (int16_t)(uint16_t)word;
		++count;
	}
	if (ferror(input)) {
		int saved_errno = errno;
		fclose(input);
		return fail(error, error_size, "cannot read %s: %s", path,
			strerror(saved_errno));
	}
	fclose(input);
	if (count != expected_count)
		return fail(error, error_size, "%s: expected %u %s words, got %u",
			path, expected_count, kind, count);
	return 0;
}

int pss_read_ci16_file(const char *path,
	struct pss_ci16 coefficients[PSS_COEFFICIENT_COUNT],
	char *error, size_t error_size)
{
	return read_ci16_file(path, coefficients, PSS_COEFFICIENT_COUNT,
		"coefficient", error, error_size);
}

int pss_read_injection_file(const char *path,
	struct pss_ci16 samples[PSS_INJECTION_SAMPLES],
	char *error, size_t error_size)
{
	return read_ci16_file(path, samples, PSS_INJECTION_SAMPLES,
		"injection", error, error_size);
}

int pss_load_coefficients(const struct pss_io *io,
	const struct pss_ci16 coefficients[PSS_COEFFICIENT_COUNT],
	uint32_t generation, unsigned int timeout_ms,
	char *error, size_t error_size)
{
	struct pss_info info;
	uint32_t overrun_before, overrun_after, status, active;
	uint64_t deadline;
	unsigned int index;

	if (!coefficients)
		return fail(error, error_size, "missing coefficients");
	if (!generation)
		return fail(error, error_size, "coefficient generation must be nonzero");
	if (!timeout_ms)
		return fail(error, error_size, "coefficient timeout must be nonzero");
	if (pss_require_contract(io, &info, error, error_size) < 0)
		return -1;
	if (info.status & (PSS_STATUS_COMMAND_BUFFERED | PSS_STATUS_RESULT_AVAILABLE))
		return fail(error, error_size,
			"tracker has a buffered command or unread result");
	if (info.active_generation == generation)
		return fail(error, error_size,
			"generation 0x%08" PRIx32 " is already active", generation);
	if (read32(io, PSS_REG_COEFFICIENT_WRITE_OVERRUN, &overrun_before,
			error, error_size) < 0)
		return -1;

	deadline = monotonic_milliseconds() + timeout_ms;
	if (write32(io, PSS_REG_COEFFICIENT_CONTROL, 1U, error, error_size) < 0)
		return -1;
	for (;;) {
		if (read32(io, PSS_REG_STATUS, &status, error, error_size) < 0)
			return -1;
		if (((status >> 8) & 0x7fU) == 0U &&
		    (status & PSS_STATUS_COEFFICIENT_READY))
			break;
		if (monotonic_milliseconds() >= deadline)
			return fail(error, error_size, "coefficient clear timed out");
		poll_delay();
	}

	for (index = 0; index < PSS_COEFFICIENT_COUNT; ++index) {
		uint32_t packed = (uint32_t)(uint16_t)coefficients[index].i |
			(uint32_t)(uint16_t)coefficients[index].q << 16;

		if (write32(io, PSS_REG_COEFFICIENT_DATA, packed,
				error, error_size) < 0)
			return -1;
		for (;;) {
			if (read32(io, PSS_REG_STATUS, &status, error, error_size) < 0)
				return -1;
			if (((status >> 8) & 0x7fU) == index + 1U)
				break;
			if (monotonic_milliseconds() >= deadline)
				return fail(error, error_size,
					"coefficient %u was not accepted", index);
			poll_delay();
		}
	}
	if (!(status & PSS_STATUS_COEFFICIENT_COMMIT_READY))
		return fail(error, error_size, "coefficient bank is not commit-ready");
	if (write32(io, PSS_REG_COEFFICIENT_GENERATION, generation,
			error, error_size) < 0 ||
	    write32(io, PSS_REG_COEFFICIENT_CONTROL, 2U, error, error_size) < 0)
		return -1;
	for (;;) {
		if (read32(io, PSS_REG_ACTIVE_COEFFICIENT_GENERATION, &active,
				error, error_size) < 0 ||
		    read32(io, PSS_REG_STATUS, &status, error, error_size) < 0)
			return -1;
		if (active == generation &&
		    (status & PSS_STATUS_COEFFICIENT_VALID) &&
		    ((status >> 8) & 0x7fU) == 0U)
			break;
		if (monotonic_milliseconds() >= deadline)
			return fail(error, error_size, "coefficient commit timed out");
		poll_delay();
	}
	if (read32(io, PSS_REG_COEFFICIENT_WRITE_OVERRUN, &overrun_after,
			error, error_size) < 0)
		return -1;
	if (overrun_after != overrun_before)
		return fail(error, error_size,
			"coefficient write-overrun counter changed (%" PRIu32 " -> %" PRIu32 ")",
			overrun_before, overrun_after);
	return 0;
}

int pss_read_injection_status(const struct pss_io *io,
	struct pss_injection_status *status, char *error, size_t error_size)
{
	uint32_t start_low, start_high;

	if (!status)
		return fail(error, error_size, "missing injection-status destination");
	memset(status, 0, sizeof(*status));
	if (read32(io, PSS_REG_INJECTION_START_LO, &start_low,
			error, error_size) < 0 ||
	    read32(io, PSS_REG_INJECTION_START_HI, &start_high,
			error, error_size) < 0 ||
	    read32(io, PSS_REG_INJECTION_GENERATION, &status->generation_stage,
			error, error_size) < 0 ||
	    read32(io, PSS_REG_INJECTION_STATUS, &status->raw_status,
			error, error_size) < 0 ||
	    read32(io, PSS_REG_INJECTION_LAST_GENERATION,
			&status->last_completed_generation, error, error_size) < 0)
		return -1;
	status->start_index = combine_u64(start_low, start_high);
	status->fixture_count = (uint8_t)(status->raw_status >> 8);
	return 0;
}

static int reject_bad_injection_status(const struct pss_injection_status *status,
	char *error, size_t error_size)
{
	if (status->raw_status & PSS_INJECTION_REJECTED)
		return fail(error, error_size,
			"injection hardware reports a rejected command (status=0x%08" PRIx32 ")",
			status->raw_status);
	if (status->raw_status & PSS_INJECTION_MISMATCH)
		return fail(error, error_size,
			"injection hardware reports an accepted-index mismatch "
			"(status=0x%08" PRIx32 ")", status->raw_status);
	return 0;
}

int pss_load_injection_fixture(const struct pss_io *io,
	const struct pss_ci16 samples[PSS_INJECTION_SAMPLES],
	uint32_t generation, unsigned int timeout_ms,
	struct pss_injection_status *status, char *error, size_t error_size)
{
	struct pss_info info;
	struct pss_injection_status observed;
	struct pss_injection_status *destination = status ? status : &observed;
	uint64_t deadline;
	unsigned int index;

	if (!samples)
		return fail(error, error_size, "missing injection samples");
	if (!generation)
		return fail(error, error_size, "injection generation must be nonzero");
	if (!timeout_ms)
		return fail(error, error_size, "injection timeout must be nonzero");
	if (pss_require_contract(io, &info, error, error_size) < 0 ||
	    pss_read_injection_status(io, destination, error, error_size) < 0)
		return -1;
	if (destination->raw_status &
	    (PSS_INJECTION_ARM_PENDING | PSS_INJECTION_ACTIVE |
	     PSS_INJECTION_INFLIGHT))
		return fail(error, error_size, "cannot load while injection is active");

	deadline = monotonic_milliseconds() + timeout_ms;
	if (write32(io, PSS_REG_INJECTION_CONTROL, 1U, error, error_size) < 0)
		return -1;
	for (;;) {
		if (pss_read_injection_status(io, destination,
				error, error_size) < 0)
			return -1;
		if (destination->fixture_count == 0 &&
		    !(destination->raw_status &
		      (PSS_INJECTION_FIXTURE_VALID | PSS_INJECTION_REJECTED |
		       PSS_INJECTION_MISMATCH)))
			break;
		if (monotonic_milliseconds() >= deadline)
			return fail(error, error_size, "injection fixture clear timed out");
		poll_delay();
	}

	for (index = 0; index < PSS_INJECTION_SAMPLES; ++index) {
		uint32_t packed = (uint32_t)(uint16_t)samples[index].i |
			(uint32_t)(uint16_t)samples[index].q << 16;

		if (write32(io, PSS_REG_INJECTION_DATA, packed,
				error, error_size) < 0)
			return -1;
		for (;;) {
			if (pss_read_injection_status(io, destination,
					error, error_size) < 0 ||
			    reject_bad_injection_status(destination,
					error, error_size) < 0)
				return -1;
			if (destination->fixture_count == index + 1U)
				break;
			if (monotonic_milliseconds() >= deadline)
				return fail(error, error_size,
					"injection sample %u was not accepted", index);
			poll_delay();
		}
	}

	if (write32(io, PSS_REG_INJECTION_GENERATION, generation,
			error, error_size) < 0 ||
	    write32(io, PSS_REG_INJECTION_CONTROL, 2U,
			error, error_size) < 0)
		return -1;
	for (;;) {
		if (pss_read_injection_status(io, destination,
				error, error_size) < 0 ||
		    reject_bad_injection_status(destination, error, error_size) < 0)
			return -1;
		if ((destination->raw_status & PSS_INJECTION_FIXTURE_VALID) &&
		    destination->fixture_count == PSS_INJECTION_SAMPLES &&
		    destination->generation_stage == generation)
			break;
		if (monotonic_milliseconds() >= deadline)
			return fail(error, error_size, "injection fixture commit timed out");
		poll_delay();
	}
	return 0;
}

int pss_arm_injection(const struct pss_io *io, uint64_t start_index,
	unsigned int timeout_ms, struct pss_injection_status *status,
	char *error, size_t error_size)
{
	struct pss_injection_status observed;
	struct pss_injection_status *destination = status ? status : &observed;
	uint64_t current, deadline;

	if (!timeout_ms)
		return fail(error, error_size, "injection timeout must be nonzero");
	if (pss_require_contract(io, NULL, error, error_size) < 0 ||
	    pss_read_current_index(io, &current, error, error_size) < 0)
		return -1;
	if (start_index < current || start_index - current < PSS_MINIMUM_HOST_LEAD)
		return fail(error, error_size,
			"injection start needs at least %" PRIu64
			" samples of host lead (current=%" PRIu64 ", start=%" PRIu64 ")",
			PSS_MINIMUM_HOST_LEAD, current, start_index);
	if (UINT64_MAX - start_index < PSS_INJECTION_SAMPLES - 1U)
		return fail(error, error_size,
			"injection window overflows the accepted-sample index");
	if (write32(io, PSS_REG_INJECTION_START_LO, (uint32_t)start_index,
			error, error_size) < 0 ||
	    write32(io, PSS_REG_INJECTION_START_HI, (uint32_t)(start_index >> 32),
			error, error_size) < 0)
		return -1;

	deadline = monotonic_milliseconds() + timeout_ms;
	for (;;) {
		if (pss_read_injection_status(io, destination,
				error, error_size) < 0 ||
		    reject_bad_injection_status(destination, error, error_size) < 0)
			return -1;
		if (destination->start_index == start_index &&
		    (destination->raw_status & PSS_INJECTION_ARM_READY))
			break;
		if (monotonic_milliseconds() >= deadline)
			return fail(error, error_size, "injection arm-ready timed out");
		poll_delay();
	}
	if (write32(io, PSS_REG_INJECTION_CONTROL, 4U,
			error, error_size) < 0)
		return -1;
	for (;;) {
		if (pss_read_injection_status(io, destination,
				error, error_size) < 0 ||
		    reject_bad_injection_status(destination, error, error_size) < 0)
			return -1;
		if ((destination->raw_status & PSS_INJECTION_INFLIGHT) &&
		    !(destination->raw_status & PSS_INJECTION_ARM_PENDING))
			return 0;
		if (monotonic_milliseconds() >= deadline)
			return fail(error, error_size, "injection arm handshake timed out");
		poll_delay();
	}
}

int pss_wait_injection_complete(const struct pss_io *io,
	uint32_t expected_generation, unsigned int timeout_ms,
	struct pss_injection_status *status, char *error, size_t error_size)
{
	struct pss_injection_status observed;
	struct pss_injection_status *destination = status ? status : &observed;
	uint64_t deadline;

	if (!expected_generation)
		return fail(error, error_size,
			"expected injection generation must be nonzero");
	if (!timeout_ms)
		return fail(error, error_size, "injection timeout must be nonzero");
	deadline = monotonic_milliseconds() + timeout_ms;
	for (;;) {
		if (pss_read_injection_status(io, destination,
				error, error_size) < 0 ||
		    reject_bad_injection_status(destination, error, error_size) < 0)
			return -1;
		if ((destination->raw_status & PSS_INJECTION_COMPLETED) &&
		    !(destination->raw_status &
		      (PSS_INJECTION_ARM_PENDING | PSS_INJECTION_ACTIVE |
		       PSS_INJECTION_INFLIGHT)) &&
		    destination->last_completed_generation == expected_generation)
			return 0;
		if (monotonic_milliseconds() >= deadline)
			return fail(error, error_size,
				"injection completion timed out for generation 0x%08" PRIx32,
				expected_generation);
		poll_delay();
	}
}

int pss_snapshot_counters(const struct pss_io *io,
	struct pss_counters *counters, unsigned int timeout_ms,
	char *error, size_t error_size)
{
	uint32_t before, generation, status;
	uint64_t deadline;

	if (!counters)
		return fail(error, error_size, "missing counter destination");
	if (!timeout_ms)
		return fail(error, error_size, "telemetry timeout must be nonzero");
	deadline = monotonic_milliseconds() + timeout_ms;
	for (;;) {
		if (read32(io, PSS_REG_TELEMETRY_STATUS, &status, error, error_size) < 0)
			return -1;
		if (!(status & 2U))
			break;
		if (monotonic_milliseconds() >= deadline)
			return fail(error, error_size, "prior telemetry request stayed busy");
		poll_delay();
	}
	if (read32(io, PSS_REG_TELEMETRY_GENERATION, &before,
			error, error_size) < 0 ||
	    write32(io, PSS_REG_TELEMETRY_CONTROL, 1U, error, error_size) < 0)
		return -1;
	for (;;) {
		if (read32(io, PSS_REG_TELEMETRY_STATUS, &status, error, error_size) < 0 ||
		    read32(io, PSS_REG_TELEMETRY_GENERATION, &generation,
				error, error_size) < 0)
			return -1;
		if ((status & 3U) == 1U && generation != before)
			break;
		if (monotonic_milliseconds() >= deadline)
			return fail(error, error_size, "telemetry snapshot timed out");
		poll_delay();
	}

	memset(counters, 0, sizeof(*counters));
	counters->telemetry_generation = generation;
#define READ_COUNTER(member, offset) \
	do { \
		if (read32(io, (offset), &counters->member, error, error_size) < 0) \
			return -1; \
	} while (0)
	READ_COUNTER(candidate_command_overrun, PSS_REG_CANDIDATE_COMMAND_OVERRUN);
	READ_COUNTER(coefficient_write_overrun, PSS_REG_COEFFICIENT_WRITE_OVERRUN);
	READ_COUNTER(queue_overrun, PSS_REG_QUEUE_OVERRUN);
	READ_COUNTER(admitted, PSS_REG_ADMITTED);
	READ_COUNTER(completed_capture, PSS_REG_COMPLETED_CAPTURE);
	READ_COUNTER(rejected, PSS_REG_REJECTED);
	READ_COUNTER(late, PSS_REG_LATE);
	READ_COUNTER(duplicate, PSS_REG_DUPLICATE);
	READ_COUNTER(overlap, PSS_REG_OVERLAP);
	READ_COUNTER(aborted, PSS_REG_ABORTED);
	READ_COUNTER(valid_gap_abort, PSS_REG_VALID_GAP_ABORT);
	READ_COUNTER(index_jump_abort, PSS_REG_INDEX_JUMP_ABORT);
	READ_COUNTER(timestamp_abort, PSS_REG_TIMESTAMP_ABORT);
	READ_COUNTER(capture_published, PSS_REG_CAPTURE_PUBLISHED);
	READ_COUNTER(capture_abort_discard, PSS_REG_CAPTURE_ABORT_DISCARD);
	READ_COUNTER(capture_buffer_overrun, PSS_REG_CAPTURE_BUFFER_OVERRUN);
	READ_COUNTER(capture_protocol_error, PSS_REG_CAPTURE_PROTOCOL_ERROR);
	READ_COUNTER(engine_consumed, PSS_REG_ENGINE_CONSUMED);
	READ_COUNTER(correlator_bound_error, PSS_REG_CORRELATOR_BOUND_ERROR);
	READ_COUNTER(reducer_processed, PSS_REG_REDUCER_PROCESSED);
	READ_COUNTER(reducer_emitted, PSS_REG_REDUCER_EMITTED);
	READ_COUNTER(reducer_invalid, PSS_REG_REDUCER_INVALID);
	READ_COUNTER(reducer_bound_error, PSS_REG_REDUCER_BOUND_ERROR);
	READ_COUNTER(reducer_protocol_error, PSS_REG_REDUCER_PROTOCOL_ERROR);
	READ_COUNTER(result_published, PSS_REG_RESULT_PUBLISHED);
	READ_COUNTER(result_overrun, PSS_REG_RESULT_OVERRUN);
	READ_COUNTER(result_consumed, PSS_REG_RESULT_CONSUMED);
#undef READ_COUNTER
	return 0;
}

int pss_validate_packet(const uint32_t words[PSS_RESULT_WORDS],
	uint32_t request_id, uint64_t center_index, uint64_t center_timestamp,
	uint32_t generation,
	struct pss_packet *packet, char *error, size_t error_size)
{
	int32_t lag;
	uint64_t winner_timestamp;

	if (!words || !packet)
		return fail(error, error_size, "missing packet input or destination");
	if (words[0] != PSS_PACKET_MAGIC)
		return fail(error, error_size, "bad packet magic 0x%08" PRIx32, words[0]);
	if (words[1] != PSS_PACKET_HEADER)
		return fail(error, error_size, "bad packet header 0x%08" PRIx32, words[1]);
	if (words[2] != request_id)
		return fail(error, error_size,
			"packet request mismatch: expected 0x%08" PRIx32 ", got 0x%08" PRIx32,
			request_id, words[2]);
	if (combine_u64(words[3], words[4]) != center_index ||
	    combine_u64(words[5], words[6]) != center_timestamp)
		return fail(error, error_size, "packet center index/timestamp mismatch");
	lag = (int32_t)words[7];
	if (lag < PSS_FIRST_LAG || lag > PSS_LAST_LAG)
		return fail(error, error_size, "packet lag %" PRId32 " is outside %d..%d",
			lag, PSS_FIRST_LAG, PSS_LAST_LAG);
	winner_timestamp = combine_u64(words[8], words[9]);
	if (winner_timestamp != (uint64_t)((int64_t)center_timestamp + lag))
		return fail(error, error_size, "packet winner timestamp is inconsistent");
	if (words[10] != generation)
		return fail(error, error_size,
			"packet coefficient generation mismatch: expected 0x%08" PRIx32
			", got 0x%08" PRIx32, generation, words[10]);
	if (combine_s48(words[15], words[16]) <= 0 ||
	    combine_s48(words[17], words[18]) <= 0)
		return fail(error, error_size, "packet contains non-positive energy");

	memset(packet, 0, sizeof(*packet));
	memcpy(packet->words, words, sizeof(packet->words));
	packet->request_id = words[2];
	packet->center_index = combine_u64(words[3], words[4]);
	packet->center_timestamp = combine_u64(words[5], words[6]);
	packet->lag = lag;
	packet->winner_timestamp = winner_timestamp;
	packet->coefficient_generation = words[10];
	packet->correlation_real = combine_s48(words[11], words[12]);
	packet->correlation_imag = combine_s48(words[13], words[14]);
	packet->sample_energy = combine_s48(words[15], words[16]);
	packet->coefficient_energy = combine_s48(words[17], words[18]);
	packet->saturation_events = words[19];
	return 0;
}

static int require_delta(const char *name, uint32_t before, uint32_t after,
	uint32_t expected, char *error, size_t error_size)
{
	uint32_t delta = counter_delta(before, after);

	if (delta != expected)
		return fail(error, error_size,
			"counter %s delta: expected %" PRIu32 ", got %" PRIu32,
			name, expected, delta);
	return 0;
}

static int validate_track_deltas(const struct pss_counters *before,
	const struct pss_counters *after, char *error, size_t error_size)
{
#define EXPECT_DELTA(member, expected) \
	do { \
		if (require_delta(#member, before->member, after->member, (expected), \
				error, error_size) < 0) \
			return -1; \
	} while (0)
	EXPECT_DELTA(candidate_command_overrun, 0);
	EXPECT_DELTA(coefficient_write_overrun, 0);
	EXPECT_DELTA(queue_overrun, 0);
	EXPECT_DELTA(admitted, 1);
	EXPECT_DELTA(completed_capture, 1);
	EXPECT_DELTA(rejected, 0);
	EXPECT_DELTA(late, 0);
	EXPECT_DELTA(duplicate, 0);
	EXPECT_DELTA(overlap, 0);
	EXPECT_DELTA(aborted, 0);
	EXPECT_DELTA(valid_gap_abort, 0);
	EXPECT_DELTA(index_jump_abort, 0);
	EXPECT_DELTA(timestamp_abort, 0);
	EXPECT_DELTA(capture_published, 1);
	EXPECT_DELTA(capture_abort_discard, 0);
	EXPECT_DELTA(capture_buffer_overrun, 0);
	EXPECT_DELTA(capture_protocol_error, 0);
	EXPECT_DELTA(engine_consumed, 1);
	EXPECT_DELTA(correlator_bound_error, 0);
	EXPECT_DELTA(reducer_processed, 1);
	EXPECT_DELTA(reducer_emitted, 1);
	EXPECT_DELTA(reducer_invalid, 0);
	EXPECT_DELTA(reducer_bound_error, 0);
	EXPECT_DELTA(reducer_protocol_error, 0);
	EXPECT_DELTA(result_published, 1);
	EXPECT_DELTA(result_overrun, 0);
	EXPECT_DELTA(result_consumed, 0);
#undef EXPECT_DELTA
	return 0;
}

int pss_track_one(const struct pss_io *io,
	const struct pss_track_request *request, struct pss_track_result *result,
	char *error, size_t error_size)
{
	struct pss_info info;
	uint32_t status, result_status, words[PSS_RESULT_WORDS];
	uint32_t consumed;
	uint64_t current, center, deadline;
	unsigned int index;

	if (!request || !result)
		return fail(error, error_size, "missing track request or destination");
	if (!request->request_id)
		return fail(error, error_size, "request ID must be nonzero");
	if (!request->timeout_ms)
		return fail(error, error_size, "track timeout must be nonzero");
	if (pss_require_contract(io, &info, error, error_size) < 0)
		return -1;
	if (!(info.status & PSS_STATUS_COEFFICIENT_VALID) ||
	    !info.active_generation)
		return fail(error, error_size, "no committed coefficient bank is active");
	if (!(info.status & PSS_STATUS_CANDIDATE_READY) ||
	    (info.status & (PSS_STATUS_COMMAND_BUFFERED | PSS_STATUS_RESULT_AVAILABLE)))
		return fail(error, error_size,
			"tracker is not idle/ready or has an unread result");
	if (pss_read_current_index(io, &current, error, error_size) < 0)
		return -1;
	center = request->center_is_explicit ? request->center :
		current + (request->lead_samples ? request->lead_samples :
			PSS_DEFAULT_LEAD_SAMPLES);
	if (center < current || center - current < PSS_MINIMUM_HOST_LEAD)
		return fail(error, error_size,
			"center needs at least %" PRIu64 " samples of host lead (current=%" PRIu64
			", center=%" PRIu64 ")", PSS_MINIMUM_HOST_LEAD, current, center);

	memset(result, 0, sizeof(*result));
	result->scheduled_center = center;
	if (pss_snapshot_counters(io, &result->before, request->timeout_ms,
			error, error_size) < 0)
		return -1;
	if (write32(io, PSS_REG_CANDIDATE_REQUEST, request->request_id,
			error, error_size) < 0 ||
	    write32(io, PSS_REG_CANDIDATE_CENTER_LO, (uint32_t)center,
			error, error_size) < 0 ||
	    write32(io, PSS_REG_CANDIDATE_CENTER_HI, (uint32_t)(center >> 32),
			error, error_size) < 0 ||
	    write32(io, PSS_REG_CANDIDATE_TIMESTAMP_LO, (uint32_t)center,
			error, error_size) < 0 ||
	    write32(io, PSS_REG_CANDIDATE_TIMESTAMP_HI, (uint32_t)(center >> 32),
			error, error_size) < 0 ||
	    write32(io, PSS_REG_CANDIDATE_CONTROL, 1U, error, error_size) < 0)
		return -1;

	deadline = monotonic_milliseconds() + request->timeout_ms;
	for (;;) {
		if (read32(io, PSS_REG_RESULT_STATUS, &result_status,
				error, error_size) < 0)
			return -1;
		if ((result_status & 1U) && ((result_status >> 24) & 0x1fU) == 26U)
			break;
		if (monotonic_milliseconds() >= deadline)
			return fail(error, error_size,
				"candidate 0x%08" PRIx32 " timed out", request->request_id);
		poll_delay();
	}
	for (index = 0; index < PSS_RESULT_WORDS; ++index) {
		if (write32(io, PSS_REG_RESULT_WORD_INDEX, index,
				error, error_size) < 0 ||
		    read32(io, PSS_REG_RESULT_WORD_DATA, &words[index],
				error, error_size) < 0)
			return -1;
	}
	if (pss_validate_packet(words, request->request_id, center, center,
			info.active_generation, &result->packet, error, error_size) < 0)
		return -1;
	if (result->packet.saturation_events)
		return fail(error, error_size,
			"packet reports %" PRIu32 " saturation events; result retained",
			result->packet.saturation_events);
	if (pss_snapshot_counters(io, &result->after, request->timeout_ms,
			error, error_size) < 0 ||
	    validate_track_deltas(&result->before, &result->after,
			error, error_size) < 0)
		return -1;

	if (write32(io, PSS_REG_RESULT_CONTROL, 1U, error, error_size) < 0)
		return -1;
	for (;;) {
		if (read32(io, PSS_REG_RESULT_STATUS, &result_status,
				error, error_size) < 0 ||
		    read32(io, PSS_REG_RESULT_CONSUMED, &consumed,
				error, error_size) < 0)
			return -1;
		if (!(result_status & 1U) &&
		    counter_delta(result->before.result_consumed, consumed) == 1U)
			break;
		if (monotonic_milliseconds() >= deadline)
			return fail(error, error_size, "result release timed out");
		poll_delay();
	}
	result->after.result_consumed = consumed;
	if (read32(io, PSS_REG_STATUS, &status, error, error_size) < 0)
		return -1;
	if (status & PSS_STATUS_RESULT_AVAILABLE)
		return fail(error, error_size, "result remained available after release");
	return 0;
}
