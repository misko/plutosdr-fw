# Clocked inverse-final validation passes tests but regresses routing

Implemented default-off staged inverse-final validation in the result guard,
enabled only in the experimental FFT/buffer integration. It captures seven
independent veto facts after a held final word has all structural qualifications.
The guard and descriptor controller consume the same private certificate.
Current-fault bank authorization, actual publication request observation and
final-reader ACK remain independent requirements. No radio deployment occurred.

This explicitly changes experimental `output_complete_accept` to private close:
a new fault at consumption may advance close/lock/pending, but cannot publish,
notify release or reuse the epoch. Default guard callers and legacy public-valid
predicates retain their prior behavior. Forward final consumption is unchanged.

## Verified results

- V3 actual generated-FFT verification passes in **128.73 seconds**. All
  **64,512 numerical records** independently match the pinned reference. Sorted
  CSVs match the private-capture baseline exactly; raw bytes differ because
  stream interleaving changes with the added cycle.
- All prior healthy/reset/fault/admission/completion/replay/writer/capture cases
  pass. Eight new cases cover faults before capture and at consumption, both
  resets, extra raw output, duplicate status, late first legal status, and
  16 clocks of completion backpressure. The two healthy cases each return 512
  correct reads/one real release. Six cancellation cases allow no publication,
  reuse, reads or release. Per-edge checks compare offered facts with the legacy
  final predicate and require captured permission for every private close.
- Normal service increases from **3659 to 3660 fast clocks**; the qualifying
  stalled context increases from 4927 to 4929. Both remain below the unchanged
  5215 limit. The deliberately 9000-clock-stalled reader has no service claim.
  Each healthy inverse block has one exact final-word private rewrite while
  completion is staged: 18 total, not extra numerical samples.
- **397 regression tests pass in 51.78 seconds.** Certificate tests include all
  individual zero/X/Z checks, held evidence, no refresh or duplicate consume,
  quarantine/reset and fresh epoch recovery at widths 7/22/28. Four unsafe
  certificate mutations fail at each width. Ten new evidence-parser controls
  reject incomplete or weakened final validation evidence.
- Source-matched synthesis and route finish in **99.11 / 51.67 seconds**.
  Source/checkpoint checks pass. The independent route audit confirms the
  measured result below; it does not turn failing timing into a pass.

## Physical result: not promoted

| Candidate | Worst slack | Total negative slack | Failing setup endpoints |
|---|---:|---:|---:|
| Private-capture reference | **-1.969 ns** | **-813.676 ns** | **914** |
| Clocked inverse-final validation | -2.379 ns | -941.022 ns | 1038 |

The candidate regresses all three setup metrics and remains an experiment.
1038 / 13803 endpoints fail. Hold +0.064 ns and pulse +1.830 ns pass; 8335 nets
route with zero errors. Resources: 2738 LUT / 5669 FF / 21 DSP / 15 RAMB18.
Device, generated FFT, diagnostic 100/175 MHz clocks and route recipe are unchanged.
Five critical CDC findings, 208 warnings and 114/124 unconstrained I/O remain.
No timing waiver or full receiver/board signoff is claimed.

The worst path now runs from product-bank held metadata through comparison and
shared fault checks into forward acceptance and the kernel ROM's
`expected_bin_index_reg[5]/CE`: 11 levels, 7.804 ns data delay including 5.922 ns
routing. Completion-pending is no longer the worst endpoint, but no claim is
made that every completion/ACK path is timing-clean.

## Next step and full release path

Inspect forward/kernel ordinal control. Private payload loads already avoid
global acceptance gating; expected-index state still uses it. A private advance
must preserve public per-bin identity checks, real-backpressure freeze and block
boundaries, with fault/reset quarantine before publication. Compare against the
better private-capture reference as well as this staged-final variant; do not
assume combining changes improves timing. Retest actual FFT/cancellation and
route before full receiver integration or additional features.

Native **60 MS/s fine search** and independent **2.5 MS/s CI16 IIO inspection**
remain required. Full receiver route/CDC/reset/board constraints, sustained
capture and actual 60 MS/s RX calibration precede `.18` reversible canary, then
`.17` via PPU Ethernet with pinned rollback. Final verification remains the
300-second scan, 120 ms valid dwells and blind host GLRT comparison. No radio,
PPU, main branch or primary production HDL gitlink changed in this increment.

## Retained failures and source provenance

V1's scoreboard counted an identical held-final private rewrite as a new sample.
V2 verifies/counts those rewrites separately, without weakening numerical checks.
V2 then timed out because its stalled-READY test could miss the consumed
one-cycle handshake while polling falling edges. V3 observes the rising-edge
handshake with a 32-clock resume bound. The 3 ms absolute deadline is unchanged.
Runtime RTL is identical across all three attempts; only test/evidence handling
changed. Both failed outcomes are retained and neither was routed.

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Final folders: `staged-final-prepared-v3`, `staged-final-actual-v3`,
`staged-final-synth-v3`, `staged-final-route-v3`. All vendor runs are terminal.

Inventory: `8df8afa4b1d98bea85d33432eb8d34750a772e003dd89d619d1286591bbb0a97`.
CSV: `30d99ca45c77ab72bae3a982b4097fded1dd04e8b03995e742c401020c9c9c96`.
Synthesis DCP: `b667cc03ce83f56e67357e3b198a48f949deb5c8357c55d4d5599b472286bf24`.
Routed DCP: `d860b58833cae1af963e04f5183fb98fe102e7d62fcd12cbc31c6bdc3aa0a67d`.

[Verified source/results archive](20260911-staged-final-evidence.tgz):
21,419,381 bytes, 7372 regular members, all read-back checked by SHA256 and size.
SHA256: `99f107747534640f364dc0ca35451231f58419dabd2b7e5e2d91aca4e472707e`.
Includes all three frozen attempts, failed/passing simulation evidence, synthesis,
V3 route reports/checkpoints, tests and pinned references.

Implementation pushed to remote `codex/starlink-rx-only-do-not-merge-rom-prefetch`:
FW `04b00108a2dc35b5b59aa1f9beb8ffbc5dc7832d`,
HDL `fe024d804c43e437f8ce1881544f28e3d77ab57d`. No merge into main.
