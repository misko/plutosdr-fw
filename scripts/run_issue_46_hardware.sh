#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
MANIFEST=${IIO_MANIFEST:-${ROOT}/manifests/tandem-agc-v8-rc2-source.yaml}
IIO_SOURCE=${IIO_SOURCE:-$(cd -- "${ROOT}/.." && pwd)/libiio}

[[ -f "${MANIFEST}" ]] || {
  printf 'ERROR: source manifest not found: %s\n' "${MANIFEST}" >&2
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
[[ -z "$(git -C "${IIO_SOURCE}" status --porcelain --untracked-files=no)" ]] || {
  printf 'ERROR: libiio worktree has tracked modifications: %s\n' "${IIO_SOURCE}" >&2
  exit 2
}

IIO_BUILD=${IIO_BUILD:-${IIO_SOURCE}/build-issue46-${expected_commit:0:12}}
if [[ ! -f "${IIO_BUILD}/libiio.so" ]]; then
  command -v cmake >/dev/null || {
    printf 'ERROR: cmake is required to build the pinned host libiio\n' >&2
    exit 2
  }
  cmake -S "${IIO_SOURCE}" -B "${IIO_BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DINSTALL_UDEV_RULE=OFF \
    -DPYTHON_BINDINGS=ON \
    -DPYTHON_EXECUTABLE="${PYTHON:-python3}" \
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
fi
cache_source=$(awk -F= '$1 == "CMAKE_HOME_DIRECTORY:INTERNAL" {print $2}' \
  "${IIO_BUILD}/CMakeCache.txt")
[[ "$(realpath -- "${cache_source}")" == "$(realpath -- "${IIO_SOURCE}")" ]] || {
  printf 'ERROR: IIO_BUILD belongs to a different source tree: %s\n' \
    "${cache_source}" >&2
  exit 2
}
cmake --build "${IIO_BUILD}" --parallel

python_bin=${PYTHON:-python3}
"${python_bin}" -c 'import pytest, numpy' 2>/dev/null || {
  printf 'ERROR: install tests/radio_hardware/requirements.txt into %s\n' \
    "${python_bin}" >&2
  exit 2
}

export PYTHONPATH="${IIO_SOURCE}/bindings/python${PYTHONPATH:+:${PYTHONPATH}}"
export LD_LIBRARY_PATH="${IIO_BUILD}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT="${expected_commit}"

"${python_bin}" - "${IIO_BUILD}" "${expected_commit}" <<'PY'
import pathlib
import sys

import iio

build = pathlib.Path(sys.argv[1]).resolve()
expected = sys.argv[2]
if getattr(iio, "MetadataBuffer", None) is None:
    raise SystemExit("ERROR: pinned pylibiio has no MetadataBuffer")
mapped = []
for line in pathlib.Path("/proc/self/maps").read_text().splitlines():
    path = line.rsplit(maxsplit=1)[-1]
    if "/libiio.so" in path:
        mapped.append(str(pathlib.Path(path).resolve()))
if not mapped or not all(pathlib.Path(path).is_relative_to(build) for path in mapped):
    raise SystemExit(f"ERROR: process mapped libiio outside {build}: {mapped}")
print(f"attested libiio {expected} from {mapped[0]}")
print(f"attested pylibiio from {pathlib.Path(iio.__file__).resolve()}")
PY

cd -- "${ROOT}"
exec "${python_bin}" -m pytest \
  tests/radio_hardware/test_tx2_fixture.py \
  tests/radio_hardware/test_issue_46_refill_continuity.py \
  "$@"
