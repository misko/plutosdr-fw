/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_tracking_resolver.h"
#include <math.h>
#include <string.h>

static int resolve(
    struct glrt_resolver_workspace *w,
    const int16_t *reference, size_t reference_samples,
    const int16_t *observations, size_t observation_samples,
    const size_t *starts, size_t frames,
    int32_t first_shift, int32_t last_shift, glrt_resolver_fft fft, void *context,
    struct glrt_resolver_result *result, struct glrt_resolver_peak *best)
{
    struct glrt_resolver_result pending = {0};
    double reference_energy = 0;
    size_t frame, n;
    int32_t shift;
    if (result) memset(result, 0, sizeof(*result));
    if (best) memset(best, 0, sizeof(*best));
    if (!w || !reference || !observations || !starts || !fft ||
        (!result == !best) || first_shift < -8 || last_shift > 8 || first_shift > last_shift ||
        reference_samples != GLRT_RESOLVER_SAMPLES || frames != GLRT_RESOLVER_FRAMES ||
        observation_samples < GLRT_RESOLVER_SAMPLES+16U || observation_samples > SIZE_MAX/4U)
        return -1;
    for (frame = 0; frame < frames; frame++)
        if (starts[frame] < 8U || starts[frame] > observation_samples-(GLRT_RESOLVER_SAMPLES+8U))
            return -1;
    for (n = 0; n < reference_samples; n++) {
        double i = reference[2*n], q = reference[2*n+1];
        reference_energy += i*i+q*q;
    }
    if (reference_energy == 0) return -1;
    pending.best.power_coherence = -1;
    for (shift = first_shift; shift <= last_shift; shift++) {
        size_t peak = 0;
        double left, center, right, curvature, fraction, signed_peak;
        struct glrt_resolver_peak candidate={.shift=shift};
        memset(w->power, 0, sizeof(w->power));
        for (frame = 0; frame < frames; frame++) {
            size_t start = (size_t)((int64_t)starts[frame]+shift);
            double observed_energy = 0, denominator, reciprocal;
            memset(w->bins, 0, sizeof(w->bins));
            for (n = 0; n < reference_samples; n++) {
                double i = observations[2*(start+n)], q = observations[2*(start+n)+1];
                double ri = reference[2*n], rq = reference[2*n+1];
                w->bins[n][0] = i*ri+q*rq;
                w->bins[n][1] = q*ri-i*rq;
                observed_energy += i*i+q*q;
            }
            denominator = fmax(observed_energy*reference_energy, 1.0);
            reciprocal = 1.0/denominator;
            if (fft(context, w->bins, GLRT_RESOLVER_FFT)) return -1;
            for (n = 0; n < GLRT_RESOLVER_FFT; n++) {
                double power = (w->bins[n][0]*w->bins[n][0]+w->bins[n][1]*w->bins[n][1])*reciprocal;
                if (!isfinite(power)) return -1;
                w->power[n] += power/GLRT_RESOLVER_FRAMES;
            }
        }
        for (n = 1; n < GLRT_RESOLVER_FFT; n++)
            if (w->power[n] > w->power[peak]) peak = n;
        left = w->power[(peak+GLRT_RESOLVER_FFT-1U)%GLRT_RESOLVER_FFT];
        center = w->power[peak];
        right = w->power[(peak+1U)%GLRT_RESOLVER_FFT];
        curvature = left-2*center+right;
        fraction = curvature < 0 ? .5*(left-right)/curvature : 0;
        if (!isfinite(fraction) || fabs(fraction) > .500000001) return -1;
        signed_peak = peak < GLRT_RESOLVER_FFT/2U ? (double)peak : (double)peak-GLRT_RESOLVER_FFT;
        candidate.cfo_hz = (signed_peak+fraction)*2500000.0/GLRT_RESOLVER_FFT;
        candidate.power_coherence = center;
        if (result) pending.hypotheses[shift+8]=candidate;
        if (center > pending.best.power_coherence) pending.best = candidate;
    }
    if (result) *result = pending;
    else *best = pending.best;
    return 0;
}

int glrt_tracking_resolve_2500000(
    struct glrt_resolver_workspace *w,
    const int16_t *reference, size_t reference_samples,
    const int16_t *observations, size_t observation_samples,
    const size_t *starts, size_t frames,
    glrt_resolver_fft fft, void *context, struct glrt_resolver_result *result)
{
    if(!result) return -1;
    memset(result,0,sizeof(*result));
    return resolve(w,reference,reference_samples,observations,observation_samples,
                   starts,frames,-8,8,fft,context,result,NULL);
}

int glrt_tracking_resolve_2500000_local(
    struct glrt_resolver_workspace *w,
    const int16_t *reference, size_t reference_samples,
    const int16_t *observations, size_t observation_samples,
    const size_t *starts, size_t frames, uint32_t timing_radius,
    glrt_resolver_fft fft, void *context, struct glrt_resolver_peak *best)
{
    if(!best) return -1;
    memset(best,0,sizeof(*best));
    if(timing_radius>8) return -1;
    return resolve(w,reference,reference_samples,observations,observation_samples,
                   starts,frames,-(int32_t)timing_radius,(int32_t)timing_radius,
                   fft,context,NULL,best);
}
