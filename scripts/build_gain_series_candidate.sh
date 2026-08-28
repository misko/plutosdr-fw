#!/usr/bin/env bash
# Reproducible entry point for the unpromoted gain-series firmware candidate.

set -euo pipefail

# Buildroot's reproducible source archives include permission bits. Normalize
# the process mask so a secure caller umask (for example 0077) cannot change
# otherwise identical archive hashes.
umask 0022

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="${SPF_GAIN_SERIES_MANIFEST:-${ROOT}/manifests/libiio-frame-metadata-v5-source.yaml}"
MODE="${1:-source-check}"
VIVADO_SETTINGS="${VIVADO_SETTINGS:-/opt/Xilinx/Vivado/2022.2/settings64.sh}"
BUILDROOT_PRIMARY_SITE="${BR2_PRIMARY_SITE:-https://sources.buildroot.net}"
BUILDROOT_GNU_MIRROR="${BR2_GNU_MIRROR:-https://ftpmirror.gnu.org}"
BUILDROOT_BACKUP_SITE="${BR2_BACKUP_SITE:-https://sources.buildroot.net}"

buildroot_make_args=(
    "BR2_PRIMARY_SITE=${BUILDROOT_PRIMARY_SITE}"
    "BR2_GNU_MIRROR=${BUILDROOT_GNU_MIRROR}"
    "BR2_BACKUP_SITE=${BUILDROOT_BACKUP_SITE}"
)
if [[ -n "${BR2_DL_DIR:-}" ]]; then
    [[ "$BR2_DL_DIR" == /* ]] || {
        printf 'FAIL: BR2_DL_DIR must be absolute: %s\n' "$BR2_DL_DIR" >&2
        exit 1
    }
    buildroot_make_args+=("BR2_DL_DIR=${BR2_DL_DIR}")
fi

usage() {
    cat <<'EOF'
Usage: scripts/build_gain_series_candidate.sh MODE

Modes:
  source-check  Verify the pinned source graph; works on any architecture.
  preflight     Verify an x86-64 checkout and all build prerequisites.
  rootfs        Run preflight, then build build/rootfs.cpio.gz.
  image         Run preflight, rebuild the pinned FPGA XSA, then build
                build/pluto.dfu and build/pluto.frm from the same FIT image.

The script never flashes a radio. RAM boot and promotion are separate,
explicit hardware gates.
EOF
}

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

case "$MODE" in
    source-check|preflight|rootfs|image) ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; fail "unknown mode: ${MODE}" ;;
esac

cd "$ROOT"
[[ -f "$MANIFEST" ]] || fail "manifest not found: ${MANIFEST}"
manifest_name="$(basename -- "$MANIFEST")"
case "$manifest_name" in
tandem-agc-v8-rc5-source.yaml | tandem-agc-v8-rc6-source.yaml | tandem-agc-v8-rc7-source.yaml | tandem-agc-v8-rc8-source.yaml | tandem-agc-v8-rc9-source.yaml | tandem-agc-v8-rc10-source.yaml | tandem-agc-v8-rc11-source.yaml | tandem-agc-v8-rc12-source.yaml | tandem-agc-v8-rc13-source.yaml | tandem-agc-v8-rc14-source.yaml | tandem-agc-v8-rc15-source.yaml | tandem-agc-v8-rc16-source.yaml | tandem-agc-v8-rc17-source.yaml | tandem-agc-v8-rc18-source.yaml | tandem-agc-v8-rc19-source.yaml | tandem-agc-v8-rc20-source.yaml | tandem-agc-v8-rc21-source.yaml | tandem-agc-v8-rc22-source.yaml | tandem-agc-v8-rc23-source.yaml | tandem-agc-v8-rc24-source.yaml | tandem-agc-v8-rc25-source.yaml | tandem-agc-v8-rc26-source.yaml | tandem-agc-v8-rc27-source.yaml | tandem-agc-v8-rc28-source.yaml | tandem-agc-v8-rc29-source.yaml | tandem-agc-v8-rc30-source.yaml | tandem-agc-v8-rc31-source.yaml | tandem-agc-v8-rc32-source.yaml | tandem-agc-v8-source.yaml | metadata-timeout-main-v1-source.yaml | single-rx-metadata-rc1-source.yaml | ddr-burst-v1-rc1-source.yaml | ddr-burst-v1-rc2-source.yaml)
    canonical_manifest="${ROOT}/manifests/${manifest_name}"
    [[ "$(realpath -- "$MANIFEST")" == "$canonical_manifest" ]] ||
        fail "protected manifest must use the canonical repository path: ${canonical_manifest}"
    git --no-replace-objects show "HEAD:manifests/${manifest_name}" |
        cmp -s - "$canonical_manifest" ||
        fail "protected manifest differs from its committed HEAD blob"
    ;;
esac
scripts/check_source_graph.sh "$MANIFEST"
[[ "$MODE" == source-check ]] && exit 0

[[ "$(uname -m)" == x86_64 ]] ||
    fail "firmware builds require x86-64 (this host is $(uname -m))"

dirty="$(git status --porcelain --untracked-files=all)"
[[ -z "$dirty" ]] || fail "firmware checkout has tracked or untracked source changes"

submodule_error=0
while IFS= read -r line; do
    marker="${line:0:1}"
    if [[ "$marker" == "-" || "$marker" == "+" || "$marker" == "U" ]]; then
        printf 'FAIL: submodule is not at its pinned gitlink: %s\n' "$line" >&2
        submodule_error=1
    fi
done < <(git submodule status --recursive)
(( submodule_error == 0 )) ||
    fail "run git submodule sync --recursive && git submodule update --init --recursive, then retry"

required=(
    awk bash bc bison cmake cpio dfu-suffix dtc dumpimage file flex git gzip
    iverilog make openssl patch perl python3 rsync sed sha256sum tar unzip vvp
    wget zip
)
missing=()
for command_name in "${required[@]}"; do
    command -v "$command_name" >/dev/null 2>&1 || missing+=("$command_name")
done
(( ${#missing[@]} == 0 )) || fail "missing commands: ${missing[*]}"

available_kib="$(df -Pk "$ROOT" | awk 'NR==2 {print $4}')"
minimum_kib=$((40 * 1024 * 1024))
(( available_kib >= minimum_kib )) ||
    fail "less than 40 GiB free in the firmware workspace"

if [[ "$MODE" == image ]]; then
    [[ -r "$VIVADO_SETTINGS" ]] ||
        fail "Vivado settings not readable: ${VIVADO_SETTINGS}"
    vivado_version="$({
        source "$VIVADO_SETTINGS"
        vivado -version
    } | head -1)"
    [[ "$vivado_version" == *"v2022.2"* ]] ||
        fail "Vivado 2022.2 required; got: ${vivado_version}"
fi

printf 'Preflight passed: mode=%s manifest=%s\n' "$MODE" "$MANIFEST"
printf 'Buildroot sources: cache=%s primary=%s gnu=%s backup=%s\n' \
    "${BR2_DL_DIR:-${ROOT}/buildroot/dl}" \
    "$BUILDROOT_PRIMARY_SITE" "$BUILDROOT_GNU_MIRROR" \
    "$BUILDROOT_BACKUP_SITE"
[[ "$MODE" == preflight ]] && exit 0

if [[ "$MODE" == rootfs ]]; then
    exec make "${buildroot_make_args[@]}" build/rootfs.cpio.gz
fi

# Fetch and hash-check the selected Buildroot sources before spending time in
# Vivado. The subsequent firmware make receives the same command-line values,
# which override this older Buildroot tree's plain-HTTP Kconfig defaults.
make -C "$ROOT/buildroot" ARCH=arm "${buildroot_make_args[@]}" \
    zynq_pluto_defconfig
make -C "$ROOT/buildroot" "${buildroot_make_args[@]}" source

(
    source "$VIVADO_SETTINGS"
    make -C "$ROOT/hdl/projects/pluto" clean
    make -C "$ROOT/hdl/projects/pluto"
)
candidate_xsa="$ROOT/hdl/projects/pluto/pluto.sdk/system_top.xsa"
[[ -r "$candidate_xsa" ]] ||
    fail "candidate HDL build did not produce ${candidate_xsa}"
mkdir -p "$ROOT/build"
cp "$candidate_xsa" "$ROOT/build/system_top.xsa"
printf 'Candidate FPGA XSA: '
sha256sum "$ROOT/build/system_top.xsa"

# Pass the version pin on the command line rather than relying on the
# environment, so it wins over the Makefile's default unconditionally. Empty
# means "derive it from git describe", which is what every development build
# wants; a release build sets it. See the RELEASE_VERSION comment in Makefile.
exec make "${buildroot_make_args[@]}" \
    RELEASE_VERSION="${RELEASE_VERSION:-}" \
    VIVADO_SETTINGS="$VIVADO_SETTINGS" \
    build/pluto.dfu build/pluto.frm
