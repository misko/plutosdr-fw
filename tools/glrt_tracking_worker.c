/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_tracking_worker.h"
#include <string.h>

struct execution {
    struct glrt_tracking_worker *work;
    const struct glrt_tracking_worker_config *config;
};

static int stop(struct glrt_tracking_worker *w, int status)
{
    w->status=status;w->live.core.valid=0;w->live.core.pending=0;w->live.core.ready=0;
    memset(&w->trace.handoff,0,sizeof(w->trace.handoff));
    return status;
}

static int poll(struct execution *e)
{
    struct glrt_tracking_worker *w=e->work;
    const struct glrt_tracking_worker_ports *p=&e->config->ports;
    uint64_t now=p->clock_ns(p->context);
    int cancelled;
    if(!now || now<w->last_ns) return stop(w,GLRT_WORKER_PORT);
    w->last_ns=now;
    if(now>=w->deadline_ns) return stop(w,GLRT_WORKER_DEADLINE);
    cancelled=p->cancelled(p->context);
    if(cancelled==1) return stop(w,GLRT_WORKER_CANCELLED);
    return cancelled ? stop(w,GLRT_WORKER_PORT) : 0;
}

static int guarded_fft(void *context, double (*bins)[2], size_t count)
{
    struct execution *e=context;
    int rc;
    if(poll(e)) return -1;
    e->work->fft_calls++;
    rc=e->config->fft(e->config->fft_context,bins,count);
    return poll(e) ? -1 : rc;
}

static int retain(struct execution *e, enum glrt_tracking_worker_record kind)
{
    const struct glrt_tracking_worker_ports *p=&e->config->ports;
    if(poll(e)) return e->work->status;
    if(p->retain(p->context,kind,e->work)) return stop(e->work,GLRT_WORKER_RETENTION);
    return poll(e);
}

static int source(struct execution *e, int handoff)
{
    const struct glrt_tracking_worker_config *cfg=e->config;
    struct glrt_tracking_worker *w=e->work;
    struct glrt_tracking_iq_view v={0};
    int rc=glrt_tracking_iq_owner_copy(cfg->owner,w->seed.event[1],0,NULL,0,&v);
    w->checked_source=v;w->source_checked_ns=0;
    if(poll(e)) return w->status;
    w->source_checked_ns=w->last_ns;
    if(rc || !v.valid || v.closed) return stop(w,GLRT_WORKER_SOURCE);
    if(!v.observed_ns || v.observed_ns>w->last_ns) return stop(w,GLRT_WORKER_PORT);
    if(v.source_now>cfg->source_deadline) return stop(w,GLRT_WORKER_DEADLINE);
    if(handoff && (v.source_now>UINT64_MAX-cfg->lead_samples ||
        w->trace.job.start<v.source_now+cfg->lead_samples)) return stop(w,GLRT_WORKER_STALE);
    return 0;
}

int glrt_tracking_worker_run(struct glrt_tracking_worker *w,
    const struct glrt_tracking_worker_config *cfg, const uint32_t event[16])
{
    struct execution execution={w,cfg};
    unsigned n;
    int rc;
    if(!w) return GLRT_WORKER_INVALID;
    memset(w,0,sizeof(*w));
    if(!cfg || !cfg->owner || !cfg->references || !cfg->fft || !cfg->ports.clock_ns ||
        !cfg->ports.cancelled || !cfg->ports.wait || !cfg->ports.retain ||
        !cfg->wall_budget_ns || cfg->wall_budget_ns>UINT64_C(5000000000) ||
        !cfg->source_deadline || !cfg->lead_samples ||
        !cfg->maximum_seed_age || cfg->maximum_seed_age>2500000U)
        return stop(w,GLRT_WORKER_INVALID);
    w->started_ns=w->last_ns=cfg->ports.clock_ns(cfg->ports.context);
    if(!w->started_ns || cfg->wall_budget_ns>UINT64_MAX-w->started_ns)
        return stop(w,GLRT_WORKER_PORT);
    w->deadline_ns=w->started_ns+cfg->wall_budget_ns;w->status=GLRT_WORKER_RUNNING;
    if(poll(&execution)) return w->status;
    rc=glrt_tracking_seed_copy(cfg->owner,event,cfg->maximum_seed_age,w->seed_iq,
        GLRT_SEED_WINDOW_SAMPLES,&w->seed);
    if(rc==GLRT_SEED_IGNORE) return stop(w,GLRT_WORKER_IGNORED);
    if(rc!=GLRT_SEED_READY)
        return stop(w,rc==GLRT_SEED_INVALID ? GLRT_WORKER_INVALID : GLRT_WORKER_SOURCE);
    if(source(&execution,0) || retain(&execution,GLRT_WORKER_SEED_IQ)) return w->status;
    for(n=0;n<3300;n++) {
        w->reference[2*n]=cfg->references[4*n];w->reference[2*n+1]=cfg->references[4*n+1];
    }
    rc=glrt_tracking_seed_resolve(&w->seed,&w->fft_workspace,w->reference,w->seed_iq,
        guarded_fft,&execution,cfg->source_deadline,&w->resolved,&w->live);
    if(rc!=GLRT_SEED_READY)
        return stop(w,w->status<0 ? w->status : GLRT_WORKER_INVALID);
    if(source(&execution,0) || retain(&execution,GLRT_WORKER_RESOLVED)) return w->status;
    for(;;) {
        if(poll(&execution)) return w->status;
        rc=glrt_tracking_live_bootstrap_step(&w->live,cfg->owner,cfg->references,w->scratch,
            cfg->lead_samples,&w->trace);
        if(rc==GLRT_BOOTSTRAP_PAST) {
            if(retain(&execution,GLRT_WORKER_PAST)) return w->status;
            w->retained_past++;
        } else if(rc==GLRT_BOOTSTRAP_WAIT) {
            w->waits++;
            if(cfg->ports.wait(cfg->ports.context)) return stop(w,GLRT_WORKER_PORT);
        } else if(rc==GLRT_BOOTSTRAP_READY) {
            if(source(&execution,1) || retain(&execution,GLRT_WORKER_HANDOFF) || source(&execution,1))
                return w->status;
            w->status=GLRT_WORKER_READY;return w->status;
        } else return stop(w,w->live.core.failure==GLRT_BOOTSTRAP_SOURCE_LOSS ? GLRT_WORKER_SOURCE :
            w->live.core.failure==GLRT_BOOTSTRAP_BUDGET ? GLRT_WORKER_DEADLINE : GLRT_WORKER_HISTORY);
    }
}
