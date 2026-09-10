/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_native_trend.h"
#include <math.h>
#include <string.h>

#define RATE 60000000.0
#define PERIOD UINT64_C(80000)
#define MAX_FRAMES 1350000U

void glrt_native_trend_reset(struct glrt_native_trend *t, uint32_t epoch)
{
    memset(t,0,sizeof(*t));
    t->epoch = epoch;
    t->valid = epoch != 0;
}

int glrt_native_trend_observe(struct glrt_native_trend *t, uint32_t epoch,
    uint32_t frame, uint64_t start, const struct glrt_native_estimate *e)
{
    uint64_t advance, nominal;
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
        fabs(e->cfo_hz)+250 >= RATE/2 || e->coherence < .05 || e->coherence > 1 ||
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
    nominal = (uint64_t)(frame-t->first_frame)*PERIOD;
    /* Broad coordinate sanity bound, not a precision/innovation gate. Allows
     * >900 ppm cumulative timing drift across the bounded 30-minute epoch.
     * Subtract integers first; large absolute source indexes keep low bits. */
    if ((advance >= nominal ? advance-nominal : nominal-advance) > 100000000) {
        t->valid = 0;
        return -1;
    }
    offset = advance >= nominal ? (double)(advance-nominal) : -(double)(nominal-advance);
    offset += e->delay_correction_s*RATE;
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

static uint64_t phase(double hz)
{
    double value = fmod(round_even(hz/RATE*0x1p48),0x1p48);
    if (value < 0) value += 0x1p48;
    return (uint64_t)value;
}

int glrt_native_trend_batch(const struct glrt_native_trend *t,
    uint32_t first, uint32_t repeats, uint32_t tag, uint32_t seed,
    struct glrt_native_batch *out, double *cfo_rate)
{
    struct glrt_native_batch b;
    double mx=0, my=0, mf=0, xx=0, xy=0, xf=0, dy, df, target, offset, frequency, period;
    uint64_t nominal, start, last;
    uint32_t unused;
    unsigned i, n=0;
    int64_t whole;
    double fraction;
    if (!t || !out || !cfo_rate || !t->valid || !t->initialized || !tag ||
        !repeats || repeats > 32 || first <= t->last_seen || first < t->last_supported ||
        first-t->last_supported > 32 || repeats-1 > 32-(first-t->last_supported) ||
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
    period = round_even((PERIOD+dy)*65536);
    if (!isfinite(offset) || fabs(offset) > 100000000 || !isfinite(frequency) ||
        fabs(frequency)+250 >= RATE/2 || fabs(frequency+df*(repeats-1))+250 >= RATE/2 ||
        !isfinite(period) || period < 79328.0*65536 || period > 81000.0*65536) return -1;
    nominal = (uint64_t)(first-t->first_frame)*PERIOD;
    if (t->anchor > UINT64_MAX-nominal) return -1;
    start = t->anchor+nominal;
    /* Round only the local correction to Q16; keep the large anchor integer. */
    offset = round_even(offset*65536)/65536;
    whole = (int64_t)floor(offset);
    fraction = (offset-whole)*65536;
    if ((whole < 0 && start < (uint64_t)-whole) ||
        (whole >= 0 && start > UINT64_MAX-(uint64_t)whole)) return -1;
    start = whole < 0 ? start-(uint64_t)-whole : start+(uint64_t)whole;
    b = (struct glrt_native_batch){.epoch=t->epoch,.tag=tag,.start=start,
        .period=(uint64_t)period,.step=phase(frequency),.delta=phase(df),
        .expires=UINT64_MAX,.fraction=(uint32_t)fraction,.seed=seed,.repeats=repeats};
    if (glrt_native_prediction(&b,repeats-1,&last,&unused)) return -1;
    b.expires = last+79200-1;
    *out = b;
    /* Report the fitted physical-time slope, before schedule quantization. */
    *cfo_rate = df*RATE/(PERIOD+dy);
    return 0;
}
