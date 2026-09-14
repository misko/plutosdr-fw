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

/* Before the eight-point timing/carrier trend is eligible, account for a
 * measured carrier ramp without inventing support. Use only earlier accepted
 * startup measurements; a rejection keeps the old hold-last behavior. The
 * next measurement still passes the same coherence/local-correction gates. */
static double startup_carrier(const struct glrt_tracking_bootstrap *s,uint32_t target)
{
    const struct glrt_native_trend *h=&s->trend.history;
    double mx=0,mf=0,xx=0,xf=0,predicted;
    unsigned n;
    if(s->jobs<3 || s->jobs>=8 || h->count!=s->jobs || !h->valid ||
       target<=h->last_supported || target-h->last_supported>s->spacing)
        return s->seed_cfo;
    for(n=0;n<h->count;n++) {
        mx-=(double)(h->last_supported-h->observations[n].frame);
        mf+=h->observations[n].cfo_hz;
    }
    mx/=h->count;mf/=h->count;
    for(n=0;n<h->count;n++) {
        double x=-(double)(h->last_supported-h->observations[n].frame)-mx;
        xx+=x*x;xf+=x*(h->observations[n].cfo_hz-mf);
    }
    if(!(xx>0)) return s->seed_cfo;
    predicted=mf+xf/xx*((double)(target-h->last_supported)-mx);
    if(!isfinite(predicted) || fabs(predicted)+250>=RATE/2.0 ||
       fabs(predicted-s->seed_cfo)>250) return s->seed_cfo;
    return predicted;
}

int glrt_tracking_bootstrap_init(struct glrt_tracking_bootstrap *s, uint32_t epoch,
    uint64_t start, uint32_t fraction, double cfo)
{
    if (!s) return -1;
    memset(s,0,sizeof(*s));
    if (!epoch || fraction>=65536 || !isfinite(cfo) || fabs(cfo)+250>=RATE/2.0 ||
        start>UINT64_MAX-SAMPLES || glrt_tracking_trend_reset(&s->trend,epoch,RATE))
        return fail(s,GLRT_BOOTSTRAP_INVALID);
    s->seed_start=start; s->seed_fraction=fraction; s->seed_cfo=cfo;
    s->spacing=GLRT_BOOTSTRAP_SPACING; s->valid=1;
    return 0;
}

int glrt_tracking_bootstrap_set_spacing(struct glrt_tracking_bootstrap *s,uint32_t spacing)
{
    if(!s || !s->valid || s->jobs || s->pending || s->ready ||
       (spacing!=3 && spacing!=GLRT_BOOTSTRAP_SPACING)) return -1;
    s->spacing=spacing;
    return 0;
}

static int next(struct glrt_tracking_bootstrap *s, uint64_t earliest,
    uint64_t available, uint64_t source_now, int live, uint32_t lead, uint32_t *frame,
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
        !lead || source_now>UINT64_MAX-lead || available>source_now || earliest>available)
        return fail(s,GLRT_BOOTSTRAP_INVALID);
    if (s->clock_seen && available<s->last_available)
        return fail(s,GLRT_BOOTSTRAP_SOURCE_LOSS);
    s->last_available=available; s->clock_seen=1;
    if (s->jobs>=GLRT_BOOTSTRAP_LIMIT) return fail(s,GLRT_BOOTSTRAP_BUDGET);
    if(s->spacing!=3 && s->spacing!=GLRT_BOOTSTRAP_SPACING)
        return fail(s,GLRT_BOOTSTRAP_INVALID);
    target=s->jobs*s->spacing;
    if (s->jobs<8) {
        /* Advance by the explicitly selected 750-Hz frame cadence. */
        uint64_t advance=(uint64_t)(target-s->seed_frame)*RATE/750;
        if (s->seed_start>UINT64_MAX-advance) return fail(s,GLRT_BOOTSTRAP_INVALID);
        batch=(struct glrt_tracking_batch){.rate=RATE,.prediction={
            .epoch=s->trend.history.epoch,.tag=1,.start=s->seed_start+advance,
            .fraction=s->seed_fraction,.period=UINT64_C(218453333),
            .step=phase(startup_carrier(s,target)),.expires=UINT64_MAX,.repeats=1}};
    } else if (glrt_tracking_trend_batch(&s->trend,target,1,1,0,&batch,&slope))
        return fail(s,GLRT_BOOTSTRAP_HISTORY);
    if (glrt_tracking_prediction(&batch,0,&job) || job.start>UINT64_MAX-SAMPLES)
        return fail(s,GLRT_BOOTSTRAP_INVALID);
    if (job.start<earliest) return fail(s,GLRT_BOOTSTRAP_SOURCE_LOSS);
    if (job.start+SAMPLES<=available) {
        s->pending=1; s->pending_job=job; *frame=target; *out=job;
        return GLRT_BOOTSTRAP_PAST;
    }
    if (s->jobs<8) return live ? GLRT_BOOTSTRAP_WAIT : fail(s,GLRT_BOOTSTRAP_HISTORY);
    first=target-s->spacing+1;
    /* The trend still enforces the same last-supported +32 horizon. A live
     * DMA block can lag the receiver beyond the legacy eighteen-position
     * search, so consider every eight-repeat batch inside that horizon. */
    last=live ? s->trend.history.last_supported+32-7 : target+s->spacing;
    for (; first<=last; first++) {
        if (glrt_tracking_trend_batch(&s->trend,first,8,1,0,&batch,&slope) ||
            glrt_tracking_prediction(&batch,0,&job)) continue;
        if (job.start>=source_now+lead) {
            s->ready=1; *frame=first; *out=job; *handoff=batch;
            return GLRT_BOOTSTRAP_READY;
        }
    }
    return live ? GLRT_BOOTSTRAP_WAIT : fail(s,GLRT_BOOTSTRAP_FUTURE);
}

int glrt_tracking_bootstrap_next(struct glrt_tracking_bootstrap *s, uint64_t earliest,
    uint64_t available, uint32_t lead, uint32_t *frame,
    struct glrt_tracking_job *out, struct glrt_tracking_batch *handoff)
{
    return next(s,earliest,available,available,0,lead,frame,out,handoff);
}

int glrt_tracking_bootstrap_live_init(struct glrt_tracking_bootstrap_live *s,
    uint32_t epoch, uint64_t start, uint32_t fraction, double cfo, uint64_t deadline)
{
    if (!s) return GLRT_BOOTSTRAP_ERROR;
    memset(s,0,sizeof(*s));
    if (glrt_tracking_bootstrap_init(&s->core,epoch,start,fraction,cfo))
        return GLRT_BOOTSTRAP_ERROR;
    if (deadline<=start) return fail(&s->core,GLRT_BOOTSTRAP_INVALID);
    s->source_deadline=deadline;
    return 0;
}

int glrt_tracking_bootstrap_live_next(struct glrt_tracking_bootstrap_live *s,
    uint64_t earliest, uint64_t retained_end, uint64_t source_now, uint32_t lead,
    uint32_t *frame, struct glrt_tracking_job *out, struct glrt_tracking_batch *handoff)
{
    if (frame) *frame=0;
    if (out) memset(out,0,sizeof(*out));
    if (handoff) memset(handoff,0,sizeof(*handoff));
    if (!s) return GLRT_BOOTSTRAP_ERROR;
    if (s->seen && (source_now<s->last_source || earliest<s->last_earliest))
        return fail(&s->core,GLRT_BOOTSTRAP_SOURCE_LOSS);
    if (source_now>s->source_deadline) return fail(&s->core,GLRT_BOOTSTRAP_BUDGET);
    s->last_source=source_now; s->last_earliest=earliest; s->seen=1;
    return next(&s->core,earliest,retained_end,source_now,1,lead,frame,out,handoff);
}

int glrt_tracking_bootstrap_observe(struct glrt_tracking_bootstrap *s, uint32_t epoch,
    uint32_t frame, const struct glrt_tracking_job *job, const struct glrt_native_estimate *estimate)
{
    int rc;
    if (!s || !s->valid || !s->pending || !job || !estimate || epoch!=s->trend.history.epoch ||
        frame!=s->jobs*s->spacing || job->start!=s->pending_job.start ||
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
