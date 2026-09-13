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
/* Internal disjoint grid partitions. These publish no peaks. Caller owns the
 * complete input lifetime, uses separate completion counters, and joins every
 * writer before selecting peaks. Poll must be safe for concurrent calls.
 * select requires all 3333 epochs computed successfully. */
int glrt_cpu_coarse_grid(uint32_t grid[11][GLRT_CPU_COARSE_EPOCHS], const int16_t *,
    const int16_t [12][11][11][2], unsigned begin, unsigned end,
    uint32_t *completed, int (*poll)(void *), void *context);
int glrt_cpu_coarse_select(struct glrt_cpu_coarse_workspace *, int (*poll)(void *), void *context);
/* Internal opt-in proposal budget, 1..64. Does not change the legacy eight
 * outputs or workspace layout. Caller supplies budget entries and count.
 * Poll before each selection and publication; failure publishes count=0 and
 * clears a valid-sized output. No candidate confers acquisition authority. */
int glrt_cpu_coarse_select_bounded(const struct glrt_cpu_coarse_workspace *,
    struct glrt_cpu_coarse_peak *, unsigned budget, uint32_t *count,
    int (*poll)(void *), void *context);
#endif
