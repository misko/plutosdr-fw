"""Resource table interpretation tests; no timing or synthesized-area claim."""

from .iq_bank_owned_resource_evidence import hierarchy_rows


def test_full_coarse_resource_columns_are_not_slice_or_logic_only():
    rows = hierarchy_rows(
        "| Instance | Module | Total LUTs | Logic LUTs | LUTRAMs | SRLs | FFs | RAMB36 | RAMB18 | DSP Blocks |\n"
        "| starlink_pss_iq_to_score_bank_owned | (top) | 3868 | 3616 | 64 | 188 | 6499 | 6 | 16 | 27 |\n"
        "| island | starlink_pss_fft_bank_owned_slice | 1829 | 1641 | 0 | 188 | 4375 | 0 | 15 | 21 |\n"
    )
    assert len(rows) == 2
    coarse, island = rows
    assert coarse["total_luts"] == coarse["logic_luts"] + coarse["lutram"] + coarse["srl"]
    assert coarse["ramb36"] + coarse["ramb18"] / 2 == 14
    assert island["ramb36"] + island["ramb18"] / 2 == 7.5
    assert coarse["dsp"] == 27 and island["dsp"] == 21


def test_incomplete_or_non_numeric_resource_rows_are_not_accepted():
    assert hierarchy_rows("| incomplete | (top) | 123 |\n") == []
    assert hierarchy_rows("| instance | (top) | unknown | 0 | 0 | 0 | 0 | 0 | 0 | 0 |\n") == []
