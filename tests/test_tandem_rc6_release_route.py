"""Offline oracles for the protected tandem AGC v8 RC6 build route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC4_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc4-source.yaml"
RC5_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc5-source.yaml"
RC6_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc6-source.yaml"
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


def test_rc6_reuses_only_the_reviewed_rc5_external_source_graph() -> None:
    rc4 = _manifest_values(RC4_MANIFEST)
    rc5 = _manifest_values(RC5_MANIFEST)
    rc6 = _manifest_values(RC6_MANIFEST)
    final = _manifest_values(FINAL_MANIFEST)

    assert rc6 == rc5 == rc4 == final
    assert rc6["schema"] == "plutosdr-fw.source-manifest"
    assert rc6["schema_version"] == "1"
    assert rc6["release_state"] == "candidate"
    assert "release_tag" not in rc6


def test_rc6_owner_only_route_maps_ref_manifest_and_package_together() -> None:
    workflow = MAIN_WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc6"

    # One occurrence authorizes dispatch; two select the source manifest and
    # package namespace; the fourth guards the exact candidate version input.
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc6-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc6'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc6'") == 1
    assert "Require the exact protected RC6 candidate identity" in workflow
    assert workflow.index(branch) < workflow.index("tandem-agc-v8-rc5-source.yaml")


def test_rc6_source_graph_is_a_required_pr_check() -> None:
    workflow = PR_WORKFLOW.read_text(encoding="utf-8")
    checker = OFFLINE_CHECK.read_text(encoding="utf-8")

    assert "./scripts/check_tandem_release_offline.sh source-graph" in workflow
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc6-source.yaml"
    ) in checker


def test_rc6_keeps_the_two_reviewed_slice_relief_mappings() -> None:
    core = TANDEM_CORE.read_text(encoding="utf-8")

    # The XC7Z010 image is slice-limited and has spare DSP48s.  Removing either
    # mapping silently returns the trusted build to the placement cliff, so the
    # inexpensive offline route oracle guards the two measured accumulators.
    assert '(* use_dsp = "yes" *) reg [19:0] pwr_div;' in core
    assert '(* use_dsp = "yes" *) reg [31:0] evt_seq;' in core
    assert core.count('(* use_dsp = "yes" *)') == 2


def test_rc6_bundle_upload_does_not_require_github_attestation() -> None:
    workflow = MAIN_WORKFLOW.read_text(encoding="utf-8")

    # The build job itself uploads the exact bundle and detached checksum.
    # Supporting provenance attestation is an optional operator action and
    # cannot turn a successful single-owner firmware build into a failed run.
    assert "Upload deployment bundle and verification sidecars" in workflow
    assert "${{ steps.build.outputs.bundle_path }}" in workflow
    assert "${{ steps.build.outputs.bundle_path }}.sha256" in workflow
    assert "if-no-files-found: error" in workflow
    assert "actions/attest@" not in workflow
    assert "\n  attest:" not in workflow


def test_kalman_handoff_matches_the_rc6_bundle_checksum_contract() -> None:
    runner = KALMAN_RUNNER.read_text(encoding="utf-8")

    assert "The RC6 workflow has no separate attestation job." in runner
    assert "GitHub attestation is not required for this handoff." in runner
    assert "plutosdr-fw.github-attestation-not-performed.v1" in runner
    assert 'sidecars=("$artifact_dir"/*.tar.gz.sha256)' in runner
    assert 'sha256sum -c "$(basename "$sidecar")"' in runner
    assert "sha256sum -c SHA256SUMS" in runner
    assert "gh attestation verify" not in runner
    assert "downloads, verifies, and attests" not in runner


def test_rc6_release_docs_bind_exact_stage_locks_and_full_final_campaign() -> None:
    releasing = RELEASING.read_text(encoding="utf-8")
    plan = RELEASE_PLAN.read_text(encoding="utf-8")
    candidate_lock = "refs/tags/tandem-agc-v8-rc6-source/firmware-v1"
    final_lock = "refs/tags/tandem-agc-v8-source/firmware-v1"

    assert "The active candidate is RC6" in releasing
    assert candidate_lock in releasing
    assert final_lock in releasing
    assert "repeat the full four-radio campaign" in releasing
    assert 'gh attestation verify "$release_work"' not in releasing

    assert candidate_lock in plan
    assert final_lock in plan
    assert "exact_main_commit='<40-character-exact-main-commit>'" in plan
    assert 'git tag tandem-agc-v8-source/firmware-v1 "$exact_main_commit"' in plan
    assert "The v8 policy always\nselects `full-campaign`." in plan
