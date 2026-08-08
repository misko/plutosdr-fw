#!/usr/bin/env bash
# Reproducible entry point for the unpromoted gain-series firmware candidate.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="${SPF_GAIN_SERIES_MANIFEST:-${ROOT}/manifests/gain-series-v4-source.yaml}"
MODE="${1:-source-check}"
VIVADO_SETTINGS="${VIVADO_SETTINGS:-/opt/Xilinx/Vivado/2022.2/settings64.sh}"

usage() {
    cat <<'EOF'
Usage: scripts/build_gain_series_candidate.sh MODE

Modes:
  source-check  Verify the pinned source graph; works on any architecture.
  preflight     Verify an x86-64 checkout and all build prerequisites.
  rootfs        Run preflight, then build build/rootfs.cpio.gz.
  image         Run preflight, rebuild the pinned FPGA XSA, then build
                build/pluto.dfu.

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
scripts/check_source_graph.sh "$MANIFEST"
[[ "$MODE" == source-check ]] && exit 0

[[ "$(uname -m)" == x86_64 ]] ||
    fail "firmware builds require x86-64 (this host is $(uname -m))"

dirty="$(git status --porcelain --untracked-files=no)"
[[ -z "$dirty" ]] || fail "tracked firmware checkout is dirty"

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
    awk bash bc bison cmake cpio dfu-suffix dtc flex git gzip make
    openssl patch perl python3 rsync sed sha256sum tar unzip wget zip
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
[[ "$MODE" == preflight ]] && exit 0

if [[ "$MODE" == rootfs ]]; then
    exec make SKIP_LEGAL=1 build/rootfs.cpio.gz
fi

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

exec make SKIP_LEGAL=1 VIVADO_SETTINGS="$VIVADO_SETTINGS" build/pluto.dfu
