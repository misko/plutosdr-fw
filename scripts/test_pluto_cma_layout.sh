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
grep -qx 'CONFIG_CMA_SIZE_MBYTES=216' "$DEFCONFIG" ||
	fail 'Pluto CMA must request the qualified 216 MiB pool'
grep -qx 'CONFIG_CMA_ALIGNMENT=8' "$DEFCONFIG" ||
	fail 'Pluto CMA alignment changed; re-evaluate the exact 200 MB profile'

# The fixed pstore region starts at 239 MiB. A 256 MiB CMA request cannot fit
# contiguously below it on the DMA-limited Zynq address map and silently leaves
# the board with CmaTotal: 0 kB. The 216 MiB pool is hardware-proven at
# 0x10c00000. Fifty 1,000,000-IQ-sample ABI-3 buffers each carry an eight-byte
# prefix and occupy a 4 MiB CMA-aligned address span: exactly 200 MiB total,
# leaving 16 MiB for placement headroom and other coherent users.
grep -q 'reg = <0x0ef00000 0x00100000>;' "$DTS" ||
	fail 'unexpected Pluto ramoops placement; re-evaluate CMA qualification'

cma_bytes=$((216 * 1024 * 1024))
raw_frame_bytes=$((1000000 * 4 + 8))
cma_alignment_bytes=$((4096 * 256))
frame_span_bytes=$(((raw_frame_bytes + cma_alignment_bytes - 1) / cma_alignment_bytes * cma_alignment_bytes))
profile_span_bytes=$((50 * frame_span_bytes))
headroom_bytes=$((cma_bytes - profile_span_bytes))
((profile_span_bytes == 200 * 1024 * 1024)) ||
	fail 'exact 200 MB DMA profile no longer occupies the expected CMA span'
((headroom_bytes == 16 * 1024 * 1024)) ||
	fail 'exact 200 MB DMA profile no longer has the qualified CMA headroom'

printf 'PASS: Pluto reserves 216 MiB CMA for 50 x 1,000,000-sample buffers (200 MiB span, 16 MiB headroom)\n'
