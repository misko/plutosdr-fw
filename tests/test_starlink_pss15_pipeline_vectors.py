from __future__ import annotations

from pathlib import Path

from tools.generate_starlink_pss15_pipeline_vectors import generate

EXPECTED_FILES = {
    "samples_ci16.mem": {
        "lines": 1406,
        "sha256": "4abe27ba953cf49f84d9979966625a2436ad59359b616321e881b42dd4c84723",
    },
    "forward_q23.mem": {
        "lines": 1536,
        "sha256": "92240f871d3d59e66923e412d7d933fe9938438c6eabdd005182d2e8daf109cc",
    },
    "product_q23.mem": {
        "lines": 1536,
        "sha256": "63f6c4ba900b25d5cfc9ec8161765b8e9776e6711eedc94edef2d43d46a92615",
    },
    "inverse_q23.mem": {
        "lines": 1536,
        "sha256": "3fdebbc406d6cc3e9bfdc199820416c56fcde640777ee7cd7da0bc75078f8884",
    },
    "forward_exponents.mem": {
        "lines": 3,
        "sha256": "18ac6df6a1ae3f19e5153524b33f336a60eabdd6dbd182d46c43450302e4b52f",
    },
    "inverse_exponents.mem": {
        "lines": 3,
        "sha256": "899b7a2486fd3759c6e4905110fc4d86ffdb6ec884da2a7f2aca4acdfd363dff",
    },
    "scores_u8.mem": {
        "lines": 1341,
        "sha256": "a8c5596bdea4f7a618082467e222c6088d589174bb69f96238df83def2ce02a0",
    },
}


def test_generated_xfft_pipeline_vectors_are_exact_and_self_cleaning(
    tmp_path: Path,
) -> None:
    evidence = generate(tmp_path)

    assert evidence["schema"] == "starlink-pss15-generated-xfft-pipeline-vectors-v1"
    assert evidence["sample_rate_hz"] == 15_000_000
    assert evidence["acquisition_clock_hz"] == 100_000_000
    assert evidence["sample_count"] == 1406
    assert evidence["block_count"] == 3
    assert evidence["fft_samples"] == 512
    assert evidence["valid_scores_per_block"] == 447
    assert evidence["score_count"] == 1341
    assert evidence["first_sample_index"] == 1_000_000
    assert evidence["pss_starts_relative"] == [100, 447, 1000]
    assert evidence["pss_scores"] == [255, 255, 255]
    assert evidence["forward_block_exponents"] == [5, 4, 4]
    assert evidence["inverse_block_exponents"] == [3, 4, 4]
    assert evidence["score_minimum"] == 0
    assert evidence["score_maximum"] == 255
    assert evidence["nonzero_score_count"] == 1071
    assert evidence["random_seed"] == 0x15F17E
    assert evidence["files"] == EXPECTED_FILES
    assert {path.name for path in tmp_path.iterdir()} == {
        *EXPECTED_FILES,
        "pipeline_vectors.json",
    }
