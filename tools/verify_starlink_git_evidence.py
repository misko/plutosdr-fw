"""Verify a SHA256SUMS archive in a pinned Git commit, without filesystem writes.

This checks publication contents, not test validity or remote availability.
Working-tree files (including ignored evidence) cannot satisfy this gate.
"""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def safe_path(value):
    if (
        not value
        or any(part in ("", ".", "..") for part in value.split("/"))
        or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError(f"noncanonical archive path: {value!r}")
    return value


def git(repo, *args):
    return subprocess.check_output(
        ["git", "--no-replace-objects", "--literal-pathspecs", "-C", str(repo), *args],
        stderr=subprocess.PIPE,
    )


def parse_manifest(data):
    entries = {}
    text = data.decode("utf-8")
    if not text.endswith("\n"):
        raise ValueError("manifest must end with a newline")
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            raise ValueError("malformed SHA256SUMS row")
        name = safe_path(match[2].removeprefix("./"))
        if name in entries or name == "SHA256SUMS":
            raise ValueError("duplicate or self-referential manifest member")
        entries[name] = match[1]
    if not entries:
        raise ValueError("empty evidence manifest")
    return entries


def blob_digest(repo, oid):
    command = [
        "git", "--no-replace-objects", "-C", str(repo), "cat-file", "blob", oid,
    ]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as child:
        value = hashlib.file_digest(child.stdout, "sha256").hexdigest()
        error = child.stderr.read()
        if child.wait() != 0:
            raise ValueError(f"cannot read committed blob {oid}: {error!r}")
    return value


def verify(repo, commit, archive, expected_manifest):
    """Require exact committed path closure and all committed content hashes."""
    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit) is None:
        raise ValueError("commit must be a complete immutable Git object ID")
    if re.fullmatch(r"[0-9a-f]{64}", expected_manifest) is None:
        raise ValueError("expected manifest must be a SHA256 digest")
    repo = Path(repo).resolve()
    archive = safe_path(archive)
    resolved = git(repo, "rev-parse", "--verify", f"{commit}^{{commit}}").decode().strip()
    if resolved != commit:
        raise ValueError("object is not the exact requested commit")
    prefix = archive + "/"
    tree = {}
    for row in git(repo, "ls-tree", "-r", "-z", commit, "--", prefix).split(b"\0"):
        if not row:
            continue
        info, raw_path = row.split(b"\t", 1)
        mode, kind, oid = info.decode().split()
        path = raw_path.decode("utf-8")
        if not path.startswith(prefix):
            raise ValueError("Git returned a path outside the archive")
        name = safe_path(path[len(prefix):])
        if mode not in ("100644", "100755") or kind != "blob":
            raise ValueError(f"archive member is not a regular Git blob: {name}")
        if name in tree:
            raise ValueError("duplicate committed path")
        tree[name] = oid
    if "SHA256SUMS" not in tree:
        raise ValueError("manifest is missing from the committed archive")
    data = git(repo, "cat-file", "blob", tree["SHA256SUMS"])
    if hashlib.sha256(data).hexdigest() != expected_manifest:
        raise ValueError("committed manifest differs from reviewed identity")
    entries = parse_manifest(data)
    missing = set(entries) - tree.keys()
    extra = tree.keys() - set(entries) - {"SHA256SUMS"}
    if missing or extra:
        raise ValueError(f"committed archive closure differs: missing={sorted(missing)}, extra={sorted(extra)}")
    for name, expected in entries.items():
        if blob_digest(repo, tree[name]) != expected:
            raise ValueError(f"committed member SHA256 mismatch: {name}")
    return {
        "scope": "committed_archive_integrity_only_NOT_test_or_remote_qualification",
        "commit": commit,
        "archive": archive,
        "manifest_sha256": expected_manifest,
        "members": len(entries),
        "tracked_files": len(tree),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--expected-manifest", required=True)
    args = parser.parse_args()
    try:
        result = verify(args.repo, args.commit, args.archive, args.expected_manifest)
    except (ValueError, UnicodeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Git evidence verification failed: {error}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
