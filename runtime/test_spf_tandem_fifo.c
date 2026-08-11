/* test_spf_tandem_fifo.c -- the FIFO read protocol, including the pop order. */

#include "spf_tandem_fifo.h"
#include "spf_tandem_drain.h"

#include <stdio.h>
#include <string.h>

static int checks;
#define CHECK(cond, what)                                                      \
	do { checks++; if (!(cond)) {                                              \
		fprintf(stderr, "FAIL: %s (%s:%d)\n", (what), __FILE__, __LINE__);      \
		return 1; } } while (0)

/* a model of the block: four windows onto a 104-bit record, and reading the
 * last window pops */
typedef struct {
	uint64_t counter[8];
	uint8_t  index[8], epoch[8];
	uint16_t seq[8];
	unsigned depth, head;
	uint32_t ovf;
	int      reads;
	int      fail_at;
	int      pops;
} model_t;

static int model_read(void *v, uint8_t addr, uint32_t *out)
{
	model_t *m = v;
	uint64_t hi;

	if (++m->reads == m->fail_at)
		return -1;
	switch (addr) {
	case SPF_TANDEM_REG_EVT_LEVEL: *out = m->depth - m->head; return 0;
	case SPF_TANDEM_REG_EVT_OVF:   *out = m->ovf; return 0;
	default: break;
	}
	if (m->head >= m->depth) { *out = 0; return 0; }
	hi = ((uint64_t)m->seq[m->head] << 24) | ((uint64_t)m->epoch[m->head] << 16)
	   | ((uint64_t)2u << 12) | ((uint64_t)1u << 8) | m->index[m->head];
	switch (addr) {
	case SPF_TANDEM_REG_EVT_LO0: *out = (uint32_t)m->counter[m->head]; break;
	case SPF_TANDEM_REG_EVT_LO1: *out = (uint32_t)(m->counter[m->head] >> 32); break;
	case SPF_TANDEM_REG_EVT_HI2: *out = (uint32_t)hi; break;
	case SPF_TANDEM_REG_EVT_HI3:
		*out = (uint32_t)(hi >> 32) & 0xFFu;
		m->head++; m->pops++;    /* THIS window pops, and only this one */
		break;
	default: *out = 0; break;
	}
	return 0;
}

static void model_init(model_t *m, unsigned n)
{
	unsigned i;
	memset(m, 0, sizeof(*m));
	m->depth = n;
	for (i = 0; i < n; i++) {
		m->counter[i] = 100000ull + i * 1000ull;
		m->index[i] = (uint8_t)(44 - i);
		m->epoch[i] = 3;
		m->seq[i] = (uint16_t)(i + 1);
	}
}

static int test_unpack_matches_the_rtl_layout(void)
{
	uint32_t w[4];
	spf_tandem_record_t r;

	/* the §7.1 record, assembled bit by bit the way the RTL concatenates it */
	w[0] = 0x89ABCDEFu;
	w[1] = 0x01234567u;
	/* [71:64]=index 43, [75:72]=reason 5, [77:76]=dir 2, [79:78]=0,
	 * [87:80]=epoch 9, [95:88]=seq low byte 0x34 */
	w[2] = 0x34090000u | (2u << 12) | (5u << 8) | 43u;
	w[3] = 0x12u;   /* [103:96] = seq high byte */

	spf_tandem_fifo_unpack(w, &r);
	CHECK(r.sample_counter == 0x0123456789ABCDEFull, "64-bit counter spans two words");
	CHECK(r.gain_index == 43, "index");
	CHECK(r.reason == 5, "reason");
	CHECK(r.direction == 2, "direction");
	CHECK(r.epoch == 9, "epoch survives, and is what the drain filters on");
	CHECK(r.sequence == 0x1234u,
	      "the sequence straddles the word boundary and reassembles");
	return 0;
}

static int test_hi3_is_what_pops(void)
{
	model_t m;
	spf_tandem_record_t out[8];
	uint32_t ovf = 0;
	int n;

	model_init(&m, 3);
	n = spf_tandem_fifo_drain(model_read, &m, out, 8, &ovf);
	CHECK(n == 3, "all three records drain");
	CHECK(m.pops == 3, "exactly one pop per record, never more");
	CHECK(out[0].sample_counter == 100000ull, "first record");
	CHECK(out[2].sample_counter == 102000ull, "third record");
	CHECK(out[1].sequence == 2, "sequence numbers survive in order");
	CHECK(out[1].epoch == 3, "so does the epoch");
	return 0;
}

static int test_bounded_by_the_level_read_once(void)
{
	model_t m;
	spf_tandem_record_t out[4];
	uint32_t ovf = 0;
	int n;

	model_init(&m, 8);
	n = spf_tandem_fifo_drain(model_read, &m, out, 4, &ovf);
	CHECK(n == 4, "the drain stops at the caller's capacity");
	CHECK(m.pops == 4, "and does not pop what it cannot return");
	/* the rest are still there for the next call -- not lost */
	n = spf_tandem_fifo_drain(model_read, &m, out, 4, &ovf);
	CHECK(n == 4, "the remainder drains on the next call");
	return 0;
}

static int test_overflow_and_read_failure(void)
{
	model_t m;
	spf_tandem_record_t out[8];
	uint32_t ovf = 0;
	int n;

	model_init(&m, 2);
	m.ovf = 17;
	n = spf_tandem_fifo_drain(model_read, &m, out, 8, &ovf);
	CHECK(n == 2 && ovf == 17, "the block's drop count is reported");

	/* a register read that fails mid-record must not fabricate a record */
	model_init(&m, 3);
	m.fail_at = 5;   /* inside the first record */
	n = spf_tandem_fifo_drain(model_read, &m, out, 8, &ovf);
	CHECK(n < 0, "a failure inside the first record is an error, not a short read");

	model_init(&m, 3);
	m.fail_at = 9;   /* inside the second record */
	n = spf_tandem_fifo_drain(model_read, &m, out, 8, &ovf);
	CHECK(n == 1, "a later failure returns what was completely read");
	CHECK(out[0].sample_counter == 100000ull, "and that record is intact");
	return 0;
}

static int test_end_to_end_fifo_to_series(void)
{
	model_t m;
	spf_tandem_record_t recs[8];
	spf_tandem_drain_t d;
	spf_tandem_drain_result_t res;
	spf_tandem_frame_t f;
	uint8_t wire[16 * 16], series[4096];
	uint32_t ovf = 0;
	int n;
	unsigned i;

	/* the whole path: block registers -> records -> frame array -> series */
	model_init(&m, 3);
	m.counter[0] = 1000; m.counter[1] = 2000; m.counter[2] = 3000;
	/* model_init's default indices start AT the opening index, which would make
	 * the first transition invisible; step them so each edge is distinguishable */
	m.index[0] = 43; m.index[1] = 42; m.index[2] = 41;
	n = spf_tandem_fifo_drain(model_read, &m, recs, 8, &ovf);
	CHECK(n == 3, "three records off the block");

	spf_tandem_drain_init(&d, 44);
	spf_tandem_drain_arm(&d, 3, 44);          /* same epoch the model stamps */
	spf_tandem_drain_frame(&d, recs, (unsigned)n, ovf, 0, 4096, wire, 16, &res);
	CHECK(res.count == 3, "all three reach the frame");
	CHECK(res.events_valid, "and the frame is marked as having a producer");

	memset(&f, 0, sizeof(f));
	f.frame_start = 0; f.samples = 4096;
	f.index_at_frame_start = res.index_at_start;
	f.events_valid = res.events_valid;
	f.overflow_count = res.overflow_count;
	f.expect_first_sequence = res.first_sequence;
	CHECK(spf_tandem_reconstruct(&f, wire, res.count, 0, series, sizeof(series))
	      == SPF_TANDEM_RECON_OK, "and the series reconstructs");
	for (i = 0; i < 1000; i++)    CHECK(series[i] == 44, "opening index");
	for (i = 1000; i < 2000; i++) CHECK(series[i] == 43, "after the first");
	for (i = 2000; i < 3000; i++) CHECK(series[i] == 42, "after the second");
	for (i = 3000; i < 4096; i++) CHECK(series[i] == 41, "after the third");

	/* a record from another epoch never reaches the frame */
	model_init(&m, 2);
	m.epoch[0] = 2;                        /* a previous owner's record */
	m.counter[0] = 200500; m.counter[1] = 201500;   /* both inside the frame */
	n = spf_tandem_fifo_drain(model_read, &m, recs, 8, &ovf);
	CHECK(n == 2, "both records come off the block -- the block does not filter");
	spf_tandem_drain_frame(&d, recs, (unsigned)n, 0, 200000, 4096, wire, 16, &res);
	CHECK(res.count == 1, "but the stale-epoch one is dropped at the drain");
	return 0;
}

int main(void)
{
	struct { const char *n; int (*f)(void); } t[] = {
		{ "unpack_matches_the_rtl_layout", test_unpack_matches_the_rtl_layout },
		{ "hi3_is_what_pops",              test_hi3_is_what_pops },
		{ "bounded_by_level_read_once",    test_bounded_by_the_level_read_once },
		{ "overflow_and_read_failure",     test_overflow_and_read_failure },
		{ "end_to_end_fifo_to_series",     test_end_to_end_fifo_to_series },
	};
	size_t i;
	for (i = 0; i < sizeof(t) / sizeof(t[0]); i++) {
		if (t[i].f() != 0) { fprintf(stderr, "test %s FAILED\n", t[i].n); return 1; }
		printf("  ok  %s\n", t[i].n);
	}
	printf("PASS: spf_tandem_fifo (%d checks)\n", checks);
	return 0;
}
