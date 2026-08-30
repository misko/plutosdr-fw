#include "spf_gain_timeline.h"

#include <limits.h>

static bool pair_valid(const spf_gain_timeline_pair_t *pair)
{
	return pair->rx1_gain_index <= UINT8_C(0x7F) &&
		pair->rx1_gain_index == pair->rx2_gain_index;
}

static spf_gain_timeline_result_t apply_event(
	spf_gain_timeline_state_t *state,
	const spf_gain_event_v7_t *event,
	bool *rx1_changed,
	bool *rx2_changed)
{
	const spf_gain_timeline_pair_t next_gain = {
		.rx1_gain_index = event->rx1_gain_index,
		.rx2_gain_index = event->rx2_gain_index,
	};

	if (!spf_gain_event_v7_flags_valid(event->flags))
		return SPF_GAIN_TIMELINE_UNKNOWN_EVENT_FLAGS;
	if (!spf_gain_event_v7_pair_valid(event))
		return SPF_GAIN_TIMELINE_INVALID_GAIN_PAIR;
	if (state->event_sequence_valid &&
		event->event_sequence != state->next_event_sequence)
		return SPF_GAIN_TIMELINE_EVENT_SEQUENCE_GAP;
	if (state->sample_sequence_valid &&
		event->sample_sequence < state->last_event_sample_sequence)
		return SPF_GAIN_TIMELINE_SAMPLE_REGRESSION;
	if (state->transition_count == UINT64_MAX)
		return SPF_GAIN_TIMELINE_RANGE_ERROR;

	*rx1_changed = next_gain.rx1_gain_index != state->gain.rx1_gain_index;
	*rx2_changed = next_gain.rx2_gain_index != state->gain.rx2_gain_index;
	state->gain = next_gain;
	state->next_event_sequence = event->event_sequence + UINT32_C(1);
	state->event_sequence_valid = true;
	state->last_event_sample_sequence = event->sample_sequence;
	state->sample_sequence_valid = true;
	state->transition_count++;
	return SPF_GAIN_TIMELINE_OK;
}

spf_gain_timeline_result_t spf_gain_timeline_resolve(
	const spf_gain_timeline_state_t *seed,
	uint64_t frame_start,
	uint32_t samples,
	const spf_gain_event_v7_t *events,
	size_t event_count,
	spf_gain_timeline_frame_t *frame,
	spf_gain_timeline_state_t *next_state)
{
	spf_gain_timeline_state_t candidate_state;
	spf_gain_timeline_frame_t candidate_frame;
	uint64_t frame_end;
	size_t index = 0;

	if (!seed || !frame || !next_state || (!events && event_count != 0) ||
		samples == 0)
		return SPF_GAIN_TIMELINE_INVALID_ARGUMENT;
	if (!pair_valid(&seed->gain))
		return SPF_GAIN_TIMELINE_INVALID_GAIN_PAIR;
	frame_end = frame_start + samples;
	if (frame_end < frame_start)
		return SPF_GAIN_TIMELINE_RANGE_ERROR;

	candidate_state = *seed;
	candidate_frame = (spf_gain_timeline_frame_t){
		.rx1_first_change_sample = SPF_FIRST_CHANGE_UNAVAILABLE,
		.rx2_first_change_sample = SPF_FIRST_CHANGE_UNAVAILABLE,
	};

	/* Consume historical events before choosing the first-sample state. */
	while (index < event_count && events[index].sample_sequence < frame_start)
	{
		bool rx1_changed;
		bool rx2_changed;
		spf_gain_timeline_result_t result = apply_event(
			&candidate_state, &events[index], &rx1_changed, &rx2_changed);
		(void)rx1_changed;
		(void)rx2_changed;
		if (result != SPF_GAIN_TIMELINE_OK)
			return result;
		index++;
	}

	candidate_frame.gain_start = candidate_state.gain;
	candidate_frame.transition_count_start = candidate_state.transition_count;
	candidate_frame.frame_event_offset = index;

	while (index < event_count && events[index].sample_sequence < frame_end)
	{
		bool rx1_changed;
		bool rx2_changed;
		spf_gain_timeline_result_t result = apply_event(
			&candidate_state, &events[index], &rx1_changed, &rx2_changed);
		if (result != SPF_GAIN_TIMELINE_OK)
			return result;

		const uint32_t offset =
			(uint32_t)(events[index].sample_sequence - frame_start);
		if (rx1_changed && candidate_frame.rx1_first_change_sample ==
				SPF_FIRST_CHANGE_UNAVAILABLE)
			candidate_frame.rx1_first_change_sample = offset;
		if (rx2_changed && candidate_frame.rx2_first_change_sample ==
				SPF_FIRST_CHANGE_UNAVAILABLE)
			candidate_frame.rx2_first_change_sample = offset;
		/* A boundary event is the state of the first captured sample. */
		if (events[index].sample_sequence == frame_start)
		{
			candidate_frame.gain_start = candidate_state.gain;
		}
		index++;
	}

	candidate_frame.gain_end = candidate_state.gain;
	candidate_frame.transition_count_end = candidate_state.transition_count;
	candidate_frame.frame_event_count =
		index - candidate_frame.frame_event_offset;
	candidate_frame.consumed_event_count = index;
	*frame = candidate_frame;
	*next_state = candidate_state;
	return SPF_GAIN_TIMELINE_OK;
}
