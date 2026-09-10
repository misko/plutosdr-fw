# Offered-input fault-summary candidate: frozen pre-evaluation contract

This is an additive, default-off offline candidate on the retained lane. It
replaces none of the input guard, FFT, arithmetic, counters, certified-input
connections, owner recurrence predicates, ACK predicates or public-return
predicates. No vendor execution or clock/constraint change is authorized.

The new top option is `INPUT_OFFER_FAULT_SUMMARY=0`. Its enabled common-current
summary consumes metadata-independent `guard_valid && transport_ready` and
that offered beat AND `guard_last`. Both owner summaries use the existing
`routed_inverse == OWNER` mask. The old full cutover and owner-current
diagnostics remain literal. Parallel cutover expressions substitute only the
two input strobes; parallel guard expressions additionally tie inherited
external fault to zero, avoiding its repeated propagation. The top OR retains
every original independent input/sticky/raw/source/bank/retained/preflight/
result root exactly once. Indirect admission/state effects through common
current fault are intentional; no guard recurrence is directly substituted.

Acceptance is frozen before testing:

- Strict 21-anchor whole-source inverse of all four additive files restores
  the preceding closed/private candidate bytes. Default-disabled full old
  shadows and all declared state remain unchanged.
- With real `input_fault_now === 0`, offered beat/end must case-equal both
  original certificates, including X/Z enable, valid, READY, identity, ordinal,
  LAST, owner route and masked closed-slot conditions. Real input state is
  clocked through all 512 accepted words; abstract/forced-state probes are
  separately classified, never represented as reachable traffic.
- For known input fault 0/1 the offered and original common summaries must
  be case-equal. Unknown input fault deliberately produces known-one common
  fault in the enabled mode. This is explicit fail-closed tightening, not
  four-state equivalence: `I || (!I && L)` is X for I=X/L=1, while `I || L`
  is 1. No original diagnostic predicate is rewritten by that absorption.
- Old full state/output shadows, real input certificates, ordinal/TLAST,
  arithmetic, final retirement, real ACK/release, reset and existing bounded
  service/stall geometry must pass. Fault plus ACK/publication, malformed
  ordinal/LAST, delivery gaps, duplicate starts and unknown controls must
  preserve immediate quarantine; direct input fault may never be masked by
  offered beat or owner routing.
- Negative controls must reject missing READY, wrong LAST, wrong owner,
  omitted direct fault, omitted independent root, and substitution of offers
  into real certification/state. Source mutations must fail the inverse.

The candidate adds combinational wires only; actual declared-register count
must be checked (no mapped-resource claim). The intended cut removes serial
identity-to-certificate-to-reconstructed-fault propagation, not all identity
ancestry. Direct input identity fault, handoff/preflight, original ACK/return,
and product-write framing/ROM cones remain. No timing closure, lower clock,
continuous-source capacity, causal acquisition, radio or production claim.
