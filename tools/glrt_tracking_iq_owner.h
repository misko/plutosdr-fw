/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_TRACKING_IQ_OWNER_H
#define GLRT_TRACKING_IQ_OWNER_H
#include <pthread.h>
#include "glrt_tracking_recent_iq.h"

enum { GLRT_IQ_OWNER_CLOSED=-6 };
struct glrt_tracking_iq_view {
    uint64_t first, end, source_now, observed_ns, generation;
    uint32_t epoch, valid, closed;
};
/* Internal radio-local boundary, not a persisted contract. Initialize a zeroed
 * owner before starting workers. One capture thread publishes already-attested
 * blocks and source snapshots; workers copy past IQ under the mutex and do
 * all numerical work after copy returns. Storage is caller-owned and must not
 * alias publish/copy buffers. This does not attest the radio or submit jobs.
 * Close stops publication. Join every worker before destroy or reinitialize.
 */
struct glrt_tracking_iq_owner {
    pthread_mutex_t mutex;
    struct glrt_tracking_recent_iq ring;
    uint64_t source_now, observed_ns, generation;
    unsigned initialized, closed;
};
int glrt_tracking_iq_owner_init(struct glrt_tracking_iq_owner *, int16_t *,
    size_t capacity, uint32_t epoch, uint64_t first);
int glrt_tracking_iq_owner_publish(struct glrt_tracking_iq_owner *, uint32_t epoch,
    uint64_t first, const int16_t *, size_t samples, uint64_t source_now, uint64_t observed_ns);
/* Copy returns a matching view of retained IQ and receiver time. With samples
 * zero, only the view is requested and first/out are ignored. Failed copies
 * leave IQ output untouched; a view obtained under the lock remains available
 * to explain stale/overwritten/closed history. Normal close retains past IQ;
 * view.closed must prevent new handoff even if a past copy succeeds. A view is
 * not a current admission check: refresh the hardware counter before SUBMIT.
 */
int glrt_tracking_iq_owner_copy(struct glrt_tracking_iq_owner *, uint32_t epoch,
    uint64_t first, int16_t *, size_t samples, struct glrt_tracking_iq_view *);
int glrt_tracking_iq_owner_close(struct glrt_tracking_iq_owner *, int source_lost);
int glrt_tracking_iq_owner_destroy(struct glrt_tracking_iq_owner *);
#endif
