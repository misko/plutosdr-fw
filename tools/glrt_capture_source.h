/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_CAPTURE_SOURCE_H
#define GLRT_CAPTURE_SOURCE_H
#include <stddef.h>
#include <stdint.h>

/* Direct 2.5-MS/s GLA1 capture contract. This is not a higher-rate index map. */
struct glrt_capture_snapshot {
    uint32_t generation, recovery_failed, readback_rate;
    int32_t dma_error;
    uint64_t cpu[5];
    uint32_t cpu_fault, words[64];
};
struct glrt_capture_source {
    struct glrt_capture_snapshot baseline;
    uint64_t first, received, limit, last_source, admitted, delivered, cpu_read, cpu_pushed;
    uint32_t visit, generation, bound, valid;
};
/* Text length excludes a C terminator; embedded NULs and extra fields fail.
 * Failed decoding leaves output unchanged. Source-health checks are separate. */
int glrt_capture_snapshot_parse(const char *, size_t, struct glrt_capture_snapshot *);
int glrt_capture_source_begin(struct glrt_capture_source *, uint32_t visit,
    uint64_t samples, const struct glrt_capture_snapshot *baseline);
/* Bind one contiguous delivered CI16 block to the attested original source.
 * Samples must already have been refilled before taking this snapshot. The
 * exclusive source_now is latest_ingress_index+1, not the retained-IQ end.
 * Any failed take fences the cursor; outputs clear and no count is advanced. */
int glrt_capture_source_take(struct glrt_capture_source *, const struct glrt_capture_snapshot *,
    size_t samples, uint64_t *first, uint64_t *source_now);
#endif
