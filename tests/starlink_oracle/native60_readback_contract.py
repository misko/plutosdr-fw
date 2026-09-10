"""Additive readback-only contract. Original command/source/service recipe stays fixed."""

from copy import deepcopy

CONTRACT = {
    "schema": "native60-public-index-readback-v1",
    "control_period_fs": 10000000,
    "source_period_fs": 16666666,
    "source_offer_to_accept_fs": 8333333,
    "gray_control_stages": 2,
    "public_read_transactions": 2,
    "per_transaction_control_cycles": 24,
    "low_capture_to_pair_return_control_cycles": 48,
    "maximum_offered_source_lag_at_capture": 2,
    "maximum_offered_source_lag_at_return": 31,
    "low_word_address": 0x18,
    "low_word_up_address": 6,
    "capture_condition": "known up_rreq && !register_read_pending && !result_read_pending && !telemetry_read_pending && up_raddr==6",
    "capture_count": 1,
    "coherence": "completed public low/high64 and retained hardware snapshot equal independently observed current_sample_index at actual low-register capture",
    "no_future": True,
    "original_command_source_service_limits_unchanged": True,
    "scope": "ideal fixed-phase simulation; registered Gray plus2control stages; no physical CDC/metastability latency claim",
}


def contract():
    return deepcopy(CONTRACT)


def limits():
    c = contract()
    ceil_div = lambda n, d: (n+d-1)//d
    capture = ceil_div(c["gray_control_stages"]*c["control_period_fs"] + c["source_offer_to_accept_fs"], c["source_period_fs"])
    cycles = c["public_read_transactions"]*c["per_transaction_control_cycles"]
    returned = capture + ceil_div(cycles*c["control_period_fs"], c["source_period_fs"])
    assert (capture, cycles, returned) == (2, 48, 31)
    return {"capture_lag": capture, "return_cycles": cycles, "return_lag": returned}
