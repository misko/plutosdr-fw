#!/bin/sh

IIOD_BIN=${SPF_IIOD_BIN:-/usr/sbin/iiod}
RESTART_DELAY=${SPF_IIOD_RESTART_DELAY_SECONDS:-1}
MAX_RESTARTS=${SPF_IIOD_MAX_RESTARTS:-0}
LOGGER=${SPF_IIOD_LOGGER:-logger}
PMSG=${SPF_IIOD_PMSG_PATH:-/dev/pmsg0}
GENERATION_FILE=${SPF_IIOD_GENERATION_FILE:-/run/iiod-generation}
CHILD_PID_FILE=${SPF_IIOD_CHILD_PID_FILE:-/var/run/iiod-child.pid}
ERROR_LOG=${SPF_IIOD_ERROR_LOG:-/dev/kmsg}
CHILD_PID=
STOPPING=0
RESTART_COUNT=0

record_event()
{
	message=$1
	"$LOGGER" -t iiod-supervisor "$message"
	if [ -w "$PMSG" ]; then
		printf 'iiod-supervisor: %s\n' "$message" > "$PMSG" 2>/dev/null || true
	fi
}

stop_child()
{
	STOPPING=1
	if [ -n "$CHILD_PID" ]; then
		kill "$CHILD_PID" 2>/dev/null
		wait "$CHILD_PID" 2>/dev/null
	fi
	rm -f "$CHILD_PID_FILE"
	exit 0
}

trap stop_child INT TERM

while [ "$STOPPING" -eq 0 ]; do
	GENERATION=$((RESTART_COUNT + 1))
	printf '%s\n' "$GENERATION" > "$GENERATION_FILE"
	record_event "starting generation=$GENERATION restart=$RESTART_COUNT"
	# iiOD emits sparse, actionable capture-admission and continuity failures on
	# stderr. Preserve them in the bounded kernel ring instead of inheriting the
	# background launcher's /dev/null; tests may substitute a regular file.
	if [ -w "$ERROR_LOG" ]; then
		"$IIOD_BIN" "$@" 2>> "$ERROR_LOG" &
	else
		"$IIOD_BIN" "$@" 2>/dev/null &
	fi
	CHILD_PID=$!
	printf '%s\n' "$CHILD_PID" > "$CHILD_PID_FILE"
	wait "$CHILD_PID"
	STATUS=$?
	CHILD_PID=
	rm -f "$CHILD_PID_FILE"
	RESTART_COUNT=$((RESTART_COUNT + 1))
	record_event "child exited status=$STATUS restart=$RESTART_COUNT"
	if [ "$MAX_RESTARTS" -gt 0 ] && [ "$RESTART_COUNT" -ge "$MAX_RESTARTS" ]; then
		exit "$STATUS"
	fi
	sleep "$RESTART_DELAY"
done

exit 0
