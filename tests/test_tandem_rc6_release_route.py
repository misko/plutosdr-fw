"""Offline oracles for the immutable tandem AGC v8 RC6 reproduction route."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC4_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc4-source.yaml"
RC5_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc5-source.yaml"
RC6_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc6-source.yaml"
FINAL_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
MAIN_WORKFLOW = ROOT / ".github" / "workflows" / "firmware-main.yml"
PR_WORKFLOW = ROOT / ".github" / "workflows" / "firmware.yml"
OFFLINE_CHECK = ROOT / "scripts" / "check_tandem_release_offline.sh"
RELEASE_NOTES = ROOT / "RELEASE_NOTES.md"


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
    assert "Require the exact protected RC6 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index("tandem-agc-v8-rc5-source.yaml")


def test_rc6_source_graph_is_a_required_pr_check() -> None:
    workflow = PR_WORKFLOW.read_text(encoding="utf-8")
    checker = OFFLINE_CHECK.read_text(encoding="utf-8")

    assert "./scripts/check_tandem_release_offline.sh source-graph" in workflow
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc6-source.yaml"
    ) in checker


def test_rc6_failure_is_retained_as_exact_non_artifact_history() -> None:
    notes = RELEASE_NOTES.read_text(encoding="utf-8")

    assert "32944830787" in notes
    assert "32,908 of 32,908" in notes
    assert re.search(r"4,399 of 4,400\s+slices", notes)
    assert "74 of 80 DSPs" in notes
    assert "WNS `+0.645 ns`" in notes
    assert re.search(r"WHS\s+`\+0\.022 ns`", notes)
    assert "bus-skew minimum was `+8.606 ns`" in notes
    assert "no deployment bundle, candidate index, or DFU" in notes
