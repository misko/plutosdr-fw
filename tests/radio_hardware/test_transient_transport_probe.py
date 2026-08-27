"""Physical qualification of tandem metadata transport at a guarded weak level."""

import json
from typing import Any

import pytest

from .experiment import Issue46Options
from .tandem_quality import TandemQualityOptions
from .transient_transport_probe import (
    TransientTransportProbeOptions,
    run_serial_transient_transport_probe,
)

pytestmark = [
    pytest.mark.radio_hardware,
    pytest.mark.tandem_transient_transport_probe,
]


def test_weak_tandem_transient_transport_is_qualified(
    tandem_transient_transport_probe_radio_options: Issue46Options,
    tandem_transient_transport_probe_quality: TandemQualityOptions,
    tandem_transient_transport_probe_options: TransientTransportProbeOptions,
) -> None:
    pytest.importorskip("numpy", reason="dual-RX transport capture requires numpy")
    try:
        import iio
    except ImportError:
        pytest.fail("manifest-pinned pylibiio is not importable", pytrace=False)

    report, path = run_serial_transient_transport_probe(
        iio,
        tandem_transient_transport_probe_radio_options,
        tandem_transient_transport_probe_quality,
        probe=tandem_transient_transport_probe_options,
    )

    assert report["verdict"] == "qualified_transport", (
        f"tandem transient transport was not qualified; report={path}\n"
        f"{json.dumps(report, indent=2, sort_keys=True)}"
    )
    assert report["release_pass_eligible"] is False
    cleanup: Any = report.get("cleanup")
    assert isinstance(cleanup, dict) and cleanup.get("verified") is True
