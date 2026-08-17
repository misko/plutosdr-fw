#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SUPERVISOR="$SCRIPT_DIR/iiod_supervisor.sh"
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT INT TERM

printf '%s\n' '#!/bin/sh' \
	'printf "start:%s:%s\\n" "$1" "$2" >> "$SPF_IIOD_TEST_EVENTS"' \
	'exit 70' > "$TEST_DIR/fake_iiod"
chmod +x "$TEST_DIR/fake_iiod"
printf '%s\n' '#!/bin/sh' \
	'printf "%s\\n" "$*" >> "$SPF_IIOD_TEST_LOG"' > "$TEST_DIR/fake_logger"
chmod +x "$TEST_DIR/fake_logger"
: > "$TEST_DIR/pmsg"

export SPF_IIOD_BIN="$TEST_DIR/fake_iiod"
export SPF_IIOD_LOGGER="$TEST_DIR/fake_logger"
export SPF_IIOD_PMSG_PATH="$TEST_DIR/pmsg"
export SPF_IIOD_GENERATION_FILE="$TEST_DIR/generation"
export SPF_IIOD_CHILD_PID_FILE="$TEST_DIR/child.pid"
export SPF_IIOD_RESTART_DELAY_SECONDS=0
export SPF_IIOD_MAX_RESTARTS=3
export SPF_IIOD_TEST_EVENTS="$TEST_DIR/events"
export SPF_IIOD_TEST_LOG="$TEST_DIR/log"

set +e
"$SUPERVISOR" -D -n
STATUS=$?
set -e
[ "$STATUS" -eq 70 ]
[ "$(wc -l < "$TEST_DIR/events")" -eq 3 ]
[ "$(cat "$TEST_DIR/generation")" -eq 3 ]
[ "$(grep -c 'child exited status=70' "$TEST_DIR/log")" -eq 3 ]
[ "$(grep -c 'child exited status=70' "$TEST_DIR/pmsg")" -eq 1 ]
[ ! -e "$TEST_DIR/child.pid" ]

printf 'PASS: iiOD supervised restart red/green cases\n'
