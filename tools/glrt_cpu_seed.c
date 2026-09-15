/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_cpu_seed.h"
#include <string.h>

int glrt_cpu_seed_plan(const struct glrt_cpu_candidate *c, const struct glrt_tracking_iq_view *v,
    uint32_t maximum_age, struct glrt_cpu_seed *out)
{
    struct glrt_cpu_seed p={0};
    uint64_t origin;
    unsigned n;
    if(!out) return -1;
    memset(out,0,sizeof(*out));
    if(!c || !c->epoch || c->peak.epoch>=3333 || c->peak.frequency>=11 ||
       !c->peak.score || c->peak.score>65536 || c->window_start>UINT64_MAX-14000 ||
       !v || !maximum_age || maximum_age>2500000 || !v->valid || v->closed ||
       v->epoch!=c->epoch || !v->observed_ns || !v->generation ||
       v->first>v->end || v->end>v->source_now) return -1;
    if(v->source_now<c->window_start || v->source_now-c->window_start>maximum_age ||
       v->end<c->window_start+14000) return -2;
    origin=c->window_start+c->peak.epoch+22;
    /* Resolve the measured candidate before propagating it. A nominal jump
     * toward source_now has no timing-rate evidence and can move the true
     * pilot outside the resolver's eight-sample guard. Catch-up owns that
     * propagation after supported observations exist. */
    p.first=origin-8;
    if(p.first<v->first || p.first>v->end || GLRT_CPU_SEED_SAMPLES>v->end-p.first) return -2;
    p.start=origin;
    for(n=0;n<4;n++) p.starts[n]=(size_t)(8+((uint64_t)n*10000+1)/3);
    p.candidate=*c;p.maximum_age=maximum_age;p.selected=*v;
    *out=p;
    return 0;
}

int glrt_cpu_seed_copy(struct glrt_tracking_iq_owner *owner,const struct glrt_cpu_candidate *c,
    uint32_t maximum_age,int16_t *iq,size_t capacity,struct glrt_cpu_seed *out)
{
    struct glrt_tracking_iq_view view;
    struct glrt_cpu_seed p;
    int rc;
    if(!out) return -1;
    memset(out,0,sizeof(*out));
    if(!c || !iq || capacity<GLRT_CPU_SEED_SAMPLES) return -1;
    if(glrt_tracking_iq_owner_copy(owner,c->epoch,0,NULL,0,&view)) return -2;
    rc=glrt_cpu_seed_plan(c,&view,maximum_age,&p);
    if(rc) return rc;
    if(glrt_tracking_iq_owner_copy(owner,c->epoch,p.first,iq,GLRT_CPU_SEED_SAMPLES,&p.copied) ||
       p.copied.closed || p.copied.source_now<c->window_start ||
       p.copied.source_now-c->window_start>maximum_age) return -2;
    *out=p;
    return 0;
}

static int resolve_ready(const struct glrt_cpu_seed *p,uint64_t deadline,
    struct glrt_resolver_result *out,struct glrt_tracking_bootstrap_live *live)
{
    struct glrt_cpu_seed expected;
    unsigned n;
    if(out) memset(out,0,sizeof(*out));
    if(live) memset(live,0,sizeof(*live));
    if(!p || !out || !live || glrt_cpu_seed_plan(&p->candidate,&p->selected,p->maximum_age,&expected) ||
       p->first!=expected.first || p->start!=expected.start || p->fraction!=expected.fraction ||
       p->first_repeat!=expected.first_repeat || !p->copied.valid || p->copied.closed ||
       p->copied.epoch!=p->candidate.epoch || p->copied.first>p->first ||
       p->copied.end<p->first || p->copied.end-p->first<GLRT_CPU_SEED_SAMPLES ||
       p->copied.end>p->copied.source_now || p->copied.source_now<p->selected.source_now ||
       p->copied.observed_ns<p->selected.observed_ns || p->copied.generation<p->selected.generation ||
       p->copied.source_now-p->candidate.window_start>p->maximum_age ||
       deadline<=p->copied.source_now) return -1;
    for(n=0;n<4;n++) if(p->starts[n]!=expected.starts[n]) return -1;
    return 0;
}

static int initialize(const struct glrt_cpu_seed *p,uint64_t deadline,
    struct glrt_resolver_result *out,struct glrt_tracking_bootstrap_live *live)
{
    uint64_t origin=p->start;
    int64_t shift=out->best.shift;
    if((shift<0 && origin<(uint64_t)-shift) || (shift>=0 && origin>UINT64_MAX-(uint64_t)shift)) goto bad;
    origin=shift<0 ? origin-(uint64_t)-shift : origin+(uint64_t)shift;
    if(glrt_tracking_bootstrap_live_init(live,p->candidate.epoch,origin,p->fraction,
                                        out->best.cfo_hz,deadline)) goto bad;
    return 0;
bad:
    memset(out,0,sizeof(*out));memset(live,0,sizeof(*live));return -1;
}

int glrt_cpu_seed_resolve(const struct glrt_cpu_seed *p,struct glrt_resolver_workspace *workspace,
    const int16_t *reference,const int16_t *iq,glrt_resolver_fft fft,void *context,
    uint64_t deadline,struct glrt_resolver_result *out,struct glrt_tracking_bootstrap_live *live)
{
    if(resolve_ready(p,deadline,out,live)) return -1;
    if(glrt_tracking_resolve_2500000(workspace,reference,3300,iq,GLRT_CPU_SEED_SAMPLES,
                                    p->starts,4,fft,context,out)) return -1;
    return initialize(p,deadline,out,live);
}

int glrt_cpu_seed_resolve_local(const struct glrt_cpu_seed *p,struct glrt_resolver_workspace *workspace,
    const int16_t *reference,const int16_t *iq,uint32_t radius,glrt_resolver_fft fft,void *context,
    uint64_t deadline,struct glrt_resolver_result *out,struct glrt_tracking_bootstrap_live *live)
{
    struct glrt_resolver_peak best;
    if(resolve_ready(p,deadline,out,live) || !radius || radius>8) return -1;
    if(glrt_tracking_resolve_2500000_local(workspace,reference,3300,iq,GLRT_CPU_SEED_SAMPLES,
                                          p->starts,4,radius,fft,context,&best)) return -1;
    out->best=best;
    return initialize(p,deadline,out,live);
}
