"""Original-IQ replay must pass before a positive or negative local fit is used."""
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tools import starlink_glrt_native_support as support
from tools.starlink_glrt_native_abi import SAMPLES, NativeResult
from tools.starlink_glrt_native_replay import coefficients

from .test_native_capture_rtl import native_bank
from .test_native_control_rtl import record
from .test_native_replay import write_capture
from .test_native_solver import BANK
from .test_native_solver import solver as solver  # noqa: PLC0414


@pytest.fixture(scope="module")
def captures():
    raw = np.asarray(coefficients(BANK.read_bytes()), dtype=np.int64)
    ref = raw[:, 0] + 1j*raw[:, 1]
    rng = np.random.default_rng(741)
    cases = {
        "pilot": np.rint(np.column_stack((ref.real, ref.imag))*.25).astype(np.int64),
        "noise": np.rint(rng.normal(0, 2000, (SAMPLES, 2))).astype(np.int64),
        "zero": np.zeros((SAMPLES, 2), dtype=np.int64),
    }
    result = {}
    start = 2**55+12345
    for name, iq in cases.items():
        words = record((start, 0, 0), SAMPLES, native_bank(),
            iq_values=[(start+n, int(i), int(q)) for n, (i, q) in enumerate(iq)])
        result[name] = struct.pack("<32I", *words), iq.astype("<i2").tobytes()
    return result


def evaluate(root, solver):
    library = Path(solver._name)
    return support.evaluate_capture(root, BANK, library,
        solver_sha256=hashlib.sha256(library.read_bytes()).hexdigest())


@pytest.mark.parametrize("name", ["pilot", "noise", "zero"])
def test_full_original_iq_replay_precedes_local_support_and_controls_keep_null_estimates(
        tmp_path, solver, captures, name):
    write_capture(tmp_path, captures[name], exact=True)
    result = evaluate(tmp_path, solver)
    assert result["replay"]["status"] == "arithmetic_pass"
    assert result["fits"][0]["supported"] == (name == "pilot")
    assert result["status"] == ("supported_local_fits" if name == "pilot" else "local_fit_rejected")
    fit = result["fits"][0]
    if name == "pilot":
        assert fit["coherence"] > .99
        assert abs(fit["delay_correction_s"]) < 1e-9 and abs(fit["residual_cfo_hz"]) < 1
    else:
        assert fit["rejection"] and fit["delay_correction_s"] is None and fit["cfo_hz"] is None
    assert result["acquisition_verified"] is result["source_continuity_verified"] is False
    assert result["precision_qualified"] is False


def test_mismatched_library_is_rejected_before_loading(tmp_path, solver, captures, monkeypatch):
    write_capture(tmp_path, captures["pilot"], exact=True)
    monkeypatch.setattr(support.C, "CDLL", lambda *a: pytest.fail("unverified library load"))
    with pytest.raises(ValueError, match="pinned digest"):
        support.evaluate_capture(tmp_path, BANK, Path(solver._name), solver_sha256="0"*64)


@pytest.mark.parametrize("fault", ["saved_iq", "post_replay_result"])
def test_changed_native_evidence_cannot_reach_supported_output(tmp_path, solver, captures, monkeypatch, fault):
    write_capture(tmp_path, captures["pilot"], exact=True)
    if fault == "saved_iq":
        with (tmp_path/"job-0/iq.ci16").open("r+b") as stream:
            stream.write(b"xx")
    else:
        replay = support.verify_capture
        def changed(*args):
            checked = replay(*args)
            path = tmp_path/"job-0/result.raw"
            words = list(struct.unpack("<32I", path.read_bytes()))
            words[9] += 1
            path.write_bytes(struct.pack("<32I", *words))
            # Same start/tag; a stale association check alone cannot detect this.
            assert NativeResult.decode(path.read_bytes()).start == int(checked["start_sample"])
            return checked
        monkeypatch.setattr(support, "verify_capture", changed)
    with pytest.raises(ValueError, match="transport hashes|changed after"):
        evaluate(tmp_path, solver)


def test_support_cli_keeps_complete_replay_and_supported_fit(tmp_path, solver, captures):
    write_capture(tmp_path, captures["pilot"], exact=True)
    library = Path(solver._name)
    output = tmp_path/"support.json"
    command = [sys.executable, "-m", "tools.starlink_glrt_native_support",
        "--capture", str(tmp_path), "--bank", str(BANK), "--solver", str(library),
        "--solver-sha256", hashlib.sha256(library.read_bytes()).hexdigest(), "--output", str(output)]
    process = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
    assert process.returncode == 0, process.stderr
    result = json.loads(output.read_text())
    assert result["status"] == "supported_local_fits" and result["replay"]["status"] == "arithmetic_pass"
    assert result["fits"][0]["supported"] and not result["precision_qualified"]
    original = output.read_bytes()
    again = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
    assert again.returncode != 0 and "already exists" in again.stderr
    assert output.read_bytes() == original
