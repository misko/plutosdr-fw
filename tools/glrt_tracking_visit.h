/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_TRACKING_VISIT_H
#define GLRT_TRACKING_VISIT_H
#include <stdint.h>

/* Internal two-visit supervisor. References are upper-edge only; the caller
 * attests the fixed native image, reference banks and RX calibration. Each
 * run is the existing finite 1536-block probe (10.0663296 s of coarse IQ).
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
     * Return zero only for a successful finite probe, not arbitrary exit 1. */
    int (*run)(void *,unsigned,uint64_t);
    int (*retain)(void *,const char *,unsigned,int,const struct glrt_visit_state *);
};
enum glrt_visit_result {
    GLRT_VISIT_DONE=0, GLRT_VISIT_INVALID=-1, GLRT_VISIT_SOURCE=-2,
    GLRT_VISIT_TUNE=-3, GLRT_VISIT_RUN=-4, GLRT_VISIT_RETENTION=-5,
    GLRT_VISIT_DEADLINE=-6, GLRT_VISIT_CANCELLED=-7
};
/* Exactly two distinct configured upper-edge centers. Caller retains plan and
 * identity first. No mutation follows failed inspection, missing evidence,
 * time regression, cancellation, failed run, or undrained source. */
int glrt_tracking_visit_run(const struct glrt_visit_ports *,uint32_t,
    const uint64_t lo_hz[2]);
#endif
