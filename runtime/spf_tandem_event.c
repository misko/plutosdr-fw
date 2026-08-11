/* spf_tandem_event.c -- see the header for the layout and why the epoch is not
 * on the wire. */

#include "spf_tandem_event.h"

#include <string.h>

static void put_u64(uint8_t *p, uint64_t v)
{ int i; for (i = 0; i < 8; i++) p[i] = (uint8_t)(v >> (8 * i)); }
static void put_u32(uint8_t *p, uint32_t v)
{ int i; for (i = 0; i < 4; i++) p[i] = (uint8_t)(v >> (8 * i)); }
static void put_u16(uint8_t *p, uint16_t v)
{ p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static uint64_t get_u64(const uint8_t *p)
{ uint64_t v = 0; int i; for (i = 7; i >= 0; i--) v = (v << 8) | p[i]; return v; }
static uint32_t get_u32(const uint8_t *p)
{ uint32_t v = 0; int i; for (i = 3; i >= 0; i--) v = (v << 8) | p[i]; return v; }
static uint16_t get_u16(const uint8_t *p)
{ return (uint16_t)(p[0] | ((uint16_t)p[1] << 8)); }

void spf_tandem_event_encode(const spf_tandem_record_t *in, uint8_t out[16])
{
	uint16_t flags;

	if (in == NULL || out == NULL)
		return;
	memset(out, 0, SPF_GAIN_EVENT_BYTES);

	/*
	 * Under tandem both channels move together, always, so both CHANGED bits
	 * are set on every transition. That is not decoration: it is the wire
	 * evidence that tandem was actually in control, and a consumer can reject
	 * a frame where only one is set.
	 */
	flags = (uint16_t)(SPF_GAIN_EVENT_RX1_CHANGED | SPF_GAIN_EVENT_RX2_CHANGED);

	put_u64(&out[0], in->sample_counter);
	put_u16(&out[8], flags);
	out[10] = in->gain_index;
	out[11] = (uint8_t)((in->reason & 0x0Fu) | ((in->direction & 0x03u) << 4));
	put_u32(&out[12], in->sequence);
}

void spf_tandem_event_decode(const uint8_t in[16], spf_tandem_event_t *out)
{
	if (in == NULL || out == NULL)
		return;
	out->sample_sequence = get_u64(&in[0]);
	out->flags           = get_u16(&in[8]);
	out->gain_index      = in[10];
	out->reason          = (uint8_t)(in[11] & 0x0Fu);
	out->direction       = (uint8_t)((in[11] >> 4) & 0x03u);
	out->event_sequence  = get_u32(&in[12]);
}

spf_tandem_recon_rc_t spf_tandem_reconstruct(
	const spf_tandem_frame_t *frame,
	const uint8_t *wire_events, size_t event_count,
	int32_t effect_offset,
	uint8_t *series, size_t series_len)
{
	size_t i;
	uint64_t prev_counter = 0;
	uint32_t prev_seq = 0;
	bool have_prev = false;
	uint8_t current;

	if (frame == NULL || series == NULL || series_len < frame->samples)
		return SPF_TANDEM_RECON_EINVAL;
	if (event_count != 0 && wire_events == NULL)
		return SPF_TANDEM_RECON_EINVAL;

	/*
	 * A frame with no events is NOT the same as a frame the producer was not
	 * running for. The first is "gain held constant", which is a complete and
	 * useful answer; the second is "unknown". Conflating them is precisely the
	 * defect in the shipped builder, which derives its validity flag from a
	 * non-zero count.
	 */
	if (!frame->events_valid)
		return SPF_TANDEM_RECON_NOT_ADVERTISED;

	/* Overflow means the producer dropped transitions. The series after that
	 * point cannot be reconstructed, and a plausible-but-wrong one is worse
	 * than an annotated gap, so refuse rather than interpolate. */
	if (frame->overflow_count != 0)
		return SPF_TANDEM_RECON_OVERFLOW;

	current = frame->index_at_frame_start;
	for (i = 0; i < frame->samples; i++)
		series[i] = current;

	for (i = 0; i < event_count; i++) {
		spf_tandem_event_t e;
		int64_t rel;
		size_t start;

		spf_tandem_event_decode(&wire_events[i * SPF_GAIN_EVENT_BYTES], &e);

		if (have_prev) {
			if (e.sample_sequence < prev_counter)
				return SPF_TANDEM_RECON_OUT_OF_ORDER;
			/* serial-number comparison, so a wrap is ordered correctly */
			if ((int32_t)(e.event_sequence - prev_seq) <= 0)
				return SPF_TANDEM_RECON_OUT_OF_ORDER;
			if (frame->expect_first_sequence != 0 &&
			    e.event_sequence != prev_seq + 1u)
				return SPF_TANDEM_RECON_SEQUENCE_GAP;
		} else if (frame->expect_first_sequence != 0 &&
		           e.event_sequence != frame->expect_first_sequence) {
			return SPF_TANDEM_RECON_SEQUENCE_GAP;
		}
		prev_counter = e.sample_sequence;
		prev_seq = e.event_sequence;
		have_prev = true;

		/* The recorded counter is the decision; the change appears later. */
		rel = (int64_t)e.sample_sequence + effect_offset - (int64_t)frame->frame_start;
		if (rel < 0)
			rel = 0;                      /* landed before this frame started */
		if (rel >= (int64_t)frame->samples)
			continue;                     /* lands in the next frame */
		for (start = (size_t)rel; start < frame->samples; start++)
			series[start] = e.gain_index;
	}
	return SPF_TANDEM_RECON_OK;
}

const char *spf_tandem_recon_rc_name(spf_tandem_recon_rc_t rc)
{
	switch (rc) {
	case SPF_TANDEM_RECON_OK:             return "ok";
	case SPF_TANDEM_RECON_OVERFLOW:       return "overflow";
	case SPF_TANDEM_RECON_SEQUENCE_GAP:   return "sequence-gap";
	case SPF_TANDEM_RECON_OUT_OF_ORDER:   return "out-of-order";
	case SPF_TANDEM_RECON_NOT_ADVERTISED: return "not-advertised";
	default:                              return "invalid";
	}
}
