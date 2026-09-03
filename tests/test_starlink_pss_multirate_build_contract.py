import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "starlink-pss-multirate-rx-only-dnm-v1-source.yaml"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _validator_module():
    path = ROOT / "scripts/ci/validate_starlink_pss_multirate_route_reports.py"
    spec = importlib.util.spec_from_file_location("multirate_route_validator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_multirate_manifest_is_immutable_dnm_and_records_all_routes() -> None:
    manifest = _read(f"manifests/{MANIFEST_NAME}")

    for boundary in (
        "do_not_merge: true",
        "merge_target: none",
        "persistent_flash_eligible: false",
        "hardware_qualified: false",
        "hardware_accessed_by_this_revision: false",
        "ppu_changed: false",
        "allocated_radio_serial: 104000bac4950008230026001b440a003a",
    ):
        assert boundary in manifest
    assert "starlink_pss_supported_rates_msps: 15,30,60" in manifest
    assert "starlink_pss_shared_xfft_instances: 1" in manifest
    assert "submodule_hdl: a3cc9592207e5600f617e5d82686c1c6671a8d67" in manifest
    assert (
        "submodule_hdl_ref: refs/tags/starlink-rx-only-dnm-v1-source/"
        "hdl-pss15-30-60-acquisition-v2"
    ) in manifest
    assert "submodule_buildroot: daf5ec3fe6b394337379394fa98a52815520d886" in manifest
    for rate in (15, 30, 60):
        assert f"route_{rate}_github_run:" in manifest
        assert f"route_{rate}_firmware_source:" in manifest
        assert f"route_{rate}_hdl_source:" in manifest
        assert f"route_{rate}_wns_ns:" in manifest
        assert f"route_{rate}_whs_ns:" in manifest
        assert f"route_{rate}_xsa_sha256:" in manifest
        assert f"route_{rate}_bit_sha256:" in manifest


def test_manual_dispatch_selects_one_rate_only_on_the_dnm_branch() -> None:
    workflow = _read(".github/workflows/firmware-main.yml")

    assert "Kalman firmware build (main + locked experiments)" in workflow
    assert "starlink_rate_msps:" in workflow
    for rate in ("'15'", "'30'", "'60'"):
        assert f"- {rate}" in workflow
    assert MANIFEST_NAME in workflow
    assert "format('plutoplus-starlink-pss-{0}m-rx-only-dnm-v1'" in workflow
    assert "STARLINK_PSS_RATE_MSPS:" in workflow
    assert "15|30|60" in workflow
    assert "astral-sh/setup-uv@d0cc045d04ccac9d8b7881df0226f9e82c39688e" in workflow
    assert "version: '0.12.5'" in workflow
    assert "Install pinned uv for Starlink model-vector tests" in workflow
    assert (
        'expected="v0.50-plutoplus-starlink-pss-'
        '${STARLINK_PSS_RATE_MSPS}m-rx-only-dnm-v1"'
    ) in workflow
    assert "push:\n    branches: [main]" in workflow
    assert "pull_request:" not in workflow


def test_multirate_builder_runs_current_rtl_and_only_selected_vendor_replay() -> None:
    builder = _read("scripts/ci/build_main_firmware.sh")
    image_builder = _read("scripts/build_gain_series_candidate.sh")
    runner = _read("run_starlink_pss_multirate_ddc_to_score_xfft.sh")

    assert MANIFEST_NAME in builder
    assert MANIFEST_NAME in image_builder
    for suite in (
        "hdl/library/axi_starlink_pss_acquisition/run_tests.sh",
        "hdl/library/starlink_pss_acquisition/run_tests.sh",
        "hdl/library/starlink_pss_raw_correlator/run_tests.sh",
        "hdl/library/axi_starlink_pss_tracker/run_tests.sh",
    ):
        assert suite in builder
    assert 'if [[ "$STARLINK_PSS_RATE_MSPS" == 15 ]]' in builder
    assert "run_starlink_pss15_iq_to_score_xfft.sh" in builder
    assert "run_starlink_pss_multirate_ddc_to_score_xfft.sh" in builder
    assert 'case "$rate_msps" in\n30|60)' in runner
    assert "simulate_pss30_ddc_to_score_xfft.tcl" in runner
    assert 'generator="tools/generate_starlink_pss${rate_msps}_ddc_xfft_vectors.py"' in runner

    rejected = subprocess.run(
        ["bash", str(ROOT / "run_starlink_pss_multirate_ddc_to_score_xfft.sh"), "25"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode == 2
    assert "{30|60}" in rejected.stderr


def test_only_60_msps_selects_the_timing_oriented_implementation_strategy() -> None:
    project = _read("hdl/projects/pluto/system_project.tcl")
    normalized = " ".join(project.replace("#", "").split())

    assert '$::env(STARLINK_PSS_RATE_MSPS) eq "60"' in project
    assert (
        "set_property strategy Performance_ExplorePostRoutePhysOpt "
        "[get_runs impl_1]"
    ) in project
    assert "does not reuse a prior checkpoint" in normalized
    assert "relax any timing constraint" in normalized
    assert project.count("Performance_ExplorePostRoutePhysOpt") == 1


def test_packager_dispatches_new_exact_route_gate_and_keeps_legacy_gate() -> None:
    packager = _read("scripts/ci/package_main_firmware.sh")

    assert 'STARLINK_RX_ONLY_BUILD=false' in packager
    assert 'STARLINK_PSS_MULTIRATE_BUILD=false' in packager
    assert "HEAD:manifests/starlink-rx-only-dnm-v1-source.yaml" in packager
    assert f"HEAD:manifests/{MANIFEST_NAME}" in packager
    assert "REQUIRED_BUS_SKEW_CONSTRAINTS=3" in packager
    assert "REQUIRED_BUS_SKEW_CONSTRAINTS=6" in packager
    assert "validate_starlink_rx_only_route_reports.py" in packager
    assert "validate_starlink_pss_multirate_route_reports.py" in packager
    assert (
        'protected_version="v0.50-plutoplus-starlink-pss-'
        '${STARLINK_PSS_RATE_MSPS}m-rx-only-dnm-v1"'
    ) in packager
    assert "persistent_flash_eligible=false" in packager


def _reviewed_cdc_report(module) -> str:
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
    return "\n".join(summary + [""] + rows) + "\n"


def _reviewed_bus_skew_report(module) -> str:
    chunks = []
    for source, endpoints in zip(
        module.BUS_SKEW_SOURCES,
        module.EXPECTED_BUS_SKEW_ENDPOINTS,
        strict=True,
    ):
        chunks.append(
            f"set_bus_skew -from [get_cells {{{source}}}] -to reviewed\n"
            f"Requirement: 10.000ns\nEndpoints: {endpoints}\nSlack (MET) : 1.000ns\n"
        )
    return "\n".join(chunks)


def test_multirate_route_validator_is_exact_and_fail_closed() -> None:
    validator = _validator_module()
    cdc = _reviewed_cdc_report(validator)
    bus_skew = _reviewed_bus_skew_report(validator)

    validator.validate_cdc_report(cdc)
    validator.validate_bus_skew_report(bus_skew)

    with pytest.raises(validator.ValidationError, match="critical crossing"):
        validator.validate_cdc_report(cdc.replace("overflow_sync/input", "other/input", 1))
    with pytest.raises(validator.ValidationError, match="bus-skew report has a violation"):
        validator.validate_bus_skew_report(bus_skew.replace("Slack (MET)", "Slack (VIOLATED)", 1))
    with pytest.raises(validator.ValidationError, match="endpoint inventory differs"):
        validator.validate_bus_skew_report(bus_skew.replace("Endpoints: 64", "Endpoints: 63", 1))
