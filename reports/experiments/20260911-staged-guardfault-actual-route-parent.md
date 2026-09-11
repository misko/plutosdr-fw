# Exact guard fault summary: actual FFT passes, route regresses

Implemented and tested independently on the better private-capture reference
(FW `fcc3dc202`, HDL `c25126a2e`). No radio was flashed, and the primary
production HDL gitlink remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

FW `b5e15f51b` and HDL `29575e18f` are preserved on the separate branch
`codex/starlink-rx-only-do-not-merge-fault-summary`. Neither main nor PPU changes.
Worktree: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/fault-summary-reference-worktree-v1`.

The guard-facing fault expression now uses an equivalent offered-input summary
for known input-fault values, with the original expression retained for X/Z
and when disabled. No clock latency, public fault veto, buffer ownership or
reader-ACK contract changes. Real input-checker/cutover tests cover 524,288
four-state cases, plus a scalar table and three rejected unsafe aliases.

Actual generated FFT and real buffers pass: **64,512 numerical records match**,
with a byte-identical reference CSV and unchanged healthy service intervals.
Each full fault register matches the original arithmetic for **259,384 cycles**.
Five new actual fault cases and the prior full campaign pass. **397 regression
tests pass in 53.88 seconds**. These are subsystem tests, not continuous RX proof.

| Candidate | Worst slack | Total negative slack | Failing setup endpoints |
|---|---:|---:|---:|
| Private-capture reference | -1.969 ns | -813.676 ns | 914 |
| Guard fault summary | -2.566 ns | -921.237 ns | 958 |

The candidate is **not promoted**. 8350 nets route without errors, but 958/13780
setup endpoints fail; hold +0.058 ns and pulse +1.830 ns pass. Resources:
2744 LUT / 5658 FF / 21 DSP / 15 RAMB18. Five critical CDC findings,
208 warnings and unqualified 114/124 board I/O delays remain.

Worst path: publication phase -> bank metadata selection/comparison -> guard
fault qualification -> completion acceptance -> mailbox `final_data` enable.
Ten levels, 7.991 ns data delay (6.157 ns routing), final enable fanout 71.
The exact fault simplification is functionally sound in these tests but does
not solve the full completion-control dependency.

## Next step

On the better reference, inspect final-data/tag capture together with bank
metadata selection. Separate private capture/hold from small publication
authorization using local registered ownership. Preserve exact final-word
identity, immediate fault vetoes, reset cancellation and real reader ACK before
reuse. Prove against the actual adapter and FFT, then route before further
features. Do not combine a routed regression or remove TX to address this path.

Native **60 MS/s fine search** and **2.5 MS/s CI16 IIO inspection** remain
required. Full receiver timing/CDC/reset/board constraints, sustained capture,
actual 60 MS/s RX calibration and Ethernet verification precede `.18` reversible
canary, then `.17` PPU Ethernet-only deployment with pinned rollback. Final
verification remains 300 seconds, 120 ms valid dwells and blind host GLRT.
No deployment ETA is established while these gates remain open.

## Reproducible evidence

[Archived sources, tests and route](20260911-staged-guardfault-evidence.tgz),
[verified receipt](20260911-staged-guardfault-evidence.json).
18,732,121 bytes, 10,154 regular members, all read-back verified.
SHA256 `1b0ca299c218820fb1c313823d228bf147aa7ae19ef4cb5f2689ef258ac29b0d`.

Prepared/actual/synth folders are `staged-guardfault-*-v1` under the recovery
root. Successful route is `staged-guardfault-route-v2`. The first route launch
was rejected for relative paths before routing; V2 supplies absolute paths.
First regression omitted private TMPDIR and failed Icarus preprocessing; the
same sources/tests pass in regression-v2 with explicit private TMPDIR. Both
failed attempts and successes are archived, without overwriting evidence.

Actual/synthesis/route elapsed: 111.49 / 97.03 / 45.97 seconds. Exact prepared
inventory `5cec30567067daef19715fd16b4b50f8c56569b917063df9067bc6e49d98477b`;
synthesis DCP `04e1391133570b09f0d40767701fcda7686173e78c849c437548cfa0dc8df2d1`;
routed DCP `19a0d27f9f3d17f83b9893259b7fc10cf1198f68ac7a47e06d8dfe59453a5d79`.
Independent audit confirms unchanged sources/checkpoints, not timing closure.
