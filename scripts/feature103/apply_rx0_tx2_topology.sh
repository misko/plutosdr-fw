#!/usr/bin/env bash
# Narrow every FIT device-tree slot to the hardware-qualified feature-103
# RX0/TX2 topology. The input files are modified in place before mkimage runs.

set -euo pipefail

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

mode=apply
if [[ "${1:-}" == --check ]]; then
    mode=check
    shift
fi
(( $# > 0 )) || fail "usage: $0 [--check] DTB [DTB ...]"
command -v fdtget >/dev/null 2>&1 || fail "fdtget is required"
command -v fdtput >/dev/null 2>&1 || fail "fdtput is required"

phy=/amba/spi@e0006000/ad9361-phy@0
dds=/fpga-axi@0/cf-ad9361-dds-core-lpc@79024000

for dtb in "$@"; do
    [[ -f "$dtb" && ! -L "$dtb" ]] || fail "unsafe or missing DTB: $dtb"
    if [[ "$mode" == apply ]]; then
        if fdtget -p "$dtb" "$phy" | grep -Fxq 'adi,2rx-2tx-mode-enable'; then
            fdtput -d "$dtb" "$phy" adi,2rx-2tx-mode-enable
        fi
        fdtput -t x "$dtb" "$phy" adi,1rx-1tx-mode-use-rx-num 1
        fdtput -t x "$dtb" "$phy" adi,1rx-1tx-mode-use-tx-num 2
        fdtput -t s "$dtb" "$dds" compatible adi,axi-ad9364-dds-6.00.a
    fi

    ! fdtget -p "$dtb" "$phy" | grep -Fxq 'adi,2rx-2tx-mode-enable' ||
        fail "2R2T property survived in $dtb"
    [[ "$(fdtget -t x "$dtb" "$phy" adi,1rx-1tx-mode-use-rx-num)" == 1 ]] ||
        fail "RX selector differs in $dtb"
    [[ "$(fdtget -t x "$dtb" "$phy" adi,1rx-1tx-mode-use-tx-num)" == 2 ]] ||
        fail "TX selector differs in $dtb"
    [[ "$(fdtget -t s "$dtb" "$dds" compatible)" == adi,axi-ad9364-dds-6.00.a ]] ||
        fail "DDS compatibility differs in $dtb"
done
