"""Rate/phase-bound radio fits against a dense independent real SVD oracle."""
import ctypes

import numpy as np
import pytest

from tools.generate_glrt_tracking_gram import (
    DIRECT_SHA256,
    PROFILES,
    generate,
    reference_rows,
)
from tools.starlink_glrt_native_replay import BANK_SHA256

from . import test_native_solver
from .test_native_solver import BANK, ROOT, Estimate, dense_fit, packed

native_solver = test_native_solver.solver

DIRECT = ROOT/"hdl/library/starlink_glrt/native_direct_2500000_phase4_upper_interleaved.mem"


class Profile(ctypes.Structure):
    _fields_ = [(name,ctypes.c_uint32) for name in ("rate","samples","phase","phases")]+[
        ("reference_delay",ctypes.c_double),("bank",ctypes.c_char_p)]


class Moments(ctypes.Structure):
    _fields_ = [("start",ctypes.c_uint64)]+[
        (name,ctypes.c_uint32) for name in ("count","fault","step")]+[
        ("words",ctypes.c_uint32*16)]


@pytest.fixture(scope="module")
def solver(native_solver):
    native_solver.glrt_tracking_profile_get.argtypes = [ctypes.c_uint32,ctypes.c_uint32]
    native_solver.glrt_tracking_profile_get.restype = ctypes.POINTER(Profile)
    native_solver.glrt_tracking_solve.argtypes = [ctypes.c_uint32,ctypes.c_uint32,
        ctypes.POINTER(Moments),ctypes.POINTER(Estimate)]
    native_solver.glrt_tracking_solve.restype = ctypes.c_int
    return native_solver


@pytest.fixture(scope="module")
def models():
    cubic, direct = BANK.read_bytes(), DIRECT.read_bytes()
    result = {}
    for rate,phase in PROFILES:
        raw = np.asarray(reference_rows(cubic,direct,rate,phase),dtype=np.int64)
        ref = raw[:,0]+1j*raw[:,1]
        derivative = raw[:,2]+1j*raw[:,3]
        t = (2*np.arange(len(raw))-(len(raw)-1))/2/rate
        result[rate,phase] = np.column_stack((ref,-derivative,2j*np.pi*1000*t*ref)),raw
    return result


def moments(iq, raw):
    count = len(raw)
    a,b = iq.T
    ri,rq,di,dq = raw.T
    products = [a*ri+b*rq,b*ri-a*rq,-a*di-b*dq,a*dq-b*di]
    values = [int(p.sum()) for p in products]
    weights = count-1-np.arange(count)
    values += [int((weights*p).sum()) for p in products[:2]]
    values += [int((a*a+b*b).sum())]
    words = []
    for value,n in zip(values,(2,2,2,2,3,3,2),strict=True):
        words.extend(packed(value,n))
    return Moments(2**60+1000,count,0,2**32-12345,(ctypes.c_uint32*16)(*words))


def call(solver, rate, phase, data):
    # A malformed call must invalidate this deliberately stale supported fit.
    out = Estimate(123,456,789,1,1,0)
    rc = solver.glrt_tracking_solve(rate,phase,ctypes.byref(data) if data is not None else None,
                                    ctypes.byref(out))
    return rc,out


def test_generated_bases_are_bound_to_the_actual_roms():
    assert (ROOT/"tools/glrt_tracking_gram.inc").read_text() == generate(BANK.read_bytes(),DIRECT.read_bytes())
    with pytest.raises(ValueError,match="pinned"):
        generate(BANK.read_bytes(),DIRECT.read_bytes()+b"\n")


@pytest.mark.parametrize("rate,phase", PROFILES)
def test_profile_has_correct_rate_support_reference_phase_and_bank(solver,rate,phase):
    profile = solver.glrt_tracking_profile_get(rate,phase).contents
    assert (profile.rate,profile.samples,profile.phase,profile.phases) == (
        rate,round(rate*.00132),phase,4 if rate==2500000 else 1)
    assert profile.reference_delay == phase/(rate*profile.phases)
    assert profile.bank.decode() == (DIRECT_SHA256 if rate==2500000 else BANK_SHA256)


@pytest.mark.parametrize("rate,phase", PROFILES)
@pytest.mark.parametrize("delay,cfo,angle", [(.07,.06,.4),(-.09,-.08,-1.7),(.173,.177,2.9),(.4,0,-.7)])
def test_multirate_moments_match_the_dense_nuisance_projected_fit(solver,models,rate,phase,delay,cfo,angle):
    basis,raw = models[rate,phase]
    signal = .3*np.exp(1j*angle)*(basis@np.array([1,delay,cfo]))
    iq = np.rint(np.column_stack((signal.real,signal.imag))+
        np.random.default_rng(981).normal(0,50,(len(raw),2))).astype(np.int64)
    expected,coherence,improved = dense_fit(basis,iq)
    data = moments(iq,raw)
    rc,out = call(solver,rate,phase,data)
    assert rc == 0
    np.testing.assert_allclose([out.delay*1e6,out.residual/1000],np.clip(expected,-.25,.25),atol=2e-12,rtol=0)
    assert out.coherence == pytest.approx(coherence,abs=2e-13)
    assert out.linearized_coherence == pytest.approx(improved,abs=2e-13)
    assert out.cfo == pytest.approx(-12345*rate/2**32+out.residual,abs=1e-10)
    assert out.rejection == (32 if np.any(abs(expected)>=.25) else 0)


@pytest.mark.parametrize("rate,phase", PROFILES)
@pytest.mark.parametrize("kind", ["noise","tone","zero"])
def test_controls_do_not_produce_supported_multirate_updates(solver,models,rate,phase,kind):
    _,raw = models[rate,phase]
    if kind=="noise":
        iq = np.rint(np.random.default_rng(852).normal(0,1000,(len(raw),2))).astype(np.int64)
    elif kind=="tone":
        values = 1000*np.exp(2j*np.pi*38171*np.arange(len(raw))/rate)
        iq = np.rint(np.column_stack((values.real,values.imag))).astype(np.int64)
    else:
        iq = np.zeros((len(raw),2),dtype=np.int64)
    rc,out = call(solver,rate,phase,moments(iq,raw))
    assert rc == 0 and out.rejection & (4 if kind=="zero" else 64)


@pytest.mark.parametrize("rate,phase", [(0,0),(25000000,0),(2500000,4),(5000000,1),(15000000,1)])
def test_unknown_profile_never_leaves_a_stale_fit(solver,rate,phase):
    assert not solver.glrt_tracking_profile_get(rate,phase)
    rc,out = call(solver,rate,phase,Moments())
    assert rc == -1 and out.rejection == 1 and out.delay == out.residual == out.cfo == 0


@pytest.mark.parametrize("rate", [2500000,5000000,15000000,30000000,60000000])
@pytest.mark.parametrize("negative", [False,True])
@pytest.mark.parametrize("offset", [-1,0,1])
def test_centered_prefix_preserves_low_bits_at_each_accumulator_width(solver,rate,negative,offset):
    count = round(rate*.00132)
    bits = (count-1).bit_length()
    ref = -(2**(34+bits)) if negative else 2**(34+bits)-1
    prefix = (ref*(count-1))//2+offset
    actual = solver.exact_center_count((ctypes.c_uint32*2)(*packed(ref,2)),
        (ctypes.c_uint32*3)(*packed(prefix,3)),count)
    assert actual == (count-1)*ref-2*prefix


@pytest.mark.parametrize("rate,phase", PROFILES)
def test_narrow_accumulators_and_partial_counts_are_validated(solver,models,rate,phase):
    _,raw = models[rate,phase]
    zero = moments(np.zeros((len(raw),2),dtype=np.int64),raw)
    bits = (len(raw)-1).bit_length()
    for first,width,slots in ((0,35+bits,2),(2,35+bits,2),(4,35+bits,2),(6,35+bits,2),
                              (8,35+2*bits,3),(11,35+2*bits,3),(14,36+bits,2)):
        bad = Moments.from_buffer_copy(zero)
        # A bit outside the exact RTL width is malformed even in a 96-bit slot.
        for k,value in enumerate(packed(1 << width,slots)):
            bad.words[first+k] = value
        rc,out = call(solver,rate,phase,bad)
        assert rc == -1 and out.rejection == 1
    for count in (0,10,len(raw)):
        partial = Moments.from_buffer_copy(zero)
        partial.count,partial.fault = count,1
        rc,out = call(solver,rate,phase,partial)
        assert rc == 0 and out.rejection == (1 if count==len(raw) else 3)
    bad = Moments.from_buffer_copy(zero)
    bad.start = 2**64-len(raw)+1
    assert call(solver,rate,phase,bad)[0] == -1
    bad = Moments.from_buffer_copy(zero)
    bad.fault = 256
    assert call(solver,rate,phase,bad)[0] == -1
    bad = Moments.from_buffer_copy(zero)
    bad.count -= 1
    assert call(solver,rate,phase,bad)[0] == -1
    assert call(solver,rate,phase,None)[0] == -1
