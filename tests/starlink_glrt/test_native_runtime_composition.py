"""Complete software composition: host/PPU/source/C with simulated external I/O.

Requires the host checkout's src and PPU src on PYTHONPATH explicitly. No radio,
network, production-control access or RF. Both real lease implementations use
isolated temporary directories; hardware packages are real, I/O is simulated.
"""
import json
from contextlib import contextmanager
from dataclasses import asdict

import pytest
from leo.acquisition.authority import (
    CaptureTaskKind,
    LocalCaptureAuthority,
    RadioBusyError,
    RadioResource,
)
from leo.acquisition.native_runtime import (
    TARGET,
    NativeRuntimeRequest,
    run_native_capture,
)
from leo.analysis.research.coarse_native_bootstrap import CoarsePilotObservation
from pluto_plus.radio_lock import acquire_radio_lock

from tests.starlink_glrt.test_native_source import IDENTITY, PROGRAMS, Harness
from tools import starlink_glrt_native_source as source

pytest_plugins = ('tests.starlink_glrt.test_native_controller',)


@pytest.mark.parametrize('failure', [None, 'identity', 'no_pilot', 'uncertain_send',
    'export_corruption', 'cancel_execution', 'history_identity', 'companion_identity'])
def test_full_composition_with_actual_predictor_authority_adapters_and_controller(
    tmp_path, monkeypatch, controller, pilot_words, failure
):
    harness = Harness(tmp_path, monkeypatch, controller, pilot_words, failure)
    output = tmp_path/'runtime'
    harness.root = output
    authority = LocalCaptureAuthority(tmp_path/'control', (TARGET,
        RadioResource('scanner', 'separate-radio', 'ip:192.168.1.21')))
    before = authority.snapshot()
    real_pipeline = source.CapturePipeline
    real_source = source.EthernetNativeSource
    real_command = harness.command
    real_run = harness.run

    def pipeline(programs, root, *, clock):
        harness.pipeline = real_pipeline(programs, root, popen=harness.popen, clock=clock,
                                         sleep=harness.sleep)
        return harness.pipeline

    def adapter(**kwargs):
        kwargs['sleep'] = harness.sleep
        harness.owner = real_source(**kwargs)
        # Harness retains the same layout expected by its simulated wire peer.
        assert kwargs['evidence'] == output/'native'
        return harness.owner

    @contextmanager
    def ppu_lock(serial):
        # The actual host admission must already exclude the scanner.
        with pytest.raises(RadioBusyError):
            authority.claim(('scanner',), task_id='conflict', task_kind=CaptureTaskKind.SCANNER_SWEEP)
        with acquire_radio_lock(serial, root=tmp_path/'ppu-locks'):
            harness.leases.extend(['station', 'ppu'])
            try:
                yield
            finally:
                assert harness.leases.pop() == 'ppu'
                assert harness.leases.pop() == 'station'

    def command(name, value):
        real_command(name, value)
        ready = harness.pipeline.root/'work/ready.json'
        if value == 16 and ready.exists():
            history = json.loads(ready.read_text())
            history['history'] = [asdict(CoarsePilotObservation(
                i*4, row['sample_start'], row['available_through_sample'],
                0, 102_000+i*.1, 1, 0, True, True,
            )) for i, row in enumerate(history['history'])]
            ready.write_text(json.dumps(history))

    def run(command, **kwargs):
        # The peer fixture's artifact lookup predates the composed layout.
        evidence = output/'evidence'
        if harness.owner.evidence.exists() and not evidence.exists():
            evidence.symlink_to(harness.owner.evidence, target_is_directory=True)
        return real_run(command, **kwargs)

    monkeypatch.setattr(source, 'CapturePipeline', pipeline)
    monkeypatch.setattr(source, 'EthernetNativeSource', adapter)
    monkeypatch.setattr(source, 'acquire_radio_lock', ppu_lock)
    monkeypatch.setattr(harness, 'command', command)
    monkeypatch.setattr(harness, 'run', run)
    request = NativeRuntimeRequest(identity=IDENTITY, programs=PROGRAMS,
        deployment=tmp_path/'deployment.json', controller_sha256='b'*64, output=output,
        visit=7, task_id='composed-native-test')
    result = run_native_capture(request, authority=authority, transport=harness,
                                handle_signals=False, clock=harness.clock)
    assert authority.snapshot() == before and not harness.leases
    with authority.claim_exact((TARGET,), task_id='after', task_kind=CaptureTaskKind.QUALIFICATION):
        pass
    assert result['physical_precision_qualified'] is False
    assert result['autonomous_service_deployed'] is False
    if failure is None:
        assert result['outcome'] == 'episode_limit_reached', result
        assert result['cleanup_verified']
        assert [item['result'] for item in result['episodes']] == [-4, 0]
        assert [item['supported'] for item in result['episodes']] == [32, 64]
        assert len(list((output/'native').glob('episode-*.glrj'))) == 2
    elif failure == 'no_pilot':
        assert result['outcome'] == 'no_supported_candidate', result
        assert result['cleanup_verified'] and harness.episodes == 0
    elif failure == 'cancel_execution':
        assert result['outcome'] == 'cancelled', result
        assert result['cleanup_verified'] and harness.episodes == 1
    else:
        assert result['outcome'] == 'failed', result
        assert harness.episodes <= 1


def test_short_rf_session_bounds_native_execution_before_source_end(tmp_path, monkeypatch, controller, pilot_words):
    harness = Harness(tmp_path, monkeypatch, controller, pilot_words)
    harness.owner.samples = 50_000_000
    result = harness.supervise()
    assert result['outcome'] == 'episode_limit_reached', result
    assert harness.owner.native_runtime_seconds == 10
    assert harness.owner.launch_deadline <= harness.pipeline.source_end-6
