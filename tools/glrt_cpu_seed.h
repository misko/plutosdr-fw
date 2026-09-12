/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_CPU_SEED_H
#define GLRT_CPU_SEED_H
#include "glrt_cpu_coarse.h"
#include "glrt_tracking_iq_owner.h"
#include "glrt_tracking_resolver.h"
#include "glrt_tracking_bootstrap.h"

#define GLRT_CPU_SEED_SAMPLES 13316U
struct glrt_cpu_candidate {
    uint64_t window_start;
    uint32_t epoch;
    struct glrt_cpu_coarse_peak peak;
};
struct glrt_cpu_seed {
    struct glrt_cpu_candidate candidate;
    uint32_t maximum_age, first_repeat, fraction;
    uint64_t first, start;
    size_t starts[4];
    struct glrt_tracking_iq_view selected, copied;
};
/* Internal SOFTWARE proposal port: no GLA1 event or accepted decision is
 * fabricated. The caller retains the complete 14000-sample coarse input and
 * scored candidate, and binds epoch to the live IQ owner's source epoch.
 * All coordinates are 2.5-MS/s signal centers. The upper-pilot origin is
 * window_start + epoch_bin + 22. Native conversion occurs after catch-up.
 *
 * Select the first four of the latest 64 complete 750-Hz repeats. Maximum
 * proposal age remains <= one second. Error clears the plan; copied IQ alone
 * never authorizes a handoff. 0 success, -1 invalid, -2 unavailable/stale. */
int glrt_cpu_seed_plan(const struct glrt_cpu_candidate *, const struct glrt_tracking_iq_view *,
    uint32_t maximum_age, struct glrt_cpu_seed *);
int glrt_cpu_seed_copy(struct glrt_tracking_iq_owner *, const struct glrt_cpu_candidate *,
    uint32_t maximum_age, int16_t *, size_t capacity, struct glrt_cpu_seed *);
/* Full resolution initializes an empty software bootstrap. Only supported
 * subsequent past-pilot observations may authorize a future proposal.
 * Caller guards every FFT with its wall/source deadline and cancellation. */
int glrt_cpu_seed_resolve(const struct glrt_cpu_seed *, struct glrt_resolver_workspace *,
    const int16_t *reference, const int16_t *iq, glrt_resolver_fft, void *,
    uint64_t source_deadline, struct glrt_resolver_result *, struct glrt_tracking_bootstrap_live *);
#endif
