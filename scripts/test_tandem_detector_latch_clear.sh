#!/usr/bin/env bash
# Verify that acquisition clears stale AD9361 overload latches with a real
# manual-gain edge before seeding the requested tandem gain index.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRIVER="${ROOT}/linux/drivers/iio/adc/ad9361.c"

python3 - "$DRIVER" <<'PY'
import re
import sys
from pathlib import Path

source = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(
    r"int ad9361_tandem_prepare\(.*?\n\}\nEXPORT_SYMBOL_GPL\(ad9361_tandem_prepare\);",
    source,
    re.DOTALL,
)
if match is None:
    raise SystemExit("FAIL: ad9361_tandem_prepare was not found")

body = match.group(0)
needles = [
    "clear_index = initial_index < table->max_index - 1 ?",
    "RX_FULL_TBL_IDX_MASK, clear_index);",
    "RX_FULL_TBL_IDX_MASK, clear_index);",
    "RX_FULL_TBL_IDX_MASK, initial_index);",
    "RX_FULL_TBL_IDX_MASK, initial_index);",
]
cursor = 0
for needle in needles:
    position = body.find(needle, cursor)
    if position < 0:
        raise SystemExit(
            "FAIL: tandem prepare does not clear detector latches before initial gain"
        )
    cursor = position + len(needle)

print("PASS: tandem prepare clears detector latches before initial gain")
PY
