# Clocked completion and private ROM loads: tests pass, timing remains open

Implemented clocked producer-completion facts, retaining the bank/phase while
validating the close. Added ten actual cancellation cases for both transform
phases, corrupted forward metadata/position and resets. The final revision also
extends the existing private-payload mode into the kernel ROM: data may load on
available capacity, while public-valid and protocol checks remain unchanged.
A stalled valid output still freezes. Neither change is deployed to a radio.

## Verified results

- Both actual generated-FFT runs pass: all **64,512 numerical records** match
  the earlier pinned actual reference. The complete V1/V2 numerical CSV and
  all parsed service/reset/fault/admission/completion results are identical.
- Six numerical/backpressure contexts, two stopped-reader resets, seven prior
  fault cases, six admission-cancellation cases and ten new completion cases
  pass. At completion capture, the bench checks the facts against the original
  full close predicate. No post-cancellation reuse/publication/release is allowed.
- Normal service is **3659 fast clocks**, two more than the admission baseline;
  the qualifying stalled case remains 4927, below the unchanged 5215 cap.
  The deliberately 9000-clock-stalled reader has no real-time capacity claim.
- **346 regression tests pass in 46.17 seconds.** Separate ROM comparison covers
  4096 healthy lookups, changing invalid-input data, stalls, malformed beats and
  flush/recovery, comparing the original ROM with both candidate modes. Three
  unsafe ROM mutants are rejected. Certificate tests cover both 22/28-bit widths.
- Source-matched synthesis and routing complete with the same device, diagnostic
  100/175 MHz clocks, FFT configuration and route recipe. No timing waiver.

## Physical result: still not deployable

| Candidate | Worst slack | Total negative slack | Failing setup endpoints |
|---|---:|---:|---:|
| Admission baseline | -3.080 ns | -1541.860 ns | 1511 |
| Clocked completion V1 | -3.637 ns | -1943.578 ns | 1368 |
| Private ROM loads V2 | **-3.134 ns** | **-1304.699 ns** | **1398** |

The final result is mixed versus the starting baseline: worst slack is slightly
worse, while TNS and endpoint count improve. All candidates fail timing. V2
hold +0.070 ns and pulse +1.830 ns pass; all 8376 nets route with zero errors.
Resources are 2773 LUT / 5594 FF / 21 DSP / 15 RAMB18. V2 actual/synthesis/route
finish in 86.64/97.08/71.59 seconds. Failed physical V1 is retained, not promoted.

V1's worst path fed the kernel ROM enable through fault/return qualification.
V2's worst path is now engine metadata → preflight/current fault logic →
publication-controller phase: 10 logic levels, 8.793 ns data delay, including
7.097 ns routing. Five critical CDC findings, 208 warnings and 114/124
unconstrained I/O ports remain. This is an isolated diagnostic route, not board
or full-receiver timing signoff.

## Next bounded step and full release path

Inspect the publication controller's private replay handshake. Any separation
from actual authorization must prove that a fault-edge private advance is
cancelled before publication notification or RELEASE. Keep the current-fault
bank authorization fence, require the actual bank request transition for
publication, and retain the real final-reader ACK for release. Add boundary
tests, run actual FFT verification and route again before adding features.

Native **60 MS/s fine search** and independent **2.5 MS/s CI16 IIO inspection**
remain required. Full receiver timing/CDC/reset/board constraints, sustained
capture and actual RX calibration precede `.18` reversible canary, then `.17`
PPU Ethernet deployment with a pinned rollback package. Finish the 300-second
scan with 120 ms valid dwells and blind host GLRT comparison. No radio, PPU,
main branch or primary production HDL gitlink is changed by this experiment.

## Evidence and remote preservation

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Final folders: `staged-completion-prepared-v2`, `staged-completion-actual-v2`,
`staged-completion-synth-v2`, `staged-completion-route-v2`. All vendor handles are
terminal. Independent audit checks sources/checkpoints, every clock pair,
timing summary, utilization and complete routing.

Final inventory: `9ef0ccb07b0739a61a0bc5b6559594198c78047b93ade9215f29fff5ac2c31f8`.
V1/V2 CSV: `d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
Final synthesis DCP: `85006af21c7e0815ea12714710b40be582757b199a615eb16b8e9c50735926b2`.
Final routed DCP: `298832d0be4428422a6eca70ae6ed36a93fb70aac0efee68a1045b57563f5cc5`.

[Verified source/results archive](20260911-staged-completion-evidence.tgz):
25,993,896 bytes, 10,322 regular members, all read-back checked by SHA256 and
size. SHA256: `ee2c323ad31d731b8fe851e6863ee3c6117f25e4d1e48f3943a55207f544fa40`.
Both frozen candidates, actual logs/CSV, synthesis and routed attempts, and
test/audit evidence are included.

Implementation commits: FW `cdf68656c3c60166a40d6110d563db98bd37cd40`,
HDL `b4d092fa7785221cd47ea1d7ec67c984318e1680`, on remote
`codex/starlink-rx-only-do-not-merge-rom-prefetch`. No merge into main.
