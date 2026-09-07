#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
acquisition_dir="$repository_root/hdl/library/starlink_pss_acquisition"
output_dir="${1:-${repository_root}/build/starlink-pss30-ddc-to-score-xfft-longrun}"
vivado_bin="/opt/Xilinx/Vivado/2022.2/bin/vivado"
compat_lib="/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE"

if [[ ! -x "$vivado_bin" || ! -r "$compat_lib/libtinfo.so.5" ]]; then
  printf '%s\n' \
    'The canonical Vivado 2022.2 binary or compatibility library is unavailable.' >&2
  exit 1
fi

mkdir -p "$output_dir"
output_dir="$(cd "$output_dir" && pwd)"

(
  cd "$output_dir"
  LD_LIBRARY_PATH="$compat_lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" \
    "$vivado_bin" -mode batch -nojournal -nolog \
      -source "$acquisition_dir/simulate_pss30_ddc_to_score_xfft_longrun.tcl" \
      -tclargs "$output_dir" 2>&1 | \
      tee pss30_ddc_to_score_xfft_longrun_transcript.log
)

transcript="$output_dir/pss30_ddc_to_score_xfft_longrun_transcript.log"
if grep -q '^PSS30_DDC_XFFT_LONGRUN_FAULT' "$transcript" ||
   ! grep -q '^PSS30_DDC_XFFT_LONGRUN_PASS' "$transcript"; then
  printf '%s\n' \
    'The 30 MS/s DDC-to-XFFT long-run diagnostic did not produce a clean PASS.' >&2
  exit 1
fi
