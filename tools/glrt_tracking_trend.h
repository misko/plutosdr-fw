/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_TRACKING_TREND_H
#define GLRT_TRACKING_TREND_H
#include "glrt_native_trend.h"
#include "glrt_tracking_schedule.h"

/* Rate-bound causal history. Caller must associate moments with the source
 * epoch, rate, reference bank/phase and admitted job before observe(). These
 * are internal ports; neither old GLS1 packets nor timestamps are relabeled. */
struct glrt_tracking_trend {
    struct glrt_native_trend history;
    uint32_t rate;
};
int glrt_tracking_trend_reset(struct glrt_tracking_trend *, uint32_t epoch, uint32_t rate);
/* delay_correction_s is relative to the selected reference. Its fractional
 * delay is added exactly once; observed start remains the integer IQ index.
 * Return values, rejection fencing and 96-frame window match the native API. */
int glrt_tracking_trend_observe(struct glrt_tracking_trend *, uint32_t epoch,
    uint32_t frame, uint64_t start, uint32_t reference_phase,
    const struct glrt_native_estimate *);
int glrt_tracking_trend_batch(const struct glrt_tracking_trend *,
    uint32_t first_frame, uint32_t repeats, uint32_t tag, uint32_t seed,
    struct glrt_tracking_batch *, double *cfo_rate_hz_s);
/* Validate an imported history's bounded storage, chronological ownership and
 * finite values before using it for a new controller run. This does not attest
 * RF support or replace the batch predictor's quality/forecast checks. */
int glrt_tracking_trend_handoff_valid(const struct glrt_tracking_trend *,
    uint32_t first_frame, uint32_t frames);
#endif
