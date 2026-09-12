/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_TRACKING_SCHEDULE_H
#define GLRT_TRACKING_SCHEDULE_H
#include "glrt_native_schedule.h"

/* Internal prediction geometry, not a reinterpretation of GLS1. start/fraction
 * describe the predicted pilot origin in native Q16 sample coordinates. At
 * 2.5 MS/s it rounds to the nearest of four delayed references; elsewhere to
 * the nearest sample. Keep absolute source coordinates integer throughout. */
struct glrt_tracking_batch {
    struct glrt_native_batch prediction;
    uint32_t rate;
};
struct glrt_tracking_job {
    uint64_t start;
    uint32_t phase_step, reference_phase;
};
int glrt_tracking_batch_valid(const struct glrt_tracking_batch *);
/* Failure leaves the caller's job untouched. Expiry covers the last observed
 * sample, including the rounding carry; it never licenses an expired pilot. */
int glrt_tracking_prediction(const struct glrt_tracking_batch *, unsigned repeat,
                            struct glrt_tracking_job *);
#endif
