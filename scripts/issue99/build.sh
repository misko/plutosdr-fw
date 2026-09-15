#!/usr/bin/env bash
# Build a below-boundary candidate without rebuilding or changing the FPGA.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$root"
: "${PLUTO_BUILDROOT_HOST:?Set the existing Buildroot output/host directory}"
export CROSS_COMPILE="$PLUTO_BUILDROOT_HOST/bin/arm-linux-gnueabihf-"
export SOURCE_DATE_EPOCH=1789257600
export KBUILD_BUILD_TIMESTAMP='Sun Sep 13 00:00:00 UTC 2026'
export KBUILD_BUILD_USER=codex KBUILD_BUILD_HOST=firmware-build KBUILD_BUILD_VERSION=1
work="$root/build/issue99"
mkdir -p "$work/baseline" "$root/build/linux"
if [[ ! -f "$work/baseline/pluto.dfu" ]]; then
    curl --fail --location --retry 2 https://github.com/misko/plutosdr-fw/releases/download/v0.50-plutoplus-spf-counter-rx-v1/plutoplus-spf-counter-rx-v1-619ecedf23a3-pluto.dfu -o "$work/baseline/pluto.dfu"
fi
printf '%s  %s\n' 435a26369018e86ee66262b79c32895dbaaacef510a1efb71c566d6409555344 "$work/baseline/pluto.dfu" | sha256sum -c -
head -c -16 "$work/baseline/pluto.dfu" > "$work/baseline/pluto.itb"
dumpimage -T flat_dt -p 4 -o "$work/baseline/zImage" "$work/baseline/pluto.itb"
linux/scripts/extract-ikconfig "$work/baseline/zImage" > "$root/build/linux/.config"
linux/scripts/config --file "$root/build/linux/.config" --set-str LOCALVERSION -counter-rx-v1-flash-safety-rc1
make -C linux O="$root/build/linux" ARCH=arm LOCALVERSION= olddefconfig
make -C linux O="$root/build/linux" ARCH=arm LOCALVERSION= -j"${JOBS:-8}" zImage dtbs modules
make -C linux O="$root/build/linux" ARCH=arm LOCALVERSION= INSTALL_MOD_PATH="$work/modules" INSTALL_MOD_STRIP=1 modules_install
make -C u-boot-xlnx O="$root/build/uboot" zynq_pluto_defconfig
make -C u-boot-xlnx O="$root/build/uboot" -j"${JOBS:-8}"
scripts/issue99/build_tools.sh
python3 scripts/issue99/package.py
