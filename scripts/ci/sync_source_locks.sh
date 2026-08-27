#!/usr/bin/env bash
# Synchronize only the immutable component tags named by a source manifest.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MANIFEST="${1:-${SPF_GAIN_SERIES_MANIFEST:-}}"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

[[ -n "$MANIFEST" ]] || fail "usage: $0 manifests/source.yaml"
[[ "$MANIFEST" == /* ]] || MANIFEST="$ROOT/$MANIFEST"
[[ -f "$MANIFEST" ]] || fail "source manifest not found: $MANIFEST"

# shellcheck source=scripts/ci/source_manifest_lib.sh
source "$ROOT/scripts/ci/source_manifest_lib.sh"

components=(
    "buildroot:submodule_buildroot:submodule_buildroot_repo:submodule_buildroot_ref"
    "hdl:submodule_hdl:submodule_hdl_repo:submodule_hdl_ref"
    "hdl-quantulum:submodule_hdl_quantulum:submodule_hdl_quantulum_repo:submodule_hdl_quantulum_ref"
    "linux:submodule_linux:submodule_linux_repo:submodule_linux_ref"
    "u-boot-xlnx:submodule_u_boot_xlnx:submodule_u_boot_xlnx_repo:submodule_u_boot_xlnx_ref"
)

for entry in "${components[@]}"; do
    IFS=: read -r path pin_key repo_key ref_key <<<"$entry"
    pin="$(source_manifest_value "$MANIFEST" "$pin_key")"
    repo="$(source_manifest_value "$MANIFEST" "$repo_key")"
    ref="$(source_manifest_value "$MANIFEST" "$ref_key")"
    [[ "$pin" =~ ^[0-9a-f]{40}$ ]] || fail "$path has no exact commit pin"
    [[ -n "$repo" && "$ref" == refs/tags/* ]] ||
        fail "$path must use an immutable refs/tags source lock"
    [[ -e "$ROOT/$path/.git" ]] || fail "$path is not an initialized git worktree"

    head_commit="$(git -C "$ROOT/$path" rev-parse HEAD)"
    [[ "$head_commit" == "$pin" ]] ||
        fail "$path HEAD is $head_commit; manifest pins $pin"
    remote_commit="$(source_manifest_ref_commit "$repo" "$ref")"
    [[ "$remote_commit" == "$pin" ]] ||
        fail "$path remote $ref is ${remote_commit:-missing}; manifest pins $pin"

    # Fetch only the declared lock, never the remote's ambient tag namespace.
    # Force is intentional: a stale persistent-runner tag previously made the
    # packed Buildroot identity read v1-1-g<sha> even at the pinned commit.
    git -C "$ROOT/$path" fetch --force --no-tags "$repo" "+$ref:$ref"
    local_commit="$(git -C "$ROOT/$path" rev-parse "${ref}^{commit}")"
    [[ "$local_commit" == "$pin" ]] ||
        fail "$path local $ref is $local_commit after synchronization"
    printf 'source lock %-15s %s == %s\n' "$path" "${pin:0:12}" "$ref"
done

# A persistent runner may retain another tag at the same commit.  Git permits
# that, and `git describe --tags` then chooses one alias according to its own
# ordering rather than the tag we just fetched.  /opt/VERSIONS is generated
# from that exact command, so prove the live worktree will emit the manifest's
# expected identity before starting any expensive build work.
packed_identities=(
    "hdl:versions_hdl"
    "buildroot:versions_buildroot"
    "linux:versions_linux"
    "u-boot-xlnx:versions_u_boot_xlnx"
)
for entry in "${packed_identities[@]}"; do
    IFS=: read -r path identity_key <<<"$entry"
    expected_identity="$(source_manifest_value "$MANIFEST" "$identity_key")"
    [[ -n "$expected_identity" ]] || continue
    actual_identity="$(
        git -C "$ROOT/$path" describe --abbrev=4 --dirty --always --tags
    )"
    [[ "$actual_identity" == "$expected_identity" ]] ||
        fail "$path git describe is '$actual_identity'; manifest requires '$expected_identity'"
    printf 'packed identity %-12s %s\n' "$path" "$actual_identity"
done
