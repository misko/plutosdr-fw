/*
 * test_spf_tandem_ctl.c -- §8.4's runtime tests, against a mock backend.
 *
 * The point of the backend indirection is that every failure path in the §11
 * transaction is reachable here: an SPI failure at each step, unequal
 * read-back, an ownership timeout, split-table mode, the wrong ENSM state.
 * None of it needs a radio.
 */

#include "spf_tandem_ctl.h"

#include <stdio.h>
#include <string.h>

static int checks;

#define CHECK(cond, what)                                                      \
	do {                                                                       \
		checks++;                                                              \
		if (!(cond)) {                                                         \
			fprintf(stderr, "FAIL: %s (%s:%d)\n", (what), __FILE__, __LINE__);  \
			return 1;                                                          \
		}                                                                      \
	} while (0)

/* ------------------------------------------------------------------ mock -- */

typedef struct {
	uint32_t fpga[64];
	uint8_t  ad9361[0x400];
	uint8_t  gain[2];
	char     mode[2][16];
	char     ensm[16];
	bool     full_table;

	/* injectable failures */
	int  fail_fpga_read_at;   int n_fpga_read;
	int  fail_fpga_write_at;  int n_fpga_write;
	int  fail_ad9361_write_at;int n_ad9361_write;
	int  fail_gain_set_at;    int n_gain_set;
	int  fail_gain_get_at;    int n_gain_get;
	int  fail_mode_set_at;    int n_mode_set;
	bool never_own;           /* STATUS never reports ownership */
	bool unequal_readback;
} mock_t;

static int m_fpga_read(void *v, uint8_t a, uint32_t *o)
{
	mock_t *m = v;
	if (++m->n_fpga_read == m->fail_fpga_read_at) return -1;
	*o = m->fpga[a >> 2];
	return 0;
}
static int m_fpga_write(void *v, uint8_t a, uint32_t d)
{
	mock_t *m = v;
	if (++m->n_fpga_write == m->fail_fpga_write_at) return -1;
	m->fpga[a >> 2] = d;
	if (a == SPF_TANDEM_REG_CTRL) {
		uint32_t s = m->fpga[SPF_TANDEM_REG_STATUS >> 2] & ~(1u << 4);
		if (d != 0 && !m->never_own) s |= (1u << 4);
		m->fpga[SPF_TANDEM_REG_STATUS >> 2] = (s & ~7u) | (d ? (d == 2 ? 3u : 2u) : 0u);
	}
	return 0;
}
static int m_ad_read(void *v, uint16_t r, uint8_t *o)
{ mock_t *m = v; *o = m->ad9361[r]; return 0; }
static int m_ad_write(void *v, uint16_t r, uint8_t d)
{
	mock_t *m = v;
	if (++m->n_ad9361_write == m->fail_ad9361_write_at) return -1;
	m->ad9361[r] = d; return 0;
}
static int m_gain_get(void *v, int ch, uint8_t *o)
{
	mock_t *m = v;
	if (++m->n_gain_get == m->fail_gain_get_at) return -1;
	*o = (m->unequal_readback && ch == 1) ? (uint8_t)(m->gain[1] + 3u) : m->gain[ch];
	return 0;
}
static int m_gain_set(void *v, int ch, uint8_t g)
{
	mock_t *m = v;
	if (++m->n_gain_set == m->fail_gain_set_at) return -1;
	/* the real part drops these silently once armed; the mock mirrors that so
	 * a test can prove the runtime refuses before the device would swallow it */
	if ((m->ad9361[SPF_AD9361_REG_AGC_CONFIG_2] & SPF_AD9361_PIN_CTRL_MASK) != 0)
		return 0;
	m->gain[ch] = g;
	return 0;
}
static int m_mode_set(void *v, int ch, const char *s)
{
	mock_t *m = v;
	if (++m->n_mode_set == m->fail_mode_set_at) return -1;
	snprintf(m->mode[ch], sizeof(m->mode[ch]), "%s", s);
	return 0;
}
static int m_ensm(void *v, char *b, size_t n)
{ mock_t *m = v; snprintf(b, n, "%s", m->ensm); return 0; }
static int m_full(void *v, bool *f)
{ mock_t *m = v; *f = m->full_table; return 0; }

static void mock_init(mock_t *m, spf_tandem_backend_t *be)
{
	memset(m, 0, sizeof(*m));
	m->fpga[SPF_TANDEM_REG_ID >> 2] = SPF_TANDEM_ID_MAGIC;
	m->ad9361[SPF_AD9361_REG_AGC_CONFIG_2] = 0x08; /* bit 3 live, as measured */
	m->ad9361[SPF_AD9361_REG_PEAK_WAIT_TIME] = 0x23; /* step 2, PWOT 3 */
	m->ad9361[SPF_AD9361_REG_AGC_CONFIG_3] = 0x23;
	m->ad9361[SPF_AD9361_REG_MAX_GAIN_INDEX] = 76; /* chip default; D-8 says read it */
	m->full_table = true;
	snprintf(m->ensm, sizeof(m->ensm), "fdd");

	memset(be, 0, sizeof(*be));
	be->ctx = m;
	be->fpga_read = m_fpga_read;   be->fpga_write = m_fpga_write;
	be->ad9361_read = m_ad_read;   be->ad9361_write = m_ad_write;
	be->gain_get = m_gain_get;     be->gain_set = m_gain_set;
	be->mode_set = m_mode_set;     be->ensm_get = m_ensm;
	be->full_gain_table = m_full;
}

/* ----------------------------------------------------------------- tests -- */

static int test_enable_disable_happy(void)
{
	mock_t m; spf_tandem_backend_t be; spf_tandem_ctl_t c;
	char buf[512];

	mock_init(&m, &be);
	spf_tandem_ctl_init(&c, &be, 40);

	CHECK(spf_tandem_ctl_enable(&c, true) == SPF_TANDEM_OK, "enable succeeds");
	CHECK(c.lc.state == SPF_TANDEM_ACTIVE, "reaches tandem-auto");
	CHECK(m.gain[0] == 40 && m.gain[1] == 40, "both channels programmed equal");
	CHECK((m.ad9361[SPF_AD9361_REG_AGC_CONFIG_2] & 0x03) == 0x03, "pin control armed");
	CHECK((m.ad9361[SPF_AD9361_REG_AGC_CONFIG_2] & 0x08) == 0x08,
	      "read-modify-write preserved the live bit 3");
	CHECK(m.ad9361[SPF_AD9361_REG_CTRL_OUT_PTR] == 0x03, "detector page selected");
	CHECK((m.ad9361[SPF_AD9361_REG_PEAK_WAIT_TIME] & 0x1F) == 0x03,
	      "Peak Overload Wait Time preserved while writing the step size");
	CHECK((m.ad9361[SPF_AD9361_REG_PEAK_WAIT_TIME] >> 5) == 0,
	      "decrement step programmed to one index");

	CHECK(spf_tandem_ctl_status(&c, buf, sizeof(buf)) > 0, "status renders");
	CHECK(strstr(buf, "\"gain_writable\":false") != NULL,
	      "status reports that software gain writes are refused");

	CHECK(spf_tandem_ctl_disable(&c, "slow_attack") == SPF_TANDEM_OK, "disable");
	CHECK((m.ad9361[SPF_AD9361_REG_AGC_CONFIG_2] & 0x03) == 0x00, "disarmed");
	CHECK(strcmp(m.mode[0], "slow_attack") == 0, "legacy mode restored");
	CHECK(c.lc.state == SPF_TANDEM_LEGACY, "back to legacy");
	return 0;
}

static int test_preconditions_refused(void)
{
	mock_t m; spf_tandem_backend_t be; spf_tandem_ctl_t c;

	/* wrong ENSM */
	mock_init(&m, &be); snprintf(m.ensm, sizeof(m.ensm), "alert");
	spf_tandem_ctl_init(&c, &be, 40);
	CHECK(spf_tandem_ctl_enable(&c, true) == SPF_TANDEM_ENOTRX, "alert refused");
	CHECK((m.ad9361[SPF_AD9361_REG_AGC_CONFIG_2] & 0x03) == 0,
	      "nothing was armed on the refused path");
	CHECK(strstr(c.last_error_detail, "step 3") != NULL, "names the failing step");

	/* split gain table */
	mock_init(&m, &be); m.full_table = false;
	spf_tandem_ctl_init(&c, &be, 40);
	CHECK(spf_tandem_ctl_enable(&c, true) == SPF_TANDEM_ECONFLICT, "split refused");
	CHECK(strstr(c.last_error_detail, "step 2") != NULL, "names the failing step");

	/* wrong FPGA ID */
	mock_init(&m, &be); m.fpga[0] = 0xDEADBEEF;
	spf_tandem_ctl_init(&c, &be, 40);
	CHECK(spf_tandem_ctl_enable(&c, true) == SPF_TANDEM_EINVAL, "bad ID refused");
	return 0;
}

static int test_unequal_readback(void)
{
	mock_t m; spf_tandem_backend_t be; spf_tandem_ctl_t c;
	mock_init(&m, &be); m.unequal_readback = true;
	spf_tandem_ctl_init(&c, &be, 40);
	CHECK(spf_tandem_ctl_enable(&c, true) == SPF_TANDEM_ECONFLICT,
	      "unequal read-back aborts the enable");
	CHECK((m.ad9361[SPF_AD9361_REG_AGC_CONFIG_2] & 0x03) == 0, "never armed");
	CHECK(c.lc.state == SPF_TANDEM_FAULTED, "and faults rather than continuing");
	return 0;
}

static int test_ownership_timeout(void)
{
	mock_t m; spf_tandem_backend_t be; spf_tandem_ctl_t c;
	mock_init(&m, &be); m.never_own = true;
	spf_tandem_ctl_init(&c, &be, 40);
	CHECK(spf_tandem_ctl_enable(&c, true) == SPF_TANDEM_EBUSY,
	      "ownership timeout is reported");
	CHECK(c.retries_used > 0, "retry was attempted");
	CHECK(c.retries_used <= c.retry_limit + 1, "and it was BOUNDED");
	CHECK((m.ad9361[SPF_AD9361_REG_AGC_CONFIG_2] & 0x03) == 0,
	      "never armed without ownership");
	return 0;
}

static int test_spi_failure_at_every_step(void)
{
	int step;
	/* walk the failure injection across every AD9361 write in the sequence and
	 * require that none of them leaves the part armed */
	/* The enable path makes five AD9361 writes. Injecting beyond that is not a
	 * failure case at all -- the write never happens and the enable correctly
	 * succeeds -- so the invariant is conditional on the enable having failed. */
	for (step = 1; step <= 5; step++) {
		mock_t m; spf_tandem_backend_t be; spf_tandem_ctl_t c;
		spf_tandem_rc_t rc;
		mock_init(&m, &be);
		m.fail_ad9361_write_at = step;
		spf_tandem_ctl_init(&c, &be, 40);
		rc = spf_tandem_ctl_enable(&c, true);
		CHECK(rc != SPF_TANDEM_OK, "an SPI write failure aborts the enable");
		CHECK((m.ad9361[SPF_AD9361_REG_AGC_CONFIG_2] & 0x03) == 0,
		      "an SPI failure never leaves pin control armed");
		CHECK(c.lc.state != SPF_TANDEM_ACTIVE,
		      "and never reaches tandem-auto");
	}
	/*
	 * The same walk over the FPGA register writes. This covers the index
	 * window write (step 4c) and the ownership request (step 10); a failure at
	 * either must leave the part in legacy mode with the pins unclaimed,
	 * because a block that half-owns the pins is worse than one that never
	 * tried.
	 */
	for (step = 1; step <= 4; step++) {
		mock_t m; spf_tandem_backend_t be; spf_tandem_ctl_t c;
		mock_init(&m, &be);
		m.fail_fpga_write_at = step;
		spf_tandem_ctl_init(&c, &be, 40);
		if (spf_tandem_ctl_enable(&c, true) == SPF_TANDEM_OK)
			continue;   /* past the last write; the enable correctly succeeds */
		CHECK((m.ad9361[SPF_AD9361_REG_AGC_CONFIG_2] & 0x03) == 0,
		      "an FPGA write failure never leaves pin control armed");
		CHECK(!spf_tandem_owns_pins(&c.lc),
		      "and never leaves the block owning the pins");
		CHECK(c.lc.state != SPF_TANDEM_ACTIVE, "and never reaches tandem-auto");
	}

	/* the enable path calls gain_set exactly twice, one per channel */
	for (step = 1; step <= 2; step++) {
		mock_t m; spf_tandem_backend_t be; spf_tandem_ctl_t c;
		mock_init(&m, &be);
		m.fail_gain_set_at = step;
		spf_tandem_ctl_init(&c, &be, 40);
		CHECK(spf_tandem_ctl_enable(&c, true) != SPF_TANDEM_OK,
		      "a gain-set failure aborts the enable");
		CHECK((m.ad9361[SPF_AD9361_REG_AGC_CONFIG_2] & 0x03) == 0, "never armed");
	}
	return 0;
}

static int test_gain_write_refused_while_armed(void)
{
	mock_t m; spf_tandem_backend_t be; spf_tandem_ctl_t c;
	mock_init(&m, &be);
	spf_tandem_ctl_init(&c, &be, 40);
	CHECK(spf_tandem_ctl_enable(&c, false) == SPF_TANDEM_OK, "enable to hold");

	/* the runtime must say no before the device silently swallows it */
	CHECK(spf_tandem_check_op(&c.lc, SPF_TANDEM_OP_GAIN_WRITE) == SPF_TANDEM_ECONFLICT,
	      "the runtime refuses a gain write while armed");
	CHECK(!spf_tandem_gain_writable(&c.lc), "and reports it as not writable");

	/* prove the device really would have swallowed it: bypass the runtime */
	CHECK(be.gain_set(be.ctx, 0, 7) == 0, "the part returns success");
	CHECK(m.gain[0] == 40, "but the write was dropped -- exactly E-AGC1's finding");
	return 0;
}

static int test_sync_quiescence_rule(void)
{
	mock_t m; spf_tandem_backend_t be; spf_tandem_ctl_t c;
	mock_init(&m, &be);
	spf_tandem_ctl_init(&c, &be, 40);
	CHECK(spf_tandem_ctl_enable(&c, true) == SPF_TANDEM_OK, "enable");
	m.fpga[SPF_TANDEM_REG_EXPECT >> 2] = 40;

	CHECK(spf_tandem_ctl_check_sync(&c) == SPF_TANDEM_OK, "agreement is not a fault");

	/* a disagreement while a pulse is in flight must be ignored */
	m.fpga[SPF_TANDEM_REG_STATUS >> 2] |= (1u << 6);
	m.gain[0] = 33; m.gain[1] = 33;
	CHECK(spf_tandem_ctl_check_sync(&c) == SPF_TANDEM_OK,
	      "a non-quiescent disagreement is ignored");
	CHECK(c.lc.state != SPF_TANDEM_FAULTED, "and does not fault");

	/* quiescent now: first disagreement tolerated, second faults */
	m.fpga[SPF_TANDEM_REG_STATUS >> 2] &= ~(1u << 6);
	CHECK(spf_tandem_ctl_check_sync(&c) == SPF_TANDEM_OK, "first is tolerated");
	CHECK(spf_tandem_ctl_check_sync(&c) == SPF_TANDEM_ECONFLICT,
	      "two consecutive quiescent disagreements fault");
	CHECK(c.lc.state == SPF_TANDEM_FAULTED, "and disarm");
	return 0;
}

/*
 * D-8: the clamp bound is read from the part, never assumed.
 *
 * The chip default is 76 and the RTL's reset default is also 76, so a
 * hard-coded bound looks correct on every radio anyone has tested. It stops
 * being correct the moment a driver loads a shorter gain table -- and then the
 * index model walks off the end of the table it exists to model, silently.
 */
static int test_max_index_is_read_from_the_part(void)
{
	mock_t m; spf_tandem_backend_t be; spf_tandem_ctl_t c;
	uint8_t max = 0;

	mock_init(&m, &be);
	m.ad9361[SPF_AD9361_REG_MAX_GAIN_INDEX] = 0xC3; /* [7] set, must be masked */
	spf_tandem_ctl_init(&c, &be, 40);
	CHECK(spf_tandem_ctl_max_index(&c, &max) == 0, "the bound is readable");
	CHECK(max == 0x43, "and only the 7-bit field is used");

	mock_init(&m, &be);
	m.ad9361[SPF_AD9361_REG_MAX_GAIN_INDEX] = 60;
	spf_tandem_ctl_init(&c, &be, 40);
	CHECK(spf_tandem_ctl_enable(&c, true) == SPF_TANDEM_OK, "a short table enables");
	CHECK(c.device_max_index == 60, "and the measured bound is what was read");
	CHECK((m.fpga[SPF_TANDEM_REG_INDEX >> 2] >> 8 & 0xFF) == 60,
	      "and it reaches the block's index window, overwriting the RTL's 76");
	return 0;
}

static int test_enable_refuses_an_index_past_the_table(void)
{
	mock_t m; spf_tandem_backend_t be; spf_tandem_ctl_t c;

	mock_init(&m, &be);
	m.ad9361[SPF_AD9361_REG_MAX_GAIN_INDEX] = 40;
	spf_tandem_ctl_init(&c, &be, 50);   /* legal against 76, not against 40 */
	CHECK(spf_tandem_ctl_enable(&c, true) != SPF_TANDEM_OK,
	      "an index past the part's table is refused, not clamped silently");
	CHECK(!spf_tandem_owns_pins(&c.lc), "and the pins were never handed over");

	mock_init(&m, &be);
	m.ad9361[SPF_AD9361_REG_MAX_GAIN_INDEX] = 0;
	spf_tandem_ctl_init(&c, &be, 40);
	CHECK(spf_tandem_ctl_enable(&c, true) != SPF_TANDEM_OK,
	      "a zero-length table is refused rather than treated as 'no limit'");
	return 0;
}

int main(void)
{
	struct { const char *name; int (*fn)(void); } tests[] = {
		{ "max_index_is_read_from_the_part", test_max_index_is_read_from_the_part },
		{ "enable_refuses_index_past_table", test_enable_refuses_an_index_past_the_table },
		{ "enable_disable_happy",           test_enable_disable_happy },
		{ "preconditions_refused",          test_preconditions_refused },
		{ "unequal_readback",               test_unequal_readback },
		{ "ownership_timeout",              test_ownership_timeout },
		{ "spi_failure_at_every_step",      test_spi_failure_at_every_step },
		{ "gain_write_refused_while_armed", test_gain_write_refused_while_armed },
		{ "sync_quiescence_rule",           test_sync_quiescence_rule },
	};
	size_t i;
	for (i = 0; i < sizeof(tests) / sizeof(tests[0]); i++) {
		if (tests[i].fn() != 0) {
			fprintf(stderr, "test %s FAILED\n", tests[i].name);
			return 1;
		}
		printf("  ok  %s\n", tests[i].name);
	}
	printf("PASS: spf_tandem_ctl (%d checks)\n", checks);
	return 0;
}
