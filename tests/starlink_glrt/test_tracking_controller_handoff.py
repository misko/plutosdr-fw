"""Transferred causal history survives controller admission, journaling and recovery."""
import ctypes as c
from fractions import Fraction
import struct

import pytest

from tools.starlink_glrt_native_journal import records, review as legacy_review
from tools.starlink_glrt_tracking_handoff import decode
from tools.starlink_glrt_tracking_journal import recover, review

from . import test_tracking_controller as existing
from . import test_tracking_trend as trend
from .test_native_controller import Ports, Radio
from .test_native_journal import Port, journal, retained
from .test_tracking_schedule import TrackingBatch

controller=existing.controller
models=existing.models
pilot_moments=existing.pilot_moments


@pytest.fixture(scope="module")
def handoff_api(controller):
    trend.core.__wrapped__(controller)
    controller.glrt_tracking_controller_init_handoff.argtypes=[c.c_void_p,c.POINTER(Ports),
        c.POINTER(TrackingBatch),c.POINTER(trend.TrackingTrend),c.c_uint32,c.c_uint32,c.c_double]
    controller.glrt_tracking_controller_refresh_handoff.argtypes=[
        c.c_void_p,c.POINTER(trend.TrackingTrend)]
    return controller


def prepare(lib,pilot_moments,rate=2500000,*,first=600,wrapped=False,frames=128,initialize=True):
    radio=Radio(lib,pilot_moments,frames=frames,tracking_rate=rate)
    history=trend.fresh(lib,rate)
    points=range(first-129,first-9) if wrapped else range(first-100,first-9,9)
    anchor=radio.origin
    for frame in points:
        relative=frame-points.start
        origin=Fraction(anchor)+relative*(Fraction(rate,750)+Fraction(1,100))
        assert trend.observe(lib,history,frame,origin,100000+1000*relative/750)==1
    rc,batch,_=trend.predict(lib,history,first,8)
    assert rc==0
    radio.seed=batch.prediction
    radio.origin=radio.latest=batch.prediction.start-rate//200
    if initialize:
        assert lib.glrt_tracking_controller_init_handoff(radio.state,c.byref(radio.ports),
            c.byref(batch),c.byref(history),first,frames,2)==0
    return radio,history,batch


def extend_from_prediction(lib,history,batch,first,*frames):
    refreshed=trend.TrackingTrend.from_buffer_copy(bytes(history))
    p=batch.prediction
    for frame in frames:
        origin=Fraction(p.start*65536+p.fraction+(frame-first)*p.period,65536)
        phase=(p.step+(frame-first)*p.delta)%(2**48)
        if phase>=2**47: phase-=2**48
        assert trend.observe(lib,refreshed,frame,origin,Fraction(phase*batch.rate,2**48))==1
    return refreshed


@pytest.mark.parametrize("rate", [2500000,5000000,15000000])
@pytest.mark.parametrize("first,wrapped", [(600,False),(1000000,True)])
def test_history_drives_continuation_before_new_measurements_and_preserves_ordinals(
        handoff_api,pilot_moments,rate,first,wrapped):
    radio,history,batch=prepare(handoff_api,pilot_moments,rate,first=first,wrapped=wrapped)
    original=trend.TrackingTrend.from_buffer_copy(bytes(history))
    history.history.valid=0  # The controller owns a copy, not this caller's memory.
    assert radio.tick()==1
    assert radio.tick()==1
    assert len(radio.descriptors)==2
    assert not any(name=='head' for kind,name,_ in radio.events if kind=='retain')
    assert radio.descriptors[0].start==batch.prediction.start
    assert radio.run()==0
    result=review(journal(radio),epoch=3,rate=rate)
    assert [e['frame'] for e in result['estimates']]==list(range(first,first+128))
    assert len(result['heads'])==128 and result['supported']==128
    assert sum(b.repeats for b in radio.descriptors)==128
    marker=result['handoff']
    assert (marker.first,marker.limit,marker.next_slot,marker.anchor)==(
        first,first+128,original.history.next,original.history.anchor)
    for got,expected in zip(marker.observations,original.history.observations):
        assert got[0]==expected.frame
        assert struct.pack('>dd',*got[1:])==struct.pack('>dd',expected.offset,expected.cfo)
    handoff_rows=[raw for kind,name,raw in radio.events if (kind,name)==('retain','tracking_handoff')]
    assert len(handoff_rows)==1 and len(handoff_rows[0])<=4096
    actions=[(kind,name) for kind,name,_ in radio.events]
    assert actions.index(('retain','tracking_handoff'))<actions.index(('write','tracking_submit'))
    assert not radio.queue and not radio.pending and not radio.valid
    with pytest.raises(ValueError): legacy_review(journal(radio),epoch=3)


def test_ten_second_30_msps_handoff_runs_all_7500_scheduled_results(
        handoff_api,pilot_moments):
    rate=30000000
    radio,history,batch=prepare(
        handoff_api,pilot_moments,rate,frames=7500,initialize=False)
    assert handoff_api.glrt_tracking_controller_init_handoff(
        radio.state,c.byref(radio.ports),c.byref(batch),c.byref(history),600,7500,12)==0
    for _ in range(30000):
        status=radio.tick()
        if status!=1:
            break
        radio.advance(rate//1000)
    assert status==0
    result=review(journal(radio),epoch=3,rate=rate)
    assert len(result['heads'])==result['supported']==7500
    assert result['estimates'][0]['frame']==600
    assert result['estimates'][-1]['frame']==8099
    assert sum(item.repeats for item in radio.descriptors)==7500


def test_drained_coarse_authority_renews_only_future_tracking_work(
        handoff_api,pilot_moments):
    first=600
    radio,history,batch=prepare(handoff_api,pilot_moments,first=first)
    refreshed=extend_from_prediction(handoff_api,history,batch,first,599,608,617)
    radio.reject=True
    assert radio.tick()==1
    assert radio.tick()==1
    assert sum(item.repeats for item in radio.descriptors)==23
    # Work through frame 622 is already immutable. The new history is retained
    # before it can authorize frame 623 or any later descriptor, while native
    # results from the two owned batches continue to arrive in order.
    assert handoff_api.glrt_tracking_controller_refresh_handoff(
        radio.state,c.byref(refreshed))==0
    for _ in range(10000):
        assert radio.tick()==1
        radio.advance()
        if sum(item.repeats for item in radio.descriptors)>23:
            radio.reject=False
            break
    else: pytest.fail("refreshed authority did not schedule future work")
    assert radio.run()==0
    data=journal(radio)
    result=review(data,epoch=3,rate=2500000)
    assert [e['frame'] for e in result['estimates']]==list(range(first,first+128))
    assert 0<result['supported']<128
    actions=[(kind,name) for kind,name,_ in radio.events]
    authority=actions.index(('retain','tracking_authority'))
    assert actions[authority+1:].index(('write','tracking_submit'))>=0
    assert sum(item.repeats for item in radio.descriptors)==128
    entries,_=records(data)
    stripped=b'GLRJ1\n'+b''.join(retained(row.kind,row.payload) for row in entries
                                if row.kind!='tracking_authority')
    with pytest.raises(ValueError,match='authority'):
        review(stripped,epoch=3,rate=2500000)


def test_refresh_refuses_owned_work_and_retention_failure_stops_safely(
        handoff_api,pilot_moments):
    first=600
    radio,history,batch=prepare(handoff_api,pilot_moments,first=first)
    refreshed=extend_from_prediction(handoff_api,history,batch,first,599,608,617)
    # Before startup no future descriptor frontier has been established.
    assert handoff_api.glrt_tracking_controller_refresh_handoff(
        radio.state,c.byref(refreshed))==-1
    assert not any(name=='tracking_authority' for kind,name,_ in radio.events if kind=='retain')
    assert radio.tick()==1
    assert radio.tick()==1
    radio.fail_retain='tracking_authority'
    assert handoff_api.glrt_tracking_controller_refresh_handoff(
        radio.state,c.byref(refreshed))==-6
    assert radio.run()==-6
    assert sum(item.repeats for item in radio.descriptors)==23


def test_coarse_authority_uses_its_partial_final_horizon_when_native_rejects(
        handoff_api,pilot_moments):
    first=600
    radio,history,batch=prepare(handoff_api,pilot_moments,first=first)
    refreshed=extend_from_prediction(handoff_api,history,batch,first,599,608,617)
    radio.reject=True
    assert radio.tick()==1 and radio.tick()==1
    assert handoff_api.glrt_tracking_controller_refresh_handoff(
        radio.state,c.byref(refreshed))==0
    assert radio.run()==-4
    result=review(journal(radio),epoch=3,rate=2500000)
    assert not result['supported']
    assert result['estimates'][-1]['frame']==617+32
    assert sum(item.repeats for item in radio.descriptors)==617+33-first


@pytest.mark.parametrize("rate", [2500000,5000000,15000000])
def test_lost_new_support_uses_only_remaining_horizon(handoff_api,pilot_moments,rate):
    radio,history,_=prepare(handoff_api,pilot_moments,rate)
    last=history.history.last_supported
    radio.reject=True
    assert radio.run()==-4
    result=review(journal(radio),epoch=3,rate=rate)
    assert not result['supported']
    assert result['estimates'][-1]['frame']==last+32
    assert len(result['heads'])==last+33-600
    assert radio.writes('command')==[b'2\n',b'4\n']


@pytest.mark.parametrize("damage", ['epoch','rate','count','next','seen','order','nan','cfo',
    'last_supported','first_frame','start','fraction','step','period','expiry','work_limit','overflow','seconds'])
def test_bad_history_or_mismatched_prediction_cannot_modify_controller(handoff_api,pilot_moments,damage):
    radio,history,batch=prepare(handoff_api,pilot_moments,initialize=False)
    first,frames,seconds=600,128,2.0
    h=history.history
    if damage=='epoch': h.epoch+=1
    elif damage=='rate': history.rate=5000000
    elif damage=='count': h.count=97
    elif damage=='next': h.next=96
    elif damage=='seen': h.seen=0
    elif damage=='order': h.observations[1].frame=h.observations[0].frame
    elif damage=='nan': h.observations[0].offset=float('nan')
    elif damage=='cfo': h.observations[0].cfo=1250000
    elif damage=='last_supported': h.last_supported+=1
    elif damage=='first_frame': first=h.last_seen
    elif damage in ('start','fraction','step','period','expiry'):
        field='expires' if damage=='expiry' else damage
        setattr(batch.prediction,field,getattr(batch.prediction,field)+1)
    elif damage=='work_limit': frames=225001
    elif damage=='overflow': first=2**32-1
    else: seconds=float('nan')
    before=bytes(radio.state)
    assert handoff_api.glrt_tracking_controller_init_handoff(radio.state,c.byref(radio.ports),
        c.byref(batch),c.byref(history),first,frames,seconds)==-1
    assert bytes(radio.state)==before and not radio.events


def test_history_can_alias_existing_controller_memory(handoff_api,pilot_moments):
    radio,history,batch=prepare(handoff_api,pilot_moments,initialize=False)
    c.memmove(radio.state,c.byref(history),c.sizeof(history))
    alias=c.cast(radio.state,c.POINTER(trend.TrackingTrend))
    assert handoff_api.glrt_tracking_controller_init_handoff(radio.state,c.byref(radio.ports),
        c.byref(batch),alias,600,128,2)==0
    assert radio.run()==0
    assert review(journal(radio),epoch=3,rate=2500000)['supported']==128


@pytest.mark.parametrize("failure", ['retention','slow_retention','epoch_change'])
def test_retained_history_never_bypasses_live_admission_checks(handoff_api,pilot_moments,failure):
    radio,history,batch=prepare(handoff_api,pilot_moments,initialize=False)
    if failure=='retention': radio.fail_retain='tracking_handoff'
    elif failure=='epoch_change': radio.epoch+=1
    else:
        old=radio.retain
        def slow(context,name,data,size):
            rc=old(context,name,data,size)
            if name==b'tracking_handoff': radio.advance(radio.rate//100)
            return rc
        radio.ports.retain=type(radio.ports.retain)(slow)
    # Install callbacks before C copies the ports; replacing an already copied
    # ctypes callback can free the trampoline still referenced by the C state.
    assert handoff_api.glrt_tracking_controller_init_handoff(radio.state,c.byref(radio.ports),
        c.byref(batch),c.byref(history),600,128,2)==0
    assert radio.run()=={'retention':-6,'slow_retention':-5,'epoch_change':-3}[failure]
    assert not radio.writes('submit') and not radio.writes('pop')


@pytest.mark.parametrize("damage", ['missing','duplicate','late','truncated','epoch','rate','next',
    'frame','limit','row_count','row_nan','row_order','row_last','first_descriptor'])
def test_damaged_handoff_journal_cannot_authorize_results(handoff_api,pilot_moments,damage):
    radio,_,_=prepare(handoff_api,pilot_moments,frames=16)
    assert radio.run()==0
    entries,_=records(journal(radio))
    pairs=[(e.kind,e.payload) for e in entries]
    at=next(i for i,(kind,_) in enumerate(pairs) if kind=='tracking_handoff')
    if damage=='missing': pairs.pop(at)
    elif damage=='duplicate': pairs.insert(at,pairs[at])
    elif damage=='late': pairs.insert(at+2,pairs.pop(at))
    elif damage=='first_descriptor':
        pos=next(i for i,(kind,_) in enumerate(pairs) if kind=='descriptor')
        pairs[pos]=('descriptor',pairs[pos][1].replace(b'frame 600 ',b'frame 0 '))
    else:
        lines=pairs[at][1].splitlines()
        fields=lines[0].split()
        if damage in ('epoch','rate','next','frame','limit'):
            position={'epoch':3,'rate':2,'next':11,'frame':4,'limit':5}[damage]
            value={'epoch':4,'rate':5000000,'next':96,'frame':1,'limit':601}[damage]
            fields[position]=f'{value:08x}'.encode();lines[0]=b' '.join(fields)
        elif damage=='row_count': lines.pop()
        elif damage=='row_nan': lines[1]=lines[1][:8]+b'7ff8000000000000'+lines[1][24:]
        elif damage=='row_order': lines[2]=lines[1]
        elif damage=='row_last': lines[-1]=b'0000024d'+lines[-1][8:]
        raw=b'\n'.join(lines)+b'\n'
        pairs[at]=('tracking_handoff',raw[:-1] if damage=='truncated' else raw)
    data=b'GLRJ1\n'+b''.join(retained(kind,raw) for kind,raw in pairs)
    with pytest.raises(ValueError): review(data,epoch=3,rate=2500000)


@pytest.mark.parametrize("uncertain", [False,True])
def test_stopped_handoff_recovery_preserves_nonzero_frame_ownership(handoff_api,pilot_moments,uncertain):
    radio,_,_=prepare(handoff_api,pilot_moments)
    assert radio.tick()==1
    radio.advance(radio.rate//100)
    assert len(radio.queue)>1
    data=journal(radio)
    port=Port(radio)
    radio.pop_return_error=uncertain
    final=recover(port,data,epoch=3,rate=2500000,writer_stopped=True,retain=port.retain,
        deadline=1,clock=lambda:radio.time,sleep=lambda _:radio.advance())
    assert final.configured==0 and not radio.queue and not radio.pending
    assert radio.writes('command')==[b'2\n',b'4\n']


def test_empty_handoff_payload_is_rejected():
    with pytest.raises(ValueError): decode(b'',epoch=3,rate=2500000)
