#ifndef SPF_GAIN_TIMELINE_H
#define SPF_GAIN_TIMELINE_H

#include "spf_gain_metadata.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/*
 * Portable post-change tandem event.  This is deliberately independent of
 * the Linux tandem UAPI so the same reducer can be used by iiOD and direct
 * capture providers.
 */
#pragma pack(push, 1)
typedef struct
{
	uint64_t sample_sequence;
	uint32_t event_sequence;
	uint16_t flags;
	uint8_t rx1_gain_index;
	uint8_t rx2_gain_index;
} spf_gain_event_v7_t;
#pragma pack(pop)

#define SPF_GAIN_EVENT_V7_KNOWN_FLAGS UINT16_C(0x003F)

_Static_assert(sizeof(spf_gain_event_v7_t) == SPF_GAIN_EVENT_BYTES,
	"SPF v7 gain event must be 16 bytes");
_Static_assert(offsetof(spf_gain_event_v7_t, event_sequence) == 8,
	"unexpected SPF v7 event-sequence offset");
_Static_assert(offsetof(spf_gain_event_v7_t, flags) == 12,
	"unexpected SPF v7 event-flags offset");
_Static_assert(offsetof(spf_gain_event_v7_t, rx1_gain_index) == 14,
	"unexpected SPF v7 event-gain offset");

static inline bool spf_gain_event_v7_flags_valid(uint16_t flags)
{
	const uint16_t direction = (flags >> 4) & UINT16_C(0x3);
	return (flags & ~SPF_GAIN_EVENT_V7_KNOWN_FLAGS) == 0 &&
		direction >= UINT16_C(1) && direction <= UINT16_C(2) &&
		(flags & UINT16_C(0xF)) <= UINT16_C(6);
}

static inline bool spf_gain_event_v7_pair_valid(
	const spf_gain_event_v7_t *event)
{
	return event && event->rx1_gain_index <= UINT8_C(0x7F) &&
		event->rx1_gain_index == event->rx2_gain_index;
}

typedef struct
{
	uint8_t rx1_gain_index;
	uint8_t rx2_gain_index;
} spf_gain_timeline_pair_t;

/*
 * Committed state immediately after the last consumed event.  A session may
 * begin with no event-sequence/sample-sequence history, but its gain pair is
 * always authoritative (for example, the tandem ACQUIRE status pair).
 */
typedef struct
{
	spf_gain_timeline_pair_t gain;
	uint32_t next_event_sequence;
	uint64_t transition_count;
	uint64_t last_event_sample_sequence;
	bool event_sequence_valid;
	bool sample_sequence_valid;
} spf_gain_timeline_state_t;

typedef struct
{
	spf_gain_timeline_pair_t gain_start;
	spf_gain_timeline_pair_t gain_end;
	uint64_t transition_count_start;
	uint64_t transition_count_end;
	uint32_t rx1_first_change_sample;
	uint32_t rx2_first_change_sample;
	/* Events before frame_event_offset advance the opening state. */
	size_t frame_event_offset;
	size_t frame_event_count;
	/* Events at frame_end and later are not consumed. */
	size_t consumed_event_count;
} spf_gain_timeline_frame_t;

typedef enum
{
	SPF_GAIN_TIMELINE_OK = 0,
	SPF_GAIN_TIMELINE_INVALID_ARGUMENT,
	SPF_GAIN_TIMELINE_RANGE_ERROR,
	SPF_GAIN_TIMELINE_EVENT_SEQUENCE_GAP,
	SPF_GAIN_TIMELINE_SAMPLE_REGRESSION,
	SPF_GAIN_TIMELINE_INVALID_GAIN_PAIR,
	SPF_GAIN_TIMELINE_UNKNOWN_EVENT_FLAGS,
} spf_gain_timeline_result_t;

/*
 * Resolve authoritative gains for [frame_start, frame_start + samples).
 *
 * Events are post-change records.  Pre-frame events advance gain_start but
 * are not counted in frame_event_count.  An event exactly at frame_start
 * applies to the first sample and reports first-change offset zero.  An event
 * exactly at frame_end is deferred to the next call.  Equal sample sequences
 * are valid and are applied in event-sequence order.
 *
 * The operation is transactional: frame and next_state are not modified on
 * failure.  seed and next_state may point to the same object.
 */
spf_gain_timeline_result_t spf_gain_timeline_resolve(
	const spf_gain_timeline_state_t *seed,
	uint64_t frame_start,
	uint32_t samples,
	const spf_gain_event_v7_t *events,
	size_t event_count,
	spf_gain_timeline_frame_t *frame,
	spf_gain_timeline_state_t *next_state);

#endif
