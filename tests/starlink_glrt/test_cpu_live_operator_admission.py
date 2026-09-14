"""Admission failures retain truthful receipts and never contact the radio."""
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from tools.generate_glrt_tracking_gram import reference_rows
from .test_cpu_coarse import bank


@pytest.fixture
def storage_operator(tmp_path, monkeypatch):
    """No radio or production lease objects are available to these storage tests."""
    def module(name, **values):
        result = ModuleType(name);result.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, result)
    module('leo');module('leo.acquisition')
    module('leo.acquisition.authority', LocalCaptureAuthority=None, RadioResource=None, CaptureTaskKind=None)
    module('pluto_plus', bootstrap_firmware=None, glrt_canary=None)
    module('pluto_plus.glrt_iq_tracking_profiles', ENDPOINT=('serial20','192.168.1.20'))
    module('pluto_plus.radio_lock', acquire_radio_lock=None)
    module('pluto_plus.release_candidate_rx_only_linux', _close_iio_context=None)
    module('deploy_glrt_iq_tracking20', EVIDENCE=tmp_path, PASSWORD=tmp_path/'unused')
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('live_operator_storage', root/'scripts/qualify_glrt_cpu_live20.py')
    operator = importlib.util.module_from_spec(spec);spec.loader.exec_module(operator)
    return operator


@pytest.mark.parametrize('blocks', [1536,4096,45000])
@pytest.mark.parametrize('case', ['ready','short','wrong_mount','wrong_fs','malformed'])
def test_filesystem_capacity_is_separate_from_available_memory(storage_operator, blocks, case):
    remote = '/tmp/gli-live20-test'
    mount = remote if blocks != 1536 else '/tmp'
    required = (256*1024 if blocks == 45000 else blocks*64) + 40*1024
    free = required-1 if case == 'short' else required
    if case == 'wrong_mount': mount = '/mnt/jffs2'
    filesystem = 'mtd2' if case == 'wrong_fs' else 'tmpfs'
    output = f'Filesystem 1024-blocks Used Available Capacity Mounted on\n{filesystem} 327680 0 {free} 0% {mount}\n'
    if case == 'malformed': output = output.splitlines()[0]
    evidence = {}
    storage_operator.preflight_memory('MemAvailable: 440000 kB\n', blocks, evidence)
    if case == 'ready':
        storage_operator.preflight_filesystem(output, remote, blocks, evidence)
        assert evidence['filesystem_preflight']['required_kib'] == required
    else:
        with pytest.raises(ValueError):
            storage_operator.preflight_filesystem(output, remote, blocks, evidence)


@pytest.mark.parametrize('blocks,spacing',[(4096,3),(45000,3),(1536,0),(1536,6)])
def test_observer_cadence_rejects_unbounded_or_unknown_profile(storage_operator,blocks,spacing):
    with pytest.raises(ValueError): storage_operator.observer_profile(blocks,spacing)
    with pytest.raises(ValueError): storage_operator.capture_artifacts(blocks,spacing)


def test_three_frame_profile_retains_selected_iq_and_one_episode(storage_operator):
    assert storage_operator.observer_profile(1536,3)=='1536-selected-observer3'
    names=storage_operator.capture_artifacts(1536,3)
    assert 'scan.iq.ci16' in names and 'iq.ci16' not in names
    assert 'observer.jsonl' in names and 'observer.iq.ci16' in names
    assert not any(name.startswith('native-') for name in names)


@pytest.mark.parametrize('mounted', [False,True])
@pytest.mark.parametrize('attempted,terminal,retrieved,expected', [
    (False,False,False,True), (True,False,False,False),
    (True,True,False,False), (True,True,True,True),
])
def test_storage_cleanup_preserves_uncertain_execution_and_unretrieved_evidence(
        storage_operator, mounted, attempted, terminal, retrieved, expected):
    commands = []
    def run(command):
        commands.append(command)
        return SimpleNamespace(check_returncode=lambda: None)
    assert storage_operator.cleanup_evidence(run, '/tmp/gli-test', ['probe','iq.ci16'],
        mounted=mounted, execution_attempted=attempted, terminal=terminal, retrieved=retrieved) == expected
    assert commands == (['rm -f /tmp/gli-test/probe /tmp/gli-test/iq.ci16'] +
        (['umount /tmp/gli-test'] if mounted else []) + ['rmdir /tmp/gli-test'] if expected else [])


@pytest.mark.parametrize("failure", ["busy", "bank", "references", "lo", "rate"])
def test_refusal_precedes_radio_contact_and_records_busy_receipt(tmp_path, monkeypatch, failure):
    root = Path(__file__).resolve().parents[2]
    calls = []

    def contact(*args, **kwargs):
        calls.append("radio_contact")
        pytest.fail("refused invocation must not contact the radio")

    class Authority:
        def __init__(self, *args): pass
        def claim(self, *args, **kwargs):
            calls.append("claim")
            raise RuntimeError("radio lease is busy")

    def module(name, **values):
        result = ModuleType(name)
        result.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, result)
        return result

    module("leo");module("leo.acquisition")
    module("leo.acquisition.authority", LocalCaptureAuthority=Authority,
           RadioResource=lambda *args: args, CaptureTaskKind=SimpleNamespace(QUALIFICATION="qualification"))
    b = SimpleNamespace(BoundSshBootstrapTransport=contact)
    g = SimpleNamespace(deployment_identity=lambda *args, **kwargs: (
        {"expected_firmware": "wrong" if failure == "rate" else "glrt-iq-tracking-r30000000-v1"},
        SimpleNamespace(return_iio_layout=None)))
    module("pluto_plus", bootstrap_firmware=b, glrt_canary=g)
    module("pluto_plus.glrt_iq_tracking_profiles", ENDPOINT=("serial20", "192.168.1.20"))
    module("pluto_plus.radio_lock", acquire_radio_lock=contact)
    module("pluto_plus.release_candidate_rx_only_linux", _close_iio_context=contact)
    module("deploy_glrt_iq_tracking20", EVIDENCE=tmp_path, PASSWORD=tmp_path/"must_not_read_password")
    spec = importlib.util.spec_from_file_location("live_operator_admission", root/"scripts/qualify_glrt_cpu_live20.py")
    operator = importlib.util.module_from_spec(spec);spec.loader.exec_module(operator)
    coefficients = bank().astype("<i2")
    if failure == "bank": coefficients[0, 0, 0, 0] ^= 1
    coefficients.tofile(tmp_path/"coarse-bank.ci16")
    rom = root/"hdl/library/starlink_glrt"
    refs = np.asarray([reference_rows((rom/"native_cubic_60000000_upper.mem").read_bytes(),
        (rom/"native_direct_2500000_phase4_upper_interleaved.mem").read_bytes(), 2500000, p)
        for p in range(4)], dtype="<i2")
    if failure == "references": refs[0, 0, 0] ^= 1
    refs.tofile(tmp_path/"direct-references.ci16")
    (tmp_path/"probe").write_bytes(b"test-only executable, never dispatched")
    output = tmp_path/"evidence"
    monkeypatch.setattr(sys, "argv", ["qualify", "--deployment", "unused.json", "--rate", "30000000",
        "--binary", str(tmp_path/"probe"), "--output", str(output), "--lo-hz", "1" if failure == "lo" else "1690312496"])
    with pytest.raises((ValueError, RuntimeError)):
        operator.main()
    assert calls == (["claim"] if failure == "busy" else [])
    if failure == "busy":
        receipt = json.loads((output/"operator.json").read_text())
        assert receipt["status"] == "admission_refused" and receipt["rf_samples_collected"] == 0
        assert receipt["live_tracking_qualified"] is False
    else:
        assert not output.exists()


@pytest.mark.parametrize('case', [
    'ready', 'boot_drops', 'unread', 'active', 'unaccounted', 'fault',
    'epoch_valid', 'uncleared', 'wrong_rate', 'malformed', 'missing',
    'memory_short', 'memory_missing', 'memory_unit', 'memory_duplicate',
])
@pytest.mark.parametrize('blocks', [1536,4096,45000])
def test_native_preflight_precedes_every_rf_mutation(tmp_path, monkeypatch, case, blocks):
    """A prior failed controller's retained results survive a later invocation."""
    def module(name, **values):
        result = ModuleType(name)
        result.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, result)
        return result

    mutations = []
    module('leo');module('leo.acquisition')
    module('leo.acquisition.authority', LocalCaptureAuthority=None,
           RadioResource=None, CaptureTaskKind=None)
    module('pluto_plus', bootstrap_firmware=None, glrt_canary=SimpleNamespace(
        configure_checked_rx=lambda *args, **kwargs: mutations.append(kwargs)))
    module('pluto_plus.glrt_iq_tracking_profiles', ENDPOINT=('serial20', '192.168.1.20'))
    module('pluto_plus.radio_lock', acquire_radio_lock=None)
    module('pluto_plus.release_candidate_rx_only_linux', _close_iio_context=None)
    module('deploy_glrt_iq_tracking20', EVIDENCE=tmp_path, PASSWORD=tmp_path/'unused')
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('live_operator_preflight', root/'scripts/qualify_glrt_cpu_live20.py')
    operator = importlib.util.module_from_spec(spec);spec.loader.exec_module(operator)
    # CLEAR invalidates the epoch but preserves its monotonically increasing ID.
    words = [0x474c5431, 3, 19, 42, 7, 0, 0, 0, 0, 0, 0, 0, 0, 0,
             0, 0, 0, 0, 0, 0, 30000000, 39600, 0xb04a2fab, 1]
    if case == 'boot_drops': words[18:20] = [31, 72]
    if case == 'unread':
        for index in (7, 8, 14, 16, 17): words[index] = 1
    if case == 'active': words[5] = 4
    if case == 'unaccounted': words[7] = 1
    if case == 'fault': words[6] = 8
    if case == 'epoch_valid': words[5] = 16
    if case == 'uncleared':
        for index in (7, 8, 14, 15, 17): words[index] = 1
    if case == 'wrong_rate': words[20:22] = [60000000, 79200]
    wire = 'GLT1SNAP 00010000 '+' '.join(f'{word:08x}' for word in words)+'\n'
    if case == 'malformed': wire = wire[:-10]
    device = None if case == 'missing' else SimpleNamespace(attrs={
        'tracking_snapshot': SimpleNamespace(value=wire)})
    context = SimpleNamespace(find_device=lambda name: device)
    evidence = {}
    required_kib = (256*1024 if blocks == 45000 else blocks*64) + 80*1024
    memory_info = f'MemAvailable:    {required_kib} kB\n'
    if case == 'memory_short': memory_info = f'MemAvailable: {required_kib-1} kB\n'
    if case == 'memory_missing': memory_info = 'MemFree: 500000 kB\n'
    if case == 'memory_unit': memory_info = f'MemAvailable: {required_kib} MB\n'
    if case == 'memory_duplicate': memory_info *= 2
    if case in ('ready', 'boot_drops'):
        operator.configure_idle_rx(context, rate=30000000, lo_hz=1690312496, evidence=evidence,
                                   memory_info=memory_info, blocks=blocks)
        assert len(mutations) == 1 and mutations[0]['source_rate'] == 30000000
        assert evidence['memory_preflight']['required_kib'] == required_kib
    else:
        with pytest.raises(ValueError):
            operator.configure_idle_rx(context, rate=30000000, lo_hz=1690312496, evidence=evidence,
                                       memory_info=memory_info, blocks=blocks)
        assert mutations == []
    if case != 'missing' and not case.startswith('memory_'):
        assert evidence['tracking_before_configuration'] == wire


def test_selected_capture_budget_and_artifacts_are_explicit(storage_operator):
    selected = storage_operator.capture_artifacts(45000)
    assert 'scan.iq.ci16' in selected and 'iq.ci16' not in selected
    assert selected[-3:] == ('native-1.journal','native-2.journal','native-3.journal')
    assert storage_operator.retention_budget_kib(45000) == 256*1024
    assert {'observer.jsonl','observer.iq.ci16'} <= set(selected)
    # The long scan64 profile's worst-case selected IQ and grids fit the allowance.
    assert 80_000_000+14_400_000+37_600_000+4*200*3300*4+4*8*1024**2 < 256*1024**2
    for blocks in (1536,4096):
        assert storage_operator.capture_artifacts(blocks) == storage_operator.ARTIFACTS
    for blocks in (0,45001):
        with pytest.raises(ValueError): storage_operator.capture_artifacts(blocks)


@pytest.mark.parametrize('blocks,spacing,budget,valid',[
    (1536,3,64,True),(45000,3,64,True),(1536,9,64,False),(4096,3,64,False),(45000,9,64,False),
    (1536,3,65,False),(1536,3,0,False)])
def test_expanded_scan_is_admitted_only_in_short_selected_profile(storage_operator,blocks,spacing,budget,valid):
    if valid:
        expected='1536-selected-observer3-scan64' if blocks==1536 else '45000-selected-observer3-scan64'
        assert storage_operator.observer_profile(blocks,spacing,budget)==expected
        artifacts=storage_operator.capture_artifacts(blocks,spacing,budget)
        assert 'scan.iq.ci16' in artifacts and 'iq.ci16' not in artifacts
        assert any(n.startswith('native-') for n in artifacts)==(blocks==45000)
    else:
        with pytest.raises(ValueError):storage_operator.observer_profile(blocks,spacing,budget)


@pytest.mark.parametrize('missing',[None,'observer.jsonl','observer.iq.ci16'])
def test_observer_artifacts_are_required_even_without_handoff(storage_operator,missing):
    evidence={'artifacts':{name:{'bytes':0} for name in ('observer.jsonl','observer.iq.ci16')}}
    if missing:
        evidence['artifacts'][missing]=None
        with pytest.raises(ValueError,match='missing passive observer evidence'):
            storage_operator.require_observer_artifacts(evidence)
    else: storage_operator.require_observer_artifacts(evidence)


@pytest.mark.parametrize('failed', [False,True])
@pytest.mark.parametrize('changed', [False,True])
def test_failed_capture_still_records_final_rf_comparison(storage_operator, failed, changed):
    calls=[]
    context=SimpleNamespace(attrs={'hw_serial':'serial20','fw_version':'image'},find_device=lambda _: object())
    def rf_state(_):
        calls.append('rf_read');return {'lo': 2 if changed else 1}
    def check_exit():
        calls.append('check_exit')
        if failed: raise RuntimeError('capture failed')
    storage_operator.g=SimpleNamespace(rf_state=rf_state)
    evidence={'configured':{'rf_state':{'lo':1}}}
    result=SimpleNamespace(check_returncode=check_exit)
    if failed or changed:
        with pytest.raises(ValueError if changed else RuntimeError):
            storage_operator.check_terminal_capture(context,result,'image',evidence)
    else:
        storage_operator.check_terminal_capture(context,result,'image',evidence)
    assert evidence['rf_after']=={'lo':2 if changed else 1}
    assert calls==(['rf_read'] if changed else ['rf_read','check_exit'])
