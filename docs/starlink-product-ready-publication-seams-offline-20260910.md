# Sampled READY and publication-only current faults: pre-evaluation contract

Bounded additive primitive experiment only. Canonical d9c bank, reviewed
1444-test interface and P1 top remain byte-identical. No vendor/physical run.

## Advertised capacity versus sampled READY

Let C be the issuer's existing product_ready output, V the ungated raw product
VALID, and A a new separately supplied sampled_product_ready input. In the new
opt-in mode, A must be the exact arithmetic output READY signal, including the
old P1 !fast_fault gate and the actual force-visible test net. Default mode
selects A=C and must restore the entire old issuer source/behavior.

The bank receives input_valid=V unchanged. Its input_offer_new becomes
producer_reference && !final_taken && A && C (the disabled branch retains the
literal original marker). Hence private_take requires V===1, A===1, C===1
and owned bank capacity. A=0,C=1 must hold arithmetic payload and prevent
private take without hiding raw offers. A=X/Z with V nonzero is a current
interface fault. A=1,C!=1 with V nonzero is an invalid caller handshake: it must
be diagnosed, not falsely counted as matching bank acceptance. This case is
impossible for correctly connected A=C&&!fast_fault, but tests must execute it.
Existing current issuer reason7 records the interface-control failure. All
closed/unowned/raw-X producer checks remain independent of sampled take.
The invalid A=1/C=0 witness includes issuer-only reason Q with producer ownership
still held and inner bank capacity1; checking only a full bank is insufficient.

## Publication-only fault routing

New additive bank parameter PUBLICATION_ONLY_FAULTS defaults0. A new input
publication_faults[7:0] uses the same eight logical caller-cause categories as
live_faults[7:0], but a different current timing route. This does NOT provide
seventeen independently distinguishable causes in the original16-bit ledger.
If separate route provenance is required, extra reason state would be needed.

For each bit i, P[i] = option && armed && (publication_faults[i] !== 1'b0).
Only these equations change in enabled mode:

    checked_seal = original_checked_seal && !(|P)
    publish      = original_publish      && !(|P)
    reasons_next = reasons | original_errors_now | {P,8'b0}

Canonical errors_now, local_current_clean, raw input observation, certificate
acceptance, lease release, output_valid and all other original state/enables
remain literal. Default option0 ignores hostile/X/Z publication inputs and
whole-body inverse/equivalence must restore canonical d9c.
Like the original live causes, P is armed-gated: a pulse present only on the
pre-armed rearm edge is not captured. This is a publication observation window,
not an all-epoch raw-event recorder. Source integration must independently retain
global faults or prove that such pulses cannot be relevant before ownership.

In particular P must NOT be ORed into live_faults or errors_now. Those current
predicates affect bank read VALID and release, and can return through reader
validity and real input certification to the publication-only source. P's only
direct control sinks are seal/publication; reason Q closes the epoch after the
edge. Legitimate bank read transport may still occur on that edge. Downstream
actual ACK/result-publication fault checks remain separately protected by the
caller; this seam is not permission to publish poisoned downstream evidence.

The expected state change is zero bits: the existing per-cause reason bits are
reused. No pipeline cycle, RAM or DSP is added. This is a logical expectation,
not a mapped resource or timing result.

## Required predeclared tests

- Whole-source inverses and disabled equivalence against d9c and the reviewed
  interface, including all original bank causes and hostile new inputs.
- Current1/X/Z publication faults at seal and publication with reason Q still0;
  exact sticky category capture, reset recovery, and no current read-valid or
  certificate/release dependence. Exercise legitimate ready-high bank reading
  on the fault edge, followed by next-edge quarantine.
- Actual sampled READY0 while capacity1, finite interior/final stalls, X/Z and
  impossible READY1/capacity0. Raw VALID/closed offers remain visible throughout.
- Real input-guard closed-input/certification controls, not only forced abstract
  fault bits; distinguish natural closed-phase invariants from deliberate
  standalone diagnostic coupling. No real-top reachability claim.
- Complete LS-aware graph from an acyclic base; restoring publication faults
  to bank live/current-all-fault paths must be rejected, as must lost direct
  seal/publication veto, reason loss and sampled-READY/raw-observer omissions.
- Immutable legacy1444 replay plus additive bank/interface regressions. Preserve
  every failed attempt and report any unavoidable timing/diagnostic difference.

The contract above was written before evaluation. Results below do not revise it.

## Frozen result

Owner original65756 exited0: **2752 PASS in78.64s**, comprising1308 new checks
and the immutable1444 suite. FW source eba403dc38b7a0d5a5634a4f76cb0bf78a3d7ae9;
HDL source1703e90347b607219d9c714c2cce698deea6ab9d. Parent independently replayed
2752 PASS in78.61s (original97763), with154 source pins unchanged.

New modules are starlink_pss_epoch_sealed_publication_bank.v (76d6985a...) and
starlink_pss_product_sealed_publication_interface.v (03c37b96...). Exact fixed
inverse patches restore the whole canonical d9c and reviewed5e060a23 bodies;
unreviewed additions are rejected. New test source db0d31b2... contains the
explicit compile recipe and strict original-fixture inverse. Both new knobs
reject-1/2/X/Z. No canonical/P1 RTL or frozen1444 test changed.

New-seam option0 means an **active sealed bank/adapter with the new seams off**,
not every public diagnostic port inert. Paired bank outputs and original state
are compared including invalid payload. The default adapter executes all508
old composed cases and eight healthy leases while hostile new unused inputs
are ignored; independent old predicates plus whole-source inverse establish
the narrow default delta. The untouched legacy-bank branch is restored by the
same literal inverse, not falsely presented as a new active-legacy test suite.

Current1/X/Z category tests cover seal, publish, certificate, ready-high read,
release and the pre-armed window. Current read/certificate/release still occurs
where originally eligible; next reason Q quarantines. Both reset sides recover
only after explicit rearm. Same-edge caller ACK veto is tested separately with
the real result guard. Real checked-input certification is also coupled to the
publication-only port (two actual accepted consumer beats before quarantine),
without putting that cause into the bank's shared current-fault route.

Actual READY tests include four held edges at interior37 and final511, raw
closed/X/Z offers at A0, unknown A, and naturally reached issuer-reason-Q01 /
bank-Q0 / inner-capacity1 / C0 with forged A1. The latter is an invalid caller,
not a top-reachability claim: private_take remains0 and reason7 records it.
Interior source backpressure still causes the original non-backpressureable
actor's quarantine; final hold completes. Missing A/C/raw observation, current
veto, reason capture, internal state gates and caller ACK fence mutants fail.

The complete coupled VVP has3488 combinational nodes,38 LS nodes, no cycle.
Source selection resolves publication_faults to its **immediate driver**, not
named aliases or all upstream state. That driver reaches checked_seal/publish,
but not bank_live/read-VALID/certificate ready-or-take/release ready-or-take/
product capacity. Three independently restored backedges are cyclic. Separate
read-only final-netlist inspection also finds sampled_ready_error absent from
advertised capacity and actual READY, but present at bank_live/current ACK
health. This is structural Icarus evidence, not mapped timing or reachability.

No registers/RAM/DSP were added: exact register declarations remain unchanged,
760 logical register bits plus one512x36 bank for the reviewed adapter+reader+
bank. The eight healthy leases in both modes have identical measured traces:
final product→seal2, publication3, forward completion→publication6,
publication→handoff10, handoff→first accepted core beat2, final core→release1;
512 beats span511 with zero holes, admission→release1555 cycles. These actor
measurements are not an actual-controller/FFT service budget or physical claim.

## Retained failures and replay

All attempts are archived, not overwritten. Initial96988:128PASS/25FAIL from a
new fixture observing output_accept in the same delta as driving READY; adding
the declared1ps settle fixed it. Initial95481:670PASS/78FAIL:77 concurrent new
finish/old healthy-handoff-fatal terminations, one incorrect persistent-C1
expectation after intentional raw-source stall. New negative epochs now exit
through an additive main wait hook; all original assertions remain literal.
50547:88 focusedPASS;60822:1286PASS;91017:2730PASS before strict receipts.
14624:2749PASS/1FAIL exposed named-alias source selection in the new positive
graph witness. Its earlier alias-ID negative exclusions were insufficient and
are superseded, not retained as proof. The complete parser never changed.
Connected/disconnected controls now share upstream state while distinguishing
the exact bus route. Final2752 also rejects missing/wrong/duplicate/bare/late
error/zero-count receipts; reads/reasons remain bench-asserted fields, additionally
audited across96 rows by the parent, not claimed newly value-validated by the
small receipt parser.

Persistent owner output:
/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-publication-seams-final-v3.iNkUV3PJ.
Portable artifacts reside under HDL library/starlink_pss_acquisition/evidence/
product-publication-seams-offline-v1, with a complete SHA256SUMS and exact source
pins in final-receipt.json. Each compressed attempt retains source/commands/
exit/log/XML/netlists; immutable snapshots are preserved independently.

Replay from the pinned FW tree with a fresh non-/tmp basename:

```sh
env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH PYTHONDONTWRITEBYTECODE=1 \
 /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B -m pytest -q -p no:cacheprovider \
 tests/starlink_oracle/test_product_publication_seams.py \
 tests/starlink_oracle/test_product_sealed_interface.py \
 tests/starlink_oracle/test_product_sealed_adapter.py \
 tests/starlink_oracle/test_checked_product_read.py \
 --basetemp=/ABSENT/UNIQUE/pytest --junitxml=/ABSENT/UNIQUE/results.xml
```

Ruff passes the new test file. No vendor/top integration is qualified by this
study. Independent origin/head identity at actual ACK and inverse start,
persistent receipt consumption, disabled diagnostic isolation and paused-slow
common-epoch purge remain the next separately tested integration obligations.
