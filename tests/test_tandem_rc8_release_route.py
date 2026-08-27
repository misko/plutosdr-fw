"""Offline oracles for the immutable tandem AGC v8 RC8 reproduction route."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RC6_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc6-source.yaml"
RC7_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc7-source.yaml"
RC8_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-rc8-source.yaml"
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


def test_rc8_reuses_only_the_reviewed_rc7_external_source_graph() -> None:
    rc6 = _manifest_values(RC6_MANIFEST)
    rc7 = _manifest_values(RC7_MANIFEST)
    rc8 = _manifest_values(RC8_MANIFEST)
    final = _manifest_values(FINAL_MANIFEST)

    assert rc8 == rc7 == rc6 == final
    assert rc8["schema"] == "plutosdr-fw.source-manifest"
    assert rc8["schema_version"] == "1"
    assert rc8["release_state"] == "candidate"
    assert "release_tag" not in rc8


def test_rc8_owner_only_route_maps_ref_manifest_and_package_together() -> None:
    workflow = MAIN_WORKFLOW.read_text(encoding="utf-8")
    branch = "refs/heads/codex/firmware-tandem-agc-v8-rc8"

    # One occurrence authorizes dispatch; two select the source manifest and
    # package namespace; the fourth guards the exact candidate version input.
    assert workflow.count(branch) == 4
    assert workflow.count("'tandem-agc-v8-rc8-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-tandem-agc-v8-rc8'") == 1
    assert workflow.count("'v0.41-plutoplus-spf-tandem-agc-v8-rc8'") == 1
    assert "Require the exact protected RC8 reproduction identity" in workflow
    assert workflow.index(branch) < workflow.index("tandem-agc-v8-rc7-source.yaml")


def test_rc8_source_graph_is_a_required_pr_check() -> None:
    workflow = PR_WORKFLOW.read_text(encoding="utf-8")
    checker = OFFLINE_CHECK.read_text(encoding="utf-8")

    assert "./scripts/check_tandem_release_offline.sh source-graph" in workflow
    assert (
        "./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc8-source.yaml"
    ) in checker


def test_rc8_success_is_retained_as_indexed_non_deployment_history() -> None:
    notes = RELEASE_NOTES.read_text(encoding="utf-8")

    for expected in (
        "32952343526",
        "d94b9c37a8c6f1e5935df5ae4bdfd03be49b7aba40236a32386382a0f09004a8",
        "d55b58e489a58c3c8868f4bfcec4a7901c229a25e801c172bf2dd1fa08965c77",
        "2c74f06bff072d9c3250e5e028e18ddda4f700f5960cd07153432f1a081a8f49",
        "30f7816ea2f1b66aff928613b95748f952cafbb35bc7320a05bfdd5e3075b9d8",
        "32,908 of 32,908",
        "4,399 of 4,400",
        "74 of 80 DSPs",
        "WNS `+0.645 ns`",
        "WHS `+0.022 ns`",
        "bus-skew minimum `+8.606 ns`",
        "zero hardware deployment",
    ):
        assert expected in notes
