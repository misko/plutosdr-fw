# Private descriptor capture improves timing; deployment remains gated

Implemented a local ownership-based enable for descriptor data. Values may load
privately before accepted completion; the acceptance edge freezes the exact
validated bundle through pending validation, publication and real reader release.
Public validation, current-fault vetoes and bank request/reader ACK checks remain.
The change removes the global completion/fault tree from 178 payload-bit enables.

## Verified results

- **64,512 actual generated-FFT numerical records match** the pinned reference.
  The CSV and six service intervals are unchanged. Normal service is 3659 fast
  clocks; the qualifying stalled case remains 4927 against the unchanged 5215
  bound. The deliberate 9000-clock reader stall retains no service-capacity claim.
- All previous reset/fault/admission/completion/replay/writer cases pass.
  Healthy-context monitoring checks 32,616 private loads, 74,846 holds and all
  18 accepted captures, plus the unchanged actual publication-authorization rule.
- Three added actual cases cover invalid/X lookup churn before completion,
  continued churn while the accepted descriptor is held through real reader
  completion, and a vendor fault exactly at poised completion. The two healthy
  cases each finish 512 correct reads and one release. The fault case privately
  loads data but produces no acceptance, publication, reads or release.
- **382 regression tests pass in 49.09 seconds.** The actual capture always-block
  is also compared against the pinned prior qualified-capture block over 80
  epochs, including reset, missing/X lookup evidence and descriptor mismatches.
  Five broken capture/validation variants fail. The initial unit wrapper omitted
  a simulation timescale; its failing logs are retained. Correcting the harness,
  without RTL changes, yields six passing tests. Actual FFT tests are separate.
- Actual simulation, synthesis and route finish in 108.78 / 103.43 / 57.70
  seconds. Independent source/checkpoint and physical report audits pass; a
  successful report audit does **not** mean that its measured timing passes.

## Physical comparison

| Candidate | Worst slack | Total negative slack | Failing setup endpoints |
|---|---:|---:|---:|
| Replay-only V1 | -2.265 ns | -1021.803 ns | 936 |
| Staged writer V2 | -3.251 ns | -1733.553 ns | 1364 |
| Private descriptor capture | **-1.969 ns** | **-813.676 ns** | **914** |

The wide enable bottleneck is removed. The worst path now ends at the single
`output_descriptor_pending_reg/D` input, still reached through publication phase,
metadata/fault qualification and completion acceptance: 12 levels, 7.631 ns data
delay including 5.687 ns routing. The next path, at -1.943 ns, feeds the inverse
guard's awaiting-ACK bit. Timing still fails at 914 / 13803 setup endpoints.

Hold +0.058 ns and pulse +1.830 ns pass; 8403 nets fully route, zero errors.
Resources: 2790 LUT / 5667 FF / 21 DSP / 15 RAMB18. Five critical CDC findings,
208 warnings and 114/124 unconstrained I/O remain. The device, generated FFT,
diagnostic 100/175 MHz clocks and route recipe are unchanged. No timing waiver,
full-receiver signoff or deployment is claimed.

## Next step and full deployment path

Stage producer-final validation and ownership transfer itself, considering the
completion and awaiting-ACK paths together. The final word and descriptor must
stay owned while validation is pending; bind the receipt to the exact job and
cancel it on fault/reset. Preserve the independent immediate publication veto
and actual reader ACK before reuse. Prove added latency, no duplicate close and
fault-edge cancellation with actual FFT tests, then route before new features.

Native **60 MS/s fine search** and independent **2.5 MS/s CI16 IIO inspection**
remain required. Full receiver timing/CDC/reset/board constraints, sustained
capture and actual 60 MS/s RX calibration precede `.18` reversible canary and
`.17` PPU Ethernet deployment with pinned rollback. Final verification remains
the 300-second scan, 120 ms valid dwells and blind host GLRT comparison. No radio,
PPU, main branch or primary production HDL gitlink changed in this increment.

## Preserved sources and evidence

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Folders: `staged-capture-prepared-v1`, `staged-capture-actual-v1`,
`staged-capture-synth-v1`, `staged-capture-route-v1`; all runs terminal.

Inventory: `b873108f88659eb8c17d206a5415718404146823d69119f56be446d6ef7c676a`.
CSV: `d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
Synthesis DCP: `19465164a70afe872316cd74ccdae505184299527d60a582d75629440babe50e`.
Routed DCP: `8dd7f2735482e3c6a0158693bf24340130770a51362182690bba43ffdc8e5d5b`.

[Verified source/results archive](20260911-staged-capture-evidence.tgz):
15,610,631 bytes, 7177 regular members, all read-back checked by SHA256 and size.
SHA256: `3211aa1f917858b60437aa668dff2ded21835a73d385b07a9e39d79d65335918`.
Contains frozen runtime/bench/vectors, actual logs/CSV, synthesis and route
checkpoints/reports, test evidence and the pinned prior capture RTL.

Implementation pushed to remote `codex/starlink-rx-only-do-not-merge-rom-prefetch`:
FW `fcc3dc20205243adf4fbfcf6a43312b35d7a3aa6`,
HDL `c25126a2ecf391344c6d50b483aef2ee5217ba26`. No merge into main.
