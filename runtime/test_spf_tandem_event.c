/*
 * test_spf_tandem_event.c -- §8.5's protocol and post-processing tests.
 *
 * The exit criterion is exact reconstruction at every transition boundary,
 * INCLUDING frames with no transitions at all -- that case is what the shipped
 * validity flag currently gets wrong.
 */

#include "spf_tandem_event.h"

#include <stdio.h>
#include <string.h>

static int checks;
#define CHECK(cond, what)                                                      \
	do { checks++; if (!(cond)) {                                              \
		fprintf(stderr, "FAIL: %s (%s:%d)\n", (what), __FILE__, __LINE__);      \
		return 1; } } while (0)

#define FRAME_SAMPLES 4096u

static void mk(uint8_t *buf, size_t i, uint64_t counter, uint8_t index,
               uint8_t dir, uint32_t seq)
{
	spf_tandem_record_t r;
	memset(&r, 0, sizeof(r));
	r.sample_counter = counter;
	r.gain_index = index;
	r.direction = dir;
	r.reason = SPF_TANDEM_REASON_LG_ADC;
	r.sequence = seq;
	spf_tandem_event_encode(&r, &buf[i * SPF_GAIN_EVENT_BYTES]);
}

static int test_roundtrip(void)
{
	uint8_t w[16];
	spf_tandem_record_t r;
	spf_tandem_event_t e;

	memset(&r, 0, sizeof(r));
	r.sample_counter = 0x0123456789ABCDEFull;
	r.gain_index = 47;
	r.reason = SPF_TANDEM_REASON_BOTH_LOW_POWER;
	r.direction = SPF_TANDEM_DIR_INCREASE;
	r.sequence = 0xDEADBEEFu;
	spf_tandem_event_encode(&r, w);
	spf_tandem_event_decode(w, &e);

	CHECK(e.sample_sequence == r.sample_counter, "64-bit counter survives");
	CHECK(e.gain_index == 47, "index survives");
	CHECK(e.reason == SPF_TANDEM_REASON_BOTH_LOW_POWER, "reason survives");
	CHECK(e.direction == SPF_TANDEM_DIR_INCREASE, "direction survives");
	CHECK(e.event_sequence == 0xDEADBEEFu, "sequence survives");
	CHECK((e.flags & SPF_GAIN_EVENT_RX1_CHANGED) != 0 &&
	      (e.flags & SPF_GAIN_EVENT_RX2_CHANGED) != 0,
	      "both CHANGED bits set: the wire evidence that tandem was in control");
	CHECK(sizeof(w) == SPF_GAIN_EVENT_BYTES, "record is exactly 16 bytes");
	return 0;
}

static int test_exact_reconstruction(void)
{
	uint8_t w[3 * 16], s[FRAME_SAMPLES];
	spf_tandem_frame_t f;
	unsigned i;

	memset(&f, 0, sizeof(f));
	f.frame_start = 1000000; f.samples = FRAME_SAMPLES;
	f.index_at_frame_start = 40; f.events_valid = true;

	mk(w, 0, 1000100, 39, SPF_TANDEM_DIR_DECREASE, 1);
	mk(w, 1, 1001000, 38, SPF_TANDEM_DIR_DECREASE, 2);
	mk(w, 2, 1002000, 39, SPF_TANDEM_DIR_INCREASE, 3);

	CHECK(spf_tandem_reconstruct(&f, w, 3, 0, s, sizeof(s)) == SPF_TANDEM_RECON_OK,
	      "reconstruction succeeds");
	for (i = 0; i < 100; i++)  CHECK(s[i] == 40, "before the first transition");
	for (i = 100; i < 1000; i++) CHECK(s[i] == 39, "after the first");
	for (i = 1000; i < 2000; i++) CHECK(s[i] == 38, "after the second");
	for (i = 2000; i < FRAME_SAMPLES; i++) CHECK(s[i] == 39, "after the third");
	CHECK(s[99] == 40 && s[100] == 39, "the boundary sample is EXACT");
	return 0;
}

static int test_zero_event_frame(void)
{
	uint8_t s[FRAME_SAMPLES];
	spf_tandem_frame_t f;
	unsigned i;

	memset(&f, 0, sizeof(f));
	f.frame_start = 0; f.samples = FRAME_SAMPLES;
	f.index_at_frame_start = 44; f.events_valid = true;

	/* the case the shipped builder cannot express: gain genuinely held */
	CHECK(spf_tandem_reconstruct(&f, NULL, 0, 0, s, sizeof(s)) == SPF_TANDEM_RECON_OK,
	      "a frame with no transitions reconstructs");
	for (i = 0; i < FRAME_SAMPLES; i++)
		CHECK(s[i] == 44, "and the whole frame holds the carried index");

	/* the same frame, but the producer was not running: must NOT be confused
	 * with the above */
	f.events_valid = false;
	CHECK(spf_tandem_reconstruct(&f, NULL, 0, 0, s, sizeof(s))
	      == SPF_TANDEM_RECON_NOT_ADVERTISED,
	      "producer-not-armed is distinguishable from gain-held");
	return 0;
}

static int test_frame_boundaries(void)
{
	uint8_t w[16], s[FRAME_SAMPLES];
	spf_tandem_frame_t f;

	memset(&f, 0, sizeof(f));
	f.frame_start = 5000; f.samples = FRAME_SAMPLES;
	f.index_at_frame_start = 30; f.events_valid = true;

	/* exactly on the first sample */
	mk(w, 0, 5000, 31, SPF_TANDEM_DIR_INCREASE, 1);
	CHECK(spf_tandem_reconstruct(&f, w, 1, 0, s, sizeof(s)) == SPF_TANDEM_RECON_OK, "on");
	CHECK(s[0] == 31, "a transition on the first sample applies to it");

	/* before the frame: the whole frame carries the new index */
	mk(w, 0, 4000, 32, SPF_TANDEM_DIR_INCREASE, 1);
	CHECK(spf_tandem_reconstruct(&f, w, 1, 0, s, sizeof(s)) == SPF_TANDEM_RECON_OK, "before");
	CHECK(s[0] == 32 && s[FRAME_SAMPLES - 1] == 32,
	      "a transition before the frame applies to all of it");

	/* after the frame: none of it changes */
	mk(w, 0, 5000 + FRAME_SAMPLES + 10, 33, SPF_TANDEM_DIR_INCREASE, 1);
	CHECK(spf_tandem_reconstruct(&f, w, 1, 0, s, sizeof(s)) == SPF_TANDEM_RECON_OK, "after");
	CHECK(s[FRAME_SAMPLES - 1] == 30, "a transition after the frame does not apply");

	/* the last sample exactly */
	mk(w, 0, 5000 + FRAME_SAMPLES - 1, 34, SPF_TANDEM_DIR_INCREASE, 1);
	CHECK(spf_tandem_reconstruct(&f, w, 1, 0, s, sizeof(s)) == SPF_TANDEM_RECON_OK, "last");
	CHECK(s[FRAME_SAMPLES - 1] == 34 && s[FRAME_SAMPLES - 2] == 30,
	      "a transition on the last sample applies to exactly that sample");
	return 0;
}

static int test_decision_to_effect_offset(void)
{
	uint8_t w[16], s[FRAME_SAMPLES];
	spf_tandem_frame_t f;

	memset(&f, 0, sizeof(f));
	f.frame_start = 0; f.samples = FRAME_SAMPLES;
	f.index_at_frame_start = 20; f.events_valid = true;
	mk(w, 0, 1000, 21, SPF_TANDEM_DIR_INCREASE, 1);

	CHECK(spf_tandem_reconstruct(&f, w, 1, 0, s, sizeof(s)) == SPF_TANDEM_RECON_OK, "0");
	CHECK(s[1000] == 21 && s[999] == 20, "with no offset the decision is the effect");

	/* Campaign C measures this; applying it moves the edge, which is the whole
	 * point of publishing it */
	CHECK(spf_tandem_reconstruct(&f, w, 1, 250, s, sizeof(s)) == SPF_TANDEM_RECON_OK, "+250");
	CHECK(s[1250] == 21 && s[1249] == 20,
	      "the published offset moves the edge to where the IQ actually changes");
	return 0;
}

static int test_faults_are_explicit(void)
{
	uint8_t w[2 * 16], s[FRAME_SAMPLES];
	spf_tandem_frame_t f;

	memset(&f, 0, sizeof(f));
	f.frame_start = 0; f.samples = FRAME_SAMPLES;
	f.index_at_frame_start = 40; f.events_valid = true;

	/* overflow: refuse rather than produce a plausible wrong series */
	f.overflow_count = 1;
	mk(w, 0, 100, 39, SPF_TANDEM_DIR_DECREASE, 1);
	CHECK(spf_tandem_reconstruct(&f, w, 1, 0, s, sizeof(s)) == SPF_TANDEM_RECON_OVERFLOW,
	      "overflow is an explicit fault, never silently interpolated");
	f.overflow_count = 0;

	/* out of order by counter */
	mk(w, 0, 500, 39, SPF_TANDEM_DIR_DECREASE, 1);
	mk(w, 1, 200, 38, SPF_TANDEM_DIR_DECREASE, 2);
	CHECK(spf_tandem_reconstruct(&f, w, 2, 0, s, sizeof(s)) == SPF_TANDEM_RECON_OUT_OF_ORDER,
	      "a non-monotonic counter is a fault");

	/* sequence regression */
	mk(w, 0, 100, 39, SPF_TANDEM_DIR_DECREASE, 5);
	mk(w, 1, 200, 38, SPF_TANDEM_DIR_DECREASE, 5);
	CHECK(spf_tandem_reconstruct(&f, w, 2, 0, s, sizeof(s)) == SPF_TANDEM_RECON_OUT_OF_ORDER,
	      "a repeated sequence number is a fault");

	/* missing event, detected by continuity */
	f.expect_first_sequence = 1;
	mk(w, 0, 100, 39, SPF_TANDEM_DIR_DECREASE, 1);
	mk(w, 1, 200, 37, SPF_TANDEM_DIR_DECREASE, 3);   /* 2 is missing */
	CHECK(spf_tandem_reconstruct(&f, w, 2, 0, s, sizeof(s)) == SPF_TANDEM_RECON_SEQUENCE_GAP,
	      "a missing event is caught by sequence continuity");
	return 0;
}

static int test_long_frame(void)
{
	static uint8_t s[524288];
	static uint8_t w[64 * 16];
	spf_tandem_frame_t f;
	unsigned i, n = 18;   /* §7.3's worst case at the 1 ms cooldown */

	memset(&f, 0, sizeof(f));
	f.frame_start = 1000; f.samples = 524288;
	f.index_at_frame_start = 40; f.events_valid = true;

	for (i = 0; i < n; i++)
		mk(w, i, 1000 + 20000ull * (i + 1), (uint8_t)(40 + i + 1),
		   SPF_TANDEM_DIR_INCREASE, i + 1);

	CHECK(spf_tandem_reconstruct(&f, w, n, 0, s, sizeof(s)) == SPF_TANDEM_RECON_OK,
	      "a full 524,288-sample frame reconstructs");
	for (i = 0; i < n; i++) {
		size_t at = 20000u * (i + 1);
		CHECK(s[at] == (uint8_t)(40 + i + 1), "each transition lands exactly");
		CHECK(s[at - 1] == (uint8_t)(40 + i), "and the sample before it does not");
	}
	return 0;
}

int main(void)
{
	struct { const char *n; int (*f)(void); } t[] = {
		{ "roundtrip",                 test_roundtrip },
		{ "exact_reconstruction",      test_exact_reconstruction },
		{ "zero_event_frame",          test_zero_event_frame },
		{ "frame_boundaries",          test_frame_boundaries },
		{ "decision_to_effect_offset", test_decision_to_effect_offset },
		{ "faults_are_explicit",       test_faults_are_explicit },
		{ "long_frame",                test_long_frame },
	};
	size_t i;
	for (i = 0; i < sizeof(t) / sizeof(t[0]); i++) {
		if (t[i].f() != 0) { fprintf(stderr, "test %s FAILED\n", t[i].n); return 1; }
		printf("  ok  %s\n", t[i].n);
	}
	printf("PASS: spf_tandem_event (%d checks)\n", checks);
	return 0;
}
