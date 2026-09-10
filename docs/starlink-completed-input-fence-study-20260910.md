# Completed-input return predicate: equivalent tests, failed timing experiment

The bounded experiment preserves the tested bank-owned FFT numerics, public
controls and exact fault reasons. It does **not** improve the measured175MHz
setup path: diagnostic WNS changes from−2.557ns to−3.855ns. This is not eligible
for receiver integration or deployment on the strength of this study. No second
physical iteration, receiver build, radio operation, PPU edit, remote push or
other-agent worktree edit was performed.

## Pins and evidence

- Baseline FW `1035b93d53b8519f18d280e50f7e3ab11e56edce`, HDL
  `169f9fb659bd98b4cb1e76163f4fdb8b853a7d1b`.
- Tested source FW `29586ce04fd5f1bdca92549c9132c7a3f3230252`, HDL
  `0bbc4cdca81da6771f5849c86fd127effd5287f0`.
- Both branches: `codex/starlink-rx-only-do-not-merge-completed-input-fence`.
- Tracked evidence: `hdl/library/starlink_pss_acquisition/evidence/completed-input-fence-v1/`;
  its `provenance.json` and `SHA256SUMS` identify copies of actual logs, frozen
  simulation sources/vectors, the rejected mutation, and synthesis/route reports.
- Original complete run directory: `/tmp/starlink-completed-input.5EaJuD/`.
  The pre-run source snapshot records the then-current baseline commit because
  the candidate was uncommitted; all seven synthesized RTL files were subsequently
  byte-compared with tested HDL0bbc4cdc and its actual-core snapshot, without edits.
- Immutable vector source, read only:
  `/home/mouse9911/gits/plutosdr-fw-starlink-rx-only/hdl/library/starlink_pss_raw_correlator/build/input-cursor-paired-v1/frozen_sources`.
  No coefficient or numerical acceptance gate was changed.

## Exact refactor and its limits

The input guard exports an alias of its existing `duplicate_start` predicate;
its original full metadata/ordinal/TLAST/delivery checks, input certification and
reason accumulation are unchanged. Its already-registered `input_complete`
is the closed-input certificate; no new descriptor identity or epoch counter
is introduced.

The result guard's new `USE_COMPLETED_INPUT_FAULT` parameter defaults to0.
Only the isolated bank-owned wrapper opts in. A visible held return must have
survived the preceding edge's full `output_error`: although the private payload
capture is speculative, missing effective count512/completion/frame sets the
sticky fault bank on that same edge and suppresses the held return. Therefore
the valid occupied-return phase implies registered count512, input completion,
frame and exponent observations. The live input guard is closed in that phase;
its framing/delivery checks and both input-certificate pulses are zero, while
a coincident duplicate start remains an immediate fault.

The specialized predicate retains live output ordinal/TLAST/TUSER/exponent and
status consistency checks, current mailbox/ownership/kernel/product/vendor faults,
and watchdog expiry. A first matching status during a nonfinal return remains
legal; it is not confused with a duplicate status during a qualified final.
The full original `faults_now` and exact reason accumulation still run in every
phase. Default admission and ACK behavior is unchanged. The final fence is the
exact identity `input_complete && !input_guard_fault && !duplicate_start`:
when input_complete is true it equals the original full input-fault fence, and
when false both fences are false. No same-edge final fault veto is registered
or deferred.

The wrapper's specialized external predicate omits the forward handoff check
only for an occupied return: `forward_committed` is set on the edge on which
final commit clears active, and the next job clears that token. Thus the handoff
phase cannot coexist with a visible return. The full handoff identity/position/
TLAST checks remain on product publication, actual ownership ACK and quarantine.
The real mailbox read ACKs still require all512 words. This is a phase proof,
not permission for timing exceptions or arbitrary state-corruption assumptions.

The product-selected metadata to forward join path is also direction-exclusive:
`next_inverse` selects product input while `!next_inverse` enables forward join.
The immutable mailbox descriptor is loaded only when ownership changes and held
through its512th read ACK. Neither observation justifies disabling the live
per-beat identity check: corrupted input metadata must still fault during active
input, including a presented malformed word while the FFT stalls.

## Executed gates

Actual generated FFT,100/175MHz behavioral simulation passed the unchanged
three-bank suite:44 complete healthy blocks,22658 accepted inverse words
(including a130-word provisional prefix),24064 forward and24064 product words,
4 reset/purge cases and10 fault cases. The full-predicate shadow compared public
controls and fault reasons495484 times;101832 occupied-return checks established
the phase premises and equality of full/reduced predicates and final fences.
Nominal maximum forward interval remains4540fast clocks; this does not establish
universal stall capacity or physical clock attainment.

The separate live-input-checker/default-versus-opt-in control test passed4healthy
and26rejected cases,58076 comparisons,15433 return-phase checks and3commits.
It includes legal simultaneous512th certified input/first raw output, malformed
metadata/ordinal/TLAST on that edge, active corruption during a core stall,
closed-input N+1 metadata, and duplicate start during nonfinal, unqualified final,
qualified final and ACK. It also covers first good versus bad/duplicate status,
extra/malformed raw output, ownership/readiness loss, frame and current faults.
Dropping the narrow duplicate-start veto is rejected on its exact nonfinal
same-edge witness (`phase=2 kind=0`). Removing the existing joiner's
product-bank-ready gate is independently rejected by the actual FFT's held-final
retirement witness. Neither failure is accepted as a numerical pass.

The retained final regression run is74passed/6skipped. The six explicit skips
are four older input-cursor synthesized-netlist probes and two older occupancy
physical measurements, not missing cases in the new actual-core or control suite.
Default full-guard-versus-immutable-golden behavior, watchdog/final-veto mutations,
private-state checks, input-retirement checks and evidence-parser checks passed.
Ruff and `git diff --check` passed.

Development failures are recorded in the evidence's `development_failures.md`.
The initial new test examined the old raw-output stimulus immediately after a
capture edge; deasserting raw_valid and allowing combinational settling fixed
the assertion without changing RTL or an acceptance gate. A wider test invocation
then reported13failures:12wildcard-port elaborations lacked names for the new
unused inputs, and one structural input-checker proof did not recognize the new
pure output alias. The wildcard test wires are explicitly Z to verify default
ignoring behavior; the structural proof now verifies/removes only that exact
port/assignment before retaining its original entire-body comparison. No frozen
golden, live checker term, reason, or numerical tolerance was altered.

## Single diagnostic synthesis and route

Vivado2022.2,xc7z010clg400-1, general.maxThreads2. Synthesis uses the passing
actual-core snapshot, original generated FFT configuration/OOC clock, and the
same100/175MHz resource constraints. The route script checks the source checkpoint
hash and both inherited clocks; the resulting XDC differs from the baseline
only in its generated comment naming the output path. No new timing exception,
multicycle, false path or clock relaxation was added.

| Isolated complete three-bank slice | Baseline169f9fb route | Completed-input synthesis | Completed-input route |
| --- | ---: | ---: | ---: |
| LUTs |1878|1832|1842|
| Registers |4425|4375|4375|
| Slices |1087|not placed|1046|
| DSP48E1 |21|21|21|
| BRAM tiles |7.5|7.5|7.5|
| Unique control sets |55|not measured|56|
|175MHz setup/hold slack,ns |−2.557 / +0.070|not routed|−3.855 / +0.074|
|100MHz setup/hold slack,ns |+2.347 / +0.100|not routed|+1.975 / +0.100|

The candidate's worst175MHz setup endpoint is
`next_inverse_reg/C` → `joiner/kernel_rom/block_start_index_reg[12]/CE`:
9.280ns data,2.938ns logic/6.342ns route,17levels including6CARRY4. The baseline
was `product_bank/metadata_out_hold_reg[3]/C` → kernel ROM ENARDEN,
7.744ns data,2.444ns logic/5.300ns route,13levels. Thus a smaller isolated resource
count is not a timing improvement or an exact whole-receiver saving.

The candidate's worst175MHz hold path is inside the unchanged FFT:
`...input_muxes[0].write_data_im_mux/use_lut6_2.latency1.Q_reg[6]/C` →
`...memories[0].blkmem_gen.use_bram_only.dpms/depths_3to9.ram_loop[0].use_RAMB18.SDP_RAMB18E1_36x512/DIBDI[6]`;
0.251ns data,0.141ns logic/0.110ns route,slack+0.074ns. The complete unabridged
endpoints are in `route/receipt.txt` and `route/island_175_min.rpt`.

100MHz setup is `fast_reset_slow_reg[1]/C` →
`source_bank/metadata_in_hold_reg[56]/CE`,7.736ns data
(1.218logic/6.518route),slack+1.975ns. Its minimum path is
`output_bank/request_sync_reg[0]/C` → `output_bank/request_sync_reg[1]/D`,
0.197ns data(0.141logic/0.056route),slack+0.100ns.

All6359routable nets routed with0routing errors and0unconstrained internal
endpoints. Nevertheless114input ports and124output ports lack external delay
constraints; CDC reports139clock-enable-controlled warnings and6synchronizers.
The OOC clock-source/partial-port limitations remain. These are unchanged
diagnostic resource constraints, not qualified CDC/I/O/receiver constraints.
The already-negative internal setup slack independently fails the experiment.

## Remaining dependency and root's next option — not implemented

The candidate still routes the full input metadata check through
`forward_handoff_ack` → `result_destination_ready` → `slot_error` → join enable.
The direct return-fault edge was factored, but the full fault tree re-enters through
the ACK/readiness mux. The measured17level path exposes that missed dependency;
there is no claim that the comparator was physically removed from the join cone.

Root's next proposed separation is sound subject to a new equivalence test:
in `forward_committed`, let the guard's raw readiness be `product_bank_valid`,
while keeping the full `handoff_fault_now` in `external_fault_now`/`idle_fault_now`
and explicitly requiring `forward_handoff_ack` in forward `ACK_DRAIN`.
Do not change actual mailbox512th-read ACKs, product commit authorization,
descriptor validation, the inverse readiness branch, or sticky quarantine.

Reason: forward_committed implies !active/!return_valid, so this mux branch has
no valid return to consume and no active slot-error contribution. In that phase
a malformed identity/position/TLAST raises the unchanged handoff external fault;
an orphan raw/status/frame/input event raises the unchanged idle fault. Both
directly prevent the result guard's `awaiting_ack` clear even when raw ownership
is high. Correct ownership with no current/sticky fault makes raw-ready and
certified-ready equivalent for ACK acceptance. Explicit controller handoff-ACK
qualification also protects the later drain edge if a fault arrives after the
guard's ACK-clear edge. Admission/reservations and the inverse branch stay as-is.

Required negative cases for that next change: malformed descriptor or first
position/TLAST coincident with ownership, all orphan events coincident with
ownership and with ACK-clear/drain, late fault after a healthy ACK-clear but
before phase switch, source-prefetch overlap, held final bank-not-ready, and
one-sided reset in the handoff interval. Compare exact fault reasons, actual
ACK-clear edges, forward/inverse admission and external results against the
existing full-ready implementation; internal raw-ready alone is not an ACK.
This option was assessed only. No implementation or additional route was run.

Full bank-owned score integration, exact normalization, both detector stages,
2.5MS/s independent pilot export, source timestamps/rate conditioning and live
RF/GLRT/scanner qualification remain outside this slice. This study does not
alter the prior direct66-tap numerical failures or make that alternative eligible.
