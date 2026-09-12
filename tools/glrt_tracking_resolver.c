/* SPDX-License-Identifier: GPL-2.0 */
#include "glrt_tracking_resolver.h"
#include <math.h>
#include <string.h>

int glrt_tracking_resolve_2500000(
    struct glrt_resolver_workspace *w,
    const int16_t *reference, size_t reference_samples,
    const int16_t *observations, size_t observation_samples,
    const size_t *starts, size_t frames,
    glrt_resolver_fft fft, void *context, struct glrt_resolver_result *result)
{
    struct glrt_resolver_result pending = {0};
    double reference_energy = 0;
    size_t frame, n, hypothesis;
    if (!result) return -1;
    memset(result, 0, sizeof(*result));
    if (!w || !reference || !observations || !starts || !fft ||
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
    for (hypothesis = 0; hypothesis < GLRT_RESOLVER_SHIFTS; hypothesis++) {
        size_t peak = 0;
        double left, center, right, curvature, fraction, signed_peak;
        struct glrt_resolver_peak *candidate = &pending.hypotheses[hypothesis];
        candidate->shift = (int32_t)hypothesis-8;
        memset(w->power, 0, sizeof(w->power));
        for (frame = 0; frame < frames; frame++) {
            size_t start = starts[frame]-8U+hypothesis;
            double observed_energy = 0, denominator;
            memset(w->bins, 0, sizeof(w->bins));
            for (n = 0; n < reference_samples; n++) {
                double i = observations[2*(start+n)], q = observations[2*(start+n)+1];
                double ri = reference[2*n], rq = reference[2*n+1];
                w->bins[n][0] = i*ri+q*rq;
                w->bins[n][1] = q*ri-i*rq;
                observed_energy += i*i+q*q;
            }
            denominator = fmax(observed_energy*reference_energy, 1.0);
            if (fft(context, w->bins, GLRT_RESOLVER_FFT)) return -1;
            for (n = 0; n < GLRT_RESOLVER_FFT; n++) {
                double power = (w->bins[n][0]*w->bins[n][0]+w->bins[n][1]*w->bins[n][1])/denominator;
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
        candidate->cfo_hz = (signed_peak+fraction)*2500000.0/GLRT_RESOLVER_FFT;
        candidate->power_coherence = center;
        if (center > pending.best.power_coherence) pending.best = *candidate;
    }
    *result = pending;
    return 0;
}
