#!/usr/bin/env bash
# Build the v0.59 iiOD deadline fix with the release's metadata and ARM sysroot.
set -euo pipefail
if [[ $# != 5 ]]; then
    echo "usage: $0 LIBIIO_SOURCE METADATA_SOURCE TOOLCHAIN_FILE SYSROOT OUTPUT" >&2
    exit 2
fi
src=$(realpath "$1")
metadata=$(realpath "$2")
toolchain=$(realpath "$3")
sysroot=$(realpath "$4")
mkdir -p "$5"
out=$(realpath "$5")
test "$(git -C "$src" rev-parse HEAD)" = 345cd699236bce30eb5eed6d0e6adec6e2746360
test "$(git -C "$metadata" rev-parse HEAD)" = 3294365ff44da26b261be4a2ccb241b7896d23ad
git -C "$src" diff --exit-code HEAD -- iiod CMakeLists.txt
git -C "$metadata" diff --exit-code HEAD
extra="$src/iiod/spf-tandem-session.c;$src/iiod/spf-tandem-metadata.c"
for name in spf_gain_read spf_gain_sampler spf_rssi_read spf_radio_frame_v3 spf_thread_join; do
    extra+=";$metadata/$name.c"
done
cmake -S "$src" -B "$out" \
    -DCMAKE_TOOLCHAIN_FILE="$toolchain" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_SKIP_RPATH=ON -DWITH_TESTS=OFF -DWITH_IIOD=ON \
    -DWITH_IIOD_USBD=ON -DWITH_IIOD_SERIAL=OFF -DWITH_SERIAL_BACKEND=ON \
    -DWITH_DOC=OFF -DWITH_MAN=OFF -DWITH_EXAMPLES=OFF -DWITH_ZSTD=OFF \
    -DWITH_SYSTEMD=OFF -DWITH_SYSVINIT=OFF -DWITH_UPSTART=OFF \
    -DIIOD_BUFFER_METADATA_PROVIDER="$src/iiod/spf-buffer-metadata.c" \
    -DIIOD_BUFFER_METADATA_PROVIDER_EXTRA_SOURCES="$extra" \
    -DIIOD_BUFFER_METADATA_INCLUDE_DIRS="$metadata;$sysroot/usr/include"
cmake --build "$out" -j8
mkdir -p "$out/artifacts"
cp "$out/iiod/iiod" "$out/artifacts/iiod"
cp "$out/libiio.so.0.25" "$out/artifacts/libiio.so.0.25"
strip_tool=$(sed -n 's/^CMAKE_STRIP:FILEPATH=//p' "$out/CMakeCache.txt")
test -x "$strip_tool"
"$strip_tool" "$out/artifacts/iiod" "$out/artifacts/libiio.so.0.25"
