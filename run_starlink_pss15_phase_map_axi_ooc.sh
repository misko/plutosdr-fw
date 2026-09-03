#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hdl_root="$repository_root/hdl"
bridge_relative="library/axi_starlink_pss_phase_map"
bridge="$hdl_root/$bridge_relative"
hdl_commit="e2e1b87fccfb7efbeb3612e2a3b5a0fea919ba93"
output_dir="${1:-${repository_root}/build/starlink-pss15-phase-map-axi-ooc}"

if [[ "$(git -C "$hdl_root" rev-parse HEAD)" != "$hdl_commit" ]]; then
  printf '%s\n' "The HDL checkout is not the frozen phase-map AXI checkpoint." >&2
  exit 1
fi
if ! git -C "$hdl_root" diff --quiet "$hdl_commit" -- "$bridge_relative" ||
   ! git -C "$hdl_root" diff --cached --quiet "$hdl_commit" -- "$bridge_relative"; then
  printf '%s\n' "The frozen phase-map AXI source directory has local changes." >&2
  exit 1
fi

exec "$bridge/run_ooc.sh" "$output_dir"
