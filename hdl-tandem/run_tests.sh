#!/usr/bin/env bash
#
# Tandem AGC HDL test suite. Follows the repository's existing iverilog pattern
# (see hdl-quantulum/util_upack2_timestamp/test/run_*.sh): compile with
# iverilog -g2012, run with vvp, and let the testbench $fatal on failure.
#
# There are no SystemVerilog concurrent assertions here -- Icarus has no support
# for them and this repository uses none. The twelve §10 assertions are
# procedural checkers in tandem_agc_checkers.v.

set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/tandem-agc.XXXXXX")"
trap 'rm -rf "${work}"' EXIT

run() {
    local top="$1"; shift
    local extra="${EXTRA_ARGS:-}"
    echo "--- ${top} ${extra} ---"
    # shellcheck disable=SC2086
    iverilog -g2012 -Wall ${extra} -s "${top}" -o "${work}/${top}" "$@"
    vvp "${work}/${top}"
}

# 1. the model must be right before anything is tested against it
run tb_ad9361_model "${here}/ad9361_gain_model.v" "${here}/tb_ad9361_model.v"

# 2. closed loop at ratio 1.0 (rx_fir_dec = 2, SPF production at 30 MS/s)
EXTRA_ARGS="" run tb_tandem_agc \
    "${here}/ad9361_gain_model.v" "${here}/tandem_agc_core.v" \
    "${here}/tandem_agc_checkers.v" "${here}/tb_tandem_agc.v"

# 3. closed loop at ratio 2.0 (rx_fir_dec = 1, the device-tree boot default and
#    the case where a naive two-cycle pulse would be illegal)
EXTRA_ARGS="-Ptb_tandem_agc.CLKRF_DIV=2" run tb_tandem_agc \
    "${here}/ad9361_gain_model.v" "${here}/tandem_agc_core.v" \
    "${here}/tandem_agc_checkers.v" "${here}/tb_tandem_agc.v"

# 4. §8.2 edge cases: randomised traffic, reset in every state, disable at every
#    pulse phase, chatter, long idle, FIFO overflow, rollover, index mismatch
run tb_tandem_agc_stress \
    "${here}/ad9361_gain_model.v" "${here}/tandem_agc_core.v" \
    "${here}/tandem_agc_checkers.v" "${here}/tb_tandem_agc_stress.v"

# 5. the control surface, driven exactly as software will drive it
run tb_tandem_agc_regs \
    "${here}/ad9361_gain_model.v" "${here}/tandem_agc_core.v" \
    "${here}/tandem_agc_regs.v" "${here}/tb_tandem_agc_regs.v"

echo
echo "ALL TANDEM AGC TESTS PASSED"
