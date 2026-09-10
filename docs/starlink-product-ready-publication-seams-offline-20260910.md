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

Implementation/tests are pending. This document freezes the intended contract
before controlled evaluation; it is not a PASS receipt or top-integration claim.
