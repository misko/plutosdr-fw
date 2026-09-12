/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_TRACKING_BOOTSTRAP_H
#define GLRT_TRACKING_BOOTSTRAP_H
#include "glrt_tracking_trend.h"

#define GLRT_BOOTSTRAP_SPACING 9U
#define GLRT_BOOTSTRAP_LIMIT 200U

enum glrt_bootstrap_status { GLRT_BOOTSTRAP_ERROR=-1, GLRT_BOOTSTRAP_PAST=1,
                             GLRT_BOOTSTRAP_READY=2 };
enum glrt_bootstrap_failure { GLRT_BOOTSTRAP_NONE, GLRT_BOOTSTRAP_INVALID,
    GLRT_BOOTSTRAP_SOURCE_LOSS, GLRT_BOOTSTRAP_BUDGET, GLRT_BOOTSTRAP_HISTORY,
    GLRT_BOOTSTRAP_FUTURE };

/* Internal 2.5-MS/s coarse-lane bootstrap, with no I/O or allocation. The caller
 * owns continuous recent IQ and four reference phases. Software past-job
 * moments are never labeled FPGA results. Epoch/gap/retune resets are required.
 * One job may be outstanding. The existing trend's acceptance and 32-repeat
 * forecast limits are unchanged. This is not a higher-rate coordinate mapping. */
struct glrt_tracking_bootstrap {
    struct glrt_tracking_trend trend;
    struct glrt_tracking_job pending_job;
    uint64_t seed_start, last_available;
    double seed_cfo;
    uint32_t seed_fraction, seed_frame, jobs, pending, ready, valid, clock_seen;
    uint32_t failure;
};

/* A causally resolved pilot origin in Q16 samples and full-pilot CFO. Reference
 * identity, source continuity, resolver support and available IQ belong to the
 * caller. No accepted tracking estimate is created by initialization. */
int glrt_tracking_bootstrap_init(struct glrt_tracking_bootstrap *, uint32_t epoch,
    uint64_t start, uint32_t fraction, double cfo_hz);

/* earliest is inclusive and available is exclusive in original coarse-lane
 * samples; available must advance with actual acquisition during computation.
 * A past job must be copied/attested before the ring overwrites it. READY emits
 * eight future jobs beginning at least lead samples after available. Caller
 * checks actual admission time again before submission. Outputs clear on error.
 * A failure is terminal until init(), and retains its reason/history for audit. */
int glrt_tracking_bootstrap_next(struct glrt_tracking_bootstrap *, uint64_t earliest,
    uint64_t available, uint32_t lead, uint32_t *frame,
    struct glrt_tracking_job *, struct glrt_tracking_batch *handoff);

/* Accept only the outstanding job's associated software estimate. Return 1
 * for supported, 0 for a retained quality rejection, -1 for a terminal fault.
 * Copying IQ, exact moments, solving and continuity attestation are caller ports. */
int glrt_tracking_bootstrap_observe(struct glrt_tracking_bootstrap *, uint32_t epoch,
    uint32_t frame, const struct glrt_tracking_job *, const struct glrt_native_estimate *);
#endif
