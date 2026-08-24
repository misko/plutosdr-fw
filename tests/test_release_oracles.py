"""Offline release-process regressions that need no firmware toolchain."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_LIB = ROOT / "scripts" / "ci" / "source_manifest_lib.sh"


def _git(*args: str, cwd: Path) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL
    ).strip()


def _resolve(repo: Path, ref: str) -> str:
    script = (
        f"source {SOURCE_LIB!s}; "
        'source_manifest_ref_commit "$1" "$2"'
    )
    return subprocess.check_output(
        ["bash", "-c", script, "bash", str(repo), ref], text=True
    ).strip()


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
