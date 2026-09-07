from __future__ import annotations

import numpy as np
import pytest

from tests.starlink_oracle import projected_pss, quantize_q15, x2_ddc_ci16
from tools.generate_starlink_pss30_cabled_waveform import (
    FRAME_SAMPLES,
    SAMPLE_RATE_HZ,
    TEMPLATE_PHASE,
    TEMPLATE_SAMPLES,
    WAVEFORM_NAME,
    generate,
)


def test_30m_cabled_waveform_is_exact_and_ddc_ready(tmp_path) -> None:
    evidence = generate(tmp_path)
    waveform = np.fromfile(tmp_path / WAVEFORM_NAME, dtype="<i2").reshape(-1, 2)
    template = quantize_q15(projected_pss(SAMPLE_RATE_HZ, "upper"))
    assert waveform.shape == (FRAME_SAMPLES, 2)
    assert template.shape == (TEMPLATE_SAMPLES, 2)
    np.testing.assert_array_equal(
        waveform[TEMPLATE_PHASE : TEMPLATE_PHASE + TEMPLATE_SAMPLES], template
    )
    assert not np.any(waveform[:TEMPLATE_PHASE])
    assert not np.any(waveform[TEMPLATE_PHASE + TEMPLATE_SAMPLES :])
    ddc = x2_ddc_ci16(waveform, first_input_index=0, edge="upper")
    assert ddc.discontinuities == 0
    assert ddc.saturation_events == 0
    assert evidence["nominal_detector_peak_phase_bin_canonical"] == 4096
    assert evidence["waveform"]["bytes"] == FRAME_SAMPLES * 4


def test_30m_cabled_waveform_generation_is_absent_only(tmp_path) -> None:
    generate(tmp_path)
    with pytest.raises(FileExistsError, match="refusing to replace"):
        generate(tmp_path)
