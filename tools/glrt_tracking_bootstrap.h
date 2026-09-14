/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_TRACKING_BOOTSTRAP_H
#define GLRT_TRACKING_BOOTSTRAP_H
#include "glrt_tracking_trend.h"

#define GLRT_BOOTSTRAP_SPACING 9U
#define GLRT_BOOTSTRAP_LIMIT 200U

enum glrt_bootstrap_status { GLRT_BOOTSTRAP_ERROR=-1, GLRT_BOOTSTRAP_WAIT=0, GLRT_BOOTSTRAP_PAST=1,
                             GLRT_BOOTSTRAP_READY=2 };
enum glrt_bootstrap_failure { GLRT_BOOTSTRAP_NONE, GLRT_BOOTSTRAP_INVALID,
    GLRT_BOOTSTRAP_SOURCE_LOSS, GLRT_BOOTSTRAP_BUDGET, GLRT_BOOTSTRAP_HISTORY,
    GLRT_BOOTSTRAP_FUTURE };

/* Internal 2.5-MS/s coarse-lane bootstrap, with no I/O or allocation. The caller
 * owns continuous recent IQ and four reference phases. Software past-job
 * moments are never labeled FPGA results. Epoch/gap/retune resets are required.
 * One job may be outstanding. The existing trend's acceptance and 32-repeat
 * forecast limits are unchanged. During initial jobs 3..7, three or more
 * earlier accepted pilots can predict the next carrier using a linear ramp.
 * All prior startup jobs must be accepted, the lead is bounded by the selected cadence,
 * and the forecast must remain within 250 Hz of the last accepted carrier.
 * Otherwise startup holds that carrier. No future batch is authorized before
 * the existing eight-observation history gate. This is not a higher-rate
 * coordinate mapping. */
struct glrt_tracking_bootstrap {
    struct glrt_tracking_trend trend;
    struct glrt_tracking_job pending_job;
    uint64_t seed_start, last_available;
    double seed_cfo;
    uint32_t seed_fraction, seed_frame, jobs, pending, ready, valid, clock_seen, spacing;
    uint32_t failure;
};

/* A causally resolved pilot origin in Q16 samples and full-pilot CFO. Reference
 * identity, source continuity, resolver support and available IQ belong to the
 * caller. No accepted tracking estimate is created by initialization. */
int glrt_tracking_bootstrap_init(struct glrt_tracking_bootstrap *, uint32_t epoch,
    uint64_t start, uint32_t fraction, double cfo_hz);

/* Select startup cadence before the first job. Nine frames remains the
 * default; three frames is the measured lower-cadence ARM option. */
int glrt_tracking_bootstrap_set_spacing(struct glrt_tracking_bootstrap *, uint32_t spacing);

/* earliest is inclusive and available is exclusive in original coarse-lane
 * samples; available must advance with actual acquisition during computation.
 * A past job must be copied/attested before the ring overwrites it. READY emits
 * eight future jobs beginning at least lead samples after available. Caller
 * checks actual admission time again before submission. Outputs clear on error.
 * A failure is terminal until init(), and retains its reason/history for audit. */
int glrt_tracking_bootstrap_next(struct glrt_tracking_bootstrap *, uint64_t earliest,
    uint64_t available, uint32_t lead, uint32_t *frame,
    struct glrt_tracking_job *, struct glrt_tracking_batch *handoff);

/* Additive live adapter: DMA delivery and actual reception have separate
 * clocks. All coordinates are in the same attested 2.5-MS/s epoch. Retained
 * IQ ends at retained_end (exclusive); source_now is the next receiver sample
 * index. The caller serializes ring admission/copy, enforces a wall-time
 * timeout even if the source stops, and rechecks the hardware SUBMIT deadline.
 * WAIT clears outputs and creates no pending measurement. It does not extend
 * the configured source deadline, 200-anchor budget or 32-repeat forecast.
 * Observe past jobs through live.core using the original observe() port. */
struct glrt_tracking_bootstrap_live {
    struct glrt_tracking_bootstrap core;
    uint64_t source_deadline, last_source, last_earliest;
    uint32_t seen;
};
int glrt_tracking_bootstrap_live_init(struct glrt_tracking_bootstrap_live *,
    uint32_t epoch, uint64_t start, uint32_t fraction, double cfo_hz,
    uint64_t source_deadline);
int glrt_tracking_bootstrap_live_next(struct glrt_tracking_bootstrap_live *,
    uint64_t earliest, uint64_t retained_end, uint64_t source_now, uint32_t lead,
    uint32_t *frame, struct glrt_tracking_job *, struct glrt_tracking_batch *handoff);

/* Accept only the outstanding job's associated software estimate. Return 1
 * for supported, 0 for a retained quality rejection, -1 for a terminal fault.
 * Copying IQ, exact moments, solving and continuity attestation are caller ports. */
int glrt_tracking_bootstrap_observe(struct glrt_tracking_bootstrap *, uint32_t epoch,
    uint32_t frame, const struct glrt_tracking_job *, const struct glrt_native_estimate *);
#endif
