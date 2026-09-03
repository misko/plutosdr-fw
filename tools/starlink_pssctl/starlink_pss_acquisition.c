// SPDX-License-Identifier: GPL-2.0-or-later
#define _POSIX_C_SOURCE 200809L

#include "starlink_pss_acquisition.h"

#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

const int32_t
	pss_acquisition_default_drift_bank[PSS_ACQUISITION_DRIFT_HYPOTHESES] = {
		-12, -8, -4, 0, 4, 8, 12,
	};

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

static int map_read32(const struct pss_map_io *io, uint32_t offset,
	uint32_t *value, char *error, size_t error_size)
{
	if (!io || !io->read32 || !value)
		return fail(error, error_size, "invalid phase-map read arguments");
	if (offset > PSS_MAP_REG_SNAPSHOT_CANDIDATE_FIFO || (offset & 3U))
		return fail(error, error_size,
			"invalid phase-map read offset 0x%08" PRIx32, offset);
	if (io->read32(io->context, offset, value) < 0)
		return fail(error, error_size,
			"phase-map read 0x%02" PRIx32 " failed", offset);
	return 0;
}

static int map_write32(const struct pss_map_io *io, uint32_t offset,
	uint32_t value, char *error, size_t error_size)
{
	if (!io || !io->write32)
		return fail(error, error_size, "invalid phase-map write arguments");
	if (offset > PSS_MAP_REG_SNAPSHOT_CANDIDATE_FIFO || (offset & 3U))
		return fail(error, error_size,
			"invalid phase-map write offset 0x%08" PRIx32, offset);
	if (io->write32(io->context, offset, value) < 0)
		return fail(error, error_size,
			"phase-map write 0x%02" PRIx32 " failed", offset);
	return 0;
}

static uint64_t combine_u64(uint32_t low, uint32_t high)
{
	return (uint64_t)low | (uint64_t)high << 32;
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

static int timeout_expired(uint64_t start, unsigned int timeout_ms,
	bool *expired, char *error, size_t error_size)
{
	uint64_t now;

	if (!expired || monotonic_milliseconds(&now) < 0)
		return fail(error, error_size, "CLOCK_MONOTONIC read failed");
	*expired = now - start >= timeout_ms;
	return 0;
}

static void poll_delay(void)
{
	struct timespec delay = {.tv_sec = 0, .tv_nsec = 100000L};

	while (nanosleep(&delay, &delay) < 0 && errno == EINTR)
		;
}

static bool known_contract(uint32_t version, uint32_t capabilities)
{
	return (version == PSS_MAP_VERSION_1_0 &&
		capabilities == PSS_MAP_CAPABILITIES_1_0) ||
		(version == PSS_MAP_VERSION_1_1 &&
		 capabilities == PSS_MAP_CAPABILITIES_1_1);
}

int pss_map_require_contract(const struct pss_map_io *io,
	struct pss_map_info *info, char *error, size_t error_size)
{
	struct pss_map_info local;
	struct pss_map_info *destination = info ? info : &local;

	memset(destination, 0, sizeof(*destination));
	if (map_read32(io, PSS_MAP_REG_IDENTIFICATION,
			&destination->identification, error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_VERSION, &destination->version,
			error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_PHASE_BINS, &destination->phase_bins,
			error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_TILE_GEOMETRY,
			&destination->tile_geometry, error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_CAPABILITIES,
			&destination->capabilities, error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_STATUS, &destination->status,
			error, error_size) < 0)
		return -1;
	if (destination->identification != PSS_MAP_IDENTIFICATION)
		return fail(error, error_size,
			"wrong phase-map ID: expected 0x%08" PRIx32 ", got 0x%08" PRIx32,
			PSS_MAP_IDENTIFICATION, destination->identification);
	if (destination->version != PSS_MAP_VERSION_1_0 &&
	    destination->version != PSS_MAP_VERSION_1_1)
		return fail(error, error_size,
			"unsupported phase-map version 0x%08" PRIx32,
			destination->version);
	if (destination->phase_bins != PSS_MAP_PHASE_BINS ||
	    destination->tile_geometry != PSS_MAP_TILE_GEOMETRY)
		return fail(error, error_size,
			"wrong phase-map geometry: bins=%" PRIu32 " geometry=0x%08" PRIx32,
			destination->phase_bins, destination->tile_geometry);
	if (!known_contract(destination->version, destination->capabilities))
		return fail(error, error_size,
			"wrong phase-map capabilities 0x%08" PRIx32
			" for version 0x%08" PRIx32,
			destination->capabilities, destination->version);
	if (!(destination->status & PSS_MAP_STATUS_CONTROL_EPOCH_LIVE))
		return fail(error, error_size, "phase-map control epoch is not live");
	return 0;
}

int pss_map_set_enabled(const struct pss_map_io *io, bool enabled, bool flush,
	char *error, size_t error_size)
{
	if (pss_map_require_contract(io, NULL, error, error_size) < 0)
		return -1;
	return map_write32(io, PSS_MAP_REG_CONTROL,
		(enabled ? 1U : 0U) | (flush ? 2U : 0U), error, error_size);
}

static int read_snapshot_payload(const struct pss_map_io *io,
	struct pss_map_snapshot *snapshot, uint32_t abi_version,
	char *error, size_t error_size)
{
	uint32_t start_low[2], start_high[2], fifo_levels, candidate_levels;

	if (map_read32(io, PSS_MAP_REG_SNAPSHOT_READY, &snapshot->ready_mask,
			error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_MAP_GENERATION_0,
			&snapshot->map_generation[0], error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_MAP_GENERATION_1,
			&snapshot->map_generation[1], error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_START_INDEX_0_LO,
			&start_low[0], error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_START_INDEX_0_HI,
			&start_high[0], error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_START_INDEX_1_LO,
			&start_low[1], error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_START_INDEX_1_HI,
			&start_high[1], error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_ACCEPTED,
			&snapshot->accepted_score_count, error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_DISCARDED,
			&snapshot->discarded_score_count, error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_DISCONTINUITY,
			&snapshot->discontinuity_abort_count, error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_PUBLISHED,
			&snapshot->map_publish_count, error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_OVERRUN,
			&snapshot->map_overrun_count, error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_PROTOCOL_ERROR,
			&snapshot->score_protocol_error_count, error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_ARITHMETIC_OVERFLOW,
			&snapshot->arithmetic_overflow_count, error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_READ_ERROR,
			&snapshot->map_read_error_count, error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_RELEASE_ERROR,
			&snapshot->map_release_error_count, error, error_size) < 0)
		return -1;
	snapshot->ready_mask &= 3U;
	snapshot->map_start_index[0] = combine_u64(start_low[0], start_high[0]);
	snapshot->map_start_index[1] = combine_u64(start_low[1], start_high[1]);
	if (abi_version == PSS_MAP_VERSION_1_0)
		return 0;
	if (abi_version != PSS_MAP_VERSION_1_1)
		return fail(error, error_size,
			"unsupported phase-map snapshot version 0x%08" PRIx32,
			abi_version);
	if (map_read32(io, PSS_MAP_REG_SNAPSHOT_HEALTH_FLAGS,
			&snapshot->health_flags, error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_INGRESS_DROPPED,
			&snapshot->ingress_dropped_sample_count,
			error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_INGRESS_FIFO, &fifo_levels,
			error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_SCHEDULER_GAP,
			&snapshot->scheduler_gap_count, error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_SCHEDULER_INDEX_ERROR,
			&snapshot->scheduler_index_error_count,
			error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_SCHEDULER_OVERFLOW,
			&snapshot->scheduler_overflow_count,
			error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_DETECTOR_FAULT,
			&snapshot->detector_fault_count, error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_PHASE_DISCONTINUITY,
			&snapshot->score_phase_index_discontinuity_count,
			error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_DENOMINATOR_ZERO,
			&snapshot->score_denominator_zero_count,
			error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_CANDIDATE_FIFO,
			&candidate_levels, error, error_size) < 0)
		return -1;
	if (snapshot->health_flags & ~PSS_MAP_HEALTH_KNOWN_MASK)
		return fail(error, error_size,
			"phase-map snapshot has unknown health flags 0x%08" PRIx32,
			snapshot->health_flags & ~PSS_MAP_HEALTH_KNOWN_MASK);
	if (candidate_levels & UINT32_C(0xfc00fc00))
		return fail(error, error_size,
			"phase-map candidate FIFO snapshot has nonzero reserved bits");
	snapshot->ingress_fifo_level = (uint16_t)fifo_levels;
	snapshot->ingress_maximum_fifo_level = (uint16_t)(fifo_levels >> 16);
	snapshot->candidate_fifo_stored_count =
		(uint16_t)(candidate_levels & UINT32_C(0x3ff));
	snapshot->candidate_fifo_maximum_stored_count =
		(uint16_t)((candidate_levels >> 16) & UINT32_C(0x3ff));
	return 0;
}

int pss_map_take_snapshot(const struct pss_map_io *io,
	struct pss_map_snapshot *snapshot, unsigned int timeout_ms,
	char *error, size_t error_size)
{
	struct pss_map_info info;
	uint32_t generation_before, generation_after, generation_final;
	uint32_t status, status_final;
	uint32_t overrun_before, overrun_after;
	uint64_t start;
	bool expired;

	if (!snapshot)
		return fail(error, error_size, "missing phase-map snapshot destination");
	if (!timeout_ms)
		return fail(error, error_size, "phase-map snapshot timeout must be nonzero");
	memset(snapshot, 0, sizeof(*snapshot));
	if (pss_map_require_contract(io, &info, error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_STATUS, &status,
			error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_GENERATION, &generation_before,
			error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_REQUEST_OVERRUN, &overrun_before,
			error, error_size) < 0)
		return -1;
	if (status & 2U)
		return fail(error, error_size, "a phase-map snapshot is already pending");
	if (generation_before == UINT32_MAX)
		return fail(error, error_size,
			"phase-map snapshot generation is saturated");
	if (overrun_before == UINT32_MAX)
		return fail(error, error_size,
			"phase-map snapshot-request overrun counter is saturated");
	if (map_write32(io, PSS_MAP_REG_SNAPSHOT_CONTROL, 1U,
			error, error_size) < 0)
		return -1;
	if (monotonic_milliseconds(&start) < 0)
		return fail(error, error_size, "CLOCK_MONOTONIC read failed");
	for (;;) {
		if (map_read32(io, PSS_MAP_REG_SNAPSHOT_STATUS, &status,
				error, error_size) < 0 ||
		    map_read32(io, PSS_MAP_REG_SNAPSHOT_GENERATION,
				&generation_after, error, error_size) < 0)
			return -1;
		if (generation_after != generation_before &&
		    generation_after != generation_before + 1U)
			return fail(error, error_size,
				"phase-map snapshot generation changed unexpectedly");
		if ((status & 3U) == 1U &&
		    generation_after == generation_before + 1U)
			break;
		if (timeout_expired(start, timeout_ms, &expired,
				error, error_size) < 0)
			return -1;
		if (expired)
			return fail(error, error_size, "phase-map snapshot timed out");
		poll_delay();
	}
	snapshot->abi_version = info.version;
	if (read_snapshot_payload(io, snapshot, info.version,
			error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_REQUEST_OVERRUN, &overrun_after,
			error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_STATUS, &status_final,
			error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_SNAPSHOT_GENERATION, &generation_final,
			error, error_size) < 0)
		return -1;
	if (overrun_after != overrun_before)
		return fail(error, error_size,
			"phase-map snapshot-request overrun changed (%" PRIu32
			" -> %" PRIu32 ")", overrun_before, overrun_after);
	if ((status_final & 3U) != 1U || generation_final != generation_after)
		return fail(error, error_size,
			"phase-map snapshot changed while its payload was read");
	snapshot->snapshot_generation = generation_after;
	return 0;
}

static bool bank_unchanged(const struct pss_map_snapshot *before,
	const struct pss_map_snapshot *after, unsigned int bank)
{
	return (after->ready_mask & (1U << bank)) &&
		after->map_generation[bank] == before->map_generation[bank] &&
		after->map_start_index[bank] == before->map_start_index[bank];
}

static bool fault_counters_unchanged(const struct pss_map_snapshot *before,
	const struct pss_map_snapshot *after)
{
	bool base_unchanged = before && after &&
		before->abi_version == after->abi_version &&
		before->discarded_score_count != UINT32_MAX &&
		before->discontinuity_abort_count != UINT32_MAX &&
		before->map_overrun_count != UINT32_MAX &&
		before->score_protocol_error_count != UINT32_MAX &&
		before->arithmetic_overflow_count != UINT32_MAX &&
		before->map_read_error_count != UINT32_MAX &&
		before->map_release_error_count != UINT32_MAX &&
		after->discarded_score_count == before->discarded_score_count &&
		after->discontinuity_abort_count ==
			before->discontinuity_abort_count &&
		after->map_overrun_count == before->map_overrun_count &&
		after->score_protocol_error_count ==
			before->score_protocol_error_count &&
		after->arithmetic_overflow_count ==
			before->arithmetic_overflow_count &&
		after->map_read_error_count == before->map_read_error_count &&
		after->map_release_error_count == before->map_release_error_count;

	if (!base_unchanged)
		return false;
	if (before->abi_version == PSS_MAP_VERSION_1_0)
		return true;
	if (before->abi_version != PSS_MAP_VERSION_1_1)
		return false;
	return (before->health_flags & PSS_MAP_HEALTH_CONTINUITY_MASK) ==
		(after->health_flags & PSS_MAP_HEALTH_CONTINUITY_MASK) &&
		before->ingress_dropped_sample_count != UINT32_MAX &&
		before->scheduler_gap_count != UINT32_MAX &&
		before->scheduler_index_error_count != UINT32_MAX &&
		before->scheduler_overflow_count != UINT32_MAX &&
		before->detector_fault_count != UINT32_MAX &&
		before->score_phase_index_discontinuity_count != UINT32_MAX &&
		after->ingress_dropped_sample_count ==
			before->ingress_dropped_sample_count &&
		after->scheduler_gap_count == before->scheduler_gap_count &&
		after->scheduler_index_error_count ==
			before->scheduler_index_error_count &&
		after->scheduler_overflow_count == before->scheduler_overflow_count &&
		after->detector_fault_count == before->detector_fault_count &&
		after->score_phase_index_discontinuity_count ==
			before->score_phase_index_discontinuity_count;
}

static bool copy_is_coherent(const struct pss_map_copy *copy)
{
	return copy && copy->bank < PSS_MAP_BANKS &&
		(copy->before.ready_mask & (1U << copy->bank)) &&
		(copy->after.ready_mask & (1U << copy->bank)) &&
		copy->before.snapshot_generation != UINT32_MAX &&
		copy->after.snapshot_generation ==
			copy->before.snapshot_generation + 1U &&
		copy->generation != UINT32_MAX &&
		copy->before.map_generation[copy->bank] == copy->generation &&
		copy->after.map_generation[copy->bank] == copy->generation &&
		copy->before.map_start_index[copy->bank] == copy->start_index &&
		copy->after.map_start_index[copy->bank] == copy->start_index &&
		fault_counters_unchanged(&copy->before, &copy->after) &&
		copy->bridge_read_error_before != UINT32_MAX &&
		copy->bridge_release_error_before != UINT32_MAX &&
		copy->bridge_read_error_after == copy->bridge_read_error_before &&
		copy->bridge_release_error_after == copy->bridge_release_error_before;
}

int pss_map_copy_and_release(const struct pss_map_io *io,
	const struct pss_map_snapshot *snapshot, unsigned int bank,
	uint16_t *destination, size_t destination_words,
	struct pss_map_copy *copy, unsigned int timeout_ms,
	char *error, size_t error_size)
{
	struct pss_map_info info;
	struct pss_map_snapshot after;
	struct pss_map_copy completed;
	uint32_t bridge_read_before, bridge_read_after;
	uint32_t bridge_release_before, bridge_release_after;
	uint32_t command_status, value;
	uint64_t start;
	size_t index;
	bool expired;

	if (!snapshot || !destination || !copy)
		return fail(error, error_size, "missing phase-map copy arguments");
	if (bank >= PSS_MAP_BANKS)
		return fail(error, error_size, "phase-map bank %u is invalid", bank);
	if (!(snapshot->ready_mask & (1U << bank)))
		return fail(error, error_size, "phase-map bank %u was not ready", bank);
	if (snapshot->map_generation[bank] == UINT32_MAX)
		return fail(error, error_size,
			"phase-map bank %u generation is saturated", bank);
	if (!timeout_ms)
		return fail(error, error_size, "phase-map copy timeout must be nonzero");
	if (pss_map_require_contract(io, &info, error, error_size) < 0)
		return -1;
	if (snapshot->abi_version != info.version)
		return fail(error, error_size,
			"phase-map ABI changed before copy (0x%08" PRIx32
			" -> 0x%08" PRIx32 ")",
			snapshot->abi_version, info.version);
	if (destination_words < info.phase_bins)
		return fail(error, error_size,
			"phase-map destination has %zu words; needs %" PRIu32,
			destination_words, info.phase_bins);
	if (map_read32(io, PSS_MAP_REG_BRIDGE_READ_ERROR, &bridge_read_before,
			error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_BRIDGE_RELEASE_ERROR, &bridge_release_before,
			error, error_size) < 0 ||
	    map_write32(io, PSS_MAP_REG_SELECT, bank, error, error_size) < 0 ||
	    map_write32(io, PSS_MAP_REG_INDEX, 0U, error, error_size) < 0)
		return -1;
	if (bridge_read_before == UINT32_MAX ||
	    bridge_release_before == UINT32_MAX)
		return fail(error, error_size,
			"phase-map bridge error counter is saturated");
	for (index = 0; index < info.phase_bins; ++index) {
		if (map_read32(io, PSS_MAP_REG_DATA, &value, error, error_size) < 0)
			return -1;
		if (value > UINT16_MAX)
			return fail(error, error_size,
				"phase-map word %zu is not zero-extended 16-bit data", index);
		destination[index] = (uint16_t)value;
	}
	if (map_read32(io, PSS_MAP_REG_COMMAND_STATUS, &command_status,
			error, error_size) < 0 ||
	    map_read32(io, PSS_MAP_REG_BRIDGE_READ_ERROR, &bridge_read_after,
			error, error_size) < 0)
		return -1;
	if (command_status & (PSS_MAP_COMMAND_READ_PENDING |
			PSS_MAP_COMMAND_READ_ERROR))
		return fail(error, error_size,
			"phase-map read completed with command status 0x%08" PRIx32,
			command_status);
	if (bridge_read_after != bridge_read_before)
		return fail(error, error_size,
			"phase-map bridge read-error counter changed (%" PRIu32
			" -> %" PRIu32 ")", bridge_read_before, bridge_read_after);
	if (pss_map_take_snapshot(io, &after, timeout_ms, error, error_size) < 0)
		return -1;
	if (!bank_unchanged(snapshot, &after, bank))
		return fail(error, error_size,
			"phase-map bank %u changed while it was copied", bank);
	if (!fault_counters_unchanged(snapshot, &after))
		return fail(error, error_size,
			"phase-map fault counters changed or saturated while copied");

	if (map_write32(io, PSS_MAP_REG_RELEASE, 1U, error, error_size) < 0)
		return -1;
	if (monotonic_milliseconds(&start) < 0)
		return fail(error, error_size, "CLOCK_MONOTONIC read failed");
	for (;;) {
		if (map_read32(io, PSS_MAP_REG_COMMAND_STATUS, &command_status,
				error, error_size) < 0)
			return -1;
		if (!(command_status & PSS_MAP_COMMAND_RELEASE_PENDING))
			break;
		if (timeout_expired(start, timeout_ms, &expired,
				error, error_size) < 0)
			return -1;
		if (expired)
			return fail(error, error_size, "phase-map release timed out");
		poll_delay();
	}
	if (command_status & PSS_MAP_COMMAND_RELEASE_ERROR)
		return fail(error, error_size,
			"phase-map release completed with command status 0x%08" PRIx32,
			command_status);
	if (map_read32(io, PSS_MAP_REG_BRIDGE_RELEASE_ERROR, &bridge_release_after,
			error, error_size) < 0)
		return -1;
	if (bridge_release_after != bridge_release_before)
		return fail(error, error_size,
			"phase-map bridge release-error counter changed (%" PRIu32
			" -> %" PRIu32 ")", bridge_release_before,
			bridge_release_after);
	memset(&completed, 0, sizeof(completed));
	completed.bank = bank;
	completed.generation = snapshot->map_generation[bank];
	completed.start_index = snapshot->map_start_index[bank];
	completed.before = *snapshot;
	completed.after = after;
	completed.bridge_read_error_before = bridge_read_before;
	completed.bridge_read_error_after = bridge_read_after;
	completed.bridge_release_error_before = bridge_release_before;
	completed.bridge_release_error_after = bridge_release_after;
	*copy = completed;
	return 0;
}

bool pss_map_copies_contiguous(const struct pss_map_copy *previous,
	const struct pss_map_copy *current)
{
	const uint64_t tile_samples =
		(uint64_t)PSS_MAP_PHASE_BINS * PSS_MAP_TILE_FRAMES;

	return copy_is_coherent(previous) && copy_is_coherent(current) &&
		previous->generation != UINT32_MAX &&
		current->generation == previous->generation + 1U &&
		previous->start_index <= UINT64_MAX - tile_samples &&
		current->start_index == previous->start_index + tile_samples &&
		fault_counters_unchanged(&previous->after, &current->before) &&
		previous->bridge_read_error_after != UINT32_MAX &&
		previous->bridge_release_error_after != UINT32_MAX &&
		current->bridge_read_error_before ==
			previous->bridge_read_error_after &&
		current->bridge_release_error_before ==
			previous->bridge_release_error_after;
}

int pss_map_window_init(struct pss_map_window *window, uint16_t *storage,
	size_t storage_words, uint32_t phase_bins, uint32_t tile_frames,
	char *error, size_t error_size)
{
	size_t required;

	if (!window || !storage)
		return fail(error, error_size, "missing phase-map window or storage");
	if (phase_bins < 2U || phase_bins > INT32_MAX || tile_frames < 2U)
		return fail(error, error_size, "phase-map window geometry is invalid");
	required = (size_t)phase_bins * PSS_ACQUISITION_WINDOW_MAPS;
	if (required / phase_bins != PSS_ACQUISITION_WINDOW_MAPS)
		return fail(error, error_size, "phase-map window size overflows size_t");
	if (storage_words < required)
		return fail(error, error_size,
			"phase-map window has %zu words; needs %zu", storage_words, required);
	memset(window, 0, sizeof(*window));
	window->maps = storage;
	window->storage_words = storage_words;
	window->phase_bins = phase_bins;
	window->tile_frames = tile_frames;
	return 0;
}

void pss_map_window_reset(struct pss_map_window *window)
{
	if (!window)
		return;
	window->count = 0U;
	memset(window->generations, 0, sizeof(window->generations));
	memset(window->start_indexes, 0, sizeof(window->start_indexes));
}

int pss_map_window_push(struct pss_map_window *window, const uint16_t *map,
	uint32_t generation, uint64_t start_index,
	char *error, size_t error_size)
{
	uint64_t tile_samples;
	size_t destination;

	if (!window || !window->maps || !map)
		return fail(error, error_size, "missing phase-map window input");
	if (window->phase_bins > UINT64_MAX / window->tile_frames)
		return fail(error, error_size, "phase-map tile span overflows");
	tile_samples = (uint64_t)window->phase_bins * window->tile_frames;
	if (window->count) {
		size_t previous = window->count - 1U;

		if (window->generations[previous] == UINT32_MAX ||
		    generation != window->generations[previous] + 1U ||
		    window->start_indexes[previous] > UINT64_MAX - tile_samples ||
		    start_index != window->start_indexes[previous] + tile_samples) {
			pss_map_window_reset(window);
			return fail(error, error_size,
				"phase-map generation or start-index continuity changed");
		}
	}
	if (window->count == PSS_ACQUISITION_WINDOW_MAPS) {
		memmove(window->maps, window->maps + window->phase_bins,
			(size_t)(PSS_ACQUISITION_WINDOW_MAPS - 1U) *
			window->phase_bins * sizeof(*window->maps));
		memmove(window->generations, window->generations + 1,
			(PSS_ACQUISITION_WINDOW_MAPS - 1U) *
			sizeof(*window->generations));
		memmove(window->start_indexes, window->start_indexes + 1,
			(PSS_ACQUISITION_WINDOW_MAPS - 1U) *
			sizeof(*window->start_indexes));
		window->count--;
	}
	destination = window->count;
	memcpy(window->maps + destination * window->phase_bins, map,
		(size_t)window->phase_bins * sizeof(*map));
	window->generations[destination] = generation;
	window->start_indexes[destination] = start_index;
	window->count++;
	return 0;
}

bool pss_map_window_ready(const struct pss_map_window *window)
{
	return window && window->count == PSS_ACQUISITION_WINDOW_MAPS;
}

static int compare_u32(const void *left, const void *right)
{
	uint32_t a = *(const uint32_t *)left;
	uint32_t b = *(const uint32_t *)right;

	return (a > b) - (a < b);
}

static uint32_t wrapped_index(uint32_t phase, size_t tile, int32_t drift,
	uint32_t phase_bins)
{
	int64_t index = (int64_t)phase + (int64_t)tile * drift;

	index %= phase_bins;
	if (index < 0)
		index += phase_bins;
	return (uint32_t)index;
}

static uint32_t combine_at(const struct pss_map_window *window,
	uint32_t phase, int32_t drift)
{
	uint32_t sum = 0U;
	size_t tile;

	for (tile = 0; tile < window->count; ++tile) {
		uint32_t source = wrapped_index(phase, tile, drift,
			window->phase_bins);

		sum += window->maps[tile * window->phase_bins + source];
	}
	return sum;
}

int pss_acquisition_extract(const struct pss_map_window *window,
	const int32_t *drift_bank, size_t drift_count,
	uint32_t *scratch, size_t scratch_words,
	struct pss_acquisition_candidate *candidate,
	char *error, size_t error_size)
{
	uint32_t *combined = scratch;
	uint32_t *ordered;
	uint32_t best_score = 0U, best_phase = 0U;
	int32_t best_drift = 0;
	bool have_best = false;
	uint64_t median_twice, mad_four;
	double median, median_absolute_deviation, robust_sigma;
	size_t hypothesis, phase;

	if (!window || !drift_bank || !scratch || !candidate)
		return fail(error, error_size, "missing acquisition extraction argument");
	if (!pss_map_window_ready(window))
		return fail(error, error_size, "three complete phase maps are required");
	if (!drift_count || drift_count > PSS_ACQUISITION_DRIFT_HYPOTHESES)
		return fail(error, error_size,
			"drift bank must contain one through seven hypotheses");
	if ((size_t)window->phase_bins * 2U / window->phase_bins != 2U ||
	    scratch_words < (size_t)window->phase_bins * 2U)
		return fail(error, error_size, "acquisition scratch buffer is too small");
	ordered = scratch + window->phase_bins;
	for (hypothesis = 0; hypothesis < drift_count; ++hypothesis) {
		uint32_t hypothesis_score = 0U, hypothesis_phase = 0U;
		int32_t drift = drift_bank[hypothesis];

		if ((hypothesis && drift <= drift_bank[hypothesis - 1U]) ||
		    drift <= -(int32_t)window->phase_bins ||
		    drift >= (int32_t)window->phase_bins)
			return fail(error, error_size,
				"drift bank must be strictly increasing and bounded");
		for (phase = 0; phase < window->phase_bins; ++phase) {
			uint32_t score = combine_at(window, (uint32_t)phase, drift);

			if (!phase || score > hypothesis_score) {
				hypothesis_score = score;
				hypothesis_phase = (uint32_t)phase;
			}
		}
		if (!have_best || hypothesis_score > best_score) {
			have_best = true;
			best_score = hypothesis_score;
			best_phase = hypothesis_phase;
			best_drift = drift;
		}
	}
	for (phase = 0; phase < window->phase_bins; ++phase)
		combined[phase] = combine_at(window, (uint32_t)phase, best_drift);
	memcpy(ordered, combined, (size_t)window->phase_bins * sizeof(*ordered));
	qsort(ordered, window->phase_bins, sizeof(*ordered), compare_u32);
	if (window->phase_bins & 1U)
		median_twice = (uint64_t)ordered[window->phase_bins / 2U] * 2U;
	else
		median_twice = (uint64_t)ordered[window->phase_bins / 2U - 1U] +
			ordered[window->phase_bins / 2U];
	for (phase = 0; phase < window->phase_bins; ++phase) {
		uint64_t value_twice = (uint64_t)combined[phase] * 2U;

		ordered[phase] = (uint32_t)(value_twice >= median_twice ?
			value_twice - median_twice : median_twice - value_twice);
	}
	qsort(ordered, window->phase_bins, sizeof(*ordered), compare_u32);
	if (window->phase_bins & 1U)
		mad_four = (uint64_t)ordered[window->phase_bins / 2U] * 2U;
	else
		mad_four = (uint64_t)ordered[window->phase_bins / 2U - 1U] +
			ordered[window->phase_bins / 2U];
	median = (double)median_twice / 2.0;
	median_absolute_deviation = (double)mad_four / 4.0;
	robust_sigma = 1.4826 * median_absolute_deviation;
	memset(candidate, 0, sizeof(*candidate));
	candidate->phase_bin = best_phase;
	candidate->drift_bins_per_tile = best_drift;
	candidate->combined_score = best_score;
	candidate->combined_median = median;
	candidate->peak_to_median = median > 0.0 ? best_score / median :
		(best_score ? INFINITY : 1.0);
	candidate->robust_z = robust_sigma > 0.0 ?
		(best_score - median) / robust_sigma :
		(best_score > median ? INFINITY : 0.0);
	candidate->estimated_frame_period_samples = window->phase_bins +
		(double)best_drift / window->tile_frames;
	candidate->reference_start_index = window->start_indexes[0];
	candidate->newest_generation =
		window->generations[PSS_ACQUISITION_WINDOW_MAPS - 1U];
	candidate->newest_start_index =
		window->start_indexes[PSS_ACQUISITION_WINDOW_MAPS - 1U];
	return 0;
}

bool pss_acquisition_candidate_passes(
	const struct pss_acquisition_candidate *candidate,
	double minimum_peak_to_median, double minimum_robust_z)
{
	if (!candidate || !isfinite(minimum_peak_to_median) ||
	    !isfinite(minimum_robust_z) || minimum_peak_to_median <= 0.0 ||
	    minimum_robust_z <= 0.0 || isnan(candidate->peak_to_median) ||
	    isnan(candidate->robust_z))
		return false;
	return candidate->peak_to_median >= minimum_peak_to_median &&
		candidate->robust_z >= minimum_robust_z;
}

static void reset_detection(struct pss_lock_controller *controller)
{
	controller->state = PSS_LOCK_ACQUIRE;
	controller->confirmation_count = 0U;
	controller->holdover_miss_count = 0U;
	controller->have_anchor = false;
	controller->anchor_phase = 0U;
	controller->anchor_drift = 0;
	controller->anchor_generation = 0U;
}

void pss_lock_controller_reset(struct pss_lock_controller *controller)
{
	if (!controller)
		return;
	reset_detection(controller);
	controller->lock_generation = 0U;
	controller->have_last_metadata = false;
	controller->last_generation = 0U;
	controller->last_start_index = 0U;
}

int pss_lock_controller_init(struct pss_lock_controller *controller,
	const struct pss_lock_policy *policy, char *error, size_t error_size)
{
	if (!controller || !policy)
		return fail(error, error_size, "missing lock controller or policy");
	if (!isfinite(policy->minimum_peak_to_median) ||
	    !isfinite(policy->minimum_robust_z) ||
	    policy->minimum_peak_to_median <= 0.0 ||
	    policy->minimum_robust_z <= 0.0 || policy->confirmation_hits < 2U ||
	    !policy->maximum_holdover_misses || policy->phase_bins < 2U ||
	    policy->phase_bins > INT32_MAX ||
	    policy->tile_frames < 2U ||
	    policy->phase_tolerance_samples >= policy->phase_bins / 2U ||
	    policy->drift_tolerance_bins_per_tile >= policy->phase_bins / 2U)
		return fail(error, error_size, "lock policy is invalid or unsafe");
	memset(controller, 0, sizeof(*controller));
	controller->policy = *policy;
	pss_lock_controller_reset(controller);
	return 0;
}

static uint32_t circular_distance(uint32_t left, uint32_t right, uint32_t size)
{
	uint32_t direct = left > right ? left - right : right - left;

	return direct < size - direct ? direct : size - direct;
}

static uint32_t candidate_absolute_phase(
	const struct pss_acquisition_candidate *candidate, uint32_t phase_bins)
{
	return (uint32_t)((candidate->reference_start_index % phase_bins +
		candidate->phase_bin) % phase_bins);
}

static void update_anchor(struct pss_lock_controller *controller,
	const struct pss_acquisition_candidate *candidate)
{
	controller->have_anchor = true;
	controller->anchor_phase = candidate_absolute_phase(candidate,
		controller->policy.phase_bins);
	controller->anchor_drift = candidate->drift_bins_per_tile;
	controller->anchor_generation = candidate->newest_generation;
}

static bool candidate_consistent(const struct pss_lock_controller *controller,
	const struct pss_acquisition_candidate *candidate)
{
	uint32_t generation_delta;
	int64_t predicted;
	uint32_t expected, observed;
	uint64_t drift_delta;

	if (!controller->have_anchor ||
	    candidate->newest_generation < controller->anchor_generation)
		return false;
	generation_delta = candidate->newest_generation -
		controller->anchor_generation;
	predicted = (int64_t)controller->anchor_phase +
		(int64_t)generation_delta * controller->anchor_drift;
	predicted %= controller->policy.phase_bins;
	if (predicted < 0)
		predicted += controller->policy.phase_bins;
	expected = (uint32_t)predicted;
	observed = candidate_absolute_phase(candidate, controller->policy.phase_bins);
	drift_delta = candidate->drift_bins_per_tile > controller->anchor_drift ?
		(uint64_t)((int64_t)candidate->drift_bins_per_tile -
			controller->anchor_drift) :
		(uint64_t)((int64_t)controller->anchor_drift -
			candidate->drift_bins_per_tile);
	return circular_distance(expected, observed, controller->policy.phase_bins) <=
		controller->policy.phase_tolerance_samples &&
		drift_delta <= controller->policy.drift_tolerance_bins_per_tile;
}

static bool observation_shape_valid(const struct pss_lock_controller *controller,
	const struct pss_acquisition_candidate *candidate)
{
	uint64_t tile_samples = (uint64_t)controller->policy.phase_bins *
		controller->policy.tile_frames;
	uint64_t window_span =
		(PSS_ACQUISITION_WINDOW_MAPS - 1U) * tile_samples;

	return candidate->phase_bin < controller->policy.phase_bins &&
		candidate->newest_generation >= PSS_ACQUISITION_WINDOW_MAPS &&
		candidate->reference_start_index <= candidate->newest_start_index &&
		candidate->newest_start_index - candidate->reference_start_index ==
			window_span &&
		candidate->drift_bins_per_tile >
			-(int32_t)controller->policy.phase_bins &&
		candidate->drift_bins_per_tile <
			(int32_t)controller->policy.phase_bins &&
		!isnan(candidate->peak_to_median) && !isnan(candidate->robust_z);
}

int pss_lock_controller_step(struct pss_lock_controller *controller,
	const struct pss_lock_observation *observation,
	char *error, size_t error_size)
{
	const struct pss_acquisition_candidate *candidate;
	uint64_t tile_samples;
	bool passes, consistent;

	if (!controller || !observation)
		return fail(error, error_size, "missing lock controller observation");
	candidate = &observation->candidate;
	if (!observation_shape_valid(controller, candidate))
		return fail(error, error_size, "lock observation geometry is invalid");
	tile_samples = (uint64_t)controller->policy.phase_bins *
		controller->policy.tile_frames;
	if (!observation->continuity_ok ||
	    (controller->have_last_metadata &&
	     (controller->last_generation == UINT32_MAX ||
	      candidate->newest_generation != controller->last_generation + 1U ||
	      controller->last_start_index > UINT64_MAX - tile_samples ||
	      candidate->newest_start_index !=
			controller->last_start_index + tile_samples))) {
		reset_detection(controller);
		controller->have_last_metadata = true;
		controller->last_generation = candidate->newest_generation;
		controller->last_start_index = candidate->newest_start_index;
		return 0;
	}
	controller->have_last_metadata = true;
	controller->last_generation = candidate->newest_generation;
	controller->last_start_index = candidate->newest_start_index;
	passes = pss_acquisition_candidate_passes(candidate,
		controller->policy.minimum_peak_to_median,
		controller->policy.minimum_robust_z);
	consistent = passes && candidate_consistent(controller, candidate);

	switch (controller->state) {
	case PSS_LOCK_ACQUIRE:
		if (passes) {
			update_anchor(controller, candidate);
			controller->confirmation_count = 1U;
			controller->state = PSS_LOCK_CONFIRM;
		}
		break;
	case PSS_LOCK_CONFIRM:
		if (!passes) {
			reset_detection(controller);
		} else if (!consistent) {
			update_anchor(controller, candidate);
			controller->confirmation_count = 1U;
		} else {
			update_anchor(controller, candidate);
			controller->confirmation_count++;
			if (controller->confirmation_count >=
			    controller->policy.confirmation_hits) {
				controller->state = PSS_LOCK_LOCK;
				if (controller->lock_generation != UINT32_MAX)
					controller->lock_generation++;
			}
		}
		break;
	case PSS_LOCK_LOCK:
	case PSS_LOCK_TRACK:
		if (consistent) {
			update_anchor(controller, candidate);
			controller->holdover_miss_count = 0U;
			controller->state = PSS_LOCK_TRACK;
		} else {
			controller->holdover_miss_count = 1U;
			controller->state = PSS_LOCK_HOLDOVER;
		}
		break;
	case PSS_LOCK_HOLDOVER:
		if (consistent) {
			update_anchor(controller, candidate);
			controller->holdover_miss_count = 0U;
			controller->state = PSS_LOCK_TRACK;
		} else {
			controller->holdover_miss_count++;
			if (controller->holdover_miss_count >
			    controller->policy.maximum_holdover_misses)
				reset_detection(controller);
		}
		break;
	default:
		return fail(error, error_size, "lock controller state is invalid");
	}
	return 0;
}

const char *pss_lock_state_name(enum pss_lock_state state)
{
	switch (state) {
	case PSS_LOCK_ACQUIRE:
		return "ACQUIRE";
	case PSS_LOCK_CONFIRM:
		return "CONFIRM";
	case PSS_LOCK_LOCK:
		return "LOCK";
	case PSS_LOCK_TRACK:
		return "TRACK";
	case PSS_LOCK_HOLDOVER:
		return "HOLDOVER";
	default:
		return "INVALID";
	}
}
