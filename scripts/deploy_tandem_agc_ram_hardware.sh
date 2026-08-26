#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON=${PYTHON:-python3}

printf '%s\n' \
  'INFO: default mode is offline planning and never opens USB or executes SSH/DFU.' \
  'INFO: --execute also requires a private password file and a free exact /32 route to the selected radio interface.' \
  'INFO: only a unique serialless 0456:b674 on the pre-attested runtime topology may omit the requested serial.' \
  'INFO: the only executable transition is firmware.dfu download followed by DFU detach (-e).'

cd -- "${ROOT}"
exec "${PYTHON}" -m tests.radio_hardware.tandem_ram_deploy "$@"
