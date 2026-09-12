import numpy as np
import pytest

from tools import starlink_coarse25_fixed as fixed


def test_coefficient_energy_contract():
    h = fixed.coefficients()
    assert int(np.sum(h * h)) == 1073660387


def test_ties_even_and_special_cases():
    assert fixed.round_score(1, 0, 1, 2) == 128
    assert fixed.round_score(1, 0, 3, 2) == 42
    assert fixed.round_score(0, 0, 0, 2) == 0
    assert fixed.round_score(3, 4, 1, 2) == 255


@pytest.mark.parametrize('extreme', [False, True])
def test_vectorized_against_independent_dot_products(extreme):
    rng = np.random.default_rng(3917)
    x = rng.integers(-32768 if extreme else -200, 32768 if extreme else 201, size=(200, 2))
    if extreme:
        x[:32] = -32768
    h = fixed.coefficients()
    eh = int(np.sum(h * h))
    expected = []
    for k in range(len(x) - 15):
        window = x[k:k + 16]
        re = sum(int(a)*int(c) + int(b)*int(d) for (a,b),(c,d) in zip(window,h))
        im = sum(int(b)*int(c) - int(a)*int(d) for (a,b),(c,d) in zip(window,h))
        energy = sum(int(a)**2 + int(b)**2 for a,b in window)
        expected.append(fixed.round_score(re, im, energy, eh))
    np.testing.assert_array_equal(fixed.scores(x), expected)


def test_zero_input():
    assert not np.any(fixed.scores(np.zeros((32, 2), dtype=np.int16)))
