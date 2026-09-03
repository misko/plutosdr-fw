from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests/starlink-pss15-arm-acquisition-dnm-v1-source.yaml"
REPORT = ROOT / "reports/STARLINK_PSS15_ARM_ACQUISITION_V1.md"
SUMMARY = ROOT / "reports/starlink-pss15-arm-acquisition-v1-offline-summary.txt"
PLAN = ROOT / "STARLINK_PSS_15_30_60_PLAN.md"

SOURCE_COMMIT = "b26ed7a685d9d994b89fa9159af751825835270b"
SOURCE_TAG = "starlink-rx-only-dnm-v1-source/firmware-pss15-arm-acquisition-v1"
SUMMARY_SHA256 = "7ce4cb62daa63503b8a34270a330344036f3662da5be1cb4ff074eee02b87c6d"

SOURCE_FILES = {
    "arm_acquisition_runner_sha256": "run_starlink_pss15_arm_acquisition.sh",
    "arm_acquisition_differential_test_sha256": (
        "tests/test_starlink_pss_acquisition_c.py"
    ),
    "arm_acquisition_makefile_sha256": "tools/starlink_pssctl/Makefile",
    "arm_acquisition_readme_sha256": "tools/starlink_pssctl/README.md",
    "arm_acquisition_library_sha256": (
        "tools/starlink_pssctl/starlink_pss_acquisition.c"
    ),
    "arm_acquisition_header_sha256": (
        "tools/starlink_pssctl/starlink_pss_acquisition.h"
    ),
    "arm_acquisition_selftest_sha256": (
        "tools/starlink_pssctl/test_starlink_pss_acquisition.c"
    ),
}

SOURCE_SHA256 = {
    "arm_acquisition_runner_sha256": (
        "1ca766e11fa6ffc6e0752bc99ddff7bb04384bf143963757d784a80fa120b1e4"
    ),
    "arm_acquisition_differential_test_sha256": (
        "e1cbd226e5cc6b31cb0d22982c7325870d7354db089c6978657979e8e488c429"
    ),
    "arm_acquisition_makefile_sha256": (
        "313a8fbba99ee6d0593568f54d18c27dc6be88a93388f0b94ad30a8496478e87"
    ),
    "arm_acquisition_readme_sha256": (
        "8d9bd03ab06c304d5de8d1365bb552db7d7b6c04dff60bd363291cca397058c1"
    ),
    "arm_acquisition_library_sha256": (
        "30ce4596f184e32aeddb1ed915450045a725226596b55049ea9f79fb7fed3937"
    ),
    "arm_acquisition_header_sha256": (
        "0dbf604cc5dbe4fe5ed8b5ae3e822d1e8d4de7d873607265d65e4f7b2bae48b9"
    ),
    "arm_acquisition_selftest_sha256": (
        "b70fd9d0b51cadb8d2dddfd342f05642b28a47dab82b81116a007877d79478bd"
    ),
}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _source_file(relative: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{SOURCE_COMMIT}:{relative}"],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def _summary() -> dict[str, str]:
    return dict(line.split("=", 1) for line in SUMMARY.read_text().splitlines())


def test_arm_acquisition_source_tag_and_blobs_are_frozen() -> None:
    peeled = subprocess.run(
        ["git", "rev-parse", f"{SOURCE_TAG}^{{}}"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    assert peeled == SOURCE_COMMIT
    for field, relative in SOURCE_FILES.items():
        assert _sha256_bytes(_source_file(relative)) == SOURCE_SHA256[field]


def test_arm_acquisition_offline_summary_is_exact_and_narrow() -> None:
    assert _sha256(SUMMARY) == SUMMARY_SHA256
    assert _summary() == {
        "source_commit": SOURCE_COMMIT,
        "source_tag": SOURCE_TAG,
        "host_compiler": "Ubuntu-GCC-15.2.0",
        "arm_compiler": "Linaro-GCC-7.3.1",
        "python_version": "3.14.4",
        "uv_version": "0.12.5",
        "strict_warning_build": "PASS",
        "arm_eabi_cross_build": "PASS",
        "asan_ubsan": "PASS",
        "phase_map_words_per_copy": "20000",
        "successful_complete_map_copies": "2",
        "copy_failure_retains_bank": "true",
        "hardware_fault_epoch_continuity": "true",
        "window_maps": "3",
        "window_storage_bytes": "120000",
        "scratch_storage_bytes": "160000",
        "incoming_copy_storage_bytes": "40000",
        "maximum_working_storage_bytes": "320000",
        "drift_hypotheses": "7",
        "drift_bins_per_tile": "-12,-8,-4,0,4,8,12",
        "drift_ppm": "-9.375,-6.25,-3.125,0,3.125,6.25,9.375",
        "python_c_oracle_cases": "13",
        "lock_state_path": "ACQUIRE,CONFIRM,LOCK,TRACK,HOLDOVER,ACQUIRE",
        "radio_contacted": "false",
        "firmware_image_built": "false",
        "mmio_shell_integrated": "false",
        "frame_alignment_qualified": "false",
        "verdict": "PASS",
    }


def test_arm_acquisition_source_contract_is_bounded_and_fail_closed() -> None:
    header = _source_file(SOURCE_FILES["arm_acquisition_header_sha256"]).decode()
    library = _source_file(SOURCE_FILES["arm_acquisition_library_sha256"]).decode()
    selftest = _source_file(SOURCE_FILES["arm_acquisition_selftest_sha256"]).decode()
    differential = _source_file(
        SOURCE_FILES["arm_acquisition_differential_test_sha256"]
    ).decode()
    makefile = _source_file(SOURCE_FILES["arm_acquisition_makefile_sha256"]).decode()
    runner = _source_file(SOURCE_FILES["arm_acquisition_runner_sha256"]).decode()

    assert "#define PSS_MAP_PHASE_BINS 20000U" in header
    assert "#define PSS_ACQUISITION_WINDOW_MAPS 3U" in header
    assert "#define PSS_ACQUISITION_DRIFT_HYPOTHESES 7U" in header
    assert "pss_map_copies_contiguous" in header
    assert "-12, -8, -4, 0, 4, 8, 12" in library
    assert "fault_counters_unchanged" in library
    assert "drift_count > PSS_ACQUISITION_DRIFT_HYPOTHESES" in library
    assert "phase_bins > INT32_MAX" in library
    assert library.index("fault_counters_unchanged(snapshot, &after)") < library.index(
        "map_write32(io, PSS_MAP_REG_RELEASE"
    )
    assert "failed map copy released source ownership" in selftest
    assert "a changed fault epoch was accepted as continuous" in selftest
    assert "state_path=" in selftest
    assert differential.count("@pytest.mark.parametrize") == 2
    assert "search_phase_map_drift" in differential
    assert "arm-linux-gnueabihf-gcc" in makefile
    assert "-fsanitize=address,undefined" in makefile
    assert "radio_contacted=false" in runner
    for forbidden in ("iio", "ssh", "dfu", "/dev/mem"):
        assert forbidden not in runner.lower()


def test_arm_acquisition_manifest_binds_evidence_and_preserves_boundaries() -> None:
    manifest = MANIFEST.read_text()
    report = REPORT.read_text()
    plan = PLAN.read_text()

    assert "do_not_merge: true" in manifest
    assert "do_not_release: true" in manifest
    assert "persistent_flash_eligible: false" in manifest
    assert "build_eligible: false" in manifest
    assert "radio_eligible: false" in manifest
    assert "radio_contacted_by_this_revision: false" in manifest
    assert "qualification_radio_serial: 104000bac4950008230026001b440a003a" in manifest
    assert f"firmware_source_commit: {SOURCE_COMMIT}" in manifest
    assert f"firmware_source_ref: refs/tags/{SOURCE_TAG}" in manifest
    assert "submodule_sources_changed: false" in manifest
    assert "firmware_main_gitlink_guard_required: false" in manifest
    assert "arm_candidate_extraction_implemented: true" in manifest
    assert "arm_lock_state_machine_implemented: true" in manifest
    assert "arm_target_executable_linked: false" in manifest
    assert "rtl_rx_shell_connected: false" in manifest
    assert "hardware_qualified: false" in manifest
    assert "frame_alignment_qualified: false" in manifest
    assert "stage_30_authorized: false" in manifest
    assert "stage_60_authorized: false" in manifest
    for field, digest in SOURCE_SHA256.items():
        assert f"{field}: {digest}" in manifest
    current_files = {
        "arm_acquisition_summary_sha256": (
            "reports/starlink-pss15-arm-acquisition-v1-offline-summary.txt"
        ),
        "arm_acquisition_report_sha256": (
            "reports/STARLINK_PSS15_ARM_ACQUISITION_V1.md"
        ),
        "arm_acquisition_evidence_test_sha256": (
            "tests/test_starlink_arm_acquisition_evidence.py"
        ),
        "starlink_plan_sha256": "STARLINK_PSS_15_30_60_PLAN.md",
    }
    for field, relative in current_files.items():
        assert f"{field}: {_sha256(ROOT / relative)}" in manifest
    assert SOURCE_COMMIT in report
    assert SOURCE_TAG in report
    assert SUMMARY_SHA256 in report
    assert "deliberately not" in report
    assert "linked into the existing tracker controller" in report
    assert SOURCE_COMMIT in plan
    assert SOURCE_TAG in plan
