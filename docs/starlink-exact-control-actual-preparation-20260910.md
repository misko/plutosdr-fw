# Exact-control actual-core preparation — not executed

Offline preparation is complete: **93 tests passed in16.40s** (original
session20822, exit0), comprising44 new preparation/observer/receipt tests
and49 existing exact-control fast tests. **No actual FFT simulation,
synthesis, route or radio run was launched.** Active numerical/control
equivalence remains an unexecuted gate, not a result of stub elaboration.

Final tested preparation source: FW `7cc98f66b834c0c3f015c8dccf41e8b051232d7c`,
HDL `d5cc9f28ecd389e277a2278131661b6f21beac41`. All seven RTL files remain
byte-identical to tested `ae50b1889fd10cd762fb60266aecbb7c163e1d1a` and the
prior archived RTL `978371f0e8f9a36bc43c2f315d4eebe5d9ec9ce7`.
The canonical actual bench remains literal
`dec20d6371f2d77b6e09c4bcdda2f3d7f8715776`; that pin supplies the independent
old whole-module reference. The only additions are four offline/simulation
helper files and one Python test file. No rounding or operand change is
included; the earlier failed physical measurements remain immutable.

## Prepared matrix and independence

Eight unique freezes are under
`/tmp/starlink-completed-input.5EaJuD/exact-control-actual-matrix-v3/`.
Each has its own settings, source inventory and SHA256SUMS; all use175MHz,
QUICK_MUTATION=0 and EXACT_EXTRA_EPOCHS=1. R is REGISTERED_SCHEDULING,
D is DISTRIBUTED_FAST_FAULT, S is PRIVATE_NEXT_START_SCRATCH.

| R | D/S00 | D/S01 | D/S10 | D/S11 |
|---|---|---|---|---|
|0|r0-d0-s0|r0-d0-s1|r0-d1-s0|r0-d1-s1|
|1|r1-d0-s0|r1-d0-s1|r1-d1-s0|r1-d1-s1|

All eight were **compiled only** with a quiescent vendor stub; none of those
executables was run. An eventual authorized simulation instantiates TWO
independent real vendor cores: candidate and dec20 reference, each driven
by its own complete original bench, including its own force/release tasks.
No candidate internals drive the reference. Exact whole-bench inverse tests
restore both generated benches to the original bytes after stripping only
the additive helper regions, parameter plumbing, reference renaming,
distinct trace filename and reference completion flag. All original
healthy/fault stimulus, numerical/latency assertions, old shadows and
84+12 boundary/active fault checks are preserved literally.

The additive observer compares217 named fields (2168 compiled bits) twice
per fast-clock cycle after2ps settlement: public ports, raw current fences,
detailed/sticky reasons, scheduling state, ownership/reservations/leases,
commit/ACK, core transport/status/events, guard state, ROM state/checks and
all three bank identities/cursors/toggles/read payloads. The only excluded
ROM state is the permitted private next-start scratch. Its64 bits are
compared before every actual next-identity consumption, including malformed
input; consume events themselves must agree. Private differences and all
coverage counters are reported, including reset-owned counts even if zero.
Independent full-size vendor execution, settling behavior and resulting
active coverage counts have NOT yet been measured.

## Additional epochs and terminal gates

After every original assertion/receipt, both benches separately execute
four new epochs: a current vendor last-missing fault at a genuinely
qualified forward final slot; the same fault after three held-final stall
cycles; slow-only reset while that slot is held; and fast-only reset while
held. Each epoch checks its final boundary before injection and performs a
fresh healthy recovery afterward. Fault cases check same-edge retirement,
commit and ACK veto, sticky exact reason, quarantine and no poisoned
product/inverse ownership escape. These tasks are prepared/elaborated,
**not evidence that the intended boundaries were reached**.

EXACT_EXTRA_EPOCHS defaults0 in both generated benches and rejects−1,2,X,Z
using case inequality. Standalone literal entry-check tests apply these
values using SystemVerilog instance overrides, without running an actual
bench. The future runner rejects reused project paths and checks source
hashes before/after, explicit options and175MHz. Its offline-tested parser
requires exactly one parameter-matched actual terminal, nonzero checks,
active and consumed counts, and with extras1 at least two active final-fault
edges and three owned-stall observations. It also requires exactly TWO
independently asserted extra receipts, each with2 faults/3 stalls/2 one-sided
resets/4 recoveries; candidate completion requires reference_done.
Malformed settings, zero counts, missing reference receipt, wrong counts
and duplicate terminals are rejected. A Tcl completeness check does not
claim Vivado command execution.

Original complete candidate/reference CSVs must match each other AND the
unchanged historical hash: R0
`b0d60e80101b34ff163b85ef7547814e0403561b315f975eb38a98817b7eb84d`, R1
`25ab9d06ca0e03f280540cda625a7826b3c4cbaa6322ce3266c59e1fbad94122`.
Extra epochs write separate traces and cannot retune the original gate.

## Retained preparation failures

Initial14-pass and63-pass receipts are retained but do NOT prove an adequate
observer: Icarus resolved the original hierarchical `$bits` localparam to0.
This was found by reading the compiled VVP before any actual launch.
Initial source FW `e08800d79275cd48b853457fc73db9e356505d7a` /
HDL `d2861397f10109f19e999acf6b8cc0a5a283d479`, initial matrix-v1 and its
zero-width witness remain available. The corrected observer uses
self-sized case-equality concatenations, with no separately sized bus;
every one of eight final elaborations explicitly verifies2168 equality
bits. Standalone observer self-tests reject public, consume and consumed
scratch mismatches. They are observer tests, not FFT proof.

Expanded v5 (session44269, exit1) retained89 passes/four failures: Icarus
command-line `-P` rejected X/Z syntax while returning0 and leaving the
default value, so requested negative stimuli were not applied. Only the
standalone test's parameter injection changed to literal SV overrides;
the same case-inequality body and rejection marker now reject all four
candidate/reference X/Z cases. Final v6 is93/0. Existing timescale and
default-inert dangling old-shadow-port warnings are retained. There are no
skips in this focused selection; the earlier818/10/7 broad snapshot and
its known missing-Linux-file limitations are unchanged, not rerun here.

## Next review gate and runtime estimate

Proposed staged actual execution, pending separate authorization: first
r0-d0-s0 baseline and r1-d1-s1 combined, both extras1; if both pass, run
r1-d1-s0 and r1-d0-s1 for attribution. Retain eight-way offline coverage;
do not start eight concurrent vendor simulations. Use one unique prepared
directory per run, original handles, Vivado2022.2 and two threads, with no
timeout restart or physical run.

Historical single-island175 runs took150s default and248s registered
(simulation CPU136.35s/233.93s). Two independently simulated cores plus the
observer and extra epochs are estimated at4.5–6min/default case and
8–10min/registered case: about13–16min for the first pair,29–36min for four
serial cases, or50–64min for all eight. These are forecasts, not measured
current-runtime limits; allow additional margin for simulator/event load.

Archive: `hdl/library/starlink_pss_acquisition/evidence/exact-control-actual-preparation-v1/`.
It contains all eight final freezes, exact source/test copies, original
and corrected receipts, standalone rejection logs and both retained
preparation failures. Raw runs remain at
`/tmp/starlink-completed-input.5EaJuD/exact-control-actual-preparation-v1` through
`-v6`. Nothing is promoted; primary runtime and physical eligibility are unchanged.
