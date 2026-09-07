from __future__ import annotations

import hashlib

import numpy as np
import pytest

from tests.starlink_oracle import projected_pss, quantize_q15
from tools.generate_starlink_pss_tracker_coefficients import generate


@pytest.mark.parametrize("rate_msps,taps", [(15, 66), (30, 132), (60, 264)])
def test_tracker_coefficients_are_the_exact_full_rate_pss(
    tmp_path, rate_msps: int, taps: int
) -> None:
    evidence = generate(tmp_path, rate_msps=rate_msps)
    path = tmp_path / evidence["memory_file"]["name"]
    words = [int(line, 16) for line in path.read_text(encoding="ascii").splitlines()]
    observed = np.empty((len(words), 2), dtype=np.int16)
    for index, word in enumerate(words):
        observed[index, 0] = np.uint16(word >> 16).view(np.int16)
        observed[index, 1] = np.uint16(word & 0xFFFF).view(np.int16)
    expected = quantize_q15(projected_pss(rate_msps * 1_000_000, "upper"))
    np.testing.assert_array_equal(observed, expected)
    assert observed.shape == (taps, 2)
    assert evidence["coefficient_energy"] == int(
        np.sum(expected.astype(np.int64) ** 2, dtype=np.int64)
    )
    assert evidence["coefficient_ci16le_sha256"] == hashlib.sha256(
        np.asarray(expected, dtype="<i2").tobytes(order="C")
    ).hexdigest()


def test_tracker_coefficients_support_deterministic_cfo_conditioning(tmp_path) -> None:
    evidence = generate(tmp_path, rate_msps=60, cfo_hz=-100_000.0)
    sample_indices = np.arange(264, dtype=np.float64)
    conditioned = np.asarray(projected_pss(60_000_000, "upper"), dtype=np.complex128)
    conditioned *= np.exp(2j * np.pi * -100_000.0 * sample_indices / 60_000_000)
    expected = quantize_q15(conditioned)
    assert evidence["tap_count"] == 264
    assert evidence["cfo_hz"] == -100_000.0
    assert evidence["coefficient_ci16le_sha256"] == hashlib.sha256(
        np.asarray(expected, dtype="<i2").tobytes(order="C")
    ).hexdigest()


def test_tracker_coefficient_generation_is_absent_only(tmp_path) -> None:
    generate(tmp_path, rate_msps=60)
    with pytest.raises(FileExistsError, match="refusing to replace"):
        generate(tmp_path, rate_msps=60)
