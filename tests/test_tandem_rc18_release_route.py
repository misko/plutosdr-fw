"""Offline oracles for the protected tandem AGC v8 RC18 runner-binding route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC17_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc17-source.yaml"
RC18_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc18-source.yaml"
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


def test_rc18_reuses_the_exact_rc17_and_final_external_source_graph() -> None:
    assert (
        _manifest_values(RC18_MANIFEST)
        == _manifest_values(RC17_MANIFEST)
        == _manifest_values(FINAL_MANIFEST)
    )


def test_rc18_owner_route_maps_branch_manifest_package_and_version() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc18"
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc18-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc18'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc18'") == 1
    assert "Require the exact protected RC18 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc17"
    )


def test_rc18_is_in_every_offline_and_protected_package_gate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    assert "tests/test_tandem_rc18_release_route.py" in offline
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc18-source.yaml"
        in offline
    )
    assert "tandem-agc-v8-rc18-source.yaml:*" in package
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc18" in package


def test_rc18_fixes_the_distinct_runner_repository_binding() -> None:
    source = RELEASE_CLI.read_text(encoding="utf-8")
    assert (
        'wrapper_repository = PurePosixPath(normalized_wrapper["repository_path"])'
        in source
    )
    assert (
        '!= wrapper_repository / "scripts/run_tandem_agc_release_hardware.sh"' in source
    )


def test_rc18_evidence_identity_is_immutable_and_docs_advance_to_rc20() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    sources = tuple(
        path.read_text(encoding="utf-8") for path in (RELEASING, NOTES, PLAN, KALMAN)
    )
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc32" in evidence
    assert "refs/tags/tandem-agc-v8-rc32-source/firmware-v1" in evidence
    for source in sources:
        assert "RC19" in source
        assert "RC18" in source
        assert "RC17" in source
        assert "host-libiio" in source
    assert any("v0.41-plutoplus-spf-tandem-agc-v8-rc18" in source for source in sources)
    assert "The active candidate is RC32" in sources[0]


def test_rc18_history_keeps_single_owner_optional_github_attestation_policy() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN.read_text(encoding="utf-8")
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC22 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
