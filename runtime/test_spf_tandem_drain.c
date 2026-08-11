/*
 * test_spf_tandem_drain.c -- the drain rules that a memcpy would get wrong.
 */

#include "spf_tandem_drain.h"

#include <stdio.h>
#include <string.h>

static int checks;
#define CHECK(cond, what)                                                      \
	do { checks++; if (!(cond)) {                                              \
		fprintf(stderr, "FAIL: %s (%s:%d)\n", (what), __FILE__, __LINE__);      \
		return 1; } } while (0)

#define CAP 16

static spf_tandem_record_t rec(uint64_t counter, uint8_t index, uint8_t epoch,
                               uint32_t seq)
{
	spf_tandem_record_t r;
	memset(&r, 0, sizeof(r));
	r.sample_counter = counter;
	r.gain_index = index;
	r.epoch = epoch;
	r.sequence = seq;
	r.direction = SPF_TANDEM_DIR_DECREASE;
	r.reason = SPF_TANDEM_REASON_LG_ADC;
	return r;
}

static int test_not_armed_is_not_zero_events(void)
{
	spf_tandem_drain_t d;
	spf_tandem_drain_result_t r;
	uint8_t out[CAP * 16];

	spf_tandem_drain_init(&d, 40);
	spf_tandem_drain_frame(&d, NULL, 0, 0, 0, 4096, out, CAP, &r);
	CHECK(!r.events_valid && r.count == 0,
	      "an unarmed drain reports nothing known, not zero events");

	spf_tandem_drain_arm(&d, 1, 40);
	spf_tandem_drain_frame(&d, NULL, 0, 0, 0, 4096, out, CAP, &r);
	CHECK(r.events_valid && r.count == 0,
	      "an armed drain with no transitions reports a valid, empty frame");
	CHECK(r.index_at_start == 40, "and carries the index it armed at");
	return 0;
}

static int test_epoch_filtering(void)
{
	spf_tandem_drain_t d;
	spf_tandem_drain_result_t r;
	spf_tandem_record_t in[4];
	uint8_t out[CAP * 16];
	spf_tandem_event_t e;

	spf_tandem_drain_init(&d, 40);
	spf_tandem_drain_arm(&d, 7, 40);

	in[0] = rec(100, 39, 6, 11);   /* previous owner */
	in[1] = rec(200, 38, 7, 1);    /* ours */
	in[2] = rec(300, 37, 5, 12);   /* older still */
	in[3] = rec(400, 36, 7, 2);    /* ours */

	spf_tandem_drain_frame(&d, in, 4, 0, 0, 4096, out, CAP, &r);
	CHECK(r.count == 2, "only this epoch's records reach the frame");
	CHECK(d.dropped_stale == 2, "and the stale ones are counted, not hidden");
	spf_tandem_event_decode(&out[0], &e);
	CHECK(e.sample_sequence == 200, "the first shipped record is ours");
	spf_tandem_event_decode(&out[16], &e);
	CHECK(e.sample_sequence == 400, "so is the second");
	return 0;
}

static int test_rearm_discards_carry(void)
{
	spf_tandem_drain_t d;
	spf_tandem_drain_result_t r;
	spf_tandem_record_t in[1];
	uint8_t out[CAP * 16];

	spf_tandem_drain_init(&d, 40);
	spf_tandem_drain_arm(&d, 3, 40);

	/* a record for the NEXT frame arrives during this one */
	in[0] = rec(9000, 35, 3, 1);
	spf_tandem_drain_frame(&d, in, 1, 0, 0, 4096, out, CAP, &r);
	CHECK(r.count == 0, "a later-frame record is not shipped in this frame");
	CHECK(d.carry_count == 1, "it is carried forward, not dropped");

	/* the session is torn down and a new one arms */
	spf_tandem_drain_arm(&d, 4, 50);
	CHECK(d.carry_count == 0,
	      "re-arming discards the carry: it belonged to the previous owner");

	spf_tandem_drain_frame(&d, NULL, 0, 0, 8192, 4096, out, CAP, &r);
	CHECK(r.count == 0 && r.index_at_start == 50,
	      "and the new session starts from its own index");
	return 0;
}

static int test_carry_forward(void)
{
	spf_tandem_drain_t d;
	spf_tandem_drain_result_t r;
	spf_tandem_record_t in[3];
	uint8_t out[CAP * 16];
	spf_tandem_event_t e;

	spf_tandem_drain_init(&d, 40);
	spf_tandem_drain_arm(&d, 1, 40);

	/* one drain returns events spanning two frames -- the FIFO is read on a
	 * schedule that has nothing to do with frame boundaries */
	in[0] = rec(1000, 39, 1, 1);   /* frame 0 */
	in[1] = rec(5000, 38, 1, 2);   /* frame 1 */
	in[2] = rec(6000, 37, 1, 3);   /* frame 1 */

	spf_tandem_drain_frame(&d, in, 3, 0, 0, 4096, out, CAP, &r);
	CHECK(r.count == 1, "frame 0 gets only its own event");
	CHECK(r.index_at_start == 40, "opening at the armed index");
	CHECK(d.carry_count == 2, "the other two are held");

	spf_tandem_drain_frame(&d, NULL, 0, 0, 4096, 4096, out, CAP, &r);
	CHECK(r.count == 2, "frame 1 gets them, from the carry, with no new read");
	CHECK(r.index_at_start == 39,
	      "and opens at the index frame 0's last event left in force");
	spf_tandem_event_decode(&out[0], &e);
	CHECK(e.sample_sequence == 5000, "in order");
	spf_tandem_event_decode(&out[16], &e);
	CHECK(e.sample_sequence == 6000, "still in order");
	CHECK(d.carry_count == 0, "and the carry is now empty");
	return 0;
}

static int test_pre_frame_event_sets_opening_index(void)
{
	spf_tandem_drain_t d;
	spf_tandem_drain_result_t r;
	spf_tandem_record_t in[1];
	uint8_t out[CAP * 16];

	spf_tandem_drain_init(&d, 40);
	spf_tandem_drain_arm(&d, 1, 40);

	/* drained late: the transition happened before this frame began */
	in[0] = rec(500, 33, 1, 1);
	spf_tandem_drain_frame(&d, in, 1, 0, 4096, 4096, out, CAP, &r);
	CHECK(r.count == 0, "a pre-frame transition is not shipped as an event");
	CHECK(r.index_at_start == 33,
	      "but it does set the index the frame opens at, so the series is right");
	return 0;
}

static int test_overflow_is_reported(void)
{
	spf_tandem_drain_t d;
	spf_tandem_drain_result_t r;
	spf_tandem_record_t in[CAP + 4];
	uint8_t out[CAP * 16];
	unsigned i;

	spf_tandem_drain_init(&d, 40);
	spf_tandem_drain_arm(&d, 1, 40);
	for (i = 0; i < CAP + 4; i++)
		in[i] = rec(100 + i, (uint8_t)(40 - i), 1, i + 1);

	spf_tandem_drain_frame(&d, in, CAP + 4, 0, 0, 4096, out, CAP, &r);
	CHECK(r.count == CAP, "the frame carries exactly its capacity");
	CHECK(r.overflow_count == 4,
	      "and the excess is reported as overflow, never silently truncated");

	/* the block's own drops are passed through and added to ours */
	spf_tandem_drain_arm(&d, 2, 40);
	spf_tandem_drain_frame(&d, NULL, 0, 9, 0, 4096, out, CAP, &r);
	CHECK(r.overflow_count == 9, "a hardware drop is reported even with no events");
	CHECK(r.events_valid, "and the frame is still marked as having a producer");
	return 0;
}

static int test_end_to_end_reconstruction(void)
{
	spf_tandem_drain_t d;
	spf_tandem_drain_result_t r;
	spf_tandem_record_t in[3];
	uint8_t out[CAP * 16];
	uint8_t series[4096];
	spf_tandem_frame_t f;
	unsigned i;

	/* drain -> encode -> reconstruct, the whole Stage 5 path */
	spf_tandem_drain_init(&d, 44);
	spf_tandem_drain_arm(&d, 2, 44);
	in[0] = rec(1000, 43, 2, 1);
	in[1] = rec(2000, 42, 2, 2);
	in[2] = rec(3000, 43, 2, 3);
	spf_tandem_drain_frame(&d, in, 3, 0, 0, 4096, out, CAP, &r);
	CHECK(r.count == 3, "all three transitions land in the frame");

	memset(&f, 0, sizeof(f));
	f.frame_start = 0;
	f.samples = 4096;
	f.index_at_frame_start = r.index_at_start;
	f.events_valid = r.events_valid;
	f.overflow_count = r.overflow_count;
	f.expect_first_sequence = r.first_sequence;

	CHECK(spf_tandem_reconstruct(&f, out, r.count, 0, series, sizeof(series))
	      == SPF_TANDEM_RECON_OK, "and the frame reconstructs");
	for (i = 0; i < 1000; i++)  CHECK(series[i] == 44, "opening index holds");
	for (i = 1000; i < 2000; i++) CHECK(series[i] == 43, "first transition");
	for (i = 2000; i < 3000; i++) CHECK(series[i] == 42, "second");
	for (i = 3000; i < 4096; i++) CHECK(series[i] == 43, "third");
	return 0;
}

int main(void)
{
	struct { const char *n; int (*f)(void); } t[] = {
		{ "not_armed_is_not_zero_events",   test_not_armed_is_not_zero_events },
		{ "epoch_filtering",                test_epoch_filtering },
		{ "rearm_discards_carry",           test_rearm_discards_carry },
		{ "carry_forward",                  test_carry_forward },
		{ "pre_frame_event_sets_index",     test_pre_frame_event_sets_opening_index },
		{ "overflow_is_reported",           test_overflow_is_reported },
		{ "end_to_end_reconstruction",      test_end_to_end_reconstruction },
	};
	size_t i;
	for (i = 0; i < sizeof(t) / sizeof(t[0]); i++) {
		if (t[i].f() != 0) { fprintf(stderr, "test %s FAILED\n", t[i].n); return 1; }
		printf("  ok  %s\n", t[i].n);
	}
	printf("PASS: spf_tandem_drain (%d checks)\n", checks);
	return 0;
}
