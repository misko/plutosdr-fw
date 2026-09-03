from __future__ import annotations

from pathlib import Path

from tools.generate_starlink_pss60_ddc_vectors import generate as generate_ddc
from tools.generate_starlink_pss60_ddc_xfft_vectors import generate as generate_xfft


EXPECTED_XFFT_FILES = {
    "source_ci16.mem": {
        "lines": 5666,
        "sha256": "03ef77e7e31b2f5a79dbc4a3e69bf80d11c69cc808cfcfd322f508e311ce4ed3",
    },
    "ddc_ci16.mem": {
        "lines": 1406,
        "sha256": "4b50998ee551bf3085055570312066b90294b18861834b126aa9dfd8290708dc",
    },
    "forward_q17.mem": {
        "lines": 1536,
        "sha256": "0daee251502c4de6615f037bc86b60b29791613412bfcf5ea58f5ff4d018e2d5",
    },
    "product_q17.mem": {
        "lines": 1536,
        "sha256": "9679854e28951d23424b9989e46e31d61e8e3df9bc7e1d53b50f9a88a1e823c5",
    },
    "inverse_q17.mem": {
        "lines": 1536,
        "sha256": "8214a4e636c7a91f73d7f94dc5ef4b1e64554b100ea0ca84af4a3e4fe6fd7310",
    },
    "forward_exponents.mem": {
        "lines": 3,
        "sha256": "86ee5df6b541f409eb28e2e3021c9eb40da54c17145c3e0de1fc9cd591d66baa",
    },
    "inverse_exponents.mem": {
        "lines": 3,
        "sha256": "899b7a2486fd3759c6e4905110fc4d86ffdb6ec884da2a7f2aca4acdfd363dff",
    },
    "scores_u8.mem": {
        "lines": 1341,
        "sha256": "bd03449267e648a460a3826cdb391ff2bbe3285f4eee799c7ebc3632fb45108c",
    },
}


def test_x4_ddc_vectors_are_exact(tmp_path: Path) -> None:
    evidence = generate_ddc(tmp_path)
    assert evidence["schema"] == "starlink-pss60-x4-ddc-vectors-v1"
    assert evidence["sample_count"] == 500
    assert evidence["ddc_x4_contract_sha256"] == (
        "8e807d15d5372b0a9669d1190d899697e7c2911a73ddfb23095806c2a31de5b2"
    )
    assert evidence["edges"] == {
        "lower": {
            "stage_60_to_30_outputs": 229,
            "outputs": 93,
            "discontinuities": 3,
            "saturation_events": 3,
            "expected_text_sha256": "0bbbd62c850abefa29688891ad2928b94433bbb8ae4e291cd4655dc4d846d0ce",
            "summary_text_sha256": "fb47ae4b68de830f6fb514bc15c4cde8d2ae2c21e239ce8598929145dd83a8e4",
        },
        "upper": {
            "stage_60_to_30_outputs": 229,
            "outputs": 93,
            "discontinuities": 3,
            "saturation_events": 2,
            "expected_text_sha256": "70e530bd7cdfb781dc1acc4a8ba03ee310e8f94ce930b432509dabfb45348ac2",
            "summary_text_sha256": "2ebedb0da9ed6b23ed459931269ebd23273fdbf943e6343ff49ab1a622564b49",
        },
    }


def test_x4_ddc_to_xfft_vectors_are_exact(tmp_path: Path) -> None:
    evidence = generate_xfft(tmp_path)
    assert evidence["schema"] == "starlink-pss60-ddc-to-xfft-v1"
    assert evidence["source_sample_rate_hz"] == 60_000_000
    assert evidence["source_sample_count"] == 5666
    assert evidence["stage_60_to_30_sample_count"] == 2826
    assert evidence["acquisition_sample_count"] == 1406
    assert evidence["first_source_index"] == 4_000_000
    assert evidence["first_acquisition_index"] == 1_000_006
    assert evidence["source_pss_starts_relative"] == [424, 1812, 4024]
    assert evidence["pss_score_offsets"] == [100, 447, 1000]
    assert evidence["pss_scores"] == [255, 255, 255]
    assert evidence["forward_block_exponents"] == [3, 2, 2]
    assert evidence["inverse_block_exponents"] == [3, 4, 4]
    assert evidence["coefficient_energy"] == 1_073_765_335
    assert evidence["kernel_canonical_sha256"] == (
        "497ab1527fefaf2e0c2ed0ad7260c1fc01bec6b9062a1857b66bd7ec45bedccb"
    )
    assert evidence["ddc_x4_contract_sha256"] == (
        "8e807d15d5372b0a9669d1190d899697e7c2911a73ddfb23095806c2a31de5b2"
    )
    assert evidence["ddc_discontinuities"] == 1
    assert evidence["ddc_saturation_events"] == 0
    assert evidence["score_count"] == 1341
    assert evidence["score_minimum"] == 0
    assert evidence["score_maximum"] == 255
    assert evidence["nonzero_score_count"] == 1159
    assert evidence["files"] == EXPECTED_XFFT_FILES
