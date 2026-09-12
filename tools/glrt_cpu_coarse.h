/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_CPU_COARSE_H
#define GLRT_CPU_COARSE_H
#include <stdint.h>

#define GLRT_CPU_COARSE_SAMPLES 14000U
#define GLRT_CPU_COARSE_EPOCHS 3333U
struct glrt_cpu_coarse_peak { uint32_t epoch, frequency, score; };
struct glrt_cpu_coarse_workspace {
    uint32_t grid[11][GLRT_CPU_COARSE_EPOCHS];
    struct glrt_cpu_coarse_peak peaks[8];
    uint32_t completed_epochs, count;
};
/* Software proposals only. Caller owns exactly 14000 contiguous CI16 samples
 * and the reviewed Q9 coefficient bank [symbol][frequency][tap][I/Q]. No
 * output here is an acquisition decision or a fabricated GLA1 event. Resolve
 * and verify repeated full pilots before using a proposal for catch-up.
 * Poll runs before each block of <=16 epochs and before publishing peaks;
 * it must reject cancellation, source loss or the caller's wall deadline.
 * A nonzero poll or malformed coefficient returns -1 with count=0. The
 * workspace is caller-owned (roughly 144 KiB), never the capture-thread stack.
 */
int glrt_cpu_coarse_search(struct glrt_cpu_coarse_workspace *, const int16_t *iq,
    const int16_t coefficients[12][11][11][2], int (*poll)(void *), void *context);
#endif
