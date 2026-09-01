#!/usr/bin/env bash
set -euo pipefail

head_ref=${1:?usage: check_firmware_merge_guard.sh HEAD_REF [TREE]}
tree=${2:-.}

case "$head_ref" in
  *do-not-merge*|*-dnm-*|dnm-*|*-dnm)
    echo "refusing firmware-main promotion from experimental branch: $head_ref" >&2
    exit 1
    ;;
esac

if [[ -e "$tree/DO_NOT_MERGE_INTO_FIRMWARE_MAIN" ]]; then
  echo 'refusing firmware-main promotion: repository marker is present' >&2
  exit 1
fi

manifest_marker=$(find "$tree/manifests" -maxdepth 1 -type f \
  \( -name '*-dnm-*' -o -name '*do-not-merge*' \) -print -quit 2>/dev/null || true)
if [[ -n "$manifest_marker" ]]; then
  echo "refusing firmware-main promotion: experimental manifest $manifest_marker" >&2
  exit 1
fi

echo "firmware-main merge guard passed for $head_ref"
