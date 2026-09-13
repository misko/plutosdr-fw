"""Actual fork/wait and evidence isolation; mock child performs no IIO calls."""
import ctypes as c
import os
from pathlib import Path
import subprocess

import pytest

from .test_tracking_seed import SOURCES

pytestmark=pytest.mark.fftw

WRAPPER=r'''
#include "glrt_cpu_visit_probe.c"
int inspect_idle_words(const uint32_t w[24],uint32_t rate) { return visit_idle_snapshot(w,rate); }
int loss_disposition(unsigned fault) {
    struct live s={0};s.done=1;s.result=GLRT_NATIVE_ACQUISITION_LOST;s.native_clean_loss=1;
    interrupted=fault==1;
    if(fault==2) s.done=0;
    if(fault==3) s.started=1;
    if(fault==4) s.observer_started=1;
    if(fault==5) s.result=GLRT_NATIVE_RETENTION_ERROR;
    if(fault==6) s.native_clean_loss=0;
    if(fault==9) s.stop=1;
    return live_visit_clean_loss(fault==8 ? NULL : &s,fault!=7);
}
const char *iio_device_get_id(const struct iio_device *d) { (void)d;return "iio:device0"; }
int iio_channel_attr_read_longlong(const struct iio_channel *c,const char *n,long long *out)
{ (void)c;(void)n;(void)out;return -1; }
int iio_channel_attr_write_longlong(const struct iio_channel *c,const char *n,long long out)
{ (void)c;(void)n;(void)out;return -1; }
static int simulated_child(int argc,char **argv) {
    if(argc!=6) return 9;
    printf("retained child output\n");fprintf(stderr,"retained child diagnostics\n");
    if(!strcmp(argv[1],"fail")) return 1;
    if(!strcmp(argv[1],"clean_loss")) return LIVE_VISIT_CLEAN_LOSS_EXIT;
    if(!strcmp(argv[1],"unknown")) return 4;
    if(!strcmp(argv[1],"signal")) { raise(SIGKILL);return 0; }
    if(!strcmp(argv[1],"hang")) {
        signal(SIGTERM,SIG_IGN);
        while(1) pause();
    }
    return 0;
}
int exercise_child(const char *directory,const char *mode) {
    char *args[]={"probe",(char *)mode,"serial","bank","refs",(char *)directory};
    struct visit_context context={.args=args,.probe_main=simulated_child};
    uint64_t budget=!strcmp(mode,"hang") ? UINT64_C(100000000) : UINT64_C(2000000000);
    interrupted=0;
    int rc=visit_child(&context,0,clock_ns(NULL)+budget),status;
    if(waitpid(-1,&status,WNOHANG)!=-1 || errno!=ECHILD) return 99;
    return rc;
}
'''


@pytest.fixture(scope='module')
def probe(tmp_path_factory):
    root=Path(__file__).resolve().parents[2];out=tmp_path_factory.mktemp('visit-child')
    fixture=root/'tests/starlink_glrt/iio_probe_fixture'
    (out/'iio.h').write_text((fixture/'iio.h').read_text()+
        '\nconst char *iio_device_get_id(const struct iio_device *);\n'
        'int iio_channel_attr_read_longlong(const struct iio_channel *,const char *,long long *);\n'
        'int iio_channel_attr_write_longlong(const struct iio_channel *,const char *,long long);\n')
    (out/'wrapper.c').write_text(WRAPPER)
    prefix=os.environ.get('GLRT_FFTW_PREFIX')
    include=['-I',str(Path(prefix)/'include')] if prefix else []
    libraries=['-L',str(Path(prefix)/'lib'),'-Wl,-rpath,'+str(Path(prefix)/'lib')] if prefix else []
    names=['glrt_tracking_visit.c','glrt_cpu_coarse.c','glrt_cpu_seed.c','glrt_tracking_worker.c',
        'glrt_tracking_live_bootstrap.c','glrt_tracking_observer.c','glrt_tracking_iq.c',
        'glrt_iq_tracking_source.c','glrt_capture_source.c','glrt_tracking_transport.c',
        'glrt_native_controller.c','glrt_native_posix.c',*SOURCES]
    subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-pthread','-shared','-fPIC',
        '-I',str(out),'-I',str(root/'tools'),*include,str(out/'wrapper.c'),str(fixture/'backend.c'),
        *(str(root/'tools'/name) for name in names),*libraries,'-lfftw3','-lm','-o',str(out/'visit.so')],check=True)
    lib=c.CDLL(str(out/'visit.so'));lib.exercise_child.argtypes=[c.c_char_p,c.c_char_p]
    lib.inspect_idle_words.argtypes=[c.POINTER(c.c_uint32),c.c_uint32]
    return lib


@pytest.mark.parametrize('mode',['pass','fail','hang','existing','clean_loss','unknown','signal'])
def test_child_is_reaped_before_return_and_evidence_is_never_overwritten(probe,tmp_path,mode):
    if mode=='existing':
        (tmp_path/'visit-0').mkdir();(tmp_path/'visit-0/stdout.json').write_text('preserved')
    assert probe.exercise_child(os.fsencode(tmp_path),mode.encode())==({'pass':0,'clean_loss':1}.get(mode,-1))
    if mode=='existing': assert (tmp_path/'visit-0/stdout.json').read_text()=='preserved'
    elif mode not in ('hang','signal'):
        assert (tmp_path/'visit-0/stdout.json').read_text()=='retained child output\n'
        assert (tmp_path/'visit-0/stderr.txt').read_text()=='retained child diagnostics\n'


@pytest.mark.parametrize('fault',range(10))
def test_clean_loss_requires_terminal_joined_native_provenance(probe,fault):
    assert probe.loss_disposition(fault)==int(fault==0)


@pytest.mark.parametrize('rate',[30000000,60000000])
@pytest.mark.parametrize('epoch',[0,1,7])
@pytest.mark.parametrize('mode',['idle','boot_drops','active','fault','configured','wrong_rate','unread'])
def test_only_epoch_zero_can_have_pre_acquisition_drop_counters(probe,rate,epoch,mode):
    words=(c.c_uint32*24)();words[2]=epoch;words[20]=rate
    words[0]=0x474c5431;words[1]=1;words[21]=rate*33//25000;words[22]=0xb04a2fab;words[23]=1
    if mode=='boot_drops': words[18]=4;words[19]=5413144
    if mode=='active': words[5]=16
    if mode=='fault': words[6]=1
    if mode=='configured': words[7]=1
    if mode=='wrong_rate': words[20]=2500000
    if mode=='unread': words[9]=1
    assert probe.inspect_idle_words(words,rate)==int(mode=='idle' or (mode=='boot_drops' and epoch==0))
