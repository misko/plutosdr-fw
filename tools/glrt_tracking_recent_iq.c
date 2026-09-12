/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_tracking_recent_iq.h"
#include <string.h>

#define IQ_BYTES (2*sizeof(int16_t))

int glrt_tracking_recent_iq_reset(struct glrt_tracking_recent_iq *r, int16_t *storage,
    size_t capacity, uint32_t epoch, uint64_t first)
{
    if (!r) return GLRT_RECENT_IQ_INVALID;
    memset(r,0,sizeof(*r));
    if (!storage || !capacity || capacity>PTRDIFF_MAX/IQ_BYTES || !epoch)
        return GLRT_RECENT_IQ_INVALID;
    r->iq=storage; r->capacity=capacity; r->epoch=epoch;
    r->first=r->end=first; r->valid=1;
    return GLRT_RECENT_IQ_OK;
}

int glrt_tracking_recent_iq_append(struct glrt_tracking_recent_iq *r, uint32_t epoch,
    uint64_t first, const int16_t *iq, size_t samples)
{
    size_t evict, position, part;
    if (!r) return GLRT_RECENT_IQ_INVALID;
    if (epoch!=r->epoch) return GLRT_RECENT_IQ_STALE;
    if (!r->valid) return GLRT_RECENT_IQ_SOURCE_LOSS;
    if ((!iq && samples) || samples>PTRDIFF_MAX/IQ_BYTES)
        return GLRT_RECENT_IQ_INVALID;
    if (first!=r->end || samples>UINT64_MAX-r->end) {
        r->valid=0; r->count=0; r->first=r->end;
        return GLRT_RECENT_IQ_SOURCE_LOSS;
    }
    if (!samples) return GLRT_RECENT_IQ_OK;
    if (samples>=r->capacity) {
        memcpy(r->iq,iq+2*(samples-r->capacity),r->capacity*IQ_BYTES);
        r->head=0; r->count=r->capacity;
    } else {
        evict=r->count+samples>r->capacity ? r->count+samples-r->capacity : 0;
        r->head=(r->head+evict)%r->capacity; r->count-=evict;
        position=(r->head+r->count)%r->capacity;
        part=samples<r->capacity-position ? samples : r->capacity-position;
        memcpy(r->iq+2*position,iq,part*IQ_BYTES);
        if (part<samples) memcpy(r->iq,iq+2*part,(samples-part)*IQ_BYTES);
        r->count+=samples;
    }
    r->end+=samples; r->first=r->end-r->count;
    return GLRT_RECENT_IQ_OK;
}

int glrt_tracking_recent_iq_read(const struct glrt_tracking_recent_iq *r, uint32_t epoch,
    uint64_t first, int16_t *out, size_t samples)
{
    size_t position, part;
    if (!r) return GLRT_RECENT_IQ_INVALID;
    if (epoch!=r->epoch) return GLRT_RECENT_IQ_STALE;
    if (!r->valid) return GLRT_RECENT_IQ_SOURCE_LOSS;
    if ((!out && samples) || samples>PTRDIFF_MAX/IQ_BYTES || samples>UINT64_MAX-first)
        return GLRT_RECENT_IQ_INVALID;
    if (first<r->first) return GLRT_RECENT_IQ_OVERWRITTEN;
    if (first>r->end || samples>r->end-first) return GLRT_RECENT_IQ_NOT_READY;
    if (!samples) return GLRT_RECENT_IQ_OK;
    position=(r->head+(size_t)(first-r->first))%r->capacity;
    part=samples<r->capacity-position ? samples : r->capacity-position;
    memcpy(out,r->iq+2*position,part*IQ_BYTES);
    if (part<samples) memcpy(out+2*part,r->iq,(samples-part)*IQ_BYTES);
    return GLRT_RECENT_IQ_OK;
}
