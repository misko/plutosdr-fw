/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_tracking_bootstrap.h"
#include <math.h>
#include <string.h>

#define RATE 2500000U
#define SAMPLES 3300U

static int fail(struct glrt_tracking_bootstrap *s, uint32_t reason)
{
    if (s) { s->valid=0; s->pending=0; s->failure=reason; }
    return GLRT_BOOTSTRAP_ERROR;
}

static double round_even(double value)
{
    double lo=floor(value), fraction=value-lo;
    return lo+(fraction>.5 || (fraction==.5 && fmod(lo,2)!=0));
}

static uint64_t phase(double hz)
{
    double value=fmod(round_even(hz/RATE*0x1p48),0x1p48);
    if (value<0) value+=0x1p48;
    return (uint64_t)value;
}

int glrt_tracking_bootstrap_init(struct glrt_tracking_bootstrap *s, uint32_t epoch,
    uint64_t start, uint32_t fraction, double cfo)
{
    if (!s) return -1;
    memset(s,0,sizeof(*s));
    if (!epoch || fraction>=65536 || !isfinite(cfo) || fabs(cfo)+250>=RATE/2.0 ||
        start>UINT64_MAX-SAMPLES || glrt_tracking_trend_reset(&s->trend,epoch,RATE))
        return fail(s,GLRT_BOOTSTRAP_INVALID);
    s->seed_start=start; s->seed_fraction=fraction; s->seed_cfo=cfo; s->valid=1;
    return 0;
}

int glrt_tracking_bootstrap_next(struct glrt_tracking_bootstrap *s, uint64_t earliest,
    uint64_t available, uint32_t lead, uint32_t *frame,
    struct glrt_tracking_job *out, struct glrt_tracking_batch *handoff)
{
    struct glrt_tracking_batch batch;
    struct glrt_tracking_job job;
    uint32_t target, first, last;
    double slope;
    if (frame) *frame=0;
    if (out) memset(out,0,sizeof(*out));
    if (handoff) memset(handoff,0,sizeof(*handoff));
    if (!s || !frame || !out || !handoff || !s->valid || s->pending || s->ready ||
        !lead || available>UINT64_MAX-lead || earliest>available)
        return fail(s,GLRT_BOOTSTRAP_INVALID);
    if (s->clock_seen && available<s->last_available)
        return fail(s,GLRT_BOOTSTRAP_SOURCE_LOSS);
    s->last_available=available; s->clock_seen=1;
    if (s->jobs>=GLRT_BOOTSTRAP_LIMIT) return fail(s,GLRT_BOOTSTRAP_BUDGET);
    target=s->jobs*GLRT_BOOTSTRAP_SPACING;
    if (s->jobs<8) {
        /* Nine 750-Hz repeats span exactly 30,000 coarse samples. */
        uint64_t advance=(uint64_t)(target-s->seed_frame)*RATE/750;
        if (s->seed_start>UINT64_MAX-advance) return fail(s,GLRT_BOOTSTRAP_INVALID);
        batch=(struct glrt_tracking_batch){.rate=RATE,.prediction={
            .epoch=s->trend.history.epoch,.tag=1,.start=s->seed_start+advance,
            .fraction=s->seed_fraction,.period=UINT64_C(218453333),
            .step=phase(s->seed_cfo),.expires=UINT64_MAX,.repeats=1}};
    } else if (glrt_tracking_trend_batch(&s->trend,target,1,1,0,&batch,&slope))
        return fail(s,GLRT_BOOTSTRAP_HISTORY);
    if (glrt_tracking_prediction(&batch,0,&job) || job.start>UINT64_MAX-SAMPLES)
        return fail(s,GLRT_BOOTSTRAP_INVALID);
    if (job.start<earliest) return fail(s,GLRT_BOOTSTRAP_SOURCE_LOSS);
    if (job.start+SAMPLES<=available) {
        s->pending=1; s->pending_job=job; *frame=target; *out=job;
        return GLRT_BOOTSTRAP_PAST;
    }
    if (s->jobs<8) return fail(s,GLRT_BOOTSTRAP_HISTORY);
    first=target-GLRT_BOOTSTRAP_SPACING+1;
    last=target+GLRT_BOOTSTRAP_SPACING;
    for (; first<=last; first++) {
        if (glrt_tracking_trend_batch(&s->trend,first,8,1,0,&batch,&slope) ||
            glrt_tracking_prediction(&batch,0,&job)) continue;
        if (job.start>=available+lead) {
            s->ready=1; *frame=first; *out=job; *handoff=batch;
            return GLRT_BOOTSTRAP_READY;
        }
    }
    return fail(s,GLRT_BOOTSTRAP_FUTURE);
}

int glrt_tracking_bootstrap_observe(struct glrt_tracking_bootstrap *s, uint32_t epoch,
    uint32_t frame, const struct glrt_tracking_job *job, const struct glrt_native_estimate *estimate)
{
    int rc;
    if (!s || !s->valid || !s->pending || !job || !estimate || epoch!=s->trend.history.epoch ||
        frame!=s->jobs*GLRT_BOOTSTRAP_SPACING || job->start!=s->pending_job.start ||
        job->phase_step!=s->pending_job.phase_step || job->reference_phase!=s->pending_job.reference_phase)
        return fail(s,GLRT_BOOTSTRAP_INVALID);
    rc=glrt_tracking_trend_observe(&s->trend,epoch,frame,job->start,job->reference_phase,estimate);
    if (rc<0) return fail(s,GLRT_BOOTSTRAP_INVALID);
    if (rc==1 && s->jobs<8) {
        double correction=round_even((job->reference_phase/4.0+estimate->delay_correction_s*RATE)*65536);
        int64_t whole=(int64_t)floor(correction/65536);
        if ((whole<0 && job->start<(uint64_t)-whole) ||
            (whole>=0 && job->start>UINT64_MAX-(uint64_t)whole))
            return fail(s,GLRT_BOOTSTRAP_INVALID);
        s->seed_start=whole<0 ? job->start-(uint64_t)-whole : job->start+(uint64_t)whole;
        s->seed_fraction=(uint32_t)(correction-whole*65536);
        s->seed_frame=frame; s->seed_cfo=estimate->cfo_hz;
    }
    s->pending=0; s->jobs++;
    return rc;
}
