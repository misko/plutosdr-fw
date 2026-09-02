from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from tests.starlink_oracle import (
    INSTALLED_CMODEL_ARCHIVE,
    PSS_KERNEL_Q23_INT32LE_SHA256,
    XFFT_BITACC_SCHEMA,
    XFFT_DATA_BITS,
    XFFT_SAMPLES,
    XFFT_VALID_OUTPUTS,
    XfftBitAccModel,
    direct_fixed_match_scores,
    overlap_save_fixed_match_scores,
    prepare_installed_cmodel,
    projected_pss,
    quantize_q15,
    xfft_bitacc_match_scores,
)
from tests.starlink_oracle.xfft_bitacc import _round_shift_ties_even


def test_convergent_signed_power_of_two_rounding() -> None:
    values = np.asarray(
        (-10, -8, -6, -2, -1, 0, 1, 2, 6, 8, 10), dtype=np.int64
    )

    rounded = _round_shift_ties_even(values, 2)

    assert rounded.tolist() == [-2, -2, -2, 0, 0, 0, 0, 0, 2, 2, 2]


@pytest.fixture(scope="module")
def xfft_model(tmp_path_factory: pytest.TempPathFactory):
    if not INSTALLED_CMODEL_ARCHIVE.is_file():
        pytest.skip("canonical Vivado 2022.2 XFFT C model is not installed")
    directory = prepare_installed_cmodel(
        tmp_path_factory.mktemp("starlink-xfft-cmodel")
    )
    with XfftBitAccModel(directory) as model:
        yield model


def test_xfft_candidate_matches_direct_scores_on_random_ci16(
    xfft_model: XfftBitAccModel,
) -> None:
    assert XFFT_DATA_BITS == 24
    assert XFFT_VALID_OUTPUTS == 447
    rng = np.random.default_rng(0xA15C)
    samples = rng.integers(-20_000, 20_001, size=(1_237, 2), dtype=np.int16)
    coefficients = quantize_q15(projected_pss(15_000_000, "upper"))

    result = xfft_bitacc_match_scores(samples, coefficients, xfft_model)
    direct = direct_fixed_match_scores(samples, coefficients)
    accelerated = overlap_save_fixed_match_scores(samples, coefficients)

    np.testing.assert_array_equal(result.stream.scores, direct.scores)
    np.testing.assert_array_equal(result.stream.scores, accelerated.scores)
    assert result.schema == XFFT_BITACC_SCHEMA
    assert result.stream.fft_samples == XFFT_SAMPLES
    assert result.stream.scores.size == samples.shape[0] - 65
    assert math.isnan(result.stream.maximum_fft_rounding_residual)
    assert result.block_count == 3
    assert not result.stream.scores.flags.writeable
    assert result.forward_overflow_blocks == 0
    assert result.inverse_overflow_blocks == 0
    assert result.product_overflow_blocks == 0


@pytest.mark.parametrize("edge", ("lower", "upper"))
def test_template_kernel_is_stable_and_does_not_overflow(
    xfft_model: XfftBitAccModel,
    edge: str,
) -> None:
    coefficients = quantize_q15(projected_pss(15_000_000, edge))
    samples = np.zeros((66, 2), dtype=np.int16)

    result = xfft_bitacc_match_scores(samples, coefficients, xfft_model)

    assert result.kernel_iq.shape == (512, 2)
    assert result.kernel_iq.dtype == np.int32
    assert result.kernel_sha256 == PSS_KERNEL_Q23_INT32LE_SHA256[edge]
    assert result.stream.scores.tolist() == [0]
    assert result.forward_overflow_blocks == 0
    assert result.inverse_overflow_blocks == 0
    assert result.product_overflow_blocks == 0


@pytest.mark.parametrize("start", (0, 446, 447, 448, 893))
def test_xfft_overlap_save_keeps_full_scale_peak_at_every_boundary(
    xfft_model: XfftBitAccModel,
    start: int,
) -> None:
    coefficients = quantize_q15(projected_pss(15_000_000, "upper"))
    samples = np.zeros((start + coefficients.shape[0] + 100, 2), dtype=np.int16)
    samples[start : start + coefficients.shape[0]] = coefficients

    result = xfft_bitacc_match_scores(samples, coefficients, xfft_model)

    assert int(np.argmax(result.stream.scores)) == start
    assert int(result.stream.scores[start]) == 255
    assert result.forward_overflow_blocks == 0
    assert result.inverse_overflow_blocks == 0
    assert result.product_overflow_blocks == 0


def test_xfft_block_floating_path_accepts_full_range_constant_input(
    xfft_model: XfftBitAccModel,
) -> None:
    coefficients = quantize_q15(projected_pss(15_000_000, "lower"))
    samples = np.empty((1_024, 2), dtype=np.int16)
    samples[:, 0] = np.int16(32_767)
    samples[:, 1] = np.int16(-32_768)

    result = xfft_bitacc_match_scores(samples, coefficients, xfft_model)

    assert result.stream.scores.size == 959
    assert result.block_count == 3
    assert min(result.forward_block_exponents) > 0
    assert result.forward_overflow_blocks == 0
    assert result.inverse_overflow_blocks == 0
    assert result.product_overflow_blocks == 0


def test_prepare_cmodel_rejects_noncanonical_archive(tmp_path: Path) -> None:
    archive = tmp_path / "not-xfft.zip"
    archive.write_bytes(b"not the canonical model")

    with pytest.raises(ValueError, match="digest"):
        prepare_installed_cmodel(tmp_path / "output", archive=archive)
