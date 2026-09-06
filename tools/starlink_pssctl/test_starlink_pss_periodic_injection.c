// SPDX-License-Identifier: GPL-2.0-or-later
#include "starlink_pss_periodic_injection.h"

#include <stdio.h>
#include <string.h>

#define MOCK_WORDS ((PSS_INJECTION_REG_LAST_OFFSET_HI / 4U) + 1U)
#define ERROR_SIZE 256U

struct mock_injection {
	uint32_t registers[MOCK_WORDS];
	uint32_t fixture[PSS_INJECTION_FIXTURE_SAMPLES];
	uint32_t fixture_count;
	uint32_t current_generation;
	uint64_t current_index;
	bool complete_on_arm;
};

static unsigned int failures;

#define CHECK(condition, message) \
	do { \
		if (!(condition)) { \
			fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, message); \
			failures++; \
		} \
	} while (0)

static uint32_t *mock_register(struct mock_injection *mock, uint32_t offset)
{
	return &mock->registers[offset / 4U];
}

static void mock_set_count(struct mock_injection *mock)
{
	uint32_t *status = mock_register(mock, PSS_INJECTION_REG_STATUS);

	*status = (*status & UINT32_C(0xff)) | (mock->fixture_count << 8);
}

static void mock_init(struct mock_injection *mock)
{
	memset(mock, 0, sizeof(*mock));
	*mock_register(mock, PSS_INJECTION_REG_IDENTIFICATION) =
		PSS_INJECTION_IDENTIFICATION;
	*mock_register(mock, PSS_INJECTION_REG_VERSION) = PSS_INJECTION_VERSION;
	*mock_register(mock, PSS_INJECTION_REG_CAPABILITIES) =
		PSS_INJECTION_CAPABILITIES;
	*mock_register(mock, PSS_INJECTION_REG_GEOMETRY) = PSS_INJECTION_GEOMETRY;
	*mock_register(mock, PSS_INJECTION_REG_PERIOD) =
		PSS_INJECTION_PERIOD_SAMPLES;
	*mock_register(mock, PSS_INJECTION_REG_LAST_OFFSET_LO) =
		(uint32_t)PSS_INJECTION_LAST_SAMPLE_OFFSET;
	*mock_register(mock, PSS_INJECTION_REG_LAST_OFFSET_HI) =
		(uint32_t)(PSS_INJECTION_LAST_SAMPLE_OFFSET >> 32);
	mock->current_index = UINT64_C(1000000);
	mock->complete_on_arm = true;
}

static int mock_read32(void *context, uint32_t offset, uint32_t *value)
{
	struct mock_injection *mock = context;

	if (!value || offset > PSS_INJECTION_REG_LAST_OFFSET_HI || (offset & 3U))
		return -1;
	if (offset == PSS_INJECTION_REG_CURRENT_INDEX_LO) {
		*value = (uint32_t)mock->current_index;
		*mock_register(mock, PSS_INJECTION_REG_CURRENT_INDEX_HI) =
			(uint32_t)(mock->current_index >> 32);
		return 0;
	}
	*value = *mock_register(mock, offset);
	return 0;
}

static int mock_write32(void *context, uint32_t offset, uint32_t value)
{
	struct mock_injection *mock = context;
	uint32_t *status = mock_register(mock, PSS_INJECTION_REG_STATUS);

	if (offset > PSS_INJECTION_REG_LAST_OFFSET_HI || (offset & 3U))
		return -1;
	switch (offset) {
	case PSS_INJECTION_REG_FIXTURE_DATA:
		if (mock->fixture_count >= PSS_INJECTION_FIXTURE_SAMPLES ||
		    (*status & PSS_INJECTION_STATUS_FIXTURE_VALID)) {
			*status |= PSS_INJECTION_STATUS_REJECTED;
		} else {
			mock->fixture[mock->fixture_count++] = value;
			mock_set_count(mock);
		}
		break;
	case PSS_INJECTION_REG_GENERATION:
		mock->current_generation = value;
		*mock_register(mock, offset) = value;
		break;
	case PSS_INJECTION_REG_CONTROL:
		if (value == 1U) {
			mock->fixture_count = 0U;
			*status = 0U;
			*mock_register(mock, PSS_INJECTION_REG_LAST_GENERATION) = 0U;
			*mock_register(mock, PSS_INJECTION_REG_LAST_REPETITIONS) = 0U;
		} else if (value == 2U &&
			   mock->fixture_count == PSS_INJECTION_FIXTURE_SAMPLES &&
			   mock->current_generation) {
			*status |= PSS_INJECTION_STATUS_FIXTURE_VALID |
				PSS_INJECTION_STATUS_ARM_READY;
		} else if (value == 4U &&
			   (*status & PSS_INJECTION_STATUS_ARM_READY)) {
			if (mock->complete_on_arm) {
				*status &= ~(PSS_INJECTION_STATUS_ARM_READY |
					PSS_INJECTION_STATUS_INFLIGHT |
					PSS_INJECTION_STATUS_ACTIVE |
					PSS_INJECTION_STATUS_ARM_PENDING);
				*status |= PSS_INJECTION_STATUS_COMPLETED;
				*mock_register(mock,
					PSS_INJECTION_REG_LAST_GENERATION) =
					mock->current_generation;
				*mock_register(mock,
					PSS_INJECTION_REG_LAST_REPETITIONS) =
					PSS_INJECTION_REPETITIONS;
			} else {
				*status &= ~PSS_INJECTION_STATUS_ARM_READY;
				*status |= PSS_INJECTION_STATUS_INFLIGHT;
			}
		} else {
			*status |= PSS_INJECTION_STATUS_REJECTED;
		}
		break;
	default:
		*mock_register(mock, offset) = value;
		break;
	}
	return 0;
}

static struct pss_injection_io mock_io(struct mock_injection *mock)
{
	struct pss_injection_io io = {
		.context = mock,
		.read32 = mock_read32,
		.write32 = mock_write32,
	};

	return io;
}

static void test_contract_load_and_completion(void)
{
	struct mock_injection mock;
	struct pss_injection_io io;
	struct pss_injection_info info;
	struct pss_injection_state state;
	uint32_t fixture[PSS_INJECTION_FIXTURE_SAMPLES];
	uint64_t current_index;
	char error[ERROR_SIZE] = {0};
	size_t index;

	mock_init(&mock);
	io = mock_io(&mock);
	for (index = 0; index < PSS_INJECTION_FIXTURE_SAMPLES; ++index)
		fixture[index] = UINT32_C(0xa5000000) | (uint32_t)index;
	CHECK(pss_injection_require_contract(&io, &info,
		error, sizeof(error)) == 0, error);
	CHECK(info.last_sample_offset == PSS_INJECTION_LAST_SAMPLE_OFFSET,
		"wrong interval offset");
	CHECK(pss_injection_read_current_index(&io, &current_index,
		error, sizeof(error)) == 0, error);
	CHECK(current_index == mock.current_index, "coherent current index changed");
	CHECK(pss_injection_load_fixture(&io, fixture,
		PSS_INJECTION_FIXTURE_SAMPLES, UINT32_C(0x15020001), 10U,
		error, sizeof(error)) == 0, error);
	CHECK(!memcmp(fixture, mock.fixture, sizeof(fixture)),
		"fixture words changed during load");
	CHECK(pss_injection_read_state(&io, &state, error, sizeof(error)) == 0,
		error);
	CHECK(state.fixture_count == PSS_INJECTION_FIXTURE_SAMPLES,
		"sealed fixture count changed");
	CHECK(pss_injection_arm(&io,
		mock.current_index + PSS_INJECTION_MINIMUM_ARM_LEAD, 10U,
		error, sizeof(error)) < 0,
		"instant completion incorrectly satisfied inflight arm acknowledgement");

	/* Reload after the deliberate mocked race and model a real inflight arm. */
	mock_init(&mock);
	io = mock_io(&mock);
	mock.complete_on_arm = false;
	CHECK(pss_injection_load_fixture(&io, fixture,
		PSS_INJECTION_FIXTURE_SAMPLES, UINT32_C(0x15020002), 10U,
		error, sizeof(error)) == 0, error);
	CHECK(pss_injection_arm(&io,
		mock.current_index + PSS_INJECTION_MINIMUM_ARM_LEAD, 10U,
		error, sizeof(error)) == 0, error);
	*mock_register(&mock, PSS_INJECTION_REG_STATUS) &=
		~PSS_INJECTION_STATUS_INFLIGHT;
	*mock_register(&mock, PSS_INJECTION_REG_STATUS) |=
		PSS_INJECTION_STATUS_COMPLETED;
	*mock_register(&mock, PSS_INJECTION_REG_LAST_GENERATION) =
		UINT32_C(0x15020002);
	*mock_register(&mock, PSS_INJECTION_REG_LAST_REPETITIONS) =
		PSS_INJECTION_REPETITIONS;
	CHECK(pss_injection_wait_complete(&io, UINT32_C(0x15020002), 10U,
		&state, error, sizeof(error)) == 0, error);
	CHECK(pss_injection_state_fault_free(&state),
		"positive completion was not fault free");
}

static void test_fail_closed_arguments_and_contract(void)
{
	struct mock_injection mock;
	struct pss_injection_io io;
	uint32_t fixture[PSS_INJECTION_FIXTURE_SAMPLES] = {0};
	char error[ERROR_SIZE] = {0};

	mock_init(&mock);
	io = mock_io(&mock);
	CHECK(pss_injection_load_fixture(&io, fixture,
		PSS_INJECTION_FIXTURE_SAMPLES - 1U, 1U, 10U,
		error, sizeof(error)) < 0, "short fixture was accepted");
	CHECK(pss_injection_load_fixture(&io, fixture,
		PSS_INJECTION_FIXTURE_SAMPLES, 0U, 10U,
		error, sizeof(error)) < 0, "zero generation was accepted");
	CHECK(pss_injection_arm(&io,
		mock.current_index + PSS_INJECTION_MINIMUM_ARM_LEAD - 1U, 10U,
		error, sizeof(error)) < 0, "short arm lead was accepted");
	*mock_register(&mock, PSS_INJECTION_REG_CAPABILITIES) ^= 1U;
	CHECK(pss_injection_require_contract(&io, NULL,
		error, sizeof(error)) < 0, "contract mismatch was accepted");
}

int main(void)
{
	test_contract_load_and_completion();
	test_fail_closed_arguments_and_contract();
	if (failures) {
		fprintf(stderr, "PSS_PERIODIC_INJECTION_TEST_FAIL failures=%u\n",
			failures);
		return 1;
	}
	printf("PSS_PERIODIC_INJECTION_TEST_PASS fixture_words=%u period=%u repetitions=%u\n",
		PSS_INJECTION_FIXTURE_SAMPLES, PSS_INJECTION_PERIOD_SAMPLES,
		PSS_INJECTION_REPETITIONS);
	return 0;
}
