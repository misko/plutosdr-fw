/* SPDX-License-Identifier: GPL-2.0 */
/* One bounded GLI1 acquisition/catch-up/native-feedback experiment. Caller
 * holds the radio lease, attests ROMs and calibrates the exact receive clock. */
#define _XOPEN_SOURCE 700
#include "glrt_iq_tracking_source.h"
#include "glrt_tracking_worker.h"
#include "glrt_tracking_transport.h"
#include "glrt_native_posix.h"
#include "glrt_tracking_observer.h"
#include <fftw3.h>
#include <iio.h>
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define CHUNK 16384U
#define BLOCKS 1536U
#define RING 5000000U
#define ATTEMPTS 6U
#define PAIR_LIMIT 64U
#define PAIR_SAMPLES 3333U
#define RESTART_LIMIT 3U
struct paired_head { uint32_t words[32]; };
struct dwell_limits { unsigned blocks,attempts,alarm_seconds; uint64_t worker_ns; int selected_iq; };
static int dwell_limits(const char *blocks,struct dwell_limits *out)
{
    if(!blocks || !strcmp(blocks,"1536"))
        *out=(struct dwell_limits){BLOCKS,ATTEMPTS,25,UINT64_C(12000000000),0};
    else if(!strcmp(blocks,"4096"))
        *out=(struct dwell_limits){4096,16,45,UINT64_C(30000000000),0};
    else if(!strcmp(blocks,"45000"))
        *out=(struct dwell_limits){45000,200,325,UINT64_C(300000000000),1};
    else if(!strcmp(blocks,"1536-selected"))
        *out=(struct dwell_limits){BLOCKS,ATTEMPTS,25,UINT64_C(12000000000),1};
    else return -1;
    return 0;
}
static volatile sig_atomic_t interrupted;
static void signal_stop(int n) { (void)n;interrupted=1; }
static uint64_t wide(const uint32_t *w) { return w[0]|((uint64_t)w[1]<<32); }
static uint64_t clock_ns(void *unused)
{
    struct timespec t;(void)unused;
    if(clock_gettime(CLOCK_MONOTONIC,&t)) return 0;
    return (uint64_t)t.tv_sec*UINT64_C(1000000000)+(uint64_t)t.tv_nsec;
}
struct live {
    pthread_mutex_t mutex;
    pthread_t thread;
    int stop,done,result,started;
    uint32_t epoch,rate,attempts,handoffs,attempt_limit;
    uint32_t restarts,native_runs,native_results,native_completed_runs;
    int native_clean_loss;
    struct glrt_tracking_iq_owner owner;
    struct glrt_tracking_worker worker;
    struct glrt_cpu_coarse_workspace coarse;
    struct glrt_native_controller controller;
    struct glrt_native_ports native;
    int16_t bank[12][11][11][2],refs[52800],scan_iq[28000];
    fftw_plan fft;
    FILE *journal,*worker_iq,*grids,*scan_samples,*native_coarse_iq;
    uint64_t iq_samples,deadline_ns,scan_iq_samples;
    struct paired_head paired[PAIR_LIMIT];
    uint32_t paired_queued,paired_copied,paired_episode_first;
    int selected_iq,visit_mode;
    pthread_t observer_thread;
    int observer_started,observer_stop,observer_result;
    struct glrt_tracking_observer observer;
    int16_t observer_scratch[6600];
    FILE *observer_journal,*observer_iq;
    uint32_t observer_retained;
};
static int cancelled(void *pointer)
{
    struct live *s=pointer;int value;uint64_t now=clock_ns(NULL);
    if(pthread_mutex_lock(&s->mutex)) return -1;
    value=s->stop || interrupted || !now || now>=s->deadline_ns;
    return pthread_mutex_unlock(&s->mutex) ? -1 : value;
}
static int pause_worker(void *unused)
{
    struct timespec t={0,1000000};(void)unused;
    return nanosleep(&t,NULL) && errno!=EINTR ? -1 : 0;
}
static int fft(void *pointer,double (*bins)[2],size_t count)
{
    if(count!=GLRT_RESOLVER_FFT) return -1;
    fftw_execute_dft(((struct live *)pointer)->fft,bins,bins);return 0;
}
static void view(FILE *f,const struct glrt_tracking_iq_view *v)
{
    fprintf(f,"{\"first\":%" PRIu64 ",\"end\":%" PRIu64 ",\"source_now\":%" PRIu64
        ",\"observed_ns\":%" PRIu64 ",\"generation\":%" PRIu64 ",\"epoch\":%u,\"valid\":%u,\"closed\":%u}",
        v->first,v->end,v->source_now,v->observed_ns,v->generation,v->epoch,v->valid,v->closed);
}
static int observer_cancelled(void *pointer)
{
    struct live *s=pointer;int stop,rc=cancelled(s);
    if(rc) return rc;
    if(pthread_mutex_lock(&s->mutex)) return -1;
    stop=s->observer_stop;
    return pthread_mutex_unlock(&s->mutex) ? -1 : stop;
}
/* Only this worker writes observer files. The acquired history is retained in
 * worker.jsonl kind 4, bound here by attempt and epoch. Native history, ports
 * and evidence are never accessed from the observer thread. */
static int observer_retain(void *pointer,const struct glrt_tracking_observer_trace *t,const int16_t *iq)
{
    struct live *s=pointer;FILE *f=s->observer_journal;
    if(!f || !s->observer_iq || s->observer_retained>=200*(RESTART_LIMIT+1) ||
       fwrite(iq,4,3300,s->observer_iq)!=3300 || fflush(s->observer_iq)) return -1;
    fprintf(f,"{\"kind\":\"measurement\",\"attempt\":%u,\"episode\":%u,\"epoch\":%u,\"rate\":2500000,"
        "\"recorded_ns\":%" PRIu64 ",\"sequence\":%u,\"frame\":%u,\"first\":%" PRIu64
        ",\"phase_step\":%u,\"reference_phase\":%u,\"accepted\":%d,\"rejection\":%u,"
        "\"coherence\":%.17g,\"linearized_coherence\":%.17g,\"delay_correction_s\":%.17g,"
        "\"residual_cfo_hz\":%.17g,\"cfo_hz\":%.17g,\"iq_offset\":%u,\"iq_samples\":3300,\"source\":",
        s->attempts,s->restarts,s->epoch,clock_ns(NULL),s->observer.measurements,t->frame,t->job.start,
        t->job.phase_step,t->job.reference_phase,t->accepted,t->estimate.rejection,t->estimate.coherence,
        t->estimate.linearized_coherence,t->estimate.delay_correction_s,t->estimate.residual_cfo_hz,
        t->estimate.cfo_hz,s->observer_retained*3300);
    view(f,&t->source);fputs(",\"moments\":[",f);
    for(unsigned k=0;k<16;k++) fprintf(f,"%s%u",k ? "," : "",t->moments.words[k]);
    fputs("]}\n",f);
    if(ferror(f) || fflush(f)) return -1;
    s->observer_retained++;return 0;
}
static void *observer_thread(void *pointer)
{
    struct live *s=pointer;struct glrt_tracking_observer_trace trace;int rc;
    struct glrt_tracking_observer_ports ports={s,clock_ns,observer_cancelled,observer_retain};
    do {
        rc=glrt_tracking_observer_step(&s->observer,&s->owner,s->refs,s->observer_scratch,&ports,&trace);
        if(rc==GLRT_OBSERVER_WAIT && pause_worker(s)) {
            s->observer.status=rc=GLRT_OBSERVER_INVALID;
        }
    } while(rc==GLRT_OBSERVER_WAIT || rc==GLRT_OBSERVER_MEASURED);
    fprintf(s->observer_journal,"{\"kind\":\"terminal\",\"attempt\":%u,\"episode\":%u,\"epoch\":%u,"
        "\"recorded_ns\":%" PRIu64 ",\"status\":%d,\"measurements\":%u,\"retained_total\":%u,"
        "\"last_seen\":%u,\"last_supported\":%u}\n",
        s->attempts,s->restarts,s->epoch,clock_ns(NULL),rc,s->observer.measurements,
        s->observer_retained,s->observer.trend.history.last_seen,s->observer.trend.history.last_supported);
    s->observer_result=ferror(s->observer_journal) || fflush(s->observer_journal) ?
        GLRT_OBSERVER_RETENTION : rc;
    return NULL;
}
static int start_observer(struct live *s)
{
    const struct glrt_tracking_trend *history=&s->worker.live.core.trend;
    struct glrt_tracking_batch batch;struct glrt_tracking_job job;double slope;
    uint64_t now=clock_ns(NULL);uint32_t first=history->history.last_seen;
    if(s->observer_started || !s->observer_journal || !s->observer_iq || first>UINT32_MAX-9)
        return GLRT_NATIVE_RETENTION_ERROR;
    first+=9;
    if(glrt_tracking_trend_batch(history,first,1,1,0,&batch,&slope) ||
       glrt_tracking_prediction(&batch,0,&job) || job.start>UINT64_MAX-7500000 ||
       glrt_tracking_observer_init(&s->observer,history,first,200,job.start+7500000,now,UINT64_C(3000000000)))
        return GLRT_NATIVE_PROTOCOL_ERROR;
    fprintf(s->observer_journal,"{\"kind\":\"start\",\"attempt\":%u,\"episode\":%u,\"epoch\":%u,"
        "\"rate\":2500000,\"native_rate\":%u,\"first_frame\":%u,\"maximum_measurements\":200,"
        "\"source_limit\":%" PRIu64 ",\"started_ns\":%" PRIu64 ",\"deadline_ns\":%" PRIu64
        ",\"retained_total\":%u}\n",s->attempts,s->restarts,s->epoch,s->rate,first,
        s->observer.source_limit,now,s->observer.deadline_ns,s->observer_retained);
    if(ferror(s->observer_journal) || fflush(s->observer_journal)) return GLRT_NATIVE_RETENTION_ERROR;
    s->observer_stop=0;s->observer_result=GLRT_OBSERVER_WAIT;
    if(pthread_create(&s->observer_thread,NULL,observer_thread,s)) return GLRT_NATIVE_IO_ERROR;
    s->observer_started=1;return 0;
}
/* Called by the native worker after its controller has terminated, including
 * error recovery. A failed join keeps observer_started set: nobody may destroy
 * or rebase its owner. Diagnostic history exhaustion does not change native
 * support; infrastructure/evidence failures still fail the qualification. */
static int join_observer(struct live *s)
{
    void *result=NULL;
    if(!s->observer_started) return 0;
    if(pthread_mutex_lock(&s->mutex)) return GLRT_NATIVE_IO_ERROR;
    s->observer_stop=1;
    if(pthread_mutex_unlock(&s->mutex) || pthread_join(s->observer_thread,&result)) return GLRT_NATIVE_IO_ERROR;
    s->observer_started=0;
    if(result) return GLRT_NATIVE_IO_ERROR;
    switch(s->observer_result) {
    case GLRT_OBSERVER_DONE: case GLRT_OBSERVER_HISTORY: case GLRT_OBSERVER_CANCELLED: return 0;
    case GLRT_OBSERVER_RETENTION: return GLRT_NATIVE_RETENTION_ERROR;
    case GLRT_OBSERVER_SOURCE: return GLRT_NATIVE_SOURCE_LOST;
    case GLRT_OBSERVER_DEADLINE: return GLRT_NATIVE_DEADLINE;
    default: return GLRT_NATIVE_IO_ERROR;
    }
}
static int retain(void *pointer,enum glrt_tracking_worker_record kind,const struct glrt_tracking_worker *w)
{
    struct live *s=pointer;FILE *f=s->journal;
    const uint64_t iq_limit=s->selected_iq ? 20000000 : 6000000;
    const int16_t *iq=NULL;size_t samples=0;
    fprintf(f,"{\"attempt\":%u,\"kind\":%d,\"recorded_ns\":%" PRIu64,s->attempts,kind,clock_ns(NULL));
    if(kind==GLRT_WORKER_SEED_IQ) {
        const struct glrt_cpu_seed *p=&w->cpu_seed;
        iq=w->seed_iq;samples=GLRT_CPU_SEED_SAMPLES;
        fprintf(f,",\"first\":%" PRIu64 ",\"start\":%" PRIu64 ",\"fraction\":%u,\"repeat\":%u,"
            "\"starts\":[%zu,%zu,%zu,%zu],\"selected\":",p->first,p->start,p->fraction,p->first_repeat,
            p->starts[0],p->starts[1],p->starts[2],p->starts[3]);view(f,&p->selected);
        fputs(",\"copied\":",f);view(f,&p->copied);
    } else if(kind==GLRT_WORKER_RESOLVED) {
        fprintf(f,",\"best_shift\":%d,\"cfo_hz\":%.17g,\"coherence\":%.17g,\"hypotheses\":[",
            w->resolved.best.shift,w->resolved.best.cfo_hz,w->resolved.best.power_coherence);
        for(unsigned n=0;n<17;n++) {
            const struct glrt_resolver_peak *p=&w->resolved.hypotheses[n];
            fprintf(f,"%s[%d,%.17g,%.17g]",n ? "," : "",p->shift,p->cfo_hz,p->power_coherence);
        }
        fputs("]",f);
    } else if(kind==GLRT_WORKER_PAST) {
        const struct glrt_tracking_bootstrap_trace *t=&w->trace;
        iq=w->scratch;samples=3300;
        fprintf(f,",\"frame\":%u,\"first\":%" PRIu64 ",\"phase_step\":%u,\"reference_phase\":%u,"
            "\"accepted\":%d,\"rejection\":%u,\"coherence\":%.17g,\"cfo_hz\":%.17g,\"source\":",
            t->frame,t->job.start,t->job.phase_step,t->job.reference_phase,t->accepted,
            t->estimate.rejection,t->estimate.coherence,t->estimate.cfo_hz);view(f,&t->source);
        fputs(",\"moments\":[",f);
        for(unsigned n=0;n<16;n++) fprintf(f,"%s%u",n ? "," : "",t->moments.words[n]);
        fputs("]",f);
    } else if(kind==GLRT_WORKER_HANDOFF) {
        const struct glrt_native_trend *h=&w->live.core.trend.history;
        fprintf(f,",\"frame\":%u,\"start\":%" PRIu64 ",\"epoch\":%u,\"anchor\":%" PRIu64
            ",\"count\":%u,\"next\":%u,\"first_frame\":%u,\"last_seen\":%u,\"last_supported\":%u,\"history\":[",
            w->trace.frame,w->trace.job.start,h->epoch,h->anchor,h->count,h->next,
            h->first_frame,h->last_seen,h->last_supported);
        for(unsigned n=0;n<GLRT_NATIVE_TREND_WINDOW;n++) fprintf(f,"%s[%u,%.17g,%.17g]",n ? "," : "",
            h->observations[n].frame,h->observations[n].offset_samples,h->observations[n].cfo_hz);
        fputs("],\"checked_source\":",f);view(f,&w->checked_source);
    } else return -1;
    fprintf(f,",\"iq_offset\":%" PRIu64 ",\"iq_samples\":%zu}\n",s->iq_samples,samples);
    if(s->iq_samples>iq_limit || samples>iq_limit-s->iq_samples ||
       (samples && (fwrite(iq,4,samples,s->worker_iq)!=samples || fflush(s->worker_iq))) ||
       ferror(f) || fflush(f)) return -1;
    s->iq_samples+=samples;return 0;
}
/* Retain only actually searched input in the explicitly selected-IQ profile.
 * Every record associates its byte range with the same owned source view used
 * for the search. This is not a full raw-IQ recording. */
static int retain_scan(struct live *s)
{
    uint64_t limit=(uint64_t)s->attempt_limit*14000;
    if(!s->selected_iq) return 0;
    if(!s->scan_samples || s->scan_iq_samples>limit || limit-s->scan_iq_samples<14000 ||
       fwrite(s->scan_iq,4,14000,s->scan_samples)!=14000 || fflush(s->scan_samples)) return -1;
    s->scan_iq_samples+=14000;return 0;
}
static int capture_worker_done(struct live *s)
{
    int done;
    if((!s->selected_iq && !s->visit_mode) || !s->started) return 0;
    if(pthread_mutex_lock(&s->mutex)) return -1;
    done=s->done;
    return pthread_mutex_unlock(&s->mutex) ? -1 : done;
}
static int capture_early_final(const struct glrt_capture_snapshot *capture,unsigned returned,unsigned limit)
{
    const uint32_t *w=capture->words;
    return !(w[19]&3) && wide(w+4)==wide(w+6) &&
        wide(w+4)>=(uint64_t)returned*CHUNK && wide(w+4)<=(uint64_t)limit*CHUNK;
}
struct partition {
    struct live *live;
    unsigned first,end;
    uint32_t completed;
    int result;
};
static void *scan_partition(void *pointer)
{
    struct partition *p=pointer;struct live *s=p->live;
    p->result=glrt_cpu_coarse_grid(s->coarse.grid,s->scan_iq,s->bank,p->first,p->end,
        &p->completed,cancelled,s);return NULL;
}
static int scan(struct live *s)
{
    pthread_t child;
    struct partition p[2]={{s,0,1666,0,-1},{s,1666,3333,0,-1}};
    memset(&s->coarse,0,sizeof(s->coarse));
    if(pthread_create(&child,NULL,scan_partition,&p[0])) return -1;
    scan_partition(&p[1]);
    /* pthread_join on our joinable child is required before releasing p/IQ.
     * On an impossible ownership error terminate: the kernel closes finite RX. */
    if(pthread_join(child,NULL)) _exit(2);
    if(p[0].result || p[1].result) return -1;
    s->coarse.completed_epochs=p[0].completed+p[1].completed;
    return glrt_cpu_coarse_select(&s->coarse,cancelled,s);
}
/* Cheap ordering only: one original full pilot per coarse basin, with CFO
 * searched by FFT. The selected proposal must still pass the unchanged
 * four-pilot resolver, retained-history gates and live source deadlines. */
static int rank_candidates(struct live *s,double scores[8],unsigned *selected)
{
    double pending[8]={0},energy=0;
    double (*bins)[2]=s->worker.fft_workspace.bins;
    unsigned best=0,n,k;
    memset(scores,0,8*sizeof(*scores));*selected=0;
    if(!s->coarse.count || s->coarse.count>8 || cancelled(s)) return -1;
    for(n=0;n<3300;n++) {
        double i=s->refs[4*n],q=s->refs[4*n+1];energy+=i*i+q*q;
    }
    if(!energy) return -1;
    for(k=0;k<s->coarse.count;k++) {
        unsigned start=s->coarse.peaks[k].epoch+22;
        double observed=0,peak=0,denominator;
        if(s->coarse.peaks[k].epoch>=3333 || cancelled(s)) return -1;
        memset(bins,0,sizeof(s->worker.fft_workspace.bins));
        for(n=0;n<3300;n++) {
            double i=s->scan_iq[2*(start+n)],q=s->scan_iq[2*(start+n)+1];
            double ri=s->refs[4*n],rq=s->refs[4*n+1];
            bins[n][0]=i*ri+q*rq;bins[n][1]=q*ri-i*rq;observed+=i*i+q*q;
        }
        if(fft(s,bins,GLRT_RESOLVER_FFT) || cancelled(s)) return -1;
        denominator=fmax(observed*energy,1);
        for(n=0;n<GLRT_RESOLVER_FFT;n++) {
            double power=(bins[n][0]*bins[n][0]+bins[n][1]*bins[n][1])/denominator;
            if(!isfinite(power)) return -1;
            if(power>peak) peak=power;
        }
        pending[k]=peak;
        if(peak>pending[best]) best=k;
    }
    if(cancelled(s)) return -1;
    memcpy(scores,pending,sizeof(pending));*selected=best;return 0;
}
/* Observe the first 64 retained native heads without changing their authority.
 * Forward exact evidence before remembering metadata; the controller still
 * associates the head, retains its estimate and performs POP itself. */
static int paired_read(void *context,const char *key,char *raw,size_t size)
{
    struct live *s=context;return s->native.read(s->native.context,key,raw,size);
}
static int paired_write(void *context,const char *key,const char *raw,size_t size)
{
    struct live *s=context;return s->native.write(s->native.context,key,raw,size);
}
static double paired_clock(void *context)
{
    struct live *s=context;return s->native.clock(s->native.context);
}
static int paired_retain(void *context,const char *kind,const char *raw,size_t size)
{
    struct live *s=context;uint32_t epoch,w[32];
    if(s->native.retain(s->native.context,kind,raw,size)) return -1;
    if(strcmp(kind,"head") || s->paired_queued==PAIR_LIMIT) return 0;
    if(glrt_tracking_head_parse(raw,size,&epoch,w) || epoch!=s->epoch ||
       w[25]!=s->rate || w[1]!=s->paired_queued-s->paired_episode_first) return -1;
    memcpy(s->paired[s->paired_queued++].words,w,sizeof(w));return 0;
}
/* GLI1 owner coordinates already describe delayed-filter signal centers.
 * Convert native start to that same coordinate system, keeping 16 leading
 * coarse samples and 17 trailing samples for diagnostic timing refinement.
 * A head can precede publication of its matching coarse IQ. Leave it queued
 * until a later tick; never block native submission waiting for a refill. */
static int paired_copy(struct live *s)
{
    struct glrt_tracking_iq_view v;int16_t iq[2*PAIR_SAMPLES];
    while(s->paired_copied<s->paired_queued) {
        const uint32_t *w=s->paired[s->paired_copied].words;
        uint64_t first=wide(w+3)/(s->rate/2500000);
        if(first<16 || first>UINT64_MAX-PAIR_SAMPLES) return GLRT_NATIVE_PROTOCOL_ERROR;
        first-=16;
        if(glrt_tracking_iq_owner_copy(&s->owner,s->epoch,0,NULL,0,&v) ||
           !v.valid || v.closed || first<v.first) return GLRT_NATIVE_SOURCE_LOST;
        if(first+PAIR_SAMPLES>v.end) return 0;
        if(glrt_tracking_iq_owner_copy(&s->owner,s->epoch,first,iq,PAIR_SAMPLES,&v) || v.closed)
            return GLRT_NATIVE_SOURCE_LOST;
        if(!s->native_coarse_iq || fwrite(iq,4,PAIR_SAMPLES,s->native_coarse_iq)!=PAIR_SAMPLES ||
           fflush(s->native_coarse_iq)) return GLRT_NATIVE_RETENTION_ERROR;
        fprintf(s->journal,"{\"kind\":\"native_coarse_iq\",\"attempt\":%u,\"native_episode\":%u,\"recorded_ns\":%" PRIu64
            ",\"native_sequence\":%u,\"native_start\":%" PRIu64 ",\"native_phase_step\":%u,\"native_phase_seed\":%u,"
            "\"native_reference_phase\":%u,\"native_count\":%u,\"native_fault\":%u,\"first\":%" PRIu64
            ",\"iq_offset\":%u,\"iq_samples\":%u,\"source\":",
            s->attempts,s->restarts,clock_ns(NULL),w[1],wide(w+3),w[6],w[5],w[28],w[7],w[8],first,
            s->paired_copied*PAIR_SAMPLES,PAIR_SAMPLES);
        view(s->journal,&v);fputs("}\n",s->journal);
        if(ferror(s->journal) || fflush(s->journal)) return GLRT_NATIVE_RETENTION_ERROR;
        s->paired_copied++;
    }
    return 0;
}
static int run_native_feedback(struct live *s)
{
    struct glrt_tracking_trend native;
    struct glrt_tracking_batch batch;
    struct glrt_tracking_job job;
    char raw[4096];uint32_t words[24];uint64_t earliest;
    double slope;int rc,n,pair_result=0;
    struct glrt_native_ports ports={s,paired_read,paired_write,paired_retain,paired_clock};
    uint32_t frame=s->worker.trace.frame;
    s->native_clean_loss=0;
    if(glrt_tracking_trend_from_coarse(&s->worker.live.core.trend,s->rate,frame,1500,&native)) return -1;
    n=s->native.read(s->native.context,"tracking_snapshot",raw,sizeof(raw));
    if(n<=0 || (size_t)n>sizeof(raw)) return GLRT_NATIVE_IO_ERROR;
    if(s->native.retain(s->native.context,"snapshot",raw,(size_t)n)) return GLRT_NATIVE_RETENTION_ERROR;
    if(glrt_tracking_snapshot_parse(raw,(size_t)n,words) || words[20]!=s->rate ||
       words[2]!=s->epoch || (words[5]&48)!=48 || words[6] || words[7] ||
       words[18] || words[19] || !glrt_tracking_snapshot_drained(words)) return GLRT_NATIVE_SOURCE_LOST;
    if(wide(words+3)>UINT64_MAX-s->rate/200) return GLRT_NATIVE_DEADLINE;
    earliest=wide(words+3)+s->rate/200;
    /* Publication can lag the live native clock by a refill interval. Choose
     * a fresh batch from the SAME supported history and its existing horizon;
     * the controller still rereads hardware after descriptor retention. */
    for(;frame<=native.history.last_supported+25;frame++) {
        if(!glrt_tracking_trend_batch(&native,frame,8,s->attempts,0,&batch,&slope) &&
           !glrt_tracking_prediction(&batch,0,&job) && job.start>=earliest) break;
    }
    if(frame>native.history.last_supported+25) return GLRT_NATIVE_DEADLINE;
    if(glrt_tracking_controller_init_handoff(&s->controller,&ports,&batch,&native,frame,1500,3)) return -1;
    s->native_runs++;
    do {
        struct timespec pause={0,100000};
        if(cancelled(s)) glrt_native_controller_request_stop(&s->controller);
        rc=glrt_native_controller_tick(&s->controller);
        if(!pair_result) pair_result=paired_copy(s);
        if(pair_result) glrt_native_controller_request_stop(&s->controller);
        if(rc==GLRT_NATIVE_RUNNING) nanosleep(&pause,NULL);
    } while(rc==GLRT_NATIVE_RUNNING);
    {
        uint64_t deadline=clock_ns(NULL)+UINT64_C(100000000);
        while(!pair_result && s->paired_copied<s->paired_queued) {
            if(cancelled(s) || clock_ns(NULL)>=deadline) { pair_result=GLRT_NATIVE_DEADLINE;break; }
            pair_result=paired_copy(s);
            if(!pair_result && s->paired_copied<s->paired_queued && pause_worker(s))
                pair_result=GLRT_NATIVE_IO_ERROR;
        }
    }
    /* Local initialization is only a proposal; count a handoff after at least
     * one descriptor write completed. Native support still needs real heads. */
    s->handoffs+=s->controller.configured!=0;
    s->native_results+=s->controller.sequence;
    s->native_completed_runs+=rc==0 && !s->controller.stopping && s->controller.sequence==1500;
    s->native_clean_loss=rc==GLRT_NATIVE_ACQUISITION_LOST && s->controller.done &&
        s->controller.clearing && s->controller.failure==GLRT_NATIVE_ACQUISITION_LOST &&
        s->controller.sequence && s->controller.sequence==s->controller.configured &&
        !pair_result && s->paired_copied==s->paired_queued;
    fprintf(s->journal,"{\"kind\":\"native_terminal\",\"attempt\":%u,\"native_episode\":%u,\"epoch\":%u,\"result\":%d,\"configured\":%u,\"retained_popped\":%u,"
        "\"paired_result\":%d,\"paired_queued\":%u,\"paired_copied\":%u}\n",
        s->attempts,s->restarts,s->epoch,rc,s->controller.configured,s->controller.sequence,pair_result,
        s->paired_queued,s->paired_copied);
    return ferror(s->journal) || fflush(s->journal) ? -1 : pair_result ? pair_result : rc;
}
static int run_feedback(struct live *s)
{
    int rc,observer_result=start_observer(s);
    if(observer_result) return observer_result;
    /* Thread creation and start retention precede the native freshness read.
     * Do not spend the native admission lead on observer initialization. Every
     * native return, including failed preflight, now passes through this join. */
    rc=run_native_feedback(s);
    observer_result=join_observer(s);
    if(observer_result || s->observer_started) s->native_clean_loss=0;
    fprintf(s->journal,"{\"kind\":\"observer_join\",\"attempt\":%u,\"episode\":%u,\"epoch\":%u,"
        "\"native_result\":%d,\"observer_result\":%d,\"observer_status\":%d,\"observer_joined\":%d}\n",
        s->attempts,s->restarts,s->epoch,rc,observer_result,s->observer_result,!s->observer_started);
    return ferror(s->journal) || fflush(s->journal) ? GLRT_NATIVE_RETENTION_ERROR : observer_result ? observer_result : rc;
}
static void *worker_thread(void *pointer)
{
    struct live *s=pointer;int result=0;
    while(s->attempts<s->attempt_limit) {
        struct glrt_tracking_iq_view v;
        struct glrt_cpu_candidate candidate;
        struct glrt_tracking_worker_config cfg={.owner=&s->owner,.references=s->refs,.fft=fft,.fft_context=s,
            .ports={s,clock_ns,cancelled,pause_worker,retain},.wall_budget_ns=UINT64_C(3000000000),
            .maximum_seed_age=2500000,.lead_samples=12500};
        uint64_t started=clock_ns(NULL),scan_done;int rc;
        if(cancelled(s)) break;
        s->attempts++;
        if(glrt_tracking_iq_owner_copy(&s->owner,s->epoch,0,NULL,0,&v) || v.closed || !v.valid ||
           v.end-v.first<14000) { result=-1;break; }
        candidate=(struct glrt_cpu_candidate){.window_start=v.end-14000,.epoch=s->epoch};
        if(glrt_tracking_iq_owner_copy(&s->owner,s->epoch,candidate.window_start,s->scan_iq,14000,&v) || v.closed)
            { result=-1;break; }
        if(scan(s)) { result=cancelled(s) ? GLRT_WORKER_CANCELLED : -1;break; }
        scan_done=clock_ns(NULL);
        if(retain_scan(s)) { result=GLRT_WORKER_RETENTION;break; }
        fprintf(s->journal,"{\"kind\":\"scan\",\"attempt\":%u,\"window_start\":%" PRIu64
            ",\"epoch\":%u,\"started_ns\":%" PRIu64 ",\"completed_ns\":%" PRIu64 ",\"source\":",
            s->attempts,candidate.window_start,s->epoch,started,scan_done);view(s->journal,&v);
        if(s->selected_iq) fprintf(s->journal,",\"scan_iq_offset\":%" PRIu64 ",\"scan_iq_samples\":14000",s->scan_iq_samples-14000);
        fputs(",\"peaks\":[",s->journal);
        for(unsigned n=0;n<s->coarse.count;n++) fprintf(s->journal,"%s[%u,%u,%u]",n ? "," : "",
            s->coarse.peaks[n].epoch,s->coarse.peaks[n].frequency,s->coarse.peaks[n].score);
        fputs("]}\n",s->journal);
        if(ferror(s->journal) || fflush(s->journal) ||
           fwrite(s->coarse.grid,sizeof(s->coarse.grid),1,s->grids)!=1 || fflush(s->grids)) { result=-1;break; }
        if(!s->coarse.count) continue;
        {
            double scores[8];unsigned selected;
            uint64_t rank_started=clock_ns(NULL);
            if(rank_candidates(s,scores,&selected)) { result=cancelled(s) ? GLRT_WORKER_CANCELLED : -1;break; }
            fprintf(s->journal,"{\"kind\":\"candidate_order\",\"attempt\":%u,\"selected_rank\":%u,"
                "\"started_ns\":%" PRIu64 ",\"completed_ns\":%" PRIu64 ",\"single_pilot_power\":[",
                s->attempts,selected,rank_started,clock_ns(NULL));
            for(unsigned n=0;n<s->coarse.count;n++) fprintf(s->journal,"%s%.17g",n ? "," : "",scores[n]);
            fputs("]}\n",s->journal);
            if(ferror(s->journal) || fflush(s->journal)) { result=-1;break; }
            candidate.peak=s->coarse.peaks[selected];
        }
        if(candidate.window_start>UINT64_MAX-5000000) { result=-1;break; }
        cfg.source_deadline=candidate.window_start+5000000;
        /* A fast scanner can finish before four complete repeats exist.
         * Wait for real retained samples; never manufacture startup history. */
        while(!cancelled(s)) {
            if(glrt_tracking_iq_owner_copy(&s->owner,s->epoch,0,NULL,0,&v) || v.closed || !v.valid)
                { result=GLRT_WORKER_SOURCE;break; }
            if(v.end>=candidate.window_start+17000) break;
            if(pause_worker(s)) { result=GLRT_WORKER_PORT;break; }
        }
        if(result || cancelled(s)) break;
        rc=glrt_tracking_worker_run_cpu(&s->worker,&cfg,&candidate);
        fprintf(s->journal,"{\"kind\":\"worker_terminal\",\"attempt\":%u,\"status\":%d,\"completed_ns\":%" PRIu64
            ",\"retained_past\":%u,\"supported_history\":%u,\"fft_calls\":%u,\"source\":",
            s->attempts,rc,clock_ns(NULL),s->worker.retained_past,s->worker.live.core.trend.history.count,s->worker.fft_calls);
        view(s->journal,&s->worker.checked_source);fputs("}\n",s->journal);
        if(ferror(s->journal) || fflush(s->journal)) { result=-1;break; }
        if(rc==GLRT_WORKER_READY) { result=run_feedback(s);break; }
        if(rc==GLRT_WORKER_RETENTION || rc==GLRT_WORKER_PORT || rc==GLRT_WORKER_INVALID || rc==GLRT_WORKER_SOURCE)
            { result=rc;break; }
    }
    if(pthread_mutex_lock(&s->mutex)) return (void *)(uintptr_t)1;
    s->result=result;s->done=1;
    return (void *)(uintptr_t)(pthread_mutex_unlock(&s->mutex)!=0);
}
/* Caller has joined the worker and set started=0. No owner may be destroyed
 * while a worker can still reference it. Retry only the controller's clean
 * acquisition loss, not another component's numerically equal error code.
 * A negative result leaves the old owner intact for ordinary failure cleanup. */
static int restart_owner(struct live *s,FILE *capture_journal)
{
    char raw[4096];uint32_t w[24];int n;
    if(s->visit_mode || s->started || s->observer_started || !s->done || !s->selected_iq || !s->native_clean_loss ||
       s->result!=GLRT_NATIVE_ACQUISITION_LOST || s->restarts>=RESTART_LIMIT ||
       s->attempts>=s->attempt_limit || cancelled(s)) return 0;
    n=s->native.read(s->native.context,"tracking_snapshot",raw,sizeof(raw));
    if(n<=0 || (size_t)n>sizeof(raw)) return GLRT_NATIVE_IO_ERROR;
    if(fprintf(capture_journal,"tracking_restart_snapshot %.*s\n",n,raw)<0 ||
       fflush(capture_journal)) return GLRT_NATIVE_RETENTION_ERROR;
    if(glrt_tracking_snapshot_parse(raw,(size_t)n,w) || w[2]!=s->epoch || w[20]!=s->rate ||
       (w[5]&48)!=32 || w[6] || w[7] || w[18] || w[19] || !glrt_tracking_snapshot_drained(w))
        return GLRT_NATIVE_SOURCE_LOST;
    fprintf(s->journal,"{\"kind\":\"reacquisition\",\"previous_epoch\":%u,\"native_episode\":%u,"
        "\"attempts_used\":%u,\"attempt_limit\":%u,\"deadline_ns\":%" PRIu64 "}\n",
        s->epoch,s->restarts+1,s->attempts,s->attempt_limit,s->deadline_ns);
    if(ferror(s->journal) || fflush(s->journal)) return GLRT_NATIVE_RETENTION_ERROR;
    if(glrt_tracking_iq_owner_close(&s->owner,0) || glrt_tracking_iq_owner_destroy(&s->owner))
        return GLRT_NATIVE_SOURCE_LOST;
    s->restarts++;s->done=0;s->stop=0;s->result=0;s->native_clean_loss=0;
    s->paired_episode_first=s->paired_queued;
    memset(&s->controller,0,sizeof(s->controller));
    return 1;
}
/* Called after a real refill, with the old worker joined and GLT1 drained.
 * Native journals contain one controller lifecycle each; source binding is
 * retained in the capture journal, never appended after a native final. */
static int rebase_source(struct live *s,FILE *journal,uint32_t visit,uint64_t *boundary)
{
    char raw[4096];uint32_t w[24];int n;
    if(s->epoch==UINT32_MAX || s->native.write(s->native.context,"tracking_command","16\n",3)!=3)
        return -1;
    n=s->native.read(s->native.context,"tracking_snapshot",raw,sizeof(raw));
    if(n<=0 || (size_t)n>sizeof(raw) ||
       fprintf(journal,"tracking_snapshot %.*s\n",n,raw)<0 || fflush(journal)) return -1;
    if(glrt_tracking_snapshot_parse(raw,(size_t)n,w) || !w[2] ||
       (s->epoch && w[2]!=s->epoch+1) || (w[5]&48)!=48 || w[6] || w[7] ||
       w[18] || w[19] || w[20]!=s->rate || !glrt_tracking_snapshot_drained(w)) return -1;
    s->epoch=w[2];*boundary=wide(w+3)/(s->rate/2500000)+1;
    return fprintf(journal,"epoch_binding %u %u %" PRIu64 " %" PRIu64 "\n",
        visit,s->epoch,wide(w+3),*boundary)>0 && !fflush(journal) ? 0 : -1;
}
static int attr(struct iio_device *d,const char *key,char text[4096],FILE *journal)
{
    ssize_t n=iio_device_attr_read(d,key,text,4096);
    if(n<=0 || n>=4096) return -1;
    if(!text[n-1]) n--;
    if(memchr(text,0,(size_t)n)) return -1;
    text[n]=0;
    if(journal && (fprintf(journal,"%s %s\n",key,text)<0 || fflush(journal))) return -1;
    return (int)n;
}
static int is_attr(struct iio_device *d,const char *key,const char *expected)
{
    char text[4096];int n=attr(d,key,text,NULL);
    while(n>0 && (text[n-1]=='\n' || text[n-1]=='\r')) text[--n]=0;
    return n>0 && !strcmp(text,expected);
}
static int snapshot(struct iio_device *d,uint32_t w[24],FILE *journal)
{
    char text[4096];int n=attr(d,"tracking_snapshot",text,journal);
    return n>0 ? glrt_tracking_snapshot_parse(text,(size_t)n,w) : -1;
}
static int load(const char *path,void *out,size_t bytes)
{
    FILE *f=fopen(path,"rb");int bad;
    if(!f) return -1;
    bad=fread(out,1,bytes,f)!=bytes || fgetc(f)!=EOF;
    return fclose(f) || bad ? -1 : 0;
}
static int open_native_episode(struct live *s,struct glrt_native_posix *p,
    const char *device,const char *directory)
{
    char path[PATH_MAX];int n;
    if(p->device!=-1 || p->journal!=-1 || s->restarts>RESTART_LIMIT) return -1;
    n=s->restarts ? snprintf(path,sizeof(path),"%s/native-%u.journal",directory,s->restarts) :
        snprintf(path,sizeof(path),"%s/native.journal",directory);
    return n>0 && (size_t)n<sizeof(path) ?
        glrt_native_posix_open(p,&s->native,device,path,8U*1024U*1024U) : -1;
}
#define LIVE_VISIT_CLEAN_LOSS_EXIT 3
static int live_visit_clean_loss(const struct live *s,int worker_complete)
{
    return s && worker_complete && s->done && !s->started && !s->observer_started &&
        !interrupted && !s->stop && s->result==GLRT_NATIVE_ACQUISITION_LOST && s->native_clean_loss;
}
static int live_probe_run(int argc,char **argv,int visit_mode)
{
    struct live *s=NULL;
    struct iio_context *ctx=NULL;struct iio_device *iq=NULL,*phy=NULL;struct iio_buffer *buffer=NULL;
    struct glrt_native_posix posix={.device=-1,.journal=-1};
    struct glrt_capture_snapshot capture;
    struct glrt_iq_tracking_source source;
    struct sigaction action={0};
    struct dwell_limits limits;
    fftw_complex *fft_storage=NULL;int16_t *ring=NULL;
    FILE *journal=NULL,*samples=NULL;
    uint32_t rate=0,visit=9122201,w[24],block=0;
    uint64_t first=0,now=0,boundary=0,max_refill_ns=0,previous=0,published=0;
    char text[4096],label[80],path[PATH_MAX],resolved[PATH_MAX];
    int n,rc=1,mutex=0,owned=0,rebased=0,joined=1,worker_complete=0,visit_loss=0;
    uint32_t completed_refills=0;
    const char *stage="arguments";
#define NEED(x,name) do { stage=name; if(!(x)) goto done; } while(0)
    if((argc!=6 && argc!=7) || (strcmp(argv[1],"30000000") && strcmp(argv[1],"60000000")) ||
       dwell_limits(argc==7 ? argv[6] : NULL,&limits)) {
        fprintf(stderr,"usage: %s 30000000|60000000 SERIAL BANK REFERENCES NEW_OUTPUT_DIRECTORY [1536|4096|45000|1536-selected]\n",argv[0]);return 2;
    }
    rate=(uint32_t)strtoul(argv[1],NULL,10);
    action.sa_handler=signal_stop;sigemptyset(&action.sa_mask);
    NEED(!sigaction(SIGALRM,&action,NULL) && !sigaction(SIGINT,&action,NULL) && !sigaction(SIGTERM,&action,NULL),"signals");
    alarm(limits.alarm_seconds);
    NEED((s=calloc(1,sizeof(*s))) && (ring=malloc(RING*4U)),"storage");
    s->rate=rate;s->attempt_limit=limits.attempts;s->selected_iq=limits.selected_iq;s->visit_mode=visit_mode;
    NEED(!pthread_mutex_init(&s->mutex,NULL),"mutex");mutex=1;
    NEED(!load(argv[3],s->bank,sizeof(s->bank)) && !load(argv[4],s->refs,sizeof(s->refs)),"reference_files");
    NEED((fft_storage=fftw_malloc(GLRT_RESOLVER_FFT*sizeof(*fft_storage)))!=NULL,"fft_storage");
    s->fft=fftw_plan_dft_1d(GLRT_RESOLVER_FFT,fft_storage,fft_storage,FFTW_FORWARD,FFTW_ESTIMATE|FFTW_UNALIGNED);
    NEED(s->fft!=NULL,"fft_plan");
    /* Directory is created by the operator; every evidence file is new. */
#define FILE_NEW(field,name,mode) do { NEED(snprintf(path,sizeof(path),"%s/%s",argv[5],name)>0,"path"); NEED((field=fopen(path,mode))!=NULL,"new_evidence"); } while(0)
    FILE_NEW(journal,"capture.txt","wx");
    if(s->selected_iq) { FILE_NEW(s->scan_samples,"scan.iq.ci16","wbx"); }
    else { FILE_NEW(samples,"iq.ci16","wbx"); }
    FILE_NEW(s->journal,"worker.jsonl","wx");FILE_NEW(s->worker_iq,"worker.iq.ci16","wbx");FILE_NEW(s->grids,"grids.u32","wbx");
    FILE_NEW(s->native_coarse_iq,"native.coarse.ci16","wbx");
    FILE_NEW(s->observer_journal,"observer.jsonl","wx");FILE_NEW(s->observer_iq,"observer.iq.ci16","wbx");
    NEED((ctx=iio_create_local_context())!=NULL,"local_context");
    snprintf(label,sizeof(label),"glrt-iq-tracking-r%u-v1",rate);
    NEED(iio_context_get_attr_value(ctx,"hw_serial") && !strcmp(iio_context_get_attr_value(ctx,"hw_serial"),argv[2]) &&
         iio_context_get_attr_value(ctx,"fw_version") && !strcmp(iio_context_get_attr_value(ctx,"fw_version"),label),"identity");
    NEED(!iio_context_set_timeout(ctx,2000),"timeout");
    iq=iio_context_find_device(ctx,"starlink-glrt-iq");phy=iio_context_find_device(ctx,"ad9361-phy");
    NEED(iq && phy && !iio_context_find_device(ctx,"starlink-glrt-events"),"inventory");
    NEED(is_attr(iq,"capture_abi","GLI1-1.0-upper-only") && is_attr(iq,"tracking_abi","GLT1-1.0"),"abi");
    {
        long long actual,tx;
        struct iio_channel *rx=iio_device_find_channel(phy,"voltage0",false),*lo=iio_device_find_channel(phy,"altvoltage1",true);
        NEED(rx && lo && !iio_channel_attr_read_longlong(rx,"sampling_frequency",&actual) &&
             !iio_channel_attr_read_longlong(lo,"powerdown",&tx) && actual==rate && tx==1,"rx_clock_tx_idle");
    }
    NEED(!snapshot(iq,w,journal) && glrt_tracking_snapshot_drained(w) && !w[6],"initial_tracking_idle");
    NEED(iio_device_get_id(iq) && snprintf(path,sizeof(path),"/sys/bus/iio/devices/%s",iio_device_get_id(iq))>0 &&
         realpath(path,resolved),"sysfs_device");
    NEED(!open_native_episode(s,&posix,resolved,argv[5]),"native_ports");
    NEED(iio_device_get_channels_count(iq)==2,"scan_count");
    for(unsigned k=0;k<2;k++) {
        struct iio_channel *ch=iio_device_get_channel(iq,k);
        const struct iio_data_format *f=iio_channel_get_data_format(ch);
        NEED(iio_channel_is_scan_element(ch) && !iio_channel_is_output(ch) && iio_channel_get_index(ch)==(long)k &&
             f && f->bits==16 && f->length==16 && f->is_signed && !f->is_be && !f->shift && !f->with_scale && f->repeat==1,"scan_format");
        iio_channel_enable(ch);
    }
    NEED(iio_device_attr_write_longlong(iq,"capture_visit_id",visit)==0 &&
         iio_device_attr_write_longlong(iq,"capture_sample_limit",CHUNK*limits.blocks)==0 &&
         iio_device_set_kernel_buffers_count(iq,4)==0,"capture_setup");
    NEED((buffer=iio_device_create_buffer(iq,CHUNK,false))!=NULL,"start");
    n=attr(iq,"capture_baseline_snapshot",text,journal);
    NEED(n>0 && !glrt_iq_tracking_snapshot_parse(text,(size_t)n,&capture) &&
         !glrt_iq_tracking_source_begin(&source,visit,CHUNK*limits.blocks,&capture),"baseline");
    s->deadline_ns=clock_ns(NULL)+limits.worker_ns;previous=clock_ns(NULL);
    for(block=0;block<limits.blocks;block++) {
        ssize_t bytes;uint64_t stamped,elapsed;size_t skip=0;
        NEED(!interrupted,"wall_deadline");
        bytes=iio_buffer_refill(buffer);stamped=clock_ns(NULL);elapsed=stamped-previous;previous=stamped;
        if(elapsed>max_refill_ns) max_refill_ns=elapsed;
        NEED(bytes==4*CHUNK && iio_buffer_step(buffer)==4 &&
             (char *)iio_buffer_end(buffer)-(char *)iio_buffer_start(buffer)==bytes,"refill");
        n=attr(iq,"capture_snapshot",text,journal);
        NEED(n>0 && !glrt_iq_tracking_snapshot_parse(text,(size_t)n,&capture) &&
             !glrt_iq_tracking_source_take(&source,&capture,CHUNK,&first,&now),"contiguous_source");
        completed_refills++;
        NEED(!samples || fwrite(iio_buffer_start(buffer),1,(size_t)bytes,samples)==(size_t)bytes,"retain_iq");
        if(!rebased) {
            rebased=1;
            NEED(!rebase_source(s,journal,visit,&boundary),"rebase_source");
        }
        if(first+CHUNK<=boundary) continue;
        if(first<boundary) skip=(size_t)(boundary-first);
        if(!owned) {
            NEED(!glrt_tracking_iq_owner_init(&s->owner,ring,RING,s->epoch,first+skip),"owner_init");owned=1;
        }
        NEED(!glrt_tracking_iq_owner_publish(&s->owner,s->epoch,first+skip,
            (const int16_t *)iio_buffer_start(buffer)+2*skip,CHUNK-skip,now,clock_ns(NULL)),"owner_publish");
        published+=CHUNK-skip;
        if(!s->started && published>=14000) {
            NEED(!pthread_create(&s->thread,NULL,worker_thread,s),"worker_start");s->started=1;
        }
        n=capture_worker_done(s);NEED(n>=0,"worker_state");
        if(n) {
            void *result=NULL;
            if(pthread_join(s->thread,&result)) { joined=0;NEED(0,"worker_join"); }
            s->started=0;
            NEED(!result && s->done,"worker_terminal");
            n=restart_owner(s,journal);NEED(n>=0,"reacquisition_admission");
            if(n) {
                owned=0;
                NEED(!glrt_native_posix_close(&posix),"close_native_episode");
                NEED(!open_native_episode(s,&posix,resolved,argv[5]),"next_native_episode");
                rebased=0;published=0;boundary=0;
            } else { worker_complete=1;block++;break; }
        }
    }
    if(worker_complete) { stage="worker_complete"; }
    else { NEED(wide(capture.words+4)==CHUNK*limits.blocks && wide(capture.words+6)==CHUNK*limits.blocks && !(capture.words[19]&3),"finite_source_complete"); }
    visit_loss=visit_mode && live_visit_clean_loss(s,worker_complete);
    rc=worker_complete && s->result && !visit_loss ? 1 : 0;
done:
    if(s && s->started) {
        void *result=NULL;
        if(pthread_mutex_lock(&s->mutex)) rc=1;
        else { s->stop=1;if(pthread_mutex_unlock(&s->mutex)) rc=1; }
        if(owned && glrt_tracking_iq_owner_close(&s->owner,rc!=0)) rc=1;
        if(pthread_join(s->thread,&result)) { joined=0;rc=1; }
        else if(result || !s->done || s->result) rc=1;
    }
    if(buffer) { iio_buffer_destroy(buffer);buffer=NULL; }
    if(iq && journal) {
        n=attr(iq,"capture_final_snapshot",text,journal);
        if(n<0) rc=1;
        else if(worker_complete && (glrt_iq_tracking_snapshot_parse(text,(size_t)n,&capture) ||
                !capture_early_final(&capture,completed_refills,limits.blocks))) rc=1;
        if(attr(iq,"capture_final_extension_snapshot",text,journal)<0) rc=1;
        if(rebased && joined) {
            /* Do not clear unread heads after a failed controller recovery. */
            if(snapshot(iq,w,journal) || !glrt_tracking_snapshot_drained(w)) rc=1;
            else if(iio_device_attr_write_longlong(iq,"tracking_command",4)<0 || snapshot(iq,w,journal) ||
                    !glrt_tracking_snapshot_drained(w) || (w[5]&16) || w[6] || w[7]) rc=1;
        }
    }
    if(!joined || (s && s->observer_started)) _exit(2); /* Keep all worker-reachable storage alive until process exit. */
    if(owned) { if(glrt_tracking_iq_owner_close(&s->owner,0) || glrt_tracking_iq_owner_destroy(&s->owner)) rc=1; }
    if(glrt_native_posix_close(&posix)) rc=1;
    if(ctx) iio_context_destroy(ctx);
    if(samples && fclose(samples)) rc=1;
    if(journal && fclose(journal)) rc=1;
    if(s) {
        if(s->journal && fclose(s->journal)) rc=1;
        if(s->worker_iq && fclose(s->worker_iq)) rc=1;
        if(s->grids && fclose(s->grids)) rc=1;
        if(s->scan_samples && fclose(s->scan_samples)) rc=1;
        if(s->native_coarse_iq && fclose(s->native_coarse_iq)) rc=1;
        if(s->observer_journal && fclose(s->observer_journal)) rc=1;
        if(s->observer_iq && fclose(s->observer_iq)) rc=1;
        if(s->fft) fftw_destroy_plan(s->fft);
        if(mutex && pthread_mutex_destroy(&s->mutex)) rc=1;
    }
    fftw_free(fft_storage);free(ring);alarm(0);
    /* The typed visit result is available only after every cleanup and
     * evidence close succeeded. Standalone probe exit semantics are unchanged. */
    if(visit_loss && !rc) rc=interrupted ? 1 : LIVE_VISIT_CLEAN_LOSS_EXIT;
    printf("{\"scope\":\"bounded_live_cpu_acquisition_native_feedback\",\"rate\":%u,\"status\":%d,"
        "\"stage\":\"%s\",\"blocks\":%u,\"attempts\":%u,\"handoffs\":%u,\"native_results\":%u,\"max_refill_gap_ns\":%" PRIu64
        ",\"reacquisitions\":%u,\"native_runs\":%u,\"native_completed_runs\":%u"
        ",\"retention_mode\":\"%s\",\"completed_refills\":%u,\"worker_complete\":%d,\"retained_scan_samples\":%" PRIu64 "}\n",
        rate,rc,stage,block,s ? s->attempts : 0,s ? s->handoffs : 0,s ? s->native_results : 0,max_refill_ns,
        s ? s->restarts : 0,s ? s->native_runs : 0,s ? s->native_completed_runs : 0,
        s && s->selected_iq ? "selected_windows" : "full",completed_refills,worker_complete,s ? s->scan_iq_samples : 0);
    free(s);return rc;
}
int main(int argc,char **argv) { return live_probe_run(argc,argv,0); }
