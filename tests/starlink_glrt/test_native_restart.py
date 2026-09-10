"""Automatic restart gates use journals from the actual C controller."""
from dataclasses import replace
import ctypes as c

import pytest

from tests.starlink_glrt.test_native_controller import Radio, controller, pilot_words
from tests.starlink_glrt.test_native_journal import journal
from tools.starlink_glrt_native_journal import review
from tools.starlink_glrt_native_restart import RestartFence, restart_fence
from tools.starlink_glrt_schedule_abi import ScheduleSnapshot


def completed(controller, pilot_words, *, rejected=False):
    radio = Radio(controller, pilot_words, frames=32)
    radio.reject = rejected
    result = radio.run()
    current = ScheduleSnapshot.from_sysfs(radio.snapshot().decode())
    count = 16 if rejected else 32
    return journal(radio), dict(epoch=3, result=result, configured=count,
        retained_popped=count, writer_stopped=True, current=current)


@pytest.mark.parametrize('rejected', [False, True])
def test_actual_completion_and_acquisition_loss_produce_new_iq_fence(controller, pilot_words, rejected):
    data, args = completed(controller, pilot_words, rejected=rejected)
    assert args['result'] == (-4 if rejected else 0)
    fence = restart_fence(data, **args)
    assert fence == RestartFence(3, args['current'].latest_index)
    fence.require_fresh_observations(tuple(fence.native_sample+1+i*320000 for i in range(24)))


@pytest.mark.parametrize('change', [dict(writer_stopped=False), dict(writer_stopped=1),
    dict(result=-1), dict(result=-2), dict(result=-3), dict(result=-5), dict(result=-6),
    dict(result=False), dict(configured=31), dict(retained_popped=31), dict(epoch=4)])
def test_uncertain_or_mismatched_episode_cannot_authorize_restart(controller, pilot_words, change):
    data, args = completed(controller, pilot_words)
    args.update(change)
    with pytest.raises(ValueError):
        restart_fence(data, **args)


@pytest.mark.parametrize('change', [dict(epoch=4), dict(status=0x32), dict(faults=1),
    dict(cdc_drops=1), dict(pacer_drops=1), dict(latest_index=2**60),
    dict(configured=16, cancelled=16), dict(status=0x02)])
def test_current_source_must_match_retained_clean_termination(controller, pilot_words, change):
    data, args = completed(controller, pilot_words)
    args['current'] = replace(args['current'], **change)
    with pytest.raises(ValueError):
        restart_fence(data, **args)


def test_partial_journal_never_authorizes_restart(controller, pilot_words):
    data, args = completed(controller, pilot_words)
    with pytest.raises(ValueError):
        restart_fence(data[:-1], **args)


def test_actual_controller_reacquires_after_loss_with_new_epoch_and_only_fresh_history(
    controller, pilot_words
):
    class ReturningPilotRadio(Radio):
        lose_after = 32

        def advance(self, samples=3000):
            self.reject = self.lose_after is not None and self.admitted >= self.lose_after
            super().advance(samples)

    radio = ReturningPilotRadio(controller, pilot_words, frames=128)
    assert radio.run() == -4
    first_data = journal(radio)
    first = review(first_data, epoch=3)
    assert 0 < first['supported'] < len(first['heads']) < 128
    current = ScheduleSnapshot.from_sysfs(radio.snapshot().decode())
    fence = restart_fence(first_data, epoch=3, result=-4,
        configured=len(first['heads']), retained_popped=len(first['heads']),
        writer_stopped=True, current=current)
    # Failed freshness cannot submit a second descriptor or change ownership.
    before = list(radio.events)
    with pytest.raises(ValueError):
        fence.require_fresh_observations(tuple(fence.native_sample-i for i in range(24)))
    assert radio.events == before and not radio.pending and not radio.queue
    starts = tuple(fence.native_sample+1+i*320000 for i in range(24))
    fence.require_fresh_observations(starts)
    radio.advance(starts[-1]+3402*24-radio.latest)
    # Model the owner's explicit, drained REBASE. The native ADC index never resets.
    assert not radio.valid and radio.configured == radio.admitted == radio.popped == 0
    radio.epoch += 1
    radio.valid = True
    radio.lose_after = None
    radio.reject = False
    radio.events = []
    radio.descriptors = []
    radio.seed.epoch = radio.epoch
    radio.seed.start = radio.latest+300000
    radio.seed.expires = radio.seed.start+radio.seed.repeats*80000
    assert controller.glrt_native_controller_init(radio.state, c.byref(radio.ports),
        c.byref(radio.seed), 64, 2) == 0
    assert radio.run() == 0
    second = review(journal(radio), epoch=4)
    assert second['supported'] == len(second['heads']) == 64
    assert second['heads'][0].start > starts[-1]+3402*24
    assert not radio.valid and not radio.pending and not radio.queue
    assert radio.configured == radio.admitted == radio.popped == 0
    # Retaining the next episode must not alter the prior failed-acquisition evidence.
    assert review(first_data, epoch=3)['supported'] == first['supported']


@pytest.mark.parametrize('change', ['old', 'edge', 'unordered', 'duplicate', 'short', 'float'])
def test_reacquisition_cannot_reuse_any_guard_sample_from_previous_episode(change):
    fence = RestartFence(3, 2**60+7)
    starts = [fence.native_sample+1+i*320000 for i in range(24)]
    if change == 'old': starts[0] = fence.native_sample-1
    if change == 'edge': starts[0] = fence.native_sample
    if change == 'unordered': starts.reverse()
    if change == 'duplicate': starts[1] = starts[0]
    if change == 'short': starts.pop()
    if change == 'float': starts[0] = float(starts[0])
    with pytest.raises(ValueError):
        fence.require_fresh_observations(tuple(starts))


@pytest.mark.parametrize('supported_phases', [(0,), (0, 1)])
@pytest.mark.parametrize('bootstrap_repeats', [12, 64])
def test_long_finite_seed_collects_sparse_pilots_without_accepting_rejected_frames(
    controller, pilot_words, supported_phases, bootstrap_repeats
):
    # This test qualifies controller scheduling with a declared availability
    # pattern. Zero moments represent rejected input, not generated RF truth.
    class SparseRadio(Radio):
        def advance(self, samples=3000):
            before=len(self.queue)
            super().advance(samples)
            for words in self.queue[before:]:
                frame=sum(b.repeats for b in self.descriptors if b.tag<words[2])+words[27]
                if frame%4 not in supported_phases:
                    words[9:25]=[0]*16

    radio=SparseRadio(controller,pilot_words,frames=128)
    radio.seed.repeats=bootstrap_repeats
    radio.seed.expires=radio.seed.start+bootstrap_repeats*80000
    assert controller.glrt_native_controller_init(radio.state,c.byref(radio.ports),
        c.byref(radio.seed),128,2)==0
    assert radio.run()==(-4 if bootstrap_repeats==12 else 0)
    checked=review(journal(radio),epoch=3)
    expected_count=12 if bootstrap_repeats==12 else 128
    assert len(checked['heads'])==expected_count
    assert [row['frame'] for row in checked['estimates']]==list(range(expected_count))
    assert [row['rejection']==0 for row in checked['estimates']]==[
        frame%4 in supported_phases for frame in range(expected_count)]
    assert not radio.queue and not radio.pending and not radio.valid
