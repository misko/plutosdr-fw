"""Live worker with advancing owned IQ and explicit simulated native ports.

This exercises the actual pthread/FFTW composition, not FPGA or RF accuracy.
"""
import ctypes as c
import json
import os
from pathlib import Path
import subprocess
import time

import numpy as np
import pytest

from tools.generate_glrt_tracking_gram import reference_rows
from .test_cpu_coarse import bank
from .test_tracking_seed import SOURCES
from .test_native_controller import Radio, Ports, Read, Write, Retain, Clock
from .test_tracking_controller import controller, models, pilot_moments

pytestmark = pytest.mark.fftw

WRAPPER = r'''
#define main unused_probe_main
#include "glrt_cpu_live_probe.c"
#undef main
struct test_live { struct live live; int16_t *ring; fftw_complex *fft; uint64_t end; };
const char *iio_device_get_id(const struct iio_device *d) { (void)d;return "iio:device0"; }
int iio_channel_attr_read_longlong(const struct iio_channel *c,const char *name,long long *out)
{ char text[128];if(iio_channel_attr_read(c,name,text,sizeof(text))<=0) return -1;*out=strtoll(text,NULL,10);return 0; }
void *live_new(const int16_t *refs,const int16_t *bank,const char *directory,
              const struct glrt_native_ports *ports,unsigned rate)
{
    struct test_live *t=calloc(1,sizeof(*t));struct live *s=&t->live;char path[4096];
    if(!t) abort();
    t->ring=malloc(RING*4U);t->fft=fftw_malloc(GLRT_RESOLVER_FFT*sizeof(*t->fft));
    if(!t->ring || !t->fft || pthread_mutex_init(&s->mutex,NULL)) abort();
    memcpy(s->refs,refs,sizeof(s->refs));memcpy(s->bank,bank,sizeof(s->bank));
    s->native=*ports;s->epoch=3;s->rate=rate;t->end=1000000;
    s->fft=fftw_plan_dft_1d(GLRT_RESOLVER_FFT,t->fft,t->fft,FFTW_FORWARD,FFTW_ESTIMATE|FFTW_UNALIGNED);
    if(!s->fft || glrt_tracking_iq_owner_init(&s->owner,t->ring,RING,s->epoch,t->end)) abort();
    snprintf(path,sizeof(path),"%s/worker.jsonl",directory);s->journal=fopen(path,"wx");
    snprintf(path,sizeof(path),"%s/worker.iq",directory);s->worker_iq=fopen(path,"wbx");
    snprintf(path,sizeof(path),"%s/grids",directory);s->grids=fopen(path,"wbx");
    if(!s->journal || !s->worker_iq || !s->grids) abort();
    return t;
}
int live_publish(struct test_live *t,const int16_t *iq,size_t count)
{
    int rc=glrt_tracking_iq_owner_publish(&t->live.owner,3,t->end,iq,count,t->end+count,clock_ns(NULL));
    if(!rc) t->end+=count;
    return rc;
}
void live_start(struct test_live *t)
{
    t->live.deadline_ns=clock_ns(NULL)+UINT64_C(5000000000);
    if(pthread_create(&t->live.thread,NULL,worker_thread,&t->live)) abort();
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
    struct live *s=&t->live;
    memcpy(s->scan_iq,iq,sizeof(s->scan_iq));s->coarse.count=count;
    for(unsigned k=0;k<count && k<8;k++) s->coarse.peaks[k].epoch=epochs[k];
    s->deadline_ns=clock_ns(NULL)+UINT64_C(3000000000);
    return rank_candidates(s,scores,selected);
}
void live_free_unstarted(struct test_live *t)
{
    struct live *s=&t->live;
    if(glrt_tracking_iq_owner_close(&s->owner,0) || glrt_tracking_iq_owner_destroy(&s->owner)) abort();
    fclose(s->journal);fclose(s->worker_iq);fclose(s->grids);
    fftw_destroy_plan(s->fft);fftw_free(t->fft);free(t->ring);
    if(pthread_mutex_destroy(&s->mutex)) abort();
    free(t);
}
void live_finish(struct test_live *t,uint64_t out[5])
{
    void *result=NULL;struct live *s=&t->live;
    if(pthread_join(s->thread,&result) || result) abort();
    out[0]=(uint64_t)(int64_t)s->result;out[1]=s->attempts;out[2]=s->handoffs;
    out[3]=s->controller.configured;out[4]=s->controller.sequence;
    if(glrt_tracking_iq_owner_close(&s->owner,0) || glrt_tracking_iq_owner_destroy(&s->owner)) abort();
    fclose(s->journal);fclose(s->worker_iq);fclose(s->grids);
    fftw_destroy_plan(s->fft);fftw_free(t->fft);free(t->ring);
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
    names = ["glrt_cpu_coarse.c", "glrt_cpu_seed.c", "glrt_tracking_worker.c", "glrt_tracking_live_bootstrap.c",
             "glrt_tracking_iq.c", "glrt_iq_tracking_source.c", "glrt_capture_source.c",
             "glrt_tracking_transport.c", "glrt_native_controller.c", "glrt_native_posix.c", *SOURCES]
    subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread", "-shared", "-fPIC",
        "-I", str(out), "-I", str(root/"tools"), *includes, str(out/"wrapper.c"), str(fixture/"backend.c"),
        *(str(root/"tools"/name) for name in names), *libraries, "-lfftw3", "-lm", "-o", str(out/"live.so")], check=True)
    lib = c.CDLL(str(out/"live.so"))
    lib.live_new.argtypes = [c.c_void_p, c.c_void_p, c.c_char_p, c.POINTER(Ports), c.c_uint]
    lib.live_new.restype = c.c_void_p
    lib.live_publish.argtypes = [c.c_void_p, c.c_void_p, c.c_size_t]
    lib.live_rank.argtypes = [c.c_void_p,c.c_void_p,c.c_void_p,c.c_uint,c.c_void_p,c.c_void_p]
    lib.live_free_unstarted.argtypes = [c.c_void_p]
    for name in ("live_start", "live_done", "live_stop", "live_close_source"):
        getattr(lib, name).argtypes = [c.c_void_p]
    lib.live_finish.argtypes = [c.c_void_p, c.c_void_p]
    rom = root/"hdl/library/starlink_glrt"
    refs = np.asarray([reference_rows((rom/"native_cubic_60000000_upper.mem").read_bytes(),
        (rom/"native_direct_2500000_phase4_upper_interleaved.mem").read_bytes(), 2500000, p)
        for p in range(4)], dtype=np.int16)
    return lib, refs


@pytest.mark.parametrize('mode', ['secondary_pilot', 'noise', 'zero', 'cancel', 'invalid_epoch'])
def test_original_pilot_order_matches_independent_fft(live_api, tmp_path, mode):
    lib, refs = live_api
    coefficients = bank()
    ports = Ports()
    handle = lib.live_new(refs.ctypes.data, coefficients.ctypes.data, os.fsencode(tmp_path), c.byref(ports), 60000000)
    iq = np.random.default_rng(982).integers(-100,101,(14000,2),dtype=np.int16)
    epochs = np.array([500,1023,1800,2200,2600,3000,50,3250],dtype=np.uint32)
    if mode == 'secondary_pilot':
        ref = refs[0,:,0].astype(float)+1j*refs[0,:,1]
        pilot = ref*np.exp(2j*np.pi*464356*np.arange(3300)/2500000)
        iq[1045:4345] = np.rint(np.column_stack((pilot.real,pilot.imag)))
    if mode == 'zero': iq[:]=0
    if mode == 'cancel': lib.live_stop(handle)
    if mode == 'invalid_epoch': epochs[7]=3333
    scores = np.full(8,999.,dtype=np.float64);selected=c.c_uint(999)
    try:
        rc = lib.live_rank(handle,iq.ctypes.data,epochs.ctypes.data,8,scores.ctypes.data,c.byref(selected))
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
        expected.append(max(abs(np.fft.fft(z*np.conj(ref),16384))**2)/
                        max(float(np.vdot(z,z).real*np.vdot(ref,ref).real),1))
    assert rc == 0 and selected.value == np.argmax(expected)
    np.testing.assert_allclose(scores,expected,rtol=2e-12,atol=2e-15)
    if mode == 'secondary_pilot': assert selected.value == 1


@pytest.mark.parametrize("rate,mode", [(30000000,"signal"),(60000000,"signal"),
    (60000000,"publication_lag"),(60000000,"handoff_horizon_expired"),
    (30000000,"zero"),(30000000,"cancel"),(30000000,"source_loss"),
    (30000000,"native_rejection"),(30000000,"native_retention"),(30000000,"late_handoff")])
def test_advancing_capture_worker_and_native_feedback(live_api, controller, pilot_moments, tmp_path, rate, mode):
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
    iq = np.zeros((10_000_000, 2), dtype=np.int16)
    if mode in ("signal", "publication_lag", "handoff_horizon_expired", "native_rejection", "native_retention", "late_handoff"):
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
        lib.live_stop(handle)
        out = (c.c_uint64*5)();lib.live_finish(handle, out)
    assert not radio.errors, radio.errors
    rows = [json.loads(s) for s in (tmp_path/"worker.jsonl").read_text().splitlines()]
    if mode in ("signal", "publication_lag"):
        assert list(out)[0] == 0, (list(out), rows[-3:])
        assert list(out)[2:] == [1,1500,1500]
        assert len(radio.writes("submit")) > 1 and len(radio.writes("pop")) == 1500
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
