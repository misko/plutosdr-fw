/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_tracking_iq_owner.h"
#include <string.h>

static int lock(struct glrt_tracking_iq_owner *o)
{
    return !o || !o->initialized || pthread_mutex_lock(&o->mutex) ? -1 : 0;
}
static int unlock(struct glrt_tracking_iq_owner *o, int rc)
{
    return pthread_mutex_unlock(&o->mutex) ? GLRT_RECENT_IQ_INVALID : rc;
}
static void lost(struct glrt_tracking_iq_owner *o)
{
    o->ring.valid=0; o->ring.count=0;
}

int glrt_tracking_iq_owner_init(struct glrt_tracking_iq_owner *o, int16_t *storage,
    size_t capacity, uint32_t epoch, uint64_t first)
{
    struct glrt_tracking_recent_iq ring;
    if (!o || o->initialized || glrt_tracking_recent_iq_reset(&ring,storage,capacity,epoch,first))
        return GLRT_RECENT_IQ_INVALID;
    if (pthread_mutex_init(&o->mutex,NULL)) return GLRT_RECENT_IQ_INVALID;
    o->ring=ring; o->source_now=first; o->observed_ns=0; o->generation=1;
    o->closed=0; o->initialized=1;
    return 0;
}

int glrt_tracking_iq_owner_publish(struct glrt_tracking_iq_owner *o, uint32_t epoch,
    uint64_t first, const int16_t *iq, size_t samples, uint64_t source_now, uint64_t observed_ns)
{
    int rc;
    if (lock(o)) return GLRT_RECENT_IQ_INVALID;
    if (epoch!=o->ring.epoch) return unlock(o,GLRT_RECENT_IQ_STALE);
    if (o->closed) return unlock(o,GLRT_IQ_OWNER_CLOSED);
    if (!o->ring.valid) return unlock(o,GLRT_RECENT_IQ_SOURCE_LOSS);
    if (!samples || !iq) return unlock(o,GLRT_RECENT_IQ_INVALID);
    if (samples>UINT64_MAX-first || source_now<first+samples || source_now<o->source_now ||
        !observed_ns || observed_ns<o->observed_ns || o->generation==UINT64_MAX) {
        lost(o); return unlock(o,GLRT_RECENT_IQ_SOURCE_LOSS);
    }
    rc=glrt_tracking_recent_iq_append(&o->ring,epoch,first,iq,samples);
    if (!rc) {
        o->source_now=source_now; o->observed_ns=observed_ns; o->generation++;
    }
    return unlock(o,rc);
}

int glrt_tracking_iq_owner_copy(struct glrt_tracking_iq_owner *o, uint32_t epoch,
    uint64_t first, int16_t *iq, size_t samples, struct glrt_tracking_iq_view *view)
{
    int rc;
    if (!view) return GLRT_RECENT_IQ_INVALID;
    memset(view,0,sizeof(*view));
    if (lock(o)) return GLRT_RECENT_IQ_INVALID;
    *view=(struct glrt_tracking_iq_view){o->ring.first,o->ring.end,o->source_now,
        o->observed_ns,o->generation,o->ring.epoch,o->ring.valid,o->closed};
    if (epoch!=o->ring.epoch) rc=GLRT_RECENT_IQ_STALE;
    else if (!o->ring.valid) rc=GLRT_RECENT_IQ_SOURCE_LOSS;
    else rc=samples ? glrt_tracking_recent_iq_read(&o->ring,epoch,first,iq,samples) : 0;
    return unlock(o,rc);
}

int glrt_tracking_iq_owner_close(struct glrt_tracking_iq_owner *o, int source_lost)
{
    if (lock(o)) return GLRT_RECENT_IQ_INVALID;
    o->closed=1;
    if (source_lost) lost(o);
    return unlock(o,0);
}

int glrt_tracking_iq_owner_destroy(struct glrt_tracking_iq_owner *o)
{
    if (!o || !o->initialized || !o->closed || pthread_mutex_destroy(&o->mutex))
        return GLRT_RECENT_IQ_INVALID;
    o->initialized=0;
    return 0;
}
