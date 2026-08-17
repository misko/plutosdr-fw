#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECKER="${ROOT}/scripts/check_pluto_pstore_layout.sh"
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT INT TERM

"$CHECKER"

sed 's/0x0ef00000/0x1ff00000/' \
	"${ROOT}/linux/arch/arm/boot/dts/zynq-pluto-sdr.dtsi" > "$TEST_DIR/unsafe.dtsi"
if RAMOOPS_DTS="$TEST_DIR/unsafe.dtsi" "$CHECKER" >/dev/null 2>&1; then
	printf 'FAIL: unsafe high-memory ramoops fixture was accepted\n' >&2
	exit 1
fi

printf 'PASS: unsafe high-memory red fixture is rejected\n'
