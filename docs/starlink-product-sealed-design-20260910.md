# Next producer/product design: two checked ownership boundaries

Read-only design following the failed P1 route; **no RTL implementation, vendor
execution, or composition with inverse-sealed runtime is included**. Recommended
next cut is a staged product writer AND a checked-token bank reader. Another
final-enable change or write seal alone cannot remove the dominant read cone.

Source bindings: P1 top8923b42b…/input guardeb1f968a… in this tree; complete pins
and failed artifacts are in `starlink-producer-final-route-result-20260910.md`.
The separately reviewed fast-only bank is SHA
`d9c2382f9087ccd2088fa5a5d3fed5c6fe885359d6d4c367ed2ea81ce099d9f6`
at `/tmp/starlink-coarse-alternatives.Y3JzOI/bank-arithmetic/hdl/library/starlink_pss_acquisition/starlink_pss_epoch_sealed_bank.v`.
Its526 standalone tests are existing evidence, not new integrated proof.
Inverse issuer8ad9c2e7…/CDC bankea27c4e2…/top2f988a16… were consulted read-only.
The inverse owner confirmed the reference naming but warned that its live final
certificate rule is phase-specific; no source from that worktree is changed.

## What is live, and what must move together

P1 top lines344–356 instantiate the product bank; lines248–250 combine its
current framing error into `external_fault_now`; lines268–294 propagate it
through result validity/final completion. The new worst7.154ns path begins in
the producer's stored metadata and ends at result guard active state. Separately,
top lines145–150/209–221 feed raw product-read metadata to the input guard;
guard lines59–97 compare it, qualify core input, and emit current errors. Sixteen
of the top20 paths traverse that second family. These are legitimate current
dependencies under the OLD unchecked mailbox interfaces, not false paths.

The three conceptual events must stay distinct:

| Boundary | Private work | Evidence authorizing progress |
| --- | --- | --- |
| Producer | One product RAM write per real taken product token | All512 token checks drained plus independent forward completion certificate |
| Handoff | Immutable bank and prefetched inverse head | Matching lease/descriptor, validated head, consumer reservation, no current/sticky veto |
| Inverse input | Raw read snapshot and check pipeline | Same-token GOOD register before actual core handshake; last core acceptance plus all references drained before release |

The current product descriptor is **70**, not75 bits: top351 packs
`{1'b1, product_start[63:0], product_exponent[4:0]}`. Proposed explicit binding
to unchanged d9c is `{5'b0, product70}` on both data and certificate interfaces;
low70 projects back to the existing inverse descriptor. All75 bits, including
the five declared reserved-zero bits, are checked. This is NOT the inverse
output's direction/start/input-exponent/output-exponent75-bit encoding, and does
not pretend five extra historical product fields existed. Parent acceptance of
this adapter packing is required before implementation.

## A. Producer-owned seal and independent completion reference

New additive issuer reserves the fast bank's lease at actual FORWARD admission,
before any product word. It snapshots expected block identity from the admitted
engine descriptor, not the first arriving product. At actual qualified forward
final retirement (P1 lines480–481), it records the independently validated forward
exponent and completion reference. Thus uniform wrong product metadata can seal
locally but cannot match the independent certificate.

Retain explicit `producer_reference`, `lease_reference`, `final_product_taken`,
`completion_reference`, `certificate_consumed`, `published_reference`, and
`reader_reference`. A token's pending marker survives stalls and is consumed only
by actual private take; it is not VALID-edge detection. Product overflow must be
the held output-stage flag (product lines148–160), not only `overflow_pulse`.
New raw core output remains an orphan independently of bank READY. An extra
product after its consumed final is a new reference fault, not hidden by the
final-taken flag. Prove this against the real product's refill/hold semantics.

Use d9c unchanged:25 equality leaves→five registered groups; ordinal/TLAST/lease
are tagged with the offered token. Final take at n permits checked seal at n+2
and publication no earlier than n+3 (d9c128–200/244–271). Its sticky local causes
are delayed by two edges. Do not retain the old full product comparator as a
parallel raw global publication input; that would recreate the measured cone.
Instead map staged token causes into common-epoch detailed reasons and retain
their original offered lease/index and all simultaneous raw causes.

Unlike inverse output, forward `return_commit_valid` legitimately drops before
the arithmetic pipeline's final product emerges. Therefore inverse issuer44–60's
`certificate_lost` expression is NOT reusable. The held descriptor-bound forward
completion reference stays valid until certified handoff. Raw vendor/status/
orphan/reset/current duplicate, source-fault, kernel, held overflow and relevant
ownership faults remain direct vetoes throughout actual publication/handoff;
common sticky reasons remain active. No global one-cycle fault delay is proposed.

Forward guard final retirement may precede a delayed PRIVATE product error. That
retirement may create a private completion reference, never a bank publication.
The seal/drain requirement defeats publication before the late cause can arrive.
The existing guard can remain unchanged except the explicit adapter's new bank
cause timing; all its genuinely raw current-event/publication checks remain.

## B. Checked read tokens, not an unverified canonical descriptor

A writer seal alone does not establish equality of each subsequently offered
read tuple. Add a three-slot private payload/token queue and a two-stage checker
against the independently held lease/descriptor. At each raw offered edge,
compare all75 bits, position, TLAST and lease; capture the actual data on a take.
The checker runs even when payload capacity is full, so malformed presented/
held words are not silently dropped (the old guard79–86 checks them when stalled).

Each check carries offered lease/index, TAKE, and queue-slot tag. Only a matching
TAKE verdict may mark that slot GOOD; non-taken observations can still fault.
Queue payload/position/TLAST remain immutable until actual core acceptance.
Issue cursor advances on raw private pop; independent delivered cursor advances
only on GOOD-head core handshakes. No stale verdict may mark a reused slot.

Proposed explicit opt-in checked-token guard seam: identity is supplied by the
registered GOOD receipt for that exact held token, not recomputed from raw bank
metadata on its consumption edge. The old full-identity path remains default and
remains used for the forward source. Position/TLAST, current duplicate start,
actual core-demand delivery and reset checks remain immediate. Simply passing a
certificate wire into the old70-bit comparator is not a physical cut; silently
substituting expected metadata for unchecked raw words is unacceptable.

Healthy validated metadata can be projected from the held certificate only
AFTER the raw token was fully checked. Direct corruption of post-check internal
certificate/payload registers is a different fault-injection boundary; do not
claim seal checks detect arbitrary memory/FF bit flips or add nonexistent ECC.
All existing raw bank-output metadata/position/TLAST corruption intents must
target the actual raw adapter input, including stalled offers.

Read prefetch can start privately during forward ACK wait. Handoff ACK requires
a matching descriptor/lease and validated position0/nonlast head plus the actual
inverse-consumer reservation; a toggle or certificate receipt alone is not that
ACK. Start the core only after the queue has the declared prefilling credits.
With three queue slots, two-edge check evidence and registered GOOD, earliest
core take is n+3 after raw take n. Three staged slots plus the bank's existing
registered output are the complete outstanding payload-credit budget. Exact
steady one-word/edge, simultaneous dequeue/refill, arbitrary core stalls, and
final-tail continuity must be proved before accepting the three-slot depth.

Final RAM pop may ACK the bank's internal reader before the final queued token
reaches the core. The issuer MUST retain its reader/lease reference until actual
certified final core acceptance, all observed checks drained, all queue tokens
retired, and the tagged release opportunity is current-fault clean. Neither RAM
prefetch completion nor VALID briefly becoming0 authorizes bank overwrite.

## Safety counterexamples and contract boundary

1. Registering old product framing fault alone: corrupt final at n toggles
ownership while `fault_q` is still0; n+1 quarantine is too late.
2. Passing raw read position37 with last0 while the expected position is36 and
READY1: using the prior cycle's good/fault register delivers and certifies the
bad current word. GOOD must be attached to the captured same-token payload.
3. Preflight-only metadata equality misses a one-word interior or stalled
metadata mutation. Every raw offered token needs the full check boundary.
4. Releasing on final prefetch leaves unchecked/stalled old tokens queued while
the next lease overwrites their bank or retags their verdicts.

Delayed LOCAL check reasons and private read/ACK timing are explicitly different
from the old raw-cycle observer ABI. Integration needs a new strict-derived
accepted-event observer: exact numerical values, full metadata/ordinal/epoch,
all reasons/first offending tags, no unauthorized publication or lease reuse,
and absolute deadlines. Keep the original raw tests/logs unchanged as historical
evidence; do not mask fields or call a changed-latency trace byte-identical.
Other source/vendor/status/orphan current faults must not be globally delayed.

Common-epoch reset owns bank/issuer/check queues; per-transform core reset must
not erase poison/references. Reuse the inverse owner's independent remote purge
and source-reader/source-fault barrier contract before rearm, including paused
slow clocks. The fast-only bank by itself does not repair that old reset gap.
Two-bit lease safety remains conditional on finite drained references before
wrap/reset, not a hash or unconditional ABA guarantee.

## Budget and next proof gate

Arithmetic unchanged: no new FFT/DSP, rounding, payload RAM or mathematical
latency. One512×36 product RAM remains. d9c declares317 total logical bank bits
(not mapped FF); its documented+86 is versus a75-bit old mailbox, not the70-bit
P1 bank. A draft three-slot queue needs about150 payload/tag/state bits; staged
offer checks about62; descriptor/lease binding about78; cursors/reason/first-tag
and control about44: roughly334 reader bits BEFORE implementation accounting.
Producer-held certificate/references add roughly90 unless existing held state
can be proven reusable. This could cost hundreds of FF, not a free enable tweak;
full synthesized delta, LUT mux/credit costs and any duplicated certificates are
unknown. Do not claim an exact area total from these planning counts.

For service, allocate a provisional+12 fast clocks for product sealing,
read qualification/handoff and release; this is a target, not a demonstrated
bound. At175MHz it is68.57ns. The exact passed P1 log shows profile0 inter-forward
admission4547–4548 clocks and profile1 bounded-stall4821/4825/4828, duplicated by
the independent two benches. Nominal29.8us budget is5215 clocks. This leaves
planning room but proves neither sustained production source60 operation nor
new queue liveness. Measure first/last/take/seal/certificate/publication/core
acceptance/ACK/release and total pair service with the real core before physical
work. Inverse-output staged overhead is separate; no automatic +12 composition.

First offline gates: full default inverses; all75 bits first/interior/final and
uniform/certificate corruptions; malformed stalled offers; pending check at
seal/publication/handoff/core-final/release; duplicate/raw orphan/status/watchdog/
held overflow on each boundary; queue credit/refill/underflow; wrong/missing/stale
verdict tags; both-phase/lease-wrap/one-sided paused-reset purge; missing-stage,
veto/cause, early GOOD/ACK/release and lost-stall-evidence mutants. Include real
guard/product sources and acyclic elaborated graph evidence. Do not launch a
vendor or physical trial until that new source-specific contract is reviewed.

The two M1 ROM metadata-selector→index-enable paths remain independent; this
proposal does not fix them or all remaining source/input/current-fault cones.
