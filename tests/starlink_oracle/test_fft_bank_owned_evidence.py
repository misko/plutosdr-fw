"""Evidence gates must reject incomplete, faulted, or mismatched simulation."""
from pathlib import Path

import pytest

from .fft_bank_owned_evidence import budget, read_mutation, require_pass

PASS = ("FFT_BANK_OWNED_SLICE_PASS fast_mhz=150 healthy_blocks=44 inverse_words=22658 "
        "purge_cases=4 fault_cases=10 provisional_prefix_words=130 overlap_loads=37 "
        "acceptance_equality_witnesses=2 closed_input_prefetch_witnesses=18340 "
        "held_final_ready_witnesses=3")


def test_complete_and_provisional_words_are_separate():
    receipt = require_pass(PASS, 150)
    assert receipt["inverse_words"] - receipt["provisional_prefix_words"] == 44 * 512


@pytest.mark.parametrize("log,frequency", [
    ("Fatal: unqualified guard commit", 150),
    (PASS + "\nFatal: late failure", 150),
    (PASS, 175),
    (PASS.replace("fault_cases=10", "fault_cases=9"), 150),
    (PASS.replace("inverse_words=22658", "inverse_words=22528"), 150),
    (PASS.replace("held_final_ready_witnesses=3", "held_final_ready_witnesses=0"), 150),
    (PASS + "\n" + PASS, 150),
])
def test_reject_insufficient_receipts(log, frequency):
    with pytest.raises(ValueError):
        require_pass(log, frequency)


def test_150mhz_nominal_margin_does_not_cover_repeated_stalls():
    nominal, stalled = budget(4410, 150), budget(4650, 150)
    assert nominal["slack_fast_cycles"] == 60
    assert nominal["slack_us"] == 0.4
    assert nominal["observed_interval_within_budget"]
    assert not nominal["universal_worst_case_bound_proved"]
    assert not stalled["observed_interval_within_budget"]


def test_resource_clock_is_not_an_achieved_clock():
    assert budget(4820, 175)["observed_interval_within_budget"]
    with pytest.raises(ValueError):
        budget(0, 175)


def test_mutation_gate_rejects_unrelated_failures(tmp_path: Path):
    sim = tmp_path / "project/fft_bank_owned_slice.sim/sim_1/behav/xsim"
    sim.mkdir(parents=True)
    (sim / "simulate.log").write_text("Fatal: unrelated configuration failure\n")
    with pytest.raises(ValueError, match="specific held-final"):
        read_mutation(tmp_path)
