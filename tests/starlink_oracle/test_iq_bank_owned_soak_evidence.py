"""4096 receipt must contain every ordered block, not merely a longer label."""

import pytest

from .iq_bank_owned_evidence import parse_run
from .test_iq_bank_owned_evidence import CAPACITY, receipt


def long_transcript():
    header = "\n".join(
        line for line in CAPACITY.splitlines() if "LONGRUN_PROGRESS" not in line
    )
    header = header.replace("blocks=64", "blocks=4096").replace(
        "samples=28673", "samples=1830977"
    )
    header = header.replace("scores=28608", "scores=1830912").replace(
        "=32768", "=2097152"
    )
    return (
        header
        + "\n"
        + "".join(
            f"IQ_TO_SCORE_XFFT_LONGRUN_PROGRESS block={n} scores={n * 447}\n"
            for n in range(1, 4097)
        )
    )


def soak_receipt(tmp_path, text):
    directory = receipt(tmp_path, text, "capacity")
    scope = directory / "scope.txt"
    scope.write_text(
        scope.read_text().replace("capacity_blocks=64 ", "capacity_blocks=4096 ")
    )
    return directory


def test_full_4096_inventory_is_distinct_from_default64(tmp_path):
    directory = soak_receipt(tmp_path, long_transcript())
    result = parse_run(
        directory, "capacity", 175, "bursty-stalled", capacity_blocks=4096
    )
    assert result["counts"]["samples"] == 1830977
    assert result["counts"]["scores"] == 1830912
    assert len(result["score_block_progress"]) == 4096
    with pytest.raises(ValueError, match="pre-run scope"):
        parse_run(directory, "capacity", 175, "bursty-stalled")


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "metadata", "scope", "failure"]
)
def test_4096_false_receipts_rejected(tmp_path, mutation):
    text = long_transcript()
    if mutation == "missing":
        text = text.replace(
            "IQ_TO_SCORE_XFFT_LONGRUN_PROGRESS block=2048 scores=915456\n", ""
        )
    elif mutation == "duplicate":
        text = text.replace("block=2048 scores=915456", "block=2047 scores=915009")
    elif mutation == "metadata":
        text = text.replace("forward=2097152", "forward=32768")
    elif mutation == "failure":
        text += "IQ_TO_SCORE_XFFT_LONGRUN_FAULT cause=energy_cache_miss\n"
    directory = soak_receipt(tmp_path, text)
    if mutation == "scope":
        scope = directory / "scope.txt"
        scope.write_text(
            scope.read_text().replace("capacity_blocks=4096 ", "capacity_blocks=64 ")
        )
    with pytest.raises(ValueError):
        parse_run(directory, "capacity", 175, "bursty-stalled", capacity_blocks=4096)
