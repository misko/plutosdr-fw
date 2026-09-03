from __future__ import annotations

import math
import subprocess
from pathlib import Path

import numpy as np
import pytest

from .starlink_oracle.acquisition import PhaseMapTiles, search_phase_map_drift

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/starlink_pssctl"
BINARY = SOURCE / "build/test_starlink_pss_acquisition"


@pytest.fixture(scope="module", autouse=True)
def _build_c_oracle() -> None:
    subprocess.run(
        ["make", "-C", str(SOURCE), "build/test_starlink_pss_acquisition"],
        check=True,
    )


def _python_candidate(maps: np.ndarray, tile_frames: int, drifts: list[int]):
    phase_bins = maps.shape[1]
    tile_samples = phase_bins * tile_frames
    tiles = PhaseMapTiles(
        maps=np.asarray(maps, dtype=np.uint16),
        tile_start_sample_indexes=np.arange(3, dtype=np.int64) * tile_samples,
        phase_bin_samples=1,
        tile_frames=tile_frames,
        frame_samples=phase_bins,
        score_bits=8,
        phase_map_word_bits=16,
        discarded_leading_scores=0,
        discarded_trailing_scores=0,
    )
    return search_phase_map_drift(tiles, drift_bins_per_tile=drifts)


def _c_candidate(maps: np.ndarray, tile_frames: int, drifts: list[int]):
    phase_bins = maps.shape[1]
    fields = [str(phase_bins), str(tile_frames), str(len(drifts))]
    fields.extend(str(value) for value in drifts)
    fields.extend(str(int(value)) for value in maps.reshape(-1))
    completed = subprocess.run(
        [str(BINARY), "--extract-stdin"],
        input=" ".join(fields) + "\n",
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    phase, drift, score, median, ratio, robust_z, period = completed.stdout.split()
    return {
        "phase": int(phase),
        "drift": int(drift),
        "score": int(score),
        "median": float(median),
        "ratio": float(ratio),
        "robust_z": float(robust_z),
        "period": float(period),
    }


@pytest.mark.parametrize("phase_bins", [31, 32, 127, 128])
@pytest.mark.parametrize("seed", [0x15AC001, 0x15AC002, 0x15AC003])
def test_c_extractor_matches_python_shift_sum_median_and_mad(
    phase_bins: int, seed: int
) -> None:
    rng = np.random.default_rng(seed + phase_bins)
    maps = rng.integers(0, 16_321, size=(3, phase_bins), dtype=np.uint16)
    drifts = [-3, -2, -1, 0, 1, 2, 3]

    expected = _python_candidate(maps, 64, drifts)
    actual = _c_candidate(maps, 64, drifts)

    assert actual["phase"] == expected.phase_bin
    assert actual["drift"] == expected.drift_bins_per_tile
    assert actual["score"] == expected.combined_score
    assert actual["median"] == expected.combined_median
    assert actual["ratio"] == pytest.approx(expected.peak_to_median, rel=1e-14)
    assert actual["robust_z"] == pytest.approx(expected.robust_z, rel=1e-14)
    assert actual["period"] == expected.estimated_frame_period_samples


def test_c_extractor_matches_python_zero_mad_tie_rules() -> None:
    maps = np.full((3, 32), 100, dtype=np.uint16)
    drifts = [-3, 0, 3]

    expected = _python_candidate(maps, 64, drifts)
    actual = _c_candidate(maps, 64, drifts)

    assert actual["phase"] == expected.phase_bin == 0
    assert actual["drift"] == expected.drift_bins_per_tile == -3
    assert actual["score"] == expected.combined_score == 300
    assert actual["ratio"] == expected.peak_to_median == 1.0
    assert actual["robust_z"] == expected.robust_z == 0.0
    assert math.isfinite(actual["period"])
