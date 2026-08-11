/*
 * spf_tandem_lifecycle.c -- see the header for why this is a transposition of
 * RC17's spf_ip_rx_lifecycle rather than an independent design.
 */

#include "spf_tandem_lifecycle.h"

#include <string.h>

void spf_tandem_init(spf_tandem_lifecycle_t *lc)
{
	if (lc == NULL)
		return;
	memset(lc, 0, sizeof(*lc));
	lc->state = SPF_TANDEM_LEGACY;
	lc->epoch = 0;                 /* the first begin() takes epoch 1 */
	lc->consumer_ready = false;
	lc->ensm_rx_active = false;
}

bool spf_tandem_busy(const spf_tandem_lifecycle_t *lc)
{
	return lc == NULL || lc->state != SPF_TANDEM_LEGACY;
}

bool spf_tandem_owns_pins(const spf_tandem_lifecycle_t *lc)
{
	if (lc == NULL)
		return false;
	return lc->state == SPF_TANDEM_ARMING ||
	       lc->state == SPF_TANDEM_OWNED_IDLE ||
	       lc->state == SPF_TANDEM_ACTIVE ||
	       lc->state == SPF_TANDEM_DISARMING;
}

bool spf_tandem_gain_writable(const spf_tandem_lifecycle_t *lc)
{
	if (lc == NULL)
		return false;
	/*
	 * Measured on the part (E-AGC1): once 0x0FB[1:0] is armed, a hardwaregain
	 * write returns success and is dropped, and the readback reports the
	 * pin-controlled index. Silent success is worse than an error, so the
	 * boundary is drawn here rather than at the device.
	 */
	return !lc->pin_control_armed;
}

static void bump(spf_tandem_lifecycle_t *lc)
{
	lc->transition_count++;
}

spf_tandem_rc_t spf_tandem_begin(spf_tandem_lifecycle_t *lc)
{
	if (lc == NULL)
		return SPF_TANDEM_EINVAL;
	if (lc->state == SPF_TANDEM_FAULTED)
		return (lc->last_error = SPF_TANDEM_EFAULTED);
	if (lc->state != SPF_TANDEM_LEGACY)
		return (lc->last_error = SPF_TANDEM_EBUSY);

	/*
	 * Both are preconditions rather than warnings. Arming outside RX gives a
	 * controller that believes it owns gain while every edge it emits is
	 * ignored (E-AGC1 H6); arming without a consumer loses events from the
	 * first transition (RC11's lesson, carried into §2.3).
	 */
	if (!lc->ensm_rx_active)
		return (lc->last_error = SPF_TANDEM_ENOTRX);
	if (!lc->consumer_ready)
		return (lc->last_error = SPF_TANDEM_ENOCONSUMER);

	lc->epoch = (uint8_t)(lc->epoch + 1u);
	if (lc->epoch == 0u)
		lc->epoch = 1u;            /* never zero, never reused */
	lc->state = SPF_TANDEM_ARMING;
	bump(lc);
	return (lc->last_error = SPF_TANDEM_OK);
}

spf_tandem_rc_t spf_tandem_pins_owned(spf_tandem_lifecycle_t *lc)
{
	if (lc == NULL)
		return SPF_TANDEM_EINVAL;
	if (lc->state != SPF_TANDEM_ARMING)
		return (lc->last_error = SPF_TANDEM_EBUSY);
	lc->fpga_owns_pins = true;
	bump(lc);
	return (lc->last_error = SPF_TANDEM_OK);
}

spf_tandem_rc_t spf_tandem_armed(spf_tandem_lifecycle_t *lc, uint8_t ack_epoch)
{
	if (lc == NULL)
		return SPF_TANDEM_EINVAL;
	if (lc->state != SPF_TANDEM_ARMING)
		return (lc->last_error = SPF_TANDEM_EBUSY);
	if (ack_epoch != lc->epoch) {
		lc->stale_epoch_count++;   /* a late ack from a previous arm */
		return (lc->last_error = SPF_TANDEM_EBUSY);
	}
	if (!lc->fpga_owns_pins) {
		/*
		 * §11: pin control may only be armed after the FPGA owns the pins and
		 * is holding them low. The pins float, so arming first is an
		 * uncommanded gain change on both receivers.
		 */
		spf_tandem_fault(lc, SPF_TANDEM_ECONFLICT);
		return SPF_TANDEM_ECONFLICT;
	}
	lc->pin_control_armed = true;
	lc->state = SPF_TANDEM_OWNED_IDLE;
	bump(lc);
	return (lc->last_error = SPF_TANDEM_OK);
}

spf_tandem_rc_t spf_tandem_activate(spf_tandem_lifecycle_t *lc)
{
	if (lc == NULL)
		return SPF_TANDEM_EINVAL;
	if (lc->state != SPF_TANDEM_OWNED_IDLE)
		return (lc->last_error = SPF_TANDEM_EBUSY);
	lc->state = SPF_TANDEM_ACTIVE;
	bump(lc);
	return (lc->last_error = SPF_TANDEM_OK);
}

spf_tandem_rc_t spf_tandem_request_stop(spf_tandem_lifecycle_t *lc, uint8_t epoch)
{
	if (lc == NULL)
		return SPF_TANDEM_EINVAL;

	/* A delayed or duplicated stop for a session that already retired is
	 * answered from the tombstone, idempotently, without touching a session
	 * armed since. Straight from RC17's completed_stream_id. */
	if (epoch != 0u && epoch == lc->epoch_tomb && epoch != lc->epoch) {
		lc->duplicate_stop_count++;
		return (lc->last_error = SPF_TANDEM_OK);
	}
	if (epoch != 0u && epoch != lc->epoch) {
		lc->stale_epoch_count++;
		return (lc->last_error = SPF_TANDEM_EINVAL);
	}
	if (lc->state == SPF_TANDEM_DISARMING ||
	    lc->state == SPF_TANDEM_RELEASABLE) {
		lc->duplicate_stop_count++;   /* coalesced, never applied twice */
		return (lc->last_error = SPF_TANDEM_OK);
	}
	if (lc->state != SPF_TANDEM_ARMING &&
	    lc->state != SPF_TANDEM_OWNED_IDLE &&
	    lc->state != SPF_TANDEM_ACTIVE)
		return (lc->last_error = SPF_TANDEM_EINVAL);

	lc->state = SPF_TANDEM_DISARMING;
	bump(lc);
	return (lc->last_error = SPF_TANDEM_OK);
}

spf_tandem_rc_t spf_tandem_released(spf_tandem_lifecycle_t *lc, uint8_t epoch)
{
	if (lc == NULL)
		return SPF_TANDEM_EINVAL;
	if (lc->state != SPF_TANDEM_DISARMING)
		return (lc->last_error = SPF_TANDEM_EBUSY);
	if (epoch != lc->epoch) {
		lc->stale_epoch_count++;
		return (lc->last_error = SPF_TANDEM_EINVAL);
	}
	/*
	 * Ordering is the safety property: disarm before the pins are released,
	 * never after. Reported released only once both are true.
	 */
	lc->pin_control_armed = false;
	lc->fpga_owns_pins = false;
	lc->state = SPF_TANDEM_RELEASABLE;
	bump(lc);
	return (lc->last_error = SPF_TANDEM_OK);
}

spf_tandem_rc_t spf_tandem_reap(spf_tandem_lifecycle_t *lc)
{
	if (lc == NULL)
		return SPF_TANDEM_EINVAL;
	if (lc->state != SPF_TANDEM_RELEASABLE)
		return (lc->last_error = SPF_TANDEM_EBUSY);
	lc->epoch_tomb = lc->epoch;
	lc->state = SPF_TANDEM_LEGACY;
	bump(lc);
	return (lc->last_error = SPF_TANDEM_OK);
}

spf_tandem_rc_t spf_tandem_ensm_left_rx(spf_tandem_lifecycle_t *lc)
{
	if (lc == NULL)
		return SPF_TANDEM_EINVAL;
	lc->ensm_rx_active = false;
	if (!spf_tandem_owns_pins(lc))
		return (lc->last_error = SPF_TANDEM_OK);
	/*
	 * O-6. The part does not fault and neither does the controller: the pins
	 * simply stop having any effect, so expected_index would drift away from
	 * hardware with nothing local to detect it. Treat it as a synchronisation
	 * fault and disarm rather than continue issuing pulses at a deaf part.
	 */
	spf_tandem_fault(lc, SPF_TANDEM_ENOTRX);
	return SPF_TANDEM_ENOTRX;
}

void spf_tandem_fault(spf_tandem_lifecycle_t *lc, spf_tandem_rc_t why)
{
	if (lc == NULL)
		return;
	lc->pin_control_armed = false;   /* fail closed */
	lc->fpga_owns_pins = false;
	lc->state = SPF_TANDEM_FAULTED;
	lc->last_error = why;
	bump(lc);
}

spf_tandem_rc_t spf_tandem_clear_fault(spf_tandem_lifecycle_t *lc)
{
	if (lc == NULL)
		return SPF_TANDEM_EINVAL;
	if (lc->state != SPF_TANDEM_FAULTED)
		return SPF_TANDEM_EINVAL;
	lc->state = SPF_TANDEM_LEGACY;
	lc->last_error = SPF_TANDEM_OK;
	bump(lc);
	return SPF_TANDEM_OK;
}

spf_tandem_rc_t spf_tandem_check_op(spf_tandem_lifecycle_t *lc, spf_tandem_op_t op)
{
	if (lc == NULL || op >= SPF_TANDEM_OP_COUNT)
		return SPF_TANDEM_EINVAL;

	/* Everything in this list is refused whenever the FPGA owns the pins or is
	 * still releasing them -- §6.3. Legacy and faulted states allow them. */
	if (!spf_tandem_owns_pins(lc))
		return SPF_TANDEM_OK;

	lc->refused_op_count[op]++;
	return SPF_TANDEM_ECONFLICT;
}

bool spf_tandem_retryable(spf_tandem_rc_t rc)
{
	/* Bounded retry only for a transient ownership handoff. Never against a
	 * fault -- RC13/RC14's lesson, made explicit. */
	return rc == SPF_TANDEM_EBUSY;
}

const char *spf_tandem_state_name(spf_tandem_state_t s)
{
	switch (s) {
	case SPF_TANDEM_LEGACY:     return "legacy";
	case SPF_TANDEM_ARMING:     return "arming";
	case SPF_TANDEM_OWNED_IDLE: return "tandem-hold";
	case SPF_TANDEM_ACTIVE:     return "tandem-auto";
	case SPF_TANDEM_DISARMING:  return "disarming";
	case SPF_TANDEM_RELEASABLE: return "releasable";
	case SPF_TANDEM_FAULTED:    return "faulted";
	default:                    return "unknown";
	}
}

const char *spf_tandem_rc_name(spf_tandem_rc_t rc)
{
	switch (rc) {
	case SPF_TANDEM_OK:           return "ok";
	case SPF_TANDEM_EBUSY:        return "busy";
	case SPF_TANDEM_EINVAL:       return "invalid";
	case SPF_TANDEM_EFAULTED:     return "faulted";
	case SPF_TANDEM_ENOTRX:       return "ensm-not-rx";
	case SPF_TANDEM_ENOCONSUMER:  return "consumer-not-ready";
	case SPF_TANDEM_ECONFLICT:    return "conflicting-operation";
	default:                      return "unknown";
	}
}

const char *spf_tandem_op_name(spf_tandem_op_t op)
{
	switch (op) {
	case SPF_TANDEM_OP_GAIN_WRITE:     return "gain-write";
	case SPF_TANDEM_OP_GAIN_TABLE:     return "gain-table";
	case SPF_TANDEM_OP_SPLIT_TABLE:    return "split-table";
	case SPF_TANDEM_OP_FIR_DECIMATION: return "fir-decimation";
	case SPF_TANDEM_OP_SAMPLE_RATE:    return "sample-rate";
	case SPF_TANDEM_OP_BAND_CROSSING:  return "band-crossing";
	case SPF_TANDEM_OP_GAIN_MODE:      return "gain-mode";
	case SPF_TANDEM_OP_HYBRID_MODE:    return "hybrid-mode";
	case SPF_TANDEM_OP_INITIALIZE:     return "initialize";
	default:                           return "unknown";
	}
}
