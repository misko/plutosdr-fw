/* SPDX-License-Identifier: GPL-2.0 */
#define _POSIX_C_SOURCE 200809L
#include "glrt_tracking_session.h"
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <math.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define EVENT_BYTES 65536U
#define MAX_BYTES (8U*1024U*1024U-EVENT_BYTES)
struct line { char text[16384]; size_t used; int failed; };
static void add(struct line *l, const char *format, ...)
{
    va_list args;int n;
    if(l->failed) return;
    va_start(args,format);n=vsnprintf(l->text+l->used,sizeof(l->text)-l->used,format,args);va_end(args);
    if(n<0 || (size_t)n>=sizeof(l->text)-l->used) l->failed=1;
    else l->used+=(size_t)n;
}
static void real(struct line *l,double x) { if(!isfinite(x)) l->failed=1;else add(l,"%.17g",x); }
static void words(struct line *l,const uint32_t *w,unsigned n)
{
    add(l,"[");for(unsigned i=0;i<n;i++) add(l,"%s%" PRIu32,i ? "," : "",w[i]);add(l,"]");
}
static void view(struct line *l,const struct glrt_tracking_iq_view *v)
{
    add(l,"{\"first\":%" PRIu64 ",\"end\":%" PRIu64 ",\"source_now\":%" PRIu64
        ",\"observed_ns\":%" PRIu64 ",\"generation\":%" PRIu64
        ",\"epoch\":%u,\"valid\":%u,\"closed\":%u}",
        v->first,v->end,v->source_now,v->observed_ns,v->generation,v->epoch,v->valid,v->closed);
}
static FILE *create(int directory,const char *name)
{
    int fd=openat(directory,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    FILE *f;if(fd<0) return NULL;
    f=fdopen(fd,"wb");if(!f) close(fd);return f;
}
static uint64_t clock_ns(void *unused)
{
    struct timespec t;(void)unused;
    if(clock_gettime(CLOCK_MONOTONIC,&t)) return 0;
    return (uint64_t)t.tv_sec*UINT64_C(1000000000)+(uint64_t)t.tv_nsec;
}
static int cancelled(void *context)
{
    struct glrt_tracking_session *s=context;int value;
    if(pthread_mutex_lock(&s->mutex)) return -1;
    value=s->stopping || s->fatal;
    return pthread_mutex_unlock(&s->mutex) ? -1 : value;
}
static int wait_for_iq(void *context)
{
    struct glrt_tracking_session *s=context;struct timespec t;int rc=0;
    if(clock_gettime(CLOCK_MONOTONIC,&t) || pthread_mutex_lock(&s->mutex)) return -1;
    t.tv_nsec+=1000000;if(t.tv_nsec>=1000000000) { t.tv_sec++;t.tv_nsec-=1000000000; }
    if(!s->stopping && !s->fatal) rc=pthread_cond_timedwait(&s->changed,&s->mutex,&t);
    if(pthread_mutex_unlock(&s->mutex)) return -1;
    return rc && rc!=ETIMEDOUT ? -1 : 0;
}

/* Worker-thread-only, synchronous exact evidence. Terminal records are
 * separate from HANDOFF proposals; a proposal can still fail its last check. */
static int record(struct glrt_tracking_session *s,int kind,const struct glrt_tracking_worker *w)
{
    struct line l={0};const int16_t *iq=NULL;size_t samples=0;
    const struct glrt_tracking_bootstrap_trace *t=&w->trace;
    add(&l,"{\"schema\":\"glrt_bootstrap_diagnostic_v1\",\"attempt\":%" PRIu64
        ",\"kind\":%d,\"status\":%d,\"recorded_ns\":%" PRIu64 ",\"event\":",
        s->attempts,kind,w->status,clock_ns(NULL));words(&l,s->active,16);
    if(kind==GLRT_WORKER_SEED_IQ) {
        const struct glrt_tracking_seed_window *p=&w->seed;
        iq=w->seed_iq;samples=GLRT_SEED_WINDOW_SAMPLES;
        add(&l,",\"first\":%" PRIu64 ",\"first_repeat\":%u,\"seed_start\":%" PRIu64
            ",\"seed_fraction\":%u,\"maximum_age\":%u,\"starts\":[%zu,%zu,%zu,%zu],\"selected\":",
            p->first,p->first_repeat,p->seed_start,p->seed_fraction,p->maximum_age,
            p->starts[0],p->starts[1],p->starts[2],p->starts[3]);view(&l,&p->selected);
        add(&l,",\"copied\":");view(&l,&p->copied);
    } else if(kind==GLRT_WORKER_RESOLVED) {
        add(&l,",\"seed_start\":%" PRIu64 ",\"seed_fraction\":%u,\"hypotheses\":[",
            w->live.core.seed_start,w->live.core.seed_fraction);
        for(unsigned i=0;i<17;i++) {
            const struct glrt_resolver_peak *p=&w->resolved.hypotheses[i];
            add(&l,"%s[%d,",i ? "," : "",p->shift);real(&l,p->cfo_hz);add(&l,",");real(&l,p->power_coherence);add(&l,"]");
        }
        add(&l,"],\"best_shift\":%d,\"cfo_hz\":",w->resolved.best.shift);real(&l,w->resolved.best.cfo_hz);
    } else if(kind==GLRT_WORKER_PAST) {
        iq=w->scratch;samples=3300;
        add(&l,",\"frame\":%u,\"first\":%" PRIu64 ",\"phase_step\":%u,\"reference_phase\":%u,\"source\":",
            t->frame,t->job.start,t->job.phase_step,t->job.reference_phase);view(&l,&t->source);
        add(&l,",\"moment_start\":%" PRIu64 ",\"moment_count\":%u,\"moment_fault\":%u,\"moment_step\":%u,\"moments\":",
            t->moments.start,t->moments.count,t->moments.fault,t->moments.phase_step);words(&l,t->moments.words,16);
        add(&l,",\"estimate\":[");real(&l,t->estimate.delay_correction_s);add(&l,",");real(&l,t->estimate.residual_cfo_hz);
        add(&l,",");real(&l,t->estimate.cfo_hz);add(&l,",");real(&l,t->estimate.coherence);
        add(&l,",");real(&l,t->estimate.linearized_coherence);
        add(&l,"],\"rejection\":%u,\"accepted\":%d",t->estimate.rejection,t->accepted);
    } else if(kind==GLRT_WORKER_HANDOFF) {
        const struct glrt_native_batch *b=&t->handoff.prediction;
        const struct glrt_native_trend *h=&w->live.core.trend.history;
        add(&l,",\"frame\":%u,\"rate\":%u,\"batch\":[%u,%u,%" PRIu64 ",%" PRIu64
            ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%u,%u,%u],\"history\":{\"epoch\":%u,\"first_frame\":%u,"
            "\"last_seen\":%u,\"last_supported\":%u,\"anchor\":%" PRIu64 ",\"count\":%u,\"next\":%u,\"rows\":[",
            t->frame,t->handoff.rate,b->epoch,b->tag,b->start,b->period,b->step,b->delta,b->expires,
            b->fraction,b->seed,b->repeats,h->epoch,h->first_frame,h->last_seen,h->last_supported,h->anchor,h->count,h->next);
        for(unsigned i=0;i<GLRT_NATIVE_TREND_WINDOW;i++) {
            add(&l,"%s[%u,",i ? "," : "",h->observations[i].frame);real(&l,h->observations[i].offset_samples);
            add(&l,",");real(&l,h->observations[i].cfo_hz);add(&l,"]");
        }
        add(&l,"]},\"checked_source\":");view(&l,&w->checked_source);
    } else if(kind==0) {
        add(&l,",\"started_ns\":%" PRIu64 ",\"last_ns\":%" PRIu64 ",\"deadline_ns\":%" PRIu64
            ",\"source_checked_ns\":%" PRIu64 ",\"fft_calls\":%u,\"retained_past\":%u,\"waits\":%u,"
            "\"failure\":%u,\"history_count\":%u,\"checked_source\":",
            w->started_ns,w->last_ns,w->deadline_ns,w->source_checked_ns,w->fft_calls,w->retained_past,
            w->waits,w->live.core.failure,w->live.core.trend.history.count);view(&l,&w->checked_source);
    } else return -1;
    add(&l,",\"iq_offset_samples\":%" PRIu64 ",\"iq_samples\":%zu}\n",s->iq_samples,samples);
    if(l.failed || s->bytes>MAX_BYTES || samples*4+l.used>MAX_BYTES-s->bytes) return -1;
    if(samples && (fwrite(iq,4,samples,s->iq)!=samples || fflush(s->iq))) return -1;
    if(fwrite(l.text,1,l.used,s->journal)!=l.used || fflush(s->journal)) return -1;
    s->bytes+=samples*4+l.used;s->iq_samples+=samples;return 0;
}
static int retain(void *context,enum glrt_tracking_worker_record kind,const struct glrt_tracking_worker *w)
{ return record(context,kind,w); }

static void *run(void *context)
{
    struct glrt_tracking_session *s=context;
    for(;;) {
        uint64_t first;int rc,failed;
        if(pthread_mutex_lock(&s->mutex)) return (void *)(uintptr_t)1;
        while(!s->queued && !s->stopping && !s->fatal)
            if(pthread_cond_wait(&s->changed,&s->mutex)) { s->fatal=1;break; }
        if(s->fatal || (s->stopping && !s->queued)) { pthread_mutex_unlock(&s->mutex);return NULL; }
        memcpy(s->active,s->pending,sizeof(s->active));s->queued=0;s->busy=1;s->attempts++;
        pthread_mutex_unlock(&s->mutex);
        first=s->active[3]|((uint64_t)s->active[4]<<32);
        if(first>UINT64_MAX-5000000U) {
            memset(s->worker,0,sizeof(*s->worker));rc=s->worker->status=GLRT_WORKER_SOURCE;
        } else {
            s->config.source_deadline=first+5000000U;
            rc=glrt_tracking_worker_run(s->worker,&s->config,s->active);
        }
        failed=record(s,0,s->worker) || rc==GLRT_WORKER_RETENTION || rc==GLRT_WORKER_PORT;
        if(pthread_mutex_lock(&s->mutex)) return (void *)(uintptr_t)1;
        s->completed++;s->ready+=!failed && rc==GLRT_WORKER_READY;s->busy=0;
        if(failed) s->fatal=1;
        pthread_cond_broadcast(&s->changed);pthread_mutex_unlock(&s->mutex);
    }
}

int glrt_tracking_session_start(struct glrt_tracking_session *s,int directory,
    struct glrt_tracking_iq_owner *owner,const int16_t *refs,glrt_resolver_fft fft,void *fft_context)
{
    pthread_condattr_t attr;int have_mutex=0,have_attr=0,have_cond=0;
    if(!s || directory<0 || !owner || !refs || !fft) return -1;
    memset(s,0,sizeof(*s));
    if(pthread_mutex_init(&s->mutex,NULL)) goto bad;
    have_mutex=1;
    if(pthread_condattr_init(&attr)) goto bad;
    have_attr=1;
    if(pthread_condattr_setclock(&attr,CLOCK_MONOTONIC) || pthread_cond_init(&s->changed,&attr)) goto bad;
    have_cond=1;pthread_condattr_destroy(&attr);have_attr=0;
    s->worker=calloc(1,sizeof(*s->worker));
    s->journal=create(directory,"bootstrap.jsonl");s->iq=create(directory,"bootstrap.iq.ci16");
    s->events=create(directory,"bootstrap_events.csv");
    if(!s->worker || !s->journal || !s->iq || !s->events ||
        fputs("sequence,observed_ns,disposition\n",s->events)<0 || fflush(s->events)) goto bad;
    s->config=(struct glrt_tracking_worker_config){.owner=owner,.references=refs,.fft=fft,.fft_context=fft_context,
        .ports={s,clock_ns,cancelled,wait_for_iq,retain},.wall_budget_ns=UINT64_C(3000000000),
        .maximum_seed_age=2500000U,.lead_samples=2500};
    s->event_bytes=sizeof("sequence,observed_ns,disposition\n")-1;
    s->initialized=1;
    if(pthread_create(&s->thread,NULL,run,s)) goto bad;
    s->started=1;return 0;
bad:
    if(s->journal) fclose(s->journal);
    if(s->iq) fclose(s->iq);
    if(s->events) fclose(s->events);
    free(s->worker);if(have_cond) pthread_cond_destroy(&s->changed);
    if(have_attr) pthread_condattr_destroy(&attr);
    if(have_mutex) pthread_mutex_destroy(&s->mutex);
    memset(s,0,sizeof(*s));return -1;
}

int glrt_tracking_session_offer(struct glrt_tracking_session *s,const uint32_t event[16])
{
    int rc,classification,written;
    if(!s || !s->started || s->joined || !event) return -1;
    classification=glrt_tracking_seed_event(event);
    if(pthread_mutex_lock(&s->mutex)) return -1;
    if(classification<0 || s->fatal) { s->fatal=1;rc=-1; }
    else if(classification==GLRT_SEED_IGNORE) { s->ignored++;rc=GLRT_SESSION_IGNORED; }
    else if(s->stopping) { s->stopped_events++;rc=GLRT_SESSION_STOPPED; }
    else if(s->queued || s->busy) { s->busy_events++;rc=GLRT_SESSION_BUSY; }
    else rc=GLRT_SESSION_QUEUED;
    /* Retain admission before publishing the queue slot. This short write
     * holds only the session mutex, never the capture-IQ mutex. */
    written=s->event_bytes>EVENT_BYTES-128 ? -1 :
        fprintf(s->events,"%u,%" PRIu64 ",%d\n",event[2],clock_ns(NULL),rc);
    if(written<0 || fflush(s->events)) { s->fatal=1;rc=-1; }
    else s->event_bytes+=(unsigned)written;
    if(rc==GLRT_SESSION_QUEUED) { memcpy(s->pending,event,sizeof(s->pending));s->queued=1; }
    pthread_cond_broadcast(&s->changed);
    return pthread_mutex_unlock(&s->mutex) ? -1 : rc;
}
int glrt_tracking_session_wake(struct glrt_tracking_session *s)
{
    int failed;if(!s || !s->started || s->joined || pthread_mutex_lock(&s->mutex)) return -1;
    failed=s->fatal || pthread_cond_broadcast(&s->changed);
    return pthread_mutex_unlock(&s->mutex) || failed ? -1 : 0;
}
int glrt_tracking_session_stop(struct glrt_tracking_session *s)
{
    if(!s || !s->started || s->joined || pthread_mutex_lock(&s->mutex)) return -1;
    s->stopping=1;pthread_cond_broadcast(&s->changed);
    return pthread_mutex_unlock(&s->mutex) ? -1 : 0;
}
int glrt_tracking_session_join(struct glrt_tracking_session *s)
{
    int failed=0;void *thread_result=NULL;
    if(!s || !s->started || s->joined || !s->stopping || pthread_join(s->thread,&thread_result)) return -1;
    s->joined=1;
    if(thread_result || s->queued || s->busy || s->attempts!=s->completed) failed=1;
    if(fclose(s->journal)) failed=1;
    if(fclose(s->iq)) failed=1;
    if(fclose(s->events)) failed=1;
    free(s->worker);s->worker=NULL;
    if(pthread_cond_destroy(&s->changed) || pthread_mutex_destroy(&s->mutex)) failed=1;
    s->initialized=0;return failed || s->fatal ? -1 : 0;
}
