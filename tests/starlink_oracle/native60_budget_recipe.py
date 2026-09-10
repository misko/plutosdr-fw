"""Native60-only service-probe admission, frozen before service evaluation.

This does not enable a PSMA60/bank60 profile. The source/goldens belong to the
already frozen numerical cohort; the probe may not extend that finite source.
"""

from copy import deepcopy

RECIPE = {
    "case": "native60-upper-full-source-service-v1",
    "cohort_sha256": "6de2f3645459f8649d8fee127e479991fb1cc55b75001a37c763223e716b4dfa",
    "cohort_source_signature": "c56f812b79f5bb8d5b60bc70af43ad0b5f1579e5af0e74dd8516fabeb2237c0a",
    "source_rate_msps": 60,
    "source_clock_phase_ns": "2.1",
    "source_half_period_ns_expression": "500.0/60",
    "source_half_period_fs": 8333333,
    "source_period_fs": 16666666,
    "source_clock_tolerance_fs": 1,
    "control_period_fs": 10000000,
    "source_clock_runs_after_valid_stop": True,
    "source_half_open": [34359735211, 34359751634],
    "source_count": 16423,
    "added_tail_count": 0,
    "command_trigger": 34359738560,
    "command_handshake_closed": [34359738560, 34359738720],
    "command_lead_closed": [1535, 1695],
    "command_limit_control_cycles": 256,
    "native_center": 34359740384,
    "native_capture_half_open": [34359740256, 34359740776],
    "native_capture_count": 520,
    "native_taps": 264,
    "native_raw_lags_closed": [-128, 128],
    "native_raw_count": 257,
    "native_qualified_lags_closed": [-120, 120],
    "native_qualified_count": 241,
    "native_lag_wire_bits": 9,
    "native_Eh": 1073758594,
    "request_id": 0x60000520,
    "coefficient_generation": 0x60000001,
    "visit_fixture_context_only": 0x60000052,
    "public_identity": [0x50535354, 0x00010003, 60, 0x0F8C1108, 0x1D],
    "capture_transfer_cycles": 3 * 520 + 64,
    "sample_energy_cycles": 520 + 16,
    "per_raw_lag_cycles": 264 + 16 + 16,
    "publication_allowance_cycles": 128,
    "engine_derived_cycles": 78360,
    "publication_and_full_drain_limit_cycles": 84000,
    "axi_transaction_limit_cycles": 24,
    "readout_transaction_limit": 140,
    "packet_words": 26,
    "packet_read_passes": 2,
    "retention_control_cycles": 32,
    "release_settle_control_cycles": 24,
    "post_capture_limit_cycles": 88000,
    "final_no_stale_control_cycles": 256,
    "final_no_stale_start": "after source off, public result release, all257 raw handshakes and engine/bridge idle",
    "coefficient_generation_poll_limit": 2000,
    "global_control_cycle_watchdog": 160000,
    "assumptions": "healthy already-configured single job; free result store; 100MHz engine; dedicated public AXI <=24 cycles/transaction; no external arbitration",
    "scope": "standalone native wrapper only; static known center; no actual FFT/PSMA/PIL1, causal detection, hardware clock qualification or deployment",
}


def recipe():
    return deepcopy(RECIPE)
