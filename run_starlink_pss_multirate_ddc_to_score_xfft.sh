#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
rate_msps="${1:-}"
output_dir="${2:-${repository_root}/build/starlink-pss${rate_msps}-ddc-to-score-xfft}"
acquisition_dir="$repository_root/hdl/library/starlink_pss_acquisition"
vivado_bin="/opt/Xilinx/Vivado/2022.2/bin/vivado"
compat_lib="/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE"

case "$rate_msps" in
30|60) ;;
*)
  printf '%s\n' 'usage: run_starlink_pss_multirate_ddc_to_score_xfft.sh {30|60} [OUTPUT]' >&2
  exit 2
  ;;
esac

if [[ ! -x "$vivado_bin" || ! -r "$compat_lib/libtinfo.so.5" ]]; then
  printf '%s\n' \
    'The canonical Vivado 2022.2 binary or compatibility library is unavailable.' >&2
  exit 1
fi
command -v uv >/dev/null 2>&1 || {
  printf '%s\n' 'uv is required to create the isolated NumPy vector environment.' >&2
  exit 1
}

vector_dir="$output_dir/vectors"
simulation_dir="$output_dir/simulation"
mkdir -p "$vector_dir" "$simulation_dir"
output_dir="$(cd "$output_dir" && pwd)"
vector_dir="$(cd "$vector_dir" && pwd)"
simulation_dir="$(cd "$simulation_dir" && pwd)"

generator="tools/generate_starlink_pss${rate_msps}_ddc_xfft_vectors.py"
cd "$repository_root"
uv run --with numpy python "$generator" "$vector_dir" 2>&1 | \
  tee "$output_dir/vector-generation.log"

grep -q "STARLINK_PSS${rate_msps}_DDC_XFFT_VECTORS_PASS" \
  "$output_dir/vector-generation.log" || {
    printf '%s\n' "The ${rate_msps} MS/s vector generator did not produce its PASS signature." >&2
    exit 1
  }

(
  cd "$simulation_dir"
  LD_LIBRARY_PATH="$compat_lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" \
    "$vivado_bin" -mode batch -nojournal -nolog \
      -source "$acquisition_dir/simulate_pss30_ddc_to_score_xfft.tcl" \
      -tclargs "$simulation_dir" "$vector_dir" "$rate_msps" 2>&1 | \
      tee ddc_to_score_xfft_transcript.log
)

transcript="$simulation_dir/ddc_to_score_xfft_transcript.log"
if grep -q '^PSS_DDC_XFFT_FAIL' "$transcript" ||
   ! grep -q "^PSS_DDC_XFFT_PASS rate=${rate_msps} .*pss255=3" "$transcript" ||
   ! grep -q "^STARLINK_PSS${rate_msps}_DDC_TO_SCORE_XFFT_SIMULATION_COMPLETE$" \
      "$transcript"; then
  printf '%s\n' "The ${rate_msps} MS/s DDC-to-XFFT replay did not produce a clean PASS." >&2
  exit 1
fi
