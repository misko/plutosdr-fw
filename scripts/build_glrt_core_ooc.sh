#!/usr/bin/env bash
# Standalone resource investigation only; never opens a radio or deploys.
set -euo pipefail
if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo 'usage: build_glrt_core_ooc.sh RATE_HZ NEW_OUTPUT_DIRECTORY [ddc|correlator|score|pilot-bank|acquisition|receiver]' >&2
  exit 2
fi
case "$1" in 2500000|5000000|10000000|25000000|60000000) ;; *) exit 2 ;; esac
core=${3:-ddc}
case "$core" in ddc|correlator|score|pilot-bank|acquisition|receiver) ;; *) exit 2 ;; esac
repository=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
output=$(realpath -m "$2")
if [[ -e "$output" ]]; then
  echo "evidence directory already exists: $output" >&2
  exit 2
fi
mkdir -p "$output"
cd "$repository"
# Capture inputs before tool startup, then reject even a successful route if
# any of those sources changed while Vivado was running.
rg --files hdl/library/starlink_glrt -g '*.v' -g '*.mem' -g '*.json' -g '*.tcl' \
  | LC_ALL=C sort | xargs -d '\n' sha256sum >"$output/source_before.sha256"
sha256sum scripts/build_glrt_core_ooc.sh >>"$output/source_before.sha256"
set +u
source /opt/Xilinx/Vivado/2022.2/settings64.sh
set -u
export LD_LIBRARY_PATH="/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE:${LD_LIBRARY_PATH:-}"
arguments=("$1" "$output")
if [[ "$core" != ddc ]]; then arguments+=("$core"); fi
if nice -n 10 vivado -mode batch -notrace -log "$output/vivado.log" \
  -journal "$output/vivado.jou" \
  -source hdl/library/starlink_glrt/synthesize_ddc_ooc.tcl \
  -tclargs "${arguments[@]}" >"$output/console.log" 2>&1; then
  vivado_status=0
else
  vivado_status=$?
fi
sha256sum --check "$output/source_before.sha256" >"$output/source_validation.log" 2>&1
test "$vivado_status" -eq 0
# Some Vivado startup failures exit zero without executing Tcl.
test -s "$output/summary.txt"
rg -q '^internal_timing_pass=1$' "$output/summary.txt"
