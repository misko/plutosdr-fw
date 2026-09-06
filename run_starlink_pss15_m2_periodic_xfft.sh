#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
acquisition_dir="$repository_root/hdl/library/starlink_pss_acquisition"
vector_dir="$repository_root/hdl/library/axi_starlink_pss_periodic_injector/tb"
output_dir="${1:-${repository_root}/build/starlink-pss15-m2-periodic-xfft}"
simulation_dir="$output_dir/simulation"
vivado_bin="/opt/Xilinx/Vivado/2022.2/bin/vivado"
compat_lib="/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE"

if [[ ! -x "$vivado_bin" || ! -r "$compat_lib/libtinfo.so.5" ]]; then
  printf '%s\n' \
    'The canonical Vivado 2022.2 binary or compatibility library is unavailable.' >&2
  exit 1
fi

mkdir -p "$simulation_dir"
simulation_dir="$(cd "$simulation_dir" && pwd)"

(
  cd "$simulation_dir"
  LD_LIBRARY_PATH="$compat_lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" \
    "$vivado_bin" -mode batch -nojournal -nolog \
      -source "$acquisition_dir/simulate_m2_periodic_xfft.tcl" \
      -tclargs "$simulation_dir" "$vector_dir" 2>&1 | \
      tee m2_periodic_xfft_transcript.log
)

transcript="$simulation_dir/m2_periodic_xfft_transcript.log"
if grep -q 'M2_PERIODIC_XFFT_FAIL' "$transcript" ||
   ! grep -q 'M2_PERIODIC_XFFT_PASS .*unique_peak=32 .*zero_denominators=0' \
     "$transcript"; then
  printf '%s\n' 'The M2 periodic XFFT replay did not produce a clean PASS.' >&2
  exit 1
fi
