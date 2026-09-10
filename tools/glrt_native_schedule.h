/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_NATIVE_SCHEDULE_H
#define GLRT_NATIVE_SCHEDULE_H
#include <stddef.h>
#include <stdint.h>
#include "glrt_native_solver.h"

/* Internal radio-controller port for the GLS1 v1.0 draft. Integer native
 * coordinates are never converted to double. No radio or filesystem I/O. */
struct glrt_native_batch {
    uint32_t epoch, tag;
    uint64_t start, period, step, delta, expires;
    uint32_t fraction, seed, repeats;
};

int glrt_native_batch_valid(const struct glrt_native_batch *batch);
int glrt_native_batch_encode(const struct glrt_native_batch *batch, char *text, size_t size);
int glrt_native_prediction(const struct glrt_native_batch *batch, unsigned repeat,
                           uint64_t *start, uint32_t *step);
/* Explicit lengths exclude any C terminator. Embedded NUL/trailing data fail.
 * No partial output is published after a parse failure. */
int glrt_native_head_parse(const char *text, size_t size, uint32_t *epoch, uint32_t words[32]);
int glrt_native_snapshot_parse(const char *text, size_t size, uint32_t words[20]);
int glrt_native_snapshot_drained(const uint32_t words[20]);
/* Caller retains raw head before invoking this and acknowledges only after
 * success. A supported fit requires return 0 AND estimate.rejection == 0.
 * Faulted/partial but associated heads return 0 with rejection bits, allowing
 * retained drain. No accepted estimate can cross a source epoch or mismatch. */
int glrt_native_associated_solve(const struct glrt_native_batch *batch,
    uint32_t epoch, uint32_t sequence, const uint32_t words[32],
    struct glrt_native_estimate *estimate);
#endif
