"""Offline oracles for the protected tandem AGC v8 RC17 ABI-contract route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC16_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc16-source.yaml"
RC17_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc17-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
OFFLINE = ROOT / "scripts" / "check_tandem_release_offline.sh"
PACKAGE = ROOT / "scripts" / "ci" / "package_main_firmware.sh"
EVIDENCE = ROOT / "scripts" / "tandem_release_evidence.py"
DEVICE_PLAN = ROOT / "scripts" / "tandem_release_device_plan.py"
BINDING = ROOT / "tests" / "radio_hardware" / "pluto_plus_candidate.py"
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


def test_rc17_reuses_the_exact_rc16_and_final_external_source_graph() -> None:
    assert (
        _manifest_values(RC17_MANIFEST)
        == _manifest_values(RC16_MANIFEST)
        == _manifest_values(FINAL_MANIFEST)
    )


def test_rc17_owner_route_maps_branch_manifest_package_and_version() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc17"
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc17-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc17'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc17'") == 1
    assert "Require the exact protected RC17 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc16"
    )


def test_rc17_is_in_every_offline_and_protected_package_gate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    assert "tests/test_tandem_rc17_release_route.py" in offline
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc17-source.yaml"
        in offline
    )
    assert "tandem-agc-v8-rc17-source.yaml:*" in package
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc17" in package


def test_rc17_separates_release_frame_schema_from_live_buffer_abi() -> None:
    plan = DEVICE_PLAN.read_text(encoding="utf-8")
    binding = BINDING.read_text(encoding="utf-8")
    for source in (plan, binding):
        assert "PLUTO_IIO_BUFFER_METADATA_ABI" in source
        assert "frame-metadata-v2" in binding
        assert "frame-metadata-v5" in binding
    assert '"metadata_abi": PLUTO_IIO_BUFFER_METADATA_ABI' in plan


def test_rc17_history_is_retained_while_rc20_is_active() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    sources = tuple(
        path.read_text(encoding="utf-8") for path in (RELEASING, NOTES, PLAN, KALMAN)
    )
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc26" in evidence
    assert "refs/tags/tandem-agc-v8-rc26-source/firmware-v1" in evidence
    for source in sources:
        assert "RC17" in source
        assert "RC19" in source
        assert "frame-metadata-v5" in source
        assert "frame-metadata-v2" in source
    assert "The active candidate is RC26" in sources[0]


def test_rc17_keeps_single_owner_optional_github_attestation_policy() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN.read_text(encoding="utf-8")
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC22 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
