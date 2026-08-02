#!/bin/sh

# Restart only the vendor direct-USB FunctionFS daemon. Standard iiod remains
# untouched, so radio configuration stays available while the host detects the
# new gadget process nonce and starts a new capture artifact.

GADGET_BIN=${SPF_GADGET_BIN:-/usr/sbin/sdr_usb_gadget}
RESTART_DELAY=${SPF_GADGET_RESTART_DELAY_SECONDS:-1}
MAX_RESTARTS=${SPF_GADGET_MAX_RESTARTS:-0}
LOGGER=${SPF_GADGET_LOGGER:-logger}
UDC_PATH=${SPF_GADGET_UDC_PATH:-/sys/kernel/config/usb_gadget/composite_gadget/UDC}
UDC_NAME=${SPF_GADGET_UDC_NAME:-ci_hdrc.0}
REBIND_DELAY=${SPF_GADGET_REBIND_DELAY_SECONDS:-0.2}
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

rebind_udc() {
	# Closing the last FunctionFS descriptor disconnects the whole composite
	# gadget. Starting a new daemon republishes descriptors, but the host will
	# not see them until the UDC is explicitly rebound.
	if [ ! -w "$UDC_PATH" ]; then
		"$LOGGER" -t sdr_usb_gadget \
			"cannot rebind direct-USB gadget: UDC path is not writable: $UDC_PATH"
		return 1
	fi
	if ! printf '\n' > "$UDC_PATH"; then
		"$LOGGER" -t sdr_usb_gadget \
			"cannot unbind direct-USB gadget from UDC: $UDC_PATH"
		return 1
	fi
	sleep "$REBIND_DELAY"
	if ! printf '%s\n' "$UDC_NAME" > "$UDC_PATH"; then
		"$LOGGER" -t sdr_usb_gadget \
			"cannot bind direct-USB gadget to UDC: $UDC_NAME"
		return 1
	fi
	"$LOGGER" -t sdr_usb_gadget \
		"rebound composite USB gadget after direct-USB daemon restart=$RESTART_COUNT"
}

while [ "$STOPPING" -eq 0 ]; do
	if [ "$DEBUG" -eq 1 ]; then
		"$GADGET_BIN" -d "$1" > /var/log/sdr_usb_gadget.log 2>&1 &
	else
		"$GADGET_BIN" "$1" > /dev/null 2>&1 &
	fi
	CHILD_PID=$!
	if [ "$RESTART_COUNT" -gt 0 ]; then
		sleep "$REBIND_DELAY"
		if ! rebind_udc; then
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
