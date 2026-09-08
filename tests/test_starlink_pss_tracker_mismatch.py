from __future__ import annotations

from pathlib import Path

import pytest

from tools.generate_starlink_pss_tracker_coefficients import (
    generate as generate_matched,
)
from tools.generate_starlink_pss_tracker_mismatch import (
    MASK_DOMAIN,
    _mask_bytes,
    _read_matched,
    _rotate,
    generate,
)


def test_mismatched_control_is_an_exact_energy_preserving_qpsk_mask(
    tmp_path: Path,
) -> None:
    matched_directory = tmp_path / "matched"
    matched_evidence = generate_matched(matched_directory, rate_msps=30)
    matched_path = matched_directory / matched_evidence["memory_file"]["name"]
    output = tmp_path / "control"

    evidence = generate(output, matched_path=matched_path, rate_msps=30)
    control_path = output / evidence["memory_file"]["name"]
    matched = _read_matched(matched_path, rate_msps=30)
    control = _read_matched(control_path, rate_msps=30)
    phases = [value & 3 for value in _mask_bytes(len(matched))]

    assert control == [
        _rotate(value, phase) for value, phase in zip(matched, phases, strict=True)
    ]
    assert evidence["energy_exact"] is True
    assert (
        evidence["matched_coefficient_energy"] == evidence["control_coefficient_energy"]
    )
    assert evidence["mask"]["domain_utf8"] == MASK_DOMAIN.decode("ascii")
    assert evidence["correlation_diagnostic"]["aperture_samples"] == 60
    assert evidence["correlation_diagnostic"]["maximum_overlap_normalized_score"] < 0.08
    assert evidence["radio_access"] is False


@pytest.mark.parametrize("rate_msps", [15, 30, 60])
def test_control_geometry_tracks_the_full_rate_bank(
    tmp_path: Path, rate_msps: int
) -> None:
    matched_directory = tmp_path / f"matched-{rate_msps}"
    matched_evidence = generate_matched(matched_directory, rate_msps=rate_msps)
    matched_path = matched_directory / matched_evidence["memory_file"]["name"]
    evidence = generate(
        tmp_path / f"control-{rate_msps}",
        matched_path=matched_path,
        rate_msps=rate_msps,
    )

    assert evidence["tap_count"] == 66 * (rate_msps // 15)
    assert evidence["correlation_diagnostic"]["aperture_samples"] == 2 * rate_msps
    assert (
        evidence["matched_coefficient_energy"] == evidence["control_coefficient_energy"]
    )


def test_mismatched_control_generation_is_absent_only(tmp_path: Path) -> None:
    matched_directory = tmp_path / "matched"
    matched_evidence = generate_matched(matched_directory, rate_msps=30)
    matched_path = matched_directory / matched_evidence["memory_file"]["name"]
    output = tmp_path / "control"
    generate(output, matched_path=matched_path, rate_msps=30)

    with pytest.raises(FileExistsError, match="refusing to replace"):
        generate(output, matched_path=matched_path, rate_msps=30)
