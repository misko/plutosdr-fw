/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_tracking_observer.h"
#include "glrt_tracking_iq.h"
#include <string.h>

static int finish(struct glrt_tracking_observer *s,
    struct glrt_tracking_observer_trace *trace, int result)
{
    if(s) s->status=result;
    if(trace) memset(trace,0,sizeof(*trace));
    return result;
}

int glrt_tracking_observer_init(struct glrt_tracking_observer *s,
    const struct glrt_tracking_trend *history, uint32_t first, uint32_t maximum,
    uint64_t source_limit, uint64_t now, uint64_t budget)
{
    return glrt_tracking_observer_init_cadence(s,history,first,9,maximum,source_limit,now,budget);
}

int glrt_tracking_observer_init_cadence(struct glrt_tracking_observer *s,
    const struct glrt_tracking_trend *history, uint32_t first, uint32_t spacing,
    uint32_t maximum, uint64_t source_limit, uint64_t now, uint64_t budget)
{
    struct glrt_tracking_trend retained;
    struct glrt_tracking_batch batch;
    struct glrt_tracking_job job;
    double slope;
    if(!s) return -1;
    if(history) retained=*history;
    memset(s,0,sizeof(*s));s->status=GLRT_OBSERVER_INVALID;
    if(!history || retained.rate!=2500000 || (spacing!=3 && spacing!=9) || !maximum || maximum>1024 ||
       !now || !budget || budget>UINT64_C(15000000000) || now>UINT64_MAX-budget ||
       !glrt_tracking_trend_handoff_valid(&retained,first,maximum*spacing) ||
       glrt_tracking_trend_batch(&retained,first,1,1,0,&batch,&slope) ||
       glrt_tracking_prediction(&batch,0,&job) || job.start>UINT64_MAX-3300 ||
       source_limit<job.start+3300 || source_limit-job.start>30000000) return -1;
    s->trend=retained;s->next_frame=first;s->maximum_measurements=maximum;
    s->frame_spacing=spacing;
    s->deadline_ns=now+budget;s->last_ns=now;s->source_limit=source_limit;
    s->status=GLRT_OBSERVER_WAIT;
    return 0;
}

static int guard(struct glrt_tracking_observer *s, struct glrt_tracking_iq_owner *owner,
    const struct glrt_tracking_observer_ports *ports, struct glrt_tracking_iq_view *view)
{
    uint64_t now=ports->clock_ns(ports->context);
    int cancelled=ports->cancelled(ports->context);
    if(cancelled) return cancelled==1 ? GLRT_OBSERVER_CANCELLED : GLRT_OBSERVER_INVALID;
    if(!now || now<s->last_ns || now>=s->deadline_ns) return GLRT_OBSERVER_DEADLINE;
    s->last_ns=now;
    if(glrt_tracking_iq_owner_copy(owner,s->trend.history.epoch,0,NULL,0,view) ||
       !view->valid || view->closed || view->source_now<s->last_source ||
       view->end>view->source_now) return GLRT_OBSERVER_SOURCE;
    /* A producer can publish while we wait for the owner lock. Compare its
     * timestamp to a clock read AFTER the copied view, not the earlier one. */
    now=ports->clock_ns(ports->context);
    if(!now || now<s->last_ns || now>=s->deadline_ns) return GLRT_OBSERVER_DEADLINE;
    s->last_ns=now;
    if(view->observed_ns>now) return GLRT_OBSERVER_SOURCE;
    s->last_source=view->source_now;
    if(view->source_now>s->source_limit) return GLRT_OBSERVER_DONE;
    return GLRT_OBSERVER_WAIT;
}

int glrt_tracking_observer_step(struct glrt_tracking_observer *s,
    struct glrt_tracking_iq_owner *owner, const int16_t *refs, int16_t *scratch,
    const struct glrt_tracking_observer_ports *ports, struct glrt_tracking_observer_trace *trace)
{
    struct glrt_tracking_trend pending;
    struct glrt_tracking_batch batch;
    struct glrt_tracking_iq_view checked;
    struct glrt_tracking_observer_trace next;
    double slope;
    int rc;
    if(trace) memset(trace,0,sizeof(*trace));
    if(!s || !trace || !refs || !scratch || !ports || !ports->clock_ns ||
       !ports->cancelled || !ports->retain) return finish(s,trace,GLRT_OBSERVER_INVALID);
    if(s->status!=GLRT_OBSERVER_WAIT) return s->status;
    if(s->trend.rate!=2500000 || !s->maximum_measurements || s->maximum_measurements>1024 ||
       (s->frame_spacing!=3 && s->frame_spacing!=9))
        return finish(s,trace,GLRT_OBSERVER_INVALID);
    if(s->measurements>=s->maximum_measurements) return finish(s,trace,GLRT_OBSERVER_DONE);
    rc=guard(s,owner,ports,&checked);
    if(rc!=GLRT_OBSERVER_WAIT) return finish(s,trace,rc);
    if(!checked.observed_ns) return GLRT_OBSERVER_WAIT;
    memset(&next,0,sizeof(next));next.frame=s->next_frame;
    if(glrt_tracking_trend_batch(&s->trend,next.frame,1,s->measurements+1,0,&batch,&slope) ||
       glrt_tracking_prediction(&batch,0,&next.job)) return finish(s,trace,GLRT_OBSERVER_HISTORY);
    if(next.job.start>UINT64_MAX-3300) return finish(s,trace,GLRT_OBSERVER_INVALID);
    if(next.job.start+3300>s->source_limit) return finish(s,trace,GLRT_OBSERVER_DONE);
    if(next.job.start<checked.first) return finish(s,trace,GLRT_OBSERVER_SOURCE);
    if(next.job.start+3300>checked.end) return GLRT_OBSERVER_WAIT;
    if(glrt_tracking_iq_owner_copy(owner,s->trend.history.epoch,next.job.start,scratch,3300,&next.source) ||
       !next.source.valid || next.source.closed) return finish(s,trace,GLRT_OBSERVER_SOURCE);
    if(glrt_tracking_iq_moments_2500000(scratch,refs+13200*next.job.reference_phase,3300,
           next.job.start,0,next.job.phase_step,&next.moments) ||
       glrt_tracking_solve(2500000,next.job.reference_phase,&next.moments,&next.estimate))
        return finish(s,trace,GLRT_OBSERVER_INVALID);
    pending=s->trend;
    next.accepted=glrt_tracking_trend_observe(&pending,pending.history.epoch,next.frame,
        next.job.start,next.job.reference_phase,&next.estimate);
    if(next.accepted<0) return finish(s,trace,GLRT_OBSERVER_HISTORY);
    rc=guard(s,owner,ports,&checked);
    if(rc!=GLRT_OBSERVER_WAIT) return finish(s,trace,rc);
    if(ports->retain(ports->context,&next,scratch)) return finish(s,trace,GLRT_OBSERVER_RETENTION);
    rc=guard(s,owner,ports,&checked);
    if(rc!=GLRT_OBSERVER_WAIT) return finish(s,trace,rc);
    s->trend=pending;s->measurements++;s->next_frame+=s->frame_spacing;
    *trace=next;
    return GLRT_OBSERVER_MEASURED;
}
