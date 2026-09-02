// SPDX-License-Identifier: GPL-2.0-or-later
#define _POSIX_C_SOURCE 200809L

#include "starlink_pss_hw.h"

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#define SERIAL_FILE "/etc/serial"

struct mapped_mmio {
	int fd;
	void *mapping;
	size_t mapping_size;
	volatile uint32_t *registers;
};

static void usage(FILE *stream)
{
	fprintf(stream,
		"usage: starlink_pssctl --expect-serial SERIAL [--devmem PATH] COMMAND [ARGS]\n"
		"\n"
		"Commands:\n"
		"  info\n"
		"  snapshot\n"
		"  clock-slope [--duration-ms N] [--tolerance-ppm N]\n"
		"  counters [--timeout-ms N]\n"
		"  load --coeff FILE --generation N [--timeout-ms N]\n"
		"  track --request N [--lead N | --center N] [--timeout-ms N]\n"
		"  track-batch --request-base N --count N [--period N]\n"
		"              [--lead N | --first-center N] [--queue-target N]\n"
		"              [--timeout-ms N]\n"
		"  inject-status\n"
		"  inject-load --samples FILE --generation N [--timeout-ms N]\n"
		"  inject-track --request N [--lead N | --start N] [--timeout-ms N]\n"
		"\n"
		"The tool always maps the source-locked tracker at 0x%08" PRIx64
		" and refuses any serial or ABI mismatch.\n", PSS_MMIO_BASE);
}

static int parse_u64(const char *text, uint64_t *value)
{
	char *end;
	unsigned long long parsed;

	if (!text || !*text)
		return -1;
	errno = 0;
	parsed = strtoull(text, &end, 0);
	if (errno || *end)
		return -1;
	*value = (uint64_t)parsed;
	return 0;
}

static int parse_u32(const char *text, uint32_t *value)
{
	uint64_t parsed;

	if (parse_u64(text, &parsed) < 0 || parsed > UINT32_MAX)
		return -1;
	*value = (uint32_t)parsed;
	return 0;
}

static int parse_timeout(const char *text, unsigned int *value)
{
	uint32_t parsed;

	if (parse_u32(text, &parsed) < 0 || !parsed)
		return -1;
	*value = parsed;
	return 0;
}

static int parse_double(const char *text, double *value)
{
	char *end;
	double parsed;

	if (!text || !*text)
		return -1;
	errno = 0;
	parsed = strtod(text, &end);
	if (errno || *end || !isfinite(parsed))
		return -1;
	*value = parsed;
	return 0;
}

static int monotonic_nanoseconds(uint64_t *value)
{
	struct timespec now;

	if (clock_gettime(CLOCK_MONOTONIC, &now) < 0)
		return -1;
	*value = (uint64_t)now.tv_sec * UINT64_C(1000000000) +
		(uint64_t)now.tv_nsec;
	return 0;
}

static int sleep_milliseconds(uint32_t duration_ms)
{
	struct timespec remaining = {
		.tv_sec = duration_ms / 1000U,
		.tv_nsec = (long)(duration_ms % 1000U) * 1000000L,
	};

	while (nanosleep(&remaining, &remaining) < 0) {
		if (errno != EINTR)
			return -1;
	}
	return 0;
}

static int verify_local_serial(const char *expected)
{
	FILE *input;
	char actual[128];
	size_t length;

	if (!expected || !*expected) {
		fprintf(stderr, "--expect-serial is mandatory\n");
		return -1;
	}
	input = fopen(SERIAL_FILE, "r");
	if (!input) {
		fprintf(stderr, "cannot read %s: %s\n", SERIAL_FILE, strerror(errno));
		return -1;
	}
	if (!fgets(actual, sizeof(actual), input)) {
		fprintf(stderr, "cannot read a serial from %s\n", SERIAL_FILE);
		fclose(input);
		return -1;
	}
	fclose(input);
	length = strlen(actual);
	while (length && (actual[length - 1] == '\n' || actual[length - 1] == '\r' ||
			actual[length - 1] == ' ' || actual[length - 1] == '\t'))
		actual[--length] = '\0';
	if (strcmp(actual, expected)) {
		fprintf(stderr, "radio serial mismatch: expected %s, local radio is %s\n",
			expected, actual);
		return -1;
	}
	return 0;
}

static int mapped_read32(void *context, uint32_t offset, uint32_t *value)
{
	struct mapped_mmio *mmio = context;

	__sync_synchronize();
	*value = mmio->registers[offset / sizeof(uint32_t)];
	__sync_synchronize();
	return 0;
}

static int mapped_write32(void *context, uint32_t offset, uint32_t value)
{
	struct mapped_mmio *mmio = context;

	__sync_synchronize();
	mmio->registers[offset / sizeof(uint32_t)] = value;
	__sync_synchronize();
	return 0;
}

static int map_mmio(struct mapped_mmio *mmio, const char *path)
{
	long page_size = sysconf(_SC_PAGESIZE);
	off_t aligned_base;
	size_t page_offset;

	memset(mmio, 0, sizeof(*mmio));
	mmio->fd = -1;
	if (page_size <= 0 || ((uint64_t)page_size & ((uint64_t)page_size - 1U))) {
		fprintf(stderr, "cannot determine a power-of-two system page size\n");
		return -1;
	}
	aligned_base = (off_t)(PSS_MMIO_BASE & ~((uint64_t)page_size - 1U));
	page_offset = (size_t)(PSS_MMIO_BASE - (uint64_t)aligned_base);
	mmio->mapping_size = page_offset + PSS_MMIO_SPAN;
	mmio->fd = open(path, O_RDWR | O_SYNC | O_CLOEXEC);
	if (mmio->fd < 0) {
		fprintf(stderr, "cannot open %s: %s\n", path, strerror(errno));
		return -1;
	}
	mmio->mapping = mmap(NULL, mmio->mapping_size, PROT_READ | PROT_WRITE,
		MAP_SHARED, mmio->fd, aligned_base);
	if (mmio->mapping == MAP_FAILED) {
		fprintf(stderr, "cannot map tracker MMIO: %s\n", strerror(errno));
		close(mmio->fd);
		mmio->fd = -1;
		return -1;
	}
	mmio->registers = (volatile uint32_t *)((uint8_t *)mmio->mapping + page_offset);
	return 0;
}

static void unmap_mmio(struct mapped_mmio *mmio)
{
	if (mmio->mapping && mmio->mapping != MAP_FAILED)
		munmap(mmio->mapping, mmio->mapping_size);
	if (mmio->fd >= 0)
		close(mmio->fd);
}

struct clock_observation {
	uint64_t index;
	uint64_t before_ns;
	uint64_t after_ns;
	uint64_t midpoint_ns;
	uint64_t read_span_ns;
};

static int read_clock_observation(const struct pss_io *io,
	struct clock_observation *observation, char *error, size_t error_size)
{
	if (monotonic_nanoseconds(&observation->before_ns) < 0) {
		snprintf(error, error_size, "host monotonic clock read failed: %s",
			strerror(errno));
		return -1;
	}
	if (pss_read_current_index(io, &observation->index,
			error, error_size) < 0)
		return -1;
	if (monotonic_nanoseconds(&observation->after_ns) < 0) {
		snprintf(error, error_size, "host monotonic clock read failed: %s",
			strerror(errno));
		return -1;
	}
	if (observation->after_ns < observation->before_ns) {
		snprintf(error, error_size, "host monotonic clock moved backwards");
		return -1;
	}
	observation->read_span_ns =
		observation->after_ns - observation->before_ns;
	observation->midpoint_ns = observation->before_ns +
		observation->read_span_ns / 2U;
	return 0;
}

static void print_info(const char *serial, const struct pss_info *info)
{
	printf("{\n"
	       "  \"serial\": \"%s\",\n"
	       "  \"mmio_base\": \"0x%08" PRIx64 "\",\n"
	       "  \"identification\": \"0x%08" PRIx32 "\",\n"
	       "  \"version\": \"%u.%u\",\n"
	       "  \"rate_msps\": %" PRIu32 ",\n"
	       "  \"taps\": %u,\n"
	       "  \"capture_samples\": %u,\n"
	       "  \"lags\": %u,\n"
	       "  \"capabilities\": \"0x%08" PRIx32 "\",\n"
	       "  \"status\": \"0x%08" PRIx32 "\",\n"
	       "  \"active_coefficient_generation\": \"0x%08" PRIx32 "\",\n"
	       "  \"contract_valid\": true\n"
	       "}\n",
	       serial, PSS_MMIO_BASE, info->identification,
	       info->version >> 16, info->version & 0xffffU, info->rate_msps,
	       info->geometry & 0xffU, (info->geometry >> 8) & 0xffU,
	       (info->geometry >> 16) & 0xffU, info->capabilities,
	       info->status, info->active_generation);
}

static void print_counters(const struct pss_counters *counters)
{
#define FIELD(name) printf("  \"" #name "\": %" PRIu32 ",\n", counters->name)
	printf("{\n");
	FIELD(telemetry_generation);
	FIELD(candidate_command_overrun);
	FIELD(coefficient_write_overrun);
	FIELD(queue_overrun);
	FIELD(admitted);
	FIELD(completed_capture);
	FIELD(rejected);
	FIELD(late);
	FIELD(duplicate);
	FIELD(overlap);
	FIELD(aborted);
	FIELD(valid_gap_abort);
	FIELD(index_jump_abort);
	FIELD(timestamp_abort);
	FIELD(capture_published);
	FIELD(capture_abort_discard);
	FIELD(capture_buffer_overrun);
	FIELD(capture_protocol_error);
	FIELD(engine_consumed);
	FIELD(correlator_bound_error);
	FIELD(reducer_processed);
	FIELD(reducer_emitted);
	FIELD(reducer_invalid);
	FIELD(reducer_bound_error);
	FIELD(reducer_protocol_error);
	FIELD(result_published);
	FIELD(result_overrun);
	printf("  \"result_consumed\": %" PRIu32 "\n", counters->result_consumed);
	printf("}\n");
#undef FIELD
}

static void print_track_result(const char *serial,
	const struct pss_track_result *result)
{
	unsigned int index;

	printf("{\n"
	       "  \"serial\": \"%s\",\n"
	       "  \"request_id\": \"0x%08" PRIx32 "\",\n"
	       "  \"scheduled_center\": %" PRIu64 ",\n"
	       "  \"winner_lag\": %" PRId32 ",\n"
	       "  \"winner_timestamp\": %" PRIu64 ",\n"
	       "  \"coefficient_generation\": \"0x%08" PRIx32 "\",\n"
	       "  \"correlation_real\": %" PRId64 ",\n"
	       "  \"correlation_imag\": %" PRId64 ",\n"
	       "  \"sample_energy\": %" PRId64 ",\n"
	       "  \"coefficient_energy\": %" PRId64 ",\n"
	       "  \"saturation_events\": %" PRIu32 ",\n"
	       "  \"telemetry_generation_before\": %" PRIu32 ",\n"
	       "  \"telemetry_generation_after\": %" PRIu32 ",\n"
	       "  \"all_counter_gates_passed\": true,\n"
	       "  \"result_released\": true,\n"
	       "  \"packet_words\": [",
	       serial, result->packet.request_id, result->scheduled_center,
	       result->packet.lag, result->packet.winner_timestamp,
	       result->packet.coefficient_generation,
	       result->packet.correlation_real, result->packet.correlation_imag,
	       result->packet.sample_energy, result->packet.coefficient_energy,
	       result->packet.saturation_events,
	       result->before.telemetry_generation,
	       result->after.telemetry_generation);
	for (index = 0; index < PSS_RESULT_WORDS; ++index)
		printf("%s\"0x%08" PRIx32 "\"", index ? ", " : "",
			result->packet.words[index]);
	printf("]\n}\n");
}

static void print_clock_slope(const char *serial, uint32_t duration_ms,
	const struct clock_observation *start,
	const struct clock_observation *end,
	const struct pss_clock_slope *slope, bool passed)
{
	printf("{\"serial\":\"%s\",\"kind\":\"accepted_sample_clock_slope\","
	       "\"expected_rate_hz\":%u,\"requested_duration_ms\":%" PRIu32 ","
	       "\"start_index\":%" PRIu64 ",\"end_index\":%" PRIu64 ","
	       "\"sample_delta\":%" PRIu64 ",\"elapsed_ns\":%" PRIu64 ","
	       "\"start_read_span_ns\":%" PRIu64 ","
	       "\"end_read_span_ns\":%" PRIu64 ","
	       "\"measured_rate_hz\":%.3f,\"error_ppm\":%.3f,"
	       "\"tolerance_ppm\":%.3f,\"passed\":%s}\n",
	       serial, PSS_RATE_MSPS * 1000000U, duration_ms,
	       slope->start_index, slope->end_index, slope->sample_delta,
	       slope->elapsed_ns, start->read_span_ns, end->read_span_ns,
	       slope->measured_rate_hz, slope->error_ppm, slope->tolerance_ppm,
	       passed ? "true" : "false");
}

struct batch_print_context {
	const char *serial;
};

static int print_batch_packet(void *context,
	const struct pss_batch_packet *completed)
{
	const struct batch_print_context *printer = context;
	unsigned int index;

	printf("{\"serial\":\"%s\",\"kind\":\"batch_result\","
	       "\"ordinal\":%" PRIu32 ",\"request_id\":\"0x%08" PRIx32 "\","
	       "\"center\":%" PRIu64 ",\"submit_lead_samples\":%" PRIu64 ","
	       "\"winner_lag\":%" PRId32 ",\"winner_timestamp\":%" PRIu64 ","
	       "\"coefficient_generation\":\"0x%08" PRIx32 "\","
	       "\"correlation_real\":%" PRId64 ","
	       "\"correlation_imag\":%" PRId64 ","
	       "\"sample_energy\":%" PRId64 ","
	       "\"coefficient_energy\":%" PRId64 ","
	       "\"saturation_events\":%" PRIu32 ",\"packet_words\":[",
	       printer->serial, completed->ordinal, completed->packet.request_id,
	       completed->packet.center_index, completed->submit_lead_samples,
	       completed->packet.lag, completed->packet.winner_timestamp,
	       completed->packet.coefficient_generation,
	       completed->packet.correlation_real,
	       completed->packet.correlation_imag,
	       completed->packet.sample_energy,
	       completed->packet.coefficient_energy,
	       completed->packet.saturation_events);
	for (index = 0; index < PSS_RESULT_WORDS; ++index)
		printf("%s\"0x%08" PRIx32 "\"", index ? "," : "",
			completed->packet.words[index]);
	printf("]}\n");
	return ferror(stdout) ? -1 : 0;
}

static uint32_t cli_counter_delta(uint32_t before, uint32_t after)
{
	return after - before;
}

static void print_batch_summary(const char *serial,
	const struct pss_batch_result *result)
{
	printf("{\"serial\":\"%s\",\"kind\":\"batch_summary\","
	       "\"initial_index\":%" PRIu64 ",\"first_center\":%" PRIu64 ","
	       "\"period_samples\":%" PRIu64 ",\"requested\":%" PRIu32 ","
	       "\"submitted\":%" PRIu32 ",\"completed\":%" PRIu32 ","
	       "\"queue_target\":%u,\"maximum_inflight\":%u,"
	       "\"minimum_queue_room\":%u,"
	       "\"minimum_submit_lead_samples\":%" PRIu64 ","
	       "\"maximum_submit_lead_samples\":%" PRIu64 ","
	       "\"monotonic_duration_ns\":%" PRIu64 ","
	       "\"admitted_delta\":%" PRIu32 ","
	       "\"completed_capture_delta\":%" PRIu32 ","
	       "\"capture_published_delta\":%" PRIu32 ","
	       "\"engine_consumed_delta\":%" PRIu32 ","
	       "\"reducer_processed_delta\":%" PRIu32 ","
	       "\"reducer_emitted_delta\":%" PRIu32 ","
	       "\"result_published_delta\":%" PRIu32 ","
	       "\"result_consumed_delta\":%" PRIu32 ","
	       "\"all_error_counter_deltas_zero\":true,"
	       "\"all_counter_gates_passed\":true}\n",
	       serial, result->initial_index, result->first_center,
	       result->period_samples, result->requested, result->submitted,
	       result->completed, result->queue_target, result->maximum_inflight,
	       result->minimum_queue_room, result->minimum_submit_lead_samples,
	       result->maximum_submit_lead_samples,
	       result->monotonic_end_ns - result->monotonic_start_ns,
	       cli_counter_delta(result->before.admitted, result->after.admitted),
	       cli_counter_delta(result->before.completed_capture,
			result->after.completed_capture),
	       cli_counter_delta(result->before.capture_published,
			result->after.capture_published),
	       cli_counter_delta(result->before.engine_consumed,
			result->after.engine_consumed),
	       cli_counter_delta(result->before.reducer_processed,
			result->after.reducer_processed),
	       cli_counter_delta(result->before.reducer_emitted,
			result->after.reducer_emitted),
	       cli_counter_delta(result->before.result_published,
			result->after.result_published),
	       cli_counter_delta(result->before.result_consumed,
			result->after.result_consumed));
}

static void print_injection_status(const char *serial,
	const struct pss_injection_status *status)
{
	printf("{\n"
	       "  \"serial\": \"%s\",\n"
	       "  \"injection_status\": \"0x%08" PRIx32 "\",\n"
	       "  \"fixture_count\": %u,\n"
	       "  \"fixture_generation\": \"0x%08" PRIx32 "\",\n"
	       "  \"start_index\": %" PRIu64 ",\n"
	       "  \"last_completed_generation\": \"0x%08" PRIx32 "\",\n"
	       "  \"fixture_valid\": %s,\n"
	       "  \"arm_ready\": %s,\n"
	       "  \"arm_pending\": %s,\n"
	       "  \"active\": %s,\n"
	       "  \"completed\": %s,\n"
	       "  \"rejected\": %s,\n"
	       "  \"mismatch\": %s,\n"
	       "  \"inflight\": %s\n"
	       "}\n",
	       serial, status->raw_status, status->fixture_count,
	       status->generation_stage, status->start_index,
	       status->last_completed_generation,
	       status->raw_status & PSS_INJECTION_FIXTURE_VALID ? "true" : "false",
	       status->raw_status & PSS_INJECTION_ARM_READY ? "true" : "false",
	       status->raw_status & PSS_INJECTION_ARM_PENDING ? "true" : "false",
	       status->raw_status & PSS_INJECTION_ACTIVE ? "true" : "false",
	       status->raw_status & PSS_INJECTION_COMPLETED ? "true" : "false",
	       status->raw_status & PSS_INJECTION_REJECTED ? "true" : "false",
	       status->raw_status & PSS_INJECTION_MISMATCH ? "true" : "false",
	       status->raw_status & PSS_INJECTION_INFLIGHT ? "true" : "false");
}

static void print_injected_track_result(const char *serial,
	const struct pss_track_result *result,
	const struct pss_injection_status *injection)
{
	unsigned int index;

	printf("{\n"
	       "  \"serial\": \"%s\",\n"
	       "  \"execution_path\": \"accepted-sample-injection\",\n"
	       "  \"injection_start\": %" PRIu64 ",\n"
	       "  \"injection_samples\": %u,\n"
	       "  \"injection_generation\": \"0x%08" PRIx32 "\",\n"
	       "  \"injection_status\": \"0x%08" PRIx32 "\",\n"
	       "  \"injection_completed\": true,\n"
	       "  \"injection_rejected\": false,\n"
	       "  \"injection_mismatch\": false,\n"
	       "  \"request_id\": \"0x%08" PRIx32 "\",\n"
	       "  \"scheduled_center\": %" PRIu64 ",\n"
	       "  \"winner_lag\": %" PRId32 ",\n"
	       "  \"winner_timestamp\": %" PRIu64 ",\n"
	       "  \"coefficient_generation\": \"0x%08" PRIx32 "\",\n"
	       "  \"correlation_real\": %" PRId64 ",\n"
	       "  \"correlation_imag\": %" PRId64 ",\n"
	       "  \"sample_energy\": %" PRId64 ",\n"
	       "  \"coefficient_energy\": %" PRId64 ",\n"
	       "  \"saturation_events\": %" PRIu32 ",\n"
	       "  \"telemetry_generation_before\": %" PRIu32 ",\n"
	       "  \"telemetry_generation_after\": %" PRIu32 ",\n"
	       "  \"all_counter_gates_passed\": true,\n"
	       "  \"result_released\": true,\n"
	       "  \"packet_words\": [",
	       serial, injection->start_index, PSS_INJECTION_SAMPLES,
	       injection->last_completed_generation, injection->raw_status,
	       result->packet.request_id, result->scheduled_center,
	       result->packet.lag, result->packet.winner_timestamp,
	       result->packet.coefficient_generation,
	       result->packet.correlation_real, result->packet.correlation_imag,
	       result->packet.sample_energy, result->packet.coefficient_energy,
	       result->packet.saturation_events,
	       result->before.telemetry_generation,
	       result->after.telemetry_generation);
	for (index = 0; index < PSS_RESULT_WORDS; ++index)
		printf("%s\"0x%08" PRIx32 "\"", index ? ", " : "",
			result->packet.words[index]);
	printf("]\n}\n");
}

static int option_value(int argc, char **argv, int *index, const char **value)
{
	if (*index + 1 >= argc) {
		fprintf(stderr, "%s requires a value\n", argv[*index]);
		return -1;
	}
	*value = argv[++*index];
	return 0;
}

int main(int argc, char **argv)
{
	const char *expected_serial = NULL;
	const char *devmem = "/dev/mem";
	const char *command;
	struct mapped_mmio mmio;
	struct pss_io io;
	struct pss_info info;
	char error[256] = {0};
	int argument = 1;
	int return_code = EXIT_FAILURE;

	while (argument < argc && argv[argument][0] == '-') {
		if (!strcmp(argv[argument], "--expect-serial")) {
			if (option_value(argc, argv, &argument, &expected_serial) < 0)
				return EXIT_FAILURE;
		} else if (!strcmp(argv[argument], "--devmem")) {
			if (option_value(argc, argv, &argument, &devmem) < 0)
				return EXIT_FAILURE;
		} else if (!strcmp(argv[argument], "--help")) {
			usage(stdout);
			return EXIT_SUCCESS;
		} else {
			fprintf(stderr, "unknown global option: %s\n", argv[argument]);
			usage(stderr);
			return EXIT_FAILURE;
		}
		++argument;
	}
	if (argument >= argc) {
		usage(stderr);
		return EXIT_FAILURE;
	}
	command = argv[argument++];
	if (verify_local_serial(expected_serial) < 0)
		return EXIT_FAILURE;
	if (map_mmio(&mmio, devmem) < 0)
		return EXIT_FAILURE;
	io.context = &mmio;
	io.read32 = mapped_read32;
	io.write32 = mapped_write32;
	if (pss_require_contract(&io, &info, error, sizeof(error)) < 0) {
		fprintf(stderr, "contract check failed: %s\n", error);
		goto out;
	}

	if (!strcmp(command, "info")) {
		if (argument != argc) {
			fprintf(stderr, "info takes no arguments\n");
			goto out;
		}
		print_info(expected_serial, &info);
		return_code = EXIT_SUCCESS;
	} else if (!strcmp(command, "snapshot")) {
		uint64_t index;

		if (argument != argc) {
			fprintf(stderr, "snapshot takes no arguments\n");
			goto out;
		}
		if (pss_read_current_index(&io, &index, error, sizeof(error)) < 0) {
			fprintf(stderr, "snapshot failed: %s\n", error);
			goto out;
		}
		printf("{\"serial\":\"%s\",\"current_index\":%" PRIu64 "}\n",
			expected_serial, index);
		return_code = EXIT_SUCCESS;
	} else if (!strcmp(command, "clock-slope")) {
		struct clock_observation start, end;
		struct pss_clock_slope slope = {0};
		uint32_t duration_ms = 1000U;
		double tolerance_ppm = 5000.0;
		int slope_status;

		while (argument < argc) {
			const char *value;

			if (option_value(argc, argv, &argument, &value) < 0)
				goto out;
			if (!strcmp(argv[argument - 1], "--duration-ms")) {
				if (parse_u32(value, &duration_ms) < 0 ||
				    duration_ms < 100U || duration_ms > 60000U)
					goto invalid_clock_slope;
			} else if (!strcmp(argv[argument - 1], "--tolerance-ppm")) {
				if (parse_double(value, &tolerance_ppm) < 0 ||
				    tolerance_ppm <= 0.0 || tolerance_ppm > 100000.0)
					goto invalid_clock_slope;
			} else {
				goto invalid_clock_slope;
			}
			++argument;
		}
		if (read_clock_observation(&io, &start, error, sizeof(error)) < 0 ||
		    sleep_milliseconds(duration_ms) < 0 ||
		    read_clock_observation(&io, &end, error, sizeof(error)) < 0) {
			if (!error[0])
				snprintf(error, sizeof(error), "observation sleep failed: %s",
					strerror(errno));
			fprintf(stderr, "clock-slope observation failed: %s\n", error);
			goto out;
		}
		slope_status = pss_calculate_clock_slope(start.index, end.index,
			start.midpoint_ns, end.midpoint_ns,
			PSS_RATE_MSPS * 1000000U, tolerance_ppm,
			&slope, error, sizeof(error));
		if (slope.elapsed_ns)
			print_clock_slope(expected_serial, duration_ms,
				&start, &end, &slope, slope_status == 0);
		if (slope_status < 0) {
			fprintf(stderr, "clock-slope gate failed: %s\n", error);
			goto out;
		}
		return_code = EXIT_SUCCESS;
		goto out;
invalid_clock_slope:
		fprintf(stderr,
			"invalid clock-slope arguments (duration must be 100..60000 ms)\n");
	} else if (!strcmp(command, "counters")) {
		struct pss_counters counters;
		unsigned int timeout_ms = 2000U;

		while (argument < argc) {
			const char *value;
			if (!strcmp(argv[argument], "--timeout-ms") &&
			    option_value(argc, argv, &argument, &value) == 0 &&
			    parse_timeout(value, &timeout_ms) == 0) {
				++argument;
				continue;
			}
			fprintf(stderr, "invalid counters option\n");
			goto out;
		}
		if (pss_snapshot_counters(&io, &counters, timeout_ms,
				error, sizeof(error)) < 0) {
			fprintf(stderr, "counter snapshot failed: %s\n", error);
			goto out;
		}
		print_counters(&counters);
		return_code = EXIT_SUCCESS;
	} else if (!strcmp(command, "inject-status")) {
		struct pss_injection_status injection;

		if (argument != argc) {
			fprintf(stderr, "inject-status takes no arguments\n");
			goto out;
		}
		if (pss_read_injection_status(&io, &injection,
				error, sizeof(error)) < 0) {
			fprintf(stderr, "injection status failed: %s\n", error);
			goto out;
		}
		print_injection_status(expected_serial, &injection);
		return_code = EXIT_SUCCESS;
	} else if (!strcmp(command, "inject-load")) {
		const char *sample_path = NULL;
		struct pss_ci16 samples[PSS_INJECTION_SAMPLES];
		struct pss_injection_status injection;
		uint32_t generation = 0;
		unsigned int timeout_ms = 2000U;

		while (argument < argc) {
			const char *value;
			if (option_value(argc, argv, &argument, &value) < 0)
				goto out;
			if (!strcmp(argv[argument - 1], "--samples"))
				sample_path = value;
			else if (!strcmp(argv[argument - 1], "--generation")) {
				if (parse_u32(value, &generation) < 0) {
					fprintf(stderr, "invalid injection generation\n");
					goto out;
				}
			} else if (!strcmp(argv[argument - 1], "--timeout-ms")) {
				if (parse_timeout(value, &timeout_ms) < 0) {
					fprintf(stderr, "invalid injection timeout\n");
					goto out;
				}
			} else {
				fprintf(stderr, "unknown inject-load option: %s\n",
					argv[argument - 1]);
				goto out;
			}
			++argument;
		}
		if (!sample_path || !generation) {
			fprintf(stderr,
				"inject-load requires --samples and nonzero --generation\n");
			goto out;
		}
		if (pss_read_injection_file(sample_path, samples,
				error, sizeof(error)) < 0 ||
		    pss_load_injection_fixture(&io, samples, generation, timeout_ms,
				&injection, error, sizeof(error)) < 0) {
			fprintf(stderr, "injection load failed: %s\n", error);
			goto out;
		}
		print_injection_status(expected_serial, &injection);
		return_code = EXIT_SUCCESS;
	} else if (!strcmp(command, "inject-track")) {
		struct pss_track_request request = {
			.lead_samples = PSS_DEFAULT_LEAD_SAMPLES,
			.timeout_ms = 5000U,
		};
		struct pss_track_result result;
		struct pss_injection_status injection;
		uint64_t current, start = 0;
		bool lead_seen = false;
		bool start_seen = false;

		while (argument < argc) {
			const char *value;
			if (option_value(argc, argv, &argument, &value) < 0)
				goto out;
			if (!strcmp(argv[argument - 1], "--request")) {
				if (parse_u32(value, &request.request_id) < 0)
					goto invalid_inject_track;
			} else if (!strcmp(argv[argument - 1], "--lead")) {
				if (start_seen || parse_u64(value, &request.lead_samples) < 0)
					goto invalid_inject_track;
				lead_seen = true;
			} else if (!strcmp(argv[argument - 1], "--start")) {
				if (lead_seen || parse_u64(value, &start) < 0)
					goto invalid_inject_track;
				start_seen = true;
			} else if (!strcmp(argv[argument - 1], "--timeout-ms")) {
				if (parse_timeout(value, &request.timeout_ms) < 0)
					goto invalid_inject_track;
			} else {
				goto invalid_inject_track;
			}
			++argument;
		}
		if (!request.request_id)
			goto invalid_inject_track;
		if (pss_read_injection_status(&io, &injection,
				error, sizeof(error)) < 0 ||
		    !(injection.raw_status & PSS_INJECTION_FIXTURE_VALID) ||
		    !injection.generation_stage) {
			fprintf(stderr, "no valid injection fixture is loaded: %s\n", error);
			goto out;
		}
		if (!start_seen) {
			if (pss_read_current_index(&io, &current,
					error, sizeof(error)) < 0 ||
			    UINT64_MAX - current < request.lead_samples) {
				fprintf(stderr, "cannot derive injection start: %s\n", error);
				goto out;
			}
			start = current + request.lead_samples;
		}
		if (UINT64_MAX - start < PSS_INJECTION_SAMPLES - 1U) {
			fprintf(stderr, "injection window overflows the accepted-sample index\n");
			goto out;
		}
		if (pss_arm_injection(&io, start, request.timeout_ms,
				&injection, error, sizeof(error)) < 0) {
			fprintf(stderr, "injection arm failed: %s\n", error);
			goto out;
		}
		request.center = start + 32U;
		request.center_is_explicit = true;
		if (pss_track_one(&io, &request, &result,
				error, sizeof(error)) < 0 ||
		    pss_wait_injection_complete(&io, injection.generation_stage,
				request.timeout_ms, &injection,
				error, sizeof(error)) < 0) {
			fprintf(stderr, "injected track failed: %s\n", error);
			goto out;
		}
		print_injected_track_result(expected_serial, &result, &injection);
		return_code = EXIT_SUCCESS;
		goto out;
invalid_inject_track:
		fprintf(stderr, "invalid inject-track arguments\n");
	} else if (!strcmp(command, "load")) {
		const char *coefficient_path = NULL;
		struct pss_ci16 coefficients[PSS_COEFFICIENT_COUNT];
		uint32_t generation = 0;
		unsigned int timeout_ms = 2000U;

		while (argument < argc) {
			const char *value;
			if (option_value(argc, argv, &argument, &value) < 0)
				goto out;
			if (!strcmp(argv[argument - 1], "--coeff"))
				coefficient_path = value;
			else if (!strcmp(argv[argument - 1], "--generation")) {
				if (parse_u32(value, &generation) < 0) {
					fprintf(stderr, "invalid generation\n");
					goto out;
				}
			} else if (!strcmp(argv[argument - 1], "--timeout-ms")) {
				if (parse_timeout(value, &timeout_ms) < 0) {
					fprintf(stderr, "invalid timeout\n");
					goto out;
				}
			} else {
				fprintf(stderr, "unknown load option: %s\n", argv[argument - 1]);
				goto out;
			}
			++argument;
		}
		if (!coefficient_path || !generation) {
			fprintf(stderr, "load requires --coeff and nonzero --generation\n");
			goto out;
		}
		if (pss_read_ci16_file(coefficient_path, coefficients,
				error, sizeof(error)) < 0 ||
		    pss_load_coefficients(&io, coefficients, generation, timeout_ms,
				error, sizeof(error)) < 0) {
			fprintf(stderr, "coefficient load failed: %s\n", error);
			goto out;
		}
		printf("{\"serial\":\"%s\",\"coefficient_generation\":"
		       "\"0x%08" PRIx32 "\",\"taps_loaded\":%u}\n",
		       expected_serial, generation, PSS_COEFFICIENT_COUNT);
		return_code = EXIT_SUCCESS;
	} else if (!strcmp(command, "track-batch")) {
		struct pss_batch_request request = {
			.period_samples = 20000U,
			.lead_samples = PSS_DEFAULT_LEAD_SAMPLES,
			.queue_target = PSS_DEFAULT_QUEUE_TARGET,
			.timeout_ms = 5000U,
		};
		struct pss_batch_result result;
		struct batch_print_context printer = {.serial = expected_serial};
		bool lead_seen = false;

		while (argument < argc) {
			const char *value;
			uint32_t parsed;

			if (option_value(argc, argv, &argument, &value) < 0)
				goto out;
			if (!strcmp(argv[argument - 1], "--request-base")) {
				if (parse_u32(value, &request.request_id_base) < 0)
					goto invalid_track_batch;
			} else if (!strcmp(argv[argument - 1], "--count")) {
				if (parse_u32(value, &request.count) < 0)
					goto invalid_track_batch;
			} else if (!strcmp(argv[argument - 1], "--period")) {
				if (parse_u64(value, &request.period_samples) < 0)
					goto invalid_track_batch;
			} else if (!strcmp(argv[argument - 1], "--lead")) {
				if (request.first_center_is_explicit ||
				    parse_u64(value, &request.lead_samples) < 0)
					goto invalid_track_batch;
				lead_seen = true;
			} else if (!strcmp(argv[argument - 1], "--first-center")) {
				if (lead_seen || parse_u64(value, &request.first_center) < 0)
					goto invalid_track_batch;
				request.first_center_is_explicit = true;
			} else if (!strcmp(argv[argument - 1], "--queue-target")) {
				if (parse_u32(value, &parsed) < 0 ||
				    !parsed || parsed > PSS_COMMAND_FIFO_USABLE)
					goto invalid_track_batch;
				request.queue_target = parsed;
			} else if (!strcmp(argv[argument - 1], "--timeout-ms")) {
				if (parse_timeout(value, &request.timeout_ms) < 0)
					goto invalid_track_batch;
			} else {
				goto invalid_track_batch;
			}
			++argument;
		}
		if (!request.request_id_base || !request.count)
			goto invalid_track_batch;
		if (pss_track_batch(&io, &request, print_batch_packet, &printer,
				&result, error, sizeof(error)) < 0) {
			fprintf(stderr, "track-batch failed: %s\n", error);
			goto out;
		}
		print_batch_summary(expected_serial, &result);
		if (fflush(stdout) < 0) {
			fprintf(stderr, "track-batch output failed: %s\n", strerror(errno));
			goto out;
		}
		return_code = EXIT_SUCCESS;
		goto out;
invalid_track_batch:
		fprintf(stderr, "invalid track-batch arguments\n");
	} else if (!strcmp(command, "track")) {
		struct pss_track_request request = {
			.lead_samples = PSS_DEFAULT_LEAD_SAMPLES,
			.timeout_ms = 2000U,
		};
		struct pss_track_result result;
		bool lead_seen = false;

		while (argument < argc) {
			const char *value;
			if (option_value(argc, argv, &argument, &value) < 0)
				goto out;
			if (!strcmp(argv[argument - 1], "--request")) {
				if (parse_u32(value, &request.request_id) < 0)
					goto invalid_track;
			} else if (!strcmp(argv[argument - 1], "--lead")) {
				if (request.center_is_explicit ||
				    parse_u64(value, &request.lead_samples) < 0)
					goto invalid_track;
				lead_seen = true;
			} else if (!strcmp(argv[argument - 1], "--center")) {
				if (lead_seen || parse_u64(value, &request.center) < 0)
					goto invalid_track;
				request.center_is_explicit = true;
			} else if (!strcmp(argv[argument - 1], "--timeout-ms")) {
				if (parse_timeout(value, &request.timeout_ms) < 0)
					goto invalid_track;
			} else {
				goto invalid_track;
			}
			++argument;
		}
		if (!request.request_id)
			goto invalid_track;
		if (pss_track_one(&io, &request, &result, error, sizeof(error)) < 0) {
			fprintf(stderr, "track failed: %s\n", error);
			goto out;
		}
		print_track_result(expected_serial, &result);
		return_code = EXIT_SUCCESS;
		goto out;
invalid_track:
		fprintf(stderr, "invalid track arguments\n");
	} else {
		fprintf(stderr, "unknown command: %s\n", command);
		usage(stderr);
	}

out:
	unmap_mmio(&mmio);
	return return_code;
}
