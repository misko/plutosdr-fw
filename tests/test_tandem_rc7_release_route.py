"""Offline oracles for the protected tandem AGC v8 RC7 build route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC5_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc5-source.yaml"
RC6_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc6-source.yaml"
RC7_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc7-source.yaml"
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


def test_rc7_reuses_only_the_reviewed_rc6_external_source_graph() -> None:
    rc5 = _manifest_values(RC5_MANIFEST)
    rc6 = _manifest_values(RC6_MANIFEST)
    rc7 = _manifest_values(RC7_MANIFEST)
    final = _manifest_values(FINAL_MANIFEST)

    assert rc7 == rc6 == rc5 == final
    assert rc7["schema"] == "plutosdr-fw.source-manifest"
    assert rc7["schema_version"] == "1"
    assert rc7["release_state"] == "candidate"
    assert "release_tag" not in rc7


def test_rc7_owner_only_route_maps_ref_manifest_and_package_together() -> None:
    workflow = MAIN_WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc7"

    # One occurrence authorizes dispatch; two select the source manifest and
    # package namespace; the fourth guards the exact candidate version input.
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc7-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc7'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc7'") == 1
    assert "Require the exact protected RC7 candidate identity" in workflow
    assert workflow.index(branch) < workflow.index("tandem-agc-v8-rc6-source.yaml")


def test_rc7_source_graph_is_a_required_pr_check() -> None:
    workflow = PR_WORKFLOW.read_text(encoding="utf-8")
    checker = OFFLINE_CHECK.read_text(encoding="utf-8")

    assert "./scripts/check_tandem_release_offline.sh source-graph" in workflow
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc7-source.yaml"
    ) in checker


def test_rc7_keeps_the_two_reviewed_slice_relief_mappings() -> None:
    core = TANDEM_CORE.read_text(encoding="utf-8")

    assert '(* use_dsp = "yes" *) reg [19:0] pwr_div;' in core
    assert '(* use_dsp = "yes" *) reg [31:0] evt_seq;' in core
    assert core.count('(* use_dsp = "yes" *)') == 2


def test_rc7_bundle_upload_does_not_require_github_attestation() -> None:
    workflow = MAIN_WORKFLOW.read_text(encoding="utf-8")

    assert "Upload deployment bundle and verification sidecars" in workflow
    assert "${{ steps.build.outputs.bundle_path }}" in workflow
    assert "${{ steps.build.outputs.bundle_path }}.sha256" in workflow
    assert "if-no-files-found: error" in workflow
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow


def test_kalman_handoff_retains_the_rejected_rc7_build_record() -> None:
    runner = KALMAN_RUNNER.read_text(encoding="utf-8")

    assert "32948720383" in runner
    assert "7f13d6dd3f814af1a1e0d06d65535d2f60499b4bb3c0ab0e5cc4e7b8c8836f34" in runner
    assert "no deployment" in runner.lower()
    assert "GitHub attestation is not required for this handoff." in runner
    assert "plutosdr-fw.github-attestation-not-performed.v1" in runner
    assert 'sidecars=("$artifact_dir"/*.tar.gz.sha256)' in runner
    assert 'sha256sum -c "$(basename "$sidecar")"' in runner
    assert "sha256sum -c SHA256SUMS" in runner
    assert "gh attestation verify" not in runner


def test_rc7_release_docs_preserve_failed_candidate_lineage() -> None:
    releasing = RELEASING.read_text(encoding="utf-8")
    plan = RELEASE_PLAN.read_text(encoding="utf-8")
    candidate_lock = "refs/tags/tandem-agc-v8-rc7-source/firmware-v1"
    final_lock = "refs/tags/tandem-agc-v8-source/firmware-v1"

    assert "32948720383" in releasing
    assert (
        "7f13d6dd3f814af1a1e0d06d65535d2f60499b4bb3c0ab0e5cc4e7b8c8836f34" in releasing
    )
    assert "no deployment" in releasing.lower()
    assert candidate_lock in releasing
    assert final_lock in releasing
    assert "repeat the full three-radio campaign" in releasing
    assert 'gh attestation verify "$release_work"' not in releasing

    assert candidate_lock in plan
    assert final_lock in plan
    assert "32948720383" in plan
    assert "7f13d6dd3f814af1a1e0d06d65535d2f60499b4bb3c0ab0e5cc4e7b8c8836f34" in plan
