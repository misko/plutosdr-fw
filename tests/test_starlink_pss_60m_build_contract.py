from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "starlink-pss-multirate-rx-only-dnm-v10-source.yaml"


def test_v10_manifest_is_nonpersistent_60_msps_acquisition_only() -> None:
    manifest = (ROOT / "manifests" / MANIFEST_NAME).read_text()
    for expected in (
        "do_not_merge: true",
        "persistent_flash_eligible: false",
        "source_change: widen-60m-ddc-observation-counters",
        "starlink_pss_profile: acquisition-only",
        "starlink_pss_profile_rate_gate_msps: 60",
        "starlink_pss_tracker_included: false",
        "starlink_pss_60_ddc_stages: 2",
        "starlink_pss_abi_60: 1.4",
        "starlink_pss_60_ddc_observation_counter_bits: 64",
        "starlink_pss_60_ddc_counter_read_policy: high-low-high-coherent",
        "submodule_hdl: b6a8cdf1a2f627b32b3f80d179802efe2ff2313f",
        "versions_hdl: starlink-rx-only-dnm-v1-source/hdl-pss60-acquisition-v9",
    ):
        assert expected in manifest


def test_v10_build_and_package_routes_are_exactly_60_msps() -> None:
    build = (ROOT / "scripts/ci/build_main_firmware.sh").read_text()
    package = (ROOT / "scripts/ci/package_main_firmware.sh").read_text()
    candidate = (ROOT / "scripts/build_gain_series_candidate.sh").read_text()
    for source in (build, package, candidate):
        assert MANIFEST_NAME in source
    for source in (build, package):
        assert "v10 acquisition-only qualification is gated to 60 MS/s" in source
    assert '${STARLINK_PSS_RATE_MSPS}m-rx-only-dnm-v10"' in package


def test_candidate_planner_admits_but_does_not_default_to_v10() -> None:
    planner = (ROOT / "scripts/starlink_pss_multirate_candidate_plan.py").read_text()
    assert f'"{MANIFEST_NAME}": "v10"' in planner
    assert 'SOURCE_MANIFEST_NAME = "starlink-pss-multirate-rx-only-dnm-v7-source.yaml"' in planner
