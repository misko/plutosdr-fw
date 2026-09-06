// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef STARLINK_PSS_PERIODIC_INJECTION_H
#define STARLINK_PSS_PERIODIC_INJECTION_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PSS_INJECTION_IDENTIFICATION UINT32_C(0x50535349)
#define PSS_INJECTION_VERSION UINT32_C(0x00010000)
#define PSS_INJECTION_CAPABILITIES UINT32_C(0x0000000f)
#define PSS_INJECTION_FIXTURE_SAMPLES 130U
#define PSS_INJECTION_REPETITIONS 130U
#define PSS_INJECTION_PERIOD_SAMPLES 20000U
#define PSS_INJECTION_GEOMETRY UINT32_C(0x00820082)
#define PSS_INJECTION_MINIMUM_ARM_LEAD UINT64_C(65536)
#define PSS_INJECTION_LAST_SAMPLE_OFFSET UINT64_C(2580129)

enum pss_injection_register {
	PSS_INJECTION_REG_IDENTIFICATION = 0x00,
	PSS_INJECTION_REG_VERSION = 0x04,
	PSS_INJECTION_REG_CAPABILITIES = 0x08,
	PSS_INJECTION_REG_GEOMETRY = 0x0c,
	PSS_INJECTION_REG_PERIOD = 0x10,
	PSS_INJECTION_REG_CURRENT_INDEX_LO = 0x14,
	PSS_INJECTION_REG_CURRENT_INDEX_HI = 0x18,
	PSS_INJECTION_REG_FIXTURE_DATA = 0x1c,
	PSS_INJECTION_REG_CONTROL = 0x20,
	PSS_INJECTION_REG_START_INDEX_LO = 0x24,
	PSS_INJECTION_REG_START_INDEX_HI = 0x28,
	PSS_INJECTION_REG_GENERATION = 0x2c,
	PSS_INJECTION_REG_STATUS = 0x30,
	PSS_INJECTION_REG_LAST_GENERATION = 0x34,
	PSS_INJECTION_REG_LAST_REPETITIONS = 0x38,
	PSS_INJECTION_REG_LAST_OFFSET_LO = 0x3c,
	PSS_INJECTION_REG_LAST_OFFSET_HI = 0x40,
};

enum pss_injection_status_bit {
	PSS_INJECTION_STATUS_FIXTURE_VALID = 1U << 0,
	PSS_INJECTION_STATUS_ARM_READY = 1U << 1,
	PSS_INJECTION_STATUS_ARM_PENDING = 1U << 2,
	PSS_INJECTION_STATUS_ACTIVE = 1U << 3,
	PSS_INJECTION_STATUS_COMPLETED = 1U << 4,
	PSS_INJECTION_STATUS_REJECTED = 1U << 5,
	PSS_INJECTION_STATUS_MISMATCH = 1U << 6,
	PSS_INJECTION_STATUS_INFLIGHT = 1U << 7,
};

#define PSS_INJECTION_STATUS_KNOWN_MASK UINT32_C(0x0000ffff)
#define PSS_INJECTION_STATUS_FAULT_MASK \
	(PSS_INJECTION_STATUS_REJECTED | PSS_INJECTION_STATUS_MISMATCH)

struct pss_injection_io {
	void *context;
	int (*read32)(void *context, uint32_t offset, uint32_t *value);
	int (*write32)(void *context, uint32_t offset, uint32_t value);
};

struct pss_injection_info {
	uint32_t identification;
	uint32_t version;
	uint32_t capabilities;
	uint32_t geometry;
	uint32_t period_samples;
	uint64_t last_sample_offset;
};

struct pss_injection_state {
	uint32_t status;
	uint32_t fixture_count;
	uint32_t last_completed_generation;
	uint32_t last_completed_repetitions;
};

int pss_injection_require_contract(const struct pss_injection_io *io,
	struct pss_injection_info *info, char *error, size_t error_size);
int pss_injection_read_state(const struct pss_injection_io *io,
	struct pss_injection_state *state, char *error, size_t error_size);
int pss_injection_read_current_index(const struct pss_injection_io *io,
	uint64_t *current_index, char *error, size_t error_size);
int pss_injection_load_fixture(const struct pss_injection_io *io,
	const uint32_t *packed_qi_words, size_t word_count, uint32_t generation,
	unsigned int timeout_ms, char *error, size_t error_size);
int pss_injection_arm(const struct pss_injection_io *io, uint64_t start_index,
	unsigned int timeout_ms, char *error, size_t error_size);
int pss_injection_wait_complete(const struct pss_injection_io *io,
	uint32_t generation, unsigned int timeout_ms,
	struct pss_injection_state *final_state, char *error, size_t error_size);
bool pss_injection_state_fault_free(const struct pss_injection_state *state);

#endif
