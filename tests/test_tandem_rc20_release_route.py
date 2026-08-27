"""Offline oracles for the protected tandem AGC v8 RC20 quality-policy route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC19_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc19-source.yaml"
RC20_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc20-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
OFFLINE = ROOT / "scripts" / "check_tandem_release_offline.sh"
PACKAGE = ROOT / "scripts" / "ci" / "package_main_firmware.sh"
EVIDENCE = ROOT / "scripts" / "tandem_release_evidence.py"
QUALITY = ROOT / "tests" / "radio_hardware" / "tandem_quality.py"
TONE_QUALITY = ROOT / "tests" / "radio_hardware" / "tone_quality.py"
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


def test_rc20_reuses_the_exact_rc19_and_final_external_source_graph() -> None:
    assert (
        _manifest_values(RC20_MANIFEST)
        == _manifest_values(RC19_MANIFEST)
        == _manifest_values(FINAL_MANIFEST)
    )


def test_rc20_owner_route_maps_branch_manifest_package_and_version() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc20"
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc20-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc20'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc20'") == 1
    assert "Require the exact protected RC20 reproduction identity" in workflow
    assert "Require the exact protected RC19 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc19"
    )


def test_rc20_is_in_every_offline_and_protected_package_gate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    assert "tests/test_tandem_rc20_release_route.py" in offline
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc20-source.yaml"
        in offline
    )
    assert "tandem-agc-v8-rc20-source.yaml:*" in package
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc20" in package


def test_rc20_quality_policy_is_narrow_fixed_and_fail_closed() -> None:
    source = QUALITY.read_text(encoding="utf-8")
    assert "NATIVE_FAST_MAX_TONE_DBFS = -2.0" in source
    assert "if mode == MODE_NATIVE_FAST:" in source
    assert "thresholds=tone_quality_thresholds_for_mode(options, mode)" in source
    assert "thresholds=options.thresholds" in source
    assert "must remain exactly -2.0 dBFS" in source
    tone_source = TONE_QUALITY.read_text(encoding="utf-8")
    assert (
        "clipping_fraction[channel] > thresholds.max_clipping_fraction" in tone_source
    )


def test_rc20_evidence_identity_is_immutable_and_docs_name_rc22_active() -> None:
    sources = tuple(
        path.read_text(encoding="utf-8") for path in (RELEASING, NOTES, PLAN, KALMAN)
    )
    for source in sources:
        assert "RC20" in source
        assert "RC19" in source
        assert "-2.0 dBFS" in source
    assert "The active candidate is RC26" in sources[0]
    assert "RC20 is immutable" in sources[3]


def test_rc20_keeps_single_owner_optional_github_attestation_policy() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN.read_text(encoding="utf-8")
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC22 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
