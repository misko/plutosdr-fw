#!/usr/bin/env bash
# Verify the three packaged Pluto DTBs retain their board-specific topology.

set -euo pipefail

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

(( $# == 3 )) || fail "usage: $0 REVA_DTB REVB_DTB REVC_DTB"
command -v fdtget >/dev/null 2>&1 || fail "fdtget is required"

phy=/amba/spi@e0006000/ad9361-phy@0
dds=/fpga-axi@0/cf-ad9361-dds-core-lpc@79024000
expected_models=(
    'Analog Devices PlutoSDR Rev.A (Z7010/AD9363)'
    'Analog Devices PlutoSDR Rev.B (Z7010/AD9363)'
    'Analog Devices PlutoSDR Rev.C (Z7010/AD9363)'
)
dtbs=("$1" "$2" "$3")

for index in 0 1 2; do
    dtb="${dtbs[$index]}"
    [[ -f "$dtb" && ! -L "$dtb" ]] || fail "unsafe or missing DTB: $dtb"
    [[ "$(fdtget -t s "$dtb" / model)" == "${expected_models[$index]}" ]] ||
        fail "unexpected board model in $dtb"
done

for dtb in "$1" "$2"; do
    ! fdtget -p "$dtb" "$phy" | grep -Fxq 'adi,2rx-2tx-mode-enable' ||
        fail "2R2T unexpectedly enabled for Rev.A/B in $dtb"
    [[ "$(fdtget -t s "$dtb" "$dds" compatible)" == adi,axi-ad9364-dds-6.00.a ]] ||
        fail "single-RX DDS compatibility differs in $dtb"
done

fdtget -p "$3" "$phy" | grep -Fxq 'adi,2rx-2tx-mode-enable' ||
    fail "Rev.C/Pluto+ 2R2T property is missing in $3"
[[ "$(fdtget -t s "$3" "$dds" compatible)" == adi,axi-ad9361-dds-6.00.a ]] ||
    fail "Rev.C/Pluto+ paired-RX DDS compatibility differs in $3"

# One physical AD9361 node provides both receive paths, which is the shared-LO
# invariant.  A second PHY node would imply an unsupported independent LO.
for dtb in "$1" "$2" "$3"; do
    [[ "$(fdtget -l "$dtb" /amba/spi@e0006000 | grep -Ec '^ad9361-phy@')" == 1 ]] ||
        fail "expected exactly one shared-LO AD9361 PHY in $dtb"
done

printf 'PASS: Rev.C/Pluto+ shared-LO 2R2T topology and Rev.A/B safety verified\n'
