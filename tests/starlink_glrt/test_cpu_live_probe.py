"""Live worker with advancing owned IQ and explicit simulated native ports.

This exercises the actual pthread/FFTW composition, not FPGA or RF accuracy.
"""
import ctypes as c
import copy
import json
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

import numpy as np
import pytest

from tools.generate_glrt_tracking_gram import reference_rows
from .test_cpu_coarse import bank
from .test_tracking_seed import SOURCES
from .test_native_controller import Radio, Ports, Read, Write, Retain, Clock
from .test_tracking_controller import controller, models, pilot_moments
from .test_native_journal import journal as native_journal
from tools.starlink_glrt_tracking_journal import review as review_native_journal
from tools.review_glrt_cpu_live_epochs import review_epochs
from tools.review_glrt_cpu_visit_loss import review_clean_loss

pytestmark = pytest.mark.fftw

WRAPPER = r'''
#define main unused_probe_main
#include "glrt_cpu_live_probe.c"
#undef main
struct test_live { struct live live; int16_t *ring; fftw_complex *fft; uint64_t end; FILE *capture; };
const char *iio_device_get_id(const struct iio_device *d) { (void)d;return "iio:device0"; }
int iio_channel_attr_read_longlong(const struct iio_channel *c,const char *name,long long *out)
{ char text[128];if(iio_channel_attr_read(c,name,text,sizeof(text))<=0) return -1;*out=strtoll(text,NULL,10);return 0; }
int live_journal_file(const char *directory,unsigned episode,const char *kind,const char *raw)
{
    struct live *s=calloc(1,sizeof(*s));struct glrt_native_posix p={.device=-1,.journal=-1};int rc;
    if(!s) abort();
    s->restarts=episode;rc=open_native_episode(s,&p,directory,directory);
    if(!rc) rc=s->native.retain(s->native.context,kind,raw,strlen(raw));
    if(glrt_native_posix_close(&p)) rc=-1;
    free(s);return rc;
}
void *live_new(const int16_t *refs,const int16_t *bank,const char *directory,
              const struct glrt_native_ports *ports,unsigned rate)
{
    struct test_live *t=calloc(1,sizeof(*t));struct live *s=&t->live;char path[4096];
    if(!t) abort();
    t->ring=malloc(RING*4U);t->fft=fftw_malloc(GLRT_RESOLVER_FFT*sizeof(*t->fft));
    if(!t->ring || !t->fft || pthread_mutex_init(&s->mutex,NULL)) abort();
    memcpy(s->refs,refs,sizeof(s->refs));memcpy(s->bank,bank,sizeof(s->bank));
    s->native=*ports;s->epoch=3;s->rate=rate;s->attempt_limit=ATTEMPTS;s->restart_on_loss=1;
    s->native_result_limit=NATIVE_RESULTS;s->native_seconds=NATIVE_SECONDS;t->end=1000000;
    s->fft=fftw_plan_dft_1d(GLRT_RESOLVER_FFT,t->fft,t->fft,FFTW_FORWARD,FFTW_ESTIMATE|FFTW_UNALIGNED);
    if(!s->fft || glrt_tracking_iq_owner_init(&s->owner,t->ring,RING,s->epoch,t->end)) abort();
    snprintf(path,sizeof(path),"%s/worker.jsonl",directory);s->journal=fopen(path,"wx");
    snprintf(path,sizeof(path),"%s/worker.iq",directory);s->worker_iq=fopen(path,"wbx");
    snprintf(path,sizeof(path),"%s/grids",directory);s->grids=fopen(path,"wbx");
    snprintf(path,sizeof(path),"%s/native.coarse.ci16",directory);s->native_coarse_iq=fopen(path,"wbx");
    snprintf(path,sizeof(path),"%s/observer.jsonl",directory);s->observer_journal=fopen(path,"wx");
    snprintf(path,sizeof(path),"%s/observer.iq.ci16",directory);s->observer_iq=fopen(path,"wbx");
    snprintf(path,sizeof(path),"%s/capture.txt",directory);t->capture=fopen(path,"wx");
    if(!s->journal || !s->worker_iq || !s->grids || !s->native_coarse_iq || !t->capture ||
       !s->observer_journal || !s->observer_iq) abort();
    fprintf(t->capture,"epoch_binding 9122201 3 %" PRIu64 " %" PRIu64 "\n",t->end*(rate/2500000)-1,t->end);
    return t;
}
int live_publish(struct test_live *t,const int16_t *iq,size_t count)
{
    int rc=glrt_tracking_iq_owner_publish(&t->live.owner,t->live.epoch,t->end,iq,count,t->end+count,clock_ns(NULL));
    if(!rc) t->end+=count;
    return rc;
}
int live_set_dwell(struct test_live *t,const char *blocks,uint64_t out[4])
{
    struct dwell_limits limits;
    if(dwell_limits(blocks,&limits)) return -1;
    if(t) { t->live.attempt_limit=limits.attempts;t->live.selected_iq=limits.selected_iq;
        t->live.observer_spacing=limits.observer_spacing;t->live.rank_budget=limits.rank_budget;
        t->live.restart_on_loss=limits.restart_on_loss;
        t->live.native_result_limit=limits.native_results;t->live.native_seconds=limits.native_seconds;
        if(limits.rank_budget>8 && !t->live.ranking_fft) {
            t->live.ranking_fft=fftw_plan_dft_1d(limits.rank_budget==80 ? 512 : 4096,
                t->fft,t->fft,FFTW_FORWARD,FFTW_ESTIMATE|FFTW_UNALIGNED);
            if(!t->live.ranking_fft) abort();
        } }
    out[0]=limits.blocks;out[1]=limits.attempts;
    out[2]=limits.alarm_seconds;out[3]=limits.worker_ns;
    return 0;
}
int live_restart_on_loss(const char *blocks)
{ struct dwell_limits limits;return dwell_limits(blocks,&limits) ? -1 : limits.restart_on_loss; }
int live_native_limits(const char *blocks,uint64_t out[2])
{
    struct dwell_limits limits;
    if(dwell_limits(blocks,&limits)) return -1;
    out[0]=limits.native_results;out[1]=(uint64_t)limits.native_seconds;
    return 0;
}
void live_select_windows(struct test_live *t,const char *directory,unsigned attempts,int fail)
{
    char path[4096];struct live *s=&t->live;
    s->selected_iq=1;s->attempt_limit=attempts;
    snprintf(path,sizeof(path),"%s/scan.iq.ci16",directory);
    s->scan_samples=fopen(fail ? "/dev/full" : path,fail ? "wb" : "wbx");
    if(!s->scan_samples) abort();
}
int live_capture_done(struct test_live *t) { return capture_worker_done(&t->live); }
int live_final(unsigned admitted,unsigned delivered,unsigned flags,unsigned returned,unsigned limit)
{
    struct glrt_capture_snapshot s={0};s.words[4]=admitted;s.words[6]=delivered;s.words[19]=flags;
    return capture_early_final(&s,returned,limit);
}
int live_worker_terminal_clean(int result,int finite_source_complete)
{ return worker_terminal_is_clean(result,finite_source_complete); }
int live_rank_fast_reject(unsigned budget,double power,unsigned attempt)
{ return rank_fast_reject(budget,power,attempt); }
void live_pair_stage(struct test_live *t,uint64_t native_start,int fail)
{
    struct live *s=&t->live;uint32_t *w=s->paired[0].words;
    w[3]=(uint32_t)native_start;w[4]=(uint32_t)(native_start>>32);w[7]=s->rate*33/25000;
    s->paired_queued=1;
    if(fail) { fclose(s->native_coarse_iq);s->native_coarse_iq=fopen("/dev/full","wb");if(!s->native_coarse_iq) abort(); }
}
void live_observer_fail(struct test_live *t,int journal)
{
    FILE **f=journal ? &t->live.observer_journal : &t->live.observer_iq;
    fclose(*f);*f=fopen("/dev/full","wb");if(!*f) abort();
}
int live_observer_seed_start(struct test_live *t)
{
    struct live *s=&t->live;struct glrt_native_estimate e={0};
    e.coherence=e.linearized_coherence=.9;
    if(glrt_tracking_trend_reset(&s->worker.live.core.trend,3,2500000)) abort();
    unsigned spacing=s->observer_spacing ? s->observer_spacing : 9;
    uint64_t anchor=1000000-(63+spacing)*2500000U/750;
    for(unsigned k=0;k<8;k++)
        if(glrt_tracking_trend_observe(&s->worker.live.core.trend,3,k*9,anchor+k*30000,0,&e)!=1) abort();
    s->deadline_ns=clock_ns(NULL)+UINT64_C(5000000000);
    return start_observer(s);
}
int live_observer_join(struct test_live *t) { return join_observer(&t->live); }
void live_observer_spacing(struct test_live *t,unsigned spacing) { t->live.observer_spacing=spacing; }
void live_deadline(struct test_live *t,uint64_t nanoseconds) { t->live.deadline_ns=clock_ns(NULL)+nanoseconds; }
int live_pair_copy(struct test_live *t,unsigned *copied)
{
    int result=paired_copy(&t->live);*copied=t->live.paired_copied;return result;
}
void live_start(struct test_live *t)
{
    if(!t->live.deadline_ns) t->live.deadline_ns=clock_ns(NULL)+UINT64_C(5000000000);
    if(pthread_create(&t->live.thread,NULL,worker_thread,&t->live)) abort();
    t->live.started=1;
}
void live_join(struct test_live *t)
{
    void *result=NULL;
    if(pthread_join(t->live.thread,&result) || result) abort();
    t->live.started=0;
}
int live_restart(struct test_live *t) { return restart_owner(&t->live,t->capture); }
int live_visit_loss(struct test_live *t) { return live_visit_clean_loss(&t->live,1); }
void live_visit_mode(struct test_live *t) { t->live.visit_mode=1; }
int live_rebase(struct test_live *t,uint64_t *first)
{
    int rc=rebase_source(&t->live,t->capture,9122201,first);
    if(rc) return rc;
    t->end=*first;
    return glrt_tracking_iq_owner_init(&t->live.owner,t->ring,RING,t->live.epoch,t->end);
}
void live_totals(struct test_live *t,uint64_t out[8])
{
    struct live *s=&t->live;
    out[0]=s->attempts;out[1]=s->restarts;out[2]=s->native_runs;out[3]=s->native_results;
    out[4]=s->native_completed_runs;out[5]=s->iq_samples;out[6]=s->scan_iq_samples;out[7]=s->deadline_ns;
}
/* Admission faults are injected only after the actual worker has joined. */
void live_restart_fault(struct test_live *t,unsigned mode)
{
    struct live *s=&t->live;
    if(mode==1) s->selected_iq=0;
    if(mode==2) s->native_clean_loss=0;
    if(mode==3) s->result=GLRT_NATIVE_RETENTION_ERROR;
    if(mode==4) s->restarts=RESTART_LIMIT;
    if(mode==5) s->attempt_limit=s->attempts;
    if(mode==6) s->stop=1;
    if(mode==7) s->deadline_ns=1;
}
int live_done(struct test_live *t)
{
    int done;if(pthread_mutex_lock(&t->live.mutex)) abort();done=t->live.done;
    if(pthread_mutex_unlock(&t->live.mutex)) abort();
    return done;
}
void live_stop(struct test_live *t)
{
    if(pthread_mutex_lock(&t->live.mutex)) abort();
    t->live.stop=1;
    if(pthread_mutex_unlock(&t->live.mutex)) abort();
}
void live_close_source(struct test_live *t) { if(glrt_tracking_iq_owner_close(&t->live.owner,1)) abort(); }
int live_rank(struct test_live *t,const int16_t *iq,const unsigned *epochs,unsigned count,
              double *scores,unsigned *selected)
{
    struct live *s=&t->live;int selected_shift;
    memcpy(s->scan_iq,iq,sizeof(s->scan_iq));s->coarse.count=count;
    for(unsigned k=0;k<count && k<8;k++) s->coarse.peaks[k].epoch=epochs[k];
    s->wide_count=count;
    for(unsigned k=0;k<count && k<80;k++) s->wide_peaks[k].epoch=epochs[k];
    s->deadline_ns=clock_ns(NULL)+UINT64_C(3000000000);
    return rank_candidates(s,scores,selected,&selected_shift);
}
int live_rank_shift(struct test_live *t,const int16_t *iq,const unsigned *epochs,unsigned count,
                    double *scores,unsigned *selected,int *selected_shift)
{
    struct live *s=&t->live;
    memcpy(s->scan_iq,iq,sizeof(s->scan_iq));s->wide_count=count;
    for(unsigned k=0;k<count && k<80;k++) s->wide_peaks[k].epoch=epochs[k];
    s->deadline_ns=clock_ns(NULL)+UINT64_C(3000000000);
    return rank_candidates(s,scores,selected,selected_shift);
}
void live_free_unstarted(struct test_live *t)
{
    struct live *s=&t->live;
    if(s->observer_started) abort();
    if(s->owner.initialized && (glrt_tracking_iq_owner_close(&s->owner,0) || glrt_tracking_iq_owner_destroy(&s->owner))) abort();
    fclose(s->journal);fclose(s->worker_iq);fclose(s->grids);
    fclose(s->native_coarse_iq);fclose(t->capture);
    fclose(s->observer_journal);fclose(s->observer_iq);
    if(s->scan_samples) fclose(s->scan_samples);
    fftw_destroy_plan(s->fft);if(s->ranking_fft) fftw_destroy_plan(s->ranking_fft);fftw_free(t->fft);free(t->ring);
    if(pthread_mutex_destroy(&s->mutex)) abort();
    free(t);
}
void live_finish(struct test_live *t,uint64_t out[5])
{
    void *result=NULL;struct live *s=&t->live;
    if(s->started && (pthread_join(s->thread,&result) || result)) abort();
    if(s->observer_started) abort();
    out[0]=(uint64_t)(int64_t)s->result;out[1]=s->attempts;out[2]=s->handoffs;
    out[3]=s->controller.configured;out[4]=s->controller.sequence;
    if(s->owner.initialized && (glrt_tracking_iq_owner_close(&s->owner,0) || glrt_tracking_iq_owner_destroy(&s->owner))) abort();
    fclose(s->journal);fclose(s->worker_iq);fclose(s->grids);
    fclose(s->native_coarse_iq);fclose(t->capture);
    fclose(s->observer_journal);fclose(s->observer_iq);
    if(s->scan_samples) fclose(s->scan_samples);
    fftw_destroy_plan(s->fft);if(s->ranking_fft) fftw_destroy_plan(s->ranking_fft);fftw_free(t->fft);free(t->ring);
    if(pthread_mutex_destroy(&s->mutex)) abort();
    free(t);
}
'''


@pytest.fixture(scope="module")
def live_api(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    out = tmp_path_factory.mktemp("cpu-live")
    fixture = root/"tests/starlink_glrt/iio_probe_fixture"
    (out/"iio.h").write_text((fixture/"iio.h").read_text()+
        '\nconst char *iio_device_get_id(const struct iio_device *);\n'
        'int iio_channel_attr_read_longlong(const struct iio_channel *,const char *,long long *);\n')
    (out/"wrapper.c").write_text(WRAPPER)
    prefix = os.environ.get("GLRT_FFTW_PREFIX")
    includes = ["-I", str(Path(prefix)/"include")] if prefix else []
    libraries = ["-L", str(Path(prefix)/"lib"), "-Wl,-rpath,"+str(Path(prefix)/"lib")] if prefix else []
    names = ["glrt_cpu_coarse.c", "glrt_cpu_seed.c", "glrt_tracking_worker.c", "glrt_tracking_live_bootstrap.c", "glrt_tracking_observer.c",
             "glrt_tracking_iq.c", "glrt_iq_tracking_source.c", "glrt_capture_source.c",
             "glrt_tracking_transport.c", "glrt_native_controller.c", "glrt_native_posix.c", *SOURCES]
    subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread", "-shared", "-fPIC",
        "-I", str(out), "-I", str(root/"tools"), *includes, str(out/"wrapper.c"), str(fixture/"backend.c"),
        *(str(root/"tools"/name) for name in names), *libraries, "-lfftw3", "-lm", "-o", str(out/"live.so")], check=True)
    lib = c.CDLL(str(out/"live.so"))
    lib.live_new.argtypes = [c.c_void_p, c.c_void_p, c.c_char_p, c.POINTER(Ports), c.c_uint]
    lib.live_new.restype = c.c_void_p
    lib.live_journal_file.argtypes = [c.c_char_p,c.c_uint,c.c_char_p,c.c_char_p]
    lib.live_publish.argtypes = [c.c_void_p, c.c_void_p, c.c_size_t]
    lib.live_set_dwell.argtypes = [c.c_void_p, c.c_char_p, c.c_void_p]
    lib.live_restart_on_loss.argtypes = [c.c_char_p]
    lib.live_select_windows.argtypes = [c.c_void_p,c.c_char_p,c.c_uint,c.c_int]
    lib.live_capture_done.argtypes = [c.c_void_p]
    lib.live_final.argtypes = [c.c_uint]*5
    lib.live_worker_terminal_clean.argtypes = [c.c_int,c.c_int]
    lib.live_rank_fast_reject.argtypes = [c.c_uint,c.c_double,c.c_uint]
    lib.live_deadline.argtypes = [c.c_void_p,c.c_uint64]
    lib.live_pair_stage.argtypes = [c.c_void_p,c.c_uint64,c.c_int]
    lib.live_pair_copy.argtypes = [c.c_void_p,c.c_void_p]
    lib.live_observer_fail.argtypes = [c.c_void_p,c.c_int]
    lib.live_observer_seed_start.argtypes = [c.c_void_p]
    lib.live_observer_join.argtypes = [c.c_void_p]
    lib.live_observer_spacing.argtypes = [c.c_void_p,c.c_uint]
    lib.live_rebase.argtypes = [c.c_void_p,c.c_void_p]
    lib.live_totals.argtypes = [c.c_void_p,c.c_void_p]
    lib.live_restart_fault.argtypes = [c.c_void_p,c.c_uint]
    lib.live_native_limits.argtypes = [c.c_char_p,c.c_void_p]
    lib.unused_probe_main.argtypes = [c.c_int, c.POINTER(c.c_char_p)]
    lib.live_rank.argtypes = [c.c_void_p,c.c_void_p,c.c_void_p,c.c_uint,c.c_void_p,c.c_void_p]
    lib.live_rank_shift.argtypes = [c.c_void_p,c.c_void_p,c.c_void_p,c.c_uint,c.c_void_p,c.c_void_p,c.c_void_p]
    lib.live_free_unstarted.argtypes = [c.c_void_p]
    for name in ("live_start", "live_done", "live_stop", "live_close_source", "live_join", "live_restart", "live_visit_loss", "live_visit_mode"):
        getattr(lib, name).argtypes = [c.c_void_p]
    lib.live_finish.argtypes = [c.c_void_p, c.c_void_p]
    rom = root/"hdl/library/starlink_glrt"
    refs = np.asarray([reference_rows((rom/"native_cubic_60000000_upper.mem").read_bytes(),
        (rom/"native_direct_2500000_phase4_upper_interleaved.mem").read_bytes(), 2500000, p)
        for p in range(4)], dtype=np.int16)
    return lib, refs


@pytest.mark.parametrize('blocks,expected', [
    (None, [1536,6,25,12000000000]), (b'1536', [1536,6,25,12000000000]),
    (b'4096', [4096,16,45,30000000000]),
    (b'45000', [45000,200,325,300000000000]),
    (b'45000-selected-observer3-scan64', [45000,256,325,300000000000]),
    (b'45000-selected-observer3-scan80-local2', [45000,256,325,300000000000]),
    (b'45000-selected-observer3-scan80-local2-track10', [45000,256,325,300000000000]),
    (b'45000-selected-observer9-scan80-local2-track10', [45000,256,325,300000000000]),
    (b'1536-selected', [1536,6,25,12000000000]),
    (b'1536-selected-observer3', [1536,6,25,12000000000]),
    (b'1536-selected-observer3-scan64', [1536,6,25,12000000000]),
    (b'1536-selected-observer3-scan80-local2', [1536,6,25,12000000000]),
])
def test_dwell_profiles_have_finite_capture_and_worker_limits(live_api, blocks, expected):
    lib, _ = live_api
    out = (c.c_uint64*4)()
    assert lib.live_set_dwell(None, blocks, out) == 0
    assert list(out) == expected
    assert out[0]*16384/2500000 < 300


@pytest.mark.parametrize('profile,expected',[
    (b'1536',[1500,3]),
    (b'45000-selected-observer3-scan80-local2',[1500,3]),
    (b'45000-selected-observer3-scan80-local2-track10',[7500,12]),
    (b'45000-selected-observer9-scan80-local2-track10',[7500,12]),
])
def test_native_tracking_horizon_is_explicit_per_profile(live_api,profile,expected):
    lib,_=live_api
    out=(c.c_uint64*2)()
    assert lib.live_native_limits(profile,out)==0
    assert list(out)==expected


@pytest.mark.parametrize('profile,expected',[
    (b'45000',1),(b'45000-selected-observer3-scan64',1),(b'45000-selected-observer3-scan80-local2',1),
    (b'45000-selected-observer3-scan80-local2-track10',1),
    (b'45000-selected-observer9-scan80-local2-track10',1),(b'1536',0),
    (b'4096',0),(b'1536-selected',0),(b'1536-selected-observer3',0),
    (b'1536-selected-observer3-scan64',0),(b'1536-selected-observer3-scan80-local2',0),(b'unknown',-1)])
def test_only_long_profiles_restart_after_clean_native_loss(live_api,profile,expected):
    lib,_=live_api
    assert lib.live_restart_on_loss(profile)==expected


@pytest.mark.parametrize('blocks', [b'0', b'4097', b'-1', b'4096garbage', b'4294967296'])
def test_invalid_dwell_rejected_before_opening_evidence_or_radio(live_api, tmp_path, blocks):
    lib, _ = live_api
    args = [b'probe', b'30000000', b'serial', b'missing-bank', b'missing-refs', os.fsencode(tmp_path), blocks]
    assert lib.unused_probe_main(len(args), (c.c_char_p*len(args))(*args)) == 2
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('admitted,delivered,flags,expected', [
    (32768,32768,8,1), (32891,32891,8,1),
    (32891,32890,8,0), (32767,32767,8,0),
    (32768,32768,9,0), (32768,32768,10,0),
    (65537,65537,8,0),
])
def test_early_stop_requires_idle_complete_counters_with_bounded_tail(live_api, admitted, delivered, flags, expected):
    lib,_=live_api
    assert lib.live_final(admitted,delivered,flags,2,4)==expected


@pytest.mark.parametrize('result,finite,expected',[
    (0,0,1),(0,1,1),(-4,1,1),(-4,0,0),(-1,1,0),(-5,1,0),(-6,1,0)])
def test_finite_source_accepts_only_clean_worker_cancellation(live_api,result,finite,expected):
    lib,_=live_api
    assert lib.live_worker_terminal_clean(result,finite)==expected


@pytest.mark.parametrize('budget,power,attempt,expected',[
    (80,0.0,1,1),(80,0.029999,2,1),(80,0.029999,4,0),
    (80,0.03,1,0),(80,0.05,1,0),(64,0.0,1,0),(8,0.0,1,0)])
def test_scan80_only_fast_rejects_below_resolver_power_floor(live_api,budget,power,attempt,expected):
    lib,_=live_api
    assert lib.live_rank_fast_reject(budget,power,attempt)==expected


def test_scan80_noise_records_prefiltered_attempt_without_resolver(live_api,tmp_path):
    lib,refs=live_api;handle=lib.live_new(refs.ctypes.data,bank().ctypes.data,
        os.fsencode(tmp_path),c.byref(Ports()),30000000)
    assert lib.live_set_dwell(handle,b'1536-selected-observer3-scan80-local2',(c.c_uint64*4)())==0
    # Leave capture headroom so the finite-source stop cannot race the worker's
    # first scan on a busy test host.
    lib.live_select_windows(handle,os.fsencode(tmp_path),8,0)
    lib.live_deadline(handle,30_000_000_000)
    iq=np.random.default_rng(8030).integers(-100,101,(16384,2),dtype=np.int16)
    assert lib.live_publish(handle,iq.ctypes.data,len(iq))==0
    lib.live_start(handle)
    try:
        deadline=time.monotonic()+10
        while len((tmp_path/'worker.jsonl').read_text().splitlines())<3:
            assert time.monotonic()<deadline
            time.sleep(.001)
    finally:
        lib.live_stop(handle)
        out=(c.c_uint64*5)();lib.live_finish(handle,out)
    rows=[json.loads(line) for line in (tmp_path/'worker.jsonl').read_text().splitlines()]
    assert [row['kind'] for row in rows[:3]]==['scan','candidate_order','worker_terminal']
    rank,terminal=rows[1:3]
    assert max(rank['single_pilot_power'])<0.03
    assert terminal['status']==-6 and terminal['prefiltered']==1
    assert terminal['retained_past']==terminal['supported_history']==terminal['fft_calls']==0
    assert c.c_int64(out[0]).value in (0,-4)
    assert out[1]>=1 and list(out)[2:]==[0,0,0]


def test_native_episodes_use_separate_exclusive_bounded_journals(live_api,tmp_path):
    lib,_=live_api
    saved={}
    for episode in range(4):
        payload=f'preserved episode {episode}\n'.encode()
        assert lib.live_journal_file(os.fsencode(tmp_path),episode,b'final',payload)==0
        name='native.journal' if not episode else f'native-{episode}.journal'
        saved[name]=b'GLRJ1\nfinal '+str(len(payload)).encode()+b'\n'+payload
        assert lib.live_journal_file(os.fsencode(tmp_path),episode,b'final',b'replacement')==-1
    assert lib.live_journal_file(os.fsencode(tmp_path),4,b'final',b'unbounded')==-1
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir()}==saved


@pytest.mark.parametrize('rate', [30000000,60000000])
@pytest.mark.parametrize('mode', ['delayed','closed','overwritten','retention'])
def test_paired_iq_waits_for_real_publication_and_rejects_lost_inputs(live_api, tmp_path, rate, mode):
    lib,refs=live_api; coefficients=bank();ports=Ports()
    handle=lib.live_new(refs.ctypes.data,coefficients.ctypes.data,os.fsencode(tmp_path),c.byref(ports),rate)
    iq=np.random.default_rng(718).integers(-1000,1001,(3333,2),dtype=np.int16)
    copied=c.c_uint(999)
    try:
        lib.live_pair_stage(handle,1000016*(rate//2500000)+3,mode=='retention')
        assert lib.live_publish(handle,iq.ctypes.data,2000)==0
        assert lib.live_pair_copy(handle,c.byref(copied))==0 and copied.value==0
        assert (tmp_path/'native.coarse.ci16').stat().st_size==0
        if mode=='closed':
            lib.live_close_source(handle)
        elif mode=='overwritten':
            extra=np.zeros((5000000,2),dtype=np.int16)
            assert lib.live_publish(handle,extra.ctypes.data,len(extra))==0
        else:
            extra=np.ascontiguousarray(iq[2000:])
            assert lib.live_publish(handle,extra.ctypes.data,len(extra))==0
        rc=lib.live_pair_copy(handle,c.byref(copied))
        assert rc=={'delayed':0,'closed':-3,'overwritten':-3,'retention':-6}[mode]
        assert copied.value==int(mode=='delayed')
    finally:
        lib.live_free_unstarted(handle)
    if mode=='delayed':
        np.testing.assert_array_equal(np.fromfile(tmp_path/'native.coarse.ci16',dtype='<i2').reshape(-1,2),iq)
        row=json.loads((tmp_path/'worker.jsonl').read_text())
        assert row['first']==1000000 and row['native_start']==1000016*(rate//2500000)+3


@pytest.mark.parametrize('mode', ['secondary_pilot', 'noise', 'zero', 'cancel', 'invalid_epoch'])
@pytest.mark.parametrize('wide',[False,True])
def test_original_pilot_order_matches_independent_fft(live_api, tmp_path, mode,wide):
    lib, refs = live_api
    coefficients = bank()
    ports = Ports()
    handle = lib.live_new(refs.ctypes.data, coefficients.ctypes.data, os.fsencode(tmp_path), c.byref(ports), 60000000)
    iq = np.random.default_rng(982).integers(-100,101,(14000,2),dtype=np.int16)
    epochs = np.array([500,1023,1800,2200,2600,3000,50,3250],dtype=np.uint32)
    if wide:
        assert lib.live_set_dwell(handle,b'1536-selected-observer3-scan64',(c.c_uint64*4)())==0
        epochs=np.concatenate([epochs,np.arange(56,dtype=np.uint32)*53])
    if mode == 'secondary_pilot':
        ref = refs[0,:,0].astype(float)+1j*refs[0,:,1]
        pilot = ref*np.exp(2j*np.pi*464356*np.arange(3300)/2500000)
        iq[1045:4345] = np.rint(np.column_stack((pilot.real,pilot.imag)))
    if mode == 'zero': iq[:]=0
    if mode == 'cancel': lib.live_stop(handle)
    if mode == 'invalid_epoch': epochs[7]=3333
    scores = np.full(len(epochs),999.,dtype=np.float64);selected=c.c_uint(999)
    try:
        rc = lib.live_rank(handle,iq.ctypes.data,epochs.ctypes.data,len(epochs),scores.ctypes.data,c.byref(selected))
    finally:
        lib.live_free_unstarted(handle)
    if mode in ('cancel','invalid_epoch'):
        assert rc == -1 and selected.value == 0 and not scores.any()
        return
    ref = refs[0,:,0].astype(float)+1j*refs[0,:,1]
    expected=[]
    for epoch in epochs:
        cut=iq[int(epoch)+22:int(epoch)+3322].astype(float)
        z=cut[:,0]+1j*cut[:,1]
        expected.append(max(abs(np.fft.fft(z*np.conj(ref),4096 if wide else 16384))**2)/
                        max(float(np.vdot(z,z).real*np.vdot(ref,ref).real),1))
    assert rc == 0 and selected.value == np.argmax(expected)
    np.testing.assert_allclose(scores,expected,rtol=2e-12,atol=2e-15)
    if mode == 'secondary_pilot': assert selected.value == 1


def test_scan80_local_timing_search_selects_corrected_epoch(live_api,tmp_path):
    lib,refs=live_api;handle=lib.live_new(refs.ctypes.data,bank().ctypes.data,
        os.fsencode(tmp_path),c.byref(Ports()),60000000)
    assert lib.live_set_dwell(handle,b'1536-selected-observer3-scan80-local2',(c.c_uint64*4)())==0
    iq=np.random.default_rng(8042).integers(-50,51,(14000,2),dtype=np.int16)
    epochs=np.arange(80,dtype=np.uint32)*39+100
    selected_epoch=int(epochs[37]);corrected_epoch=selected_epoch+2
    ref=refs[0,:512,0].astype(float)+1j*refs[0,:512,1]
    pilot=ref*np.exp(2j*np.pi*31*np.arange(512)/512)
    iq[corrected_epoch+22:corrected_epoch+22+512]=np.rint(
        np.column_stack((pilot.real,pilot.imag))).astype(np.int16)
    scores=np.full(80,999.,dtype=np.float64);selected=c.c_uint(999);shift=c.c_int(999)
    try:
        rc=lib.live_rank_shift(handle,iq.ctypes.data,epochs.ctypes.data,len(epochs),
            scores.ctypes.data,c.byref(selected),c.byref(shift))
    finally:
        lib.live_free_unstarted(handle)
    assert rc==0 and selected.value==37 and shift.value==2
    assert scores[37]>0.99 and np.count_nonzero(scores>0.1)==1


def check_observer_evidence(directory,iq,origin,worker_rows,rate,spacing=9):
    rows=[json.loads(line) for line in (directory/'observer.jsonl').read_text().splitlines()]
    retained=np.fromfile(directory/'observer.iq.ci16',dtype='<i2').reshape(-1,2)
    offset=0;active=None;measurements=[]
    seeds={r['attempt']:r for r in worker_rows if r['kind']==4}
    for row in rows:
        if row['kind']=='start':
            assert active is None
            active=row;measurements=[]
            assert row['rate']==2500000 and row['native_rate']==rate
            assert row['frame_spacing']==spacing
            assert row['first_frame']==seeds[row['attempt']]['last_seen']+spacing
            assert row['epoch']==seeds[row['attempt']]['epoch']
            assert row['maximum_measurements']==200
            assert row['retained_total']*3300==offset
        else:
            assert active is not None
            assert all(row[k]==active[k] for k in ('attempt','episode','epoch'))
            if row['kind']=='measurement':
                assert row['sequence']==len(measurements)<200
                assert row['frame']==active['first_frame']+spacing*row['sequence']
                assert row['iq_offset']==offset and row['iq_samples']==3300
                start=row['first']-origin
                np.testing.assert_array_equal(retained[offset:offset+3300],iq[start:start+3300])
                assert row['source']['epoch']==row['epoch'] and not row['source']['closed']
                assert row['source']['first']<=row['first'] and row['first']+3300<=row['source']['end']
                assert row['source']['end']<=row['source']['source_now']<=active['source_limit']
                assert row['accepted']==int(row['rejection']==0)
                measurements.append(row);offset+=3300
            else:
                assert row['kind']=='terminal'
                assert row['retained_total']*3300==offset
                # Cancellation can race retention: the last retained record is
                # deliberately not committed until the post-retention guard.
                assert 0<=len(measurements)-row['measurements']<=1
                committed=measurements[:row['measurements']]
                seed=seeds[row['attempt']]
                assert row['last_seen']==(committed[-1]['frame'] if committed else seed['last_seen'])
                supported=[r['frame'] for r in committed if r['accepted']]
                assert row['last_supported']==(supported[-1] if supported else seed['last_supported'])
                active=None
    assert active is None and offset==len(retained)
    return rows


@pytest.mark.parametrize('mode',['waiting_cancel','retained_cancel','closed','iq_failure','journal_failure'])
@pytest.mark.parametrize('spacing',[9,3])
def test_observer_thread_has_separate_retention_and_is_joined_before_owner_release(live_api,tmp_path,mode,spacing):
    lib,refs=live_api;coefficients=bank();ports=Ports()
    handle=lib.live_new(refs.ctypes.data,coefficients.ctypes.data,os.fsencode(tmp_path),c.byref(ports),60000000)
    try:
        limits=(c.c_uint64*4)()
        profile=b'1536-selected-observer3' if spacing==3 else b'1536-selected'
        assert lib.live_set_dwell(handle,profile,limits)==0
        if mode in ('iq_failure','journal_failure'): lib.live_observer_fail(handle,int(mode=='journal_failure'))
        rc=lib.live_observer_seed_start(handle)
        assert rc==(-6 if mode=='journal_failure' else 0)
        if mode!='journal_failure':
            if mode=='closed': lib.live_close_source(handle)
            elif mode!='waiting_cancel':
                cut=np.ascontiguousarray(refs[0,:,:2])
                assert lib.live_publish(handle,cut.ctypes.data,len(cut))==0
            # Wait on concrete evidence, with an explicit short bound.
            if mode!='waiting_cancel':
                until=time.monotonic()+1
                while True:
                    rows=[json.loads(line) for line in (tmp_path/'observer.jsonl').read_text().splitlines()]
                    if any(r['kind']==('measurement' if mode=='retained_cancel' else 'terminal') for r in rows): break
                    assert time.monotonic()<until
                    time.sleep(.002)
            assert lib.live_observer_join(handle)=={'closed':-3,'iq_failure':-6}.get(mode,0)
            assert lib.live_observer_join(handle)==0
    finally:
        lib.live_free_unstarted(handle)  # C aborts if any observer remains live.
    assert (tmp_path/'worker.jsonl').read_bytes()==b''
    assert (tmp_path/'native.coarse.ci16').read_bytes()==b''
    if mode!='journal_failure':
        rows=[json.loads(line) for line in (tmp_path/'observer.jsonl').read_text().splitlines()]
        assert rows[0]['frame_spacing']==spacing and rows[0]['first_frame']==63+spacing
        assert rows[-1]['kind']=='terminal'
        assert rows[-1]['status']=={'closed':-2,'iq_failure':-4}.get(mode,-6)
        if mode=='retained_cancel':
            assert rows[-1]['measurements']==1
            np.testing.assert_array_equal(np.fromfile(tmp_path/'observer.iq.ci16',dtype='<i2').reshape(-1,2),refs[0,:,:2])


@pytest.mark.parametrize("rate,mode", [(30000000,"signal"),(60000000,"signal"),
    (60000000,"publication_lag"),(60000000,"handoff_horizon_expired"),
    (30000000,"zero"),(30000000,"zero_long"),(30000000,"cancel"),(30000000,"source_loss"),
    (30000000,"selected_signal"),(60000000,"selected_signal"),
    (60000000,"selected_zero"),(60000000,"selected_retention"),
    (30000000,"native_rejection"),(30000000,"native_retention"),(30000000,"late_handoff"),
    (30000000,"observer_retention"),(60000000,"observer_retention")])
@pytest.mark.parametrize('observer_spacing',[9,3])
def test_advancing_capture_worker_and_native_feedback(live_api, controller, pilot_moments, tmp_path, rate, mode,observer_spacing):
    lib, refs = live_api
    radio = Radio(controller, pilot_moments, tracking_rate=rate)
    if mode == "native_rejection": radio.reject = True
    if mode == "native_retention": radio.fail_retain = "head"
    if mode == "late_handoff": radio.retention_delay = rate//10
    radio.origin = radio.latest = 1000000*(rate//2500000)
    initial = time.monotonic()

    def read(context, name, output, size):
        # Explicit simulated source clock; generated native heads remain port-fixture data.
        latest = radio.origin+int((time.monotonic()-initial)*rate)
        if mode == 'publication_lag': latest += rate//125
        if mode == 'handoff_horizon_expired': latest += rate//10
        radio.advance(max(0, latest-radio.latest))
        return radio.read(context, name, output, size)

    ports = Ports(None, Read(read), Write(radio.write), Retain(radio.retain), Clock(lambda _: radio.time))
    coefficients = bank()
    handle = lib.live_new(refs.ctypes.data, coefficients.ctypes.data, os.fsencode(tmp_path), c.byref(ports), rate)
    lib.live_observer_spacing(handle,observer_spacing)
    if mode=='observer_retention': lib.live_observer_fail(handle,0)
    if mode == 'zero_long':
        assert lib.live_set_dwell(handle, b'4096', (c.c_uint64*4)()) == 0
    if mode.startswith('selected_'):
        lib.live_select_windows(handle, os.fsencode(tmp_path), 3, mode == 'selected_retention')
    assert lib.live_capture_done(handle) == 0
    iq = np.zeros((10_000_000, 2), dtype=np.int16)
    if mode in ("signal", "selected_signal", "publication_lag", "handoff_horizon_expired", "native_rejection", "native_retention", "late_handoff", "observer_retention"):
        for frame in range(3000):
            start = 22+(frame*10000+1)//3
            if start+3300 <= len(iq): iq[start:start+3300] = refs[0, :, :2]
    count = 16384
    assert lib.live_publish(handle, iq.ctypes.data, count) == 0
    initial = time.monotonic()-count/2500000
    lib.live_start(handle)
    try:
        while not lib.live_done(handle):
            elapsed = time.monotonic()-initial
            assert elapsed < 6
            if mode == "cancel":
                lib.live_stop(handle)
            elif mode == "source_loss":
                lib.live_close_source(handle)
            elif count+16384 <= len(iq) and (count+16384)/2500000 <= elapsed:
                block = np.ascontiguousarray(iq[count:count+16384])
                assert lib.live_publish(handle, block.ctypes.data, len(block)) == 0
                count += len(block)
            else:
                time.sleep(.001)
    finally:
        capture_done = lib.live_capture_done(handle)
        lib.live_stop(handle)
        out = (c.c_uint64*5)();lib.live_finish(handle, out)
    assert not radio.errors, radio.errors
    rows = [json.loads(s) for s in (tmp_path/"worker.jsonl").read_text().splitlines()]
    observer_rows=check_observer_evidence(tmp_path,iq,1000000,rows,rate,observer_spacing)
    pairs = [r for r in rows if r['kind']=='native_coarse_iq']
    paired_iq = np.fromfile(tmp_path/'native.coarse.ci16',dtype='<i2').reshape(-1,2)
    assert len(paired_iq)==len(pairs)*3333 and len(pairs)<=64
    for index,row in enumerate(pairs):
        assert row['native_sequence']==index and row['iq_offset']==index*3333 and row['iq_samples']==3333
        assert row['first']==row['native_start']//(rate//2500000)-16
        first=row['first']-1000000
        np.testing.assert_array_equal(paired_iq[index*3333:(index+1)*3333],iq[first:first+3333])
        assert row['source']['first']<=row['first'] and row['first']+3333<=row['source']['end']
        assert row['source']['epoch']==3 and not row['source']['closed']
    assert capture_done == int(mode.startswith('selected_'))
    if mode.startswith('selected_'):
        scans = [r for r in rows if r['kind'] == 'scan']
        if mode == 'selected_retention':
            assert not scans and c.c_int64(out[0]).value == -5
        else:
            searched = np.fromfile(tmp_path/'scan.iq.ci16',dtype='<i2').reshape(-1,2)
            assert len(searched) == 14000*len(scans)
            for index,row in enumerate(scans):
                assert row['scan_iq_offset'] == index*14000 and row['scan_iq_samples'] == 14000
                start = row['window_start']-1000000
                np.testing.assert_array_equal(searched[index*14000:(index+1)*14000],iq[start:start+14000])
                assert row['source']['first'] <= row['window_start']
                assert row['window_start']+14000 <= row['source']['end']
            if mode == 'selected_zero': assert len(scans) == 3 and out[0] == 0
    if mode == 'zero_long':
        assert out[1] == 16 and out[2] == 0
        assert len([r for r in rows if r['kind'] == 'scan']) == 16
    if mode in ("signal", "selected_signal", "publication_lag", "observer_retention"):
        assert c.c_int64(out[0]).value == (-6 if mode=='observer_retention' else 0), (list(out), rows[-3:])
        assert list(out)[2:] == [1,1500,1500]
        assert len(radio.writes("submit")) > 1 and len(radio.writes("pop")) == 1500
        reviewed = review_native_journal(native_journal(radio), epoch=3, rate=rate)
        assert len(reviewed['heads']) == reviewed['supported'] == 1500
        assert len(pairs)==64
        for row,head in zip(pairs,reviewed['heads'][:64],strict=True):
            assert (row['native_start'],row['native_phase_step'],row['native_phase_seed'])==(
                head.start,head.phase_step,head.phase_seed)
            assert row['native_count']==head.count and row['native_fault']==head.fault
        pair_terminal=next(r for r in rows if r['kind']=='native_terminal')
        assert pair_terminal['paired_result']==0 and pair_terminal['paired_copied']==64
        observer_join=next(r for r in rows if r['kind']=='observer_join')
        assert observer_join['observer_joined']==1
        if mode=='observer_retention':
            assert observer_join['observer_result']==-6
            assert observer_rows[-1]['status']==-4 and observer_rows[-1]['measurements']==0
        else:
            assert observer_join['observer_result']==0
            assert len([r for r in observer_rows if r['kind']=='measurement'])>0
        assert reviewed['handoff'].rate == rate
        assert not radio.pending and not radio.queue and not radio.valid
        first = next(row for row in rows if row["kind"] == "scan")
        terminal = next(row for row in rows if row["kind"] == "worker_terminal")
        assert terminal["source"]["source_now"] > first["source"]["source_now"]
        if mode == 'publication_lag':
            proposal = next(row for row in rows if row['kind'] == 4)
            assert radio.descriptors[0].start > proposal['start']*(rate//2500000)
    elif mode == 'handoff_horizon_expired':
        assert c.c_int64(out[0]).value == -5 and list(out)[2:] == [0,0,0]
        assert not radio.writes('submit') and not radio.writes('command')
    elif mode in ("native_rejection", "native_retention", "late_handoff"):
        result = c.c_int64(out[0]).value
        assert result == {"native_rejection":-4,"native_retention":-6,"late_handoff":-5}[mode]
        if mode == "native_retention":
            assert radio.queue and not radio.writes("pop") and b"4\n" not in radio.writes("command")
        else:
            assert not radio.pending and not radio.queue and not radio.valid
        if mode == "late_handoff": assert out[2] == 0 and not radio.writes("submit")
    else:
        assert list(out)[2:] == [0,0,0] and not radio.events


@pytest.mark.parametrize('rate', [30000000,60000000])
@pytest.mark.parametrize('mode', [
    'loss_then_supported','four_losses','attempt_budget','full_profile','visit_full_profile','visit_selected_profile','short_observer3','short_scan64','visit_scan64','worker_error',
    'retention_error','restart_budget','cancel','deadline','uncleared','source_gap',
    'wrong_epoch','wrong_rate','unread_head','read_failure','rebase_same_epoch',
    'rebase_short_write',
])
def test_clean_native_loss_reacquires_in_new_epoch_with_global_budgets(
        live_api, controller, pilot_moments, tmp_path, rate, mode):
    lib,refs=live_api
    radio=Radio(controller,pilot_moments,tracking_rate=rate)
    ratio=rate//2500000
    radio.origin=radio.latest=1000000*ratio
    radio.reject=True
    initial=time.monotonic()
    read_failed=False

    def read(context,name,output,size):
        if read_failed: return -1
        radio.advance(max(0,radio.origin+int((time.monotonic()-initial)*rate)-radio.latest))
        return radio.read(context,name,output,size)

    def write(context,name,data,size):
        raw=c.string_at(data,size)
        if name==b'tracking_command' and raw==b'16\n':
            assert not radio.valid and not radio.pending and not radio.queue
            assert radio.configured==radio.popped==radio.admitted==0
            radio.events.append(('write','tracking_command',raw))
            if mode=='rebase_short_write': return 2
            if mode!='rebase_same_epoch': radio.epoch+=1
            radio.valid=True
            return size
        return radio.write(context,name,data,size)

    ports=Ports(None,Read(read),Write(write),Retain(radio.retain),Clock(lambda _:radio.time))
    coefficients=bank()
    handle=lib.live_new(refs.ctypes.data,coefficients.ctypes.data,os.fsencode(tmp_path),c.byref(ports),rate)
    lib.live_select_windows(handle,os.fsencode(tmp_path),1 if mode=='attempt_budget' else 8,0)
    if mode=='visit_full_profile':
        lib.live_restart_fault(handle,1)  # Full IQ, not the selected-window profile.
        lib.live_visit_mode(handle)
    if mode=='visit_selected_profile':
        assert lib.live_set_dwell(handle,b'1536-selected',(c.c_uint64*4)())==0
        lib.live_visit_mode(handle)
    if mode=='short_observer3':
        assert lib.live_set_dwell(handle,b'1536-selected-observer3',(c.c_uint64*4)())==0
    if mode in ('short_scan64','visit_scan64'):
        assert lib.live_set_dwell(handle,b'1536-selected-observer3-scan64',(c.c_uint64*4)())==0
        if mode=='visit_scan64': lib.live_visit_mode(handle)
    iq=np.zeros((10_000_000,2),dtype=np.int16)
    for frame in range(3000):
        start=22+(frame*10000+1)//3
        if start+3300<=len(iq): iq[start:start+3300]=refs[0,:,:2]
    count=16384
    assert lib.live_publish(handle,iq.ctypes.data,count)==0
    initial=time.monotonic()-count/2500000
    lib.live_start(handle)
    episodes=[];before=None;initial_deadline=None
    try:
        for episode in range(4):
            while not lib.live_done(handle):
                elapsed=time.monotonic()-initial
                assert elapsed<6
                if (count+16384)/2500000<=elapsed:
                    block=np.ascontiguousarray(iq[count:count+16384])
                    assert len(block)==16384 and lib.live_publish(handle,block.ctypes.data,len(block))==0
                    count+=len(block)
                else: time.sleep(.001)
            # This is the same capture-thread ordering as the executable:
            # finished worker -> join -> retained/drained source check -> release owner.
            if mode in ('visit_full_profile','visit_selected_profile','visit_scan64'): assert lib.live_capture_done(handle)==1
            lib.live_join(handle)
            assert lib.live_visit_loss(handle)==int(not (mode=='loss_then_supported' and episode==1))
            totals=(c.c_uint64*8)();lib.live_totals(handle,totals)
            if initial_deadline is None: initial_deadline=totals[7]
            assert totals[7]==initial_deadline
            if before is not None:
                assert totals[0]>before[0] and totals[5]>before[5] and totals[6]>before[6]
            assert totals[0]<=8 and totals[1]==episode and totals[2]==episode+1
            data=native_journal(radio)
            path=tmp_path/('native.journal' if not episode else f'native-{episode}.journal')
            path.write_bytes(data)
            reviewed=review_native_journal(data,epoch=3+episode,rate=rate)
            assert reviewed['heads'] and not radio.queue and not radio.pending and not radio.valid
            assert reviewed['supported']==(1500 if mode=='loss_then_supported' and episode else 0)
            episodes.append(reviewed)
            assert totals[3]==sum(len(r['heads']) for r in episodes)
            assert totals[4]==int(mode=='loss_then_supported' and episode==1)
            if mode in ('full_profile','visit_full_profile','visit_selected_profile','visit_scan64'):
                rows=[json.loads(line) for line in (tmp_path/'worker.jsonl').read_text().splitlines()]
                observer_rows=[json.loads(line) for line in (tmp_path/'observer.jsonl').read_text().splitlines()]
                disposition=dict(status=3,stage='worker_complete',worker_complete=1,
                    retention_mode='selected_windows' if mode in ('visit_selected_profile','visit_scan64') else 'full',reacquisitions=0,native_completed_runs=0,
                    handoffs=1,native_runs=1,completed_refills=count//16384,blocks=count//16384,
                    attempts=int(totals[0]),rate=rate,native_results=int(totals[3]))
                result=review_clean_loss(rows,data,disposition,observer_rows)
                assert result['status']=='pass' and result['final_frame']==result['last_supported_frame']+32
                for kind,field,value in [
                    ('native_terminal','result',0),('native_terminal','retained_popped',0),
                    ('native_terminal','paired_copied',0),('observer_join','observer_joined',0),
                    ('observer_join','observer_result',-1),('observer_join','epoch',99),
                    ('observer_join','native_result',0),('worker_terminal','status',0),
                ]:
                    altered=copy.deepcopy(rows)
                    next(r for r in altered if r['kind']==kind)[field]=value
                    with pytest.raises((AssertionError,ValueError)):
                        review_clean_loss(altered,data,disposition,observer_rows)
                for field,value in [('status',1),('worker_complete',0),('reacquisitions',1),
                                    ('native_results',0),('blocks',1537),('rate',2500000)]:
                    with pytest.raises((AssertionError,ValueError)):
                        review_clean_loss(rows,data,{**disposition,field:value},observer_rows)
                with pytest.raises((AssertionError,ValueError)):
                    review_clean_loss(rows,data,disposition,observer_rows[:-1])
            if mode=='loss_then_supported' and episode==1:
                assert lib.live_restart(handle)==0
                break
            fault={'full_profile':1,'visit_full_profile':1,'worker_error':2,'retention_error':3,'restart_budget':4,
                   'cancel':6,'deadline':7}.get(mode)
            if fault: lib.live_restart_fault(handle,fault)
            if mode in ('worker_error','retention_error','cancel'):
                assert lib.live_visit_loss(handle)==0
            if mode=='uncleared': radio.valid=True
            if mode=='source_gap': radio.gap=True
            if mode=='wrong_epoch': radio.epoch+=1
            if mode=='wrong_rate': radio.rate=30000000 if rate==60000000 else 60000000
            if mode=='unread_head': radio.queue.append([0]*32)
            if mode=='read_failure': read_failed=True
            prior_writes=len(radio.writes('command'))
            admitted=lib.live_restart(handle)
            assert len(radio.writes('command'))==prior_writes
            if fault or mode=='attempt_budget' or episode==3:
                assert admitted==0
                break
            if mode in ('visit_selected_profile','short_observer3','short_scan64','visit_scan64'):
                assert admitted==0  # Return clean loss to the LO owner, without same-LO REBASE.
                break
            if mode in ('uncleared','source_gap','wrong_epoch','wrong_rate','unread_head','read_failure'):
                assert admitted==(-1 if mode=='read_failure' else -3)
                break
            assert admitted==1
            before=list(totals)
            lib.live_totals(handle,totals)
            assert totals[0]==before[0] and list(totals)[5:]==before[5:]
            assert totals[1]==episode+1
            # A different GLRJ1 stream starts here. Old final records remain
            # immutable and independently reviewable; no cross-epoch append.
            radio.events=[]
            first=c.c_uint64()
            result=lib.live_rebase(handle,c.byref(first))
            if mode.startswith('rebase_'):
                assert result==-1 and not radio.writes('submit')
                break
            assert result==0 and first.value>1000000+count
            count=first.value-1000000
            radio.reject=mode!='loss_then_supported'
            while (count+16384)/2500000>time.monotonic()-initial: time.sleep(.001)
            block=np.ascontiguousarray(iq[count:count+16384])
            assert lib.live_publish(handle,block.ctypes.data,len(block))==0
            count+=len(block)
            lib.live_start(handle)
    finally:
        lib.live_stop(handle)
        out=(c.c_uint64*5)();lib.live_finish(handle,out)
    assert not radio.errors,radio.errors
    rows=[json.loads(line) for line in (tmp_path/'worker.jsonl').read_text().splitlines()]
    check_observer_evidence(tmp_path,iq,1000000,rows,rate,3 if mode in ('short_observer3','short_scan64','visit_scan64') else 9)
    if mode in ('short_scan64','visit_scan64'):
        scans=[r for r in rows if r['kind']=='scan']
        ranks=[r for r in rows if r['kind']=='candidate_order']
        assert scans and ranks and len(scans)==len(ranks)
        assert all(len(r['peaks'])==64 for r in scans)
        assert all(r['ranking_fft']==4096 and r['candidate_budget']==64 and len(r['single_pilot_power'])==64 for r in ranks)
        assert any(r['kind']==4 for r in rows)
    if mode in ('loss_then_supported','four_losses'):
        assert len(episodes)==(2 if mode=='loss_then_supported' else 4)
        scans=[r for r in rows if r['kind']=='scan']
        assert [r['attempt'] for r in scans]==list(range(1,len(scans)+1))
        assert sorted({r['epoch'] for r in scans})==list(range(3,3+len(episodes)))
        assert len([r for r in rows if r['kind']=='reacquisition'])==len(episodes)-1
        pairs=[r for r in rows if r['kind']=='native_coarse_iq']
        paired=np.fromfile(tmp_path/'native.coarse.ci16',dtype='<i2').reshape(-1,2)
        assert len(paired)==len(pairs)*3333<=64*3333
        for index,row in enumerate(pairs):
            head=episodes[row['native_episode']]['heads'][row['native_sequence']]
            assert row['native_start']==head.start
            assert row['source']['epoch']==3+row['native_episode']
            assert row['iq_offset']==index*3333
            start=row['first']-1000000
            np.testing.assert_array_equal(paired[index*3333:(index+1)*3333],iq[start:start+3333])
        if mode=='loss_then_supported': assert len(pairs)==64
        capture_text=(tmp_path/'capture.txt').read_text()
        journals={p.name:p.read_bytes() for p in tmp_path.glob('native*.journal')}
        status=dict(rate=rate,reacquisitions=totals[1],attempts=totals[0],native_runs=totals[2],
                    native_results=totals[3],native_completed_runs=totals[4],handoffs=out[2])
        result=review_epochs(capture_text,rows,journals,status)
        assert result['reacquisitions']==len(episodes)-1
        if mode=='loss_then_supported':
            assert result['native_results_per_completed_run']==1500
            with pytest.raises(AssertionError):
                review_epochs(capture_text,rows,journals,status,
                              native_results_per_completed_run=7500)
            with pytest.raises(ValueError,match='positive integer'):
                review_epochs(capture_text,rows,journals,status,
                              native_results_per_completed_run=0)
            source_lost_rows=copy.deepcopy(rows);source_lost_status=dict(status)
            source_lost_terminal=[r for r in source_lost_rows if r['kind']=='native_terminal'][-1]
            source_lost_terminal['result']=-3;source_lost_terminal['configured']+=7
            source_lost_status['native_completed_runs']=0
            source_lost=review_epochs(capture_text,source_lost_rows,journals,source_lost_status)
            assert source_lost['episodes'][-1]['controller_result']==-3
        for mutation in ('missing_episode','wrong_epoch','reset_budget','wrong_total','wrong_pair','uncleared_loss'):
            altered_rows=copy.deepcopy(rows);altered_status=dict(status);altered_journals=dict(journals)
            if mutation=='missing_episode': altered_journals.pop('native-1.journal')
            if mutation=='wrong_epoch':
                next(r for r in altered_rows if r['kind']=='native_terminal')['epoch']+=1
            if mutation=='reset_budget':
                next(r for r in altered_rows if r['kind']=='reacquisition')['attempts_used']=0
            if mutation=='wrong_total': altered_status['native_results']-=1
            if mutation=='wrong_pair':
                next(r for r in altered_rows if r['kind']=='native_coarse_iq')['native_episode']+=1
            if mutation=='uncleared_loss':
                next(r for r in altered_rows if r['kind']=='native_terminal')['result']=-6
            with pytest.raises((AssertionError,ValueError)):
                review_epochs(capture_text,altered_rows,altered_journals,altered_status)
