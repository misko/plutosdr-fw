from __future__ import annotations

import hashlib

import numpy as np
import pytest

from tests.starlink_oracle import (
    FIR_Q15,
    GROUP_DELAY_INPUT_SAMPLES,
    conditioned_pss,
    conditioned_pss_x4,
    ddc_contract_sha256,
    ddc_x4_contract_sha256,
    quantize_q15,
    x2_ddc_ci16,
    x4_ddc_ci16,
)
from tests.starlink_oracle.waveforms import complex64_sha256


EXPECTED_TEMPLATE_HASHES = {
    "lower": "ade23098af611821e4a34a87240c24510f16381cc3ce52e599306c4b7117d7e4",
    "upper": "009d208bf6a5d3c295e3dc1c3888f4dcbbe32b47b888fb715940b0ab8c7d583e",
}
EXPECTED_Q15_HASHES = {
    "lower": "23c1d0fa463a0c611166fbf0f6d8876c0dd099119468aed9328e3022f44ece43",
    "upper": "de3b7a29618b1b0406d3b9bfbb94188ba5c65a114072b1a1337ef7d23fea19bf",
}
EXPECTED_CONTRACT_HASH = (
    "731426047077b036f9213db3574e4a556fd424b97a293843bd6ee085c2bf33af"
)
EXPECTED_X4_TEMPLATE_HASHES = {
    "lower": "ef6253b04d0358dd864357c01821e4eb27743cca6f3ffa0d8991d6c3b23ca38d",
    "upper": "90c5f32d93deecfaef4d6f289aed7bdc9931cbf6b68ca96961ae0255fb00dc87",
}
EXPECTED_X4_Q15_HASHES = {
    "lower": "51295d1b97b2c13911261e310f9b88937d12ced88a781d761f96044c010c543d",
    "upper": "39070e0f6100a0eac71e2dcfcda94941f7248f694179fc7fa404380a4123d7dc",
}
EXPECTED_X4_CONTRACT_HASH = (
    "8e807d15d5372b0a9669d1190d899697e7c2911a73ddfb23095806c2a31de5b2"
)


def test_frozen_halfband_response_and_delay() -> None:
    assert len(FIR_Q15) == 15
    assert FIR_Q15 == FIR_Q15[::-1]
    assert FIR_Q15[1:7:2] == (0, 0, 0)
    assert FIR_Q15[8::2] == (10235, -2923, 1260, -572)
    assert FIR_Q15[7] == 16384
    assert GROUP_DELAY_INPUT_SAMPLES == 7
    assert sum(FIR_Q15) == 32384

    response = np.fft.rfft(np.pad(np.asarray(FIR_Q15, dtype=float) / 32768, (0, 262129)))
    frequency_hz = np.linspace(0, 15_000_000, response.size)
    response_db = 20 * np.log10(np.maximum(np.abs(response), 1e-300))
    passband = response_db[frequency_hz <= 5_625_000]
    stopband = response_db[frequency_hz >= 9_375_000]
    nyquist_edge = response_db[np.argmin(np.abs(frequency_hz - 7_500_000))]
    assert float(passband.max() - passband.min()) < 0.205
    assert float(stopband.max()) < -38.53
    assert float(nyquist_edge) == pytest.approx(-6.0206, abs=0.001)


@pytest.mark.parametrize("edge", ("lower", "upper"))
def test_conditioned_template_identity(edge: str) -> None:
    template = conditioned_pss(edge)  # type: ignore[arg-type]
    coefficients = quantize_q15(template)
    assert template.shape == (66,)
    assert np.linalg.norm(template) == pytest.approx(1.0, abs=1e-7)
    assert complex64_sha256(template) == EXPECTED_TEMPLATE_HASHES[edge]
    assert (
        hashlib.sha256(np.asarray(coefficients, dtype="<i2").tobytes()).hexdigest()
        == EXPECTED_Q15_HASHES[edge]
    )


def test_fixed_stream_index_gap_and_rounding_contract() -> None:
    samples = np.asarray(
        [[offset - 40, 40 - offset] for offset in range(100)], dtype=np.int16
    )
    result = x2_ddc_ci16(
        samples, first_input_index=100, edge="upper"
    )
    assert result.accepted_samples == 100
    assert result.discontinuities == 1
    assert result.saturation_events == 0
    np.testing.assert_array_equal(result.output_indexes, np.arange(54, 97))
    np.testing.assert_array_equal(
        result.output_gaps, np.asarray([True] + [False] * 42)
    )
    assert hashlib.sha256(result.samples_iq.tobytes()).hexdigest() == (
        "2d3bd6aa911b2d8cc259143802e662ab7ef9238e26d213bffbac89aa56dcf9b2"
    )

    gaps = np.zeros(100, dtype=np.bool_)
    gaps[[0, 50]] = True
    restarted = x2_ddc_ci16(
        samples, first_input_index=100, edge="upper", gap_before=gaps
    )
    assert restarted.discontinuities == 2
    assert np.count_nonzero(restarted.output_gaps) == 2
    assert np.all(np.diff(restarted.output_indexes[restarted.output_gaps]) > 0)


def test_contract_digest_and_invalid_inputs() -> None:
    assert ddc_contract_sha256() == EXPECTED_CONTRACT_HASH
    with pytest.raises(ValueError, match="shape"):
        x2_ddc_ci16(np.zeros(4, dtype=np.int16))
    with pytest.raises(ValueError, match="edge"):
        x2_ddc_ci16(np.zeros((4, 2), dtype=np.int16), edge="center")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="one flag"):
        x2_ddc_ci16(
            np.zeros((4, 2), dtype=np.int16), gap_before=np.zeros(3, dtype=bool)
        )


@pytest.mark.parametrize("edge", ("lower", "upper"))
def test_x4_conditioned_template_identity(edge: str) -> None:
    template = conditioned_pss_x4(edge)  # type: ignore[arg-type]
    coefficients = quantize_q15(template)
    assert template.shape == (66,)
    assert np.linalg.norm(template) == pytest.approx(1.0, abs=1e-7)
    assert complex64_sha256(template) == EXPECTED_X4_TEMPLATE_HASHES[edge]
    assert (
        hashlib.sha256(np.asarray(coefficients, dtype="<i2").tobytes()).hexdigest()
        == EXPECTED_X4_Q15_HASHES[edge]
    )


def test_x4_fixed_stream_index_and_stage_evidence() -> None:
    samples = np.asarray(
        [[offset - 40, 40 - offset] for offset in range(200)], dtype=np.int16
    )
    result = x4_ddc_ci16(samples, first_input_index=100, edge="upper")
    assert result.accepted_samples == 200
    assert result.emitted_samples == 39
    assert result.discontinuities == 1
    assert result.saturation_events == 0
    np.testing.assert_array_equal(result.output_indexes, np.arange(31, 70))
    np.testing.assert_array_equal(
        result.output_gaps, np.asarray([True] + [False] * 38)
    )
    assert hashlib.sha256(result.samples_iq.tobytes()).hexdigest() == (
        "3aa72adb3a6f4bfe2bc2987f11240cb66de2afa7eb26873715254e3a7cd1e9d0"
    )
    assert result.stage_60_to_30.accepted_samples == 200
    assert result.stage_30_to_15.accepted_samples == 93
    assert ddc_x4_contract_sha256() == EXPECTED_X4_CONTRACT_HASH
