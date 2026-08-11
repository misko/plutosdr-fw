/*
 * spf_tandem_ctl.h
 *
 * The transactional control layer: it drives the §11 enable and disable
 * sequences, in order, against a backend it never assumes anything about.
 *
 * Every hardware touch goes through spf_tandem_backend_t. That is what makes
 * §8.4's list testable -- SPI failures at each step, unequal read-back, an
 * acknowledgement timeout, split-table mode, a wrong ENSM state -- without a
 * radio. The real backend talks to iio; the test backend is a struct of
 * counters and injectable failures.
 */

#ifndef SPF_TANDEM_CTL_H
#define SPF_TANDEM_CTL_H

#include "spf_tandem_lifecycle.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* AD9361 registers this layer touches, named so the call sites read as the
 * datasheet does. */
#define SPF_AD9361_REG_AGC_CONFIG_2   0x0FBu   /* [1:0] = MAN_GAIN_CTRL_RX1/RX2 */
#define SPF_AD9361_REG_AGC_CONFIG_3   0x0FCu   /* [7:5] manual increment step   */
#define SPF_AD9361_REG_PEAK_WAIT_TIME 0x0FEu   /* [7:5] decrement step, [4:0] PWOT */
#define SPF_AD9361_REG_CTRL_OUT_PTR   0x035u
#define SPF_AD9361_REG_CTRL_OUT_EN    0x036u
#define SPF_AD9361_REG_GAIN_RX1       0x2B0u
#define SPF_AD9361_REG_GAIN_RX2       0x2B5u

#define SPF_AD9361_PIN_CTRL_MASK      0x03u
#define SPF_CTRL_OUT_PAGE_DETECTORS   0x03u

/* FPGA block registers, TANDEM_AGC_V1_DESIGN.md §8 */
#define SPF_TANDEM_REG_ID      0x00u
#define SPF_TANDEM_REG_CTRL    0x08u
#define SPF_TANDEM_REG_STATUS  0x0Cu
#define SPF_TANDEM_REG_EPOCH   0x10u
#define SPF_TANDEM_REG_INDEX   0x14u
#define SPF_TANDEM_REG_EXPECT  0x18u
#define SPF_TANDEM_REG_FAULT   0x2Cu
#define SPF_TANDEM_ID_MAGIC    0x54414731u   /* "TAG1" */

typedef struct spf_tandem_backend spf_tandem_backend_t;

struct spf_tandem_backend {
	void *ctx;

	/* FPGA block registers */
	int (*fpga_read)(void *ctx, uint8_t addr, uint32_t *out);
	int (*fpga_write)(void *ctx, uint8_t addr, uint32_t val);

	/* AD9361 registers, via direct_reg_access. Writes are unmasked, so the
	 * caller must read-modify-write -- this layer always does. */
	int (*ad9361_read)(void *ctx, uint16_t reg, uint8_t *out);
	int (*ad9361_write)(void *ctx, uint16_t reg, uint8_t val);

	/* gain index per channel, and the gain-control mode */
	int (*gain_get)(void *ctx, int channel, uint8_t *index);
	int (*gain_set)(void *ctx, int channel, uint8_t index);
	int (*mode_set)(void *ctx, int channel, const char *mode);

	/* "fdd", "alert", "sleep", ... */
	int (*ensm_get)(void *ctx, char *buf, size_t len);

	/* true when the full gain table is in use; split table cannot support
	 * per-channel increment and decrement on four pins (§5.0) */
	int (*full_gain_table)(void *ctx, bool *full);
};

typedef struct {
	spf_tandem_lifecycle_t lc;
	const spf_tandem_backend_t *be;

	uint8_t initial_index;
	uint8_t last_rx1;
	uint8_t last_rx2;

	/* bounded retry, RC13/RC14's lesson made explicit */
	unsigned retry_limit;
	unsigned retries_used;

	char last_error_detail[128];
} spf_tandem_ctl_t;

void spf_tandem_ctl_init(spf_tandem_ctl_t *c, const spf_tandem_backend_t *be,
                         uint8_t initial_index);

/* §11 enable, in order. Any failure rolls back to a known-safe legacy state
 * and reports precisely which step failed. */
spf_tandem_rc_t spf_tandem_ctl_enable(spf_tandem_ctl_t *c, bool auto_mode);

/* §11 disable: disarm BEFORE releasing the pins, restore the legacy mode, and
 * report disarmed only once every step has completed. */
spf_tandem_rc_t spf_tandem_ctl_disable(spf_tandem_ctl_t *c, const char *restore_mode);

/* the §6.2 quiescence rule: only compare when no pulse is in flight and the
 * cooldown has expired, and require two consecutive disagreements */
spf_tandem_rc_t spf_tandem_ctl_check_sync(spf_tandem_ctl_t *c);

/* machine-readable status, §5.7 */
int spf_tandem_ctl_status(spf_tandem_ctl_t *c, char *buf, size_t len);

#endif /* SPF_TANDEM_CTL_H */
