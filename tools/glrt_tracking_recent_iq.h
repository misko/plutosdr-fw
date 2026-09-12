/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_TRACKING_RECENT_IQ_H
#define GLRT_TRACKING_RECENT_IQ_H
#include <stddef.h>
#include <stdint.h>

enum glrt_recent_iq_status {
    GLRT_RECENT_IQ_OK=0, GLRT_RECENT_IQ_INVALID=-1, GLRT_RECENT_IQ_STALE=-2,
    GLRT_RECENT_IQ_SOURCE_LOSS=-3, GLRT_RECENT_IQ_OVERWRITTEN=-4,
    GLRT_RECENT_IQ_NOT_READY=-5
};

/* Caller-owned interleaved host-endian CI16 storage, in complex samples.
 * No allocation, I/O or locking. The capture owner serializes append/read;
 * input/output arrays must not alias storage. Epoch and source coordinates
 * must come from the attested capture, not from a guessed first DMA index. */
struct glrt_tracking_recent_iq {
    int16_t *iq;
    size_t capacity, head, count;
    uint64_t first, end; /* retained interval [first,end) */
    uint32_t epoch, valid;
};

int glrt_tracking_recent_iq_reset(struct glrt_tracking_recent_iq *, int16_t *storage,
    size_t capacity, uint32_t epoch, uint64_t first);
/* Keep the newest capacity samples. A gap, overlap or source-counter overflow
 * invalidates all history until reset. A stale epoch cannot poison a new one. */
int glrt_tracking_recent_iq_append(struct glrt_tracking_recent_iq *, uint32_t epoch,
    uint64_t first, const int16_t *iq, size_t samples);
/* Failed reads leave output untouched; overwritten and not-yet-delivered
 * samples are distinct. A successful copy remains owned by its caller even
 * after subsequent ingestion wraps the ring. */
int glrt_tracking_recent_iq_read(const struct glrt_tracking_recent_iq *, uint32_t epoch,
    uint64_t first, int16_t *out, size_t samples);
#endif
