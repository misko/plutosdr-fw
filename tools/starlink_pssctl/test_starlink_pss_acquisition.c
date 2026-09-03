// SPDX-License-Identifier: GPL-2.0-or-later
#include "starlink_pss_acquisition.h"

#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MOCK_REGISTER_WORDS ((PSS_MAP_REG_SNAPSHOT_REQUEST_OVERRUN / 4U) + 1U)
#define ERROR_SIZE 256U

struct mock_map {
	uint32_t registers[MOCK_REGISTER_WORDS];
	uint16_t maps[PSS_MAP_BANKS][PSS_MAP_PHASE_BINS];
	uint32_t map_generation[PSS_MAP_BANKS];
	uint64_t map_start_index[PSS_MAP_BANKS];
	uint32_t ready_mask;
	uint32_t selected_bank;
	uint32_t selected_index;
	uint32_t map_read_error_count;
	uint32_t map_release_error_count;
	uint32_t data_reads;
	uint32_t releases;
	uint32_t flushes;
	uint32_t mutate_after_read;
	uint32_t fault_after_read;
};

static unsigned int failures;

#define CHECK(condition, message) \
	do { \
		if (!(condition)) { \
			fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, message); \
			failures++; \
		} \
	} while (0)

static uint32_t *mock_register(struct mock_map *mock, uint32_t offset)
{
	return &mock->registers[offset / 4U];
}

static void mock_status(struct mock_map *mock)
{
	uint32_t status = PSS_MAP_STATUS_CONTROL_EPOCH_LIVE;

	if (*mock_register(mock, PSS_MAP_REG_CONTROL) & 1U)
		status |= PSS_MAP_STATUS_ENABLED;
	status |= (mock->ready_mask & 3U) << 2;
	if (mock->ready_mask)
		status |= PSS_MAP_STATUS_IRQ;
	*mock_register(mock, PSS_MAP_REG_STATUS) = status;
}

static void mock_capture_snapshot(struct mock_map *mock)
{
	uint32_t generation =
		*mock_register(mock, PSS_MAP_REG_SNAPSHOT_GENERATION);

	if (generation != UINT32_MAX)
		generation++;
	*mock_register(mock, PSS_MAP_REG_SNAPSHOT_GENERATION) = generation;
	*mock_register(mock, PSS_MAP_REG_SNAPSHOT_READY) = mock->ready_mask;
	*mock_register(mock, PSS_MAP_REG_SNAPSHOT_MAP_GENERATION_0) =
		mock->map_generation[0];
	*mock_register(mock, PSS_MAP_REG_SNAPSHOT_MAP_GENERATION_1) =
		mock->map_generation[1];
	*mock_register(mock, PSS_MAP_REG_SNAPSHOT_START_INDEX_0_LO) =
		(uint32_t)mock->map_start_index[0];
	*mock_register(mock, PSS_MAP_REG_SNAPSHOT_START_INDEX_0_HI) =
		(uint32_t)(mock->map_start_index[0] >> 32);
	*mock_register(mock, PSS_MAP_REG_SNAPSHOT_START_INDEX_1_LO) =
		(uint32_t)mock->map_start_index[1];
	*mock_register(mock, PSS_MAP_REG_SNAPSHOT_START_INDEX_1_HI) =
		(uint32_t)(mock->map_start_index[1] >> 32);
	*mock_register(mock, PSS_MAP_REG_SNAPSHOT_READ_ERROR) =
		mock->map_read_error_count;
	*mock_register(mock, PSS_MAP_REG_SNAPSHOT_RELEASE_ERROR) =
		mock->map_release_error_count;
	*mock_register(mock, PSS_MAP_REG_SNAPSHOT_STATUS) = 1U;
}

static void mock_init(struct mock_map *mock)
{
	size_t index;

	memset(mock, 0, sizeof(*mock));
	*mock_register(mock, PSS_MAP_REG_IDENTIFICATION) = PSS_MAP_IDENTIFICATION;
	*mock_register(mock, PSS_MAP_REG_VERSION) = PSS_MAP_VERSION;
	*mock_register(mock, PSS_MAP_REG_PHASE_BINS) = PSS_MAP_PHASE_BINS;
	*mock_register(mock, PSS_MAP_REG_TILE_GEOMETRY) = PSS_MAP_TILE_GEOMETRY;
	*mock_register(mock, PSS_MAP_REG_CAPABILITIES) = PSS_MAP_CAPABILITIES;
	mock->ready_mask = 3U;
	mock->map_generation[0] = 10U;
	mock->map_generation[1] = 11U;
	mock->map_start_index[0] = UINT64_C(0x1234567800000000);
	mock->map_start_index[1] =
		mock->map_start_index[0] +
		(uint64_t)PSS_MAP_PHASE_BINS * PSS_MAP_TILE_FRAMES;
	for (index = 0; index < PSS_MAP_PHASE_BINS; ++index) {
		mock->maps[0][index] = (uint16_t)index;
		mock->maps[1][index] = (uint16_t)(index + 100U);
	}
	mock_status(mock);
}

static int mock_read32(void *context, uint32_t offset, uint32_t *value)
{
	struct mock_map *mock = context;

	if (!value || offset > PSS_MAP_REG_SNAPSHOT_REQUEST_OVERRUN ||
	    (offset & 3U))
		return -1;
	if (offset == PSS_MAP_REG_STATUS)
		mock_status(mock);
	if (offset == PSS_MAP_REG_DATA) {
		unsigned int bank = mock->selected_bank;

		if (bank >= PSS_MAP_BANKS || !(mock->ready_mask & (1U << bank))) {
			*value = 0U;
			*mock_register(mock, PSS_MAP_REG_COMMAND_STATUS) |=
				PSS_MAP_COMMAND_READ_ERROR;
			*mock_register(mock, PSS_MAP_REG_BRIDGE_READ_ERROR) += 1U;
			mock->map_read_error_count++;
			return 0;
		}
		*value = mock->maps[bank][mock->selected_index];
		if (mock->selected_index < PSS_MAP_PHASE_BINS - 1U)
			mock->selected_index++;
		mock->data_reads++;
		if (mock->mutate_after_read &&
		    mock->data_reads == mock->mutate_after_read)
			mock->map_generation[bank]++;
		if (mock->fault_after_read &&
		    mock->data_reads == mock->fault_after_read)
			(*mock_register(mock, PSS_MAP_REG_SNAPSHOT_DISCARDED))++;
		return 0;
	}
	*value = *mock_register(mock, offset);
	return 0;
}

static int mock_write32(void *context, uint32_t offset, uint32_t value)
{
	struct mock_map *mock = context;

	if (offset > PSS_MAP_REG_SNAPSHOT_REQUEST_OVERRUN || (offset & 3U))
		return -1;
	switch (offset) {
	case PSS_MAP_REG_CONTROL:
		*mock_register(mock, offset) = value & 1U;
		if (value & 2U)
			mock->flushes++;
		break;
	case PSS_MAP_REG_SELECT:
		mock->selected_bank = value & 1U;
		break;
	case PSS_MAP_REG_INDEX:
		mock->selected_index =
			value < PSS_MAP_PHASE_BINS ? value : PSS_MAP_PHASE_BINS - 1U;
		break;
	case PSS_MAP_REG_RELEASE:
		*mock_register(mock, PSS_MAP_REG_COMMAND_STATUS) &=
			~PSS_MAP_COMMAND_RELEASE_ERROR;
		if ((value & 1U) &&
		    (mock->ready_mask & (1U << mock->selected_bank))) {
			mock->ready_mask &= ~(1U << mock->selected_bank);
			mock->releases++;
		} else {
			*mock_register(mock, PSS_MAP_REG_COMMAND_STATUS) |=
				PSS_MAP_COMMAND_RELEASE_ERROR;
			*mock_register(mock, PSS_MAP_REG_BRIDGE_RELEASE_ERROR) += 1U;
			mock->map_release_error_count++;
		}
		break;
	case PSS_MAP_REG_SNAPSHOT_CONTROL:
		if (value & 1U)
			mock_capture_snapshot(mock);
		break;
	default:
		*mock_register(mock, offset) = value;
		break;
	}
	return 0;
}

static struct pss_map_io mock_io(struct mock_map *mock)
{
	struct pss_map_io io = {
		.context = mock,
		.read32 = mock_read32,
		.write32 = mock_write32,
	};

	return io;
}

static void test_contract_snapshot_copy_and_release(void)
{
	struct mock_map *mock = calloc(1U, sizeof(*mock));
	struct pss_map_io io;
	struct pss_map_info info;
	struct pss_map_snapshot snapshot, next_snapshot;
	struct pss_map_copy copy, next_copy;
	uint16_t *destination = calloc(PSS_MAP_PHASE_BINS, sizeof(*destination));
	char error[ERROR_SIZE] = {0};
	size_t index;

	CHECK(mock && destination, "allocation failed");
	if (!mock || !destination)
		goto done;
	mock_init(mock);
	io = mock_io(mock);
	CHECK(pss_map_require_contract(&io, &info, error, sizeof(error)) == 0,
		error);
	CHECK(info.phase_bins == PSS_MAP_PHASE_BINS, "wrong contract bin count");
	CHECK(pss_map_set_enabled(&io, true, true, error, sizeof(error)) == 0,
		error);
	CHECK(mock->flushes == 1U, "flush did not cross exactly once");
	CHECK(pss_map_take_snapshot(&io, &snapshot, 10U, error, sizeof(error)) == 0,
		error);
	CHECK(snapshot.snapshot_generation == 1U, "wrong snapshot generation");
	CHECK(snapshot.ready_mask == 3U, "wrong snapshot ready mask");
	CHECK(snapshot.map_generation[0] == 10U, "wrong bank generation");
	CHECK(snapshot.map_start_index[0] == UINT64_C(0x1234567800000000),
		"64-bit map start was not coherent");
	CHECK(pss_map_copy_and_release(&io, &snapshot, 0U, destination,
		PSS_MAP_PHASE_BINS, &copy, 10U, error, sizeof(error)) == 0, error);
	CHECK(copy.bank == 0U && copy.generation == 10U,
		"copy metadata is incorrect");
	CHECK(copy.start_index == snapshot.map_start_index[0],
		"copy start index is incorrect");
	CHECK(mock->data_reads == PSS_MAP_PHASE_BINS,
		"copy did not read exactly one complete map");
	CHECK(mock->releases == 1U && !(mock->ready_mask & 1U),
		"successful map was not released exactly once");
	for (index = 0; index < PSS_MAP_PHASE_BINS; ++index) {
		if (destination[index] != (uint16_t)index) {
			CHECK(false, "copied map word mismatch");
			break;
		}
	}
	CHECK(pss_map_take_snapshot(&io, &next_snapshot, 10U,
		error, sizeof(error)) == 0, error);
	CHECK(pss_map_copy_and_release(&io, &next_snapshot, 1U, destination,
		PSS_MAP_PHASE_BINS, &next_copy, 10U,
		error, sizeof(error)) == 0, error);
	CHECK(pss_map_copies_contiguous(&copy, &next_copy),
		"consecutive healthy map copies were not continuous");
	next_copy.before.discarded_score_count++;
	CHECK(!pss_map_copies_contiguous(&copy, &next_copy),
		"a changed fault epoch was accepted as continuous");
	next_copy.before.discarded_score_count--;
	next_copy.generation++;
	CHECK(!pss_map_copies_contiguous(&copy, &next_copy),
		"a generation gap was accepted as continuous");
	CHECK(mock->data_reads == 2U * PSS_MAP_PHASE_BINS,
		"two copies did not read exactly two complete maps");
	CHECK(mock->releases == 2U && mock->ready_mask == 0U,
		"successful maps were not released exactly once each");

done:
	free(destination);
	free(mock);
}

static void test_copy_fail_closed_on_metadata_change(void)
{
	struct mock_map *mock = calloc(1U, sizeof(*mock));
	struct pss_map_io io;
	struct pss_map_snapshot snapshot;
	struct pss_map_copy copy;
	uint16_t *destination = calloc(PSS_MAP_PHASE_BINS, sizeof(*destination));
	char error[ERROR_SIZE] = {0};

	CHECK(mock && destination, "allocation failed");
	if (!mock || !destination)
		goto done;
	mock_init(mock);
	io = mock_io(mock);
	CHECK(pss_map_take_snapshot(&io, &snapshot, 10U, error, sizeof(error)) == 0,
		error);
	mock->mutate_after_read = 100U;
	CHECK(pss_map_copy_and_release(&io, &snapshot, 0U, destination,
		PSS_MAP_PHASE_BINS, &copy, 10U, error, sizeof(error)) < 0,
		"mutated map copy was accepted");
	CHECK(strstr(error, "changed while it was copied") != NULL,
		"mutated map failed for the wrong reason");
	CHECK(mock->releases == 0U && (mock->ready_mask & 1U),
		"failed map copy released source ownership");

	mock_init(mock);
	CHECK(pss_map_take_snapshot(&io, &snapshot, 10U, error, sizeof(error)) == 0,
		error);
	mock->fault_after_read = 100U;
	CHECK(pss_map_copy_and_release(&io, &snapshot, 0U, destination,
		PSS_MAP_PHASE_BINS, &copy, 10U, error, sizeof(error)) < 0,
		"copy spanning a changed fault epoch was accepted");
	CHECK(strstr(error, "fault counters changed") != NULL,
		"fault-epoch mutation failed for the wrong reason");
	CHECK(mock->releases == 0U && (mock->ready_mask & 1U),
		"faulted map copy released source ownership");

done:
	free(destination);
	free(mock);
}

static void test_snapshot_and_contract_fail_closed(void)
{
	struct mock_map *mock = calloc(1U, sizeof(*mock));
	struct pss_map_io io;
	struct pss_map_snapshot snapshot;
	char error[ERROR_SIZE] = {0};

	CHECK(mock != NULL, "allocation failed");
	if (!mock)
		return;
	mock_init(mock);
	io = mock_io(mock);
	*mock_register(mock, PSS_MAP_REG_IDENTIFICATION) ^= 1U;
	CHECK(pss_map_require_contract(&io, NULL, error, sizeof(error)) < 0,
		"wrong hardware ID was accepted");
	*mock_register(mock, PSS_MAP_REG_IDENTIFICATION) = PSS_MAP_IDENTIFICATION;
	*mock_register(mock, PSS_MAP_REG_SNAPSHOT_STATUS) = 2U;
	CHECK(pss_map_take_snapshot(&io, &snapshot, 10U, error, sizeof(error)) < 0,
		"already-pending snapshot was accepted");
	CHECK(strstr(error, "already pending") != NULL,
		"pending snapshot failed for the wrong reason");
	*mock_register(mock, PSS_MAP_REG_SNAPSHOT_STATUS) = 0U;
	*mock_register(mock, PSS_MAP_REG_SNAPSHOT_GENERATION) = UINT32_MAX;
	CHECK(pss_map_take_snapshot(&io, &snapshot, 10U, error, sizeof(error)) < 0,
		"saturated snapshot generation was accepted");
	free(mock);
}

static void fill_map(uint16_t *map, uint16_t even, uint16_t odd)
{
	size_t index;

	for (index = 0; index < PSS_MAP_PHASE_BINS; ++index)
		map[index] = index & 1U ? odd : even;
}

static void test_window_and_extractor(void)
{
	static const int32_t expected_drift_bank[] = {-12, -8, -4, 0, 4, 8, 12};
	static const int32_t too_many_drifts[] = {-4, -3, -2, -1, 0, 1, 2, 3};
	uint16_t *storage = calloc(
		PSS_ACQUISITION_WINDOW_MAPS * PSS_MAP_PHASE_BINS, sizeof(*storage));
	uint16_t *map = calloc(PSS_MAP_PHASE_BINS, sizeof(*map));
	uint32_t *scratch = calloc(PSS_ACQUISITION_SCRATCH_WORDS, sizeof(*scratch));
	struct pss_map_window window, invalid_window;
	struct pss_acquisition_candidate candidate;
	char error[ERROR_SIZE] = {0};
	uint64_t tile_samples =
		(uint64_t)PSS_MAP_PHASE_BINS * PSS_MAP_TILE_FRAMES;
	size_t tile, index;

	CHECK(storage && map && scratch, "allocation failed");
	if (!storage || !map || !scratch)
		goto done;
	CHECK(memcmp(pss_acquisition_default_drift_bank, expected_drift_bank,
		sizeof(expected_drift_bank)) == 0,
		"default drift bank changed");
	CHECK(pss_map_window_init(&invalid_window, map, 1U,
		(uint32_t)INT32_MAX + 1U, PSS_MAP_TILE_FRAMES,
		error, sizeof(error)) < 0,
		"unsafe signed-index geometry was accepted");
	CHECK(pss_map_window_init(&window, storage,
		PSS_ACQUISITION_WINDOW_MAPS * PSS_MAP_PHASE_BINS,
		PSS_MAP_PHASE_BINS, PSS_MAP_TILE_FRAMES,
		error, sizeof(error)) == 0, error);
	for (tile = 0; tile < PSS_ACQUISITION_WINDOW_MAPS; ++tile) {
		for (index = 0; index < PSS_MAP_PHASE_BINS; ++index)
			map[index] = 100U;
		map[1200U + tile * 12U] = 300U;
		CHECK(pss_map_window_push(&window, map, 10U + (uint32_t)tile,
			tile * tile_samples, error, sizeof(error)) == 0, error);
	}
	CHECK(pss_map_window_ready(&window), "three-map window is not ready");
	CHECK(pss_acquisition_extract(&window, pss_acquisition_default_drift_bank,
		PSS_ACQUISITION_DRIFT_HYPOTHESES, scratch,
		PSS_ACQUISITION_SCRATCH_WORDS, &candidate,
		error, sizeof(error)) == 0, error);
	CHECK(candidate.phase_bin == 1200U, "drift search found the wrong phase");
	CHECK(candidate.drift_bins_per_tile == 12,
		"drift search found the wrong period hypothesis");
	CHECK(candidate.combined_score == 900U, "wrong combined peak score");
	CHECK(candidate.combined_median == 300.0, "wrong combined median");
	CHECK(candidate.peak_to_median == 3.0, "wrong peak/median ratio");
	CHECK(isinf(candidate.robust_z), "zero-MAD peak should have infinite z");
	CHECK(fabs(candidate.estimated_frame_period_samples - 20000.1875) < 1e-12,
		"wrong frame-period estimate");
	CHECK(pss_acquisition_candidate_passes(&candidate, 1.15, 6.0),
		"strong candidate did not pass inclusive gates");

	for (index = 0; index < PSS_ACQUISITION_WINDOW_MAPS *
	     PSS_MAP_PHASE_BINS; ++index)
		storage[index] = 100U;
	CHECK(pss_acquisition_extract(&window, pss_acquisition_default_drift_bank,
		PSS_ACQUISITION_DRIFT_HYPOTHESES, scratch,
		PSS_ACQUISITION_SCRATCH_WORDS, &candidate,
		error, sizeof(error)) == 0, error);
	CHECK(candidate.phase_bin == 0U && candidate.drift_bins_per_tile == -12,
		"exact tie did not select smallest drift then phase");
	CHECK(candidate.peak_to_median == 1.0 && candidate.robust_z == 0.0,
		"flat map statistics are wrong");
	CHECK(!pss_acquisition_candidate_passes(&candidate, 1.15, 6.0),
		"flat map passed candidate gates");
	CHECK(pss_acquisition_extract(&window, too_many_drifts,
		sizeof(too_many_drifts) / sizeof(too_many_drifts[0]), scratch,
		PSS_ACQUISITION_SCRATCH_WORDS, &candidate,
		error, sizeof(error)) < 0,
		"an unbounded drift bank was accepted");

	for (tile = 0; tile < PSS_ACQUISITION_WINDOW_MAPS; ++tile) {
		fill_map(storage + tile * PSS_MAP_PHASE_BINS, 10U, 20U);
		storage[tile * PSS_MAP_PHASE_BINS + 101U] = 100U;
	}
	{
		static const int32_t zero_drift[] = {0};
		double expected_z = 255.0 / (1.4826 * 15.0);

		CHECK(pss_acquisition_extract(&window, zero_drift, 1U, scratch,
			PSS_ACQUISITION_SCRATCH_WORDS, &candidate,
			error, sizeof(error)) == 0, error);
		CHECK(candidate.phase_bin == 101U && candidate.combined_score == 300U,
			"finite-MAD fixture found the wrong peak");
		CHECK(candidate.combined_median == 45.0,
			"finite-MAD fixture median is wrong");
		CHECK(fabs(candidate.peak_to_median - (300.0 / 45.0)) < 1e-12,
			"finite-MAD peak/median is wrong");
		CHECK(fabs(candidate.robust_z - expected_z) < 1e-12,
			"finite-MAD robust z is wrong");
	}

	fill_map(map, 1U, 1U);
	CHECK(pss_map_window_push(&window, map, 13U, 3U * tile_samples,
		error, sizeof(error)) == 0, error);
	CHECK(window.count == 3U && window.generations[0] == 11U &&
		window.generations[2] == 13U,
		"sliding window did not discard exactly the oldest map");
	CHECK(pss_map_window_push(&window, map, 15U, 4U * tile_samples,
		error, sizeof(error)) < 0,
		"generation discontinuity was accepted");
	CHECK(window.count == 0U, "discontinuous map window did not reset");

done:
	free(scratch);
	free(map);
	free(storage);
}

static struct pss_lock_observation make_observation(uint32_t generation,
	uint32_t phase, int32_t drift, bool qualifies, bool continuity_ok)
{
	uint64_t tile_samples =
		(uint64_t)PSS_MAP_PHASE_BINS * PSS_MAP_TILE_FRAMES;
	struct pss_lock_observation observation;

	memset(&observation, 0, sizeof(observation));
	observation.continuity_ok = continuity_ok;
	observation.candidate.phase_bin = phase;
	observation.candidate.drift_bins_per_tile = drift;
	observation.candidate.combined_score = qualifies ? 1000U : 100U;
	observation.candidate.combined_median = 100.0;
	observation.candidate.peak_to_median = qualifies ? 2.0 : 1.0;
	observation.candidate.robust_z = qualifies ? 10.0 : 0.0;
	observation.candidate.estimated_frame_period_samples =
		PSS_MAP_PHASE_BINS + (double)drift / PSS_MAP_TILE_FRAMES;
	observation.candidate.newest_generation = generation;
	observation.candidate.newest_start_index =
		(uint64_t)(generation - 1U) * tile_samples;
	observation.candidate.reference_start_index =
		observation.candidate.newest_start_index - 2U * tile_samples;
	return observation;
}

static void step_expect(struct pss_lock_controller *controller,
	struct pss_lock_observation observation, enum pss_lock_state expected)
{
	char error[ERROR_SIZE] = {0};

	CHECK(pss_lock_controller_step(controller, &observation,
		error, sizeof(error)) == 0, error);
	CHECK(controller->state == expected, "unexpected lock-state transition");
}

static void test_lock_state_machine(void)
{
	struct pss_lock_policy policy = {
		.minimum_peak_to_median = 1.15,
		.minimum_robust_z = 6.0,
		.confirmation_hits = 3U,
		.maximum_holdover_misses = 2U,
		.phase_tolerance_samples = 16U,
		.drift_tolerance_bins_per_tile = 4U,
		.phase_bins = PSS_MAP_PHASE_BINS,
		.tile_frames = PSS_MAP_TILE_FRAMES,
	};
	struct pss_lock_controller controller;
	struct pss_lock_observation observation;
	char error[ERROR_SIZE] = {0};

	CHECK(pss_lock_controller_init(&controller, &policy,
		error, sizeof(error)) == 0, error);
	CHECK(strcmp(pss_lock_state_name(controller.state), "ACQUIRE") == 0,
		"initial state name is wrong");
	step_expect(&controller, make_observation(3U, 1200U, 12, true, true),
		PSS_LOCK_CONFIRM);
	step_expect(&controller, make_observation(4U, 1212U, 12, true, true),
		PSS_LOCK_CONFIRM);
	step_expect(&controller, make_observation(5U, 1224U, 12, true, true),
		PSS_LOCK_LOCK);
	CHECK(controller.lock_generation == 1U,
		"confirmation did not publish one lock generation");
	step_expect(&controller, make_observation(6U, 1236U, 12, true, true),
		PSS_LOCK_TRACK);
	step_expect(&controller, make_observation(7U, 0U, 12, false, true),
		PSS_LOCK_HOLDOVER);
	step_expect(&controller, make_observation(8U, 1260U, 12, true, true),
		PSS_LOCK_TRACK);
	step_expect(&controller, make_observation(9U, 0U, 12, false, true),
		PSS_LOCK_HOLDOVER);
	step_expect(&controller, make_observation(10U, 0U, 12, false, true),
		PSS_LOCK_HOLDOVER);
	step_expect(&controller, make_observation(11U, 0U, 12, false, true),
		PSS_LOCK_ACQUIRE);
	CHECK(controller.lock_generation == 1U,
		"loss of lock rewrote the lock generation");

	step_expect(&controller, make_observation(12U, 1308U, 12, true, true),
		PSS_LOCK_CONFIRM);
	step_expect(&controller, make_observation(13U, 1320U, 12, true, false),
		PSS_LOCK_ACQUIRE);
	step_expect(&controller, make_observation(14U, 1332U, 12, true, true),
		PSS_LOCK_CONFIRM);
	step_expect(&controller, make_observation(15U, 5000U, 12, true, true),
		PSS_LOCK_CONFIRM);
	CHECK(controller.confirmation_count == 1U,
		"inconsistent confirmation did not restart at one");

	observation = make_observation(17U, 5024U, 12, true, true);
	step_expect(&controller, observation, PSS_LOCK_ACQUIRE);
	CHECK(controller.confirmation_count == 0U,
		"metadata discontinuity was not fail-closed");

	policy.confirmation_hits = 1U;
	CHECK(pss_lock_controller_init(&controller, &policy,
		error, sizeof(error)) < 0,
		"unsafe one-hit lock policy was accepted");
	policy.confirmation_hits = 3U;
	policy.phase_bins = (uint32_t)INT32_MAX + 1U;
	CHECK(pss_lock_controller_init(&controller, &policy,
		error, sizeof(error)) < 0,
		"unsafe signed-phase lock geometry was accepted");
}

static int run_stdin_extractor(void)
{
	struct pss_map_window window;
	struct pss_acquisition_candidate candidate;
	uint16_t *storage = NULL;
	uint16_t *map = NULL;
	uint32_t *scratch = NULL;
	int32_t *drifts = NULL;
	unsigned int phase_bins, tile_frames, drift_count;
	uint64_t tile_samples;
	char error[ERROR_SIZE] = {0};
	size_t tile, phase;
	int result = EXIT_FAILURE;

	if (scanf("%u %u %u", &phase_bins, &tile_frames, &drift_count) != 3 ||
	    phase_bins < 2U || phase_bins > INT32_MAX || tile_frames < 2U ||
	    !drift_count || drift_count > PSS_ACQUISITION_DRIFT_HYPOTHESES)
		goto done;
	storage = calloc((size_t)PSS_ACQUISITION_WINDOW_MAPS * phase_bins,
		sizeof(*storage));
	map = calloc(phase_bins, sizeof(*map));
	scratch = calloc((size_t)phase_bins * 2U, sizeof(*scratch));
	drifts = calloc(drift_count, sizeof(*drifts));
	if (!storage || !map || !scratch || !drifts)
		goto done;
	for (phase = 0; phase < drift_count; ++phase) {
		if (scanf("%" SCNd32, &drifts[phase]) != 1)
			goto done;
	}
	if (pss_map_window_init(&window, storage,
		(size_t)PSS_ACQUISITION_WINDOW_MAPS * phase_bins,
		phase_bins, tile_frames, error, sizeof(error)) < 0)
		goto done;
	tile_samples = (uint64_t)phase_bins * tile_frames;
	for (tile = 0; tile < PSS_ACQUISITION_WINDOW_MAPS; ++tile) {
		for (phase = 0; phase < phase_bins; ++phase) {
			unsigned int value;

			if (scanf("%u", &value) != 1 || value > UINT16_MAX)
				goto done;
			map[phase] = (uint16_t)value;
		}
		if (pss_map_window_push(&window, map, (uint32_t)tile + 1U,
			tile * tile_samples, error, sizeof(error)) < 0)
			goto done;
	}
	if (pss_acquisition_extract(&window, drifts, drift_count, scratch,
		(size_t)phase_bins * 2U, &candidate, error, sizeof(error)) < 0)
		goto done;
	printf("%" PRIu32 " %" PRId32 " %" PRIu32 " %.17g %.17g %.17g %.17g\n",
		candidate.phase_bin, candidate.drift_bins_per_tile,
		candidate.combined_score, candidate.combined_median,
		candidate.peak_to_median, candidate.robust_z,
		candidate.estimated_frame_period_samples);
	result = EXIT_SUCCESS;

done:
	if (result != EXIT_SUCCESS && error[0])
		fprintf(stderr, "%s\n", error);
	free(drifts);
	free(scratch);
	free(map);
	free(storage);
	return result;
}

int main(int argc, char **argv)
{
	if (argc == 2 && strcmp(argv[1], "--extract-stdin") == 0)
		return run_stdin_extractor();
	if (argc != 1) {
		fprintf(stderr, "usage: %s [--extract-stdin]\n", argv[0]);
		return EXIT_FAILURE;
	}
	test_contract_snapshot_copy_and_release();
	test_copy_fail_closed_on_metadata_change();
	test_snapshot_and_contract_fail_closed();
	test_window_and_extractor();
	test_lock_state_machine();

	if (failures) {
		fprintf(stderr, "STARLINK_PSS_ACQUISITION_FAIL failures=%u\n",
			failures);
		return EXIT_FAILURE;
	}
	printf("STARLINK_PSS_ACQUISITION_PASS map_words=%u map_reads=%u "
		"window_maps=%u drift_hypotheses=7 state_path="
		"ACQUIRE-CONFIRM-LOCK-TRACK-HOLDOVER-ACQUIRE\n",
		PSS_MAP_PHASE_BINS, PSS_MAP_PHASE_BINS,
		PSS_ACQUISITION_WINDOW_MAPS);
	return EXIT_SUCCESS;
}
