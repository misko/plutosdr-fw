import numpy as np
import pytest

from tools import starlink_pss_rate_diagnostic as rate


def test_five_fir_is_symmetric_and_unity_dc():
    h = rate.fir5()
    np.testing.assert_array_equal(h, h[::-1])
    assert h.sum() == 2**17


def test_five_impulse_source_center():
    x = np.zeros(1800, dtype=complex)
    x[600] = 1
    y, centers = rate.condition5(x, 0)
    assert np.all(np.diff(centers) == 3)
    assert abs(centers[np.argmax(abs(y))] - 600) <= 1


@pytest.mark.parametrize('sample_rate', [5, 15])
@pytest.mark.parametrize('cfo', [-500000, 0, 500000])
def test_known_frame_phase(sample_rate, cfo):
    x = np.zeros(240000, dtype=complex)
    pulse = rate.base.projected_pss(15000000, 'upper')
    for start in range(6012, len(x) - len(pulse), 20000):
        x[start:start + len(pulse)] = pulse
    x *= np.exp(2j * np.pi * cfo * np.arange(len(x)) / 15000000)
    y, centers = (rate.condition5(x, 0) if sample_rate == 5 else
                  (x, np.arange(len(x), dtype=np.int64)))
    result = rate.search(y, centers, sample_rate)
    assert rate.base.circular_distance(result['winner']['phase_us'], 6012 / 15,
                                       4000 / 3) <= 1 / sample_rate
