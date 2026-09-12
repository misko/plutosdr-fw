"""Independent GLT1 journal review and stopped-writer recovery at every rate."""
import pytest

from tools.starlink_glrt_native_journal import records
from tools.starlink_glrt_native_journal import review as legacy_review
from tools.starlink_glrt_tracking_journal import batch, descriptors, recover, review

from . import test_tracking_controller
from .test_native_controller import Radio
from .test_native_journal import Port, journal, retained
from .test_tracking_schedule import RATES
from .test_tracking_transport import descriptor

controller = test_tracking_controller.controller
models = test_tracking_controller.models
pilot_moments = test_tracking_controller.pilot_moments


@pytest.mark.parametrize("rate", RATES)
def test_independent_review_accepts_actual_controller_journal(controller,pilot_moments,rate):
    radio = Radio(controller,pilot_moments,tracking_rate=rate)
    assert radio.run() == 0
    data = journal(radio)
    result = review(data,epoch=3,rate=rate)
    assert len(result['heads']) == result['supported'] == 128
    assert [r['frame'] for r in result['estimates']] == list(range(128))
    assert all(h.rate == rate for h in result['heads'])
    assert result['drained'].popped == 128 and not result['final'].configured
    with pytest.raises(ValueError): legacy_review(data,epoch=3)
    with pytest.raises(ValueError): review(data,epoch=3,rate=15000000 if rate!=15000000 else 30000000)


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("damage", ["truncated", "owner", "estimate", "drain", "nan",
                                   "tag", "phase", "epoch", "future_owner", "extra_final"])
def test_damaged_or_misassociated_journal_cannot_pass(controller,pilot_moments,rate,damage):
    radio = Radio(controller,pilot_moments,frames=16,tracking_rate=rate)
    assert radio.run() == 0
    entries,_ = records(journal(radio))
    pairs = [(r.kind,r.payload) for r in entries]
    if damage in ('owner','estimate','drain'):
        kind = {'owner':'descriptor','estimate':'estimate','drain':'drained'}[damage]
        pairs.pop(next(i for i,(k,_) in enumerate(pairs) if k==kind))
    elif damage == 'nan':
        at = next(i for i,(k,_) in enumerate(pairs) if k=='estimate')
        f = pairs[at][1].split(); f[3] = b'nan'; pairs[at] = ('estimate',b' '.join(f)+b'\n')
    elif damage in ('tag','phase'):
        at = next(i for i,(k,_) in enumerate(pairs) if k=='head')
        f = pairs[at][1].split(); index = 5 if damage=='tag' else 31
        f[index] = f'{int(f[index],16)^1:08x}'.encode(); pairs[at] = ('head',b' '.join(f)+b'\n')
    elif damage == 'future_owner':
        pairs.append(pairs.pop(next(i for i,(k,_) in enumerate(pairs) if k=='descriptor')))
    elif damage == 'extra_final': pairs.append(pairs[-1])
    data = b'GLRJ1\n'+b''.join(retained(k,raw) for k,raw in pairs)
    if damage=='truncated': data = data[:-1]
    with pytest.raises(ValueError): review(data,epoch=4 if damage=='epoch' else 3,rate=rate)


def stopped(radio):
    assert radio.tick() == 1
    radio.advance(radio.rate//100)
    assert len(radio.queue) > 1
    return journal(radio)


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("uncertain_pop", [False,True])
def test_recovery_retains_exact_heads_and_never_retries_uncertain_pop(controller,pilot_moments,rate,uncertain_pop):
    radio = Radio(controller,pilot_moments,tracking_rate=rate)
    data = stopped(radio)+b'hea'
    port = Port(radio); queued = len(radio.queue)
    radio.pop_return_error = uncertain_pop
    final = recover(port,data,epoch=3,rate=rate,writer_stopped=True,retain=port.retain,
                    deadline=1,clock=lambda:radio.time,sleep=lambda _:radio.advance())
    assert final.rate == rate and final.configured == 0
    assert not radio.queue and not radio.pending and not final.status&16
    assert len(radio.writes('pop')) == queued
    assert len([1 for kind,_ in port.evidence if kind=='head']) == queued
    assert radio.writes('command') == [b'2\n',b'4\n']


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("failure", ["writer", "rate", "epoch", "owner", "retain", "pop", "deadline", "partial"])
def test_failed_recovery_preserves_unacknowledged_evidence(controller,pilot_moments,rate,failure):
    radio = Radio(controller,pilot_moments,tracking_rate=rate)
    data = stopped(radio)
    port = Port(radio)
    if failure=='owner': data = b'GLRJ1\n'
    elif failure=='pop': radio.fail_write = 'tracking_pop'
    elif failure=='partial':
        entries,_ = records(data)
        owner = next(r for r in entries if r.kind=='descriptor')
        data = data[:data.index(retained('descriptor',owner.payload))]+b'descriptor 256\nframe 0 GLT1'
        entries,partial = records(data,allow_partial=True)
        assert partial and not descriptors(entries,epoch=3,rate=rate)
    def retain(kind,raw):
        if failure=='retain' and kind=='head': raise OSError('retention failed')
        port.retain(kind,raw)
    with pytest.raises((ValueError,OSError,TimeoutError)):
        recover(port,data,epoch=4 if failure=='epoch' else 3,
                rate=(15000000 if rate!=15000000 else 30000000) if failure=='rate' else rate,
                writer_stopped=failure!='writer',retain=retain,
                deadline=-1 if failure=='deadline' else 1,clock=lambda:radio.time)
    assert radio.queue and b'4\n' not in radio.writes('command')
    if failure in ('writer','rate','epoch','deadline'): assert not radio.writes('command')


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("damage", ["prefix", "version", "bank", "short", "extra", "nul", "expiry"])
def test_retained_descriptor_requires_complete_versioned_profile_and_horizon(rate,damage):
    b = descriptor(rate)
    assert batch(b.encode(),rate=rate) == b
    fields = b.encode().split()
    if damage=='prefix': fields[0] = 'GLS1'
    elif damage=='version': fields[1] = '00020000'
    elif damage=='bank': fields[3] = '00000000'
    elif damage=='short': fields.pop()
    elif damage=='extra': fields.append('0')
    elif damage=='nul': fields[-1] += '\0'
    else: fields[-1] = f'{b.start+b.samples-1:x}'
    with pytest.raises(ValueError): batch(' '.join(fields),rate=rate)
