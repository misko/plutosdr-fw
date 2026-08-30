#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
PLUTO_PLUS_UTILS=${PLUTO_PLUS_UTILS:-$(cd -- "${ROOT}/.." && pwd)/pluto-plus-utils}
EXPECTED_TOOL_COMMIT=97487a04810ea120e4071146d8a14ee95f0fcecd

printf '%s\n' \
  'INFO: device operations are owned by the pinned pluto-plus-utils candidate-ram command.' \
  'INFO: inventory and plan are read-only; execute requires a private password file and exact confirmation.' \
  'INFO: SSH is password-only and host-key checking is disabled because Pluto RAM boots generate a fresh host key.' \
  'INFO: only a unique serialless 0456:b674 on the pre-attested runtime topology may omit the requested serial.' \
  'INFO: the only executable transition is firmware.dfu download followed by DFU detach (-e).'

[[ -d "${PLUTO_PLUS_UTILS}/.git" ]] || {
  printf 'ERROR: PLUTO_PLUS_UTILS is not a Git checkout: %s\n' \
    "${PLUTO_PLUS_UTILS}" >&2
  exit 2
}
tool_commit=$(git -C "${PLUTO_PLUS_UTILS}" rev-parse --verify 'HEAD^{commit}')
[[ "${tool_commit}" == "${EXPECTED_TOOL_COMMIT}" ]] || {
  printf 'ERROR: pluto-plus-utils must be exact commit %s, got %s\n' \
    "${EXPECTED_TOOL_COMMIT}" "${tool_commit}" >&2
  exit 2
}
[[ -z "$(git -C "${PLUTO_PLUS_UTILS}" status --porcelain=v1 --untracked-files=all)" ]] || {
  printf 'ERROR: pluto-plus-utils checkout must be fully clean\n' >&2
  exit 2
}

exec uv run --frozen --project "${PLUTO_PLUS_UTILS}" \
  pluto firmware candidate-ram "$@"
