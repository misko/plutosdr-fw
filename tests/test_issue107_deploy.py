from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/issue107/deploy.py"
SPEC = importlib.util.spec_from_file_location("issue107_deploy", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)


def _private_json(path: Path, document: dict[str, object]) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    path.chmod(0o600)
    return path


def _functional_report(**overrides: object) -> dict[str, object]:
    report: dict[str, object] = {
        "schema": "issue107.functional-capture/v1",
        "radio_serial": "104000b29905000e17000800065934759d",
        "firmware": deploy.CANDIDATE_FIRMWARE,
        "boot_id": "0123456789abcdef0123456789abcdef",
        "image_sha256": "a" * 64,
        "rates_hz": [10_000_000, 15_000_000, 20_000_000],
        "all_rates_passed": True,
        "scantime_protocol_version": 1,
        "counter_continuity_passed": True,
        "utc_hardware_qualified": False,
        "test_evidence_sha256": "b" * 64,
    }
    report.update(overrides)
    return report


def _dual_functional_report(**overrides: object) -> dict[str, object]:
    report: dict[str, object] = {
        "schema": "issue107.dual-rx-functional-capture/v1",
        "radio_serial": "104000b29905000e17000800065934759d",
        "firmware": deploy.CANDIDATE_FIRMWARE,
        "image_sha256": "a" * 64,
        "candidate_manifest_sha256": "c" * 64,
        "capture_evidence_sha256": "d" * 64,
        "boot_id": "0123456789abcdef0123456789abcdef",
        "rate_hz": deploy.DUAL_RX_RATE_HZ,
        "rx_mask": 3,
        "rx_channels": [0, 1],
        "duration_seconds": 300,
        "counter_sample_unit": "shared-complex-sample-time-index",
        "scan_session": 101,
        "scan_generation": 7,
        "counter_session": 101,
        "counter_generation": 7,
        "timing_sample_rate_hz": deploy.DUAL_RX_RATE_HZ,
        "anchor_count": 61,
        "maximum_query_width_ns": 3_000_000,
        "maximum_inclusive_anchor_span_ns": 5_001_000_000,
        "functional_pass": True,
        "all_visits_passed": True,
        "counter_continuity_passed": True,
        "iq_geometry_passed": True,
        "timing_query_pass": True,
        "timing_anchor_coverage_pass": True,
        "utc_accuracy_qualified": False,
        "valid_sample_count": 750_000_000,
        "iq_bytes_received": 6_000_000_000,
        "planned_visits": 2_100,
        "delivered_visits": 2_100,
        "skipped_visits": 0,
        "invalid_visits": 0,
        "cancelled_visits": 0,
        "missing_samples_reported": 0,
    }
    report.update(overrides)
    return report


def test_manifest_rejects_image_hash_mismatch(tmp_path: Path, monkeypatch) -> None:
    image = tmp_path / "candidate.dfu"
    image.write_bytes(b"candidate bytes")
    manifest = _private_json(
        tmp_path / "manifest.json",
        {
            "firmware": deploy.CANDIDATE_FIRMWARE,
            "asset_sha256": "0" * 64,
            "fit_sha256": "1" * 64,
            "fit_size": 3,
            "sources": {"firmware_base": "c" * 40},
        },
    )
    monkeypatch.setattr(deploy, "validate_dfu", lambda _payload: b"fit")

    with pytest.raises(ValueError, match="DFU SHA-256"):
        deploy._manifest(image, manifest)


def test_manifest_requires_new_v054_candidate_tag(tmp_path: Path, monkeypatch) -> None:
    image = tmp_path / "candidate.dfu"
    image.write_bytes(b"candidate bytes")
    manifest = _private_json(
        tmp_path / "manifest.json",
        {
            "firmware": "v0.53-plutoplus-spf-adaptive-scan-v2",
            "asset_sha256": "0" * 64,
            "fit_sha256": "1" * 64,
            "fit_size": 3,
            "sources": {"firmware_base": "c" * 40},
        },
    )

    with pytest.raises(ValueError, match="candidate v0.54"):
        deploy._manifest(image, manifest)


def test_candidate_profiles_use_paired_rev_c_layout_on_both_sides(
    monkeypatch, tmp_path: Path
) -> None:
    image = tmp_path / "candidate.dfu"
    image.write_bytes(b"candidate bytes")
    monkeypatch.setattr(deploy, "validate_dfu", lambda _payload: b"fit body")
    manifest = {
        "firmware": deploy.CANDIDATE_FIRMWARE,
        "firmware_source_commit": "c" * 40,
        "release_url": "https://example.invalid/candidate",
    }

    ram_id, persistent_id = deploy._candidate_profiles(
        manifest, image, image.read_bytes()
    )
    ram = deploy.STANDALONE_FLASH_PROFILES[ram_id]
    persistent = deploy.STANDALONE_FLASH_PROFILES[persistent_id]

    assert ram.source_iio_layout is deploy.SINGLE_RX_TX_CAPABLE_LAYOUT
    assert ram.return_iio_layout is deploy.PAIRED_RX_TX_CAPABLE_LAYOUT
    assert persistent.source_iio_layout is deploy.PAIRED_RX_TX_CAPABLE_LAYOUT
    assert persistent.return_iio_layout is deploy.PAIRED_RX_TX_CAPABLE_LAYOUT
    assert deploy.CURRENT_FIRMWARE == "v0.52-plutoplus-spf-counter-utc-v1-rc1"
    assert ram.allowed_before_firmwares == (deploy.CURRENT_FIRMWARE,)
    assert persistent.allowed_before_firmwares == (deploy.CANDIDATE_FIRMWARE,)


def test_dual_report_requires_exact_manifest_and_pair_sample_accounting(
    tmp_path: Path,
) -> None:
    report_path = _private_json(
        tmp_path / "dual.json", _dual_functional_report()
    )

    report, digest = deploy._load_dual_functional_report(
        report_path,
        serial="104000b29905000e17000800065934759d",
        firmware=deploy.CANDIDATE_FIRMWARE,
        image_sha="a" * 64,
        manifest_sha="c" * 64,
    )

    assert report["valid_sample_count"] == 750_000_000
    assert report["iq_bytes_received"] == 8 * report["valid_sample_count"]
    assert digest == hashlib.sha256(report_path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "changes",
    [
        {"rate_hz": 15_000_000},
        {"rx_mask": 1},
        {"duration_seconds": 30},
        {"candidate_manifest_sha256": "e" * 64},
        {"iq_bytes_received": 12_000_000_000},
        {"counter_session": 102},
        {"counter_sample_unit": "bytes"},
        {"maximum_query_width_ns": -1},
        {"maximum_inclusive_anchor_span_ns": -1},
        {"maximum_query_width_ns": 50_000_001},
    ],
)
def test_dual_report_rejects_unqualified_capture_shape(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    report_path = _private_json(
        tmp_path / "dual.json", _dual_functional_report(**changes)
    )

    with pytest.raises(ValueError, match="paired-RX report"):
        deploy._load_dual_functional_report(
            report_path,
            serial="104000b29905000e17000800065934759d",
            firmware=deploy.CANDIDATE_FIRMWARE,
            image_sha="a" * 64,
            manifest_sha="c" * 64,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"radio_serial": "1040007c4a94000211000b009186843ef2"},
        {"image_sha256": "c" * 64},
    ],
)
def test_functional_report_rejects_wrong_radio_or_image(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    report_path = _private_json(
        tmp_path / "functional.json", _functional_report(**changes)
    )

    with pytest.raises(ValueError, match="exact-radio"):
        deploy._load_functional_report(
            report_path,
            serial="104000b29905000e17000800065934759d",
            firmware=deploy.CANDIDATE_FIRMWARE,
            image_sha="a" * 64,
        )


def test_functional_report_rejects_live_boot_id_mismatch() -> None:
    report = _functional_report()

    with pytest.raises(ValueError, match="boot UUID"):
        deploy._require_report_boot_id(report, "fedcba9876543210fedcba9876543210")


def test_read_boot_id_ignores_ssh_pty_banner_and_prompt(tmp_path: Path, monkeypatch) -> None:
    expected = "d27cdcb9-f0a9-4c90-8295-59c6fc012812"

    class StubTransport:
        def __init__(self, **kwargs: object) -> None:
            pass

        def run(self, command: str, *, timeout_s: int) -> str:
            assert "ISSUE107_BOOT_ID=" in command
            assert "/proc/sys/kernel/random/boot_id" in command
            assert timeout_s == 15
            return (
                "** WARNING: SSH PTY banner **\n"
                "root@192.168.1.18's password:\n"
                "ISSUE107_BOOT_ID=" + expected + "\n"
            )

    monkeypatch.setattr(deploy, "BoundSshBootstrapTransport", StubTransport)
    monkeypatch.setattr(deploy, "_password", lambda: "unused-test-secret")
    assert deploy._read_boot_id(host="192.168.1.18", known_hosts=tmp_path / "known_hosts") == (
        expected.replace("-", "")
    )


@pytest.mark.parametrize(
    "transcript",
    [
        "SSH warning only\n01234567-89ab-cdef-0123-456789abcdef\n",
        (
            "ISSUE107_BOOT_ID=01234567-89ab-cdef-0123-456789abcdef\n"
            "ISSUE107_BOOT_ID=01234567-89ab-cdef-0123-456789abcdef\n"
        ),
        "ISSUE107_BOOT_ID=not-a-uuid\n",
        "ISSUE107_BOOT_ID=01234567-89ab-cdef-0123-456789abcdeF\n",
    ],
)
def test_marked_boot_id_parser_rejects_missing_duplicate_or_malformed(
    transcript: str,
) -> None:
    with pytest.raises(RuntimeError, match="boot-ID response|boot UUID"):
        deploy._parse_marked_boot_id(transcript)


def test_ssh_flash_plan_requires_controlled_flash_safety(monkeypatch, tmp_path: Path) -> None:
    transport = object()
    observed: dict[str, object] = {}

    def prepare(*args: object, **kwargs: object):
        observed["args"] = args
        observed.update(kwargs)
        return SimpleNamespace(flash_safety=object()), b"canonical FRM"

    monkeypatch.setattr(deploy, "prepare_usb_flash_plan", prepare)
    plan, frm = deploy._prepare_ssh_usb_flash_plan(
        tmp_path / "candidate.dfu",
        tmp_path / "usb-device",
        mutation_profile_id="counter-utc-test",
        transport=transport,
    )
    assert plan.flash_safety is not None
    assert frm == b"canonical FRM"
    assert observed["flash_transport"] is transport


def test_ssh_flash_plan_refuses_missing_flash_safety(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        deploy,
        "prepare_usb_flash_plan",
        lambda *args, **kwargs: (SimpleNamespace(flash_safety=None), b"frm"),
    )
    with pytest.raises(RuntimeError, match="controlled flash-safety"):
        deploy._prepare_ssh_usb_flash_plan(
            tmp_path / "candidate.dfu",
            tmp_path / "usb-device",
            mutation_profile_id="counter-utc-test",
            transport=object(),
        )


@pytest.mark.parametrize("receipt_kind", ["missing", "wrong-serial", "wrong-image"])
def test_persistence_requires_matching_successful_ram_receipt(
    tmp_path: Path, receipt_kind: str
) -> None:
    receipt_path = tmp_path / "receipt-123.json"
    if receipt_kind == "missing":
        with pytest.raises(OSError):
            deploy._load_matching_ram_receipt(
                receipt_path,
                serial="104000b29905000e17000800065934759d",
                image_sha="a" * 64,
                firmware=deploy.CANDIDATE_FIRMWARE,
                usb_path="/sys/bus/usb/devices/1-2",
            )
        return
    plan = {
        "serial": "104000b29905000e17000800065934759d",
        "usb_sysfs_path": "/sys/bus/usb/devices/1-2",
        "image_sha256": "a" * 64,
        "expected_firmware": deploy.CANDIDATE_FIRMWARE,
    }
    if receipt_kind == "wrong-serial":
        plan["serial"] = "1040007c4a94000211000b009186843ef2"
    if receipt_kind == "wrong-image":
        plan["image_sha256"] = "d" * 64
    _private_json(
        receipt_path,
        {
            "receipt_id": receipt_path.stem,
            "outcome": "success",
            "phases": sorted(deploy.RAM_PHASES),
            "plan": plan,
            "returned_serial": "104000b29905000e17000800065934759d",
            "returned_firmware": deploy.CANDIDATE_FIRMWARE,
        },
    )

    with pytest.raises(ValueError, match="exact radio and candidate image"):
        deploy._load_matching_ram_receipt(
            receipt_path,
            serial="104000b29905000e17000800065934759d",
            image_sha="a" * 64,
            firmware=deploy.CANDIDATE_FIRMWARE,
            usb_path="/sys/bus/usb/devices/1-2",
        )


def test_attempt_directories_are_unique_and_never_overwrite(tmp_path: Path) -> None:
    first = deploy._new_attempt(tmp_path, "ram")
    second = deploy._new_attempt(tmp_path, "ram")

    assert first != second
    assert first.is_dir() and second.is_dir()
    first_file = first / "plan.json"
    first_file.write_text("original", encoding="utf-8")
    assert deploy._new_attempt(tmp_path, "ram") != first
    assert first_file.read_text(encoding="utf-8") == "original"


def test_default_phase_is_read_only_ram_plan() -> None:
    args = deploy._argument_parser().parse_args(
        [
            "--serial",
            "104000b29905000e17000800065934759d",
            "--host",
            "192.168.1.15",
            "--image",
            "candidate.dfu",
            "--manifest",
            "manifest.json",
            "--evidence-root",
            "/tmp/issue107-test-evidence",
        ]
    )

    assert args.phase == "ram"
    assert args.execute is False
