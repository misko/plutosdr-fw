/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_TRACKING_RECENTER_H
#define GLRT_TRACKING_RECENTER_H
#include "glrt_tracking_schedule.h"

/* Internal proposal only: no accepted estimate, IQ access or state mutation.
 * completed_attempts includes the original evaluation and is in [1,3]. A
 * low-coherence-only local fit may propose at most two corrected evaluations.
 * Caller must own/copy each complete pilot, recompute exact moments, apply
 * unchanged acceptance gates and retain every attempted evaluation. Count
 * their real processing cost against the original source/wall deadline.
 *
 * original/previous identify this same pilot; bounded movement and carrier
 * differences are checked. Return -1 for invalid arguments/association, zero
 * for no usable proposal or exhausted attempts, one for a new unverified job.
 * out clears on non-success (unless out itself is NULL). Input/output jobs may
 * alias; all input values are copied before writing the result.
 */
int glrt_tracking_recenter_propose_2500000(unsigned completed_attempts,
    const struct glrt_tracking_job *original, const struct glrt_tracking_job *previous,
    const struct glrt_native_estimate *, struct glrt_tracking_job *out);
#endif
