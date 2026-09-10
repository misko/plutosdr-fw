/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_NATIVE_CONTROLLER_H
#define GLRT_NATIVE_CONTROLLER_H
#include "glrt_native_trend.h"

/* Narrow synchronous ports. read/write return byte counts or negative errors.
 * retain returns zero only once the exact bytes are retained. It must finish
 * before SUBMIT/POP; a storage failure never permits discarding a hardware head.
 * The caller owns the PPU radio lease and supplies a monotonic clock. */
struct glrt_native_ports {
    void *context;
    int (*read)(void *, const char *, char *, size_t);
    int (*write)(void *, const char *, const char *, size_t);
    int (*retain)(void *, const char *, const char *, size_t);
    double (*clock)(void *);
};
enum glrt_native_controller_result {
    GLRT_NATIVE_RUNNING = 1,
    GLRT_NATIVE_COMPLETE = 0,
    GLRT_NATIVE_IO_ERROR = -1,
    GLRT_NATIVE_PROTOCOL_ERROR = -2,
    GLRT_NATIVE_SOURCE_LOST = -3,
    GLRT_NATIVE_ACQUISITION_LOST = -4,
    GLRT_NATIVE_DEADLINE = -5,
    GLRT_NATIVE_RETENTION_ERROR = -6
};
struct glrt_native_owned_batch {
    struct glrt_native_batch batch;
    uint32_t first_frame, received;
    int occupied;
};
struct glrt_native_controller {
    struct glrt_native_trend trend;
    struct glrt_native_owned_batch slots[2];
    struct glrt_native_ports ports;
    uint32_t frames, next_frame, next_tag, sequence, configured;
    double deadline, cleanup_deadline;
    int started, stopping, cancelled, clearing, done, failure;
};
/* Bootstrap is a retained acquisition prediction in a freshly rebased source
 * epoch, with zero scheduled counters. It begins at global frame zero. The
 * runtime checks live source lead before submitting it. No acquisition truth
 * is invented here. Total work is bounded to frames <=225000 and <=300 s.
 * Returns zero after local validation; does not perform I/O. */
int glrt_native_controller_init(struct glrt_native_controller *,
    const struct glrt_native_ports *, const struct glrt_native_batch *bootstrap,
    uint32_t frames, double seconds);
/* One bounded read/process/submit step. Caller polls or waits between ticks.
 * End-of-run CLEAR happens only after every result is retained and popped.
 * A negative return ends the run. If retention/protocol recovery fails, the
 * hardware heads remain unacknowledged; external recovery must retain them.
 * Call request_stop for an orderly bounded cancellation (also for signals). */
int glrt_native_controller_tick(struct glrt_native_controller *);
void glrt_native_controller_request_stop(struct glrt_native_controller *);
#endif
