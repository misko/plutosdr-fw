#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON=${PYTHON:-python3}

printf '%s\n' \
  'INFO: default mode is offline planning and never opens USB or executes SSH/DFU.' \
  'INFO: --execute requires exact serial/artifact/index bindings and operator confirmation; no external transition proof.' \
  'INFO: the only executable transition is firmware.dfu download followed by DFU detach (-e).'

cd -- "${ROOT}"
exec "${PYTHON}" -m tests.radio_hardware.tandem_ram_deploy "$@"
