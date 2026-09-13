"""Blind ARM coarse proposals against independent full-grid integer math."""
import ctypes as C
import math
from pathlib import Path
import subprocess

import numpy as np
import pytest

from tools.starlink_glrt_coarse_replay import expected_candidates

ROOT = Path(__file__).resolve().parents[2]
POLL = C.CFUNCTYPE(C.c_int,C.c_void_p)


class Peak(C.Structure):
    _fields_ = [(n,C.c_uint32) for n in ("epoch","frequency","score")]


class Workspace(C.Structure):
    _fields_ = [("grid",(C.c_uint32*3333)*11),("peaks",Peak*8),
                ("completed_epochs",C.c_uint32),("count",C.c_uint32)]


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    root = tmp_path_factory.mktemp("cpu-coarse")
    subprocess.run(["cc","-O2","-std=c99","-Wall","-Wextra","-Werror","-shared","-fPIC",
                    str(ROOT/"tools/glrt_cpu_coarse.c"),"-lm","-o",str(root/"coarse.so")],
                   check=True,capture_output=True)
    lib = C.CDLL(str(root/"coarse.so"))
    lib.glrt_cpu_coarse_search.argtypes = [C.POINTER(Workspace),C.c_void_p,C.c_void_p,POLL,C.c_void_p]
    lib.glrt_cpu_coarse_grid.argtypes = [C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,
                                        C.POINTER(C.c_uint32),POLL,C.c_void_p]
    lib.glrt_cpu_coarse_select.argtypes = [C.POINTER(Workspace),POLL,C.c_void_p]
    return lib


def bank():
    packed = [int(s,16) for s in (ROOT/"hdl/library/starlink_glrt/coarse_upper_q9.mem").read_text().split()]
    coefficients = np.zeros((12,11,11,2),dtype=np.int16)
    for symbol in range(12):
        for f in range(11):
            for tap in range(11):
                word = packed[(symbol*2+f//6)*11+tap]>>(24*(f%6))
                for lane in range(2):
                    v = (word>>(12*lane))&4095
                    coefficients[symbol,f,tap,lane] = v-4096 if v&2048 else v
    return coefficients


def integer_grid(iq, coefficients):
    totals = np.zeros((11,3333),dtype=np.uint64)
    support = np.zeros(3333,dtype=np.uint32)
    iq = iq.astype(np.int64)
    for symbol in range(12):
        for frame_offset in (0,3333,6667,10000,13333):
            start = 22+286*symbol+frame_offset
            count = min(3333,14000-start-10)
            if count<=0: continue
            indexes = start+np.arange(count)[:,None]+np.arange(11)
            values = iq[indexes]
            energy = np.sum(values*values,axis=(1,2))
            support[:count] += 1
            for frequency in range(11):
                c = coefficients[symbol,frequency].astype(np.int64)
                re = np.sum(values[:,:,0]*c[:,0]+values[:,:,1]*c[:,1],axis=1)
                im = np.sum(values[:,:,1]*c[:,0]-values[:,:,0]*c[:,1],axis=1)
                # Python isqrt is independent of the C floating seed/correction.
                numerator = [math.isqrt(int(a)**2+int(b)**2) for a,b in zip(re,im)]
                denominator = [math.isqrt(int(e)*int(np.sum(c*c))) for e in energy]
                totals[frequency,:count] += np.asarray([
                    min(65536,(a<<16)//b) if b else 0 for a,b in zip(numerator,denominator)],dtype=np.uint64)
    return (totals//support).astype(np.uint32)


@pytest.mark.parametrize("signal", ["random","rails","zero","full_scale_coefficients"])
def test_every_grid_value_and_selected_peak_matches_independent_math(api, signal):
    iq = np.random.default_rng(700600).integers(-32768,32768,(14000,2),dtype=np.int16)
    coefficients = bank()
    if signal == "rails": iq[:] = -32768
    elif signal == "zero": iq[:] = 0
    elif signal == "full_scale_coefficients":
        iq[:]=[-32768,32767]
        coefficients[:]=[-2048,2047]
    w = Workspace()
    assert api.glrt_cpu_coarse_search(C.byref(w),iq.ctypes.data,coefficients.ctypes.data,POLL(lambda _:0),None) == 0
    expected = integer_grid(iq,coefficients)
    np.testing.assert_array_equal(np.ctypeslib.as_array(w.grid),expected)
    peaks = expected_candidates(expected)
    assert w.completed_epochs == 3333 and w.count == len(peaks)
    assert [(p.epoch,p.frequency,p.score) for p in w.peaks[:w.count]] == [p[:3] for p in peaks]


@pytest.mark.parametrize("when", [1,2,9,211])
def test_cancel_or_deadline_cannot_publish_partial_grid_as_proposals(api, when):
    iq = np.ones((14000,2),dtype=np.int16)
    coefficients = bank()
    calls = 0
    def poll(_):
        nonlocal calls
        calls += 1
        return int(calls>=when)
    w = Workspace()
    assert api.glrt_cpu_coarse_search(C.byref(w),iq.ctypes.data,coefficients.ctypes.data,POLL(poll),None) == -1
    assert w.count == 0 and calls == when


def test_coefficient_range_is_checked_before_computation(api):
    iq = np.ones((14000,2),dtype=np.int16)
    coefficients = bank();coefficients[0,0,0,0] = 2048
    w = Workspace()
    assert api.glrt_cpu_coarse_search(C.byref(w),iq.ctypes.data,coefficients.ctypes.data,POLL(lambda _:0),None) == -1
    assert w.count == w.completed_epochs == 0


def test_disjoint_partitions_cannot_publish_an_incomplete_scan(api):
    iq=np.random.default_rng(8523).integers(-32768,32768,(14000,2),dtype=np.int16)
    c=bank();w=Workspace();done=C.c_uint32();check=POLL(lambda _:0)
    np.ctypeslib.as_array(w.grid)[:]=0xdeadbeef
    assert api.glrt_cpu_coarse_grid(C.byref(w),iq.ctypes.data,c.ctypes.data,1666,3333,
                                    C.byref(done),check,None)==0
    assert done.value==1667
    w.completed_epochs=done.value
    assert np.all(np.ctypeslib.as_array(w.grid)[:,:1666]==0xdeadbeef)
    assert api.glrt_cpu_coarse_select(C.byref(w),check,None)==-1 and not w.count
    assert api.glrt_cpu_coarse_grid(C.byref(w),iq.ctypes.data,c.ctypes.data,0,1666,
                                    C.byref(done),check,None)==0
    assert done.value==1666
    w.completed_epochs+=done.value
    assert api.glrt_cpu_coarse_select(C.byref(w),check,None)==0
    expected=integer_grid(iq,c)
    np.testing.assert_array_equal(np.ctypeslib.as_array(w.grid),expected)
    assert [(p.epoch,p.frequency,p.score) for p in w.peaks[:w.count]]==[
        p[:3] for p in expected_candidates(expected)]


def test_actual_two_thread_benchmark_matches_complete_serial_grid(api,tmp_path):
    binary=tmp_path/'bench'
    subprocess.run(['cc','-O2','-std=c99','-Wall','-Wextra','-Werror',
        '-DGLRT_COARSE_BENCH_PARALLEL',str(ROOT/'tools/glrt_cpu_coarse_bench.c'),
        str(ROOT/'tools/glrt_cpu_coarse.c'),'-pthread','-lm','-o',str(binary)],check=True)
    iq=np.random.default_rng(6148).integers(-32768,32768,(56000,2),dtype=np.int16)
    c=bank();c.tofile(tmp_path/'bank');iq.tofile(tmp_path/'iq')
    subprocess.run([str(binary),str(tmp_path/'bank'),str(tmp_path/'iq'),str(tmp_path/'grid')],
                   check=True,capture_output=True,timeout=10)
    grids=np.fromfile(tmp_path/'grid',dtype='<u4').reshape(4,11,3333)
    for i in range(4):
        w=Workspace();cut=iq[i*14000:(i+1)*14000]
        assert api.glrt_cpu_coarse_search(C.byref(w),cut.ctypes.data,c.ctypes.data,POLL(lambda _:0),None)==0
        np.testing.assert_array_equal(grids[i],np.ctypeslib.as_array(w.grid))


def test_dot_products_match_wide_integer_arithmetic_across_rails_and_alignments(tmp_path):
    source=tmp_path/'dot.c'; binary=tmp_path/'dot'
    source.write_text('#include "glrt_cpu_coarse.c"\n#include "cpu_coarse_dot_check.c"\n'
                      'int main(void) { return check_dot11()!=0; }\n')
    subprocess.run(['cc','-O2','-std=c99','-Wall','-Wextra','-Werror',
        '-I',str(ROOT/'tools'),'-I',str(ROOT/'tests/starlink_glrt'),str(source),
        '-lm','-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=10)
