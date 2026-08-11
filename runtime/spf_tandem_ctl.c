/*
 * spf_tandem_ctl.c -- the §11 enable and disable transactions.
 *
 * The ordering in here is the safety property, not a style choice. See the
 * comments at each step; every one of them is either a measured hardware fact
 * from E-AGC1 or a lesson carried from an earlier candidate.
 */

#include "spf_tandem_ctl.h"

#include <stdio.h>
#include <string.h>

#define FAIL(c, rc, ...)                                                       \
	do {                                                                       \
		snprintf((c)->last_error_detail, sizeof((c)->last_error_detail),        \
		         __VA_ARGS__);                                                  \
		return (rc);                                                            \
	} while (0)

void spf_tandem_ctl_init(spf_tandem_ctl_t *c, const spf_tandem_backend_t *be,
                         uint8_t initial_index)
{
	if (c == NULL)
		return;
	memset(c, 0, sizeof(*c));
	spf_tandem_init(&c->lc);
	c->be = be;
	c->initial_index = initial_index;
	c->retry_limit = 8;
}

int spf_tandem_ctl_max_index(spf_tandem_ctl_t *c, uint8_t *out)
{
	uint8_t raw;

	if (c == NULL || out == NULL || c->be == NULL || c->be->ad9361_read == NULL)
		return -1;
	if (c->be->ad9361_read(c->be->ctx, SPF_AD9361_REG_MAX_GAIN_INDEX, &raw) != 0)
		return -1;
	*out = (uint8_t)(raw & SPF_AD9361_MAX_GAIN_INDEX_MASK);
	return 0;
}

/* Read-modify-write is mandatory: direct_reg_access writes the whole byte, and
 * 0x0FB carries live bits besides [1:0] on the shipped builds -- E-AGC1 found
 * bit 3 set, so a bare 0x03 would have cleared it. */
static int ad9361_rmw(const spf_tandem_backend_t *be, uint16_t reg,
                      uint8_t clear, uint8_t set)
{
	uint8_t v;
	int rc = be->ad9361_read(be->ctx, reg, &v);
	if (rc != 0)
		return rc;
	v = (uint8_t)((v & (uint8_t)~clear) | set);
	return be->ad9361_write(be->ctx, reg, v);
}

static bool ensm_is_rx_active(const char *s)
{
	/* E-AGC1 H6: edges are honoured in fdd and ignored in alert and sleep.
	 * `wait` is advertised but unreachable, so it is not treated as a state. */
	return strcmp(s, "fdd") == 0 || strcmp(s, "rx") == 0 ||
	       strcmp(s, "pinctrl_fdd_indep") == 0;
}

spf_tandem_rc_t spf_tandem_ctl_enable(spf_tandem_ctl_t *c, bool auto_mode)
{
	const spf_tandem_backend_t *be;
	char ensm[32];
	bool full = false;
	uint32_t id = 0, status = 0;
	uint8_t rx1 = 0, rx2 = 0;
	spf_tandem_rc_t rc;
	unsigned tries;

	if (c == NULL || c->be == NULL)
		return SPF_TANDEM_EINVAL;
	be = c->be;
	c->last_error_detail[0] = '\0';

	/* step 1: the block must actually be present */
	if (be->fpga_read(be->ctx, SPF_TANDEM_REG_ID, &id) != 0)
		FAIL(c, SPF_TANDEM_EINVAL, "step 1: FPGA ID register unreadable");
	if (id != SPF_TANDEM_ID_MAGIC)
		FAIL(c, SPF_TANDEM_EINVAL, "step 1: FPGA ID 0x%08x is not TAG1", id);

	/* step 2: full gain table. Split table reuses the same four pins for
	 * LMT/LPF selection and cannot do per-channel increment and decrement. */
	if (be->full_gain_table(be->ctx, &full) != 0)
		FAIL(c, SPF_TANDEM_EINVAL, "step 2: gain table mode unreadable");
	if (!full)
		FAIL(c, SPF_TANDEM_ECONFLICT, "step 2: split gain table cannot support tandem");

	/* step 3: the ENSM must be RX-active BEFORE arming, or every edge the
	 * controller emits is silently ignored (E-AGC1 H6) */
	if (be->ensm_get(be->ctx, ensm, sizeof(ensm)) != 0)
		FAIL(c, SPF_TANDEM_EINVAL, "step 3: ENSM state unreadable");
	if (!ensm_is_rx_active(ensm))
		FAIL(c, SPF_TANDEM_ENOTRX, "step 3: ENSM is '%s', not RX-active", ensm);
	c->lc.ensm_rx_active = true;
	c->lc.consumer_ready = true;

	rc = spf_tandem_begin(&c->lc);
	if (rc != SPF_TANDEM_OK)
		FAIL(c, rc, "step 3: lifecycle refused to begin (%s)",
		     spf_tandem_rc_name(rc));

	/* step 4: both channels to manual gain */
	if (be->mode_set(be->ctx, 0, "manual") != 0 ||
	    be->mode_set(be->ctx, 1, "manual") != 0) {
		spf_tandem_fault(&c->lc, SPF_TANDEM_EINVAL);
		FAIL(c, SPF_TANDEM_EINVAL, "step 4: could not set manual gain mode");
	}

	/* step 4b: the clamp bound comes from the part, never from a constant
	 * (D-8). A driver-loaded gain table can be shorter than the chip default
	 * of 76, and clamping the index model to a stale bound would walk it off
	 * the end of the table it exists to model. */
	if (spf_tandem_ctl_max_index(c, &c->device_max_index) != 0) {
		spf_tandem_fault(&c->lc, SPF_TANDEM_EINVAL);
		FAIL(c, SPF_TANDEM_EINVAL, "step 4b: max gain index unreadable");
	}
	if (c->device_max_index == 0) {
		spf_tandem_fault(&c->lc, SPF_TANDEM_EINVAL);
		FAIL(c, SPF_TANDEM_EINVAL, "step 4b: part reports a zero-length gain table");
	}
	if (c->initial_index > c->device_max_index) {
		spf_tandem_fault(&c->lc, SPF_TANDEM_EINVAL);
		FAIL(c, SPF_TANDEM_EINVAL,
		     "step 4b: initial index %u exceeds the part's maximum %u",
		     c->initial_index, c->device_max_index);
	}

	/* step 4c: push the measured bound into the block's index window. The
	 * RTL's reset default is 76, which is the chip default and therefore the
	 * same hard-coded constant D-8 rejects -- it is a safe starting value, not
	 * an authority. Overwriting it from the part is what makes the clamp
	 * correct on a radio whose driver loaded a shorter table. idx_min stays 0;
	 * the narrow D-7 window is an operator choice, not something enable
	 * imposes. */
	if (be->fpga_write(be->ctx, SPF_TANDEM_REG_INDEX,
	                   ((uint32_t)c->initial_index << 16) |
	                   ((uint32_t)c->device_max_index << 8)) != 0) {
		spf_tandem_fault(&c->lc, SPF_TANDEM_EINVAL);
		FAIL(c, SPF_TANDEM_EINVAL, "step 4c: could not program the index window");
	}

	/* step 5: program the common index. This is the LAST point at which
	 * software can set gain -- after step 11 every such write is dropped with
	 * a success return (E-AGC1). */
	if (be->gain_set(be->ctx, 0, c->initial_index) != 0 ||
	    be->gain_set(be->ctx, 1, c->initial_index) != 0) {
		spf_tandem_fault(&c->lc, SPF_TANDEM_EINVAL);
		FAIL(c, SPF_TANDEM_EINVAL, "step 5: could not program the initial index");
	}

	/* step 6: read back and require equality */
	if (be->gain_get(be->ctx, 0, &rx1) != 0 || be->gain_get(be->ctx, 1, &rx2) != 0) {
		spf_tandem_fault(&c->lc, SPF_TANDEM_EINVAL);
		FAIL(c, SPF_TANDEM_EINVAL, "step 6: could not read the indices back");
	}
	if (rx1 != rx2 || rx1 != c->initial_index) {
		spf_tandem_fault(&c->lc, SPF_TANDEM_ECONFLICT);
		FAIL(c, SPF_TANDEM_ECONFLICT,
		     "step 6: read-back unequal (rx1=%u rx2=%u wanted %u)",
		     rx1, rx2, c->initial_index);
	}
	c->last_rx1 = rx1;
	c->last_rx2 = rx2;

	/* step 7: detector page and output enables */
	if (be->ad9361_write(be->ctx, SPF_AD9361_REG_CTRL_OUT_PTR,
	                     SPF_CTRL_OUT_PAGE_DETECTORS) != 0 ||
	    be->ad9361_write(be->ctx, SPF_AD9361_REG_CTRL_OUT_EN, 0xFF) != 0) {
		spf_tandem_fault(&c->lc, SPF_TANDEM_EINVAL);
		FAIL(c, SPF_TANDEM_EINVAL, "step 7: could not select CTRL_OUT page 0x03");
	}

	/* step 8: one index per pulse, so the FPGA model is auditable. Both step
	 * fields store value-1, and 0x0FE also holds the Peak Overload Wait Time
	 * in [4:0] -- read-modify-write or that gets destroyed. */
	if (ad9361_rmw(be, SPF_AD9361_REG_AGC_CONFIG_3, 0xE0, 0x00) != 0 ||
	    ad9361_rmw(be, SPF_AD9361_REG_PEAK_WAIT_TIME, 0xE0, 0x00) != 0) {
		spf_tandem_fault(&c->lc, SPF_TANDEM_EINVAL);
		FAIL(c, SPF_TANDEM_EINVAL, "step 8: could not program the gain step size");
	}

	/* step 10: hand the pins to the FPGA, held low, before anything is armed */
	if (be->fpga_write(be->ctx, SPF_TANDEM_REG_CTRL, 1u) != 0) {
		spf_tandem_fault(&c->lc, SPF_TANDEM_EINVAL);
		FAIL(c, SPF_TANDEM_EINVAL, "step 10: could not request ownership");
	}

	/* bounded retry, only against a transient ownership handoff */
	for (tries = 0; tries <= c->retry_limit; tries++) {
		if (be->fpga_read(be->ctx, SPF_TANDEM_REG_STATUS, &status) != 0) {
			spf_tandem_fault(&c->lc, SPF_TANDEM_EINVAL);
			FAIL(c, SPF_TANDEM_EINVAL, "step 10: STATUS unreadable");
		}
		if ((status & (1u << 4)) != 0)          /* fpga_owns */
			break;
		c->retries_used++;
	}
	if ((status & (1u << 4)) == 0) {
		spf_tandem_fault(&c->lc, SPF_TANDEM_EBUSY);
		FAIL(c, SPF_TANDEM_EBUSY,
		     "step 10: ownership not acknowledged after %u retries", c->retry_limit);
	}
	(void)spf_tandem_pins_owned(&c->lc);

	/* step 11: ONLY NOW arm pin control, read-modify-write */
	if (ad9361_rmw(be, SPF_AD9361_REG_AGC_CONFIG_2, 0x00,
	               SPF_AD9361_PIN_CTRL_MASK) != 0) {
		/* roll back: give the pins back before giving up */
		(void)be->fpga_write(be->ctx, SPF_TANDEM_REG_CTRL, 0u);
		spf_tandem_fault(&c->lc, SPF_TANDEM_EINVAL);
		FAIL(c, SPF_TANDEM_EINVAL, "step 11: could not arm 0x0FB");
	}

	rc = spf_tandem_armed(&c->lc, c->lc.epoch);
	if (rc != SPF_TANDEM_OK) {
		(void)ad9361_rmw(be, SPF_AD9361_REG_AGC_CONFIG_2,
		                 SPF_AD9361_PIN_CTRL_MASK, 0x00);
		(void)be->fpga_write(be->ctx, SPF_TANDEM_REG_CTRL, 0u);
		FAIL(c, rc, "step 11: arm not acknowledged (%s)", spf_tandem_rc_name(rc));
	}

	/* step 12: open the policy gate only after success is established */
	if (auto_mode) {
		if (be->fpga_write(be->ctx, SPF_TANDEM_REG_CTRL, 2u) != 0) {
			/*
			 * Roll back in the reverse of the order that built it up. Without
			 * this the caller sees a failed enable while the part is armed for
			 * pin control and the block owns the pins -- the gain is then
			 * frozen wherever step 5 left it, host gain writes are accepted
			 * and silently dropped (E-AGC1), and nothing anywhere reports why.
			 * A half-applied enable is worse than one that never started.
			 */
			(void)ad9361_rmw(be, SPF_AD9361_REG_AGC_CONFIG_2,
			                 SPF_AD9361_PIN_CTRL_MASK, 0x00);
			(void)be->fpga_write(be->ctx, SPF_TANDEM_REG_CTRL, 0u);
			spf_tandem_fault(&c->lc, SPF_TANDEM_EINVAL);
			FAIL(c, SPF_TANDEM_EINVAL, "step 12: could not enter tandem-auto");
		}
		(void)spf_tandem_activate(&c->lc);
	}
	return SPF_TANDEM_OK;
}

spf_tandem_rc_t spf_tandem_ctl_disable(spf_tandem_ctl_t *c, const char *restore_mode)
{
	const spf_tandem_backend_t *be;
	spf_tandem_rc_t rc;

	if (c == NULL || c->be == NULL)
		return SPF_TANDEM_EINVAL;
	be = c->be;
	c->last_error_detail[0] = '\0';

	rc = spf_tandem_request_stop(&c->lc, c->lc.epoch);
	if (rc != SPF_TANDEM_OK)
		FAIL(c, rc, "disable: lifecycle refused the stop (%s)",
		     spf_tandem_rc_name(rc));

	/* ask the block to stop and hold the outputs low */
	if (be->fpga_write(be->ctx, SPF_TANDEM_REG_CTRL, 0u) != 0)
		FAIL(c, SPF_TANDEM_EINVAL, "disable: could not request stop");

	/* disarm BEFORE the pins are released. The other order leaves armed pin
	 * control over pins the PS may drive or leave floating. */
	if (ad9361_rmw(be, SPF_AD9361_REG_AGC_CONFIG_2,
	               SPF_AD9361_PIN_CTRL_MASK, 0x00) != 0)
		FAIL(c, SPF_TANDEM_EINVAL, "disable: could not disarm 0x0FB");

	rc = spf_tandem_released(&c->lc, c->lc.epoch);
	if (rc != SPF_TANDEM_OK)
		FAIL(c, rc, "disable: release rejected (%s)", spf_tandem_rc_name(rc));

	/* only now restore the legacy gain mode; software writes work again */
	if (restore_mode != NULL) {
		if (be->mode_set(be->ctx, 0, restore_mode) != 0 ||
		    be->mode_set(be->ctx, 1, restore_mode) != 0)
			FAIL(c, SPF_TANDEM_EINVAL, "disable: could not restore mode '%s'",
			     restore_mode);
	}

	rc = spf_tandem_reap(&c->lc);
	if (rc != SPF_TANDEM_OK)
		FAIL(c, rc, "disable: reap rejected (%s)", spf_tandem_rc_name(rc));
	return SPF_TANDEM_OK;
}

spf_tandem_rc_t spf_tandem_ctl_check_sync(spf_tandem_ctl_t *c)
{
	const spf_tandem_backend_t *be;
	uint32_t status = 0, expect = 0;
	uint8_t rx1 = 0, rx2 = 0;

	if (c == NULL || c->be == NULL)
		return SPF_TANDEM_EINVAL;
	be = c->be;

	if (!spf_tandem_owns_pins(&c->lc))
		return SPF_TANDEM_OK;

	if (be->fpga_read(be->ctx, SPF_TANDEM_REG_STATUS, &status) != 0)
		FAIL(c, SPF_TANDEM_EINVAL, "sync: STATUS unreadable");

	/* §6.2 quiescence rule: a read that straddles a transition legitimately
	 * differs by a step, so only compare when nothing is in flight. */
	if ((status & (1u << 6)) != 0 || (status & (1u << 7)) != 0)
		return SPF_TANDEM_OK;      /* pulse in flight or cooling down */

	if (be->fpga_read(be->ctx, SPF_TANDEM_REG_EXPECT, &expect) != 0)
		FAIL(c, SPF_TANDEM_EINVAL, "sync: EXPECT unreadable");
	if (be->gain_get(be->ctx, 0, &rx1) != 0 || be->gain_get(be->ctx, 1, &rx2) != 0)
		FAIL(c, SPF_TANDEM_EINVAL, "sync: gain read-back failed");

	if (rx1 == (uint8_t)expect && rx2 == (uint8_t)expect) {
		c->lc.stale_epoch_count = c->lc.stale_epoch_count;  /* agreement */
		c->last_rx1 = rx1;
		c->last_rx2 = rx2;
		return SPF_TANDEM_OK;
	}

	/* one disagreement is not a fault; two consecutive ones are */
	if (c->last_rx1 == rx1 && c->last_rx2 == rx2) {
		spf_tandem_fault(&c->lc, SPF_TANDEM_ECONFLICT);
		FAIL(c, SPF_TANDEM_ECONFLICT,
		     "sync: two consecutive quiescent disagreements (rx1=%u rx2=%u expect=%u)",
		     rx1, rx2, (uint8_t)expect);
	}
	c->last_rx1 = rx1;
	c->last_rx2 = rx2;
	return SPF_TANDEM_OK;
}

int spf_tandem_ctl_status(spf_tandem_ctl_t *c, char *buf, size_t len)
{
	uint32_t status = 0, epoch = 0, expect = 0, fault = 0;

	if (c == NULL || buf == NULL || len == 0)
		return -1;
	if (c->be != NULL) {
		(void)c->be->fpga_read(c->be->ctx, SPF_TANDEM_REG_STATUS, &status);
		(void)c->be->fpga_read(c->be->ctx, SPF_TANDEM_REG_EPOCH, &epoch);
		(void)c->be->fpga_read(c->be->ctx, SPF_TANDEM_REG_EXPECT, &expect);
		(void)c->be->fpga_read(c->be->ctx, SPF_TANDEM_REG_FAULT, &fault);
	}
	return snprintf(buf, len,
		"{\"state\":\"%s\",\"epoch\":%u,\"tombstone\":%u,"
		"\"owns_pins\":%s,\"pin_control_armed\":%s,\"gain_writable\":%s,"
		"\"expected_index\":%u,\"rx1_index\":%u,\"rx2_index\":%u,"
		"\"fault\":%u,\"transitions\":%u,\"stale_epoch\":%u,"
		"\"duplicate_stop\":%u,\"retries_used\":%u,"
		"\"device_max_index\":%u,\"last_error\":\"%s\"}",
		spf_tandem_state_name(c->lc.state),
		c->lc.epoch, c->lc.epoch_tomb,
		spf_tandem_owns_pins(&c->lc) ? "true" : "false",
		c->lc.pin_control_armed ? "true" : "false",
		spf_tandem_gain_writable(&c->lc) ? "true" : "false",
		(unsigned)(uint8_t)expect, c->last_rx1, c->last_rx2,
		fault, c->lc.transition_count, c->lc.stale_epoch_count,
		c->lc.duplicate_stop_count, c->retries_used, c->device_max_index,
		c->last_error_detail);
}
