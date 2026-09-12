/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_TRACKING_SEED_H
#define GLRT_TRACKING_SEED_H
#include "glrt_tracking_bootstrap.h"
#include "glrt_tracking_iq_owner.h"
#include "glrt_tracking_resolver.h"

#define GLRT_SEED_WINDOW_SAMPLES 13316U
enum { GLRT_SEED_INVALID=-1, GLRT_SEED_UNAVAILABLE=-2, GLRT_SEED_IGNORE=0, GLRT_SEED_READY=1 };
struct glrt_tracking_seed_window {
    uint32_t event[16], maximum_age, first_repeat, seed_fraction;
    uint64_t first, seed_start;
    size_t starts[4];
    struct glrt_tracking_iq_view selected, copied;
};
/* Internal direct 2.5-MS/s upper-edge profile. Caller attests the GLA1 stream,
 * radio/reference identities and event sequence before offering CPU-endian
 * words. Transport-valid final accepted decisions alone may seed resolution.
 * This preserves the existing upper-template origin convention (epoch+22),
 * rational 750-Hz period and first four pilots of 64 recent complete repeats.
 * It does not generalize that convention to a new rate or filter bank.
 *
 * maximum_age is measured from acquisition-window origin at selection time,
 * bounded to one second. Planning uses retained end, not the newer receiver
 * counter, for IQ availability. All outputs clear on IGNORE/error.
 */
int glrt_tracking_seed_plan(const uint32_t event[16], const struct glrt_tracking_iq_view *,
    uint32_t maximum_age, struct glrt_tracking_seed_window *);
/* Copy complete resolver IQ out of the protected owner. Selection and copy
 * snapshots are both retained; no numerical work runs under the mutex.
 * Caller-owned output has capacity in complex CI16 samples. On failure IQ
 * may already have been copied, but the cleared plan cannot authorize its use.
 */
int glrt_tracking_seed_copy(struct glrt_tracking_iq_owner *, const uint32_t event[16],
    uint32_t maximum_age, int16_t *iq, size_t capacity, struct glrt_tracking_seed_window *);
/* The input must be the owned copy associated with window; reference is the
 * pinned 3300-pair phase-zero pilot. Full FFT resolution and bootstrap init
 * run outside the capture lock. Numerical success is not tracking support:
 * only subsequent accepted past-pilot history can produce a future handoff.
 * source_deadline and caller wall-time/cancellation limits remain mandatory.
 */
int glrt_tracking_seed_resolve(const struct glrt_tracking_seed_window *,
    struct glrt_resolver_workspace *, const int16_t *reference, const int16_t *iq,
    glrt_resolver_fft, void *fft_context, uint64_t source_deadline,
    struct glrt_resolver_result *, struct glrt_tracking_bootstrap_live *);
#endif
