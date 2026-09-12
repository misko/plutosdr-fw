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
