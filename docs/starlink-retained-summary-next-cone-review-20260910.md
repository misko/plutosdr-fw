# Offered-summary route: defer write-side work; target epoch/admission and phase selection

Read-only analysis of HDL `b013cb91ffc8038e39726109ebfe5ee5afe032ed` in the high-rate60-paired lane. No RTL, tests, constraints or vendor executions were changed/run. Proposed cuts below are not qualified implementations. This report remains unpushed pending parent review.

## Measured priority

Root's original route `26806` completed at `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-summary-route-parent.qxOkezJN`. Timing still fails: WNS -2.504 ns, TNS -829.822 ns, 679 setup endpoints, hold +0.049 ns with zero hold failures. There are 7253 routed nets, zero routing errors, 2344 LUT, 4766 FF, 21 DSP, 15 RAMB18. CDC remains unqualified (5 critical / 139 warning / 3 info), as do 114 input and 124 output budgets. Source100/island175 constraints remain 10.000/5.714 ns.

The [same-domain top twenty](/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-summary-route-parent.qxOkezJN/route/island_175_island_175_max.rpt:14) divides exactly:

| Launch group | Paths | Destinations represented |
| --- | ---: | --- |
| epoch_barrier.fast_release | 10 | cutover owner_inverse (including replica); retained fault/reserved/busy/lease; admission receipt; forward guard active |
| held_phase | 10 | cutover frame/full/configured/owner; completion receipt; retained transfer/request/lease; inverse guard state/reason |
| Product write/read metadata, forward_committed or ROM CE | 0 | None in this top twenty |

Therefore defer the delayed-commit/ACK-phase proposal. Its old -2.594 ns write-metadata path is no longer among these twenty; this is not proof that it disappeared from the full design. Do not add an ownership-risky change solely because it targeted the previous route. Pulse-only remains rejected by the preserved cycle2736 early-ACK counterexample.

The new worst path is fast_release→cutover.owner_inverse D, 8.163 ns (1.758 logic + 6.405 routing), ten LUT levels. It traverses a reset-qualified net of fanout1226, output-bank readiness, retained reservation, preflight/current-fault aggregation and job admission. It is a synchronous D path—not permission to false-path reset assertion or deassertion.

## Source-bound causes

- [Barrier lines 11–36](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output/starlink_pss_retained_epoch_barrier.v:11): fast_release is set only after outer_fast_running and both actual mailbox purge receipts; it remains set until raw common reset. fast_running includes raw_epoch_ok, outer_fast_running and fast_release.
- [Mailbox readiness line 131](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output/starlink_pss_mailbox_owner_view.v:131): in_running && !input_fault && request_toggle==acknowledge_sync[1].
- [Retained owner lines 28–40](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output/starlink_pss_retained_output_owner.v:28): reusable and reservation requalify reset, fault, current request/lease health and bank readiness. Actual release additionally requires the real read ACK, guard ACK and current common health.
- [Top lines 178–193 and 270–290](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output_summary_candidate/starlink_pss_fft_retained_output_impl.v:178): inverse destination_reserved=output_bank_ready&&(retained_reserved||retained_reusable); its negation enters preflight bit4. preparation_fault_now feeds common_current_fault; job_ready again requires cutover admission, reusable capacity and !common_current_fault.
- [Cutover lines 76–102](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output_summary_candidate/starlink_pss_core_job_cutover.v:76): admission requires actual reset-flush/owner/health conditions and then captures owner_inverse on the real job_accept.

The held-phase half is **not only preflight**. [Top lines 141–146](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output_summary_candidate/starlink_pss_fft_retained_output_impl.v:141) mux the live input guard's full metadata by held_phase. [Input guard lines 63–100](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output/baseline/starlink_pss_realtime_input_guard_local_admission.v:63) compares all70 bits to its own immutable admitted descriptor, and retains malformed-presented checking while stalled. Path4 (report line211) follows this actual guard equality/fault cone through completion_accept to cutover fresh_frame. Preflight-only factoring cannot claim to remove it.

## First bounded combinational opportunity: context-preserving preparation summary

Keep original preflight_events_now and every exact detailed reason capture literal. Consider a parallel, source-specific preparation predicate only for the common-fault aggregate.

Under fast_running===1 and both retained_fault_now and retained_reasons known clean (already independent terms in that aggregate), output_bank_ready===1 implies a healthy mailbox with request==ACK. Whether the retained owner's private reserved bit is zero or one, retained_reserved||retained_reusable is then true. With output_bank_ready===0 both original and raw-ready destination tests reject. Thus, **inside this clean aggregate context**, inverse destination failure reduces to !output_bank_ready. It does not justify deleting retained reservation globally, changing release, or changing original preflight bit4.

A candidate common summary can use the raw phase-selected destination readiness and preserve all five other preflight reasons, while the original detailed preflight vector still records faults. Prove equality of the full old/new common aggregate, including the independently ORed current/sticky retained faults; do not compare only the replacement bit or assume legal requests. Retain the original expression outside a proven context if needed. Expected state/latency cost is zero; logic reduction is plausible, not measured. This directly addresses the reset→ready→reservation→preflight reconvergence. It cannot remove direct reset/current-fault paths or the live input guard.

Bank-local comparisons before a scalar phase selection are another combinational option, separately for preflight and—if justified—the live guard. Preflight must use engine_metadata; live guard must use its own descriptor, not an assumed alias. Two independent70-bit equality trees replace one mux-before-equality tree (roughly one extra24-leaf/four-group equality tree, offset by removed payload mux logic; no mapped LUT estimate). All metadata bits/ordinal/TLAST and held/invalid offer checks stay present. Do not silently disable CHECK_INPUT_BLOCK_IDENTITY.

Four-state caveat is concrete: with unknown select, A=01, B=10 and E=00, (select?A:B)==E evaluates X, while select?(A==E):(B==E) evaluates0. Two-state algebra alone cannot authorize this transformation. Require exhaustive/symbolic four-state equivalence of the accepted fault scope, or an explicitly reviewed unknown-phase handling seam retaining old behavior. This is not a reason to mask phase-X tests.

## Concrete state-reuse alternative: delay private cleanup, never effective closure

A bounded candidate for several held-phase endpoints uses the **existing completion_receipt**, not a new delayed ACK:

- [Top lines 448–451](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output_summary_candidate/starlink_pss_fft_retained_output_impl.v:448) compute the current-safe completion_accept from real ownership/ACK and all current vetoes. Line523 registers it into completion_receipt.
- [Cutover lines 111–114](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/hdl/library/starlink_pss_acquisition/retained_output_summary_candidate/starlink_pss_core_job_cutover.v:111) currently fan completion_accept into clearing six bits: owner_open, configured, reset_flushed, quiet_released, fresh_frame and fresh_full.

Proposal only: retain those six bits as hidden storage and clear them privately on the following receipt edge. Expose their original effective values through a known-one receipt mask: effective_bit=private_bit && !(completion_receipt===1'b1). Every checker, public output, observation and state-dependent classification uses the effective view. Preserve original raw producer_closed/unknown-control reason capture at its old edge. No new FF is expected; six existing bits are renamed, with small scalar-mask logic. The physical dependency stops at the existing receipt Q instead of propagating to six more D pins.

At completion edge n the receipt becomes1 and masks all six effective values to0, matching the old closure. At n+1 hidden storage clears before the receipt can drop, so the view stays0. This needs a source-specific proof that no next admission/configuration/reset-flush update legitimately overlaps cleanup. Existing controller consumes completion_receipt before core release/next phase (lines554–556); core reset and cutover low_count priorities must be checked, not assumed. Preserve exact reset assertion, private-core reset observations and all original reason bits. Unknown receipt must not be treated as a true procedural close.

Naively delaying producer_closed alone is unsafe: during the extra edge configured_owner could remain live and classify a late raw frame/output/status differently, potentially missing an orphan. Likewise, delaying admission wholesale would open the core/start path before cutover/retained ownership if not comprehensively fenced. owner_inverse is externally used for raw-event routing even while idle, so it is not an arbitrary speculative scratch bit.

This cleanup candidate does not shorten completion_receipt D itself (-2.166 ns here), the worst admission path, retained-owner actual reader_release, or all input-guard identity paths. It adds no healthy public cycle only if the effective-state equivalence and ordering proof succeeds. Do not delay actual ACK, release, bank reuse, configuration/start qualification, or raw event veto to make the graph pass.

## Reset-specific constraints and next qualification gate

The barrier must still observe actual slow purge and all fast mailbox idle receipts, including a paused peer; no local transform reset may reopen the common epoch. Removing raw_epoch_ok gating, replacing actual purge with nominal delay, or adding an unconstrained reset pipeline is not proposed. Monotonic fast_release may make the outer_fast_running factor redundant under a proved top invariant, but raw assertion/unknown reset kill remains independent. Removing that one factor need not solve fanout1226 or the reconvergent logic, and must not be credited as timing closure.

Before any RTL authorization:

1. Preserve default whole-source inverse and independent source/guard/cutover/owner observations. Separate changes; do not union write-token, ROM, checked-bank or scheduler alternatives.
2. Prove every full current aggregate and exact reason vector across all simultaneous causes, malformed/unknown phase and request/ACK/lease controls, reset assertion/release and both paused-clock orders. A known-clean premise must be established by actual independent logic, not the same summary being proved.
3. For cleanup, compare all effective old state each edge, including closure receipt onset/drop, raw events on closure and following edge, core-reset low_count0/1/2, common reset mid-receipt, and earliest legal next admission. Execute missing-mask, early-mask-drop, wrong-owner/pulse, delayed-reason and overlap mutants.
4. Assert no public ACK without the actual bank ownership/read ACK; no invalid emitted start/configuration; no stale input/output/lease before peer purge. Preserve original source backpressure/recovery limits and full numerical/accepted tuples.
5. Use the complete LS-aware graph plus positive backedge controls. Prove intended paths end at state boundaries, while current write framing, overflow, raw vendor/status/input faults and independent head/lease checks still reach their required public fences. No reset false-path exemption.
6. Only a separately authorized actual/physical measurement can establish service/timing effects. Preserve the [retained summary campaign's frozen seven contexts and full original result gate](/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/docs/starlink-retained-summary-actual-result-20260910.md:35): H0/H1/H2/H4/H5/R1/R2, 40 admissions, 38 complete jobs, two aborted prefixes, all77,953 numerical rows, causal frame/reset/configuration joins and unchanged service/stall limits. Its accepted nominal recurrence is3,645 clocks and parked-reader service4,912 at fixed100/175; these are not the checked-product lane's5215 gate. The checked lane's -8.324 ns,26-level origin cascade remains a warning against reconnecting all independent predicates through a new omnibus certificate enable.

## Pins and limitations

The seven relevant live files were byte-compared with the immutable input snapshot at `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-summary-synth-parent.39BysdkS/synthesis/inputs/source_snapshot`.

| Source | SHA-256 |
| --- | --- |
| summary top implementation | 3b98a25b8c5d50a18da1692511ae1647c2969fadf5c55d679278b2d5a7bbf0ff |
| summary result guard | 8b853ee26ab18b4639ab0faf156fd75661f86030773c14f5a9843140c52b5d02 |
| summary cutover | c67b62486356215a12cd8e9c2b220c5a877a661bd1b15a13b25f9904171ba330 |
| epoch barrier | 954cff125145c81081678967f8afeecc6430dac07a4b7aff16c87b6174bf3afd |
| retained owner | b6280f6a894ec120f0e57415d5cc6da7b9e193a65f42b1d7f9789cbdbaa5d648 |
| mailbox owner view | de060a7930be1d65cc91903da447e51ead3efad4ebed4b61e4f257e45d76d2d6 |
| actual input guard | 55438743eede0d346cec67351e079eb6ae21da437d4088a131a2a258b43ff233 |

Input DCP SHA2348ac8205738a178e11d3f51c8d5b46199ab8548a57573bae0edd785f3f5eb5; routed DCP SHA83d268fff699dae1ca3fca8bd1debddd04562590a284f982e05844bdb1059d38; top20 report SHAa3ed1b2487e86e8e2291a7350e695b8465b171fa2c666b52bbe882988625bd90. No new tests, vendor runs or source changes were performed for this analysis. None of these hypotheses is a physical pass or permission to weaken fault/ownership scope.
