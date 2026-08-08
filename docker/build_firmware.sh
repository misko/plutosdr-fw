#!/usr/bin/env bash
#
# Clone + compile the PlutoSDR firmware from scratch inside the container.
#
# Everything it needs comes from the network and the manifest; nothing is
# inherited from a developer's machine. That is the whole point -- the deployed
# v3 image was built with two pieces of uncommitted local state (a hand-edited
# buildroot .config selecting a different toolchain, and a local.mk pointing at
# /tmp), and this script exists so that can never silently happen again.
#
# Env (all optional, defaults reproduce the v3 source graph):
#   FW_REPO             firmware repository URL
#   FW_REF              tag/branch/commit to build
#   XSA_URL, XSA_SHA256 pinned FPGA input (never derived from LATEST_TAG)
#   SOURCE_DATE_EPOCH   pin the FIT/rootfs timestamps (see note below)
#   REPRODUCIBLE        1 to enable BR2_REPRODUCIBLE + kernel timestamp pinning
#   JOBS                parallelism, default nproc

set -euo pipefail

FW_REPO="${FW_REPO:-https://github.com/misko/plutosdr-fw.git}"
FW_REF="${FW_REF:-f53dd006c26677a256520b86b7c864100ccd62d2}"
XSA_URL="${XSA_URL:-https://github.com/pgreenland/plutosdr-fw/releases/download/v0.38_plutoplus_with_timestamping/system_top.xsa}"
XSA_SHA256="${XSA_SHA256:-e07af4a31973e332f1c7b19a20b8d9527df6ccf91d3b805db417e0164981be3a}"
REPRODUCIBLE="${REPRODUCIBLE:-0}"
JOBS="${JOBS:-$(nproc)}"
SRC=/build/fw
OUT=/out

log() { printf '\n=== %s ===\n' "$*"; }
die() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

log "clone ${FW_REPO} @ ${FW_REF}"
rm -rf "$SRC"
# Full history and ALL tags, deliberately not shallow: Makefile:113-114 derives
# device-fw and every /opt/VERSIONS entry from `git describe --abbrev=4 --dirty
# --always --tags`. A shallow clone silently yields bare SHAs and the resulting
# image identity will not match the manifest.
git clone --no-checkout "$FW_REPO" "$SRC"
cd "$SRC"
git fetch --tags --force origin
git checkout --detach "$FW_REF"

# Submodules are fetched at the depth the DEPLOYED image was actually built
# with, which is not uniform and is not an optimisation -- it is part of the
# recipe. /opt/VERSIONS records `git describe --abbrev=4 --always --tags` per
# component, so depth changes the recorded string:
#
#   linux, u-boot-xlnx, hdl-quantulum  depth 1  -> bare short SHA (d798b, 1ff04)
#   buildroot                          shallow  -> bare short SHA (f37f)
#   hdl                                FULL     -> dev_prj_2018_r1-1859-gbe89
#
# Only hdl needs full history and tags, because only hdl has a reachable tag.
# A blanket `git submodule update --init --recursive` pulls a ~2.8 GB kernel
# history that is never used, and will OOM a small builder.
sub_clone() {
    local path="$1" url="$2" ref="$3" pin="$4" depth="$5"
    rm -rf "$path"
    if [[ "$depth" == "full" ]]; then
        git clone --quiet "$url" "$path"
        git -C "$path" fetch --quiet --tags origin
        git -C "$path" checkout --quiet --detach "$pin"
    else
        git clone --quiet --depth "$depth" --branch "$ref" "$url" "$path"
    fi
    local got
    got="$(git -C "$path" rev-parse HEAD)"
    [[ "$got" == "$pin" ]] || die "${path}: expected ${pin}, got ${got}"
    echo "  ${path} @ ${got:0:12} ($(git -C "$path" describe --abbrev=4 --dirty --always --tags))"
}

log "fetch submodules at the depths the deployed image used"
sub_clone buildroot     "${SUB_BUILDROOT_URL:-https://github.com/misko/plutosdr-fw.git}" \
    codex/buildroot-gadget-supervisor-v3 f37fe105ff4df531311b0cf85584461fb03e0e4e 1
sub_clone hdl           "${SUB_HDL_URL:-https://github.com/misko/plutosdr-hdl.git}" \
    v0.38_plutoplus_timestamp be89a77d3fd0b344419377fac6fab8cfc7a66ad8 full
sub_clone hdl-quantulum "${SUB_HDLQ_URL:-https://github.com/misko/plutosdr-hdl-quantulum}" \
    main d70102267713f5bbc99805be5f4f08b0a07766cb 1
sub_clone linux         "${SUB_LINUX_URL:-https://github.com/misko/plutosdr-linux.git}" \
    v0.38_plutoplus d798b0d821b85ebd51ecffbfa68d8e4d69b77132 1
sub_clone u-boot-xlnx   "${SUB_UBOOT_URL:-https://github.com/misko/plutosdr-u-boot-xlnx.git}" \
    v0.38_plutoplus 1ff0468e9bea29b0a768a7bf52db8d025c521b9a 1

log "assert the rebuilt identity matches the deployed release"
want_device_fw="${EXPECT_DEVICE_FW:-v0.38-plutoplus-spf-gain-rssi-fingerprint-v2-8-gf53d}"
got_device_fw="$(git describe --abbrev=4 --dirty --always --tags)"
echo "  device-fw: ${got_device_fw}"
[[ "$got_device_fw" == "$want_device_fw" ]] ||
    die "device-fw would be '${got_device_fw}', expected '${want_device_fw}'.
     A '-dirty' suffix means the tree was modified; bare SHAs mean the clone
     lacks tags (never use --depth on the superproject)."


log "guard against local source overrides"
# A Buildroot <PKG>_OVERRIDE_SRCDIR still passes -DGIT_VERSION_OVERRIDE from the
# pinned .mk, so an overridden build produces a binary that REPORTS the pinned
# gadget SHA while containing different code. Refuse to build at all.
mapfile -t strays < <(find . -name local.mk -not -path './.git/*')
(( ${#strays[@]} == 0 )) || die "local.mk present, refusing to build: ${strays[*]}"

# `git describe --dirty` must not see a modified tree, or device-fw gains a
# "-dirty" suffix and stops matching the manifest.
[[ -z "$(git status --porcelain)" ]] || die "source tree is dirty"

log "fetch and verify pinned XSA"
mkdir -p build
if [[ ! -f /cache/system_top.xsa ]]; then
    wget -q -O /cache/system_top.xsa.part "$XSA_URL" || die "XSA download failed"
    mv /cache/system_top.xsa.part /cache/system_top.xsa
fi
got="$(sha256sum /cache/system_top.xsa | awk '{print $1}')"
[[ "$got" == "$XSA_SHA256" ]] || die "XSA sha256 mismatch: got ${got}, want ${XSA_SHA256}"
cp /cache/system_top.xsa build/system_top.xsa
echo "XSA verified: ${got}"

MAKE_ARGS=(TARGET=pluto "XSA_FILE=/cache/system_top.xsa")

log "assert the toolchain kconfig actually resolves to"
# The committed zynq_pluto_defconfig sets BR2_TOOLCHAIN_EXTERNAL_LINARO_ARM
# (gcc 7.3.1, arm-linux-gnueabihf). On aarch64 that option is unselectable, so
# kconfig silently falls back to BR2_TOOLCHAIN_EXTERNAL_ARM_ARM (ARM GNU
# 10.3-2021.07, arm-none-linux-gnueabihf) -- which is what actually built the
# deployed v3 image. On x86_64 the Linaro option IS selectable and wins, so the
# SAME SOURCE builds with a DIFFERENT COMPILER depending on host architecture.
#
# That divergence is silent and would otherwise only surface as a mysteriously
# different binary. Resolve the config early and refuse to continue unless the
# toolchain matches the one recorded in the manifest.
make -C buildroot ARCH=arm zynq_pluto_defconfig >/dev/null
selected="$(sed -n 's/^BR2_TOOLCHAIN_EXTERNAL_PREFIX="\(.*\)"$/\1/p' buildroot/.config | head -1)"
want_prefix="${EXPECT_TOOLCHAIN_PREFIX:-arm-none-linux-gnueabihf}"
echo "  host arch:        $(uname -m)"
echo "  toolchain prefix: ${selected}"
if [[ "$selected" != "$want_prefix" ]]; then
    die "toolchain mismatch: kconfig resolved to '${selected}' but the manifest
     requires '${want_prefix}'. On x86_64 this happens because the committed
     defconfig still selects BR2_TOOLCHAIN_EXTERNAL_LINARO_ARM. Pin
     BR2_TOOLCHAIN_EXTERNAL_ARM_ARM in configs/zynq_pluto_defconfig, or build on
     aarch64, which is the architecture that produced the deployed release."
fi

if [[ "${DRY_RUN:-0}" == "1" ]]; then
    log "DRY_RUN=1: pull and every pre-build gate passed; stopping before the compile"
    exit 0
fi

if [[ "$REPRODUCIBLE" == "1" ]]; then
    log "timestamp pinning (partial reproducibility)"
    : "${SOURCE_DATE_EPOCH:=$(git log -1 --format=%ct)}"
    export SOURCE_DATE_EPOCH
    export KBUILD_BUILD_TIMESTAMP="$(date -u -d "@${SOURCE_DATE_EPOCH}" 2>/dev/null || date -u)"
    export KBUILD_BUILD_USER=builder
    export KBUILD_BUILD_HOST=container
    echo "  SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}"
    echo "  KBUILD_BUILD_TIMESTAMP/_USER/_HOST pinned"

    # Be honest about what this flag does NOT do. BR2_REPRODUCIBLE cannot be
    # enabled from here: the Makefile's rootfs target re-runs
    # `make -C buildroot ARCH=arm zynq_pluto_defconfig` immediately before
    # `make -C buildroot all`, which overwrites any .config edit made now.
    # Enabling it genuinely requires committing BR2_REPRODUCIBLE=y to
    # configs/zynq_pluto_defconfig -- which changes the buildroot commit, hence
    # the pin, hence device-fw. That belongs on the next release line.
    #
    # Buildroot also documents BR2_REPRODUCIBLE as restricted to builds using
    # the same output directory, which is why this image fixes the path at
    # /build rather than building wherever it happens to be invoked.
    if grep -q '^BR2_REPRODUCIBLE=y' buildroot/.config 2>/dev/null; then
        echo "  BR2_REPRODUCIBLE=y (from the committed defconfig)"
    else
        echo "  WARNING: BR2_REPRODUCIBLE is NOT enabled and cannot be set here."
        echo "           Timestamps are pinned; build paths and per-package"
        echo "           nondeterminism are not. Two builds may still differ."
        echo "           To enable it, commit BR2_REPRODUCIBLE=y to"
        echo "           configs/zynq_pluto_defconfig on the next release line."
    fi
fi

# SKIP_LEGAL=1 looks like a harmless way to save time. It is not: the Makefile
# guards BOTH `make -C buildroot legal-info` AND the copy of the generated
# LICENSE.html into board/pluto/msd/ behind it, and the mass-storage image lists
# LICENSE.html as a required file. Skipping it fails late, in target-finalize,
# after the entire kernel and every package have already been compiled:
#
#   ERROR: file(LICENSE.html): stat(.../board/pluto/msd/LICENSE.html) failed
#   ERROR: vfat(boot.vfat): could not setup LICENSE.html
#
# Verified the hard way. Refuse it rather than burn another hour.
[[ "${SKIP_LEGAL:-0}" != "1" ]] ||
    die "SKIP_LEGAL=1 is not a supported configuration; legal-info generates
     LICENSE.html which the mass-storage image requires, and the build fails
     in target-finalize after everything else has compiled."

log "build build/pluto.dfu with ${JOBS} jobs"
# Deliberately NOT `make all`: that drags in zip-all and legal-info, neither of
# which is part of the deployed artifact.
make "${MAKE_ARGS[@]}" -j"${JOBS}" build/pluto.dfu

[[ -f build/pluto.dfu ]] || die "build produced no build/pluto.dfu"

log "record what was built"
mkdir -p "$OUT"
sha="$(sha256sum build/pluto.dfu | awk '{print $1}')"
short="$(git rev-parse --short=12 HEAD)"
# Never reuse the canonical release asset name: a source rebuild is a DIFFERENT
# artifact from the deployed binary, even when every identity inside matches.
cp build/pluto.dfu "${OUT}/fingerprint-source-rebuild-${short}.dfu"

{
    printf '{\n'
    printf '  "firmware_repo": "%s",\n'   "$FW_REPO"
    printf '  "firmware_ref": "%s",\n'    "$FW_REF"
    printf '  "firmware_commit": "%s",\n' "$(git rev-parse HEAD)"
    printf '  "output_sha256": "%s",\n'   "$sha"
    printf '  "host_arch": "%s",\n'       "$(uname -m)"
    printf '  "reproducible": %s,\n'      "$([[ "$REPRODUCIBLE" == 1 ]] && echo true || echo false)"
    printf '  "source_date_epoch": "%s",\n' "${SOURCE_DATE_EPOCH:-unset}"
    printf '  "xsa_sha256": "%s",\n'      "$XSA_SHA256"
    printf '  "submodules": {\n'
    git submodule status --recursive | awk '{gsub(/^[-+ ]/,"",$1); printf "    \"%s\": \"%s\"%s\n", $2, $1, (NR<5?",":"")}'
    printf '  }\n}\n'
} > "${OUT}/build-provenance-${short}.json"

log "done"
echo "output:  ${OUT}/fingerprint-source-rebuild-${short}.dfu"
echo "sha256:  ${sha}"
cat "${OUT}/build-provenance-${short}.json"
