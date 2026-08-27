"""Offline oracles for the protected tandem AGC v8 RC28 release route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC27_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc27-source.yaml"
RC28_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc28-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
OFFLINE = ROOT / "scripts" / "check_tandem_release_offline.sh"
PACKAGE = ROOT / "scripts" / "ci" / "package_main_firmware.sh"
EVIDENCE = ROOT / "scripts" / "tandem_release_evidence.py"
QUALITY = ROOT / "tests" / "radio_hardware" / "tandem_quality.py"
RELEASE_CLI = ROOT / "tests" / "radio_hardware" / "release_cli.py"
TONE_QUALITY = ROOT / "tests" / "radio_hardware" / "tone_quality.py"
RELEASE_CLI_ORACLES = (
    ROOT / "tests" / "radio_hardware" / "test_release_cli_oracles.py"
)
RELEASING = ROOT / "RELEASING.md"
NOTES = ROOT / "RELEASE_NOTES.md"
PLAN = ROOT / "tandem_AGC_fw_plan.md"
KALMAN = ROOT / "KALMAN_GITHUB_RUNNER.md"


def _manifest_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def test_rc28_reuses_the_exact_rc27_and_final_external_source_graph() -> None:
    assert (
        _manifest_values(RC28_MANIFEST)
        == _manifest_values(RC27_MANIFEST)
        == _manifest_values(FINAL_MANIFEST)
    )


def test_rc28_owner_route_maps_branch_manifest_package_and_version() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc28"
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc28-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc28'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc28'") == 1
    assert "Require the exact protected RC28 reproduction identity" in workflow
    assert "Require the exact protected RC27 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc27"
    )


def test_rc28_is_in_every_offline_and_protected_package_gate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    assert "tests/test_tandem_rc28_release_route.py" in offline
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc28-source.yaml"
        in offline
    )
    assert "tandem-agc-v8-rc28-source.yaml:*" in package
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc28" in package


def test_rc28_uses_sixteen_buffers_without_weakening_event_proof() -> None:
    quality = QUALITY.read_text(encoding="utf-8")
    release_cli = RELEASE_CLI.read_text(encoding="utf-8")
    tone_quality = TONE_QUALITY.read_text(encoding="utf-8")
    release_cli_oracles = RELEASE_CLI_ORACLES.read_text(encoding="utf-8")
    assert "_STEADY_MATRIX_KERNEL_BUFFERS = 16" in release_cli
    assert "kernel_buffers=_STEADY_MATRIX_KERNEL_BUFFERS" in release_cli
    assert "full_base.kernel_buffers == 16" in release_cli_oracles
    assert '"gap_accounted_unproven"' in quality
    assert "hidden transition" in quality
    assert "min_tone_snr_db: float = 10.0" in tone_quality


def test_rc28_docs_preserve_truthful_result_while_rc31_is_active() -> None:
    notes = NOTES.read_text(encoding="utf-8")
    assert "33072902542" in notes
    assert "all 44 authorizing steady matrices" in notes
    assert "1,024,000-S/s" in notes
    assert "RC28" in notes and "not hardware-qualified" in notes
    for source in (RELEASING, PLAN, KALMAN):
        text = source.read_text(encoding="utf-8")
        assert "The active candidate is RC32" in text or "forward-only RC32" in text


def test_rc28_route_remains_reproducible_while_rc31_is_active() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN.read_text(encoding="utf-8")
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc32" in evidence
    assert "refs/tags/tandem-agc-v8-rc32-source/firmware-v1" in evidence
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC29 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
