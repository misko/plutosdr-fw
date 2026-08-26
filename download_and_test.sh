#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

printf '%s\n' >&2 \
  'ERROR: download_and_test.sh is quarantined; it cannot identify one radio or bind release evidence.' \
  "ERROR: use ${ROOT}/scripts/deploy_tandem_agc_ram_hardware.sh (offline planning by default)."
exit 2
