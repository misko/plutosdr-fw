"""Adversarial finite replay accounting cannot excuse a lost supported vector."""
import pytest

from tools.starlink_glrt_replay import closed_terminal_state


def test_finite_replay_distinguishes_tail_from_supported_vector_loss():
    status = [0] * 18
    status[8], status[9], status[10], status[15] = 3, 1, 2, 5
    trace = [1, 1, 0, 1, 1, 2, 2, 1, 1, 0]
    result = closed_terminal_state(status, trace, [4900], 5000, 1)
    assert result["native_incomplete_tails"] == 1
    assert result["completed_native_vectors"] == 2
    for changed_index, value in [(0, 0), (1, 0), (2, 1), (3, 0), (5, 1), (6, 1), (7, 0), (8, 2), (9, 1)]:
        changed = trace.copy()
        changed[changed_index] = value
        with pytest.raises(ValueError):
            closed_terminal_state(status, changed, [4900], 5000, 1)
    with pytest.raises(ValueError, match="supported work"):
        closed_terminal_state(status, trace, [4000], 5000, 1)
    with pytest.raises(ValueError, match="supported work"):
        closed_terminal_state(status, trace, [], 5000, 1)
