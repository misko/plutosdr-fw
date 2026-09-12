/* SPDX-License-Identifier: GPL-2.0 */
#ifndef GLRT_TRACKING_SESSION_H
#define GLRT_TRACKING_SESSION_H
#include "glrt_tracking_worker.h"
#include <stdio.h>

enum { GLRT_SESSION_IGNORED=0, GLRT_SESSION_QUEUED=1, GLRT_SESSION_BUSY=2, GLRT_SESSION_STOPPED=3 };
struct glrt_tracking_session {
    pthread_mutex_t mutex;
    pthread_cond_t changed;
    pthread_t thread;
    struct glrt_tracking_worker *worker;
    struct glrt_tracking_worker_config config;
    FILE *journal, *iq, *events;
    uint32_t pending[16], active[16];
    uint64_t attempts, completed, ready, ignored, busy_events, stopped_events;
    uint64_t bytes, iq_samples, event_bytes;
    int initialized, started, stopping, queued, busy, fatal, joined;
};
/* Start one waiting background thread. The capture owner may be initialized
 * after this call but must be published before the first offer. The caller
 * attests references/FFT and retains their identities with the radio receipt.
 * Files are exclusive in an already-owned directory; combined worker evidence
 * is limited to 8 MiB. Only the worker writes journal/IQ; the capture thread
 * writes event dispositions. No native tracking job is submitted by this
 * diagnostic session. refs/owner/FFT must remain valid until join completes. */
int glrt_tracking_session_start(struct glrt_tracking_session *, int directory,
    struct glrt_tracking_iq_owner *, const int16_t *references, glrt_resolver_fft, void *fft_context);
/* Capture-thread-only: validate every GLA1 record; queue at most one accepted
 * event while idle. Busy/ignored/stopped decisions are explicitly retained.
 * The original raw event stream remains authoritative for sequence/closure. */
int glrt_tracking_session_offer(struct glrt_tracking_session *, const uint32_t event[16]);
int glrt_tracking_session_wake(struct glrt_tracking_session *);
int glrt_tracking_session_stop(struct glrt_tracking_session *);
/* Called after stop and final event drain, before destroying the IQ owner.
 * Joins the thread, closes its evidence and destroys synchronization. On a
 * join failure nothing reachable by the worker is freed. A failed retention
 * or port is fatal even if receiver IQ itself remained healthy. */
int glrt_tracking_session_join(struct glrt_tracking_session *);
#endif
