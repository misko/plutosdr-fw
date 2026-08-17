#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
READER="$SCRIPT_DIR/pluto-read-identity"
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT INT TERM

assert_eq()
{
	actual=$1
	expected=$2
	message=$3
	if [ "$actual" != "$expected" ]; then
		printf 'FAIL: %s: expected <%s>, got <%s>\n' \
			"$message" "$expected" "$actual" >&2
		exit 1
	fi
}

printf '[    0.1] SPI-NOR-UniqueID 0123456789abcdefABCDEF0123456789ABCD\n' > "$TEST_DIR/dmesg"
printf '\001\043\105\147\211\253\315\357' > "$TEST_DIR/uid"
actual=$(PLUTO_IDENTITY_DMESG_FILE="$TEST_DIR/dmesg" \
	PLUTO_IDENTITY_UID_FILE="$TEST_DIR/uid" "$READER")
assert_eq "$actual" "0123456789abcdefABCDEF0123456789ABCD" \
	"the historical Micron serial has priority and is unchanged"

: > "$TEST_DIR/dmesg"
actual=$(PLUTO_IDENTITY_DMESG_FILE="$TEST_DIR/dmesg" \
	PLUTO_IDENTITY_UID_FILE="$TEST_DIR/uid" "$READER")
assert_eq "$actual" "winbond-0123456789abcdef" \
	"the Winbond binary UID is encoded deterministically"

printf '\000\000\000\000\000\000\000\000' > "$TEST_DIR/uid"
if PLUTO_IDENTITY_DMESG_FILE="$TEST_DIR/dmesg" \
	PLUTO_IDENTITY_UID_FILE="$TEST_DIR/uid" "$READER" >/dev/null 2>&1; then
	printf 'FAIL: an all-zero UID was accepted\n' >&2
	exit 1
fi

printf '\377\377\377\377\377\377\377\377' > "$TEST_DIR/uid"
if PLUTO_IDENTITY_DMESG_FILE="$TEST_DIR/dmesg" \
	PLUTO_IDENTITY_UID_FILE="$TEST_DIR/uid" "$READER" >/dev/null 2>&1; then
	printf 'FAIL: an all-ones UID was accepted\n' >&2
	exit 1
fi

printf '[    0.1] SPI-NOR-UniqueID 0000000000000000000000000000000000\n' > "$TEST_DIR/dmesg"
if PLUTO_IDENTITY_DMESG_FILE="$TEST_DIR/dmesg" \
	PLUTO_IDENTITY_UID_FILE="$TEST_DIR/missing" "$READER" >/dev/null 2>&1; then
	printf 'FAIL: an all-zero legacy UID was accepted\n' >&2
	exit 1
fi

printf 'PASS: board identity red/green cases\n'
