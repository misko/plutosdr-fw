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
start_epoch="$(date +%s)"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git show -s --format=%ct HEAD)}"
export KBUILD_BUILD_TIMESTAMP="${KBUILD_BUILD_TIMESTAMP:-$(date -u -d "@${SOURCE_DATE_EPOCH}")}"
export KBUILD_BUILD_USER="${KBUILD_BUILD_USER:-github-actions}"
export KBUILD_BUILD_HOST="${KBUILD_BUILD_HOST:-kalman}"

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
