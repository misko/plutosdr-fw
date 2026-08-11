/*
 * test_spf_tandem_lifecycle.c
 *
 * Native tests for the tandem ownership lifecycle. Mirrors the shape of RC17's
 * own lifecycle test, and covers the §8.4 list: every legal transition and the
 * rejection of every illegal one, stale epochs, the completed-session
 * tombstone, coalesced duplicate stops, bounded retry, the conflicting-operation
 * interlocks, and the two facts E-AGC1 measured on the part.
 */

#include "spf_tandem_lifecycle.h"

#include <assert.h>
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

/* drive a lifecycle all the way to tandem-auto */
static void go_active(spf_tandem_lifecycle_t *lc)
{
	lc->consumer_ready = true;
	lc->ensm_rx_active = true;
	assert(spf_tandem_begin(lc) == SPF_TANDEM_OK);
	assert(spf_tandem_pins_owned(lc) == SPF_TANDEM_OK);
	assert(spf_tandem_armed(lc, lc->epoch) == SPF_TANDEM_OK);
	assert(spf_tandem_activate(lc) == SPF_TANDEM_OK);
}

static int test_clean_lifecycle(void)
{
	spf_tandem_lifecycle_t lc;
	spf_tandem_init(&lc);

	CHECK(lc.state == SPF_TANDEM_LEGACY, "reset state is legacy");
	CHECK(!spf_tandem_busy(&lc), "legacy is not busy");
	CHECK(!spf_tandem_owns_pins(&lc), "legacy does not own the pins");
	CHECK(spf_tandem_gain_writable(&lc), "software may set gain while disarmed");

	go_active(&lc);
	CHECK(lc.state == SPF_TANDEM_ACTIVE, "reaches tandem-auto");
	CHECK(lc.epoch == 1, "first session takes epoch 1");
	CHECK(spf_tandem_owns_pins(&lc), "owns the pins while active");
	CHECK(!spf_tandem_gain_writable(&lc),
	      "software gain writes are refused once armed");

	CHECK(spf_tandem_request_stop(&lc, lc.epoch) == SPF_TANDEM_OK, "stop accepted");
	CHECK(lc.state == SPF_TANDEM_DISARMING, "enters disarming");
	CHECK(spf_tandem_released(&lc, lc.epoch) == SPF_TANDEM_OK, "release accepted");
	CHECK(!lc.pin_control_armed, "disarmed before ownership returned");
	CHECK(!lc.fpga_owns_pins, "ownership returned");
	CHECK(spf_tandem_reap(&lc) == SPF_TANDEM_OK, "reaped");
	CHECK(lc.state == SPF_TANDEM_LEGACY, "back to legacy");
	CHECK(lc.epoch_tomb == 1, "retired epoch is tombstoned");
	CHECK(spf_tandem_gain_writable(&lc), "gain writable again after disarm");
	return 0;
}

static int test_preconditions(void)
{
	spf_tandem_lifecycle_t lc;

	/* ENSM not RX-active: E-AGC1 H6 measured that edges are simply ignored */
	spf_tandem_init(&lc);
	lc.consumer_ready = true;
	lc.ensm_rx_active = false;
	CHECK(spf_tandem_begin(&lc) == SPF_TANDEM_ENOTRX,
	      "arming outside RX is refused, not attempted");
	CHECK(lc.state == SPF_TANDEM_LEGACY, "a refused arm changes nothing");

	/* consumer not ready */
	spf_tandem_init(&lc);
	lc.ensm_rx_active = true;
	lc.consumer_ready = false;
	CHECK(spf_tandem_begin(&lc) == SPF_TANDEM_ENOCONSUMER,
	      "arming without a ready consumer is refused");
	CHECK(lc.state == SPF_TANDEM_LEGACY, "still legacy");
	return 0;
}

static int test_arming_order_is_enforced(void)
{
	spf_tandem_lifecycle_t lc;
	spf_tandem_init(&lc);
	lc.consumer_ready = true;
	lc.ensm_rx_active = true;
	CHECK(spf_tandem_begin(&lc) == SPF_TANDEM_OK, "begin");

	/* arming 0x0FB before the FPGA holds the pins is the hazard §11 exists to
	 * prevent -- the pins float, so it is an uncommanded gain change */
	CHECK(spf_tandem_armed(&lc, lc.epoch) == SPF_TANDEM_ECONFLICT,
	      "arming before ownership is refused");
	CHECK(lc.state == SPF_TANDEM_FAULTED, "and faults rather than continuing");
	CHECK(!lc.pin_control_armed, "fails closed: not armed");
	return 0;
}

static int test_stale_epoch_and_tombstone(void)
{
	spf_tandem_lifecycle_t lc;
	uint8_t first;

	spf_tandem_init(&lc);
	go_active(&lc);
	first = lc.epoch;

	/* retire session 1 */
	CHECK(spf_tandem_request_stop(&lc, first) == SPF_TANDEM_OK, "stop 1");
	CHECK(spf_tandem_released(&lc, first) == SPF_TANDEM_OK, "release 1");
	CHECK(spf_tandem_reap(&lc) == SPF_TANDEM_OK, "reap 1");

	/* arm session 2 */
	go_active(&lc);
	CHECK(lc.epoch == (uint8_t)(first + 1), "second session takes a new epoch");

	/* a delayed stop for session 1 must be answered idempotently and must NOT
	 * disturb session 2 -- RC17's completed_stream_id, transposed */
	CHECK(spf_tandem_request_stop(&lc, first) == SPF_TANDEM_OK,
	      "delayed stop for a retired session succeeds");
	CHECK(lc.state == SPF_TANDEM_ACTIVE,
	      "and leaves the newer session untouched");
	CHECK(lc.duplicate_stop_count == 1, "it is counted as a duplicate");

	/* an acknowledgement carrying a retired epoch is counted and discarded */
	{
		spf_tandem_lifecycle_t l2;
		spf_tandem_init(&l2);
		l2.consumer_ready = true;
		l2.ensm_rx_active = true;
		CHECK(spf_tandem_begin(&l2) == SPF_TANDEM_OK, "begin");
		CHECK(spf_tandem_pins_owned(&l2) == SPF_TANDEM_OK, "pins");
		CHECK(spf_tandem_armed(&l2, (uint8_t)(l2.epoch + 7)) == SPF_TANDEM_EBUSY,
		      "an ack with the wrong epoch is rejected");
		CHECK(l2.stale_epoch_count == 1, "and counted");
		CHECK(l2.state == SPF_TANDEM_ARMING, "state is unchanged by it");
	}
	return 0;
}

static int test_epoch_never_zero(void)
{
	spf_tandem_lifecycle_t lc;
	int i;

	spf_tandem_init(&lc);
	/* wrap the 8-bit epoch all the way round and check it never lands on 0 */
	for (i = 0; i < 300; i++) {
		go_active(&lc);
		CHECK(lc.epoch != 0, "epoch is never zero, including across the wrap");
		CHECK(spf_tandem_request_stop(&lc, lc.epoch) == SPF_TANDEM_OK, "stop");
		CHECK(spf_tandem_released(&lc, lc.epoch) == SPF_TANDEM_OK, "release");
		CHECK(spf_tandem_reap(&lc) == SPF_TANDEM_OK, "reap");
	}
	return 0;
}

static int test_duplicate_stop_coalesced(void)
{
	spf_tandem_lifecycle_t lc;
	spf_tandem_init(&lc);
	go_active(&lc);

	CHECK(spf_tandem_request_stop(&lc, lc.epoch) == SPF_TANDEM_OK, "first stop");
	CHECK(spf_tandem_request_stop(&lc, lc.epoch) == SPF_TANDEM_OK, "second stop ok");
	CHECK(spf_tandem_request_stop(&lc, lc.epoch) == SPF_TANDEM_OK, "third stop ok");
	CHECK(lc.duplicate_stop_count == 2, "duplicates are coalesced and counted");
	CHECK(lc.state == SPF_TANDEM_DISARMING, "never applied twice");
	return 0;
}

static int test_conflicting_operations(void)
{
	spf_tandem_lifecycle_t lc;
	int op;

	spf_tandem_init(&lc);
	/* everything is permitted while legacy */
	for (op = 0; op < SPF_TANDEM_OP_COUNT; op++)
		CHECK(spf_tandem_check_op(&lc, (spf_tandem_op_t)op) == SPF_TANDEM_OK,
		      "legacy permits every operation");

	go_active(&lc);
	for (op = 0; op < SPF_TANDEM_OP_COUNT; op++)
		CHECK(spf_tandem_check_op(&lc, (spf_tandem_op_t)op) == SPF_TANDEM_ECONFLICT,
		      "every listed operation is refused while tandem owns the pins");

	CHECK(lc.refused_op_count[SPF_TANDEM_OP_GAIN_WRITE] == 1,
	      "refusals are counted per operation");
	CHECK(lc.refused_op_count[SPF_TANDEM_OP_HYBRID_MODE] == 1,
	      "hybrid mode is refused: it re-arms CTRL_IN2 behind the interlock");

	/* still refused while releasing, not only while active */
	CHECK(spf_tandem_request_stop(&lc, lc.epoch) == SPF_TANDEM_OK, "stop");
	CHECK(spf_tandem_check_op(&lc, SPF_TANDEM_OP_GAIN_WRITE) == SPF_TANDEM_ECONFLICT,
	      "refused while still releasing, not only while active");
	return 0;
}

static int test_ensm_transition_while_armed(void)
{
	spf_tandem_lifecycle_t lc;
	spf_tandem_init(&lc);
	go_active(&lc);

	/* O-6: the pins go deaf with no fault anywhere, so the runtime has to be
	 * the thing that notices */
	CHECK(spf_tandem_ensm_left_rx(&lc) == SPF_TANDEM_ENOTRX,
	      "leaving RX while armed is a synchronisation fault");
	CHECK(lc.state == SPF_TANDEM_FAULTED, "and takes the controller out of active");
	CHECK(!lc.pin_control_armed, "fails closed: disarmed");
	CHECK(!lc.fpga_owns_pins, "fails closed: ownership dropped");

	/* leaving RX while legacy is simply a state update, not a fault */
	{
		spf_tandem_lifecycle_t l2;
		spf_tandem_init(&l2);
		l2.ensm_rx_active = true;
		CHECK(spf_tandem_ensm_left_rx(&l2) == SPF_TANDEM_OK,
		      "leaving RX while legacy is not a fault");
		CHECK(l2.state == SPF_TANDEM_LEGACY, "still legacy");
	}
	return 0;
}

static int test_fault_recovery_and_retry(void)
{
	spf_tandem_lifecycle_t lc;
	spf_tandem_init(&lc);
	go_active(&lc);
	spf_tandem_fault(&lc, SPF_TANDEM_ECONFLICT);

	CHECK(lc.state == SPF_TANDEM_FAULTED, "faulted");
	CHECK(spf_tandem_begin(&lc) == SPF_TANDEM_EFAULTED,
	      "arming from faulted is refused");
	CHECK(!spf_tandem_retryable(SPF_TANDEM_EFAULTED),
	      "a fault is never retryable");
	CHECK(spf_tandem_retryable(SPF_TANDEM_EBUSY),
	      "a transient busy is retryable, boundedly");

	CHECK(spf_tandem_clear_fault(&lc) == SPF_TANDEM_OK, "explicit recovery");
	CHECK(lc.state == SPF_TANDEM_LEGACY, "recovers to legacy");
	go_active(&lc);
	CHECK(lc.state == SPF_TANDEM_ACTIVE, "and can arm again afterwards");
	return 0;
}

static int test_illegal_transitions(void)
{
	spf_tandem_lifecycle_t lc;

	spf_tandem_init(&lc);
	CHECK(spf_tandem_pins_owned(&lc) == SPF_TANDEM_EBUSY, "pins_owned from legacy");
	CHECK(spf_tandem_armed(&lc, 1) == SPF_TANDEM_EBUSY, "armed from legacy");
	CHECK(spf_tandem_activate(&lc) == SPF_TANDEM_EBUSY, "activate from legacy");
	CHECK(spf_tandem_released(&lc, 1) == SPF_TANDEM_EBUSY, "released from legacy");
	CHECK(spf_tandem_reap(&lc) == SPF_TANDEM_EBUSY, "reap from legacy");

	go_active(&lc);
	CHECK(spf_tandem_begin(&lc) == SPF_TANDEM_EBUSY, "begin while active");
	CHECK(spf_tandem_activate(&lc) == SPF_TANDEM_EBUSY, "activate twice");
	CHECK(spf_tandem_reap(&lc) == SPF_TANDEM_EBUSY, "reap while active");
	return 0;
}

static int test_null_safety(void)
{
	CHECK(spf_tandem_begin(NULL) == SPF_TANDEM_EINVAL, "begin(NULL)");
	CHECK(spf_tandem_request_stop(NULL, 1) == SPF_TANDEM_EINVAL, "stop(NULL)");
	CHECK(!spf_tandem_owns_pins(NULL), "owns_pins(NULL)");
	CHECK(!spf_tandem_gain_writable(NULL), "gain_writable(NULL) is closed");
	CHECK(spf_tandem_busy(NULL), "busy(NULL) is conservative");
	spf_tandem_init(NULL);            /* must not crash */
	return 0;
}

int main(void)
{
	struct { const char *name; int (*fn)(void); } tests[] = {
		{ "clean_lifecycle",            test_clean_lifecycle },
		{ "preconditions",              test_preconditions },
		{ "arming_order_is_enforced",   test_arming_order_is_enforced },
		{ "stale_epoch_and_tombstone",  test_stale_epoch_and_tombstone },
		{ "epoch_never_zero",           test_epoch_never_zero },
		{ "duplicate_stop_coalesced",   test_duplicate_stop_coalesced },
		{ "conflicting_operations",     test_conflicting_operations },
		{ "ensm_transition_while_armed",test_ensm_transition_while_armed },
		{ "fault_recovery_and_retry",   test_fault_recovery_and_retry },
		{ "illegal_transitions",        test_illegal_transitions },
		{ "null_safety",                test_null_safety },
	};
	size_t i;

	for (i = 0; i < sizeof(tests) / sizeof(tests[0]); i++) {
		if (tests[i].fn() != 0) {
			fprintf(stderr, "test %s FAILED\n", tests[i].name);
			return 1;
		}
		printf("  ok  %s\n", tests[i].name);
	}
	printf("PASS: spf_tandem_lifecycle (%d checks)\n", checks);
	return 0;
}
