"""PPU supervision drives real C controller episodes through deterministic ports.

No radio/network activity. This qualifies orchestration and evidence ordering,
not the still-required Ethernet session adapter or physical precision.
"""
import ctypes as c
import hashlib
import json
import os

from pluto_plus.native_prepared_session import PreparedNativeSession
from pluto_plus.native_supervisor import (
    NativeCandidate,
    NativeEpisode,
    NativeIdentity,
    supervise_native,
)

from tests.starlink_glrt.test_native_controller import Radio
from tests.starlink_glrt.test_native_journal import journal
from tools.starlink_glrt_native_journal import review

pytest_plugins = ('tests.starlink_glrt.test_native_controller',)


def test_supervisor_retains_lost_then_reacquired_C_episodes_before_clean_shutdown(
    controller, pilot_words, tmp_path
):
    class ReturningRadio(Radio):
        lose_after = 32

        def advance(self, samples=3000):
            self.reject = self.lose_after is not None and self.admitted >= self.lose_after
            super().advance(samples)

    identity = NativeIdentity('simulated-native', 'C-controller-test', 'simulated-boot', 'a'*64)
    radio = ReturningRadio(controller, pilot_words, frames=128)

    class Session:
        def __init__(self):
            self.index = 0
            self.saved = []

        def open(self, expected, deadline, cancel):
            assert expected == identity and radio.time < deadline

        def wait_candidate(self, deadline, cancel):
            if self.index:
                # All prior evidence is durable before any new source epoch.
                assert len(self.saved) == self.index
                assert not radio.valid and not radio.pending and not radio.queue
                radio.epoch += 1
                radio.valid = True
            starts = tuple(radio.latest + 1 + i*320000 for i in range(24))
            radio.advance(starts[-1]+3402*24-radio.latest)
            self.index += 1
            return NativeCandidate(identity, radio.epoch, starts, radio.latest+300000)

        def execute(self, candidate, deadline, cancel):
            radio.events = []
            radio.descriptors = []
            radio.lose_after = 32 if self.index == 1 else None
            radio.reject = False
            radio.seed.epoch = candidate.epoch
            radio.seed.start = candidate.native_start
            radio.seed.expires = candidate.native_start + radio.seed.repeats*80000
            assert controller.glrt_native_controller_init(radio.state, c.byref(radio.ports),
                c.byref(radio.seed), 128 if self.index == 1 else 64, 2) == 0
            result = radio.run()
            self.data = journal(radio)
            checked = review(self.data, epoch=candidate.epoch)
            drained, final = checked['drained'], checked['final']
            return NativeEpisode(identity, candidate.epoch, result, drained.configured,
                drained.admitted, drained.committed, drained.popped, checked['supported'],
                final.latest_index, hashlib.sha256(self.data).hexdigest(),
                not radio.valid and not radio.pending and not radio.queue,
                drained.faults, drained.cdc_drops+drained.pacer_drops)

        def retain_episode(self, episode, deadline):
            assert hashlib.sha256(self.data).hexdigest() == episode.journal_sha256
            path = tmp_path/f'epoch-{episode.epoch}.glrj'
            with path.open('xb') as stream:
                stream.write(self.data)
                stream.flush()
                os.fsync(stream.fileno())
            assert review(path.read_bytes(), epoch=episode.epoch)['supported'] == episode.supported
            self.saved.append(path)

        def prepare_launch(self, deadline, cancel):
            candidate = self.wait_candidate(deadline, cancel)
            return candidate, b"printf 'simulated controller launch\\n'\n"

        def finish_execution(self, output, candidate, deadline):
            assert output == 'authenticated simulated native output'
            return self.execute(candidate, deadline, None)

        def finish_observation(self, deadline, cancel):
            pass

        def close(self, deadline):
            return not radio.valid and not radio.pending and not radio.queue and radio.time < deadline

    session = Session()

    class Transport:
        def run_prepared_stdin(self, command, *, byte_count, prepare, timeout_s, cancelled=None):
            assert command == 'sh -s' and byte_count == 4096
            radio.advance(30_000_000)  # Authentication cost occurs before fresh prediction.
            payload = prepare()
            assert len(payload) == byte_count
            return 'authenticated simulated native output'

    prepared = PreparedNativeSession(Transport(), session, clock=lambda: radio.time)
    result = supervise_native(prepared, identity=identity, events_path=tmp_path/'supervisor.jsonl',
                              clock=lambda: radio.time)
    assert result['outcome'] == 'episode_limit_reached' and result['cleanup_verified']
    assert [item['result'] for item in result['episodes']] == [-4, 0]
    assert [item['epoch'] for item in result['episodes']] == [3, 4]
    assert result['episodes'][0]['supported'] == 32
    assert result['episodes'][1]['supported'] == 64
    assert not result['physical_precision_qualified']
    events = [json.loads(line) for line in (tmp_path/'supervisor.jsonl').read_text().splitlines()]
    launches = [i for i, event in enumerate(events) if event['kind'] == 'launching']
    retained = [i for i, event in enumerate(events) if event['kind'] == 'episode_retained']
    assert launches[0] < retained[0] < launches[1] < retained[1]
    assert len(session.saved) == 2
