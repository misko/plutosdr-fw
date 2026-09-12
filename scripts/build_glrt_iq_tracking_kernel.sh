#!/usr/bin/env bash
# Build a fresh committed kernel snapshot; no radio I/O or firmware mutation.
set -euo pipefail
[[ $# -eq 1 ]]
repository=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
output=$(realpath -m "$1")
test ! -e "$output"
git -C "$repository/linux" diff --quiet
git -C "$repository/linux" diff --cached --quiet
commit=$(git -C "$repository/linux" rev-parse HEAD)
cross=/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-
mkdir -p "$output"
git clone --shared --no-checkout "$repository/linux" "$output/source-checkout" > "$output/checkout.log" 2>&1
git -C "$output/source-checkout" checkout --detach "$commit" >> "$output/checkout.log" 2>&1
printf '%s\n' "$commit" > "$output/kernel_commit.txt"
sha256sum "$0" > "$output/build_script.sha256"
make -C "$output/source-checkout" O="$output" ARCH=arm CROSS_COMPILE="$cross" zynq_pluto_glrt_defconfig > "$output/configure.log" 2>&1
status=0
nice -n 10 make -C "$output/source-checkout" O="$output" ARCH=arm CROSS_COMPILE="$cross" -j4 zImage modules zynq-pluto-sdr-glrt.dtb > "$output/build.log" 2>&1 || status=$?
printf '%s\n' "$status" > "$output/build_exit_code.txt"
test "$status" -eq 0
git -C "$output/source-checkout" diff --exit-code > "$output/source_validation.log"
sha256sum "$output/arch/arm/boot/zImage" "$output/arch/arm/boot/dts/zynq-pluto-sdr-glrt.dtb" > "$output/outputs.sha256"
