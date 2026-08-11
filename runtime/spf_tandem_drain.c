/* spf_tandem_drain.c -- see the header for the epoch and attribution rules. */

#include "spf_tandem_drain.h"

#include <string.h>

void spf_tandem_drain_init(spf_tandem_drain_t *d, uint8_t initial_index)
{
	if (d == NULL)
		return;
	memset(d, 0, sizeof(*d));
	d->current_index = initial_index;
}

void spf_tandem_drain_arm(spf_tandem_drain_t *d, uint8_t epoch,
                          uint8_t current_index)
{
	if (d == NULL)
		return;
	/*
	 * Arming discards the carry. Whatever was held over belonged to the
	 * previous owner's epoch, and holding it across a re-arm is exactly the
	 * misattribution the epoch exists to prevent.
	 */
	d->carry_count = 0;
	d->epoch = epoch;
	d->armed = true;
	d->current_index = current_index;
	d->last_sequence = 0;
	d->dropped_stale = 0;
	d->dropped_overflow = 0;
}

void spf_tandem_drain_disarm(spf_tandem_drain_t *d)
{
	if (d == NULL)
		return;
	d->armed = false;
	d->carry_count = 0;
}

static bool in_frame(uint64_t counter, uint64_t start, uint32_t samples)
{
	return counter >= start && counter < start + samples;
}

void spf_tandem_drain_frame(spf_tandem_drain_t *d,
                            const spf_tandem_record_t *records,
                            unsigned record_count,
                            uint32_t hw_overflow,
                            uint64_t frame_start, uint32_t frame_samples,
                            uint8_t *out, uint16_t capacity,
                            spf_tandem_drain_result_t *result)
{
	spf_tandem_record_t next_carry[SPF_TANDEM_DRAIN_CAPACITY];
	unsigned next_carry_count = 0;
	unsigned i, total;
	uint16_t written = 0;
	uint32_t overflow;
	uint32_t first_sequence = 0;

	if (d == NULL || result == NULL)
		return;
	memset(result, 0, sizeof(*result));
	result->index_at_start = d->current_index;

	if (!d->armed) {
		/* Not armed: report nothing known. The frame builder will leave
		 * SPF_META_FPGA_EVENTS_VALID clear, which is the honest answer. */
		result->events_valid = false;
		return;
	}
	result->events_valid = true;
	overflow = hw_overflow;

	/* the carry first, then the fresh read: FIFO order across both */
	total = d->carry_count + record_count;
	for (i = 0; i < total; i++) {
		const spf_tandem_record_t *r = (i < d->carry_count)
			? &d->carry[i]
			: &records[i - d->carry_count];

		if (r->epoch != d->epoch) {
			/* a previous owner's record; it describes a different session */
			d->dropped_stale++;
			continue;
		}
		if (r->sample_counter >= frame_start + frame_samples) {
			/* belongs to a later frame -- hold it rather than lose it */
			if (next_carry_count < SPF_TANDEM_DRAIN_CAPACITY)
				next_carry[next_carry_count++] = *r;
			else
				overflow++;
			continue;
		}
		/*
		 * Anything at or before the frame start still matters: it sets the
		 * index the frame opens at. It is applied but not shipped, because a
		 * consumer reconstructing from index_at_start already has its effect.
		 */
		if (!in_frame(r->sample_counter, frame_start, frame_samples)) {
			d->current_index = r->gain_index;
			d->last_sequence = r->sequence;
			result->index_at_start = r->gain_index;
			continue;
		}
		if (written >= capacity) {
			/* the frame cannot carry it; say so rather than truncate quietly */
			overflow++;
			d->dropped_overflow++;
			continue;
		}
		if (written == 0)
			first_sequence = r->sequence;
		spf_tandem_event_encode(r, &out[(size_t)written * SPF_GAIN_EVENT_BYTES]);
		written++;
		d->current_index = r->gain_index;
		d->last_sequence = r->sequence;
	}

	memcpy(d->carry, next_carry,
	       (size_t)next_carry_count * sizeof(next_carry[0]));
	d->carry_count = next_carry_count;

	result->count = written;
	result->overflow_count = overflow;
	result->first_sequence = first_sequence;
}
