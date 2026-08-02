#!/bin/sh
set -eu

TEST_DIR=$(mktemp -d)
SUPERVISOR=$(dirname "$0")/sdr_usb_gadget_supervisor.sh
trap 'rm -rf "$TEST_DIR"' EXIT

cat > "$TEST_DIR/fake_gadget" <<'EOF'
#!/bin/sh
printf 'start:%s\n' "$(cat "$SPF_GADGET_UDC_PATH")" >> "$SPF_GADGET_TEST_EVENTS"
echo 'Ready :-)'
exit 7
EOF
chmod +x "$TEST_DIR/fake_gadget"

cat > "$TEST_DIR/fake_logger" <<'EOF'
#!/bin/sh
echo "$*" >> "$SPF_GADGET_TEST_LOG"
EOF
chmod +x "$TEST_DIR/fake_logger"
printf '%s\n' test_udc > "$TEST_DIR/udc"

export SPF_GADGET_BIN="$TEST_DIR/fake_gadget"
export SPF_GADGET_LOGGER="$TEST_DIR/fake_logger"
export SPF_GADGET_RESTART_DELAY_SECONDS=0
export SPF_GADGET_REBIND_DELAY_SECONDS=0
export SPF_GADGET_READY_DELAY_SECONDS=0
export SPF_GADGET_MAX_RESTARTS=3
export SPF_GADGET_TEST_EVENTS="$TEST_DIR/events"
export SPF_GADGET_TEST_LOG="$TEST_DIR/log"
export SPF_GADGET_UDC_PATH="$TEST_DIR/udc"
export SPF_GADGET_UDC_NAME=test_udc

set +e
"$SUPERVISOR" "$TEST_DIR/ffs"
STATUS=$?
set -e
[ "$STATUS" -eq 7 ]
[ "$(wc -l < "$TEST_DIR/events")" -eq 3 ]
[ "$(sed -n '1p' "$TEST_DIR/events")" = start:test_udc ]
[ "$(sed -n '2p' "$TEST_DIR/events")" = start: ]
[ "$(sed -n '3p' "$TEST_DIR/events")" = start: ]
[ "$(cat "$TEST_DIR/udc")" = test_udc ]
[ "$(grep -c 'rebound composite USB gadget' "$TEST_DIR/log")" -eq 2 ]

cat > "$TEST_DIR/fake_gadget" <<'EOF'
#!/bin/sh
trap 'echo term >> "$SPF_GADGET_TEST_EVENTS"; exit 0' INT TERM
echo start >> "$SPF_GADGET_TEST_EVENTS"
echo 'Ready :-)'
while :; do sleep 1; done
EOF
chmod +x "$TEST_DIR/fake_gadget"
: > "$TEST_DIR/events"
export SPF_GADGET_MAX_RESTARTS=0
: > "$TEST_DIR/log"

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
