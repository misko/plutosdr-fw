// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef STARLINK_PSS_ACQUISITION_H
#define STARLINK_PSS_ACQUISITION_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PSS_MAP_IDENTIFICATION UINT32_C(0x50534d41)
#define PSS_MAP_VERSION_1_0 UINT32_C(0x00010000)
#define PSS_MAP_VERSION_1_1 UINT32_C(0x00010001)
#define PSS_MAP_VERSION PSS_MAP_VERSION_1_1
#define PSS_MAP_PHASE_BINS 20000U
#define PSS_MAP_TILE_FRAMES 64U
#define PSS_MAP_WORD_BITS 16U
#define PSS_MAP_BANKS 2U
#define PSS_MAP_CAPABILITIES_1_0 UINT32_C(0x0000001f)
#define PSS_MAP_CAPABILITIES_1_1 UINT32_C(0x0000003f)
#define PSS_MAP_CAPABILITIES PSS_MAP_CAPABILITIES_1_1
#define PSS_MAP_TILE_GEOMETRY UINT32_C(0x00401002)
#define PSS_ACQUISITION_WINDOW_MAPS 3U
#define PSS_ACQUISITION_DRIFT_HYPOTHESES 7U
#define PSS_ACQUISITION_SCRATCH_WORDS (2U * PSS_MAP_PHASE_BINS)

extern const int32_t
	pss_acquisition_default_drift_bank[PSS_ACQUISITION_DRIFT_HYPOTHESES];

enum pss_map_register {
	PSS_MAP_REG_IDENTIFICATION = 0x00,
	PSS_MAP_REG_VERSION = 0x04,
	PSS_MAP_REG_PHASE_BINS = 0x08,
	PSS_MAP_REG_TILE_GEOMETRY = 0x0c,
	PSS_MAP_REG_CAPABILITIES = 0x10,
	PSS_MAP_REG_CONTROL = 0x14,
	PSS_MAP_REG_STATUS = 0x18,
	PSS_MAP_REG_SELECT = 0x1c,
	PSS_MAP_REG_INDEX = 0x20,
	PSS_MAP_REG_DATA = 0x24,
	PSS_MAP_REG_RELEASE = 0x28,
	PSS_MAP_REG_COMMAND_STATUS = 0x2c,
	PSS_MAP_REG_SNAPSHOT_CONTROL = 0x30,
	PSS_MAP_REG_SNAPSHOT_STATUS = 0x34,
	PSS_MAP_REG_SNAPSHOT_GENERATION = 0x38,
	PSS_MAP_REG_SNAPSHOT_READY = 0x3c,
	PSS_MAP_REG_SNAPSHOT_MAP_GENERATION_0 = 0x40,
	PSS_MAP_REG_SNAPSHOT_MAP_GENERATION_1 = 0x44,
	PSS_MAP_REG_SNAPSHOT_START_INDEX_0_LO = 0x48,
	PSS_MAP_REG_SNAPSHOT_START_INDEX_0_HI = 0x4c,
	PSS_MAP_REG_SNAPSHOT_START_INDEX_1_LO = 0x50,
	PSS_MAP_REG_SNAPSHOT_START_INDEX_1_HI = 0x54,
	PSS_MAP_REG_SNAPSHOT_ACCEPTED = 0x58,
	PSS_MAP_REG_SNAPSHOT_DISCARDED = 0x5c,
	PSS_MAP_REG_SNAPSHOT_DISCONTINUITY = 0x60,
	PSS_MAP_REG_SNAPSHOT_PUBLISHED = 0x64,
	PSS_MAP_REG_SNAPSHOT_OVERRUN = 0x68,
	PSS_MAP_REG_SNAPSHOT_PROTOCOL_ERROR = 0x6c,
	PSS_MAP_REG_SNAPSHOT_ARITHMETIC_OVERFLOW = 0x70,
	PSS_MAP_REG_SNAPSHOT_READ_ERROR = 0x74,
	PSS_MAP_REG_SNAPSHOT_RELEASE_ERROR = 0x78,
	PSS_MAP_REG_BRIDGE_READ_ERROR = 0x7c,
	PSS_MAP_REG_BRIDGE_RELEASE_ERROR = 0x80,
	PSS_MAP_REG_SNAPSHOT_REQUEST_OVERRUN = 0x84,
	PSS_MAP_REG_SNAPSHOT_HEALTH_FLAGS = 0x88,
	PSS_MAP_REG_SNAPSHOT_INGRESS_DROPPED = 0x8c,
	PSS_MAP_REG_SNAPSHOT_INGRESS_FIFO = 0x90,
	PSS_MAP_REG_SNAPSHOT_SCHEDULER_GAP = 0x94,
	PSS_MAP_REG_SNAPSHOT_SCHEDULER_INDEX_ERROR = 0x98,
	PSS_MAP_REG_SNAPSHOT_SCHEDULER_OVERFLOW = 0x9c,
	PSS_MAP_REG_SNAPSHOT_DETECTOR_FAULT = 0xa0,
	PSS_MAP_REG_SNAPSHOT_PHASE_DISCONTINUITY = 0xa4,
	PSS_MAP_REG_SNAPSHOT_DENOMINATOR_ZERO = 0xa8,
	PSS_MAP_REG_SNAPSHOT_CANDIDATE_FIFO = 0xac,
};

enum pss_map_health_bit {
	PSS_MAP_HEALTH_DETECTOR_FAULT = 1U << 0,
	PSS_MAP_HEALTH_SCHEDULER_GAP = 1U << 1,
	PSS_MAP_HEALTH_SCHEDULER_INDEX_ERROR = 1U << 2,
	PSS_MAP_HEALTH_SCHEDULER_OVERFLOW = 1U << 3,
	PSS_MAP_HEALTH_FORWARD_FFT = 1U << 4,
	PSS_MAP_HEALTH_KERNEL_JOIN = 1U << 5,
	PSS_MAP_HEALTH_PRODUCT_OVERFLOW = 1U << 6,
	PSS_MAP_HEALTH_INVERSE_FFT = 1U << 7,
	PSS_MAP_HEALTH_FORWARD_EXPONENT = 1U << 8,
	PSS_MAP_HEALTH_CANDIDATE_PATH = 1U << 9,
	PSS_MAP_HEALTH_PHASE_DISCONTINUITY = 1U << 10,
	PSS_MAP_HEALTH_DENOMINATOR_ZERO = 1U << 11,
	PSS_MAP_HEALTH_INGRESS_OVERFLOW = 1U << 12,
};

#define PSS_MAP_HEALTH_KNOWN_MASK UINT32_C(0x00001fff)
#define PSS_MAP_HEALTH_CONTINUITY_MASK UINT32_C(0x000017ff)

enum pss_map_status_bit {
	PSS_MAP_STATUS_CONTROL_EPOCH_LIVE = 1U << 0,
	PSS_MAP_STATUS_ENABLED = 1U << 1,
	PSS_MAP_STATUS_READY_0 = 1U << 2,
	PSS_MAP_STATUS_READY_1 = 1U << 3,
	PSS_MAP_STATUS_IRQ = 1U << 4,
};

enum pss_map_command_status_bit {
	PSS_MAP_COMMAND_READ_PENDING = 1U << 0,
	PSS_MAP_COMMAND_RELEASE_PENDING = 1U << 1,
	PSS_MAP_COMMAND_READ_ERROR = 1U << 2,
	PSS_MAP_COMMAND_RELEASE_ERROR = 1U << 3,
};

struct pss_map_io {
	void *context;
	int (*read32)(void *context, uint32_t offset, uint32_t *value);
	int (*write32)(void *context, uint32_t offset, uint32_t value);
};

struct pss_map_info {
	uint32_t identification;
	uint32_t version;
	uint32_t phase_bins;
	uint32_t tile_geometry;
	uint32_t capabilities;
	uint32_t status;
};

struct pss_map_snapshot {
	uint32_t abi_version;
	uint32_t snapshot_generation;
	uint32_t ready_mask;
	uint32_t map_generation[2];
	uint64_t map_start_index[2];
	uint32_t accepted_score_count;
	uint32_t discarded_score_count;
	uint32_t discontinuity_abort_count;
	uint32_t map_publish_count;
	uint32_t map_overrun_count;
	uint32_t score_protocol_error_count;
	uint32_t arithmetic_overflow_count;
	uint32_t map_read_error_count;
	uint32_t map_release_error_count;
	uint32_t health_flags;
	uint32_t ingress_dropped_sample_count;
	uint16_t ingress_fifo_level;
	uint16_t ingress_maximum_fifo_level;
	uint32_t scheduler_gap_count;
	uint32_t scheduler_index_error_count;
	uint32_t scheduler_overflow_count;
	uint32_t detector_fault_count;
	uint32_t score_phase_index_discontinuity_count;
	uint32_t score_denominator_zero_count;
	uint16_t candidate_fifo_stored_count;
	uint16_t candidate_fifo_maximum_stored_count;
};

struct pss_map_copy {
	unsigned int bank;
	uint32_t generation;
	uint64_t start_index;
	struct pss_map_snapshot before;
	struct pss_map_snapshot after;
	uint32_t bridge_read_error_before;
	uint32_t bridge_read_error_after;
	uint32_t bridge_release_error_before;
	uint32_t bridge_release_error_after;
};

struct pss_map_window {
	uint16_t *maps;
	size_t storage_words;
	uint32_t phase_bins;
	uint32_t tile_frames;
	size_t count;
	uint32_t generations[PSS_ACQUISITION_WINDOW_MAPS];
	uint64_t start_indexes[PSS_ACQUISITION_WINDOW_MAPS];
};

struct pss_acquisition_candidate {
	uint32_t phase_bin;
	int32_t drift_bins_per_tile;
	uint32_t combined_score;
	double combined_median;
	double peak_to_median;
	double robust_z;
	double estimated_frame_period_samples;
	uint64_t reference_start_index;
	uint32_t newest_generation;
	uint64_t newest_start_index;
};

enum pss_lock_state {
	PSS_LOCK_ACQUIRE = 0,
	PSS_LOCK_CONFIRM,
	PSS_LOCK_LOCK,
	PSS_LOCK_TRACK,
	PSS_LOCK_HOLDOVER,
};

struct pss_lock_policy {
	double minimum_peak_to_median;
	double minimum_robust_z;
	uint32_t confirmation_hits;
	uint32_t maximum_holdover_misses;
	uint32_t phase_tolerance_samples;
	uint32_t drift_tolerance_bins_per_tile;
	uint32_t phase_bins;
	uint32_t tile_frames;
};

struct pss_lock_observation {
	bool continuity_ok;
	struct pss_acquisition_candidate candidate;
};

struct pss_lock_controller {
	struct pss_lock_policy policy;
	enum pss_lock_state state;
	uint32_t confirmation_count;
	uint32_t holdover_miss_count;
	uint32_t lock_generation;
	bool have_last_metadata;
	uint32_t last_generation;
	uint64_t last_start_index;
	bool have_anchor;
	uint32_t anchor_phase;
	int32_t anchor_drift;
	uint32_t anchor_generation;
};

int pss_map_require_contract(const struct pss_map_io *io,
	struct pss_map_info *info, char *error, size_t error_size);
int pss_map_set_enabled(const struct pss_map_io *io, bool enabled, bool flush,
	char *error, size_t error_size);
int pss_map_take_snapshot(const struct pss_map_io *io,
	struct pss_map_snapshot *snapshot, unsigned int timeout_ms,
	char *error, size_t error_size);
int pss_map_copy_and_release(const struct pss_map_io *io,
	const struct pss_map_snapshot *snapshot, unsigned int bank,
	uint16_t *destination, size_t destination_words,
	struct pss_map_copy *copy, unsigned int timeout_ms,
	char *error, size_t error_size);
bool pss_map_copies_contiguous(const struct pss_map_copy *previous,
	const struct pss_map_copy *current);

int pss_map_window_init(struct pss_map_window *window, uint16_t *storage,
	size_t storage_words, uint32_t phase_bins, uint32_t tile_frames,
	char *error, size_t error_size);
void pss_map_window_reset(struct pss_map_window *window);
int pss_map_window_push(struct pss_map_window *window, const uint16_t *map,
	uint32_t generation, uint64_t start_index,
	char *error, size_t error_size);
bool pss_map_window_ready(const struct pss_map_window *window);

int pss_acquisition_extract(const struct pss_map_window *window,
	const int32_t *drift_bank, size_t drift_count,
	uint32_t *scratch, size_t scratch_words,
	struct pss_acquisition_candidate *candidate,
	char *error, size_t error_size);
bool pss_acquisition_candidate_passes(
	const struct pss_acquisition_candidate *candidate,
	double minimum_peak_to_median, double minimum_robust_z);

int pss_lock_controller_init(struct pss_lock_controller *controller,
	const struct pss_lock_policy *policy, char *error, size_t error_size);
void pss_lock_controller_reset(struct pss_lock_controller *controller);
int pss_lock_controller_step(struct pss_lock_controller *controller,
	const struct pss_lock_observation *observation,
	char *error, size_t error_size);
const char *pss_lock_state_name(enum pss_lock_state state);

#endif
