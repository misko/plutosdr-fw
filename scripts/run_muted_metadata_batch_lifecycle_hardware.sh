#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
IIO_SOURCE=${IIO_SOURCE:-$(cd -- "${ROOT}/.." && pwd)/libiio}
PYTHON=${PYTHON:-python3}
EXPECTED_COMMIT=70739d25ec1fa7b95d9069bd26a3e4192fdb3851

[[ -d "${IIO_SOURCE}/.git" || -f "${IIO_SOURCE}/.git" ]] || {
  printf 'ERROR: IIO_SOURCE is not a git worktree: %s\n' "${IIO_SOURCE}" >&2
  exit 2
}
actual_commit=$(git -C "${IIO_SOURCE}" rev-parse HEAD)
[[ "${actual_commit}" == "${EXPECTED_COMMIT}" ]] || {
  printf 'ERROR: libiio HEAD %s is not exact %s\n' \
    "${actual_commit}" "${EXPECTED_COMMIT}" >&2
  exit 2
}
[[ -z "$(git -C "${IIO_SOURCE}" status --porcelain --untracked-files=no)" ]] || {
  printf 'ERROR: libiio has tracked modifications: %s\n' "${IIO_SOURCE}" >&2
  exit 2
}

if [[ -z "${IIO_BUILD:-}" ]]; then
  IIO_BUILD=$(mktemp -d /tmp/plutosdr-fw-muted-batch-${EXPECTED_COMMIT:0:8}.XXXXXX)
fi
cmake -S "${IIO_SOURCE}" -B "${IIO_BUILD}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DINSTALL_UDEV_RULE=OFF \
  -DPYTHON_BINDINGS=ON \
  -DPYTHON_EXECUTABLE="${PYTHON}" \
  -DHAVE_DNS_SD=OFF \
  -DWITH_DOC=OFF \
  -DWITH_EXAMPLES=OFF \
  -DWITH_AIO=OFF \
  -DWITH_IIOD=OFF \
  -DWITH_LOCAL_BACKEND=ON \
  -DWITH_NETWORK_BACKEND=ON \
  -DWITH_SERIAL_BACKEND=OFF \
  -DWITH_TESTS=OFF \
  -DWITH_USB_BACKEND=ON
cmake --build "${IIO_BUILD}" --parallel

library=$(realpath -- "${IIO_BUILD}/libiio.so.0.25")
library_sha=$(sha256sum "${library}" | awk '{print $1}')
export PYTHONPATH="${IIO_SOURCE}/bindings/python${PYTHONPATH:+:${PYTHONPATH}}"
export LD_LIBRARY_PATH="${IIO_BUILD}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT="${EXPECTED_COMMIT}"
export PLUTOSDR_FW_LIBIIO_SHA256="${library_sha}"
export PLUTOSDR_FW_LIBIIO_PATH="${library}"
export PLUTOSDR_FW_LIBIIO_BUILD="$(realpath -- "${IIO_BUILD}")"
export PLUTOSDR_FW_LIBIIO_SOURCE="$(realpath -- "${IIO_SOURCE}")"
runner_module=tests/radio_hardware/muted_metadata_batch_lifecycle.py
runner_shell=scripts/run_muted_metadata_batch_lifecycle_hardware.sh
runner_metadata_abi=tests/radio_hardware/metadata_abi.py
for runner_path in \
  "${runner_module}" "${runner_shell}" "${runner_metadata_abi}"; do
  git -C "${ROOT}" diff --quiet HEAD -- "${runner_path}" || {
    printf 'ERROR: runner source differs from HEAD: %s\n' "${runner_path}" >&2
    exit 2
  }
done
export PLUTOSDR_FW_RUNNER_COMMIT="$(git -C "${ROOT}" rev-parse HEAD)"
runner_module_sha=$(sha256sum "${ROOT}/${runner_module}" | awk '{print $1}')
runner_shell_sha=$(sha256sum "${ROOT}/${runner_shell}" | awk '{print $1}')
runner_metadata_abi_sha=$(sha256sum \
  "${ROOT}/${runner_metadata_abi}" | awk '{print $1}')
runner_module_head_sha=$(git -C "${ROOT}" show \
  "${PLUTOSDR_FW_RUNNER_COMMIT}:${runner_module}" | sha256sum | awk '{print $1}')
runner_shell_head_sha=$(git -C "${ROOT}" show \
  "${PLUTOSDR_FW_RUNNER_COMMIT}:${runner_shell}" | sha256sum | awk '{print $1}')
runner_metadata_abi_head_sha=$(git -C "${ROOT}" show \
  "${PLUTOSDR_FW_RUNNER_COMMIT}:${runner_metadata_abi}" | sha256sum | awk '{print $1}')
[[ "${runner_module_sha}" == "${runner_module_head_sha}" ]] || {
  printf 'ERROR: runner blob does not match commit: %s\n' "${runner_module}" >&2
  exit 2
}
[[ "${runner_shell_sha}" == "${runner_shell_head_sha}" ]] || {
  printf 'ERROR: runner blob does not match commit: %s\n' "${runner_shell}" >&2
  exit 2
}
[[ "${runner_metadata_abi_sha}" == "${runner_metadata_abi_head_sha}" ]] || {
  printf 'ERROR: runner blob does not match commit: %s\n' \
    "${runner_metadata_abi}" >&2
  exit 2
}
export PLUTOSDR_FW_RUNNER_MODULE_SHA256="${runner_module_sha}"
export PLUTOSDR_FW_RUNNER_MODULE_HEAD_SHA256="${runner_module_head_sha}"
export PLUTOSDR_FW_RUNNER_SHELL_SHA256="${runner_shell_sha}"
export PLUTOSDR_FW_RUNNER_SHELL_HEAD_SHA256="${runner_shell_head_sha}"
export PLUTOSDR_FW_RUNNER_SHELL_PATH="$(realpath -- "${ROOT}/${runner_shell}")"
export PLUTOSDR_FW_RUNNER_METADATA_ABI_SHA256="${runner_metadata_abi_sha}"
export PLUTOSDR_FW_RUNNER_METADATA_ABI_HEAD_SHA256="${runner_metadata_abi_head_sha}"
export PLUTOSDR_FW_RUNNER_METADATA_ABI_PATH="$(realpath -- \
  "${ROOT}/${runner_metadata_abi}")"

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
exec "${PYTHON}" -m tests.radio_hardware.muted_metadata_batch_lifecycle "$@"
