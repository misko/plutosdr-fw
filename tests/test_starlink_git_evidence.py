"""Git-object publication tests; fixtures never alter any production repository."""

import hashlib
import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/verify_starlink_git_evidence.py"
SPEC = importlib.util.spec_from_file_location("git_evidence", SCRIPT)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)


def commit(repo):
    git(repo, "-c", "user.name=Evidence Test", "-c", "user.email=test@example.invalid",
        "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgSign=false", "commit", "-qm", "fixture")
    return git(repo, "rev-parse", "HEAD").decode().strip()


@pytest.fixture
def archive(tmp_path):
    repo = tmp_path / "repository"
    repo.mkdir()
    git(repo, "init", "-q")
    root = repo / "evidence" / "with spaces"
    root.mkdir(parents=True)
    (root / "source.v").write_bytes(b"module source; endmodule\n")
    (root / "original.log").write_bytes(b"original FAIL retained\n")
    (repo / ".gitignore").write_text("*.log\n")
    manifest = b"".join(
        f"{sha((root / name).read_bytes())}  ./{name}\n".encode()
        for name in ("source.v", "original.log")
    )
    (root / "SHA256SUMS").write_bytes(manifest)
    git(repo, "add", ".")
    return repo, root, sha(manifest)


def verify(fixture, pin):
    repo, root, expected = fixture
    return CHECK.verify(repo, pin, str(root.relative_to(repo)), expected)


def test_ignored_local_file_cannot_satisfy_publication_then_additive_repair(archive):
    repo, root, _ = archive
    failed_pin = commit(repo)
    with pytest.raises(ValueError, match="missing=.*original.log"):
        verify(archive, failed_pin)
    git(repo, "add", "-f", "evidence/with spaces/original.log")
    passing_pin = commit(repo)
    result = verify(archive, passing_pin)
    assert result["members"] == 2 and result["tracked_files"] == 3
    assert result["commit"] == passing_pin
    with pytest.raises(ValueError, match="missing="):
        verify(archive, failed_pin)
    # The gate reads immutable Git objects, not current/ignored/index bytes.
    (root / "original.log").write_bytes(b"changed working tree\n")
    (root / "untracked.log").write_bytes(b"untracked is irrelevant\n")
    git(repo, "add", "-f", "evidence/with spaces/original.log")
    assert verify(archive, passing_pin) == result


@pytest.mark.parametrize("change", ["content", "extra", "symlink", "manifest", "missing_manifest"])
def test_committed_corruption_or_extra_paths_rejected(archive, change):
    repo, root, _ = archive
    git(repo, "add", "-f", "evidence/with spaces/original.log")
    if change == "content":
        (root / "source.v").write_bytes(b"changed\n")
    elif change == "extra":
        (root / "extra.txt").write_bytes(b"not inventoried\n")
    elif change == "symlink":
        (root / "source.v").unlink()
        (root / "source.v").symlink_to("original.log")
    elif change == "manifest":
        (root / "SHA256SUMS").write_bytes(b"substituted manifest\n")
    else:
        (root / "SHA256SUMS").unlink()
    git(repo, "add", "-A")
    pin = commit(repo)
    with pytest.raises(ValueError, match={
        "content": "member SHA256 mismatch", "extra": "closure differs",
        "symlink": "not a regular Git blob", "manifest": "reviewed identity",
        "missing_manifest": "manifest is missing",
    }[change]):
        verify(archive, pin)


@pytest.mark.parametrize("value", ["", "/absolute", "../outside", "a/../b", "a//b", "a/", "a\\b", "a\nb", "./a"])
def test_noncanonical_paths_rejected(value):
    with pytest.raises(ValueError, match="noncanonical"):
        CHECK.safe_path(value)


@pytest.mark.parametrize("data", [
    b"", b"\n", b"bad\n", ("a" * 64 + " file\n").encode(),
    ("a" * 64 + "  file").encode(),
    ("a" * 64 + "  file\n" + "a" * 64 + "  ./file\n").encode(),
    ("a" * 64 + "  SHA256SUMS\n").encode(),
    ("a" * 64 + "  ../escape\n").encode(),
    b"\xff\n",
])
def test_bad_manifests_rejected(data):
    with pytest.raises((ValueError, UnicodeError)):
        CHECK.parse_manifest(data)


@pytest.mark.parametrize("pin", ["HEAD", "main", "abc123", "--all", "A" * 40])
def test_moving_or_noncanonical_references_rejected(archive, pin):
    with pytest.raises(ValueError, match="complete immutable"):
        verify(archive, pin)


def test_cli_reports_only_committed_integrity(archive):
    import sys

    repo, root, expected = archive
    git(repo, "add", "-f", "evidence/with spaces/original.log")
    pin = commit(repo)
    command = [sys.executable, "-B", str(SCRIPT), "--repo", str(repo), "--commit", pin,
               "--archive", str(root.relative_to(repo)), "--expected-manifest", expected]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "NOT_test_or_remote_qualification" in result.stdout
    result = subprocess.run(command[:-1] + ["0" * 64], capture_output=True, text=True, check=False)
    assert result.returncode == 1 and "reviewed identity" in result.stderr
