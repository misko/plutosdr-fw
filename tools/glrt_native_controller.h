/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_NATIVE_CONTROLLER_H
#define GLRT_NATIVE_CONTROLLER_H
#include "glrt_tracking_trend.h"

/* Narrow synchronous ports. read/write return byte counts or negative errors.
 * retain returns zero only once the exact bytes are retained. It must finish
 * before SUBMIT/POP; a storage failure never permits discarding a hardware head.
 * The caller owns the PPU radio lease and supplies a monotonic clock. */
struct glrt_native_ports {
    void *context;
    int (*read)(void *, const char *, char *, size_t);
    int (*write)(void *, const char *, const char *, size_t);
    int (*retain)(void *, const char *, const char *, size_t);
    double (*clock)(void *);
};
enum glrt_native_controller_result {
    GLRT_NATIVE_RUNNING = 1,
    GLRT_NATIVE_COMPLETE = 0,
    GLRT_NATIVE_IO_ERROR = -1,
    GLRT_NATIVE_PROTOCOL_ERROR = -2,
    GLRT_NATIVE_SOURCE_LOST = -3,
    GLRT_NATIVE_ACQUISITION_LOST = -4,
    GLRT_NATIVE_DEADLINE = -5,
    GLRT_NATIVE_RETENTION_ERROR = -6
};
struct glrt_native_owned_batch {
    struct glrt_native_batch batch;
    uint32_t first_frame, received;
    int occupied;
};
struct glrt_native_controller {
    struct glrt_tracking_trend trend;
    struct glrt_tracking_trend authority;
    struct glrt_native_owned_batch slots[2];
    struct glrt_native_ports ports;
    struct glrt_native_batch bootstrap;
    int64_t bootstrap_delay_q16, bootstrap_cfo_q48;
    uint32_t frames, next_frame, next_tag, sequence, configured;
    double deadline, cleanup_deadline;
    int started, stopping, cancelled, clearing, done, failure, bootstrap_active, bootstrap_offset_valid;
    int acquisition_horizon_exhausted;
    int tracking;
    int handoff_pending;
    int authority_valid;
};
/* Bootstrap is a retained acquisition prediction in a freshly rebased source
 * epoch, with zero scheduled counters. It begins at global frame zero. The
 * runtime checks live source lead before submitting it. No acquisition truth
 * is invented here. Total work is bounded to frames <=225000 and <=300 s.
 * Returns zero after local validation; does not perform I/O. */
int glrt_native_controller_init(struct glrt_native_controller *,
    const struct glrt_native_ports *, const struct glrt_native_batch *bootstrap,
    uint32_t frames, double seconds);
/* GLT1 uses explicitly rate-bound descriptors, snapshots, heads and ports.
 * The caller must attest the profile's full ROM hash and receiver rate before
 * init. This initializer performs local validation only. Tick/request_stop
 * and retention/ownership semantics are shared with the legacy controller. */
int glrt_tracking_controller_init(struct glrt_native_controller *,
    const struct glrt_native_ports *, const struct glrt_tracking_batch *bootstrap,
    uint32_t frames, double seconds);
/* Continue a validated causal history without resetting its frame ordinals.
 * frames is the additional work budget, not the absolute ending ordinal.
 * The bootstrap must exactly match a prediction from this same rate/epoch and
 * history. Copy history on success; leave the controller untouched on error.
 * The caller has retained the acquisition/past-IQ evidence and attested the
 * reference bank. First tick retains the transferred history before SUBMIT;
 * live deadline, source ownership and finite recovery checks still apply. */
int glrt_tracking_controller_init_handoff(struct glrt_native_controller *,
    const struct glrt_native_ports *, const struct glrt_tracking_batch *,
    const struct glrt_tracking_trend *, uint32_t first_frame,
    uint32_t frames, double seconds);
/* Supply a separate predictor for work beyond the current descriptor frontier.
 * The caller supplies causal history in the same rate and epoch, beginning at
 * exactly the next unowned frame. The refresh is persisted before it can affect
 * another descriptor and cannot rewrite work already owned by FPGA. Native
 * result history remains separate, so already submitted results still update
 * in their original order. */
int glrt_tracking_controller_refresh_handoff(struct glrt_native_controller *,
    const struct glrt_tracking_trend *);
/* Explicit startup mode: a 17..64-repeat externally validated prediction is
 * an authorization horizon. Submit 12 first, then at most four at a time
 * until native rate feedback is available. Supported native results may update
 * bounded timing/CFO offsets while the coarse rates remain fixed. Never extend
 * that horizon or return to
 * it after native feedback takes over. The ordinary initializer is unchanged. */
int glrt_native_controller_init_sliced(struct glrt_native_controller *,
    const struct glrt_native_ports *, const struct glrt_native_batch *bootstrap,
    uint32_t frames, double seconds);
/* One bounded read/process/submit step. Caller polls or waits between ticks.
 * End-of-run CLEAR happens only after every result is retained and popped.
 * A negative return ends the run. If retention/protocol recovery fails, the
 * hardware heads remain unacknowledged; external recovery must retain them.
 * Call request_stop for an orderly bounded cancellation (also for signals). */
int glrt_native_controller_tick(struct glrt_native_controller *);
void glrt_native_controller_request_stop(struct glrt_native_controller *);
#endif
