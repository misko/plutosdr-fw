/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_TRACKING_RESOLVER_H
#define GLRT_TRACKING_RESOLVER_H
#include <stddef.h>
#include <stdint.h>

#define GLRT_RESOLVER_SAMPLES 3300U
#define GLRT_RESOLVER_FFT 16384U
#define GLRT_RESOLVER_FRAMES 4U
#define GLRT_RESOLVER_SHIFTS 17U

/* Caller owns this 384-KiB workspace and the FFT plan. One resolver at a time.
 * FFT must perform an unnormalized forward complex transform in place. */
struct glrt_resolver_workspace {
    double bins[GLRT_RESOLVER_FFT][2];
    double power[GLRT_RESOLVER_FFT];
};
typedef int (*glrt_resolver_fft)(void *context, double (*bins)[2], size_t count);
struct glrt_resolver_peak {
    int32_t shift;
    double cfo_hz, power_coherence;
};
struct glrt_resolver_result {
    struct glrt_resolver_peak best;
    struct glrt_resolver_peak hypotheses[GLRT_RESOLVER_SHIFTS];
};

/* Software bootstrap evidence on the 2.5-MS/s coarse lane at every native rate.
 * Input is interleaved CI16; starts are four local sample offsets, each with
 * eight samples of timing guard. The caller attests reference identity,
 * continuity and availability at the coarse-result arrival time. No future IQ
 * may enter these observations. No detection/quality/expiry gate is implied.
 * Returns 0 on numerical success, -1 on invalid input or FFT failure; clears
 * result on failure. Input/reference buffers and workspace must not overlap. */
int glrt_tracking_resolve_2500000(
    struct glrt_resolver_workspace *workspace,
    const int16_t *reference, size_t reference_samples,
    const int16_t *observations, size_t observation_samples,
    const size_t *starts, size_t frames,
    glrt_resolver_fft fft, void *fft_context, struct glrt_resolver_result *result);
#endif
