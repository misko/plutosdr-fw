#!/usr/bin/env bash
# Verify that the kernel waits for receive-domain ownership acknowledgements.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRIVER="${ROOT}/linux/drivers/iio/adc/adi_tandem_agc.c"

python3 - "$DRIVER" <<'PY'
import re
import sys
from pathlib import Path

source = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(
    r"static int tandem_acquire_locked\(.*?\n\}\n\nstatic int tandem_open",
    source,
    re.DOTALL,
)
if match is None:
    raise SystemExit("FAIL: tandem_acquire_locked was not found")

body = match.group(0)
steps = [
    ("assert HOLD ownership", "tandem_write(st, TANDEM_REG_CONTROL, control);"),
    (
        "wait for ARMED_HOLD",
        "tandem_wait_state(st, ADI_TANDEM_AGC_STATE_ARMED_HOLD);",
    ),
    ("arm AD9361 pin control", "ad9361_tandem_arm(st->phy, st);"),
    ("request AUTO", "control |= TANDEM_CONTROL_AUTO;"),
    (
        "wait for ARMED_AUTO",
        "tandem_wait_state(st, ADI_TANDEM_AGC_STATE_ARMED_AUTO);",
    ),
]

cursor = 0
for label, needle in steps:
    position = body.find(needle, cursor)
    if position < 0:
        raise SystemExit(f"FAIL: acquire sequence does not {label}")
    cursor = position + len(needle)

print("PASS: tandem acquire waits for HOLD and AUTO receive-domain acknowledgements")
PY
