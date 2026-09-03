#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
controller_dir="$repo_root/tools/starlink_pssctl"

make -C "$controller_dir" clean
make -C "$controller_dir" check
make -C "$controller_dir" sanitize
uv run --with pytest --with numpy pytest -q \
  "$repo_root/tests/test_starlink_pss_acquisition_c.py"

printf '%s\n' \
  'host_strict_build=PASS' \
  'arm_eabi_cross_build=PASS' \
  'asan_ubsan=PASS' \
  'python_c_oracle_cases=13' \
  'radio_contacted=false' \
  'verdict=PASS'
