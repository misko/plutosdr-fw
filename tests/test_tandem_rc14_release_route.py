"""Offline oracles for the protected tandem AGC v8 RC14 utility-owned route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC13_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc13-source.yaml"
RC14_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc14-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
OFFLINE = ROOT / "scripts" / "check_tandem_release_offline.sh"
PACKAGE = ROOT / "scripts" / "ci" / "package_main_firmware.sh"
EVIDENCE = ROOT / "scripts" / "tandem_release_evidence.py"
DEVICE_PLAN = ROOT / "scripts" / "tandem_release_device_plan.py"
DEPLOY_WRAPPER = ROOT / "scripts" / "deploy_tandem_agc_ram_hardware.sh"
UTILITY_BINDING = ROOT / "tests" / "radio_hardware" / "pluto_plus_candidate.py"
RELEASE_RUNNER = ROOT / "tests" / "radio_hardware" / "release_cli.py"
RELEASING = ROOT / "RELEASING.md"
RELEASE_NOTES = ROOT / "RELEASE_NOTES.md"
RELEASE_PLAN = ROOT / "tandem_AGC_fw_plan.md"
KALMAN = ROOT / "KALMAN_GITHUB_RUNNER.md"


def _manifest_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def test_rc14_reuses_the_exact_rc13_and_final_external_source_graph() -> None:
    rc13 = _manifest_values(RC13_MANIFEST)
    rc14 = _manifest_values(RC14_MANIFEST)
    final = _manifest_values(FINAL_MANIFEST)

    assert rc14 == rc13 == final
    assert rc14["release_state"] == "candidate"
    assert "release_tag" not in rc14


def test_rc14_reproduction_route_remains_exact() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc14"

    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc14-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc14'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc14'") == 1
    assert "Require the exact protected RC14 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index(
        "refs/heads/codex/firmware-tandem-agc-v8-rc13"
    )


def test_rc14_is_in_every_offline_and_protected_package_gate() -> None:
    offline = OFFLINE.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")

    assert "tests/test_tandem_rc14_release_route.py" in offline
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc14-source.yaml"
        in offline
    )
    assert "tests/test_tandem_release_device_plan.py" in offline
    assert "tandem-agc-v8-rc14-source.yaml:*" in package
    assert "v0.41-plutoplus-spf-tandem-agc-v8-rc14" in package


def test_rc14_preserves_the_original_utility_identity() -> None:
    expected_commit = "9ef137768d59925acf21d5cd3ff71d1cb523dba7"
    wrapper = DEPLOY_WRAPPER.read_text(encoding="utf-8")
    producer = DEVICE_PLAN.read_text(encoding="utf-8")
    binding = UTILITY_BINDING.read_text(encoding="utf-8")

    assert expected_commit in RC14_MANIFEST.read_text(encoding="utf-8")
    assert expected_commit not in wrapper
    assert expected_commit not in binding
    assert "PLUTO_PLUS_UTILS_SOURCE_COMMIT" in producer
    assert "verify_artifact_index_semantics" in producer
    assert "misko/pluto-plus-utils" in binding
    assert "pluto-plus-utils.release-candidate-plan.v1" in binding
    assert "pluto-plus-utils.release-usb-inventory.v1" in binding
    assert "pluto-plus-utils.release-candidate-operation-plan.v1" in binding
    assert "pluto-plus-utils.release-candidate-ram-receipt.v1" in binding
    assert 'pluto firmware candidate-ram "$@"' in wrapper
    assert "fully clean" in wrapper


def test_rc14_active_harness_uses_utility_adapter_not_retired_deployer() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    runner = RELEASE_RUNNER.read_text(encoding="utf-8")
    required = (
        "scripts/tandem_release_device_plan.py",
        "tests/radio_hardware/pluto_plus_candidate.py",
    )
    for source in (evidence, runner):
        for path in required:
            assert path in source
        assert '"tests/radio_hardware/tandem_ram_deploy.py"' not in source
    assert "validate_release_candidate_receipt" in evidence
    assert "validate_release_candidate_receipt" in runner


def test_rc14_docs_preserve_the_indexed_build_and_pretransition_failure() -> None:
    sources = tuple(
        path.read_text(encoding="utf-8")
        for path in (RELEASING, RELEASE_NOTES, RELEASE_PLAN, KALMAN)
    )
    for source in sources:
        assert "RC14" in source
        assert "pluto-plus-utils" in source
    assert "9ef137768d59925acf21d5cd3ff71d1cb523dba7" in sources[1]
    assert "The active candidate is RC24" in sources[0]
    assert "refs/tags/tandem-agc-v8-rc14-source/firmware-v1" in sources[1]
    assert "RC13" in sources[1]
    assert "3361acb3446b517854ca1cfc144d28c4dd853743" in sources[1]


def test_rc14_keeps_single_owner_optional_github_attestation_policy() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = KALMAN.read_text(encoding="utf-8")

    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow
    assert "The RC22 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
