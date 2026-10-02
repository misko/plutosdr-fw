#!/usr/bin/env bash
# Build the integrated v0.60 iiOD with the release's metadata and ARM sysroot.
set -euo pipefail
if [[ $# != 5 ]]; then
    echo "usage: $0 LIBIIO_SOURCE METADATA_SOURCE TOOLCHAIN_FILE SYSROOT OUTPUT" >&2
    exit 2
fi
src=$(realpath -s "$1")
metadata=$(realpath -s "$2")
toolchain=$(realpath -s "$3")
sysroot=$(realpath -s "$4")
mkdir -p "$5"
out=$(realpath -s "$5")
test "$(git -C "$src" rev-parse HEAD)" = 0b7718af9eed0a42eec448d03248c8497b13a779
test "$(git -C "$metadata" rev-parse HEAD)" = 3294365ff44da26b261be4a2ccb241b7896d23ad
git -C "$src" diff --exit-code HEAD -- iiod CMakeLists.txt
git -C "$metadata" diff --exit-code HEAD
extra="$src/iiod/spf-tandem-session.c;$src/iiod/spf-tandem-metadata.c"
for name in spf_radio_frame_v3 spf_gain_read spf_gain_sampler spf_rssi_read spf_thread_join spf_time_anchor; do
    extra+=";$metadata/$name.c"
done
cmake -S "$src" -B "$out" \
    -DCMAKE_TOOLCHAIN_FILE="$toolchain" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_SKIP_RPATH=OFF -DHAVE_DNS_SD=OFF -DWITH_TESTS=ON -DWITH_IIOD=ON \
    -DWITH_IIOD_USBD=ON -DWITH_IIOD_SERIAL=OFF -DWITH_SERIAL_BACKEND=OFF \
    -DWITH_DOC=OFF -DWITH_MAN=OFF -DWITH_EXAMPLES=OFF -DWITH_ZSTD=OFF \
    -DWITH_SYSTEMD=OFF -DWITH_SYSVINIT=OFF -DWITH_UPSTART=OFF \
    -DIIOD_BUFFER_METADATA_PROVIDER="$src/iiod/spf-buffer-metadata.c" \
    -DIIOD_BUFFER_METADATA_PROVIDER_EXTRA_SOURCES="$extra" \
    -DIIOD_BUFFER_METADATA_INCLUDE_DIRS="$metadata;$sysroot/usr/include"
cmake --build "$out" --target iiod -j8
