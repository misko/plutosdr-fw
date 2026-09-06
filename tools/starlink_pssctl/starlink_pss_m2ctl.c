// SPDX-License-Identifier: GPL-2.0-or-later
#define _POSIX_C_SOURCE 200809L

#include "starlink_pss_acquisition.h"
#include "starlink_pss_m2_qualification.h"
#include "starlink_pss_periodic_injection.h"

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <unistd.h>

#define PSS_INJECTION_MMIO_BASE UINT64_C(0x79030000)
#define PSS_ACQUISITION_MMIO_BASE UINT64_C(0x79040000)
#define MMIO_SPAN 0x1000U
#define SERIAL_FILE "/etc/serial"
#define ERROR_SIZE 256U
#define DEFAULT_TIMEOUT_MS 2000U
#define DEFAULT_PHASES "0,19999,7311"
#define MAX_CASES 16U

struct mapped_mmio {
	int fd;
	void *mapping;
	size_t mapping_size;
	volatile uint32_t *registers;
};

static volatile sig_atomic_t interrupted;

static void usage(FILE *stream)
{
	fprintf(stream,
		"usage: starlink_pss_m2ctl --expect-serial SERIAL [--devmem PATH] info\n"
		"       starlink_pss_m2ctl --expect-serial SERIAL --fixture PATH "
		"--scores PATH [--devmem PATH] qualify [--phases CSV] "
		"[--timeout-ms N]\n"
		"\n"
		"Runs deterministic internal 15 MS/s PSS timing qualification. The "
		"default phases are %s. It refuses serial, ABI, geometry, health, "
		"continuity, or exact-map mismatches and never claims live PSS, SSS, "
		"or frame lock.\n",
		DEFAULT_PHASES);
}

static void catch_signal(int signal_number)
{
	(void)signal_number;
	interrupted = 1;
}

static int install_signal_handlers(void)
{
	struct sigaction action;

	memset(&action, 0, sizeof(action));
	action.sa_handler = catch_signal;
	return sigemptyset(&action.sa_mask) < 0 ||
		sigaction(SIGINT, &action, NULL) < 0 ||
		sigaction(SIGTERM, &action, NULL) < 0 ||
		sigaction(SIGHUP, &action, NULL) < 0 ||
		sigaction(SIGPIPE, &action, NULL) < 0 ? -1 : 0;
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

static int parse_timeout(const char *text, unsigned int *value)
{
	char *end;
	unsigned long parsed;

	if (!text || !*text)
		return -1;
	errno = 0;
	parsed = strtoul(text, &end, 0);
	if (errno || *end || !parsed || parsed > 60000UL)
		return -1;
	*value = (unsigned int)parsed;
	return 0;
}

static bool valid_serial(const char *serial)
{
	size_t index, length;

	if (!serial)
		return false;
	length = strlen(serial);
	if (!length || length >= 128U)
		return false;
	for (index = 0; index < length; ++index) {
		if (!isxdigit((unsigned char)serial[index]))
			return false;
	}
	return true;
}

static int verify_local_serial(const char *expected)
{
	FILE *input;
	char actual[128];
	size_t length;
	int extra;

	if (!valid_serial(expected)) {
		fprintf(stderr, "--expect-serial must be a nonempty hexadecimal serial\n");
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
	while ((extra = fgetc(input)) != EOF) {
		if (!isspace((unsigned char)extra)) {
			fprintf(stderr, "serial in %s has extra data\n", SERIAL_FILE);
			fclose(input);
			return -1;
		}
	}
	fclose(input);
	length = strlen(actual);
	while (length && isspace((unsigned char)actual[length - 1U]))
		actual[--length] = '\0';
	if (!valid_serial(actual) || strcmp(actual, expected)) {
		fprintf(stderr, "radio serial mismatch: expected %s, local radio is %s\n",
			expected, actual);
		return -1;
	}
	return 0;
}

static int map_mmio(struct mapped_mmio *mmio, const char *path,
	uint64_t base, const char *label)
{
	long page_size = sysconf(_SC_PAGESIZE);
	off_t aligned_base;
	size_t page_offset;

	memset(mmio, 0, sizeof(*mmio));
	mmio->fd = -1;
	if (page_size <= 0 ||
	    ((uint64_t)page_size & ((uint64_t)page_size - 1U))) {
		fprintf(stderr, "cannot determine a power-of-two system page size\n");
		return -1;
	}
	aligned_base = (off_t)(base & ~((uint64_t)page_size - 1U));
	page_offset = (size_t)(base - (uint64_t)aligned_base);
	mmio->mapping_size = page_offset + MMIO_SPAN;
	mmio->fd = open(path, O_RDWR | O_SYNC | O_CLOEXEC);
	if (mmio->fd < 0) {
		fprintf(stderr, "cannot open %s: %s\n", path, strerror(errno));
		return -1;
	}
	mmio->mapping = mmap(NULL, mmio->mapping_size, PROT_READ | PROT_WRITE,
		MAP_SHARED, mmio->fd, aligned_base);
	if (mmio->mapping == MAP_FAILED) {
		fprintf(stderr, "cannot map %s MMIO: %s\n", label, strerror(errno));
		close(mmio->fd);
		mmio->fd = -1;
		return -1;
	}
	mmio->registers = (volatile uint32_t *)
		((uint8_t *)mmio->mapping + page_offset);
	return 0;
}

static void unmap_mmio(struct mapped_mmio *mmio)
{
	if (mmio->mapping && mmio->mapping != MAP_FAILED)
		munmap(mmio->mapping, mmio->mapping_size);
	if (mmio->fd >= 0)
		close(mmio->fd);
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

static int parse_hex_line(const char *line, size_t digits, uint32_t *value)
{
	size_t index;
	uint32_t parsed = 0U;

	if (!line || !value || strlen(line) != digits)
		return -1;
	for (index = 0; index < digits; ++index) {
		unsigned int nibble;

		if (line[index] >= '0' && line[index] <= '9')
			nibble = (unsigned int)(line[index] - '0');
		else if (line[index] >= 'a' && line[index] <= 'f')
			nibble = (unsigned int)(line[index] - 'a') + 10U;
		else
			return -1;
		parsed = (parsed << 4) | nibble;
	}
	*value = parsed;
	return 0;
}

static int read_hex_words(const char *path, size_t digits, uint32_t *words,
	size_t word_count, char *error, size_t error_size)
{
	FILE *input;
	char line[64];
	size_t count = 0U;

	input = fopen(path, "r");
	if (!input) {
		snprintf(error, error_size, "cannot open %s: %s", path, strerror(errno));
		return -1;
	}
	while (fgets(line, sizeof(line), input)) {
		size_t length = strlen(line);
		uint32_t value;

		if (!length || line[length - 1U] != '\n' || count >= word_count) {
			snprintf(error, error_size, "%s has invalid line geometry", path);
			fclose(input);
			return -1;
		}
		line[--length] = '\0';
		if (parse_hex_line(line, digits, &value) < 0) {
			snprintf(error, error_size,
				"%s line %zu is not %zu lowercase hex digits",
				path, count + 1U, digits);
			fclose(input);
			return -1;
		}
		words[count++] = value;
	}
	if (ferror(input)) {
		snprintf(error, error_size, "cannot read %s", path);
		fclose(input);
		return -1;
	}
	fclose(input);
	if (count != word_count) {
		snprintf(error, error_size, "%s has %zu words, expected %zu",
			path, count, word_count);
		return -1;
	}
	return 0;
}

static int load_vectors(const char *fixture_path, const char *scores_path,
	uint32_t *fixture_qi, uint8_t *scores, char *error, size_t error_size)
{
	uint32_t fixture_iq[PSS_INJECTION_FIXTURE_SAMPLES];
	uint32_t score_words[PSS_MAP_PHASE_BINS];
	size_t index;

	if (read_hex_words(fixture_path, 8U, fixture_iq,
			PSS_INJECTION_FIXTURE_SAMPLES, error, error_size) < 0 ||
	    read_hex_words(scores_path, 2U, score_words,
			PSS_MAP_PHASE_BINS, error, error_size) < 0)
		return -1;
	for (index = 0; index < PSS_INJECTION_FIXTURE_SAMPLES; ++index) {
		uint32_t i = fixture_iq[index] >> 16;
		uint32_t q = fixture_iq[index] & UINT32_C(0xffff);

		fixture_qi[index] = (q << 16) | i;
	}
	for (index = 0; index < PSS_MAP_PHASE_BINS; ++index)
		scores[index] = (uint8_t)score_words[index];
	return 0;
}

static int parse_phases(const char *text, uint32_t *phases, size_t *count)
{
	const char *cursor = text;
	size_t parsed_count = 0U;

	if (!text || !*text || !phases || !count)
		return -1;
	for (;;) {
		char *end;
		unsigned long value;

		if (parsed_count >= MAX_CASES)
			return -1;
		errno = 0;
		value = strtoul(cursor, &end, 10);
		if (errno || end == cursor || value >= PSS_MAP_PHASE_BINS)
			return -1;
		phases[parsed_count++] = (uint32_t)value;
		if (!*end)
			break;
		if (*end != ',')
			return -1;
		cursor = end + 1;
		if (!*cursor)
			return -1;
	}
	*count = parsed_count;
	return 0;
}

static int require_copy_health_and_continuity(const struct pss_map_copy *previous,
	bool have_previous, const struct pss_map_copy *current,
	char *error, size_t error_size)
{
	if (!pss_map_snapshot_fault_free(&current->before) ||
	    !pss_map_snapshot_fault_free(&current->after) ||
	    current->before.health_flags || current->after.health_flags ||
	    current->before.score_denominator_zero_count ||
	    current->after.score_denominator_zero_count) {
		snprintf(error, error_size,
			"phase-map health fault at generation %" PRIu32,
			current->generation);
		return -1;
	}
	if (have_previous && !pss_map_copies_contiguous(previous, current)) {
		snprintf(error, error_size,
			"phase-map continuity failure between generations %" PRIu32
			" and %" PRIu32, previous->generation, current->generation);
		return -1;
	}
	return 0;
}

static void print_case(const char *serial, size_t case_index,
	const struct pss_m2_case_plan *plan, const struct pss_map_copy *copy,
	const struct pss_m2_map_result *result,
	const struct pss_injection_state *injection_state)
{
	printf("{\"schema\":\"starlink-pss-m2ctl.case.v1\","
	       "\"stimulus\":\"deterministic_internal\","
	       "\"serial\":\"%s\",\"case\":%zu,"
	       "\"requested_phase\":%" PRIu32
	       ",\"injection_start_index\":%" PRIu64
	       ",\"target_map_start_index\":%" PRIu64
	       ",\"map_generation\":%" PRIu32
	       ",\"actual_peak_phase\":%" PRIu32
	       ",\"actual_peak_value\":%u,\"actual_runner_up_value\":%u,"
	       "\"mismatch_count\":%" PRIu32
	       ",\"unique_peak\":%s,\"exact_map\":%s,"
	       "\"completed_generation\":%" PRIu32
	       ",\"completed_repetitions\":%" PRIu32
	       ",\"pss_timing_qualified\":%s,"
	       "\"live_pss_detected\":false,\"sss_detected\":false,"
	       "\"frame_lock_claim\":false}\n",
	       serial, case_index, plan->requested_phase,
	       plan->injection_start, plan->target_map_start, copy->generation,
	       result->actual_peak_phase, result->actual_peak_value,
	       result->actual_runner_up_value, result->mismatch_count,
	       result->unique_peak ? "true" : "false",
	       result->exact ? "true" : "false",
	       injection_state->last_completed_generation,
	       injection_state->last_completed_repetitions,
	       result->exact ? "true" : "false");
	fflush(stdout);
}

static int print_info(const char *serial, const struct pss_map_info *map_info,
	const struct pss_injection_io *injection_io,
	const struct pss_injection_info *injection_info,
	char *error, size_t error_size)
{
	struct pss_injection_state state;
	uint64_t current_index;

	if (pss_injection_read_state(injection_io, &state, error, error_size) < 0 ||
	    pss_injection_read_current_index(injection_io, &current_index,
			error, error_size) < 0)
		return -1;
	printf("{\"schema\":\"starlink-pss-m2ctl.info.v1\","
	       "\"claim_scope\":\"deterministic_qualification_contract_only\","
	       "\"serial\":\"%s\",\"input_rate_msps\":%" PRIu32
	       ",\"psma_version\":\"0x%08" PRIx32 "\","
	       "\"psma_status\":\"0x%08" PRIx32 "\","
	       "\"psma_enabled\":%s,"
	       "\"pssi_identification\":\"0x%08" PRIx32 "\","
	       "\"pssi_version\":\"0x%08" PRIx32 "\","
	       "\"pssi_capabilities\":\"0x%08" PRIx32 "\","
	       "\"pssi_geometry\":\"0x%08" PRIx32 "\","
	       "\"pssi_period_samples\":%" PRIu32
	       ",\"pssi_last_sample_offset\":%" PRIu64
	       ",\"pssi_current_index\":%" PRIu64
	       ",\"pssi_status\":\"0x%08" PRIx32 "\","
	       "\"pssi_fixture_count\":%" PRIu32
	       ",\"pssi_fault_free\":%s,"
	       "\"live_pss_detected\":false,\"sss_detected\":false,"
	       "\"frame_lock_claim\":false}\n",
	       serial, map_info->input_rate_msps, map_info->version,
	       map_info->status,
	       (map_info->status & PSS_MAP_STATUS_ENABLED) ? "true" : "false",
	       injection_info->identification, injection_info->version,
	       injection_info->capabilities, injection_info->geometry,
	       injection_info->period_samples, injection_info->last_sample_offset,
	       current_index, state.status, state.fixture_count,
	       pss_injection_state_fault_free(&state) ? "true" : "false");
	return 0;
}

static int run_qualification(const char *serial,
	const struct pss_map_io *map_io, const struct pss_map_info *map_info,
	const struct pss_injection_io *injection_io,
	const uint32_t *fixture, const uint8_t *scores,
	const uint32_t *phases, size_t phase_count, unsigned int timeout_ms,
	char *error, size_t error_size)
{
	const uint32_t fixture_generation = UINT32_C(0x15020001);
	uint16_t *actual_map = NULL, *expected_map = NULL;
	struct pss_map_copy previous_copy, current_copy;
	struct pss_map_snapshot initial_snapshot, final_snapshot;
	size_t case_index;
	uint32_t maps_copied = 0U, first_map_generation = 0U;
	bool have_previous = false, enabled = false;
	int result = -1;

	if (map_info->version != PSS_MAP_VERSION_1_1 ||
	    map_info->input_rate_msps != 15U ||
	    (map_info->status & PSS_MAP_STATUS_ENABLED)) {
		snprintf(error, error_size,
			"M2 requires a disabled exact 15 MS/s PSMA v1.1 engine");
		return -1;
	}
	actual_map = calloc(PSS_MAP_PHASE_BINS, sizeof(*actual_map));
	expected_map = calloc(PSS_MAP_PHASE_BINS, sizeof(*expected_map));
	if (!actual_map || !expected_map) {
		snprintf(error, error_size, "cannot allocate fixed M2 map buffers");
		goto done;
	}
	if (pss_injection_load_fixture(injection_io, fixture,
			PSS_INJECTION_FIXTURE_SAMPLES, fixture_generation,
			timeout_ms, error, error_size) < 0 ||
	    pss_map_set_enabled(map_io, true, true, error, error_size) < 0)
		goto done;
	enabled = true;
	if (pss_map_take_snapshot(map_io, &initial_snapshot, timeout_ms,
			error, error_size) < 0 ||
	    !pss_map_snapshot_fault_free(&initial_snapshot) ||
	    initial_snapshot.health_flags ||
	    initial_snapshot.score_denominator_zero_count) {
		if (!error[0])
			snprintf(error, error_size, "initial M2 map health is faulted");
		goto done;
	}
	if (pss_map_wait_copy(map_io, actual_map, PSS_MAP_PHASE_BINS,
			&previous_copy, timeout_ms, error, error_size) < 0 ||
	    require_copy_health_and_continuity(NULL, false, &previous_copy,
			error, error_size) < 0)
		goto done;
	have_previous = true;
	maps_copied++;
	first_map_generation = previous_copy.generation;

	for (case_index = 0; case_index < phase_count; ++case_index) {
		struct pss_m2_case_plan plan;
		struct pss_m2_map_result map_result;
		struct pss_injection_state injection_state;
		uint64_t current_index;

		if (interrupted) {
			snprintf(error, error_size, "M2 qualification interrupted");
			goto done;
		}
		if (pss_injection_read_current_index(injection_io, &current_index,
				error, error_size) < 0 ||
		    pss_m2_plan_case(current_index, previous_copy.start_index,
				phases[case_index], &plan, error, error_size) < 0 ||
		    pss_m2_build_expected_map(scores, PSS_MAP_PHASE_BINS, &plan,
				expected_map, PSS_MAP_PHASE_BINS,
				error, error_size) < 0 ||
		    pss_injection_arm(injection_io, plan.injection_start,
				timeout_ms, error, error_size) < 0)
			goto done;

		for (;;) {
			if (interrupted) {
				snprintf(error, error_size, "M2 qualification interrupted");
				goto done;
			}
			if (pss_map_wait_copy(map_io, actual_map, PSS_MAP_PHASE_BINS,
					&current_copy, timeout_ms, error, error_size) < 0 ||
			    require_copy_health_and_continuity(&previous_copy,
					have_previous, &current_copy,
					error, error_size) < 0)
				goto done;
			maps_copied++;
			previous_copy = current_copy;
			if (current_copy.start_index >= plan.target_map_start)
				break;
		}
		if (current_copy.start_index != plan.target_map_start) {
			snprintf(error, error_size,
				"M2 target map was skipped: expected=%" PRIu64
				" observed=%" PRIu64,
				plan.target_map_start, current_copy.start_index);
			goto done;
		}
		if (pss_m2_check_map(actual_map, PSS_MAP_PHASE_BINS,
				expected_map, PSS_MAP_PHASE_BINS, phases[case_index],
				&map_result, error, error_size) < 0)
			goto done;
		if (!map_result.exact) {
			snprintf(error, error_size,
				"M2 exact map mismatch at requested phase %" PRIu32
				": mismatches=%" PRIu32 " first=%" PRIu32
				" expected=%u actual=%u peak=%" PRIu32,
				phases[case_index], map_result.mismatch_count,
				map_result.first_mismatch_phase,
				map_result.first_mismatch_expected,
				map_result.first_mismatch_actual,
				map_result.actual_peak_phase);
			goto done;
		}
		if (pss_injection_wait_complete(injection_io, fixture_generation,
				timeout_ms, &injection_state, error, error_size) < 0)
			goto done;
		print_case(serial, case_index, &plan, &current_copy,
			&map_result, &injection_state);
	}
	if (pss_map_take_snapshot(map_io, &final_snapshot, timeout_ms,
			error, error_size) < 0 ||
	    !pss_map_snapshot_fault_free(&final_snapshot) ||
	    final_snapshot.health_flags ||
	    final_snapshot.score_denominator_zero_count) {
		if (!error[0])
			snprintf(error, error_size, "final M2 map health is faulted");
		goto done;
	}
	if (pss_map_set_enabled(map_io, false, true, error, error_size) < 0)
		goto done;
	enabled = false;
	printf("{\"schema\":\"starlink-pss-m2ctl.summary.v1\","
	       "\"stimulus\":\"deterministic_internal\","
	       "\"serial\":\"%s\",\"input_rate_msps\":15,"
	       "\"cases_requested\":%zu,\"cases_passed\":%zu,"
	       "\"maps_copied\":%" PRIu32
	       ",\"first_map_generation\":%" PRIu32
	       ",\"last_map_generation\":%" PRIu32
	       ",\"final_health_flags\":\"0x%08" PRIx32 "\","
	       "\"fault_free_epoch\":true,\"continuity_ok\":true,"
	       "\"pss_timing_qualified\":true,"
	       "\"live_pss_detected\":false,\"sss_detected\":false,"
	       "\"frame_lock_claim\":false}\n",
	       serial, phase_count, phase_count, maps_copied,
	       first_map_generation,
	       previous_copy.generation, final_snapshot.health_flags);
	fflush(stdout);
	result = 0;

done:
	if (enabled) {
		char cleanup_error[ERROR_SIZE] = {0};

		if (pss_map_set_enabled(map_io, false, true,
				cleanup_error, sizeof(cleanup_error)) < 0)
			fprintf(stderr, "M2 acquisition cleanup failed: %s\n",
				cleanup_error);
		result = -1;
	}
	free(expected_map);
	free(actual_map);
	return result;
}

int main(int argc, char **argv)
{
	const char *expected_serial = NULL, *fixture_path = NULL, *scores_path = NULL;
	const char *devmem = "/dev/mem", *phase_text = DEFAULT_PHASES;
	const char *command;
	struct mapped_mmio injection_mmio = {.fd = -1};
	struct mapped_mmio map_mmio_region = {.fd = -1};
	struct pss_injection_io injection_io;
	struct pss_injection_info injection_info;
	struct pss_map_io map_io;
	struct pss_map_info map_info;
	uint32_t fixture[PSS_INJECTION_FIXTURE_SAMPLES];
	uint8_t scores[PSS_MAP_PHASE_BINS];
	uint32_t phases[MAX_CASES];
	size_t phase_count = 0U;
	unsigned int timeout_ms = DEFAULT_TIMEOUT_MS;
	char error[ERROR_SIZE] = {0};
	int argument = 1, return_code = EXIT_FAILURE;

	while (argument < argc && argv[argument][0] == '-') {
		if (!strcmp(argv[argument], "--help")) {
			usage(stdout);
			return EXIT_SUCCESS;
		} else if (!strcmp(argv[argument], "--expect-serial")) {
			if (option_value(argc, argv, &argument, &expected_serial) < 0)
				return EXIT_FAILURE;
		} else if (!strcmp(argv[argument], "--fixture")) {
			if (option_value(argc, argv, &argument, &fixture_path) < 0)
				return EXIT_FAILURE;
		} else if (!strcmp(argv[argument], "--scores")) {
			if (option_value(argc, argv, &argument, &scores_path) < 0)
				return EXIT_FAILURE;
		} else if (!strcmp(argv[argument], "--devmem")) {
			if (option_value(argc, argv, &argument, &devmem) < 0)
				return EXIT_FAILURE;
		} else {
			fprintf(stderr, "unknown global option: %s\n", argv[argument]);
			return EXIT_FAILURE;
		}
		++argument;
	}
	if (argument >= argc) {
		usage(stderr);
		return EXIT_FAILURE;
	}
	command = argv[argument++];
	if (strcmp(command, "qualify") && strcmp(command, "info")) {
		fprintf(stderr, "unknown command: %s\n", command);
		return EXIT_FAILURE;
	}
	while (!strcmp(command, "qualify") && argument < argc) {
		const char *value;

		if (!strcmp(argv[argument], "--phases")) {
			if (option_value(argc, argv, &argument, &phase_text) < 0)
				return EXIT_FAILURE;
		} else if (!strcmp(argv[argument], "--timeout-ms")) {
			if (option_value(argc, argv, &argument, &value) < 0 ||
			    parse_timeout(value, &timeout_ms) < 0) {
				fprintf(stderr, "invalid timeout\n");
				return EXIT_FAILURE;
			}
		} else {
			fprintf(stderr, "invalid qualify option: %s\n", argv[argument]);
			return EXIT_FAILURE;
		}
		++argument;
	}
	if (!strcmp(command, "info") && argument != argc) {
		fprintf(stderr, "info takes no arguments\n");
		return EXIT_FAILURE;
	}
	if (!strcmp(command, "qualify") &&
	    (!fixture_path || !scores_path ||
	     parse_phases(phase_text, phases, &phase_count) < 0)) {
		fprintf(stderr, "fixture, scores, and valid phase list are required\n");
		return EXIT_FAILURE;
	}
	if (!strcmp(command, "qualify") &&
	    load_vectors(fixture_path, scores_path, fixture, scores,
			error, sizeof(error)) < 0) {
		fprintf(stderr, "M2 vector load failed: %s\n", error);
		return EXIT_FAILURE;
	}
	if (verify_local_serial(expected_serial) < 0)
		return EXIT_FAILURE;
	if (install_signal_handlers() < 0) {
		fprintf(stderr, "cannot install cleanup signal handlers: %s\n",
			strerror(errno));
		return EXIT_FAILURE;
	}
	if (map_mmio(&injection_mmio, devmem, PSS_INJECTION_MMIO_BASE,
			"periodic injection") < 0 ||
	    map_mmio(&map_mmio_region, devmem, PSS_ACQUISITION_MMIO_BASE,
			"phase map") < 0)
		goto done;
	injection_io.context = &injection_mmio;
	injection_io.read32 = mapped_read32;
	injection_io.write32 = mapped_write32;
	map_io.context = &map_mmio_region;
	map_io.read32 = mapped_read32;
	map_io.write32 = mapped_write32;
	if (pss_injection_require_contract(&injection_io, &injection_info,
			error, sizeof(error)) < 0 ||
	    pss_map_require_contract(&map_io, &map_info,
			error, sizeof(error)) < 0) {
		fprintf(stderr, "M2 hardware contract check failed: %s\n", error);
		goto done;
	}
	if (!strcmp(command, "info") &&
	    print_info(expected_serial, &map_info, &injection_io, &injection_info,
			error, sizeof(error)) < 0) {
		fprintf(stderr, "M2 state read failed: %s\n", error);
		goto done;
	}
	if (!strcmp(command, "qualify") &&
	    run_qualification(expected_serial, &map_io, &map_info, &injection_io,
		fixture, scores, phases, phase_count, timeout_ms,
		error, sizeof(error)) < 0) {
		fprintf(stderr, "M2 qualification failed: %s\n", error);
		goto done;
	}
	return_code = EXIT_SUCCESS;

done:
	unmap_mmio(&map_mmio_region);
	unmap_mmio(&injection_mmio);
	return return_code;
}
