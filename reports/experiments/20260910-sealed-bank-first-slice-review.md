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
