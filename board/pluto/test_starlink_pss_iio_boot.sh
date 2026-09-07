#!/bin/sh

set -eu

TEST_DIR=$(mktemp -d)
LOADER=$(dirname "$0")/S22starlink_pss_iio
trap 'rm -rf "$TEST_DIR"' EXIT

make_fixture()
{
	fixture=$1
	mkdir -p "$fixture/modules" "$fixture/iio" "$fixture/run"
	: > "$fixture/proc_modules"
	: > "$fixture/insmod_calls"
	: > "$fixture/log"
	touch "$fixture/modules/adi_starlink_pss_tracker.ko"
	touch "$fixture/modules/adi_starlink_pss_map.ko"

	cat > "$fixture/insmod" <<'EOF'
#!/bin/sh
module=$(basename "$1" .ko)
echo "$module" >> "$STARLINK_PSS_TEST_CALLS"
if [ "${STARLINK_PSS_TEST_FAIL_MODULE:-}" = "$module" ]; then
	exit 17
fi
echo "$module 1 0 - Live 0x0" >> "$STARLINK_PSS_PROC_MODULES"
case "$module" in
  adi_starlink_pss_tracker)
	device_name=starlink-pss-track
	device_number=3
	;;
  adi_starlink_pss_map)
	device_name=starlink-pss-map
	device_number=4
	;;
esac
mkdir -p "$STARLINK_PSS_IIO_ROOT/iio:device${device_number}"
echo "$device_name" > "$STARLINK_PSS_IIO_ROOT/iio:device${device_number}/name"
EOF
	chmod +x "$fixture/insmod"

	cat > "$fixture/logger" <<'EOF'
#!/bin/sh
echo "$*" >> "$STARLINK_PSS_TEST_LOG"
EOF
	chmod +x "$fixture/logger"
}

run_loader()
{
	fixture=$1
	STARLINK_PSS_MODULE_DIR="$fixture/modules" \
	STARLINK_PSS_IIO_ROOT="$fixture/iio" \
	STARLINK_PSS_PROC_MODULES="$fixture/proc_modules" \
	STARLINK_PSS_RUN_DIR="$fixture/run" \
	STARLINK_PSS_INSMOD="$fixture/insmod" \
	STARLINK_PSS_LOGGER="$fixture/logger" \
	STARLINK_PSS_TEST_CALLS="$fixture/insmod_calls" \
	STARLINK_PSS_TEST_LOG="$fixture/log" \
	STARLINK_PSS_TEST_FAIL_MODULE="${2:-}" \
	"$LOADER" start
}

PASS_FIXTURE="$TEST_DIR/pass"
make_fixture "$PASS_FIXTURE"
run_loader "$PASS_FIXTURE"
grep -qx 'overall=PASS' "$PASS_FIXTURE/run/starlink-pss-iio-load"
[ "$(wc -l < "$PASS_FIXTURE/insmod_calls")" -eq 2 ]
grep -q 'PSS IIO boot binding PASS' "$PASS_FIXTURE/log"

# A repeated start is idempotent and must not call insmod again.
run_loader "$PASS_FIXTURE"
grep -qx 'overall=PASS' "$PASS_FIXTURE/run/starlink-pss-iio-load"
[ "$(wc -l < "$PASS_FIXTURE/insmod_calls")" -eq 2 ]

FAIL_FIXTURE="$TEST_DIR/fail"
make_fixture "$FAIL_FIXTURE"
set +e
run_loader "$FAIL_FIXTURE" adi_starlink_pss_map
status=$?
set -e
[ "$status" -eq 1 ]
grep -qx 'overall=FAIL' "$FAIL_FIXTURE/run/starlink-pss-iio-load"
grep -q 'module=adi_starlink_pss_map .*state=insmod-failed present=no' \
	"$FAIL_FIXTURE/run/starlink-pss-iio-load"
grep -q 'PSS IIO boot binding FAIL' "$FAIL_FIXTURE/log"

# The loader is lifecycle-only: it must never activate either FPGA engine.
! grep -Eq 'acquisition_enable|schedule_enable' "$LOADER"
grep -Fq 'S22starlink_pss_iio' "$(dirname "$0")/post-build.sh"

printf '%s\n' 'PASS: PSS IIO devices bind before iiOD and failures are recorded'
