"""Scheduling assumptions and rejection gates; no new FFT numerical oracle."""
from pathlib import Path

import pytest

from .fft_island_budget import estimate, read_measurement, verify_reference


def run(rate, **kwargs):
    return estimate(rate, service_cycles=5182, output_offset=4664, **kwargs)


@pytest.mark.parametrize("rate,sustainable", [(150_000_000, False), (175_000_000, True),
                                            (200_000_000, True)])
def test_nominal_capacity_and_expiry_are_distinct(rate, sustainable):
    result = run(rate)
    assert result.sustained_under_declared_model == sustainable
    if sustainable:
        assert result.final_start_backlog_us == 0
        assert result.maximum_pending_input_blocks == 1
        assert result.first_energy_expiry_block is None
    else:
        assert result.first_energy_expiry_block is not None
        assert result.maximum_pending_input_blocks > 4


def test_outer_bank_owns_slow_drain_and_absorbs_bounded_stall():
    # A 10 us stall cannot stall this island while the prior bank ACK fits
    # inside the 29.8 us output-to-output period. The extra retention age counts.
    nominal, stalled = run(200_000_000), run(200_000_000, egress_stall=1000)
    assert stalled.maximum_egress_wait_us == 0
    assert stalled.maximum_energy_age_samples == nominal.maximum_energy_age_samples + 150
    assert stalled.sustained_under_declared_model


def test_repeated_small_compute_stall_consumes_175mhz_margin():
    result = run(175_000_000, extra_cycles=64)
    assert not result.sustained_under_declared_model
    assert result.island_slack_us < 0
    assert result.final_start_backlog_us > 0
    assert result.first_energy_expiry_block is not None


def test_outer_bank_cannot_hide_unbounded_sink_stall():
    result = run(200_000_000, egress_stall=4000)
    assert result.maximum_egress_wait_us > 0
    assert not result.sustained_under_declared_model


def test_input_validation_and_missing_reference(tmp_path: Path):
    with pytest.raises(ValueError):
        run(0)
    with pytest.raises(ValueError):
        run(200_000_000, extra_cycles=-1)
    with pytest.raises(FileNotFoundError):
        verify_reference(tmp_path)


def test_failed_simulation_is_not_measurement(tmp_path: Path):
    log = tmp_path / "simulate.log"
    log.write_text("Fatal: incomplete numerical test\n")
    with pytest.raises(ValueError, match="passing actual-core"):
        read_measurement(tmp_path / "nonexistent.csv", log)
