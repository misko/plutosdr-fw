"""Causal prediction review against actual C jobs and corrupted evidence."""
import copy

import pytest

from tools.review_glrt_cpu_startup import review_startup_carrier
from .test_tracking_catchup import bootstrap, fresh, next_job, observe, Estimate


def recorded(lib,mode):
    initial=1249550 if mode=='nyquist' else 400000
    state=fresh(lib,cfo=initial);rows=[]
    for index in range(8):
        rc,frame,job,_=next_job(lib,state,0,3000000)
        assert rc==1
        predicted=(job.phase_step if job.phase_step<2**31 else job.phase_step-2**32)*2500000/2**32
        hz=initial+({'up':60,'down':-60}.get(mode,0))*index
        if mode=='bound': hz=initial if index==0 else predicted+240
        if mode=='nyquist': hz=min(1249710,initial+80*index)
        rejected=mode=='rejected' and index==1
        estimate=Estimate(0,hz-predicted,hz,.01 if rejected else .9,.91,64 if rejected else 0)
        assert observe(lib,state,frame,job,estimate)==int(not rejected)
        rows.append(dict(frame=frame,phase_step=job.phase_step,cfo_hz=hz,accepted=int(not rejected)))
    return initial,rows


@pytest.mark.parametrize('mode',['up','down','constant','rejected','bound','nyquist'])
def test_review_matches_actual_C_startup_with_guards(bootstrap,mode):
    initial,rows=recorded(bootstrap,mode)
    result=review_startup_carrier(initial,rows)
    assert result['initial_jobs_checked']==8
    if mode in ('up','down','constant'): assert result['causal_forecasts_checked']==5
    if mode=='rejected': assert result['causal_forecasts_checked']==0


@pytest.mark.parametrize('damage',['held_carrier','future_carrier','old_estimate','frame','accepted','step','nan'])
def test_review_rejects_mutated_or_noncausal_carriers(bootstrap,damage):
    initial,rows=recorded(bootstrap,'up');rows=copy.deepcopy(rows)
    if damage=='held_carrier': rows[3]['phase_step']=rows[2]['phase_step']
    if damage=='future_carrier': rows[3]['phase_step']=rows[4]['phase_step']
    if damage=='old_estimate': rows[1]['cfo_hz']+=100
    if damage=='frame': rows[2]['frame']+=1
    if damage=='accepted': rows[1]['accepted']=2
    if damage=='step': rows[0]['phase_step']=-1
    if damage=='nan': rows[3]['cfo_hz']=float('nan')
    with pytest.raises(AssertionError):review_startup_carrier(initial,rows)


def test_current_estimate_only_affects_the_next_prediction(bootstrap):
    initial,rows=recorded(bootstrap,'up');changed=copy.deepcopy(rows)
    changed[3]['cfo_hz']+=100
    # The current NCO is independent of the estimate measured at that NCO.
    assert review_startup_carrier(initial,changed[:4])==review_startup_carrier(initial,rows[:4])
    with pytest.raises(AssertionError):review_startup_carrier(initial,changed[:5])
