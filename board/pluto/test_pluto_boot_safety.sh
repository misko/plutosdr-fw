#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
S23UDC="$SCRIPT_DIR/S23udc"

mute_line=$(grep -n -m1 '/usr/sbin/pluto-mute-tx' "$S23UDC" | cut -d: -f1)
identity_line=$(grep -n -m1 'serial=$(/usr/sbin/pluto-read-identity' "$S23UDC" | cut -d: -f1)
bind_line=$(grep -n -m1 'echo ci_hdrc.0 > $GADGET/UDC' "$S23UDC" | cut -d: -f1)

[ "$mute_line" -lt "$identity_line" ]
[ "$identity_line" -lt "$bind_line" ]
[ "$(grep -c '/usr/sbin/device_reboot ram' "$S23UDC")" -eq 1 ]
grep -Fq 'IDENTITY-RECOVERY/RNDIS/MSD/ACM' "$S23UDC"
grep -Fq 'RF services withheld' "$S23UDC"

printf '%s\n' "PASS: TX mute and identity recovery remain fail-closed"
