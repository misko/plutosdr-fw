#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFCONFIG="$ROOT/linux/arch/arm/configs/zynq_pluto_defconfig"
DTS="$ROOT/linux/arch/arm/boot/dts/zynq-pluto-sdr.dtsi"

fail() {
	printf 'FAIL: %s\n' "$*" >&2
	exit 1
}

grep -qx 'CONFIG_DMA_CMA=y' "$DEFCONFIG" ||
	fail 'Pluto must allocate coherent DMA buffers from CMA'
grep -qx 'CONFIG_CMA_SIZE_MBYTES=64' "$DEFCONFIG" ||
	fail 'Pluto CMA must request the bounded 64 MiB pool'

# The fixed pstore region starts at 239 MiB. A 256 MiB CMA request cannot fit
# contiguously below it on the DMA-limited Zynq address map and silently leaves
# the board with CmaTotal: 0 kB.
grep -q 'reg = <0x0ef00000 0x00100000>;' "$DTS" ||
	fail 'unexpected Pluto ramoops placement; re-evaluate CMA qualification'

printf 'PASS: Pluto reserves a 64 MiB CMA pool compatible with ramoops\n'
