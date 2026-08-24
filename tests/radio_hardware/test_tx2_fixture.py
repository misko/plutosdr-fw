"""Physical gate: TX2 reaches both receivers through the declared pads/tee."""

import pytest

from .experiment import Issue46Radio

pytestmark = [pytest.mark.radio_hardware, pytest.mark.issue46]


def test_tx2_dds_tone_qualifies_both_tee_branches(
    qualified_issue46_radio: Issue46Radio,
) -> None:
    result = qualified_issue46_radio.tone_qualification
    assert result is not None
    assert result["valid"]
    assert result["rx0"]["valid"]
    assert result["rx1"]["valid"]
