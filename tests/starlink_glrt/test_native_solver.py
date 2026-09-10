"""Portable radio solver vs an independent dense real least-squares fit."""
import ctypes
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tools.generate_glrt_native_gram import generate
from tools.starlink_glrt_native_replay import coefficients
from tools.starlink_glrt_schedule_abi import MAGIC, RATE, SAMPLES

ROOT = Path(__file__).resolve().parents[2]
BANK = ROOT/"hdl/library/starlink_glrt/native_cubic_60000000_upper.mem"


class Estimate(ctypes.Structure):
    _fields_ = [(name,ctypes.c_double) for name in (
        "delay", "residual", "cfo", "coherence", "linearized_coherence")]+[("rejection",ctypes.c_uint32)]


@pytest.fixture(scope="module")
def solver(tmp_path_factory):
    root = tmp_path_factory.mktemp("native-solver")
    # Expose only the integer-centering helper for its carry/cancellation test.
    (root/"wrapper.c").write_text('#include "glrt_native_solver.c"\n'
        'double exact_center(const uint32_t *r,const uint32_t *t) {return centered(r,t);}\n')
    subprocess.run(["cc","-std=c99","-O2","-Wall","-Wextra","-Werror","-shared","-fPIC",
                    "-I",str(ROOT/"tools"),str(root/"wrapper.c"),"-lm","-o",str(root/"solver.so")],check=True)
    lib = ctypes.CDLL(str(root/"solver.so"))
    lib.glrt_native_solve.argtypes = [ctypes.POINTER(ctypes.c_uint32),ctypes.POINTER(Estimate)]
    lib.glrt_native_solve.restype = ctypes.c_int
    lib.exact_center.argtypes = [ctypes.POINTER(ctypes.c_uint32),ctypes.POINTER(ctypes.c_uint32)]
    lib.exact_center.restype = ctypes.c_double
    return lib


@pytest.fixture(scope="module")
def model():
    raw = np.asarray(coefficients(BANK.read_bytes()),dtype=np.int64)
    ref = raw[:,0]+1j*raw[:,1]
    derivative = raw[:,2]+1j*raw[:,3]
    t = (2*np.arange(SAMPLES)-(SAMPLES-1))/2/RATE
    return np.column_stack((ref,-derivative,2j*np.pi*1000*t*ref)), raw


def packed(value, n):
    return [(int(value) >> (32*k)) % 2**32 for k in range(n)]


def packet(iq, raw):
    a,b = iq[:,0],iq[:,1]
    ri,rq,di,dq = raw.T
    products = [a*ri+b*rq,b*ri-a*rq,-a*di-b*dq,a*dq-b*di]
    values = [int(p.sum()) for p in products]
    weights = SAMPLES-1-np.arange(SAMPLES)
    values += [int((weights*p).sum()) for p in products[:2]]
    values += [int((a*a+b*b).sum())]
    start = 2**60+1000
    w = [MAGIC,0,1,*packed(start,2),17,12345,SAMPLES,0]
    for value,n in zip(values,[2,2,2,2,3,3,2],strict=True):
        w += packed(value,n)
    return w+[RATE,SAMPLES,0,0,0,0,0]


def call(solver,w):
    out = Estimate()
    rc = solver.glrt_native_solve((ctypes.c_uint32*32)(*w),ctypes.byref(out))
    return rc,out


def dense_fit(basis, iq):
    y = iq[:,0]+1j*iq[:,1]
    ref = basis[:,0]
    gain = np.vdot(ref,y)/np.vdot(ref,ref)
    # Eliminate arbitrary complex gain from both derivative columns, then
    # solve the actual tall real Jacobian with SVD, not the C 2x2 formula.
    jac = gain*(basis[:,1:]-np.outer(ref,ref.conj()@basis[:,1:])/np.vdot(ref,ref))
    residual = y-gain*ref
    correction = np.linalg.lstsq(np.vstack((jac.real,jac.imag)),
                                 np.concatenate((residual.real,residual.imag)),rcond=None)[0]
    coh = abs(np.vdot(ref,y))**2/(np.vdot(ref,ref).real*np.vdot(y,y).real)
    direction = np.clip(correction,-.25,.25)
    fitted = basis@np.concatenate(([1],direction))
    improved = abs(np.vdot(fitted,y))**2/(np.vdot(fitted,fitted).real*np.vdot(y,y).real)
    return correction,coh,improved


def test_generated_gram_is_bound_to_exact_integer_reference():
    assert (ROOT/"tools/glrt_native_gram.inc").read_text() == generate(BANK.read_bytes())


@pytest.mark.parametrize("delay,cfo,phase", [(0,0,0),(.07,.06,.4),(-.09,-.08,-1.7),
    (.173,.177,2.9),(-.2,.19,1.2),(.4,0,-.7),(0,-.4,1.1)])
def test_native_moments_match_independent_dense_fit(solver,model,delay,cfo,phase):
    basis,raw = model
    rng = np.random.default_rng(981)
    values = .3*np.exp(1j*phase)*(basis@np.array([1,delay,cfo]))
    iq = np.rint(np.column_stack((values.real,values.imag))+rng.normal(0,50,(SAMPLES,2))).astype(np.int64)
    expected,coherence,improved = dense_fit(basis,iq)
    rc,estimate = call(solver,packet(iq,raw))
    assert rc == 0
    np.testing.assert_allclose([estimate.delay*1e6,estimate.residual/1000],
                               np.clip(expected,-.25,.25),atol=2e-12,rtol=0)
    assert estimate.coherence == pytest.approx(coherence,abs=2e-13)
    assert estimate.linearized_coherence == pytest.approx(improved,abs=2e-13)
    assert estimate.cfo == pytest.approx(12345*RATE/2**32+estimate.residual,abs=1e-10)
    assert estimate.rejection == (32 if np.any(abs(expected)>=.25) else 0)


@pytest.mark.parametrize("control", ["noise","tone","zero"])
def test_controls_cannot_produce_supported_updates(solver,model,control):
    _,raw = model
    if control == "noise":
        iq = np.rint(np.random.default_rng(852).normal(0,1000,(SAMPLES,2))).astype(np.int64)
    elif control == "tone":
        signal = 1000*np.exp(2j*np.pi*38171*np.arange(SAMPLES)/RATE)
        iq = np.rint(np.column_stack((signal.real,signal.imag))).astype(np.int64)
    else:
        iq = np.zeros((SAMPLES,2),dtype=np.int64)
    rc,estimate = call(solver,packet(iq,raw))
    assert rc == 0 and estimate.rejection
    assert estimate.rejection & (4 if control == "zero" else 64)


@pytest.mark.parametrize("r", [2**51-1,-2**51,2**40+1,-2**40+1,1,-1])
@pytest.mark.parametrize("offset", [-1,0,1])
def test_centered_integer_moment_preserves_low_bits_before_double_conversion(solver,r,offset):
    prefix = (r*(SAMPLES-1))//2+offset
    actual = solver.exact_center((ctypes.c_uint32*2)(*packed(r,2)),
                                 (ctypes.c_uint32*3)(*packed(prefix,3)))
    assert actual == (SAMPLES-1)*r-2*prefix


@pytest.mark.parametrize("index,value", [(0,0x474c4e31),(2,0),(7,SAMPLES-1),
    (7,SAMPLES+1),(8,1024),(10,0x100000),(19,0x20),(24,0x200000),
    (25,2500000),(26,64),(27,64),(31,1)])
def test_malformed_packet_cannot_reach_solver(solver,model,index,value):
    _,raw = model
    w = packet(np.zeros((SAMPLES,2),dtype=np.int64),raw)
    w[index] = value
    assert call(solver,w)[0] == -1


def test_faulted_partial_and_empty_observations_are_retained_without_full_gram_fit(solver,model):
    _,raw = model
    w = packet(np.zeros((SAMPLES,2),dtype=np.int64),raw)
    for count in (0,10,SAMPLES):
        w[7:9] = [count,512]
        rc,estimate = call(solver,w)
        assert rc == 0 and estimate.rejection == (1 if count==SAMPLES else 3)
        assert estimate.delay == estimate.residual == 0


def test_large_native_coordinates_and_signed_carrier_step_do_not_lose_precision(solver,model):
    basis,raw = model
    iq = np.rint(.3*np.column_stack((basis[:,0].real,basis[:,0].imag))).astype(np.int64)
    w = packet(iq,raw)
    w[6] = 2**32-12345
    rc,estimate = call(solver,w)
    assert rc == 0 and not estimate.rejection
    assert estimate.cfo == pytest.approx(-12345*RATE/2**32+estimate.residual,abs=1e-10)
    w[3:5] = packed(2**64-SAMPLES,2)
    rc,high = call(solver,w)
    assert rc == 0 and bytes(high) == bytes(estimate)
    w[3:5] = packed(2**64-SAMPLES+1,2)
    assert call(solver,w)[0] == -1
    w[3:5] = packed(1000,2)
    for step in (2**31,2**31-1):
        w[6] = step
        rc,out = call(solver,w)
        assert rc == 0 and out.rejection == 32
