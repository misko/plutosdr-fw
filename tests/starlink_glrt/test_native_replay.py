"""Offline arithmetic replay, including corrupted IQ and mismatched receipts."""
import hashlib
import json
import struct
from dataclasses import replace
from fractions import Fraction

import pytest

from tools.starlink_glrt_native_abi import RATE, SAMPLES, NativeResult
from tools.starlink_glrt_native_replay import round_even, verify, verify_capture

from .ddc import BANK_ROOT
from .test_native_capture_rtl import native_bank
from .test_native_control_rtl import record


@pytest.fixture(scope="module")
def evidence():
    job = (2**55+177, 2**32-9, 2**32-97137)
    iq = [((n*977 % 65536)-32768, (n*331 % 65536)-32768) for n in range(SAMPLES)]
    payload = struct.pack("<32I", *record(job, SAMPLES, native_bank(),
        iq_values=[(job[0]+n, i, q) for n, (i, q) in enumerate(iq)]))
    return payload, b"".join(struct.pack("<hh", *value) for value in iq)


def test_rounding_matches_exact_rational_for_positive_and_negative_half_ties():
    for divisor in (16, 2048):
        for n in range(-1000, 1001):
            for offset in (-1, 0, 1):
                numerator = n*divisor+divisor//2+offset
                assert round_even(numerator, divisor) == round(Fraction(numerator, divisor))


def test_full_signed_iq_and_negative_phase_step_match_independent_oracle(evidence):
    payload, iq = evidence
    result = verify(NativeResult.decode(payload), iq, (BANK_ROOT/"native_cubic_60000000_upper.mem").read_bytes())
    assert result["exact_integer_match"] is True and result["precision_qualified"] is False


@pytest.mark.parametrize("fault", ["iq", "phase", "moment", "prefix", "energy", "length", "bank", "partial"])
def test_replay_rejects_arithmetic_and_provenance_corruption(evidence, fault):
    payload, iq = evidence
    result = NativeResult.decode(payload)
    bank = (BANK_ROOT/"native_cubic_60000000_upper.mem").read_bytes()
    if fault == "iq":
        iq = bytes([iq[0] ^ 1])+iq[1:]
    elif fault == "phase":
        result = replace(result, phase_step=result.phase_step+8192)
    elif fault == "moment":
        result = replace(result, delay_sum=(result.delay_sum[0]+1, result.delay_sum[1]))
    elif fault == "prefix":
        result = replace(result, reference_prefix_integral=(result.reference_prefix_integral[0]+1, result.reference_prefix_integral[1]))
    elif fault == "energy":
        result = replace(result, observed_energy=result.observed_energy+1)
    elif fault == "length":
        iq = iq[:-4]
    elif fault == "bank":
        bank += b"\n"
    else:
        result = replace(result, fault=1, count=SAMPLES-1)
    with pytest.raises(ValueError):
        verify(result, iq, bank)


def write_capture(tmp_path, evidence, *, exact=False):
    payload, iq = evidence
    result = NativeResult.decode(payload)
    protocol = {"schema": "starlink-gln1-native-bringup/v1", "jobs": 1, "tag": result.tag,
                "phase_seed": result.phase_seed, "phase_step": result.phase_step}
    if exact:
        protocol.update(schema="starlink-gln1-native-exact-start/v1",
            start_sample=str(result.start), sample_rate_hz=RATE, samples_per_job=SAMPLES,
            acquisition_verified=False, prediction_source_verified=False)
    summary = {"status": "transport_pass", "failures": [], "jobs": [{"tag": result.tag,
        "start": result.start, "samples": result.count, "iq_sha256": hashlib.sha256(iq).hexdigest(),
        "result_sha256": hashlib.sha256(payload).hexdigest()}]}
    (tmp_path/"protocol.json").write_text(json.dumps(protocol))
    (tmp_path/"summary.json").write_text(json.dumps(summary))
    root = tmp_path/"job-0"
    root.mkdir()
    (root/"result.raw").write_bytes(payload)
    (root/"iq.ci16").write_bytes(iq)
    return protocol


def test_capture_verifies_original_request_and_transport_hashes(tmp_path, evidence):
    protocol = write_capture(tmp_path, evidence)
    _, iq = evidence
    root = tmp_path/"job-0"
    bank = BANK_ROOT/"native_cubic_60000000_upper.mem"
    assert verify_capture(tmp_path, bank)["status"] == "arithmetic_pass"
    protocol["tag"] += 1
    (tmp_path/"protocol.json").write_text(json.dumps(protocol))
    with pytest.raises(ValueError, match="requested job"):
        verify_capture(tmp_path, bank)
    (root/"iq.ci16").write_bytes(iq[:-1])
    with pytest.raises(ValueError, match="transport hashes"):
        verify_capture(tmp_path, bank)


def test_exact_capture_replays_all_original_iq_and_preserves_diagnostic_scope(tmp_path, evidence):
    protocol = write_capture(tmp_path, evidence, exact=True)
    result = verify_capture(tmp_path, BANK_ROOT/"native_cubic_60000000_upper.mem")
    assert result["schema"] == "starlink-gln1-native-exact-start-replay/v1"
    assert result["status"] == "arithmetic_pass"
    assert result["start_sample"] == protocol["start_sample"]
    assert int(result["start_sample"]) > 2**53
    assert result["exact_start_verified"] is True
    assert result["jobs"][0]["exact_integer_match"] is True
    assert result["precision_qualified"] is False
    assert result["acquisition_verified"] is False
    assert result["prediction_source_verified"] is False


@pytest.mark.parametrize("key,value", [
    ("start_sample", None), ("start_sample", 2**55+177),
    ("start_sample", "0"), ("start_sample", "01"), ("start_sample", "-1"),
    ("start_sample", str((1 << 64)-SAMPLES+1)), ("start_sample", "9"*100),
    ("jobs", 2), ("jobs", True), ("sample_rate_hz", 2500000),
    ("samples_per_job", SAMPLES-1), ("acquisition_verified", True),
    ("prediction_source_verified", None),
])
def test_exact_capture_rejects_invalid_request_before_replay(tmp_path, evidence, key, value):
    protocol = write_capture(tmp_path, evidence, exact=True)
    protocol[key] = value
    (tmp_path/"protocol.json").write_text(json.dumps(protocol))
    with pytest.raises(ValueError, match="exact-start diagnostic request"):
        verify_capture(tmp_path, BANK_ROOT/"native_cubic_60000000_upper.mem")


def test_exact_capture_rejects_wrong_start_even_with_self_consistent_transport(tmp_path, evidence):
    protocol = write_capture(tmp_path, evidence, exact=True)
    protocol["start_sample"] = str(int(protocol["start_sample"])+1)
    (tmp_path/"protocol.json").write_text(json.dumps(protocol))
    with pytest.raises(ValueError, match="requested exact start"):
        verify_capture(tmp_path, BANK_ROOT/"native_cubic_60000000_upper.mem")
