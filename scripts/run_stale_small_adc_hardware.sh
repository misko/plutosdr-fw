#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
IIO_SOURCE=${IIO_SOURCE:-$(cd -- "${ROOT}/.." && pwd)/libiio}
PYTHON=${PYTHON:-python3}

SOURCE_MANIFEST=
HARDWARE_REQUESTED=0
previous=
for argument in "$@"; do
  if [[ "${previous}" == "--source-manifest" ]]; then
    SOURCE_MANIFEST=${argument}
    previous=
    continue
  fi
  case "${argument}" in
    --hardware)
      HARDWARE_REQUESTED=1
      previous=
      ;;
    --source-manifest)
      previous=--source-manifest
      ;;
    --source-manifest=*)
      SOURCE_MANIFEST=${argument#--source-manifest=}
      previous=
      ;;
    *)
      previous=
      ;;
  esac
done
[[ "${HARDWARE_REQUESTED}" == 1 ]] || {
  printf 'ERROR: refusing hardware access without explicit --hardware\n' >&2
  exit 2
}
[[ -z "${previous}" ]] || {
  printf 'ERROR: --source-manifest requires a value\n' >&2
  exit 2
}
[[ -n "${SOURCE_MANIFEST}" ]] || {
  printf 'ERROR: --source-manifest is required\n' >&2
  exit 2
}
[[ "${SOURCE_MANIFEST}" == /* ]] || {
  printf 'ERROR: --source-manifest must be absolute: %s\n' \
    "${SOURCE_MANIFEST}" >&2
  exit 2
}
[[ -f "${SOURCE_MANIFEST}" && ! -L "${SOURCE_MANIFEST}" ]] || {
  printf 'ERROR: source manifest must be a regular nonsymlink file: %s\n' \
    "${SOURCE_MANIFEST}" >&2
  exit 2
}
SOURCE_MANIFEST=$(realpath -- "${SOURCE_MANIFEST}")

source_manifest_value() {
  local manifest=$1 key=$2 value
  value=$(sed -n "s/^${key}:[[:space:]]*//p" "${manifest}" | head -1)
  printf '%s' "${value%"${value##*[![:space:]]}"}"
}

EXPECTED_COMMIT=$(source_manifest_value \
  "${SOURCE_MANIFEST}" libiio_0_25_source)
EXPECTED_REF=$(source_manifest_value "${SOURCE_MANIFEST}" libiio_0_25_ref)
[[ "${EXPECTED_COMMIT}" =~ ^[0-9a-f]{40}$ ]] || {
  printf 'ERROR: source manifest has no exact libiio commit: %s\n' \
    "${SOURCE_MANIFEST}" >&2
  exit 2
}
[[ "${EXPECTED_REF}" == refs/tags/* ]] || {
  printf 'ERROR: source manifest has no protected libiio tag: %s\n' \
    "${SOURCE_MANIFEST}" >&2
  exit 2
}

[[ -d "${IIO_SOURCE}/.git" || -f "${IIO_SOURCE}/.git" ]] || {
  printf 'ERROR: IIO_SOURCE is not a git worktree: %s\n' "${IIO_SOURCE}" >&2
  exit 2
}
actual_commit=$(git -C "${IIO_SOURCE}" rev-parse HEAD)
[[ "${actual_commit}" == "${EXPECTED_COMMIT}" ]] || {
  printf 'ERROR: libiio commit %s != required %s\n' \
    "${actual_commit}" "${EXPECTED_COMMIT}" >&2
  exit 2
}
[[ -z "$(git -C "${IIO_SOURCE}" status --porcelain --untracked-files=no)" ]] || {
  printf 'ERROR: libiio worktree has tracked modifications\n' >&2
  exit 2
}
tag_commit=$(git -C "${IIO_SOURCE}" rev-parse "${EXPECTED_REF}^{commit}")
[[ "${tag_commit}" == "${EXPECTED_COMMIT}" ]] || {
  printf 'ERROR: libiio protected tag moved: %s\n' "${EXPECTED_REF}" >&2
  exit 2
}

IIO_BUILD=$(mktemp -d "${TMPDIR:-/tmp}/libiio-stale-observer.XXXXXX")
cleanup() { rm -rf -- "${IIO_BUILD}"; }
trap cleanup EXIT INT TERM HUP

cmake -S "${IIO_SOURCE}" -B "${IIO_BUILD}" \
  -DWITH_PYTHON_BINDINGS=ON \
  -DWITH_NETWORK_BACKEND=ON \
  -DWITH_USB_BACKEND=ON \
  -DWITH_LOCAL_BACKEND=OFF \
  -DWITH_TESTS=OFF \
  -DWITH_EXAMPLES=OFF \
  -DWITH_DOC=OFF
cmake --build "${IIO_BUILD}" --parallel

library=$(find "${IIO_BUILD}" -type f -name 'libiio.so.0.25' -print -quit)
[[ -n "${library}" ]] || {
  printf 'ERROR: fresh build did not produce libiio.so.0.25\n' >&2
  exit 2
}
library=$(realpath -- "${library}")
library_sha=$(sha256sum "${library}" | awk '{print $1}')

export PYTHONPATH="${IIO_SOURCE}/bindings/python${PYTHONPATH:+:${PYTHONPATH}}"
export LD_LIBRARY_PATH="${IIO_BUILD}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT="${EXPECTED_COMMIT}"
export PLUTOSDR_FW_LIBIIO_SOURCE_REF="${EXPECTED_REF}"
export PLUTOSDR_FW_LIBIIO_SHA256="${library_sha}"
export PLUTOSDR_FW_LIBIIO_PATH="${library}"
export PLUTOSDR_FW_LIBIIO_BUILD="$(realpath -- "${IIO_BUILD}")"
export PLUTOSDR_FW_LIBIIO_SOURCE="$(realpath -- "${IIO_SOURCE}")"

export PLUTOSDR_FW_RUNNER_COMMIT=$(git -C "${ROOT}" rev-parse HEAD)

attest_harness_file() {
  local relative=$1 role=$2 live_sha head_sha absolute
  git -C "${ROOT}" diff --quiet HEAD -- "${relative}" || {
    printf 'ERROR: runner source differs from HEAD: %s\n' "${relative}" >&2
    exit 2
  }
  absolute=$(realpath -- "${ROOT}/${relative}")
  live_sha=$(sha256sum "${absolute}" | awk '{print $1}')
  head_sha=$(git -C "${ROOT}" show \
    "${PLUTOSDR_FW_RUNNER_COMMIT}:${relative}" | sha256sum | awk '{print $1}')
  [[ "${live_sha}" == "${head_sha}" ]] || {
    printf 'ERROR: runner blob does not match commit: %s\n' "${relative}" >&2
    exit 2
  }
  export "PLUTOSDR_FW_${role}_PATH=${absolute}"
  export "PLUTOSDR_FW_${role}_SHA256=${live_sha}"
  export "PLUTOSDR_FW_${role}_HEAD_SHA256=${head_sha}"
}

attest_harness_file \
  tests/radio_hardware/muted_metadata_batch_lifecycle.py RUNNER_MODULE
attest_harness_file \
  scripts/run_muted_metadata_batch_lifecycle_hardware.sh RUNNER_SHELL
attest_harness_file tests/radio_hardware/metadata_abi.py RUNNER_METADATA_ABI
attest_harness_file \
  tests/radio_hardware/candidate_binding.py RUNNER_CANDIDATE_BINDING
attest_harness_file \
  linux/drivers/iio/adc/adi_tandem_agc.c RELEASE_DRIVER
attest_harness_file linux/include/uapi/linux/adi_tandem_agc.h RELEASE_UAPI
attest_harness_file scripts/run_stale_small_adc_hardware.sh STALE_SHELL
attest_harness_file \
  tests/radio_hardware/stale_small_adc_hardware.py STALE_MODULE

"${PYTHON}" - "${IIO_BUILD}" "${library}" <<'PY'
import pathlib
import sys

import iio

build = pathlib.Path(sys.argv[1]).resolve()
expected_library = pathlib.Path(sys.argv[2]).resolve()
mapped = {
    pathlib.Path(line.rsplit(maxsplit=1)[-1]).resolve()
    for line in pathlib.Path("/proc/self/maps").read_text().splitlines()
    if "/libiio.so" in line.rsplit(maxsplit=1)[-1]
}
if mapped != {expected_library} or not expected_library.is_relative_to(build):
    raise SystemExit(f"ERROR: mapped libiio mismatch: {mapped}")
if getattr(iio, "MetadataBuffer", None) is None:
    raise SystemExit("ERROR: pylibiio lacks MetadataBuffer")
print(f"attested fresh libiio mapping: {expected_library}")
print(f"attested pylibiio: {pathlib.Path(iio.__file__).resolve()}")
PY

cd -- "${ROOT}"
exec "${PYTHON}" -m tests.radio_hardware.stale_small_adc_hardware "$@"
