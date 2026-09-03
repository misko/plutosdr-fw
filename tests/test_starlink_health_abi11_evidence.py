from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HDL = ROOT / "hdl"
MANIFEST = ROOT / "manifests/starlink-pss15-health-abi11-dnm-v1-source.yaml"
REPORT = ROOT / "reports/STARLINK_PSS15_HEALTH_ABI11_V1.md"
FUNCTIONAL = ROOT / "reports/starlink-pss15-health-abi11-v1-functional-summary.txt"
SAMPLE_CDC_OOC = ROOT / "reports/starlink-pss15-sample-cdc-v1-ooc-summary.txt"
IQ_MAP_OOC = ROOT / "reports/starlink-pss15-health-abi11-iq-map-ooc-summary.txt"
AXI_OOC = ROOT / "reports/starlink-pss15-health-abi11-axi-ooc-summary.txt"
PLAN = ROOT / "STARLINK_PSS_15_30_60_PLAN.md"

FIRMWARE_COMMIT = "3fa1b1ba3a3bd7f115231ae8ffb8983300259d8e"
FIRMWARE_TAG = "starlink-rx-only-dnm-v1-source/firmware-pss15-health-abi11-v1"
HDL_COMMIT = "b7b564dd5e6a66a5c1ddf8f144d3bb6a9f8fc86a"
HDL_TAG = "starlink-rx-only-dnm-v1-source/hdl-pss15-health-abi11-v1"
INGRESS_COMMIT = "883e9824cebc2c8eaac0ad818cde22595dfd65e0"
INGRESS_TAG = "starlink-rx-only-dnm-v1-source/hdl-pss15-sample-cdc-v1"
GUARD_COMMIT = "4e443ec0463c5814e39819c4162ac9e94276ff78"

SUMMARY_SHA256 = {
    "health_abi11_functional_summary_sha256": (
        "f8128625db2bf916c1e6b1288a80c6a1c3cb7cffe98a6df616e91c404a68d63b"
    ),
    "sample_cdc_ooc_summary_sha256": (
        "c922c847c3049c1aef70fa24f1bc6a0acb0c6da3343cb7cd877add26f052fa1f"
    ),
    "health_abi11_iq_map_ooc_summary_sha256": (
        "3fdf00e63a955c45a69c923c6e377bd10ad2f3400568321b008c082f84273db2"
    ),
    "health_abi11_axi_ooc_summary_sha256": (
        "3efa46b7a9c140c4379c6958dfcd02d424e63c8bcb27893141ca800564a4f952"
    ),
}

HDL_FILES = {
    "sample_cdc_rtl_sha256": (
        "library/starlink_pss_acquisition/starlink_pss_sample_cdc.v",
        "e70c686701030fba054a8ff8af986078f5e9361e6858e866a6fcb07f95d6bf5a",
    ),
    "sample_cdc_constraints_sha256": (
        "library/starlink_pss_acquisition/starlink_pss_sample_cdc_constr.xdc",
        "507d2190ff261bf141f5b879d924f9935cf495f6483d684e018b704012207556",
    ),
    "sample_cdc_ooc_constraints_sha256": (
        "library/starlink_pss_acquisition/starlink_pss_sample_cdc_ooc.xdc",
        "74bf78ef625aab345ed98283350ccb08705d4d394b695a33935a974fd0a78009",
    ),
    "sample_cdc_ooc_tcl_sha256": (
        "library/starlink_pss_acquisition/synthesize_sample_cdc_ooc.tcl",
        "dc2988f7cd3cbf721da7bf1af7711f3c90b6af761b0d656469f8a890896365ce",
    ),
    "sample_cdc_ooc_runner_sha256": (
        "library/starlink_pss_acquisition/run_sample_cdc_ooc.sh",
        "4904c314e15634d7e6b97fa2c7fa5986e1b4038d62c9daefa508c27996d99a09",
    ),
    "sample_cdc_testbench_sha256": (
        "library/starlink_pss_acquisition/tb/tb_starlink_pss_sample_cdc.sv",
        "abbababa7a3dc87c357ebace77ab2c39b462fa3e504ede815981f698c1b038a0",
    ),
    "acquisition_health_rtl_sha256": (
        "library/starlink_pss_acquisition/starlink_pss_acquisition_health.v",
        "9c0a81f1487ee6c254dc7a5ece9049c5bc3f7aed47f6ba95ffb62df550ff3e36",
    ),
    "acquisition_health_testbench_sha256": (
        "library/starlink_pss_acquisition/tb/tb_starlink_pss_acquisition_health.sv",
        "7cb4d4e1c1ac55f0b522300098330673b36e7d86b102f2ad748ecb280bb3e1da",
    ),
    "iq_to_phase_map_rtl_sha256": (
        "library/starlink_pss_acquisition/starlink_pss_iq_to_phase_map.v",
        "11cf874b9c41dc1f426486223a6d631135d84bbf8bcfc94b88475719ae9a720e",
    ),
    "phase_map_axi_rtl_sha256": (
        "library/axi_starlink_pss_phase_map/axi_starlink_pss_phase_map.v",
        "07be49bf862c7ddc79c0ba6d5c60a301727d5e43506efe64ac6d36db71bdec95",
    ),
    "phase_map_axi_snapshot_testbench_sha256": (
        "library/axi_starlink_pss_phase_map/tb/tb_axi_starlink_pss_phase_map_snapshot.sv",
        "75ae8ca091050315fe144b88869ee0cabb64719314edb71bd2b70432637e92a7",
    ),
}

FIRMWARE_FILES = {
    "arm_acquisition_library_sha256": (
        "tools/starlink_pssctl/starlink_pss_acquisition.c",
        "72616d2af5bf9b4f02470d28049cd7cde27c55305ac0b0671533293415707081",
    ),
    "arm_acquisition_header_sha256": (
        "tools/starlink_pssctl/starlink_pss_acquisition.h",
        "b3cf0c695fdebd0629c20c5bfb242a58b395fd159c2eed3f05ad1a70d097b958",
    ),
    "arm_acquisition_selftest_sha256": (
        "tools/starlink_pssctl/test_starlink_pss_acquisition.c",
        "63748dcb33f88a1f556bee4d79d47ba1f39b80fb2f9d85a004b9a46c9fa2f09c",
    ),
    "arm_acquisition_readme_sha256": (
        "tools/starlink_pssctl/README.md",
        "0befef0aa5f92ae6e2767f77ade3671c7c1f917ff287f46bdac5702d7b329cf0",
    ),
    "arm_acquisition_differential_test_sha256": (
        "tests/test_starlink_pss_acquisition_c.py",
        "e1cbd226e5cc6b31cb0d22982c7325870d7354db089c6978657979e8e488c429",
    ),
    "arm_acquisition_runner_sha256": (
        "run_starlink_pss15_arm_acquisition.sh",
        "1ca766e11fa6ffc6e0752bc99ddff7bb04384bf143963757d784a80fa120b1e4",
    ),
}


def _run(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(
        args, cwd=cwd, check=True, text=True, stdout=subprocess.PIPE
    ).stdout.strip()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _summary(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text().splitlines())


def _git_blob(commit: str, relative: str, cwd: Path = ROOT) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def test_health_abi11_source_graph_and_tags_are_frozen() -> None:
    assert _run("git", "rev-parse", f"{FIRMWARE_TAG}^{{}}") == FIRMWARE_COMMIT
    assert _run("git", "rev-parse", f"{HDL_TAG}^{{}}", cwd=HDL) == HDL_COMMIT
    assert _run("git", "rev-parse", f"{INGRESS_TAG}^{{}}", cwd=HDL) == INGRESS_COMMIT
    assert _run("git", "ls-tree", FIRMWARE_COMMIT, "hdl").split()[2] == HDL_COMMIT

    for field, (relative, digest) in HDL_FILES.items():
        assert _sha256_bytes(_git_blob(HDL_COMMIT, relative, HDL)) == digest, field
    for field, (relative, digest) in FIRMWARE_FILES.items():
        assert _sha256_bytes(_git_blob(FIRMWARE_COMMIT, relative)) == digest, field


def test_health_abi11_functional_summary_is_exact() -> None:
    assert _sha256(FUNCTIONAL) == SUMMARY_SHA256[
        "health_abi11_functional_summary_sha256"
    ]
    summary = _summary(FUNCTIONAL)
    assert summary["firmware_source_commit"] == FIRMWARE_COMMIT
    assert summary["hdl_source_commit"] == HDL_COMMIT
    assert summary["ingress_source_commit"] == INGRESS_COMMIT
    assert summary["health_counter_saturation"] == "PASS"
    assert summary["health_detector_episodes"] == "2"
    assert summary["health_sticky_causes"] == "12"
    assert summary["sample_cdc_depth4"] == "PASS"
    assert summary["sample_cdc_depth128"] == "PASS"
    assert summary["sample_cdc_gap_recovery"] == "PASS"
    assert summary["axi_structure"] == "PASS"
    assert summary["axi_snapshot_words"] == "26"
    assert summary["axi_integrated_clock_cases"] == "4"
    assert summary["arm_supported_abis"] == "1.0,1.1"
    assert summary["arm_phase_map_words_per_copy"] == "20000"
    assert summary["host_strict_build"] == "PASS"
    assert summary["arm_eabi_cross_build"] == "PASS"
    assert summary["asan_ubsan"] == "PASS"
    assert summary["python_c_oracle_cases"] == "13"
    assert summary["radio_contacted"] == "false"
    assert summary["rx_shell_integrated"] == "false"
    assert summary["frame_alignment_qualified"] == "false"
    assert summary["verdict"] == "PASS"


def test_health_abi11_physical_summaries_are_exact() -> None:
    assert _sha256(SAMPLE_CDC_OOC) == SUMMARY_SHA256["sample_cdc_ooc_summary_sha256"]
    assert _sha256(IQ_MAP_OOC) == SUMMARY_SHA256[
        "health_abi11_iq_map_ooc_summary_sha256"
    ]
    assert _sha256(AXI_OOC) == SUMMARY_SHA256["health_abi11_axi_ooc_summary_sha256"]

    sample = _summary(SAMPLE_CDC_OOC)
    assert sample["timing_scope"] == "post_opt_unplaced"
    assert float(sample["setup_wns_ns"]) >= 0.0
    assert float(sample["hold_whs_ns"]) >= 0.0
    assert sample["critical_cdc_paths"] == "0"
    assert sample["gray_bus_skew_constraints"] == "3"
    assert sample["fifo_depth"] == "128"

    iq_map = _summary(IQ_MAP_OOC)
    assert iq_map["timing_scope"] == "post_opt_unplaced"
    assert float(iq_map["setup_wns_ns"]) >= 0.0
    assert float(iq_map["hold_whs_ns"]) >= 0.0
    assert iq_map["methodology_violations"] == "0"
    assert iq_map["bram_tiles"] == "38.5"

    axi = _summary(AXI_OOC)
    assert axi["timing_scope"] == "post_route"
    assert float(axi["setup_wns_ns"]) >= 0.0
    assert float(axi["hold_whs_ns"]) >= 0.0
    assert axi["critical_cdc_rows"] == "0"
    assert axi["bus_skew_met"] == "3"
    assert axi["bus_skew_violated"] == "0"
    assert axi["snapshot_source_bits"] == "790"
    assert axi["snapshot_synchronizer_bits"] == "1580"
    assert axi["snapshot_destination_bits"] == "790"


def test_health_abi11_guard_and_manifest_preserve_boundaries() -> None:
    denylist = _git_blob(
        GUARD_COMMIT, ".github/experimental-firmware-gitlinks.txt"
    ).decode()
    assert f"hdl {INGRESS_COMMIT} starlink-pss15-sample-cdc-hdl-v1" in denylist
    assert f"hdl {HDL_COMMIT} starlink-pss15-health-abi11-hdl-v1" in denylist

    manifest = MANIFEST.read_text()
    for boundary in (
        "do_not_merge: true",
        "do_not_release: true",
        "persistent_flash_eligible: false",
        "build_eligible: false",
        "radio_eligible: false",
        "radio_contacted_by_this_revision: false",
        "rtl_rx_shell_connected: false",
        "firmware_image_built: false",
        "hardware_qualified: false",
        "frame_alignment_qualified: false",
        "stage_30_authorized: false",
        "stage_60_authorized: false",
    ):
        assert boundary in manifest
    assert f"firmware_source_commit: {FIRMWARE_COMMIT}" in manifest
    assert f"firmware_source_ref: refs/tags/{FIRMWARE_TAG}" in manifest
    assert f"submodule_hdl: {HDL_COMMIT}" in manifest
    assert f"submodule_hdl_ref: refs/tags/{HDL_TAG}" in manifest
    assert f"ingress_hdl_source_commit: {INGRESS_COMMIT}" in manifest
    assert "firmware_main_gitlink_guard_pr: https://github.com/misko/plutosdr-fw/pull/96" in manifest
    assert f"firmware_main_gitlink_guard_merge_commit: {GUARD_COMMIT}" in manifest
    assert "firmware_main_gitlink_guard_changed_only_denylist: true" in manifest
    assert "qualification_radio_serial: 104000bac4950008230026001b440a003a" in manifest
    assert "qualification_utility_changed: false" in manifest

    for field, (_, digest) in HDL_FILES.items():
        assert f"{field}: {digest}" in manifest
    for field, (_, digest) in FIRMWARE_FILES.items():
        assert f"{field}: {digest}" in manifest
    for field, digest in SUMMARY_SHA256.items():
        assert f"{field}: {digest}" in manifest

    current = {
        "health_abi11_report_sha256": REPORT,
        "health_abi11_evidence_test_sha256": Path(__file__),
        "starlink_plan_sha256": PLAN,
    }
    for field, path in current.items():
        assert f"{field}: {_sha256(path)}" in manifest

    report = REPORT.read_text()
    plan = PLAN.read_text()
    assert FIRMWARE_COMMIT in report and FIRMWARE_TAG in report
    assert HDL_COMMIT in report and HDL_TAG in report
    assert GUARD_COMMIT in report
    assert "changed only the append-only experimental-gitlink" in report
    assert "No experimental HDL" in report
    assert FIRMWARE_COMMIT in plan and GUARD_COMMIT in plan
