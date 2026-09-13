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
const char *iio_device_get_id(const struct iio_device *d) { (void)d;return "iio:device0"; }
int iio_channel_attr_read_longlong(const struct iio_channel *c,const char *n,long long *out)
{ (void)c;(void)n;(void)out;return -1; }
int iio_channel_attr_write_longlong(const struct iio_channel *c,const char *n,long long out)
{ (void)c;(void)n;(void)out;return -1; }
static int simulated_child(int argc,char **argv) {
    if(argc!=6) return 9;
    printf("retained child output\n");fprintf(stderr,"retained child diagnostics\n");
    if(!strcmp(argv[1],"fail")) return 1;
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
    return lib


@pytest.mark.parametrize('mode',['pass','fail','hang','existing'])
def test_child_is_reaped_before_return_and_evidence_is_never_overwritten(probe,tmp_path,mode):
    if mode=='existing':
        (tmp_path/'visit-0').mkdir();(tmp_path/'visit-0/stdout.json').write_text('preserved')
    assert probe.exercise_child(os.fsencode(tmp_path),mode.encode())==(0 if mode=='pass' else -1)
    if mode=='existing': assert (tmp_path/'visit-0/stdout.json').read_text()=='preserved'
    elif mode!='hang':
        assert (tmp_path/'visit-0/stdout.json').read_text()=='retained child output\n'
        assert (tmp_path/'visit-0/stderr.txt').read_text()=='retained child diagnostics\n'
