# Monotonic reset-release experiment — DO NOT MERGE

This is an isolated actual-FFT/buffer timing experiment, not receiver firmware
qualification or permission to flash a radio. Native 60 MS/s fine search and the
independent 2.5 MS/s IIO inspection stream remain required deployment features.

## Contract and bounded change

The previous routed same-domain critical path starts at the second fast reset
synchronizer stage and ends at the output mailbox request toggle (−1.037 ns).
The top's four reset synchronizers can only rise within a common known-high raw
reset epoch. The existing fast release receipt already requires both local purge
receipts; the slow release is a two-stage synchronization of that receipt.
Consequently each release implies its corresponding outer reset readiness.

The opt-in `MONOTONIC_OUTER_RESET=1` removes only the redundant outer-readiness
terms from the barrier's two running outputs. Raw reset cancellation, all purge
state, all synchronizers and every release cycle remain unchanged. The top
passes this parameter into the barrier; the actual bench and synthesis profile
enable it together. Defaults remain zero. Unknown/nonboolean modes are rejected.

This is NOT a valid simplification for generic outer readiness signals that can
fall independently of raw reset. Directed tests demonstrate that counterexample
for each domain, and verify that the default generic mode retains its vetoes.

## Evidence required

- Exact inverse source checks: only barrier and top runtime changes; no arithmetic,
  FFT, buffer, publication, reset-state, latency or timing-constraint changes.
- Independent complete parent barrier comparison using the actual top's reset
  synchronizer logic: 25 epochs per campaign, three clock ratios, four phases,
  modes zero/one, X/Z reset and idle levels, either/both clocks stopped, raw reset
  released before restart, and normal mailbox occupancy after startup.
- Negative tests for missing purge/receipt/synchronization and invalid modes.
- Actual payload mailbox reset/recovery tests with the opt-in enabled, including
  unsafe data-path mutants. These are digital tests, not metastability signoff.
- Frozen actual generated-FFT main/auxiliary campaigns, complete numerical CSV
  comparison and matching synthesis profile; no expected numerical/service change.
- Same diagnostic 100/175 MHz routing recipe, routed-checkpoint source pin, old
  path queries, reset synchronizer structure, and explicit CDC findings.

## Promotion remains separate

## Measured result

948 distinct tests pass (921 regression, 16 enabled mailbox tests, 11 new
actual-evidence checks). Both actual-FFT campaigns pass; 64,512 numerical records
and CSV bytes match the parent, with unchanged `3663/3663/4929/11729/3663/3663`
service clocks. The main reset witness covers 503,564 fast, 287,723 slow and 272
reset observations; the auxiliary covers 437,625 / 250,071 / 215 respectively.

Routing completes in 43.05 s without routing errors. Setup still FAILS:
global WNS −1.399 ns, same-fast-domain WNS −1.324 ns, TNS −250.635 ns, 446
failing endpoints. Parent values were −1.373 / −1.037 / −292.853 / 580.
Both targeted reset-stage-1 paths disappear; the earlier metadata-to-fault path
passes at +0.137 ns. This is not an overall timing improvement or signoff:
the new fast-domain worst is `epoch_barrier/fast_release_reg` to `fast_fault_reg`,
ten logic levels, 6.983 ns data delay, 75.7% routing. The release enable drives
a 2156-fanout net in that cone. Global worst is the fast fault's crossing into
the first slow-domain synchronizer stage; CDC qualification remains separate.

Use is 2739 LUT / 5787 FF / 21 DSP / 15 RAMB18; all 8426 nets route, hold
and pulse pass. First-stage-only synchronization and registered purge checks
pass. CDC reports nine CDC-3 items and 208 CDC-15 warnings, not waived. The
114 unconstrained inputs and 124 outputs remain outside OOC qualification.

Do not promote this candidate over its parent based on endpoint count alone.
Next inspect the release-to-product-ready-to-forward-fault control cone. A
candidate change must prove the exact registered fault next-state and public
transfer behavior across every phase/reset, rather than merely relocating the
same high-fanout reset term or delaying a safety veto. Keep held-data CDC and
full receiver qualification as independent gates.

## Deployment restrictions

No timing exception, clock reduction, TX deletion or radio access is authorized
by this experiment. Even an isolated timing pass would still require full RX/IIO
integration, real board clocks and reset/CDC qualification, 60 MS/s calibration,
continuous operation and sustained Ethernet/inspection throughput. Then qualify
the pinned rollback-capable package on `.18`, followed by PPU Ethernet deployment
and real-world verification on `.17`. `.20` and `.21` remain excluded.
