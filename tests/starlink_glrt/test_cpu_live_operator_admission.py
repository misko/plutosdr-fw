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
@pytest.mark.parametrize('blocks', [1536,4096])
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
    required_kib = 16384*blocks*4//1024 + 80*1024
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
