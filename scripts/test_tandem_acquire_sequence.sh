#!/usr/bin/env bash
# Verify kernel ownership acknowledgement and release-time event retirement.

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

retire_match = re.search(
    r"static int tandem_retire_events_locked\(.*?\n\}\n\nstatic void tandem_fill_status",
    source,
    re.DOTALL,
)
if retire_match is None:
    raise SystemExit("FAIL: tandem_retire_events_locked was not found")
retire = retire_match.group(0)
retire_steps = [
    ("settle the final receive-domain write pointer", "usleep_range(50, 100)"),
    ("read FIFO occupancy", "TANDEM_REG_FIFO_LEVEL"),
    ("bound retirement by FIFO depth", "retired >= st->fifo_depth"),
    ("read event word zero", "TANDEM_REG_EVENT_WORD0"),
    ("read event word one", "TANDEM_REG_EVENT_WORD1"),
    ("read event word two", "TANDEM_REG_EVENT_WORD2"),
    ("pop through event word three", "TANDEM_REG_EVENT_WORD3_POP"),
    ("wait for CDC occupancy convergence", "readl_poll_timeout"),
    ("use the bounded pop timeout", "TANDEM_FIFO_POP_TIMEOUT_US"),
]
cursor = 0
for label, needle in retire_steps:
    position = retire.find(needle, cursor)
    if position < 0:
        raise SystemExit(f"FAIL: release retirement does not {label}")
    cursor = position + len(needle)
if "TANDEM_CONTROL_CLEAR" in retire:
    raise SystemExit("FAIL: release retirement erases session diagnostics with CLEAR")
if not re.search(r"level\s*<\s*previous", retire):
    raise SystemExit("FAIL: release retirement does not prove each pop converged")

release_match = re.search(
    r"static int tandem_release_locked\(.*?\n\}\n\nstatic void tandem_watchdog_work",
    source,
    re.DOTALL,
)
if release_match is None:
    raise SystemExit("FAIL: tandem_release_locked was not found")
release = release_match.group(0)
release_steps = [
    ("suppress AUTO", "tandem_write(st, TANDEM_REG_CONTROL, TANDEM_CONTROL_OWN);"),
    ("wait for pulse quiescence", "tandem_wait_quiescent(st, !st->acquired);"),
    ("retire queued event records", "tandem_retire_events_locked(st);"),
    ("restore the AD9361 snapshot", "ad9361_tandem_release(st->phy, st);"),
    ("return the mux to PS/high-Z", "tandem_write(st, TANDEM_REG_CONTROL, 0);"),
    ("drop software ownership last", "st->acquired = false;"),
]
cursor = 0
for label, needle in release_steps:
    position = release.find(needle, cursor)
    if position < 0:
        raise SystemExit(f"FAIL: release sequence does not {label}")
    cursor = position + len(needle)
if "TANDEM_CONTROL_CLEAR" in release:
    raise SystemExit("FAIL: release sequence erases session diagnostics with CLEAR")
if "st->software_fault |= ADI_TANDEM_AGC_FAULT_RADIO_IO" not in release:
    raise SystemExit("FAIL: release retirement failure is not sticky and observable")
error_precedence = [
    "if (restore_ret)",
    "return restore_ret;",
    "if (quiesce_ret)",
    "return quiesce_ret;",
    "return retire_ret;",
]
cursor = 0
for needle in error_precedence:
    position = release.find(needle, cursor)
    if position < 0:
        raise SystemExit("FAIL: release does not preserve restore/quiesce/drain errno precedence")
    cursor = position + len(needle)

quiescent_match = re.search(
    r"static int tandem_wait_quiescent\(.*?\n\}\n\nstatic int tandem_retire_events_locked",
    source,
    re.DOTALL,
)
if quiescent_match is None:
    raise SystemExit("FAIL: tandem_wait_quiescent was not found")
quiescent = quiescent_match.group(0)
for needle in (
    "ADI_TANDEM_AGC_STATE_ARMED_HOLD",
    "ADI_TANDEM_AGC_STATE_FAULTED",
    "allow_idle",
):
    if needle not in quiescent:
        raise SystemExit(f"FAIL: quiescence proof lacks {needle}")
if "ADI_TANDEM_AGC_STATE_RESTORING" in quiescent:
    raise SystemExit("FAIL: RESTORING is not a proof that the active pulse ended")

# Acquire failures occur in tandem_acquire_locked, not release. Verify their
# post-CLEAR cleanup separately so a failed ownership acknowledgment cannot
# strand records that no future idle reader is allowed to drain.
for needle in (
    "err_release:",
    "err_disarm:",
    "tandem_wait_quiescent(st, false);",
    "tandem_retire_events_locked(st);",
    "st->software_fault |= ADI_TANDEM_AGC_FAULT_RADIO_IO",
):
    if needle not in body:
        raise SystemExit(f"FAIL: acquire abort cleanup lacks {needle}")

clear_at = body.find(
    "tandem_write(st, TANDEM_REG_CONTROL, TANDEM_CONTROL_CLEAR);"
)
clear_recovered_at = body.find("st->software_fault = 0;", clear_at)
own_at = body.find("control = TANDEM_CONTROL_OWN;", clear_at)
if clear_at < 0 or clear_recovered_at < clear_at or own_at < clear_recovered_at:
    raise SystemExit(
        "FAIL: software fault recovery is not bound to a completed hardware CLEAR"
    )
post_clear = body[clear_at:]
if "goto err_restore" in post_clear or post_clear.count("goto err_disarm;") < 2:
    raise SystemExit("FAIL: a post-CLEAR acquire failure can bypass event retirement")

watchdog_match = re.search(
    r"static void tandem_watchdog_work\(.*?\n\}\n\nstatic int tandem_acquire_locked",
    source,
    re.DOTALL,
)
if watchdog_match is None or (
    "tandem_release_locked(st);" not in watchdog_match.group(0)
    or "st->software_fault |= ADI_TANDEM_AGC_FAULT_WATCHDOG"
    not in watchdog_match.group(0)
):
    raise SystemExit("FAIL: watchdog does not preserve release failure diagnostics")

print(
    "PASS: tandem release and acquire-abort paths quiesce, retire bounded FIFO "
    "records, preserve diagnostics, and fail observably"
)
PY
