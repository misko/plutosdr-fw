/* SPDX-License-Identifier: GPL-2.0 */
#define _POSIX_C_SOURCE 200809L
#include "glrt_native_posix.h"
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t interrupted;
static void interrupt_run(int sig) { (void)sig; interrupted = 1; }

static int integer(const char *text, unsigned base, uint64_t *out)
{
    uint64_t value = 0;
    unsigned digit;
    if (!*text) return -1;
    for (; *text; text++) {
        if (*text >= '0' && *text <= '9') digit = (unsigned)(*text-'0');
        else if (*text >= 'a' && *text <= 'f') digit = (unsigned)(*text-'a'+10);
        else if (*text >= 'A' && *text <= 'F') digit = (unsigned)(*text-'A'+10);
        else return -1;
        if (digit >= base || value > (UINT64_MAX-digit)/base) return -1;
        value = value*base+digit;
    }
    *out = value;
    return 0;
}

static int bootstrap(const char *path, struct glrt_native_batch *b, char raw[256], size_t *length)
{
    int fd, rc;
    ssize_t n;
    struct stat st;
    char copy[256], *token, *save;
    uint64_t v[10];
    unsigned i;
    fd = open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK);
    if (fd < 0) return -1;
    rc = fstat(fd,&st);
    if (rc || !S_ISREG(st.st_mode) || st.st_size <= 0 || st.st_size >= 256) { close(fd); return -1; }
    do { n = read(fd,raw,256); } while (n < 0 && errno == EINTR);
    rc = close(fd);
    if (rc || n != st.st_size || memchr(raw,0,(size_t)n)) return -1;
    *length = (size_t)n;
    memcpy(copy,raw,(size_t)n); copy[n] = 0;
    token = strtok_r(copy," \t\r\n",&save);
    for (i=0; i<10; i++) {
        if (!token || integer(token,16,&v[i])) return -1;
        token = strtok_r(NULL," \t\r\n",&save);
    }
    if (token || v[0] > UINT32_MAX || v[1] > UINT32_MAX || v[3] > 65535 ||
        v[7] > UINT32_MAX || v[8] > 64) return -1;
    *b = (struct glrt_native_batch){(uint32_t)v[0],(uint32_t)v[1],v[2],v[4],v[5],v[6],v[9],
                                    (uint32_t)v[3],(uint32_t)v[7],(uint32_t)v[8]};
    return glrt_native_batch_valid(b) ? 0 : -1;
}

/* The PPU operator must attest the radio and hold its lease, start coarse RX,
 * retain an actual acquisition, then explicitly rebase and provide its mapped
 * finite prediction. This executable never starts RX, acquires, rebases or
 * guesses a sysfs directory. Unacknowledged heads after failure need retained
 * recovery by that same operator; never clear them merely to restart. */
int main(int argc, char **argv)
{
    struct glrt_native_posix io;
    struct glrt_native_ports p;
    struct glrt_native_controller controller;
    struct glrt_native_batch b;
    struct sigaction action;
    struct timespec pause = {0,100000};
    uint64_t frames, seconds;
    char raw[256];
    size_t size;
    int rc;
    if (argc != 6 || integer(argv[4],10,&frames) || integer(argv[5],10,&seconds) ||
        !frames || frames > 225000 || !seconds || seconds > 300 || bootstrap(argv[3],&b,raw,&size)) {
        fprintf(stderr,"usage: %s ATTESTED_SYSFS_DIRECTORY NEW_JOURNAL BOOTSTRAP_FILE FRAMES SECONDS\n",argv[0]);
        return 2;
    }
    if (glrt_native_posix_open(&io,&p,argv[1],argv[2],128U*1024U*1024U)) return 2;
    if (glrt_native_controller_init(&controller,&p,&b,(uint32_t)frames,(double)seconds)) {
        glrt_native_posix_close(&io); return 2;
    }
    memset(&action,0,sizeof(action));
    action.sa_handler = interrupt_run;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT,&action,NULL) || sigaction(SIGTERM,&action,NULL) ||
        p.retain(p.context,"acquisition_seed",raw,size)) { glrt_native_posix_close(&io); return 2; }
    do {
        if (interrupted) glrt_native_controller_request_stop(&controller);
        rc = glrt_native_controller_tick(&controller);
        if (rc == GLRT_NATIVE_RUNNING) nanosleep(&pause,NULL);
    } while (rc == GLRT_NATIVE_RUNNING);
    if (glrt_native_posix_close(&io) && !rc) rc = GLRT_NATIVE_IO_ERROR;
    printf("{\"scope\":\"finite_radio_local_feedback\",\"result\":%d,"
           "\"configured\":%" PRIu32 ",\"retained_popped\":%" PRIu32 ","
           "\"journal_bytes\":%" PRIu64 "}\n",rc,controller.configured,controller.sequence,io.bytes);
    return rc ? 1 : 0;
}
