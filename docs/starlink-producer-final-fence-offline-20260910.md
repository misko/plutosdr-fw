# Producer-local product final fence: offline conditional proof

This is an additive, default-off alternative, not a receiver change or a timing
closure result. No vendor simulation, synthesis, route, radio, or inverse-adapter
composition was performed for this experiment. The preceding immutable K1/M1
route still fails setup at −1.360 ns. Its report and source are unchanged.

## Frozen source and result

- Tested FW: `61d5ff33c5faff20c4a05540e8efdb08f03c7709`.
- Tested HDL: `a226dd615db76830928c83253d204deccdff41e8`.
- Literal inverse baseline: HDL `efc97d8ac92578e1e37eb0bb28c64780b86cf76a`.
- New top SHA256: `8923b42b3574fc1418eee99c5f5819f173c73fbf7b8bb65726a7ab3a5d8a6f7c`.
- New mailbox SHA256: `e4f4c56ddab8f05d0f9b9da9a75f975e11cb8ad441581c904bfb094f3013982f`.

Original process 98534 exited 0: **26 PASS in 24.56 s**. Root independently
repeated the identical five-file source: process 20741 exited 0, 26 PASS in
24.70 s. The earlier unchanged ROM regression plus then-current local tests was
85 PASS in 41.13 s (35969). Ruff passes. No numerical FFT execution is claimed
by these fast tests.

## Exact change and scope

`starlink_pss_fft_bank_owned_product_fence.v` copies the measured additive ROM
top. `starlink_pss_product_fence_mailbox.v` copies the canonical mailbox. Both
have explicit fail-closed 0/1 parameters; defaults preserve the original branch.
Whole-file inverse tests restore the frozen original bytes, not merely selected
expressions. All seven prior runtime source files remain unchanged.

Only the mailbox's final-write authorization selects the new producer-local
predicate. It retains forward completion plus all ten local current/sticky
causes: duplicate start, sticky input guard fault, synchronized source fault,
vendor fault, fast epoch fault, kernel fault, product overflow, sticky product
bank fault, current product framing fault, and result fault. Original
`product_commit_authorized`, `external_fault_now`, completion, handoff ACK,
publication fences, reasons, resets, ownership, payload, and all other mailbox
state updates remain literal.

The excluded raw active-input framing/delivery and handoff identity cones remain
fully checked globally. They are excluded only from the sampled producer-final
seal. A qualified forward return has already completed input; inverse consumption
and handoff require product-bank consumer ownership, which excludes producer
readiness. This is a **conditional ownership/phase proof**, not full controller
reachability proof. The bench drives `forward_committed` at a declared boundary
after a real guard accepts 512 inputs; it does not execute the vendor FFT or the
real controller's completion transition.

Naively delaying every raw fault would be unsafe: a duplicate start coincident
with an otherwise valid final product write must prevent that edge's request
toggle, before sticky quarantine catches up. Both the current duplicate veto and
the retained input-fault veto are tested independently here. The latter isolates
the guard term after the pulse has deasserted; it does **not** claim the full
wrapper's fast epoch fault would remain clear following that duplicate.

No banks, registers, cycles, or mathematical changes are added. The source-level
cone cut is not a measured post-synthesis path-removal claim.

## Executed observations

For each enabled setting at full depth 512: 89,228 edge checks, 15 actually sampled
final authorizations, 3 nonsampled private authorization differences, 70 active
input identity bit corruptions, 71 malformed product-final rows, 7 current-fault
rows, one completed inverse epoch, 515 stall checks, two common epoch resets,
512 read words, four X/Z final rows, and one sticky-input-only row.

All old mailbox public outputs, internal state, and every payload-memory cell are
compared unconditionally every checked edge. The three private differences occur
only with consumer ownership while deliberately corrupting handoff identity;
producer publication cannot be sampled. X/Z framing follows the exact procedural
`if (!framing) ... else` semantics, including the else branch for unknown framing.
No invalid payload/state mask is used.

The depth-four geometry intentionally exposes malformed early TLAST to the fixed
512-input guard: three words are read and the terminal word/ownership is retained,
not ACKed. Quiescent full-top shadows use a parked FFT stub and exercise both raw
reset inputs with both clocks running. They are not active FFT or paused-clock
reset qualification; the separately found paused-slow reset issue is not fixed
or qualified here.

All seven missing-veto mutants reject at the exact sampled-authorization
assertion. Raw-private authorization substitution rejects at public state
comparison. A deliberately inconsistent active-input caller rejects the caller
invariant rather than being admitted as equivalent. Parameter omission/readback,
invalid −1/2/X/Z settings, literal inverses, and top binding are checked.

## Retained attempts and portable evidence

The archive is
`hdl/library/starlink_pss_acquisition/evidence/producer-final-fence-offline-v1/`.
Its outer manifest covers the compressed complete attempt inventory, packaging
receipt, and README. `inventory.json` gives every tar member's byte length,
SHA256, and original path; `attempts.tgz` contains the same receipt and source
closure. Symlink identities are recorded separately; their original local
targets remain untouched. The earlier pre-sticky portable package remains at
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-fence-package-v1.ULIgAGbf/archive/attempts.tgz`
with SHA256 `1e4e61d64a89fbf63c5e85980cba88b4bccdb5e8833a7f464b81863587395df6`.

Failures are preserved, not relabeled: initial 83891 (5 PASS / 17 FAIL), a bad
TMPDIR compile attempt (2/1), and a short-geometry incorrect ACK expectation
(2/1). Corrections were fixture scheduling/geometry, literal parameter-instance
overrides (Icarus command-line X/Z overrides were ignored), and source-token
matching. Mutants failing before their intended witness were not counted as
passing rejection evidence. Later 22-, 25-, 85-, and final 26-test runs and all
old bench/test snapshots are retained.

## Next independently gated work

Attach an additive sampled-final observer to the accepted K1/M1 actual harness,
using the real controller's `forward_committed`, bank ownership, and guard phase.
Keep every old vector, fatal, observer, qualified-status rule, and historical CSV
gate literal; compare all old public bank state plus sampled authorization.
This preparation is separately authorized offline only. Actual vendor execution
and physical measurement still require source-specific review and approval.
