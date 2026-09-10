"""60 MS/s support checked against two existing independent streaming paths."""

import numpy as np
import pytest

from tests.starlink_oracle.ddc import FIR_Q15, x4_ddc_ci16
from tests.starlink_oracle.high_rate60_support import (
    CANONICAL_COUNT,
    CANONICAL_FIRST,
    COARSE_FIRST,
    LIMIT,
    NATIVE_CENTER,
    native_lead,
    native_support,
    pilot_support,
    raw_support,
    recipe,
)
from tests.starlink_oracle.pilot_ddc import PilotDdcOracle


@pytest.mark.parametrize("first,count", [(6, 1), (7, 2), (2**30 - 1, 19),
                                         (CANONICAL_FIRST, CANONICAL_COUNT)])
@pytest.mark.parametrize("edge", ["upper", "lower"])
def test_full_support_has_exact_streaming_indexes_and_stage_counts(first, count, edge):
    start, stop = raw_support(first, count)
    rng = np.random.default_rng(600021)
    source = rng.integers(-400, 401, (stop - start, 2), dtype=np.int16)
    result = x4_ddc_ci16(source, first_input_index=start, edge=edge)
    assert result.accepted_samples == stop - start == 4 * count + 39
    assert result.stage_60_to_30.samples_iq.shape == (2 * count + 13, 2)
    assert result.samples_iq.shape == (count, 2)
    np.testing.assert_array_equal(result.output_indexes, np.arange(first, first + count))
    assert result.discontinuities == result.saturation_events == 0
    assert not np.any(result.output_gaps)

    # Independent vectorized convolution/absolute rotation, not x2 oracle calls.
    # Rounding is repeated at both stages: a flattened 43-tap FIR is not equivalent.
    values = source.astype(np.int64)
    index = start
    for _ in range(2):
        phases = (np.arange(len(values)) + index) % 4
        rotation = np.array([[1, 0], [0, -1 if edge == "upper" else 1],
                             [-1, 0], [0, 1 if edge == "upper" else -1]])[phases]
        mixed = np.column_stack((values[:, 0] * rotation[:, 0] - values[:, 1] * rotation[:, 1],
                                 values[:, 0] * rotation[:, 1] + values[:, 1] * rotation[:, 0]))
        sums = np.column_stack([np.convolve(mixed[:, lane], FIR_Q15, "valid")[::2]
                                for lane in range(2)])
        # These bounded integer sums fit exactly in binary64; power-of-two
        # division is exact, and np.rint is ties-to-even for this independent path.
        assert np.max(np.abs(sums)) < 2**53
        values = np.clip(np.rint(sums / 32768), -32768, 32767).astype(np.int64)
        index = (index + 7) // 2
    np.testing.assert_array_equal(values, result.samples_iq)


@pytest.mark.parametrize("side", ["first", "last"])
def test_missing_one_boundary_sample_loses_exactly_one_canonical_output(side):
    start, stop = raw_support(CANONICAL_FIRST, 20)
    source = np.ones((stop - start - 1, 2), dtype=np.int16)
    result = x4_ddc_ci16(source, first_input_index=start + (side == "first"))
    expected = CANONICAL_FIRST + (side == "first")
    np.testing.assert_array_equal(result.output_indexes, np.arange(expected, expected + 19))


def test_recipe_pilot_support_and_native_support_share_one_raw_timeline():
    r = recipe()
    assert r["raw_count"] == 16423
    assert r["raw_half_open"] == [34359735211, 34359751634]
    assert r["native_capture_half_open"] == [34359740256, 34359740776]
    assert r["raw_after_capture"] == 10858
    assert r["native_tap_lag_products"] == 67848  # operation count, not cycle bound
    canonical = np.zeros((CANONICAL_COUNT, 2), dtype=np.int16)
    result = PilotDdcOracle("upper").process(canonical, first_index=CANONICAL_FIRST)
    selected = result.accepted_input_indexes[result.support_valid][:512]
    assert len(selected) == 512
    assert [int(selected[0]), int(selected[-1])] == r["pilot_newest_canonical"]
    assert np.all(np.diff(selected) * 4 == 24)
    assert r["raw_half_open"][0] <= r["pilot_raw_support_half_open"][0]
    assert r["pilot_raw_support_half_open"][1] <= r["raw_half_open"][1]
    for newest in selected:
        start, stop = pilot_support(int(newest))
        assert (start + stop - 1) // 2 == 4 * (int(newest) - 269)
        assert stop - start == 2195
    assert NATIVE_CENTER == 4 * (COARSE_FIRST + 520)
    begin, end = native_support(NATIVE_CENTER)
    assert end - begin == 520
    assert [center - begin for center in (NATIVE_CENTER - 128, NATIVE_CENTER + 128)] == [0, 256]
    assert NATIVE_CENTER + 128 + 264 == end
    assert native_lead(NATIVE_CENTER, begin - 257) == r["native_default_minimum_lead"] == 256
    assert native_lead(NATIVE_CENTER, begin - 256) == 255  # insufficient default lead
    assert native_lead(NATIVE_CENTER, begin - 1) == 0
    assert native_lead(NATIVE_CENTER, begin) == -1


@pytest.mark.parametrize("first,count", [(True, 1), (6, False), (6.0, 1), (6, 1.0),
                                         (-1, 1), (5, 1), (6, 0), (6, -1), (LIMIT // 4, 1), (6, LIMIT)])
def test_invalid_canonical_support_rejected(first, count):
    with pytest.raises(ValueError):
        raw_support(first, count)


@pytest.mark.parametrize("center", [True, 128.0, 127, LIMIT - 391, -1])
def test_invalid_native_support_rejected(center):
    with pytest.raises(ValueError):
        native_support(center)


@pytest.mark.parametrize("accepted", [True, 2.0, -1, LIMIT - 1, 1 << 63])
def test_invalid_native_lead_rejected(accepted):
    with pytest.raises(ValueError):
        native_lead(128, accepted)


@pytest.mark.parametrize("newest", [True, 600.0, 601, 0, -6, LIMIT])
def test_invalid_pilot_support_rejected(newest):
    with pytest.raises(ValueError):
        pilot_support(newest)


def test_recipe_is_not_mutable_global_state():
    first = recipe()
    first["raw_half_open"][0] = 0
    assert recipe()["raw_half_open"][0] != 0


def test_largest_legal_coordinates_preserve_half_open_end():
    assert native_support(128) == (0, 520)
    assert native_support(LIMIT - 392) == (LIMIT - 520, LIMIT)
    last_canonical = (LIMIT - 22) // 4
    first, stop = raw_support(last_canonical, 1)
    assert stop <= LIMIT and stop - first == 43
    with pytest.raises(ValueError):
        raw_support(last_canonical + 1, 1)
