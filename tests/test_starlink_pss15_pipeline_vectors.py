from __future__ import annotations

from pathlib import Path

from tools.generate_starlink_pss15_pipeline_vectors import generate

EXPECTED_FILES = {
    "samples_ci16.mem": {
        "lines": 1406,
        "sha256": "4abe27ba953cf49f84d9979966625a2436ad59359b616321e881b42dd4c84723",
    },
    "forward_q17.mem": {
        "lines": 1536,
        "sha256": "d934a8ecd0888c294fc0abfbdbe7c439bff7097ea169b937638c4b7000479bfd",
    },
    "product_q17.mem": {
        "lines": 1536,
        "sha256": "b316522a68529a73d3d8e4121badea61e24621c93a97365e894f5bd416bcecb7",
    },
    "inverse_q17.mem": {
        "lines": 1536,
        "sha256": "c8c5b4e28ab621d0b1d5c1dc288f6e66495b3319d348442ce5d7b8f6ea8025a1",
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
        "sha256": "c22f751a2a82244268dd9ea4989c4ff3b5364c172526e80886c5da3d1959e45d",
    },
}


def test_generated_xfft_pipeline_vectors_are_exact_and_self_cleaning(
    tmp_path: Path,
) -> None:
    evidence = generate(tmp_path)

    assert evidence["schema"] == "starlink-pss15-generated-xfft-pipeline-vectors-v2"
    assert evidence["sample_rate_hz"] == 15_000_000
    assert evidence["acquisition_clock_hz"] == 100_000_000
    assert evidence["sample_count"] == 1406
    assert evidence["block_count"] == 3
    assert evidence["fft_samples"] == 512
    assert evidence["data_bits"] == 18
    assert evidence["valid_scores_per_block"] == 447
    assert evidence["score_count"] == 1341
    assert evidence["first_sample_index"] == 1_000_000
    assert evidence["pss_starts_relative"] == [100, 447, 1000]
    assert evidence["pss_scores"] == [255, 255, 255]
    assert evidence["forward_block_exponents"] == [5, 4, 4]
    assert evidence["inverse_block_exponents"] == [3, 4, 4]
    assert evidence["score_minimum"] == 0
    assert evidence["score_maximum"] == 255
    assert evidence["nonzero_score_count"] == 1072
    assert evidence["random_seed"] == 0x15F17E
    assert evidence["files"] == EXPECTED_FILES
    assert {path.name for path in tmp_path.iterdir()} == {
        *EXPECTED_FILES,
        "pipeline_vectors.json",
    }
