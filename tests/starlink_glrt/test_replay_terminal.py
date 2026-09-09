import pytest

from tools.starlink_glrt_replay import terminal_state


def test_partial_frame_is_retained_without_excusing_unfinished_complete_work():
    status = [0]*18
    status[13] = status[14] = 1
    trace = [1, 50000, 49999, 49600, 1, 34, 49600]
    result = terminal_state(status, trace, 50000, 1)
    assert result["native_waiting_for_future_input"]
    assert result["required_support_end_native"] == 50326
    assert result["collected_symbols"] == 34
    for index, value in [(0, 0), (1, 49999), (2, 49998), (3, 49000), (4, 3), (5, 0), (5, 64), (6, 49599)]:
        changed = trace.copy()
        changed[index] = value
        with pytest.raises(ValueError):
            terminal_state(status, changed, 50000, 1)
    status[13] = 0
    with pytest.raises(ValueError, match="complete scorer"):
        terminal_state(status, trace, 50000, 1)
