/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_TRACKING_TRANSPORT_H
#define GLRT_TRACKING_TRANSPORT_H
#include "glrt_tracking_schedule.h"

#define GLRT_TRACKING_MAGIC UINT32_C(0x474c5431)
#define GLRT_TRACKING_VERSION UINT32_C(0x10000)

/* GLT1 v1.0; see GLRT_TRACKING_TRANSPORT.md. These ports perform no I/O.
 * Deployment must attest the full reference SHA256 before accepting a source
 * epoch. The on-wire 32-bit bank discriminator is not a hash attestation. */
int glrt_tracking_batch_encode(const struct glrt_tracking_batch *, char *, size_t);
/* Explicit size excludes any C terminator. Parse failure publishes nothing. */
int glrt_tracking_head_parse(const char *, size_t, uint32_t *epoch, uint32_t words[32]);
int glrt_tracking_snapshot_parse(const char *, size_t, uint32_t words[24]);
int glrt_tracking_snapshot_drained(const uint32_t words[24]);
/* Retain the original head before association/acknowledgement. Associated
 * partial/faulted heads return 0 with rejection bits for explicit draining.
 * Invalid association/encoding returns -1 and invalidates any stale estimate. */
int glrt_tracking_associated_solve(const struct glrt_tracking_batch *,
    uint32_t epoch, uint32_t sequence, const uint32_t words[32],
    struct glrt_native_estimate *);
#endif
