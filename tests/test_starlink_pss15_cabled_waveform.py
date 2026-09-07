from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tests.starlink_oracle import complex64_sha256, projected_pss, quantize_q15
from tools.generate_starlink_pss15_cabled_waveform import (
    EDGE,
    EVIDENCE_NAME,
    FRAME_SAMPLES,
    MINIMUM_EFFECTIVE_ATTENUATION_DB,
    SAMPLE_RATE_HZ,
    SCHEMA,
    TEMPLATE_PHASE,
    TEMPLATE_SAMPLES,
    WAVEFORM_NAME,
    generate,
)


def test_cabled_waveform_is_exact_bounded_and_self_describing(tmp_path: Path) -> None:
    evidence = generate(tmp_path)
    persisted = json.loads((tmp_path / EVIDENCE_NAME).read_text(encoding="utf-8"))
    waveform = np.fromfile(tmp_path / WAVEFORM_NAME, dtype="<i2").reshape(-1, 2)
    expected_template = quantize_q15(projected_pss(SAMPLE_RATE_HZ, EDGE))

    assert persisted == evidence
    assert evidence["schema"] == SCHEMA
    assert evidence["claim_scope"] == "deterministic_cabled_rf_stimulus_only"
    assert evidence["offline_generation_only"] is True
    assert evidence["cabled_only"] is True
    assert evidence["over_the_air_authorized"] is False
    assert evidence["transmitter_configuration_included"] is False
    assert evidence["minimum_effective_attenuation_db"] == (
        MINIMUM_EFFECTIVE_ATTENUATION_DB
    )
    assert evidence["sample_rate_hz"] == SAMPLE_RATE_HZ
    assert evidence["frame_samples"] == FRAME_SAMPLES
    assert evidence["template_samples"] == TEMPLATE_SAMPLES
    assert evidence["template_phase_bin"] == TEMPLATE_PHASE
    assert evidence["nominal_detector_peak_phase_bin"] == TEMPLATE_PHASE
    assert evidence["waveform"]["bytes"] == FRAME_SAMPLES * 4
    assert (tmp_path / WAVEFORM_NAME).stat().st_mode & 0o777 == 0o600
    assert (tmp_path / EVIDENCE_NAME).stat().st_mode & 0o777 == 0o600
    assert waveform.shape == (FRAME_SAMPLES, 2)
    assert np.array_equal(
        waveform[TEMPLATE_PHASE : TEMPLATE_PHASE + TEMPLATE_SAMPLES],
        expected_template,
    )
    assert not np.any(waveform[:TEMPLATE_PHASE])
    assert not np.any(waveform[TEMPLATE_PHASE + TEMPLATE_SAMPLES :])
    assert evidence["maximum_absolute_component"] == 6_904
    assert evidence["nonzero_complex_samples"] == TEMPLATE_SAMPLES
    assert evidence["projected_template_complex64_sha256"] == complex64_sha256(
        projected_pss(SAMPLE_RATE_HZ, EDGE)
    )


def test_cabled_waveform_generation_is_absent_only(tmp_path: Path) -> None:
    generate(tmp_path)
    with pytest.raises(FileExistsError, match="refusing to replace"):
        generate(tmp_path)
