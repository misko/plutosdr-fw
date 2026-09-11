# Private certification: new best measured subsystem reference

FW `eda2c6dce` / HDL `cf4b70230` are preserved on
`codex/starlink-rx-only-do-not-merge-private-certification`, based on the private
sequence candidate (`74c1e2b67` / `f4e14c326`). No radio was flashed; no PPU/main
changes. Primary production HDL remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

## Implemented and verified

In certified-admission mode, the descriptor register captures only preparation
validity. Admission still checks original current rejection facts and consumes
its clocked certificate under epoch quarantine. Non-certified mode retains the
original fault-qualified descriptor expression. No public start/publication,
fault recording, bank ownership or reader-ACK gate changes; no clock is added.

The complete source inverse proves only that expression changed. A four-state
table checks private capture and exact fallback; two unsafe expressions fail.
**449 regression tests pass in 56.53 seconds**. **All 64,512 actual FFT records
match**, with byte-identical CSV and unchanged service intervals.

A 318,097-cycle original-certificate comparison observes exactly two private
differences: vendor faults during forward and inverse preparation. Both are
contained by known asserted quarantine with known-zero public start/config/input.
Six new actual cases also cover both resets, invalid position and X position.
All block stale work for 100 clocks and recover after reset with 512 correct
reads and one real release. The unknown case retains preflight evidence and
known-zero starts; no claim of a known binary fault diagnostic is made for it.
All prior admission-consumption, fault/reset/ownership and sequence cases pass.
Total campaign receipts: 119 admissions / 90 completions, including aborted work.

## Routed comparison

| Candidate | Worst slack | Total negative slack | Failing setup endpoints |
|---|---:|---:|---:|
| Private descriptor capture | -1.969 ns | -813.676 ns | 914 |
| Private sequence parent | -2.047 ns | -550.201 ns | 825 |
| Private certification | **-1.452 ns** | **-451.168 ns** | **704** |

All three metrics improve versus both references. This becomes the best measured
development reference, **not a timing pass or deployment promotion**. 704/13801
setup endpoints still fail. Hold +0.070 ns and pulse +1.830 ns pass; 8350 nets
fully route without errors. Resources: 2744 LUT / 5668 FF / 21 DSP / 15 RAMB18.
Diagnostic clocks remain 100/175 MHz. Five critical CDC findings, 208 warnings
and 114/124 unqualified board I/O remain. No timing waivers were added.

Worst path now ends at completion snapshot bit 9: publication phase -> output-
bank metadata mux/comparison -> inverse guard local fault aggregate -> snapshot.
Eight levels, 7.020 ns data delay, 5.572 ns routing. The next path (-1.437 ns)
ends at inverse guard awaiting-ACK. These are still control-path failures.

## Next gate and deployment path

Continue from this reference. Split compound guard-local completion predicates
into smaller independent registered facts, proving the same aggregate result
and unknown handling. Inspect inverse retirement alongside completion. Preserve
held final data/descriptor, immediate publication vetoes, reset cancellation and
actual reader ACK. Rerun actual FFT/fault/stall/reset proof and source-matched
routing before accepting another candidate; do not relax the diagnostic clocks.

Native 60 MS/s fine search and 2.5 MS/s CI16 inspection remain required.
Subsystem timing/CDC and full receiver route/reset/board constraints, sustained
capture, actual 60 MS/s RX calibration and Ethernet/IIO verification precede
`.18` reversible canary and `.17` PPU Ethernet-only deployment with rollback.
Final verification remains a 300-second scan, 120 ms valid dwells and blind host
GLRT comparison. This result does not establish a deployment date.

## Evidence

[Read-back verified archive](20260911-staged-certification-evidence.tgz),
[receipt](20260911-staged-certification-evidence.json): 15,772,506 bytes,
7,366 regular members. SHA256
`bc708da6c133c9329858c577f309a8693f0667da6b40f676b5c9b86c573e4751`.
Actual / synthesis / route elapsed: 133.25 / 98.88 / 58.71 seconds, first-attempt
successes. Source and checkpoint audits pass; they do not claim physical signoff.

Worktree: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/private-certification-worktree-v1`.
Sibling artifacts: `staged-certification-{prepared,actual,synth,route}-v1`.
Inventory `73770113445a26a7ee7589064071bb28192a76d35688a8737dfc9ac391c677c1`;
synthesis DCP `174267cb6bbb8e7c1becfdc3c2e7c0d30f7d4b53c54c151c034d17bc654a9cc8`;
routed DCP `5e388b0bd65cab4b5f703ecb019c5f53c1959595f22c7613febbe57f46a77ec6`.
