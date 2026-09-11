"""Offline Ethernet-source integration; no network, hardware or RF required."""
import ctypes as c
import hashlib
import json
import re
import signal
import subprocess
import time
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
from pluto_plus.native_prepared_session import PreparedNativeSession
from pluto_plus.native_supervisor import (
    NativeIdentity,
    NativeSupervisorLimits,
    supervise_native,
)

from tests.starlink_glrt.test_native_controller import Radio
from tests.starlink_glrt.test_native_journal import journal
from tools import starlink_glrt_native_source as source
from tools.starlink_glrt_schedule_abi import ScheduleBatch

IDENTITY = NativeIdentity('1040005e0b100007100010000bf33a5d4d', 'native-test', 'boot-test', 'a'*64)
pytest_plugins = ('tests.starlink_glrt.test_native_controller',)
PROGRAMS = source.CapturePrograms(*(Path('/declared')/name for name in
    ('host-python', 'host-cwd', 'follower.py', 'capture-python', 'fw-cwd', 'bank.mem', 'ddc.json')))


@pytest.mark.parametrize('mode', ['complete', 'failed', 'cancelled', 'deadline'])
def test_finite_pipeline_wait_is_bounded_and_rejects_failed_children(tmp_path, mode):
    now = [0.0]
    cancel = Event()
    pipeline = source.CapturePipeline(PROGRAMS, tmp_path, clock=lambda: now[0],
        sleep=lambda seconds: now.__setitem__(0, now[0]+seconds))
    pipeline.children = [('coarse', SimpleNamespace(poll=lambda:
        1 if mode == 'failed' else 0 if now[0] >= .03 else None), None)]
    if mode == 'cancelled':
        cancel.set()
    if mode == 'complete':
        pipeline.finish(1, cancel)
        assert .03 <= now[0] < 1
    else:
        error = {'failed': RuntimeError, 'cancelled': InterruptedError, 'deadline': TimeoutError}[mode]
        with pytest.raises(error):
            pipeline.finish(.01 if mode == 'deadline' else 1, cancel)


class Harness:
    def __init__(self, tmp_path, monkeypatch, controller, pilot_words, failure=None):
        self.root, self.failure = tmp_path, failure
        self.leases, self.actions, self.files = [], [], {}
        self.episodes = 0
        class ReturningRadio(Radio):
            lose_after = 32

            def advance(self, samples=3000):
                self.reject = self.lose_after is not None and self.admitted >= self.lose_after
                super().advance(samples)

        self.radio = ReturningRadio(controller, pilot_words, frames=128)
        self.radio.valid = False
        self.radio.epoch = 2
        self.controller = controller
        self.pipeline = source.CapturePipeline(PROGRAMS, tmp_path/'pipeline', popen=self.popen,
            clock=self.clock, sleep=self.sleep)
        self.owner = source.EthernetNativeSource(transport=self, deployment=tmp_path/'deployment.json',
            controller_sha256='b'*64, host='192.168.1.20', visit=7, pipeline=self.pipeline,
            evidence=tmp_path/'evidence', station_lease=lambda identity, deadline: self.lease('station'),
            predict=self.predict, clock=self.clock, sleep=self.sleep)
        monkeypatch.setattr(source, 'acquire_radio_lock', lambda serial: self.lease('ppu'))
        monkeypatch.setattr(source.g, 'deployment_identity', lambda *a, **kw:
            ({'expected_firmware': IDENTITY.firmware}, SimpleNamespace(return_iio_layout='fake')))
        monkeypatch.setattr(source.g, 'attest_tx_safe_idle', self.attest)
        monkeypatch.setattr(source.EthernetNativeSource, '_configure', lambda owner: self.actions.append('configure'))
        monkeypatch.setattr(source, 'Library', lambda: None)
        monkeypatch.setattr(source, 'Context', lambda *a, **kw: self)
        monkeypatch.setattr(source.LeanSnapshot, 'decode', lambda raw: SimpleNamespace(
            require_live_prefix=lambda **kw: self.radio.origin,
            recovery_failed=False, dma_error=0, words=[0]*64))

    def clock(self):
        return self.radio.time

    def sleep(self, seconds):
        self.radio.advance(max(1, int(seconds*60_000_000)))

    @contextmanager
    def lease(self, name):
        self.leases.append(name)
        self.actions.append('acquire-'+name)
        try:
            yield
        finally:
            assert self.leases.pop() == name
            self.actions.append('release-'+name)

    def attest(self, *args, **kwargs):
        assert self.leases == ['station', 'ppu']
        self.actions.append('attest')
        fields = asdict(IDENTITY)
        if self.failure == 'identity':
            fields['boot_id'] = 'other'
        return {'remote': fields}

    def device(self, name):
        assert name == 'starlink-glrt-iq'
        return self

    def close(self):
        self.actions.append('context-close')

    def read(self, name):
        if name == 'native_schedule_snapshot':
            return self.radio.snapshot().decode()
        return {'capture_abi': 'GLF1-1.0-upper-only', 'native_schedule_abi': 'GLS1-1.0',
                'native_capture_enable': '0', 'capture_snapshot': 'simulated GLF1'}[name]

    def command(self, name, value):
        assert name == 'native_schedule_command'
        self.actions.append('command-'+str(value))
        if value == 16:
            assert not self.radio.valid
            self.radio.epoch += 1
            self.radio.valid = True
            # Complete all 24 new windows after the previous terminal sample.
            first = (self.radio.latest-self.radio.origin)//24+1000
            rows = [{'sample_start': first+i*13333, 'available_through_sample': first+i*13333+3402}
                    for i in range(24)]
            self.radio.advance(24*(rows[-1]['available_through_sample']+100)-
                               (self.radio.latest-self.radio.origin))
            history = {'schema': 'glrt-coarse-bootstrap-history/v2',
                'epoch_reference': 'acquired_full_pilot_template', 'physical_frame_epoch_qualified': False,
                'provisional': True, 'serial': IDENTITY.serial, 'visit': 7, 'native_origin': self.radio.origin,
                'history': rows}
            if self.failure == 'history_identity':
                history['serial'] = 'other'
            if self.failure != 'no_pilot':
                (self.pipeline.root/'work/ready.json').write_text(json.dumps(history))
        else:
            assert value in (2, 4)
            assert not self.radio.pending and not self.radio.queue
            if value == 4:
                self.radio.valid = False

    def predict(self, history, snapshot, origin):
        assert 'authenticated' in self.actions
        start = snapshot.latest_index+3_000_000
        seed = ScheduleBatch(snapshot.epoch, 7, start, 0, 80000*65536, 7310173*65536,
                             0, 17, 64, start+64*80000)
        return replace(seed, epoch=seed.epoch+1) if self.failure == 'seed_epoch' else seed

    def popen(self, argv, *, cwd, stdout, stderr):
        assert self.leases == ['station', 'ppu']
        output = Path(argv[argv.index('--output')+1])
        output.mkdir()
        name = output.name
        self.actions.append('start-'+name)
        if name == 'live':
            source.save(output/'protocol.json', {'schema': 'glrt-precision-stream/v1'})
        elif name == 'work':
            source.save(output/'protocol.json', {'scope': 'coarse_native_bootstrap_companion',
                        'arguments': {'template_relative': self.failure != 'companion_identity'}})
        else:
            assert name == 'capture'
            source.save(output/'live_source.json', {'schema': 'glrt-lean-live-source/v1',
                'serial': IDENTITY.serial, 'visit': 7, 'provisional': True, 'source_rate_hz': 60000000,
                'output_rate_hz': 2500000, 'native_samples_per_output_sample': 24})
        harness = self

        class Child:
            pid = 12345
            code = None

            def poll(self):
                if (self.code is None and harness.pipeline.source_end is not None
                        and harness.clock() >= harness.pipeline.source_end+1):
                    self.code = 0
                return self.code

            def send_signal(self, signum):
                assert signum == signal.SIGINT
                harness.actions.append('stop-'+name)
                self.code = 0

            def wait(self, timeout):
                assert timeout > 0
                return self.code

        return Child()

    def run(self, command, *, timeout_s, stdin=None):
        assert self.leases == ['station', 'ppu'] and 0 < timeout_s <= 30
        self.sleep(.001)
        if command == 'sh -s':
            if b'kill -INT' in stdin:
                if self.failure == 'uncertain_send':
                    raise OSError('no owned PID confirmed')
                self.actions.append('owned-stop')
                self.writer_active = False
                return 'OWNED_STOP_SENT\n'
            assert b'native_schedule_abi' in stdin
            return '/sys/devices/fake/iio:device0\n'
        if command == 'mktemp -d /tmp/glrt-acquired.XXXXXX':
            self.remote = '/tmp/glrt-acquired.'+str(self.episodes).zfill(6)
            return self.remote+'\n'
        if command.startswith('set -eu; test -f /usr/sbin/glrt_native_radio'):
            return ('c' if self.failure == 'controller_hash' else 'b')*64+'  /usr/sbin/glrt_native_radio\n'
        if command.startswith('cp ') or command == 'sha256sum -c':
            return ''
        if command.startswith(('rm -f ', 'rmdir ')):
            assert list((self.root/'evidence').glob('episode-*.glrj'))
            self.actions.append('scratch-remove')
            return ''
        if 'if test -s ' in command and '/exit' in command:
            if not hasattr(self, 'data') or getattr(self, 'writer_active', False):
                return 'RUNNING\n'
            return '0\n' if self.runtime_result == 0 else '1\n'
        if 'wc -c' in command:
            digest = hashlib.sha256(self.data).hexdigest()
            return f'PPU_SIZE={len(self.data)}\n{digest}  {self.remote}/journal\n'
        if 'dd if=' in command:
            index = int(re.search(r'skip=(\d+)', command)[1])
            data = self.data[index*65536:(index+1)*65536]
            if self.failure == 'export_corruption':
                data = b'X'+data[1:]
            return 'PPU_CHUNK_BEGIN\n'+data.decode()+'\nPPU_CHUNK_END\n'
        raise AssertionError('unexpected command: '+command)

    def run_prepared_stdin(self, command, *, byte_count, prepare, timeout_s, cancelled=None):
        self.sleep(.5)
        self.actions.append('authenticated')
        payload = prepare()
        assert len(payload) == byte_count == 4096 and command == 'sh -s'
        if self.failure == 'uncertain_send':
            raise OSError('simulated unknown SSH dispatch')
        seeds = sorted((self.root/'evidence').glob('evidence-*-seed'))
        seed = json.loads(seeds[-1].read_text())
        for key, value in seed.items():
            setattr(self.radio.seed, key, value)
        self.radio.events, self.radio.descriptors = [], []
        self.radio.lose_after = 32 if self.episodes == 0 else None
        self.radio.reject = False
        assert self.controller.glrt_native_controller_init(self.radio.state, c.byref(self.radio.ports),
            c.byref(self.radio.seed), 128 if self.episodes == 0 else 64, 2) == 0
        self.runtime_result = self.radio.run()
        self.data = journal(self.radio)
        self.episodes += 1
        if self.failure == 'cancel_execution':
            self.writer_active = True
            cancelled.__self__.set()
            raise InterruptedError('prepared wait cancelled')
        checked = source.review(self.data, epoch=self.radio.epoch)
        result = {'scope': 'finite_radio_local_feedback', 'result': self.runtime_result,
            'configured': len(checked['heads']), 'retained_popped': len(checked['heads']), 'journal_bytes': len(self.data)}
        return json.dumps(result, separators=(',', ':'))+'\nGLRT_RUNTIME_EXIT '+str(int(self.runtime_result != 0))+'\n'

    def supervise(self):
        session = PreparedNativeSession(self, self.owner, clock=self.clock)
        return supervise_native(session, identity=IDENTITY, events_path=self.root/'events.jsonl', clock=self.clock)


def test_complete_source_hooks_execute_export_reacquire_and_close_under_both_leases(
    tmp_path, monkeypatch, controller, pilot_words
):
    harness = Harness(tmp_path, monkeypatch, controller, pilot_words)
    result = harness.supervise()
    assert result['outcome'] == 'episode_limit_reached', result
    assert result['cleanup_verified'] and not result['physical_precision_qualified']
    assert [episode['result'] for episode in result['episodes']] == [-4, 0]
    assert [episode['epoch'] for episode in result['episodes']] == [3, 4]
    assert len(list((tmp_path/'evidence').glob('episode-*.glrj'))) == 2
    assert harness.actions[-2:] == ['release-ppu', 'release-station']
    assert not any(action.startswith('stop-') for action in harness.actions)
    assert harness.clock() >= harness.pipeline.source_end
    assert harness.actions.count('scratch-remove') == 4
    assert not harness.leases


@pytest.mark.parametrize('samples,delay,budget', [(150_000_000, 50, 240),
                                                (1_250_000_000, 450, 600)])
def test_late_candidate_gets_bounded_native_run(
    tmp_path, monkeypatch, controller, pilot_words, samples, delay, budget
):
    harness = Harness(tmp_path, monkeypatch, controller, pilot_words)
    harness.owner.samples = samples
    command, transport = harness.command, harness.run_prepared_stdin
    scripts = []

    def delayed_history(name, value):
        if value == 16:
            harness.sleep(delay)
        return command(name, value)

    def capture_script(command, *, prepare, **kwargs):
        def retain_script():
            script = prepare()
            scripts.append(script)
            return script
        return transport(command, prepare=retain_script, **kwargs)

    monkeypatch.setattr(harness, 'command', delayed_history)
    monkeypatch.setattr(harness, 'run_prepared_stdin', capture_script)
    session = PreparedNativeSession(harness, harness.owner, clock=harness.clock)
    result = supervise_native(session, identity=IDENTITY, events_path=tmp_path/'events.jsonl',
        limits=NativeSupervisorLimits(budget, 1, 30), clock=harness.clock)
    assert result['outcome'] == 'episode_limit_reached' and result['cleanup_verified'], result
    assert len(scripts) == 1
    seconds = int(re.search(rb'32768 ([0-9]+) --bootstrap-slices', scripts[0])[1])
    assert 1 <= seconds <= min(45, samples/2_500_000-delay-5)
    assert harness.clock() >= harness.pipeline.source_end


@pytest.mark.parametrize('failure', ['recovery', 'fault', 'queued'])
def test_cleanup_cannot_claim_reusable_radio_with_latched_coarse_fault(
    tmp_path, monkeypatch, controller, pilot_words, failure
):
    harness = Harness(tmp_path, monkeypatch, controller, pilot_words, 'no_pilot')
    words = [0]*64
    if failure == 'fault':
        words[18] = 4
    if failure == 'queued':
        words[19] = 2
    monkeypatch.setattr(source.LeanSnapshot, 'decode', lambda raw: SimpleNamespace(
        require_live_prefix=lambda **kw: harness.radio.origin,
        recovery_failed=failure == 'recovery', dma_error=0, words=words))
    result = harness.supervise()
    assert result['outcome'] == 'failed' and not result['cleanup_verified']
    assert not harness.leases
    retained = [json.loads(p.read_text()) for p in (tmp_path/'evidence').glob('*-cleanup')]
    assert any('coarse capture fault' in error for entry in retained for error in entry['errors'])


@pytest.mark.parametrize('failure', ['identity', 'history_identity', 'seed_epoch', 'controller_hash',
    'companion_identity', 'export_corruption', 'uncertain_send'])
def test_source_failures_close_without_second_submission(tmp_path, monkeypatch, controller, pilot_words, failure):
    harness = Harness(tmp_path, monkeypatch, controller, pilot_words, failure)
    result = harness.supervise()
    assert result['outcome'] == 'failed' and result['error']
    assert harness.episodes <= 1
    assert not harness.leases
    assert 'scratch-remove' not in harness.actions
    if failure in ('identity', 'companion_identity'):
        assert 'start-capture' not in harness.actions
    if failure == 'uncertain_send':
        assert not result['cleanup_verified']


def test_absent_pilot_clears_unlaunched_epoch_and_stops_bounded_source(tmp_path, monkeypatch, controller, pilot_words):
    harness = Harness(tmp_path, monkeypatch, controller, pilot_words, 'no_pilot')
    result = harness.supervise()
    assert result['outcome'] == 'no_supported_candidate', result
    assert result['cleanup_verified'] and harness.episodes == 0
    assert not harness.radio.valid and not harness.leases
    assert 'command-4' in harness.actions


def test_cancellation_stops_owned_writer_keeps_remote_journal_and_does_not_reacquire(
    tmp_path, monkeypatch, controller, pilot_words
):
    harness = Harness(tmp_path, monkeypatch, controller, pilot_words, 'cancel_execution')
    result = harness.supervise()
    assert result['outcome'] == 'cancelled', result
    assert result['cleanup_verified'] and not result['episodes']
    assert harness.episodes == 1 and not harness.leases
    assert 'owned-stop' in harness.actions and 'scratch-remove' not in harness.actions
    paths = list((tmp_path/'evidence').glob('*-interrupted-remote-journal'))
    retained = json.loads(paths[0].read_text())
    assert not retained['exported'] and not retained['reviewed']
    assert retained['sha256'] == hashlib.sha256(harness.data).hexdigest()


def test_capture_that_cannot_fit_deadline_is_rejected_before_rx(tmp_path, monkeypatch, controller, pilot_words):
    harness = Harness(tmp_path, monkeypatch, controller, pilot_words)
    harness.owner.samples = 600_000_000
    result = harness.supervise()
    assert result['outcome'] == 'failed'
    assert 'finite source' in result['error']
    assert 'start-capture' not in harness.actions
    assert not harness.leases


def test_export_deadline_is_absolute_across_chunks():
    clock = [0.0]
    class Transport:
        def __init__(self):
            self.calls = []
        def run(self, command, *, timeout_s):
            self.calls.append(timeout_s)
            clock[0] += 1
            return ''
    transport = Transport()
    bound = source.DeadlineTransport(transport, 2, lambda: clock[0])
    bound.run('read')
    bound.run('read')
    with pytest.raises(TimeoutError):
        bound.run('read')
    assert transport.calls == [2, 1]


def test_capture_commands_use_ethernet_complete_buffer_and_declared_public_clis(tmp_path):
    commands = PROGRAMS.commands(tmp_path, IDENTITY, '192.168.1.20', 7, 600_000_000)
    assert [name for name, _, _ in commands] == ['precision', 'companion', 'coarse']
    collector = commands[-1][1]
    assert collector[collector.index('--uri')+1] == 'ip:192.168.1.20'
    assert collector[collector.index('--chunk-samples')+1] == '250000'
    assert collector[collector.index('--samples')+1] == '600000000'
    assert 'leo.cli.glrt_precision' in commands[0][1]


def test_selected_tuning_and_long_follower_budget_reach_collector(tmp_path, monkeypatch):
    pipeline = source.CapturePipeline(replace(PROGRAMS, rx_lo_hz=1440312500), tmp_path/'source')
    owner = source.EthernetNativeSource(transport=None, deployment=tmp_path/'deployment',
        controller_sha256='b'*64, host='192.168.1.20', visit=7, pipeline=pipeline,
        evidence=tmp_path/'evidence', station_lease=None, predict=None, samples=1_250_000_000)
    owner.identity = IDENTITY
    requests = []
    def configure(**kwargs):
        requests.append(kwargs)
        return {'configured': {'rf_state': {'rx_lo': '1440312498'}}}
    monkeypatch.setattr(source.g, 'configure_native_source', configure)
    monkeypatch.setattr(owner, 'retain', lambda *args: None)
    owner._configure()
    assert requests[0]['lo_hz'] == 1440312500
    commands = pipeline.programs.commands(tmp_path, IDENTITY, '192.168.1.20', 7, 1_250_000_000)
    collector, follower = commands[-1][1], commands[1][1]
    assert collector[collector.index('--lo-hz')+1] == '1440312498'
    assert float(follower[follower.index('--timeout')+1]) == 620


@pytest.mark.parametrize('lo', [True, 0, 6_000_000_001, '1440312500'])
def test_invalid_tuning_is_rejected_before_configuration(lo):
    with pytest.raises(ValueError, match='RX LO'):
        replace(PROGRAMS, rx_lo_hz=lo)


def test_unapproved_target_rejected_before_any_source_action(tmp_path):
    with pytest.raises(ValueError, match='bounded authorized'):
        source.EthernetNativeSource(transport=None, deployment=tmp_path/'deployment',
            controller_sha256='b'*64, host='192.168.1.14', visit=7, pipeline=None,
            evidence=tmp_path/'evidence', station_lease=None, predict=None)


@pytest.mark.parametrize('host,serial', [
    ('192.168.1.21', IDENTITY.serial),
    ('192.168.1.20', '10400056f695001322002d0010ad1719f2'),
])
def test_authorized_address_cannot_be_combined_with_other_serial(tmp_path, host, serial):
    owner = source.EthernetNativeSource(transport=None, deployment=tmp_path/'deployment',
        controller_sha256='b'*64, host=host, visit=7, pipeline=None,
        evidence=tmp_path/'evidence', station_lease=None, predict=None)
    with pytest.raises(ValueError, match='exact authorized serial/address'):
        owner.open(replace(IDENTITY, serial=serial), 10, Event())
    assert not (tmp_path/'evidence').exists()


def test_radio21_accepts_identity_then_requires_station_lease(tmp_path):
    def refuse(identity, deadline):
        assert identity.serial == '10400056f695001322002d0010ad1719f2'
        raise RuntimeError('station busy')
    owner = source.EthernetNativeSource(transport=None, deployment=tmp_path/'deployment',
        controller_sha256='b'*64, host='192.168.1.21', visit=7, pipeline=None,
        evidence=tmp_path/'evidence', station_lease=refuse, predict=None)
    with pytest.raises(RuntimeError, match='station busy'):
        owner.open(replace(IDENTITY, serial='10400056f695001322002d0010ad1719f2'), 10, Event())


@pytest.mark.parametrize('owned', [True, False])
def test_stop_script_signals_only_the_executable_in_its_owned_directory(tmp_path, owned):
    """Run the actual shell identity guard against local disposable processes."""
    scratch = tmp_path/'glrt-acquired.ABCDEF'
    scratch.mkdir()
    other = tmp_path/'other'
    other.mkdir()
    program = tmp_path/'wait.c'
    program.write_text('#include <signal.h>\n#include <unistd.h>\n#include <stdio.h>\n'
        'static volatile sig_atomic_t done;\nstatic void stop(int s) {(void)s; done=1;}\n'
        'int main(void) {signal(SIGINT,stop); puts("READY"); fflush(stdout); '
        'while(!done) pause(); return 0;}\n')
    executable = (scratch if owned else other)/'controller'
    subprocess.run(['cc', str(program), '-o', str(executable)], check=True, capture_output=True)
    process = subprocess.Popen([str(executable)], stdout=subprocess.PIPE, text=True)
    assert process.stdout.readline() == 'READY\n'
    (scratch/'pid').write_text(str(process.pid)+'\n')

    class LocalTransport:
        def run(self, command, *, timeout_s, stdin=None):
            if process.poll() is not None and not (scratch/'exit').exists():
                (scratch/'exit').write_text(str(process.returncode)+'\n')
            completed = subprocess.run(command, shell=True, input=stdin, capture_output=True,
                                       timeout=timeout_s, check=True)
            return completed.stdout.decode()

    owner = object.__new__(source.EthernetNativeSource)
    owner.remote, owner.transport = str(scratch), LocalTransport()
    owner.clock, owner.sleep = time.monotonic, time.sleep
    try:
        if owned:
            owner._stop_owned_writer(time.monotonic()+2)
            assert process.wait(timeout=1) == 0
        else:
            with pytest.raises(subprocess.CalledProcessError):
                owner._stop_owned_writer(time.monotonic()+2)
            assert process.poll() is None
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=2)
        process.stdout.close()
