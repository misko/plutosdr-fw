/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_TRACKING_IQ_H
#define GLRT_TRACKING_IQ_H
#include <stddef.h>
#include "glrt_native_solver.h"

/* Internal offline/radio-ARM bootstrap arithmetic, not a hardware result.
 * iq contains exactly 3300 interleaved CI16 pairs. reference contains 3300
 * rows of {reference I,Q, derivative I,Q} from the selected pinned 2.5-MS/s
 * Q11 bank. The caller owns source continuity, epoch, rate/phase/bank binding
 * and quality decisions. No sample buffering, acquisition or I/O occurs here.
 * Exact native CORDIC rounding and integer moments; out is unchanged on error.
 */
int glrt_tracking_iq_moments_2500000(const int16_t *iq, const int16_t *reference,
    size_t count, uint64_t start, uint32_t phase_seed, uint32_t phase_step,
    struct glrt_tracking_moments *out);
#endif
