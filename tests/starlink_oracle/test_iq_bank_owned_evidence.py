"""Portable receipt rejection tests, not another arithmetic simulation."""

from pathlib import Path

import pytest

from .iq_bank_owned_evidence import digest, expected_sources, parse_run

NUMERIC = """BANK_IQ_EXACT_REPLAY_PASS epoch=2 scores=1341
BANK_IQ_EXACT_REPLAY_PASS epoch=3 scores=1341
BANK_IQ_EXACT_REPLAY_PASS epoch=4 scores=1341
BANK_IQ_FAULT_RESET_GAP_PASS qualifier_mutations=5 descriptor=1 core_fault=1 fft_reset=1 slow_reset=1 source_gap=1 source_index=1 exact_epochs=4 exact_scores=5364 autonomous_gap_index_recovery=1
IQ_TO_SCORE_XFFT_PASS samples=1406 blocks=3 forward=1536 product=1536 inverse=1536 scores=1341 pss255=3 max_fifo=358
"""
CAPACITY = """BANK_IQ_CAPACITY_COMPLETE blocks=64 samples=28673 scores=28608
IQ_TO_SCORE_XFFT_LONGRUN_PASS samples=28673 blocks=64 forward=32768 product=32768 inverse=32768 scores=28608 fifo_max=358
IQ_TO_SCORE_XFFT_BACKLOG_PASS blocks=64 overlap_queue_max=1 ring_retention_age_max=589 energy_lookup_age_max=847 source_burst_mode=1 score_stall_mode=1
BANK_IQ_CAPACITY_METADATA_PASS blocks=64 forward=32768 product=32768 inverse=32768
""" + "".join(
    f"IQ_TO_SCORE_XFFT_LONGRUN_PROGRESS block={n} scores={n * 447}\n"
    for n in range(1, 65)
)


def receipt(tmp_path: Path, transcript: str, mode: str = "numeric") -> Path:
    directory = tmp_path / "receipt"
    logdir = directory / "project/iq_to_score_bank_owned.sim/sim_1/behav/xsim"
    logdir.mkdir(parents=True)
    (logdir / "simulate.log").write_text(transcript)
    (directory / "receipt.log").write_text(
        f"BANK_IQ_TO_SCORE_ACTUAL_CORE_VERIFIED mode={mode} fast_mhz=175 NO_PHYSICAL_OR_RF_CLAIM\n"
    )
    source_dir = directory / "frozen_sources"
    source_dir.mkdir()
    sources = [source_dir / name for name in sorted(expected_sources(mode))]
    for source in sources:
        source.write_text("// synthetic parser fixture, not HDL evidence\n")
    suffix = "_longrun" if mode == "capacity" else ""
    generated = [
        directory / f"tb_starlink_pss_iq_to_score_xfft{suffix}.sv",
        directory / "project/iq_to_score_bank_owned.gen/sources_1/ip/"
        "starlink_pss_fft512_bfp18_rt_candidate/synth/"
        "starlink_pss_fft512_bfp18_rt_candidate.vhd",
    ]
    for path in generated:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic generated input for parser test only\n")
    (directory / "scope.txt").write_text(
        "fast_mhz=175 slow_mhz=100 source_msps=15\n"
        + "".join(f"{digest(source)}  {source}\n" for source in sources)
        + "".join(f"{digest(path)}  {path}\n" for path in generated)
    )
    return directory


def test_numeric_receipt_keeps_four_epochs_distinct(tmp_path):
    result = parse_run(receipt(tmp_path, NUMERIC), "numeric", 175, "exact")
    assert result["numeric"]["scores"] == 1341
    assert result["boundary_receipt"]["exact_scores"] == 5364
    assert [row["epoch"] for row in result["exact_replays"]] == [2, 3, 4]


@pytest.mark.parametrize(
    "bad",
    [
        NUMERIC + "Fatal: problem\n",
        NUMERIC + "IQ_TO_SCORE_XFFT_FAIL assertion\n",
        NUMERIC + "IQ_TO_SCORE_XFFT_LONGRUN_FAULT assertion\n",
        NUMERIC.replace("epoch=3", "epoch=2"),
        NUMERIC.replace(
            "autonomous_gap_index_recovery=1", "autonomous_gap_index_recovery=0"
        ),
        NUMERIC.replace("product=1536", "product=1535"),
        NUMERIC + NUMERIC,
    ],
)
def test_false_numeric_passes_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        parse_run(receipt(tmp_path, bad), "numeric", 175, "exact")


def test_source_must_match_pre_run_hash(tmp_path):
    directory = receipt(tmp_path, NUMERIC)
    (directory / "frozen_sources/starlink_pss_iq_to_score_bank_owned.v").write_text(
        "changed after measurement\n"
    )
    with pytest.raises(ValueError, match="pre-simulation hash"):
        parse_run(directory, "numeric", 175, "exact")


@pytest.mark.parametrize("mutation", ["deleted", "extra"])
def test_missing_or_extra_frozen_source_is_rejected(tmp_path, mutation):
    directory = receipt(tmp_path, NUMERIC)
    if mutation == "deleted":
        (directory / "frozen_sources/starlink_pss_iq_to_score_bank_owned.v").unlink()
    else:
        (directory / "frozen_sources/unmeasured.v").write_text("extra\n")
    with pytest.raises(ValueError, match="source inventory"):
        parse_run(directory, "numeric", 175, "exact")


def test_capacity_has_full_continuous_inventory(tmp_path):
    result = parse_run(
        receipt(tmp_path, CAPACITY, "capacity"), "capacity", 175, "bursty-stalled"
    )
    assert result["counts"]["scores"] == 28608
    assert len(result["score_block_progress"]) == 64


@pytest.mark.parametrize(
    "bad",
    [
        CAPACITY.replace("block=64 scores=28608", "block=63 scores=28161"),
        CAPACITY.replace("fifo_max=358", "fifo_max=512"),
        CAPACITY.replace("energy_lookup_age_max=847", "energy_lookup_age_max=2048"),
        CAPACITY.replace("score_stall_mode=1", "score_stall_mode=0"),
    ],
)
def test_capacity_boundary_failures_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        parse_run(receipt(tmp_path, bad, "capacity"), "capacity", 175, "bursty-stalled")
