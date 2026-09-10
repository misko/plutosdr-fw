"""Partial batches use the existing horizon without extrapolating farther."""
import ctypes as c

import pytest

from tests.starlink_glrt.test_native_controller import Radio, controller, pilot_words
from tests.starlink_glrt.test_native_journal import journal
from tools.starlink_glrt_native_journal import review
from tools.starlink_glrt_native_restart import restart_fence
from tools.starlink_glrt_schedule_abi import ScheduleSnapshot


class IntermittentRadio(Radio):
    def __init__(self, lib, words, resume_at):
        super().__init__(lib, words, frames=128)
        self.resume_at = resume_at

    def advance(self, samples=3000):
        before = len(self.queue)
        super().advance(samples)
        for words in self.queue[before:]:
            frame = words[1]
            if frame >= 20 and (self.resume_at is None or frame < self.resume_at):
                words[9:25] = [0] * 16


@pytest.mark.parametrize('resume_at', [48, 50, 51, 52, None])
def test_returning_pilot_can_only_restore_feedback_before_original_expiry(controller, pilot_words, resume_at):
    radio = IntermittentRadio(controller, pilot_words, resume_at)
    assert radio.run() == (0 if resume_at in (48,50) else -4)
    checked = review(journal(radio), epoch=3)
    assert not radio.pending and not radio.queue and not radio.valid
    assert checked['drained'].cancelled == 0
    assert any(b.repeats < 16 for b in radio.descriptors[1:])
    if resume_at in (48,50):
        assert len(checked['heads']) == 128
        assert [e['rejection'] == 0 for e in checked['estimates']] == [i < 20 or i >= resume_at for i in range(128)]
    else:
        assert len(checked['heads']) == 52
        assert checked['supported'] == (21 if resume_at==51 else 20)
        assert checked['estimates'][-1]['frame'] == 51
    # Audit authorization using only estimates retained before each submission.
    last_supported = None
    for kind, name, body in radio.events:
        if (kind, name) == ('retain', 'estimate'):
            fields = body.split()
            if int(fields[8]) == 0:
                last_supported = int(fields[2])
        if (kind, name) == ('retain', 'descriptor'):
            fields = body.split()
            assert fields[0] == b'frame'
            first, repeats = int(fields[1]), int(fields[-2], 16)
            if first:
                assert last_supported is not None
                assert first + repeats - 1 <= last_supported + 32


@pytest.mark.parametrize('fault', ['source','deadline','stop'])
def test_exhausted_horizon_does_not_mask_source_or_wall_deadlines(controller,pilot_words,fault):
    radio=IntermittentRadio(controller,pilot_words,51)
    for _ in range(10000):
        assert radio.tick()==1
        estimates=[body.split() for kind,name,body in radio.events if (kind,name)==('retain','estimate')]
        if estimates and int(estimates[-1][2])==51:
            break
        radio.advance()
    else:pytest.fail('last horizon result was not consumed')
    if fault=='source':radio.gap=True
    elif fault=='deadline':radio.time=3.0
    else:controller.glrt_native_controller_request_stop(radio.state)
    assert radio.run()==(-3 if fault=='source' else -5)
    checked=review(journal(radio),epoch=3)
    assert checked['drained'].configured==checked['drained'].popped==52
    assert checked['drained'].cancelled==0 and not radio.valid


def test_boundary_loss_passes_unchanged_restart_gate_only_after_retained_clear(controller,pilot_words):
    radio=IntermittentRadio(controller,pilot_words,51)
    result=radio.run()
    assert result==-4
    data=journal(radio)
    checked=review(data,epoch=3)
    fence=restart_fence(data,epoch=3,result=result,configured=52,retained_popped=52,
        writer_stopped=True,current=ScheduleSnapshot.from_sysfs(radio.snapshot().decode()))
    assert fence.native_sample>=checked['final'].latest_index
    with pytest.raises(ValueError,match='confirmed stopped'):
        restart_fence(data,epoch=3,result=result,configured=52,retained_popped=52,
            writer_stopped=False,current=checked['final'])
    with pytest.raises(ValueError,match='new ordered'):
        fence.require_fresh_observations(tuple(fence.native_sample+i for i in range(24)))
    fence.require_fresh_observations(tuple(fence.native_sample+i+1 for i in range(24)))


def test_requested_completion_at_boundary_is_still_success(controller,pilot_words):
    radio=IntermittentRadio(controller,pilot_words,51)
    assert controller.glrt_native_controller_init(radio.state,c.byref(radio.ports),
        c.byref(radio.seed),52,2)==0
    assert radio.run()==0
    checked=review(journal(radio),epoch=3)
    assert checked['drained'].configured==checked['drained'].popped==52
    assert checked['supported']==21
