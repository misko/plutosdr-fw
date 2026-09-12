/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_TRACKING_LIVE_BOOTSTRAP_H
#define GLRT_TRACKING_LIVE_BOOTSTRAP_H
#include "glrt_tracking_bootstrap.h"
#include "glrt_tracking_iq_owner.h"

struct glrt_tracking_bootstrap_trace {
    struct glrt_tracking_iq_view source;
    uint32_t frame;
    struct glrt_tracking_job job;
    struct glrt_tracking_batch handoff;
    struct glrt_tracking_moments moments;
    struct glrt_native_estimate estimate;
    int accepted;
};
/* One bounded worker step on the actual capture owner's retained IQ and
 * published receiver time. The caller first resolves/attests a real seed and
 * initializes live; references are the pinned four 3300x4 Q11 phase banks.
 * scratch holds 3300 CI16 pairs and remains caller-owned after copying.
 * No FFT, IIO or numerical computation runs under the owner's mutex.
 *
 * PAST returns copied IQ, exact SOFTWARE moments and the associated estimate;
 * persist that evidence before another step or any handoff. On retention
 * failure stop the worker and discard its prediction. WAIT invents no result;
 * READY returns a bounded future batch/history, not a hardware admission.
 * The controller must recheck the current hardware source counter before
 * SUBMIT and retain the transferred history through its handoff port.
 * This internal adapter supports only the current direct 2.5-MS/s bootstrap.
 */
int glrt_tracking_live_bootstrap_step(struct glrt_tracking_bootstrap_live *,
    struct glrt_tracking_iq_owner *, const int16_t *references, int16_t *scratch,
    uint32_t lead, struct glrt_tracking_bootstrap_trace *);
#endif
