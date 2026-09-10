/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_NATIVE_POSIX_H
#define GLRT_NATIVE_POSIX_H
#include "glrt_native_controller.h"

/* The operator supplies the attested IIO sysfs directory and a new journal on
 * a bounded spool. This adapter never discovers radios or changes RF settings.
 * GLRJ1 is an internal, length-framed journal; payloads remain exact sysfs text.
 * A journal on tmpfs survives process failure, not power loss. The operator
 * must export it before cleanup. No automatic file removal or overwrite. */
struct glrt_native_posix {
    int device, journal, failed;
    uint64_t bytes, limit;
};
int glrt_native_posix_open(struct glrt_native_posix *, struct glrt_native_ports *,
    const char *device_directory, const char *new_journal, uint64_t byte_limit);
int glrt_native_posix_close(struct glrt_native_posix *);
#endif
