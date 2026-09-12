"""Portable bootstrap IQ arithmetic against the independent Python/ROM oracle."""
import ctypes as c
from pathlib import Path
import subprocess

import numpy as np
import pytest

from tools.generate_glrt_tracking_gram import reference_rows
from tools.starlink_glrt_native_replay import rotate
from .test_tracking_solver import Moments, moments

ROOT = Path(__file__).parents[2]


@pytest.fixture(scope='module')
def collector(tmp_path_factory):
    output = tmp_path_factory.mktemp('tracking-iq')/'iq.so'
    subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
        str(ROOT/'tools/glrt_tracking_iq.c'),'-o',str(output)],check=True)
    lib = c.CDLL(str(output))
    call = lib.glrt_tracking_iq_moments_2500000
    call.argtypes = [c.POINTER(c.c_int16),c.POINTER(c.c_int16),c.c_size_t,c.c_uint64,
                     c.c_uint32,c.c_uint32,c.POINTER(Moments)]
    call.restype = c.c_int
    return call


@pytest.fixture(scope='module')
def references():
    bank = ROOT/'hdl/library/starlink_glrt'
    cubic = (bank/'native_cubic_60000000_upper.mem').read_bytes()
    direct = (bank/'native_direct_2500000_phase4_upper_interleaved.mem').read_bytes()
    return [np.asarray(reference_rows(cubic,direct,2500000,phase),dtype=np.int16) for phase in range(4)]


def pointer(array):
    return array.ctypes.data_as(c.POINTER(c.c_int16))


@pytest.mark.parametrize('reference_phase',range(4))
@pytest.mark.parametrize('kind',['random','rails','zero','extreme_reference'])
def test_all_words_match_full_pilot_integer_oracle(collector,references,reference_phase,kind):
    rng = np.random.default_rng(918750+reference_phase)
    iq = rng.integers(-32768,32768,(3300,2),dtype=np.int16)
    ref = references[reference_phase]
    if kind=='rails':
        iq = rng.choice(np.array([-32768,-32767,-1,0,1,32766,32767],dtype=np.int16),(3300,2))
    elif kind=='zero':
        iq[:] = 0
    elif kind=='extreme_reference':
        ref = rng.choice(np.array([-32768,32767],dtype=np.int16),(3300,4))
    for seed,step in ((0,0),(0x3fffffff,0x80000001),(0xc0000000,0xffffffff),
                      (int(rng.integers(2**32)),int(rng.integers(2**32)))):
        out = Moments()
        assert collector(pointer(iq),pointer(ref),3300,2**60+3,seed,step,c.byref(out))==0
        rotated = np.asarray([rotate(int(i),int(q),seed+n*step) for n,(i,q) in enumerate(iq)],dtype=np.int64)
        expected = moments(rotated,ref.astype(np.int64))
        assert list(out.words) == list(expected.words)
        assert (out.start,out.count,out.fault,out.step)==(2**60+3,3300,0,step)


@pytest.mark.parametrize('damage',['iq','reference','out','short','long','wrap'])
def test_malformed_input_never_publishes_partial_moments(collector,references,damage):
    iq = np.zeros((3300,2),dtype=np.int16)
    out = Moments(123,3300,7,456,(c.c_uint32*16)(*range(16)))
    before = bytes(out)
    count = 3299 if damage=='short' else 3301 if damage=='long' else 3300
    start = 2**64-3299 if damage=='wrap' else 123
    assert collector(None if damage=='iq' else pointer(iq),
        None if damage=='reference' else pointer(references[0]),count,start,0,1,
        None if damage=='out' else c.byref(out))==-1
    assert bytes(out)==before
