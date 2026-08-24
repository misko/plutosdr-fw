"""Offline release-process regressions that need no firmware toolchain."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_LIB = ROOT / "scripts" / "ci" / "source_manifest_lib.sh"
FINAL_SOURCE_MANIFEST = ROOT / "manifests" / "tandem-agc-v8-source.yaml"
FIRMWARE_PR_WORKFLOW = ROOT / ".github" / "workflows" / "firmware.yml"


def _git(*args: str, cwd: Path) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL
    ).strip()


def _resolve(repo: Path, ref: str) -> str:
    script = f'source {SOURCE_LIB!s}; source_manifest_ref_commit "$1" "$2"'
    return subprocess.check_output(
        ["bash", "-c", script, "bash", str(repo), ref], text=True
    ).strip()


def _tag_identity(ref: str) -> str:
    script = f'source {SOURCE_LIB!s}; source_manifest_tag_identity "$1"'
    return subprocess.check_output(
        ["bash", "-c", script, "bash", ref], text=True
    ).strip()


def _manifest_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def test_source_manifest_ref_commit_peels_annotated_tag(tmp_path: Path) -> None:
    work = tmp_path / "work"
    bare = tmp_path / "remote.git"
    work.mkdir()
    _git("init", cwd=work)
    _git("config", "user.name", "release oracle", cwd=work)
    _git("config", "user.email", "oracle@example.invalid", cwd=work)
    (work / "payload").write_text("qualified\n", encoding="utf-8")
    _git("add", "payload", cwd=work)
    _git("commit", "-m", "qualified source", cwd=work)
    commit = _git("rev-parse", "HEAD", cwd=work)
    _git("tag", "-a", "v8", "-m", "annotated v8", cwd=work)
    _git("init", "--bare", str(bare), cwd=work)
    _git("remote", "add", "origin", str(bare), cwd=work)
    _git("push", "origin", "HEAD", "refs/tags/v8", cwd=work)

    assert _resolve(bare, "refs/tags/v8") == commit


def test_source_manifest_ref_commit_accepts_lightweight_tag(tmp_path: Path) -> None:
    work = tmp_path / "work"
    bare = tmp_path / "remote.git"
    work.mkdir()
    _git("init", cwd=work)
    _git("config", "user.name", "release oracle", cwd=work)
    _git("config", "user.email", "oracle@example.invalid", cwd=work)
    (work / "payload").write_text("candidate\n", encoding="utf-8")
    _git("add", "payload", cwd=work)
    _git("commit", "-m", "candidate source", cwd=work)
    commit = _git("rev-parse", "HEAD", cwd=work)
    _git("tag", "source-lock", cwd=work)
    _git("init", "--bare", str(bare), cwd=work)
    _git("remote", "add", "origin", str(bare), cwd=work)
    _git("push", "origin", "HEAD", "refs/tags/source-lock", cwd=work)

    assert _resolve(bare, "refs/tags/source-lock") == commit


def test_source_manifest_tag_identity_preserves_namespace() -> None:
    assert (
        _tag_identity("refs/tags/tandem-agc-v8-rc2-source/buildroot-v1")
        == "tandem-agc-v8-rc2-source/buildroot-v1"
    )


def test_final_packed_identities_match_declared_source_lock_tags() -> None:
    values = _manifest_values(FINAL_SOURCE_MANIFEST)
    mappings = {
        "versions_hdl": "submodule_hdl_ref",
        "versions_buildroot": "submodule_buildroot_ref",
        "versions_linux": "submodule_linux_ref",
        "versions_u_boot_xlnx": "submodule_u_boot_xlnx_ref",
    }

    for identity_key, ref_key in mappings.items():
        assert values[identity_key] == _tag_identity(values[ref_key])


def test_required_hdl_simulation_uses_final_timestamp_source() -> None:
    values = _manifest_values(FINAL_SOURCE_MANIFEST)
    workflow = FIRMWARE_PR_WORKFLOW.read_text(encoding="utf-8")
    checkout = re.search(
        r"repository:\s*misko/plutosdr-hdl-quantulum\s*\n\s*"
        r"ref:\s*([0-9a-f]{40})",
        workflow,
    )

    assert checkout is not None
    assert checkout.group(1) == values["submodule_hdl_quantulum"]
    assert "./run_timestamp_check_pipeline.sh" in workflow
