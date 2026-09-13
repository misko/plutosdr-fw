"""Two ARM-local visits require verified cleanup and retained transitions."""
from pathlib import Path
import subprocess

import pytest

BENCH=r'''
#include "glrt_tracking_visit.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct test {
    const char *mode;
    int loss;
    struct glrt_visit_state state;
    uint64_t now;
    unsigned inspections,tunes,runs,retained;
};
static uint64_t clock_ns(void *p) { return ((struct test *)p)->now; }
static int cancelled(void *p) {
    struct test *t=p;return !strcmp(t->mode,"cancel") && t->retained;
}
static int inspect(void *p,struct glrt_visit_state *s) {
    struct test *t=p;t->inspections++;
    if(!strcmp(t->mode,"read")) return -1;
    *s=t->state;
    if(!strcmp(t->mode,"busy") || (!strcmp(t->mode,"after_busy") && t->runs)) s->idle=0;
    if(!strcmp(t->mode,"fixed_rf")) s->fixed_rf_valid=0;
    if(!strcmp(t->mode,"wrong_rate")) s->rate=2500000;
    if(!strcmp(t->mode,"between_epoch") && t->inspections==4) s->epoch++;
    return 0;
}
static int tune(void *p,uint64_t hz) {
    struct test *t=p;
    assert(t->retained==t->runs*3+1);t->tunes++;
    if(!strcmp(t->mode,"tune_fail")) return -1;
    t->state.lo_hz=hz-4;t->now+=1000000;
    if(!strcmp(t->mode,"wrong_lo")) t->state.lo_hz+=100;
    if(!strcmp(t->mode,"tune_epoch")) t->state.epoch++;
    if(!strcmp(t->mode,"tune_counter")) t->state.native_latest--;
    return 0;
}
static int run(void *p,unsigned n,uint64_t deadline) {
    struct test *t=p;assert(n==t->runs && t->retained==3*n+2);
    assert(deadline==UINT64_C(60000001000));t->runs++;
    if(strcmp(t->mode,"no_epoch")) t->state.epoch++;
    if(strcmp(t->mode,"no_samples")) t->state.native_latest+=UINT64_C(300000000);
    t->now+=UINT64_C(10000000000);
    if(!strcmp(t->mode,"run_rf")) t->state.lo_hz++;
    if(!strcmp(t->mode,"deadline")) t->now=deadline;
    if(!strcmp(t->mode,"clock_regress")) t->now=999;
    return !strcmp(t->mode,"child_fail") ? -1 :
        t->loss ? GLRT_VISIT_CLEAN_LOSS :
        !strcmp(t->mode,"unknown_result") ? 2 : 0;
}
static int retain(void *p,const char *kind,unsigned n,int result,const struct glrt_visit_state *s) {
    struct test *t=p;(void)s;assert(n==t->retained/3);
    const char *names[]={"before_tune","tuned","after_run"};assert(!strcmp(kind,names[t->retained%3]));
    if(!strcmp(kind,"after_run")) assert(result==(!strcmp(t->mode,"child_fail") ? -1 :
        t->loss ? GLRT_VISIT_CLEAN_LOSS : !strcmp(t->mode,"unknown_result") ? 2 : 0));
    t->retained++;
    return (!strcmp(t->mode,"retention_before") && t->retained==1) ||
        (!strcmp(t->mode,"retention_tuned") && t->retained==2) ||
        (!strcmp(t->mode,"retention_after") && t->retained==3) ? -1 : 0;
}
int main(int argc,char **argv) {
    assert(argc==3);struct test t={0};t.mode=argv[1];t.now=1000;
    if(!strcmp(t.mode,"loss")) { t.loss=1;t.mode="ready"; }
    else if(!strncmp(t.mode,"loss_",5)) { t.loss=1;t.mode+=5; }
    unsigned rate=(unsigned)strtoul(argv[2],NULL,10);
    t.state=(struct glrt_visit_state){1690312496,1000000,rate,3,1,1};
    struct glrt_visit_ports p={&t,clock_ns,cancelled,inspect,tune,run,retain};
    uint64_t frequencies[]={1690312500,1940312500};
    if(!strcmp(t.mode,"lower_edge")) frequencies[1]=1709687500;
    if(!strcmp(t.mode,"duplicate")) frequencies[1]=frequencies[0];
    if(!strcmp(t.mode,"invalid_rate")) rate=2500000;
    if(!strcmp(t.mode,"missing_port")) p.inspect=NULL;
    int rc=glrt_tracking_visit_run(&p,rate,frequencies);
    printf("%d %u %u %u %u\n",rc,t.inspections,t.tunes,t.runs,t.retained);
}
'''


@pytest.fixture(scope='module')
def probe(tmp_path_factory):
    root=Path(__file__).resolve().parents[2];out=tmp_path_factory.mktemp('visit')
    (out/'bench.c').write_text(BENCH)
    subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-I',str(root/'tools'),
                    str(out/'bench.c'),str(root/'tools/glrt_tracking_visit.c'),'-o',str(out/'bench')],check=True)
    return out/'bench'


@pytest.mark.parametrize('rate',[30000000,60000000])
@pytest.mark.parametrize('mode,result,tunes,runs',[
    ('ready',0,2,2),('lower_edge',-1,0,0),('duplicate',-1,0,0),('invalid_rate',-1,0,0),
    ('missing_port',-1,0,0),('read',-2,0,0),('busy',-2,0,0),('fixed_rf',-2,0,0),
    ('wrong_rate',-2,0,0),('tune_fail',-3,1,0),('wrong_lo',-2,1,0),
    ('tune_epoch',-2,1,0),('tune_counter',-2,1,0),('after_busy',-2,1,1),
    ('no_epoch',-2,1,1),('no_samples',-2,1,1),('run_rf',-2,1,1),
    ('between_epoch',-2,1,1),('child_fail',-4,1,1),('deadline',-6,1,1),
    ('clock_regress',-6,1,1),('cancel',-7,0,0),('retention_before',-5,0,0),
    ('retention_tuned',-5,1,0),('retention_after',-5,1,1),
    ('loss',0,2,2),('unknown_result',-4,1,1),
    ('loss_after_busy',-2,1,1),('loss_no_epoch',-2,1,1),
    ('loss_no_samples',-2,1,1),('loss_run_rf',-2,1,1),
    ('loss_retention_after',-5,1,1),('loss_deadline',-6,1,1),
    ('loss_clock_regress',-6,1,1),('loss_between_epoch',-2,1,1),
])
def test_two_visits_preserve_fixed_rate_and_require_idle_retained_boundaries(probe,rate,mode,result,tunes,runs):
    row=list(map(int,subprocess.check_output([str(probe),mode,str(rate)],text=True).split()))
    assert (row[0],row[2],row[3])==(result,tunes,runs)
    if mode=='ready': assert row==[0,6,2,2,6]
    if mode in ('child_fail','deadline','clock_regress','no_epoch','no_samples'):
        assert row[4]==3  # failure still retains verified post-child state
