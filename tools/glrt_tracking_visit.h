/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_TRACKING_VISIT_H
#define GLRT_TRACKING_VISIT_H
#include <stdint.h>

/* Internal bounded visit supervisor. References are upper-edge only; the caller
 * attests the fixed native image, reference banks and RX calibration. Each
 * run is a finite 1536-block probe (at most 10.0663296 s of coarse IQ).
 * This controller never changes clocks, bandwidth, gain, TX or tracking gates.
 */
struct glrt_visit_state {
    uint64_t lo_hz, native_latest;
    uint32_t rate, epoch;
    int idle, fixed_rf_valid;
};
struct glrt_visit_ports {
    void *context;
    uint64_t (*clock_ns)(void *);
    int (*cancelled)(void *);
    int (*inspect)(void *,struct glrt_visit_state *);
    int (*tune)(void *,uint64_t);
    /* Must join its bounded child before returning, even on cancellation.
     * Return zero for successful finite capture, or GLRT_VISIT_CLEAN_LOSS for
     * explicitly proven, retained and drained native loss after full cleanup.
     * An arbitrary failed child never supplies this disposition. */
    int (*run)(void *,unsigned,uint64_t);
    int (*retain)(void *,const char *,unsigned,int,const struct glrt_visit_state *);
};
enum glrt_visit_result {
    GLRT_VISIT_DONE=0, GLRT_VISIT_CLEAN_LOSS=1,
    GLRT_VISIT_SIGNAL=2, GLRT_VISIT_NO_TRACK=3,
    GLRT_VISIT_INVALID=-1, GLRT_VISIT_SOURCE=-2,
    GLRT_VISIT_TUNE=-3, GLRT_VISIT_RUN=-4, GLRT_VISIT_RETENTION=-5,
    GLRT_VISIT_DEADLINE=-6, GLRT_VISIT_CANCELLED=-7
};
/* Exactly two distinct configured upper-edge centers. Caller retains plan and
 * identity first. No mutation follows failed inspection, missing evidence,
 * time regression, cancellation, failed run, or undrained source. */
int glrt_tracking_visit_run(const struct glrt_visit_ports *,uint32_t,
    const uint64_t lo_hz[2]);
/* Bounded scan/revisit plan: 2..4 centers, adjacent visits must differ.
 * Repeated nonadjacent centers are intentional revisits. All validation is
 * performed before the first port call; the shared deadline remains 60 s. */
int glrt_tracking_visit_plan_run(const struct glrt_visit_ports *,uint32_t,
    const uint64_t *lo_hz,unsigned count);
/* Short radio-local scouts stop after the first child proves either its finite
 * signal horizon or a fully cleaned native signal loss and return that plan
 * index. A caller can then run one long follow-up on that LO without returning
 * control to a host scheduler. */
int glrt_tracking_visit_until_signal(const struct glrt_visit_ports *,uint32_t,
    const uint64_t *lo_hz,unsigned count,unsigned *selected_index);
/* The same bounded scout with a caller-owned first evidence number. This is
 * used by an opt-in continuity plan to return to the reviewed LO list after a
 * clean segment loss without reusing an evidence directory. */
int glrt_tracking_visit_until_signal_from(const struct glrt_visit_ports *,uint32_t,
    const uint64_t *lo_hz,unsigned count,unsigned first_evidence_number,
    unsigned *selected_index);
/* One bounded long follow-up. The callback number is caller-owned so its
 * evidence directory cannot collide with preceding scouts. CLEAN_LOSS and
 * NO_TRACK are reviewed outcomes; zero alone means the callback proved its
 * requested tracking completion. */
int glrt_tracking_visit_followup_run(const struct glrt_visit_ports *,uint32_t,
    uint64_t lo_hz,unsigned evidence_number);
#endif
