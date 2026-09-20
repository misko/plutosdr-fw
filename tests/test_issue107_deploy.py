from __future__ import annotations

import importlib.util
import json
from pathlib import Path

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
        "firmware": "v0.52-plutoplus-spf-counter-utc-v1-rc1",
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


def test_manifest_rejects_image_hash_mismatch(tmp_path: Path, monkeypatch) -> None:
    image = tmp_path / "candidate.dfu"
    image.write_bytes(b"candidate bytes")
    manifest = _private_json(
        tmp_path / "manifest.json",
        {
            "firmware": "v0.52-plutoplus-spf-counter-utc-v1-rc1",
            "asset_sha256": "0" * 64,
            "fit_sha256": "1" * 64,
            "fit_size": 3,
            "sources": {"firmware_base": "c" * 40},
        },
    )
    monkeypatch.setattr(deploy, "validate_dfu", lambda _payload: b"fit")

    with pytest.raises(ValueError, match="DFU SHA-256"):
        deploy._manifest(image, manifest)


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
            firmware="v0.52-plutoplus-spf-counter-utc-v1-rc1",
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
                firmware="v0.52-plutoplus-spf-counter-utc-v1-rc1",
                usb_path="/sys/bus/usb/devices/1-2",
            )
        return
    plan = {
        "serial": "104000b29905000e17000800065934759d",
        "usb_sysfs_path": "/sys/bus/usb/devices/1-2",
        "image_sha256": "a" * 64,
        "expected_firmware": "v0.52-plutoplus-spf-counter-utc-v1-rc1",
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
            "returned_firmware": "v0.52-plutoplus-spf-counter-utc-v1-rc1",
        },
    )

    with pytest.raises(ValueError, match="exact radio and candidate image"):
        deploy._load_matching_ram_receipt(
            receipt_path,
            serial="104000b29905000e17000800065934759d",
            image_sha="a" * 64,
            firmware="v0.52-plutoplus-spf-counter-utc-v1-rc1",
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
