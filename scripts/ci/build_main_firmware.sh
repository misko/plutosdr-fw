#!/usr/bin/env bash
# Trusted post-merge entry point for the Kalman GitHub Actions runner.

set -euo pipefail
umask 0022

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARTIFACT_ROOT="${1:-}"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

[[ -n "$ARTIFACT_ROOT" ]] ||
    fail "usage: scripts/ci/build_main_firmware.sh /absolute/artifact/directory"
[[ "$ARTIFACT_ROOT" == /* ]] || fail "artifact directory must be absolute"

artifact_real="$(realpath -m "$ARTIFACT_ROOT")"
root_real="$(realpath "$ROOT")"
[[ "$artifact_real" != "$root_real" && "$artifact_real" != "$root_real"/* ]] ||
    fail "artifact directory must be outside the firmware checkout"

mkdir -p "$artifact_real"
[[ -z "$(find "$artifact_real" -mindepth 1 -maxdepth 1 -print -quit)" ]] ||
    fail "artifact directory is not empty: $artifact_real"

cd "$ROOT"

# Vivado's make wrapper writes only a one-line pointer to pluto_vivado.log on
# failure. Preserve the underlying logs before the Actions workspace can be
# cleaned; otherwise the uploaded outer transcript cannot explain the build.
collect_failure_diagnostics() {
    local status=$?
    local file_list="$artifact_real/build-diagnostics-files.bin"
    local archive="$artifact_real/vivado-build-diagnostics.tar.gz"

    trap - EXIT
    if (( status != 0 )); then
        find hdl/projects/pluto build \
            -type f \
            \( -name '*.log' -o -name '*.jou' -o -name '*.rpt' \
               -o -name '*.str' -o -name '*.pb' -o -name '*.tcl' \) \
            -print0 2>/dev/null > "$file_list" || true
        if [[ -s "$file_list" ]]; then
            tar --null --files-from="$file_list" -czf "$archive" || true
        fi
        unlink "$file_list" 2>/dev/null || true
    fi
    exit "$status"
}
trap collect_failure_diagnostics EXIT

start_epoch="$(date +%s)"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git show -s --format=%ct HEAD)}"
export KBUILD_BUILD_TIMESTAMP="${KBUILD_BUILD_TIMESTAMP:-$(date -u -d "@${SOURCE_DATE_EPOCH}")}"
export KBUILD_BUILD_USER="${KBUILD_BUILD_USER:-github-actions}"
export KBUILD_BUILD_HOST="${KBUILD_BUILD_HOST:-kalman}"
export BR2_DL_DIR="${BR2_DL_DIR:-/opt/actions-runner-plutosdr-fw/cache/buildroot-dl}"
export BR2_PRIMARY_SITE="${BR2_PRIMARY_SITE:-https://sources.buildroot.net}"
export BR2_GNU_MIRROR="${BR2_GNU_MIRROR:-https://ftpmirror.gnu.org}"
export BR2_BACKUP_SITE="${BR2_BACKUP_SITE:-https://sources.buildroot.net}"

[[ "$BR2_DL_DIR" == /* ]] || fail "BR2_DL_DIR must be absolute"
install -d -m 0755 "$BR2_DL_DIR"
[[ -r "$BR2_DL_DIR" && -w "$BR2_DL_DIR" && -x "$BR2_DL_DIR" ]] ||
    fail "Buildroot cache is not accessible: $BR2_DL_DIR"
printf 'Persistent Buildroot cache: %s\n' "$BR2_DL_DIR"

scripts/test_pluto_pstore_layout.sh \
	2>&1 | tee "$artifact_real/pstore-layout.log"
scripts/test_pluto_cma_layout.sh \
	2>&1 | tee "$artifact_real/cma-layout.log"
scripts/test_tandem_acquire_sequence.sh \
    2>&1 | tee "$artifact_real/tandem-acquire-sequence.log"
scripts/test_tandem_detector_latch_clear.sh \
    2>&1 | tee "$artifact_real/tandem-detector-latch-clear.log"
scripts/test_winbond_uid_fixup.sh \
    2>&1 | tee "$artifact_real/winbond-uid-fixup.log"
buildroot/board/pluto/test_pluto_mute_tx.sh \
    2>&1 | tee "$artifact_real/boot-tx-mute.log"
buildroot/board/pluto/test_pluto_boot_safety.sh \
    2>&1 | tee "$artifact_real/boot-safety.log"
buildroot/board/pluto/test_pluto_read_identity.sh \
    2>&1 | tee "$artifact_real/identity-reader.log"
scripts/build_gain_series_candidate.sh source-check \
    2>&1 | tee "$artifact_real/source-check.log"
scripts/build_gain_series_candidate.sh preflight \
    2>&1 | tee "$artifact_real/preflight.log"
TMPDIR="$artifact_real" scripts/test_gain_series_hdl.sh \
    2>&1 | tee "$artifact_real/hdl-simulation.log"
scripts/build_gain_series_candidate.sh image \
    2>&1 | tee "$artifact_real/image-build.log"

end_epoch="$(date +%s)"
export CI_BUILD_DURATION_SECONDS="$((end_epoch - start_epoch))"
scripts/ci/package_main_firmware.sh "$artifact_real"
