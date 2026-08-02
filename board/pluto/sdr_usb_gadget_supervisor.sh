#!/bin/sh

# Restart only the vendor direct-USB FunctionFS daemon. Its filesystem is
# mounted with no_disconnect=1, so closing the last child descriptor
# deactivates only this function instead of unregistering the composite gadget.
# Standard iiod remains available while the replacement process reopens ep0.

GADGET_BIN=${SPF_GADGET_BIN:-/usr/sbin/sdr_usb_gadget}
RESTART_DELAY=${SPF_GADGET_RESTART_DELAY_SECONDS:-1}
MAX_RESTARTS=${SPF_GADGET_MAX_RESTARTS:-0}
LOGGER=${SPF_GADGET_LOGGER:-logger}
READY_ATTEMPTS=${SPF_GADGET_READY_ATTEMPTS:-50}
READY_DELAY=${SPF_GADGET_READY_DELAY_SECONDS:-0.1}
CHILD_LOG=${SPF_GADGET_CHILD_LOG:-}
DEBUG=0
CHILD_PID=
STOPPING=0
RESTART_COUNT=0

if [ "$1" = "-d" ]; then
	DEBUG=1
	shift
fi

if [ "$#" -ne 1 ]; then
	echo "Usage: $0 [-d] FFS_DIRECTORY" >&2
	exit 64
fi

if [ -z "$CHILD_LOG" ]; then
	if [ "$DEBUG" -eq 1 ]; then
		CHILD_LOG=/var/log/sdr_usb_gadget.log
	else
		CHILD_LOG=/tmp/sdr_usb_gadget_supervisor_child.log
	fi
fi

stop_child() {
	STOPPING=1
	if [ -n "$CHILD_PID" ]; then
		kill "$CHILD_PID" 2>/dev/null
		wait "$CHILD_PID" 2>/dev/null
	fi
	exit 0
}

trap stop_child INT TERM

wait_for_child_ready() {
	ATTEMPT=1
	while [ "$ATTEMPT" -le "$READY_ATTEMPTS" ]; do
		if grep -q '^Ready :-)$' "$CHILD_LOG" 2>/dev/null; then
			return 0
		fi
		if ! kill -0 "$CHILD_PID" 2>/dev/null; then
			return 1
		fi
		sleep "$READY_DELAY"
		ATTEMPT=$((ATTEMPT + 1))
	done
	return 1
}

while [ "$STOPPING" -eq 0 ]; do
	: > "$CHILD_LOG"
	if [ "$DEBUG" -eq 1 ]; then
		"$GADGET_BIN" -d "$1" > "$CHILD_LOG" 2>&1 &
	else
		"$GADGET_BIN" "$1" > "$CHILD_LOG" 2>&1 &
	fi
	CHILD_PID=$!
	if ! wait_for_child_ready; then
		"$LOGGER" -t sdr_usb_gadget \
			"direct-USB gadget failed readiness restart=$RESTART_COUNT log=$CHILD_LOG"
		kill "$CHILD_PID" 2>/dev/null
		wait "$CHILD_PID" 2>/dev/null
		CHILD_PID=
		RESTART_COUNT=$((RESTART_COUNT + 1))
		if [ "$MAX_RESTARTS" -gt 0 ] && [ "$RESTART_COUNT" -ge "$MAX_RESTARTS" ]; then
			exit 1
		fi
		sleep "$RESTART_DELAY"
		continue
	fi
	if [ "$RESTART_COUNT" -gt 0 ]; then
		"$LOGGER" -t sdr_usb_gadget \
			"recovered direct-USB gadget process restart=$RESTART_COUNT"
	fi
	wait "$CHILD_PID"
	STATUS=$?
	CHILD_PID=
	RESTART_COUNT=$((RESTART_COUNT + 1))
	"$LOGGER" -t sdr_usb_gadget \
		"direct-USB gadget exited status=$STATUS restart=$RESTART_COUNT"
	if [ "$MAX_RESTARTS" -gt 0 ] && [ "$RESTART_COUNT" -ge "$MAX_RESTARTS" ]; then
		exit "$STATUS"
	fi
	sleep "$RESTART_DELAY"
done

exit 0
