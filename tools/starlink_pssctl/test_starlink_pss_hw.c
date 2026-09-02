// SPDX-License-Identifier: GPL-2.0-or-later
#include "starlink_pss_hw.h"

#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MOCK_REGISTERS (PSS_MMIO_SPAN / sizeof(uint32_t))

struct mock_candidate {
	uint32_t request;
	uint64_t center;
	uint64_t timestamp;
};

struct mock_device {
	uint32_t registers[MOCK_REGISTERS];
	uint32_t result[PSS_RESULT_WORDS];
	uint32_t loaded[PSS_COEFFICIENT_COUNT];
	uint32_t injected[PSS_INJECTION_SAMPLES];
	struct mock_candidate candidates[PSS_COMMAND_FIFO_USABLE];
	uint64_t current_index;
	uint64_t index_snapshot;
	uint64_t center;
	uint64_t timestamp;
	uint32_t request;
	uint32_t generation_stage;
	uint32_t result_index;
	unsigned int loaded_count;
	unsigned int injection_count;
	unsigned int injection_status_reads;
	unsigned int candidate_head;
	unsigned int candidate_tail;
	unsigned int candidate_count;
	uint32_t injection_flags;
	bool inject_rejected;
};

static uint32_t *mock_register(struct mock_device *mock, uint32_t offset)
{
	return &mock->registers[offset / sizeof(uint32_t)];
}

static void mock_status(struct mock_device *mock)
{
	unsigned int queue_room = PSS_COMMAND_FIFO_USABLE - mock->candidate_count;
	uint32_t status = PSS_STATUS_RESET_RELEASED;

	if (queue_room)
		status |= PSS_STATUS_CANDIDATE_READY;
	if (*mock_register(mock, PSS_REG_ACTIVE_COEFFICIENT_GENERATION))
		status |= PSS_STATUS_COEFFICIENT_VALID;
	if (mock->loaded_count < PSS_COEFFICIENT_COUNT)
		status |= PSS_STATUS_COEFFICIENT_READY;
	if (mock->loaded_count == PSS_COEFFICIENT_COUNT)
		status |= PSS_STATUS_COEFFICIENT_COMMIT_READY;
	if (*mock_register(mock, PSS_REG_RESULT_STATUS) & 1U)
		status |= PSS_STATUS_RESULT_AVAILABLE;
	status |= mock->loaded_count << 8;
	status |= queue_room << 17;
	*mock_register(mock, PSS_REG_STATUS) = status;
}

static void mock_make_result(struct mock_device *mock,
	const struct mock_candidate *candidate)
{
	int32_t lag = -7;
	uint64_t winner = candidate->timestamp + lag;

	memset(mock->result, 0, sizeof(mock->result));
	mock->result[0] = UINT32_C(0x31535350);
	mock->result[1] = UINT32_C(0x1a010001);
	mock->result[2] = candidate->request;
	mock->result[3] = (uint32_t)candidate->center;
	mock->result[4] = (uint32_t)(candidate->center >> 32);
	mock->result[5] = (uint32_t)candidate->timestamp;
	mock->result[6] = (uint32_t)(candidate->timestamp >> 32);
	mock->result[7] = (uint32_t)lag;
	mock->result[8] = (uint32_t)winner;
	mock->result[9] = (uint32_t)(winner >> 32);
	mock->result[10] = *mock_register(mock,
		PSS_REG_ACTIVE_COEFFICIENT_GENERATION);
	mock->result[11] = 12U;
	mock->result[13] = (uint32_t)-34;
	mock->result[14] = UINT32_MAX;
	mock->result[15] = 12345U;
	mock->result[17] = 23456U;
	mock->result[20] = 144U;
	mock->result[23] = 12345U;
	*mock_register(mock, PSS_REG_RESULT_STATUS) = (26U << 24) | 1U;

	++*mock_register(mock, PSS_REG_ADMITTED);
	++*mock_register(mock, PSS_REG_COMPLETED_CAPTURE);
	++*mock_register(mock, PSS_REG_CAPTURE_PUBLISHED);
	++*mock_register(mock, PSS_REG_ENGINE_CONSUMED);
	++*mock_register(mock, PSS_REG_REDUCER_PROCESSED);
	++*mock_register(mock, PSS_REG_REDUCER_EMITTED);
	++*mock_register(mock, PSS_REG_RESULT_PUBLISHED);
	if (mock->inject_rejected)
		++*mock_register(mock, PSS_REG_REJECTED);
}

static void mock_publish_next_result(struct mock_device *mock)
{
	struct mock_candidate *candidate;

	if ((*mock_register(mock, PSS_REG_RESULT_STATUS) & 1U) ||
	    !mock->candidate_count)
		return;
	candidate = &mock->candidates[mock->candidate_head];
	mock_make_result(mock, candidate);
	mock->candidate_head =
		(mock->candidate_head + 1U) % PSS_COMMAND_FIFO_USABLE;
	--mock->candidate_count;
}

static int mock_read32(void *context, uint32_t offset, uint32_t *value)
{
	struct mock_device *mock = context;

	if (offset >= PSS_MMIO_SPAN || (offset & 3U))
		return -1;
	if (offset == PSS_REG_STATUS)
		mock_status(mock);
	if (offset == PSS_REG_CURRENT_INDEX_LO) {
		mock->index_snapshot = mock->current_index;
		*value = (uint32_t)mock->index_snapshot;
		return 0;
	}
	if (offset == PSS_REG_CURRENT_INDEX_HI) {
		*value = (uint32_t)(mock->index_snapshot >> 32);
		return 0;
	}
	if (offset == PSS_REG_RESULT_WORD_DATA) {
		*value = mock->result[mock->result_index];
		return 0;
	}
	if (offset == PSS_REG_RESULT_STATUS)
		mock_publish_next_result(mock);
	if (offset == PSS_REG_INJECTION_STATUS) {
		*value = mock->injection_flags | mock->injection_count << 8;
		if (mock->injection_flags & PSS_INJECTION_INFLIGHT) {
			if (mock->injection_status_reads++) {
				mock->injection_flags =
					PSS_INJECTION_FIXTURE_VALID |
					PSS_INJECTION_ARM_READY |
					PSS_INJECTION_COMPLETED;
				*mock_register(mock,
					PSS_REG_INJECTION_LAST_GENERATION) =
					*mock_register(mock, PSS_REG_INJECTION_GENERATION);
			}
		}
		return 0;
	}
	*value = *mock_register(mock, offset);
	return 0;
}

static int mock_write32(void *context, uint32_t offset, uint32_t value)
{
	struct mock_device *mock = context;

	if (offset >= PSS_MMIO_SPAN || (offset & 3U))
		return -1;
	switch (offset) {
	case PSS_REG_COEFFICIENT_CONTROL:
		if (value & 1U)
			mock->loaded_count = 0;
		else if ((value & 2U) && mock->loaded_count == PSS_COEFFICIENT_COUNT) {
			*mock_register(mock, PSS_REG_ACTIVE_COEFFICIENT_GENERATION) =
				mock->generation_stage;
			mock->loaded_count = 0;
		}
		break;
	case PSS_REG_COEFFICIENT_DATA:
		if (mock->loaded_count < PSS_COEFFICIENT_COUNT)
			mock->loaded[mock->loaded_count++] = value;
		else
			++*mock_register(mock, PSS_REG_COEFFICIENT_WRITE_OVERRUN);
		break;
	case PSS_REG_COEFFICIENT_GENERATION:
		mock->generation_stage = value;
		break;
	case PSS_REG_CANDIDATE_REQUEST:
		mock->request = value;
		break;
	case PSS_REG_CANDIDATE_CENTER_LO:
		mock->center = (mock->center & UINT64_C(0xffffffff00000000)) | value;
		break;
	case PSS_REG_CANDIDATE_CENTER_HI:
		mock->center = (mock->center & UINT64_C(0xffffffff)) | (uint64_t)value << 32;
		break;
	case PSS_REG_CANDIDATE_TIMESTAMP_LO:
		mock->timestamp = (mock->timestamp & UINT64_C(0xffffffff00000000)) | value;
		break;
	case PSS_REG_CANDIDATE_TIMESTAMP_HI:
		mock->timestamp = (mock->timestamp & UINT64_C(0xffffffff)) |
			(uint64_t)value << 32;
		break;
	case PSS_REG_CANDIDATE_CONTROL:
		if (value & 1U) {
			struct mock_candidate *candidate;

			if (mock->candidate_count == PSS_COMMAND_FIFO_USABLE) {
				++*mock_register(mock, PSS_REG_CANDIDATE_COMMAND_OVERRUN);
				break;
			}
			candidate = &mock->candidates[mock->candidate_tail];
			candidate->request = mock->request;
			candidate->center = mock->center;
			candidate->timestamp = mock->timestamp;
			mock->candidate_tail =
				(mock->candidate_tail + 1U) % PSS_COMMAND_FIFO_USABLE;
			++mock->candidate_count;
		}
		break;
	case PSS_REG_RESULT_WORD_INDEX:
		mock->result_index = value < PSS_RESULT_WORDS ? value :
			PSS_RESULT_WORDS - 1U;
		break;
	case PSS_REG_RESULT_CONTROL:
		if (value & 1U) {
			*mock_register(mock, PSS_REG_RESULT_STATUS) = 0;
			++*mock_register(mock, PSS_REG_RESULT_CONSUMED);
		}
		break;
	case PSS_REG_TELEMETRY_CONTROL:
		if (value & 1U) {
			++*mock_register(mock, PSS_REG_TELEMETRY_GENERATION);
			*mock_register(mock, PSS_REG_TELEMETRY_STATUS) = 1U;
		}
		break;
	case PSS_REG_INJECTION_DATA:
		if (!(mock->injection_flags & PSS_INJECTION_FIXTURE_VALID) &&
		    mock->injection_count < PSS_INJECTION_SAMPLES)
			mock->injected[mock->injection_count++] = value;
		else
			mock->injection_flags |= PSS_INJECTION_REJECTED;
		break;
	case PSS_REG_INJECTION_CONTROL:
		if (value == 1U) {
			mock->injection_count = 0;
			mock->injection_flags = 0;
			mock->injection_status_reads = 0;
			*mock_register(mock, PSS_REG_INJECTION_LAST_GENERATION) = 0;
		} else if (value == 2U &&
			   mock->injection_count == PSS_INJECTION_SAMPLES &&
			   *mock_register(mock, PSS_REG_INJECTION_GENERATION)) {
			mock->injection_flags =
				PSS_INJECTION_FIXTURE_VALID | PSS_INJECTION_ARM_READY;
		} else if (value == 4U &&
			   (mock->injection_flags & PSS_INJECTION_ARM_READY)) {
			mock->injection_flags =
				PSS_INJECTION_FIXTURE_VALID | PSS_INJECTION_INFLIGHT;
			mock->injection_status_reads = 0;
		} else {
			mock->injection_flags |= PSS_INJECTION_REJECTED;
		}
		break;
	default:
		*mock_register(mock, offset) = value;
		break;
	}
	return 0;
}

static void mock_initialize(struct mock_device *mock)
{
	memset(mock, 0, sizeof(*mock));
	*mock_register(mock, PSS_REG_IDENTIFICATION) = PSS_IDENTIFICATION;
	*mock_register(mock, PSS_REG_VERSION) = PSS_VERSION;
	*mock_register(mock, PSS_REG_RATE_MSPS) = PSS_RATE_MSPS;
	*mock_register(mock, PSS_REG_GEOMETRY) = PSS_GEOMETRY;
	*mock_register(mock, PSS_REG_CAPABILITIES) = PSS_CAPABILITIES;
	mock->current_index = UINT64_C(0x0000000200010000);
	mock_status(mock);
}

static int load_packet_file(const char *path, uint32_t words[PSS_RESULT_WORDS])
{
	FILE *input = fopen(path, "r");
	unsigned int index;

	if (!input) {
		fprintf(stderr, "cannot open %s: %s\n", path, strerror(errno));
		return -1;
	}
	for (index = 0; index < PSS_RESULT_WORDS; ++index) {
		unsigned int value;
		if (fscanf(input, "%x", &value) != 1) {
			fprintf(stderr, "%s: missing packet word %u\n", path, index);
			fclose(input);
			return -1;
		}
		words[index] = value;
	}
	fclose(input);
	return 0;
}

#define CHECK(condition, message) \
	do { \
		if (!(condition)) { \
			fprintf(stderr, "SELFTEST_FAIL: %s\n", (message)); \
			return EXIT_FAILURE; \
		} \
	} while (0)

struct batch_observer {
	uint32_t request_id_base;
	uint32_t received;
	uint64_t first_center;
	uint64_t period_samples;
};

static int observe_batch_packet(void *context,
	const struct pss_batch_packet *packet)
{
	struct batch_observer *observer = context;
	uint64_t expected_center = observer->first_center +
		(uint64_t)observer->received * observer->period_samples;

	if (packet->ordinal != observer->received ||
	    packet->packet.request_id !=
		observer->request_id_base + observer->received ||
	    packet->packet.center_index != expected_center ||
	    packet->packet.center_timestamp != expected_center ||
	    packet->submit_lead_samples < PSS_MINIMUM_HOST_LEAD)
		return -1;
	++observer->received;
	return 0;
}

int main(int argc, char **argv)
{
	struct mock_device mock;
	struct pss_io io;
	struct pss_info info;
	struct pss_ci16 coefficients[PSS_COEFFICIENT_COUNT];
	struct pss_ci16 injection_samples[PSS_INJECTION_SAMPLES];
	struct pss_injection_status injection;
	struct pss_track_request request = {
		.request_id = UINT32_C(0x12345678),
		.lead_samples = PSS_DEFAULT_LEAD_SAMPLES,
		.timeout_ms = 100U,
	};
	struct pss_track_result result;
	struct pss_batch_request batch_request = {
		.request_id_base = UINT32_C(0x20000000),
		.count = 12U,
		.period_samples = 20000U,
		.lead_samples = PSS_DEFAULT_LEAD_SAMPLES,
		.queue_target = PSS_DEFAULT_QUEUE_TARGET,
		.timeout_ms = 100U,
	};
	struct pss_batch_result batch_result;
	struct batch_observer batch_observer = {
		.request_id_base = UINT32_C(0x20000000),
		.first_center = UINT64_C(0x0000000200010000) +
			PSS_DEFAULT_LEAD_SAMPLES,
		.period_samples = 20000U,
	};
	struct pss_clock_slope slope;
	struct pss_packet fixture_packet;
	uint32_t fixture_words[PSS_RESULT_WORDS];
	uint64_t fixture_timestamp;
	char error[256] = {0};

	if (argc != 4) {
		fprintf(stderr, "usage: %s COEFFICIENTS PACKETS INJECTION\n", argv[0]);
		return EXIT_FAILURE;
	}
	mock_initialize(&mock);
	io.context = &mock;
	io.read32 = mock_read32;
	io.write32 = mock_write32;

	CHECK(pss_require_contract(&io, &info, error, sizeof(error)) == 0,
		error);
	*mock_register(&mock, PSS_REG_VERSION) = UINT32_C(0x00010000);
	CHECK(pss_require_contract(&io, NULL, error, sizeof(error)) < 0,
		"legacy ABI was not rejected");
	*mock_register(&mock, PSS_REG_VERSION) = PSS_VERSION;

	CHECK(pss_read_ci16_file(argv[1], coefficients, error, sizeof(error)) == 0,
		error);
	CHECK(coefficients[0].i == (int16_t)UINT16_C(0x077d) &&
	      coefficients[0].q == (int16_t)UINT16_C(0x0503),
		"coefficient fixture I/Q parsing is wrong");
	CHECK(pss_load_coefficients(&io, coefficients, UINT32_C(0x07120001),
		100U, error, sizeof(error)) == 0, error);
	CHECK(mock.loaded[0] == UINT32_C(0x0503077d),
		"AXI coefficient I/Q packing is wrong");
	CHECK(*mock_register(&mock, PSS_REG_ACTIVE_COEFFICIENT_GENERATION) ==
	      UINT32_C(0x07120001), "coefficient generation did not commit");

	CHECK(pss_read_injection_file(argv[3], injection_samples,
		error, sizeof(error)) == 0, error);
	CHECK(pss_load_injection_fixture(&io, injection_samples,
		UINT32_C(0x1a120001), 100U, &injection,
		error, sizeof(error)) == 0, error);
	CHECK(mock.injected[0] ==
	      ((uint32_t)(uint16_t)injection_samples[0].i |
	       (uint32_t)(uint16_t)injection_samples[0].q << 16),
		"injection I/Q packing is wrong");
	CHECK(pss_arm_injection(&io,
		mock.current_index + PSS_DEFAULT_LEAD_SAMPLES,
		100U, &injection, error, sizeof(error)) == 0, error);
	CHECK(pss_wait_injection_complete(&io, UINT32_C(0x1a120001),
		100U, &injection, error, sizeof(error)) == 0, error);
	CHECK((injection.raw_status & PSS_INJECTION_COMPLETED) &&
	      !(injection.raw_status &
	        (PSS_INJECTION_REJECTED | PSS_INJECTION_MISMATCH |
	         PSS_INJECTION_INFLIGHT)),
		"injection terminal status is not clean");
	CHECK(pss_arm_injection(&io,
		UINT64_MAX - (PSS_INJECTION_SAMPLES - 2U),
		100U, &injection, error, sizeof(error)) < 0,
		"overflowing injection window was accepted");
	CHECK(strstr(error, "overflows the accepted-sample index") != NULL,
		"overflowing injection window returned the wrong error");

	CHECK(pss_track_one(&io, &request, &result, error, sizeof(error)) == 0,
		error);
	CHECK(result.packet.lag == -7, "mock winner lag is wrong");
	CHECK(result.scheduled_center ==
	      mock.current_index + PSS_DEFAULT_LEAD_SAMPLES,
		"default scheduling lead is wrong");
	CHECK(!(*mock_register(&mock, PSS_REG_RESULT_STATUS) & 1U),
		"validated result was not released");
	CHECK(result.after.result_consumed - result.before.result_consumed == 1U,
		"result-consumed gate is wrong");

	CHECK(pss_track_batch(&io, &batch_request, observe_batch_packet,
		&batch_observer, &batch_result, error, sizeof(error)) == 0, error);
	CHECK(batch_observer.received == batch_request.count,
		"batch callback did not receive every result");
	CHECK(batch_result.submitted == batch_request.count &&
	      batch_result.completed == batch_request.count,
		"batch submit/completion totals are wrong");
	CHECK(batch_result.maximum_inflight == PSS_COMMAND_FIFO_USABLE,
		"batch did not fill the seven-entry command FIFO");
	CHECK(batch_result.minimum_queue_room == 1U,
		"batch did not observe the final writable FIFO slot");
	CHECK(batch_result.minimum_submit_lead_samples >= PSS_MINIMUM_HOST_LEAD,
		"batch violated the minimum host lead");
	CHECK(batch_result.after.result_consumed -
	      batch_result.before.result_consumed == batch_request.count,
		"batch result-consumed aggregate gate is wrong");
	CHECK(!mock.candidate_count &&
	      !(*mock_register(&mock, PSS_REG_RESULT_STATUS) & 1U),
		"batch did not drain the mock command/result queues");

	batch_request.period_samples = PSS_INJECTION_SAMPLES - 1U;
	CHECK(pss_track_batch(&io, &batch_request, NULL, NULL, &batch_result,
		error, sizeof(error)) < 0,
		"batch accepted overlapping candidate geometry");
	batch_request.period_samples = 20000U;
	batch_request.request_id_base = UINT32_MAX - 1U;
	CHECK(pss_track_batch(&io, &batch_request, NULL, NULL, &batch_result,
		error, sizeof(error)) < 0,
		"batch accepted overflowing request IDs");
	batch_request.request_id_base = UINT32_C(0x30000000);
	*mock_register(&mock, PSS_REG_QUEUE_OVERRUN) = UINT32_MAX;
	CHECK(pss_track_batch(&io, &batch_request, NULL, NULL, &batch_result,
		error, sizeof(error)) < 0,
		"batch accepted a saturated error counter");
	CHECK(strstr(error, "lacks batch headroom") != NULL,
		"saturated batch counter returned the wrong error");
	*mock_register(&mock, PSS_REG_QUEUE_OVERRUN) = 0;

	CHECK(pss_calculate_clock_slope(100U, UINT64_C(15000100),
		UINT64_C(1000000000), UINT64_C(2000000000), 15000000U,
		100.0, &slope, error, sizeof(error)) == 0,
		"exact 15 MS/s clock slope was rejected");
	CHECK(slope.sample_delta == UINT64_C(15000000) &&
	      slope.elapsed_ns == UINT64_C(1000000000) &&
	      slope.error_ppm == 0.0,
		"clock-slope calculation is wrong");
	CHECK(pss_calculate_clock_slope(100U, UINT64_C(14900100),
		UINT64_C(1000000000), UINT64_C(2000000000), 15000000U,
		1000.0, &slope, error, sizeof(error)) < 0,
		"out-of-tolerance clock slope was accepted");

	CHECK(load_packet_file(argv[2], fixture_words) == 0,
		"could not load retained replay packet");
	fixture_timestamp = (uint64_t)fixture_words[5] |
		(uint64_t)fixture_words[6] << 32;
	CHECK(pss_validate_packet(fixture_words, UINT32_C(0x71200000), 128U,
		fixture_timestamp, UINT32_C(0x07120001), &fixture_packet,
		error, sizeof(error)) == 0, error);
	CHECK(fixture_packet.lag == -17,
		"retained replay packet did not decode to frozen lag -17");

	mock_initialize(&mock);
	*mock_register(&mock, PSS_REG_ACTIVE_COEFFICIENT_GENERATION) =
		UINT32_C(0x07120001);
	mock.inject_rejected = true;
	CHECK(pss_track_one(&io, &request, &result, error, sizeof(error)) < 0,
		"unexpected rejected-counter delta was accepted");
	CHECK(*mock_register(&mock, PSS_REG_RESULT_STATUS) & 1U,
		"failed-gate result should remain retained");

	printf("STARLINK_PSSCTL_SELFTEST_PASS contract=1.2 taps=66 lags=61 "
	       "coefficient_iq_swap=1 atomic_telemetry=1 packet_fixture=1 "
	       "injection_samples=130 injection_iq_swap=1 "
	       "failure_retains_result=1 batch_fifo=7 batch_refill=1 "
	       "clock_slope=1\n");
	return EXIT_SUCCESS;
}
