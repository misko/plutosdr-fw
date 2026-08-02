#!/bin/sh

# Restart only the vendor direct-USB FunctionFS daemon. Standard iiod remains
# untouched, so radio configuration stays available while the host detects the
# new gadget process nonce and starts a new capture artifact.

GADGET_BIN=${SPF_GADGET_BIN:-/usr/sbin/sdr_usb_gadget}
RESTART_DELAY=${SPF_GADGET_RESTART_DELAY_SECONDS:-1}
MAX_RESTARTS=${SPF_GADGET_MAX_RESTARTS:-0}
LOGGER=${SPF_GADGET_LOGGER:-logger}
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

stop_child() {
	STOPPING=1
	if [ -n "$CHILD_PID" ]; then
		kill "$CHILD_PID" 2>/dev/null
		wait "$CHILD_PID" 2>/dev/null
	fi
	exit 0
}

trap stop_child INT TERM

while [ "$STOPPING" -eq 0 ]; do
	if [ "$DEBUG" -eq 1 ]; then
		"$GADGET_BIN" -d "$1" > /var/log/sdr_usb_gadget.log 2>&1 &
	else
		"$GADGET_BIN" "$1" > /dev/null 2>&1 &
	fi
	CHILD_PID=$!
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
