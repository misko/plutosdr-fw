// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef STARLINK_PSS_HW_H
#define STARLINK_PSS_HW_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PSS_MMIO_BASE UINT64_C(0x79030000)
#define PSS_MMIO_SPAN 4096U

#define PSS_IDENTIFICATION UINT32_C(0x50535354)
#define PSS_VERSION UINT32_C(0x00010001)
#define PSS_RATE_MSPS UINT32_C(15)
#define PSS_GEOMETRY UINT32_C(0x003d8242)
#define PSS_CAPABILITIES UINT32_C(0x0000001d)

#define PSS_COEFFICIENT_COUNT 66U
#define PSS_RESULT_WORDS 26U
#define PSS_FIRST_LAG (-30)
#define PSS_LAST_LAG 30
#define PSS_DEFAULT_LEAD_SAMPLES UINT64_C(1000000)

enum pss_register {
	PSS_REG_IDENTIFICATION = 0x00,
	PSS_REG_VERSION = 0x04,
	PSS_REG_RATE_MSPS = 0x08,
	PSS_REG_GEOMETRY = 0x0c,
	PSS_REG_CAPABILITIES = 0x10,
	PSS_REG_STATUS = 0x14,
	PSS_REG_CURRENT_INDEX_LO = 0x18,
	PSS_REG_CURRENT_INDEX_HI = 0x1c,
	PSS_REG_CANDIDATE_REQUEST = 0x20,
	PSS_REG_CANDIDATE_CENTER_LO = 0x24,
	PSS_REG_CANDIDATE_CENTER_HI = 0x28,
	PSS_REG_CANDIDATE_TIMESTAMP_LO = 0x2c,
	PSS_REG_CANDIDATE_TIMESTAMP_HI = 0x30,
	PSS_REG_CANDIDATE_CONTROL = 0x34,
	PSS_REG_CANDIDATE_COMMAND_OVERRUN = 0x38,
	PSS_REG_COEFFICIENT_WRITE_OVERRUN = 0x3c,
	PSS_REG_COEFFICIENT_DATA = 0x40,
	PSS_REG_COEFFICIENT_CONTROL = 0x44,
	PSS_REG_COEFFICIENT_GENERATION = 0x48,
	PSS_REG_ACTIVE_COEFFICIENT_GENERATION = 0x4c,
	PSS_REG_RESULT_WORD_INDEX = 0x50,
	PSS_REG_RESULT_WORD_DATA = 0x54,
	PSS_REG_RESULT_CONTROL = 0x58,
	PSS_REG_RESULT_STATUS = 0x5c,
	PSS_REG_ACTIVE_ENERGY_LO = 0x60,
	PSS_REG_ACTIVE_ENERGY_HI = 0x64,
	PSS_REG_TELEMETRY_CONTROL = 0x68,
	PSS_REG_TELEMETRY_STATUS = 0x6c,
	PSS_REG_TELEMETRY_GENERATION = 0x70,
	PSS_REG_QUEUE_OVERRUN = 0x80,
	PSS_REG_ADMITTED = 0x84,
	PSS_REG_COMPLETED_CAPTURE = 0x88,
	PSS_REG_REJECTED = 0x8c,
	PSS_REG_LATE = 0x90,
	PSS_REG_DUPLICATE = 0x94,
	PSS_REG_OVERLAP = 0x98,
	PSS_REG_ABORTED = 0x9c,
	PSS_REG_VALID_GAP_ABORT = 0xa0,
	PSS_REG_INDEX_JUMP_ABORT = 0xa4,
	PSS_REG_TIMESTAMP_ABORT = 0xa8,
	PSS_REG_CAPTURE_PUBLISHED = 0xac,
	PSS_REG_CAPTURE_ABORT_DISCARD = 0xb0,
	PSS_REG_CAPTURE_BUFFER_OVERRUN = 0xb4,
	PSS_REG_CAPTURE_PROTOCOL_ERROR = 0xb8,
	PSS_REG_ENGINE_CONSUMED = 0xbc,
	PSS_REG_CORRELATOR_BOUND_ERROR = 0xc0,
	PSS_REG_REDUCER_PROCESSED = 0xc4,
	PSS_REG_REDUCER_EMITTED = 0xc8,
	PSS_REG_REDUCER_INVALID = 0xcc,
	PSS_REG_REDUCER_BOUND_ERROR = 0xd0,
	PSS_REG_REDUCER_PROTOCOL_ERROR = 0xd4,
	PSS_REG_RESULT_PUBLISHED = 0xd8,
	PSS_REG_RESULT_OVERRUN = 0xdc,
	PSS_REG_RESULT_CONSUMED = 0xe0,
};

enum pss_status_bit {
	PSS_STATUS_RESET_RELEASED = 1U << 0,
	PSS_STATUS_CANDIDATE_READY = 1U << 1,
	PSS_STATUS_COMMAND_BUFFERED = 1U << 2,
	PSS_STATUS_COEFFICIENT_VALID = 1U << 3,
	PSS_STATUS_COEFFICIENT_READY = 1U << 4,
	PSS_STATUS_COEFFICIENT_COMMIT_READY = 1U << 5,
	PSS_STATUS_RESULT_AVAILABLE = 1U << 6,
};

struct pss_io {
	void *context;
	int (*read32)(void *context, uint32_t offset, uint32_t *value);
	int (*write32)(void *context, uint32_t offset, uint32_t value);
};

struct pss_info {
	uint32_t identification;
	uint32_t version;
	uint32_t rate_msps;
	uint32_t geometry;
	uint32_t capabilities;
	uint32_t status;
	uint32_t active_generation;
};

struct pss_ci16 {
	int16_t i;
	int16_t q;
};

struct pss_counters {
	uint32_t telemetry_generation;
	uint32_t candidate_command_overrun;
	uint32_t coefficient_write_overrun;
	uint32_t queue_overrun;
	uint32_t admitted;
	uint32_t completed_capture;
	uint32_t rejected;
	uint32_t late;
	uint32_t duplicate;
	uint32_t overlap;
	uint32_t aborted;
	uint32_t valid_gap_abort;
	uint32_t index_jump_abort;
	uint32_t timestamp_abort;
	uint32_t capture_published;
	uint32_t capture_abort_discard;
	uint32_t capture_buffer_overrun;
	uint32_t capture_protocol_error;
	uint32_t engine_consumed;
	uint32_t correlator_bound_error;
	uint32_t reducer_processed;
	uint32_t reducer_emitted;
	uint32_t reducer_invalid;
	uint32_t reducer_bound_error;
	uint32_t reducer_protocol_error;
	uint32_t result_published;
	uint32_t result_overrun;
	uint32_t result_consumed;
};

struct pss_packet {
	uint32_t words[PSS_RESULT_WORDS];
	uint32_t request_id;
	uint64_t center_index;
	uint64_t center_timestamp;
	int32_t lag;
	uint64_t winner_timestamp;
	uint32_t coefficient_generation;
	int64_t correlation_real;
	int64_t correlation_imag;
	int64_t sample_energy;
	int64_t coefficient_energy;
	uint32_t saturation_events;
};

struct pss_track_request {
	uint32_t request_id;
	uint64_t center;
	uint64_t lead_samples;
	bool center_is_explicit;
	unsigned int timeout_ms;
};

struct pss_track_result {
	uint64_t scheduled_center;
	struct pss_packet packet;
	struct pss_counters before;
	struct pss_counters after;
};

int pss_read_info(const struct pss_io *io, struct pss_info *info,
	char *error, size_t error_size);
int pss_require_contract(const struct pss_io *io, struct pss_info *info,
	char *error, size_t error_size);
int pss_read_current_index(const struct pss_io *io, uint64_t *index,
	char *error, size_t error_size);
int pss_read_ci16_file(const char *path,
	struct pss_ci16 coefficients[PSS_COEFFICIENT_COUNT],
	char *error, size_t error_size);
int pss_load_coefficients(const struct pss_io *io,
	const struct pss_ci16 coefficients[PSS_COEFFICIENT_COUNT],
	uint32_t generation, unsigned int timeout_ms,
	char *error, size_t error_size);
int pss_snapshot_counters(const struct pss_io *io,
	struct pss_counters *counters, unsigned int timeout_ms,
	char *error, size_t error_size);
int pss_validate_packet(const uint32_t words[PSS_RESULT_WORDS],
	uint32_t request_id, uint64_t center_index, uint64_t center_timestamp,
	uint32_t generation,
	struct pss_packet *packet, char *error, size_t error_size);
int pss_track_one(const struct pss_io *io,
	const struct pss_track_request *request, struct pss_track_result *result,
	char *error, size_t error_size);

#endif
