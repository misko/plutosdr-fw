import numpy as np
import pytest

from tools.starlink_coarse25_normalized import normalized_scores


def test_matches_independent_window_dot_product():
    rng = np.random.default_rng(23)
    x = rng.normal(size=97) + 1j * rng.normal(size=97)
    h = rng.normal(size=16) + 1j * rng.normal(size=16)
    expected = []
    for k in range(len(x) - len(h) + 1):
        window = x[k:k + len(h)]
        expected.append(abs(np.vdot(h, window)) ** 2 /
                        (np.vdot(h, h).real * np.vdot(window, window).real))
    np.testing.assert_allclose(normalized_scores(x, h), expected, rtol=1e-13)


def test_gain_and_carrier_phase_invariance():
    rng = np.random.default_rng(24)
    x = rng.normal(size=100) + 1j * rng.normal(size=100)
    h = rng.normal(size=16) + 1j * rng.normal(size=16)
    np.testing.assert_allclose(normalized_scores(x * (43 - 19j), h * (-2 + 3j)),
                               normalized_scores(x, h), rtol=1e-13)


def test_exact_match_is_unity_and_zero_input_is_zero():
    h = np.arange(1, 17) + 1j * np.arange(16)
    assert normalized_scores(h * (3 + 4j), h)[0] == pytest.approx(1)
    assert np.all(normalized_scores(np.zeros(50, dtype=complex), h) == 0)


def test_zero_template_is_rejected():
    with pytest.raises(ValueError, match='positive energy'):
        normalized_scores(np.ones(100, dtype=complex), np.zeros(16))
