# Sealed-bank pipeline: first implementation scope

The L1 diagnostic route failed setup (-1.549 ns). Its two worst reported paths
cross module boundaries: input metadata/current faults into result-fault state,
and output-bank metadata/current faults into admission. Moving one descriptor
enable did not establish timing improvement. The next experiment therefore
changes the private transfer protocol, rather than just rewriting the same
combinational checks.

This is an implementation decision, **not** a functional or physical pass.
The independently running C1/K1/M1 ROM experiment remains separate; no flags
are silently combined and no current receiver module is promoted.

## Approved first slice

An additive, fast-clock-only RTL controller will reuse a 512 x 36-bit payload
bank and its full 75-bit descriptor. It separates:

1. Private acceptance into exclusively reserved storage.
2. Completion of the local two-stage metadata/ordinal/final-word checks,
   followed by sealing immutable storage.
3. Publication after both the matching transform/status certificate and the
   drained local checks, with a direct veto for remaining live faults.

The proposed earliest publication is three edges after the final private take.
This is a contract to test, not an observed implementation result. Writes while
sealing/sealed must never overwrite the completed block or race publication.
The final token must not be repeatedly accepted while held upstream.

The reference source is the explicitly tested R1/B1/O1/L1 runtime cohort
`62da6a39edb8e40e08d41cbb13ba04af7584842d` in the arithmetic worktree. Existing
modules, old numerical tests and the old 155-bit observer remain unchanged.
The new private pipeline is checked with independent transaction-level output
and safety expectations; its internal registers need not match the old pipeline
cycle for cycle. Added latency must be explicit and included in later complete
island service measurements.

## Parent review findings to resolve

- A two-bit lease alone cannot distinguish a stale certificate after wrap.
  Reuse requires proof that no token, certificate, read or ACK remains in
  flight, plus an explicit certificate handshake/drain contract. Resetting a
  lease to zero is not proof that an old zero-tag certificate is gone.
- One-sided reset must invalidate outstanding ownership and require explicit
  epoch rearming. The first fast-clock slice cannot claim cross-clock reset
  safety merely from single-clock tests; the subsequent CDC integration needs
  its own protocol evidence.
- The proposed equality tree initially budgeted four second-level flags.
  **75 bits require 25 three-bit leaves and five six-input groups.** The final
  leaf covers bits 72–74 and must be exercised independently.
- Registering the old global fault OR is insufficient. A fresh fault on the
  publication edge must still veto publication. Wide metadata cones can be
  removed from that edge only after immutable sealed ownership and complete
  validation are established. Live vendor/orphan/reset/ownership events remain
  checked, and simultaneous fault causes remain sticky.
- A privately stored word is not a public result. Previously accepted
  slow-domain prefixes cannot be retroactively revoked instantaneously; later
  integration must preserve provisional-data and sticky-CDC-fault semantics.

## Tests and resource gate

Use actual RTL RAM reads and an independently generated ordered-token model.
Check all 512 data words and all 75 metadata bits, including first/interior/final
corruption, missing/duplicate final words, delayed/wrong/absent certificates,
lease wrap and reset races, extra tokens during both drain cycles and on the
publication edge, consumer stalls, current faults during ACK, and simultaneous
causes. Mutations must expose early sealing, shortened drain, removed current
veto, duplicate acceptance, stale lease reuse and lost sticky faults.

The first-slice target is no additional full payload bank or DSP and roughly
80 additional logical state bits, to be counted against the actual baseline.
If correct reset/lease/certificate handling requires more, report the additional
state rather than dropping checks. This is not a mapped-resource estimate.
The suggested full-island allocation of at most 24 added fast-clock cycles per
pair likewise remains an unproven planning budget, not a throughput result.

Only standalone RTL/model tests are authorized at this step. No new vendor run,
synthesis/route, full-island integration, firmware flash or radio access follows
until the implemented contract and evidence are reviewed. An independent agent
is reviewing the same proposal for safety and throughput counterexamples in
parallel with implementation.

The complete goal remains source 15/30/60 MS/s with native fine search,
independent 2.5 MS/s host evidence, causal scheduling, the 120 ms/300 s scanner,
full receiver physical/calibration qualification, and staged hardware deployment.

## Draft RTL review findings (before qualification)

Parent and independent review of the first 250-line draft found issues to fix
before any passing claim:

- Closed-current-lease offers were ignored when READY was low, allowing
  publication despite an extra token; an already-seen certificate had the
  analogous duplicate-offer ambiguity. The new interface must distinguish
  the legacy held final from a genuinely new offer, with executable issuer
  behavior and a direct current-event veto.
- Releasing N required `input_valid==0`, while N+1 could legally hold VALID
  waiting for READY. READY stayed low until release, creating deadlock. Only
  qualified future-lease offers may be tolerated during old-lease release;
  old-reference drainage must still be established.
- A parallel full-width metadata comparison still fed immediate reasons and
  publication control, despite the added pipelined equality tree. The revised
  design must actually break the wide path. Bounded delayed observation of a
  private metadata fault is acceptable only with the original token identity
  preserved and no seal/publication/reuse before all checks drain. Legacy
  externally visible reason/counter timing needs a later explicit adapter,
  not an automatic compatibility claim.
- A missing certificate needs a modeled bounded timeout issuer. A bench-wide
  watchdog does not establish the controller's rejection behavior. Normal
  two-stage drain and final-read/ACK turnaround did not reveal another
  two-state counterexample in the independent read-only review.

The draft is not an integrated receiver change. Its original source/compile
failure is to be retained separately from the corrected standalone tests.
The additional issuer/reset bookkeeping must enter the eventual full resource
and latency budget; the controller's conditional interface alone is not an
end-to-end lease freshness or CDC proof.

## Revised standalone review (13:39 UTC)

The independent read-only reviewer found no additional RTL safety counterexample
under the explicitly conditional issuer contracts in RTL
`d9c2382f9087ccd2088fa5a5d3fed5c6fe885359d6d4c367ed2ea81ce099d9f6`.
Exact-next payload and certificate offers can now survive old release; early
certificates are pinned to immutable first-word metadata. Unknown offer controls
veto publication, and missing-status testing uses an external 8,192-cycle issuer.
The wide payload checks now actually pass through leaf/group registers; this is
a source-level timing cut, not a physical pass.

Two test-strength gaps were identified before independent qualification:

- The receipt model accepted a terminal-only negative case with no stimulus or
  rejection evidence. Parent reproduced this with case 7 and model
  `3fe32d1e59c25f3c496b0f19413b2809e3e07826cc25bc251c33d4512bbd1545`.
  Case-specific event inventories and removed-event mutations are required.
- The stalled-output check only tested an unchanged tuple when current VALID
  remained high. It must also reject a healthy one-cycle VALID withdrawal while
  stalled, except for a genuine reset or current/sticky quarantine event.

These are verifier/bench gaps, not observed failures of the current RTL.
The implementation agent's 476-test pass remains standalone evidence pending
these corrections, source freeze, and parent repeat. Earlier failed test attempts
remain retained rather than replaced by the later count.

Parent independently counted 317 declared logical register bits: 222 reused
payload/reader metadata/cursor bits and 95 control/check bits, plus the same
18,432-bit payload RAM. The 95-bit control subtotal is not a mapped resource
measurement or a net FF increase versus all old mailbox controls. External
issuer and eventual cross-clock adapter state is not included.

## Frozen standalone result and next composition

Final standalone source FW `f8754e23afc136870d1dd68228bdecb197a6e6c7` / HDL
`2c2460ad55981ed0833eeadfef60463f1d1bca10` resolves the two reviewer-requested
test gaps. Parent read the complete revised contract, model/profile inventories,
bench checks and executed mutation selectors. Independent original **96302
exited 0: 526 tests passed in 8.17 seconds**, including all 15 RTL mutants.
The five RTL/bench/model/test source hashes were unchanged across the repeat.
Artifacts are in recovery-parent `epoch-sealed-parent.vWc0Zi`:
log `a77309363a1749efc21534846807c81417134272b251a93302d6451092e4669e`,
XML `3a85a2c72a860ce706fd77b675baaf7e99aea02deefda9e2ceefdcd176fcefef`.
The startup-X exception is confined to the documented pre-first-reset receipt;
unknown owned-epoch faults are rejected. Failed intermediate parser/mutation
selection attempts remain preserved, not relabelled as RTL failures or passes.

The next authorized implementation is additive and inverse-output-only: a true
175/100 dual-clock bank plus concrete issuer adapter, leaving the fast-only
prototype, original result guard, arithmetic, forward/product/source banks and
FFT unchanged. Source review identified four separate lifecycle receipts:

1. Idle/nonfinal transport capacity.
2. Held-final retirement on actual sealed publication.
3. Guard ACK retirement on synchronized actual final read.
4. Scheduler completion only after explicit release makes the bank reusable.

Using private readiness as final retirement deadlocks after the final take;
using reuse as guard ACK creates another release/reference-drain cycle. The
certificate source is held `return_commit_valid`, not the later commit pulse.
Its loss before publication (including watchdog expiry) remains a same-edge
veto; the normal post-publication drop must not create a false fault.

The slow reader must retain proper request/ACK CDC, immutable metadata through
release, and existing slow sticky-fault visibility. It must not gate slow VALID
from raw fast-domain publication/fault/armed signals. Implement real producer,
certificate and reader reference ownership and common-reset rearm; ordinary
per-transform reset cannot clear common quarantine.

Offline composition tests must exercise exact 512-word data/metadata, delayed
status and once-only final take, publication-edge deadline, final-read/ACK/release
faults, real 175/100 clocks and reset skew, and N+1 source movement. Initial
adapter allocation is at most 24 extra state bits and eight added fast clocks
per inverse lifecycle within the earlier 24-clock pair allocation. These are
planning budgets; report any safety-required overshoot, not omitted checks.
No vendor, synthesis, route or receiver deployment is authorized for this next
composition until its actual source and offline evidence are reviewed.

Standalone portable evidence is now committed and pushed at FW
`b2dfc0d6546810a4ffbc1b331c371c2af0939fc6` (unchanged source f8754e23a / HDL
2c2460ad). Parent independently verified all 5,705 safe unique archive members
directly from Git: 9,372,940 compressed bytes, SHA-256
`a0742fb322eb2382088b49aa273f5e9068679f30cb944ebbbb9a3d6fafd55fef`.
All 15 mutant receipts retain their actual rejection layer: the RAM corruption
case reaches simulator exit 0 and is rejected by the independent numerical
oracle; the other cases terminate with their retained simulator fatal evidence.
The initial archive classifier incorrectly required every mutant to abort the
simulator; that packaging attempt is preserved separately. No RTL or test result
was changed to repair that classification.
