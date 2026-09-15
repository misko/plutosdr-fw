"""Passive measurements retain copied IQ before updating an independent history."""
from pathlib import Path
import subprocess

import numpy as np
import pytest

from tools.generate_glrt_tracking_gram import reference_rows


BENCH = r'''
#include "glrt_tracking_observer.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct context {
    struct glrt_tracking_iq_owner *owner;
    struct glrt_tracking_observer *observer;
    const char *mode;
    const int16_t *input;
    uint64_t now, first;
    unsigned retained;
    int cancelled;
    int advance;
};
static uint64_t clock_ns(void *p) {
    struct context *c=p;uint64_t before=c->now;
    if(c->advance) {
        struct glrt_tracking_iq_view v;int16_t extra[2]={1,2};
        c->advance=0;
        assert(!glrt_tracking_iq_owner_copy(c->owner,3,0,NULL,0,&v));
        assert(!glrt_tracking_iq_owner_publish(c->owner,3,v.end,extra,1,v.source_now+1,before+1));
        c->now=before+2;
    }
    return before;
}
static int cancelled(void *p) { return ((struct context *)p)->cancelled; }
static int retain(void *p,const struct glrt_tracking_observer_trace *t,const int16_t *iq)
{
    struct context *c=p;
    assert(!pthread_mutex_trylock(&c->owner->mutex));
    assert(!pthread_mutex_unlock(&c->owner->mutex));
    assert(c->observer->measurements==c->retained);
    assert(c->observer->trend.history.last_seen<t->frame);
    assert(t->source.epoch==3 && t->source.valid && !t->source.closed);
    assert(t->source.first<=t->job.start && t->job.start+3300<=t->source.end);
    assert(t->moments.count==3300 && t->moments.start==t->job.start);
    assert(!memcmp(iq,c->input+2*(t->job.start-c->first),6600*sizeof(*iq)));
    c->retained++;
    if(!strcmp(c->mode,"retention")) return -1;
    if(!strcmp(c->mode,"close_during_retention")) assert(!glrt_tracking_iq_owner_close(c->owner,0));
    if(!strcmp(c->mode,"cancel_during_retention")) c->cancelled=1;
    if(!strcmp(c->mode,"clock_during_retention")) c->now=1;
    return 0;
}
static void seed(struct glrt_tracking_trend *t,uint64_t anchor,unsigned phase)
{
    struct glrt_native_estimate e={0};
    e.coherence=e.linearized_coherence=.9;
    assert(!glrt_tracking_trend_reset(t,3,2500000));
    for(unsigned n=0;n<8;n++)
        assert(glrt_tracking_trend_observe(t,3,n*9,anchor+n*30000,phase,&e)==1);
}
int main(int argc,char **argv)
{
    assert(argc==3);
    const char *mode=argv[1];
    struct glrt_tracking_iq_owner owner={0};
    struct glrt_tracking_trend original,saved;
    struct glrt_tracking_observer observer;
    struct glrt_tracking_observer_trace trace;
    int16_t refs[52800],scratch[6600];
    uint64_t anchor=!strcmp(mode,"large") ? UINT64_C(0x1000000000000000)+1000 : 1000000;
    uint64_t first=anchor+240000;
    size_t count=400000,capacity=!strcmp(mode,"overwrite") ? 3300 : 500000;
    int16_t *storage=calloc(2*capacity,sizeof(*storage)),*iq=calloc(2*count,sizeof(*iq));
    FILE *f=fopen(argv[2],"rb");assert(f && storage && iq);
    assert(fread(refs,sizeof(refs),1,f)==1 && fgetc(f)==EOF);assert(!fclose(f));
    unsigned phase=!strncmp(mode,"phase",5) ? (unsigned)(mode[5]-'0') : 0;
    seed(&original,anchor,phase);saved=original;
    unsigned maximum=10;
    unsigned cadence=9;
    uint64_t budget=UINT64_C(1000000000),limit=first+5000000,now=1000;
    uint32_t frame=72;
    if(!strcmp(mode,"init_rate")) original.rate=30000000;
    if(!strcmp(mode,"init_history")) original.history.count=7;
    if(!strcmp(mode,"init_frame")) frame=63;
    if(!strcmp(mode,"init_far_frame")) frame=100;
    if(!strcmp(mode,"init_count")) maximum=GLRT_TRACKING_OBSERVER_MAXIMUM+1;
    if(!strcmp(mode,"init_zero_count")) maximum=0;
    if(!strcmp(mode,"init_budget")) budget=GLRT_TRACKING_OBSERVER_MAX_BUDGET_NS+1;
    if(!strcmp(mode,"init_zero_budget")) budget=0;
    if(!strcmp(mode,"init_overflow")) now=UINT64_MAX-10;
    if(!strcmp(mode,"init_source")) limit=first+3299;
    if(!strcmp(mode,"init_long_source")) limit=first+GLRT_TRACKING_OBSERVER_MAX_SOURCE_SPAN+1;
    if(!strcmp(mode,"init_horizon")) {
        assert(glrt_tracking_observer_init_cadence_horizon(&observer,&original,frame,
            cadence,maximum,limit,now,budget,33)==-1);
        assert(observer.status==GLRT_OBSERVER_INVALID);
        free(iq);free(storage);puts("PASS");return 0;
    }
    if(!strncmp(mode,"init_",5)) {
        if(!strncmp(mode,"init_spacing",12)) {
            assert(glrt_tracking_observer_init_cadence(&observer,&original,frame,
                (unsigned)atoi(mode+12),maximum,limit,now,budget)==-1);
            assert(observer.status==GLRT_OBSERVER_INVALID);
            free(iq);free(storage);puts("PASS");return 0;
        }
        assert(glrt_tracking_observer_init(&observer,&original,frame,maximum,limit,now,budget)==-1);
        assert(observer.status==GLRT_OBSERVER_INVALID);
        free(iq);free(storage);puts("PASS");return 0;
    }
    if(!strcmp(mode,"coast_noise") || !strcmp(mode,"coast10_noise")) {
        maximum=40;
        assert(!glrt_tracking_observer_init_cadence_horizon(&observer,&original,frame,
            !strcmp(mode,"coast10_noise") ? 10 : cadence,maximum,limit,now,budget,96));
    } else
        assert(!glrt_tracking_observer_init(&observer,&original,frame,maximum,limit,now,budget));
    assert(!memcmp(&original,&saved,sizeof(saved)));
    struct context c={&owner,&observer,mode,iq,1000,first,0,0,0};
    struct glrt_tracking_observer_ports ports={&c,clock_ns,cancelled,retain};
    assert(!glrt_tracking_iq_owner_init(&owner,storage,capacity,!strcmp(mode,"epoch") ? 4 : 3,first));
    if(strcmp(mode,"noise") && strcmp(mode,"coast_noise") && strcmp(mode,"coast10_noise"))
        for(unsigned k=0;k<10;k++) for(unsigned n=0;n<3300;n++) {
            iq[2*(k*30000+n)]=refs[13200*phase+4*n];iq[2*(k*30000+n)+1]=refs[13200*phase+4*n+1];
        }
    int rc;
    if(!strcmp(mode,"epoch")) {
        assert(glrt_tracking_observer_step(&observer,&owner,refs,scratch,&ports,&trace)==GLRT_OBSERVER_SOURCE);
    } else {
        memset(&trace,0x55,sizeof(trace));
        assert(glrt_tracking_observer_step(&observer,&owner,refs,scratch,&ports,&trace)==GLRT_OBSERVER_WAIT);
        assert(!trace.moments.count && !trace.job.start && !observer.measurements);
        if(!strcmp(mode,"waiting") || !strcmp(mode,"waiting_deadline")) {
            assert(!glrt_tracking_iq_owner_publish(&owner,3,first,iq,3299,first+3300,42));
            for(unsigned n=0;n<3;n++) {
                assert(glrt_tracking_observer_step(&observer,&owner,refs,scratch,&ports,&trace)==GLRT_OBSERVER_WAIT);
                assert(!trace.job.start && !observer.measurements && !c.retained);
            }
            if(!strcmp(mode,"waiting_deadline")) {
                c.now=observer.deadline_ns;
                assert(glrt_tracking_observer_step(&observer,&owner,refs,scratch,&ports,&trace)==GLRT_OBSERVER_DEADLINE);
            }
        } else {
            assert(!glrt_tracking_iq_owner_publish(&owner,3,first,iq,count,first+count+100,42));
            if(!strcmp(mode,"closed")) assert(!glrt_tracking_iq_owner_close(&owner,0));
            if(!strcmp(mode,"lost")) assert(!glrt_tracking_iq_owner_close(&owner,1));
            if(!strcmp(mode,"cancelled")) c.cancelled=1;
            if(!strcmp(mode,"invalid_cancel")) c.cancelled=2;
            if(!strcmp(mode,"deadline")) c.now=observer.deadline_ns;
            if(!strcmp(mode,"clock_regression")) c.now--;
            if(!strcmp(mode,"future_source_clock")) observer.last_ns=c.now=41;
            if(!strcmp(mode,"source_budget")) observer.source_limit=first+count;
            if(!strcmp(mode,"advance_during_guard")) c.advance=1;
            int success=!strcmp(mode,"positive") || !strcmp(mode,"large") ||
                !strncmp(mode,"phase",5) || !strcmp(mode,"advance_during_guard");
            if(success) {
                for(unsigned n=0;n<10;n++) {
                    rc=glrt_tracking_observer_step(&observer,&owner,refs,scratch,&ports,&trace);
                    assert(rc==GLRT_OBSERVER_MEASURED && trace.frame==72+n*9);
                    assert(trace.job.start==first+n*30000 && trace.accepted==1);
                    assert(trace.job.reference_phase==phase);
                    assert(trace.estimate.coherence>.99 && !trace.estimate.rejection);
                    assert(fabs(trace.estimate.delay_correction_s)<1e-8 && fabs(trace.estimate.cfo_hz)<5);
                    assert(observer.measurements==n+1 && c.retained==n+1);
                }
                assert(glrt_tracking_observer_step(&observer,&owner,refs,scratch,&ports,&trace)==GLRT_OBSERVER_DONE);
            } else if(!strcmp(mode,"noise") || !strcmp(mode,"coast_noise") || !strcmp(mode,"coast10_noise")) {
                unsigned jobs=0;
                while((rc=glrt_tracking_observer_step(&observer,&owner,refs,scratch,&ports,&trace))==GLRT_OBSERVER_MEASURED) {
                    assert(!trace.accepted && trace.estimate.rejection);
                    assert(observer.trend.history.last_supported==63);
                    jobs++;
                }
                unsigned expected=!strcmp(mode,"coast10_noise") ? 9 :
                    !strcmp(mode,"coast_noise") ? (cadence==9 ? 10 : 30) :
                    (cadence==9 ? 3 : 8);
                assert(rc==GLRT_OBSERVER_HISTORY && jobs==expected && c.retained==expected);
            } else {
                struct glrt_tracking_trend before=observer.trend;
                rc=glrt_tracking_observer_step(&observer,&owner,refs,scratch,&ports,&trace);
                int expected=GLRT_OBSERVER_SOURCE;
                if(!strcmp(mode,"retention")) expected=GLRT_OBSERVER_RETENTION;
                if(!strcmp(mode,"cancelled") || !strcmp(mode,"cancel_during_retention")) expected=GLRT_OBSERVER_CANCELLED;
                if(!strcmp(mode,"invalid_cancel")) expected=GLRT_OBSERVER_INVALID;
                if(!strcmp(mode,"deadline") || !strcmp(mode,"clock_regression") || !strcmp(mode,"clock_during_retention")) expected=GLRT_OBSERVER_DEADLINE;
                if(!strcmp(mode,"source_budget")) expected=GLRT_OBSERVER_DONE;
                assert(rc==expected && !observer.measurements);
                assert(!memcmp(&before,&observer.trend,sizeof(before)));
                assert(!trace.moments.count && !trace.job.start);
                assert(glrt_tracking_observer_step(&observer,&owner,refs,scratch,&ports,&trace)==expected);
            }
        }
    }
    assert(!memcmp(&original,&saved,sizeof(saved)));
    assert(!glrt_tracking_iq_owner_close(&owner,0));
    assert(!glrt_tracking_iq_owner_destroy(&owner));
    free(iq);free(storage);puts("PASS");return 0;
}
'''


@pytest.fixture(scope="module", params=[9, 3])
def observer_binary(tmp_path_factory, request):
    root = Path(__file__).resolve().parents[2]
    out = tmp_path_factory.mktemp("passive-observer")
    source = BENCH
    if request.param == 3:
        source = source.replace('unsigned cadence=9;', 'unsigned cadence=3;')
        source = source.replace('glrt_tracking_observer_init(', 'glrt_tracking_observer_init_cadence(')
        source = source.replace('frame,maximum,limit,now,budget)', 'frame,3,maximum,limit,now,budget)')
        source = source.replace('k*30000+n', 'k*10000+n')
        source = source.replace('trace.frame==72+n*9', 'trace.frame==72+n*3')
        source = source.replace('trace.job.start==first+n*30000', 'trace.job.start==first+n*10000')
        source = source.replace('jobs==3 && c.retained==3', 'jobs==8 && c.retained==8')
    (out/"test.c").write_text(source)
    sources = ["glrt_tracking_observer.c", "glrt_tracking_iq_owner.c", "glrt_tracking_recent_iq.c",
               "glrt_tracking_iq.c", "glrt_native_trend.c", "glrt_native_schedule.c",
               "glrt_tracking_schedule.c", "glrt_native_solver.c"]
    subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
                    "-I", str(root/"tools"), str(out/"test.c"),
                    *(str(root/"tools"/n) for n in sources), "-lm", "-o", str(out/"test")], check=True)
    bank = root/"hdl/library/starlink_glrt"
    cubic = (bank/"native_cubic_60000000_upper.mem").read_bytes()
    direct = (bank/"native_direct_2500000_phase4_upper_interleaved.mem").read_bytes()
    np.asarray([reference_rows(cubic,direct,2500000,phase) for phase in range(4)],dtype="<i2").tofile(out/"references")
    return out/"test", out/"references"


@pytest.mark.parametrize("mode", [
    "positive", "large", "phase1", "phase2", "phase3", "advance_during_guard",
    "noise", "coast_noise", "coast10_noise", "waiting", "waiting_deadline", "closed", "lost", "epoch",
    "overwrite", "deadline", "clock_regression", "future_source_clock", "source_budget",
    "cancelled", "invalid_cancel", "retention", "close_during_retention", "cancel_during_retention",
    "clock_during_retention", "init_rate", "init_history", "init_frame", "init_far_frame",
    "init_count", "init_zero_count", "init_budget", "init_zero_budget", "init_overflow",
    "init_source", "init_long_source", "init_horizon",
    "init_spacing0", "init_spacing1", "init_spacing2", "init_spacing6",
])
def test_passive_owner_measurements_and_fences(observer_binary, mode):
    binary, references = observer_binary
    p = subprocess.run([str(binary),mode,str(references)],capture_output=True,text=True,timeout=10)
    assert p.returncode == 0 and p.stdout.strip() == "PASS", p.stdout+p.stderr
