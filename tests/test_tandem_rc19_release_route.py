"""Offline oracles for the protected tandem AGC v8 RC19 resume-fix route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC18_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc18-source.yaml"
RC19_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc19-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
OFFLINE = ROOT / "scripts" / "check_tandem_release_offline.sh"
PACKAGE = ROOT / "scripts" / "ci" / "package_main_firmware.sh"
EVIDENCE = ROOT / "scripts" / "tandem_release_evidence.py"
RELEASE_CLI = ROOT / "tests" / "radio_hardware" / "release_cli.py"
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


def test_rc19_reuses_the_exact_rc18_and_final_external_source_graph() -> None:
    assert (
        _manifest_values(RC19_MANIFEST)
        == _manifest_values(RC18_MANIFEST)
        == _manifest_values(FINAL_MANIFEST)
    )


def test_rc19_owner_route_maps_branch_manifest_package_and_version() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc19"
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc19-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc19'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc19'") == 1
    assert "Require the exact protected RC19 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc18"
    )


def test_rc19_is_in_every_offline_and_protected_package_gate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    assert "tests/test_tandem_rc19_release_route.py" in offline
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc19-source.yaml"
        in offline
    )
    assert "tandem-agc-v8-rc19-source.yaml:*" in package
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc19" in package


def test_rc19_accepts_canonical_checkpoint_key_order_with_exact_phase_specs() -> None:
    source = RELEASE_CLI.read_text(encoding="utf-8")
    assert "set(checkpoint_phases) != set(expected_keys)" in source
    assert 'checkpoint_phases[spec.key].get("spec") != spec.to_dict()' in source


def test_rc19_history_is_retained_while_rc20_is_active() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    sources = tuple(
        path.read_text(encoding="utf-8") for path in (RELEASING, NOTES, PLAN, KALMAN)
    )
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc26" in evidence
    assert "refs/tags/tandem-agc-v8-rc26-source/firmware-v1" in evidence
    for source in sources:
        assert "RC19" in source
        assert "RC18" in source
        assert "checkpoint" in source
    assert "The active candidate is RC26" in sources[0]


def test_rc19_keeps_single_owner_optional_github_attestation_policy() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN.read_text(encoding="utf-8")
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC22 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
