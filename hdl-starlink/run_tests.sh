#!/usr/bin/env bash
set -euo pipefail

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
build_dir="${source_dir}/build"
mkdir -p "${build_dir}"

for rate in 15 30 60; do
  iverilog \
    -g2012 \
    -Wall \
    -s tb_starlink_pss_delay_candidate \
    -P "tb_starlink_pss_delay_candidate.RATE_MSPS=${rate}" \
    -o "${build_dir}/pss-delay-${rate}.vvp" \
    "${source_dir}/starlink_pss_delay_candidate.v" \
    "${source_dir}/test/tb_starlink_pss_delay_candidate.sv"
  vvp "${build_dir}/pss-delay-${rate}.vvp"
done

# The rate selector is closed: an unsupported approximation must fail at time 0.
iverilog \
  -g2012 \
  -Wall \
  -s tb_starlink_pss_delay_candidate \
  -P "tb_starlink_pss_delay_candidate.RATE_MSPS=25" \
  -o "${build_dir}/pss-delay-invalid.vvp" \
  "${source_dir}/starlink_pss_delay_candidate.v" \
  "${source_dir}/test/tb_starlink_pss_delay_candidate.sv"
if vvp "${build_dir}/pss-delay-invalid.vvp" \
    >"${build_dir}/pss-delay-invalid.log" 2>&1; then
  echo "FAIL unsupported RATE_MSPS was accepted" >&2
  exit 1
fi
grep -q "RATE_MSPS must be exactly 15, 30, or 60" \
  "${build_dir}/pss-delay-invalid.log"
echo "PASS unsupported RATE_MSPS rejected"
