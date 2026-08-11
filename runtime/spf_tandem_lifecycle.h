/*
 * spf_tandem_lifecycle.h
 *
 * Tandem AGC ownership lifecycle. A pure state machine: no syscalls, no I/O,
 * no hardware access, so every transition and every failure path is testable
 * natively on the build host.
 *
 * This is a deliberate transposition of RC17's spf_ip_rx_lifecycle rather than
 * an independent design. RC17 solved the same problem -- a hardware ownership
 * handoff whose control plane must stay responsive while slow hardware work
 * proceeds -- and it is hardware-qualified on these radios. The states, the
 * never-reused generation, the completed-session tombstone and the
 * distinct non-consuming signals all carry over. See
 * TANDEM_AGC_V1_DESIGN.md §2.2-§2.4 for the mapping and the deliberate
 * divergences.
 *
 * What differs from RC17: the resource is four AD9361 CTRL_IN pins plus their
 * tri-state rather than a DMA device node, and two hardware facts measured by
 * experiment E-AGC1 shape the sequence --
 *
 *   * CTRL_IN edges are ignored unless the ENSM is RX-active, so arming
 *     outside RX produces a controller that silently does nothing;
 *   * arming takes gain ownership away from software SILENTLY: a hardwaregain
 *     write returns success and is dropped. The runtime must therefore reject
 *     such writes itself rather than rely on the device to refuse them.
 */

#ifndef SPF_TANDEM_LIFECYCLE_H
#define SPF_TANDEM_LIFECYCLE_H

#include <stdbool.h>
#include <stdint.h>

typedef enum {
	SPF_TANDEM_LEGACY = 0,
	SPF_TANDEM_ARMING,
	SPF_TANDEM_OWNED_IDLE,   /* tandem-hold */
	SPF_TANDEM_ACTIVE,       /* tandem-auto */
	SPF_TANDEM_DISARMING,
	SPF_TANDEM_RELEASABLE,
	SPF_TANDEM_FAULTED,
} spf_tandem_state_t;

typedef enum {
	SPF_TANDEM_OK = 0,
	SPF_TANDEM_EBUSY,          /* transient: retry is permitted, bounded */
	SPF_TANDEM_EINVAL,
	SPF_TANDEM_EFAULTED,       /* never retry; operator recovery required */
	SPF_TANDEM_ENOTRX,         /* ENSM is not RX-active (E-AGC1 H6) */
	SPF_TANDEM_ENOCONSUMER,
	SPF_TANDEM_ECONFLICT,      /* a conflicting operation was attempted */
} spf_tandem_rc_t;

/* Operations that must be refused while tandem owns or is releasing the pins,
 * per TANDEM_AGC_V1_DESIGN.md §6.3. */
typedef enum {
	SPF_TANDEM_OP_GAIN_WRITE = 0,  /* silently dropped by the part when armed */
	SPF_TANDEM_OP_GAIN_TABLE,
	SPF_TANDEM_OP_SPLIT_TABLE,
	SPF_TANDEM_OP_FIR_DECIMATION,  /* changes ClkRF, invalidates the pulse width */
	SPF_TANDEM_OP_SAMPLE_RATE,     /* may change decimation as a side effect */
	SPF_TANDEM_OP_BAND_CROSSING,   /* reloads the gain table */
	SPF_TANDEM_OP_GAIN_MODE,
	SPF_TANDEM_OP_HYBRID_MODE,     /* re-arms CTRL_IN2 behind the interlock */
	SPF_TANDEM_OP_INITIALIZE,      /* reverts 0x0FB under an armed controller */
	SPF_TANDEM_OP_COUNT
} spf_tandem_op_t;

typedef struct {
	spf_tandem_state_t state;
	uint8_t  epoch;              /* never reused; skips zero on wrap */
	uint8_t  epoch_tomb;         /* completed-session tombstone */
	bool     consumer_ready;
	bool     ensm_rx_active;
	bool     pin_control_armed;
	bool     fpga_owns_pins;

	uint32_t transition_count;
	uint32_t stale_epoch_count;
	uint32_t duplicate_stop_count;
	uint32_t refused_op_count[SPF_TANDEM_OP_COUNT];
	spf_tandem_rc_t last_error;
} spf_tandem_lifecycle_t;

void spf_tandem_init(spf_tandem_lifecycle_t *lc);

bool spf_tandem_busy(const spf_tandem_lifecycle_t *lc);
bool spf_tandem_owns_pins(const spf_tandem_lifecycle_t *lc);

/* True only when software may still set gain directly. After arming, the part
 * accepts such writes and drops them with a success return, so the runtime has
 * to be the thing that says no. */
bool spf_tandem_gain_writable(const spf_tandem_lifecycle_t *lc);

/* §11 enable. Refuses if the ENSM is not RX-active or the consumer is not
 * running; both are preconditions, not warnings. */
spf_tandem_rc_t spf_tandem_begin(spf_tandem_lifecycle_t *lc);

/* the FPGA has taken the pins and is holding them low */
spf_tandem_rc_t spf_tandem_pins_owned(spf_tandem_lifecycle_t *lc);

/* 0x0FB armed and acknowledged, carrying the current epoch */
spf_tandem_rc_t spf_tandem_armed(spf_tandem_lifecycle_t *lc, uint8_t ack_epoch);

/* open the policy gate: tandem-hold -> tandem-auto */
spf_tandem_rc_t spf_tandem_activate(spf_tandem_lifecycle_t *lc);

/* §11 disable. Idempotent for an already-retired session (tombstone). */
spf_tandem_rc_t spf_tandem_request_stop(spf_tandem_lifecycle_t *lc, uint8_t epoch);

/* teardown finished: disarmed, ownership returned, legacy mode restored */
spf_tandem_rc_t spf_tandem_released(spf_tandem_lifecycle_t *lc, uint8_t epoch);

spf_tandem_rc_t spf_tandem_reap(spf_tandem_lifecycle_t *lc);

/* the ENSM left RX while armed -- O-6. The pins simply go deaf, so the model
 * would diverge with nothing local to notice. */
spf_tandem_rc_t spf_tandem_ensm_left_rx(spf_tandem_lifecycle_t *lc);

void spf_tandem_fault(spf_tandem_lifecycle_t *lc, spf_tandem_rc_t why);
spf_tandem_rc_t spf_tandem_clear_fault(spf_tandem_lifecycle_t *lc);

/* Returns SPF_TANDEM_OK if the operation is allowed right now, or ECONFLICT.
 * Refusals are counted per operation so status can show what was attempted. */
spf_tandem_rc_t spf_tandem_check_op(spf_tandem_lifecycle_t *lc, spf_tandem_op_t op);

/* True only for states where a bounded retry is meaningful: ARMING, DISARMING
 * and RELEASABLE. Never FAULTED. */
bool spf_tandem_retryable(spf_tandem_rc_t rc);

const char *spf_tandem_state_name(spf_tandem_state_t s);
const char *spf_tandem_rc_name(spf_tandem_rc_t rc);
const char *spf_tandem_op_name(spf_tandem_op_t op);

#endif /* SPF_TANDEM_LIFECYCLE_H */
