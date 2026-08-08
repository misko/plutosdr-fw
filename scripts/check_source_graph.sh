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
#   * three `branch =` keys named a branch that does NOT contain the pinned
#     commit, so `git submodule update --remote` silently retrieved different
#     firmware and reported success.
#
# Both are invisible to a compile test on a machine that already has the source.
#
# Usage: scripts/check_source_graph.sh [manifests/fingerprint-v3.yaml]

set -uo pipefail

MANIFEST="${1:-manifests/fingerprint-v3.yaml}"
[[ -f "$MANIFEST" ]] || { echo "FAIL: manifest not found: $MANIFEST" >&2; exit 1; }

RC=0
ok()   { printf '  ok    %s\n' "$*"; }
bad()  { printf '  FAIL  %s\n' "$*"; RC=1; }
warn() { printf '  warn  %s\n' "$*"; }

m() {
    local v
    v="$(sed -n "s/^$1:[[:space:]]*//p" "$MANIFEST" | head -1)"
    printf '%s' "${v%"${v##*[![:space:]]}"}"
}

echo "Source graph check: ${MANIFEST}"
echo
echo "1. every pinned commit is reachable on its declared remote"

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

for entry in "${COMPONENTS[@]}"; do
    IFS=: read -r name pin_key repo_key ref_key <<<"$entry"
    pin="$(m "$pin_key")"; repo="$(m "$repo_key")"; ref="$(m "$ref_key")"
    if [[ -z "$pin" || -z "$repo" || -z "$ref" ]]; then
        bad "${name}: manifest incomplete (pin/repo/ref)"; continue
    fi
    # ls-remote, not `--contains`: containment needs objects we deliberately do
    # not fetch here, and a narrow refspec makes `--contains` silently blind.
    actual="$(git ls-remote "$repo" "$ref" 2>/dev/null | awk '{print $1}' | head -1)"
    if [[ -z "$actual" ]]; then
        bad "${name}: ref ${ref} not found at ${repo}"
    elif [[ "$actual" != "$pin" ]]; then
        bad "${name}: ${ref} is at ${actual:0:12}, manifest pins ${pin:0:12} (ref has moved)"
    else
        ok "${name} ${pin:0:12} == ${ref}"
    fi
done

echo
echo "2. the release tag labels the commit that actually built the release"
# The v3 tag was created AFTER three further commits landed, so it points at
# dac99758 while the shipped binary was built from f53dd006. `git checkout
# <release tag>` therefore hands you source that did not build that release.
# The manifest records the true build commit; this check keeps the discrepancy
# visible instead of letting it rot into folklore.
fw_repo="$(m firmware_repo)"; fw_pin="$(m firmware_source)"; rel_tag="$(m release_tag)"
if [[ -z "$rel_tag" ]]; then
    warn "candidate source manifest has no release tag (expected before promotion)"
else
tag_sha="$(git ls-remote "$fw_repo" "refs/tags/${rel_tag}" 2>/dev/null | awk '{print $1}' | head -1)"
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
echo "3. .gitmodules hygiene"
if [[ -f .gitmodules ]]; then
    if grep -qE '^\s*url\s*=\s*\.\.' .gitmodules; then
        bad "relative submodule url present (resolves against \`origin\`, breaks fresh clones)"
    else
        ok "all submodule urls are absolute"
    fi
else
    warn ".gitmodules not present (not a firmware checkout?)"
fi

if [[ "$(m release_state)" == "candidate" ]] && \
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
fi

echo
echo "4. no local source overrides"
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
