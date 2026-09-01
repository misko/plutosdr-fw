#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
MUTER="$SCRIPT_DIR/pluto-mute-tx"
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT INT TERM

make_phy()
{
	root=$1
	channels=$2
	mkdir -p "$root/iio:device0"
	printf 'ad9361-phy\n' > "$root/iio:device0/name"
	printf '0\n' > "$root/iio:device0/out_altvoltage1_TX_LO_powerdown"
	mkdir -p "$root/iio:device1"
	printf 'cf-ad9361-dds-core-lpc\n' > "$root/iio:device1/name"
	printf '1\n' > "$root/iio:device1/out_altvoltage0_raw"
	printf '1\n' > "$root/iio:device1/out_altvoltage1_raw"
	channel=0
	while [ "$channel" -lt "$channels" ]; do
		printf '%s\n' '-10.000000 dB' \
			> "$root/iio:device0/out_voltage${channel}_hardwaregain"
		channel=$((channel + 1))
	done
}

assert_muted()
{
	root=$1
	channels=$2
	PLUTO_IIO_ROOT="$root" PLUTO_DT_ROOT="$TEST_DIR/no-marker" "$MUTER" >/dev/null
	[ "$(cat "$root/iio:device1/out_altvoltage0_raw")" = "0" ]
	[ "$(cat "$root/iio:device1/out_altvoltage1_raw")" = "0" ]
	[ "$(cat "$root/iio:device0/out_altvoltage1_TX_LO_powerdown")" = "1" ]
	channel=0
	while [ "$channel" -lt "$channels" ]; do
		[ "$(cat "$root/iio:device0/out_voltage${channel}_hardwaregain")" \
			= "-80" ]
		channel=$((channel + 1))
	done
}

make_phy "$TEST_DIR/one-tx" 1
assert_muted "$TEST_DIR/one-tx" 1

make_phy "$TEST_DIR/two-tx" 2
assert_muted "$TEST_DIR/two-tx" 2

mkdir -p "$TEST_DIR/no-phy"
if PLUTO_IIO_ROOT="$TEST_DIR/no-phy" "$MUTER" >/dev/null 2>&1; then
	printf '%s\n' "FAIL: missing ad9361-phy was accepted" >&2
	exit 1
fi

make_phy "$TEST_DIR/no-dds" 2
rm -rf "$TEST_DIR/no-dds/iio:device1"
if PLUTO_IIO_ROOT="$TEST_DIR/no-dds" PLUTO_DT_ROOT="$TEST_DIR/no-marker" \
	"$MUTER" >/dev/null 2>&1; then
	printf '%s\n' "FAIL: missing DDS core was accepted" >&2
	exit 1
fi

make_phy "$TEST_DIR/rx-only" 1
rm -rf "$TEST_DIR/rx-only/iio:device1"
mkdir -p "$TEST_DIR/rx-only-dt/fpga-axi@0/cf-ad9361-dds-core-lpc@79024000"
: > "$TEST_DIR/rx-only-dt/misko,rx-only-fpga"
printf 'disabled\000' \
	> "$TEST_DIR/rx-only-dt/fpga-axi@0/cf-ad9361-dds-core-lpc@79024000/status"
PLUTO_IIO_ROOT="$TEST_DIR/rx-only" PLUTO_DT_ROOT="$TEST_DIR/rx-only-dt" \
	"$MUTER" >/dev/null
[ "$(cat "$TEST_DIR/rx-only/iio:device0/out_voltage0_hardwaregain")" = "-80" ]
[ "$(cat "$TEST_DIR/rx-only/iio:device0/out_altvoltage1_TX_LO_powerdown")" = "1" ]

printf '%s\n' "PASS: boot TX mute red/green cases"
