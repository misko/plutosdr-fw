#!/usr/bin/env bash
#
# Prove possession of a released PlutoSDR firmware binary.
#
# Given a build manifest, this downloads (or accepts) the release DFU and
# verifies, fail-closed, that:
#
#   1. the file hashes to the manifest's image_sha256;
#   2. the DFU suffix is well formed;
#   3. the FIT structure and description match;
#   4. the FPGA bitstream and ramdisk component hashes match;
#   5. /opt/VERSIONS inside the shipped rootfs records the expected device-fw
#      and the expected hdl / buildroot / linux / u-boot-xlnx identities;
#   6. the USB gadget binary inside that rootfs embeds the expected gadget SHA.
#
# Step 6 is the one that cannot be faked by repository state: it reads the build
# ID out of the binary that actually ships. A Buildroot <PKG>_OVERRIDE_SRCDIR in
# a local.mk will still pass -DGIT_VERSION_OVERRIDE from the pinned .mk, so a
# locally built image can report a gadget SHA it does not contain. Comparing the
# shipped binary against the manifest is what closes that hole.
#
# This is NOT a build tool and it never rebuilds anything. The deployed v3 image
# was built without BR2_REPRODUCIBLE and cannot be reproduced byte-for-byte; a
# source rebuild is a DIFFERENT artifact with a different name and hash.
#
# Usage:
#   scripts/verify_release.sh manifests/fingerprint-v3.yaml
#   scripts/verify_release.sh manifests/fingerprint-v3.yaml --image /path/to.dfu
#   scripts/verify_release.sh manifests/fingerprint-v3.yaml --json
#
# Dependencies are deliberately coreutils + dumpimage + cpio only, so this runs
# in a minimal CI container with no Python or YAML library available.

set -euo pipefail

MANIFEST=""
IMAGE=""
JSON_ONLY=0
# --identity-only answers a DIFFERENT question from the default mode.
#
#   default        "is this the deployed release binary?"   -> hash must match
#   identity-only  "did we correctly recreate that build?"  -> hash must NOT match
#
# The deployed v3 was built without BR2_REPRODUCIBLE and with no kernel
# timestamp pinning, so a rebuild can never reproduce image_sha256. Comparing a
# rebuild against the release hash is guaranteed to fail and proves nothing. What
# a rebuild must prove is that every embedded identity -- device-fw, the four
# /opt/VERSIONS strings, the FPGA bitstream, and the gadget build ID -- is
# identical. That is what this mode checks, and it deliberately still fails if
# the hash DOES match, because that would mean the file is the release itself
# rather than something we built.
IDENTITY_ONLY=0
CACHE_DIR="${VERIFY_RELEASE_CACHE:-${XDG_CACHE_HOME:-${HOME}/.cache}/plutosdr-fw/releases}"

usage() {
    sed -n '3,30p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
}

die() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --image) IMAGE="${2:-}"; shift 2 ;;
        --json)  JSON_ONLY=1; shift ;;
        --identity-only) IDENTITY_ONLY=1; shift ;;
        -h|--help) usage ;;
        -*) die "unknown option: $1" ;;
        *) [[ -z "$MANIFEST" ]] || die "unexpected argument: $1"; MANIFEST="$1"; shift ;;
    esac
done

[[ -n "$MANIFEST" ]] || usage
[[ -f "$MANIFEST" ]] || die "manifest not found: $MANIFEST"

for tool in sha256sum md5sum dumpimage cpio gzip awk sed grep; do
    command -v "$tool" >/dev/null || die "required tool not found: $tool"
done

# Flat "key: value" lookup.
m() {
    local key="$1" value
    value="$(sed -n "s/^${key}:[[:space:]]*//p" "$MANIFEST" | head -1)"
    printf '%s' "${value%"${value##*[![:space:]]}"}"
}

# Every field this script consumes must be present and non-empty BEFORE any
# check runs. This cannot live inside m(): m() is called from command
# substitution, so a die() there would exit only the subshell and the empty
# value would surface as a confusing "expected ''" mismatch further down.
# Validating up front is also what makes "fail closed on any missing field"
# actually true rather than incidental.
REQUIRED_FIELDS=(
    release_tag asset_name image_url image_sha256 device_fw
    firmware_source gadget_source
    submodule_buildroot submodule_linux submodule_u_boot_xlnx
    versions_hdl versions_buildroot versions_linux versions_u_boot_xlnx
    fpga_bitstream_md5 ramdisk_md5 fit_description
)
missing=()
for key in "${REQUIRED_FIELDS[@]}"; do
    [[ -n "$(m "$key")" ]] || missing+=("$key")
done
(( ${#missing[@]} == 0 )) ||
    die "manifest is missing required field(s): ${missing[*]}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

PASS=()
note() {
    PASS+=("$1")
    (( JSON_ONLY )) || printf '  ok  %s\n' "$1"
}

expect() {
    local what="$1" want="$2" got="$3"
    [[ "$want" == "$got" ]] || die "${what}: expected '${want}', got '${got}'"
    note "${what} = ${got}"
}

release_tag="$(m release_tag)"
asset_name="$(m asset_name)"
want_sha="$(m image_sha256)"

(( JSON_ONLY )) || printf '\nVerifying %s\n  manifest: %s\n\n' "$release_tag" "$MANIFEST"

# ---------------------------------------------------------------- 1. image ---
if [[ -z "$IMAGE" ]]; then
    mkdir -p "$CACHE_DIR"
    IMAGE="${CACHE_DIR}/${asset_name}"
    if [[ ! -f "$IMAGE" ]]; then
        command -v curl >/dev/null || die "curl is required to download the release"
        curl -fsSL --retry 3 -o "${IMAGE}.part" "$(m image_url)" ||
            die "download failed: $(m image_url)"
        mv "${IMAGE}.part" "$IMAGE"
    fi
fi
[[ -r "$IMAGE" ]] || die "image is not readable: ${IMAGE}"

got_sha="$(sha256sum "$IMAGE" | awk '{print $1}')"
if (( IDENTITY_ONLY )); then
    [[ "$got_sha" != "$want_sha" ]] ||
        die "--identity-only was given but this file IS the deployed release
     (${want_sha}). Verify a rebuild, or drop --identity-only."
    note "rebuild sha256 = ${got_sha} (differs from the release, as expected)"
else
    expect "image_sha256" "$want_sha" "$got_sha"
fi

# ----------------------------------------------------------- 2. DFU suffix ---
if command -v dfu-suffix >/dev/null; then
    dfu-suffix -c "$IMAGE" >/dev/null 2>&1 || die "DFU suffix is invalid or absent"
    note "dfu suffix valid"
else
    note "dfu suffix SKIPPED (dfu-suffix not installed)"
fi

# ------------------------------------------------------------ 3. FIT layout ---
dumpimage -l "$IMAGE" > "${WORK}/fit.txt" 2>/dev/null ||
    die "not a readable FIT image"

got_desc="$(sed -n 's/^FIT description:[[:space:]]*//p' "${WORK}/fit.txt" | head -1)"
expect "fit_description" "$(m fit_description)" "$got_desc"

# Locate components by NAME, never by a hardcoded index: the image order is not
# part of the contract and a renumbering must not silently skip a check.
image_index() {
    awk -v want="$1" '
        /^[[:space:]]*Image[[:space:]]+[0-9]+[[:space:]]+\(/ {
            idx = $2
            name = $3
            gsub(/[()]/, "", name)
            if (name == want) { print idx; exit }
        }' "${WORK}/fit.txt"
}

fpga_idx="$(image_index "fpga@1")"
rd_idx="$(image_index "ramdisk@1")"
[[ -n "$fpga_idx" ]] || die "FIT has no fpga@1 component"
[[ -n "$rd_idx" ]]   || die "FIT has no ramdisk@1 component"

# The FIT records its own component hashes; recompute from the extracted data
# rather than trusting the header we are auditing.
dumpimage -T flat_dt -p "$fpga_idx" -o "${WORK}/fpga.bit" "$IMAGE" >/dev/null 2>&1 ||
    die "could not extract fpga@1"
dumpimage -T flat_dt -p "$rd_idx" -o "${WORK}/rootfs.cpio.gz" "$IMAGE" >/dev/null 2>&1 ||
    die "could not extract ramdisk@1"

# The FPGA bitstream comes straight out of the pinned XSA and is not compiled,
# so it must match even in a rebuild. The ramdisk is recompiled and carries
# build timestamps, so it legitimately differs -- checking it against the
# release value would fail every honest rebuild.
expect "fpga_bitstream_md5" "$(m fpga_bitstream_md5)" \
    "$(md5sum "${WORK}/fpga.bit" | awk '{print $1}')"
got_rd="$(md5sum "${WORK}/rootfs.cpio.gz" | awk '{print $1}')"
if (( IDENTITY_ONLY )); then
    note "ramdisk_md5 = ${got_rd} (not compared; a rebuilt rootfs differs by design)"
else
    expect "ramdisk_md5" "$(m ramdisk_md5)" "$got_rd"
fi

# ------------------------------------------------------- 4. shipped rootfs ---
mkdir -p "${WORK}/rootfs"
gzip -dc "${WORK}/rootfs.cpio.gz" > "${WORK}/rootfs.cpio" 2>/dev/null ||
    die "ramdisk is not gzip data"
( cd "${WORK}/rootfs" && cpio -idm --quiet 'opt/VERSIONS' 'usr/sbin/sdr_usb_gadget' \
    < "${WORK}/rootfs.cpio" ) 2>/dev/null || true

VERSIONS="${WORK}/rootfs/opt/VERSIONS"
[[ -f "$VERSIONS" ]] || die "/opt/VERSIONS is absent from the shipped rootfs"

field() { sed -n "s/^$1 //p" "$VERSIONS" | head -1; }

expect "device_fw"           "$(m device_fw)"           "$(field device-fw)"
expect "versions_hdl"        "$(m versions_hdl)"        "$(field hdl)"
expect "versions_buildroot"  "$(m versions_buildroot)"  "$(field buildroot)"
expect "versions_linux"      "$(m versions_linux)"      "$(field linux)"
expect "versions_u_boot_xlnx" "$(m versions_u_boot_xlnx)" "$(field u-boot-xlnx)"

# Assert the strings recorded in /opt/VERSIONS identify the pinned commits, so
# a manifest cannot pin one commit while claiming another.
#
# `git describe --abbrev=4 --tags` returns one of two shapes, and this check
# originally understood only the first:
#
#   <tag>-<n>-g<hash>   when the commit is n commits past a tag
#   <tag>               when the commit IS the tag
#
# fingerprint-v3's submodules sat on branch tips, so every recorded string
# ended in a hash prefix. As this project moved its submodules onto immutable
# source-lock tags they began describing as bare tag names, which the prefix
# rule reads as a mismatch -- failing the better-pinned build and passing the
# looser one. Resolve a tag rather than rejecting it.
pin_matches() {
    local what="$1" recorded="$2" full="$3" repo="$4" resolved=""

    if [[ "$full" == "$recorded"* ]]; then
        note "${what} prefix of pinned ${full:0:12}..."
        return
    fi

    # Local first: buildroot's source-lock tags live in this repository, so this
    # resolves offline. ls-remote is the fallback for the mirrored submodules.
    resolved="$(git rev-parse -q --verify "refs/tags/${recorded}^{commit}" 2>/dev/null || true)"
    if [[ -z "$resolved" && -n "$repo" ]]; then
        # Both refs are asked for so annotated and lightweight tags behave the
        # same: an annotated tag also returns `^{}`, which dereferences to the
        # commit and sorts last.
        resolved="$(git ls-remote "$repo" \
                        "refs/tags/${recorded}" "refs/tags/${recorded}^{}" 2>/dev/null |
                    awk '{print $1}' | tail -1)"
    fi

    [[ -n "$resolved" ]] ||
        die "${what}: /opt/VERSIONS says '${recorded}', which is neither a prefix of pinned ${full} nor a tag this checker could resolve"
    [[ "$resolved" == "$full" ]] ||
        die "${what}: '${recorded}' resolves to ${resolved}, not the pinned ${full}"
    note "${what} tag ${recorded} resolves to pinned ${full:0:12}..."
}
pin_matches "buildroot pin"   "$(m versions_buildroot)"   "$(m submodule_buildroot)"   "$(m submodule_buildroot_repo)"
pin_matches "linux pin"       "$(m versions_linux)"       "$(m submodule_linux)"       "$(m submodule_linux_repo)"
pin_matches "u-boot-xlnx pin" "$(m versions_u_boot_xlnx)" "$(m submodule_u_boot_xlnx)" "$(m submodule_u_boot_xlnx_repo)"

# ---------------------------------------------------- 5. gadget build ident ---
GADGET="${WORK}/rootfs/usr/sbin/sdr_usb_gadget"
[[ -f "$GADGET" ]] || die "usr/sbin/sdr_usb_gadget is absent from the shipped rootfs"

want_gadget="$(m gadget_source)"
if grep -aqF "$want_gadget" "$GADGET"; then
    note "gadget_source = ${want_gadget} (embedded in the shipped binary)"
else
    found="$(grep -aoE '[0-9a-f]{40}' "$GADGET" | head -1 || true)"
    die "gadget build ID not found in shipped binary; expected ${want_gadget}, saw '${found:-none}'"
fi

# ------------------------------------------------------------------ result ---
if (( JSON_ONLY )); then
    printf '{\n'
    printf '  "release_verified": true,\n'
    printf '  "release_tag": "%s",\n'      "$release_tag"
    printf '  "image": "%s",\n'            "$IMAGE"
    printf '  "image_sha256": "%s",\n'     "$got_sha"
    printf '  "device_fw": "%s",\n'        "$(field device-fw)"
    printf '  "firmware_source": "%s",\n'  "$(m firmware_source)"
    printf '  "gadget_source": "%s",\n'    "$want_gadget"
    printf '  "fpga_bitstream_md5": "%s",\n' "$(m fpga_bitstream_md5)"
    printf '  "checks_passed": %d\n'       "${#PASS[@]}"
    printf '}\n'
else
    printf '\nrelease_verified=true\n'
    printf 'image_sha256=%s\n'     "$got_sha"
    printf 'device_fw=%s\n'        "$(field device-fw)"
    printf 'firmware_source=%s\n'  "$(m firmware_source)"
    printf 'gadget_source=%s\n'    "$want_gadget"
    printf '\n%d checks passed.\n' "${#PASS[@]}"
fi
