from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.starlink_oracle import (
    INSTALLED_CMODEL_SHA256,
    PSS_KERNEL_Q23_INT32LE_SHA256,
    XFFT_BITACC_SCHEMA,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "reports" / "starlink-pss15-xfft-bitacc-v1.json"
REPORT = ROOT / "reports" / "STARLINK_PSS15_XFFT_BITACC_V1.md"
OOC_SUMMARY = ROOT / "reports" / "starlink-pss15-xfft24-ooc-summary.txt"
PLAN = ROOT / "STARLINK_PSS_15_30_60_PLAN.md"
MANIFEST = ROOT / "manifests" / "starlink-pss15-xfft-bitacc-dnm-v1-source.yaml"
EVIDENCE_SHA256 = "2b2f54c37461a653f6c50bf5c68fec769b3b8fb6d300d82859de75949ab01a87"
OOC_SUMMARY_SHA256 = (
    "c96095a10f07739358c38ff3ae55cb0879ce42c0ae019499dc3bf9de69a3f5c1"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_xfft_bitaccurate_evidence_is_frozen_and_passing() -> None:
    document = json.loads(EVIDENCE.read_text())

    assert _sha256(EVIDENCE) == EVIDENCE_SHA256
    assert document["schema"] == XFFT_BITACC_SCHEMA
    assert document["passes"] is True
    assert all(document["gates"].values())
    assert document["cmodel"]["archive_sha256"] == INSTALLED_CMODEL_SHA256
    assert document["cmodel"]["proprietary_files_retained_in_source"] is False
    assert document["configuration"]["data_bits"] == 24
    assert document["configuration"]["phase_factor_bits"] == 16
    assert document["configuration"]["target_throughput_msps"] == 20
    assert (
        document["configuration"]["pss_kernel_q23_int32le_sha256"]
        == PSS_KERNEL_Q23_INT32LE_SHA256
    )
    assert len(document["captures"]) == 3
    assert sum(
        item["finite_width"]["score_count"] for item in document["captures"]
    ) == 12_582_717
    assert sum(
        item["difference"]["score_error_count"] for item in document["captures"]
    ) == 2_881
    for item in document["captures"]:
        assert item["passes"] is True
        assert all(item["gates"].values())
        assert item["difference"]["score_delta_min"] >= -1
        assert item["difference"]["score_delta_max"] <= 1
        assert item["difference"]["phase_cadence_and_classification_equal"]
        assert item["finite_width"]["forward_overflow_blocks"] == 0
        assert item["finite_width"]["inverse_overflow_blocks"] == 0
        assert item["finite_width"]["product_overflow_blocks"] == 0


def test_xfft_ooc_summary_and_human_reports_match_evidence() -> None:
    summary = dict(
        line.split("=", 1)
        for line in OOC_SUMMARY.read_text().splitlines()
        if line
    )
    report = REPORT.read_text()
    plan = PLAN.read_text()

    assert _sha256(OOC_SUMMARY) == OOC_SUMMARY_SHA256
    assert summary["vivado_version"] == "2022.2"
    assert summary["architecture"] == "radix_4_burst"
    assert summary["data_bits"] == "24"
    assert summary["target_throughput_msps"] == "20"
    assert summary["total_luts"] == "2189"
    assert summary["total_ffs"] == "3847"
    assert summary["ramb18e1"] == "11"
    assert summary["dsp48e1"] == "9"
    assert float(summary["setup_wns_ns"]) >= 0
    assert float(summary["hold_whs_ns"]) >= 0
    assert EVIDENCE_SHA256 in report
    assert OOC_SUMMARY_SHA256 in report
    assert XFFT_BITACC_SCHEMA in plan


def test_xfft_source_manifest_is_safe_and_binds_every_input() -> None:
    manifest = MANIFEST.read_text()
    bound_files = {
        "xfft_bitacc_model_sha256": "tests/starlink_oracle/xfft_bitacc.py",
        "xfft_bitacc_unit_test_sha256": (
            "tests/starlink_oracle/test_xfft_bitacc.py"
        ),
        "starlink_oracle_init_sha256": "tests/starlink_oracle/__init__.py",
        "starlink_oracle_readme_sha256": "tests/starlink_oracle/README.md",
        "xfft_study_tool_sha256": "tools/starlink_xfft_bitacc_study.py",
        "xfft_ooc_tcl_sha256": "tools/starlink_xfft24_ooc.tcl",
        "xfft_ooc_runner_sha256": "tools/run_starlink_xfft24_ooc.sh",
        "xfft_replay_evidence_sha256": (
            "reports/starlink-pss15-xfft-bitacc-v1.json"
        ),
        "xfft_ooc_summary_sha256": (
            "reports/starlink-pss15-xfft24-ooc-summary.txt"
        ),
        "xfft_report_sha256": "reports/STARLINK_PSS15_XFFT_BITACC_V1.md",
    }

    assert "do_not_merge: true" in manifest
    assert "persistent_flash_eligible: false" in manifest
    assert "build_eligible: false" in manifest
    assert "radio_eligible: false" in manifest
    assert "radio_contacted_by_this_revision: false" in manifest
    assert "submodule_sources_changed: false" in manifest
    assert "rtl_score_frontend_implemented: false" in manifest
    assert "rtl_fft_implemented: false" in manifest
    assert "hardware_qualified: false" in manifest
    for field, relative in bound_files.items():
        assert f"{field}: {_sha256(ROOT / relative)}" in manifest
    # The living 15/30/60 plan advances after this arithmetic-only checkpoint;
    # its historical digest remains immutable in the superseded manifest.
    assert (
        "starlink_plan_sha256: "
        "b837bbb92b1b6f9239761912b3cef7fbc785e720787428e04061c2011e5754e8"
        in manifest
    )
    assert (
        "xfft_evidence_test_sha256: "
        "72e0555322c57720219847f9652440503f7c7e25075df6fffa112a09860a03dd"
        in manifest
    )
