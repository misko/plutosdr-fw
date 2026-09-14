/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_TRACKING_OBSERVER_H
#define GLRT_TRACKING_OBSERVER_H
#include "glrt_tracking_iq_owner.h"
#include "glrt_tracking_trend.h"

enum glrt_observer_result {
    GLRT_OBSERVER_DONE=0, GLRT_OBSERVER_WAIT=1, GLRT_OBSERVER_MEASURED=2,
    GLRT_OBSERVER_INVALID=-1, GLRT_OBSERVER_SOURCE=-2,
    GLRT_OBSERVER_DEADLINE=-3, GLRT_OBSERVER_RETENTION=-4,
    GLRT_OBSERVER_HISTORY=-5, GLRT_OBSERVER_CANCELLED=-6
};
struct glrt_tracking_observer_trace {
    struct glrt_tracking_iq_view source;
    struct glrt_tracking_job job;
    struct glrt_tracking_moments moments;
    struct glrt_native_estimate estimate;
    uint32_t frame;
    int accepted;
};
struct glrt_tracking_observer {
    struct glrt_tracking_trend trend;
    uint64_t deadline_ns, last_ns, source_limit, last_source;
    uint32_t next_frame, measurements, maximum_measurements, frame_spacing;
    int status;
};
struct glrt_tracking_observer_ports {
    void *context;
    uint64_t (*clock_ns)(void *); /* owner's CLOCK_MONOTONIC domain */
    int (*cancelled)(void *);    /* 0 active, 1 cancelled; other values fail */
    /* Synchronous evidence retention before history update. Copy the trace
     * and exactly 3300 CI16 pairs; return zero only after successful retention.
     * These are SOFTWARE observations, never FPGA heads or native support.
     * No callback or numerical computation runs under the owner mutex. */
    int (*retain)(void *, const struct glrt_tracking_observer_trace *, const int16_t *);
};

/* Passive, internal 2.5-MS/s observer. Clone a validated coarse history, then
 * measure every nine frames starting at first_frame. Keep its own history;
 * this module has no native-controller, radio-configuration or SUBMIT port.
 * The caller attests reference identity and retains the imported history.
 * At most 1024 measurements, fifteen seconds of wall time and twelve seconds
 * of source look-ahead from the first predicted pilot are allowed. Callers use
 * smaller profile-owned bounds unless continuous coarse authority is enabled. The existing
 * eight-support, 96-frame fit and last-supported-plus-32 limits are unchanged.
 * DONE and failures are terminal until init. Init performs no I/O.
 */
int glrt_tracking_observer_init(struct glrt_tracking_observer *,
    const struct glrt_tracking_trend *, uint32_t first_frame, uint32_t maximum_measurements,
    uint64_t source_limit, uint64_t now_ns, uint64_t wall_budget_ns);

/* Explicit internal cadence: three or nine frames. The legacy initializer
 * selects nine. All ownership, evidence, history and budget limits above
 * still apply; a denser cadence does not authorize native measurements. */
int glrt_tracking_observer_init_cadence(struct glrt_tracking_observer *,
    const struct glrt_tracking_trend *, uint32_t first_frame, uint32_t frame_spacing,
    uint32_t maximum_measurements, uint64_t source_limit, uint64_t now_ns,
    uint64_t wall_budget_ns);

/* One bounded copied-IQ calculation, or WAIT without a fabricated measurement.
 * refs is four pinned 3300x4 phase banks; scratch is 3300 CI16 pairs. Neither
 * may alias owner's storage. The caller owns worker lifetime: close, join all
 * workers, then destroy/reinitialize the owner. Recheck cancellation, source
 * validity and wall time after retention before committing observer history.
 * A retained trace followed by failure is not a committed observation; retain
 * terminal status and measurements as well. Output clears unless MEASURED.
 */
int glrt_tracking_observer_step(struct glrt_tracking_observer *,
    struct glrt_tracking_iq_owner *, const int16_t *refs, int16_t *scratch,
    const struct glrt_tracking_observer_ports *, struct glrt_tracking_observer_trace *);
#endif
