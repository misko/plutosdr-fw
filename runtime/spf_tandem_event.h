/*
 * spf_tandem_event.h
 *
 * The exact FPGA gain-event product: encoding a controller record into the
 * existing protocol-v3 wire record, and reconstructing a per-sample gain series
 * from a frame's worth of them.
 *
 * The wire record is NOT new. `spf_gain_event_v3_t` has been in the ABI since
 * the RC14 gadget -- 16 bytes, with capacity, count, byte-size and an overflow
 * counter already negotiated in the v3 prefix, and `spf_radio_frame_v3_build()`
 * already copying the array. What has never existed is a producer:
 * `thread_read.c` passes `gain_events = NULL, gain_event_count = 0`. This fills
 * that slot rather than inventing one.
 *
 * Layout, per TANDEM_AGC_V1_DESIGN.md §7.4. The six reserved bytes are exactly
 * consumed, which is why the ownership epoch is deliberately NOT on the wire:
 * stale-epoch events are dropped at drain and never reach a frame, so a
 * per-event epoch would be redundant, and there is no room for it.
 *
 *   offset 0..7   sample_sequence      u64   the counter at the DECISION
 *   offset 8..9   flags                u16   RX1/RX2 changed, locked
 *   offset 10     gain_index           u8    common index AFTER the transition
 *   offset 11     reason_direction     u8    reason in [3:0], direction in [5:4]
 *   offset 12..15 event_sequence       u32   monotonic within an epoch
 */

#ifndef SPF_TANDEM_EVENT_H
#define SPF_TANDEM_EVENT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* from the shipped spf_gain_metadata.h; repeated here so this unit builds and
 * tests standalone, and asserted against the real header at integration */
#define SPF_GAIN_EVENT_RX1_CHANGED (UINT16_C(1) << 0)
#define SPF_GAIN_EVENT_RX2_CHANGED (UINT16_C(1) << 1)
#define SPF_GAIN_EVENT_RX1_LOCKED  (UINT16_C(1) << 2)
#define SPF_GAIN_EVENT_RX2_LOCKED  (UINT16_C(1) << 3)
#define SPF_GAIN_EVENT_BYTES       16u

typedef enum {
	SPF_TANDEM_REASON_LG_LMT = 0,
	SPF_TANDEM_REASON_LG_ADC = 1,
	SPF_TANDEM_REASON_SM_INHIBIT = 2,
	SPF_TANDEM_REASON_BOTH_LOW_POWER = 3,
	SPF_TANDEM_REASON_PEER_INHIBIT = 4,
	SPF_TANDEM_REASON_CLAMPED = 5,
	SPF_TANDEM_REASON_INIT = 6,
	SPF_TANDEM_REASON_HOLD = 7,
	SPF_TANDEM_REASON_DISABLED = 8,
} spf_tandem_reason_t;

typedef enum {
	SPF_TANDEM_DIR_NONE = 0,
	SPF_TANDEM_DIR_INCREASE = 1,
	SPF_TANDEM_DIR_DECREASE = 2,
} spf_tandem_dir_t;

/* the controller's 104-bit FIFO record, already epoch-filtered at drain */
typedef struct {
	uint64_t sample_counter;
	uint8_t  gain_index;
	uint8_t  reason;
	uint8_t  direction;
	uint8_t  epoch;
	uint32_t sequence;
} spf_tandem_record_t;

/* decoded view of a wire record */
typedef struct {
	uint64_t sample_sequence;
	uint16_t flags;
	uint8_t  gain_index;
	uint8_t  reason;
	uint8_t  direction;
	uint32_t event_sequence;
} spf_tandem_event_t;

void spf_tandem_event_encode(const spf_tandem_record_t *in, uint8_t out[16]);
void spf_tandem_event_decode(const uint8_t in[16], spf_tandem_event_t *out);

/* Why reconstruction can fail. Every one of these is an explicit metadata
 * fault: the plan is emphatic that a plausible-but-wrong series is worse than
 * an annotated gap. */
typedef enum {
	SPF_TANDEM_RECON_OK = 0,
	SPF_TANDEM_RECON_OVERFLOW,      /* the producer dropped events */
	SPF_TANDEM_RECON_SEQUENCE_GAP,  /* a sequence number is missing */
	SPF_TANDEM_RECON_OUT_OF_ORDER,  /* counters are not monotonic */
	SPF_TANDEM_RECON_NOT_ADVERTISED,/* the producer was not armed for this frame */
	SPF_TANDEM_RECON_EINVAL,
} spf_tandem_recon_rc_t;

typedef struct {
	uint64_t frame_start;
	uint32_t samples;
	uint8_t  index_at_frame_start;   /* carried from the previous frame */
	bool     events_valid;           /* the producer was armed AND drained */
	uint32_t overflow_count;
	uint32_t expect_first_sequence;  /* 0 = do not check continuity */
} spf_tandem_frame_t;

/*
 * Fill `series` with the common gain index for every sample in the frame.
 *
 * The transition is placed at `sample_sequence + effect_offset`, never at the
 * recorded counter itself: the recorded instant is the DECISION, and the change
 * becomes visible in the IQ later by analog settling and filter group delay.
 * Campaign C measures that offset; passing 0 says "unknown", which is honest
 * but not correct, so callers should pass the published value.
 */
spf_tandem_recon_rc_t spf_tandem_reconstruct(
	const spf_tandem_frame_t *frame,
	const uint8_t *wire_events, size_t event_count,
	int32_t effect_offset,
	uint8_t *series, size_t series_len);

const char *spf_tandem_recon_rc_name(spf_tandem_recon_rc_t rc);

#endif /* SPF_TANDEM_EVENT_H */
