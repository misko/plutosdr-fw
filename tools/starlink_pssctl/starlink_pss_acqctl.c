// SPDX-License-Identifier: GPL-2.0-or-later
#define _POSIX_C_SOURCE 200809L

#include "starlink_pss_acquisition.h"

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <math.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <unistd.h>

#define PSS_ACQUISITION_MMIO_BASE UINT64_C(0x79040000)
#define PSS_ACQUISITION_MMIO_SPAN 0x1000U
#ifndef STARLINK_PSS_SERIAL_FILE
#define STARLINK_PSS_SERIAL_FILE "/etc/serial"
#endif
#define SERIAL_FILE STARLINK_PSS_SERIAL_FILE
#define ERROR_SIZE 256U
#define DEFAULT_TIMEOUT_MS 2000U

struct mapped_mmio {
	int fd;
	void *mapping;
	size_t mapping_size;
	volatile uint32_t *registers;
};

struct ddc_counters {
	uint32_t accepted;
	uint32_t emitted;
	uint32_t discontinuity;
	uint32_t saturation;
};

static volatile sig_atomic_t interrupted;

static void usage(FILE *stream)
{
	fprintf(stream,
		"usage: starlink_pss_acqctl --expect-serial SERIAL [--devmem PATH] COMMAND [ARGS]\n"
		"\n"
		"Commands:\n"
		"  info\n"
		"  snapshot [--timeout-ms N]\n"
		"  candidate [--timeout-ms N]\n"
		"\n"
		"candidate flushes and enables the FPGA acquisition engine, copies exactly\n"
		"three contiguous 20,000-bin maps, runs the fixed seven-drift search on the\n"
		"Zynq ARM, prints one candidate-measurement JSON object, then disables and\n"
		"flushes the engine. It makes no threshold, PSS-detection, or lock claim.\n"
		"The tool always maps PSMA at 0x%08" PRIx64
		" and refuses any serial or ABI mismatch.\n",
		PSS_ACQUISITION_MMIO_BASE);
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
	if (sigemptyset(&action.sa_mask) < 0 ||
	    sigaction(SIGINT, &action, NULL) < 0 ||
	    sigaction(SIGTERM, &action, NULL) < 0)
		return -1;
	return 0;
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
	if (!valid_serial(actual)) {
		fprintf(stderr, "%s does not contain a valid hexadecimal serial\n",
			SERIAL_FILE);
		return -1;
	}
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
	if (page_size <= 0 ||
	    ((uint64_t)page_size & ((uint64_t)page_size - 1U))) {
		fprintf(stderr, "cannot determine a power-of-two system page size\n");
		return -1;
	}
	aligned_base = (off_t)(PSS_ACQUISITION_MMIO_BASE &
		~((uint64_t)page_size - 1U));
	page_offset = (size_t)(PSS_ACQUISITION_MMIO_BASE -
		(uint64_t)aligned_base);
	mmio->mapping_size = page_offset + PSS_ACQUISITION_MMIO_SPAN;
	mmio->fd = open(path, O_RDWR | O_SYNC | O_CLOEXEC);
	if (mmio->fd < 0) {
		fprintf(stderr, "cannot open %s: %s\n", path, strerror(errno));
		return -1;
	}
	mmio->mapping = mmap(NULL, mmio->mapping_size, PROT_READ | PROT_WRITE,
		MAP_SHARED, mmio->fd, aligned_base);
	if (mmio->mapping == MAP_FAILED) {
		fprintf(stderr, "cannot map acquisition MMIO: %s\n", strerror(errno));
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

static uint32_t input_rate_msps(const struct pss_map_info *info)
{
	if (info->version == PSS_MAP_VERSION_1_2)
		return 30U;
	if (info->version == PSS_MAP_VERSION_1_3)
		return 60U;
	return 15U;
}

static int read_ddc_counters(const struct pss_map_io *io,
	struct ddc_counters *counters)
{
	if (!io || !io->read32 || !counters)
		return -1;
	return io->read32(io->context, PSS_MAP_REG_DDC_ACCEPTED,
			&counters->accepted) < 0 ||
		io->read32(io->context, PSS_MAP_REG_DDC_EMITTED,
			&counters->emitted) < 0 ||
		io->read32(io->context, PSS_MAP_REG_DDC_DISCONTINUITY,
			&counters->discontinuity) < 0 ||
		io->read32(io->context, PSS_MAP_REG_DDC_SATURATION,
			&counters->saturation) < 0 ? -1 : 0;
}

static bool snapshot_fault_free(const struct pss_map_snapshot *snapshot)
{
	uint32_t continuity_mask;

	if (!snapshot)
		return false;
	continuity_mask = snapshot->abi_version == PSS_MAP_VERSION_1_1 ?
		PSS_MAP_HEALTH_CONTINUITY_MASK_1_1 :
		PSS_MAP_HEALTH_CONTINUITY_MASK_DDC;
	return !(snapshot->health_flags & continuity_mask) &&
		!snapshot->discarded_score_count &&
		!snapshot->discontinuity_abort_count &&
		!snapshot->map_overrun_count &&
		!snapshot->score_protocol_error_count &&
		!snapshot->arithmetic_overflow_count &&
		!snapshot->map_read_error_count &&
		!snapshot->map_release_error_count &&
		!snapshot->ingress_dropped_sample_count &&
		!snapshot->scheduler_gap_count &&
		!snapshot->scheduler_index_error_count &&
		!snapshot->scheduler_overflow_count &&
		!snapshot->detector_fault_count &&
		!snapshot->score_phase_index_discontinuity_count;
}

static void print_double_or_null(double value)
{
	if (isfinite(value))
		printf("%.17g", value);
	else
		printf("null");
}

static void print_info(const char *serial, const struct pss_map_info *info)
{
	size_t index;

	printf("{\n"
	       "  \"schema\": \"starlink-pss-acqctl.info.v1\",\n"
	       "  \"claim_scope\": \"hardware_contract_only\",\n"
	       "  \"serial\": \"%s\",\n"
	       "  \"mmio_base\": \"0x%08" PRIx64 "\",\n"
	       "  \"identification\": \"0x%08" PRIx32 "\",\n"
	       "  \"abi_version\": \"0x%08" PRIx32 "\",\n"
	       "  \"phase_bins\": %" PRIu32 ",\n"
	       "  \"tile_frames\": %u,\n"
	       "  \"map_word_bits\": %u,\n"
	       "  \"map_banks\": %u,\n"
	       "  \"capabilities\": \"0x%08" PRIx32 "\",\n"
	       "  \"status\": \"0x%08" PRIx32 "\",\n"
	       "  \"input_rate_msps\": %" PRIu32 ",\n"
	       "  \"canonical_rate_msps\": 15,\n"
	       "  \"decimation_factor\": %" PRIu32 ",\n"
	       "  \"ddc_config\": \"0x%08" PRIx32 "\",\n"
	       "  \"ddc_group_delay_source_samples\": %" PRIu32 ",\n"
	       "  \"coefficient_energy\": %" PRIu32 ",\n"
	       "  \"ddc_contract_words\": [",
	       serial, PSS_ACQUISITION_MMIO_BASE, info->identification,
	       info->version, info->phase_bins, PSS_MAP_TILE_FRAMES,
	       PSS_MAP_WORD_BITS, PSS_MAP_BANKS, info->capabilities, info->status,
	       input_rate_msps(info), input_rate_msps(info) / 15U,
	       info->ddc_config, info->ddc_group_delay, info->coefficient_energy);
	for (index = 0; index < 8U; ++index)
		printf("%s\"0x%08" PRIx32 "\"", index ? ", " : "",
			info->ddc_contract[index]);
	printf("]\n}\n");
}

static void print_snapshot(const char *serial,
	const struct pss_map_snapshot *snapshot)
{
	printf("{\n"
	       "  \"schema\": \"starlink-pss-acqctl.snapshot.v1\",\n"
	       "  \"claim_scope\": \"acquisition_telemetry_only\",\n"
	       "  \"serial\": \"%s\",\n"
	       "  \"abi_version\": \"0x%08" PRIx32 "\",\n"
	       "  \"snapshot_generation\": %" PRIu32 ",\n"
	       "  \"ready_mask\": %" PRIu32 ",\n"
	       "  \"map_generations\": [%" PRIu32 ", %" PRIu32 "],\n"
	       "  \"map_start_indexes\": [%" PRIu64 ", %" PRIu64 "],\n"
	       "  \"accepted_scores\": %" PRIu32 ",\n"
	       "  \"published_maps\": %" PRIu32 ",\n"
	       "  \"health_flags\": \"0x%08" PRIx32 "\",\n"
	       "  \"fault_free_epoch\": %s,\n"
	       "  \"discarded_scores\": %" PRIu32 ",\n"
	       "  \"discontinuity_aborts\": %" PRIu32 ",\n"
	       "  \"map_overruns\": %" PRIu32 ",\n"
	       "  \"protocol_errors\": %" PRIu32 ",\n"
	       "  \"arithmetic_overflows\": %" PRIu32 ",\n"
	       "  \"map_read_errors\": %" PRIu32 ",\n"
	       "  \"map_release_errors\": %" PRIu32 ",\n"
	       "  \"ingress_dropped_samples\": %" PRIu32 ",\n"
	       "  \"ingress_fifo_level\": %u,\n"
	       "  \"ingress_fifo_maximum\": %u,\n"
	       "  \"scheduler_gaps\": %" PRIu32 ",\n"
	       "  \"scheduler_index_errors\": %" PRIu32 ",\n"
	       "  \"scheduler_overflows\": %" PRIu32 ",\n"
	       "  \"detector_faults\": %" PRIu32 ",\n"
	       "  \"phase_discontinuities\": %" PRIu32 ",\n"
	       "  \"zero_denominators\": %" PRIu32 ",\n"
	       "  \"candidate_fifo_level\": %u,\n"
	       "  \"candidate_fifo_maximum\": %u\n"
	       "}\n",
	       serial, snapshot->abi_version, snapshot->snapshot_generation,
	       snapshot->ready_mask, snapshot->map_generation[0],
	       snapshot->map_generation[1], snapshot->map_start_index[0],
	       snapshot->map_start_index[1], snapshot->accepted_score_count,
	       snapshot->map_publish_count,
	       snapshot->health_flags, snapshot_fault_free(snapshot) ? "true" : "false",
	       snapshot->discarded_score_count,
	       snapshot->discontinuity_abort_count, snapshot->map_overrun_count,
	       snapshot->score_protocol_error_count,
	       snapshot->arithmetic_overflow_count, snapshot->map_read_error_count,
	       snapshot->map_release_error_count,
	       snapshot->ingress_dropped_sample_count, snapshot->ingress_fifo_level,
	       snapshot->ingress_maximum_fifo_level, snapshot->scheduler_gap_count,
	       snapshot->scheduler_index_error_count,
	       snapshot->scheduler_overflow_count, snapshot->detector_fault_count,
	       snapshot->score_phase_index_discontinuity_count,
	       snapshot->score_denominator_zero_count,
	       snapshot->candidate_fifo_stored_count,
	       snapshot->candidate_fifo_maximum_stored_count);
}

static void print_candidate(const char *serial, const struct pss_map_info *info,
	const struct pss_map_window *window,
	const struct pss_acquisition_candidate *candidate,
	const struct ddc_counters *ddc_before,
	const struct ddc_counters *ddc_after,
	const struct pss_map_snapshot *final_snapshot)
{
	uint32_t rate = input_rate_msps(info);
	uint32_t factor = rate / 15U;
	uint64_t canonical_index = candidate->reference_start_index +
		candidate->phase_bin;
	uint64_t source_index = canonical_index * factor;
	size_t index;

	printf("{\n"
	       "  \"schema\": \"starlink-pss-acqctl.candidate.v1\",\n"
	       "  \"execution_path\": \"exact_target_radio\",\n"
	       "  \"stimulus_source\": \"unspecified_rx_input\",\n"
	       "  \"claim_scope\": \"candidate_measurement_only\",\n"
	       "  \"serial\": \"%s\",\n"
	       "  \"mmio_base\": \"0x%08" PRIx64 "\",\n"
	       "  \"abi_version\": \"0x%08" PRIx32 "\",\n"
	       "  \"input_rate_msps\": %" PRIu32 ",\n"
	       "  \"canonical_rate_msps\": 15,\n"
	       "  \"decimation_factor\": %" PRIu32 ",\n"
	       "  \"map_generations\": [",
	       serial, PSS_ACQUISITION_MMIO_BASE, info->version, rate, factor);
	for (index = 0; index < PSS_ACQUISITION_WINDOW_MAPS; ++index)
		printf("%s%" PRIu32, index ? ", " : "", window->generations[index]);
	printf("],\n  \"map_start_indexes_canonical\": [");
	for (index = 0; index < PSS_ACQUISITION_WINDOW_MAPS; ++index)
		printf("%s%" PRIu64, index ? ", " : "", window->start_indexes[index]);
	printf("],\n"
	       "  \"continuity_ok\": true,\n"
	       "  \"phase_bin\": %" PRIu32 ",\n"
	       "  \"drift_bins_per_64_frames\": %" PRId32 ",\n"
	       "  \"combined_score\": %" PRIu32 ",\n"
	       "  \"combined_median\": ",
	       candidate->phase_bin, candidate->drift_bins_per_tile,
	       candidate->combined_score);
	print_double_or_null(candidate->combined_median);
	printf(",\n  \"peak_to_median\": ");
	print_double_or_null(candidate->peak_to_median);
	printf(",\n  \"robust_z\": ");
	print_double_or_null(candidate->robust_z);
	printf(",\n  \"estimated_frame_period_canonical_samples\": ");
	print_double_or_null(candidate->estimated_frame_period_samples);
	printf(",\n  \"estimated_frame_period_source_samples\": ");
	print_double_or_null(candidate->estimated_frame_period_samples * factor);
	printf(",\n"
	       "  \"candidate_start_index_canonical\": %" PRIu64 ",\n"
	       "  \"candidate_start_index_source_center\": %" PRIu64 ",\n"
	       "  \"threshold_decision\": null,\n"
	       "  \"frame_lock_claim\": false,\n"
	       "  \"ddc_counters_before\": {\"accepted\": %" PRIu32
	       ", \"emitted\": %" PRIu32 ", \"discontinuity\": %" PRIu32
	       ", \"saturation\": %" PRIu32 "},\n"
	       "  \"ddc_counters_after\": {\"accepted\": %" PRIu32
	       ", \"emitted\": %" PRIu32 ", \"discontinuity\": %" PRIu32
	       ", \"saturation\": %" PRIu32 "},\n"
	       "  \"final_snapshot_generation\": %" PRIu32 ",\n"
	       "  \"final_health_flags\": \"0x%08" PRIx32 "\",\n"
	       "  \"fault_free_epoch\": %s\n"
	       "}\n",
	       canonical_index, source_index,
	       ddc_before->accepted, ddc_before->emitted,
	       ddc_before->discontinuity, ddc_before->saturation,
	       ddc_after->accepted, ddc_after->emitted,
	       ddc_after->discontinuity, ddc_after->saturation,
	       final_snapshot->snapshot_generation, final_snapshot->health_flags,
	       snapshot_fault_free(final_snapshot) ? "true" : "false");
}

static int run_candidate(const char *serial, const struct pss_map_io *io,
	const struct pss_map_info *info, unsigned int timeout_ms,
	char *error, size_t error_size)
{
	uint16_t *storage = NULL, *incoming = NULL;
	uint32_t *scratch = NULL;
	struct pss_map_window window;
	struct pss_map_copy copies[PSS_ACQUISITION_WINDOW_MAPS];
	struct pss_map_snapshot initial_snapshot, final_snapshot;
	struct pss_acquisition_candidate candidate;
	struct ddc_counters ddc_before = {0}, ddc_after = {0};
	size_t index;
	bool enabled = false;
	int result = -1;

	storage = calloc(PSS_ACQUISITION_WINDOW_MAPS * PSS_MAP_PHASE_BINS,
		sizeof(*storage));
	incoming = calloc(PSS_MAP_PHASE_BINS, sizeof(*incoming));
	scratch = calloc(PSS_ACQUISITION_SCRATCH_WORDS, sizeof(*scratch));
	if (!storage || !incoming || !scratch) {
		snprintf(error, error_size, "cannot allocate fixed acquisition buffers");
		goto done;
	}
	if (pss_map_window_init(&window, storage,
		PSS_ACQUISITION_WINDOW_MAPS * PSS_MAP_PHASE_BINS,
		PSS_MAP_PHASE_BINS, PSS_MAP_TILE_FRAMES,
		error, error_size) < 0 ||
	    pss_map_set_enabled(io, true, true, error, error_size) < 0)
		goto done;
	enabled = true;
	if (pss_map_take_snapshot(io, &initial_snapshot, timeout_ms,
			error, error_size) < 0)
		goto done;
	if (!snapshot_fault_free(&initial_snapshot)) {
		snprintf(error, error_size,
			"acquisition health epoch was already faulted before capture");
		goto done;
	}
	if (read_ddc_counters(io, &ddc_before) < 0) {
		snprintf(error, error_size, "cannot read initial DDC counters");
		goto done;
	}
	if (ddc_before.discontinuity || ddc_before.saturation) {
		snprintf(error, error_size,
			"DDC fault counters were nonzero before capture");
		goto done;
	}

	for (index = 0; index < PSS_ACQUISITION_WINDOW_MAPS; ++index) {
		if (interrupted) {
			snprintf(error, error_size, "candidate acquisition interrupted");
			goto done;
		}
		if (pss_map_wait_copy(io, incoming, PSS_MAP_PHASE_BINS,
				&copies[index], timeout_ms, error, error_size) < 0)
			goto done;
		if (index && !pss_map_copies_contiguous(&copies[index - 1U],
				&copies[index])) {
			snprintf(error, error_size,
				"phase-map copies were not contiguous");
			goto done;
		}
		if (pss_map_window_push(&window, incoming,
				copies[index].generation, copies[index].start_index,
				error, error_size) < 0)
			goto done;
	}
	if (pss_acquisition_extract(&window,
			pss_acquisition_default_drift_bank,
			PSS_ACQUISITION_DRIFT_HYPOTHESES,
			scratch, PSS_ACQUISITION_SCRATCH_WORDS,
			&candidate, error, error_size) < 0 ||
	    pss_map_take_snapshot(io, &final_snapshot, timeout_ms,
			error, error_size) < 0)
		goto done;
	if (!snapshot_fault_free(&final_snapshot)) {
		snprintf(error, error_size,
			"acquisition health epoch faulted during capture");
		goto done;
	}
	if (read_ddc_counters(io, &ddc_after) < 0) {
		snprintf(error, error_size, "cannot read final DDC counters");
		goto done;
	}
	if (ddc_after.discontinuity || ddc_after.saturation ||
	    ddc_after.accepted < ddc_before.accepted ||
	    ddc_after.emitted < ddc_before.emitted ||
	    ddc_after.accepted == UINT32_MAX || ddc_after.emitted == UINT32_MAX) {
		snprintf(error, error_size,
			"DDC counters faulted, regressed, or saturated during capture");
		goto done;
	}
	if (input_rate_msps(info) > 15U &&
	    (ddc_after.accepted == ddc_before.accepted ||
	     ddc_after.emitted == ddc_before.emitted)) {
		snprintf(error, error_size, "DDC counters did not advance during capture");
		goto done;
	}
	if (candidate.reference_start_index > UINT64_MAX - candidate.phase_bin ||
	    candidate.reference_start_index + candidate.phase_bin >
		UINT64_MAX / (input_rate_msps(info) / 15U)) {
		snprintf(error, error_size,
			"candidate source-index projection overflows 64 bits");
		goto done;
	}
	if (pss_map_set_enabled(io, false, true, error, error_size) < 0)
		goto done;
	enabled = false;
	print_candidate(serial, info, &window, &candidate,
		&ddc_before, &ddc_after, &final_snapshot);
	result = 0;

done:
	if (enabled) {
		char cleanup_error[ERROR_SIZE] = {0};

		if (pss_map_set_enabled(io, false, true,
				cleanup_error, sizeof(cleanup_error)) < 0) {
			if (!io->write32 || io->write32(io->context,
					PSS_MAP_REG_CONTROL, 2U) < 0)
				fprintf(stderr, "acquisition cleanup failed: %s\n",
					cleanup_error);
			else
				fprintf(stderr,
					"acquisition cleanup required direct disable/flush fallback: %s\n",
					cleanup_error);
			result = -1;
		}
	}
	free(scratch);
	free(incoming);
	free(storage);
	return result;
}

int main(int argc, char **argv)
{
	const char *expected_serial = NULL;
	const char *devmem = "/dev/mem";
	const char *command;
	struct mapped_mmio mmio;
	struct pss_map_io io;
	struct pss_map_info info;
	char error[ERROR_SIZE] = {0};
	unsigned int timeout_ms = DEFAULT_TIMEOUT_MS;
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
	if (!strcmp(command, "snapshot") || !strcmp(command, "candidate")) {
		while (argument < argc) {
			const char *value;

			if (strcmp(argv[argument], "--timeout-ms") ||
			    option_value(argc, argv, &argument, &value) < 0 ||
			    parse_timeout(value, &timeout_ms) < 0) {
				fprintf(stderr, "invalid %s option\n", command);
				return EXIT_FAILURE;
			}
			++argument;
		}
	} else if (!strcmp(command, "info")) {
		if (argument != argc) {
			fprintf(stderr, "info takes no arguments\n");
			return EXIT_FAILURE;
		}
	} else {
		fprintf(stderr, "unknown command: %s\n", command);
		usage(stderr);
		return EXIT_FAILURE;
	}
	if (verify_local_serial(expected_serial) < 0)
		return EXIT_FAILURE;
	if (install_signal_handlers() < 0) {
		fprintf(stderr, "cannot install cleanup signal handlers: %s\n",
			strerror(errno));
		return EXIT_FAILURE;
	}
	if (map_mmio(&mmio, devmem) < 0)
		return EXIT_FAILURE;
	io.context = &mmio;
	io.read32 = mapped_read32;
	io.write32 = mapped_write32;
	if (pss_map_require_contract(&io, &info, error, sizeof(error)) < 0) {
		fprintf(stderr, "acquisition contract check failed: %s\n", error);
		goto done;
	}

	if (!strcmp(command, "info")) {
		print_info(expected_serial, &info);
		return_code = EXIT_SUCCESS;
	} else if (!strcmp(command, "snapshot")) {
		struct pss_map_snapshot snapshot;

		if (pss_map_take_snapshot(&io, &snapshot, timeout_ms,
				error, sizeof(error)) < 0) {
			fprintf(stderr, "acquisition snapshot failed: %s\n", error);
			goto done;
		}
		print_snapshot(expected_serial, &snapshot);
		return_code = EXIT_SUCCESS;
	} else if (!strcmp(command, "candidate")) {
		if (run_candidate(expected_serial, &io, &info, timeout_ms,
				error, sizeof(error)) < 0) {
			fprintf(stderr, "candidate measurement failed: %s\n", error);
			goto done;
		}
		return_code = EXIT_SUCCESS;
	}

done:
	unmap_mmio(&mmio);
	return return_code;
}
