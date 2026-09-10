"""Finite coarse horizon, small immutable slices, one-way native takeover."""
import ctypes as c

import numpy as np
import pytest

from tests.starlink_glrt.test_native_controller import Radio, controller, pilot_words
from tests.starlink_glrt.test_native_journal import journal
from tests.starlink_glrt.test_native_solver import model, packet
from tools.starlink_glrt_native_journal import review
from tools.starlink_glrt_schedule_abi import ScheduleBatch


class SlicedRadio(Radio):
    def __init__(self,lib,words,*,phases=(0,),lose_after=None):
        super().__init__(lib,words,frames=128)
        self.phases,self.lose_after=phases,lose_after
        self.seed.repeats=64
        self.seed.expires=self.seed.start+64*80000
        self.initialize()

    def initialize(self):
        assert self.lib.glrt_native_controller_init_sliced(self.state,c.byref(self.ports),
            c.byref(self.seed),128,2)==0

    def advance(self,samples=3000):
        before=len(self.queue)
        super().advance(samples)
        for words in self.queue[before:]:
            frame=sum(b.repeats for b in self.descriptors if b.tag<words[2])+words[27]
            if frame%4 not in self.phases or (self.lose_after is not None and frame>=self.lose_after):
                words[9:25]=[0]*16


@pytest.mark.parametrize('phases',[(0,),(0,1),(0,1,2,3)])
def test_small_slices_take_over_before_full_horizon_without_inventing_support(controller,pilot_words,phases):
    radio=SlicedRadio(controller,pilot_words,phases=phases)
    assert radio.run()==0
    checked=review(journal(radio),epoch=3)
    batches=[(first,b) for first,b in checked['descriptors'].values()]
    assert batches[0][1].repeats==12
    native_at=next(first for first,b in batches if b.repeats==16)
    assert 12<=native_at<64
    assert all(b.repeats==4 for first,b in batches if 0<first<native_at)
    assert [e['rejection']==0 for e in checked['estimates']]==[i%4 in phases for i in range(128)]
    assert not radio.pending and not radio.queue and not radio.valid


def test_empty_horizon_stops_at_64_and_preserves_fractional_and_modulo_phase_predictions(controller,pilot_words):
    radio=SlicedRadio(controller,pilot_words,phases=())
    radio.seed.start+=1;radio.seed.fraction=32768
    radio.seed.period=80000*65536+12345
    radio.seed.step=2**48-7;radio.seed.delta=2**48-1234567
    radio.seed.expires+=128
    radio.initialize()
    original=ScheduleBatch(epoch=3,tag=7,start=radio.seed.start,fraction=radio.seed.fraction,
        period=radio.seed.period,step=radio.seed.step,delta=radio.seed.delta,seed=radio.seed.seed,
        repeats=64,expires=radio.seed.expires)
    assert radio.run()==-4
    checked=review(journal(radio),epoch=3)
    assert len(checked['heads'])==64 and checked['supported']==0
    for frame,head in enumerate(checked['heads']):
        assert (head.start,head.phase_step)==original.prediction(frame)
    assert [b.repeats for b in radio.descriptors]==[12]+[4]*13
    assert all(b.expires<=original.expires for b in radio.descriptors)


def test_native_loss_cannot_revive_old_coarse_horizon(controller,pilot_words):
    radio=SlicedRadio(controller,pilot_words,phases=(0,1,2,3),lose_after=20)
    assert radio.run()==-4
    checked=review(journal(radio),epoch=3)
    sizes=[b.repeats for b in radio.descriptors]
    assert 16 in sizes
    assert all(count<=16 for count in sizes[sizes.index(16):])
    assert len(checked['heads'])==52  # Last supported 19, then the existing 32-frame horizon.


def test_uncertain_slice_submission_is_not_retried(controller,pilot_words):
    radio=SlicedRadio(controller,pilot_words,phases=())
    assert radio.tick()==1
    radio.submit_return_error=True
    assert radio.run()==-1
    assert len(radio.descriptors)==2
    assert len(radio.writes('submit'))==2
    assert radio.writes('command')==[b'2\n',b'4\n']
    checked=review(journal(radio),epoch=3)
    assert checked['drained'].configured==16
    assert checked['drained'].cancelled+len(checked['heads'])==16
    assert len(checked['heads'])==8
    assert not radio.queue and not radio.pending and not radio.valid


@pytest.mark.parametrize('direction',[-1,1])
@pytest.mark.parametrize('slice_index',[1,2])
def test_supported_startup_offsets_correct_next_slice_but_do_not_invent_rate(controller,model,direction,slice_index):
    basis,raw=model
    values=.3*(basis@np.array([1,direction*.07,direction*.06]))
    iq=np.rint(np.column_stack((values.real,values.imag))).astype(np.int64)
    radio=SlicedRadio(controller,packet(iq,raw),phases=(0,))
    radio.seed.step=(2**48-12345 if direction>0 else 12345)
    radio.initialize()
    for _ in range(1000):
        assert radio.tick()==1
        if len(radio.descriptors)==slice_index+1:break
        radio.advance()
    else:pytest.fail('bounded third startup slice was not submitted')
    estimates=[body.split() for kind,name,body in radio.events if (kind,name)==('retain','estimate')]
    supported=[fields for fields in estimates if int(fields[8])==0]
    assert len(supported)==(1 if slice_index==1 else 3)
    assert int(supported[-1][2])==(0 if slice_index==1 else 8)
    slice16=radio.descriptors[slice_index]
    expected_shift=round(float(supported[-1][3])*60_000_000*65536)
    first_frame=12 if slice_index==1 else 16
    assert (slice16.start-radio.seed.start-first_frame*80000)*65536+slice16.fraction==expected_shift
    original_step=radio.seed.step if radio.seed.step<2**47 else radio.seed.step-2**48
    correction_hz=float(supported[-1][5])-original_step*(60_000_000/2**48)
    expected_phase=(radio.seed.step+round(correction_hz*(2**48/60_000_000)))%(2**48)
    assert slice16.step==expected_phase
    assert slice16.period==radio.seed.period and slice16.delta==radio.seed.delta
    assert slice16.repeats==4 and slice16.expires<=radio.seed.expires
    controller.glrt_native_controller_request_stop(radio.state)
    assert radio.run()==-5
    review(journal(radio),epoch=3)
