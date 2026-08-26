#!/usr/bin/env bash
set -euo pipefail
umask 0022

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
MANIFEST=${IIO_MANIFEST:-${ROOT}/manifests/tandem-agc-v8-source.yaml}
IIO_SOURCE=${IIO_SOURCE:-$(cd -- "${ROOT}/.." && pwd)/libiio}
python_bin=${PYTHON:-python3}
plan_only=false
for argument in "$@"; do
  if [[ "${argument}" == "--plan-only" ]]; then
    plan_only=true
  fi
done

runner_commit=$(git -C "${ROOT}" rev-parse HEAD)
[[ "${runner_commit}" =~ ^[0-9a-f]{40}$ ]] || {
  printf 'ERROR: firmware runner HEAD is not an exact commit\n' >&2
  exit 2
}
[[ -z "$(git -C "${ROOT}" status --porcelain=v1 --untracked-files=all)" ]] || {
  printf 'ERROR: firmware runner repository must be fully committed and clean\n' >&2
  exit 2
}
runner_paths=(
  scripts/deploy_tandem_agc_ram_hardware.sh
  scripts/run_tandem_agc_release_hardware.sh
  scripts/tandem_release_evidence.py
  tests/radio_hardware/candidate_binding.py
  tests/radio_hardware/release_cli.py
  tests/radio_hardware/tandem_ram_deploy.py
)
runner_stems=(
  DEPLOY_SHELL
  SHELL
  SEMANTIC_EVIDENCE
  CANDIDATE_BINDING
  RELEASE_CLI
  TANDEM_RAM_DEPLOY
)
export PLUTOSDR_FW_RUNNER_REPOSITORY="$(realpath -- "${ROOT}")"
export PLUTOSDR_FW_RUNNER_COMMIT="${runner_commit}"
for index in "${!runner_paths[@]}"; do
  runner_relative=${runner_paths[${index}]}
  runner_stem=${runner_stems[${index}]}
  runner_path=$(realpath -- "${ROOT}/${runner_relative}")
  [[ "${runner_path}" == "${ROOT}/${runner_relative}" && -f "${runner_path}" && \
    ! -L "${ROOT}/${runner_relative}" ]] || {
    printf 'ERROR: runner source path is not canonical: %s\n' \
      "${runner_relative}" >&2
    exit 2
  }
  runner_sha=$(sha256sum "${runner_path}" | awk '{print $1}')
  runner_committed_sha=$(git -C "${ROOT}" show \
    "${runner_commit}:${runner_relative}" | sha256sum | awk '{print $1}')
  [[ "${runner_sha}" == "${runner_committed_sha}" ]] || {
    printf 'ERROR: runner source differs from committed blob: %s\n' \
      "${runner_relative}" >&2
    exit 2
  }
  printf -v "PLUTOSDR_FW_RUNNER_${runner_stem}_PATH" '%s' "${runner_path}"
  printf -v "PLUTOSDR_FW_RUNNER_${runner_stem}_SHA256" '%s' "${runner_sha}"
  printf -v "PLUTOSDR_FW_RUNNER_${runner_stem}_COMMITTED_SHA256" '%s' \
    "${runner_committed_sha}"
  export "PLUTOSDR_FW_RUNNER_${runner_stem}_PATH"
  export "PLUTOSDR_FW_RUNNER_${runner_stem}_SHA256"
  export "PLUTOSDR_FW_RUNNER_${runner_stem}_COMMITTED_SHA256"
done

[[ -f "${MANIFEST}" ]] || {
  printf 'ERROR: final v8 source manifest not found: %s\n' "${MANIFEST}" >&2
  exit 2
}
[[ -d "${IIO_SOURCE}/.git" || -f "${IIO_SOURCE}/.git" ]] || {
  printf 'ERROR: IIO_SOURCE is not a git worktree: %s\n' "${IIO_SOURCE}" >&2
  exit 2
}

expected_commit=$(awk '$1 == "libiio_0_25_source:" {print $2}' "${MANIFEST}")
[[ "${expected_commit}" =~ ^[0-9a-f]{40}$ ]] || {
  printf 'ERROR: manifest has no exact libiio_0_25_source: %s\n' "${MANIFEST}" >&2
  exit 2
}
actual_commit=$(git -C "${IIO_SOURCE}" rev-parse HEAD)
[[ "${actual_commit}" == "${expected_commit}" ]] || {
  printf 'ERROR: libiio worktree is %s; manifest requires %s\n' \
    "${actual_commit}" "${expected_commit}" >&2
  exit 2
}
[[ -z "$(git -C "${IIO_SOURCE}" status --porcelain --untracked-files=all)" ]] || {
  printf 'ERROR: libiio worktree must be fully committed and clean: %s\n' \
    "${IIO_SOURCE}" >&2
  exit 2
}

"${python_bin}" -c 'import numpy' 2>/dev/null || {
  printf 'ERROR: install tests/radio_hardware/requirements.txt into %s\n' \
    "${python_bin}" >&2
  exit 2
}

export PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT="${expected_commit}"

if [[ "${plan_only}" == true ]]; then
  printf '%s\n' \
    'INFO: plan-only validates candidate/receipt/runner bindings without iio or USB.' \
    'INFO: this release qualification runner never deploys, reboots, or flashes.'
  cd -- "${ROOT}"
  exec "${python_bin}" -m tests.radio_hardware.release_cli "$@"
fi

[[ -z "${IIO_BUILD:-}" ]] || {
  printf 'ERROR: IIO_BUILD reuse is forbidden for release qualification\n' >&2
  exit 2
}
command -v cmake >/dev/null || {
  printf 'ERROR: cmake is required to build the pinned host libiio\n' >&2
  exit 2
}
python_executable=$("${python_bin}" -c 'import sys; print(sys.executable)')
[[ "${python_executable}" == /* ]] || {
  printf 'ERROR: Python executable identity is not absolute: %s\n' \
    "${python_executable}" >&2
  exit 2
}
libiio_repository=$(realpath -- "${IIO_SOURCE}")
libiio_work=$(mktemp -d \
  "${TMPDIR:-/tmp}/plutosdr-libiio-${expected_commit:0:12}.XXXXXX")
libiio_work=$(realpath -- "${libiio_work}")
chmod 0700 "${libiio_work}"
libiio_snapshot="${libiio_work}/source"
IIO_BUILD="${libiio_work}/build"
mkdir -m 0700 "${libiio_snapshot}" "${IIO_BUILD}"
git -C "${libiio_repository}" archive --format=tar "${expected_commit}" | \
  tar -x -C "${libiio_snapshot}"
cmake -S "${libiio_snapshot}" -B "${IIO_BUILD}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DINSTALL_UDEV_RULE=OFF \
  -DPYTHON_BINDINGS=ON \
  -DPYTHON_EXECUTABLE="${python_executable}" \
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
cache_source=$(awk -F= '$1 == "CMAKE_HOME_DIRECTORY:INTERNAL" {print $2}' \
  "${IIO_BUILD}/CMakeCache.txt")
[[ "$(realpath -- "${cache_source}")" == "${libiio_snapshot}" ]] || {
  printf 'ERROR: IIO_BUILD belongs to a different source tree: %s\n' \
    "${cache_source}" >&2
  exit 2
}
cmake --build "${IIO_BUILD}" --parallel --clean-first

libiio_so=$(realpath -- "${IIO_BUILD}/libiio.so")
pylibiio=$(realpath -- "${libiio_snapshot}/bindings/python/iio.py")
[[ "${libiio_so}" == "${IIO_BUILD}"/* && -f "${libiio_so}" ]] || {
  printf 'ERROR: built libiio is outside the fresh build directory\n' >&2
  exit 2
}
[[ "${pylibiio}" == "${libiio_snapshot}/bindings/python/iio.py" ]] || {
  printf 'ERROR: pylibiio path is not the pinned source binding\n' >&2
  exit 2
}
libiio_so_sha=$(sha256sum "${libiio_so}" | awk '{print $1}')
pylibiio_sha=$(sha256sum "${pylibiio}" | awk '{print $1}')
cmake_cache_sha=$(sha256sum "${IIO_BUILD}/CMakeCache.txt" | awk '{print $1}')
pylibiio_committed_sha=$(git -C "${libiio_repository}" show \
  "${expected_commit}:bindings/python/iio.py" | sha256sum | awk '{print $1}')
[[ "${pylibiio_sha}" == "${pylibiio_committed_sha}" ]] || {
  printf 'ERROR: pylibiio differs from the manifest-pinned committed blob\n' >&2
  exit 2
}
export PLUTOSDR_FW_LIBIIO_REPOSITORY="${libiio_repository}"
export PLUTOSDR_FW_LIBIIO_SOURCE="${libiio_snapshot}"
export PLUTOSDR_FW_LIBIIO_BUILD="${IIO_BUILD}"
export PLUTOSDR_FW_LIBIIO_SO_PATH="${libiio_so}"
export PLUTOSDR_FW_LIBIIO_SO_SHA256="${libiio_so_sha}"
export PLUTOSDR_FW_PYLIBIIO_PATH="${pylibiio}"
export PLUTOSDR_FW_PYLIBIIO_SHA256="${pylibiio_sha}"
export PLUTOSDR_FW_LIBIIO_CMAKE_CACHE_PATH="${IIO_BUILD}/CMakeCache.txt"
export PLUTOSDR_FW_LIBIIO_CMAKE_CACHE_SHA256="${cmake_cache_sha}"
export PLUTOSDR_FW_LIBIIO_PYTHON_EXECUTABLE="${python_executable}"
export PLUTOSDR_FW_LIBIIO_GUARDED_WRAPPER=tandem-release-host-libiio-v1

export PYTHONPATH="${libiio_snapshot}/bindings/python${PYTHONPATH:+:${PYTHONPATH}}"
export LD_LIBRARY_PATH="${IIO_BUILD}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

printf '%s\n' \
  'INFO: this release qualification runner never deploys, reboots, or flashes.' \
  'INFO: USB coordinates are resolved dynamically from exactly one --radio-serial.' \
  'INFO: --firmware-version is matched as one escaped, fully anchored literal.'

cd -- "${ROOT}"
exec "${python_bin}" -m tests.radio_hardware.release_cli "$@"
