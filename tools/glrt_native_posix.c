/* SPDX-License-Identifier: GPL-2.0 */
#define _POSIX_C_SOURCE 200809L
#include "glrt_native_posix.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static int read_attribute(void *context, const char *name, char *out, size_t size)
{
    struct glrt_native_posix *p = context;
    ssize_t n;
    int fd, rc;
    if (strcmp(name,"native_schedule_snapshot") && strcmp(name,"native_schedule_result") &&
        strcmp(name,"tracking_snapshot") && strcmp(name,"tracking_result")) return -1;
    if (!size || size > INT_MAX) return -1;
    fd = openat(p->device,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (fd < 0) return -1;
    do { n = read(fd,out,size); } while (n < 0 && errno == EINTR);
    rc = close(fd);
    return rc < 0 || n < 0 ? -1 : (int)n;
}

static int write_attribute(void *context, const char *name, const char *data, size_t size)
{
    struct glrt_native_posix *p = context;
    ssize_t n;
    int fd, rc;
    if (strcmp(name,"native_schedule_submit") && strcmp(name,"native_schedule_pop") &&
        strcmp(name,"native_schedule_command") && strcmp(name,"tracking_submit") &&
        strcmp(name,"tracking_pop") && strcmp(name,"tracking_command")) return -1;
    if (!size || size > INT_MAX) return -1;
    fd = openat(p->device,name,O_WRONLY|O_CLOEXEC|O_NOFOLLOW);
    if (fd < 0) return -1;
    /* No retry after EINTR/short writes: a sysfs command may already have had
     * side effects. Controller cancellation owns uncertain completion. */
    n = write(fd,data,size);
    rc = close(fd);
    return rc < 0 || n < 0 ? -1 : (int)n;
}

static int append_all(int fd, const char *data, size_t size)
{
    while (size) {
        ssize_t n = write(fd,data,size);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        data += n;
        size -= (size_t)n;
    }
    return 0;
}

static int retain(void *context, const char *kind, const char *data, size_t size)
{
    struct glrt_native_posix *p = context;
    char header[80];
    size_t k;
    int n;
    if (p->failed) return -1;
    for (k=0; kind[k]; k++)
        if (k >= 32 || !((kind[k] >= 'a' && kind[k] <= 'z') || kind[k] == '_')) return -1;
    if (!k || size > 4096) return -1;
    n = snprintf(header,sizeof(header),"%s %zu\n",kind,size);
    if (n <= 0 || (size_t)n >= sizeof(header) || p->bytes > p->limit ||
        (uint64_t)n+size > p->limit-p->bytes) { p->failed = 1; return -1; }
    if (append_all(p->journal,header,(size_t)n) || append_all(p->journal,data,size) ||
        fdatasync(p->journal)) { p->failed = 1; return -1; }
    p->bytes += (size_t)n+size;
    return 0;
}

static double monotonic_clock(void *context)
{
    struct timespec t;
    (void)context;
    if (clock_gettime(CLOCK_MONOTONIC,&t)) return NAN;
    return t.tv_sec+t.tv_nsec/1e9;
}

int glrt_native_posix_open(struct glrt_native_posix *p, struct glrt_native_ports *ports,
    const char *device, const char *journal, uint64_t limit)
{
    if (!p || !ports || !device || !journal || limit < 4096 || limit > 128U*1024U*1024U) return -1;
    *p = (struct glrt_native_posix){-1,-1,0,0,limit};
    p->device = open(device,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if (p->device < 0) return -1;
    p->journal = open(journal,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (p->journal < 0) { close(p->device); p->device = -1; return -1; }
    if (append_all(p->journal,"GLRJ1\n",6) || fdatasync(p->journal)) {
        glrt_native_posix_close(p);
        return -1;
    }
    p->bytes = 6;
    *ports = (struct glrt_native_ports){p,read_attribute,write_attribute,retain,monotonic_clock};
    return 0;
}

int glrt_native_posix_close(struct glrt_native_posix *p)
{
    int rc = 0;
    if (!p) return -1;
    if (p->journal >= 0) {
        if (fdatasync(p->journal)) rc = -1;
        if (close(p->journal)) rc = -1;
        p->journal = -1;
    }
    if (p->device >= 0) {
        if (close(p->device)) rc = -1;
        p->device = -1;
    }
    return rc;
}
