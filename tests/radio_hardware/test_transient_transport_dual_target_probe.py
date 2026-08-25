"""Physical guarded weak dual-target batch transport preflight."""

import json
from typing import Any

import pytest

from .experiment import Issue46Options
from .tandem_quality import TandemQualityOptions
from .transient_transport_probe import (
    DUAL_TARGET_PROBE_SCHEMA,
    DUAL_TARGET_PROBE_VERDICT,
    TransientTransportProbeOptions,
    run_serial_dual_target_transient_transport_probe,
)

pytestmark = [
    pytest.mark.radio_hardware,
    pytest.mark.tandem_transient_dual_target_probe,
]


def test_weak_dual_target_batch_transport_is_qualified(
    tandem_transient_dual_target_probe_radio_options: Issue46Options,
    tandem_transient_dual_target_probe_quality: TandemQualityOptions,
    tandem_transient_transport_probe_options: TransientTransportProbeOptions,
) -> None:
    pytest.importorskip("numpy", reason="dual-RX transport capture requires numpy")
    try:
        import iio
    except ImportError:
        pytest.fail("manifest-pinned pylibiio is not importable", pytrace=False)

    report, path = run_serial_dual_target_transient_transport_probe(
        iio,
        tandem_transient_dual_target_probe_radio_options,
        tandem_transient_dual_target_probe_quality,
        probe=tandem_transient_transport_probe_options,
    )

    assert report["schema"] == DUAL_TARGET_PROBE_SCHEMA
    assert report["verdict"] == DUAL_TARGET_PROBE_VERDICT, (
        f"weak dual-target transport was not qualified; report={path}\n"
        f"{json.dumps(report, indent=2, sort_keys=True)}"
    )
    assert report["release_pass_eligible"] is False
    assert report["strong_tx_write_permitted"] is False
    cleanup: Any = report.get("cleanup")
    assert isinstance(cleanup, dict) and cleanup.get("verified") is True
