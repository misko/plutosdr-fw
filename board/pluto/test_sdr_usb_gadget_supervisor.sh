#!/bin/sh
set -eu

TEST_DIR=$(mktemp -d)
SUPERVISOR=$(dirname "$0")/sdr_usb_gadget_supervisor.sh
trap 'rm -rf "$TEST_DIR"' EXIT

cat > "$TEST_DIR/fake_gadget" <<'EOF'
#!/bin/sh
echo start >> "$SPF_GADGET_TEST_EVENTS"
exit 7
EOF
chmod +x "$TEST_DIR/fake_gadget"

export SPF_GADGET_BIN="$TEST_DIR/fake_gadget"
export SPF_GADGET_LOGGER=true
export SPF_GADGET_RESTART_DELAY_SECONDS=0
export SPF_GADGET_MAX_RESTARTS=3
export SPF_GADGET_TEST_EVENTS="$TEST_DIR/events"

set +e
"$SUPERVISOR" "$TEST_DIR/ffs"
STATUS=$?
set -e
[ "$STATUS" -eq 7 ]
[ "$(wc -l < "$TEST_DIR/events")" -eq 3 ]

cat > "$TEST_DIR/fake_gadget" <<'EOF'
#!/bin/sh
trap 'echo term >> "$SPF_GADGET_TEST_EVENTS"; exit 0' INT TERM
echo start >> "$SPF_GADGET_TEST_EVENTS"
while :; do sleep 1; done
EOF
chmod +x "$TEST_DIR/fake_gadget"
: > "$TEST_DIR/events"
export SPF_GADGET_MAX_RESTARTS=0

"$SUPERVISOR" "$TEST_DIR/ffs" &
SUPERVISOR_PID=$!
for ATTEMPT in 1 2 3 4 5; do
	[ -s "$TEST_DIR/events" ] && break
	sleep 0.1
done
kill "$SUPERVISOR_PID"
wait "$SUPERVISOR_PID"
grep -qx start "$TEST_DIR/events"
grep -qx term "$TEST_DIR/events"
