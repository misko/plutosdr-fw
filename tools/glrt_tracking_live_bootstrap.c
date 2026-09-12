/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_tracking_live_bootstrap.h"
#include "glrt_tracking_iq.h"
#include <string.h>

static int fail(struct glrt_tracking_bootstrap_live *s,
    struct glrt_tracking_bootstrap_trace *t, uint32_t reason)
{
    if(s) { s->core.valid=0; s->core.pending=0; s->core.failure=reason; }
    if(t) memset(t,0,sizeof(*t));
    return GLRT_BOOTSTRAP_ERROR;
}

int glrt_tracking_live_bootstrap_step(struct glrt_tracking_bootstrap_live *s,
    struct glrt_tracking_iq_owner *o, const int16_t *refs, int16_t *scratch,
    uint32_t lead, struct glrt_tracking_bootstrap_trace *t)
{
    int rc;
    uint32_t epoch;
    if(!s || !s->core.valid || s->core.pending || s->core.ready ||
        s->core.trend.rate!=2500000 || !refs || !scratch || !t || !lead)
        return fail(s,t,GLRT_BOOTSTRAP_INVALID);
    memset(t,0,sizeof(*t));
    epoch=s->core.trend.history.epoch;
    if(glrt_tracking_iq_owner_copy(o,epoch,0,NULL,0,&t->source) || t->source.closed)
        return fail(s,t,GLRT_BOOTSTRAP_SOURCE_LOSS);
    if(!t->source.observed_ns) return GLRT_BOOTSTRAP_WAIT;
    rc=glrt_tracking_bootstrap_live_next(s,t->source.first,t->source.end,t->source.source_now,
        lead,&t->frame,&t->job,&t->handoff);
    if(rc!=GLRT_BOOTSTRAP_PAST) return rc;
    if(glrt_tracking_iq_owner_copy(o,epoch,t->job.start,scratch,3300,&t->source) || t->source.closed)
        return fail(s,t,GLRT_BOOTSTRAP_SOURCE_LOSS);
    // owner_copy has released the mutex. Ingestion can now advance or wrap
    // while this worker computes on its independent, source-bound IQ copy.
    if(glrt_tracking_iq_moments_2500000(scratch,refs+13200*t->job.reference_phase,3300,
            t->job.start,0,t->job.phase_step,&t->moments) ||
        glrt_tracking_solve(2500000,t->job.reference_phase,&t->moments,&t->estimate))
        return fail(s,t,GLRT_BOOTSTRAP_INVALID);
    t->accepted=glrt_tracking_bootstrap_observe(&s->core,epoch,t->frame,&t->job,&t->estimate);
    if(t->accepted<0) return fail(s,t,GLRT_BOOTSTRAP_INVALID);
    return GLRT_BOOTSTRAP_PAST;
}
