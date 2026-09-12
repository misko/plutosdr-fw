import numpy as np
import pytest

from tools import starlink_coarse25 as coarse


def test_fractional_frame_period_does_not_truncate():
    centers = np.arange(30_000) * 6
    phases = (centers % 20_000) // 2
    assert len(set(phases)) == 10_000
    assert np.all(np.bincount(phases) == 3)
    assert centers[10_000] == 3 * 20_000


@pytest.mark.parametrize('cfo', coarse.CFO_BANK)
def test_template_coordinates_and_energy(cfo):
    template, retained = coarse.template(cfo)
    assert len(template) == 16
    assert np.vdot(template, template).real == pytest.approx(1)
    assert 0 < retained <= 1


def test_gap_is_rejected_not_folded_into_wrong_epoch():
    centers = np.arange(10_100) * 6
    centers[5000:] += 6
    with pytest.raises(ValueError, match='contiguous'):
        coarse.search(np.zeros(len(centers), dtype=complex), centers, [])


def test_nonfinite_is_rejected():
    samples = np.zeros(10_100, dtype=complex)
    samples[100] = np.nan
    with pytest.raises(ValueError, match='finite'):
        coarse.search(samples, np.arange(len(samples)) * 6, [])


def test_saturation_is_rejected():
    with pytest.raises(ValueError, match='CI16'):
        coarse.iq(np.array([40000 + 0j]))


def test_circular_error_wraps_at_frame_boundary():
    assert coarse.circular_distance(0.1, 4000 / 3 - .1, 4000 / 3) == pytest.approx(.2)


def test_zero_input_has_no_detection():
    result = coarse.search(np.zeros(10_100, dtype=complex), np.arange(10_100) * 6,
                           [coarse.template(cfo)[0] for cfo in coarse.CFO_BANK])
    assert result['detected'] is False
    assert result['winner']['peak_z'] == 0
