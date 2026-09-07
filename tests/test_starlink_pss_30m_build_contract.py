from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "starlink-pss-multirate-rx-only-dnm-v9-source.yaml"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_v9_manifest_is_nonpersistent_30_msps_acquisition_only() -> None:
    manifest = _read(f"manifests/{MANIFEST_NAME}")

    for contract in (
        "do_not_merge: true",
        "merge_target: none",
        "persistent_flash_eligible: false",
        "hardware_qualified: false",
        "hardware_accessed_by_this_revision: false",
        "allocated_radio_serial: 104000bac4950008230026001b440a003a",
        "source_change: separate-ddc-cold-start-index-from-real-gap",
        "starlink_pss_profile: acquisition-only",
        "starlink_pss_profile_rate_gate_msps: 30",
        "starlink_pss_tracker_included: false",
        "starlink_pss_rx0_fanout: direct-to-acquisition-and-rx-dma",
        "starlink_pss_abi_30: 1.2",
        "starlink_pss_group_delay_30_source_samples: 7",
        "route_30_firmware_source: 4dd46af19479474cc6cfd88b525ab33afa49ad7d",
        "route_30_wns_ns: 0.673",
        "route_30_whs_ns: 0.018",
        "route_30_slice: 4180",
        "route_30_dsp: 52",
        "route_30_bit_sha256: b2d514607afccc18fa68f98bc57ac9b33ca9bea2fd28316b79b15339bdb7a2df",
        "starlink_pss_clean_start_scheduler_gaps: 0",
        "submodule_hdl: 74d4d38a1df5438199c2306a84be56da900ffd96",
        "hdl-pss15-30-60-acquisition-v8",
    ):
        assert contract in manifest


def test_v9_build_and_package_routes_are_exactly_30_msps() -> None:
    builder = _read("scripts/ci/build_main_firmware.sh")
    packager = _read("scripts/ci/package_main_firmware.sh")
    image_builder = _read("scripts/build_gain_series_candidate.sh")

    for source in (builder, packager, image_builder):
        assert MANIFEST_NAME in source
    for source in (builder, packager):
        assert "v8/v9 acquisition-only qualification is gated to 30 MS/s" in source
        assert "acquisition-only" in source
    assert "STARLINK_PSS_ACQUISITION_ONLY_BUILD=true" in packager
    assert "REQUIRED_BUS_SKEW_CONSTRAINTS=5" in packager
    assert "validate_starlink_pss_acquisition_only_route_reports.py" in packager
    assert (
        'protected_version="v0.50-plutoplus-starlink-pss-'
        '${STARLINK_PSS_RATE_MSPS}m-rx-only-dnm-v9"'
    ) in packager


def test_candidate_planner_admits_but_does_not_default_to_v9() -> None:
    planner = _read("scripts/starlink_pss_multirate_candidate_plan.py")

    assert f'"{MANIFEST_NAME}": "v9"' in planner
    assert '{"v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9"}' in planner
    assert (
        'SOURCE_MANIFEST_NAME = '
        '"starlink-pss-multirate-rx-only-dnm-v7-source.yaml"'
    ) in planner
