/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_IQ_TRACKING_SOURCE_H
#define GLRT_IQ_TRACKING_SOURCE_H
#include "glrt_capture_source.h"

/* Internal coordinate adapter, never a replacement persisted snapshot.
 * Retain the original GLI1 native snapshot with every delivered IQ block.
 * first is the 2.5-MS/s signal-center index (native newest/ratio - 53).
 * source_now is conservative receiver time, floor(native latest/ratio)+1;
 * it is intentionally later than the filtered signal-center prefix.
 */
struct glrt_iq_tracking_source {
    struct glrt_capture_source coarse;
    uint64_t native_latest;
    uint32_t native_rate;
};
int glrt_iq_tracking_source_begin(struct glrt_iq_tracking_source *, uint32_t visit,
    uint64_t samples, const struct glrt_capture_snapshot *native_baseline);
int glrt_iq_tracking_source_take(struct glrt_iq_tracking_source *,
    const struct glrt_capture_snapshot *native_snapshot, size_t samples,
    uint64_t *coarse_first, uint64_t *coarse_source_now);
#endif
