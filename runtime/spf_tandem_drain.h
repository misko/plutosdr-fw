/*
 * spf_tandem_drain.h
 *
 * The producer that has never existed: draining the FPGA event FIFO into the
 * per-frame array that spf_radio_frame_v3_build() already knows how to ship.
 *
 * Two rules make this more than a memcpy.
 *
 * Epoch filtering. A record carries the ownership epoch it was generated
 * under. When a session is torn down and a new one arms, the epoch increments
 * and never repeats, so records still sitting in the FIFO from the previous
 * owner are recognisable and are dropped here -- they describe a gain series
 * that has nothing to do with the frame being built. This is why the epoch is
 * not on the wire: it does its whole job at the drain.
 *
 * Frame attribution. An event belongs to the frame whose sample range contains
 * its counter. The FIFO is drained on a completely unrelated schedule, so a
 * drain routinely returns events belonging to the frame after this one; those
 * are carried forward rather than misattributed or dropped.
 */

#ifndef SPF_TANDEM_DRAIN_H
#define SPF_TANDEM_DRAIN_H

#include "spf_tandem_event.h"

#define SPF_TANDEM_DRAIN_CAPACITY 64u

typedef struct {
	/* the epoch this drain accepts; records under any other are stale */
	uint8_t  epoch;
	bool     armed;

	/* records seen but belonging to a later frame */
	spf_tandem_record_t carry[SPF_TANDEM_DRAIN_CAPACITY];
	unsigned carry_count;

	/* the index in force at the start of the next frame, carried across
	 * frames so a quiet frame still knows what gain it was at */
	uint8_t  current_index;

	/* cumulative, reported per frame and then cleared */
	uint32_t dropped_stale;
	uint32_t dropped_overflow;
	uint32_t last_sequence;
} spf_tandem_drain_t;

typedef struct {
	uint16_t count;             /* events written to the caller's array */
	uint32_t overflow_count;    /* what the frame must report */
	uint8_t  index_at_start;    /* the index in force when the frame began */
	bool     events_valid;      /* what gain_events_valid must be set to */
	uint32_t first_sequence;    /* 0 when the frame has no events */
} spf_tandem_drain_result_t;

void spf_tandem_drain_init(spf_tandem_drain_t *d, uint8_t initial_index);

/* the producer arms: adopt the epoch and start advertising */
void spf_tandem_drain_arm(spf_tandem_drain_t *d, uint8_t epoch,
                          uint8_t current_index);
void spf_tandem_drain_disarm(spf_tandem_drain_t *d);

/*
 * Take one frame's worth. `records`/`record_count` is what a FIFO read
 * returned, in FIFO order; `hw_overflow` is the block's own dropped-record
 * count since the last call.
 *
 * Writes at most `capacity` wire records to `out`, which is the frame's
 * negotiated gain_event_capacity. Anything beyond it is an overflow the frame
 * must report -- not a silent truncation.
 */
void spf_tandem_drain_frame(spf_tandem_drain_t *d,
                            const spf_tandem_record_t *records,
                            unsigned record_count,
                            uint32_t hw_overflow,
                            uint64_t frame_start, uint32_t frame_samples,
                            uint8_t *out, uint16_t capacity,
                            spf_tandem_drain_result_t *result);

#endif /* SPF_TANDEM_DRAIN_H */
