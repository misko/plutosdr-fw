/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_iq_tracking_source.h"
#include <string.h>

static uint64_t pair(const uint32_t *w, unsigned n)
{
    return w[n]|((uint64_t)w[n+1]<<32);
}

static void store(uint32_t *w, unsigned n, uint64_t value)
{
    w[n]=(uint32_t)value;w[n+1]=(uint32_t)(value>>32);
}

static int project(const struct glrt_capture_snapshot *native, uint32_t rate,
    struct glrt_capture_snapshot *coarse)
{
    uint64_t first, last, latest;
    uint32_t ratio, delay;
    unsigned n;
    if (!native || (rate!=30000000 && rate!=60000000)) return -1;
    ratio=rate/2500000;delay=53*ratio;
    if (native->words[62]!=rate || native->words[63]!=delay || native->readback_rate!=rate)
        return -1;
    /* GLI1 has no acquisition/event producer. Reject unexpected activity
     * before translating any coordinate into the software catch-up lane. */
    for(n=0;n<5;n++) if(native->cpu[n]) return -1;
    for(n=24;n<40;n++) if(native->words[n]) return -1;
    first=pair(native->words,0);last=pair(native->words,2);latest=pair(native->words,42);
    if (latest==UINT64_MAX) return -1;
    *coarse=*native;
    if (native->words[19]&8) {
        if(first<2*delay || first%ratio || last%ratio || last<first || latest<last) return -1;
        store(coarse->words,0,first/ratio-53);
        store(coarse->words,2,last/ratio-53);
    } else if (first || last) return -1;
    store(coarse->words,42,latest/ratio);
    coarse->readback_rate=2500000;coarse->words[62]=2500000;coarse->words[63]=0;
    return 0;
}

int glrt_iq_tracking_source_begin(struct glrt_iq_tracking_source *s, uint32_t visit,
    uint64_t samples, const struct glrt_capture_snapshot *baseline)
{
    struct glrt_capture_snapshot coarse;
    if(!s) return -1;
    memset(s,0,sizeof(*s));
    if(!baseline || project(baseline,baseline->words[62],&coarse) ||
       glrt_capture_source_begin(&s->coarse,visit,samples,&coarse)) return -1;
    s->native_rate=baseline->words[62];
    s->native_latest=pair(baseline->words,42);
    return 0;
}

int glrt_iq_tracking_source_take(struct glrt_iq_tracking_source *s,
    const struct glrt_capture_snapshot *snapshot, size_t samples, uint64_t *first, uint64_t *now)
{
    struct glrt_capture_snapshot coarse;
    int rc;
    if(first) *first=0;
    if(now) *now=0;
    if(!s) return -1;
    if(project(snapshot,s->native_rate,&coarse) || pair(snapshot->words,42)<s->native_latest) {
        s->coarse.valid=0;
        return -1;
    }
    rc=glrt_capture_source_take(&s->coarse,&coarse,samples,first,now);
    if(!rc) s->native_latest=pair(snapshot->words,42);
    return rc;
}
