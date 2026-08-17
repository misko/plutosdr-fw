#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WINBOND="$ROOT/linux/drivers/mtd/spi-nor/winbond.c"
CORE="$ROOT/linux/drivers/mtd/spi-nor/core.c"

fail() {
	printf 'FAIL: %s\n' "$*" >&2
	exit 1
}

grep -q 'is_zynq_qspi' "$CORE" ||
	fail 'test precondition missing: Zynq QSPI SFDP bypass'
grep -q 'spi_nor_post_sfdp_fixups(nor);' "$CORE" ||
	fail 'test precondition missing: unconditional post-SFDP fixups'
grep -q '\.post_sfdp = w25q256_post_sfdp_fixups' "$WINBOND" ||
	fail 'W25Q256 UID setup must use the post-SFDP hook'

post_sfdp_body="$({
	sed -n '/^static void w25q256_post_sfdp_fixups/,/^}/p' "$WINBOND"
})"
grep -q 'unique_id_len = WINBOND_UID_LEN' <<<"$post_sfdp_body" ||
	fail 'post-SFDP hook does not set the UID length'
grep -q 'read_unique_id = winbond_read_unique_id' <<<"$post_sfdp_body" ||
	fail 'post-SFDP hook does not install the UID reader'

printf 'PASS: W25Q256 UID reader survives the Zynq QSPI SFDP bypass\n'
