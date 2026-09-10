"""Late30 contract frozen before the first negative probe, never fitted to it."""

from copy import deepcopy

CONTRACT = {
    "case": "30-upper-bank175-native132-pil1-447x2-late-command-v1",
    "raw_first": 17179867609,
    "native_center": 17179870192,
    "capture_start": 17179870128,
    "command_trigger_raw": 17179870160,
    "actual_handshake_raw_closed": [17179870160, 17179870240],
    "actual_signed_lead_closed": [-113, -33],
    "command_control_cycle_limit": 256,
    "command_axi_transactions": 8,
    "axi_cycle_limit": 24,
    "entry_edges_allowance": 8,
    "wrapper_queue_cdc_margin_cycles": 32,
    "derived_command_cycle_budget": 8 * 24 + 8 + 32,
    "telemetry_snapshot_cycle_limit": 512,
    "negative_observation_raw": 17179875609,
    "native_rejected": 1,
    "native_late": 1,
    "native_admitted_capture_compute_result_irq": 0,
    "source_count": 12303,
    "coarse_admitted": 894,
    "map_words": 447,
    "pilot_selected": 512,
    "scope": "late command rejection with configured coefficients, not an RF detector miss",
}


def validate_contract():
    assert CONTRACT["derived_command_cycle_budget"] == 232 <= CONTRACT["command_control_cycle_limit"]
    assert CONTRACT["command_control_cycle_limit"] * 30 <= 80 * 100
    first, last = CONTRACT["actual_handshake_raw_closed"]
    assert [CONTRACT["capture_start"] - last - 1, CONTRACT["capture_start"] - first - 1] == CONTRACT["actual_signed_lead_closed"]
    assert first == CONTRACT["capture_start"] + 32
    assert CONTRACT["negative_observation_raw"] == CONTRACT["raw_first"] + 8000
    return deepcopy(CONTRACT)
