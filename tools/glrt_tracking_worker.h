/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_TRACKING_WORKER_H
#define GLRT_TRACKING_WORKER_H
#include "glrt_tracking_seed.h"
#include "glrt_tracking_live_bootstrap.h"

enum glrt_tracking_worker_status {
    GLRT_WORKER_RUNNING=2, GLRT_WORKER_READY=1, GLRT_WORKER_IGNORED=0,
    GLRT_WORKER_INVALID=-1, GLRT_WORKER_SOURCE=-2, GLRT_WORKER_DEADLINE=-3,
    GLRT_WORKER_CANCELLED=-4, GLRT_WORKER_RETENTION=-5, GLRT_WORKER_HISTORY=-6,
    GLRT_WORKER_PORT=-7, GLRT_WORKER_STALE=-8
};
enum glrt_tracking_worker_record {
    GLRT_WORKER_SEED_IQ=1, GLRT_WORKER_RESOLVED=2,
    GLRT_WORKER_PAST=3, GLRT_WORKER_HANDOFF=4
};
/* Caller-owned worker storage; allocate outside the capture loop and do not
 * put this ~0.5-MB workspace on the radio's thread stack. One worker/candidate
 * at a time. Arrays and callback views remain valid until the next run/step. */
struct glrt_tracking_worker {
    struct glrt_resolver_workspace fft_workspace;
    int16_t seed_iq[2*GLRT_SEED_WINDOW_SAMPLES], scratch[6600], reference[6600];
    struct glrt_tracking_seed_window seed;
    struct glrt_resolver_result resolved;
    struct glrt_tracking_bootstrap_live live;
    struct glrt_tracking_bootstrap_trace trace;
    struct glrt_tracking_iq_view checked_source;
    uint64_t started_ns, last_ns, deadline_ns, source_checked_ns;
    uint32_t fft_calls, retained_past, waits;
    int status;
};
struct glrt_tracking_worker_ports {
    void *context;
    uint64_t (*clock_ns)(void *); /* same CLOCK_MONOTONIC domain as the IQ owner */
    int (*cancelled)(void *);     /* 0 active, 1 cancelled; other values fail */
    int (*wait)(void *);          /* wait for publication/cancellation, <=10 ms */
    /* Synchronous retention: 0 only after the exact evidence is retained.
     * SEED_IQ: seed + seed_iq; RESOLVED: seed + resolved; PAST: trace + scratch;
     * HANDOFF: trace + live history + checked_source (a proposal). Copy fields, not padded native structs,
     * into an explicit retained format. These are internal callback tags, not
     * a new public wire contract. No callback runs under the IQ-owner mutex. */
    int (*retain)(void *, enum glrt_tracking_worker_record, const struct glrt_tracking_worker *);
};
struct glrt_tracking_worker_config {
    struct glrt_tracking_iq_owner *owner;
    const int16_t *references; /* attested four 3300x4 direct upper phase banks */
    glrt_resolver_fft fft;
    void *fft_context;
    struct glrt_tracking_worker_ports ports;
    uint64_t source_deadline, wall_budget_ns; /* explicit budget, <=5 seconds */
    uint32_t maximum_seed_age, lead_samples;
};
/* Run one real GLA1 candidate in a background worker, never the IIO capture
 * thread. The caller attests event sequence, source/profile and ROM identity.
 * Full resolution is guarded before/after every FFT, and bootstrap waits are
 * wall-time bounded even if RF publication stops. No thresholds, 200-anchor
 * budget or 32-repeat forecast are extended. Errors invalidate the handoff.
 * READY is retained history plus a freshly checked future proposal; the
 * controller must still recheck the hardware counter immediately at SUBMIT.
 * Retain the terminal status and final checked_source/source_checked_ns before
 * using the proposal. A retained HANDOFF callback alone never authorizes use;
 * cancellation, deadline or source checks after that callback may still fail.
 * No thread, IIO context, file, radio lease or hardware submission is created. */
int glrt_tracking_worker_run(struct glrt_tracking_worker *, const struct glrt_tracking_worker_config *,
    const uint32_t event[16]);
#endif
