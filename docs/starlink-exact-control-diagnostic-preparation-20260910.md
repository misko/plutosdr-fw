# Same-fatal named diagnostics — prepared, not run with actual FFT

Final offline selection: **50 passed in2.31s**, original82851 exit0
(six diagnostic tests plus44 existing preparation tests). No diagnostic
actual run, RTL edit, other mode or physical run was launched. The two
original actual failures remain immutable at FW5fe9ac36/HDL29fa754a.

Tested diagnostic source: FW `d22a91af005ad86d6a7e700f73e23484d06367bd` /
HDL `1f0068e61f56fb9af9af22e6ba13e086763d0e6c`. New prepared directory:
`/tmp/starlink-completed-input.5EaJuD/exact-control-diagnostic-actual-v1`.
It copies the original failed r0-d0-s0 freeze, verifies its complete
inventory SHA `13f525d4fa04a0f84cf4c0a26fecdd2173091556686af2feaee60379e96ab757`,
and preserves R0/D0/S0/extras1/175MHz/QUICK0. No project exists there yet.

Only TWO existing frozen files differ: the candidate bench adds a diagnostic
task, and the observer calls that task immediately before the identical
original fatal inside the SAME mismatch branch after the SAME2ps delay.
There are no new waits, signal drives, state changes, predicates, maskings
or acceptance changes. A task-local counter is initialized0 and incremented
for each printed mismatch; it is diagnostic bookkeeping, not RTL state.
The original equality expression, observer ports/counters, original entire
stimulus, reference bench, extra epochs, runner, settings, numerical/latency
assertions and historical CSV gates remain literal. All seven RTL remainae50.

For each differing field, the task prints its exact name, both runtime
widths, hexadecimal values and full four-state binary values. It checks all
217 original fields, plus prints both injected_status, test_kind, clk,
fft_clk, fast_cycle, slow_cycle, epoch, resetn and fft_resetn. The final row
prints mismatch count, original exact_public_equal and a freshly evaluated
case equality of the SAME217-field tuple. Zero named mismatches does not
suppress the original fatal; a0/1 old/fresh discrepancy would be evidence
to investigate delta ordering, not a pass or an accepted contract change.

Strict whole-file inverses restore both modified frozen bodies to original
bytes; every other original source and the entire settings file compare
unchanged. The full paired bench compiles with a non-executed quiescent
vendor stub, and its original comparison still elaborates to2168bits.
This is not FFT numerical proof.

An independent no-FFT fixture executes only the observer/task. Healthy
inputs emit no diagnostics; one status difference and217 simultaneous
differences print their exact names, widths, bit69 and X/Z binary values
before the unchanged fatal. Context values independently differ between
candidate/reference. A forced false boolean with all named values equal
prints `mismatches=0 original_equal=0 fresh_equal=1` and STILL fatals at the
same9.002ns observation. That synthetic case tests diagnostic behavior,
not an explanation of the actual epoch11 failure. Wrong baseline inventory
and output reuse are rejected. Ruff passes. Initial six-pass preparation
receipt before the requested count/fresh-equality addition is retained.

Prepared observer SHA:
`4c1cd975bad3dc9b4597ea7ddb69d6ce315fdc137e94d71cf9512c2cda25e7d3`.
Prepared bench SHA:
`f1e9a2e32241a268d507e44676e8d2effb1bee6fed8fce7c2279198a4a3a7e45`.
Unchanged runner SHA:
`496a3ed4a2b55d494a22fd78f64b4a68580d923b398f5282e31145dc6a7951b0`.

Archive: `hdl/library/starlink_pss_acquisition/evidence/exact-control-diagnostic-preparation-v1/`
contains the full prepared freeze, source tests, exact generated diffs,
compile-only logs and standalone positive/negative receipts. Raw test
directory: `/tmp/starlink-completed-input.5EaJuD/exact-control-diagnostic-preparation-v2`.
Pending source-specific approval, the next action is ONE fresh baseline
actual diagnostic using the new directory and original handle. Its intended
outcome is an exact named witness for the failure, not receiver qualification.
No source, CSV, numerical or receipt relaxation is authorized.
