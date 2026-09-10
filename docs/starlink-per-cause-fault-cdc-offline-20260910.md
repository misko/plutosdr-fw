# Per-cause fault CDC candidate — offline proof only

**122 tests pass in 22.78s**, original42701 exit0: new37 CDC/inverse tests,
unchanged exact-control49, forward-retirement17 and payload-bubble19. Parent
independent replay also passed122 in22.60s. No actual FFT, synthesis or route
has run on this candidate; the prior negative route remains immutable.

Tested source pins: FW `640cf54b8a28e979e62f90a8c57e911bb789ac7c` /
HDL `02de07cc7a6c241dd6cc8cf5b733037d89eac6bd`.
Wrapper SHA `e8285f5ef2b548272ec357fca5213b1e400b5242396be2597498eff09f665579`.

The only runtime delta is23 additive wrapper lines: default-off
PER_CAUSE_FAULT_CDC, fail-closed0/1 checks including X/Z, and a new generate around
the original slow synchronizer. Enabling it requires DISTRIBUTED_FAST_FAULT.
Each of12 source sticky Q bits feeds its own two-bit ASYNC_REG synchronization
structure, clocked by clk and cleared by the unchanged slow_running epoch.
ORs of destination stage0/stage1 retain the observable fast_fault_slow[0]/[1]
names. All fast-domain sticky recurrence, current fault fences, detailed reasons,
reset release, bank ownership, commit/ACK and public gate expressions are literal.

Nominal recurrence: with common slow reset R, old stage0'=R?OR(Q):0 and
stage1'=R?stage0:0. Independent per-bit stages T0_i'=R?Q_i:0 and
T1_i'=R?T0_i:0 give the same aggregate after each slow edge. This is a digital
four-state recurrence, not analog metastability equivalence or bus coherency.
The logical budget is24 sync FF versus2 (+22 before optimization), plus the
slow-domain OR cone. No realized resource or CDC-report improvement is claimed.

The new bench instantiates actual candidate modules and seven independently
frozen old modules from HDL2ccfac2e, plus a separately written scalar recurrence.
The FFT is explicitly a quiescent stub. Forced source-Q snapshots include all
4096 binary subsets,48 X/Z rows, transitions and nonmonotone/unreachable snapshots.
Each enabled run uses3 epoch resets (each one-sided and both) plus a separate
private core reset while fault remains held; reset assertion/release is offset
from clock edges. Registered modes0/1 run at slow phases0/713/2857ps. Each records
16836 slow checks and29464 fast checks. Aggregate default mode also passes both
registered modes. This is not active FFT/output-bank fault-epoch coverage.

All12 missing-cause mutations, missing synchronization stage, wrong private/epoch
reset and added latency are behaviorally rejected. Six malformed CDC/default/body
mutations are also rejected by the strict literal inverse. Invalid−1/2/X/Z and
enabled-without-distributed settings fail closed. The entire seven-module runtime
inverse and original actual bench bytes match the frozen baseline. The four-line
compatibility import/call strips this exact CDC addition before the untouched
legacy inverse, with an inverse proving the entire old Python helper unchanged.

Retained originals:36038 exit0,30PASS/5.68s;46213 exit1,48PASS/1FAIL/14.80s.
The sole failure was
test_exact_control.py::test_literal_seven_module_inverse_and_actual_stimulus_unchanged:
the old contiguous D/S parameter anchor did not include the new CDC parameter.
No old assertion or expected byte was changed. A failed patch-anchor attempt
made no edits; corrected compatibility/inverse tests pass in the final122 run.

Archive: `hdl/library/starlink_pss_acquisition/evidence/per-cause-fault-cdc-offline-v1/`.
It preserves final source/dependencies, original snapshot/failure, all final raw
compile/simulation receipts and new-case generated wrapper/bench witnesses.

Next proposal, not authorized execution: derive fresh no-overwrite P0/P1 actual
preparations from the passing R1/D1/S1/extras1/175/QUICK0 combined freeze. Change
only candidate wrapper bytes, explicit new top-level parameter forwarding and
additive slow-clock stage-pair observer/receipt. Reference remains frozen dec20
R1/D0/S0. Preserve every old stimulus, comparison, current-fault/ownership assertion,
CSV/latency gate and qualified-status accounting; no raw217 PASS claim. Require
literal source/bench inverse, explicit elaboration/binding checks, stage0/stage1
equality at both slow edges and nonzero fault/reset checks. Historical mainCSV
25ab9d06... and full extra pair b965d126... remain expected, with invalid-status
counts audited rather than fitted to prior totals. Review preparation before
actual launch; new actual and physical evidence are required before CDC closure.

## Remaining kernel-ROM enable path: read-only options

The failed route's product metadata → result validity → ROM CE is real:
output_kernel_word writes only on input_accept&&!protocol_error_now. Reading
under input_ready alone would hold occupied/stalled outputs and retain valid
tokens/control latency, but would change invalid-cycle coefficient payload on
bubbles/malformed words. That is NOT the present observation contract: existing
payload shadow requires kernel I/Q equality unconditionally. No observer waiver
or source change is proposed as already safe.

A separate private prefetch can remove that BRAM enable dependency while retaining
raw visible words: read prefetched_word under input_ready; keep last_visible_word
in36 FF updated from the previous prefetched word whenever the previous output_valid
was1; expose output_kernel_word=output_valid?prefetched_word:last_visible_word.
Reset both words identically. Healthy accepts update private data and unchanged
validity together; draining/bad/bubble edges retain the previous visible word;
occupied stalls hold. This may preserve zero token latency and all invalid-cycle
visible data, but costs36 FF plus a36-bit mux and may worsen the already relevant
ROM→DSP operand path. It is a hypothesis requiring independent full-word/control
shadows, X/invalid/stall/refill/fault/reset tests and mapped CE/data-path inventory.

A registered descriptor certificate alone cannot replace current per-beat checks:
active identity/ordinal/TLAST corruption must still veto the same public edge.
It could only authorize private speculative work while the original current
checker remains the publication gate. A new pipeline boundary would instead need
paired payload/metadata and poison/ownership handling plus an explicitly reviewed
latency contract. Scratch writes are not retirement; no current guard, final
commit or ACK veto may be bypassed. No ROM implementation is authorized here.
