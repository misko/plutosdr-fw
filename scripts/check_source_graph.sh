#!/usr/bin/env bash
#
# Verify the firmware source graph is complete and retrievable, without cloning
# anything. Runs in seconds on any runner and needs no toolchain.
#
# This is the cheapest CI layer and it exists because every historical failure
# in this repository was a source-graph failure, not a compile failure:
#
#   * three submodules used RELATIVE urls (../plutosdr-linux.git) which resolve
#     against whichever remote is named `origin`. Cloning from misko/ resolved
#     them to misko/plutosdr-linux.git, which did not exist -- a fresh clone was
#     simply impossible, and nobody noticed because every existing checkout had
#     `origin` pointing at pgreenland.
#
#   * three `branch =` keys named a branch that did NOT match the pinned
#     commit, so `git submodule update --remote` silently retrieved different
#     firmware and reported success. New candidate manifests use protected
#     source-lock tags; strict ref-to-pin equality keeps those locks auditable.
#
# Both are invisible to a compile test on a machine that already has the source.
#
# Usage: scripts/check_source_graph.sh [manifests/fingerprint-v3.yaml]
#
# SOURCE_GRAPH_CHECK_WORKTREE=0 validates an immutable historical manifest's
# remote refs and identities without comparing it to the current checkout.

set -uo pipefail

MANIFEST="${1:-manifests/fingerprint-v3.yaml}"
[[ -f "$MANIFEST" ]] || { echo "FAIL: manifest not found: $MANIFEST" >&2; exit 1; }
CHECK_WORKTREE="${SOURCE_GRAPH_CHECK_WORKTREE:-1}"
[[ "$CHECK_WORKTREE" == 0 || "$CHECK_WORKTREE" == 1 ]] || {
    echo "FAIL: SOURCE_GRAPH_CHECK_WORKTREE must be 0 or 1" >&2
    exit 1
}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/ci/source_manifest_lib.sh
source "$ROOT/scripts/ci/source_manifest_lib.sh"

RC=0
ok()   { printf '  ok    %s\n' "$*"; }
bad()  { printf '  FAIL  %s\n' "$*"; RC=1; }
warn() { printf '  warn  %s\n' "$*"; }

m() {
    source_manifest_value "$MANIFEST" "$1"
}

echo "Source graph check: ${MANIFEST}"
echo
echo "1. every pinned commit exactly matches its declared source ref"

# name:pin_key:repo_key:ref_key
COMPONENTS=(
    "buildroot:submodule_buildroot:submodule_buildroot_repo:submodule_buildroot_ref"
    "hdl:submodule_hdl:submodule_hdl_repo:submodule_hdl_ref"
    "hdl-quantulum:submodule_hdl_quantulum:submodule_hdl_quantulum_repo:submodule_hdl_quantulum_ref"
    "linux:submodule_linux:submodule_linux_repo:submodule_linux_ref"
    "u-boot-xlnx:submodule_u_boot_xlnx:submodule_u_boot_xlnx_repo:submodule_u_boot_xlnx_ref"
    "gadget:gadget_source:gadget_repo:gadget_ref"
    "ip-gadget:ip_gadget_source:ip_gadget_repo:ip_gadget_ref"
)

if [[ -n "$(m metadata_source)$(m metadata_repo)$(m metadata_ref)" ]]; then
    COMPONENTS+=("metadata:metadata_source:metadata_repo:metadata_ref")
fi

# Host compatibility sources are optional because historical firmware
# manifests predate the frame-metadata extension.  When a candidate declares
# either supported libiio line, require the complete immutable source lock.
for entry in \
    "libiio-0.25:libiio_0_25_source:libiio_0_25_repo:libiio_0_25_ref" \
    "libiio-0.26:libiio_0_26_source:libiio_0_26_repo:libiio_0_26_ref"; do
    IFS=: read -r name pin_key repo_key ref_key <<<"$entry"
    if [[ -n "$(m "$pin_key")$(m "$repo_key")$(m "$ref_key")" ]]; then
        COMPONENTS+=("$entry")
    fi
done

for entry in "${COMPONENTS[@]}"; do
    IFS=: read -r name pin_key repo_key ref_key <<<"$entry"
    pin="$(m "$pin_key")"; repo="$(m "$repo_key")"; ref="$(m "$ref_key")"
    if [[ -z "$pin" || -z "$repo" || -z "$ref" ]]; then
        bad "${name}: manifest incomplete (pin/repo/ref)"; continue
    fi
    # Exact equality is intentional. Candidate manifests use protected tags,
    # not moving development branches, so accepting a descendant would weaken
    # the source lock. ls-remote verifies the advertised ref without cloning.
    actual="$(source_manifest_ref_commit "$repo" "$ref" 2>/dev/null)"
    if [[ -z "$actual" ]]; then
        bad "${name}: ref ${ref} not found at ${repo}"
    elif [[ "$actual" != "$pin" ]]; then
        bad "${name}: ${ref} is at ${actual:0:12}, manifest pins ${pin:0:12} (source lock mismatch)"
    else
        ok "${name} ${pin:0:12} == ${ref}"
    fi
done

echo
echo "2. packed component identities exactly match their source-lock tags"

# Make writes these strings with `git describe --tags`.  Every final source
# lock points at the exact component commit, so the deterministic describe
# form is the complete tag name with only the refs/tags/ prefix removed.
# Checking this here prevents a typo or stale alias from wasting a full FPGA
# and rootfs build before package_main_firmware.sh detects the mismatch.
IDENTITIES=(
    "hdl:versions_hdl:submodule_hdl_ref"
    "buildroot:versions_buildroot:submodule_buildroot_ref"
    "linux:versions_linux:submodule_linux_ref"
    "u-boot-xlnx:versions_u_boot_xlnx:submodule_u_boot_xlnx_ref"
)
for entry in "${IDENTITIES[@]}"; do
    IFS=: read -r name identity_key ref_key <<<"$entry"
    identity="$(m "$identity_key")"
    [[ -n "$identity" ]] || continue
    ref="$(m "$ref_key")"
    if ! tag_identity="$(source_manifest_tag_identity "$ref")"; then
        bad "${name}: ${ref_key} must name a refs/tags source lock"
    elif [[ "$identity" != "$tag_identity" ]]; then
        bad "${name}: ${identity_key} is '${identity}', but ${ref_key} describes as '${tag_identity}'"
    else
        ok "${name} packed identity ${identity}"
    fi
done

echo
echo "3. the release tag labels the commit that actually built the release"
# The v3 tag was created AFTER three further commits landed, so it points at
# dac99758 while the shipped binary was built from f53dd006. `git checkout
# <release tag>` therefore hands you source that did not build that release.
# The manifest records the true build commit; this check keeps the discrepancy
# visible instead of letting it rot into folklore.
fw_repo="$(m firmware_repo)"; fw_pin="$(m firmware_source)"; rel_tag="$(m release_tag)"
if [[ -z "$rel_tag" ]]; then
    warn "candidate source manifest has no release tag (expected before promotion)"
else
tag_sha="$(source_manifest_ref_commit "$fw_repo" "refs/tags/${rel_tag}" 2>/dev/null)"
if [[ -z "$tag_sha" ]]; then
    bad "release tag ${rel_tag} not found at ${fw_repo}"
elif [[ "$tag_sha" == "$fw_pin" ]]; then
    ok "release tag ${rel_tag} == firmware_source ${fw_pin:0:12}"
else
    warn "release tag ${rel_tag} -> ${tag_sha:0:12}, but the release was built from ${fw_pin:0:12}"
    warn "  known and recorded for v3; a NEW release must tag its own build commit"
fi
fi

echo
echo "4. .gitmodules hygiene"
if [[ -f .gitmodules ]]; then
    if grep -qE '^\s*url\s*=\s*\.\.' .gitmodules; then
        bad "relative submodule url present (resolves against \`origin\`, breaks fresh clones)"
    else
        ok "all submodule urls are absolute"
    fi
else
    warn ".gitmodules not present (not a firmware checkout?)"
fi

if [[ "$CHECK_WORKTREE" == 1 && "$(m release_state)" == "candidate" ]] && \
    git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    for entry in "buildroot:submodule_buildroot" "hdl:submodule_hdl" \
        "hdl-quantulum:submodule_hdl_quantulum" \
        "linux:submodule_linux" "u-boot-xlnx:submodule_u_boot_xlnx"; do
        IFS=: read -r path pin_key <<<"$entry"
        expected="$(m "$pin_key")"
        actual="$(git ls-tree HEAD "$path" | awk '{print $3}')"
        if [[ -n "$expected" && "$actual" == "$expected" ]]; then
            ok "gitlink ${path} ${actual:0:12}"
        else
            bad "gitlink ${path} is ${actual:0:12}, manifest pins ${expected:0:12}"
        fi
    done

    # The libiio source lock is also the daemon compiled into the firmware.
    # Checking only the externally consumable source pin can pass while the
    # Buildroot recipe silently embeds an older iiod.
    expected_libiio="$(m libiio_0_25_source)"
    recipe="buildroot/package/libiio/libiio.mk"
    if [[ -n "$expected_libiio" && -f "$recipe" ]]; then
        recipe_libiio="$(sed -n 's/^LIBIIO_VERSION[[:space:]]*=[[:space:]]*//p' "$recipe" | head -1)"
        if [[ "$recipe_libiio" == "$expected_libiio" ]]; then
            ok "Buildroot libiio recipe ${recipe_libiio:0:12}"
        else
            bad "Buildroot libiio recipe is ${recipe_libiio:0:12}, manifest pins ${expected_libiio:0:12}"
        fi
    elif [[ -n "$expected_libiio" ]]; then
        bad "Buildroot libiio recipe not found: ${recipe}"
    fi
    expected_libiio_archive_sha="$(m libiio_0_25_archive_sha256)"
    libiio_hash="buildroot/package/libiio/libiio.hash"
    if [[ -n "$expected_libiio_archive_sha" && -f "$libiio_hash" ]]; then
        expected_hash_line="sha256 ${expected_libiio_archive_sha}  libiio-${expected_libiio}.tar.gz"
        if grep -Fqx "$expected_hash_line" "$libiio_hash"; then
            ok "Buildroot libiio archive hash ${expected_libiio_archive_sha:0:12}"
        else
            bad "Buildroot libiio archive hash does not match the manifest"
        fi
    elif [[ -n "$expected_libiio_archive_sha" ]]; then
        bad "Buildroot libiio hash file not found: ${libiio_hash}"
    fi
    expected_metadata="$(m metadata_source)"
    metadata_recipe="buildroot/package/spf_metadata_source/spf_metadata_source.mk"
    if [[ -n "$expected_metadata" && -f "$metadata_recipe" ]]; then
        recipe_metadata="$(sed -n 's/^SPF_METADATA_SOURCE_VERSION[[:space:]]*=[[:space:]]*//p' "$metadata_recipe" | head -1)"
        if [[ "$recipe_metadata" == "$expected_metadata" ]]; then
            ok "Buildroot metadata recipe ${recipe_metadata:0:12}"
        else
            bad "Buildroot metadata recipe is ${recipe_metadata:0:12}, manifest pins ${expected_metadata:0:12}"
        fi
    elif [[ -n "$expected_metadata" ]]; then
        bad "Buildroot metadata recipe not found: ${metadata_recipe}"
    fi
elif [[ "$CHECK_WORKTREE" == 0 ]]; then
    warn "historical manifest: current-worktree closure intentionally skipped"
fi

echo
echo "5. no local source overrides"
# A Buildroot <PKG>_OVERRIDE_SRCDIR still passes -DGIT_VERSION_OVERRIDE from the
# pinned .mk, so an overridden build yields a binary that REPORTS the pinned
# gadget SHA while containing entirely different code.
# Check ONLY where Buildroot actually reads an override: $(CONFIG_DIR)/local.mk,
# i.e. the buildroot top directory and its output directory. A blanket
# `find . -name local.mk` is wrong -- upstream bison and autoconf ship dozens of
# local.mk files as ordinary automake includes under buildroot/output/build/,
# and flagging those makes the check cry wolf until someone disables it.
strays=""
for candidate in local.mk buildroot/local.mk buildroot/output/local.mk; do
    [[ -f "$candidate" ]] && strays+=" ${candidate}"
done
if [[ -n "$strays" ]]; then
    bad "Buildroot source override present:${strays}"
    for s in $strays; do printf '        %s: %s\n' "$s" "$(head -1 "$s")"; done
else
    ok "no Buildroot local.mk override"
fi

echo
if (( RC == 0 )); then echo "SOURCE GRAPH OK"; else echo "SOURCE GRAPH BROKEN"; fi
exit $RC
