"""Offline oracles for the protected tandem AGC v8 RC10 build route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC8_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc8-source.yaml"
RC9_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc9-source.yaml"
RC10_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc10-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
MAIN_WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
PR_WORKFLOW = ROOT / ".github" / "workflows" / "firmware.yml"
OFFLINE_CHECK = ROOT / "scripts" / "check_tandem_release_offline.sh"
RELEASING = ROOT / "RELEASING.md"
RELEASE_PLAN = ROOT / "tandem_AGC_fw_plan.md"
KALMAN_RUNNER = ROOT / "KALMAN_GITHUB_RUNNER.md"
TANDEM_CORE = ROOT / "hdl-tandem" / "tandem_agc_core.v"


def _manifest_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def test_rc10_reuses_only_the_reviewed_rc9_external_source_graph() -> None:
    rc8 = _manifest_values(RC8_MANIFEST)
    rc9 = _manifest_values(RC9_MANIFEST)
    rc10 = _manifest_values(RC10_MANIFEST)
    final = _manifest_values(FINAL_MANIFEST)

    assert rc10 == rc9 == rc8 == final
    assert rc10["schema"] == "plutosdr-fw.source-manifest"
    assert rc10["schema_version"] == "1"
    assert rc10["release_state"] == "candidate"
    assert "release_tag" not in rc10


def test_rc10_owner_only_route_maps_ref_manifest_and_package_together() -> None:
    workflow = MAIN_WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc10"

    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc10-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc10'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc10'") == 1
    assert "Require the exact protected RC10 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index("tandem-agc-v8-rc9-source.yaml")


def test_rc10_source_graph_is_a_required_pr_check() -> None:
    workflow = PR_WORKFLOW.read_text(encoding="utf-8")
    checker = OFFLINE_CHECK.read_text(encoding="utf-8")

    assert "./scripts/check_tandem_release_offline.sh source-graph" in workflow
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc10-source.yaml"
    ) in checker


def test_rc10_keeps_the_two_reviewed_slice_relief_mappings() -> None:
    core = TANDEM_CORE.read_text(encoding="utf-8")

    assert '(* use_dsp = "yes" *) reg [19:0] pwr_div;' in core
    assert '(* use_dsp = "yes" *) reg [31:0] evt_seq;' in core
    assert core.count('(* use_dsp = "yes" *)') == 2


def test_rc10_bundle_upload_does_not_require_github_attestation() -> None:
    workflow = MAIN_WORKFLOW.read_text(encoding="utf-8")

    assert "Upload deployment bundle and verification sidecars" in workflow
    assert "${{ steps.build.outputs.bundle_path }}" in workflow
    assert "${{ steps.build.outputs.bundle_path }}.sha256" in workflow
    assert "if-no-files-found: error" in workflow
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow


def test_kalman_handoff_preserves_the_rc10_build_and_transition_history() -> None:
    runner = KALMAN_RUNNER.read_text(encoding="utf-8")

    assert "Trusted run `32964460396`" in runner
    assert "RC10 has zero candidate deployments" in runner
    assert "before any `dfu-util -D`" in runner
    assert "persistent RC1" in runner
    assert "GitHub attestation is not required for this handoff." in runner
    assert "plutosdr-fw.github-attestation-not-performed.v1" in runner
    assert 'sidecars=("$artifact_dir"/*.tar.gz.sha256)' in runner
    assert 'sha256sum -c "$(basename "$sidecar")"' in runner
    assert "sha256sum -c SHA256SUMS" in runner
    assert "gh attestation verify" not in runner


def test_release_docs_preserve_rc10_lock_and_bind_full_final_campaign() -> None:
    releasing = RELEASING.read_text(encoding="utf-8")
    plan = RELEASE_PLAN.read_text(encoding="utf-8")
    candidate_lock = "refs/tags/tandem-agc-v8-rc10-source/firmware-v1"
    final_lock = "refs/tags/tandem-agc-v8-source/firmware-v1"

    assert "The active candidate is RC21" in releasing
    assert candidate_lock in releasing
    assert final_lock in releasing
    assert "repeat the full four-radio campaign" in releasing
    assert 'gh attestation verify "$release_work"' not in releasing

    assert candidate_lock in plan
    assert final_lock in plan
    assert "exact_main_commit='<40-character-exact-main-commit>'" in plan
    assert 'git tag tandem-agc-v8-source/firmware-v1 "$exact_main_commit"' in plan
    assert "The v8 policy always\nselects `full-campaign`." in plan
