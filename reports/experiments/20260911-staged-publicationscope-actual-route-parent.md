# Publication fault scope: integrated actual FFT and route

The simpler controller is exercised with the actual generated FFT and mailbox
buffers, not an FFT stand-in. This candidate passes functional verification but
**does not close timing and is not promoted or deployed**. It is preserved on
`codex/starlink-rx-only-do-not-merge-publication-fault-scope` in firmware and HDL.
FW commit `f510063c3`; HDL `2d8eeea776fa205ae3b44628f29085583210d8d8`.
Its runtime parent is the guard-fact reference via the preflight/publication
proof branch, not the regressing bank-local-identity candidate.

## Change and verification

Remove only current preflight terms from certified, known-valid output replay
authorization. Existing phase ordering keeps those terms zero during replay.
Retain all other current and sticky faults, original diagnostic accumulation,
unknown/default fallback, reset and actual reader-release ownership. This
reachable-phase simplification is not arbitrary-input algebraic equivalence.
Only the runtime top changes; the other 16 runtime modules remain identical.

- **496 regression tests pass in 93.983 seconds**, no failures/errors/skips.
- 1,900,544 four-state authorization cases; four unsafe mutants rejected.
- Actual FFT: **64,512 records identical** to the retained numerical reference.
- Original authorization matches over 479,822 checked cycles; all 3,133 live
  replay observations retain exact current fault equality.
- Six new retained-fault injections veto publication and recover with 512
  correct reads and one actual reader release. Existing queued-input, paused
  publication, published/unread preflight fault and reset tests remain active.
- Service intervals stay 3659/3659/4927/11727/3659/3659 clocks. The 11727-clock
  context includes a deliberate 9000-clock reader stall; it is not a normal
  throughput result. The unchanged diagnostic service gate is 5215 clocks.

The first testbench revision failed an existing consistency assertion because
its forced reduced fault disagreed with the raw/vector fault views. Preserve
that failed run. V2 changes only the injection/release sites to feed consistent
views; no runtime or assertion change. Actual V2 passes in 191.24 s, synthesis
in 95.98 s and route in 53.54 s. These are subsystem tests, not RF frames or
continuous receiver throughput measurements.

## Physical result

| Same route recipe | Guard facts | Publication scope |
| --- | ---: | ---: |
| WNS (ns) | -1.340 | -1.888 |
| TNS (ns) | -463.636 | -598.888 |
| Failing setup endpoints | 821 | 881 |
| LUTs | 2808 | 2725 |
| Flip-flops | 5691 | 5684 |

New route uses 21 DSPs and 15 RAMB18s, with 8340 fully routed nets and no routing
errors. Hold +0.062 ns and pulse +1.830 ns pass. Source and checkpoint audits
pass. Setup does not. 114 unconstrained inputs and 124 unconstrained outputs
remain in the diagnostic OOC design; no full receiver or board signoff.

Worst path: held phase -> input metadata identity -> input fault events ->
owner fault aggregation -> output-bank request-toggle D. It is 11 logic levels,
7.597 ns data delay, including 5.777 ns routing (76.0%). Excluding preflight from
the replay gate did not remove this remaining combinational path. Smaller logic
utilization alone is not a timing improvement.

## Next gate and preserved deployment requirements

Keep the better guard-fact/private-certification references. Specify a registered
validation-to-publication boundary before the next implementation: private
payload/descriptor retention, validation completion, current-edge vetoes,
pending-work cancellation, actual reader ownership and producer reuse. Simply
delaying the common fault by a clock risks publishing bad data; it is not an
acceptable fix. Account explicitly for added cycles and buffering.

Test faults immediately before/on/after the boundary, unread output, queued
input, reader stalls and resets in both domains. Require actual FFT numerical
agreement and unchanged service constraints, then route the subsystem before
feature expansion. Do not lower clocks or weaken constraints to claim closure.

Native **60 MS/s fine search** and the independent **2.5 MS/s CI16 IIO inspection
stream** remain untouched. No additional TX removal is part of this fix.
After subsystem timing/CDC: full receiver integration and route, reset/board
constraints, sustained capture, real 60 MS/s calibration and Ethernet/IIO tests;
then reversible `.18` canary and `.17` Ethernet-only PPU deployment with pinned
rollback. Final qualification remains 300 seconds, 120 ms valid dwells, eight
high/low targets and blind host GLRT comparison. No deployment ETA follows from
this failing route. No radio, PPU/main or primary production HDL changes.

## Reproducible evidence

[Archive](20260911-staged-publicationscope-evidence.tgz) and
[receipt](20260911-staged-publicationscope-evidence.json): 19,085,408 bytes,
7,569 members, all read-back verified. SHA256:
`934337a610b160349db09a9d76a2f99d6fc4e19e6bb6a1fb9de5be722d9de829`.
Includes V1 failure, V2 success, prepared sources, tests, numerical CSV and
actual synthesis/route reports and checkpoints.

- V2 inventory: `62cd6b63907f29dd5e40a9802cd2ca161b897589f0d9e0775eebb8879c5a30d1`.
- Numerical CSV: `d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
- Synthesis: `316639f158210201515dbb480b99af9d00bca970e831d565db01b8a0c5f5e1e6`.
- Routed DCP: `1df782ea68ba3064e323db04edfa6e1790fe09c6a4995561decf4fe91aa765c0`.

Worktree:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/publication-fault-scope-worktree-v1`.
Artifacts: sibling `staged-publicationscope-*` directories.
Primary production HDL remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.
