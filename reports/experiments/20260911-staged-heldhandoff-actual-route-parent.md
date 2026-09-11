# Whole held bank handoff: tested ownership simplification, timing still fails

FW `563614b87` / HDL `576eb8897` are preserved on
`codex/starlink-rx-only-do-not-merge-held-bank-handoff`, based on metadata-only
(`e25e9c5bf` / `b41d5115b`). No radio, PPU/main or primary production HDL change.
Production gitlink remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

## Implemented and verified

Registered scheduling uses retired inverse guard data, position, last and
metadata through replay; the mutually exclusive private-valid and replay-valid
offers are ORed. Nonregistered callers retain original muxes. Current fault,
commit, descriptor validation and real reader-ACK predicates stay unchanged.
Complete source inverse, 23,552 four-state wiring cases and five rejected
mutations verify the limited delta/fallback. **496 tests pass in 71.28 seconds.**

The second real bank now observes ALL original selected inputs. Candidate and
reference writer state/faults/ownership and valid reader output match. Rising-edge
checks compare exact validity, disjoint ownership and accepted payload for
441,088 cycles, including 100 replay offers (some private rewrites while paused,
not 100 publications). Six additional cases cover late raw output after
retirement and at replay, late status at replay, a 16-clock replay pause/resume
and each outer reset during that pause. All recover with 512 correct reads and
one real release. Fault cases retain immediate veto and unchanged retired data;
cancelled cases reject stale output/reuse for 100 clocks. Prior campaigns pass.

All **64,512 actual generated-FFT records** match with byte-identical CSV;
service remains 3659/3659/4927/11727/3659/3659 clocks. The 11727-clock context
includes a deliberate 9000-clock reader pause, excluded from the 5215-clock
diagnostic service bound. This is not continuous receiver throughput evidence.

## Physical comparison

| Candidate | WNS | TNS | Failing setup endpoints |
|---|---:|---:|---:|
| Private certification | -1.452 ns | -451.168 ns | 704 |
| Expanded guard facts | -1.340 ns | -463.636 ns | 821 |
| Metadata-only parent | -2.203 ns | -672.268 ns | 796 |
| Whole held handoff | -1.868 ns | -565.807 ns | 720 |

Improves all three metrics over metadata-only, but remains worse than private
certification. **Not promoted as timing reference or deployment firmware.**
720/13756 endpoints fail. Resources: 2699 LUT / 5650 FF / 21 DSP / 15 RAMB18,
zero RAMB36. Hold +0.058 ns, pulse +1.830 ns; 8272 nets fully routed, zero errors.
Unchanged 100/175 MHz diagnostic clocks and no new waivers. Five critical CDC
findings, 208 warnings and 114/124 unconstrained board I/O remain.

Worst path: scheduler held phase -> input identity/checker -> inverse guard
awaiting-ACK D. Nine levels, 7.575 ns data delay, 6.003 ns routing. Next (-1.832 ns)
reaches output-descriptor pending from inverse sticky fault through completion.
The prior publication payload mux is no longer the worst reported path; other
publication paths are not thereby proven closed.

## Next gate and deployment path

Inspect the exact inverse ACK/reuse contract: why does current input-identity
checking reach its occupancy update after inverse input retirement? Preserve
orphan detection, diagnostics, current public vetoes and real reader release.
Compare any composition with the retained private-certification reference and
this candidate using actual FFT and unchanged routing constraints.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 inspection remain
required. Subsystem timing/CDC, full receiver route/reset/board constraints,
sustained capture, actual 60 MS/s calibration and Ethernet/IIO qualification
precede `.18` reversible canary, then `.17` PPU Ethernet-only deployment with
pinned rollback. Final gate: 300-second scan, 120 ms valid dwells and blind
host GLRT comparison. No deployment date is established by this result.

## Evidence

[Read-back verified archive](20260911-staged-heldhandoff-evidence.tgz),
[receipt](20260911-staged-heldhandoff-evidence.json): 15,754,417 bytes,
7,492 members; SHA256
`13b664e10ed05372b7fbc5bf792de7b058db29732514973d560397751461b8c3`.
Actual / synthesis / route: 176.38 / 97.45 / 51.06 seconds, first-attempt
successes. Source/checkpoint/report audit passes; timing gate fails.

Worktree: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/held-bank-handoff-worktree-v1`.
Sibling artifacts: `staged-heldhandoff-{prepared,actual,synth,route}-v1`.
Inventory `d84b6a46c5b376a17523e7cc8287aa075af71ac17fc0630205a77d65eb088e78`;
synthesis DCP `90b55ce275f6811ad6d39adf02758b5eaec26bd823ecd26ed436d6c828cd3ae6`;
routed DCP `de1227a92ad555224164cda294cd111a8138ca57603a6449520acc976de76c76`.
