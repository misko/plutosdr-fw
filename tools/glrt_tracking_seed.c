/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_tracking_seed.h"
#include <string.h>

#define RATE 2500000U
#define WINDOW 14000U
#define GUARD 8U
#define PILOT_OFFSET 22U

static uint64_t pair(const uint32_t *w) { return w[0]|((uint64_t)w[1]<<32); }
int glrt_tracking_seed_event(const uint32_t w[16])
{
    uint32_t flags,reasons;
    int64_t units;
    unsigned i;
    if(!w || w[0]!=UINT32_C(0x474c4131) || !w[1]) return GLRT_SEED_INVALID;
    flags=w[5];reasons=(flags>>1)&31;
    units=w[6]<=INT32_MAX ? (int64_t)w[6] : (int64_t)w[6]-INT64_C(4294967296);
    if(flags>>28 || ((flags>>16)&4095)>=3333 || ((flags>>12)&15)>10 ||
        ((flags>>6)&7)>4 || units < -4000 || units>4000 || w[12]!=WINDOW ||
        w[13] || w[14] || w[15] || pair(w+3)>UINT64_MAX-WINDOW+1)
        return GLRT_SEED_INVALID;
    for(i=7;i<12;i++) if(w[i]>65536) return GLRT_SEED_INVALID;
    if(reasons&1) {
        if(flags!=3) return GLRT_SEED_INVALID;
        for(i=6;i<12;i++) if(w[i]) return GLRT_SEED_INVALID;
    } else if(!w[7] || (!(flags&1) && reasons)) return GLRT_SEED_INVALID;
    return (flags&1) && !reasons ? GLRT_SEED_READY : GLRT_SEED_IGNORE;
}

int glrt_tracking_seed_plan(const uint32_t event[16], const struct glrt_tracking_iq_view *v,
    uint32_t maximum_age, struct glrt_tracking_seed_window *out)
{
    struct glrt_tracking_seed_window p={0};
    uint64_t origin,distance,last,advance,rounded;
    unsigned n;
    int rc;
    if(!out) return GLRT_SEED_INVALID;
    memset(out,0,sizeof(*out));
    rc=glrt_tracking_seed_event(event);
    if(rc!=GLRT_SEED_READY) return rc;
    if(!v || !maximum_age || maximum_age>RATE || !v->valid || v->closed ||
        v->epoch!=event[1] || !v->observed_ns || !v->generation ||
        v->first>v->end || v->end>v->source_now) return GLRT_SEED_INVALID;
    origin=pair(event+3);
    if(v->source_now<origin || v->source_now-origin>maximum_age ||
        v->source_now-origin<WINDOW) return GLRT_SEED_UNAVAILABLE;
    origin+=(event[5]>>16)&4095;
    origin+=PILOT_OFFSET; /* safe after the complete-window overflow guard */
    if(v->end<origin || v->end-origin<GLRT_RESOLVER_SAMPLES+GUARD)
        return GLRT_SEED_UNAVAILABLE;
    distance=v->end-origin-GLRT_RESOLVER_SAMPLES-GUARD;
    /* floor(distance*3/10000), without overflowing the original source index. */
    last=(distance/10000)*3+(distance%10000)*3/10000;
    if(last<63 || last-63>UINT32_MAX) return GLRT_SEED_UNAVAILABLE;
    p.first_repeat=(uint32_t)(last-63);
    advance=(uint64_t)p.first_repeat*10000;
    rounded=(advance+1)/3;
    p.first=origin+rounded-GUARD;
    if(p.first<v->first || p.first>v->end || GLRT_SEED_WINDOW_SAMPLES>v->end-p.first)
        return GLRT_SEED_UNAVAILABLE;
    p.seed_start=origin+advance/3;
    p.seed_fraction=(uint32_t)(((advance%3)*65536+1)/3);
    for(n=0;n<4;n++) p.starts[n]=(size_t)(GUARD+(advance+(uint64_t)n*10000+1)/3-rounded);
    memcpy(p.event,event,sizeof(p.event));p.maximum_age=maximum_age;p.selected=*v;
    *out=p;
    return GLRT_SEED_READY;
}

int glrt_tracking_seed_copy(struct glrt_tracking_iq_owner *o, const uint32_t event[16],
    uint32_t maximum_age, int16_t *iq, size_t capacity, struct glrt_tracking_seed_window *out)
{
    struct glrt_tracking_iq_view v;
    struct glrt_tracking_seed_window p;
    int rc;
    if(!out) return GLRT_SEED_INVALID;
    memset(out,0,sizeof(*out));
    rc=glrt_tracking_seed_event(event);
    if(rc!=GLRT_SEED_READY) return rc;
    if(!iq || capacity<GLRT_SEED_WINDOW_SAMPLES) return GLRT_SEED_INVALID;
    if(glrt_tracking_iq_owner_copy(o,event[1],0,NULL,0,&v)) return GLRT_SEED_UNAVAILABLE;
    rc=glrt_tracking_seed_plan(event,&v,maximum_age,&p);
    if(rc!=GLRT_SEED_READY) return rc;
    if(glrt_tracking_iq_owner_copy(o,event[1],p.first,iq,GLRT_SEED_WINDOW_SAMPLES,&p.copied) ||
        p.copied.closed || p.copied.source_now<pair(event+3) ||
        p.copied.source_now-pair(event+3)>maximum_age) return GLRT_SEED_UNAVAILABLE;
    *out=p;
    return GLRT_SEED_READY;
}

int glrt_tracking_seed_resolve(const struct glrt_tracking_seed_window *w,
    struct glrt_resolver_workspace *work, const int16_t *ref, const int16_t *iq,
    glrt_resolver_fft fft, void *context, uint64_t deadline,
    struct glrt_resolver_result *out, struct glrt_tracking_bootstrap_live *live)
{
    struct glrt_tracking_seed_window expected;
    uint64_t origin;
    int64_t shift;
    unsigned n;
    if(out) memset(out,0,sizeof(*out));
    if(live) memset(live,0,sizeof(*live));
    if(!out || !live || !w ||
        glrt_tracking_seed_plan(w->event,&w->selected,w->maximum_age,&expected)!=GLRT_SEED_READY ||
        w->first!=expected.first || w->seed_start!=expected.seed_start ||
        w->seed_fraction!=expected.seed_fraction || w->first_repeat!=expected.first_repeat ||
        !w->copied.valid || w->copied.closed || w->copied.epoch!=w->event[1] ||
        w->copied.first>w->first || w->copied.end<w->first ||
        w->copied.end-w->first<GLRT_SEED_WINDOW_SAMPLES || w->copied.end>w->copied.source_now ||
        w->copied.source_now<w->selected.source_now || w->copied.observed_ns<w->selected.observed_ns ||
        w->copied.generation<w->selected.generation ||
        w->copied.source_now-pair(w->event+3)>w->maximum_age || deadline<=w->copied.source_now)
        return GLRT_SEED_INVALID;
    for(n=0;n<4;n++) if(w->starts[n]!=expected.starts[n]) return GLRT_SEED_INVALID;
    if(glrt_tracking_resolve_2500000(work,ref,3300,iq,GLRT_SEED_WINDOW_SAMPLES,w->starts,4,fft,context,out))
        return GLRT_SEED_INVALID;
    origin=w->seed_start;shift=out->best.shift;
    if((shift<0 && origin<(uint64_t)-shift) || (shift>=0 && origin>UINT64_MAX-(uint64_t)shift))
        goto bad;
    origin=shift<0 ? origin-(uint64_t)-shift : origin+(uint64_t)shift;
    if(glrt_tracking_bootstrap_live_init(live,w->event[1],origin,w->seed_fraction,out->best.cfo_hz,deadline))
        goto bad;
    return GLRT_SEED_READY;
bad:
    memset(out,0,sizeof(*out));memset(live,0,sizeof(*live));
    return GLRT_SEED_INVALID;
}
