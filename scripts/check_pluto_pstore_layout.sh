#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DTS="${RAMOOPS_DTS:-${ROOT}/linux/arch/arm/boot/dts/zynq-pluto-sdr.dtsi}"
UBOOT_CONFIG="${RAMOOPS_UBOOT_CONFIG:-${ROOT}/u-boot-xlnx/include/configs/zynq-common.h}"
FIT_ITS="${RAMOOPS_FIT_ITS:-${ROOT}/scripts/pluto.its}"

fail()
{
	printf 'FAIL: %s\n' "$*" >&2
	exit 1
}

read -r ramoops_start_hex ramoops_size_hex < <(
	sed -n '/ramoops@/,/};/s/.*reg = <0x\([0-9A-Fa-f]*\) 0x\([0-9A-Fa-f]*\)>.*/\1 \2/p' "$DTS"
)
fit_start_hex=$(sed -n 's/.*"fit_load_address=0x\([0-9A-Fa-f]*\).*/\1/p' "$UBOOT_CONFIG" | head -n 1)
fit_size_hex=$(sed -n 's/.*sf read ${fit_load_address} 0x200000  *0x\([0-9A-Fa-f]*\).*/\1/p' "$UBOOT_CONFIG" | head -n 1)
fpga_start_hex=$(awk '
	/fpga@1[[:space:]]*{/ { in_fpga = 1 }
	in_fpga && /load = <0x/ {
		line = $0
		sub(/^.*load = <0x/, "", line)
		sub(/>;.*/, "", line)
		print line
		exit
	}' "$FIT_ITS")

[ -n "${ramoops_start_hex:-}" ] || fail "cannot read ramoops start from $DTS"
[ -n "${ramoops_size_hex:-}" ] || fail "cannot read ramoops size from $DTS"
[ -n "$fit_start_hex" ] || fail "cannot read FIT load address from $UBOOT_CONFIG"
[ -n "$fit_size_hex" ] || fail "cannot read maximum FIT size from $UBOOT_CONFIG"
[ -n "$fpga_start_hex" ] || fail "cannot read FPGA load address from $FIT_ITS"

ramoops_start=$((16#$ramoops_start_hex))
ramoops_size=$((16#$ramoops_size_hex))
ramoops_end=$((ramoops_start + ramoops_size))
fit_start=$((16#$fit_start_hex))
fit_end=$((fit_start + 16#$fit_size_hex))
fpga_start=$((16#$fpga_start_hex))

(( ramoops_start >= fit_end )) ||
	fail "ramoops overlaps the maximum FIT staging window"
(( ramoops_end <= fpga_start )) ||
	fail "ramoops overlaps the FPGA staging address or high boot memory"

printf 'PASS: ramoops [0x%x,0x%x) lies between FIT end 0x%x and FPGA load 0x%x\n' \
	"$ramoops_start" "$ramoops_end" "$fit_end" "$fpga_start"
