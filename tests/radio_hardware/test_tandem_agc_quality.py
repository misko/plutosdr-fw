"""Physical acceptance: compare dual-RX quality across all three gain modes."""

import json

import pytest

from .experiment import Issue46Radio
from .tandem_quality import TandemQualityOptions, run_tandem_quality_matrix

pytestmark = [pytest.mark.radio_hardware, pytest.mark.tandem_quality]


def test_tx2_loudness_matrix_compares_manual_native_and_tandem_agc(
    tandem_quality_radio: Issue46Radio,
    tandem_quality_options: TandemQualityOptions,
) -> None:
    report, path = run_tandem_quality_matrix(
        tandem_quality_radio, tandem_quality_options
    )
    assert report["verdict"] == "pass", (
        f"tandem AGC quality matrix failed; report={path}\n"
        f"{json.dumps(report.get('evaluation', {}), indent=2, sort_keys=True)}"
    )
