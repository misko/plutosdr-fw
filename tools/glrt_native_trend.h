/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_NATIVE_TREND_H
#define GLRT_NATIVE_TREND_H
#include "glrt_native_schedule.h"

#define GLRT_NATIVE_TREND_WINDOW 96U
struct glrt_native_observation {
    uint32_t frame;
    double offset_samples, cfo_hz;
};
struct glrt_native_trend {
    uint32_t epoch, first_frame, last_seen, last_supported, count, next;
    uint64_t anchor;
    int initialized, valid, seen;
    struct glrt_native_observation observations[GLRT_NATIVE_TREND_WINDOW];
};

void glrt_native_trend_reset(struct glrt_native_trend *trend, uint32_t epoch);
/* The caller supplies the absolute frame ordinal from retained descriptor
 * history AFTER successful GLS1 association. A rejected local fit advances
 * last_seen but not the fitted data. Source faults fence the entire trend.
 * Returns 1 for accepted data, 0 for a rejected local fit, -1 for a fence or
 * malformed/out-of-order observation. Reset and fresh acquisition are required
 * after a fence. This component neither acquires nor declares an RF pilot. */
int glrt_native_trend_observe(struct glrt_native_trend *trend, uint32_t epoch,
    uint32_t frame, uint64_t start, const struct glrt_native_estimate *estimate);
/* Fit only past supported observations within 96 frame positions (~128 ms).
 * Require >=8 supported points. Predict strictly after last_seen and at most
 * 32 frames beyond last_supported, including the last repeat of this batch.
 * Output is a finite GLS1 descriptor; no SUBMIT or ownership side effect.
 * CFO rate is relative received-carrier rate, not satellite-only Doppler. */
int glrt_native_trend_batch(const struct glrt_native_trend *trend,
    uint32_t first_frame, uint32_t repeats, uint32_t tag, uint32_t seed,
    struct glrt_native_batch *batch, double *cfo_rate_hz_s);
#endif
