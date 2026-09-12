/* SPDX-License-Identifier: GPL-2.0 */
/* Saved physical IQ only. Receiver time is a frozen retained snapshot, so this
 * measures numerical throughput/support, never live freshness or admission. */
#define _POSIX_C_SOURCE 200809L
#include "glrt_tracking_worker.h"
#include <fftw3.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define RETAINED 447851U
#define INPUT 2621440U
struct context { fftw_plan fft; uint64_t deadline; unsigned case_id; };
static uint64_t clock_ns(void *unused)
{
    struct timespec t;(void)unused;
    if(clock_gettime(CLOCK_MONOTONIC,&t)) return 0;
    return (uint64_t)t.tv_sec*UINT64_C(1000000000)+(uint64_t)t.tv_nsec;
}
static int cancelled(void *context)
{ uint64_t now=clock_ns(NULL);return !now || now>=((struct context *)context)->deadline; }
static int no_more_iq(void *context) { (void)context;return -1; }
static int fft(void *context,double (*bins)[2],size_t count)
{
    if(count!=GLRT_RESOLVER_FFT) return -1;
    fftw_execute_dft(((struct context *)context)->fft,bins,bins);return 0;
}
static int retain(void *context,enum glrt_tracking_worker_record kind,const struct glrt_tracking_worker *w)
{
    struct context *ctx=context;
    printf("{\"case\":%u,\"kind\":%d,\"elapsed_ns\":%" PRIu64,ctx->case_id,kind,clock_ns(NULL)-w->started_ns);
    if(kind==GLRT_WORKER_SEED_IQ) {
        const struct glrt_cpu_seed *p=&w->cpu_seed;
        printf(",\"first\":%" PRIu64 ",\"start\":%" PRIu64 ",\"fraction\":%u,\"first_repeat\":%u,"
               "\"source_now\":%" PRIu64 ",\"starts\":[%zu,%zu,%zu,%zu]",
               p->first,p->start,p->fraction,p->first_repeat,p->copied.source_now,
               p->starts[0],p->starts[1],p->starts[2],p->starts[3]);
    } else if(kind==GLRT_WORKER_RESOLVED) {
        printf(",\"best_shift\":%d,\"cfo_hz\":%.17g,\"coherence\":%.17g,\"hypotheses\":[",
               w->resolved.best.shift,w->resolved.best.cfo_hz,w->resolved.best.power_coherence);
        for(unsigned n=0;n<17;n++) {
            const struct glrt_resolver_peak *p=&w->resolved.hypotheses[n];
            printf("%s[%d,%.17g,%.17g]",n ? "," : "",p->shift,p->cfo_hz,p->power_coherence);
        }
        printf("]");
    } else if(kind==GLRT_WORKER_PAST) {
        const struct glrt_tracking_bootstrap_trace *t=&w->trace;
        printf(",\"frame\":%u,\"first\":%" PRIu64 ",\"phase_step\":%u,\"reference_phase\":%u,"
               "\"accepted\":%d,\"rejection\":%u,\"coherence\":%.17g,\"cfo_hz\":%.17g,\"moments\":[",
               t->frame,t->job.start,t->job.phase_step,t->job.reference_phase,t->accepted,
               t->estimate.rejection,t->estimate.coherence,t->estimate.cfo_hz);
        for(unsigned n=0;n<16;n++) printf("%s%u",n ? "," : "",t->moments.words[n]);
        printf("]");
    } else if(kind==GLRT_WORKER_HANDOFF) {
        printf(",\"frame\":%u,\"start\":%" PRIu64 ",\"history_count\":%u",
               w->trace.frame,w->trace.job.start,w->live.core.trend.history.count);
    } else return -1;
    return puts("}")<0 || fflush(stdout) ? -1 : 0;
}
struct part {
    struct glrt_cpu_coarse_workspace *work;
    const int16_t *iq;
    const int16_t (*bank)[11][11][2];
    struct context *context;
    unsigned begin,end;
    uint32_t completed;
    int result;
};
static void *partition(void *pointer)
{
    struct part *p=pointer;
    p->result=glrt_cpu_coarse_grid(p->work->grid,p->iq,p->bank,p->begin,p->end,
                                 &p->completed,cancelled,p->context);
    return NULL;
}
static int search(struct glrt_cpu_coarse_workspace *w,const int16_t *iq,
                  const int16_t bank[12][11][11][2],struct context *ctx)
{
    pthread_t child;
    struct part parts[2]={{w,iq,bank,ctx,0,1666,0,-1},{w,iq,bank,ctx,1666,3333,0,-1}};
    memset(w,0,sizeof(*w));
    if(pthread_create(&child,NULL,partition,&parts[0])) return -1;
    partition(&parts[1]);
    /* Standalone saved-IQ process: never release a writer's input on join error. */
    if(pthread_join(child,NULL)) _exit(2);
    if(parts[0].result || parts[1].result) return -1;
    w->completed_epochs=parts[0].completed+parts[1].completed;
    return glrt_cpu_coarse_select(w,cancelled,ctx);
}
static int load(const char *path,void *data,size_t bytes)
{
    FILE *f=fopen(path,"rb");int bad;
    if(!f) return -1;
    bad=fread(data,1,bytes,f)!=bytes || fgetc(f)!=EOF;
    return fclose(f) || bad ? -1 : 0;
}
int main(int argc,char **argv)
{
    struct glrt_tracking_worker *worker=calloc(1,sizeof(*worker));
    struct glrt_cpu_coarse_workspace *coarse=calloc(1,sizeof(*coarse));
    int16_t *iq=malloc(INPUT*4U),*storage=malloc(RETAINED*4U),*refs=malloc(105600);
    int16_t bank[12][11][11][2];
    struct context ctx={0};FILE *grid;
    fftw_complex *fft_storage;
    alarm(30);
    if(argc!=5 || !worker || !coarse || !iq || !storage || !refs ||
       load(argv[1],bank,sizeof(bank)) || load(argv[2],iq,INPUT*4U) ||
       load(argv[4],refs,105600) || !(grid=fopen(argv[3],"wbx")) ||
       !(fft_storage=fftw_malloc(GLRT_RESOLVER_FFT*sizeof(*fft_storage)))) return 2;
    ctx.fft=fftw_plan_dft_1d(GLRT_RESOLVER_FFT,fft_storage,fft_storage,FFTW_FORWARD,FFTW_ESTIMATE|FFTW_UNALIGNED);
    if(!ctx.fft) return 2;
    ctx.deadline=clock_ns(NULL)+UINT64_C(25000000000);
    for(ctx.case_id=0;ctx.case_id<4;ctx.case_id++) {
        uint64_t first=ctx.case_id*500000U,started=clock_ns(NULL),scan_done;
        struct glrt_tracking_iq_owner owner={0};
        struct glrt_cpu_candidate candidate;
        struct glrt_tracking_worker_config cfg={.owner=&owner,.references=refs,.fft=fft,.fft_context=&ctx,
            .ports={&ctx,clock_ns,cancelled,no_more_iq,retain},.source_deadline=first+5000000U,
            .wall_budget_ns=UINT64_C(3000000000),.maximum_seed_age=2500000,.lead_samples=2500};
        int rc;
        if(glrt_tracking_iq_owner_init(&owner,storage,RETAINED,1,first) ||
           glrt_tracking_iq_owner_publish(&owner,1,first,iq+2*first,RETAINED,first+RETAINED,started) ||
           search(coarse,iq+2*first,bank,&ctx) ||
           fwrite(coarse->grid,sizeof(coarse->grid),1,grid)!=1) return 2;
        scan_done=clock_ns(NULL);
        printf("{\"case\":%u,\"kind\":\"scan\",\"first\":%" PRIu64 ",\"milliseconds\":%.9g,\"peaks\":[",
               ctx.case_id,first,(scan_done-started)*1e-6);
        for(unsigned n=0;n<coarse->count;n++) printf("%s[%u,%u,%u]",n ? "," : "",
            coarse->peaks[n].epoch,coarse->peaks[n].frequency,coarse->peaks[n].score);
        printf("]}\n");
        if(!coarse->count) {
            printf("{\"case\":%u,\"kind\":\"terminal\",\"disposition\":\"no_candidate\","
                   "\"worker_result\":0,\"supported_history\":0,\"fft_calls\":0}\n",ctx.case_id);
            if(fflush(stdout) || glrt_tracking_iq_owner_close(&owner,0) ||
               glrt_tracking_iq_owner_destroy(&owner)) return 2;
            continue;
        }
        candidate=(struct glrt_cpu_candidate){first,1,coarse->peaks[0]};
        rc=glrt_tracking_worker_run_cpu(worker,&cfg,&candidate);
        printf("{\"case\":%u,\"kind\":\"terminal\",\"worker_result\":%d,\"scan_ms\":%.9g,"
               "\"worker_ms\":%.9g,\"retained_past\":%u,\"supported_history\":%u,\"fft_calls\":%u,\"waits\":%u}\n",
               ctx.case_id,rc,(scan_done-started)*1e-6,(clock_ns(NULL)-scan_done)*1e-6,
               worker->retained_past,worker->live.core.trend.history.count,worker->fft_calls,worker->waits);
        if(fflush(stdout) || glrt_tracking_iq_owner_close(&owner,0) ||
           glrt_tracking_iq_owner_destroy(&owner)) return 2;
        if(rc!=GLRT_WORKER_READY && rc!=GLRT_WORKER_HISTORY && !(rc==GLRT_WORKER_PORT && worker->waits)) return 1;
    }
    puts("{\"scope\":\"saved_iq_cpu_scan_resolve_catchup\",\"receiver_time\":\"frozen_snapshot\","
         "\"rf_samples\":0,\"live_tracking_qualified\":false}");
    fftw_destroy_plan(ctx.fft);fftw_free(fft_storage);
    free(worker);free(coarse);free(iq);free(storage);free(refs);
    return fclose(grid) || fflush(stdout) ? 2 : 0;
}
