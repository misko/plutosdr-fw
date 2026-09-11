#!/usr/bin/env bash
# Build one committed GLRT-only board image in a new independent HDL checkout.
# This script never opens, configures or deploys to a radio.
set -euo pipefail
if [[ $# -lt 2 || $# -gt 4 ]]; then
  echo 'usage: build_glrt_board.sh RATE_HZ NEW_OUTPUT_DIRECTORY [--native-refinement|--native-lean|--native-scheduled|--local-search NETLIST_DIRECTORY]' >&2
  exit 2
fi
case "$1" in 2500000|5000000|10000000|25000000|60000000) ;; *) exit 2 ;; esac
native_refinement=0
legacy_scorer=1
native_schedule=0
local_search=0
local_netlist=''
if [[ $# -eq 4 ]]; then
  if [[ "$3" != --local-search || "$1" != 2500000 ]]; then
    echo 'local search requires 2500000 Hz and its netlist directory' >&2
    exit 2
  fi
  local_search=1
  legacy_scorer=0
  local_netlist=$(realpath "$4")
  test -s "$local_netlist/starlink_glrt_local_control.dcp"
  (cd "$local_netlist" && sha256sum --status -c outputs.sha256)
  sha256sum --status -c "$local_netlist/source-hashes.txt"
elif [[ $# -eq 3 ]]; then
  if [[ ( "$3" != --native-refinement && "$3" != --native-lean && "$3" != --native-scheduled ) || "$1" != 60000000 ]]; then
    echo 'native profiles require 60000000 Hz and an explicit native build selection' >&2
    exit 2
  fi
  native_refinement=1
  if [[ "$3" == --native-lean || "$3" == --native-scheduled ]]; then legacy_scorer=0; fi
  if [[ "$3" == --native-scheduled ]]; then native_schedule=1; fi
fi
repository=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
output=$(realpath -m "$2")
if [[ -e "$output" ]]; then
  echo "evidence directory already exists: $output" >&2
  exit 2
fi
git -C "$repository/hdl" diff --quiet
git -C "$repository/hdl" diff --cached --quiet
hdl_commit=$(git -C "$repository/hdl" rev-parse HEAD)
mkdir -p "$output"
git clone --shared --no-checkout "$repository/hdl" "$output/hdl" >"$output/checkout.log" 2>&1
git -C "$output/hdl" checkout --detach "$hdl_commit" >>"$output/checkout.log" 2>&1
printf '%s\n' "$hdl_commit" >"$output/hdl_commit.txt"
printf '%s\n' "$1" >"$output/source_rate_hz.txt"
printf '%s\n' "$native_refinement" >"$output/native_refinement.txt"
printf '%s\n' "$legacy_scorer" >"$output/legacy_scorer.txt"
printf '%s\n' "$native_schedule" >"$output/native_schedule.txt"
printf '%s\n' "$local_search" >"$output/local_search.txt"
if [[ "$local_search" == 1 ]]; then
  mkdir "$output/local-netlist"
  cp "$local_netlist/starlink_glrt_local_control.edf" "$local_netlist/starlink_glrt_local_control_stub.v" \
    "$local_netlist/starlink_glrt_local_control.dcp" "$local_netlist/source-hashes.txt" \
    "$local_netlist/outputs.sha256" "$output/local-netlist/"
  local_netlist="$output/local-netlist"
  (cd "$local_netlist" && sha256sum --status -c outputs.sha256)
fi
git -C "$repository" rev-parse HEAD >"$output/firmware_parent_commit.txt"
sha256sum "$repository/scripts/build_glrt_board.sh" >"$output/build_script.sha256"
export STARLINK_GLRT_RATE_HZ="$1"
export STARLINK_GLRT_NATIVE_REFINEMENT="$native_refinement"
export STARLINK_GLRT_LEGACY_SCORER="$legacy_scorer"
export STARLINK_GLRT_NATIVE_SCHEDULE="$native_schedule"
export STARLINK_GLRT_LOCAL_SEARCH="$local_search"
export STARLINK_GLRT_LOCAL_NETLIST="$local_netlist"
export ADI_HDL_DIR="$output/hdl"
export ADI_USE_OOC_SYNTHESIS=n
export ADI_MAX_OOC_JOBS=4
unset ADI_PROJECT_DIR ADI_SKIP_SYNTHESIS ADI_IGNORE_VERSION_CHECK
set +u
source /opt/Xilinx/Vivado/2022.2/settings64.sh
set -u
export LD_LIBRARY_PATH="/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE:${LD_LIBRARY_PATH:-}"
if nice -n 10 make -C "$output/hdl/projects/pluto" >"$output/build.log" 2>&1; then
  build_status=0
else
  build_status=$?
fi
printf '%s\n' "$build_status" >"$output/build_exit_code.txt"
git -C "$output/hdl" diff --exit-code >"$output/source_validation.log"
test "$build_status" -eq 0
test -s "$output/hdl/projects/pluto/pluto.sdk/system_top.xsa"
test -s "$output/hdl/projects/pluto/pluto.runs/impl_1/system_top.bit"
# The ADI flow rejects violated timing before producing the normal XSA name.
# Additional implemented-netlist/CDC reports are still required for deployment.
sha256sum "$output/hdl/projects/pluto/pluto.sdk/system_top.xsa" \
  "$output/hdl/projects/pluto/pluto.runs/impl_1/system_top.bit" >"$output/outputs.sha256"
