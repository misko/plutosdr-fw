#!/usr/bin/env bash
# Build precisely pinned ARM FIT inspectors for the bootstrap rootfs overlay.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
: "${CROSS_COMPILE:?Set the Buildroot target compiler prefix}"
work="$root/build/issue99"
mkdir -p "$work/downloads" "$work/tools"
fetch() {
    local name=$1 url=$2 sha=$3
    if [[ ! -f "$work/downloads/$name" ]]; then
        curl --fail --location --retry 2 "$url" -o "$work/downloads/$name"
    fi
    printf '%s  %s\n' "$sha" "$work/downloads/$name" | sha256sum -c -
}
fetch dtc-1.6.1.tar.xz https://www.kernel.org/pub/software/utils/dtc/dtc-1.6.1.tar.xz 65cec529893659a49a89740bb362f507a3b94fc8cd791e76a8d6a2b6f3203473
fetch u-boot-2021.07.tar.bz2 https://ftp.denx.de/pub/u-boot/u-boot-2021.07.tar.bz2 312b7eeae44581d1362c3a3f02c28d806647756c82ba8c72241c7cdbe68ba77e
[[ -d "$work/tools/dtc-1.6.1" ]] || tar -xf "$work/downloads/dtc-1.6.1.tar.xz" -C "$work/tools"
[[ -d "$work/tools/u-boot-2021.07" ]] || tar -xf "$work/downloads/u-boot-2021.07.tar.bz2" -C "$work/tools"
make -C "$work/tools/dtc-1.6.1" -j"${JOBS:-8}" CC="${CROSS_COMPILE}gcc" AR="${CROSS_COMPILE}ar" NO_PYTHON=1 NO_YAML=1 fdtget
uboot="$work/tools/u-boot-2021.07"
mkdir -p "$uboot/include/config" "$uboot/include/generated" "$uboot/include/asm"
touch "$uboot/include/config/auto.conf" "$uboot/include/asm/linkage.h"
printf '#define CONFIG_FIT_PRINT 1\n' > "$uboot/include/generated/autoconf.h"
make -C "$uboot" -j"${JOBS:-8}" CROSS_COMPILE="$CROSS_COMPILE" CROSS_BUILD_TOOLS=y CONFIG_FIT=y CONFIG_MKIMAGE_DTC_PATH=dtc tools-only
"${CROSS_COMPILE}strip" "$work/tools/dtc-1.6.1/fdtget" "$work/tools/dtc-1.6.1/libfdt/libfdt-1.6.1.so" "$uboot/tools/dumpimage"
file "$work/tools/dtc-1.6.1/fdtget" "$uboot/tools/dumpimage"
