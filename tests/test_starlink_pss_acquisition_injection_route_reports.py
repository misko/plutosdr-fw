import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = (
        ROOT / "scripts/ci/validate_starlink_pss_acquisition_injection_route_reports.py"
    )
    spec = importlib.util.spec_from_file_location(
        "acquisition_injection_validator", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cdc_report(module) -> str:
    summary = [
        f"{rule} {severity} {count} description"
        for (rule, severity), count in module.EXPECTED_SUMMARY.items()
    ]
    rows: list[str] = []
    row_id = 1
    for rule, source, destination in module.CRITICAL_CROSSINGS:
        rows.append(f"{row_id} {rule} Critical reviewed {source} {destination}")
        row_id += 1
    for source, destination in module.MULTIBIT_CROSSINGS:
        rows.append(f"{row_id} CDC-6 Warning reviewed {source} {destination}")
        row_id += 1
    used = {
        ("CDC-1", "Critical"): 1,
        ("CDC-4", "Critical"): 1,
        ("CDC-6", "Warning"): len(module.MULTIBIT_CROSSINGS),
    }
    for (rule, severity), count in module.EXPECTED_SUMMARY.items():
        for _ in range(count - used.get((rule, severity), 0)):
            rows.append(f"{row_id} {rule} {severity} reviewed-filler")
            row_id += 1
    return "\n".join(summary + ["starlink_pss_periodic_injector"] + rows) + "\n"


def _bus_skew_report(module) -> str:
    return (
        "\n".join(
            f"set_bus_skew -from [get_cells {{{source}}}] -to reviewed\n"
            f"Requirement: 10.000ns\nEndpoints: {endpoints}\n"
            "Slack (MET) : 1.000ns"
            for source, endpoints in zip(
                module.BUS_SKEW_SOURCES,
                module.EXPECTED_BUS_SKEW_ENDPOINTS,
                strict=True,
            )
        )
        + "\n"
    )


def test_exact_acquisition_injection_inventory_is_accepted() -> None:
    module = _module()
    module.validate_cdc_report(_cdc_report(module))
    module.validate_bus_skew_report(_bus_skew_report(module))


def test_missing_injector_hierarchy_is_rejected() -> None:
    module = _module()
    report = _cdc_report(module).replace("starlink_pss_periodic_injector", "missing")
    with pytest.raises(module.ValidationError, match="omits injector hierarchy"):
        module.validate_cdc_report(report)


def test_injector_mailbox_inventory_change_is_rejected() -> None:
    module = _module()
    report = _cdc_report(module).replace("arm_start_mailbox", "changed_mailbox", 1)
    with pytest.raises(module.ValidationError, match="multibit crossing"):
        module.validate_cdc_report(report)


def test_missing_bus_skew_constraint_is_rejected() -> None:
    module = _module()
    report = _bus_skew_report(module).replace("Slack (MET)", "missing", 1)
    with pytest.raises(module.ValidationError, match="exactly 7 met constraints"):
        module.validate_bus_skew_report(report)
