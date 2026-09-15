/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_native_trend.h"
#include "glrt_tracking_trend.h"
#include <math.h>
#include <string.h>

#define MAX_FRAMES 1350000U

void glrt_native_trend_reset(struct glrt_native_trend *t, uint32_t epoch)
{
    memset(t,0,sizeof(*t));
    t->epoch = epoch;
    t->valid = epoch != 0;
}

static int observe(struct glrt_native_trend *t, uint32_t epoch,
    uint32_t frame, uint64_t start, const struct glrt_native_estimate *e,
    uint32_t rate, double reference_samples)
{
    uint64_t advance, nominal, numerator;
    double offset;
    if (!t) return -1;
    if (!t->valid || !e || epoch != t->epoch || (t->seen && frame <= t->last_seen) ||
        (e->rejection & ~0x7fU) ||
        (e->rejection & (GLRT_NATIVE_FAULT | GLRT_NATIVE_INCOMPLETE)) ||
        !isfinite(e->delay_correction_s) || !isfinite(e->cfo_hz) || !isfinite(e->residual_cfo_hz) ||
        !isfinite(e->coherence) || !isfinite(e->linearized_coherence)) {
        t->valid = 0;
        return -1;
    }
    t->last_seen = frame;
    t->seen = 1;
    if (e->rejection) return 0;
    if (fabs(e->delay_correction_s) > 250e-9 || fabs(e->residual_cfo_hz) > 250 ||
        fabs(e->cfo_hz)+250 >= rate/2.0 || e->coherence < .05 || e->coherence > 1 ||
        e->linearized_coherence < 0 || e->linearized_coherence > 1) {
        t->valid = 0;
        return -1;
    }
    if (!t->initialized) {
        t->anchor = start;
        t->first_frame = t->last_seen = frame;
        t->initialized = 1;
    }
    if (start < t->anchor || frame-t->first_frame > MAX_FRAMES) {
        t->valid = 0;
        return -1;
    }
    advance = start-t->anchor;
    numerator = (uint64_t)(frame-t->first_frame)*rate;
    nominal = numerator/750;
    /* Broad coordinate sanity bound, not a precision/innovation gate. Allows
     * >900 ppm cumulative timing drift across the bounded 30-minute epoch.
     * Subtract integers first; large absolute source indexes keep low bits. */
    if ((advance >= nominal ? advance-nominal : nominal-advance) > (uint64_t)rate*5/3) {
        t->valid = 0;
        return -1;
    }
    offset = advance >= nominal ? (double)(advance-nominal) : -(double)(nominal-advance);
    offset += reference_samples+e->delay_correction_s*rate-(double)(numerator%750)/750;
    t->observations[t->next] = (struct glrt_native_observation){frame,offset,e->cfo_hz};
    t->next = (t->next+1)%GLRT_NATIVE_TREND_WINDOW;
    if (t->count < GLRT_NATIVE_TREND_WINDOW) t->count++;
    t->last_supported = frame;
    return 1;
}

static double round_even(double value)
{
    double lo = floor(value), fraction = value-lo;
    return lo+(fraction > .5 || (fraction == .5 && fmod(lo,2) != 0));
}

static uint64_t phase(double hz, uint32_t rate)
{
    double value = fmod(round_even(hz/rate*0x1p48),0x1p48);
    if (value < 0) value += 0x1p48;
    return (uint64_t)value;
}

static int batch(const struct glrt_native_trend *t,
    uint32_t first, uint32_t repeats, uint32_t tag, uint32_t seed,
    struct glrt_native_batch *out, double *cfo_rate, uint32_t rate, int tracking,
    uint32_t forecast_horizon)
{
    struct glrt_native_batch b;
    double mx=0, my=0, mf=0, xx=0, xy=0, xf=0, dy, df, target, offset, frequency, period;
    uint64_t nominal, numerator, start, last;
    uint32_t stride=60000000/rate, minimum=(64+stride-1)/stride, samples=rate*33/25000;
    double nominal_period=(double)rate/750;
    uint32_t unused;
    unsigned i, n=0;
    int64_t whole;
    double fraction;
    if (!t || !out || !cfo_rate || !t->valid || !t->initialized || !tag ||
        !repeats || repeats > 32 ||
        (forecast_horizon!=GLRT_TRACKING_FORECAST_DEFAULT &&
         forecast_horizon!=GLRT_TRACKING_FORECAST_COAST) ||
        first <= t->last_seen || first < t->last_supported ||
        first-t->last_supported > forecast_horizon ||
        repeats-1 > forecast_horizon-(first-t->last_supported) ||
        first-t->first_frame > MAX_FRAMES ||
        repeats-1 > MAX_FRAMES-(first-t->first_frame)) return -1;
    for (i=0; i<t->count; i++) {
        const struct glrt_native_observation *o = t->observations+i;
        if (t->last_supported-o->frame >= GLRT_NATIVE_TREND_WINDOW) continue;
        mx -= t->last_supported-o->frame;
        my += o->offset_samples;
        mf += o->cfo_hz;
        n++;
    }
    if (n < 8) return -1;
    mx /= n; my /= n; mf /= n;
    for (i=0; i<t->count; i++) {
        const struct glrt_native_observation *o = t->observations+i;
        double x;
        if (t->last_supported-o->frame >= GLRT_NATIVE_TREND_WINDOW) continue;
        x = -(double)(t->last_supported-o->frame)-mx;
        xx += x*x; xy += x*(o->offset_samples-my); xf += x*(o->cfo_hz-mf);
    }
    if (!(xx > 0)) return -1;
    dy = xy/xx; df = xf/xx;
    target = (double)(first-t->last_supported)-mx;
    offset = my+dy*target;
    frequency = mf+df*target;
    period = round_even((nominal_period+dy)*65536);
    if (!isfinite(offset) || fabs(offset) > (double)rate*5/3 || !isfinite(frequency) ||
        fabs(frequency)+250 >= rate/2.0 || fabs(frequency+df*(repeats-1))+250 >= rate/2.0 ||
        !isfinite(period) || period < (samples+2.0*minimum)*65536 ||
        period > 81000.0*65536*rate/60000000) return -1;
    numerator = (uint64_t)(first-t->first_frame)*rate;
    nominal = numerator/750;
    if (t->anchor > UINT64_MAX-nominal) return -1;
    start = t->anchor+nominal;
    /* Round only the local correction to Q16; keep the large anchor integer. */
    offset = round_even((offset+(double)(numerator%750)/750)*65536)/65536;
    whole = (int64_t)floor(offset);
    fraction = (offset-whole)*65536;
    if ((whole < 0 && start < (uint64_t)-whole) ||
        (whole >= 0 && start > UINT64_MAX-(uint64_t)whole)) return -1;
    start = whole < 0 ? start-(uint64_t)-whole : start+(uint64_t)whole;
    b = (struct glrt_native_batch){.epoch=t->epoch,.tag=tag,.start=start,
        .period=(uint64_t)period,.step=phase(frequency,rate),.delta=phase(df,rate),
        .expires=UINT64_MAX,.fraction=(uint32_t)fraction,.seed=seed,.repeats=repeats};
    if (tracking) {
        struct glrt_tracking_batch tb={.prediction=b,.rate=rate};
        struct glrt_tracking_job job;
        if (glrt_tracking_prediction(&tb,repeats-1,&job)) return -1;
        last=job.start;
    } else if (glrt_native_prediction(&b,repeats-1,&last,&unused)) return -1;
    b.expires = last+samples-1;
    *out = b;
    /* Report the fitted physical-time slope, before schedule quantization. */
    *cfo_rate = df*rate/(nominal_period+dy);
    return 0;
}

int glrt_native_trend_observe(struct glrt_native_trend *t, uint32_t epoch,
    uint32_t frame, uint64_t start, const struct glrt_native_estimate *e)
{
    return observe(t,epoch,frame,start,e,60000000,0);
}

int glrt_native_trend_batch(const struct glrt_native_trend *t,
    uint32_t first, uint32_t repeats, uint32_t tag, uint32_t seed,
    struct glrt_native_batch *out, double *cfo_rate)
{
    return batch(t,first,repeats,tag,seed,out,cfo_rate,60000000,0,
                 GLRT_TRACKING_FORECAST_DEFAULT);
}

int glrt_tracking_trend_reset(struct glrt_tracking_trend *t, uint32_t epoch, uint32_t rate)
{
    if (!t) return -1;
    memset(t,0,sizeof(*t));
    if (!epoch || !glrt_tracking_profile_get(rate,0)) return -1;
    glrt_native_trend_reset(&t->history,epoch);
    t->rate=rate;
    return 0;
}

int glrt_tracking_trend_observe(struct glrt_tracking_trend *t, uint32_t epoch,
    uint32_t frame, uint64_t start, uint32_t reference_phase, const struct glrt_native_estimate *e)
{
    const struct glrt_tracking_profile *p;
    if (!t) return -1;
    if (!(p=glrt_tracking_profile_get(t->rate,reference_phase))) {
        t->history.valid=0;
        return -1;
    }
    return observe(&t->history,epoch,frame,start,e,t->rate,
                   (double)p->reference_phase/p->reference_phases);
}

int glrt_tracking_trend_batch(const struct glrt_tracking_trend *t,
    uint32_t first, uint32_t repeats, uint32_t tag, uint32_t seed,
    struct glrt_tracking_batch *out, double *cfo_rate)
{
    struct glrt_tracking_batch b;
    if (!t || !out || !glrt_tracking_profile_get(t->rate,0)) return -1;
    if (batch(&t->history,first,repeats,tag,seed,&b.prediction,cfo_rate,t->rate,1,
              GLRT_TRACKING_FORECAST_DEFAULT)) return -1;
    b.rate=t->rate;
    *out=b;
    return 0;
}

int glrt_tracking_trend_batch_horizon(const struct glrt_tracking_trend *t,
    uint32_t first, uint32_t repeats, uint32_t tag, uint32_t seed,
    uint32_t forecast_horizon, struct glrt_tracking_batch *out, double *cfo_rate)
{
    struct glrt_tracking_batch b;
    if (!t || !out || !glrt_tracking_profile_get(t->rate,0)) return -1;
    if (batch(&t->history,first,repeats,tag,seed,&b.prediction,cfo_rate,t->rate,1,
              forecast_horizon)) return -1;
    b.rate=t->rate;
    *out=b;
    return 0;
}

int glrt_tracking_trend_handoff_valid(const struct glrt_tracking_trend *t,
    uint32_t first, uint32_t frames)
{
    const struct glrt_native_trend *h;
    uint32_t previous=0, recent=0;
    unsigned i, origin;
    if (!t || !glrt_tracking_profile_get(t->rate,0)) return 0;
    h=&t->history;
    if (h->valid!=1 || h->initialized!=1 || h->seen!=1 || !h->epoch ||
        h->count<8 || h->count>GLRT_NATIVE_TREND_WINDOW ||
        h->next>=GLRT_NATIVE_TREND_WINDOW ||
        (h->count<GLRT_NATIVE_TREND_WINDOW && h->next!=h->count) ||
        h->last_seen<h->last_supported || h->last_supported<h->first_frame ||
        first<=h->last_seen || !frames || frames>225000 || first>UINT32_MAX-frames ||
        first-h->first_frame>MAX_FRAMES || frames-1>MAX_FRAMES-(first-h->first_frame)) return 0;
    origin=h->count==GLRT_NATIVE_TREND_WINDOW ? h->next : 0;
    for (i=0;i<h->count;i++) {
        const struct glrt_native_observation *o=h->observations+(origin+i)%GLRT_NATIVE_TREND_WINDOW;
        if (o->frame<h->first_frame || o->frame>h->last_supported ||
            (i && o->frame<=previous) || !isfinite(o->offset_samples) || !isfinite(o->cfo_hz) ||
            fabs(o->offset_samples)>t->rate*(5.0/3+250e-9)+1 ||
            fabs(o->cfo_hz)+250>=t->rate/2.0) return 0;
        previous=o->frame;
        if (h->last_supported-o->frame<GLRT_NATIVE_TREND_WINDOW) recent++;
    }
    return previous==h->last_supported && recent>=8;
}

int glrt_tracking_trend_from_coarse(const struct glrt_tracking_trend *coarse, uint32_t rate,
    uint32_t first, uint32_t frames, struct glrt_tracking_trend *out)
{
    struct glrt_tracking_trend pending;
    uint32_t ratio;
    unsigned i;
    if(!out) return -1;
    if(!coarse) { memset(out,0,sizeof(*out)); return -1; }
    pending=*coarse;
    memset(out,0,sizeof(*out));
    if(pending.rate!=2500000 || (rate!=30000000 && rate!=60000000) ||
       !glrt_tracking_trend_handoff_valid(&pending,first,frames)) return -1;
    ratio=rate/2500000;
    if(pending.history.anchor>UINT64_MAX/ratio) return -1;
    pending.rate=rate;
    pending.history.anchor*=ratio;
    for(i=0;i<pending.history.count;i++) pending.history.observations[i].offset_samples*=ratio;
    if(!glrt_tracking_trend_handoff_valid(&pending,first,frames)) return -1;
    *out=pending;
    return 0;
}
