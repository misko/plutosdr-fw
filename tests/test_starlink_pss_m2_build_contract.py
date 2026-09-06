from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "starlink-pss-multirate-rx-only-dnm-v7-source.yaml"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_m2_manifest_is_nonpersistent_15_msps_internal_qualification() -> None:
    manifest = _read(f"manifests/{MANIFEST_NAME}")

    for contract in (
        "do_not_merge: true",
        "merge_target: none",
        "persistent_flash_eligible: false",
        "hardware_qualified: false",
        "allocated_radio_serial: 104000bac4950008230026001b440a003a",
        "source_change: bounded-periodic-injection-qualification",
        "starlink_pss_profile: acquisition-injection",
        "starlink_pss_profile_rate_gate_msps: 15",
        "m2_controller_persistent_install: false",
        "m2_controller_claim_scope: deterministic_internal_timing_only",
        "m2_fixture_samples: 130",
        "m2_period_samples: 20000",
        "m2_repetitions: 130",
        "m2_default_test_phases: 0,19999,7311",
        "m2_timing_tolerance_canonical_samples: 1",
        "route_15_bus_skew_endpoints: 8,8,32,64,64,4,4",
        "submodule_hdl: 9f3851d33c171a29b28a7b6a5a5469759ad5c79f",
        "hdl-pss15-30-60-acquisition-v7",
    ):
        assert contract in manifest


def test_m2_builder_and_packager_are_exactly_15_msps_and_artifact_bound() -> None:
    builder = _read("scripts/ci/build_main_firmware.sh")
    packager = _read("scripts/ci/package_main_firmware.sh")

    for source in (builder, packager):
        assert MANIFEST_NAME in source
        assert "acquisition-injection" in source
        assert '"$STARLINK_PSS_RATE_MSPS" == 15' in source
    for command in (
        "axi_starlink_pss_periodic_injector/run_tests.sh",
        "run_starlink_pss15_m2_periodic_xfft.sh",
        "make -C tools/starlink_pssctl check",
        "make -C tools/starlink_pssctl sanitize",
    ):
        assert command in builder
    for artifact in (
        "starlink_pss_m2ctl",
        "upper_edge_pss_periodic_fixture_ci16.mem",
        "m2_period_scores_u8.mem",
    ):
        assert artifact in builder
        assert artifact in packager
    assert "STARLINK_PSS_ACQUISITION_INJECTION_BUILD=true" in packager
    assert "REQUIRED_BUS_SKEW_CONSTRAINTS=7" in packager
    assert "validate_starlink_pss_acquisition_injection_route_reports.py" in packager
    assert (
        'protected_version="v0.50-plutoplus-starlink-pss-'
        '${STARLINK_PSS_RATE_MSPS}m-rx-only-dnm-v7"'
    ) in packager


def test_dnm_workflow_selects_only_the_m2_v7_identity() -> None:
    workflow = _read(".github/workflows/firmware-main.yml")

    assert MANIFEST_NAME in workflow
    assert "format('plutoplus-starlink-pss-{0}m-rx-only-dnm-v7'" in workflow
    assert "'acquisition-injection' || ''" in workflow
    assert 'test "$STARLINK_PSS_RATE_MSPS" = 15' in workflow
    assert (
        'expected="v0.50-plutoplus-starlink-pss-'
        '${STARLINK_PSS_RATE_MSPS}m-rx-only-dnm-v7"'
    ) in workflow


def test_candidate_planner_defaults_to_the_v7_manifest() -> None:
    planner = _read("scripts/starlink_pss_multirate_candidate_plan.py")

    assert f'SOURCE_MANIFEST_NAME = "{MANIFEST_NAME}"' in planner
    assert f'"{MANIFEST_NAME}": "v7"' in planner
    assert '{"v2", "v3", "v4", "v5", "v6", "v7"}' in planner


def test_m2_controller_treats_abi_1_1_as_fixed_15_msps() -> None:
    controller = _read("tools/starlink_pssctl/starlink_pss_m2ctl.c")

    assert "static uint32_t input_rate_msps(const struct pss_map_info *info)" in controller
    assert "if (info->version == PSS_MAP_VERSION_1_2)\n\t\treturn 30U;" in controller
    assert "if (info->version == PSS_MAP_VERSION_1_3)\n\t\treturn 60U;" in controller
    assert "return 15U;" in controller
    assert "serial, input_rate_msps(map_info), map_info->version" in controller
    assert "input_rate_msps(map_info) != 15U" in controller
    assert "map_info->input_rate_msps != 15U" not in controller
