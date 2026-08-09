#!/usr/bin/env bash
# Lightweight simulation of the coherent RX sample-counter clock crossing.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HDL_QUANTULUM="${ROOT}/hdl-quantulum"
MANIFEST="${SPF_GAIN_SERIES_MANIFEST:-${ROOT}/manifests/gain-series-v4-source.yaml}"

EXPECTED="$(awk '$1 == "submodule_hdl_quantulum:" { print $2 }' "$MANIFEST")"
[[ "$EXPECTED" =~ ^[0-9a-f]{40}$ ]] || {
    echo "FAIL: manifest has no valid submodule_hdl_quantulum pin: ${MANIFEST}" >&2
    exit 1
}

command -v iverilog >/dev/null || {
    echo "FAIL: iverilog is required" >&2
    exit 1
}
command -v vvp >/dev/null || {
    echo "FAIL: vvp is required" >&2
    exit 1
}

actual="$(git -C "$HDL_QUANTULUM" rev-parse HEAD 2>/dev/null || true)"
[[ "$actual" == "$EXPECTED" ]] || {
    echo "FAIL: hdl-quantulum is not initialized at ${EXPECTED}" >&2
    exit 1
}

work="$(mktemp -d "${TMPDIR:-/tmp}/spf-gain-series-cdc.XXXXXX")"
trap 'test ! -f "$work/cdc_tb" || unlink "$work/cdc_tb"; rmdir "$work" 2>/dev/null || true' EXIT

src="${HDL_QUANTULUM}/util_cpack2_timestamp/src"
iverilog -g2012 -Wall -o "${work}/cdc_tb" \
    "${src}/cdc_sync_bits.v" \
    "${src}/cdc_sync_data_closed.v" \
    "${src}/cdc_sync_data_closed_tb.v"
vvp "${work}/cdc_tb"
