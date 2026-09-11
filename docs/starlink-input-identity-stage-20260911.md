# Registered input identity stage — DO NOT MERGE experiment

Parent: preflight/publication proof, FW `a2ca89ae7`, HDL `ba8bfdf21`.
Branch: `codex/starlink-rx-only-do-not-merge-input-validation-stage`.
This is a new, tested component boundary, **not yet an integrated FFT candidate**.
The current top and all 17 integrated runtime modules remain unchanged. No
radio, PPU, main or primary production HDL changes. No timing improvement claim.

## Why this boundary

The publication-scope route still fails through phase-selected input identity,
input fault aggregation and output publication (11 levels, -1.888 ns). Adding a
register only to the common publication veto would delay fault cancellation
and could publish a bad result. Instead test registering each beat together
with its identity-check result *before* delivery to the FFT input checker.
This places the wide comparison before a register without discarding it or
delaying the check until after FFT delivery. Integration and routing must show
whether it actually helps the full control path; other fault paths remain.

## Implemented component contract

`starlink_pss_input_identity_stage.v` is a one-slot private elastic register:
36 data bits, nine position bits, LAST and a known-good identity bit, plus
occupancy/quarantine. It checks all 70 identity bits against the admitted job
descriptor on input acceptance. X/Z identity, including matching unknowns,
does not certify. Both payload and evidence remain held under backpressure.
An occupied slot may retire and refill on the same edge; an empty slot does not
combinationally bypass. Abort and unknown control signals veto handshakes and
quarantine until reset. This changes where upstream acceptance occurs, so it is
not a cycle-for-cycle replacement for the old unbuffered transport.

`starlink_pss_realtime_input_guard_staged_identity.v` is the actual input-checker
logic with only its identity comparison replaced by the accompanying registered
known-good bit. A pinned complete-source inverse checks this limited change.
Position, LAST, first admission, duplicate start, realtime missing-input demand,
certification, completion and sticky reasons remain literal. The old metadata
and balanced-comparator interface fields are retained for this source-inverse
experiment; they do not perform identity checking in the new checker. Callers
must use the new stage and checker together and keep identity checking enabled.

`output_valid` from the private stage is not authorization to the FFT: the
downstream checker must still qualify identity, position, LAST and delivery.
The stage cannot conceal arbitrary upstream gaps once realtime demand starts.
The admitted descriptor must be stable and correct at capture, not sampled
from the next job. No new CDC is introduced by these same-clock components.

## Measured component tests

The first standalone run passes eight tests. The extended stage/checker run
passes ten tests in 0.32 seconds, before adding an explicit parent-checker SHA
pin. Follow-up verification passes **16 tests in 0.40 seconds**, including that
pin, the unchanged integrated runtime/preflight ordering checks and existing
integrated-top lint. This is a focused suite, not the entire project regression.

- 512 continuous input words, 511 simultaneous retire/refill edges, then hold
  the complete final word for 200 cycles while upstream buses/descriptor change.
- All 70 metadata bits, five bad/unknown variants each: 350 rejected identities.
- 4096 deterministic randomized offer/readiness cycles with a one-slot scoreboard.
  Total stage test: 5171 cycles, 2280 accepted, 2272 retired, eight discarded by
  reset/abort, 1539 hold observations, 1572 simultaneous retire/refills.
- Seven current abort/unknown-control cases; quarantine, purge and fresh recovery.
- Six mutants rejected: lost simultaneous refill, corrupt payload, skipped
  identity, unknown-equals-unknown certification, lost reset and lost abort.
- Stage plus actual checker logic: three healthy 512-word jobs, including core
  waitstates and fresh recovery after resetting a held final word. Eight malformed
  jobs (identity, unknown identity, ordinal and LAST at positions 7/511) stop
  certification at exactly the valid prefix. A deliberate three-word gap faults
  as a realtime delivery error. This does not instantiate the vendor FFT.

## Integration gate — still required

1. Replace the input path in an isolated integrated top. Upstream bank READY
   must mean capture into the stage, while guard counters and completion must
   use actual checked FFT consumption. Change offered-beat summaries to the
   stage output too; do not count prefetch as certified delivery.
2. Bind identity capture to the already admitted descriptor and phase. Freeze
   the accepted word/evidence even if the upstream final read releases its bank.
   Keep `engine_input_reserved` through certified final consumption, including
   the buffered final word. Check all scheduler/cutover ownership assumptions.
3. Share the existing per-core reset with both components; account for stage
   occupancy at cutover and for stage control faults in existing quarantine.
   Preserve current publication/reset vetoes. No source-bank ACK is evidence
   of FFT input completion or output publication.
4. Add actual FFT monitors for accepted-versus-consumed beats, first-word
   priming, final-word stalls, all-word identity corruption, gaps, duplicate start
   and resets with a full stage. A one-slot buffer is not a throughput proof:
   verify no bubbles after realtime delivery begins and no old word survives reuse.
5. Re-run the seven-stream numerical comparison and all boundary tests. Measure
   the added service cost (one cycle per uninterrupted input phase is an estimate,
   not a full-island guarantee). Keep the 5215-clock gate and simulation deadline.
6. Only after source-bound actual FFT success: synthesize and route the entire
   subsystem under the original constraints. Inspect changed worst paths and
   resource cost. Neither component-level success nor an isolated stage route
   establishes full-island timing closure.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
required and unchanged. Following subsystem timing/CDC, qualify the full receiver
and actual 60 MS/s calibration/Ethernet stream; reversible `.18` canary precedes
`.17` PPU Ethernet-only deployment and rollback verification. Final release
still requires 300-second scanning with 120 ms valid dwells and blind host GLRT.
