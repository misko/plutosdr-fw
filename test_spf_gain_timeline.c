#include "spf_gain_timeline.h"

#include <assert.h>
#include <limits.h>
#include <string.h>

static spf_gain_timeline_state_t seed(uint8_t gain, uint32_t next_sequence)
{
	return (spf_gain_timeline_state_t){
		.gain = {.rx1_gain_index = gain, .rx2_gain_index = gain},
		.next_event_sequence = next_sequence,
		.transition_count = 10,
		.event_sequence_valid = true,
	};
}

static spf_gain_event_v7_t event(
	uint64_t sample, uint32_t sequence, uint8_t gain)
{
	return (spf_gain_event_v7_t){
		.sample_sequence = sample,
		.event_sequence = sequence,
		.flags = UINT16_C(0x13),
		.rx1_gain_index = gain,
		.rx2_gain_index = gain,
	};
}

static void assert_failure_is_transactional(
	spf_gain_timeline_result_t expected,
	const spf_gain_timeline_state_t *input,
	uint64_t frame_start,
	uint32_t samples,
	const spf_gain_event_v7_t *events,
	size_t count)
{
	spf_gain_timeline_frame_t frame;
	spf_gain_timeline_state_t next;
	spf_gain_timeline_frame_t frame_before;
	spf_gain_timeline_state_t next_before;

	memset(&frame, 0xA5, sizeof(frame));
	memset(&next, 0x5A, sizeof(next));
	frame_before = frame;
	next_before = next;
	assert(spf_gain_timeline_resolve(input, frame_start, samples,
		events, count, &frame, &next) == expected);
	assert(memcmp(&frame, &frame_before, sizeof(frame)) == 0);
	assert(memcmp(&next, &next_before, sizeof(next)) == 0);
}

static void test_hold(void)
{
	spf_gain_timeline_state_t state = seed(40, 7);
	spf_gain_timeline_frame_t frame;

	assert(spf_gain_timeline_resolve(&state, 100, 50, NULL, 0,
		&frame, &state) == SPF_GAIN_TIMELINE_OK);
	assert(frame.gain_start.rx1_gain_index == 40);
	assert(frame.gain_end.rx2_gain_index == 40);
	assert(frame.rx1_first_change_sample == SPF_FIRST_CHANGE_UNAVAILABLE);
	assert(frame.rx2_first_change_sample == SPF_FIRST_CHANGE_UNAVAILABLE);
	assert(frame.frame_event_count == 0);
	assert(frame.consumed_event_count == 0);
	assert(state.transition_count == 10);
}

static void test_boundaries_and_history(void)
{
	spf_gain_timeline_state_t state = seed(40, 7);
	spf_gain_event_v7_t events[] = {
		event(90, 7, 41),       /* pre-frame: opening history */
		event(100, 8, 42),      /* first captured sample */
		event(100, 9, 43),      /* same-sample sequence order */
		event(125, 10, 44),
		event(150, 11, 45),     /* frame_end: deferred */
		event(175, 12, 46),
	};
	spf_gain_timeline_frame_t frame;
	spf_gain_timeline_state_t next;

	assert(spf_gain_timeline_resolve(&state, 100, 50, events,
		sizeof(events) / sizeof(events[0]), &frame, &next) ==
		SPF_GAIN_TIMELINE_OK);
	assert(frame.gain_start.rx1_gain_index == 43);
	assert(frame.gain_end.rx1_gain_index == 44);
	assert(frame.rx1_first_change_sample == 0);
	assert(frame.rx2_first_change_sample == 0);
	assert(frame.frame_event_offset == 1);
	assert(frame.frame_event_count == 3);
	assert(frame.consumed_event_count == 4);
	assert(frame.transition_count_start == 11);
	assert(frame.transition_count_end == 14);
	assert(frame.transition_count_end - frame.transition_count_start ==
		frame.frame_event_count);
	assert(next.gain.rx1_gain_index == 44);
	assert(next.next_event_sequence == 11);
	assert(next.last_event_sample_sequence == 125);

	assert(spf_gain_timeline_resolve(&next, 150, 50,
		&events[frame.consumed_event_count],
		(sizeof(events) / sizeof(events[0])) - frame.consumed_event_count,
		&frame, &next) == SPF_GAIN_TIMELINE_OK);
	assert(frame.gain_start.rx1_gain_index == 45);
	assert(frame.gain_end.rx1_gain_index == 46);
	assert(frame.frame_event_count == 2);
	assert(next.next_event_sequence == 13);
}

static void test_event_sequence_wrap(void)
{
	spf_gain_timeline_state_t state = seed(10, UINT32_MAX);
	spf_gain_event_v7_t events[] = {
		event(10, UINT32_MAX, 11),
		event(11, 0, 12),
	};
	spf_gain_timeline_frame_t frame;

	assert(spf_gain_timeline_resolve(&state, 10, 10, events, 2,
		&frame, &state) == SPF_GAIN_TIMELINE_OK);
	assert(state.next_event_sequence == 1);
	assert(state.transition_count == 12);
}

static void test_failures(void)
{
	spf_gain_timeline_state_t state = seed(20, 3);
	spf_gain_event_v7_t events[2] = {
		event(100, 4, 21),
		event(101, 5, 22),
	};

	assert_failure_is_transactional(SPF_GAIN_TIMELINE_EVENT_SEQUENCE_GAP,
		&state, 100, 10, events, 2);

	events[0] = event(100, 3, 21);
	events[1] = event(99, 4, 22);
	assert_failure_is_transactional(SPF_GAIN_TIMELINE_SAMPLE_REGRESSION,
		&state, 90, 20, events, 2);

	events[0] = event(100, 3, 21);
	events[0].rx2_gain_index = 22;
	assert_failure_is_transactional(SPF_GAIN_TIMELINE_INVALID_GAIN_PAIR,
		&state, 100, 10, events, 1);

	events[0] = event(100, 3, 21);
	events[0].flags |= UINT16_C(0x8000);
	assert_failure_is_transactional(SPF_GAIN_TIMELINE_UNKNOWN_EVENT_FLAGS,
		&state, 100, 10, events, 1);
	events[0] = event(100, 3, 21);
	events[0].flags = UINT16_C(0x03);
	assert_failure_is_transactional(SPF_GAIN_TIMELINE_UNKNOWN_EVENT_FLAGS,
		&state, 100, 10, events, 1);
	events[0] = event(100, 3, 21);
	events[0].flags = UINT16_C(0x17);
	assert_failure_is_transactional(SPF_GAIN_TIMELINE_UNKNOWN_EVENT_FLAGS,
		&state, 100, 10, events, 1);

	assert_failure_is_transactional(SPF_GAIN_TIMELINE_RANGE_ERROR,
		&state, UINT64_MAX - 4, 8, NULL, 0);
	assert_failure_is_transactional(SPF_GAIN_TIMELINE_INVALID_ARGUMENT,
		&state, 100, 0, NULL, 0);

	state.gain.rx2_gain_index++;
	assert_failure_is_transactional(SPF_GAIN_TIMELINE_INVALID_GAIN_PAIR,
		&state, 100, 10, NULL, 0);
}

int main(void)
{
	test_hold();
	test_boundaries_and_history();
	test_event_sequence_wrap();
	test_failures();
	return 0;
}
