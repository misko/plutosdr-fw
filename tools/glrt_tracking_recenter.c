/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_tracking_recenter.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

#define RATE 2500000U
#define SAMPLES 3300U

static double carrier(const struct glrt_tracking_job *j)
{
    return ((double)j->phase_step-(j->phase_step&0x80000000U ? 0x1p32 : 0))*RATE/0x1p32;
}

static int valid_job(const struct glrt_tracking_job *j)
{
    return j->reference_phase<4 && j->start<=UINT64_MAX-(SAMPLES-1) &&
        fabs(carrier(j))+250<RATE/2.0;
}

static int near(const struct glrt_tracking_job *a, const struct glrt_tracking_job *b, unsigned moves)
{
    uint64_t distance=a->start>=b->start ? a->start-b->start : b->start-a->start;
    int quarters;
    if(distance>2) return 0;
    quarters=(a->start>=b->start ? (int)distance : -(int)distance)*4+
        (int)a->reference_phase-(int)b->reference_phase;
    return abs(quarters)<=3*(int)moves && fabs(carrier(a)-carrier(b))<=250*moves+.002;
}

static double round_even(double value)
{
    double lo=floor(value),fraction=value-lo;
    return lo+(fraction>.5 || (fraction==.5 && fmod(lo,2)!=0));
}

int glrt_tracking_recenter_propose_2500000(unsigned attempts,
    const struct glrt_tracking_job *original, const struct glrt_tracking_job *previous,
    const struct glrt_native_estimate *estimate, struct glrt_tracking_job *out)
{
    struct glrt_tracking_job origin,last,proposal;
    struct glrt_native_estimate e;
    struct glrt_tracking_batch batch;
    double correction,step;
    int64_t whole;
    uint64_t start;
    if(!out) return -1;
    if(!original || !previous || !estimate) { memset(out,0,sizeof(*out)); return -1; }
    origin=*original;last=*previous;e=*estimate;
    memset(out,0,sizeof(*out));
    if(!attempts || attempts>3 || !valid_job(&origin) || !valid_job(&last) ||
        !near(&origin,&last,attempts-1) ||
        (attempts==1 && (origin.start!=last.start || origin.phase_step!=last.phase_step ||
                        origin.reference_phase!=last.reference_phase)) ||
        (e.rejection&~0x7fU) || !isfinite(e.delay_correction_s) ||
        !isfinite(e.residual_cfo_hz) || !isfinite(e.cfo_hz) ||
        !isfinite(e.coherence) || !isfinite(e.linearized_coherence) ||
        e.coherence<0 || e.coherence>1 || e.linearized_coherence<0 || e.linearized_coherence>1)
        return -1;
    if(attempts==3 || e.rejection!=GLRT_NATIVE_LOW_COHERENCE) return 0;
    if(e.coherence>=.05 || fabs(e.delay_correction_s)>=250e-9 ||
        fabs(e.residual_cfo_hz)>=250 || fabs(e.cfo_hz-carrier(&last)-e.residual_cfo_hz)>1e-7)
        return -1;
    if(e.linearized_coherence<=e.coherence || fabs(e.cfo_hz)+250>=RATE/2.0) return 0;
    correction=round_even((last.reference_phase/4.0+e.delay_correction_s*RATE)*65536);
    whole=(int64_t)floor(correction/65536);
    if((whole<0 && last.start<(uint64_t)-whole) ||
        (whole>=0 && last.start>UINT64_MAX-(uint64_t)whole)) return 0;
    start=whole<0 ? last.start-(uint64_t)-whole : last.start+(uint64_t)whole;
    step=fmod(round_even(e.cfo_hz/RATE*0x1p48),0x1p48);
    if(step<0) step+=0x1p48;
    batch=(struct glrt_tracking_batch){.rate=RATE,.prediction={
        .epoch=1,.tag=1,.start=start,.fraction=(uint32_t)(correction-whole*65536),
        .period=UINT64_C(218453333),.step=(uint64_t)step,.expires=UINT64_MAX,.repeats=1}};
    if(glrt_tracking_prediction(&batch,0,&proposal) || !valid_job(&proposal) ||
        !near(&origin,&proposal,attempts)) return 0;
    if(proposal.start==last.start && proposal.reference_phase==last.reference_phase &&
        proposal.phase_step==last.phase_step) return 0;
    *out=proposal;
    return 1;
}
