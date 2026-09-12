"""Bounded retry proposals preserve fractional coordinates and estimate ownership."""
import ctypes as c
from fractions import Fraction
from pathlib import Path
import subprocess

import pytest

from .test_native_trend import Estimate
from .test_tracking_schedule import Job

RATE=2500000


@pytest.fixture(scope='module')
def recenter(tmp_path_factory):
    root=Path(__file__).resolve().parents[2]
    out=tmp_path_factory.mktemp('tracking-recenter')/'recenter.so'
    command=['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
        *(str(root/'tools'/name) for name in ['glrt_tracking_recenter.c','glrt_tracking_schedule.c','glrt_native_solver.c']),
        '-lm','-o',str(out)]
    result=subprocess.run(command,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    library=c.CDLL(str(out))
    function=library.glrt_tracking_recenter_propose_2500000
    function.argtypes=[c.c_uint,c.POINTER(Job),c.POINTER(Job),c.POINTER(Estimate),c.POINTER(Job)]
    function.restype=c.c_int
    return function


def frequency(job):
    step=job.phase_step if job.phase_step<2**31 else job.phase_step-2**32
    return step*RATE/2**32


def estimate(job, *, delay=100e-9, residual=-100):
    return Estimate(delay,residual,frequency(job)+residual,.04,.07,64)


def call(fn,origin,previous,e,attempts=1):
    out=Job(999,999,999)
    rc=fn(attempts,c.byref(origin),c.byref(previous),c.byref(e),c.byref(out))
    if rc<=0:assert bytes(out)==bytes(Job())
    return rc,out


@pytest.mark.parametrize('start',[1000,2**60+3,2**64-4000])
@pytest.mark.parametrize('phase',range(4))
@pytest.mark.parametrize('delay_ns',[-199,-100,-51,0,51,100,199])
@pytest.mark.parametrize('cfo',[-1100000,400000])
def test_known_local_corrections_keep_absolute_low_bits(recenter,start,phase,delay_ns,cfo):
    job=Job(start,round(cfo/RATE*2**32)%2**32,phase)
    e=estimate(job,delay=delay_ns*1e-9)
    rc,out=call(recenter,job,job,e)
    assert rc==1
    truth=Fraction(start)+Fraction(phase,4)+Fraction(delay_ns*RATE,10**9)
    assert Fraction(out.start)+Fraction(out.reference_phase,4)==Fraction(round(truth*4),4)
    assert frequency(out)==pytest.approx(e.cfo,abs=.0004)


@pytest.mark.parametrize('kind',['attempt_zero','attempt_four','phase','moved_start','moved_carrier',
    'coherence_flag','cfo_association','delay_outside','cfo_outside','nan_delay','nan_coherence','unknown_flag'])
def test_invalid_inputs_cannot_create_a_retry(recenter,kind):
    origin=Job(1000000,123456789,0);last=Job.from_buffer_copy(bytes(origin));e=estimate(last)
    attempts=1
    if kind=='attempt_zero':attempts=0
    if kind=='attempt_four':attempts=4
    if kind=='phase':last.reference_phase=4
    if kind=='moved_start':last.start+=1
    if kind=='moved_carrier':last.phase_step+=1
    if kind=='coherence_flag':e.coherence=.05
    if kind=='cfo_association':e.cfo+=1
    if kind=='delay_outside':e.delay=250e-9
    if kind=='cfo_outside':e.residual=250;e.cfo=frequency(last)+250
    if kind=='nan_delay':e.delay=float('nan')
    if kind=='nan_coherence':e.linearized=float('nan')
    if kind=='unknown_flag':e.rejection=128
    assert call(recenter,origin,last,e,attempts)[0]==-1


@pytest.mark.parametrize('kind',['supported','outside_local','zero_energy','no_gain','same_job','exhausted'])
def test_no_retry_does_not_relax_any_acceptance_gate(recenter,kind):
    job=Job(1000000,123456789,0);e=estimate(job);attempts=1
    if kind=='supported':e.rejection=0;e.coherence=.9;e.linearized=.95
    if kind=='outside_local':e.rejection=96
    if kind=='zero_energy':e.rejection=4
    if kind=='no_gain':e.linearized=e.coherence
    if kind=='same_job':e.delay=e.residual=0;e.cfo=frequency(job)
    if kind=='exhausted':attempts=3
    assert call(recenter,job,job,e,attempts)[0]==0


def test_two_corrections_are_bounded_and_input_output_aliasing_is_safe(recenter):
    origin=Job(2**60+99,123456789,3);original=bytes(origin)
    rc,first=call(recenter,origin,origin,estimate(origin,delay=199e-9,residual=200))
    assert rc==1 and bytes(origin)==original
    e=estimate(first,delay=199e-9,residual=200)
    assert recenter(2,c.byref(origin),c.byref(first),c.byref(e),c.byref(first))==1
    assert abs((first.start-origin.start)*4+first.reference_phase-origin.reference_phase)<=6
    assert abs(frequency(first)-frequency(origin))<=500.002
    assert call(recenter,origin,first,estimate(first),3)[0]==0
    first.start+=3
    assert call(recenter,origin,first,estimate(first),2)[0]==-1
