"""Automatic restart gates use journals from the actual C controller."""
from dataclasses import replace

import pytest

from tests.starlink_glrt.test_native_controller import Radio, controller, pilot_words
from tests.starlink_glrt.test_native_journal import journal
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
