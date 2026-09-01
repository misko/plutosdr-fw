#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
guard="$script_dir/check_firmware_merge_guard.sh"
fixture=$(mktemp -d)
trap 'rm -rf -- "$fixture"' EXIT
mkdir -p "$fixture/manifests"

"$guard" codex/ordinary-firmware-change "$fixture"

if "$guard" codex/starlink-rx-only-do-not-merge "$fixture"; then
  echo 'guard accepted a do-not-merge head ref' >&2
  exit 1
fi

touch "$fixture/DO_NOT_MERGE_INTO_FIRMWARE_MAIN"
if "$guard" codex/renamed-experiment "$fixture"; then
  echo 'guard accepted the repository marker' >&2
  exit 1
fi
rm "$fixture/DO_NOT_MERGE_INTO_FIRMWARE_MAIN"

touch "$fixture/manifests/example-dnm-v1-source.yaml"
if "$guard" codex/renamed-experiment "$fixture"; then
  echo 'guard accepted an experimental manifest marker' >&2
  exit 1
fi

echo 'PASS firmware-main merge guard negative tests'
