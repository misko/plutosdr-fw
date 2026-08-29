"""Offline oracles for the protected tandem AGC v8 RC5 build route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC4_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc4-source.yaml"
RC5_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc5-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
MAIN_WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
PR_WORKFLOW = ROOT / ".github" / "workflows" / "firmware.yml"
OFFLINE_CHECK = ROOT / "scripts" / "check_tandem_release_offline.sh"


def _manifest_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def test_rc5_reuses_only_the_reviewed_rc4_external_source_graph() -> None:
    rc4 = _manifest_values(RC4_MANIFEST)
    rc5 = _manifest_values(RC5_MANIFEST)
    final = _manifest_values(FINAL_MANIFEST)

    assert rc5 == rc4 == final
    assert rc5["schema"] == "plutosdr-fw.source-manifest"
    assert rc5["schema_version"] == "1"
    assert rc5["release_state"] == "candidate"
    assert "release_tag" not in rc5


def test_rc5_owner_only_route_maps_ref_manifest_and_package_together() -> None:
    workflow = MAIN_WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc5"

    # One occurrence authorizes dispatch; two select the source manifest and
    # package namespace; the fourth guards the exact candidate version input.
    # Missing any one must fail this oracle.
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc5-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc5'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc5'") == 1
    assert "Require the exact protected RC5 reproduction identity" in workflow
    assert workflow.count("'v0.44-plutoplus-spf-ddr-ring-prefill-v1'") == 1
    assert "Require the exact final release identity" in workflow
    assert "'final-release'" in workflow
    assert workflow.index(branch) < workflow.index("tandem-agc-v8-rc4-source.yaml")


def test_rc5_source_graph_is_a_required_pr_check() -> None:
    workflow = PR_WORKFLOW.read_text(encoding="utf-8")
    checker = OFFLINE_CHECK.read_text(encoding="utf-8")

    assert "./scripts/check_tandem_release_offline.sh source-graph" in workflow
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc5-source.yaml"
    ) in checker
